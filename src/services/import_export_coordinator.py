"""
Coordinateur d'import/export
Centralise toutes les opérations d'import et d'export pour éviter la duplication de code
"""

from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QWidget, QFileDialog

from ..core.logger import app_logger
from ..data.database_manager import DatabaseManager
from ..data.data_validator import DataValidator
from ..data.data_exporter import DataExporter, ExportError
from ..core.import_manager import ImportManager
from ..services.export_service import ExportFormat
from ..services.export_manager import ExportManagerService, ExportType
from .message_helper import show_success, show_error, ask_confirmation


class ImportWorker(QThread):
    """Worker thread pour les opérations d'import"""
    
    import_progress = pyqtSignal(int, str)  # pourcentage, message
    import_completed = pyqtSignal(dict)     # résultats
    import_error = pyqtSignal(str)          # message d'erreur
    
    def __init__(self, import_params: Dict[str, Any]):
        super().__init__()
        self.import_params = import_params
        self.should_stop = False
        
    def stop(self):
        """Arrêter l'import"""
        self.should_stop = True
        
    def run(self):
        """Exécuter l'import"""
        try:
            import_type = self.import_params.get('type', 'csv')
            file_paths = self.import_params.get('file_paths', [])
            options = self.import_params.get('options', {})
            
            self.import_progress.emit(10, f"Démarrage import {import_type.upper()}...")
            
            if import_type == 'csv':
                results = self._import_csv(file_paths[0], options)
            elif import_type == 'pdf':
                results = self._import_pdf(file_paths, options)
            else:
                raise ValueError(f"Type d'import non supporté: {import_type}")
                
            if not self.should_stop:
                self.import_completed.emit(results)
                
        except Exception as e:
            app_logger.error(f"Erreur import: {e}")
            self.import_error.emit(str(e))
            
    def _import_csv(self, file_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Importer un fichier CSV"""
        # TODO: Implémenter l'import CSV avec progression
        self.import_progress.emit(50, "Import CSV en cours...")
        # Simulation pour l'exemple
        import time
        time.sleep(1)
        self.import_progress.emit(100, "Import CSV terminé")
        
        return {
            'type': 'csv',
            'file_path': file_path,
            'imported_count': 0,
            'errors': []
        }
        
    def _import_pdf(self, file_paths: List[str], options: Dict[str, Any]) -> Dict[str, Any]:
        """Importer des fichiers PDF"""
        # TODO: Implémenter l'import PDF avec progression
        self.import_progress.emit(50, f"Import PDF en cours ({len(file_paths)} fichiers)...")
        # Simulation pour l'exemple
        import time
        time.sleep(1)
        self.import_progress.emit(100, "Import PDF terminé")
        
        return {
            'type': 'pdf',
            'file_paths': file_paths,
            'imported_count': 0,
            'errors': []
        }


class ExportWorker(QThread):
    """Worker thread pour les opérations d'export"""
    
    export_progress = pyqtSignal(int, str)  # pourcentage, message
    export_completed = pyqtSignal(dict)     # résultats
    export_error = pyqtSignal(str)          # message d'erreur
    
    def __init__(self, export_params: Dict[str, Any]):
        super().__init__()
        self.export_params = export_params
        self.should_stop = False
        
    def stop(self):
        """Arrêter l'export"""
        self.should_stop = True
        
    def run(self):
        """Exécuter l'export"""
        try:
            export_format = self.export_params.get('format')
            data = self.export_params.get('data', [])
            output_path = self.export_params.get('output_path')
            reference = self.export_params.get('reference', '')
            
            self.export_progress.emit(10, f"Démarrage export {export_format.name}...")
            
            if export_format == ExportFormat.CSV:
                results = self._export_csv(data, output_path, reference)
            elif export_format in [ExportFormat.HTML, ExportFormat.HTML_SIMPLE]:
                results = self._export_html(data, output_path, reference, export_format)
            else:
                raise ValueError(f"Format d'export non supporté: {export_format}")
                
            if not self.should_stop:
                self.export_completed.emit(results)
                
        except Exception as e:
            app_logger.error(f"Erreur export: {e}")
            self.export_error.emit(str(e))
            
    def _export_csv(self, data: List[Dict], output_path: str, reference: str) -> Dict[str, Any]:
        """Exporter en CSV"""
        self.export_progress.emit(50, "Export CSV en cours...")
        
        try:
            # TODO: Utiliser le DataExporter existant
            # Pour l'instant, simulation
            import time
            time.sleep(0.5)
            
            self.export_progress.emit(100, "Export CSV terminé")
            
            return {
                'format': 'CSV',
                'output_path': output_path,
                'records_count': len(data),
                'reference': reference,
                'success': True
            }
            
        except Exception as e:
            raise Exception(f"Erreur export CSV: {e}")
            
    def _export_html(self, data: List[Dict], output_path: str, reference: str, 
                    format_type: ExportFormat) -> Dict[str, Any]:
        """Exporter en HTML"""
        self.export_progress.emit(50, f"Export HTML ({format_type.name}) en cours...")
        
        try:
            # TODO: Utiliser le service d'export HTML existant
            # Pour l'instant, simulation
            import time
            time.sleep(0.5)
            
            self.export_progress.emit(100, "Export HTML terminé")
            
            return {
                'format': f'HTML ({format_type.name})',
                'output_path': output_path,
                'records_count': len(data),
                'reference': reference,
                'success': True
            }
            
        except Exception as e:
            raise Exception(f"Erreur export HTML: {e}")


class ImportExportCoordinator(QObject):
    """Coordinateur centralisé pour les opérations d'import et d'export"""
    
    # Signaux pour l'import
    import_started = pyqtSignal()
    import_progress = pyqtSignal(int, str)
    import_completed = pyqtSignal(dict)
    import_error = pyqtSignal(str)
    
    # Signaux pour l'export
    export_started = pyqtSignal()
    export_progress = pyqtSignal(int, str)
    export_completed = pyqtSignal(dict)
    export_error = pyqtSignal(str)
    
    def __init__(self, db_manager: DatabaseManager, parent: QWidget = None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent_widget = parent
        
        # Managers et services
        self.import_manager = ImportManager()
        self.data_exporter = DataExporter()
        self.export_manager_service = ExportManagerService()
        
        # Workers
        self.import_worker = None
        self.export_worker = None
        
        # État
        self.current_import_results = None
        self.current_export_results = None
        
    def start_import_dialog(self) -> Optional[Dict[str, Any]]:
        """Ouvrir une boîte de dialogue pour sélectionner les fichiers à importer"""
        try:
            file_dialog = QFileDialog(self.parent_widget)
            file_dialog.setWindowTitle("Sélectionner les fichiers à importer")
            file_dialog.setFileMode(QFileDialog.ExistingFiles)
            file_dialog.setNameFilter("Fichiers supportés (*.csv *.pdf);;Fichiers CSV (*.csv);;Fichiers PDF (*.pdf)")
            
            if file_dialog.exec_():
                file_paths = file_dialog.selectedFiles()
                if file_paths:
                    return self._prepare_import(file_paths)
                    
            return None
            
        except Exception as e:
            app_logger.error(f"Erreur dialog import: {e}")
            show_error(self.parent_widget, "Erreur", f"Erreur lors de l'ouverture de la boîte de dialogue: {str(e)}")
            return None
            
    def _prepare_import(self, file_paths: List[str]) -> Dict[str, Any]:
        """Préparer les paramètres d'import"""
        try:
            # Détecter le type de fichier
            first_file = Path(file_paths[0])
            file_extension = first_file.suffix.lower()
            
            if file_extension == '.csv':
                import_type = 'csv'
                # TODO: Détecter les colonnes et options par défaut
                options = self._get_default_csv_options()
            elif file_extension == '.pdf':
                import_type = 'pdf'
                # TODO: Détecter la référence pièce suggérée
                options = self._get_default_pdf_options()
            else:
                raise ValueError(f"Type de fichier non supporté: {file_extension}")
                
            return {
                'type': import_type,
                'file_paths': file_paths,
                'options': options
            }
            
        except Exception as e:
            app_logger.error(f"Erreur préparation import: {e}")
            raise
            
    def _get_default_csv_options(self) -> Dict[str, Any]:
        """Obtenir les options par défaut pour l'import CSV"""
        return {
            'delimiter': ',',
            'encoding': 'utf-8',
            'has_header': True,
            'ref_piece_column': None,  # À détecter
            'skip_duplicates': True
        }
        
    def _get_default_pdf_options(self) -> Dict[str, Any]:
        """Obtenir les options par défaut pour l'import PDF"""
        return {
            'suggested_ref_piece': None,  # À détecter depuis le nom du fichier
            'extract_method': 'auto',
            'skip_duplicates': True
        }
        
    def start_import(self, import_params: Dict[str, Any]):
        """Démarrer une opération d'import"""
        if self.import_worker and self.import_worker.isRunning():
            app_logger.warning("Import déjà en cours")
            return
            
        self.import_worker = ImportWorker(import_params)
        
        # Connecter les signaux
        self.import_worker.import_progress.connect(self.import_progress.emit)
        self.import_worker.import_completed.connect(self._on_import_completed)
        self.import_worker.import_error.connect(self.import_error.emit)
        
        self.import_started.emit()
        self.import_worker.start()
        
    def _on_import_completed(self, results: Dict[str, Any]):
        """Gérer la fin d'import"""
        self.current_import_results = results
        self.import_completed.emit(results)
        app_logger.info(f"Import terminé: {results.get('imported_count', 0)} éléments importés")
        
    def start_export_dialog(self, data: List[Dict], suggested_filename: str = "") -> Optional[Dict[str, Any]]:
        """Ouvrir une boîte de dialogue pour configurer l'export"""
        try:
            file_dialog = QFileDialog(self.parent_widget)
            file_dialog.setWindowTitle("Exporter les données")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setNameFilter("CSV (*.csv);;HTML Simple (*.html);;HTML Complet (*.html)")
            
            if suggested_filename:
                file_dialog.selectFile(suggested_filename)
                
            if file_dialog.exec_():
                file_path = file_dialog.selectedFiles()[0]
                selected_filter = file_dialog.selectedNameFilter()
                
                # Détecter le format d'export
                if "CSV" in selected_filter:
                    export_format = ExportFormat.CSV
                elif "HTML Simple" in selected_filter:
                    export_format = ExportFormat.HTML_SIMPLE
                elif "HTML Complet" in selected_filter:
                    export_format = ExportFormat.HTML
                else:
                    export_format = ExportFormat.CSV  # Par défaut
                    
                return {
                    'format': export_format,
                    'output_path': file_path,
                    'data': data,
                    'reference': self._extract_reference_from_filename(file_path)
                }
                
            return None
            
        except Exception as e:
            app_logger.error(f"Erreur dialog export: {e}")
            show_error(self.parent_widget, "Erreur", f"Erreur lors de l'ouverture de la boîte de dialogue: {str(e)}")
            return None
            
    def _extract_reference_from_filename(self, file_path: str) -> str:
        """Extraire une référence depuis le nom du fichier"""
        try:
            filename = Path(file_path).stem
            # Logique d'extraction de référence (peut être améliorée)
            # Par exemple, si le nom contient "ref_", extraire ce qui suit
            if "ref_" in filename:
                return filename.split("ref_")[1].split("_")[0]
            return filename
        except:
            return ""
            
    def start_export(self, export_params: Dict[str, Any]):
        """Démarrer une opération d'export"""
        if self.export_worker and self.export_worker.isRunning():
            app_logger.warning("Export déjà en cours")
            return
            
        self.export_worker = ExportWorker(export_params)
        
        # Connecter les signaux
        self.export_worker.export_progress.connect(self.export_progress.emit)
        self.export_worker.export_completed.connect(self._on_export_completed)
        self.export_worker.export_error.connect(self.export_error.emit)
        
        self.export_started.emit()
        self.export_worker.start()
        
    def _on_export_completed(self, results: Dict[str, Any]):
        """Gérer la fin d'export"""
        self.current_export_results = results
        self.export_completed.emit(results)
        app_logger.info(f"Export terminé: {results.get('records_count', 0)} enregistrements exportés vers {results.get('output_path', 'fichier')}")
        
    def stop_operations(self):
        """Arrêter toutes les opérations en cours"""
        if self.import_worker and self.import_worker.isRunning():
            self.import_worker.stop()
            self.import_worker.wait(3000)
            
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.stop()
            self.export_worker.wait(3000)
            
    def export_current_search_results(self, search_data: List[Dict], search_term: str = "", 
                                    export_format: ExportFormat = ExportFormat.CSV) -> bool:
        """Exporter les résultats de recherche actuels"""
        try:
            if not search_data:
                show_error(self.parent_widget, "Aucune donnée", "Aucune donnée à exporter.")
                return False
                
            # Générer un nom de fichier suggéré
            timestamp = app_logger.get_timestamp().replace(":", "-").replace(" ", "_")
            if search_term:
                suggested_name = f"export_{search_term}_{timestamp}"
            else:
                suggested_name = f"export_data_{timestamp}"
                
            # Ouvrir le dialog d'export
            export_params = self.start_export_dialog(search_data, suggested_name)
            if export_params:
                self.start_export(export_params)
                return True
                
            return False
            
        except Exception as e:
            app_logger.error(f"Erreur export résultats recherche: {e}")
            show_error(self.parent_widget, "Erreur d'export", f"Erreur lors de l'export: {str(e)}")
            return False
            
    def get_import_statistics(self) -> Dict[str, Any]:
        """Obtenir les statistiques du dernier import"""
        if self.current_import_results:
            return {
                'type': self.current_import_results.get('type', 'Unknown'),
                'imported_count': self.current_import_results.get('imported_count', 0),
                'error_count': len(self.current_import_results.get('errors', [])),
                'success_rate': self._calculate_success_rate(self.current_import_results)
            }
        return {'imported_count': 0, 'error_count': 0, 'success_rate': 0.0}
        
    def get_export_statistics(self) -> Dict[str, Any]:
        """Obtenir les statistiques du dernier export"""
        if self.current_export_results:
            return {
                'format': self.current_export_results.get('format', 'Unknown'),
                'records_count': self.current_export_results.get('records_count', 0),
                'output_path': self.current_export_results.get('output_path', ''),
                'success': self.current_export_results.get('success', False)
            }
        return {'records_count': 0, 'success': False}
        
    def _calculate_success_rate(self, results: Dict[str, Any]) -> float:
        """Calculer le taux de succès d'une opération"""
        try:
            imported = results.get('imported_count', 0)
            errors = len(results.get('errors', []))
            total = imported + errors
            
            if total == 0:
                return 0.0
                
            return (imported / total) * 100.0
            
        except:
            return 0.0
            
    def cleanup(self):
        """Nettoyer les ressources"""
        self.stop_operations()
        app_logger.debug("ImportExportCoordinator nettoyé")