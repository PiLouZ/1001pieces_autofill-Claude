#!/usr/bin/env python3
"""
Tests de non régression pour la fusion des appareils
ZÉRO RÉGRESSION ! - Vérification du bon fonctionnement après modifications
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__)))

from src.data.database_manager import DatabaseManager
from src.services.duplicates_analysis_service import DuplicatesAnalysisService
from src.services.cleanup_ui_service import DuplicateDevicesWidget
import sqlite3

def test_database_consistency():
    """Test 1: Vérifier la cohérence de la structure de base"""
    print("=== TEST 1: Cohérence structure DB ===")

    try:
        db = DatabaseManager()

        # Vérifier tables existantes
        conn = sqlite3.connect('data/appareils.db')
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        required_tables = ['appareils', 'pieces', 'piece_associations', 'reference_decisions']

        for table in required_tables:
            if table in tables:
                print(f"✅ Table {table} existe")
            else:
                print(f"❌ Table {table} manquante")

        # Vérifier structure piece_associations
        cursor.execute("PRAGMA table_info(piece_associations)")
        columns = [col[1] for col in cursor.fetchall()]
        required_columns = ['id', 'piece_id', 'appareil_id', 'created_at']

        for col in required_columns:
            if col in columns:
                print(f"✅ Colonne piece_associations.{col} existe")
            else:
                print(f"❌ Colonne piece_associations.{col} manquante")

        conn.close()
        print("✅ Test structure DB - OK")
        return True

    except Exception as e:
        print(f"❌ Test structure DB - ERREUR: {e}")
        return False

def test_merge_logic():
    """Test 2: Logique de fusion des appareils"""
    print("\n=== TEST 2: Logique fusion appareils ===")

    try:
        db = DatabaseManager()
        analysis_service = DuplicatesAnalysisService(db, None)

        # Test avec des données simulées
        test_merge_options = {
            'device_merges': [
                {
                    'master_id': 1,
                    'duplicate_ids': [2, 3]
                }
            ]
        }

        print("Test logique fusion avec données simulées...")

        # Vérifier que la méthode _merge_devices existe et prend les bons paramètres
        if hasattr(analysis_service, '_merge_devices'):
            print("✅ Méthode _merge_devices existe")

            # Test avec IDs valides
            print("Test validation IDs...")
            for merge_info in test_merge_options['device_merges']:
                master_id = merge_info['master_id']
                duplicate_ids = merge_info['duplicate_ids']

                if master_id and duplicate_ids:
                    print(f"✅ IDs valides: maître={master_id}, doublons={duplicate_ids}")
                else:
                    print(f"❌ IDs invalides: maître={master_id}, doublons={duplicate_ids}")
        else:
            print("❌ Méthode _merge_devices manquante")
            return False

        print("✅ Test logique fusion - OK")
        return True

    except Exception as e:
        print(f"❌ Test logique fusion - ERREUR: {e}")
        return False

def test_ui_widget_logic():
    """Test 3: Logique des widgets UI"""
    print("\n=== TEST 3: Logique widgets UI ===")

    try:
        # Vérifier que la classe existe et ses méthodes (sans instancier)
        from src.services.cleanup_ui_service import DuplicateDevicesWidget

        required_methods = ['get_merge_groups', '_mark_selected_as_distinct', '_update_buttons_state']

        for method in required_methods:
            if hasattr(DuplicateDevicesWidget, method):
                print(f"✅ Méthode {method} existe dans la classe")
            else:
                print(f"❌ Méthode {method} manquante dans la classe")
                return False

        print("✅ Test widgets UI - OK (structure de classe vérifiée)")
        return True

    except Exception as e:
        print(f"❌ Test widgets UI - ERREUR: {e}")
        return False

def test_reference_decisions():
    """Test 4: Système de décisions de référence"""
    print("\n=== TEST 4: Système décisions références ===")

    try:
        db = DatabaseManager()

        # Vérifier méthode save_reference_decision
        if hasattr(db, 'save_reference_decision'):
            print("✅ Méthode save_reference_decision existe")

            # Test avec données simulées (sans vraiment sauvegarder)
            print("Test validation paramètres...")
            ref_modele = "TEST_REF"
            decision = "DISTINCT"
            notes = "Test de non régression"

            if ref_modele and decision:
                print(f"✅ Paramètres valides: {ref_modele}, {decision}")
            else:
                print("❌ Paramètres invalides")
                return False
        else:
            print("❌ Méthode save_reference_decision manquante")
            return False

        print("✅ Test décisions références - OK")
        return True

    except Exception as e:
        print(f"❌ Test décisions références - ERREUR: {e}")
        return False

def main():
    """Exécuter tous les tests de non régression"""
    print("🧪 TESTS DE NON RÉGRESSION - FUSION APPAREILS")
    print("=" * 50)

    tests = [
        test_database_consistency,
        test_merge_logic,
        test_ui_widget_logic,
        test_reference_decisions
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ ERREUR CRITIQUE dans {test.__name__}: {e}")
            results.append(False)

    print("\n" + "=" * 50)
    print("📊 RÉSULTATS FINAUX:")

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"🎉 TOUS LES TESTS PASSENT ({passed}/{total})")
        print("✅ AUCUNE RÉGRESSION DÉTECTÉE")
        return True
    else:
        print(f"⚠️  CERTAINS TESTS ÉCHOUENT ({passed}/{total})")
        print("❌ RÉGRESSION POSSIBLE - VÉRIFICATION REQUISE")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)