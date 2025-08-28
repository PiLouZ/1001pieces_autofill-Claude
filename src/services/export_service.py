"""
Export Service - Phase 4 Architecture Refactoring
Sépare la logique d'export de l'interface utilisateur
"""

from typing import List, Dict, Any, Optional
import csv
import json
from datetime import datetime
from ..data.database_manager import DatabaseManager
from ..core.config import Config
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
                'format': export_format,
                'search_term': search_term
            }
            event_bus.emit('export.error', error_result)
            return error_result
    
    def _prepare_export_data(self, results: List, include_pieces: bool = True) -> List[Dict[str, Any]]:
        """Préparer les données pour l'export"""
        export_data = []
        
        for result in results:
            # result = (id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes, pieces_count)
            row_data = {
                'ID': result[0],
                'Type': result[1] or '',
                'Fabricant': result[2] or '',
                'Référence Modèle': result[3] or '',
                'Référence Commerciale': result[4] or '', 
                'Autre Référence': result[5] or '',
                'Catégorie': result[6] or '',
                'Notes': result[7] or '',
                'Nb Pièces': result[8] if len(result) > 8 else 0
            }
            
            # Ajouter les pièces associées si demandé
            if include_pieces and len(result) > 8 and result[8] > 0:
                try:
                    pieces = self.db_manager.execute_query("""
                        SELECT p.ref_piece, p.description
                        FROM pieces p
                        JOIN piece_associations pa ON p.id = pa.piece_id  
                        WHERE pa.appareil_id = ?
                        ORDER BY p.ref_piece
                    """, [result[0]])
                    
                    pieces_list = []
                    for piece in pieces:
                        piece_str = piece[0]
                        if piece[1]:  # Description existe
                            piece_str += f" ({piece[1]})"
                        pieces_list.append(piece_str)
                    
                    row_data['Pièces Associées'] = ' | '.join(pieces_list)
                except Exception as e:
                    print(f"⚠️ Erreur chargement pièces pour appareil {result[0]}: {e}")
                    row_data['Pièces Associées'] = 'Erreur chargement'
            
            export_data.append(row_data)
        
        return export_data
    
    def _export_csv(self, data: List[Dict[str, Any]], output_file: str) -> None:
        """Export au format CSV"""
        if not data:
            return
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = list(data[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in data:
                writer.writerow(row)
    
    def _export_excel(self, data: List[Dict[str, Any]], output_file: str) -> None:
        """Export au format Excel"""
        if not EXCEL_AVAILABLE:
            raise ImportError("openpyxl n'est pas installé pour l'export Excel")
        
        if not data:
            return
        
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Export Résultats"
        
        # En-têtes
        fieldnames = list(data[0].keys())
        for col, header in enumerate(fieldnames, 1):
            worksheet.cell(row=1, column=col, value=header)
        
        # Données
        for row_idx, row_data in enumerate(data, 2):
            for col_idx, field in enumerate(fieldnames, 1):
                worksheet.cell(row=row_idx, column=col_idx, value=row_data.get(field, ''))
        
        # Auto-ajuster les colonnes
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        workbook.save(output_file)
    
    def _export_json(self, data: List[Dict[str, Any]], output_file: str) -> None:
        """Export au format JSON"""
        export_obj = {
            'export_date': datetime.now().isoformat(),
            'total_records': len(data),
            'data': data
        }
        
        with open(output_file, 'w', encoding='utf-8') as jsonfile:
            json.dump(export_obj, jsonfile, indent=2, ensure_ascii=False)
    
    def get_supported_formats(self) -> List[str]:
        """Obtenir la liste des formats supportés"""
        formats = [ExportFormat.CSV, ExportFormat.JSON]
        if EXCEL_AVAILABLE:
            formats.append(ExportFormat.EXCEL)
        return formats