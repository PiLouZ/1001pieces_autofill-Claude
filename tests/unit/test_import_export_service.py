"""
Tests unitaires pour ImportExportService
Validation des opérations d'import/export sans régression
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, MagicMock, patch, mock_open
from PyQt5.QtWidgets import QApplication

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

    def test_export_with_custom_reference_no_input(self, import_export_service):
        """Test export avec référence personnalisée - pas d'entrée"""
        with patch.object(import_export_service, '_get_custom_reference_dialog', return_value=("", False)):
            import_export_service.export_with_custom_reference()

            # Aucune requête ne doit être exécutée
            import_export_service.db_manager.execute_query.assert_not_called()

    def test_export_with_custom_reference_with_data(self, import_export_service):
        """Test export avec référence personnalisée - avec données"""
        # Mock des données de retour
        mock_results = [
            ("Type1", "Marque1", "Modele1", "REF001", "Designation1", 10.50, 5, "Notes1"),
            ("Type2", "Marque2", "Modele2", "REF002", "Designation2", 20.75, 3, "Notes2")
        ]

        import_export_service.db_manager.execute_query.return_value = mock_results

        with patch.object(import_export_service, '_get_custom_reference_dialog', return_value=("TEST_REF", True)):
            with patch.object(import_export_service, '_export_custom_results') as mock_export:
                import_export_service.export_with_custom_reference()

                # Vérifier que la requête a été exécutée
                import_export_service.db_manager.execute_query.assert_called_once()

                # Vérifier que l'export a été appelé avec les bonnes données
                mock_export.assert_called_once_with(mock_results, "TEST_REF")

    def test_export_with_custom_reference_no_results(self, import_export_service):
        """Test export avec référence personnalisée - aucun résultat"""
        import_export_service.db_manager.execute_query.return_value = []

        with patch.object(import_export_service, '_get_custom_reference_dialog', return_value=("UNKNOWN_REF", True)):
            import_export_service.export_with_custom_reference()

            # Dialog d'info doit être affiché
            import_export_service.dialog_service.show_info.assert_called_once()

    def test_export_csv_with_reference(self, import_export_service):
        """Test export CSV avec référence"""
        test_data = [
            ("Type1", "Marque1", "Modele1", "REF001", "Designation1", 10.50, 5, "Notes1"),
            ("Type2", "Marque2", "Modele2", "REF002", "Designation2", 20.75, 3, "Notes2")
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            with patch('PyQt5.QtWidgets.QFileDialog.getSaveFileName', return_value=(tmp_path, "")):
                import_export_service.export_csv_with_reference(test_data, "TEST_REF")

                # Vérifier que le fichier a été créé
                assert os.path.exists(tmp_path)

                # Vérifier le contenu
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    assert "Type;Marque;Modèle" in content  # Headers
                    assert "REF001" in content  # Données
                    assert "REF002" in content

                # Vérifier les signaux
                import_export_service.dialog_service.show_success.assert_called_once()

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_export_csv_cancelled(self, import_export_service):
        """Test export CSV annulé par l'utilisateur"""
        test_data = [("Type1", "Marque1", "Modele1", "REF001", "Designation1", 10.50, 5, "Notes1")]

        with patch('PyQt5.QtWidgets.QFileDialog.getSaveFileName', return_value=("", "")):
            import_export_service.export_csv_with_reference(test_data, "TEST_REF")

            # Aucun dialogue de succès ne doit être affiché
            import_export_service.dialog_service.show_success.assert_not_called()

    def test_export_html_with_reference(self, import_export_service, qapp):
        """Test export HTML avec référence"""
        test_data = [
            ("Type1", "Marque1", "Modele1", "REF001", "Designation1", 10.50, 5, "Notes1")
        ]

        with patch.object(import_export_service, '_generate_html_table', return_value="<table>test</table>") as mock_html:
            import_export_service.export_html_with_reference(test_data, "TEST_REF")

            # Vérifier que le HTML a été généré
            mock_html.assert_called_once_with(test_data, "TEST_REF")

            # Vérifier le dialogue de succès
            import_export_service.dialog_service.show_success.assert_called_once()

    def test_generate_html_table(self, import_export_service):
        """Test génération de table HTML"""
        test_data = [
            ("Type1", "Marque1", "Modele1", "REF001", "Designation1", 10.50, 5, "Notes1"),
            ("Type2", "Marque2", "Modele2", "REF002", "Designation2", None, 0, None)  # Test valeurs nulles
        ]

        html = import_export_service._generate_html_table(test_data, "TEST_REF")

        # Vérifier la structure HTML
        assert "<table" in html
        assert "<caption>" in html
        assert "TEST_REF" in html
        assert "2 résultats" in html
        assert "<th" in html
        assert "REF001" in html
        assert "REF002" in html
        assert "</table>" in html

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
        """Test import CSV avec ImportManager disponible"""
        test_file = "/tmp/test.csv"
        mock_result = {'success': True, 'stats': {'added': 5, 'updated': 2}}

        import_export_service.import_manager.import_file.return_value = mock_result

        with patch('os.path.exists', return_value=True):
            with patch.object(import_export_service, '_get_import_options_unified', return_value={'has_headers': True}):
                with patch.object(import_export_service, '_show_import_results_new') as mock_show:
                    import_export_service.import_csv_from_path(test_file)

                    # Vérifier que ImportManager a été appelé
                    import_export_service.import_manager.import_file.assert_called_once()

                    # Vérifier que les résultats ont été affichés
                    mock_show.assert_called_once_with(mock_result)

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
        """Test import PDF via FileProcessingService"""
        test_file = "/tmp/test.pdf"

        import_export_service.import_pdf_from_path(test_file)

        # Vérifier que FileProcessingService a été appelé
        import_export_service.file_processing_service.process_pdf_file.assert_called_once_with(test_file)

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

    def test_detect_separator(self, import_export_service):
        """Test détection séparateur CSV"""
        # Test avec point-virgule
        with patch('builtins.open', mock_open(read_data="col1;col2;col3\nval1;val2;val3")):
            separator = import_export_service._detect_separator("/tmp/test.csv")
            assert separator == ';'

        # Test avec virgule
        with patch('builtins.open', mock_open(read_data="col1,col2,col3\nval1,val2,val3")):
            separator = import_export_service._detect_separator("/tmp/test.csv")
            assert separator == ','

        # Test avec tabulation
        with patch('builtins.open', mock_open(read_data="col1\tcol2\tcol3\nval1\tval2\tval3")):
            separator = import_export_service._detect_separator("/tmp/test.csv")
            assert separator == '\t'

    def test_detect_file_encoding_with_chardet(self, import_export_service):
        """Test détection encodage avec chardet"""
        with patch('chardet.detect', return_value={'encoding': 'utf-8', 'confidence': 0.9}):
            with patch('builtins.open', mock_open()):
                encoding = import_export_service._detect_file_encoding("/tmp/test.csv")
                assert encoding == 'utf-8'

    def test_detect_file_encoding_without_chardet(self, import_export_service):
        """Test détection encodage sans chardet"""
        with patch('chardet.detect', side_effect=ImportError()):
            encoding = import_export_service._detect_file_encoding("/tmp/test.csv")
            assert encoding == 'utf-8'  # Fallback

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

    def test_signal_emission(self, import_export_service):
        """Test émission des signaux"""
        # Mock des signaux
        import_export_service.import_completed = Mock()
        import_export_service.export_completed = Mock()

        # Test signal import
        mock_result = {'success': True, 'stats': {'added': 5}}
        import_export_service._show_import_results_new(mock_result)
        import_export_service.import_completed.emit.assert_called_once_with(mock_result)

        # Test signal export
        test_data = [("Type1", "Marque1", "Modele1", "REF001", "Designation1", 10.50, 5, "Notes1")]
        with patch.object(import_export_service, '_generate_html_table', return_value="<table>test</table>"):
            import_export_service.export_html_with_reference(test_data, "TEST_REF")
            import_export_service.export_completed.emit.assert_called_once_with("clipboard")

    def test_error_handling(self, import_export_service):
        """Test gestion d'erreurs"""
        # Services manquants
        import_export_service.dialog_service = None
        import_export_service.db_manager = None

        # Ces opérations ne doivent pas planter
        import_export_service.export_data()
        import_export_service.export_with_custom_reference("TEST")
        import_export_service._show_import_summary({})
        import_export_service._log_import_to_history({})

        # Pas d'exception attendue