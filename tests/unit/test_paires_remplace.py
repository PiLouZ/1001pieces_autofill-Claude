"""
Paires de « Remplace les références » (CDC docs/cdc_import_fiches_site.md, § 5.4)

Code produit en paire Whirlpool / Indesit : la ligne « Remplace » va par paires
(1ʳᵉ avec 2ᵉ, 3ᵉ avec 4ᵉ…), chaque paire devient réf. associée et équivalente.
Toute la ligne ou rien ; une réponse déjà mémorisée n'est jamais remplacée ;
la paire du code produit reste seule « ligne 0 ». Aucun accès réseau.
"""

from types import SimpleNamespace

from src.services.enregistrement_fiche_service import FicheAImporter
from src.utils.rapprochement_fiche.decisions import DecisionsFiche, planifier
from src.utils.rapprochement_fiche.paires_remplace import paires_de_la_ligne

from tests.unit.test_enregistrement_fiche import (
    CONFIG, Construite, _compte, _enregistrer, _fiche, _rapprocher,
)

CODE = ('481010467690', 'C00380758')
# Fiche 7234 du site (la 3ᵉ paire inversée, comme sur certaines fiches)
REMPLACE = ['480132102633', 'C00323671', '480132102002', 'C00314426',
            'C00320354', '481241848993']
ORIGINE = lambda ref: CONFIG.origine(ref).etiquette


def _paires(remplace, code=CODE, principale=CODE[0]):
    paires, raison = paires_de_la_ligne(code, remplace, principale, ORIGINE)
    return [(p.principale, p.associee) for p in paires], raison


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
                                      ('481241848993', 'C00320354')], '')

    def test_piece_indesit_principale_indesit(self):
        paires, _ = _paires(REMPLACE[:2], principale=CODE[1])
        assert paires == [('C00323671', '480132102633')]

    def test_toute_la_ligne_ou_rien(self):
        assert _paires(REMPLACE[:5]) == ([], 'impair')
        assert _paires(['480132102633', '480132102002']) == ([], 'formes')
        assert _paires(['480132102633', 'UKF7001AXX']) == ([], 'formes')
        assert _paires(['480132102633', 'C00323671'] * 2) == ([], 'doublon')
        assert _paires(['C00380758', '480132102633']) == ([], 'doublon')

    def test_code_produit_sans_paire(self):
        assert _paires(REMPLACE, code=(CODE[0],)) == ([], 'code_produit')
        assert _paires(REMPLACE, code=(CODE[0], '481010467691')) == ([], 'code_produit')

    def test_ligne_vide(self):
        assert _paires([]) == ([], '')


class TestEnregistrement:
    def test_paires_liees_puis_relues_sans_rien_ajouter(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        fiche = _fiche(code=CODE, remplace=REMPLACE)
        r = _rapprocher(b.db, fiche)
        assert [p.statut for p in r.paires_remplace] == ['nouveau'] * 3
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
        assert [p.statut for p in relue.paires_remplace] == ['deja_present'] * 3
        assert planifier(relue, DecisionsFiche()).paires_remplace == []

    def test_reponse_deja_donnee_jamais_remplacee(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        b.db.definir_references_associees([('480132102633', None)], '2026-01-01')
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE))
        assert [p.statut for p in r.paires_remplace] == ['conflit', 'nouveau', 'nouveau']
        assert 'aucune' in r.paires_remplace[0].raison
        plan, res = _enregistrer(b.db, r)
        assert res.paires_liees == 2
        assert ('480132102633', None) in _associees(b.db)
        assert not any(a == '480132102633' and c for a, c in _associees(b.db))

    def test_ligne_mal_formee_aucune_paire_remplacements_gardes(self, tmp_path):
        b = Construite(tmp_path)
        b.piece(CODE[0])
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE[:5]))
        assert (r.paires_remplace, r.paires_sans) == ([], 'impair')
        plan, res = _enregistrer(b.db, r)
        assert res.paires_liees == 0 and _compte(b.db, 'references_associees') == 0
        assert _compte(b.db, 'piece_supersessions') == 5


class TestSaisie:
    """Succession modifiée dans la fenêtre d'import."""

    def _fiche_a_importer(self, b):
        b.piece(CODE[0])
        r = _rapprocher(b.db, _fiche(code=CODE, remplace=REMPLACE))
        return FicheAImporter(r, planifier(r, DecisionsFiche()))

    def test_reference_retiree_sa_paire_n_est_pas_liee(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        p = f.appliquer(CODE[0], '', [r for r in REMPLACE if r != 'C00314426'], [],
                        f.equivalentes())
        assert p.paires_remplace == [('480132102633', 'C00323671'),
                                     ('481241848993', 'C00320354')]

    def test_paire_du_code_produit_retiree_aucune_paire(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        p = f.appliquer(CODE[0], '', REMPLACE, [], [])
        assert p.paires_remplace == []

    def test_inversion_principale_du_groupe_de_la_nouvelle_piece(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        for _ in range(2):          # rejouable : même résultat à chaque application
            p = f.appliquer(CODE[1], '', REMPLACE, [], [CODE[0]])
        assert p.paires_remplace[0] == ('C00323671', '480132102633')

    def test_apercu(self, tmp_path):
        f = self._fiche_a_importer(Construite(tmp_path))
        a = f.apercu()['paires']
        assert (a['a_lier'], a['deja'], a['conflits'], a['sans']) == (3, 0, [], '')
