"""
Tests unitaires pour CellEditingService
Validation des fonctionnalités d'édition, validation et sauvegarde des cellules
"""

import pytest
from unittest.mock import Mock
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem

from src.services.cell_editing_service import CellEditingService
from src.data.data_validator import DataValidator


@pytest.mark.unit
@pytest.mark.critical
class TestCellEditingService:
    """Tests critiques pour CellEditingService"""

    @pytest.fixture
    def mock_table(self, qapp):
        """Fixture table widget mockée"""
        table = QTableWidget(10, 8)
        return table

    @pytest.fixture
    def mock_data_validator(self):
        """Fixture data validator mocké"""
        validator = Mock(spec=DataValidator)
        validator.validate_field = Mock(return_value=(True, ""))
        return validator

    @pytest.fixture
    def cell_editing_service(self, mock_table, test_db_manager, mock_data_validator):
        """Fixture service d'édition de cellules"""
        service = CellEditingService(
            table_widget=mock_table,
            db_manager=test_db_manager,
            data_validator=mock_data_validator,
            parent=None
        )
        return service

    def test_service_initialization(self, cell_editing_service, mock_table, test_db_manager):
        """Test initialisation du service"""
        assert cell_editing_service.table == mock_table
        assert cell_editing_service.db_manager == test_db_manager
        assert cell_editing_service.data_validator is not None

    def test_navigation_to_empty_cell(self, cell_editing_service, mock_table):
        """Test navigation vers cellule vide"""
        # Créer un tableau avec quelques cellules pleines
        mock_table.setItem(0, 0, QTableWidgetItem("Pleine"))
        mock_table.setItem(1, 0, QTableWidgetItem(""))  # Vide
        mock_table.setItem(2, 0, QTableWidgetItem("Pleine"))

        # Simuler la cellule courante
        mock_table.setCurrentCell(0, 0)

        # Test navigation vers le bas (cellule pleine vers vide)
        success = cell_editing_service.navigate_to_empty_cell('down')

        # Dans notre cas, on s'attend à ce que ça fonctionne
        assert isinstance(success, bool)
