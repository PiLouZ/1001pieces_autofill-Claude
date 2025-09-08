"""
Export Service - Phase 4 Architecture Refactoring
Sépare la logique d'export de l'interface utilisateur
"""

from typing import List, Dict, Any, Optional, Tuple
import csv
import json
from datetime import datetime
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


class ExportService:
    """Service dédié aux opérations d'export"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def export_search_results(self, search_term: str, 
                            export_format: str,
                            output_file: str,
                            include_pieces: bool = True) -> Dict[str, Any]:
        """Exporter les résultats d'une recherche"""
        
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
                self._export_csv(export_data, output_file)
            elif export_format == ExportFormat.EXCEL:
                self._export_excel(export_data, output_file)
            elif export_format == ExportFormat.JSON:
                self._export_json(export_data, output_file)
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
    
    # Phase 2.3: Ajouter les méthodes HTML factorées ici
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
        """Générer HTML détaillé avec références par marque et gestion de la limite de caractères"""
        from collections import defaultdict
        
        # Limite de caractères pour le site web
        CHAR_LIMIT = 195000
        
        # Grouper par marque
        brands_data = defaultdict(list)
        for record in data:
            if len(record) >= 4:
                manufacturer = record[1]  # Index 1 = manufacturer
                ref_modele = record[2]    # Index 2 = ref_modele
                commercial_ref = record[3] # Index 3 = commercial_ref
                
                if manufacturer and manufacturer.strip():
                    brands_data[manufacturer].append({
                        'ref_modele': ref_modele or '',
                        'commercial_ref': commercial_ref or ''
                    })
        
        # Fonction pour calculer les caractères non-HTML
        def count_non_html_chars(html_content):
            import re
            # Supprimer toutes les balises HTML
            text_only = re.sub(r'<[^>]+>', '', html_content)
            # Remplacer les entités HTML courantes
            text_only = text_only.replace('&nbsp;', ' ')
            text_only = text_only.replace('&amp;', '&')
            text_only = text_only.replace('&lt;', '<')
            text_only = text_only.replace('&gt;', '>')
            return len(text_only)
        
        # Essai 1: Format complet (ref_modele - commercial_ref)
        html_output = self._generate_html_content(brands_data, 'full')
        char_count = count_non_html_chars(html_output)
        if char_count <= CHAR_LIMIT:
            # Stocker les informations pour le message utilisateur
            self._last_export_info = {
                'format_used': 'complet',
                'char_count': char_count,
                'char_limit': CHAR_LIMIT,
                'description': 'Référence Modèle - Référence Commerciale'
            }
            return html_output
            
        # Essai 2: Seulement ref_modele
        html_output = self._generate_html_content(brands_data, 'ref_modele')
        char_count = count_non_html_chars(html_output)
        if char_count <= CHAR_LIMIT:
            # Stocker les informations pour le message utilisateur
            self._last_export_info = {
                'format_used': 'ref_modele',
                'char_count': char_count,
                'char_limit': CHAR_LIMIT,
                'description': 'Référence Modèle uniquement'
            }
            return html_output
            
        # Essai 3: Seulement commercial_ref (sans doublons)
        html_output = self._generate_html_content(brands_data, 'commercial_ref')
        char_count = count_non_html_chars(html_output)
        # Stocker les informations pour le message utilisateur
        self._last_export_info = {
            'format_used': 'commercial_ref',
            'char_count': char_count,
            'char_limit': CHAR_LIMIT,
            'description': 'Référence Commerciale uniquement'
        }
        return html_output
    
    def _generate_html_content(self, brands_data: dict, format_type: str) -> str:
        """Générer le contenu HTML selon le format spécifié"""
        html_parts = []
        
        for brand in sorted(brands_data.keys()):
            models_info = brands_data[brand]
            html_parts.append(f'<div id="{brand}"><b><u>{brand}</u></b></div>')
            
            # Préparer les modèles selon le format
            models_to_display = []
            
            for model_info in models_info:
                ref_modele = model_info['ref_modele']
                commercial_ref = model_info['commercial_ref']
                
                if format_type == 'full':
                    # Format complet: ref_modele - commercial_ref
                    modele_complet = f"{ref_modele} - {commercial_ref}".strip(' -')
                    if modele_complet and modele_complet != ' - ':
                        models_to_display.append(modele_complet)
                        
                elif format_type == 'ref_modele':
                    # Seulement ref_modele
                    if ref_modele and ref_modele.strip():
                        models_to_display.append(ref_modele.strip())
                        
                elif format_type == 'commercial_ref':
                    # Seulement commercial_ref
                    if commercial_ref and commercial_ref.strip():
                        models_to_display.append(commercial_ref.strip())
            
            # Ajouter les modèles (sans doublons)
            for model in sorted(set(models_to_display)):
                html_parts.append(f'<div>{model}</div>')
            
            html_parts.append('<div>&nbsp;</div>')
        
        # Retirer le dernier espace
        if html_parts and html_parts[-1] == '<div>&nbsp;</div>':
            html_parts.pop()
        
        return '\n'.join(html_parts)
    
    def get_last_export_info(self):
        """Récupérer les informations du dernier export HTML détails"""
        return getattr(self, '_last_export_info', None)
    
    def _format_reference_text(self, ref_modele: str, commercial_ref: str) -> str:
        """Formater le texte d'une référence"""
        if ref_modele and commercial_ref:
            return f"{ref_modele} - {commercial_ref}"
        return ref_modele or commercial_ref or ""
    
    def _prepare_export_data(self, results: List[tuple], include_pieces: bool = True) -> List[Dict[str, Any]]:
        """Préparer les données pour l'export"""
        export_data = []
        
        for row in results:
            # Structure de base pour les appareils
            row_data = {
                'id': row[0],
                'manufacturer': row[1],
                'ref_modele': row[2],
                'commercial_ref': row[3],
                'type': row[4],
                'other_ref': row[5] if len(row) > 5 else '',
                'notes': row[6] if len(row) > 6 else ''
            }
            
            # Ajouter les pièces si demandé
            if include_pieces:
                try:
                    pieces = self.db_manager.get_pieces_for_device(row[0])
                    row_data['pieces'] = pieces
                    row_data['pieces_count'] = len(pieces)
                except Exception as e:
                    app_logger.error(f"Erreur récupération pièces pour appareil {row[0]}: {e}")
                    row_data['pieces'] = []
                    row_data['pieces_count'] = 0
            
            export_data.append(row_data)
        
        return export_data
    
    def _export_csv(self, data: List[Dict[str, Any]], output_file: str):
        """Export CSV"""
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            if not data:
                return
            
            # Headers de base
            headers = ['id', 'manufacturer', 'ref_modele', 'commercial_ref', 'type', 'other_ref', 'notes']
            
            # Ajouter headers pour pièces si présentes
            if 'pieces' in data[0]:
                headers.extend(['pieces_count', 'pieces_list'])
            
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for row in data:
                # Préparer la ligne d'export
                export_row = {k: v for k, v in row.items() if k in headers}
                
                # Formater la liste des pièces
                if 'pieces' in row:
                    export_row['pieces_list'] = '; '.join([p.get('ref_piece', '') for p in row['pieces']])
                
                writer.writerow(export_row)
    
    def _export_excel(self, data: List[Dict[str, Any]], output_file: str):
        """Export Excel"""
        if not EXCEL_AVAILABLE:
            raise ImportError("openpyxl n'est pas installé. Impossible d'exporter en Excel.")
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Export"
        
        if not data:
            wb.save(output_file)
            return
        
        # Headers
        headers = ['ID', 'Fabricant', 'Réf. Modèle', 'Réf. Commerciale', 'Type', 'Autre Réf.', 'Notes']
        if 'pieces' in data[0]:
            headers.extend(['Nb Pièces', 'Liste Pièces'])
        
        # Écrire les headers
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        
        # Écrire les données
        for row_idx, row_data in enumerate(data, 2):
            ws.cell(row=row_idx, column=1, value=row_data.get('id'))
            ws.cell(row=row_idx, column=2, value=row_data.get('manufacturer'))
            ws.cell(row=row_idx, column=3, value=row_data.get('ref_modele'))
            ws.cell(row=row_idx, column=4, value=row_data.get('commercial_ref'))
            ws.cell(row=row_idx, column=5, value=row_data.get('type'))
            ws.cell(row=row_idx, column=6, value=row_data.get('other_ref'))
            ws.cell(row=row_idx, column=7, value=row_data.get('notes'))
            
            if 'pieces' in row_data:
                ws.cell(row=row_idx, column=8, value=row_data.get('pieces_count', 0))
                pieces_list = '; '.join([p.get('ref_piece', '') for p in row_data.get('pieces', [])])
                ws.cell(row=row_idx, column=9, value=pieces_list)
        
        wb.save(output_file)
    
    def _export_json(self, data: List[Dict[str, Any]], output_file: str):
        """Export JSON"""
        export_info = {
            'export_date': datetime.now().isoformat(),
            'format': 'json',
            'count': len(data),
            'data': data
        }
        
        with open(output_file, 'w', encoding='utf-8') as jsonfile:
            json.dump(export_info, jsonfile, indent=2, ensure_ascii=False)