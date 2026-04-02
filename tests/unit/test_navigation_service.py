"""
Tests unitaires pour NavigationService
Validation de la pagination et navigation sans régression
"""

import pytest
from unittest.mock import Mock, MagicMock
from PyQt5.QtWidgets import QLabel, QPushButton, QComboBox

from src.services.navigation_service import NavigationService


@pytest.mark.unit
@pytest.mark.critical
class TestNavigationService:
    """Tests critiques pour NavigationService"""

    @pytest.fixture
    def mock_table_controller(self):
        """Fixture table controller mockée"""
        controller = Mock()
        controller.load_data = Mock()
        controller.current_page = 1
        controller.page_size = 20
        return controller

    @pytest.fixture
    def mock_widgets(self, qapp):
        """Fixture widgets de pagination mockés"""
        from unittest.mock import Mock

        # Utiliser des mocks au lieu de vrais widgets pour les tests de validation
        widgets = {
            'page_label': Mock(),
            'prev_button': Mock(),
            'next_button': Mock(),
            'page_size_combo': Mock()
        }

        # Configurer les mocks
        widgets['page_label'].setText = Mock()
        widgets['prev_button'].setEnabled = Mock()
        widgets['next_button'].setEnabled = Mock()
        widgets['page_size_combo'].currentTextChanged = Mock()

        return widgets

    @pytest.fixture
    def navigation_service(self, mock_table_controller, mock_widgets):
        """Fixture service de navigation"""
        service = NavigationService(
            table_controller=mock_table_controller,
            parent=None  # PyQt5 ne peut pas accepter un Mock comme parent
        )

        # Configurer les widgets
        service.set_pagination_widgets(
            mock_widgets['page_label'],
            mock_widgets['prev_button'],
            mock_widgets['next_button'],
            mock_widgets['page_size_combo']
        )

        return service

    def test_service_initialization(self, navigation_service, mock_table_controller):
        """Test initialisation du service"""
        assert navigation_service.table_controller == mock_table_controller
        assert navigation_service.current_page == 1
        assert navigation_service.page_size == 500  # Config.DEFAULT_PAGE_SIZE
        assert navigation_service.total_rows == 0

    def test_set_pagination_widgets(self, navigation_service, mock_widgets):
        """Test configuration des widgets de pagination"""
        assert navigation_service.page_label == mock_widgets['page_label']
        assert navigation_service.prev_button == mock_widgets['prev_button']
        assert navigation_service.next_button == mock_widgets['next_button']
        assert navigation_service.page_size_combo == mock_widgets['page_size_combo']

    def test_update_total_rows(self, navigation_service):
        """Test mise à jour du total des lignes"""
        navigation_service.update_total_rows(150)
        assert navigation_service.total_rows == 150

    def test_get_total_pages(self, navigation_service):
        """Test calcul du nombre total de pages"""
        # Test avec 0 lignes
        navigation_service.total_rows = 0
        assert navigation_service.get_total_pages() == 1

        # Test avec 50 lignes, page size 20
        navigation_service.total_rows = 50
        navigation_service.page_size = 20
        assert navigation_service.get_total_pages() == 3  # 50/20 = 2.5 -> 3 pages

        # Test avec 40 lignes, page size 20
        navigation_service.total_rows = 40
        assert navigation_service.get_total_pages() == 2  # 40/20 = 2 pages exactes

    def test_next_page(self, navigation_service, mock_table_controller):
        """Test navigation page suivante"""
        # Configurer 3 pages de données
        navigation_service.total_rows = 50
        navigation_service.page_size = 20
        navigation_service.current_page = 1

        # Aller à la page suivante
        navigation_service.next_page()

        assert navigation_service.current_page == 2
        mock_table_controller.load_data.assert_called_once()

        # Essayer d'aller au-delà de la dernière page
        navigation_service.current_page = 3
        mock_table_controller.load_data.reset_mock()

        navigation_service.next_page()

        # Doit rester sur la dernière page
        assert navigation_service.current_page == 3
        mock_table_controller.load_data.assert_not_called()

    def test_previous_page(self, navigation_service, mock_table_controller):
        """Test navigation page précédente"""
        navigation_service.current_page = 2

        # Aller à la page précédente
        navigation_service.previous_page()

        assert navigation_service.current_page == 1
        mock_table_controller.load_data.assert_called_once()

        # Essayer d'aller en-dessous de la première page
        mock_table_controller.load_data.reset_mock()

        navigation_service.previous_page()

        # Doit rester sur la première page
        assert navigation_service.current_page == 1
        mock_table_controller.load_data.assert_not_called()

    def test_go_to_page(self, navigation_service, mock_table_controller):
        """Test navigation vers page spécifique"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20  # 5 pages

        # Page valide
        navigation_service.go_to_page(3)
        assert navigation_service.current_page == 3
        mock_table_controller.load_data.assert_called()

        # Page invalide (trop haute)
        mock_table_controller.load_data.reset_mock()
        navigation_service.go_to_page(10)
        assert navigation_service.current_page == 3  # Doit rester inchangé
        mock_table_controller.load_data.assert_not_called()

        # Page invalide (trop basse)
        navigation_service.go_to_page(0)
        assert navigation_service.current_page == 3  # Doit rester inchangé

    def test_go_to_first_page(self, navigation_service, mock_table_controller):
        """Test navigation vers première page"""
        navigation_service.current_page = 5

        navigation_service.go_to_first_page()

        assert navigation_service.current_page == 1
        mock_table_controller.load_data.assert_called_once()

    def test_go_to_last_page(self, navigation_service, mock_table_controller):
        """Test navigation vers dernière page"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20  # 5 pages
        navigation_service.current_page = 1

        navigation_service.go_to_last_page()

        assert navigation_service.current_page == 5
        mock_table_controller.load_data.assert_called_once()

    def test_change_page_size(self, navigation_service, mock_table_controller):
        """Test changement de taille de page"""
        navigation_service.current_page = 3
        navigation_service.total_rows = 100

        # Changer la taille de page
        navigation_service.change_page_size("50")

        assert navigation_service.page_size == 50
        assert navigation_service.current_page == 1  # Doit revenir à page 1
        mock_table_controller.load_data.assert_called_once()

        # Test avec valeur invalide
        mock_table_controller.load_data.reset_mock()
        navigation_service.change_page_size("invalid")

        # Ne doit pas changer
        assert navigation_service.page_size == 50
        mock_table_controller.load_data.assert_not_called()

    def test_update_pagination_controls(self, navigation_service, mock_widgets):
        """Test mise à jour des contrôles de pagination"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20
        navigation_service.current_page = 3

        navigation_service.update_pagination_controls()

        # Vérifier que le label a été mis à jour
        expected_text = "Page 3 sur 5"
        mock_widgets['page_label'].setText.assert_called_with(expected_text)

        # Vérifier l'état des boutons
        mock_widgets['prev_button'].setEnabled.assert_called_with(True)  # Page 3 > 1
        mock_widgets['next_button'].setEnabled.assert_called_with(True)  # Page 3 < 5

    def test_pagination_controls_first_page(self, navigation_service, mock_widgets):
        """Test contrôles sur la première page"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20
        navigation_service.current_page = 1

        navigation_service.update_pagination_controls()

        mock_widgets['prev_button'].setEnabled.assert_called_with(False)  # Désactivé
        mock_widgets['next_button'].setEnabled.assert_called_with(True)   # Activé

    def test_pagination_controls_last_page(self, navigation_service, mock_widgets):
        """Test contrôles sur la dernière page"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20
        navigation_service.current_page = 5  # Dernière page

        navigation_service.update_pagination_controls()

        mock_widgets['prev_button'].setEnabled.assert_called_with(True)   # Activé
        mock_widgets['next_button'].setEnabled.assert_called_with(False)  # Désactivé

    def test_get_current_page_info(self, navigation_service):
        """Test récupération des informations de page"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20
        navigation_service.current_page = 3

        info = navigation_service.get_current_page_info()

        expected = {
            'current_page': 3,
            'total_pages': 5,
            'page_size': 20,
            'total_rows': 100,
            'start_row': 41,  # (3-1) * 20 + 1
            'end_row': 60     # min(3 * 20, 100)
        }

        assert info == expected

    def test_reset_pagination(self, navigation_service):
        """Test réinitialisation de la pagination"""
        navigation_service.current_page = 5
        navigation_service.total_rows = 100

        navigation_service.reset_pagination()

        assert navigation_service.current_page == 1
        assert navigation_service.total_rows == 0

    def test_handle_navigation_shortcut(self, navigation_service, mock_table_controller):
        """Test gestion des raccourcis de navigation"""
        navigation_service.total_rows = 100
        navigation_service.page_size = 20
        navigation_service.current_page = 3

        # Test raccourci page suivante
        navigation_service.handle_navigation_shortcut("Ctrl+Right")
        assert navigation_service.current_page == 4

        # Test raccourci page précédente
        navigation_service.handle_navigation_shortcut("Ctrl+Left")
        assert navigation_service.current_page == 3

        # Test raccourci première page
        navigation_service.handle_navigation_shortcut("Ctrl+Home")
        assert navigation_service.current_page == 1

        # Test raccourci dernière page
        navigation_service.handle_navigation_shortcut("Ctrl+End")
        assert navigation_service.current_page == 5

        # Test raccourci inconnu
        old_page = navigation_service.current_page
        navigation_service.handle_navigation_shortcut("Unknown")
        assert navigation_service.current_page == old_page

    def test_signal_emission(self, navigation_service):
        """Test émission des signaux"""
        # Mock des signaux
        navigation_service.page_changed = Mock()
        navigation_service.page_size_changed = Mock()
        navigation_service.navigation_requested = Mock()

        # Mock du table_controller.load_data pour éviter les erreurs
        navigation_service.table_controller.load_data = Mock()

        # Test signal changement de page
        navigation_service.total_rows = 100
        navigation_service.page_size = 20  # S'assurer d'avoir un page_size valide
        navigation_service.go_to_page(3)
        navigation_service.page_changed.emit.assert_called_with(3)

        # Test signal changement taille de page
        navigation_service.change_page_size("50")
        navigation_service.page_size_changed.emit.assert_called_with(50)

        # Test signal navigation - next_page
        navigation_service.total_rows = 100
        navigation_service.page_size = 20
        navigation_service.current_page = 2  # Page dans la plage valide
        navigation_service.next_page()
        navigation_service.navigation_requested.emit.assert_called_with("next")

    def test_edge_cases(self, navigation_service):
        """Test cas limites"""
        # Taille de page 0
        navigation_service.page_size = 0
        assert navigation_service.get_total_pages() == 1

        # Total rows négatif
        navigation_service.total_rows = -10
        assert navigation_service.get_total_pages() == 1

        # Page actuelle plus grande que le total
        navigation_service.total_rows = 20
        navigation_service.page_size = 10
        navigation_service.current_page = 5  # Devrait être max 2

        info = navigation_service.get_current_page_info()
        # La logique devrait gérer ce cas gracieusement

    def test_widgets_none_handling(self, mock_table_controller):
        """Test gestion des widgets None"""
        service = NavigationService(mock_table_controller, None)

        # Ne pas planter si les widgets ne sont pas définis
        service.update_pagination_controls()  # Ne doit pas lever d'exception

    def test_large_dataset(self, navigation_service):
        """Test avec grand dataset"""
        # 1 million de lignes
        navigation_service.total_rows = 1000000
        navigation_service.page_size = 100

        assert navigation_service.get_total_pages() == 10000

        # Navigation au milieu
        navigation_service.go_to_page(5000)
        assert navigation_service.current_page == 5000

        info = navigation_service.get_current_page_info()
        assert info['start_row'] == 499901  # (5000-1) * 100 + 1
        assert info['end_row'] == 500000    # 5000 * 100