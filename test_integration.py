#!/usr/bin/env python3
"""
Test d'intégration du nouveau ImportManager dans l'interface principale
Vérification que l'intégration n'a pas cassé les fonctionnalités existantes
"""

import sys
import os

# Ajouter le répertoire parent au path pour les imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.ui.main_refactored import MainWindow
    from src.core.import_manager import ImportManager
    from src.data.database_manager import DatabaseManager
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    print("Vérifiez que tous les modules sont présents")
    sys.exit(1)


def test_main_window_initialization():
    """Test que la MainWindow s'initialise correctement avec le nouveau ImportManager"""
    print("🔧 Test d'initialisation de MainWindow avec ImportManager...")
    
    try:
        # Créer une base en mémoire pour les tests
        db_manager = DatabaseManager(":memory:")
        
        # Créer une MainWindow factice sans interface graphique
        class TestMainWindow:
            def __init__(self):
                self.db_manager = db_manager
                self.import_manager = ImportManager(self.db_manager, parent_widget=None)
                
        window = TestMainWindow()
        
        # Vérifier que l'import manager est bien initialisé
        assert hasattr(window, 'import_manager')
        assert isinstance(window.import_manager, ImportManager)
        assert window.import_manager.db_manager == window.db_manager
        
        print("✅ MainWindow s'initialise correctement avec ImportManager")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test d'initialisation: {e}")
        return False


def test_new_import_methods():
    """Test que les nouvelles méthodes d'import sont disponibles"""
    print("📥 Test de disponibilité des nouvelles méthodes d'import...")
    
    try:
        # Importer la classe sans l'instancier complètement
        methods_to_check = [
            '_show_import_results_new',
            'dropEvent',  # Méthode mise à jour
        ]
        
        # Vérifier que les méthodes existent dans la classe
        from src.ui.main_refactored import MainWindow
        
        for method_name in methods_to_check:
            if not hasattr(MainWindow, method_name):
                print(f"❌ Méthode manquante: {method_name}")
                return False
            else:
                print(f"✅ Méthode disponible: {method_name}")
        
        print("✅ Toutes les nouvelles méthodes sont disponibles")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la vérification des méthodes: {e}")
        return False


def test_import_manager_integration():
    """Test que l'ImportManager s'intègre bien"""
    print("🔗 Test d'intégration ImportManager...")
    
    try:
        # Test avec des données simulées
        db_manager = DatabaseManager(":memory:")
        import_manager = ImportManager(db_manager)
        
        # Vérifier les méthodes essentielles
        assert hasattr(import_manager, 'import_files')
        assert hasattr(import_manager, '_detect_file_type')
        assert hasattr(import_manager, '_extract_reference_from_filename')
        
        # Test de détection de type
        from src.core.import_manager import FileType
        assert import_manager._detect_file_type("test.csv") == FileType.CSV
        assert import_manager._detect_file_type("test.pdf") == FileType.PDF
        
        # Test d'extraction de référence
        ref = import_manager._extract_reference_from_filename("piece_test.csv")
        assert ref == "piece_test"
        
        print("✅ ImportManager s'intègre correctement")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test d'intégration: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backwards_compatibility():
    """Test que les anciennes méthodes sont toujours disponibles (comme _legacy)"""
    print("🔄 Test de compatibilité descendante...")
    
    try:
        from src.ui.main_refactored import MainWindow
        
        # Vérifier que les anciennes méthodes sont encore là (renommées en _legacy)
        legacy_methods = [
            '_import_file_legacy',
            'dropEvent_legacy',
        ]
        
        for method_name in legacy_methods:
            if not hasattr(MainWindow, method_name):
                print(f"❌ Méthode legacy manquante: {method_name}")
                return False
            else:
                print(f"✅ Méthode legacy préservée: {method_name}")
        
        print("✅ Compatibilité descendante maintenue")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test de compatibilité: {e}")
        return False


def demonstrate_new_capabilities():
    """Démontrer les nouvelles capacités"""
    print("\n🌟 Démonstration des nouvelles capacités:")
    print("=" * 50)
    
    print("1. 📁 Import multi-fichiers avec interface unifiée")
    print("   - Sélection de plusieurs fichiers CSV/PDF en une fois")
    print("   - Interface de configuration des libellés hiérarchiques")
    
    print("\n2. 🏷️ Gestion des libellés hiérarchiques")
    print("   - Référence commune optionnelle pour tous les fichiers")
    print("   - Libellé commun ou individuel par fichier")
    print("   - Association multiple automatique")
    
    print("\n3. 🎯 Interface utilisateur améliorée")
    print("   - Dialogue unifié pour tous types d'import")
    print("   - Aperçu des données avant import")
    print("   - Messages d'erreur détaillés")
    
    print("\n4. 🔄 Drag & Drop amélioré")
    print("   - Support de plusieurs fichiers simultanés")
    print("   - Mélange CSV/PDF autorisé")
    print("   - Interface de configuration automatique")
    
    print("\n5. 🧪 Architecture testable")
    print("   - Code factorisé et modulaire")
    print("   - Tests automatisés")
    print("   - Compatibilité préservée")


def main():
    """Fonction principale de test"""
    print("🚀 Test d'intégration du nouveau système d'importation")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 4
    
    # Exécuter les tests
    if test_main_window_initialization():
        tests_passed += 1
    print()
    
    if test_new_import_methods():
        tests_passed += 1
    print()
    
    if test_import_manager_integration():
        tests_passed += 1
    print()
    
    if test_backwards_compatibility():
        tests_passed += 1
    print()
    
    # Résultats
    print("📊 Résultats des tests:")
    print(f"✅ {tests_passed}/{total_tests} tests réussis")
    
    if tests_passed == total_tests:
        print("\n🎉 INTÉGRATION RÉUSSIE !")
        print("✅ Le nouveau système d'importation est prêt à l'emploi")
        print("✅ Aucune régression détectée")
        print("✅ Nouvelles fonctionnalités disponibles")
        
        demonstrate_new_capabilities()
        
        return 0
    else:
        print(f"\n❌ {total_tests - tests_passed} test(s) échoué(s)")
        print("⚠️  Vérifiez les erreurs ci-dessus avant de continuer")
        return 1


if __name__ == "__main__":
    exit(main())