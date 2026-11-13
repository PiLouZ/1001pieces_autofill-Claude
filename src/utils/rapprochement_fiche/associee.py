"""
Référence associée Whirlpool / Indesit / Beko (CDC docs/cdc_import_fiches_site.md,
§ 10.12 et § 10.17, PR 4)

Une pièce Whirlpool (`48` + 10 chiffres), Indesit (`C00` + 6 chiffres) ou Beko
(10 chiffres en 17, 18, 28) a souvent une référence jumelle dans l'un des deux
autres groupes : `481073071153` et `C00319033`. L'import (PDF, CSV, collage,
fiche du site) la demande une fois : « référence associée », ou « aucune ».

La forme d'une référence se lit dans la table des formats de la configuration
(`ConfigurationRapprochement.origine`, § 5.5), lue sans jamais être écrite.
Sans Qt, sans base.
"""

from functools import lru_cache
from typing import Optional

# Groupes dont les références vont par paires
ORIGINES_ASSOCIEES = ('Whirlpool', 'Indesit', 'Beko')


@lru_cache(maxsize=1)
def _configuration():
    from src.utils.rapprochement_fiche.configuration import charger_configuration
    return charger_configuration()


def origine_associable(reference: str, config=None) -> str:
    """Whirlpool, Indesit ou Beko si la référence a la forme de l'un de ces
    groupes (on lui demande sa référence associée), sinon ''."""
    ref = (reference or '').strip()
    if not ref:
        return ''
    config = config if config is not None else _configuration()
    etiquette = config.origine(ref).etiquette
    return etiquette if etiquette in ORIGINES_ASSOCIEES else ''


def autres_origines(origine: str) -> str:
    """« Indesit ou Beko » pour Whirlpool, etc."""
    autres = [o for o in ORIGINES_ASSOCIEES if o != origine]
    return ' ou '.join(autres)


def valeur_associee(associee: Optional[str]) -> str:
    """Texte d'historique d'une réponse : la référence, ou « aucune »."""
    return associee if associee else 'aucune'
