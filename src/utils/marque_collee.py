"""
Marque collée dans une référence d'appareil (ménage des marques, 2026-11-24).

Des PDF fournisseurs écrivent la marque dans la référence : « SMEG ST995 » en
référence modèle, « ST995 SMEG » en référence commerciale (≈ 3 900 appareils en
base, une soixantaine de marques). La fiche du site affiche alors
« Smeg ST995 SMEG ».

Règle : un mot (ou une suite de mots) en tête ou en fin de référence, séparé par
un espace, est retiré **s'il est la marque de l'appareil**, comparé sans casse,
accents, espaces ni tirets (« GLEMGAS » = « Glem Gas »). Garde-fous :

- jamais collé sans espace (« SMEGST2FABBL2 » reste tel quel : « FAR123 »
  pourrait être une vraie référence Far) ;
- ce qui reste doit contenir un chiffre (une référence, pas un mot) ;
- un mot qui n'est pas la marque (« SOG » sur Haier, « WELCO » sur Welcome) ne
  bouge pas ;
- chauffage (`TypesAppareils.DESIGNATIONS_DE_GAMME`) : la référence commerciale
  est une désignation de gamme (« SAUTER VENISE VENTILO 1500 W »), jamais
  touchée ; sans type connu, une désignation (3 mots ou plus, le premier sans
  chiffre) ne l'est pas non plus.

Module pur : aucune dépendance Qt ni base. Utilisé par l'import (les deux
chemins) et par la liste figée du ménage (`scripts/menage_marques.py`).
"""

import re
import unicodedata
from typing import Optional

from ..core.constants import TypesAppareils

# Une marque de plus de trois mots n'existe pas en base
_MOTS_MAX = 3

_SEPARATEURS = re.compile(r"[\s\-_.&+']")


def cle_marque(valeur: str) -> str:
    """Même clé que `CasseNormalisationService` (sans casse, accents, espaces ni
    ponctuation de liaison), recopiée ici pour que `utils` ne dépende pas de
    `services`."""
    decomposee = unicodedata.normalize('NFKD', valeur or '')
    sans_accents = ''.join(c for c in decomposee if not unicodedata.combining(c))
    return _SEPARATEURS.sub('', sans_accents.lower())


def retirer_marque_collee(reference: Optional[str], marque: Optional[str],
                          type_appareil: Optional[str] = None) -> str:
    """Référence sans la marque collée en tête ou en fin ; inchangée sinon.

    Args:
        type_appareil: None = inconnu de l'appelant (aucune garde de type) ;
            '' = appareil sans type (garde « désignation ») ; sinon le type.

    >>> retirer_marque_collee('SMEG ST995', 'Smeg')
    'ST995'
    >>> retirer_marque_collee('XHD540IX GLEMGAS', 'Glem Gas')
    'XHD540IX'
    >>> retirer_marque_collee('SAUTER VENISE VENTILO 1500 W', 'Sauter', 'Chauffage')
    'SAUTER VENISE VENTILO 1500 W'
    """
    reference = (reference or '').strip()
    cle = cle_marque(marque or '')
    if not reference or not cle:
        return reference
    if (type_appareil or '').strip() in TypesAppareils.DESIGNATIONS_DE_GAMME:
        return reference
    mots = reference.split()
    if len(mots) < 2:
        return reference
    for n in range(1, min(_MOTS_MAX, len(mots) - 1) + 1):
        if cle_marque(''.join(mots[:n])) == cle:
            return _si_reference(mots[n:], reference, type_appareil)
        if cle_marque(''.join(mots[-n:])) == cle:
            return _si_reference(mots[:-n], reference, type_appareil)
    return reference


def _si_reference(reste: list, origine: str, type_appareil: Optional[str]) -> str:
    """Le reste s'il ressemble à une référence, sinon l'origine."""
    texte = ' '.join(reste)
    if not any(c.isdigit() for c in texte):
        return origine
    sans_type = type_appareil is not None and not type_appareil.strip()
    if sans_type and len(reste) >= 3 and not any(c.isdigit() for c in reste[0]):
        return origine          # désignation de gamme d'un appareil sans type
    return texte
