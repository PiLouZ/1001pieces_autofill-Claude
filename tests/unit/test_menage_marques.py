"""
Ménage des marques (2026-11-24).

- règle du mot collé : marque seulement, séparée par un espace, reste avec un
  chiffre, chauffage et désignations jamais touchés ;
- alias de marques : « Glem » → « Glem Gas », « Concord » → « Concorde », à
  l'import comme à la saisie ;
- liste calculée : références, marques, fusions (garde l'appareil intact le plus
  ancien, jamais deux types différents) ;
- service : simulation, écriture (historique, pièces transférées, comptage),
  second passage sans effet, retour arrière hors fusions, garde « valeur changée » ;
- import : les deux chemins retirent la marque collée et retrouvent l'appareil
  propre (pas de doublon) ; aperçu et historique l'annoncent ;
- liste versionnée lisible et cohérente.
"""

import sqlite3
from pathlib import Path

import pytest

from src.core.config import Config
from src.core.import_manager import (FileType, ImportConfiguration, ImportFile, ImportManager,
                                     ImportType, LabelConfiguration)
from src.data.database_manager import DatabaseManager
from src.services.casse_normalisation_service import CasseNormalisationService
from src.services.menage_marques_service import (
    NATURE_FUSION, NATURE_MARQUE, NATURE_REFERENCE, SENS_ANNULER, LigneMenage,
    MenageMarquesService, calculer_liste, ecrire_liste, lire_liste)
from src.utils.marque_collee import retirer_marque_collee

RACINE = Path(__file__).resolve().parents[2]
LISTE = RACINE / 'data' / 'corrections' / 'menage_marques.csv'


# ── Règle du mot collé ──────────────────────────────────────────────────────

@pytest.mark.parametrize('reference, marque, type_, attendu', [
    ('SMEG ST995', 'Smeg', 'Lave-vaisselle', 'ST995'),
    ('ST995 SMEG', 'Smeg', 'Lave-vaisselle', 'ST995'),
    ('XHD540IX GLEMGAS', 'Glem Gas', 'Hotte', 'XHD540IX'),
    ('GLEM GAS XHD540IX', 'Glem Gas', 'Hotte', 'XHD540IX'),
    ('LG WD-11401TB', 'LG', 'Lave-linge', 'WD-11401TB'),
    ('FTC 922 XS FRANKE', 'Franke', 'Hotte', 'FTC 922 XS'),
    ('SMEGST2FABBL2', 'Smeg', 'Lave-vaisselle', 'SMEGST2FABBL2'),     # collé sans espace
    ('SOG ABC123', 'Haier', 'Four', 'SOG ABC123'),                     # pas la marque
    ('SMEG LVFABCR', 'Smeg', 'Lave-vaisselle', 'SMEG LVFABCR'),        # reste sans chiffre
    ('SMEG', 'Smeg', 'Four', 'SMEG'),
    ('SAUTER VENISE VENTILO 1500 W', 'Sauter', 'Chauffage', 'SAUTER VENISE VENTILO 1500 W'),
    ('EQUATION 75L HM MONO STEATITE', 'Equation', 'Chauffe-eau', 'EQUATION 75L HM MONO STEATITE'),
    ('SAUTER VENISE VENTILO 1500 W', 'Sauter', '', 'SAUTER VENISE VENTILO 1500 W'),  # sans type
    ('SMEG TR93GR SI02', 'Smeg', '', 'TR93GR SI02'),
    ('ST995', 'Smeg', 'Four', 'ST995'),
    ('', 'Smeg', 'Four', ''),
    ('SMEG ST995', '', 'Four', 'SMEG ST995'),
])
def test_retirer_marque_collee(reference, marque, type_, attendu):
    assert retirer_marque_collee(reference, marque, type_) == attendu


# ── Alias de marques ────────────────────────────────────────────────────────

class _Base:
    def __init__(self, valeurs):
        self.valeurs = valeurs

    def valeurs_frequentes_colonne(self, colonne):
        return [(v, 1) for v in self.valeurs]

    def valeurs_colonne(self, colonne):
        return [(v,) for v in self.valeurs]


def test_alias_de_marques():
    service = CasseNormalisationService(_Base(['Glem Gas', 'Concorde', 'Glem']), 'manufacturer')
    service.charger()
    assert [service.normaliser(v) for v in ('Glem', 'GLEM', 'Concord', 'CONCORDE', 'Glem Gas')] == \
        ['Glem Gas', 'Glem Gas', 'Concorde', 'Concorde', 'Glem Gas']
    assert ('Glem', 'Glem Gas', 1) in service.alignements()
    # Base vide : l'alias donne le nom
    vide = CasseNormalisationService(_Base([]), 'manufacturer')
    assert vide.normaliser('CONCORD') == 'Concorde'
    # Les types ne sont pas concernés
    assert CasseNormalisationService(_Base([]), 'type').normaliser('Glem') == 'Glem'


# ── Liste calculée ──────────────────────────────────────────────────────────

APPAREILS = [
    # id, type, marque, ref_modele, commercial_ref
    (1, 'Lave-linge', 'Smeg', '46TLD/DIT', '46TL'),             # propre, ancien → gardé
    (2, 'Lave-linge', 'Smeg', 'SMEG 46TLD/DIT', '46TL SMEG'),   # → fusion dans 1
    (3, 'Four', 'Smeg', 'SMEG SE210P', 'SE210P SMEG'),          # nettoyé, sans doublon
    (4, 'Hotte', 'Glem', '07001920', 'K24'),                    # marque renommée
    (5, 'Chauffage', 'Sauter', '591015', 'SAUTER VENISE VENTILO 1500 W'),   # intact
    (6, 'Four', 'Haier', 'SOG ABC123', 'ABC123 SOG'),           # pas la marque : intact
    (7, 'Lave-linge', 'Far', 'FAR L61200', 'L61200 FAR'),       # nettoyé
    (8, 'Sèche-linge', 'Far', 'L61200', 'L61200'),              # même réf., autre type : pas de fusion
    (9, 'Lave-vaisselle', 'Smeg', 'SMEG LSA6447X2', 'LSA6447X2 SMEG'),   # deux sales identiques
    (10, 'Lave-vaisselle', 'Smeg', 'LSA6447X2 SMEG', 'SMEG LSA6447X2'),  # → fusion dans 9
]


def test_calculer_liste():
    lignes = calculer_liste(APPAREILS)
    par = {(l.nature, l.appareil_id, l.champ): l for l in lignes}
    assert par[(NATURE_MARQUE, 4, 'manufacturer')].apres == 'Glem Gas'
    assert par[(NATURE_REFERENCE, 2, 'ref_modele')].apres == '46TLD/DIT'
    assert par[(NATURE_REFERENCE, 3, 'commercial_ref')].apres == 'SE210P'
    assert par[(NATURE_FUSION, 2, '')].cible == 1
    assert par[(NATURE_FUSION, 10, '')].cible == 9
    assert not any(l.appareil_id in (1, 5, 6) for l in lignes)
    assert not any(l.nature == NATURE_FUSION and l.appareil_id in (7, 8) for l in lignes)
    # ordre : marques, références, fusions
    natures = [l.nature for l in lignes]
    assert natures == sorted(natures, key=[NATURE_MARQUE, NATURE_REFERENCE, NATURE_FUSION].index)


def test_liste_relue_identique(tmp_path):
    lignes = calculer_liste(APPAREILS)
    chemin = tmp_path / 'menage.csv'
    ecrire_liste(chemin, lignes)
    assert lire_liste(chemin) == lignes


def test_liste_invalide(tmp_path):
    chemin = tmp_path / 'faux.csv'
    chemin.write_text("nature;id;marque;champ;avant;apres;cible\nfusion;2;Smeg;;a;;2\n", encoding='utf-8')
    with pytest.raises(ValueError, match="cible"):
        lire_liste(chemin)
    chemin.write_text("nature;id;marque;champ;avant;apres;cible\nreference;2;Smeg;type;a;b;\n",
                      encoding='utf-8')
    with pytest.raises(ValueError, match="champ"):
        lire_liste(chemin)


# ── Service ─────────────────────────────────────────────────────────────────

@pytest.fixture
def base(tmp_path):
    chemin = str(tmp_path / 'menage.db')
    origine, recherche = Config.DB_FILE, Config.SEARCH_PIECES_ONLY
    Config.DB_FILE, Config.SEARCH_PIECES_ONLY = chemin, False
    db = DatabaseManager(chemin)
    cnx = sqlite3.connect(chemin)
    cnx.executemany("INSERT INTO appareils(id, type, manufacturer, ref_modele, commercial_ref) "
                    "VALUES (?, ?, ?, ?, ?)", APPAREILS)
    cnx.executemany("INSERT INTO pieces(id, ref_piece) VALUES (?, ?)", [(1, 'P1'), (2, 'P2'), (3, 'P3')])
    cnx.execute("INSERT INTO reference_decisions(ref_modele, decision) VALUES ('SMEG SE210P', 'DISTINCT')")
    cnx.executemany("INSERT INTO piece_associations(piece_id, appareil_id) VALUES (?, ?)",
                    [(1, 1), (1, 2), (2, 2), (3, 10)])
    cnx.commit()
    cnx.close()
    yield db, chemin
    db.close()
    Config.DB_FILE, Config.SEARCH_PIECES_ONLY = origine, recherche


def _appareils(db):
    return {r[0]: r[1:] for r in db.execute_query(
        "SELECT id, manufacturer, ref_modele, commercial_ref FROM appareils")}


def _pieces(db, ident):
    return sorted(r[0] for r in db.execute_query(
        "SELECT piece_id FROM piece_associations WHERE appareil_id = ?", (ident,)))


def test_simulation_n_ecrit_rien(base):
    db, _ = base
    service = MenageMarquesService(db)
    avant = _appareils(db)
    bilan = service.preparer(calculer_liste(service.lire_appareils()))
    assert bilan.par_nature() == {NATURE_MARQUE: 1, NATURE_REFERENCE: 10, NATURE_FUSION: 2}
    assert _appareils(db) == avant


def test_ecriture_fusion_historique_puis_annulation(base):
    db, _ = base
    service = MenageMarquesService(db)
    lignes = calculer_liste(service.lire_appareils())
    bilan = service.executer(lignes)
    assert bilan.ecrit and bilan.historique_ecrit and bilan.comptage_conforme
    assert bilan.fusions_ecrites == 2
    app = _appareils(db)
    assert 2 not in app and 10 not in app
    assert app[3] == ('Smeg', 'SE210P', 'SE210P')
    assert app[4][0] == 'Glem Gas'
    assert app[5] == ('Sauter', '591015', 'SAUTER VENISE VENTILO 1500 W')
    assert app[9] == ('Smeg', 'LSA6447X2', 'LSA6447X2')
    assert _pieces(db, 1) == [1, 2]          # P2 transférée, P1 non doublée
    assert _pieces(db, 9) == [3]
    assert db.execute_query("SELECT COUNT(*) FROM piece_associations WHERE appareil_id "
                            "NOT IN (SELECT id FROM appareils)")[0][0] == 0
    histo = db.execute_query("SELECT action_type, title, field_name FROM modifications_history")
    assert ('edit', "[Référence modèle]  'SMEG SE210P' → 'SE210P'", 'Référence modèle') in histo
    assert ('edit', "[Fabricant]  'Glem' → 'Glem Gas'", 'Fabricant') in histo
    assert sum(1 for h in histo if h[0] == 'delete') == 2
    assert db.execute_query("SELECT ref_modele FROM reference_decisions") == [('SE210P',)]

    # Second passage : rien à faire
    second = service.preparer(lignes)
    assert not second.a_faire and not second.ignorees

    # Retour arrière : références et marques, pas les fusions
    retour = service.executer(lignes, SENS_ANNULER)
    assert retour.fusions_ecrites == 0
    app = _appareils(db)
    assert app[3] == ('Smeg', 'SMEG SE210P', 'SE210P SMEG')
    assert app[4][0] == 'Glem'
    assert db.execute_query("SELECT ref_modele FROM reference_decisions") == [('SMEG SE210P',)]
    assert any('restaurant la sauvegarde' in raison for _, raison in retour.ignorees)


def test_valeur_changee_depuis_la_liste_jamais_ecrasee(base):
    db, _ = base
    service = MenageMarquesService(db)
    lignes = calculer_liste(service.lire_appareils())
    db.update_multiple_cells_batch({3: {'ref_modele': 'SE210P-MAIN'}})
    bilan = service.executer(lignes)
    assert _appareils(db)[3][1] == 'SE210P-MAIN'
    assert any(l.appareil_id == 3 and 'SE210P-MAIN' in raison for l, raison in bilan.ignorees)


# ── Import ──────────────────────────────────────────────────────────────────

REFERENCES = [("REF_TEST", "libelle")]


def _config():
    fichier = ImportFile(path='/tmp/inexistant.csv', type=FileType.CSV, suggested_reference='REF_TEST')
    config = ImportConfiguration(
        files=[fichier], import_type=ImportType.SINGLE_FILE, common_reference='REF_TEST',
        use_common_reference=True, label_config=LabelConfiguration(), individual_references={},
        individual_labels={}, csv_import_mode=2, has_headers=False)
    return config, fichier


@pytest.mark.parametrize('chemin_import', ['standard', 'batch'])
def test_import_retire_la_marque_et_retrouve_l_appareil(base, chemin_import):
    db, _ = base
    avant = len(_appareils(db))
    manager = ImportManager(db_manager=db, parent_widget=None)
    manager._reinitialiser_etat_session()
    config, fichier = _config()
    traiter = (manager._process_data_import if chemin_import == 'standard'
               else manager._process_data_import_batch)
    traiter([['Lave-linge', 'SMEG', 'SMEG 46TLD/DIT', '46TL SMEG'],      # = appareil 1
             ['Four', 'Smeg', 'SMEG SF6400', 'SF6400 SMEG'],              # nouveau, propre
             ['Hotte', 'GLEM', 'GLEMGAS GHC63BK', 'GHC63BK GLEMGAS'],     # alias + retrait
             ['Chauffage', 'Sauter', '591016', 'SAUTER VENISE 2000 W']],  # intact
            REFERENCES, config, fichier, set())
    app = {(m, r, c) for m, r, c in _appareils(db).values()}
    assert ('Smeg', 'SF6400', 'SF6400') in app
    assert ('Glem Gas', 'GHC63BK', 'GHC63BK') in app
    assert ('Sauter', '591016', 'SAUTER VENISE 2000 W') in app
    assert len(_appareils(db)) == avant + 3                    # 46TLD/DIT retrouvé
    assert 1 in {r[0] for r in db.execute_query(
        "SELECT pa.appareil_id FROM piece_associations pa JOIN pieces p ON p.id = pa.piece_id "
        "WHERE p.ref_piece = 'REF_TEST'")}
    results = {}
    manager._tracer_completions_et_alignements(results)
    assert dict(results['marques_retirees_des_refs']) == {'Smeg': 4, 'Glem Gas': 2}
    assert ('GLEM', 'Glem Gas', 1) in results['marques_alignees']


def test_lignes_d_historique():
    from src.ui.main_refactored import MainWindow
    texte = MainWindow._lignes_alignements({'marques_retirees_des_refs': [('Far', 2), ('Smeg', 12)]},
                                           retrait="  ")
    assert texte == ("  ==> Marque retirée des références :\n"
                     "  - Far (2)\n"
                     "  - Smeg (12)\n")


def test_fenetre_de_confirmation_avec_style_global(qapp):
    from PyQt5.QtWidgets import QLabel
    from src.ui.fenetre_import import ImportPreviewDialog
    from src.ui.style_manager import StyleManager
    ancien = qapp.styleSheet()
    qapp.setStyleSheet(StyleManager.get_modern_style())
    try:
        resultats = {'new_entries': 5, 'file_details': [{'filename': 'a.pdf'}],
                     'marques_retirees_des_refs': [('Smeg', 12), ('Far', 2)]}
        dlg = ImportPreviewDialog(resultats, config=None)
        dlg.show()
        qapp.processEvents()
        textes = [l.text() for l in dlg.findChildren(QLabel)]
        assert "<b>Orthographe alignée sur la base</b>" in textes
        assert "Marque retirée des références :" in textes
        assert "    Smeg (12), Far (2)" in textes
        dlg.close()
    finally:
        qapp.setStyleSheet(ancien)


# ── Liste versionnée ────────────────────────────────────────────────────────

def test_liste_versionnee_lisible():
    lignes = lire_liste(LISTE)
    assert len(lignes) == 6944
    natures = {n: sum(1 for l in lignes if l.nature == n) for n in (NATURE_MARQUE, NATURE_REFERENCE, NATURE_FUSION)}
    assert natures == {NATURE_MARQUE: 9, NATURE_REFERENCE: 6906, NATURE_FUSION: 29}
    # Chaque référence nettoyée suit la règle
    for l in lignes:
        if l.nature == NATURE_REFERENCE:
            assert retirer_marque_collee(l.avant, l.marque) == l.apres, l
        if l.nature == NATURE_MARQUE:
            assert l.apres in ('Glem Gas', 'Concorde'), l
