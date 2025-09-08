"""
ImportExportManager - Refactorisation Phase 3
Extraction de la logique d'import/export de MainWindow

RESPONSABILITÉS :
- Gestion centralisée des imports (CSV, PDF, Paste)
- Gestion des exports avec services unifiés
- Historique des imports et traçabilité
- Validation et options d'import
- Résumés et rapports d'import/export

OBJECTIF : Réduire MainWindow en extrayant ~25 méthodes liées aux imports/exports
"""

from typing import Optional, Dict, Any, List, Tuple, Union
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QProgressDialog
from PyQt5.QtCore import QObject, pyqtSignal

from ..core.logger import app_logger
from ..core.config import Config
from ..services.unified_export_service import UnifiedExportService, MainExportService, ExportFormat
from ..services.unified_dialog_service import UnifiedDialogService


class ImportExportManager(QObject):
    """
    Gestionnaire centralisé pour toutes les opérations d'import et export
    
    Extrait les responsabilités d'import/export de MainWindow :
    - Imports de fichiers (CSV, PDF) et données collées
    - Exports avec sélection de référence
    - Validation et options d'import
    - Historique et traçabilité
    - Intégration avec les services unifiés
    """
    
    # Signaux pour communication avec MainWindow
    import_started = pyqtSignal(str, dict)  # type_import, options
    import_completed = pyqtSignal(dict)  # résultats d'import
    import_error = pyqtSignal(str, str)  # type_import, erreur
    export_started = pyqtSignal(str, dict)  # format_export, options
    export_completed = pyqtSignal(dict)  # résultats d'export
    export_error = pyqtSignal(str, str)  # format_export, erreur
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # Références vers les services nécessaires
        self.db_manager = None
        self.import_manager = None  # ImportManager du core
        self.export_service = None  # UnifiedExportService
        self.main_export_service = None  # MainExportService avec UI
        self.dialog_service = None  # UnifiedDialogService
        self.validator = None  # DataValidator
        
        # Historique des imports
        self.import_history = []
        
        self._is_initialized = False
    
    def initialize(self, db_manager, import_manager, export_service, 
                  main_export_service, dialog_service, validator):
        """
        Initialiser le gestionnaire avec les services nécessaires
        
        Args:
            db_manager: Gestionnaire de base de données
            import_manager: Gestionnaire d'import du core
            export_service: Service d'export unifié (sans UI)
            main_export_service: Service d'export avec UI
            dialog_service: Service de dialogues unifié
            validator: Validateur de données
        """
        self.db_manager = db_manager
        self.import_manager = import_manager
        self.export_service = export_service
        self.main_export_service = main_export_service
        self.dialog_service = dialog_service
        self.validator = validator
        
        self._is_initialized = True
        app_logger.info("ImportExportManager initialisé avec succès")
    
    def import_file(self):
        """
        Importer un fichier avec dialogue de sélection
        
        Méthode extraite de MainWindow._import_file()
        """
        try:
            if not self._is_initialized:
                app_logger.error("ImportExportManager non initialisé")
                return
            
            # Dialogue de sélection de fichier
            file_path, _ = QFileDialog.getOpenFileName(
                self.main_window,
                "Sélectionner un fichier à importer",
                "",
                "Fichiers CSV (*.csv);;Fichiers PDF (*.pdf);;Tous les fichiers (*)"
            )
            
            if not file_path:
                app_logger.debug("Import annulé par l'utilisateur")
                return
            
            # Déterminer le type de fichier et traiter
            if file_path.lower().endswith('.csv'):
                self._import_csv_from_path(file_path)
            elif file_path.lower().endswith('.pdf'):
                self._import_pdf_from_path([file_path])
            else:
                QMessageBox.warning(
                    self.main_window,
                    "Format non supporté",
                    "Le format de fichier sélectionné n'est pas supporté.\n"
                    "Formats supportés : CSV, PDF"
                )
            
        except Exception as e:
            app_logger.error(f"Erreur import fichier: {e}")
            QMessageBox.critical(
                self.main_window,
                "Erreur d'import",
                f"Une erreur est survenue lors de l'import : {e}"
            )
    
    def _import_csv_from_path(self, file_path: str):
        """
        Importer un fichier CSV depuis un chemin
        
        Méthode extraite de MainWindow._import_csv_from_path()
        
        Args:
            file_path: Chemin du fichier CSV à importer
        """
        try:
            app_logger.info(f"Début import CSV: {file_path}")
            self.import_started.emit("CSV", {"file_path": file_path})
            
            # Utiliser l'ImportManager pour traiter le fichier
            if not self.import_manager:
                raise Exception("ImportManager non disponible")
            
            # Lire et analyser le fichier CSV pour détecter les colonnes
            import csv
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Détecter le délimiteur
                sample = csvfile.read(1024)
                csvfile.seek(0)
                
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter
                
                # Lire l'en-tête et quelques lignes d'échantillon
                reader = csv.reader(csvfile, delimiter=delimiter)
                headers = next(reader, [])
                sample_rows = [next(reader, []) for _ in range(min(5, len(list(reader))))]
                csvfile.seek(0)
                # Relire pour le nombre total de lignes
                total_rows = sum(1 for _ in reader) - 1  # -1 pour l'en-tête
            
            detected_columns = len(headers)
            
            # Suggérer une référence basée sur le nom de fichier
            import os
            filename_base = os.path.splitext(os.path.basename(file_path))[0]
            suggested_ref = filename_base.replace('_', ' ').replace('-', ' ').title()
            
            # Obtenir les options d'import via dialogue unifié
            import_options = self._get_import_options_unified(
                detected_columns=detected_columns,
                default_ref_piece=suggested_ref,
                import_method="CSV",
                sample_data=[headers] + sample_rows
            )
            
            if not import_options:
                app_logger.debug("Options d'import annulées par l'utilisateur")
                return
            
            # Procéder à l'import avec les options sélectionnées
            results = self.import_manager.import_csv_file(
                file_path,
                default_reference=import_options.get('default_reference', ''),
                import_mode=import_options.get('import_mode', 0),
                auto_complete=import_options.get('auto_complete', True),
                validate_data=import_options.get('validate_data', True),
                clean_duplicates=import_options.get('clean_duplicates', False)
            )
            
            # Traiter les résultats
            if results and results.get('success', False):
                self._show_import_summary(results, import_options.get('default_reference', ''), "CSV")
                self._log_import_to_history(results, import_options.get('default_reference', ''), f"CSV: {file_path}")
                self.import_completed.emit(results)
                
                app_logger.info(f"Import CSV réussi: {results.get('imported_count', 0)} éléments")
            else:
                error_msg = results.get('error', 'Erreur inconnue') if results else 'Aucun résultat'
                self.import_error.emit("CSV", error_msg)
                
                QMessageBox.critical(
                    self.main_window,
                    "Erreur d'import CSV",
                    f"L'import CSV a échoué : {error_msg}"
                )
            
        except Exception as e:
            app_logger.error(f"Erreur import CSV: {e}")
            self.import_error.emit("CSV", str(e))
            QMessageBox.critical(
                self.main_window,
                "Erreur d'import CSV",
                f"Une erreur est survenue : {e}"
            )
    
    def _import_pdf_from_path(self, file_paths: List[str]):
        """
        Importer des fichiers PDF depuis des chemins
        
        Méthode extraite de MainWindow._import_pdf_from_path()
        
        Args:
            file_paths: Liste des chemins de fichiers PDF à importer
        """
        try:
            app_logger.info(f"Début import PDF: {len(file_paths)} fichiers")
            self.import_started.emit("PDF", {"file_paths": file_paths})
            
            # Suggérer une référence basée sur les noms de fichiers
            if len(file_paths) == 1:
                import os
                filename_base = os.path.splitext(os.path.basename(file_paths[0]))[0]
                suggested_ref = filename_base.replace('_', ' ').replace('-', ' ').title()
            else:
                suggested_ref = f"Import PDF ({len(file_paths)} fichiers)"
            
            # Obtenir les options d'import pour PDF
            import_options = self._get_import_options_pdf(suggested_ref)
            
            if not import_options:
                app_logger.debug("Options d'import PDF annulées par l'utilisateur")
                return
            
            # Afficher une barre de progression pour les imports multiples
            progress = None
            if len(file_paths) > 1:
                progress = QProgressDialog(
                    "Import des fichiers PDF...",
                    "Annuler",
                    0, len(file_paths),
                    self.main_window
                )
                progress.setWindowTitle("Import PDF")
                progress.setModal(True)
                progress.show()
            
            # Traiter chaque fichier PDF
            all_results = []
            for i, pdf_path in enumerate(file_paths):
                if progress and progress.wasCanceled():
                    app_logger.info("Import PDF annulé par l'utilisateur")
                    break
                
                if progress:
                    progress.setValue(i)
                    progress.setLabelText(f"Traitement: {os.path.basename(pdf_path)}")
                
                # Utiliser l'ImportManager pour traiter le PDF
                pdf_results = self.import_manager.import_pdf_file(
                    pdf_path,
                    default_reference=import_options.get('default_reference', ''),
                    import_mode=import_options.get('import_mode', 0),
                    auto_complete=import_options.get('auto_complete', True),
                    validate_data=import_options.get('validate_data', True)
                )
                
                if pdf_results:
                    all_results.append(pdf_results)
            
            if progress:
                progress.close()
            
            # Consolider les résultats
            if all_results:
                consolidated_results = self._consolidate_import_results(all_results)
                self._show_import_summary(consolidated_results, import_options.get('default_reference', ''), "PDF")
                self._log_import_to_history(
                    consolidated_results, 
                    import_options.get('default_reference', ''), 
                    f"PDF: {len(file_paths)} fichiers",
                    pdf_files_info=file_paths
                )
                self.import_completed.emit(consolidated_results)
                
                app_logger.info(f"Import PDF réussi: {consolidated_results.get('imported_count', 0)} éléments")
            else:
                self.import_error.emit("PDF", "Aucun résultat d'import")
                QMessageBox.warning(
                    self.main_window,
                    "Import PDF",
                    "Aucune donnée n'a pu être extraite des fichiers PDF"
                )
            
        except Exception as e:
            app_logger.error(f"Erreur import PDF: {e}")
            self.import_error.emit("PDF", str(e))
            QMessageBox.critical(
                self.main_window,
                "Erreur d'import PDF", 
                f"Une erreur est survenue : {e}"
            )
    
    def _get_import_options_unified(self, detected_columns=None, default_ref_piece=None, 
                                  import_method="CSV", sample_data=None) -> Optional[Dict[str, Any]]:
        """
        Obtenir les options d'import via le dialogue unifié
        
        Méthode extraite de MainWindow._get_import_options_unified()
        
        Args:
            detected_columns: Nombre de colonnes détectées
            default_ref_piece: Référence par défaut
            import_method: Méthode d'import (CSV, PDF, PASTE)
            sample_data: Données d'échantillon pour l'aperçu
            
        Returns:
            Dict avec les options sélectionnées ou None si annulé
        """
        try:
            if not self.dialog_service:
                app_logger.warning("DialogService non disponible, utilisation des options par défaut")
                return {
                    'default_reference': default_ref_piece or '',
                    'import_mode': 0,
                    'import_mode_text': 'Ajouter aux données existantes',
                    'auto_complete': True,
                    'validate_data': True,
                    'clean_duplicates': False
                }
            
            # Utiliser le service de dialogues unifié
            options = self.dialog_service.get_import_options_unified(
                detected_columns=detected_columns,
                default_ref_piece=default_ref_piece,
                import_method=import_method,
                sample_data=sample_data
            )
            
            if options:
                app_logger.debug(f"Options d'import sélectionnées: {options}")
            
            return options
            
        except Exception as e:
            app_logger.error(f"Erreur obtention options import: {e}")
            return None
    
    def _get_import_options_pdf(self, suggested_ref_piece: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Obtenir les options d'import spécifiques pour PDF
        
        Méthode extraite de MainWindow._get_import_options_pdf()
        
        Args:
            suggested_ref_piece: Référence suggérée
            
        Returns:
            Dict avec les options sélectionnées ou None si annulé
        """
        return self._get_import_options_unified(
            detected_columns=None,
            default_ref_piece=suggested_ref_piece,
            import_method="PDF",
            sample_data=None
        )
    
    def _show_import_summary(self, results: Dict[str, Any], ref_piece: str, method: str = "CSV"):
        """
        Afficher le résumé d'import
        
        Méthode extraite de MainWindow._show_import_summary()
        
        Args:
            results: Résultats de l'import
            ref_piece: Référence utilisée
            method: Méthode d'import
        """
        try:
            imported_count = results.get('imported_count', 0)
            skipped_count = results.get('skipped_count', 0)
            error_count = results.get('error_count', 0)
            
            summary_text = f"""
📊 Résumé de l'import {method}

✅ Éléments importés : {imported_count}
⏭️ Éléments ignorés : {skipped_count}  
❌ Erreurs : {error_count}

🏷️ Référence utilisée : {ref_piece or 'Auto-détectée'}

{results.get('details', '')}
            """.strip()
            
            QMessageBox.information(
                self.main_window,
                f"Import {method} terminé",
                summary_text
            )
            
            app_logger.info(f"Résumé import {method} affiché: {imported_count} importés")
            
        except Exception as e:
            app_logger.error(f"Erreur affichage résumé import: {e}")
    
    def _log_import_to_history(self, results: Dict[str, Any], ref_piece: str, 
                             source: str, pdf_files_info: Optional[List[str]] = None):
        """
        Enregistrer l'import dans l'historique
        
        Méthode extraite de MainWindow._log_import_to_history()
        
        Args:
            results: Résultats de l'import
            ref_piece: Référence utilisée
            source: Source de l'import
            pdf_files_info: Informations sur les fichiers PDF (optionnel)
        """
        try:
            from datetime import datetime
            
            history_entry = {
                'timestamp': datetime.now().isoformat(),
                'source': source,
                'reference': ref_piece,
                'imported_count': results.get('imported_count', 0),
                'skipped_count': results.get('skipped_count', 0),
                'error_count': results.get('error_count', 0),
                'details': results.get('details', ''),
                'pdf_files': pdf_files_info
            }
            
            self.import_history.append(history_entry)
            
            # Limiter l'historique à 100 entrées
            if len(self.import_history) > 100:
                self.import_history = self.import_history[-100:]
            
            app_logger.info(f"Import ajouté à l'historique: {source}")
            
        except Exception as e:
            app_logger.error(f"Erreur ajout historique import: {e}")
    
    def _consolidate_import_results(self, results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consolider les résultats de plusieurs imports
        
        Args:
            results_list: Liste des résultats d'import
            
        Returns:
            Dict avec les résultats consolidés
        """
        try:
            consolidated = {
                'imported_count': 0,
                'skipped_count': 0,
                'error_count': 0,
                'success': True,
                'details': []
            }
            
            for results in results_list:
                if results:
                    consolidated['imported_count'] += results.get('imported_count', 0)
                    consolidated['skipped_count'] += results.get('skipped_count', 0)
                    consolidated['error_count'] += results.get('error_count', 0)
                    
                    if not results.get('success', False):
                        consolidated['success'] = False
                    
                    details = results.get('details', '')
                    if details:
                        consolidated['details'].append(details)
            
            consolidated['details'] = '\n'.join(consolidated['details'])
            
            return consolidated
            
        except Exception as e:
            app_logger.error(f"Erreur consolidation résultats: {e}")
            return {'success': False, 'error': str(e)}
    
    def export_data(self, export_format: str):
        """
        Exporter des données avec le service unifié
        
        Args:
            export_format: Format d'export (CSV, HTML_BRANDS, HTML_DETAILS, etc.)
        """
        try:
            if not self._is_initialized:
                app_logger.error("ImportExportManager non initialisé")
                return
            
            if not self.main_export_service:
                app_logger.error("MainExportService non disponible")
                return
            
            self.export_started.emit(export_format, {})
            
            # Déléguer à MainExportService qui gère l'interface utilisateur
            self.main_export_service.export_data(export_format)
            
            # Le MainExportService gère ses propres signaux et interface
            self.export_completed.emit({'format': export_format, 'success': True})
            
        except Exception as e:
            app_logger.error(f"Erreur export: {e}")
            self.export_error.emit(export_format, str(e))
            QMessageBox.critical(
                self.main_window,
                "Erreur d'export",
                f"Une erreur est survenue lors de l'export : {e}"
            )
    
    def get_import_history(self) -> List[Dict[str, Any]]:
        """
        Obtenir l'historique des imports
        
        Returns:
            Liste des entrées d'historique
        """
        return self.import_history.copy()
    
    def clear_import_history(self):
        """Vider l'historique des imports"""
        self.import_history.clear()
        app_logger.info("Historique des imports vidé")
    
    def cleanup(self):
        """Nettoyer les ressources du gestionnaire"""
        try:
            # Pas de signaux spécifiques à déconnecter pour le moment
            app_logger.debug("ImportExportManager nettoyé")
            
        except Exception as e:
            app_logger.error(f"Erreur nettoyage ImportExportManager: {e}")