"""
Tests unitaires pour SortingFilteringService
Validation du tri et filtrage de table sans régression
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
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
        assert sorting_service.current_sort_column == -1
        assert sorting_service.current_sort_order == Qt.SortOrder.AscendingOrder
        assert sorting_service.active_column_filters == {}
        assert not sorting_service.incomplete_filter_active

    def test_setup_sorting(self, sorting_service, mock_table):
        """Test configuration du tri"""
        # Setup sorting
        sorting_service.setup_sorting()

        # Vérifier que le signal est connecté
        header = mock_table.horizontalHeader()
        header.sectionClicked.connect.assert_called_once()

    def test_header_click_new_column(self, sorting_service):
        """Test clic sur nouvelle colonne"""
        # Simuler clic sur colonne 1
        sorting_service.on_header_clicked(1)

        # Vérifications
        assert sorting_service.current_sort_column == 1
        assert sorting_service.current_sort_order == Qt.SortOrder.AscendingOrder

    def test_header_click_same_column_toggle(self, sorting_service):
        """Test clic sur même colonne - basculement"""
        # Premier clic - ASC
        sorting_service.on_header_clicked(1)
        assert sorting_service.current_sort_order == Qt.SortOrder.AscendingOrder

        # Deuxième clic - DESC
        sorting_service.on_header_clicked(1)
        assert sorting_service.current_sort_order == Qt.SortOrder.DescendingOrder

        # Troisième clic - ASC
        sorting_service.on_header_clicked(1)
        assert sorting_service.current_sort_order == Qt.SortOrder.AscendingOrder

    def test_apply_database_sort(self, sorting_service, mock_table_controller):
        """Test application du tri en base"""
        # Configurer le tri
        sorting_service.current_sort_column = 2
        sorting_service.current_sort_order = Qt.SortOrder.DescendingOrder

        # Appliquer le tri
        sorting_service.apply_database_sort()

        # Vérifier synchronisation avec TableController
        assert mock_table_controller.current_sort_column == 2
        assert mock_table_controller.current_sort_order == Qt.SortOrder.DescendingOrder

        # Vérifier rechargement des données
        mock_table_controller.load_data.assert_called_once()

    def test_update_sort_indicators(self, sorting_service, mock_table):
        """Test mise à jour des indicateurs de tri"""
        with patch('src.services.sorting_filtering_service.Config') as mock_config:
            mock_config.DB_HEADERS = ['Type', 'Manufacturer', 'Model']

            # Configurer le tri sur colonne 1 ASC
            sorting_service.current_sort_column = 1
            sorting_service.current_sort_order = Qt.SortOrder.AscendingOrder

            # Mock des items d'en-tête
            mock_items = []
            for i in range(4):  # 3 DB_HEADERS + 1 "Nb Pièces"
                item = Mock()
                mock_items.append(item)

            mock_table.horizontalHeaderItem = Mock(side_effect=lambda i: mock_items[i])
            mock_table.setHorizontalHeaderItem = Mock()

            # Mettre à jour les indicateurs
            sorting_service.update_sort_indicators()

            # Vérifier les appels
            assert mock_table.setHorizontalHeaderItem.call_count == 4

    def test_column_filter_with_debounce(self, sorting_service):
        """Test filtrage de colonne avec debounce"""
        # Appliquer un filtre
        sorting_service.apply_column_filter(1, "test filter")

        # Vérifier que le filtre est en attente
        assert sorting_service.pending_column_filter['column'] == 1
        assert sorting_service.pending_column_filter['text'] == "test filter"

        # Vérifier que le timer est démarré
        assert sorting_service.column_filter_timer.isActive()

    def test_perform_delayed_column_filter(self, sorting_service, mock_table_controller):
        """Test exécution du filtre après délai"""
        # Configurer un filtre en attente
        sorting_service.pending_column_filter = {'column': 2, 'text': 'filter text'}

        # Exécuter le filtre
        sorting_service._perform_delayed_column_filter()

        # Vérifier que le filtre est ajouté
        assert 2 in sorting_service.active_column_filters
        assert sorting_service.active_column_filters[2] == 'filter text'

        # Vérifier rechargement
        mock_table_controller.load_data.assert_called_once()

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

    def test_get_current_sort_state(self, sorting_service):
        """Test récupération de l'état du tri"""
        with patch('src.services.sorting_filtering_service.Config') as mock_config:
            mock_config.DB_HEADERS = ['Type', 'Manufacturer', 'Model']

            # Configurer le tri
            sorting_service.current_sort_column = 1
            sorting_service.current_sort_order = Qt.SortOrder.DescendingOrder

            # Obtenir l'état
            state = sorting_service.get_current_sort_state()

            # Vérifications
            assert state['column'] == 1
            assert state['order'] == Qt.SortOrder.DescendingOrder
            assert state['column_name'] == 'Manufacturer'

    def test_get_active_filters(self, sorting_service):
        """Test récupération des filtres actifs"""
        # Ajouter des filtres
        sorting_service.active_column_filters = {1: 'filter1', 3: 'filter2'}
        sorting_service.incomplete_filter_active = True

        # Obtenir les filtres
        filters = sorting_service.get_active_filters()

        # Vérifications
        assert filters['column_filters'] == {1: 'filter1', 3: 'filter2'}
        assert filters['incomplete_filter'] == True
        assert filters['filter_count'] == 3  # 2 colonnes + 1 incomplet

    def test_reset_sorting(self, sorting_service, mock_table_controller):
        """Test réinitialisation du tri"""
        # Configurer un tri
        sorting_service.current_sort_column = 2
        sorting_service.current_sort_order = Qt.SortOrder.DescendingOrder

        # Réinitialiser
        sorting_service.reset_sorting()

        # Vérifications
        assert sorting_service.current_sort_column == -1
        assert sorting_service.current_sort_order == Qt.SortOrder.AscendingOrder
        mock_table_controller.load_data.assert_called_once()

    def test_set_sort(self, sorting_service, mock_table_controller):
        """Test définition d'un tri spécifique"""
        # Définir un tri
        sorting_service.set_sort(3, Qt.SortOrder.DescendingOrder)

        # Vérifications
        assert sorting_service.current_sort_column == 3
        assert sorting_service.current_sort_order == Qt.SortOrder.DescendingOrder
        mock_table_controller.load_data.assert_called_once()

    def test_signal_emission(self, sorting_service):
        """Test émission des signaux"""
        # Mock des signaux
        sorting_service.sort_changed = Mock()
        sorting_service.filter_applied = Mock()

        # Test signal de tri
        sorting_service.on_header_clicked(1)
        sorting_service.sort_changed.emit.assert_called_once_with(1, Qt.SortOrder.AscendingOrder)

        # Test signal de filtre
        sorting_service.pending_column_filter = {'column': 2, 'text': 'test'}
        sorting_service._perform_delayed_column_filter()
        sorting_service.filter_applied.emit.assert_called_once()

    def test_error_handling(self, sorting_service):
        """Test gestion d'erreurs"""
        # Test avec table_controller None
        sorting_service.table_controller = None

        # Ces opérations ne doivent pas planter
        sorting_service.apply_database_sort()
        sorting_service._reload_with_current_filters()
        sorting_service.clear_column_filters()

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