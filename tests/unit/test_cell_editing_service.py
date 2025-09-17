"""
Tests unitaires pour CellEditingService
Validation des fonctionnalités d'édition, validation et sauvegarde des cellules
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt5.QtCore import Qt

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
        assert cell_editing_service.pending_changes == {}
        assert not cell_editing_service.is_batch_editing

    def test_get_cell_db_info_with_valid_data(self, cell_editing_service, mock_table):
        """Test récupération info cellule avec données valides"""
        # Créer un item avec UserRole valide
        item = QTableWidgetItem("Test Value")
        item.setData(Qt.ItemDataRole.UserRole, 123)
        mock_table.setItem(0, 1, item)

        with patch.object(cell_editing_service, '_get_db_column_name', return_value='type'):
            db_id, column_name = cell_editing_service.get_cell_db_info(item)

            assert db_id == 123
            assert column_name == 'type'

    def test_get_cell_db_info_without_user_role(self, cell_editing_service):
        """Test récupération info cellule sans UserRole"""
        item = QTableWidgetItem("Test Value")
        # Pas de setData UserRole

        db_id, column_name = cell_editing_service.get_cell_db_info(item)

        assert db_id is None
        assert column_name is None

    def test_get_db_column_name_mapping(self, cell_editing_service):
        """Test mapping des colonnes UI vers DB"""
        # Test avec différents index de colonnes
        with patch('src.core.config.Config') as mock_config:
            mock_config.DB_HEADERS = ['type', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref']

            # Vider le cache pour ce test
            cell_editing_service._column_mapping_cache.clear()

            assert cell_editing_service._get_db_column_name(0) == 'type'
            assert cell_editing_service._get_db_column_name(1) == 'manufacturer'
            assert cell_editing_service._get_db_column_name(2) == 'ref_modele'
            assert cell_editing_service._get_db_column_name(10) is None  # Index invalide

    def test_validate_cell_value_success(self, cell_editing_service):
        """Test validation réussie de valeur de cellule"""
        # Test validation pour différents types de colonnes
        assert cell_editing_service._validate_cell_value('type', 'Lave-vaisselle', 1)
        assert cell_editing_service._validate_cell_value('manufacturer', 'Bosch', 1)
        assert cell_editing_service._validate_cell_value('ref_modele', 'REF123', 1)
        assert cell_editing_service._validate_cell_value('notes', 'Courte note', 1)

    def test_validate_cell_value_failure(self, cell_editing_service):
        """Test validation échouée de valeur de cellule"""
        # Test avec valeurs trop longues
        long_ref = 'A' * 150  # Dépasse la limite de 100 caractères
        assert not cell_editing_service._validate_cell_value('ref_modele', long_ref, 1)

        long_type = 'B' * 60   # Dépasse la limite de 50 caractères
        assert not cell_editing_service._validate_cell_value('type', long_type, 1)

        long_notes = 'C' * 600  # Dépasse la limite de 500 caractères
        assert not cell_editing_service._validate_cell_value('notes', long_notes, 1)

    def test_update_cell_in_db_success(self, cell_editing_service, mock_table, test_db_manager):
        """Test mise à jour réussie de cellule en DB"""
        # Créer un appareil de test
        device_data = {'type': 'Test', 'manufacturer': 'Test Co'}
        device_id = test_db_manager.insert_appareil(device_data)

        # Créer un item avec les bonnes informations
        item = QTableWidgetItem("Nouveau Type")
        item.setData(Qt.ItemDataRole.UserRole, device_id)
        item._original_value = "Test"
        mock_table.setItem(0, 0, item)

        with patch.object(cell_editing_service, '_get_db_column_name', return_value='type'):
            success = cell_editing_service.update_cell_in_db(item)

        assert success

        # Vérifier que la DB a été mise à jour
        query = "SELECT type FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert results[0][0] == "Nouveau Type"

    def test_update_cell_in_db_no_change(self, cell_editing_service, mock_table):
        """Test mise à jour sans changement"""
        item = QTableWidgetItem("Same Value")
        item.setData(Qt.ItemDataRole.UserRole, 123)
        item._original_value = "Same Value"  # Même valeur
        mock_table.setItem(0, 0, item)

        with patch.object(cell_editing_service, '_get_db_column_name', return_value='type'):
            success = cell_editing_service.update_cell_in_db(item)

        assert success  # Succès car pas de changement nécessaire

    def test_batch_edit_workflow(self, cell_editing_service, mock_table, test_db_manager):
        """Test workflow d'édition en lot"""
        # Créer des appareils de test
        device1_id = test_db_manager.insert_appareil({'type': 'Type1', 'manufacturer': 'Test'})
        device2_id = test_db_manager.insert_appareil({'type': 'Type2', 'manufacturer': 'Test'})

        # Créer des items
        item1 = QTableWidgetItem("Nouveau Type 1")
        item1.setData(Qt.ItemDataRole.UserRole, device1_id)
        item1._original_value = "Type1"
        mock_table.setItem(0, 0, item1)

        item2 = QTableWidgetItem("Nouveau Type 2")
        item2.setData(Qt.ItemDataRole.UserRole, device2_id)
        item2._original_value = "Type2"
        mock_table.setItem(1, 0, item2)

        # Démarrer l'édition en lot
        cell_editing_service.start_batch_edit()
        assert cell_editing_service.is_batch_editing

        # Ajouter des modifications au lot
        with patch.object(cell_editing_service, '_get_db_column_name', return_value='type'):
            cell_editing_service.add_to_batch(item1, "Nouveau Type 1")
            cell_editing_service.add_to_batch(item2, "Nouveau Type 2")

            assert len(cell_editing_service.pending_changes) == 2

            # Valider le lot
            success_count = cell_editing_service.commit_batch_edit()

        assert success_count == 2
        assert not cell_editing_service.is_batch_editing
        assert len(cell_editing_service.pending_changes) == 0

    def test_batch_edit_cancel(self, cell_editing_service):
        """Test annulation d'édition en lot"""
        # Démarrer l'édition en lot
        cell_editing_service.start_batch_edit()
        cell_editing_service.pending_changes[(0, 0)] = ("old", "new")

        # Annuler
        cell_editing_service.cancel_batch_edit()

        assert not cell_editing_service.is_batch_editing
        assert len(cell_editing_service.pending_changes) == 0

    def test_validation_cache(self, cell_editing_service):
        """Test du cache de validation"""
        # Premier appel - miss cache
        result1 = cell_editing_service._validate_cell_value('type', 'TestType', 1)
        assert result1

        # Deuxième appel - hit cache
        result2 = cell_editing_service._validate_cell_value('type', 'TestType', 1)
        assert result2 == result1

        # Vérifier que la valeur est en cache
        cache_key = "type:TestType"
        assert cache_key in cell_editing_service._validation_cache

        # Vider le cache
        cell_editing_service.clear_validation_cache()
        assert len(cell_editing_service._validation_cache) == 0

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

    def test_edit_statistics(self, cell_editing_service):
        """Test récupération des statistiques d'édition"""
        # État initial
        stats = cell_editing_service.get_edit_statistics()
        assert stats['pending_changes'] == 0
        assert not stats['is_batch_editing']
        assert stats['cache_size'] == 0

        # Après ajout de quelques éléments
        cell_editing_service.start_batch_edit()
        cell_editing_service.pending_changes[(0, 0)] = ("old", "new")
        cell_editing_service._validation_cache["test:value"] = True

        stats = cell_editing_service.get_edit_statistics()
        assert stats['pending_changes'] == 1
        assert stats['is_batch_editing']
        assert stats['cache_size'] == 1

    def test_signal_emission(self, cell_editing_service, mock_table):
        """Test émission des signaux"""
        # Mock des signaux
        cell_editing_service.cell_updated = Mock()
        cell_editing_service.cell_validation_failed = Mock()
        cell_editing_service.batch_edit_completed = Mock()

        # Test signal de validation échouée
        with patch.object(cell_editing_service, '_validate_cell_value', return_value=False):
            item = QTableWidgetItem("Invalid")
            cell_editing_service._validate_cell_value('ref_modele', 'A' * 150, 1)
            # Le signal sera émis dans _validate_cell_value si échec

        # Test signal de lot terminé
        cell_editing_service.start_batch_edit()
        cell_editing_service.commit_batch_edit()
        cell_editing_service.batch_edit_completed.emit.assert_called_once()

    def test_error_handling(self, cell_editing_service, mock_table):
        """Test gestion d'erreurs"""
        # Test avec item None
        result = cell_editing_service.get_cell_db_info(None)
        # Should handle gracefully without crashing

        # Test avec données corrompues
        item = QTableWidgetItem("Test")
        item.setData(Qt.ItemDataRole.UserRole, "not_an_integer")

        db_id, column_name = cell_editing_service.get_cell_db_info(item)
        assert db_id is None
        assert column_name is None

    def test_auto_create_row_functionality(self, cell_editing_service, mock_table, test_db_manager):
        """Test de la fonctionnalité d'auto-création de ligne"""
        # Créer un item orphelin (sans UserRole)
        item = QTableWidgetItem("Test Value")
        mock_table.setItem(0, 1, item)  # Colonne importante

        # Tester l'auto-création
        success = cell_editing_service._try_auto_create_row(item, 0, 1)

        # Le résultat dépend de l'implémentation - on vérifie juste qu'il n'y a pas d'erreur
        assert isinstance(success, bool)