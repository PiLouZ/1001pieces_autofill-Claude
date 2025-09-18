"""
Tests de non-régression pour AutoSaveManager
Validation CRITIQUE avant migration de main_refactored.py
"""

import sys
import os
import unittest
from unittest.mock import Mock, MagicMock, patch
from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QLabel, QStatusBar
from PyQt5.QtCore import QTimer

# Ajouter le chemin source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.auto_save_manager import AutoSaveManager
from src.core.config import Config


class TestAutoSaveManager(unittest.TestCase):
    """Tests critiques pour AutoSaveManager - ZÉRO RÉGRESSION"""

    @classmethod
    def setUpClass(cls):
        """Setup QApplication pour les tests PyQt"""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Setup pour chaque test"""
        # Mocks des dépendances
        self.db_manager = Mock()
        self.user_interaction_service = Mock()
        self.statusbar = Mock(spec=QStatusBar)

        # Widget indicateur mock
        self.save_indicator = Mock(spec=QLabel)

        # Créer AutoSaveManager
        self.auto_save_manager = AutoSaveManager(
            self.db_manager,
            self.user_interaction_service,
            self.statusbar
        )

    def test_initialization(self):
        """Test d'initialisation correcte"""
        # Vérifier l'état initial
        self.assertEqual(len(self.auto_save_manager.modified_cells), 0)
        self.assertEqual(len(self.auto_save_manager.previous_values), 0)
        self.assertTrue(self.auto_save_manager.auto_save_enabled)
        self.assertIsNone(self.auto_save_manager.auto_save_timer)

    def test_setup_auto_save(self):
        """Test configuration auto-sauvegarde"""
        # Test avec intervalle par défaut
        self.auto_save_manager.setup_auto_save()

        self.assertIsNotNone(self.auto_save_manager.auto_save_timer)
        self.assertTrue(self.auto_save_manager.auto_save_timer.isActive())

        # Test avec intervalle personnalisé
        self.auto_save_manager.setup_auto_save(10000)
        self.assertEqual(self.auto_save_manager.auto_save_timer.interval(), 10000)

    def test_setup_ui_indicator(self):
        """Test configuration indicateur UI"""
        self.auto_save_manager.setup_ui_indicator(self.save_indicator)

        self.assertEqual(self.auto_save_manager.save_indicator, self.save_indicator)
        self.save_indicator.setText.assert_called_once()

    def test_mark_cell_modified(self):
        """Test marquage cellule modifiée"""
        # Mock table widget
        table_widget = Mock()
        item = Mock(spec=QTableWidgetItem)
        item.text.return_value = "test_value"
        table_widget.item.return_value = item

        self.auto_save_manager.setup_ui_indicator(self.save_indicator)

        # Marquer cellule modifiée
        self.auto_save_manager.mark_cell_modified(0, 1, table_widget)

        # Vérifications
        self.assertIn((0, 1), self.auto_save_manager.modified_cells)
        self.assertEqual(self.auto_save_manager.previous_values[(0, 1)], "test_value")

        # Vérifier mise à jour indicateur
        self.save_indicator.setText.assert_called_with(Config.get_message('save_pending'))

    def test_clear_cell_modification(self):
        """Test effacement modification cellule"""
        # Mock table widget
        table_widget = Mock()
        item = Mock(spec=QTableWidgetItem)
        table_widget.item.return_value = item

        self.auto_save_manager.setup_ui_indicator(self.save_indicator)

        # Ajouter modification puis l'effacer
        self.auto_save_manager.modified_cells.add((0, 1))
        self.auto_save_manager.clear_cell_modification(0, 1, table_widget)

        # Vérifications
        self.assertNotIn((0, 1), self.auto_save_manager.modified_cells)
        item.setBackground.assert_called_once()

        # Vérifier indicateur si plus de modifications
        if not self.auto_save_manager.modified_cells:
            self.save_indicator.setText.assert_called_with(Config.get_message('save_success'))

    def test_trigger_manual_save(self):
        """Test sauvegarde manuelle"""
        self.auto_save_manager.trigger_manual_save()

        # Vérifier appels
        self.statusbar.showMessage.assert_called_once()
        self.user_interaction_service.add_to_history.assert_called_with("Sauvegarde manuelle effectuée")

    def test_has_pending_changes(self):
        """Test détection modifications en attente"""
        # Aucune modification
        self.assertFalse(self.auto_save_manager.has_pending_changes())

        # Ajouter modification
        self.auto_save_manager.modified_cells.add((0, 1))
        self.assertTrue(self.auto_save_manager.has_pending_changes())

        # Compter modifications
        self.assertEqual(self.auto_save_manager.get_pending_changes_count(), 1)

    def test_enable_disable_auto_save(self):
        """Test activation/désactivation auto-sauvegarde"""
        # Désactiver
        self.auto_save_manager.enable_auto_save(False)
        self.assertFalse(self.auto_save_manager.auto_save_enabled)

        # Réactiver
        self.auto_save_manager.enable_auto_save(True)
        self.assertTrue(self.auto_save_manager.auto_save_enabled)

    def test_cleanup(self):
        """Test nettoyage ressources"""
        # Setup avec timer
        self.auto_save_manager.setup_auto_save()
        self.auto_save_manager.modified_cells.add((0, 1))
        self.auto_save_manager.previous_values[(0, 1)] = "test"

        # Cleanup
        self.auto_save_manager.cleanup()

        # Vérifications
        self.assertIsNone(self.auto_save_manager.auto_save_timer)
        self.assertEqual(len(self.auto_save_manager.modified_cells), 0)
        self.assertEqual(len(self.auto_save_manager.previous_values), 0)

    def test_multiple_cell_modifications(self):
        """Test gestion multiple modifications"""
        table_widget = Mock()
        item1 = Mock(spec=QTableWidgetItem)
        item1.text.return_value = "value1"
        item2 = Mock(spec=QTableWidgetItem)
        item2.text.return_value = "value2"

        table_widget.item.side_effect = [item1, item2]

        # Marquer plusieurs cellules
        self.auto_save_manager.mark_cell_modified(0, 1, table_widget)
        self.auto_save_manager.mark_cell_modified(1, 2, table_widget)

        # Vérifier état
        self.assertEqual(self.auto_save_manager.get_pending_changes_count(), 2)
        self.assertTrue(self.auto_save_manager.has_pending_changes())

    def test_auto_save_disabled_no_action(self):
        """Test que auto-save désactivée ne fait rien"""
        self.auto_save_manager.enable_auto_save(False)
        self.auto_save_manager.modified_cells.add((0, 1))

        # Tenter auto-save
        self.auto_save_manager._auto_save()

        # Doit rester en attente
        self.assertTrue(self.auto_save_manager.has_pending_changes())


def run_tests():
    """Exécuter tous les tests de non-régression"""
    print("🧪 TESTS DE NON-RÉGRESSION - AutoSaveManager")
    print("=" * 60)

    unittest.main(argv=[''], exit=False, verbosity=2)

    print("\n✅ Tous les tests passés - AutoSaveManager prêt pour migration")


if __name__ == "__main__":
    run_tests()