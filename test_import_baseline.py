#!/usr/bin/env python3
"""
Tests Anti-Régression - Import de Fichiers
=========================================

BUT: Valider que toutes les fonctionnalités d'import actuelles fonctionnent
AVANT de commencer les optimisations Phase 1.

Ces tests doivent TOUS passer avant ET après chaque modification.
"""

import sys
import os
import tempfile
import csv
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from src.ui.qt_imports import QApplication
from src.ui.main_refactored import MainWindow
from src.core.import_manager import ImportManager, ImportConfiguration, ImportFile, FileType, ImportType
from src.data.database_manager import DatabaseManager

class TestResults:
    """Classe pour stocker et afficher les résultats des tests"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.total = 0

    def add_pass(self, test_name):
        self.total += 1
        self.passed.append(test_name)
        print(f"  ✅ {test_name}")

    def add_fail(self, test_name, error):
        self.total += 1
        self.failed.append((test_name, error))
        print(f"  ❌ {test_name}: {error}")

    def summary(self):
        print("\n" + "="*60)
        print("RÉSUMÉ DES TESTS ANTI-RÉGRESSION")
        print("="*60)
        print(f"✅ Réussis: {len(self.passed)}/{self.total}")
        print(f"❌ Échoués: {len(self.failed)}/{self.total}")

        if self.failed:
            print("\n⚠️ TESTS ÉCHOUÉS:")
            for name, error in self.failed:
                print(f"  - {name}")
                print(f"    Erreur: {error}")

        print("="*60)
        return len(self.failed) == 0


def create_test_csv_file():
    """Créer un fichier CSV de test"""
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
    writer = csv.writer(temp_file)

    # Données de test
    writer.writerow(['REF001', 'COMM001', 'Notes test 1'])
    writer.writerow(['REF002', 'COMM002', 'Notes test 2'])
    writer.writerow(['REF003', 'COMM003', 'Notes test 3'])

    temp_file.close()
    return temp_file.name


def test_baseline_initialization(results):
    """Test 1: L'application démarre correctement"""
    print("\n📝 TEST 1: Initialisation de l'application")

    try:
        app = QApplication(sys.argv)
        window = MainWindow()

        # Vérifier que les composants clés existent
        assert hasattr(window, 'import_manager'), "import_manager manquant"
        assert hasattr(window, 'db_manager'), "db_manager manquant"
        assert hasattr(window, 'file_processing_service'), "file_processing_service manquant"

        results.add_pass("Application démarre avec tous les services")
        return window
    except Exception as e:
        results.add_fail("Initialisation application", str(e))
        return None


def test_import_manager_exists(window, results):
    """Test 2: ImportManager est correctement initialisé"""
    print("\n📝 TEST 2: ImportManager initialisé")

    try:
        import_manager = window.import_manager

        # Vérifier les méthodes essentielles
        assert hasattr(import_manager, 'import_files'), "import_files manquant"
        assert hasattr(import_manager, 'load_csv_data'), "load_csv_data manquant"
        assert hasattr(import_manager, 'load_pdf_data'), "load_pdf_data manquant"
        assert hasattr(import_manager, '_get_sample_data'), "_get_sample_data manquant"

        results.add_pass("ImportManager correctement initialisé")
        return True
    except Exception as e:
        results.add_fail("ImportManager initialisé", str(e))
        return False


def test_csv_data_loading(window, results):
    """Test 3: Chargement de données CSV"""
    print("\n📝 TEST 3: Chargement données CSV")

    csv_file = None
    try:
        csv_file = create_test_csv_file()
        import_manager = window.import_manager

        # Charger les données
        data = import_manager.load_csv_data(csv_file, max_rows=10)

        # Vérifications
        assert data is not None, "Données CSV None"
        assert len(data) == 3, f"Nombre de lignes incorrect: {len(data)} au lieu de 3"
        assert len(data[0]) >= 2, f"Colonnes insuffisantes: {len(data[0])}"
        assert data[0][0] == 'REF001', f"Première valeur incorrecte: {data[0][0]}"

        results.add_pass("Chargement CSV fonctionnel")
        return True
    except Exception as e:
        results.add_fail("Chargement CSV", str(e))
        return False
    finally:
        if csv_file and os.path.exists(csv_file):
            os.unlink(csv_file)


def test_file_type_detection(window, results):
    """Test 4: Détection du type de fichier"""
    print("\n📝 TEST 4: Détection type de fichier")

    csv_file = None
    try:
        csv_file = create_test_csv_file()
        import_manager = window.import_manager

        # Tester détection CSV
        file_type = import_manager._detect_file_type(csv_file)
        assert file_type == FileType.CSV, f"Type CSV non détecté: {file_type}"

        # Tester détection PDF (avec fichier fictif)
        file_type_pdf = import_manager._detect_file_type('test.pdf')
        assert file_type_pdf == FileType.PDF, "Type PDF non détecté"

        # Tester fichier non supporté
        file_type_invalid = import_manager._detect_file_type('test.txt')
        assert file_type_invalid is None, "Fichier invalide devrait retourner None"

        results.add_pass("Détection type de fichier fonctionnelle")
        return True
    except Exception as e:
        results.add_fail("Détection type fichier", str(e))
        return False
    finally:
        if csv_file and os.path.exists(csv_file):
            os.unlink(csv_file)


def test_reference_extraction(window, results):
    """Test 5: Extraction de référence depuis nom de fichier"""
    print("\n📝 TEST 5: Extraction référence depuis nom fichier")

    try:
        import_manager = window.import_manager

        # Tester avec différents noms
        ref1 = import_manager._extract_reference_from_filename('/path/to/TEST_REF_001.csv')
        assert ref1 == 'TEST_REF_001', f"Référence incorrecte: {ref1}"

        ref2 = import_manager._extract_reference_from_filename('my-test-file.pdf')
        assert 'test' in ref2.lower(), f"Référence incorrecte: {ref2}"

        results.add_pass("Extraction référence fonctionnelle")
        return True
    except Exception as e:
        results.add_fail("Extraction référence", str(e))
        return False


def test_import_configuration_creation(window, results):
    """Test 6: Création d'une configuration d'import"""
    print("\n📝 TEST 6: Création configuration d'import")

    csv_file = None
    try:
        csv_file = create_test_csv_file()

        # Créer une configuration
        import_file = ImportFile(
            path=csv_file,
            type=FileType.CSV,
            suggested_reference='TEST_REF',
            data=None
        )

        config = ImportConfiguration(
            files=[import_file],
            import_type=ImportType.SINGLE_FILE
        )

        # Vérifications
        assert len(config.files) == 1, "Nombre de fichiers incorrect"
        assert config.import_type == ImportType.SINGLE_FILE, "Type d'import incorrect"
        assert config.files[0].suggested_reference == 'TEST_REF', "Référence incorrecte"

        results.add_pass("Configuration d'import créée correctement")
        return True
    except Exception as e:
        results.add_fail("Configuration d'import", str(e))
        return False
    finally:
        if csv_file and os.path.exists(csv_file):
            os.unlink(csv_file)


def test_sample_data_method_exists(window, results):
    """Test 7: Méthode _get_sample_data existe et fonctionne"""
    print("\n📝 TEST 7: Méthode _get_sample_data")

    csv_file = None
    try:
        csv_file = create_test_csv_file()
        import_manager = window.import_manager

        # Tester la méthode
        sample_data = import_manager._get_sample_data(csv_file, FileType.CSV)

        # Vérifications
        assert sample_data is not None, "Sample data est None"
        assert len(sample_data) > 0, "Sample data vide"

        results.add_pass("_get_sample_data fonctionnelle")
        return True
    except Exception as e:
        results.add_fail("_get_sample_data", str(e))
        return False
    finally:
        if csv_file and os.path.exists(csv_file):
            os.unlink(csv_file)


def test_database_connection(window, results):
    """Test 8: Connexion à la base de données"""
    print("\n📝 TEST 8: Connexion base de données")

    try:
        db_manager = window.db_manager

        # Vérifier que la connexion existe
        assert db_manager is not None, "db_manager est None"
        assert hasattr(db_manager, 'conn'), "Connexion DB manquante"

        # Tester une requête simple
        count = db_manager.count_incomplete_devices()
        assert isinstance(count, int), f"Count invalide: {type(count)}"

        results.add_pass("Connexion DB fonctionnelle")
        return True
    except Exception as e:
        results.add_fail("Connexion DB", str(e))
        return False


def test_file_processing_service_exists(window, results):
    """Test 9: FileProcessingService initialisé"""
    print("\n📝 TEST 9: FileProcessingService initialisé")

    try:
        service = window.file_processing_service

        # Vérifier les méthodes essentielles
        assert hasattr(service, 'import_pdf_files'), "import_pdf_files manquant"
        assert hasattr(service, '_import_pdf_legacy'), "_import_pdf_legacy manquant"

        results.add_pass("FileProcessingService initialisé")
        return True
    except Exception as e:
        results.add_fail("FileProcessingService", str(e))
        return False


def test_pdf_extractor_import(results):
    """Test 10: Module PDF extractor importable"""
    print("\n📝 TEST 10: Module PDF extractor")

    try:
        from src.data.pdf_extractor_camelot import CamelotPDFExtractor

        extractor = CamelotPDFExtractor()

        # Vérifier les méthodes essentielles
        assert hasattr(extractor, 'extract_data'), "extract_data manquant"
        assert hasattr(extractor, '_extract_with_camelot'), "_extract_with_camelot manquant"

        results.add_pass("PDF extractor importable")
        return True
    except Exception as e:
        results.add_fail("PDF extractor", str(e))
        return False


def run_all_baseline_tests():
    """Exécuter tous les tests anti-régression"""
    print("\n" + "🧪 "*30)
    print("TESTS ANTI-RÉGRESSION - BASELINE IMPORT")
    print("🧪 "*30)
    print("\n⚠️  Ces tests valident les fonctionnalités ACTUELLES")
    print("⚠️  Ils DOIVENT tous passer avant les optimisations\n")

    results = TestResults()

    # Initialisation
    window = test_baseline_initialization(results)

    if window:
        # Tests avec window
        test_import_manager_exists(window, results)
        test_csv_data_loading(window, results)
        test_file_type_detection(window, results)
        test_reference_extraction(window, results)
        test_import_configuration_creation(window, results)
        test_sample_data_method_exists(window, results)
        test_database_connection(window, results)
        test_file_processing_service_exists(window, results)

    # Tests sans window
    test_pdf_extractor_import(results)

    # Résumé
    success = results.summary()

    if success:
        print("\n🎉 TOUS LES TESTS BASELINE PASSENT!")
        print("✅ Prêt pour Phase 1 des optimisations\n")
        return 0
    else:
        print("\n❌ CERTAINS TESTS ONT ÉCHOUÉ")
        print("⚠️  NE PAS commencer les optimisations avant correction\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_baseline_tests())
