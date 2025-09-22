"""
HTML Export Service - Consolidation des logiques HTML dupliquées
Extrait et unifie les méthodes de génération HTML de data_exporter.py et services/export_service.py
"""

from collections import defaultdict
from typing import List, Tuple, Dict, Any
import re

class HtmlExportService:
    """Service centralisé pour la génération de contenu HTML d'export
    
    Élimine la duplication massive entre:
    - data_exporter.py: _export_html_brands, _export_html_details, _generate_html_content
    - services/export_service.py: _generate_html_brands, _generate_html_details, _generate_html_content
    """
    
    # Constantes centralisées
    CHAR_LIMIT = 195000  # Limite de caractères pour le site web
    
    @staticmethod
    def generate_html_brands(data: List[Tuple]) -> str:
        """Générer liens HTML des marques (anciennement dupliqué dans 2 services)
        
        Args:
            data: Données avec structure [product, manufacturer, ref_modele, commercial_ref, ...]
            
        Returns:
            String HTML avec liens vers marques: '<a href="#brand">brand</a> <a href="#brand2">brand2</a>'
        """
        brands = set()
        
        # Extraire les marques uniques
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
    
    @staticmethod
    def generate_html_details(data: List[Tuple]) -> str:
        """Générer HTML détaillé avec références par marque (anciennement dupliqué dans 2 services)
        
        Args:
            data: Données avec structure [product, manufacturer, ref_modele, commercial_ref, ...]
            
        Returns:
            HTML détaillé avec sections par marque et gestion limite caractères
        """
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
        
        # Générer le HTML avec stratégies de fallback pour respecter la limite
        strategies = ['full', 'ref_modele', 'commercial_ref']
        
        for strategy in strategies:
            html_content = HtmlExportService._generate_html_content_with_strategy(brands_data, strategy)
            
            # Vérifier si on respecte la limite de caractères
            char_count = HtmlExportService.count_non_html_chars(html_content)
            if char_count <= HtmlExportService.CHAR_LIMIT:
                return html_content
        
        # Si aucune stratégie ne fonctionne, retourner message d'erreur
        return "<p>Données trop volumineuses pour l'affichage</p>"
    
    @staticmethod
    def _generate_html_content_with_strategy(brands_data: Dict[str, List[Dict]], strategy: str) -> str:
        """Générer contenu HTML avec stratégie spécifique (anciennement dupliqué dans 2 services)
        
        Args:
            brands_data: Données groupées par marque
            strategy: 'full', 'ref_modele' ou 'commercial_ref'
            
        Returns:
            HTML généré selon la stratégie avec <div>&nbsp;</div> entre marques
        """
        html_parts = []
        
        for i, brand in enumerate(sorted(brands_data.keys())):
            models = brands_data[brand]
            
            # Ajouter div vide avant chaque marque sauf la première
            if i > 0:
                html_parts.append('<div>&nbsp;</div>')
            
            # Collecter modèles selon la stratégie
            models_to_display = set()
            
            for model_info in models:
                ref_modele = model_info['ref_modele']
                commercial_ref = model_info['commercial_ref']
                
                if strategy == 'full':
                    # Format complet: ref_modele - commercial_ref
                    modele_complet = f"{ref_modele} - {commercial_ref}".strip(' -')
                    if modele_complet and modele_complet != '-':
                        models_to_display.add(modele_complet)
                        
                elif strategy == 'ref_modele':
                    # Seulement ref_modele
                    if ref_modele and ref_modele.strip():
                        models_to_display.add(ref_modele.strip())
                        
                elif strategy == 'commercial_ref':
                    # Seulement commercial_ref
                    if commercial_ref and commercial_ref.strip():
                        models_to_display.add(commercial_ref.strip())
            
            # Ajouter la section de marque si elle a des modèles
            if models_to_display:
                # En-tête de marque
                html_parts.append(f'<div id="{brand}"><b><u>{brand}</u></b></div>')
                
                # Appareils de la marque (chacun dans sa div)
                for model in sorted(models_to_display):
                    html_parts.append(f'<div>{model}</div>')
        
        # Joindre toutes les parties HTML
        return ''.join(html_parts)
    
    @staticmethod
    def count_non_html_chars(html_content: str) -> int:
        """Compter les caractères non-HTML (anciennement dupliqué dans 2 services)
        
        Args:
            html_content: Contenu HTML à analyser
            
        Returns:
            Nombre de caractères visibles (sans balises HTML)
        """
        # Supprimer toutes les balises HTML
        text_only = re.sub(r'<[^>]*>', '', html_content)
        return len(text_only)
    
    @staticmethod
    def generate_complete_html_export(data: List[Tuple], search_term: str) -> str:
        """Générer un export HTML complet (brands + details)
        
        Args:
            data: Données à exporter
            search_term: Terme de recherche (pour titre)
            
        Returns:
            HTML complet avec en-tête et contenu
        """
        brands_html = HtmlExportService.generate_html_brands(data)
        details_html = HtmlExportService.generate_html_details(data)
        
        # Template HTML complet
        html_template = f"""
        <div class="export-container">
            <h2>Export: {search_term}</h2>
            <div class="brands-navigation">
                {brands_html}
            </div>
            <div class="details-content">
                {details_html}
            </div>
        </div>
        """
        
        return html_template.strip()