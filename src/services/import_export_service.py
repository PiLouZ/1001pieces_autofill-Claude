"""
Service centralisé pour les opérations d'import et d'export
Extrait de main_refactored.py pour centraliser la logique d'import/export
"""

import csv
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from ..ui.qt_imports import (QFileDialog, QApplication, QProgressDialog, QMessageBox,
                            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                            QPushButton, QComboBox, Qt, pyqtSignal, QInputDialog)

from ..core.logger import app_logger
from ..core.constants import ExportFormat
from ..services.export_manager import ExportManagerService, ExportType
from .base_service import BaseService, service_operation, safe_operation

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

    @service_operation("export_reference_personnalisee")
    def export_with_custom_reference(self, reference_text: str = None):
        """Export avec référence personnalisée et récupération de données"""
        if not reference_text:
            # Demander la référence à l'utilisateur
            reference_text, ok = self._get_custom_reference_dialog()
            if not ok or not reference_text.strip():
                return

        reference_text = reference_text.strip()

        # Récupérer les données depuis la base
        if not self.db_manager:
            self.handle_error(Exception("DatabaseManager non disponible"), "export_with_custom_reference")
            return

        query = """
            SELECT type, marque, modele, reference, designation, prix, stock, notes
            FROM appareils
            WHERE reference LIKE ? OR designation LIKE ? OR marque LIKE ? OR modele LIKE ?
            ORDER BY marque, modele, reference
        """
        search_pattern = f"%{reference_text}%"
        results = self.db_manager.execute_query(query, (search_pattern, search_pattern, search_pattern, search_pattern))

        if not results:
            if self.dialog_service:
                self.dialog_service.show_info("Aucun résultat", f"Aucun appareil trouvé pour la référence '{reference_text}'")
            return

        # Exporter les résultats
        self._export_custom_results(results, reference_text)

    @service_operation("export_csv_reference")
    def export_csv_with_reference(self, data: List[tuple], reference: str):
        """Export CSV avec format spécifique et gestion des headers"""
        return self._safe_export_csv_with_reference(data, reference)

    @safe_operation("export_csv_reference_helper")
    def _safe_export_csv_with_reference(self, data: List[tuple], reference: str):
        """Helper sécurisé pour export CSV"""
        # Sélectionner le fichier de destination
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent_window,
            f"Exporter CSV - {reference}",
            f"export_{reference}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "Fichiers CSV (*.csv)"
        )

        if not file_path:
            return

        # Headers standards
        headers = ["Type", "Marque", "Modèle", "Référence", "Désignation", "Prix", "Stock", "Notes"]

        # Écrire le fichier CSV
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')

            # Écrire les headers
            writer.writerow(headers)

            # Écrire les données
            for row in data:
                writer.writerow(row)

        app_logger.info(f"Export CSV réussi: {file_path} ({len(data)} lignes)")

        # Notifier le succès
        if self.dialog_service:
            self.dialog_service.show_success("Export Réussi", f"Données exportées vers:\n{file_path}")

        # Émettre le signal
        self.export_completed.emit(file_path)

    def export_html_with_reference(self, data: List[tuple], reference: str):
        """Export HTML avec copie vers presse-papiers"""
        return self._safe_export_html_with_reference(data, reference)

    @safe_operation("export_html_reference")
    def _safe_export_html_with_reference(self, data: List[tuple], reference: str):
        """Helper sécurisé pour export HTML"""
        # Générer le HTML
        html_content = self._generate_html_table(data, reference)

        # Copier vers le presse-papiers
        clipboard = QApplication.clipboard()
        clipboard.setText(html_content)

        app_logger.info(f"Export HTML copié vers presse-papiers pour référence: {reference}")

        # Notifier le succès
        if self.dialog_service:
            self.dialog_service.show_success("Export HTML", "Tableau HTML copié vers le presse-papiers")

        # Émettre le signal
        self.export_completed.emit("clipboard")

    # ================================
    # MÉTHODES D'IMPORT
    # ================================

    def import_file(self):
        """Dialogue de sélection de fichiers et délégation à ImportManager"""
        return self._safe_import_file()

    @safe_operation("import_file_dialog")
    def _safe_import_file(self):
        """Helper sécurisé pour dialogue import"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent_window,
            "Importer un fichier",
            "",
            "Fichiers supportés (*.csv *.xlsx *.json *.pdf);;Fichiers CSV (*.csv);;Fichiers Excel (*.xlsx);;Fichiers JSON (*.json);;Fichiers PDF (*.pdf)"
        )

        if file_path:
            # Déléguer au système d'import approprié
            if file_path.lower().endswith('.pdf'):
                self.import_pdf_from_path(file_path)
            else:
                self._process_import_file(file_path)

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

    def _get_custom_reference_dialog(self) -> Tuple[str, bool]:
        """Dialogue pour saisie de référence personnalisée"""
        return self._safe_get_custom_reference_dialog()

    @safe_operation("custom_reference_dialog", default_return=("", False))
    def _safe_get_custom_reference_dialog(self) -> Tuple[str, bool]:
        """Helper sécurisé pour dialogue référence"""
        text, ok = QInputDialog.getText(
            self.parent_window,
            "Export avec référence",
            "Entrez la référence ou terme de recherche:",
            QLineEdit.Normal,
            ""
        )

        return text, ok

    def _export_custom_results(self, results: List[tuple], reference: str):
        """Exporter les résultats d'une recherche personnalisée"""
        return self._safe_export_custom_results(results, reference)

    @safe_operation("export_custom_results")
    def _safe_export_custom_results(self, results: List[tuple], reference: str):
        """Helper sécurisé pour export résultats personnalisés"""
        # Demander le format d'export
        format_choice = self._get_export_format_dialog()

        if format_choice == "CSV":
            self.export_csv_with_reference(results, reference)
        elif format_choice == "HTML":
            self.export_html_with_reference(results, reference)
        else:
            app_logger.info("Export annulé par l'utilisateur")

    def _get_export_format_dialog(self) -> str:
        """Dialogue de sélection du format d'export"""
        return self._safe_get_export_format_dialog()

    @safe_operation("export_format_dialog", default_return="")
    def _safe_get_export_format_dialog(self) -> str:
        """Helper sécurisé pour dialogue format export"""
        formats = ["CSV", "HTML"]
        format_choice, ok = QInputDialog.getItem(
            self.parent_window,
            "Format d'export",
            "Choisissez le format d'export:",
            formats,
            0,
            False
        )

        return format_choice if ok else ""

    def _generate_html_table(self, data: List[tuple], reference: str) -> str:
        """Générer une table HTML depuis les données"""
        return self._safe_generate_html_table(data, reference)

    @safe_operation("generate_html_table", default_return="")
    def _safe_generate_html_table(self, data: List[tuple], reference: str) -> str:
        """Helper sécurisé pour génération HTML"""
        headers = ["Type", "Marque", "Modèle", "Référence", "Désignation", "Prix", "Stock", "Notes"]

        html = f"""
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <caption>Export - {reference} ({len(data)} résultats)</caption>
            <thead>
                <tr style="background-color: #f2f2f2;">
        """

        # Headers
        for header in headers:
            html += f"<th style='padding: 8px; text-align: left;'>{header}</th>"

        html += "</tr></thead><tbody>"

        # Données
        for row in data:
            html += "<tr>"
            for cell in row:
                html += f"<td style='padding: 8px;'>{cell if cell is not None else ''}</td>"
            html += "</tr>"

        html += "</tbody></table>"

        return html

    def _get_import_options_unified(self) -> Optional[Dict[str, Any]]:
        """Dialogue unifié pour options d'import avec conversion tuple"""
        return self._safe_get_import_options_unified()

    @safe_operation("import_options_unified", default_return=None)
    def _safe_get_import_options_unified(self) -> Optional[Dict[str, Any]]:
        """Helper sécurisé pour options d'import"""
        # Pour l'instant, retourner des options par défaut
        # TODO: Implémenter le dialogue complet
        return {
            'has_headers': True,
            'separator': ';',
            'encoding': 'utf-8',
            'skip_duplicates': True,
            'create_backup': True
        }

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

    def _detect_separator(self, file_path: str) -> str:
        """Détection automatique des séparateurs CSV"""
        return self._safe_detect_separator(file_path)

    @safe_operation("detect_separator", default_return=';')
    def _safe_detect_separator(self, file_path: str) -> str:
        """Helper sécurisé pour détection séparateur"""
        with open(file_path, 'r', encoding='utf-8') as f:
            sample = f.read(1024)

        # Logique simple de détection
        if sample.count(';') > sample.count(','):
            return ';'
        elif sample.count(',') > sample.count('\t'):
            return ','
        elif sample.count('\t') > 0:
            return '\t'
        else:
            return ';'  # Par défaut

    def _detect_file_encoding(self, file_path: str) -> str:
        """Détection de l'encodage des fichiers"""
        try:
            import chardet

            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)

            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')

            app_logger.debug(f"Encodage détecté: {encoding} (confiance: {result.get('confidence', 0)})")

            return encoding

        except ImportError:
            app_logger.warning("Module chardet non disponible, utilisation utf-8 par défaut")
            return 'utf-8'
        except Exception as e:
            app_logger.error(f"Erreur détection encodage: {e}")
            return 'utf-8'