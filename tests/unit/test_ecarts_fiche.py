"""Appareil connu dont un champ diffère sur la fiche (CDC § 10.11, point 2, et § 10.20).

Le rapprochement relève les champs qui diffèrent ; l'import garde la valeur de
l'outil (jamais écrasée) et ne complète qu'un nom commercial vide.
Base construite par DatabaseManager, sans réseau ni réglage du poste.
"""

from types import SimpleNamespace

from src.utils.lecteur_fiche.page_publique import LigneTableSite
from src.utils.rapprochement_fiche.decisions import planifier
from tests.unit.test_enregistrement_fiche import (
    Construite, _decisions, _enregistrer, _fiche, _rapprocher, _service,
)


def _ecarts(r, n=0):
    return [(e.champ, e.outil, e.site) for e in r.appareils[n].ecarts if not e.tranche]


def _ligne(b, **kw):
    return b.db.conn.execute(
        "SELECT type, manufacturer, ref_modele, commercial_ref FROM appareils WHERE id = ?",
        [kw['ident']]).fetchone()


class TestDetection:
    def test_type_de_la_table_du_site(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'XXX - XYZ', 'Lave-linge')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'XXX - XYZ')]),
                        table_site=[LigneTableSite('Sèche-linge', 'Bosch', 'XXX - XYZ', '')])
        a = r.appareils[0]
        assert a.niveau == 'exact' and a.appareil_id == ident and not a.doutes
        assert _ecarts(r) == [('type', 'Lave-linge', 'Sèche-linge')]

    def test_ecriture_de_la_ref_et_nom_commercial(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        b.appareil('Bosch', 'WAE24/01', nom='Serie 4')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'WAE2401', 'Maxx 6')]))
        assert r.appareils[0].niveau == 'normalise'
        assert _ecarts(r) == [('ref', 'WAE24/01', 'WAE2401'), ('nom', 'Serie 4', 'Maxx 6')]

    def test_nom_a_la_ponctuation_pres_et_nom_vide(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        b.appareil('Bosch', 'A1', nom='VF 3017')
        b.appareil('Bosch', 'A2', nom='')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'A1', 'VF3017'), ('Bosch', 'A2', 'Logixx')]))
        assert _ecarts(r, 0) == []
        assert _ecarts(r, 1) == [('nom', '', 'Logixx')] and r.appareils[1].ecarts[0].a_completer

    def test_marque_seulement_dans_le_groupe(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        b.appareil('Siemens', 'WM14/01')            # même groupe BSH que Bosch
        b.appareil('Ikea', 'HX99')                  # hors groupe
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'WM14/01'), ('Whirlpool', 'HX99')]))
        assert r.appareils[0].motif == 'meme_ref_groupe'
        assert _ecarts(r, 0) == [('marque', 'Siemens', 'Bosch')]
        assert _ecarts(r, 1) == []


class TestChoix:
    def test_sans_choix_l_outil_est_garde(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'XXX - XYZ', 'Lave-linge', 'Serie 4')
        fiche = _fiche(lignes=[('Bosch', 'XXX - XYZ', 'Serie 6', 'Sèche-linge')])
        r = _rapprocher(b.db, fiche)
        plan, _ = _enregistrer(b.db, r)
        assert not plan.maj_appareils
        assert _ligne(b, ident=ident) == ('Lave-linge', 'Bosch', 'XXX - XYZ', 'Serie 4')
        # Relecture : l'écart est toujours relevé, rien n'est écrit
        assert _ecarts(_rapprocher(b.db, fiche)) == [('type', 'Lave-linge', 'Sèche-linge'),
                                                    ('nom', 'Serie 4', 'Serie 6')]

    def test_nom_vide_complete_puis_relecture_sans_ecart(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'WAE24/01', 'Lave-linge', '')
        fiche = _fiche(lignes=[('Bosch', 'WAE2401', 'Maxx 6', 'Sèche-linge')])
        r = _rapprocher(b.db, fiche)
        plan, res = _enregistrer(b.db, r)
        # Nom vide dans l'outil : complété ; type et écriture de l'outil gardés
        assert plan.maj_appareils == {ident: {'commercial_ref': 'Maxx 6'}}
        assert res.champs_modifies == 1
        assert _ligne(b, ident=ident) == ('Lave-linge', 'Bosch', 'WAE24/01', 'Maxx 6')
        r2 = _rapprocher(b.db, fiche)
        assert planifier(r2, _decisions(r2)).vide

    def test_ligne_ignoree_nom_vide_non_complete(self, tmp_path):
        from src.utils.rapprochement_fiche.decisions import ChoixAppareil
        b = Construite(tmp_path)
        b.piece('REFP')
        b.appareil('Bosch', 'A1', 'Lave-linge', '')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'A1', 'Nom', 'Four')]))
        d = _decisions(r)
        d.appareils[0] = ChoixAppareil(ignorer=True)
        assert not planifier(r, d).maj_appareils

    def test_ecriture_par_la_sauvegarde_evenementielle(self, tmp_path):
        """Avec une fenêtre : le nom complété passe par EventDrivenSaveService."""
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'A1', 'Lave-linge', '')
        appels = []

        def enregistrer_champs_appareils(maj):
            appels.append(maj)
            return b.db.update_multiple_cells_batch(maj)
        fenetre = SimpleNamespace(event_driven_save_service=SimpleNamespace(
            enregistrer_champs_appareils=enregistrer_champs_appareils,
            save_after_import=lambda *_: True))
        service = _service(b.db)
        service.parent_window = fenetre
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'A1', 'Logixx', 'Four')]))
        res = service.enregistrer(planifier(r, _decisions(r)))
        assert res.ok and appels == [{ident: {'commercial_ref': 'Logixx'}}]
        assert _ligne(b, ident=ident) == ('Lave-linge', 'Bosch', 'A1', 'Logixx')


def test_noms_qui_ne_sont_pas_des_ecarts():
    from src.utils.rapprochement_fiche.rapprochement import _noms_differents
    assert not _noms_differents('AZB8200', 'AZB 82001')          # indice de version
    assert not _noms_differents('HR 6325', 'HR6325')             # ponctuation
    assert not _noms_differents('ASC10', 'ASC10 854001038001 ASC10')   # liste lue comme un nom
    assert _noms_differents('EXCELLENCE7670', 'EXCELLENCE 7671')
    assert _noms_differents('Serie 4', 'Serie 6')
    assert _noms_differents('', 'Logixx')                         # vide : complété
