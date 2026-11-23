"""
Force d'une proposition de type (CDC § 7).

- **forte** : règle validée ET au moins un signal indépendant d'accord (2e clé,
  vote des pièces > 60 %, ou libellé d'origine), entre types **éloignés** ;
  proposée en tête de revue, acceptation groupée possible (D8) ;
- **simple** : règle seule, ou types **voisins** (froid, cuisson, linge : les
  pièces ne les départagent pas) ; revue ligne à ligne.

Le libellé d'origine (`other_ref`) n'est jamais un signal seul : il ne fait
que renforcer une règle validée (cas « Four Vapeur » des listes Whirlpool).
"""

import unicodedata
from collections import Counter
from typing import Optional

from ...core.constants import TypesAppareils

FORCE_FORTE = 'forte'
FORCE_SIMPLE = 'simple'
SEUIL_VOTE_PIECES = 0.60


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize('NFKD', texte or '')
    return ''.join(c for c in decompose if not unicodedata.combining(c)).casefold()


def sont_voisins(type_a: str, type_b: str) -> bool:
    """Deux types d'une même famille voisine (froid, cuisson, linge) ?"""
    return any(type_a in famille and type_b in famille
               for famille in TypesAppareils.FAMILLES_VOISINES)


def part_du_vote(votes: Optional[Counter], type_propose: str) -> Optional[float]:
    """Part des appareils partageant ses pièces qui ont le type proposé
    (None : aucune pièce partagée)."""
    total = sum((votes or {}).values())
    return (votes[type_propose] / total) if total else None


def libelle_d_accord(libelle: str, type_propose: str) -> bool:
    """Le libellé d'origine nomme-t-il le type proposé (sans casse ni accents) ?"""
    return bool(libelle and type_propose) and _sans_accents(type_propose) in _sans_accents(libelle)


def force_proposition(type_actuel: str, type_propose: str, deux_cles: bool,
                      part_vote: Optional[float], libelle_accord: bool) -> str:
    """Force d'une proposition issue d'une règle validée."""
    if type_actuel and sont_voisins(type_actuel, type_propose):
        return FORCE_SIMPLE
    signal = deux_cles or (part_vote is not None and part_vote > SEUIL_VOTE_PIECES) or libelle_accord
    return FORCE_FORTE if signal else FORCE_SIMPLE
