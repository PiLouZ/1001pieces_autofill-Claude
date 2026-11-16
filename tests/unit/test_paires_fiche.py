"""
Paires de réf. associées des lignes « Remplace » et « Équivalentes » d'une fiche
du site (CDC docs/cdc_import_fiches_site.md, § 5.4)

Une réf. Whirlpool / Indesit / Beko suivie d'une réf. d'un autre de ces groupes
est sa jumelle ; une suite de telles réf. est liée deux par deux si elle est
paire et sans deux réf. du même groupe dans une paire. Une réponse déjà
mémorisée n'est jamais remplacée ; la paire du code produit reste seule
« ligne 0 » ; une paire décochée dans la fenêtre n'est pas liée. Aucun réseau.
"""

from src.services.enregistrement_fiche_service import FicheAImporter
from src.utils.rapprochement_fiche.decisions import DecisionsFiche, planifier
from src.utils.rapprochement_fiche.paires_fiche import paires_de_la_ligne

from tests.unit.test_enregistrement_fiche import (
    CONFIG, Construite, _compte, _enregistrer, _fiche, _rapprocher,
)

CODE = ('481010467690', 'C00380758')
# Fiche 7234 du site (la 3ᵉ paire inversée, comme sur certaines fiches)
REMPLACE = ['480132102633', 'C00323671', '480132102002', 'C00314426',
            'C00320354', '481241848993']
ORIGINE = lambda ref: CONFIG.origine(ref).etiquette


def _paires(refs, principale=CODE[0]):
    paires, non_liees = paires_de_la_ligne('remplace', refs, principale, ORIGINE)
    return ([(p.principale, p.associee) for p in paires],
            [(n.references, n.raison) for n in non_liees])


def _associees(db):
    return set(db.conn.execute("SELECT ref_piece, associee FROM references_associees"))


def _groupe(db, ref):
    row = db.conn.execute("SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?",
                          [ref]).fetchone()
    return row[0] if row else None


class TestLigne:
    def test_paires_dans_l_ordre_principale_du_groupe_de_la_piece(self):
        assert _paires(REMPLACE) == ([('480132102633', 'C00323671'),
                                      ('480132102002', 'C00314426'),
                                      ('481241848993', 'C00320354')], [])

    def test_piece_indesit_principale_indesit(self):
        assert _paires(REMPLACE[:2], principale=CODE[1])[0] == [('C00323671', '480132102633')]

    def test_piece_d_une_autre_marque_premiere_du_site(self):
        assert _paires(['C00323671', '480132102633'], principale='00054178')[0] == [
            ('C00323671', '480132102633')]

    def test_suite_au_milieu_d_autres_marques(self):
        # Fiche 8865 : Indesit suivie de Whirlpool, après deux réf. BSH
        assert _paires(['93467637', '72X0079', 'C00316028', '481246688999'],
                       principale='255430009') == ([('C00316028', '481246688999')], [])

    def test_suite_impaire_entiere_non_liee_les_autres_oui(self):
        impaire = ['480132102633', 'C00323671', '480132102973']
        paires, non_liees = _paires(impaire + ['UKF7001AXX', 'C00314426', '480132102002'])
        assert paires == [('480132102002', 'C00314426')]
        assert non_liees == [(impaire, 'impair')]

    def test_meme_groupe_ou_doublon_non_lies(self):
        assert _paires(['480132102633', '480132102002'])[1] == [
            (['480132102633', '480132102002'], 'meme_groupe')]
        assert _paires(['480132102633', 'C00323671'] * 2)[1][0][1] == 'doublon'
        assert _paires(['C00380758', CODE[0]], principale=CODE[0])[1][0][1] == 'doublon'

    def test_reference_seule_rien_a_signaler(self):
        assert _paires(['481010464112']) == ([], [])
        assert _paires([]) == ([], [])


class TestEnregistrement:
    def test_paires_liees_puis_relues_sans_rien_ajouter(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        fiche = _fiche(code=CODE, remplace=REMPLACE)
        r = _rapprocher(b.db, fiche)
        assert [p.statut for p in r.paires] == ['nouveau'] * 3
        plan, res = _enregistrer(b.db, r)
        assert res.paires_liees == 3
        assert _associees(b.db) == {('480132102633', 'C00323671'),
                                    ('480132102002', 'C00314426'),
                                    ('481241848993', 'C00320354')}
        # Jumelles = équivalentes, dans le groupe de la pièce
        assert _groupe(b.db, 'C00323671') == _groupe(b.db, '480132102633') == _groupe(b.db, CODE[0])
        # Seule la paire du code produit est « ligne 0 » : la réf. proposée pour la
        # pièce reste C00380758
        zeros = {r for (r,) in b.cnx.execute(
            "SELECT ref_piece FROM piece_equivalence_groups WHERE ligne_fiche = 0")}
        assert zeros == {CODE[1]}
        assert b.db.reference_associee(CODE[0]) == (False, CODE[1])
        # Remplacements inchangés : chacun vers la réf. de même forme du code produit
        succ = dict(b.cnx.execute("SELECT ref_old, ref_new FROM piece_supersessions"))
        assert succ['480132102633'] == CODE[0] and succ['C00323671'] == CODE[1]

        relue = _rapprocher(b.db, fiche)
        assert [p.statut for p in relue.paires] == ['deja_present'] * 3
        assert planifier(relue, DecisionsFiche()).paires == []

    def test_ligne_d_equivalentes(self, tmp_path):
        # Fiche 7084 : code produit en paire, équivalentes en paire
        b = Construite(tmp_path)
        b.piece('484000000763')
        r = _rapprocher(b.db, _fiche(code=('484000000763', 'C00375308'),
                                     equivalentes=[['484000008424', 'C00379998']]))
        assert [(p.ligne, p.principale, p.associee) for p in r.paires] == [
            ('equivalentes', '484000008424', 'C00379998')]
        plan, res = _enregistrer(b.db, r)
        assert res.paires_liees == 1 and ('484000008424', 'C00379998') in _associees(b.db)

    def test_reponse_deja_donnee_jamais_remplacee(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        b.db.definir_references_associees([('480132102633', None)], '2026-01-01')
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE))
        assert [p.statut for p in r.paires] == ['conflit', 'nouveau', 'nouveau']
        assert 'aucune' in r.paires[0].raison
        plan, res = _enregistrer(b.db, r)
        assert res.paires_liees == 2
        assert ('480132102633', None) in _associees(b.db)
        assert not any(a == '480132102633' and c for a, c in _associees(b.db))

    def test_meme_reference_dans_deux_paires_de_la_fiche(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE[:2],
                                     equivalentes=[['480132102633', 'C00999999']]))
        assert [p.statut for p in r.paires] == ['nouveau', 'conflit']
        assert 'va déjà avec C00323671' in r.paires[1].raison

    def test_suite_impaire_aucune_paire_remplacements_gardes(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE[:5]))
        assert r.paires == [] and r.suites_non_liees[0].raison == 'impair'
        plan, res = _enregistrer(b.db, r)
        assert res.paires_liees == 0 and _compte(b.db, 'references_associees') == 0
        assert _compte(b.db, 'piece_supersessions') == 5


class TestSaisie:
    """Fenêtre d'import : Succession modifiée, paires décochées."""

    def _fiche_a_importer(self, b):
        b.piece(CODE[0])
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE))
        return FicheAImporter(r, planifier(r, DecisionsFiche()))

    def test_reference_retiree_sa_paire_n_est_pas_liee(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        p = f.appliquer(CODE[0], '', [r for r in REMPLACE if r != 'C00314426'], [],
                        f.equivalentes())
        assert [(a, b) for _, a, b in p.paires] == [('480132102633', 'C00323671'),
                                                    ('481241848993', 'C00320354')]

    def test_paire_decochee_puis_recochee(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        f.paires_decochees.add(frozenset(('480132102002', 'C00314426')))
        assert f.apercu_paires()['a_lier'] == 2
        p = f.appliquer(CODE[0], '', REMPLACE, [], f.equivalentes())
        assert ('remplace', '480132102002', 'C00314426') not in p.paires and len(p.paires) == 2
        f.paires_decochees.clear()
        assert len(f.appliquer(CODE[0], '', REMPLACE, [], f.equivalentes()).paires) == 3

    def test_inversion_principale_du_groupe_de_la_nouvelle_piece(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        for _ in range(2):          # rejouable : même résultat à chaque application
            p = f.appliquer(CODE[1], '', REMPLACE, [], [CODE[0]])
        assert p.paires[0] == ('remplace', 'C00323671', '480132102633')

    def test_apercu(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        a = f.apercu_paires()
        assert a['a_lier'] == 3 and a['non_liees'] == []
        assert [(p['ligne'], p['statut'], p['cochee']) for p in a['paires']] == [
            ('Remplace', 'nouveau', True)] * 3


def test_liste_dans_la_fenetre(tmp_path, qapp):
    """La liste montre une case par paire ; décocher met à jour la fiche."""
    from src.ui.liste_paires_fiche import ListePairesFiche
    b = Construite(tmp_path)
    b.piece(CODE[0])
    r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE + ['UKF7001AXX', 'C00309487', 'C00309488', '481010464112']))
    f = FicheAImporter(r, planifier(r, DecisionsFiche()))
    appels = []
    liste = ListePairesFiche(compact=True, au_changement=lambda: appels.append(1))
    liste.definir(f)
    assert liste.isVisibleTo(None) or not liste.isHidden()
    assert len(liste.cases) == 3 and '3 à lier' in liste.titre.text()
    next(iter(liste.cases.values())).setChecked(False)
    assert len(f.paires_decochees) == 1 and appels == [1] and '2 à lier' in liste.titre.text()
