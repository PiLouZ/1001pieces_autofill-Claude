"""
Service de configuration des exports - Export configurable CSV + HTML
Gère la lecture/écriture de data/export_config.json

Responsabilités:
- Charger et valider la configuration d'export (CSV + HTML)
- Créer le fichier de config par défaut si absent (valeurs = comportement actuel)
- Fournir render_csv_row() et render_html_template() pour la génération
- Exposer get/set pour le dialogue de configuration
"""

import copy
import html
import json
import os
import re
from typing import Dict, Any, List, Tuple

from .base_service import BaseService
from src.core.logger import app_logger


# Valeurs par défaut = comportement actuel exact (zéro régression)
DEFAULT_CONFIG: Dict[str, Any] = {
    "csv": {
        "separator": ";",
        "encoding": "utf-8",
        "filename_pattern": "{export_ref}_everyParts.csv",
        "columns": [
            {"header": "product",              "source": "{export_ref}"},
            {"header": "type",                 "source": "{type_app}"},
            {"header": "manufacturer",         "source": "{manufacturer}"},
            {"header": "modele_name",          "source": "{modele_complet}"},
            {"header": "reference_modele",     "source": "{ref_modele}"},
            {"header": "commercial_reference", "source": "{commercial_ref}"}
        ]
    },
    "html": {
        "brands": {
            "link_template": "<a href=\"#{marque}\">{marque}</a>",
            "separator":     " ",
            "char_limit":    195000
        },
        "details": {
            "brand_header_template": "<div id=\"{marque}\"><b><u>{marque}</u></b></div>",
            "model_line_template":   "<div>{modele_complet}</div>",
            "group_separator":       "<div>&nbsp;</div>",
            "char_limit":            195000
        }
    }
}

# Variables disponibles dans les sources de colonnes et templates
AVAILABLE_VARIABLES = [
    "{export_ref}", "{ref_piece}", "{type_app}", "{manufacturer}",
    "{ref_modele}", "{commercial_ref}", "{other_ref}",
    "{modele_complet}", "{separateur}"
]

AVAILABLE_HTML_VARIABLES = {
    "brands":  ["{marque}"],
    "details": ["{marque}", "{ref_modele}", "{ref_commerciale}", "{other_ref}", "{modele_complet}", "{separateur}"]
}


class ExportConfigService(BaseService):
    """
    Service de gestion de la configuration des exports.

    Responsabilités:
    - Chargement/sauvegarde de data/export_config.json
    - Rendu des lignes CSV selon la config (substitution {var})
    - Rendu des templates HTML selon la config (substitution {var})
    - Fallback transparent sur les défauts si le fichier est absent ou corrompu
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Dict[str, Any] = {}
        self._config_path = self._resolve_config_path()
        self._load()

    # ─── Chemin et chargement ────────────────────────────────────────────────

    @staticmethod
    def _resolve_config_path() -> str:
        """Retourner le chemin absolu vers data/export_config.json"""
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.normpath(os.path.join(base, '..', '..', 'data', 'export_config.json'))

    def _load(self) -> None:
        """Charger la config depuis le fichier (crée le fichier si absent)"""
        if not os.path.exists(self._config_path):
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            self._write()
            app_logger.info("[OK] export_config.json créé avec les valeurs par défaut")
            return

        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self._config = self._merge_with_defaults(loaded)
        except Exception as e:
            app_logger.warning(f"[!] export_config.json illisible ({e}), utilisation des défauts")
            self._config = copy.deepcopy(DEFAULT_CONFIG)

    def _merge_with_defaults(self, loaded: Dict) -> Dict:
        """Compléter les clés manquantes avec les valeurs par défaut"""
        merged = copy.deepcopy(DEFAULT_CONFIG)
        if 'csv' in loaded:
            merged['csv'].update(loaded['csv'])
        if 'html' in loaded:
            if 'brands' in loaded['html']:
                merged['html']['brands'].update(loaded['html']['brands'])
            if 'details' in loaded['html']:
                merged['html']['details'].update(loaded['html']['details'])
        return merged

    def _write(self) -> None:
        """Écrire la config sur le disque"""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    # ─── API publique ────────────────────────────────────────────────────────

    def get_config(self) -> Dict[str, Any]:
        """Retourner une copie de la config complète"""
        return copy.deepcopy(self._config)

    def save_config(self, config: Dict[str, Any]) -> bool:
        """Valider, sauvegarder et rechager la config. Retourne True si succès."""
        try:
            self._config = self._merge_with_defaults(config)
            self._write()
            app_logger.info("[OK] export_config.json sauvegardé")
            return True
        except Exception as e:
            app_logger.error(f"[ERR] Sauvegarde export_config.json : {e}")
            return False

    def reset_to_defaults(self) -> None:
        """Remettre la config aux valeurs par défaut et sauvegarder"""
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._write()
        app_logger.info("[OK] export_config.json réinitialisé aux valeurs par défaut")

    # ─── Accesseurs CSV ──────────────────────────────────────────────────────

    def get_csv_headers(self) -> List[str]:
        return [col['header'] for col in self._config['csv']['columns']]

    def get_csv_separator(self) -> str:
        return self._config['csv'].get('separator', ';')

    def get_csv_encoding(self) -> str:
        return self._config['csv'].get('encoding', 'utf-8')

    def get_csv_filename_pattern(self) -> str:
        return self._config['csv'].get('filename_pattern', '{term}_everyParts.csv')

    def get_csv_columns(self) -> List[Dict]:
        return copy.deepcopy(self._config['csv']['columns'])

    # ─── Accesseurs HTML ─────────────────────────────────────────────────────

    def get_html_brands_config(self) -> Dict:
        return copy.deepcopy(self._config['html']['brands'])

    def get_html_details_config(self) -> Dict:
        return copy.deepcopy(self._config['html']['details'])

    # ─── Rendu CSV ───────────────────────────────────────────────────────────

    def render_csv_row(self, record: Tuple, search_term: str = '') -> List[str]:
        """
        Générer une ligne CSV depuis un record selon la config colonnes.

        record = (type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece)
        """
        type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record

        ref_m = ref_modele or ''
        ref_c = commercial_ref or ''
        modele_complet = f"{ref_m} - {ref_c}".strip(' -') if (ref_m and ref_c) else (ref_m or ref_c)
        separateur = ' - ' if (ref_m and ref_c) else ''

        context = {
            'export_ref':     search_term or '',
            'ref_piece':      ref_piece or '',
            'type_app':       type_app or '',
            'manufacturer':   manufacturer or '',
            'ref_modele':     ref_m,
            'commercial_ref': ref_c,
            'other_ref':      other_ref or '',
            'modele_complet': modele_complet,
            'separateur':     separateur,
        }

        return [
            self._render_source(col['source'], context)
            for col in self._config['csv']['columns']
        ]

    def _render_source(self, source: str, context: Dict) -> str:
        """Substituer les {variables} dans une source de colonne CSV"""
        try:
            result = source.format(**context)
            # Nettoyer les assemblages vides ex: " - " quand les deux champs sont vides
            result = result.strip()
            if result in ('-', ' - ', '- ', ' -'):
                result = ''
            return result
        except (KeyError, ValueError):
            return source

    # ─── Rendu HTML ──────────────────────────────────────────────────────────

    def render_html_template(self, template: str, context: Dict) -> str:
        """Substituer les {variables} dans un template HTML

        Les valeurs sont échappées (html.escape) : les données importées
        (PDF/CSV externes) ne doivent jamais injecter de balises dans le HTML
        exporté. Le template lui-même reste du HTML brut voulu par l'utilisateur.
        """
        for key, value in context.items():
            template = template.replace('{' + key + '}', html.escape(str(value or ''), quote=True))
        return template
