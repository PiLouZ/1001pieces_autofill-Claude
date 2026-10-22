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
    # Dossier de destination des exports fichier. "" = Bureau de l'utilisateur.
    # Volontairement stocké vide plutôt qu'en absolu : la config reste portable
    # d'une machine à l'autre et "par défaut le Bureau" y reste vrai.
    "output_dir": "",
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
            # Code englobant la liste complète des liens ; {liens} = les liens
            # joints. '{liens}' seul = liens nus (comportement historique).
            "wrapper_template": "{liens}",
            "char_limit":    195000
        },
        "details": {
            "brand_header_template": "<div id=\"{marque}\"><b><u>{marque}</u></b></div>",
            "model_line_template":   "<div>{modele_complet}</div>",
            "group_separator":       "<div>&nbsp;</div>",
            "char_limit":            195000
        },
        # Profils multiples d'export HTML Détails (v3.40.0).
        # 'details' ci-dessus est conservé comme miroir du profil par défaut
        # (compatibilité avec les configs existantes et le code legacy).
        "details_profiles": [
            {
                "name":                  "Format standard",
                "brand_header_template": "<div id=\"{marque}\"><b><u>{marque}</u></b></div>",
                "model_line_template":   "<div>{modele_complet}</div>",
                "group_separator":       "<div>&nbsp;</div>",
                "char_limit":            195000
            }
        ],
        "details_default_profile": "Format standard"
    }
}

# Clés éditables d'un profil HTML Détails (hors 'name')
DETAILS_PROFILE_KEYS = (
    "brand_header_template", "model_line_template", "group_separator", "char_limit"
)

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
        """Compléter les clés manquantes avec les valeurs par défaut.

        Migration non-destructive des profils (v3.40.0) : si la config chargée
        n'a pas de 'details_profiles', un profil unique "Format standard" est
        créé à partir de sa section 'details' existante — aucune personnalisation
        n'est perdue. 'details' reste synchronisé sur le profil par défaut.
        """
        merged = copy.deepcopy(DEFAULT_CONFIG)
        if isinstance(loaded.get('output_dir'), str):
            merged['output_dir'] = loaded['output_dir']
        if 'csv' in loaded:
            merged['csv'].update(loaded['csv'])
        if 'html' in loaded:
            if 'brands' in loaded['html']:
                merged['html']['brands'].update(loaded['html']['brands'])
            if 'details' in loaded['html']:
                merged['html']['details'].update(loaded['html']['details'])

            # Profils : valider/compléter ceux chargés, sinon migrer depuis 'details'
            valid_profiles = []
            for p in loaded['html'].get('details_profiles') or []:
                if isinstance(p, dict) and p.get('name'):
                    profile = copy.deepcopy(DEFAULT_CONFIG['html']['details'])
                    profile.update({k: p[k] for k in DETAILS_PROFILE_KEYS if k in p})
                    profile['name'] = str(p['name'])
                    valid_profiles.append(profile)

            if valid_profiles:
                merged['html']['details_profiles'] = valid_profiles
            else:
                merged['html']['details_profiles'] = [
                    {'name': 'Format standard', **merged['html']['details']}
                ]

            names = [p['name'] for p in merged['html']['details_profiles']]
            default = loaded['html'].get('details_default_profile')
            merged['html']['details_default_profile'] = default if default in names else names[0]

            # Miroir legacy : 'details' = contenu du profil par défaut
            default_profile = next(
                p for p in merged['html']['details_profiles']
                if p['name'] == merged['html']['details_default_profile']
            )
            merged['html']['details'] = {
                k: v for k, v in default_profile.items() if k != 'name'
            }
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

    # ─── Dossier de destination des exports ──────────────────────────────────

    @staticmethod
    def get_default_output_dir() -> str:
        """Dossier d'export par défaut : le Bureau de l'utilisateur.

        ~/Desktop d'abord (macOS, comportement historique). Sous Windows, le
        Bureau est souvent ailleurs (OneDrive\\Bureau) : on demande alors son
        emplacement réel au système via Qt, avec repli sur le dossier personnel.
        """
        bureau = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.isdir(bureau):
            return bureau
        try:
            from PyQt5.QtCore import QStandardPaths
            systeme = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
            if systeme and os.path.isdir(systeme):
                return systeme
        except Exception:
            pass
        return os.path.expanduser("~")

    def get_output_dir(self) -> str:
        """Dossier de destination des exports fichier (chemin absolu).

        Repli sur le Bureau si aucun dossier n'est configuré, ou si le dossier
        configuré n'est plus utilisable (disque externe débranché, dossier
        renommé ou passé en lecture seule) : un export ne doit jamais échouer
        à cause d'un réglage devenu obsolète.
        """
        configured = (self._config.get('output_dir') or '').strip()
        if not configured:
            return self.get_default_output_dir()

        expanded = os.path.abspath(os.path.expanduser(configured))
        if os.path.isdir(expanded) and os.access(expanded, os.W_OK):
            return expanded

        app_logger.warning(
            f"[!] Dossier d'export inutilisable ({configured}), repli sur le Bureau"
        )
        return self.get_default_output_dir()

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

    def get_html_details_config(self, profile_name: str = None) -> Dict:
        """Config HTML Détails du profil demandé (ou du profil par défaut).

        Sans argument, comportement historique : retourne le profil par défaut
        (miroir de l'ancienne section 'details'). Avec un nom inconnu, retombe
        sur le profil par défaut plutôt que d'échouer.
        """
        name = profile_name or self._config['html'].get('details_default_profile')
        for p in self._config['html'].get('details_profiles', []):
            if p.get('name') == name:
                return {k: copy.deepcopy(v) for k, v in p.items() if k != 'name'}
        return copy.deepcopy(self._config['html']['details'])

    def get_details_profiles(self) -> List[Dict]:
        """Liste complète des profils HTML Détails (copies)"""
        return copy.deepcopy(self._config['html'].get('details_profiles', []))

    def get_details_profile_names(self) -> List[str]:
        return [p['name'] for p in self._config['html'].get('details_profiles', [])]

    def get_default_details_profile_name(self) -> str:
        return self._config['html'].get('details_default_profile', 'Format standard')

    # ─── Rendu CSV ───────────────────────────────────────────────────────────

    def render_csv_row(self, record: Tuple, export_ref: str = '') -> List[str]:
        """
        Générer une ligne CSV depuis un record selon la config colonnes.

        record = (type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece)
        export_ref = référence d'export retenue pour ce lot (celle confirmée dans
            le dialogue d'export), substituée à {export_ref}.
        """
        return render_csv_row_with(self._config['csv']['columns'], record, export_ref)

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


# ─── Résolution du dossier d'export ──────────────────────────────────────────

def resolve_output_dir(service) -> str:
    """Dossier de destination des exports, avec repli systématique sur le Bureau.

    Point d'entrée unique pour les appelants qui n'ont pas la garantie de
    disposer du service (widgets construits sans parent, services créés avant
    la fenêtre principale). Le repli reproduit exactement le comportement
    historique — écriture sur le Bureau — donc aucun appelant ne peut régresser.
    """
    if service is not None:
        try:
            return service.get_output_dir()
        except Exception as e:
            app_logger.warning(f"[!] Dossier d'export illisible ({e}), repli sur le Bureau")
    return ExportConfigService.get_default_output_dir()


# ─── Rendu CSV partagé ───────────────────────────────────────────────────────

def _render_source(source: str, context: Dict) -> str:
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


def render_csv_row_with(columns: List[Dict], record: Tuple, export_ref: str = '') -> List[str]:
    """Rendre une ligne CSV pour un jeu de colonnes donné.

    Renderer unique de l'application : ExportConfigService.render_csv_row y
    délègue, et les appelants dépourvus de service passent les colonnes par
    défaut. Deux écrivains CSV divergents étaient précisément la cause du
    bug corrigé en v3.68.0 — il ne doit exister qu'un seul rendu.
    """
    type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record

    ref_m = ref_modele or ''
    ref_c = commercial_ref or ''
    modele_complet = f"{ref_m} - {ref_c}".strip(' -') if (ref_m and ref_c) else (ref_m or ref_c)
    separateur = ' - ' if (ref_m and ref_c) else ''

    context = {
        'export_ref':     export_ref or '',
        'ref_piece':      ref_piece or '',
        'type_app':       type_app or '',
        'manufacturer':   manufacturer or '',
        'ref_modele':     ref_m,
        'commercial_ref': ref_c,
        'other_ref':      other_ref or '',
        'modele_complet': modele_complet,
        'separateur':     separateur,
    }

    return [_render_source(col['source'], context) for col in columns]


def get_csv_settings(service) -> Dict[str, Any]:
    """Réglages CSV effectifs, avec repli sur les défauts si le service est absent.

    Même contrat que resolve_output_dir : le repli reproduit le comportement
    historique, aucun appelant ne peut donc régresser faute de service.
    """
    defauts = DEFAULT_CONFIG['csv']
    if service is None:
        return {
            'columns':          copy.deepcopy(defauts['columns']),
            'headers':          [c['header'] for c in defauts['columns']],
            'separator':        defauts['separator'],
            'encoding':         defauts['encoding'],
            'filename_pattern': defauts['filename_pattern'],
        }
    return {
        'columns':          service.get_csv_columns(),
        'headers':          service.get_csv_headers(),
        'separator':        service.get_csv_separator(),
        'encoding':         service.get_csv_encoding(),
        'filename_pattern': service.get_csv_filename_pattern(),
    }


def format_csv_filename(pattern: str, export_ref: str, timestamp: str = '') -> str:
    """Appliquer le pattern de nom de fichier, sans jamais faire échouer l'export.

    Le pattern est saisi librement dans la fenêtre de configuration : une
    variable inconnue ou une accolade mal fermée ne doit pas empêcher
    l'export, et un séparateur de chemin ne doit pas écrire hors du dossier
    de destination choisi.
    """
    try:
        nom = pattern.format(export_ref=export_ref, timestamp=timestamp)
    except (KeyError, IndexError, ValueError) as e:
        app_logger.warning(
            f"[!] Pattern de nom de fichier invalide ({pattern!r} : {e}), "
            f"utilisation du pattern par défaut"
        )
        nom = DEFAULT_CONFIG['csv']['filename_pattern'].format(
            export_ref=export_ref, timestamp=timestamp
        )

    base = os.path.basename(nom).strip()
    if base != nom.strip():
        app_logger.warning(
            f"[!] Séparateur de chemin dans le nom de fichier ({nom!r}), "
            f"conservé sous {base!r} dans le dossier d'export"
        )
    return base or DEFAULT_CONFIG['csv']['filename_pattern'].format(
        export_ref=export_ref, timestamp=timestamp
    )


# ─── Sécurité CSV ────────────────────────────────────────────────────────────
# Déplacés depuis data_exporter.py (supprimé en v3.69.0) : ils appartiennent au
# module qui porte déjà le rendu CSV, et non à un exporteur devenu inatteignable.

def _neutraliser_formule_csv(valeur):
    """Neutraliser l'injection de formule CSV (ouverture dans Excel/LibreOffice).

    Une cellule commençant par '=', '+' ou '@' serait interprétée comme une
    formule par le tableur. Les données provenant d'imports externes (PDF/CSV),
    on préfixe d'une apostrophe — convention tableur pour forcer le texte.
    Le tiret '-' n'est volontairement pas traité (peut apparaître en tête de
    références réelles, et n'est pas exploitable seul).
    """
    if isinstance(valeur, str) and valeur and valeur[0] in ('=', '+', '@'):
        return "'" + valeur
    return valeur


def _assainir_ligne_csv(row):
    """Appliquer la neutralisation de formules à toutes les cellules d'une ligne"""
    return [_neutraliser_formule_csv(cell) for cell in row]
