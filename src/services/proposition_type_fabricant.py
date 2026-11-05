"""Proposition Type / Fabricant d'un appareil d'après ses références — règle unique.

Partagée par l'import (chemin standard, `ImportManager._try_auto_complete`) et par
le bouton « Données → Autocomplétion » (`DataManagementService`). Auparavant chacun
portait sa copie de la requête, et celle du bouton n'avait pas suivi la v3.89.0 :
elle prenait des auto-complétés non vérifiés comme source et ne disait pas d'où
venait la valeur proposée.

Règle :
- correspondance exacte sur les références non vides (ref_modele, commercial_ref) ;
- seuls les appareils ayant Type ET Fabricant servent de source ;
- un appareil auto-complété non encore vérifié ne sert pas de source : sa valeur
  n'est qu'une déduction, la recompter gonflerait la confiance (« 3/3 » pour « 1/1 ») ;
- la combinaison la plus fréquente l'emporte, ex aequo départagés par valeur
  (choix reproductible) ; l'accord / total donne l'indice de confiance tracé.

Pur Python : lit via `db_manager.execute_query`, n'écrit rien.
"""

from dataclasses import dataclass
from typing import Any, Dict

# Champs que la règle sait compléter, dans l'ordre d'application.
CHAMPS_PROPOSABLES = ('type', 'manufacturer')


@dataclass(frozen=True)
class PropositionChamp:
    """Valeur proposée pour un champ vide, avec sa provenance."""
    valeur: str
    source: str     # référence d'un appareil source (exemple affiché à la revue)
    accord: int     # appareils sources donnant cette valeur
    total: int      # appareils sources trouvés


def proposer_type_fabricant(db_manager, appareil_data: Dict[str, Any]) -> Dict[str, PropositionChamp]:
    """Propositions pour les champs Type / Fabricant VIDES de l'appareil.

    Args:
        db_manager: expose `execute_query(query, params)`.
        appareil_data: champs de l'appareil (au moins type, manufacturer,
            ref_modele, commercial_ref ; valeurs absentes ou None = vides).
    Returns:
        {champ: PropositionChamp} pour chaque champ vide complétable ; {} si les
        deux champs sont remplis, si aucune référence n'est renseignée ou si
        aucun appareil source ne correspond.
    """
    vides = [champ for champ in CHAMPS_PROPOSABLES
             if not str(appareil_data.get(champ) or '').strip()]
    if not vides:
        return {}

    conditions = []
    params = []
    for colonne in ('ref_modele', 'commercial_ref'):
        valeur = str(appareil_data.get(colonne) or '').strip()
        if valeur:
            conditions.append(f'{colonne} = ?')
            params.append(valeur)
    if not conditions:
        return {}

    query = f"""
        SELECT type, manufacturer, COUNT(*) as freq,
               MIN(COALESCE(NULLIF(ref_modele, ''), commercial_ref)) AS exemple
        FROM appareils
        WHERE ({' OR '.join(conditions)})
          AND type IS NOT NULL AND type != ''
          AND manufacturer IS NOT NULL AND manufacturer != ''
          AND id NOT IN (SELECT appareil_id FROM appareils_autocompletes)
        GROUP BY type, manufacturer
        ORDER BY freq DESC, type, manufacturer
    """
    resultats = db_manager.execute_query(query, params)
    if not resultats:
        return {}

    gagnante = resultats[0]
    exemple = gagnante[3]
    total = sum(r[2] for r in resultats)
    position = {'type': 0, 'manufacturer': 1}
    propositions = {}
    for champ in vides:
        valeur = gagnante[position[champ]]
        accord = sum(r[2] for r in resultats if r[position[champ]] == valeur)
        propositions[champ] = PropositionChamp(valeur, exemple or '', accord, total)
    return propositions
