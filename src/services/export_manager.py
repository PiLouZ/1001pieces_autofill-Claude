"""
Export Manager Service - PHASE 4 Consolidation
Service unifié pour tous les types d'export

Responsabilités consolidées :
- Gestion unifiée des exports (CSV, HTML_BRANDS, HTML_DETAILS)
- Dialogues de sélection de référence standardisés
- Validation centralisée des données
- Interface unique pour tous les formats d'export
- Gestion des erreurs harmonisée
- Support des recherches simples et multiples

🎯 Remplace : MainExportService, LegacyExportService, ExportService
📈 Économie estimée : ~300 lignes de code dupliqué
"""

import csv
import os
from typing import Dict, Any, Optional, List, Union, Tuple
from PyQt5.QtWidgets import QApplication, QMessageBox
from enum import Enum

from ..core.logger import app_logger
from ..core.config import Config
# PHASE 6 CONSOLIDATION - Communication directe avec HtmlExportService
from ..core.constants import ExportFormat
from .html_export_service import HtmlExportService

class ExportType(Enum):
    """Types d'export supportés"""
    MAIN = "main"           # Export principal avec dialogue référence
    LEGACY = "legacy"       # Export legacy avec fallbacks
    QUICK = "quick"         # Export rapide sans dialogue

class ReferenceSelectionResult:
    """Résultat de sélection de référence"""
    def __init__(self, reference: str, search_term: Union[str, Dict], cancelled: bool = False):
        self.reference = reference
        self.search_term = search_term 
        self.cancelled = cancelled

class ExportManagerService:
    """
    Service unifié de gestion des exports
    
    Centralise toutes les logiques d'export précédemment dispersées dans :
    - MainExportService (export principal)
    - LegacyExportService (export legacy) 
    - ExportService (export de base)
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        # PHASE 6 CONSOLIDATION - Service HTML direct, pas de couche intermédiaire
        self._last_export_info = None  # Pour compatibilité avec get_last_export_info()
    
    def get_last_export_info(self):
        """Récupérer les informations du dernier export HTML - Compatibilité avec ExportService"""
        return self._last_export_info
        
    # ===== INTERFACE PUBLIQUE UNIFIÉE =====
    
    def export_data(self, export_format: ExportFormat, export_type: ExportType = ExportType.MAIN) -> bool:
        """
        Point d'entrée unifié pour tous les exports
        
        Args:
            export_format: Format d'export (CSV, HTML_BRANDS, HTML_DETAILS)
            export_type: Type d'export (MAIN, LEGACY, QUICK)
            
        Returns:
            bool: True si succès, False sinon
        """
        try:
            # Validation initiale commune
            search_term = self._get_search_term()
            if not self._validate_search_term(search_term):
                return False
            
            # Traitement selon le type d'export
            if export_type == ExportType.MAIN:
                return self._handle_main_export(search_term, export_format)
            elif export_type == ExportType.LEGACY:
                return self._handle_legacy_export(search_term, export_format)
            elif export_type == ExportType.QUICK:
                return self._handle_quick_export(search_term, export_format)
            else:
                raise ValueError(f"Type d'export non supporté: {export_type}")
                
        except Exception as e:
            self._handle_error(f"Erreur export {export_type.value}: {e}")
            return False
    
    def export_with_reference(self, export_format: ExportFormat, custom_reference: str) -> bool:
        """
        Export direct avec référence personnalisée (pas de dialogue)
        
        Args:
            export_format: Format d'export
            custom_reference: Référence personnalisée à utiliser
            
        Returns:
            bool: True si succès
        """
        try:
            search_term = self._get_search_term()
            if not self._validate_search_term(search_term):
                return False
                
            return self._execute_export_with_reference(search_term, custom_reference, export_format)
            
        except Exception as e:
            self._handle_error(f"Erreur export avec référence: {e}")
            return False
    
    # ===== GESTION DES TYPES D'EXPORT =====
    
    def _handle_main_export(self, search_term: str, export_format: ExportFormat) -> bool:
        """Gérer l'export principal avec dialogue de référence"""
        # Analyser le terme de recherche
        parsed_term = self._parse_search_term(search_term)
        
        # Sélection de référence avec dialogue
        selection_result = self._handle_reference_selection(search_term, parsed_term, export_format)
        if selection_result.cancelled:
            return False
            
        # Validation des résultats
        if not self._validate_search_results(search_term):
            return False
            
        # Export avec référence confirmée
        return self._execute_export_with_reference(
            selection_result.search_term, 
            selection_result.reference, 
            export_format
        )
    
    def _handle_legacy_export(self, search_term: str, export_format: ExportFormat) -> bool:
        """Gérer l'export legacy avec fallbacks"""
        try:
            # Pour CSV, toujours demander confirmation de référence
            if export_format == ExportFormat.CSV:
                selection_result = self._handle_csv_reference_selection(search_term)
                if selection_result.cancelled:
                    return False
                    
                # Export CSV simplifié
                return self._handle_csv_export_legacy(selection_result.reference)
            
            # Pour les autres formats, utiliser l'export standard
            return self._handle_standard_export(search_term, export_format)
            
        except Exception as e:
            self._handle_error(f"Erreur export legacy: {e}")
            return False
    
    def _handle_quick_export(self, search_term: str, export_format: ExportFormat) -> bool:
        """Gérer l'export rapide sans dialogue"""
        # Extraire une référence automatiquement
        reference = self._extract_default_reference(search_term)
        
        # Export direct
        return self._execute_export_with_reference(search_term, reference, export_format)
    
    # ===== SÉLECTION DE RÉFÉRENCE UNIFIÉE =====
    
    def _handle_reference_selection(self, search_term: str, parsed_term: Union[str, Dict], 
                                  export_format: ExportFormat) -> ReferenceSelectionResult:
        """
        Gérer la sélection de référence avec dialogue unifié
        
        Consolide la logique des 3 services précédents
        """
        if isinstance(parsed_term, dict) and parsed_term.get('type') == 'or':
            # Recherche multiple OR
            return self._handle_multiple_references_dialog(parsed_term, export_format)
        else:
            # Recherche simple
            return self._handle_single_reference_dialog(search_term, export_format)
    
    def _handle_single_reference_dialog(self, search_term: str, export_format: ExportFormat) -> ReferenceSelectionResult:
        """Dialogue pour référence unique"""
        default_reference = self._extract_default_reference(search_term)
        
        # Adapter le message selon le format
        title, message = self._get_reference_dialog_messages(export_format, search_term)
        
        # Afficher le dialogue
        selected_reference = self._show_reference_dialog(title, message, default_reference)
        
        if selected_reference:
            return ReferenceSelectionResult(selected_reference, search_term)
        else:
            return ReferenceSelectionResult("", "", cancelled=True)
    
    def _handle_multiple_references_dialog(self, parsed_term: Dict, export_format: ExportFormat) -> ReferenceSelectionResult:
        """Dialogue pour références multiples"""
        # Extraire les termes disponibles
        terms = self._extract_terms_from_parsed(parsed_term)
        if not terms:
            return ReferenceSelectionResult("", "", cancelled=True)
        
        # Préparer le dialogue
        default_reference = self._extract_default_reference(terms[0])
        title, message = self._get_multiple_reference_dialog_messages(export_format, terms)
        
        # Afficher le dialogue
        selected_reference = self._show_reference_dialog(title, message, default_reference)
        
        if selected_reference:
            return ReferenceSelectionResult(selected_reference, parsed_term)
        else:
            return ReferenceSelectionResult("", "", cancelled=True)
    
    def _handle_csv_reference_selection(self, search_term: str) -> ReferenceSelectionResult:
        """Sélection spécialisée pour CSV (legacy)"""
        # Vérifier si références multiples
        multi_terms = self._get_multi_reference_terms()
        
        if multi_terms:
            title = "Référence pour l'export CSV"
            message = (f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                      f"Choisissez la référence à utiliser pour la première colonne :")
            default = multi_terms[0]
        else:
            title = "Référence pour l'export CSV"
            message = (f"Référence détectée : {search_term}\n"
                      f"Confirmez ou modifiez la référence à utiliser pour la première colonne :")
            default = search_term
        
        selected_reference = self._show_reference_dialog(title, message, default)
        
        if selected_reference:
            return ReferenceSelectionResult(selected_reference, search_term)
        else:
            return ReferenceSelectionResult("", "", cancelled=True)
    
    # ===== DIALOGUES UNIFIÉS =====
    
    def _show_reference_dialog(self, title: str, message: str, default_reference: str) -> Optional[str]:
        """Afficher dialogue de sélection de référence unifié"""
        # Utiliser le service de dialogue unifié si disponible
        if hasattr(self.main_window, 'dialog_service'):
            return self.main_window.dialog_service.show_reference_selection_dialog(
                title, message, default_reference
            )
        else:
            # Fallback avec QInputDialog
            from PyQt5.QtWidgets import QInputDialog
            selected_reference, ok = QInputDialog.getText(
                self.main_window, title, message, text=default_reference
            )
            return selected_reference if ok else None
    
    def _get_reference_dialog_messages(self, export_format: ExportFormat, search_term: str) -> Tuple[str, str]:
        """Obtenir les messages de dialogue selon le format"""
        if export_format == ExportFormat.CSV:
            title = "Référence pour l'export CSV"
            message = (f"Référence détectée : {search_term}\n"
                      f"Cette référence sera utilisée dans la première colonne du fichier CSV.\n"
                      f"Confirmez ou modifiez la référence :")
        else:
            title = f"Référence pour l'export {export_format.value}"
            message = (f"Référence détectée : {search_term}\n"
                      f"Confirmez ou modifiez la référence à utiliser :")
        
        return title, message
    
    def _get_multiple_reference_dialog_messages(self, export_format: ExportFormat, terms: List[str]) -> Tuple[str, str]:
        """Obtenir les messages pour références multiples"""
        title = f"Référence pour l'export {export_format.value}"
        
        if len(terms) == 1:
            message = (f"Terme de recherche unique détecté : {terms[0]}\n"
                      f"Confirmez ou modifiez la référence :")
        else:
            message = (f"Recherche multiple détectée avec {len(terms)} termes.\n"
                      f"Premier terme suggéré : {terms[0]}\n"
                      f"Confirmez ou saisissez la référence à utiliser :")
        
        return title, message
    
    # ===== VALIDATION CENTRALISÉE =====
    
    def _validate_search_term(self, search_term: str) -> bool:
        """Validation centralisée du terme de recherche"""
        if not search_term or not search_term.strip():
            self._add_to_history("⚠️ Erreur export: Aucun terme de recherche saisi")
            return False
        return True
    
    def _validate_search_results(self, search_term: str) -> bool:
        """Valider que la recherche a des résultats"""
        try:
            # Utiliser la même logique que TableController
            if search_term and ('&&' in search_term or '||' in search_term):
                # Recherche avancée
                parsed_search_term = self.main_window.advanced_search_service.parse_advanced_search(search_term)
                results = self.main_window.db_manager.load_data(
                    parsed_search_term, {}, None, None, None, None, False
                )
            else:
                # Recherche simple
                results = self.main_window.db_manager.load_data(
                    search_term, {}, None, None, None, None, False
                )
            
            if not results:
                self._add_to_history("⚠️ Export annulé: Aucun résultat trouvé pour cette recherche")
                return False
            
            return True
            
        except Exception as e:
            app_logger.error(f"Erreur validation résultats de recherche: {e}")
            return False
    
    # ===== EXECUTION D'EXPORT UNIFIÉE =====
    
    def _execute_export_with_reference(self, search_data_term: Union[str, Dict], 
                                     reference: str, export_format: ExportFormat) -> bool:
        """
        Exécuter l'export avec référence personnalisée
        
        Unifie la logique des 3 anciens services
        """
        try:
            # Récupérer les données
            data = self._get_export_data(search_data_term)
            if not data:
                raise Exception("Aucune donnée trouvée pour la recherche")
            
            # Export selon le format
            if export_format == ExportFormat.CSV:
                return self._execute_csv_export(data, reference)
            elif export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
                return self._execute_html_export(data, reference, export_format)
            else:
                raise Exception(f"Format d'export {export_format} non supporté")
                
        except Exception as e:
            raise Exception(f"Erreur lors de l'export: {e}")
    
    def _execute_csv_export(self, data: List, reference: str) -> bool:
        """Exécuter l'export CSV avec format standardisé"""
        filename = f"{reference}_everyParts.csv"
        
        try:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            full_path = os.path.join(desktop_path, filename)
            
            with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                # En-têtes standardisés
                headers = ['product', 'type', 'manufacturer', 'modele_name', 'reference_modele', 'commercial_reference']
                writer.writerow(headers)
                
                # Données formatées
                for row in data:
                    type_val = row[0] if len(row) > 0 else ''
                    manufacturer_val = row[1] if len(row) > 1 else ''
                    ref_modele_val = row[2] if len(row) > 2 else ''
                    commercial_ref_val = row[3] if len(row) > 3 else ''
                    
                    modele_name = f"{ref_modele_val} - {commercial_ref_val}".strip(' -')
                    
                    csv_row = [
                        reference,                    # product
                        type_val,                     # type
                        manufacturer_val,             # manufacturer
                        modele_name,                  # modele_name
                        ref_modele_val,               # reference_modele
                        commercial_ref_val            # commercial_reference
                    ]
                    writer.writerow(csv_row)
            
            self._add_to_history(f"Export CSV: {filename} ({len(data)} lignes)")
            return True
            
        except Exception as e:
            raise Exception(f"Erreur export CSV: {e}")
    
    def _execute_html_export(self, data: List, reference: str, export_format: ExportFormat) -> bool:
        """Exécuter l'export HTML via service unifié"""
        try:
            # PHASE 6 CONSOLIDATION - Direct vers HtmlExportService
            if export_format == ExportFormat.HTML_BRANDS:
                result = HtmlExportService.generate_html_brands(data)
            elif export_format == ExportFormat.HTML_DETAILS:
                result = HtmlExportService.generate_html_details(data)
                # Conserver les infos d'export pour compatibilité
                char_count = HtmlExportService.count_non_html_chars(result)
                self._last_export_info = {
                    'format_used': 'optimisé',
                    'char_count': char_count,
                    'char_limit': HtmlExportService.CHAR_LIMIT,
                    'description': 'Format optimisé automatiquement'
                }
            else:
                raise ValueError(f"Format d'export HTML non supporté: {export_format}")
            
            # Copier dans le presse-papiers
            QApplication.clipboard().setText(result)
            
            format_name = "HTML Marques" if export_format == ExportFormat.HTML_BRANDS else "HTML Détails"
            self._add_to_history(f"Export {format_name}: {len(data)} résultats copiés")
            
            return True
            
        except Exception as e:
            raise Exception(f"Erreur export HTML: {e}")
    
    def _handle_csv_export_legacy(self, reference: str) -> bool:
        """Gérer l'export CSV legacy"""
        try:
            result = self.main_window._export_displayed_table_as_csv(reference)
            if result:
                self._add_to_history(f"Export CSV: {result}")
                self.main_window.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
                return True
            return False
            
        except Exception as e:
            QMessageBox.critical(
                self.main_window, 
                "Erreur d'export", 
                f"Erreur lors de l'export CSV:\n{e}"
            )
            return False
    
    def _handle_standard_export(self, search_term: str, export_format: ExportFormat) -> bool:
        """Gérer l'export standard (autres formats)"""
        try:
            # Récupérer les filtres actifs
            column_filters = self._get_active_column_filters()
            incomplete_filter = getattr(self.main_window, 'show_incomplete_only', False)
            
            # Export via DataExporter
            result = self.main_window.exporter.export_search_results(
                search_term, export_format,
                column_filters=column_filters,
                incomplete_filter=incomplete_filter
            )
            
            # Traitement du résultat
            if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
                QApplication.clipboard().setText(result)
                self._show_export_status(export_format, result)
            else:
                self.main_window.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
                self._add_to_history(f"Export {export_format.value}: {result}")
            
            return True
            
        except Exception as e:
            self._handle_error(f"Erreur export standard: {e}")
            return False
    
    # ===== UTILITAIRES =====
    
    def _get_search_term(self) -> str:
        """Récupérer le terme de recherche actuel"""
        return self.main_window.search_input.text().strip()
    
    def _parse_search_term(self, search_term: str) -> Union[str, Dict]:
        """Parser le terme de recherche"""
        return self.main_window.advanced_search_service.get_current_search_term_with_fallback(
            self.main_window
        ) or search_term
    
    def _extract_default_reference(self, search_term: str) -> str:
        """Extraire une référence par défaut"""
        return self.main_window.search_service.extract_first_term(search_term)
    
    def _extract_terms_from_parsed(self, parsed_term: Dict) -> List[str]:
        """Extraire les termes d'une recherche parsée"""
        terms = []
        for group in parsed_term.get('groups', []):
            terms.extend(group.get('terms', []))
        return terms
    
    def _get_multi_reference_terms(self) -> Optional[List[str]]:
        """Récupérer les termes de référence multiple"""
        if hasattr(self.main_window, '_get_multi_reference_terms'):
            return self.main_window._get_multi_reference_terms()
        return None
    
    def _get_export_data(self, search_data_term: Union[str, Dict]) -> List:
        """Récupérer les données d'export"""
        if isinstance(search_data_term, dict):
            return self.main_window.db_manager.get_export_data(search_data_term)
        else:
            return self.main_window.db_manager.get_export_data(search_data_term)
    
    def _get_active_column_filters(self) -> Dict[int, str]:
        """Récupérer les filtres de colonnes actifs"""
        from PyQt5.QtWidgets import QComboBox
        
        column_filters = {}
        
        if (hasattr(self.main_window, 'table_controller') and 
            hasattr(self.main_window.table_controller, 'filter_widgets')):
            
            for col_idx, filter_widget in self.main_window.table_controller.filter_widgets.items():
                if filter_widget is not None:
                    if isinstance(filter_widget, QComboBox):
                        filter_text = filter_widget.currentText().strip()
                    else:  # QLineEdit
                        filter_text = filter_widget.text().strip()
                    
                    if filter_text:
                        column_filters[col_idx] = filter_text
        
        return column_filters
    
    def _show_export_status(self, export_format: ExportFormat, result: str) -> None:
        """Afficher le statut d'export"""
        if export_format == ExportFormat.HTML_DETAILS:
            export_info = self._last_export_info
            if export_info:
                format_msg = (f"Export HTML copié ({export_info['description']}) - "
                             f"{export_info['char_count']:,} caractères")
                if export_info['format_used'] != 'complet':
                    format_msg += f" (limite: {export_info['char_limit']:,})"
                self.main_window.statusbar.showMessage(
                    format_msg, Config.LONG_STATUS_MESSAGE_TIMEOUT * 2
                )
            else:
                self.main_window.statusbar.showMessage(
                    Config.get_message('data_copied'), Config.STATUS_MESSAGE_TIMEOUT
                )
        else:
            self.main_window.statusbar.showMessage(
                Config.get_message('data_copied'), Config.STATUS_MESSAGE_TIMEOUT
            )
    
    def _add_to_history(self, message: str) -> None:
        """Ajouter un message à l'historique"""
        if hasattr(self.main_window, 'user_interaction_service'):
            self.main_window.user_interaction_service.add_to_history(message)
    
    def _handle_error(self, error_message: str) -> None:
        """Gérer les erreurs de manière unifiée"""
        app_logger.error(error_message)
        self._add_to_history(f"❌ {error_message}")
        if hasattr(self.main_window, '_show_error'):
            self.main_window._show_error(error_message)