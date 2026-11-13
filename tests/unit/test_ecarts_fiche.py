"""Appareil connu dont un champ diffère sur la fiche (CDC § 10.11, point 2).

Base construite par DatabaseManager, sans réseau ni réglage du poste.
"""

from types import SimpleNamespace

from src.utils.lecteur_fiche.page_publique import LigneTableSite
from src.utils.rapprochement_fiche.decisions import planifier
from tests.unit.test_enregistrement_fiche import (
    Construite, _enregistrer, _fiche, _rapprocher, _service, _tout_valider,
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
        assert not plan.maj_appareils and not plan.decisions_champs
        assert _ligne(b, ident=ident) == ('Lave-linge', 'Bosch', 'XXX - XYZ', 'Serie 4')
        # Relecture : rien de décidé, l'écart est reproposé
        assert _ecarts(_rapprocher(b.db, fiche)) == [('type', 'Lave-linge', 'Sèche-linge'),
                                                    ('nom', 'Serie 4', 'Serie 6')]

    def test_prendre_le_site_puis_relecture_sans_ecart(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'WAE24/01', 'Lave-linge', '')
        fiche = _fiche(lignes=[('Bosch', 'WAE2401', 'Maxx 6', 'Sèche-linge')])
        r = _rapprocher(b.db, fiche)
        d = _tout_valider(r)
        d.champs[(0, 'type')] = 'site'
        d.champs[(0, 'ref')] = 'site'
        plan, res = _enregistrer(b.db, r, d)
        # Nom vide dans l'outil : complété sans question
        assert plan.maj_appareils == {ident: {'type': 'Sèche-linge', 'ref_modele': 'WAE2401',
                                              'commercial_ref': 'Maxx 6'}}
        assert res.champs_modifies == 3
        assert _ligne(b, ident=ident) == ('Sèche-linge', 'Bosch', 'WAE2401', 'Maxx 6')
        r2 = _rapprocher(b.db, fiche)
        assert r2.appareils[0].niveau == 'exact' and _ecarts(r2) == []
        assert planifier(r2, _tout_valider(r2)).vide

    def test_garder_l_outil_memorise_puis_repropose_si_le_site_change(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'XXX - XYZ', 'Lave-linge')
        fiche = _fiche(lignes=[('Bosch', 'XXX - XYZ', '', 'Sèche-linge')])
        r = _rapprocher(b.db, fiche)
        d = _tout_valider(r)
        d.champs[(0, 'type')] = 'outil'
        plan, _ = _enregistrer(b.db, r, d)
        assert plan.decisions_champs == [(ident, 'type', 'Sèche-linge')]
        assert _ligne(b, ident=ident)[0] == 'Lave-linge'
        r2 = _rapprocher(b.db, fiche)
        assert r2.appareils[0].ecarts[0].tranche and _ecarts(r2) == []
        assert planifier(r2, _tout_valider(r2)).vide
        # Le site donne un autre type : de nouveau proposé
        r3 = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'XXX - XYZ', '', 'Four')]))
        assert _ecarts(r3) == [('type', 'Lave-linge', 'Four')]

    def test_ligne_laissee_de_cote_rien_n_est_ecrit(self, tmp_path):
        from src.utils.rapprochement_fiche.decisions import ChoixAppareil
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'A1', 'Lave-linge', '')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'A1', 'Nom', 'Four')]))
        d = _tout_valider(r)
        d.appareils[0] = ChoixAppareil(ignorer=True)
        d.champs[(0, 'type')] = 'site'
        plan = planifier(r, d)
        assert not plan.maj_appareils and not plan.decisions_champs
        assert _ligne(b, ident=ident)[0] == 'Lave-linge'

    def test_ecriture_par_la_sauvegarde_evenementielle(self, tmp_path):
        """Avec une fenêtre : les champs passent par EventDrivenSaveService."""
        b = Construite(tmp_path)
        b.piece('REFP')
        ident = b.appareil('Bosch', 'A1', 'Lave-linge')
        appels = []

        def enregistrer_champs_appareils(maj):
            appels.append(maj)
            return b.db.update_multiple_cells_batch(maj)
        fenetre = SimpleNamespace(event_driven_save_service=SimpleNamespace(
            enregistrer_champs_appareils=enregistrer_champs_appareils,
            save_after_import=lambda *_: True))
        service = _service(b.db)
        service.parent_window = fenetre
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'A1', '', 'Four')]))
        d = _tout_valider(r)
        d.champs[(0, 'type')] = 'site'
        res = service.enregistrer(planifier(r, d))
        assert res.ok and appels == [{ident: {'type': 'Four'}}]
        assert _ligne(b, ident=ident)[0] == 'Four'


def test_noms_qui_ne_sont_pas_des_ecarts():
    from src.utils.rapprochement_fiche.rapprochement import _noms_differents
    assert not _noms_differents('AZB8200', 'AZB 82001')          # indice de version
    assert not _noms_differents('HR 6325', 'HR6325')             # ponctuation
    assert not _noms_differents('ASC10', 'ASC10 854001038001 ASC10')   # liste lue comme un nom
    assert _noms_differents('EXCELLENCE7670', 'EXCELLENCE 7671')
    assert _noms_differents('Serie 4', 'Serie 6')
    assert _noms_differents('', 'Logixx')                         # vide : complété
