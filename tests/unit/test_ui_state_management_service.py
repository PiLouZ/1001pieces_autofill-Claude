"""
Tests unitaires pour UIStateManagementService
Test de la gestion de l'état de l'interface utilisateur
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableWidget, QProgressBar, QStatusBar, QPushButton
from PyQt5.QtTest import QTest

# Assurer que le module src est dans le chemin
sys.path.insert(0, '/Users/emg1/Desktop/1001 projects/1001pieces_autofill Claude')

from src.services.ui_state_management_service import UIStateManagementService


class TestUIStateManagementService:
    """Tests pour UIStateManagementService"""

    @pytest.fixture
    def mock_app(self):
        """Application Qt mockée pour les tests"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app

    @pytest.fixture
    def mock_parent_widget(self):
        """Widget parent mocké avec tous les composants nécessaires"""
        parent = Mock()
        parent.table = Mock(spec=QTableWidget)
        parent.progress_bar = Mock(spec=QProgressBar)
        parent.statusbar = Mock(spec=QStatusBar)
        parent.delete_button = Mock(spec=QPushButton)
        parent.copy_button = Mock(spec=QPushButton)
        parent.save_button = Mock(spec=QPushButton)
        parent.refresh_button = Mock(spec=QPushButton)

        # Mock du header de table
        mock_header = Mock()
        parent.table.horizontalHeader.return_value = mock_header
        parent.table.viewport.return_value = Mock()

        # Mock des méthodes principales
        parent.setWindowTitle = Mock()
        parent.setEnabled = Mock()

        return parent

    @pytest.fixture
    def ui_service(self, mock_parent_widget):
        """Service UIStateManagement avec parent mocké"""
        service = UIStateManagementService(parent=None)
        service.parent_window = mock_parent_widget
        service.initialize_services()
        return service

    def test_initialization(self, ui_service):
        """Test de l'initialisation du service"""
        assert ui_service.sort_indicators_enabled is True
        assert ui_service.progress_visible is False
        assert ui_service.current_progress_value == 0
        assert ui_service.table_widget is not None
        assert ui_service.progress_bar is not None
        assert ui_service.status_bar is not None

    def test_initialization_without_parent(self):
        """Test de l'initialisation sans parent"""
        service = UIStateManagementService()
        assert service.parent_window is None
        service.initialize_services()  # Ne doit pas lever d'exception

    def test_update_sort_indicators_enable(self, ui_service):
        """Test de l'activation des indicateurs de tri"""
        ui_service.update_sort_indicators(True)

        assert ui_service.sort_indicators_enabled is True
        ui_service.table_widget.horizontalHeader().setSectionsClickable.assert_called_with(True)
        ui_service.table_widget.horizontalHeader().setSortIndicatorShown.assert_called_with(True)

    def test_update_sort_indicators_disable(self, ui_service):
        """Test de la désactivation des indicateurs de tri"""
        ui_service.update_sort_indicators(False)

        assert ui_service.sort_indicators_enabled is False
        ui_service.table_widget.horizontalHeader().setSectionsClickable.assert_called_with(False)
        ui_service.table_widget.horizontalHeader().setSortIndicatorShown.assert_called_with(False)

    def test_update_progress_visibility_show(self, ui_service):
        """Test de l'affichage de la barre de progression"""
        ui_service.update_progress_visibility(True)

        assert ui_service.progress_visible is True
        ui_service.progress_bar.setVisible.assert_called_with(True)

    def test_update_progress_visibility_hide(self, ui_service):
        """Test du masquage de la barre de progression"""
        ui_service.update_progress_visibility(False)

        assert ui_service.progress_visible is False
        ui_service.progress_bar.setVisible.assert_called_with(False)
        ui_service.progress_bar.setValue.assert_called_with(0)
        assert ui_service.current_progress_value == 0

    def test_update_progress_value(self, ui_service):
        """Test de la mise à jour de la valeur de progression"""
        ui_service.progress_visible = True
        ui_service.update_progress_value(75)

        assert ui_service.current_progress_value == 75
        ui_service.progress_bar.setValue.assert_called_with(75)

    def test_update_progress_value_bounds(self, ui_service):
        """Test des limites de la valeur de progression"""
        ui_service.progress_visible = True

        # Test valeur négative
        ui_service.update_progress_value(-10)
        assert ui_service.current_progress_value == 0

        # Test valeur > 100
        ui_service.update_progress_value(150)
        assert ui_service.current_progress_value == 100

    def test_update_progress_value_when_hidden(self, ui_service):
        """Test que la progression ne s'affiche pas quand masquée"""
        ui_service.progress_visible = False
        ui_service.update_progress_value(50)

        assert ui_service.current_progress_value == 50
        # setValue ne doit pas être appelé si progress_visible est False
        ui_service.progress_bar.setValue.assert_not_called()

    def test_set_button_states_complete(self, ui_service):
        """Test de la configuration complète des états de boutons"""
        button_configs = {
            "delete_button": {"enabled": False, "visible": True, "text": "Supprimer"},
            "copy_button": {"enabled": True, "visible": False, "text": "Copier"}
        }

        ui_service.set_button_states(button_configs)

        # Vérifier delete_button
        ui_service.parent_window.delete_button.setEnabled.assert_called_with(False)
        ui_service.parent_window.delete_button.setVisible.assert_called_with(True)
        ui_service.parent_window.delete_button.setText.assert_called_with("Supprimer")

        # Vérifier copy_button
        ui_service.parent_window.copy_button.setEnabled.assert_called_with(True)
        ui_service.parent_window.copy_button.setVisible.assert_called_with(False)
        ui_service.parent_window.copy_button.setText.assert_called_with("Copier")

    def test_set_button_states_partial(self, ui_service):
        """Test de la configuration partielle des états de boutons"""
        button_configs = {
            "save_button": {"enabled": False}  # Seulement enabled
        }

        ui_service.set_button_states(button_configs)

        ui_service.parent_window.save_button.setEnabled.assert_called_with(False)
        ui_service.parent_window.save_button.setVisible.assert_not_called()
        ui_service.parent_window.save_button.setText.assert_not_called()

    def test_configure_table_appearance_font_size(self, ui_service):
        """Test de la configuration de la taille de police du tableau"""
        mock_font = Mock()
        ui_service.table_widget.font.return_value = mock_font

        ui_service.configure_table_appearance(font_size=14)

        mock_font.setPointSize.assert_called_with(14)
        ui_service.table_widget.setFont.assert_called_with(mock_font)

    def test_configure_table_appearance_alternate_colors(self, ui_service):
        """Test de la configuration des couleurs alternées"""
        ui_service.configure_table_appearance(alternate_colors=True)

        ui_service.table_widget.setAlternatingRowColors.assert_called_with(True)

    def test_set_window_title_suffix_with_suffix(self, ui_service):
        """Test du titre de fenêtre avec suffixe"""
        ui_service.set_window_title_suffix("Test Mode")

        ui_service.parent_window.setWindowTitle.assert_called_with("1001 Pièces Auto-Fill - Test Mode")

    def test_set_window_title_suffix_empty(self, ui_service):
        """Test du titre de fenêtre sans suffixe"""
        ui_service.set_window_title_suffix("")

        ui_service.parent_window.setWindowTitle.assert_called_with("1001 Pièces Auto-Fill")

    def test_update_selection_state_with_selection(self, ui_service):
        """Test de la mise à jour avec sélection"""
        ui_service.update_selection_state(True, 5)

        # Vérifier que les boutons sont activés
        ui_service.parent_window.delete_button.setEnabled.assert_called_with(True)
        ui_service.parent_window.copy_button.setEnabled.assert_called_with(True)

        # Vérifier le message de statut
        ui_service.status_bar.showMessage.assert_called()

    def test_update_selection_state_without_selection(self, ui_service):
        """Test de la mise à jour sans sélection"""
        ui_service.update_selection_state(False, 0)

        # Vérifier que les boutons sont désactivés
        ui_service.parent_window.delete_button.setEnabled.assert_called_with(False)
        ui_service.parent_window.copy_button.setEnabled.assert_called_with(False)

    def test_toggle_drag_handles_visibility_show(self, ui_service):
        """Test de l'affichage des poignées de redimensionnement"""
        ui_service.toggle_drag_handles_visibility(True)

        header = ui_service.table_widget.horizontalHeader()
        header.setSectionsMovable.assert_called_with(True)
        header.setStretchLastSection.assert_called_with(False)

    def test_toggle_drag_handles_visibility_hide(self, ui_service):
        """Test du masquage des poignées de redimensionnement"""
        ui_service.toggle_drag_handles_visibility(False)

        header = ui_service.table_widget.horizontalHeader()
        header.setSectionsMovable.assert_called_with(False)
        header.setStretchLastSection.assert_called_with(True)

    @patch('PyQt5.QtWidgets.QApplication.processEvents')
    def test_show_loading_overlay(self, mock_process_events, ui_service):
        """Test de l'affichage de l'overlay de chargement"""
        ui_service.show_loading_overlay("Test chargement")

        ui_service.status_bar.showMessage.assert_called_with("⏳ Test chargement")
        ui_service.parent_window.setEnabled.assert_called_with(False)
        mock_process_events.assert_called()

    @patch('PyQt5.QtWidgets.QApplication.processEvents')
    def test_hide_loading_overlay(self, mock_process_events, ui_service):
        """Test du masquage de l'overlay de chargement"""
        ui_service.hide_loading_overlay()

        ui_service.parent_window.setEnabled.assert_called_with(True)
        ui_service.status_bar.clearMessage.assert_called()
        mock_process_events.assert_called()

    def test_apply_visual_effect_highlight(self, ui_service):
        """Test de l'effet de surbrillance"""
        with patch('PyQt5.QtCore.QTimer.singleShot') as mock_timer:
            ui_service.apply_visual_effect("highlight", "table")

            # Vérifier que le style est modifié
            ui_service.table_widget.styleSheet.assert_called()
            ui_service.table_widget.setStyleSheet.assert_called()

            # Vérifier qu'un timer est programmé pour restaurer
            mock_timer.assert_called()

    def test_apply_visual_effect_flash(self, ui_service):
        """Test de l'effet de clignotement"""
        with patch.object(ui_service, '_flash_widget') as mock_flash:
            ui_service.apply_visual_effect("flash", "table")

            mock_flash.assert_called_with(ui_service.table_widget)

    def test_flash_widget(self, ui_service):
        """Test de la méthode de clignotement"""
        mock_widget = Mock()
        mock_widget.styleSheet.return_value = "original"

        with patch('PyQt5.QtCore.QTimer.singleShot') as mock_timer:
            ui_service._flash_widget(mock_widget)

            # Vérifier que le style flash est appliqué
            mock_widget.setStyleSheet.assert_called()
            # Vérifier qu'un timer est programmé pour restaurer
            mock_timer.assert_called()

    def test_schedule_refresh(self, ui_service):
        """Test de la programmation du rafraîchissement"""
        with patch.object(ui_service.refresh_timer, 'start') as mock_start:
            with patch.object(ui_service.refresh_timer, 'stop') as mock_stop:
                ui_service.schedule_refresh(500)

                mock_stop.assert_called()
                mock_start.assert_called_with(500)

    @patch('PyQt5.QtWidgets.QApplication.processEvents')
    def test_force_refresh_all_ui(self, mock_process_events, ui_service):
        """Test du rafraîchissement complet de l'interface"""
        ui_service.force_refresh_all_ui()

        # Vérifier que le viewport du tableau est mis à jour
        ui_service.table_widget.viewport().update.assert_called()

        # Vérifier que les événements sont traités
        mock_process_events.assert_called()

    def test_reset_ui_state(self, ui_service):
        """Test de la remise à zéro de l'état UI"""
        ui_service.reset_ui_state()

        # Vérifier que les indicateurs sont remis par défaut
        assert ui_service.sort_indicators_enabled is True
        assert ui_service.progress_visible is False

        # Vérifier que le titre est remis par défaut
        ui_service.parent_window.setWindowTitle.assert_called_with("1001 Pièces Auto-Fill")

    def test_get_current_state(self, ui_service):
        """Test de l'obtention de l'état actuel"""
        ui_service.sort_indicators_enabled = False
        ui_service.progress_visible = True
        ui_service.current_progress_value = 50

        state = ui_service.get_current_state()

        assert state["sort_indicators_enabled"] is False
        assert state["progress_visible"] is True
        assert state["current_progress_value"] == 50
        assert state["widgets_initialized"] is True

    def test_apply_state(self, ui_service):
        """Test de l'application d'un état"""
        state_dict = {
            "sort_indicators_enabled": False,
            "progress_visible": True,
            "current_progress_value": 75
        }

        with patch.object(ui_service, 'update_sort_indicators') as mock_sort:
            with patch.object(ui_service, 'update_progress_visibility') as mock_progress:
                with patch.object(ui_service, 'update_progress_value') as mock_value:
                    ui_service.apply_state(state_dict)

                    mock_sort.assert_called_with(False)
                    mock_progress.assert_called_with(True)
                    mock_value.assert_called_with(75)

    def test_signal_emissions(self, ui_service):
        """Test que les signaux sont émis correctement"""
        # On ne peut pas mocker directement les signaux PyQt5
        # On vérifie plutôt que les méthodes qui émettent les signaux fonctionnent

        # Test que configure_table_appearance ne lève pas d'exception
        ui_service.configure_table_appearance(font_size=12)

        # Test que update_sort_indicators ne lève pas d'exception
        ui_service.update_sort_indicators(True)

        # Test que update_progress_value ne lève pas d'exception
        ui_service.update_progress_value(50)

    def test_error_handling_no_widget(self, ui_service):
        """Test de la gestion d'erreur quand un widget n'existe pas"""
        ui_service.table_widget = None

        # Ces méthodes ne doivent pas lever d'exception
        ui_service.update_sort_indicators(True)
        ui_service.configure_table_appearance(font_size=12)
        ui_service.toggle_drag_handles_visibility(True)

    def test_error_handling_invalid_button(self, ui_service):
        """Test de la gestion d'erreur pour un bouton inexistant"""
        button_configs = {
            "nonexistent_button": {"enabled": False}
        }

        # Ne doit pas lever d'exception
        ui_service.set_button_states(button_configs)

    def test_error_handling_missing_header(self, ui_service):
        """Test de la gestion d'erreur quand le header n'existe pas"""
        ui_service.table_widget.horizontalHeader.return_value = None

        # Ne doit pas lever d'exception
        ui_service.update_sort_indicators(True)
        ui_service.toggle_drag_handles_visibility(True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])