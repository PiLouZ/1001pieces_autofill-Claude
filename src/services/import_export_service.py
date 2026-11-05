"""
Service centralisé pour les opérations d'import et d'export
Extrait de main_refactored.py pour centraliser la logique d'import/export
"""

import os
from typing import Dict, Any

from ..utils.qt_imports import pyqtSignal

from ..core.logger import app_logger
from .base_service import BaseService, service_operation, safe_operation
from ..utils.boites import choisir_fichier_a_ouvrir

class ImportExportService(BaseService):
    """Service centralisé pour les opérations d'import et d'export"""

    # Signaux pour notifier les changements
    import_completed = pyqtSignal(dict)  # résultat_import
    export_completed = pyqtSignal(str)   # chemin_fichier_exporté
    operation_progress = pyqtSignal(int)  # pourcentage

    def __init__(self, parent_window, parent=None):
        super().__init__(parent_window=parent_window, parent=parent)

        # Services requis pour l'injection automatique (seulement les essentiels disponibles)
        self._required_services = [
            'export_manager', 'db_manager',
            'import_manager', 'file_processing_service', 'table_controller'
        ]

    def initialize_services(self):
        """Initialiser les références aux services depuis la fenêtre parent"""
        # Utiliser l'injection automatique de BaseService
        self.inject_required_services()
        self.log_operation("initialize_services", "ImportExportService services initialisés", "debug")

    # ================================
    # MÉTHODES D'EXPORT
    # ================================

    @service_operation("export_donnees")
    def export_data(self):
        """Point d'entrée principal pour export avec sélection de format"""
        if not self.export_manager:
            self.handle_error(Exception("ExportManager non disponible"), "export_data")
            return

        # Déléguer à l'ExportManager
        self.export_manager.export_data()

    # ================================
    # MÉTHODES D'IMPORT
    # ================================

    def import_file(self):
        """Dialogue de sélection de fichiers et délégation à ImportManager"""
        return self._safe_import_file()

    @safe_operation("import_file_dialog")
    def _safe_import_file(self):
        """Helper sécurisé pour dialogue import"""
        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite(file_path):
            # Même garde que @safe_operation("import_file_dialog") de la méthode
            # (le décorateur, écrit pour une méthode, ne s'applique pas à ce rappel)
            try:
                # Déléguer au système d'import approprié
                if file_path.lower().endswith('.pdf'):
                    self.import_pdf_from_path(file_path)
                else:
                    self._process_import_file(file_path)
            except Exception as e:
                app_logger.error(f"{self._service_name}.Erreur import_file_dialog: {e}")

        choisir_fichier_a_ouvrir(self.parent_window, 'Importer un fichier', '', 'Fichiers supportés (*.csv *.xlsx *.json *.pdf);;Fichiers CSV (*.csv);;Fichiers Excel (*.xlsx);;Fichiers JSON (*.json);;Fichiers PDF (*.pdf)', _suite)

    def import_csv_from_path(self, file_path: str):
        """Import CSV par glisser/déposer avec fallback legacy"""
        return self._safe_import_csv_from_path(file_path)

    @safe_operation("import_csv_path")
    def _safe_import_csv_from_path(self, file_path: str):
        """Helper sécurisé pour import CSV"""
        if not os.path.exists(file_path):
            app_logger.error(f"Fichier non trouvé: {file_path}")
            return

        if self.import_manager:
            app_logger.info(f"Import CSV via ImportManager: {file_path}")
            self.import_manager.import_files(
                [file_path],
                show_dialog=True,
                callback=self.parent_window._on_import_complete
            )
        else:
            app_logger.error("ImportManager non disponible")

    def import_pdf_from_path(self, file_path: str):
        """Délégation au FileProcessingService"""
        return self._safe_import_pdf_from_path(file_path)

    @safe_operation("import_pdf_path")
    def _safe_import_pdf_from_path(self, file_path: str):
        """Helper sécurisé pour import PDF"""
        if self.file_processing_service:
            self.file_processing_service.import_pdf_files(file_path)
        else:
            app_logger.error("FileProcessingService non disponible")

    # ================================
    # MÉTHODES DE SUPPORT
    # ================================

    def _process_import_file(self, file_path: str):
        """Traiter un fichier d'import selon son extension"""
        return self._safe_process_import_file(file_path)

    @safe_operation("process_import_file")
    def _safe_process_import_file(self, file_path: str):
        """Helper sécurisé pour traitement fichier import"""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.csv':
            self.import_csv_from_path(file_path)
        elif ext in ['.xlsx', '.xls']:
            # Dette technique connue : import Excel non implémenté (cf. CLAUDE.md).
            # Formats supportés à ce jour : CSV et PDF.
            app_logger.warning("Import Excel non supporté (dette technique connue) : utilisez CSV ou PDF")
        elif ext == '.json':
            # Dette technique connue : import JSON non implémenté (cf. CLAUDE.md).
            app_logger.warning("Import JSON non supporté (dette technique connue) : utilisez CSV ou PDF")
        elif ext == '.pdf':
            self.import_pdf_from_path(file_path)
        else:
            app_logger.error(f"Format de fichier non supporté: {ext}")

    def _show_import_results_new(self, result: Dict[str, Any]):
        """Traitement des résultats du nouveau système ImportManager"""
        return self._safe_show_import_results_new(result)

    @safe_operation("show_import_results")
    def _safe_show_import_results_new(self, result: Dict[str, Any]):
        """Helper sécurisé pour affichage résultats import"""
        if result.get('success', False):
            # Import réussi
            self._show_import_summary(result)
            self._log_import_to_history(result)

            # Recharger la table
            if self.table_controller:
                self.table_controller.load_data()

            # Émettre le signal
            self.import_completed.emit(result)

        else:
            # Erreur d'import
            error_msg = result.get('error', 'Erreur inconnue')
            app_logger.error(f"Échec import: {error_msg}")
            if self.dialog_service:
                self.dialog_service.show_error("Erreur Import", f"L'import a échoué: {error_msg}")

    def _show_import_summary(self, result: Dict[str, Any]):
        """Affichage formaté des résultats d'import"""
        return self._safe_show_import_summary(result)

    @safe_operation("show_import_summary")
    def _safe_show_import_summary(self, result: Dict[str, Any]):
        """Helper sécurisé pour affichage résumé"""
        if not self.dialog_service:
            return

        summary = self._generate_console_summary(result)

        self.dialog_service.show_info("Import Terminé", summary)

    def _generate_console_summary(self, result: Dict[str, Any]) -> str:
        """Génération du résumé au format console"""
        return self._safe_generate_console_summary(result)

    @safe_operation("generate_console_summary", default_return="Résumé non disponible")
    def _safe_generate_console_summary(self, result: Dict[str, Any]) -> str:
        """Helper sécurisé pour génération résumé"""
        stats = result.get('stats', {})

        summary = f"""Import terminé avec succès !

Statistiques:
• Total traité: {stats.get('total_processed', 0)}
• Ajoutés: {stats.get('added', 0)}
• Mis à jour: {stats.get('updated', 0)}
• Ignorés: {stats.get('skipped', 0)}
• Erreurs: {stats.get('errors', 0)}

Durée: {result.get('duration', 'N/A')}
Fichier: {result.get('file_path', 'N/A')}
"""

        if result.get('warnings'):
            summary += f"\nAvertissements: {len(result['warnings'])}"

        return summary

    def _log_import_to_history(self, result: Dict[str, Any]):
        """Enregistrement dans l'historique et logs"""
        return self._safe_log_import_to_history(result)

    @safe_operation("log_import_history")
    def _safe_log_import_to_history(self, result: Dict[str, Any]):
        """Helper sécurisé pour log historique import"""
        if self.user_interaction_service:
            stats = result.get('stats', {})
            file_name = os.path.basename(result.get('file_path', 'Fichier inconnu'))

            history_entry = f"Import {file_name}: {stats.get('added', 0)} ajoutés, {stats.get('updated', 0)} mis à jour"

            self.user_interaction_service.add_to_history(history_entry)

        app_logger.info(f"Import terminé: {result}")

    # ================================
    # MÉTHODES HÉRITÉES (À ADAPTER)
    # ================================
