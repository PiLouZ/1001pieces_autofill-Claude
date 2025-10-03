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
from ..core.constants import ExportFormat, ExportError
from .event_bus import event_bus
from .html_export_service import HtmlExportService
from .base_service import BaseService
from ..utils.error_handler import handle_export_errors

try:
    from openpyxl import Workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

class ExportService(BaseService):
    """Service dédié aux opérations d'export"""
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
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

        return self._safe_export_search_results_core(search_term, export_format, output_file, include_pieces)

    @handle_export_errors()
    def _safe_export_search_results_core(self, search_term: str, export_format: str, output_file: str, include_pieces: bool) -> Dict[str, Any]:
        """Noyau sécurisé pour l'export des résultats de recherche"""
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
    
    # Phase 2.3: Ajouter les méthodes HTML factorées ici
    @handle_export_errors()
    def export_to_html(self, data: List[Tuple], export_format: str) -> str:
        """
        Exporter les données au format HTML

        Args:
            data: Liste des données (tuples avec id, manufacturer, ref_modele, commercial_ref...)
            export_format: Format HTML souhaité (HTML_BRANDS ou HTML_DETAILS)

        Returns:
            str: Code HTML généré
        """
        if export_format == ExportFormat.HTML_BRANDS:
            return self._generate_html_brands(data)
        elif export_format == ExportFormat.HTML_DETAILS:
            return self._generate_html_details(data)
        else:
            raise ValueError(f"Format d'export HTML non supporté: {export_format}")
    
    def _generate_html_brands(self, data: List[Tuple]) -> str:
        """Générer les liens HTML vers les marques - DÉLÉGUÉ AU SERVICE CENTRALISÉ"""
        return HtmlExportService.generate_html_brands(data)
    
    def _generate_html_details(self, data: List[Tuple]) -> str:
        """Générer HTML détaillé avec références par marque - DÉLÉGUÉ AU SERVICE CENTRALISÉ"""
        html_output = HtmlExportService.generate_html_details(data)
        
        # Conserver la logique _last_export_info pour compatibilité
        char_count = HtmlExportService.count_non_html_chars(html_output) 
        self._last_export_info = {
            'format_used': 'optimisé',
            'char_count': char_count,
            'char_limit': HtmlExportService.CHAR_LIMIT,
            'description': 'Format optimisé automatiquement'
        }
        
        return html_output

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
                pieces_data = self._safe_get_pieces_for_device(row[0])
                row_data['pieces'] = pieces_data['pieces']
                row_data['pieces_count'] = pieces_data['count']

            export_data.append(row_data)

        return export_data

    @handle_export_errors()
    def _safe_get_pieces_for_device(self, device_id: int) -> Dict[str, Any]:
        """Récupérer les pièces pour un appareil de manière sécurisée"""
        pieces = self.db_manager.get_pieces_for_device(device_id)
        return {'pieces': pieces, 'count': len(pieces)}
    
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