"""
Référence associée Whirlpool / Indesit / Beko (CDC docs/cdc_import_fiches_site.md,
§ 10.12 et § 10.17, PR 4)

Une pièce Whirlpool (`48` + 10 chiffres), Indesit (`C00` + 6 chiffres) ou Beko
(10 chiffres en 17, 18, 28) a souvent une référence jumelle dans l'un des deux
autres groupes : `481073071153` et `C00319033`. L'import (PDF, CSV, collage,
fiche du site) la demande une fois : « référence associée », ou « aucune ».

La forme d'une référence se lit dans la table des formats de la configuration
(`ConfigurationRapprochement.origine`, § 5.5), lue sans jamais être écrite.

Origine déclarée (§ 10.17 bis) : une référence dont la forme n'est dans aucun de
ces groupes (Beko `210480241`, `S210480241`) peut être déclarée Whirlpool, Indesit
ou Beko par l'utilisateur ; la déclaration l'emporte sur la table des formats.
La base (`origines_declarees`) remplit le registre ci-dessous à l'ouverture et le
tient à jour à chaque écriture : les appels sans base en profitent.
Sans Qt, sans base.
"""

from functools import lru_cache
from typing import Dict, Mapping, Optional

# Groupes dont les références vont par paires
ORIGINES_ASSOCIEES = ('Whirlpool', 'Indesit', 'Beko')

# Registre des origines déclarées : référence → Whirlpool / Indesit / Beko
_ORIGINES_DECLAREES: Dict[str, str] = {}


def definir_origines_declarees(origines: Mapping[str, str]) -> None:
    """Remplace le registre (lecture de la base à l'ouverture)."""
    _ORIGINES_DECLAREES.clear()
    for ref, origine in (origines or {}).items():
        noter_origine_declaree(ref, origine)


def noter_origine_declaree(reference: str, origine: Optional[str]) -> None:
    """Ajoute (ou retire, origine vide) une déclaration au registre."""
    ref = (reference or '').strip()
    if not ref:
        return
    if origine in ORIGINES_ASSOCIEES:
        _ORIGINES_DECLAREES[ref] = origine
    else:
        _ORIGINES_DECLAREES.pop(ref, None)


def origine_declaree(reference: str) -> str:
    """Origine déclarée par l'utilisateur ('' = aucune déclaration)."""
    return _ORIGINES_DECLAREES.get((reference or '').strip(), '')


def origine_du_format(reference: str, config=None) -> str:
    """Whirlpool, Indesit ou Beko d'après la seule table des formats, sinon ''."""
    ref = (reference or '').strip()
    if not ref:
        return ''
    config = config if config is not None else _configuration()
    etiquette = config.origine(ref).etiquette
    return etiquette if etiquette in ORIGINES_ASSOCIEES else ''


@lru_cache(maxsize=1)
def _configuration():
    from src.utils.rapprochement_fiche.configuration import charger_configuration
    return charger_configuration()


def origine_associable(reference: str, config=None) -> str:
    """Whirlpool, Indesit ou Beko si la référence a été déclarée de l'un de ces
    groupes, ou en a la forme (on lui demande sa référence associée), sinon ''."""
    return origine_declaree(reference) or origine_du_format(reference, config)


def autres_origines(origine: str) -> str:
    """« Indesit ou Beko » pour Whirlpool, etc."""
    autres = [o for o in ORIGINES_ASSOCIEES if o != origine]
    return ' ou '.join(autres)


def valeur_associee(associee: Optional[str]) -> str:
    """Texte d'historique d'une réponse : la référence, ou « aucune »."""
    return associee if associee else 'aucune'
