"""
Tests unitaires pour ImportExportService
Validation des opérations d'import/export sans régression
"""

import pytest
from unittest.mock import Mock, patch

from src.services.import_export_service import ImportExportService


@pytest.mark.unit
@pytest.mark.critical
class TestImportExportService:
    """Tests critiques pour ImportExportService"""

    @pytest.fixture
    def mock_parent_window(self):
        """Fixture fenêtre parent mockée"""
        parent = Mock()

        # Mock tous les services requis
        parent.export_manager = Mock()
        parent.import_manager = Mock()
        parent.db_manager = Mock()
        parent.user_interaction_service = Mock()
        parent.dialog_service = Mock()
        parent.file_processing_service = Mock()
        parent.table_controller = Mock()
        parent.undo_manager = Mock()

        return parent

    @pytest.fixture
    def import_export_service(self, mock_parent_window, qapp):
        """Fixture service d'import/export"""
        service = ImportExportService(
            parent_window=mock_parent_window,
            parent=None
        )

        # Initialiser les services
        service.initialize_services()

        return service

    def test_service_initialization(self, import_export_service, mock_parent_window):
        """Test initialisation du service"""
        assert import_export_service.parent_window == mock_parent_window
        assert import_export_service.export_manager == mock_parent_window.export_manager
        assert import_export_service.import_manager == mock_parent_window.import_manager
        assert import_export_service.db_manager == mock_parent_window.db_manager

    def test_initialize_services(self, mock_parent_window):
        """Test initialisation des références de services"""
        service = ImportExportService(mock_parent_window)

        # Après initialisation, les services sont injectés depuis parent_window
        service.initialize_services()
        assert service.export_manager == mock_parent_window.export_manager
        assert service.import_manager == mock_parent_window.import_manager

    def test_export_data(self, import_export_service):
        """Test export de données principal"""
        # Test avec export_manager disponible
        import_export_service.export_data()
        import_export_service.export_manager.export_data.assert_called_once()

    def test_export_data_no_manager(self, mock_parent_window):
        """Test export sans export_manager disponible"""
        mock_parent_window.export_manager = None
        service = ImportExportService(mock_parent_window)
        service.initialize_services()

        # Ne doit pas lever d'exception
        service.export_data()

    def test_import_file_csv(self, import_export_service):
        """Test import fichier CSV"""
        test_file = "/tmp/test.csv"

        with patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName', return_value=(test_file, "")):
            with patch.object(import_export_service, '_process_import_file') as mock_process:
                import_export_service.import_file()

                mock_process.assert_called_once_with(test_file)

    def test_import_file_pdf(self, import_export_service):
        """Test import fichier PDF"""
        test_file = "/tmp/test.pdf"

        with patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName', return_value=(test_file, "")):
            with patch.object(import_export_service, 'import_pdf_from_path') as mock_import:
                import_export_service.import_file()

                mock_import.assert_called_once_with(test_file)

    def test_import_file_cancelled(self, import_export_service):
        """Test import fichier annulé"""
        with patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName', return_value=("", "")):
            with patch.object(import_export_service, '_process_import_file') as mock_process:
                import_export_service.import_file()

                # Aucun traitement ne doit être lancé
                mock_process.assert_not_called()

    def test_import_csv_from_path_with_import_manager(self, import_export_service):
        """Import CSV (glisser/déposer) : délègue à ImportManager.import_files
        avec ouverture du dialogue et callback de fin d'import."""
        test_file = "/tmp/test.csv"

        with patch('os.path.exists', return_value=True):
            import_export_service.import_csv_from_path(test_file)

        # ImportManager.import_files appelé avec le fichier, le dialogue et le callback
        import_export_service.import_manager.import_files.assert_called_once()
        args, kwargs = import_export_service.import_manager.import_files.call_args
        assert args[0] == [test_file]
        assert kwargs.get('show_dialog') is True
        assert kwargs.get('callback') == import_export_service.parent_window._on_import_complete

    def test_import_csv_from_path_no_file(self, import_export_service):
        """Test import CSV avec fichier inexistant"""
        test_file = "/tmp/nonexistent.csv"

        with patch('os.path.exists', return_value=False):
            import_export_service.import_csv_from_path(test_file)

            # ImportManager ne doit pas être appelé
            import_export_service.import_manager.import_file.assert_not_called()

    def test_import_csv_from_path_options_cancelled(self, import_export_service):
        """Test import CSV avec options annulées"""
        test_file = "/tmp/test.csv"

        with patch('os.path.exists', return_value=True):
            with patch.object(import_export_service, '_get_import_options_unified', return_value=None):
                import_export_service.import_csv_from_path(test_file)

                # ImportManager ne doit pas être appelé
                import_export_service.import_manager.import_file.assert_not_called()

    def test_import_pdf_from_path(self, import_export_service):
        """Import PDF : délègue à FileProcessingService.import_pdf_files"""
        test_file = "/tmp/test.pdf"

        import_export_service.import_pdf_from_path(test_file)

        # Vérifier que FileProcessingService a été appelé
        import_export_service.file_processing_service.import_pdf_files.assert_called_once_with(test_file)

    def test_import_pdf_from_path_no_service(self, import_export_service):
        """Test import PDF sans FileProcessingService"""
        import_export_service.file_processing_service = None
        test_file = "/tmp/test.pdf"

        # Ne doit pas lever d'exception
        import_export_service.import_pdf_from_path(test_file)

    def test_process_import_file_csv(self, import_export_service):
        """Test traitement fichier CSV"""
        test_file = "/tmp/test.csv"

        with patch.object(import_export_service, 'import_csv_from_path') as mock_import:
            import_export_service._process_import_file(test_file)

            mock_import.assert_called_once_with(test_file)

    def test_process_import_file_pdf(self, import_export_service):
        """Test traitement fichier PDF"""
        test_file = "/tmp/test.pdf"

        with patch.object(import_export_service, 'import_pdf_from_path') as mock_import:
            import_export_service._process_import_file(test_file)

            mock_import.assert_called_once_with(test_file)

    def test_process_import_file_unsupported(self, import_export_service):
        """Test traitement fichier non supporté"""
        test_file = "/tmp/test.txt"

        # Ne doit pas lever d'exception
        import_export_service._process_import_file(test_file)

    def test_show_import_results_success(self, import_export_service):
        """Test affichage résultats import - succès"""
        mock_result = {
            'success': True,
            'stats': {'added': 5, 'updated': 2, 'total_processed': 7}
        }

        with patch.object(import_export_service, '_show_import_summary') as mock_summary:
            with patch.object(import_export_service, '_log_import_to_history') as mock_log:
                import_export_service._show_import_results_new(mock_result)

                # Vérifier les appels
                mock_summary.assert_called_once_with(mock_result)
                mock_log.assert_called_once_with(mock_result)

                # Vérifier rechargement table
                import_export_service.table_controller.load_data.assert_called_once()

    def test_show_import_results_error(self, import_export_service):
        """Test affichage résultats import - erreur"""
        mock_result = {
            'success': False,
            'error': 'Erreur de test'
        }

        import_export_service._show_import_results_new(mock_result)

        # Vérifier que l'erreur est affichée
        import_export_service.dialog_service.show_error.assert_called_once()

        # La table ne doit pas être rechargée
        import_export_service.table_controller.load_data.assert_not_called()

    def test_generate_console_summary(self, import_export_service):
        """Test génération résumé console"""
        mock_result = {
            'stats': {
                'total_processed': 10,
                'added': 5,
                'updated': 3,
                'skipped': 1,
                'errors': 1
            },
            'duration': '2.5s',
            'file_path': '/tmp/test.csv',
            'warnings': ['Warning 1', 'Warning 2']
        }

        summary = import_export_service._generate_console_summary(mock_result)

        # Vérifier le contenu
        assert "Import terminé avec succès" in summary
        assert "Total traité: 10" in summary
        assert "Ajoutés: 5" in summary
        assert "Mis à jour: 3" in summary
        assert "Durée: 2.5s" in summary
        assert "test.csv" in summary
        assert "Avertissements: 2" in summary

    def test_get_import_options_unified(self, import_export_service):
        """Test obtention options import unifiées"""
        options = import_export_service._get_import_options_unified()

        # Vérifier les options par défaut
        assert options is not None
        assert options['has_headers'] is True
        assert options['separator'] == ';'
        assert options['encoding'] == 'utf-8'
        assert options['skip_duplicates'] is True
        assert options['create_backup'] is True

    def test_log_import_to_history(self, import_export_service):
        """Test enregistrement import dans historique"""
        mock_result = {
            'stats': {'added': 5, 'updated': 2},
            'file_path': '/tmp/test_import.csv'
        }

        import_export_service._log_import_to_history(mock_result)

        # Vérifier ajout à l'historique
        import_export_service.user_interaction_service.add_to_history.assert_called_once()

        # Vérifier que l'entrée contient les bonnes informations
        call_args = import_export_service.user_interaction_service.add_to_history.call_args[0][0]
        assert "test_import.csv" in call_args
        assert "5 ajoutés" in call_args
        assert "2 mis à jour" in call_args

        # Pas d'exception attendue