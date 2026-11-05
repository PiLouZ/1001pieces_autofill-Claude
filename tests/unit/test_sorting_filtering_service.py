"""
Tests unitaires pour SortingFilteringService
Validation du tri et filtrage de table sans régression
"""

import pytest
from unittest.mock import Mock
from PyQt5.QtWidgets import QTableWidget, QHeaderView
from PyQt5.QtCore import Qt

from src.services.sorting_filtering_service import SortingFilteringService


@pytest.mark.unit
@pytest.mark.critical
class TestSortingFilteringService:
    """Tests critiques pour SortingFilteringService"""

    @pytest.fixture
    def mock_table(self, qapp):
        """Fixture table widget mockée"""
        table = QTableWidget(10, 8)

        # Mock du header
        header = Mock(spec=QHeaderView)
        table.horizontalHeader = Mock(return_value=header)

        return table

    @pytest.fixture
    def mock_table_controller(self):
        """Fixture table controller mockée"""
        controller = Mock()
        controller.load_data = Mock()
        controller.current_sort_column = -1
        controller.current_sort_order = Qt.SortOrder.AscendingOrder
        controller.column_filters = {}
        controller.incomplete_filter = False
        return controller

    @pytest.fixture
    def mock_parent_window(self):
        """Fixture fenêtre parent mockée"""
        parent = Mock()

        # Mock du service de recherche avancée
        advanced_search_service = Mock()
        advanced_search_service.get_current_search_term_with_fallback = Mock(return_value=None)
        parent.advanced_search_service = advanced_search_service

        return parent

    @pytest.fixture
    def sorting_service(self, mock_table, mock_table_controller, mock_parent_window):
        """Fixture service de tri/filtrage"""
        service = SortingFilteringService(
            table_widget=mock_table,
            table_controller=mock_table_controller,
            parent=None  # PyQt5 ne peut pas accepter un Mock comme parent
        )
        # Ajouter la référence mockée manuellement
        service.parent_window = mock_parent_window
        return service

    def test_service_initialization(self, sorting_service, mock_table, mock_table_controller):
        """Test initialisation du service"""
        assert sorting_service.table == mock_table
        assert sorting_service.table_controller == mock_table_controller
        assert sorting_service.active_column_filters == {}
        assert not sorting_service.incomplete_filter_active

    def test_clear_column_filters(self, sorting_service, mock_table_controller):
        """Test suppression de tous les filtres de colonnes"""
        # Ajouter quelques filtres
        sorting_service.active_column_filters = {1: 'filter1', 3: 'filter2'}

        # Supprimer tous les filtres
        sorting_service.clear_column_filters()

        # Vérifications
        assert sorting_service.active_column_filters == {}
        mock_table_controller.load_data.assert_called_once()

    def test_toggle_incomplete_filter(self, sorting_service, mock_table_controller):
        """Test basculement du filtre lignes incomplètes"""
        # État initial
        assert not sorting_service.incomplete_filter_active

        # Premier basculement - activer
        sorting_service.toggle_incomplete_filter()
        assert sorting_service.incomplete_filter_active
        mock_table_controller.load_data.assert_called_once()

        # Deuxième basculement - désactiver
        mock_table_controller.load_data.reset_mock()
        sorting_service.toggle_incomplete_filter()
        assert not sorting_service.incomplete_filter_active
        mock_table_controller.load_data.assert_called_once()

        # Pas d'exception attendue

    def test_reload_with_search_term(self, sorting_service, mock_parent_window, mock_table_controller):
        """Test rechargement avec terme de recherche"""
        # Configurer un terme de recherche
        mock_parent_window.advanced_search_service.get_current_search_term_with_fallback.return_value = "test search"

        # Recharger
        sorting_service._reload_with_current_filters()

        # Vérifier que load_data est appelé avec le terme de recherche
        mock_table_controller.load_data.assert_called_once_with("test search", is_search=True)

    def test_multiple_filters_interaction(self, sorting_service, mock_table_controller):
        """Test interaction entre filtres multiples"""
        # Ajouter plusieurs filtres de colonnes
        sorting_service.active_column_filters = {1: 'filter1', 2: 'filter2'}
        sorting_service.incomplete_filter_active = True

        # Configurer le tri
        sorting_service.current_sort_column = 3
        sorting_service.current_sort_order = Qt.SortOrder.DescendingOrder

        # Recharger avec tous les filtres
        sorting_service._reload_with_current_filters()

        # Vérifier que les filtres sont passés au contrôleur
        assert mock_table_controller.column_filters == {1: 'filter1', 2: 'filter2'}
        assert mock_table_controller.incomplete_filter == True
        mock_table_controller.load_data.assert_called_once()