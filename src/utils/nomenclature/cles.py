"""
Clés normalisées d'un appareil pour les règles de nomenclature (CDC § 6.1).

- clé `nom`  : réf. commerciale (à défaut, réf. modèle sans son suffixe
  « /01 »), en majuscules, sans espaces ni ponctuation, si elle contient une
  lettre (« HM633GBS1 », « GO4W264 ») ;
- clé `code` : réf. modèle (à défaut, réf. commerciale) entièrement numérique,
  d'au moins 6 chiffres (PNC Electrolux, 12NC Whirlpool : « 857700329500 »).

Mêmes clés que la liste figée du lot 2 : les règles du « Four combiné
micro-ondes » la retrouvent exactement.
"""

import re

CLE_NOM = 'nom'
CLE_CODE = 'code'
CLES = (CLE_NOM, CLE_CODE)

LONGUEUR_MIN_CODE = 6
_HORS_CLE = re.compile(r'[^A-Z0-9]')
_LETTRE = re.compile(r'[A-Z]')


def normaliser_reference(reference: str) -> str:
    """« HM 633 GBS1 » → « HM633GBS1 »."""
    return _HORS_CLE.sub('', (reference or '').upper())


def cle_nom(ref_modele: str, commercial_ref: str) -> str:
    """Clé `nom`, ou '' si la référence ne contient aucune lettre."""
    cle = normaliser_reference(commercial_ref) or normaliser_reference((ref_modele or '').split('/')[0])
    return cle if _LETTRE.search(cle) else ''


def cle_code(ref_modele: str, commercial_ref: str) -> str:
    """Clé `code`, ou '' si aucune des deux références n'est un code usine."""
    for reference in (ref_modele, commercial_ref):
        cle = normaliser_reference(reference)
        if cle.isdigit() and len(cle) >= LONGUEUR_MIN_CODE:
            return cle
    return ''
