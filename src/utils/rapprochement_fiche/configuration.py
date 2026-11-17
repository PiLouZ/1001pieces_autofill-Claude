"""
Configuration du rapprochement des fiches du site (CDC § 5.1, 5.5, 5.6, § 9)

Tables tenues EN CONFIGURATION, modifiables sans PR :
- formats de références → étiquette d'origine (§ 5.5), de la règle la plus
  précise à la plus large : la première qui correspond l'emporte. Une règle
  « doute » marque un cas mélangé (10 chiffres en 15 : Electrolux ou Beko…) ;
- préfixes de la référence produit interne (§ 5.1 : EL1113161010, GAU11051894),
  mesurés sur l'export du site (§ 10.1) ;
- correspondance catégorie du site → type d'appareil (§ 5.6) : par défaut la
  partie après le dernier « - » si c'est un type connu, plus des exceptions ;
- alias de marques : écriture de la fiche → marque de l'outil, quand la clé
  sans casse ni accents ne suffit pas (le singulier/pluriel, « Rosière » /
  « Rosières », est déjà toléré) ;
- groupes de marques (niveau « à valider » du § 5.2 : référence trouvée sous
  une autre marque du même groupe industriel). Liste de départ, à compléter ;
Les valeurs ci-dessous sont les défauts ; `data/reprise_fiches.json` (même
structure, cf. data/reprise_fiches.example.json) les remplace clé par clé.
"""

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.lecteur_fiche.lecteur import cle_marque

CHEMIN_CONFIGURATION = Path(__file__).resolve().parents[3] / 'data' / 'reprise_fiches.json'

CONFIGURATION_PAR_DEFAUT: Dict[str, Any] = {
    # Règles appliquées dans l'ordre ; `doute` = cas mélangé, origine à saisir
    'formats_references': [
        {'motif': r'48\d{10}', 'origine': 'Whirlpool'},
        {'motif': r'C00\d{6}', 'origine': 'Indesit'},
        {'motif': r'00\d{6}', 'origine': 'BSH'},
        {'motif': r'(?:10|11|12|17|20)\d{6}', 'origine': 'BSH'},
        {'motif': r'(?:41|43|49|70|91|92|93)\d{6}', 'origine': 'Candy'},
        {'motif': r'42\d{6}', 'origine': '', 'doute': 'Candy ou Sharp'},
        {'motif': r'32\d{6}', 'origine': '', 'doute': 'Sharp ?'},
        # Beko (10 chiffres) : débuts où la base ne compte que des pièces Beko ;
        # avant le doute « 15 » et la règle générale Electrolux
        {'motif': r'(?:151|19[01]|24[4-9]|27[01]|91[7-9])\d{7}', 'origine': 'Beko'},
        {'motif': r'(?:17|18|28|29|4[2-9]|5[7-9]|61)\d{8}', 'origine': 'Beko'},
        {'motif': r'15\d{8}', 'origine': '', 'doute': 'Electrolux ou Beko'},
        {'motif': r'\d{10}', 'origine': 'Electrolux'},
        {'motif': r'50\d{9}', 'origine': 'Electrolux'},
        {'motif': r'14\d{10}', 'origine': 'Electrolux'},
        {'motif': r'(?:61|71|74|95)\d{7}', 'origine': 'Liebherr'},
        {'motif': r'(?:69|75|81)\d{7}', 'origine': 'Smeg'},
        # 9 chiffres en 16 / 26 : 22 pièces en base, toutes du groupe Beko (2026-11-17)
        {'motif': r'(?:16|26)\d{7}', 'origine': 'Beko'},
        {'motif': r'\d{7}', 'origine': 'Miele'},
        {'motif': r'0\d{5}', 'origine': 'Atlantic / Thermor'},
        {'motif': r'\d{2}X\d{4}', 'origine': 'Brandt'},
        {'motif': r'AS\d{7}', 'origine': 'Brandt'},
        {'motif': r'\d{2}S\d{4}', 'origine': '', 'doute': 'Brandt ? (S au lieu de X)'},
        {'motif': r'(?:DD82|DA97|DC31)-\S+', 'origine': 'Samsung'},
        {'motif': r'[A-Z]{3}\d{8}', 'origine': 'LG'},
    ],
    # Préfixes de la référence interne (le plus long est essayé en premier)
    'prefixes_ref_interne': ['FAR', 'EL', 'GAU', 'ROS', 'MIE', 'LH', 'ATC', 'D', 'NOT',
                             'BEO', 'CET', 'STN0'],
    # Catégorie → type, au-delà de la règle « partie après le dernier « - » »
    # (clé comparée sans casse ni accents ; '' = pas de type unique)
    'categories_types': {
        'MO': 'Micro-ondes',
        'Réfrigérateur américain': 'Réfrigérateur',
        'Sac aspirateur': 'Aspirateur',
        'Brosse aspirateur': 'Aspirateur',
        'Tube aspirateur': 'Aspirateur',
        'Désodorisant réfrigérateur': 'Réfrigérateur',
        'Filtre / Climatisation': 'Climatiseur',
        'Machine à café & bouilloire': '',
        'Petit ménager': '',
    },
    # Écriture de la fiche → marque de l'outil (clé comparée sans casse ni accents)
    'alias_marques': {'GE': 'General Electric', 'Brauknecht': 'Bauknecht'},
    # Réponses mémorisées aux questions de règle de l'import par lots (clé → réponse)
    'groupes_marques': {
        'Whirlpool': ['Whirlpool', 'Bauknecht', 'Ignis', 'Laden', 'Indesit', 'Hotpoint-Ariston',
                      'Scholtès', 'Privileg', 'KitchenAid', 'Proline'],
        'BSH': ['Bosch', 'Siemens', 'Neff', 'Gaggenau', 'Balay', 'Constructa', 'Viva', 'Jünker',
                'Pitsos', 'Profilo'],
        'Electrolux': ['Electrolux', 'AEG', 'Zanussi', 'Arthur-Martin-Electrolux', 'Faure',
                       'Progress', 'Rex', 'Juno', 'Zanker', 'Husqvarna', 'Elektra-Bregenz'],
        'Candy': ['Candy', 'Hoover', 'Rosières', 'Otsein', 'Iberna', 'Zerowatt'],
        'Brandt': ['Brandt', 'De Dietrich', 'Sauter', 'Fagor', 'Vedette', 'Thomson', 'Ocean',
                   'Edesa'],
        'Beko': ['Beko', 'Blomberg', 'Grundig'],
        'Atlantic': ['Atlantic', 'Thermor'],
    },
}


@dataclass(frozen=True)
class RegleFormat:
    motif: re.Pattern
    origine: str            # '' quand la règle est un doute
    doute: str = ''         # cas mélangé : libellé des origines possibles


@dataclass(frozen=True)
class Origine:
    """Origine déduite du format d'une référence."""
    etiquette: str          # '' = inconnue ou douteuse
    doute: str = ''         # cas mélangé (règle « doute »)
    motif: str = ''         # motif de la règle retenue ('' = aucune)

    @property
    def connue(self) -> bool:
        return bool(self.etiquette)


class ConfigurationRapprochement:
    """Configuration compilée (formats, préfixes, catégories, groupes)."""

    def __init__(self, donnees: Optional[Dict[str, Any]] = None):
        d = fusionner(CONFIGURATION_PAR_DEFAUT, donnees or {})
        self.donnees = d
        self.formats: List[RegleFormat] = [
            RegleFormat(re.compile(r['motif'], re.I), r.get('origine') or '', r.get('doute') or '')
            for r in d['formats_references'] if r.get('motif')]
        self.prefixes: Tuple[str, ...] = tuple(sorted(
            {p.strip().upper() for p in d['prefixes_ref_interne'] if p and p.strip()},
            key=len, reverse=True))
        self.categories_types: Dict[str, str] = {
            cle_marque(k): v for k, v in (d.get('categories_types') or {}).items()}
        self.alias_marques: Dict[str, str] = {
            cle_marque(k): v for k, v in (d.get('alias_marques') or {}).items() if v}
        # Onglet Appareils des exports (`synonymes_appareils`) : types et appellations
        # où couper le titre d'une fiche pour en faire un libellé ; None = défauts.
        # Renseigné par le service d'enregistrement depuis la config des exports.
        self.appellations_appareils: Any = None
        # marque (clé) → nom du groupe
        self.groupe_de: Dict[str, str] = {}
        for groupe, marques in (d.get('groupes_marques') or {}).items():
            for m in marques:
                self.groupe_de[cle_marque(m)] = groupe

    # --- Formats (§ 5.5) ------------------------------------------------------
    def origine(self, reference: str) -> Origine:
        ref = (reference or '').strip()
        for regle in self.formats:
            if regle.motif.fullmatch(ref):
                return Origine(regle.origine, regle.doute, regle.motif.pattern)
        return Origine('')

    # --- Préfixes (§ 5.1) -----------------------------------------------------
    def sans_prefixe(self, ref_interne: str, attendue: str = '') -> Tuple[str, str]:
        """
        (référence, préfixe retiré). Avec `attendue` (code produit), seul un
        préfixe qui y mène est retenu ; sans elle (secours), le préfixe le plus
        long suivi d'un chiffre est retiré.
        """
        ref = (ref_interne or '').strip()
        haut = ref.upper()
        for p in self.prefixes:
            if not haut.startswith(p) or len(ref) <= len(p):
                continue
            reste = ref[len(p):]
            if attendue:
                if reste.upper() == attendue.upper():
                    return reste, p
            elif reste[0].isdigit():
                return reste, p
        return ref, ''

    # --- Catégorie → type (§ 5.6) ---------------------------------------------
    def type_de_categorie(self, categorie: str, types_connus: Dict[str, str]) -> str:
        """Type unique désigné par la catégorie ('' si aucun ou ambigu)."""
        if not categorie:
            return ''
        for candidat in (categorie, categorie.rsplit(' - ', 1)[-1]):
            cle = cle_marque(candidat)
            if cle in self.categories_types:
                return self.categories_types[cle]
            if cle in types_connus:
                return types_connus[cle]
        return ''

    # --- Groupes de marques ---------------------------------------------------
    def meme_groupe(self, marque_a: str, marque_b: str) -> bool:
        ga = self.groupe_de.get(cle_marque(marque_a))
        return bool(ga) and ga == self.groupe_de.get(cle_marque(marque_b))

    def groupe_origine(self, etiquette: str) -> str:
        """Groupe d'une étiquette d'origine (« Indesit » → « Whirlpool », « BSH » → « BSH »)."""
        cle = cle_marque(etiquette)
        if cle in self.groupe_de:
            return self.groupe_de[cle]
        for groupe in (self.donnees.get('groupes_marques') or {}):
            if cle_marque(groupe) == cle:
                return groupe
        return etiquette

    def marques_du_groupe(self, marque: str) -> List[str]:
        groupe = self.groupe_de.get(cle_marque(marque))
        if not groupe:
            return []
        return list((self.donnees.get('groupes_marques') or {}).get(groupe) or [])


def fusionner(defauts: Dict[str, Any], valeurs: Dict[str, Any]) -> Dict[str, Any]:
    """Les clés présentes dans `valeurs` remplacent celles des défauts (une par une)."""
    d = copy.deepcopy(defauts)
    for cle, val in (valeurs or {}).items():
        if cle in d and val is not None:
            d[cle] = copy.deepcopy(val)
    return d


def charger_configuration(chemin: Optional[Path] = None) -> ConfigurationRapprochement:
    """Configuration de data/reprise_fiches.json si présente et lisible, sinon les défauts."""
    chemin = Path(chemin) if chemin else CHEMIN_CONFIGURATION
    donnees: Dict[str, Any] = {}
    try:
        if chemin.exists():
            donnees = json.loads(chemin.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        donnees = {}
    return ConfigurationRapprochement(donnees if isinstance(donnees, dict) else {})
