"""
Bloc d'historique « Appareils existants complétés » (v3.88.2)

Un import qui complète le Type/Fabricant vide d'un appareil existant ne le fait
jamais en silence : la liste remonte dans results['appareils_completes'] et
s'affiche dans l'entrée d'historique de l'import.
"""

import os
import tempfile
import types

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType,
    LabelConfiguration, FileType,
)
from src.ui.main_refactored import MainWindow


def _fenetre_factice(historique):
    return types.SimpleNamespace(
        user_interaction_service=types.SimpleNamespace(
            add_to_history=lambda s, duration_ms=None: historique.append(s)),
        _lignes_alignements=MainWindow._lignes_alignements)


def test_lignes_du_bloc():
    texte = MainWindow._lignes_completions({'appareils_completes': [
        {'id': 1, 'ref_modele': 'X1', 'commercial_ref': 'CR1', 'type': 'Four', 'manufacturer': 'Bosch'},
        {'id': 2, 'ref_modele': 'X3', 'commercial_ref': '', 'type': 'Lave-linge'},
        {'id': 3, 'ref_modele': '', 'commercial_ref': '', 'manufacturer': 'Miele'},
    ]}, retrait="  ")
    assert texte.splitlines() == [
        "  ==> Appareils existants complétés : 3",
        "  - X1 / CR1 : type Four, fabricant Bosch",
        "  - X3 : type Lave-linge",
        "  - #3 : fabricant Miele",
    ]


def test_bloc_vide_sans_completion():
    assert MainWindow._lignes_completions({}, retrait="") == ''


def test_liste_plafonnee():
    completes = [{'id': i, 'ref_modele': f'R{i}', 'commercial_ref': '', 'type': 'Four'}
                 for i in range(25)]
    lignes = MainWindow._lignes_completions(
        {'appareils_completes': completes}, retrait="").splitlines()
    assert lignes[0] == "==> Appareils existants complétés : 25"
    assert len(lignes) == 1 + MainWindow.MAX_LIGNES_COMPLETIONS + 1
    assert lignes[-1] == "- … (5 de plus)"


def test_bloc_avant_l_alerte_de_mapping():
    """Placées sous un « [!] », ses lignes seraient surlignées comme l'alerte."""
    historique = []
    MainWindow._safe_show_import_results_new(_fenetre_factice(historique), {
        'total_files': 1, 'file_details': [{'filename': 'Collage', 'type': 'CSV', 'lines_processed': 1}],
        'appareils_completes': [{'id': 1, 'ref_modele': 'X1', 'commercial_ref': '', 'type': 'Four'}],
        'alerte_mapping': "alerte",
    })
    lignes = historique[0].splitlines()
    i = lignes.index("     ==> Appareils existants complétés : 1")
    assert lignes[i + 1:i + 3] == ["     - X1 : type Four", "     [!] alerte"]


def test_import_complet_remonte_la_liste(qapp, tmp_path):
    """Bout en bout : _run_import_files (moteur réel des imports) → results →
    entrée d'historique."""
    csv = tmp_path / "lot.csv"
    csv.write_text("Four;Bosch;X1;CR1\n", encoding='utf-8')
    chemin_db = tempfile.mktemp(suffix='.db')
    db_origine, recherche_origine = Config.DB_FILE, Config.SEARCH_PIECES_ONLY
    Config.DB_FILE, Config.SEARCH_PIECES_ONLY = chemin_db, False
    try:
        db = DatabaseManager()
        conn = db.get_connection()
        conn.execute("INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref, "
                     "other_ref, notes, category) VALUES ('', '', 'X1', 'CR1', '', '', '')")
        conn.commit()
        manager = ImportManager(db_manager=db, parent_widget=None)
        fichier = ImportFile(path=str(csv), type=FileType.CSV, suggested_reference='REF_TEST')
        config = ImportConfiguration(
            files=[fichier], import_type=ImportType.SINGLE_FILE, common_reference='REF_TEST',
            use_common_reference=True, label_config=LabelConfiguration(),
            individual_references={}, individual_labels={},
            csv_import_mode=2, has_headers=False)
        resultats = manager._run_import_files(config)
        en_base = db.execute_query(
            "SELECT type, manufacturer FROM appareils WHERE ref_modele = 'X1'")
        db.close()
    finally:
        Config.DB_FILE, Config.SEARCH_PIECES_ONLY = db_origine, recherche_origine
        if os.path.exists(chemin_db):
            os.remove(chemin_db)

    assert [tuple(r) for r in en_base] == [('Four', 'Bosch')]
    assert [(a['ref_modele'], a.get('type'), a.get('manufacturer'))
            for a in resultats['appareils_completes']] == [('X1', 'Four', 'Bosch')]
    historique = []
    MainWindow._safe_show_import_results_new(_fenetre_factice(historique), resultats)
    assert "     - X1 / CR1 : type Four, fabricant Bosch" in historique[0].splitlines()
