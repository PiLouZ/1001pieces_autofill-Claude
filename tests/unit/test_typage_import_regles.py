"""
Lot 5 — typage à l'import par les règles de nomenclature (CDC § 8.3).

- type vide (ou auto-complété par référence) + règle validée → type de la règle,
  tracé comme une auto-complétion « à vérifier » (source « règle de nomenclature … ») ;
- type du fichier contredit par une règle → gardé, proposition de type (D18) ;
- type hors liste → gardé, signalé (D19) ;
- refus mémorisé jamais réécrit ; règle seulement proposée sans effet ;
  accessoire jamais retypé ; les deux chemins d'import donnent le même résultat.
"""

import os
import sqlite3

import pytest

from src.core.config import Config
from src.core.import_manager import (FileType, ImportConfiguration, ImportFile, ImportManager,
                                     ImportType, LabelConfiguration)
from src.data.database_manager import DatabaseManager
from src.services.regle_nomenclature_service import RegleNomenclatureService
from src.services.typage_import_service import PREFIXE_SOURCE_REGLE, est_source_de_regle

REFERENCES = [("REF_TEST", "libelle")]

REGLES = [
    {'portee': 'marque', 'cible': 'Gaggenau', 'cle': 'nom', 'motif': 'BS*',
     'type_resultat': 'Four vapeur', 'statut': 'validee', 'origine': 'web',
     'source_url': 'https://example.invalid/bs'},
    {'portee': 'marque', 'cible': 'Liebherr', 'cle': 'nom', 'motif': 'G*',
     'type_resultat': 'Congélateur', 'statut': 'validee', 'origine': 'saisie'},
    # Seulement proposée : ne type jamais (§ 6.2, D4)
    {'portee': 'marque', 'cible': 'Bosch', 'cle': 'nom', 'motif': 'HMG*',
     'type_resultat': 'Four combiné micro-ondes', 'statut': 'proposee', 'origine': 'decouverte'},
]

# Colonnes positionnelles : type, fabricant, ref_modele, commercial_ref
LIGNES = [
    ['', 'Gaggenau', 'BS270100/01', 'BS270100'],                    # → Four vapeur (typé)
    ['Réfrigérateur', 'Liebherr', '998767602', 'GN 1013-21B 001'],  # contredit → proposition
    ['', 'Bosch', 'HMG636BS1/01', 'HMG636BS1'],                     # règle proposée : rien
    ['Cocotte', 'Seb', 'P4705100', 'Clipso'],                       # hors liste, gardé
    ['Accessoires', 'Gaggenau', 'BS999/01', 'BS999'],               # accessoire : intact
    ['', '', 'BS111/01', 'BS111'],                                  # sans marque : rien
    ['Four vapeur', 'Gaggenau', 'BS450110/01', 'BS450110'],         # déjà juste : rien
]


@pytest.fixture
def base(tmp_path):
    chemin = str(tmp_path / 'lot5.db')
    origine, recherche = Config.DB_FILE, Config.SEARCH_PIECES_ONLY
    Config.DB_FILE, Config.SEARCH_PIECES_ONLY = chemin, False
    db = DatabaseManager(chemin)
    bilan = RegleNomenclatureService(db).enregistrer_regles(REGLES)
    assert not bilan.refusees, bilan.refusees
    yield db, chemin
    db.close()
    Config.DB_FILE, Config.SEARCH_PIECES_ONLY = origine, recherche


def _config(fichier_path='/tmp/inexistant.csv'):
    fichier = ImportFile(path=fichier_path, type=FileType.CSV, suggested_reference='REF_TEST')
    config = ImportConfiguration(
        files=[fichier], import_type=ImportType.SINGLE_FILE, common_reference='REF_TEST',
        use_common_reference=True, label_config=LabelConfiguration(), individual_references={},
        individual_labels={}, csv_import_mode=2, has_headers=False)
    return config, fichier


def _importer(db, chemin_import, lignes):
    """Une session d'import par l'un des deux chemins, finalisation du typage comprise."""
    manager = ImportManager(db_manager=db, parent_widget=None)
    manager._reinitialiser_etat_session()
    manager._typage.charger()
    config, fichier = _config()
    traiter = (manager._process_data_import if chemin_import == 'standard'
               else manager._process_data_import_batch)
    traiter(lignes, REFERENCES, config, fichier, set())
    results = {}
    manager._constats_typage_regles(results, dry_run=False)
    if manager._typage.contredites:
        results['types_contredits'] = manager._typage.proposer_pour_contredits()
    return manager, results


def _appareils(db):
    return {(r[0], r[1]): (r[2], r[3]) for r in db.execute_query(
        "SELECT ref_modele, commercial_ref, type, manufacturer FROM appareils")}


def _traces(db):
    return {(r[0], r[1]): (r[2], r[3], r[4], r[5]) for r in db.execute_query(
        "SELECT a.ref_modele, t.champ, t.valeur, t.source, t.accord, t.total "
        "FROM appareils_autocompletes t JOIN appareils a ON a.id = t.appareil_id")}


def _propositions(db):
    return {r[0]: (r[1], r[2]) for r in db.execute_query(
        "SELECT a.ref_modele, p.type_actuel, p.type_propose FROM propositions_type p "
        "JOIN appareils a ON a.id = p.appareil_id")}


@pytest.mark.parametrize('chemin_import', ['standard', 'batch'])
def test_typage_contradiction_hors_liste(base, chemin_import):
    db, _ = base
    _, results = _importer(db, chemin_import, LIGNES)
    app = _appareils(db)
    assert app[('BS270100/01', 'BS270100')] == ('Four vapeur', 'Gaggenau')
    assert app[('998767602', 'GN 1013-21B 001')] == ('Réfrigérateur', 'Liebherr')  # gardé
    assert app[('HMG636BS1/01', 'HMG636BS1')][0] == ''        # règle proposée : rien
    assert app[('P4705100', 'Clipso')][0] == 'Cocotte'          # hors liste gardé
    assert app[('BS999/01', 'BS999')][0] == 'Accessoires'
    assert app[('BS111/01', 'BS111')][0] == ''

    traces = _traces(db)
    valeur, source, accord, total = traces[('BS270100/01', 'type')]
    assert (valeur, accord, total) == ('Four vapeur', 1, 1)
    assert source == f"{PREFIXE_SOURCE_REGLE}Gaggenau BS* → Four vapeur"
    assert est_source_de_regle(source)
    assert ('998767602', 'type') not in traces   # type du fichier : pas une auto-complétion

    assert _propositions(db) == {'998767602': ('Réfrigérateur', 'Congélateur')}
    assert results == {'types_par_regle': 1, 'types_contredits': 1,
                       'types_hors_liste': [('Cocotte', 1)]}


def test_les_deux_chemins_equivalents(base, tmp_path):
    db, _ = base
    _importer(db, 'standard', LIGNES)
    etat_std = (_appareils(db), _traces(db), _propositions(db))
    db2 = DatabaseManager(str(tmp_path / 'autre.db'))
    try:
        RegleNomenclatureService(db2).enregistrer_regles(REGLES)
        _importer(db2, 'batch', LIGNES)
        assert (_appareils(db2), _traces(db2), _propositions(db2)) == etat_std
    finally:
        db2.close()


def _inserer(db, lignes):
    cnx = db.get_connection()
    cnx.executemany("INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref, "
                    "other_ref, notes, category) VALUES (?, ?, ?, ?, '', '', '')", lignes)
    cnx.commit()


@pytest.mark.parametrize('chemin_import', ['standard', 'batch'])
def test_regle_l_emporte_sur_l_auto_completion_par_reference(base, chemin_import):
    db, _ = base
    # Appareil vérifié de même réf. commerciale, typé « Four » : l'auto-complétion
    # par référence recopierait « Four », la règle validée donne « Four vapeur »
    _inserer(db, [('Four', 'Gaggenau', 'BS270100/01', 'BS270100')])
    _importer(db, chemin_import, [['', '', 'BS270100/02', 'BS270100']])
    assert _appareils(db)[('BS270100/02', 'BS270100')] == ('Four vapeur', 'Gaggenau')
    traces = _traces(db)
    assert est_source_de_regle(traces[('BS270100/02', 'type')][1])
    assert not est_source_de_regle(traces[('BS270100/02', 'manufacturer')][1])


@pytest.mark.parametrize('chemin_import', ['standard', 'batch'])
def test_refus_memorise_jamais_reecrit(base, chemin_import):
    db, _ = base
    _inserer(db, [('', 'Gaggenau', 'BS270100/03', 'BS270100'),
                  ('', 'Gaggenau', 'BS270100/04', 'BS270100')])
    refuse = db.execute_query("SELECT id FROM appareils WHERE ref_modele = 'BS270100/03'")[0][0]
    db.enregistrer_refus([(refuse, 'type', 'Four vapeur')])
    _, results = _importer(db, chemin_import, [['', 'Gaggenau', 'BS270100/03', 'BS270100'],
                                               ['', 'Gaggenau', 'BS270100/04', 'BS270100']])
    app = _appareils(db)
    assert app[('BS270100/03', 'BS270100')][0] == ''             # refus respecté
    assert app[('BS270100/04', 'BS270100')][0] == 'Four vapeur'  # existant vide complété
    assert results['types_par_regle'] == 1                       # seul l'écrit compte


def test_type_existant_jamais_ecrase(base):
    db, _ = base
    _inserer(db, [('Four', 'Gaggenau', 'BS270100/05', 'BS270100')])
    _importer(db, 'standard', [['', 'Gaggenau', 'BS270100/05', 'BS270100']])
    assert _appareils(db)[('BS270100/05', 'BS270100')][0] == 'Four'


def test_proposition_d_import_laisse_les_autres(base):
    db, _ = base
    _inserer(db, [('Four', 'Gaggenau', 'BS777/01', 'BS777')])
    service = RegleNomenclatureService(db)
    assert service.calculer_propositions(ecrire=True).ecrit
    avant = _propositions(db)
    assert avant == {'BS777/01': ('Four', 'Four vapeur')}
    mesures = db.execute_query("SELECT id, couverture, accord, calcule_le FROM regles_nomenclature")
    _importer(db, 'standard', [['Réfrigérateur', 'Liebherr', '998767602', 'GN 1013-21B 001']])
    assert _propositions(db) == {**avant, '998767602': ('Réfrigérateur', 'Congélateur')}
    # Calcul restreint : mesures des règles inchangées
    assert db.execute_query("SELECT id, couverture, accord, calcule_le FROM regles_nomenclature") \
        == mesures


@pytest.mark.parametrize('chemin_import', ['standard', 'batch'])
def test_contradiction_en_double_proposee_une_fois(base, chemin_import):
    db, _ = base
    ligne = ['Réfrigérateur', 'Liebherr', '998767602', 'GN 1013-21B 001']
    _, results = _importer(db, chemin_import, [ligne, list(ligne)])
    assert _propositions(db) == {'998767602': ('Réfrigérateur', 'Congélateur')}
    assert results['types_contredits'] == 1


def test_contradiction_refusee_pas_proposee(base):
    db, _ = base
    _inserer(db, [('Réfrigérateur', 'Liebherr', '998767602', 'GN 1013-21B 001')])
    ident = db.execute_query("SELECT id FROM appareils")[0][0]
    db.enregistrer_refus([(ident, 'type', 'Congélateur')])
    _, results = _importer(db, 'standard',
                           [['Réfrigérateur', 'Liebherr', '998767602', 'GN 1013-21B 001']])
    assert _propositions(db) == {}
    assert results['types_contredits'] == 0


def test_sans_regle_import_inchange(tmp_path):
    """Base sans règle : aucun constat, aucune trace de plus (zéro régression)."""
    db = DatabaseManager(str(tmp_path / 'vide.db'))
    try:
        _, results = _importer(db, 'standard', [['', 'Gaggenau', 'BS270100/01', 'BS270100']])
        assert results == {}
        assert _appareils(db)[('BS270100/01', 'BS270100')][0] == ''
        assert _traces(db) == {}
    finally:
        db.close()


def test_import_complet_apercu_puis_reel(base, tmp_path):
    """_run_import_files de bout en bout : l'aperçu (simulation) annonce, l'import
    réel écrit et propose."""
    db, _ = base
    csv = tmp_path / 'lot5.csv'
    csv.write_text("\n".join(";".join(l) for l in LIGNES) + "\n", encoding='utf-8')
    manager = ImportManager(db_manager=db, parent_widget=None)
    config, _ = _config(str(csv))
    apercu = manager._run_import_files(config, dry_run=True)
    assert apercu['types_par_regle'] == 1
    assert apercu['types_contredits'] == 1
    assert apercu['types_hors_liste'] == [('Cocotte', 1)]
    assert _propositions(db) == {} and _traces(db) == {}

    reel = manager._run_import_files(config)
    assert reel['types_par_regle'] == 1
    assert reel['types_contredits'] == 1
    assert _propositions(db) == {'998767602': ('Réfrigérateur', 'Congélateur')}
    assert _appareils(db)[('BS270100/01', 'BS270100')][0] == 'Four vapeur'


def test_regles_illisibles_import_non_bloque(base, monkeypatch):
    db, _ = base
    manager = ImportManager(db_manager=db, parent_widget=None)

    def panne():
        raise sqlite3.OperationalError("table absente")
    monkeypatch.setattr(manager._typage._service_regles(), 'regles', panne)
    manager._reinitialiser_etat_session()
    assert manager._typage.charger() is False
    config, fichier = _config()
    manager._process_data_import([['', 'Gaggenau', 'BS270100/01', 'BS270100']],
                                 REFERENCES, config, fichier, set())
    assert _appareils(db)[('BS270100/01', 'BS270100')][0] == ''


# ── Récapitulatifs ──────────────────────────────────────────────────────────

RESULTATS = {'types_par_regle': 3, 'types_contredits': 2,
             'types_hors_liste': [('Cocotte', 12), ('Filte charbon', 1)]}


def test_lignes_d_historique():
    from src.ui.main_refactored import MainWindow
    texte = MainWindow._lignes_typage_regles(RESULTATS, retrait="  ")
    assert texte == ("  ==> Typés par une règle (à vérifier) : 3\n"
                     "  ==> Types du fichier contredits par une règle : 2 (voir « Types proposés »)\n"
                     "  [!] Types hors liste (gardés) : Cocotte (12), Filte charbon (1)\n")
    assert MainWindow._lignes_typage_regles({}, retrait="") == ''


def test_fenetre_de_confirmation_avec_style_global(qapp):
    from PyQt5.QtWidgets import QLabel
    from src.ui.fenetre_import import ImportPreviewDialog
    from src.ui.style_manager import StyleManager
    ancien = qapp.styleSheet()
    qapp.setStyleSheet(StyleManager.get_modern_style())
    try:
        resultats = dict(RESULTATS, new_entries=5, file_details=[{'filename': 'a.pdf'}])
        dlg = ImportPreviewDialog(resultats, config=None)
        dlg.show()
        qapp.processEvents()
        textes = [l.text() for l in dlg.findChildren(QLabel)]
        assert "<b>Règles de nomenclature</b>" in textes
        assert "À typer par une règle : 3 (à vérifier après l'import)" in textes
        assert "Types hors liste (gardés) : Cocotte (12), Filte charbon (1)" in textes
        dlg.close()
        sans = ImportPreviewDialog({'new_entries': 1}, config=None)
        assert "<b>Règles de nomenclature</b>" not in [l.text() for l in sans.findChildren(QLabel)]
        sans.close()
    finally:
        qapp.setStyleSheet(ancien)
