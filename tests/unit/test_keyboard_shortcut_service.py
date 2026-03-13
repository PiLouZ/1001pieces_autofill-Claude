"""
Tests unitaires pour KeyboardShortcutService
Test de la gestion des raccourcis clavier
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QKeyEvent
from PyQt5.QtWidgets import QApplication, QMainWindow, QLineEdit, QPushButton

# Assurer que le module src est dans le chemin
sys.path.insert(0, '/Users/emg1/Desktop/1001 projects/1001pieces_autofill Claude')

from src.services.keyboard_shortcut_service import KeyboardShortcutService


class TestKeyboardShortcutService:
    """Tests pour KeyboardShortcutService"""

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

        # Widgets d'interface
        parent.search_input = Mock(spec=QLineEdit)
        parent.table_controller = Mock()
        parent.advanced_search_service = Mock()

        # Méthodes d'action
        parent._add_new_row = Mock()
        parent._manual_save = Mock()
        parent._handle_paste = Mock()
        parent._handle_copy = Mock()
        parent._undo = Mock()
        parent._redo = Mock()
        parent._show_column_values_list = Mock()
        parent._navigate_to_empty_cell = Mock()
        parent._open_log_viewer = Mock()

        # Méthodes de focus
        parent.focusWidget = Mock(return_value=Mock())

        return parent

    @pytest.fixture
    def shortcut_service(self, mock_parent_widget):
        """Service KeyboardShortcut avec parent mocké"""
        service = KeyboardShortcutService(parent=None)
        service.parent_window = mock_parent_widget
        service.initialize_services()
        return service

    @pytest.fixture
    def mock_key_event(self):
        """Factory pour créer des événements clavier mockés"""
        def create_event(key, modifiers=Qt.NoModifier, standard_key=None):
            event = Mock(spec=QKeyEvent)
            event.key.return_value = key
            event.modifiers.return_value = modifiers
            if standard_key:
                event.matches.return_value = True
            else:
                event.matches.return_value = False
            return event
        return create_event

    def test_initialization(self, shortcut_service):
        """Test de l'initialisation du service"""
        assert shortcut_service.shortcut_actions is not None
        assert shortcut_service.standard_shortcuts is not None
        assert shortcut_service.function_key_shortcuts is not None
        assert shortcut_service.focus_dependent_shortcuts is not None
        assert Qt.Key.Key_D in shortcut_service.focus_dependent_shortcuts

    def test_initialization_without_parent(self):
        """Test de l'initialisation sans parent"""
        service = KeyboardShortcutService()
        assert service.parent_window is None
        service.initialize_services()  # Ne doit pas lever d'exception

    @patch('sys.platform', 'darwin')
    def test_detect_cmd_modifier_macos(self, shortcut_service, mock_key_event):
        """Test de détection des modificateurs sur macOS"""
        # Test avec MetaModifier (Cmd)
        event = mock_key_event(Qt.Key.Key_A, Qt.MetaModifier)
        assert shortcut_service._detect_cmd_modifier(event) is True

        # Test avec ControlModifier (mappage Qt)
        event = mock_key_event(Qt.Key.Key_A, Qt.ControlModifier)
        assert shortcut_service._detect_cmd_modifier(event) is True

        # Test sans modificateur
        event = mock_key_event(Qt.Key.Key_A, Qt.NoModifier)
        assert shortcut_service._detect_cmd_modifier(event) is False

    @patch('sys.platform', 'win32')
    def test_detect_cmd_modifier_windows(self, shortcut_service, mock_key_event):
        """Test de détection des modificateurs sur Windows"""
        # Test avec ControlModifier
        event = mock_key_event(Qt.Key.Key_A, Qt.ControlModifier)
        assert shortcut_service._detect_cmd_modifier(event) is True

        # Test sans modificateur
        event = mock_key_event(Qt.Key.Key_A, Qt.NoModifier)
        assert shortcut_service._detect_cmd_modifier(event) is False

    def test_handle_new_row_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+N (nouvelle ligne)"""
        event = mock_key_event(Qt.Key.Key_N, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._add_new_row.assert_called_once()

    def test_handle_save_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+S (sauvegarder)"""
        event = mock_key_event(Qt.Key.Key_S, Qt.ControlModifier)
        # Mocker event.matches pour retourner True pour Save
        event.matches = Mock(side_effect=lambda key: key == QKeySequence.StandardKey.Save)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._manual_save.assert_called_once()

    def test_handle_find_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+F (rechercher)"""
        event = mock_key_event(Qt.Key.Key_F, Qt.ControlModifier)
        event.matches = Mock(side_effect=lambda key: key == QKeySequence.StandardKey.Find)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window.search_input.setFocus.assert_called_once()
        shortcut_service.parent_window.search_input.selectAll.assert_called_once()

    def test_handle_paste_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+V (coller)"""
        event = mock_key_event(Qt.Key.Key_V, Qt.ControlModifier)
        event.matches = Mock(side_effect=lambda key: key == QKeySequence.StandardKey.Paste)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._handle_paste.assert_called_once()

    def test_handle_copy_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+C (copier)"""
        event = mock_key_event(Qt.Key.Key_C, Qt.ControlModifier)
        event.matches = Mock(side_effect=lambda key: key == QKeySequence.StandardKey.Copy)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._handle_copy.assert_called_once()

    def test_handle_undo_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+Z (annuler)"""
        event = mock_key_event(Qt.Key.Key_Z, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._undo.assert_called_once()

    def test_handle_redo_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+Y (refaire)"""
        event = mock_key_event(Qt.Key.Key_Y, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._redo.assert_called_once()

    def test_handle_column_values_shortcut_allowed(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+D (valeurs colonne) - autorisé"""
        # Le focus n'est pas sur search_input
        shortcut_service.parent_window.focusWidget.return_value = Mock()
        event = mock_key_event(Qt.Key.Key_D, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._show_column_values_list.assert_called_once()

    def test_handle_column_values_shortcut_blocked(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+D (valeurs colonne) - bloqué par focus"""
        # Le focus est sur search_input
        shortcut_service.parent_window.focusWidget.return_value = shortcut_service.parent_window.search_input
        event = mock_key_event(Qt.Key.Key_D, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is False
        shortcut_service.parent_window._show_column_values_list.assert_not_called()

    def test_handle_navigation_up_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+Up (navigation vers le haut)"""
        event = mock_key_event(Qt.Key.Key_Up, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._navigate_to_empty_cell.assert_called_once_with(direction='up')

    def test_handle_navigation_down_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Cmd+Down (navigation vers le bas)"""
        event = mock_key_event(Qt.Key.Key_Down, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._navigate_to_empty_cell.assert_called_once_with(direction='down')

    def test_handle_f5_refresh_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci F5 (actualiser)"""
        event = mock_key_event(Qt.Key.Key_F5)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window.advanced_search_service.get_current_search_term_with_fallback.assert_called_once()
        # Config.USE_ASYNC_LOAD_DATA=True → load_data_async() est appelé
        shortcut_service.parent_window.table_controller.load_data_async.assert_called_once()

    def test_handle_f12_log_viewer_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci F12 (visualiseur de logs)"""
        event = mock_key_event(Qt.Key.Key_F12)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._open_log_viewer.assert_called_once()

    def test_handle_escape_clear_search_shortcut(self, shortcut_service, mock_key_event):
        """Test du raccourci Escape (effacer recherche)"""
        event = mock_key_event(Qt.Key.Key_Escape)

        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window.advanced_search_service.clear_search_ui.assert_called_once()

    def test_unhandled_shortcut(self, shortcut_service, mock_key_event):
        """Test d'un raccourci non géré"""
        event = mock_key_event(Qt.Key.Key_Q, Qt.ControlModifier)

        result = shortcut_service.handle_key_press_event(event)

        assert result is False

    def test_unhandled_function_key(self, shortcut_service, mock_key_event):
        """Test d'une touche fonction non gérée"""
        event = mock_key_event(Qt.Key.Key_F3)

        result = shortcut_service.handle_key_press_event(event)

        assert result is False

    def test_register_shortcut(self, shortcut_service):
        """Test de l'enregistrement d'un nouveau raccourci"""
        shortcut_service.register_shortcut(Qt.Key.Key_T, "test_action", "Action de test")

        assert Qt.Key.Key_T in shortcut_service.shortcut_actions
        assert shortcut_service.shortcut_actions[Qt.Key.Key_T] == ("test_action", "Action de test")

    def test_register_function_key_shortcut(self, shortcut_service):
        """Test de l'enregistrement d'un raccourci touche fonction"""
        shortcut_service.register_shortcut(Qt.Key.Key_F3, "test_f3", "F3 test", with_modifier=False)

        assert Qt.Key.Key_F3 in shortcut_service.function_key_shortcuts
        assert shortcut_service.function_key_shortcuts[Qt.Key.Key_F3] == ("test_f3", "F3 test")

    def test_unregister_shortcut(self, shortcut_service):
        """Test de la suppression d'un raccourci"""
        # Ajouter d'abord un raccourci
        shortcut_service.register_shortcut(Qt.Key.Key_T, "test_action", "Action de test")
        assert Qt.Key.Key_T in shortcut_service.shortcut_actions

        # Le supprimer
        shortcut_service.unregister_shortcut(Qt.Key.Key_T)
        assert Qt.Key.Key_T not in shortcut_service.shortcut_actions

    def test_get_registered_shortcuts(self, shortcut_service):
        """Test de l'obtention des raccourcis enregistrés"""
        shortcuts = shortcut_service.get_registered_shortcuts()

        assert "modifier_shortcuts" in shortcuts
        assert "standard_shortcuts" in shortcuts
        assert "function_key_shortcuts" in shortcuts
        assert isinstance(shortcuts["modifier_shortcuts"], dict)
        assert Qt.Key.Key_N in shortcuts["modifier_shortcuts"]

    def test_enable_focus_constraint(self, shortcut_service):
        """Test de l'activation d'une contrainte de focus"""
        test_key = Qt.Key.Key_T
        shortcut_service.enable_focus_constraint(test_key)

        assert test_key in shortcut_service.focus_dependent_shortcuts

    def test_disable_focus_constraint(self, shortcut_service):
        """Test de la désactivation d'une contrainte de focus"""
        test_key = Qt.Key.Key_D
        assert test_key in shortcut_service.focus_dependent_shortcuts

        shortcut_service.disable_focus_constraint(test_key)
        assert test_key not in shortcut_service.focus_dependent_shortcuts

    def test_signal_emission(self, shortcut_service, mock_key_event):
        """Test que les signaux sont émis correctement"""
        # On ne peut pas mocker directement les signaux PyQt5
        # On vérifie plutôt que les méthodes qui émettent les signaux fonctionnent
        event = mock_key_event(Qt.Key.Key_N, Qt.ControlModifier)
        result = shortcut_service.handle_key_press_event(event)

        assert result is True
        shortcut_service.parent_window._add_new_row.assert_called_once()

    def test_modifier_detection_signal(self, shortcut_service, mock_key_event):
        """Test que le signal de détection de modificateur fonctionne"""
        # Test que la détection de modificateur fonctionne correctement
        event = mock_key_event(Qt.Key.Key_N, Qt.ControlModifier)
        result = shortcut_service.handle_key_press_event(event)

        assert result is True

    def test_error_handling_no_parent(self, mock_key_event):
        """Test de la gestion d'erreur sans parent"""
        service = KeyboardShortcutService(parent=None)
        event = mock_key_event(Qt.Key.Key_N, Qt.ControlModifier)

        result = service.handle_key_press_event(event)

        assert result is False

    def test_error_handling_missing_method(self, shortcut_service, mock_key_event):
        """Test de la gestion d'erreur pour une méthode manquante"""
        # Supprimer une méthode du parent
        del shortcut_service.parent_window._add_new_row

        event = mock_key_event(Qt.Key.Key_N, Qt.ControlModifier)
        result = shortcut_service.handle_key_press_event(event)

        assert result is False

    def test_error_handling_invalid_event(self, shortcut_service):
        """Test de la gestion d'erreur pour un événement invalide"""
        # Événement None
        result = shortcut_service.handle_key_press_event(None)
        assert result is False

    def test_setup_default_shortcuts(self, shortcut_service):
        """Test que les raccourcis par défaut sont correctement configurés"""
        # Vérifier quelques raccourcis clés
        assert Qt.Key.Key_N in shortcut_service.shortcut_actions
        assert Qt.Key.Key_Z in shortcut_service.shortcut_actions
        assert "Save" in shortcut_service.standard_shortcuts
        assert Qt.Key.Key_F5 in shortcut_service.function_key_shortcuts
        assert Qt.Key.Key_Escape in shortcut_service.function_key_shortcuts


if __name__ == '__main__':
    pytest.main([__file__, '-v'])