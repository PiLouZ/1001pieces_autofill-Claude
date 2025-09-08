"""
Service d'export unifié - Refactorisation Phase 1
Consolidation de ExportService et MainExportService

RESPONSABILITÉS UNIFIÉES :
- Export de base (CSV, EXCEL, JSON, HTML) sans interface utilisateur
- Export avec sélection de référence et interface utilisateur
- Gestion des recherches multiples
- Formatage HTML spécialisé

ARCHITECTURE :
- UnifiedExportService : Classe de base sans dépendances UI
- MainExportService : Extension avec fonctionnalités UI (hérite de UnifiedExportService)
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import csv
import json
from datetime import datetime
from PyQt5.QtWidgets import QMessageBox

from ..data.database_manager import DatabaseManager
from ..core.config import Config
from ..core.logger import app_logger
from .event_bus import event_bus

try:
    from openpyxl import Workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


class ExportFormat:
    """Formats d'export supportés"""
    CSV = "CSV"
    EXCEL = "EXCEL"
    JSON = "JSON"
    HTML_BRANDS = "HTML_BRANDS"
    HTML_DETAILS = "HTML_DETAILS"


class UnifiedExportService:
    """
    Service d'export unifié - Logique de base sans dépendances UI
    
    Responsabilités :
    - Export de base dans tous les formats
    - Préparation et formatage des données
    - Génération HTML spécialisée
    - Events bus pour notifications
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def export_search_results(self, search_term: str, 
                            export_format: str,
                            output_file: str,
                            include_pieces: bool = True,
                            custom_reference: Optional[str] = None) -> Dict[str, Any]:
        """
        Exporter les résultats d'une recherche (méthode de base)
        
        Args:
            search_term: Terme de recherche
            export_format: Format d'export (ExportFormat)
            output_file: Fichier de sortie
            include_pieces: Inclure les pièces dans l'export
            custom_reference: Référence personnalisée pour l'export
        """
        
        event_bus.emit('export.started', {
            'format': export_format,
            'search_term': search_term,
            'output_file': output_file
        })
        
        try:
            # Charger les données de recherche
            results = self.db_manager.load_data(search_term=search_term)
            
            if not results:
                return {
                    'success': False,
                    'error': 'Aucun résultat trouvé pour cette recherche',
                    'count': 0
                }
            
            # Préparer les données pour l'export
            export_data = self._prepare_export_data(results, include_pieces)
            
            # Exporter selon le format
            if export_format == ExportFormat.CSV:
                self._export_csv(export_data, output_file, custom_reference)
            elif export_format == ExportFormat.EXCEL:
                self._export_excel(export_data, output_file)
            elif export_format == ExportFormat.JSON:
                self._export_json(export_data, output_file)
            elif export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
                return self._export_html(results, export_format)
            else:
                raise ValueError(f"Format non supporté: {export_format}")
            
            result = {
                'success': True,
                'count': len(results),
                'format': export_format,
                'output_file': output_file
            }
            
            event_bus.emit('export.completed', result)
            return result
            
        except Exception as e:
            error_result = {
                'success': False,
                'error': str(e),
                'count': 0
            }
            
            event_bus.emit('export.error', error_result)
            return error_result
    
    def export_to_html(self, data: List[Tuple], export_format: str) -> str:
        """
        Exporter les données au format HTML
        
        Args:
            data: Liste des données (tuples avec id, manufacturer, ref_modele, commercial_ref...)
            export_format: Format HTML souhaité (HTML_BRANDS ou HTML_DETAILS)
            
        Returns:
            str: Code HTML généré
        """
        try:
            if export_format == ExportFormat.HTML_BRANDS:
                return self._generate_html_brands(data)
            elif export_format == ExportFormat.HTML_DETAILS:
                return self._generate_html_details(data)
            else:
                raise ValueError(f"Format d'export HTML non supporté: {export_format}")
                
        except Exception as e:
            app_logger.error(f"Erreur export HTML: {e}")
            raise
    
    def _prepare_export_data(self, results: List, include_pieces: bool) -> List[Dict]:
        """Préparer les données pour l'export"""
        export_data = []
        for result in results:
            # Adapter selon la structure des données reçues
            if isinstance(result, (list, tuple)):
                # Format tuple/list de la base de données
                data_dict = {
                    'id': result[0] if len(result) > 0 else '',
                    'manufacturer': result[1] if len(result) > 1 else '',
                    'ref_modele': result[2] if len(result) > 2 else '',
                    'commercial_ref': result[3] if len(result) > 3 else '',
                    # Ajouter d'autres champs selon nécessité
                }
            else:
                # Format dictionnaire
                data_dict = result
                
            export_data.append(data_dict)
        
        return export_data
    
    def _export_csv(self, data: List[Dict], output_file: str, custom_reference: Optional[str] = None):
        """Export au format CSV avec référence personnalisée optionnelle"""
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            if not data:
                return
                
            # Déterminer les en-têtes
            fieldnames = list(data[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in data:
                # Utiliser la référence personnalisée si fournie
                if custom_reference and 'commercial_ref' in row:
                    row = dict(row)  # Copie pour ne pas modifier l'original
                    row['commercial_ref'] = custom_reference
                writer.writerow(row)
    
    def _export_excel(self, data: List[Dict], output_file: str):
        """Export au format Excel"""
        if not EXCEL_AVAILABLE:
            raise ImportError("openpyxl n'est pas disponible pour l'export Excel")
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Export Data"
        
        if not data:
            wb.save(output_file)
            return
        
        # En-têtes
        headers = list(data[0].keys())
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        
        # Données
        for row_num, row_data in enumerate(data, 2):
            for col, header in enumerate(headers, 1):
                ws.cell(row=row_num, column=col, value=row_data.get(header, ''))
        
        wb.save(output_file)
    
    def _export_json(self, data: List[Dict], output_file: str):
        """Export au format JSON"""
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'count': len(data),
            'data': data
        }
        
        with open(output_file, 'w', encoding='utf-8') as jsonfile:
            json.dump(export_data, jsonfile, ensure_ascii=False, indent=2)
    
    def _export_html(self, data: List[Tuple], export_format: str) -> Dict[str, Any]:
        """Export HTML - retourne le contenu plutôt que l'écrire dans un fichier"""
        try:
            html_content = self.export_to_html(data, export_format)
            return {
                'success': True,
                'content': html_content,
                'count': len(data),
                'format': export_format
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'count': 0
            }
    
    def _generate_html_brands(self, data: List[Tuple]) -> str:
        """Générer les liens HTML vers les marques"""
        brands = set()
        
        for record in data:
            if len(record) >= 2:
                manufacturer = record[1]  # Index 1 = manufacturer
                if manufacturer and manufacturer.strip():
                    brands.add(manufacturer.strip())
        
        # Générer les liens HTML
        html_links = []
        for brand in sorted(brands):
            html_links.append(f'<a href="#{brand}">{brand}</a>')
        
        return ' '.join(html_links)
    
    def _generate_html_details(self, data: List[Tuple]) -> str:
        """Générer HTML détaillé avec références par marque"""
        brands_data = {}
        
        # Grouper par marque
        for record in data:
            if len(record) >= 4:
                manufacturer = record[1]  # Index 1 = manufacturer
                ref_modele = record[2]    # Index 2 = ref_modele
                commercial_ref = record[3] # Index 3 = commercial_ref
                
                if manufacturer and manufacturer.strip():
                    if manufacturer not in brands_data:
                        brands_data[manufacturer] = []
                    brands_data[manufacturer].append({
                        'ref_modele': ref_modele or '',
                        'commercial_ref': commercial_ref or ''
                    })
        
        # Générer le HTML
        html_parts = []
        for brand in sorted(brands_data.keys()):
            html_parts.append(f'<h3 id="{brand}">{brand}</h3>')
            html_parts.append('<ul>')
            
            for item in brands_data[brand]:
                ref_display = item['ref_modele']
                if item['commercial_ref']:
                    ref_display += f" ({item['commercial_ref']})"
                html_parts.append(f'<li>{ref_display}</li>')
            
            html_parts.append('</ul>')
        
        return '\n'.join(html_parts)


class MainExportService(UnifiedExportService):
    """
    Service d'export avec interface utilisateur - Étend UnifiedExportService
    
    Responsabilités additionnelles :
    - Gestion des dialogues de sélection de référence
    - Validation avec interface utilisateur
    - Traitement des recherches multiples
    - Intégration avec les services UI de l'application
    """
    
    def __init__(self, main_window):
        super().__init__(main_window.db_manager)
        self.main_window = main_window
    
    def export_data(self, export_format: str) -> None:
        """
        Export avec sélection de référence et validation UI
        
        Args:
            export_format: Format d'export désiré (CSV, HTML_BRANDS, HTML_DETAILS)
        """
        search_term = self.main_window.search_input.text().strip()
        if not search_term:
            QMessageBox.information(
                self.main_window, 
                "Information", 
                "Veuillez entrer un terme de recherche"
            )
            return
        
        try:
            # Détecter si c'est une recherche multiple OR pour proposer sélection de référence
            parsed_term = self.main_window.advanced_search_service.get_current_search_term_with_fallback(self.main_window) or search_term
            
            # Gérer différemment selon le format d'export
            if export_format == ExportFormat.CSV:
                export_data_term, export_reference = self._handle_csv_reference_selection(
                    search_term, parsed_term
                )
                if export_reference is None:
                    return  # Utilisateur a annulé
                
                # Export CSV avec référence personnalisée
                from PyQt5.QtWidgets import QFileDialog
                filename, _ = QFileDialog.getSaveFileName(
                    self.main_window,
                    "Sauvegarder l'export CSV",
                    f"{export_reference}.csv",
                    "Fichiers CSV (*.csv)"
                )
                
                if filename:
                    result = self.export_search_results(
                        search_term, ExportFormat.CSV, filename, 
                        custom_reference=export_reference
                    )
                    
                    if result['success']:
                        QMessageBox.information(
                            self.main_window,
                            "Export réussi",
                            f"Export CSV terminé : {result['count']} éléments exportés"
                        )
                    else:
                        QMessageBox.critical(
                            self.main_window,
                            "Erreur d'export",
                            f"Erreur : {result['error']}"
                        )
                        
            else:
                # Pour HTML : pas de demande de confirmation, utiliser directement tous les résultats
                export_data_term = parsed_term if isinstance(parsed_term, dict) else search_term
                export_reference = "recherche_multiple"  # Nom générique pour HTML
                
                # Valider que la recherche a des résultats
                if not self._validate_search_results(search_term):
                    return
                
                # Export HTML via service unifié
                result = self.export_search_results(
                    search_term, export_format, "", 
                    custom_reference=export_reference
                )
                
                if result['success']:
                    # Afficher le contenu HTML dans le presse-papiers ou une fenêtre
                    self._handle_html_export_result(result)
                else:
                    QMessageBox.critical(
                        self.main_window,
                        "Erreur d'export",
                        f"Erreur : {result['error']}"
                    )
            
        except Exception as e:
            QMessageBox.critical(
                self.main_window, 
                "Erreur", 
                f"Erreur lors de l'export: {e}"
            )
    
    def _handle_csv_reference_selection(self, search_term: str, parsed_term: Union[str, Dict]) -> tuple:
        """
        Gérer la sélection de référence pour les exports CSV
        
        Args:
            search_term: Terme de recherche brut
            parsed_term: Terme de recherche parsé
            
        Returns:
            tuple: (export_data_term, export_reference) ou (None, None) si annulé
        """
        if isinstance(parsed_term, dict) and parsed_term.get('type') == 'or':
            # Recherche multiple OR
            return self._handle_multiple_references(parsed_term)
        else:
            # Recherche simple - demander confirmation de la référence
            if hasattr(self.main_window, 'dialog_service'):
                selected_reference = self.main_window.dialog_service.show_reference_selection_dialog(
                    "Référence pour l'export CSV",
                    f"Référence détectée : {search_term}\n"
                    f"Confirmez ou modifiez la référence à utiliser pour l'export :",
                    self.main_window.search_service.extract_first_term(search_term)
                )
            else:
                # Fallback simple si pas de dialog service
                from PyQt5.QtWidgets import QInputDialog
                selected_reference, ok = QInputDialog.getText(
                    self.main_window,
                    "Référence pour l'export CSV",
                    f"Référence détectée : {search_term}\nConfirmez ou modifiez :",
                    text=search_term
                )
                if not ok:
                    selected_reference = None
            
            if not selected_reference:
                return None, None
                
            return search_term, selected_reference
    
    def _handle_multiple_references(self, parsed_term: Dict) -> tuple:
        """
        Gérer les références multiples pour export CSV
        
        Args:
            parsed_term: Dictionnaire de recherche parsée
            
        Returns:
            tuple: (export_data_term, export_reference) ou (None, None) si annulé
        """
        # Extraire tous les termes de la recherche OR
        terms = []
        for group in parsed_term.get('groups', []):
            terms.extend(group.get('terms', []))
        
        if terms:
            # Demander à l'utilisateur de choisir une référence
            if hasattr(self.main_window, 'dialog_service'):
                selected_reference = self.main_window.dialog_service.show_reference_selection_dialog(
                    "Référence pour l'export CSV",
                    f"Recherche multiple détectée ({len(terms)} références).\n"
                    f"Termes: {', '.join(terms)}\n"
                    f"Choisissez la référence à utiliser pour l'export :",
                    self.main_window.search_service.extract_first_term(terms[0]) if terms else ""
                )
            else:
                # Fallback simple
                from PyQt5.QtWidgets import QInputDialog
                selected_reference, ok = QInputDialog.getText(
                    self.main_window,
                    "Référence pour l'export CSV",
                    f"Recherche multiple détectée.\nChoisissez la référence :",
                    text=terms[0] if terms else ""
                )
                if not ok:
                    selected_reference = None
            
            if not selected_reference:
                return None, None
            
            return parsed_term, selected_reference
        else:
            return None, None
    
    def _validate_search_results(self, search_term: str) -> bool:
        """
        Valider que la recherche a des résultats
        
        Args:
            search_term: Terme de recherche à valider
            
        Returns:
            bool: True si la recherche a des résultats
        """
        try:
            results = self.db_manager.load_data(search_term=search_term)
            if not results:
                QMessageBox.information(
                    self.main_window,
                    "Aucun résultat",
                    "Aucun résultat trouvé pour cette recherche"
                )
                return False
            return True
        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Erreur de validation",
                f"Erreur lors de la validation : {e}"
            )
            return False
    
    def _handle_html_export_result(self, result: Dict[str, Any]):
        """Gérer l'affichage du résultat d'export HTML"""
        if 'content' in result:
            # Copier dans le presse-papiers
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(result['content'])
            
            QMessageBox.information(
                self.main_window,
                "Export HTML réussi",
                f"Export HTML terminé : {result['count']} éléments traités\n"
                f"Le contenu HTML a été copié dans le presse-papiers."
            )