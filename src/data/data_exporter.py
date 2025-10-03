"""
Exporteur de données pour l'application de gestion d'appareils
"""

import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config
from src.core.constants import ExportFormat, ExportError
from src.services.html_export_service import HtmlExportService
from src.utils.error_handler import handle_export_errors

class DataExporter:
    """Classe pour gérer tous les exports de données"""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.export_stats = {
            'total_exports': 0,
            'successful_exports': 0,
            'failed_exports': 0,
            'last_export_time': None
        }
    
    @handle_export_errors(title="Erreur export résultats recherche")
    def export_search_results(self, search_term: str, export_format: ExportFormat,
                            filename: Optional[str] = None,
                            column_filters: Optional[Dict[int, str]] = None,
                            incomplete_filter: bool = False) -> str:
        """Exporter les résultats de recherche dans le format spécifié"""
        if not self.db_manager:
            raise ExportError("Gestionnaire de base de données non initialisé")

        # Vérifier que le terme de recherche n'est pas vide (chaîne ou objet)
        if isinstance(search_term, str) and not search_term.strip():
            raise ExportError("Terme de recherche requis pour l'export")
        elif not search_term:
            raise ExportError("Terme de recherche requis pour l'export")

        # Récupérer les données avec les mêmes filtres que l'affichage
        data = self.db_manager.get_export_data(search_term, column_filters, incomplete_filter)

        if not data:
            raise ExportError(f"Aucune donnée trouvée pour le terme: {search_term}")

        # Générer le nom de fichier si non fourni
        if not filename:
            filename = self._generate_filename(search_term, export_format)

        # Exporter selon le format
        if export_format == ExportFormat.CSV:
            result = self._export_to_csv(data, filename, search_term)
        elif export_format == ExportFormat.JSON:
            result = self._export_to_json(data, filename, search_term)
        elif export_format == ExportFormat.HTML_BRANDS:
            result = self._export_html_brands(data, search_term)
        elif export_format == ExportFormat.HTML_DETAILS:
            result = self._export_html_details(data, search_term)
        elif export_format == ExportFormat.XML:
            result = self._export_to_xml(data, filename, search_term)
        else:
            raise ExportError(f"Format d'export non supporté: {export_format}")

        # Mettre à jour les statistiques
        self._update_export_stats(True)

        return result
    
    @handle_export_errors(title="Erreur export CSV")
    def _export_to_csv(self, data: List[Tuple], filename: str, search_term: str) -> str:
        """Exporter vers CSV"""
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')

            # En-têtes
            headers = [
                'product',
                'type',
                'manufacturer',
                'modele_name',
                'reference_modele',
                'commercial_reference'
            ]
            writer.writerow(headers)

            # Données
            for record in data:
                type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record
                modele_complet = f"{ref_modele or ''} - {commercial_ref or ''}".strip(' -')

                writer.writerow([
                    ref_piece or search_term,
                    type_app or '',
                    manufacturer or '',
                    modele_complet,
                    ref_modele or '',
                    commercial_ref or ''
                ])

        return f"Fichier CSV créé: {filename}"
    
    @handle_export_errors(title="Erreur export JSON")
    def _export_to_json(self, data: List[Tuple], filename: str, search_term: str) -> str:
        """Exporter vers JSON"""
        json_data = {
            'export_info': {
                'search_term': search_term,
                'export_date': datetime.now().isoformat(),
                'total_records': len(data)
            },
            'appareils': []
        }

        for record in data:
            type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record

            appareil = {
                'type': type_app or '',
                'manufacturer': manufacturer or '',
                'ref_modele': ref_modele or '',
                'commercial_ref': commercial_ref or '',
                'other_ref': other_ref or '',
                'pieces': [ref_piece] if ref_piece else []
            }

            json_data['appareils'].append(appareil)

        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)

        return f"Fichier JSON créé: {filename}"
    
    @handle_export_errors(title="Erreur export HTML marques")
    def _export_html_brands(self, data: List[Tuple], search_term: str) -> str:
        """Exporter les marques en HTML - DÉLÉGUÉ AU SERVICE CENTRALISÉ"""
        return HtmlExportService.generate_html_brands(data)
    
    @handle_export_errors(title="Erreur export HTML détails")
    def _export_html_details(self, data: List[Tuple], search_term: str) -> str:
        """Exporter les détails en HTML - DÉLÉGUÉ AU SERVICE CENTRALISÉ"""
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

    @handle_export_errors(title="Erreur export XML")
    def _export_to_xml(self, data: List[Tuple], filename: str, search_term: str) -> str:
        """Exporter vers XML"""
        xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_content.append('<export>')
        xml_content.append(f'  <search_term>{search_term}</search_term>')
        xml_content.append(f'  <export_date>{datetime.now().isoformat()}</export_date>')
        xml_content.append(f'  <total_records>{len(data)}</total_records>')
        xml_content.append('  <appareils>')

        for record in data:
            type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record

            xml_content.append('    <appareil>')
            xml_content.append(f'      <type>{self._escape_xml(type_app or "")}</type>')
            xml_content.append(f'      <manufacturer>{self._escape_xml(manufacturer or "")}</manufacturer>')
            xml_content.append(f'      <ref_modele>{self._escape_xml(ref_modele or "")}</ref_modele>')
            xml_content.append(f'      <commercial_ref>{self._escape_xml(commercial_ref or "")}</commercial_ref>')
            xml_content.append(f'      <other_ref>{self._escape_xml(other_ref or "")}</other_ref>')
            if ref_piece:
                xml_content.append(f'      <ref_piece>{self._escape_xml(ref_piece)}</ref_piece>')
            xml_content.append('    </appareil>')

        xml_content.append('  </appareils>')
        xml_content.append('</export>')

        with open(filename, 'w', encoding='utf-8') as xmlfile:
            xmlfile.write('\n'.join(xml_content))

        return f"Fichier XML créé: {filename}"
    
    @handle_export_errors(title="Erreur export données complètes")
    def export_all_data(self, export_format: ExportFormat,
                       filename: Optional[str] = None) -> str:
        """Exporter toutes les données"""
        if not self.db_manager:
            raise ExportError("Gestionnaire de base de données non initialisé")

        # Récupérer toutes les données
        data = self.db_manager.load_data()

        if not data:
            raise ExportError("Aucune donnée à exporter")

        # Convertir le format des données pour l'export
        export_data = []
        for record in data:
            # record[0] = id, record[1:] = données
            row_data = record[1:] + (None,)  # Ajouter None pour ref_piece
            export_data.append(row_data)

        # Générer le nom de fichier
        if not filename:
            filename = self._generate_filename("all_data", export_format)

        # Exporter selon le format
        if export_format == ExportFormat.CSV:
            return self._export_all_to_csv(export_data, filename)
        elif export_format == ExportFormat.JSON:
            return self._export_all_to_json(export_data, filename)
        elif export_format == ExportFormat.XML:
            return self._export_all_to_xml(export_data, filename)
        else:
            raise ExportError(f"Format d'export non supporté pour l'export complet: {export_format}")
    
    @handle_export_errors(title="Erreur export CSV complet")
    def _export_all_to_csv(self, data: List[Tuple], filename: str) -> str:
        """Exporter toutes les données vers CSV"""
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')

            # En-têtes
            writer.writerow(Config.UI_HEADERS)

            # Données
            for record in data:
                writer.writerow(record[:len(Config.DB_HEADERS)])

        return f"Fichier CSV complet créé: {filename}"
    
    @handle_export_errors(title="Erreur export JSON complet")
    def _export_all_to_json(self, data: List[Tuple], filename: str) -> str:
        """Exporter toutes les données vers JSON"""
        json_data = {
            'export_info': {
                'export_date': datetime.now().isoformat(),
                'total_records': len(data),
                'export_type': 'complete'
            },
            'appareils': []
        }

        for record in data:
            appareil = {}
            for i, header in enumerate(Config.DB_HEADERS):
                if i < len(record):
                    appareil[header] = record[i] or ''

            json_data['appareils'].append(appareil)

        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)

        return f"Fichier JSON complet créé: {filename}"
    
    @handle_export_errors(title="Erreur export XML complet")
    def _export_all_to_xml(self, data: List[Tuple], filename: str) -> str:
        """Exporter toutes les données vers XML"""
        xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_content.append('<export_complet>')
        xml_content.append(f'  <export_date>{datetime.now().isoformat()}</export_date>')
        xml_content.append(f'  <total_records>{len(data)}</total_records>')
        xml_content.append('  <appareils>')

        for record in data:
            xml_content.append('    <appareil>')
            for i, header in enumerate(Config.DB_HEADERS):
                if i < len(record):
                    value = record[i] or ''
                    xml_content.append(f'      <{header}>{self._escape_xml(value)}</{header}>')
            xml_content.append('    </appareil>')

        xml_content.append('  </appareils>')
        xml_content.append('</export_complet>')

        with open(filename, 'w', encoding='utf-8') as xmlfile:
            xmlfile.write('\n'.join(xml_content))

        return f"Fichier XML complet créé: {filename}"
    
    def create_export_report(self, data: List[Tuple], search_term: str = None) -> Dict[str, Any]:
        """Créer un rapport d'export"""
        report = {
            'export_date': datetime.now().isoformat(),
            'search_term': search_term,
            'total_records': len(data),
            'statistics': {
                'manufacturers': set(),
                'types': set(),
                'categories': set(),
                'empty_fields': defaultdict(int)
            }
        }
        
        # Analyser les données
        for record in data:
            if len(record) >= 2:  # Au moins type et manufacturer
                type_app = record[0] if len(record) > 0 else ''
                manufacturer = record[1] if len(record) > 1 else ''
                category = record[5] if len(record) > 5 else ''
                
                if type_app:
                    report['statistics']['types'].add(type_app)
                else:
                    report['statistics']['empty_fields']['type'] += 1
                
                if manufacturer:
                    report['statistics']['manufacturers'].add(manufacturer)
                else:
                    report['statistics']['empty_fields']['manufacturer'] += 1
                
                if category:
                    report['statistics']['categories'].add(category)
                else:
                    report['statistics']['empty_fields']['category'] += 1
        
        # Convertir les sets en listes pour la sérialisation
        report['statistics']['manufacturers'] = list(report['statistics']['manufacturers'])
        report['statistics']['types'] = list(report['statistics']['types'])
        report['statistics']['categories'] = list(report['statistics']['categories'])
        
        return report
    
    def _generate_filename(self, search_term, export_format: ExportFormat) -> str:
        """Générer un chemin complet vers le Bureau pour l'export"""
        # Convertir le terme de recherche en chaîne si c'est un objet
        if isinstance(search_term, dict):
            # Pour les objets dict, créer un nom basé sur le type de recherche
            if search_term.get('type') == 'or':
                terms = []
                for group in search_term.get('groups', []):
                    terms.extend(group.get('terms', []))
                display_term = '_'.join(terms[:3])  # Max 3 termes pour éviter nom trop long
                if len(terms) > 3:
                    display_term += f"_and_{len(terms)-3}_more"
            else:
                display_term = str(search_term)[:30]  # Limité à 30 chars
        else:
            display_term = str(search_term)
        
        # Nettoyer le terme de recherche
        clean_term = "".join(c for c in display_term if c.isalnum() or c in (' ', '-', '_')).strip()
        clean_term = clean_term.replace(' ', '_')
        
        # Ajouter la date
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Construire le nom de fichier selon le format standardisé
        if export_format == ExportFormat.CSV:
            filename = f"{clean_term}_everyParts.csv"
        else:
            filename = f"{clean_term}_{timestamp}.{export_format.lowercase}"
        
        # Obtenir le chemin du Bureau
        import os
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        # Créer le chemin complet
        full_path = os.path.join(desktop_path, filename)
        
        return full_path
    
    def _escape_xml(self, text: str) -> str:
        """Échapper les caractères spéciaux pour XML"""
        if not text:
            return ''
        
        escapes = {
            '<': '&lt;',
            '>': '&gt;',
            '&': '&amp;',
            '"': '&quot;',
            "'": '&apos;'
        }
        
        for char, escape in escapes.items():
            text = text.replace(char, escape)
        
        return text
    
    def _update_export_stats(self, success: bool):
        """Mettre à jour les statistiques d'export"""
        self.export_stats['total_exports'] += 1
        if success:
            self.export_stats['successful_exports'] += 1
        else:
            self.export_stats['failed_exports'] += 1
        self.export_stats['last_export_time'] = datetime.now().isoformat()
    
    def get_export_stats(self) -> Dict[str, Any]:
        """Récupérer les statistiques d'export"""
        return self.export_stats.copy()
    
    def get_supported_formats(self) -> List[str]:
        """Récupérer la liste des formats supportés"""
        return [fmt.lowercase for fmt in ExportFormat]