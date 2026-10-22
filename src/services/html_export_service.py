"""
HTML Export Service - Consolidation des logiques HTML dupliquées
Extrait et unifie les méthodes de génération HTML de data_exporter.py et services/export_service.py
"""

from collections import defaultdict
from typing import List, Tuple, Dict, Any
import html
import re

class HtmlExportService:
    """Service centralisé pour la génération de contenu HTML d'export

    Élimine la duplication massive entre:
    - data_exporter.py: _export_html_brands, _export_html_details, _generate_html_content
    - services/export_service.py: _generate_html_brands, _generate_html_details, _generate_html_content

    Peut être configuré via ExportConfigService (injection par set_config_service).
    Si aucun service de config n'est injecté, utilise les templates par défaut (zéro régression).
    """

    # Constante de limite de caractères (surpassée par la config si disponible)
    CHAR_LIMIT = 195000

    # Stratégie utilisée lors du dernier appel à generate_html_details()
    # ('full', 'ref_modele' ou 'commercial_ref') — permet à l'appelant de
    # savoir si une troncature a eu lieu pour respecter la limite de caractères
    last_strategy_used = 'full'

    # Service de config injecté via set_config_service() depuis main_refactored.py
    _config_service = None

    @classmethod
    def set_config_service(cls, config_service) -> None:
        """Injecter le service de configuration des exports"""
        cls._config_service = config_service

    @classmethod
    def generate_html_brands(cls, data: List[Tuple]) -> str:
        """Générer liens HTML des marques selon la config (ou défauts si pas de config)"""
        cfg = cls._config_service
        brands_cfg = cfg.get_html_brands_config() if cfg else {}

        link_template = brands_cfg.get('link_template', '<a href="#{marque}">{marque}</a>')
        separator     = brands_cfg.get('separator',     ' ')

        brands = set()
        for record in data:
            if len(record) >= 2:
                manufacturer = record[1]
                if manufacturer and manufacturer.strip():
                    brands.add(manufacturer.strip())

        html_links = []
        for brand in sorted(brands):
            context = {'marque': brand}
            if cfg:
                html_links.append(cfg.render_html_template(link_template, context))
            else:
                html_links.append(link_template.replace('{marque}', html.escape(brand, quote=True)))

        return cls.wrap_brand_links(separator.join(html_links),
                                    brands_cfg.get('wrapper_template', '{liens}'))

    @staticmethod
    def wrap_brand_links(links: str, wrapper_template: str) -> str:
        """Placer les liens de marques dans le code englobant ({liens}).

        Pas d'enveloppe sans marque (évite un « Compatible avec » vide), ni si
        le gabarit oublie {liens} (les liens seraient perdus en silence).
        Remplacement direct, sans échappement : les liens sont déjà du HTML
        dont les noms de marques ont été échappés.
        """
        if not links or not wrapper_template or '{liens}' not in wrapper_template:
            return links
        return wrapper_template.replace('{liens}', links)
    
    @classmethod
    def generate_html_details(cls, data: List[Tuple], profile_name: str = None) -> str:
        """Générer HTML détaillé avec références par marque (anciennement dupliqué dans 2 services)

        Args:
            data: Données avec structure [product, manufacturer, ref_modele, commercial_ref, ...]
            profile_name: Profil d'export à utiliser (None = profil par défaut)

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
                other_ref = record[4] if len(record) >= 5 else ''  # Index 4 = other_ref

                if manufacturer and manufacturer.strip():
                    brands_data[manufacturer].append({
                        'ref_modele': ref_modele or '',
                        'commercial_ref': commercial_ref or '',
                        'other_ref': other_ref or ''
                    })
        
        # Limite de caractères depuis la config ou constante par défaut
        cfg = cls._config_service
        details_cfg = cfg.get_html_details_config(profile_name) if cfg else {}
        char_limit = details_cfg.get('char_limit', cls.CHAR_LIMIT)

        # Générer le HTML avec stratégies de fallback pour respecter la limite
        strategies = ['full', 'ref_modele', 'commercial_ref']

        for strategy in strategies:
            html_content = HtmlExportService._generate_html_content_with_strategy(
                brands_data, strategy, details_cfg if cfg else {}
            )
            char_count = HtmlExportService.count_non_html_chars(html_content)
            if char_count <= char_limit:
                cls.last_strategy_used = strategy
                return html_content

        cls.last_strategy_used = 'commercial_ref'
        return "<p>Données trop volumineuses pour l'affichage</p>"
    
    @staticmethod
    def _generate_html_content_with_strategy(
        brands_data: Dict[str, List[Dict]],
        strategy: str,
        details_cfg: Dict = None
    ) -> str:
        """Générer contenu HTML avec stratégie spécifique.

        Args:
            brands_data:  Données groupées par marque
            strategy:     'full', 'ref_modele' ou 'commercial_ref'
            details_cfg:  Config HTML détails (templates) — None = défauts hardcodés
        """
        if details_cfg is None:
            details_cfg = {}

        brand_header_tpl  = details_cfg.get('brand_header_template',
                                            '<div id="{marque}"><b><u>{marque}</u></b></div>')
        model_line_tpl    = details_cfg.get('model_line_template',
                                            '<div>{ref_modele} - {ref_commerciale}</div>')
        group_separator   = details_cfg.get('group_separator', '<div>&nbsp;</div>')

        def _render(template: str, context: Dict) -> str:
            # html.escape sur les valeurs (données importées de sources externes),
            # jamais sur le template (HTML voulu par l'utilisateur)
            for key, val in context.items():
                template = template.replace('{' + key + '}', html.escape(str(val or ''), quote=True))
            return template

        html_parts = []

        for i, brand in enumerate(sorted(brands_data.keys())):
            models = brands_data[brand]

            if i > 0:
                html_parts.append(group_separator)

            models_to_display = set()

            for model_info in models:
                ref_modele     = model_info['ref_modele']
                commercial_ref = model_info['commercial_ref']
                other_ref      = model_info['other_ref']

                if strategy == 'full':
                    modele_complet = f"{ref_modele} - {commercial_ref}".strip(' -')
                    if modele_complet and modele_complet != '-':
                        models_to_display.add((ref_modele, commercial_ref, other_ref, modele_complet))
                elif strategy == 'ref_modele':
                    if ref_modele and ref_modele.strip():
                        models_to_display.add((ref_modele, '', other_ref, ref_modele.strip()))
                elif strategy == 'commercial_ref':
                    if commercial_ref and commercial_ref.strip():
                        models_to_display.add(('', commercial_ref, other_ref, commercial_ref.strip()))

            if models_to_display:
                html_parts.append(_render(brand_header_tpl, {'marque': brand}))

                for ref_modele, ref_commerciale, other_ref, modele_complet in sorted(models_to_display, key=lambda x: x[3]):
                    separateur = ' - ' if (ref_modele and ref_commerciale) else ''
                    context = {
                        'marque':          brand,
                        'ref_modele':      ref_modele,
                        'ref_commerciale': ref_commerciale,
                        'other_ref':       other_ref,
                        'modele_complet':  modele_complet,
                        'separateur':      separateur,
                    }
                    html_parts.append(_render(model_line_tpl, context))

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