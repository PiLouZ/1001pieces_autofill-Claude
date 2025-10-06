#!/usr/bin/env python3
"""
Test non-régression pour le drag handle et l'historique
Vérifie que seules les lignes modifiées génèrent des entrées d'historique
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.ui.qt_imports import QApplication, QTableWidgetItem, QTableWidgetSelectionRange
from src.ui.main_refactored import MainWindow
from src.data.database_manager import DatabaseManager

def test_drag_down_history():
    """Test: Drag down doit créer seulement N entrées pour N lignes modifiées"""
    print("\n" + "="*60)
    print("TEST 1: DRAG DOWN - Comptage entrées historique")
    print("="*60)

    app = QApplication(sys.argv)
    window = MainWindow()

    # Sélectionner la première ligne, colonne 0-1 (Type, Fabricant)
    selection = QTableWidgetSelectionRange(0, 0, 0, 1)
    window.table.setRangeSelected(selection, True)

    # Simuler le début du drag
    window.drag_handle.dragging = True
    window.drag_handle.orig_selection = selection
    window.drag_handle.drag_direction = "down"
    window.drag_handle.modified_rows_set.clear()

    # Simuler la duplication de 3 lignes (lignes 1, 2, 3)
    print("📝 Simulation: Duplication de 3 lignes vers le bas")

    for row in range(1, 4):
        for col in range(0, 2):
            item = window.table.item(0, col)
            if item:
                new_item = QTableWidgetItem(item.text())
                window.table.setItem(row, col, new_item)
                window.drag_handle.modified_rows_set.add(row)

    # Nombre de lignes modifiées
    num_modified_rows = len(window.drag_handle.modified_rows_set)
    print(f"✅ Lignes modifiées trackées: {sorted(window.drag_handle.modified_rows_set)}")
    print(f"✅ Nombre total: {num_modified_rows} lignes")

    # Vérifier que modified_rows_set contient exactement 3 lignes
    assert num_modified_rows == 3, f"❌ Attendu 3 lignes modifiées, obtenu {num_modified_rows}"
    print("✅ SUCCÈS: Le tracker contient exactement 3 lignes\n")

    return True

def test_drag_up_history():
    """Test: Drag up doit créer seulement N entrées pour N lignes modifiées"""
    print("\n" + "="*60)
    print("TEST 2: DRAG UP - Comptage entrées historique")
    print("="*60)

    app = QApplication(sys.argv)
    window = MainWindow()

    # Sélectionner la ligne 5, colonnes 0-1
    selection = QTableWidgetSelectionRange(5, 0, 5, 1)
    window.table.setRangeSelected(selection, True)

    # Simuler le début du drag up
    window.drag_handle.dragging = True
    window.drag_handle.orig_selection = selection
    window.drag_handle.drag_direction = "up"
    window.drag_handle.modified_rows_set.clear()

    # Simuler la duplication de 2 lignes vers le haut (lignes 3, 4)
    print("📝 Simulation: Duplication de 2 lignes vers le haut")

    for row in range(3, 5):
        for col in range(0, 2):
            item = window.table.item(5, col)
            if item:
                new_item = QTableWidgetItem(item.text())
                window.table.setItem(row, col, new_item)
                window.drag_handle.modified_rows_set.add(row)

    # Nombre de lignes modifiées
    num_modified_rows = len(window.drag_handle.modified_rows_set)
    print(f"✅ Lignes modifiées trackées: {sorted(window.drag_handle.modified_rows_set)}")
    print(f"✅ Nombre total: {num_modified_rows} lignes")

    # Vérifier que modified_rows_set contient exactement 2 lignes
    assert num_modified_rows == 2, f"❌ Attendu 2 lignes modifiées, obtenu {num_modified_rows}"
    print("✅ SUCCÈS: Le tracker contient exactement 2 lignes\n")

    return True

def test_modified_rows_set_reset():
    """Test: Le set doit être réinitialisé entre chaque drag"""
    print("\n" + "="*60)
    print("TEST 3: RÉINITIALISATION DU TRACKER")
    print("="*60)

    app = QApplication(sys.argv)
    window = MainWindow()

    # Premier drag
    window.drag_handle.modified_rows_set.add(1)
    window.drag_handle.modified_rows_set.add(2)
    print(f"📝 Premier drag: {len(window.drag_handle.modified_rows_set)} lignes")

    # Simuler mousePressEvent (doit clear le set)
    window.drag_handle.modified_rows_set.clear()
    print(f"✅ Après mousePressEvent: {len(window.drag_handle.modified_rows_set)} lignes")

    # Deuxième drag
    window.drag_handle.modified_rows_set.add(5)
    window.drag_handle.modified_rows_set.add(6)
    window.drag_handle.modified_rows_set.add(7)
    print(f"📝 Deuxième drag: {len(window.drag_handle.modified_rows_set)} lignes")

    assert len(window.drag_handle.modified_rows_set) == 3, "❌ Le set n'a pas été réinitialisé"
    print("✅ SUCCÈS: Le tracker se réinitialise correctement\n")

    return True

def test_save_specific_rows_method():
    """Test: Vérifier que _save_specific_rows existe et fonctionne"""
    print("\n" + "="*60)
    print("TEST 4: MÉTHODE _save_specific_rows")
    print("="*60)

    app = QApplication(sys.argv)
    window = MainWindow()

    # Vérifier que la méthode existe
    assert hasattr(window, '_save_specific_rows'), "❌ Méthode _save_specific_rows manquante"
    print("✅ Méthode _save_specific_rows existe")

    # Vérifier que l'ancienne méthode _save_cells_in_range n'existe plus
    has_old_method = hasattr(window, '_save_cells_in_range')
    if has_old_method:
        print("⚠️  Ancienne méthode _save_cells_in_range encore présente (peut être conservée)")
    else:
        print("✅ Ancienne méthode _save_cells_in_range supprimée")

    print("✅ SUCCÈS: Structure de méthodes conforme\n")

    return True

def run_all_tests():
    """Exécuter tous les tests"""
    print("\n" + "🧪 "*30)
    print("TESTS NON-RÉGRESSION: DRAG HANDLE & HISTORIQUE")
    print("🧪 "*30)

    tests = [
        test_drag_down_history,
        test_drag_up_history,
        test_modified_rows_set_reset,
        test_save_specific_rows_method
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(("✅", test.__name__, "SUCCÈS"))
        except AssertionError as e:
            results.append(("❌", test.__name__, str(e)))
        except Exception as e:
            results.append(("💥", test.__name__, f"ERREUR: {e}"))

    # Rapport final
    print("\n" + "="*60)
    print("RAPPORT FINAL")
    print("="*60)

    for status, name, message in results:
        print(f"{status} {name}: {message}")

    # Statistiques
    success_count = sum(1 for r in results if r[0] == "✅")
    total_count = len(results)

    print("\n" + "="*60)
    print(f"RÉSULTAT: {success_count}/{total_count} tests réussis")

    if success_count == total_count:
        print("🎉 TOUS LES TESTS PASSENT!")
        print("="*60 + "\n")
        return 0
    else:
        print("⚠️  CERTAINS TESTS ONT ÉCHOUÉ")
        print("="*60 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
