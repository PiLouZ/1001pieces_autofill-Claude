"""
Liste fermée des types d'appareils — règles de nomenclature (CDC § 3).

La liste vit dans `data/types_autorises.json`, **versionné** (contrairement à
`data/export_config.json`, propre à chaque poste) : elle doit être la même
partout et coller aux catégories du site. La changer = une PR, après création
du type côté site.

Lecteurs :
- lot 3 : contrôle à l'enregistrement d'une règle (une règle ne produit qu'un
  type de la liste) ;
- lot 5 : signalement, à l'import, d'un type hors liste (non bloquant).
"""

import json
from pathlib import Path
from typing import Optional, Tuple

from ..core.logger import app_logger

CHEMIN_TYPES_AUTORISES = Path(__file__).resolve().parents[2] / 'data' / 'types_autorises.json'


def charger_types_autorises(chemin: Optional[Path] = None) -> Tuple[str, ...]:
    """Types de la liste fermée, dans l'ordre du fichier.

    Fichier absent ou illisible : tuple vide (journalisé) — l'appelant refuse
    alors toute règle plutôt que d'en accepter n'importe laquelle.
    """
    chemin = Path(chemin) if chemin else CHEMIN_TYPES_AUTORISES
    try:
        donnees = json.loads(chemin.read_text(encoding='utf-8'))
        types = donnees.get('types') if isinstance(donnees, dict) else None
        if not isinstance(types, list):
            raise ValueError("clé « types » absente ou invalide")
        vus = []
        for t in types:
            if isinstance(t, str) and t.strip() and t.strip() not in vus:
                vus.append(t.strip())
        return tuple(vus)
    except (OSError, ValueError) as e:
        app_logger.error(f"Liste des types autorisés illisible ({chemin}) : {e}")
        return ()


def est_type_autorise(type_appareil: str, types_autorises: Tuple[str, ...]) -> bool:
    """Le type figure-t-il dans la liste, au caractère près (libellé du site) ?"""
    return bool(type_appareil) and type_appareil in types_autorises
