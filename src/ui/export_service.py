"""
Service d'export principal - Phase 2.11
Extrait de main_refactored.py pour centraliser la logique d'export avec référence personnalisée

Responsabilités:
- Export principal avec sélection de référence
- Gestion des recherches multiples et sélection utilisateur
- Export CSV avec format exact spécifié
- Export HTML avec référence personnalisée
- Interface standardisée pour tous les exports avec confirmation
"""

import csv
import os
from typing import Dict, Any, Optional, List, Union
from PyQt5.QtWidgets import QApplication

from ..services.export_service import ExportFormat
from src.core.logger import app_logger


class MainExportService:
    """
    Service spécialisé pour les exports avec sélection de référence
    
    Responsabilités:
    - Export principal avec détection des recherches multiples
    - Dialogue de sélection/confirmation de référence utilisateur
    - Export CSV avec format exact standardisé
    - Export HTML via service existant avec référence personnalisée
    - Intégration avec DatabaseManager pour récupération des données
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def export_data(self, export_format: ExportFormat) -> None:
        """
        Export avec sélection de référence (comportement original)
        
        Args:
            export_format: Format d'export désiré (CSV, HTML_BRANDS, HTML_DETAILS)
        """
        search_term = self.main_window.search_input.text().strip()
        if not search_term:
            self.main_window.user_interaction_service.add_to_history("⚠️ Erreur export: Aucun terme de recherche saisi")
            return
        
        try:
            # Détecter si c'est une recherche multiple OR pour auto-extraire la première référence
            parsed_term = self.main_window.advanced_search_service.get_current_search_term_with_fallback(self.main_window) or search_term
            
            # Extraire automatiquement la première référence sans dialogue
            export_reference = self._extract_reference_automatically(search_term, parsed_term)
            export_data_term = parsed_term if isinstance(parsed_term, dict) else search_term
            
            # Valider que la recherche a des résultats
            if not self._validate_search_results(search_term):
                return
            
            # Exporter directement sans confirmation
            self._export_with_custom_reference(export_data_term, export_reference, export_format)
            
        except Exception as e:
            self.main_window.user_interaction_service.add_to_history(f"❌ Erreur export: {str(e)}")
    
    def _extract_reference_automatically(self, search_term: str, parsed_term: Union[str, Dict]) -> str:
        """
        Extraire automatiquement une référence sans dialogue utilisateur
        
        Args:
            search_term: Terme de recherche original
            parsed_term: Terme parsé par le service de recherche avancée
            
        Returns:
            str: Référence extraite automatiquement
        """
        if isinstance(parsed_term, dict) and parsed_term.get('type') == 'or':
            # Recherche multiple OR - utiliser le premier terme
            terms = []
            for group in parsed_term.get('groups', []):
                terms.extend(group.get('terms', []))
            
            if terms:
                return self.main_window.search_service.extract_first_term(terms[0])
            else:
                return self.main_window.search_service.extract_first_term(search_term)
        else:
            # Recherche simple - utiliser le terme directement
            return self.main_window.search_service.extract_first_term(search_term)
    
    
    
    def _validate_search_results(self, search_term: str) -> bool:
        """
        Valider que la recherche a des résultats
        
        Args:
            search_term: Terme de recherche
            
        Returns:
            bool: True si des résultats existent, False sinon
        """
        try:
            # Charger les résultats pour vérification - utiliser la même logique que TableController
            if search_term and ('&&' in search_term or '||' in search_term):
                # Recherche avancée avec opérateurs
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
                self.main_window.user_interaction_service.add_to_history("⚠️ Export annulé: Aucun résultat trouvé pour cette recherche")
                return False
            
            return True
        except Exception as e:
            app_logger.error(f"Erreur validation résultats de recherche: {e}")
            return False
    
    def _export_with_custom_reference(self, search_data_term: Union[str, Dict], 
                                    reference_for_file: str, export_format: ExportFormat) -> bool:
        """
        Exporter avec tous les résultats mais utiliser une référence spécifique pour le nom et la première colonne
        
        Args:
            search_data_term: Terme de recherche (simple ou complexe)
            reference_for_file: Référence à utiliser pour le fichier
            export_format: Format d'export
            
        Returns:
            bool: True si succès, False sinon
        """
        try:
            # Récupérer toutes les données avec la recherche complète
            if isinstance(search_data_term, dict):
                # Recherche complexe - utiliser get_export_data avec fallback
                data = self.main_window.db_manager.get_export_data(search_data_term)
            else:
                # Recherche simple
                data = self.main_window.db_manager.get_export_data(search_data_term)
            
            if not data:
                raise Exception(f"Aucune donnée trouvée pour la recherche")
            
            # Exporter selon le format
            if export_format == ExportFormat.CSV:
                return self._handle_csv_export(data, reference_for_file)
            elif export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
                return self._handle_html_export(data, reference_for_file, export_format)
            else:
                raise Exception(f"Format d'export {export_format} non supporté avec référence personnalisée")
                
        except Exception as e:
            raise Exception(f"Erreur lors de l'export personnalisé: {e}")
    
    def _handle_csv_export(self, data: List, reference_for_file: str) -> bool:
        """
        Gérer l'export CSV avec référence personnalisée
        
        Args:
            data: Données à exporter
            reference_for_file: Référence pour le fichier
            
        Returns:
            bool: True si succès
        """
        filename = f"{reference_for_file}_everyParts.csv"
        success = self._export_csv_with_reference(data, filename, reference_for_file)
        if success:
            self.main_window.user_interaction_service.add_to_history(f"Export CSV: {filename} ({len(data)} lignes)")
        return success
    
    def _handle_html_export(self, data: List, reference_for_file: str, export_format: ExportFormat) -> bool:
        """
        Gérer l'export HTML avec référence personnalisée
        
        Args:
            data: Données à exporter
            reference_for_file: Référence pour le fichier
            export_format: Format HTML spécifique
            
        Returns:
            bool: True si succès
        """
        success = self._export_html_with_reference(data, reference_for_file, export_format)
        if success:
            format_name = "HTML Marques" if export_format == ExportFormat.HTML_BRANDS else "HTML Détails"
            self.main_window.user_interaction_service.add_to_history(f"Export {format_name}: {len(data)} résultats copiés")
        return success
    
    def _export_csv_with_reference(self, data: List, filename: str, reference: str) -> bool:
        """
        Exporter en CSV avec format exact spécifié
        
        Args:
            data: Données à exporter
            filename: Nom du fichier
            reference: Référence pour la première colonne
            
        Returns:
            bool: True si succès
        """
        try:
            # Chemin vers le Bureau
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            full_path = os.path.join(desktop_path, filename)
            
            with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                # En-têtes exacts selon spécification
                headers = ['product', 'type', 'manufacturer', 'modele_name', 'reference_modele', 'commercial_reference']
                writer.writerow(headers)
                
                # Données selon le format spécifié
                for row in data:
                    # get_export_data structure: [type, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece]
                    # Indexes:                     0     1            2           3               4          5
                    
                    type_val = row[0] if len(row) > 0 else ''
                    manufacturer_val = row[1] if len(row) > 1 else ''
                    ref_modele_val = row[2] if len(row) > 2 else ''
                    commercial_ref_val = row[3] if len(row) > 3 else ''
                    
                    # modele_name = "Référence Modèle - Référence Commerciale"
                    modele_name = f"{ref_modele_val} - {commercial_ref_val}".strip(' -')
                    
                    csv_row = [
                        reference,                    # product: Référence confirmée
                        type_val,                     # type: Type  
                        manufacturer_val,             # manufacturer: Fabricant
                        modele_name,                  # modele_name: "Référence Modèle - Référence Commerciale"
                        ref_modele_val,               # reference_modele: Référence Modèle
                        commercial_ref_val            # commercial_reference: Référence Commerciale
                    ]
                    writer.writerow(csv_row)
            
            return True
            
        except Exception as e:
            raise Exception(f"Erreur export CSV: {e}")
    
    def _export_html_with_reference(self, data: List, reference: str, export_format: ExportFormat) -> bool:
        """
        Exporter en HTML avec référence personnalisée
        
        Args:
            data: Données à exporter
            reference: Référence personnalisée
            export_format: Format HTML spécifique
            
        Returns:
            bool: True si succès
        """
        try:
            # Utiliser le service d'export principal des services
            from ..services.export_service import ExportService
            export_service = ExportService(self.main_window.db_manager)
            result = export_service.export_to_html(data, export_format)
            
            # Copier dans le presse-papiers
            QApplication.clipboard().setText(result)
            
            return True
            
        except Exception as e:
            raise Exception(f"Erreur export HTML: {e}")