"""
Tests unitaires pour DatabaseOperationsService
Validation des opérations CRUD sans régression
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem
from PyQt5.QtCore import Qt

from src.services.database_operations_service import DatabaseOperationsService


@pytest.mark.unit
@pytest.mark.critical
class TestDatabaseOperationsService:
    """Tests critiques pour DatabaseOperationsService"""

    @pytest.fixture
    def mock_parent_window(self):
        """Fixture fenêtre parent mockée"""
        parent = Mock()

        # Mock tous les services requis
        parent.db_manager = Mock()
        parent.table_controller = Mock()
        parent.user_interaction_service = Mock()
        parent.table_fill_service = Mock()
        parent.cell_editing_service = Mock()
        parent.cache_service = Mock()

        # Mock des attributs UI
        parent.modified_cells = set()
        parent.table = Mock()
        parent.save_indicator = Mock()
        parent.statusbar = Mock()

        return parent

    @pytest.fixture
    def database_service(self, mock_parent_window, qapp):
        """Fixture service d'opérations de base de données"""
        service = DatabaseOperationsService(
            parent_window=mock_parent_window,
            parent=None
        )

        # Initialiser les services
        service.initialize_services()

        return service

    def test_service_initialization(self, database_service, mock_parent_window):
        """Test initialisation du service"""
        assert database_service.parent_window == mock_parent_window
        assert database_service.db_manager == mock_parent_window.db_manager
        assert database_service.parent_window.table_controller == mock_parent_window.table_controller
        assert database_service.modified_cells == mock_parent_window.modified_cells
        assert not database_service.save_in_progress

    def test_initialize_services(self, mock_parent_window):
        """Test initialisation des références de services"""
        service = DatabaseOperationsService(mock_parent_window)

        # db_manager injecté via _required_services lors de initialize_services
        # table_controller est accédé via parent_window (pas un attribut direct)
        # Après initialisation
        service.initialize_services()
        assert service.db_manager == mock_parent_window.db_manager
        assert service.parent_window.table_controller == mock_parent_window.table_controller

    def test_add_new_device_success(self, database_service):
        """Test ajout nouvel appareil - succès"""
        device_data = {
            'type': 'Lave-linge',
            'marque': 'Samsung',
            'modele': 'WF80F5E3U4W',
            'reference': 'REF001',
            'designation': 'Lave-linge frontal',
            'prix': '399.99',
            'stock': '5',
            'notes': 'En promotion'
        }

        # Mock du retour de base
        database_service.db_manager.add_device.return_value = 123
        database_service.db_manager.get_device_by_reference.return_value = None  # Pas de doublon

        device_id = database_service.add_new_device(device_data)

        # Vérifications
        assert device_id == 123
        database_service.db_manager.add_device.assert_called_once_with(device_data)
        database_service.parent_window.table_controller.load_data.assert_called_once()
        database_service.cache_service.invalidate_all.assert_called_once()
        database_service.user_interaction_service.add_to_history.assert_called_once()

    def test_add_new_device_sans_service_interaction(self, database_service):
        """Cas réel (3.77.2) : user_interaction_service absent, comme en production.
        L'appareil est créé : l'ID doit revenir et le signal partir. Avant, les deux
        étaient indentés sous le `if` du service → None et faux « Échec de l'ajout »
        (35 fois entre le 2026-09-08 et le 2026-10-07)."""
        database_service.user_interaction_service = None
        database_service.db_manager.add_device.return_value = 785257
        recus = []
        database_service.device_added.connect(recus.append)

        assert database_service.add_new_device() == 785257   # ligne vide (Cmd+N)
        assert recus == [785257]

    def test_add_new_device_with_defaults(self, database_service):
        """Test ajout nouvel appareil avec données par défaut"""
        # Données par défaut avec référence valide
        default_data = {
            'reference': 'DEFAULT_REF'  # Référence valide pour passer la validation
        }

        database_service.db_manager.add_device.return_value = 124
        database_service.db_manager.get_device_by_reference.return_value = None

        device_id = database_service.add_new_device(default_data)

        # Vérifier que l'ajout a réussi
        assert device_id == 124
        database_service.db_manager.add_device.assert_called_once()

    def test_add_new_device_validation_error(self, database_service):
        """Test ajout appareil avec erreur de validation"""
        device_data = {
            'reference': '',  # Référence vide - erreur
            'prix': 'invalid_price',  # Prix invalide
            'stock': '-5'  # Stock négatif
        }

        device_id = database_service.add_new_device(device_data)

        # Vérifications
        assert device_id is None
        database_service.db_manager.add_device.assert_not_called()
        database_service.user_interaction_service.show_error.assert_called_once()

    def test_add_new_device_duplicate_reference(self, database_service):
        """Test ajout appareil avec référence dupliquée"""
        device_data = {'reference': 'REF_EXISTING'}

        # Mock d'un appareil existant
        database_service.db_manager.get_device_by_reference.return_value = {'id': 999}

        device_id = database_service.add_new_device(device_data)

        # Vérifications
        assert device_id is None
        database_service.db_manager.add_device.assert_not_called()

    def test_validate_device_data_success(self, database_service):
        """Test validation données appareil - succès"""
        device_data = {
            'reference': 'REF001',
            'marque': 'Samsung',
            'modele': 'Test',
            'prix': '299.99',
            'stock': '10',
            'notes': 'Test notes'
        }

        database_service.db_manager.get_device_by_reference.return_value = None

        is_valid, errors = database_service.validate_device_data(device_data)

        assert is_valid
        assert len(errors) == 0

    def test_validate_device_data_errors(self, database_service):
        """Test validation données appareil - erreurs"""
        device_data = {
            'reference': '',  # Vide
            'marque': 'A' * 150,  # Trop long
            'prix': 'invalid',  # Invalide
            'stock': '-1',  # Négatif
            'notes': 'A' * 1500  # Trop long
        }

        is_valid, errors = database_service.validate_device_data(device_data)

        assert not is_valid
        assert len(errors) >= 5
        assert any('référence est obligatoire' in error for error in errors)
        assert any('marque ne peut pas dépasser' in error for error in errors)
        assert any('prix doit être un nombre' in error for error in errors)
        assert any('stock ne peut pas être négatif' in error for error in errors)

    def test_save_cells_batch_success(self, database_service):
        """Test sauvegarde batch - succès"""
        updates_by_db_id = {
            123: {'marque': 'Samsung', 'prix': '399.99'},
            124: {'stock': '10', 'notes': 'Updated'}
        }

        database_service.db_manager.update_multiple_cells_batch.return_value = True

        success = database_service.save_cells_batch(updates_by_db_id)

        # Vérifications
        assert success
        database_service.db_manager.update_multiple_cells_batch.assert_called_once_with(updates_by_db_id)
        database_service.cache_service.suspend_invalidation.assert_called_once()
        database_service.cache_service.resume_invalidation.assert_called_once_with(force_invalidate=True)
        assert len(database_service.modified_cells) == 0

    def test_save_cells_batch_in_progress(self, database_service):
        """Test sauvegarde batch déjà en cours"""
        database_service.save_in_progress = True

        success = database_service.save_cells_batch({123: {'marque': 'Test'}})

        assert not success
        database_service.db_manager.update_multiple_cells_batch.assert_not_called()

    def test_save_cells_batch_from_modified_cells(self, database_service):
        """Test sauvegarde depuis modified_cells"""
        # Préparer des cellules modifiées
        database_service.modified_cells.add((0, 1))
        database_service.modified_cells.add((0, 2))

        # Mock du tableau
        table = database_service.parent_window.table
        table.item.side_effect = lambda row, col: self._mock_table_item(row, col)
        table.horizontalHeaderItem.side_effect = lambda col: self._mock_header_item(col)

        database_service.db_manager.update_multiple_cells_batch.return_value = True

        success = database_service.save_cells_batch()

        assert success

    def _mock_table_item(self, row, col):
        """Helper pour mock des items de table"""
        item = Mock()
        if col == 0:  # Colonne ID
            item.text.return_value = "123"
        elif col == 1:
            item.text.return_value = "Samsung"
        elif col == 2:
            item.text.return_value = "WF80F5E3U4W"
        return item

    def _mock_header_item(self, col):
        """Helper pour mock des headers"""
        item = Mock()
        headers = ['id', 'manufacturer', 'type', 'reference']
        item.text.return_value = headers[col] if col < len(headers) else f'col_{col}'
        return item

    def test_save_drag_changes_success(self, database_service):
        """Test sauvegarde modifications drag & drop"""
        drag_handle = Mock()
        drag_handle.get_rows_to_save.return_value = [
            {'id': 123, 'marque': 'Samsung', 'prix': '399.99'},
            {'id': 124, 'stock': '10'}
        ]

        database_service.db_manager.update_multiple_cells_batch.return_value = True

        success = database_service.save_drag_changes(drag_handle)

        assert success
        database_service.user_interaction_service.add_to_history.assert_called_once()

    def test_save_drag_changes_invalid_handle(self, database_service):
        """Test sauvegarde drag & drop avec handle invalide"""
        success = database_service.save_drag_changes(None)
        assert not success

        invalid_handle = Mock()
        del invalid_handle.get_rows_to_save  # Supprimer la méthode
        success = database_service.save_drag_changes(invalid_handle)
        assert not success

    def test_manual_save_cellules_modifiees_passe_par_le_batch(self, database_service):
        """Sauvegarde manuelle avec des cellules modifiées : délègue à save_cells_batch"""
        database_service.parent_window.modified_cells = {(0, 1)}
        with patch.object(database_service, '_convert_modified_cells_to_updates',
                          return_value={42: {'type': 'X'}}), \
             patch.object(database_service, 'save_cells_batch', return_value=True) as batch:
            success = database_service.manual_save()

        assert success
        batch.assert_called_once_with({42: {'type': 'X'}})

    def test_manual_save_sans_modification(self, database_service):
        """Sauvegarde manuelle sans cellule modifiée : succès immédiat"""
        database_service.db_manager.update_multiple_cells_batch.return_value = True

        success = database_service.manual_save()

        assert success

    def test_delete_selected_devices_success(self, database_service):
        """Test suppression appareils sélectionnés - succès"""
        device_ids = [123, 124, 125]

        # Mock des infos d'appareils
        database_service.db_manager.get_device_info.side_effect = [
            {'manufacturer': 'Samsung', 'type': 'WF80F5E3U4W'},
            {'manufacturer': 'LG', 'type': 'F4WV710S2E'},
            {'manufacturer': 'Bosch', 'type': 'WAG24060FF'}
        ]

        database_service.db_manager.delete_appareil.return_value = True

        with patch.object(database_service, '_get_selected_device_ids', return_value=device_ids):
            with patch.object(database_service, '_confirm_deletion', return_value=True):
                deleted_count = database_service.delete_selected_devices()

        # Vérifications
        assert deleted_count == 3
        assert database_service.db_manager.delete_appareil.call_count == 3
        database_service.parent_window.table_controller.load_data.assert_called_once()
        database_service.cache_service.invalidate_all.assert_called_once()
        database_service.user_interaction_service.show_success.assert_called_once()

    def test_delete_selected_devices_cancelled(self, database_service):
        """Test suppression annulée par l'utilisateur"""
        device_ids = [123, 124]

        with patch.object(database_service, '_get_selected_device_ids', return_value=device_ids):
            with patch.object(database_service, '_confirm_deletion', return_value=False):
                deleted_count = database_service.delete_selected_devices()

        assert deleted_count == 0
        database_service.db_manager.delete_appareil.assert_not_called()

    def test_delete_selected_devices_no_selection(self, database_service):
        """Test suppression sans sélection"""
        with patch.object(database_service, '_get_selected_device_ids', return_value=[]):
            deleted_count = database_service.delete_selected_devices()

        assert deleted_count == 0

    def test_delete_selected_devices_partial_failure(self, database_service):
        """Test suppression avec échecs partiels"""
        device_ids = [123, 124, 125]

        database_service.db_manager.get_device_info.return_value = {'manufacturer': 'Test', 'type': 'Test'}
        # Mock: premier réussit, deuxième échoue, troisième réussit
        database_service.db_manager.delete_appareil.side_effect = [True, False, True]

        with patch.object(database_service, '_get_selected_device_ids', return_value=device_ids):
            with patch.object(database_service, '_confirm_deletion', return_value=True):
                deleted_count = database_service.delete_selected_devices()

        assert deleted_count == 2  # 2 succès sur 3

    def test_get_selected_device_ids(self, database_service):
        """Test récupération IDs appareils sélectionnés"""
        # Mock des items sélectionnés
        selected_items = []
        for row in [0, 2, 4]:  # Lignes 0, 2, 4 sélectionnées
            item = Mock()
            item.row.return_value = row
            selected_items.append(item)

        table = database_service.parent_window.table
        table.selectedItems.return_value = selected_items

        # Mock table_fill_service.get_db_id_from_row (utilisé par _safe_get_device_id_from_row)
        database_service.parent_window.table_fill_service.get_db_id_from_row.side_effect = \
            lambda t, row: 100 + row

        device_ids = database_service._get_selected_device_ids()

        assert sorted(device_ids) == [100, 102, 104]  # IDs correspondants

    def _mock_id_item(self, row):
        """Helper pour mock des items ID"""
        item = Mock()
        item.text.return_value = str(100 + row)  # ID = 100 + numéro de ligne
        return item

    def test_confirm_deletion_single(self, database_service):
        """Test confirmation suppression simple"""
        with patch('PyQt5.QtWidgets.QMessageBox.question', return_value=QMessageBox.Yes):
            result = database_service._confirm_deletion(1)
            assert result

        with patch('PyQt5.QtWidgets.QMessageBox.question', return_value=QMessageBox.No):
            result = database_service._confirm_deletion(1)
            assert not result

    def test_confirm_deletion_multiple(self, database_service):
        """Test confirmation suppression multiple"""
        with patch('PyQt5.QtWidgets.QMessageBox.question', return_value=QMessageBox.Yes):
            result = database_service._confirm_deletion(5)
            assert result

    def test_detect_data_inconsistencies(self, database_service):
        """Test détection d'incohérences"""
        # Mock des incohérences
        database_service.db_manager.find_duplicate_references.return_value = ['REF001', 'REF002']
        database_service.db_manager.find_invalid_prices.return_value = [123, 124]
        database_service.db_manager.find_negative_stocks.return_value = [125]

        inconsistencies = database_service.detect_data_inconsistencies()

        assert len(inconsistencies) == 3
        assert 'Références dupliquées' in inconsistencies[0]
        assert 'Prix invalides' in inconsistencies[1]
        assert 'Stocks négatifs' in inconsistencies[2]

    def test_detect_data_inconsistencies_none(self, database_service):
        """Test détection sans incohérences"""
        database_service.db_manager.find_duplicate_references.return_value = []
        database_service.db_manager.find_invalid_prices.return_value = []
        database_service.db_manager.find_negative_stocks.return_value = []

        inconsistencies = database_service.detect_data_inconsistencies()

        assert len(inconsistencies) == 0

    def test_update_save_indicators(self, database_service):
        """Test mise à jour indicateurs de sauvegarde"""
        # Test sauvegarde réussie
        database_service._update_save_indicators(True)

        database_service.parent_window.save_indicator.setStyleSheet.assert_called_with("color: green;")
        database_service.parent_window.save_indicator.setText.assert_called_with("Sauvegardé")
        database_service.parent_window.statusbar.showMessage.assert_called_with("Données sauvegardées", 2000)

        # Reset mocks
        database_service.parent_window.save_indicator.reset_mock()
        database_service.parent_window.statusbar.reset_mock()

        # Test non sauvegardé
        database_service._update_save_indicators(False)

        database_service.parent_window.save_indicator.setStyleSheet.assert_called_with("color: orange;")
        database_service.parent_window.save_indicator.setText.assert_called_with("● Non sauvegardé")

    def test_execute_with_transaction_success(self, database_service):
        """Test exécution avec transaction - succès"""
        operations = [Mock(return_value=True), Mock(return_value=True), Mock(return_value=True)]

        result = database_service.execute_with_transaction(operations)

        assert result
        for op in operations:
            op.assert_called_once()
        database_service.db_manager.begin_transaction.assert_called_once()
        database_service.db_manager.commit_transaction.assert_called_once()

    def test_execute_with_transaction_failure(self, database_service):
        """Test exécution avec transaction - échec"""
        operations = [Mock(return_value=True), Mock(return_value=False), Mock(return_value=True)]

        result = database_service.execute_with_transaction(operations)

        assert not result
        database_service.db_manager.rollback_transaction.assert_called_once()
        database_service.db_manager.commit_transaction.assert_not_called()

    def test_execute_with_transaction_no_support(self, database_service):
        """Test exécution sans support transactions"""
        # Supprimer le support des transactions
        del database_service.db_manager.begin_transaction

        operations = [Mock(return_value=True), Mock(return_value=True)]

        result = database_service.execute_with_transaction(operations)

        assert result
        for op in operations:
            op.assert_called_once()

    def test_signal_emission(self, database_service):
        """Test émission des signaux"""
        # Mock des signaux
        database_service.device_added = Mock()
        database_service.device_deleted = Mock()
        database_service.data_saved = Mock()
        database_service.validation_failed = Mock()

        # Test signal ajout
        database_service.db_manager.add_device.return_value = 123
        database_service.db_manager.get_device_by_reference.return_value = None
        device_id = database_service.add_new_device({'reference': 'TEST'})
        database_service.device_added.emit.assert_called_once_with(123)

        # Test signal validation échouée (marque non-vide + référence vide = validation déclenchée)
        invalid_data = {'reference': '', 'marque': 'X'}
        database_service.add_new_device(invalid_data)
        database_service.validation_failed.emit.assert_called_once()

        # Test signal sauvegarde
        database_service.db_manager.update_multiple_cells_batch.return_value = True
        database_service.save_cells_batch({123: {'marque': 'Test'}})
        database_service.data_saved.emit.assert_called_once_with(1)

        # Test signal suppression
        database_service.db_manager.delete_appareil.return_value = True
        database_service.db_manager.get_device_info.return_value = {'manufacturer': 'Test', 'type': 'Test'}
        with patch.object(database_service, '_get_selected_device_ids', return_value=[123]):
            with patch.object(database_service, '_confirm_deletion', return_value=True):
                database_service.delete_selected_devices()
                database_service.device_deleted.emit.assert_called_once_with([123])

    def test_error_handling(self, database_service):
        """Test gestion d'erreurs"""
        # Services manquants
        database_service.db_manager = None
        database_service.user_interaction_service = None

        # Ces opérations ne doivent pas planter
        result = database_service.add_new_device({'reference': 'TEST'})
        assert result is None

        result = database_service.save_cells_batch({123: {'marque': 'Test'}})
        assert not result

        result = database_service.delete_selected_devices([123])
        assert result == 0

        # Pas d'exception attendue