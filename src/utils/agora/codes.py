"""
Règles du code produit EMG (référence PrestaShop = code Cogilog) d'une fiche nouvelle.

Une règle : constructeurs Agora concernés (vide = tous), motif de la référence
(jokers * et ?, comme les règles de nomenclature ; vide = toutes), texte à retirer
au début, préfixe. La première règle qui s'applique donne le code ; aucune : pas
de code proposé. Le code se calcule sur la référence la plus récente (Pierre-Louis,
2026-11-26), qu'elle soit Beko ou Indesit.

Règles par défaut ci-dessous ; celles de l'utilisateur sont dans
`data/regles_codes.json` (propre au poste, non suivi par git), modifiées par la
fenêtre « Règles des codes produit » (src/ui/agora_regles_codes.py).
"""

import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class RegleCode:
    nom: str
    prefixe: str = ''
    constructeurs: List[int] = field(default_factory=list)
    motif: str = ''
    retirer: str = ''

    def s_applique(self, ref: str, constructeur: Optional[int]) -> bool:
        if self.constructeurs and constructeur not in self.constructeurs:
            return False
        return not self.motif or fnmatch.fnmatchcase(ref.upper(), self.motif.strip().upper())

    def code(self, ref: str) -> str:
        if self.retirer and ref.upper().startswith(self.retirer.upper()):
            ref = ref[len(self.retirer):]
        return self.prefixe + ref


REGLES_PAR_DEFAUT = [
    RegleCode("Indesit (C00 + 6 chiffres), Whirlpool ou Beko", 'SCS', [], 'C00??????', 'C00'),
    RegleCode("Electrolux", 'EL', [3]),
    RegleCode("BSH (sans le 00 de tête)", 'GAU', [4], '', '00'),
    RegleCode("Miele", 'MIE', [5]),
    RegleCode("Beko", 'BEO', [17]),
    RegleCode("Liebherr", 'LH', [22, 37]),
    RegleCode("Candy / Hoover", 'ROS', [33]),
    RegleCode("Whirlpool (sans préfixe)", '', [2]),
]


def chemin_regles() -> str:
    from src.core.config import Config
    return os.path.join(os.path.dirname(os.path.abspath(Config.DB_FILE)), 'regles_codes.json')


def charger_regles(chemin: Optional[str] = None) -> List[RegleCode]:
    chemin = chemin or chemin_regles()
    if not os.path.exists(chemin):
        return [RegleCode(**asdict(r)) for r in REGLES_PAR_DEFAUT]
    with open(chemin, encoding='utf-8') as f:
        return [RegleCode(**r) for r in json.load(f).get('regles', [])]


def enregistrer_regles(regles: List[RegleCode], chemin: Optional[str] = None) -> None:
    with open(chemin or chemin_regles(), 'w', encoding='utf-8') as f:
        json.dump({'regles': [asdict(r) for r in regles]}, f, ensure_ascii=False, indent=1)


def code_produit(ref: str, constructeur: Optional[int],
                 regles: Optional[List[RegleCode]] = None) -> Optional[str]:
    """Code proposé (modifiable) ; None si aucune règle ne s'applique."""
    ref = re.sub(r'\s+', '', ref or '')
    if not ref:
        return None
    for regle in (charger_regles() if regles is None else regles):
        if regle.s_applique(ref, constructeur):
            return regle.code(ref)
    return None
