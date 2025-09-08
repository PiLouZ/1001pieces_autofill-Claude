"""
Service d'export legacy - Phase 2.8
Extrait de main_refactored.py pour centraliser la logique d'export legacy

Responsabilités:
- Export legacy avec formats multiples (CSV, HTML_BRANDS, HTML_DETAILS)
- Gestion des dialogues de sélection de référence
- Traitement des références multiples et filtres personnalisés
- Interface standardisée pour les exports de fallback
"""

from typing import Dict, Any, Optional
from PyQt5.QtWidgets import QApplication, QMessageBox, QComboBox
from PyQt5.QtCore import Qt

from ..services.export_service import ExportFormat
from src.data.data_exporter import ExportError
from src.core.config import Config
from src.core.logger import app_logger


class LegacyExportService:
    """
    Service spécialisé pour les exports legacy (fallback)
    
    Responsabilités:
    - Export legacy avec tous les formats supportés
    - Gestion des références multiples et sélection utilisateur  
    - Traitement des filtres de colonnes personnalisés
    - Intégration avec l'ancien système DataExporter
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def export_data_legacy(self, export_format: ExportFormat, search_term: Optional[str] = None) -> None:
        """
        Exporter les données avec l'ancienne méthode (fallback)
        
        Args:
            export_format: Format d'export désiré
            search_term: Terme de recherche à utiliser (optionnel, récupéré automatiquement)
        """
        # Récupérer le terme de recherche si non fourni
        if search_term is None:
            search_term = self.main_window.advanced_search_service.get_current_search_term_with_fallback(self.main_window)
            
        if not search_term:
            QMessageBox.information(
                self.main_window, 
                "Information", 
                "Veuillez entrer un terme de recherche"
            )
            return
        
        # Sauvegarder le terme de recherche original avant modification
        original_search_term = search_term
        is_multi_reference_export = False
        
        # Afficher dialogue de sélection de référence pour TOUS les exports CSV
        if export_format == ExportFormat.CSV:
            selected_reference = self._handle_csv_reference_selection(search_term)
            if not selected_reference:
                return  # Annulé par l'utilisateur
                
            # Remplacer le search_term par la référence sélectionnée pour l'export CSV
            search_term = selected_reference
            is_multi_reference_export = self._is_multi_reference_search(original_search_term)
        
        try:
            # Récupérer les filtres actifs
            column_filters = self._get_active_column_filters()
            incomplete_filter = getattr(self.main_window, 'show_incomplete_only', False)
            
            # Pour les exports CSV, utiliser une méthode simplifiée
            if export_format == ExportFormat.CSV:
                self._handle_csv_export(search_term)
                return
            
            # Pour les autres formats, utiliser l'ancien système
            self._handle_other_formats_export(
                export_format, search_term, original_search_term, 
                column_filters, incomplete_filter
            )
                
        except ExportError as e:
            self.main_window._show_error(f"Erreur d'export: {e}")
        except Exception as e:
            app_logger.error(f"Erreur export legacy: {e}")
            self.main_window._show_error(f"Erreur inattendue lors de l'export: {e}")
    
    
    def _handle_csv_reference_selection(self, search_term: str) -> Optional[str]:
        """
        Gérer la sélection de référence pour les exports CSV
        
        Args:
            search_term: Terme de recherche actuel
            
        Returns:
            str: Référence sélectionnée par l'utilisateur ou None si annulé
        """
        multi_terms = self._get_multi_reference_terms()
        
        if multi_terms:
            # Références multiples détectées
            return self.main_window.dialog_service.show_reference_selection_dialog(
                "Référence pour l'export CSV",
                f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                f"Choisissez la référence à utiliser pour la première colonne :",
                multi_terms[0]  # Premier terme par défaut
            )
        else:
            # Recherche simple - TOUJOURS afficher le dialogue pour confirmer la référence
            return self.main_window.dialog_service.show_reference_selection_dialog(
                "Référence pour l'export CSV",
                f"Référence détectée : {search_term}\n"
                f"Confirmez ou modifiez la référence à utiliser pour la première colonne :",
                search_term  # Terme de recherche actuel par défaut
            )
    
    def _get_multi_reference_terms(self) -> Optional[list]:
        """
        Récupérer les termes de référence multiple
        
        Returns:
            list: Liste des termes multiples ou None
        """
        if hasattr(self.main_window, '_get_multi_reference_terms'):
            return self.main_window._get_multi_reference_terms()
        return None
    
    def _is_multi_reference_search(self, search_term: str) -> bool:
        """Vérifier si c'est une recherche avec références multiples"""
        return bool(search_term and ('||' in search_term or '&&' in search_term))
    
    def _get_active_column_filters(self) -> Dict[int, str]:
        """
        Récupérer les filtres de colonnes actifs
        
        Returns:
            Dict: Mapping colonne -> filtre actif
        """
        column_filters = {}
        
        if (hasattr(self.main_window, 'table_controller') and 
            hasattr(self.main_window.table_controller, 'filter_widgets')):
            
            for col_idx, filter_widget in self.main_window.table_controller.filter_widgets.items():
                if filter_widget is not None:  # Skip removed filters
                    if isinstance(filter_widget, QComboBox):
                        filter_text = filter_widget.currentText().strip()
                    else:  # QLineEdit
                        filter_text = filter_widget.text().strip()
                    
                    if filter_text:
                        column_filters[col_idx] = filter_text
        
        return column_filters
    
    def _handle_csv_export(self, search_term: str) -> None:
        """
        Traiter l'export CSV avec la méthode simplifiée
        
        Args:
            search_term: Terme de recherche/référence pour l'export
        """
        try:
            result = self.main_window._export_displayed_table_as_csv(search_term)
            if result:
                self.main_window.user_interaction_service.add_to_history(f"Export CSV: {result}")
                self.main_window.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
        except Exception as csv_error:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self.main_window, 
                "Erreur d'export", 
                f"Erreur lors de l'export CSV:\n{csv_error}"
            )
    
    def _handle_other_formats_export(self, export_format: ExportFormat, search_term: str, 
                                   original_search_term: str, column_filters: Dict[int, str], 
                                   incomplete_filter: bool) -> None:
        """
        Traiter l'export pour les autres formats (HTML, etc.)
        
        Args:
            export_format: Format d'export
            search_term: Terme de recherche modifié
            original_search_term: Terme de recherche original
            column_filters: Filtres de colonnes actifs
            incomplete_filter: Filtre des lignes incomplètes
        """
        use_custom_export = False
        
        if use_custom_export:
            self._handle_custom_export(search_term, original_search_term)
        else:
            self._handle_standard_export(
                export_format, search_term, original_search_term, 
                column_filters, incomplete_filter
            )
    
    def _handle_custom_export(self, search_term: str, original_search_term: str) -> None:
        """
        Traiter l'export personnalisé avec fallback
        
        Args:
            search_term: Terme de recherche modifié
            original_search_term: Terme de recherche original
        """
        try:
            # Export personnalisé - utiliser les données de recherche avec référence custom
            result = self.main_window._export_custom_reference_csv_with_current_data(
                search_term, original_search_term
            )
            self.main_window.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
        except Exception as e:
            app_logger.error(f"Erreur export référence personnalisée: {e}")
            self._handle_minimal_csv_fallback(search_term, e)
    
    def _handle_minimal_csv_fallback(self, search_term: str, original_error: Exception) -> None:
        """
        Traiter le fallback CSV minimal
        
        Args:
            search_term: Terme de recherche
            original_error: Erreur originale
        """
        try:
            result = self.main_window._create_minimal_csv_fallback(search_term)
            QMessageBox.information(
                self.main_window, 
                "Export de secours", 
                f"L'export personnalisé a échoué.\n"
                f"Un fichier CSV minimal a été créé avec votre référence."
            )
            self.main_window.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
        except Exception as e2:
            app_logger.error(f"Erreur fallback export: {e2}")
            QMessageBox.warning(
                self.main_window, 
                "Erreur d'export", 
                f"Impossible d'exporter les données.\n"
                f"Erreur: {original_error}\n"
                f"Erreur fallback: {e2}"
            )
    
    def _handle_standard_export(self, export_format: ExportFormat, search_term: str, 
                              original_search_term: str, column_filters: Dict[int, str], 
                              incomplete_filter: bool) -> None:
        """
        Traiter l'export standard avec DataExporter
        
        Args:
            export_format: Format d'export
            search_term: Terme de recherche modifié  
            original_search_term: Terme de recherche original
            column_filters: Filtres de colonnes
            incomplete_filter: Filtre des lignes incomplètes
        """
        # Pour les exports HTML, utiliser le terme original pour préserver les opérateurs
        export_search_term = (original_search_term 
                             if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS] 
                             else search_term)
        
        result = self.main_window.exporter.export_search_results(
            export_search_term, export_format, 
            column_filters=column_filters, 
            incomplete_filter=incomplete_filter
        )
        
        self._handle_export_result(result, export_format)
    
    def _handle_export_result(self, result: str, export_format: ExportFormat) -> None:
        """
        Traiter le résultat de l'export
        
        Args:
            result: Résultat de l'export
            export_format: Format d'export utilisé
        """
        if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
            # Copier dans le presse-papiers
            QApplication.clipboard().setText(result)
            
            # Afficher les informations sur le format utilisé pour HTML Détails
            if export_format == ExportFormat.HTML_DETAILS:
                self._show_html_details_info()
            else:
                self.main_window.statusbar.showMessage(
                    Config.get_message('data_copied'), 
                    Config.STATUS_MESSAGE_TIMEOUT
                )
        else:
            self.main_window.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
            
            # Ajouter l'export dans l'historique avec le chemin du fichier
            if export_format == ExportFormat.CSV:
                self.main_window.user_interaction_service.add_to_history(f"Export CSV: {result}")
            else:
                self.main_window.user_interaction_service.add_to_history(f"Export {export_format.value}: {result}")
    
    def _show_html_details_info(self) -> None:
        """Afficher les informations détaillées pour l'export HTML Details"""
        export_info = self.main_window.exporter.get_last_export_info()
        if export_info:
            format_msg = (f"Export HTML copié ({export_info['description']}) - "
                         f"{export_info['char_count']:,} caractères")
            if export_info['format_used'] != 'complet':
                format_msg += f" (limite: {export_info['char_limit']:,})"
            self.main_window.statusbar.showMessage(
                format_msg, 
                Config.LONG_STATUS_MESSAGE_TIMEOUT * 2
            )
        else:
            self.main_window.statusbar.showMessage(
                Config.get_message('data_copied'), 
                Config.STATUS_MESSAGE_TIMEOUT
            )