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

 Consolidation achevée en v3.69.0 : les trois services fusionnés ici ont été
 supprimés, leur chemin d'accès n'ayant jamais été branché à l'interface.
 Économie estimée : ~300 lignes de code dupliqué
"""

import csv
import os
from typing import Dict, Any, Optional, List, Union, Tuple
from ..ui.qt_imports import QApplication, QMessageBox
from enum import Enum

from ..core.logger import app_logger
from ..core.config import Config
# PHASE 6 CONSOLIDATION - Communication directe avec HtmlExportService
from ..core.constants import ExportFormat
from .html_export_service import HtmlExportService
from ..utils.error_handler import handle_export_errors

class ExportType(Enum):
    """Types d'export supportés"""
    MAIN = "main"           # Export principal avec dialogue référence
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
        self._last_export_info = None  # Alimenté par l'export HTML, lu par _show_export_status()
    
        
    # ===== INTERFACE PUBLIQUE UNIFIÉE =====

    @handle_export_errors(title="Erreur export unifié")
    def export_data(self, export_format: ExportFormat, export_type: ExportType = ExportType.MAIN,
                    profile_name: str = None) -> bool:
        """
        Point d'entrée unifié pour tous les exports

        Args:
            export_format: Format d'export (CSV, HTML_BRANDS, HTML_DETAILS)
            export_type: Type d'export (MAIN, QUICK)
            profile_name: Profil HTML Détails à utiliser (None = profil par défaut)

        Returns:
            bool: True si succès, False sinon
        """
        # Validation initiale commune
        search_term = self._get_search_term()
        if not self._validate_search_term(search_term):
            return False

        # Traitement selon le type d'export
        if export_type == ExportType.MAIN:
            return self._handle_main_export(search_term, export_format)
        elif export_type == ExportType.QUICK:
            return self._handle_quick_export(search_term, export_format, profile_name=profile_name)
        else:
            raise ValueError(f"Type d'export non supporté: {export_type}")
    
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
    
    
    def _handle_quick_export(self, search_term: str, export_format: ExportFormat,
                             profile_name: str = None) -> bool:
        """Gérer l'export rapide sans dialogue"""
        # Extraire une référence automatiquement
        reference = self._extract_default_reference(search_term)

        # Utiliser le terme parsé avec flags bannières
        parsed = self._parse_search_term(search_term)
        return self._execute_export_with_reference(parsed, reference, export_format,
                                                   profile_name=profile_name)
    
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
            # Recherche simple — utilise parsed_term (avec flags bannières) comme données d'export
            return self._handle_single_reference_dialog(search_term, export_format, parsed_term)
    
    def _handle_single_reference_dialog(self, search_term: str, export_format: ExportFormat,
                                         parsed_term=None) -> ReferenceSelectionResult:
        """Dialogue pour référence unique"""
        default_reference = self._extract_default_reference(search_term)

        # Adapter le message selon le format
        title, message = self._get_reference_dialog_messages(export_format, search_term)

        # Afficher le dialogue
        selected_reference = self._show_reference_dialog(title, message, default_reference)

        if selected_reference:
            # Utiliser parsed_term (avec flags des bannières actives) si disponible
            search_data = parsed_term if parsed_term is not None else search_term
            return ReferenceSelectionResult(selected_reference, search_data)
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
            from ..ui.qt_imports import QInputDialog
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
            self._add_to_history("[!] Erreur export: Aucun terme de recherche saisi")
            return False
        return True
    
    @handle_export_errors(title="Erreur validation résultats")
    def _validate_search_results(self, search_term: str) -> bool:
        """Valider que la recherche a des résultats"""
        # Reproduire exactement le même périmètre que le tableau (parsing + flags
        # de supersession/équivalence actifs)
        effective_search_term = self.main_window.table_controller.build_effective_search_term(search_term)
        results = self.main_window.db_manager.load_data(
            effective_search_term, {}, None, None, None, None, False
        )

        if not results:
            self._add_to_history("[!] Export annulé: Aucun résultat trouvé pour cette recherche")
            return False

        return True
    
    # ===== EXECUTION D'EXPORT UNIFIÉE =====
    
    @handle_export_errors(title="Erreur exécution export")
    def _execute_export_with_reference(self, search_data_term: Union[str, Dict],
                                     reference: str, export_format: ExportFormat,
                                     profile_name: str = None) -> bool:
        """
        Exécuter l'export avec référence personnalisée

        Unifie la logique des 3 anciens services
        """
        # Récupérer les données
        data = self._get_export_data(search_data_term)
        if not data:
            raise Exception("Aucune donnée trouvée pour la recherche")

        # Export selon le format
        if export_format == ExportFormat.CSV:
            return self._execute_csv_export(data, reference)
        elif export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
            return self._execute_html_export(data, reference, export_format,
                                             profile_name=profile_name)
        else:
            raise Exception(f"Format d'export {export_format} non supporté")
    
    @handle_export_errors(title="Erreur export CSV")
    def _execute_csv_export(self, data: List, reference: str) -> bool:
        """Exécuter l'export CSV selon la configuration utilisateur.

        Colonnes, séparateur, encodage et pattern de nom proviennent de la
        fenêtre « Configuration des exports ». {export_ref} vaut la référence
        confirmée dans le dialogue d'export, pas le terme de recherche.
        """
        from datetime import datetime
        from .export_config_service import (
            resolve_output_dir, get_csv_settings, render_csv_row_with,
            format_csv_filename, _assainir_ligne_csv
        )

        service = getattr(self.main_window, 'export_config_service', None)
        reglages = get_csv_settings(service)

        filename = format_csv_filename(
            reglages['filename_pattern'],
            export_ref=reference,
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        full_path = os.path.join(resolve_output_dir(service), filename)

        with open(full_path, 'w', newline='', encoding=reglages['encoding']) as csvfile:
            writer = csv.writer(csvfile, delimiter=reglages['separator'])
            writer.writerow(reglages['headers'])

            for record in data:
                # Compléter les records courts : le renderer attend 6 champs
                record = tuple(record) + ('',) * (6 - len(record)) if len(record) < 6 else record
                # Neutralisation injection de formules avant écriture
                writer.writerow(_assainir_ligne_csv(
                    render_csv_row_with(reglages['columns'], record, reference)
                ))

        self._add_to_history(f"Export CSV: {filename} ({len(data)} lignes)")
        return True
    
    @handle_export_errors(title="Erreur export HTML")
    def _execute_html_export(self, data: List, reference: str, export_format: ExportFormat,
                             profile_name: str = None) -> bool:
        """Exécuter l'export HTML via service unifié"""
        # PHASE 6 CONSOLIDATION - Direct vers HtmlExportService
        if export_format == ExportFormat.HTML_BRANDS:
            result = HtmlExportService.generate_html_brands(data)
        elif export_format == ExportFormat.HTML_DETAILS:
            result = HtmlExportService.generate_html_details(data, profile_name=profile_name)
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

        if export_format == ExportFormat.HTML_BRANDS:
            # Compter les marques distinctes (col 1 = Fabricant)
            nb_marques = len(set(row[1] for row in data if len(row) > 1 and row[1]))
            self._add_to_history(f"HTML Marques: {nb_marques} marques exportées dans le presse-papier")
        else:
            # Détecter complet vs partiel : filtres de recherche actifs (col 2 = Réf Modèle,
            # col 3 = Réf Commerciale) ET/OU troncature liée à la limite de caractères HTML
            active_filters = self._get_active_column_filters()
            if 2 in active_filters:
                filter_scope = "Référence Modèle"
            elif 3 in active_filters:
                filter_scope = "Référence Commerciale"
            else:
                filter_scope = None

            strategy = HtmlExportService.last_strategy_used
            if strategy == 'ref_modele':
                truncation_note = "références modèle uniquement, limite de caractères atteinte"
            elif strategy == 'commercial_ref':
                truncation_note = "références commerciales uniquement, limite de caractères atteinte"
            else:
                truncation_note = None

            if filter_scope and truncation_note:
                scope = f"[partiel - {filter_scope} ; {truncation_note}]"
            elif filter_scope:
                scope = f"[partiel - {filter_scope}]"
            elif truncation_note:
                scope = f"[partiel - {truncation_note}]"
            else:
                scope = "[complet]"
            self._add_to_history(f"HTML Détails: {len(data)} résultats exportés dans le presse-papier {scope}")

        return True
    
    
    
    # ===== UTILITAIRES =====
    
    def _get_search_term(self) -> str:
        """Récupérer le terme de recherche actuel"""
        return self.main_window.search_input.text().strip()
    
    def _parse_search_term(self, search_term: str) -> Union[str, Dict]:
        """Parser le terme de recherche avec injection des flags des bannières actives.

        SOURCE UNIQUE DE VÉRITÉ : délègue à table_controller.build_effective_search_term,
        la MÊME méthode que celle utilisée pour remplir le tableau. L'export reproduit
        donc exactement le périmètre affiché (refs sœurs, prédécesseurs, équivalents,
        bypass). Ne JAMAIS recopier ces blocs ici : toute évolution du périmètre de
        recherche doit rester dans build_effective_search_term pour éviter la dérive
        (régression historique : le bloc "refs sœurs" n'avait jamais été propagé ici).
        """
        tc = getattr(self.main_window, 'table_controller', None)
        if tc is not None:
            return tc.build_effective_search_term(search_term)

        # Fallback si le contrôleur de tableau est indisponible : parsing brut
        if search_term and isinstance(search_term, str) and hasattr(self.main_window, 'search_service'):
            parsed = self.main_window.search_service.parse_advanced_search(search_term)
            if parsed:
                return parsed
        return search_term
    
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
        """Récupérer les données d'export en respectant les filtres colonnes actifs."""
        column_filters = self._get_active_column_filters()
        incomplete_filter = getattr(self.main_window, 'show_incomplete_only', False)
        return self.main_window.db_manager.get_export_data(
            search_data_term,
            column_filters=column_filters or None,
            incomplete_filter=incomplete_filter,
        )
    
    def _get_active_column_filters(self) -> Dict[int, str]:
        """Récupérer les filtres de colonnes actifs"""
        from ..ui.qt_imports import QComboBox
        
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