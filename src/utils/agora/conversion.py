"""
Réponses d'Agora → lignes de l'import habituel, prix et code produit EMG.

Lignes d'appareils : une par couple (réf. technique, réf. commerciale), avec la
marque et le type lus dans le référentiel produits MySpace quand il les connaît.
Elles passent ensuite par l'import comme un collage : orthographe alignée,
auto-complétion, règles de nomenclature (un type lu ici est un « type du
fichier » : une règle qui le contredit fait une proposition, CDC nomenclature D18).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

# En-têtes reconnus par la fenêtre d'import (détection des en-têtes du collage)
ENTETES = ['Ref technique', 'Ref commerciale', 'Marque', 'Type']

# Désignation du référentiel produits (français) → type de l'outil ; 1re règle qui s'applique
_TYPES = [
    ('lave-vaisselle', 'Lave-vaisselle'), ('lave vaisselle', 'Lave-vaisselle'),
    ('lavante', 'Lavante-séchante'), ('lave-linge', 'Lave-linge'), ('lave linge', 'Lave-linge'),
    ('machine a laver', 'Lave-linge'), ('seche-linge', 'Sèche-linge'), ('seche linge', 'Sèche-linge'),
    ('micro-ondes', 'Micro-ondes'), ('micro ondes', 'Micro-ondes'),
    ('four', 'Four'), ('cuisiniere', 'Cuisinière'), ('table de cuisson', 'Plaque'),
    ('tables / plaques', 'Plaque'), ('plaque', 'Plaque'), ('hotte', 'Hotte'),
    ('congel', 'Congélateur'), ('combine', 'Réfrigérateur'), ('refrig', 'Réfrigérateur'),
    ('frigo', 'Réfrigérateur'), ('cave a vin', 'Cave à vin'), ('aspirateur', 'Aspirateur'),
]
# Marques génériques du référentiel : pas une marque d'appareil
_MARQUES_VIDES = {'autresmarques', 'autremarque', 'divers', ''}


def sans_accents(texte: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texte or '')
                   if unicodedata.category(c) != 'Mn')


def cle_marque(marque: str) -> str:
    return re.sub(r'[^a-z]', '', sans_accents((marque or '').lower()))


def type_depuis_designation(designation: str) -> str:
    """Type d'appareil d'après la désignation du référentiel ('' si inconnu)."""
    d = sans_accents((designation or '').lower())
    for motif, type_ in _TYPES:
        if motif in d:
            return type_
    return ''


def marque_canonique(marque: str, marques_connues: Dict[str, str]) -> str:
    """Écriture de l'outil pour une marque Agora (« FAURE ELECTROLUX » → « Faure »,
    « LIEBHERR Appliances » → « Liebherr ») ; '' pour une marque générique.
    `marques_connues` : clé (cle_marque) → écriture en base."""
    if cle_marque(marque) in _MARQUES_VIDES:
        return ''
    m = re.sub(r'\s+appliances$', '', (marque or '').strip(), flags=re.I)
    for essai in (m, re.sub(r'\s*electrolux$', '', m, flags=re.I), m.replace(' ', '-')):
        if cle_marque(essai) in marques_connues:
            return marques_connues[cle_marque(essai)]
    return m.title() if m.isupper() else m


_MOTS_NEUTRES = {'france', 'label', 'private', 'oem', 'autres', 'marques', 'export'}


def marque_dans_designation(designation: str, marques_connues: Dict[str, str]) -> str:
    """Marque connue de l'outil citée dans la désignation, pour les appareils que
    le référentiel range sous « Autres marques » (« Kg1840 ALTUs » → Altus,
    « ECC 351b EssENTIELB_FRANCE » → Essentiel-B, « 49 VLE BLgRUNDIg » → Grundig).
    Seules les marques déjà en base sont reconnues : rien n'est inventé."""
    mots = [cle_marque(m) for m in re.split(r'[\s_()\[\]/*,;-]+', designation or '')]
    mots = [m for m in mots if m and m not in _MOTS_NEUTRES]
    candidats = mots + [a + b for a, b in zip(mots, mots[1:])]
    for c in candidats:
        if len(c) >= 4 and c in marques_connues:
            return marques_connues[c]
    for c in mots:          # marque collée à un code (« BFgRUNDIg »)
        for cle, marque in marques_connues.items():
            if len(cle) >= 6 and c != cle and c.endswith(cle):
                return marque
    return ''


@dataclass
class LignesAppareils:
    lignes: List[List[str]] = field(default_factory=list)   # sans l'en-tête
    sans_marque: int = 0
    sans_type: int = 0

    def avec_entetes(self) -> List[List[str]]:
        return [list(ENTETES)] + self.lignes


def lignes_appareils(cas: Iterable[dict],
                     referentiel: Callable[[List[Tuple[str, str]]], Dict[Tuple[str, str], Tuple[str, str]]],
                     marques_connues: Dict[str, str]) -> LignesAppareils:
    """`cas` : réponse de getsparepartusecases ; `referentiel(appareils)` →
    {(tech, com): (marque, désignation)} (FamillesMySpace.produits)."""
    vus, couples, descriptions = set(), [], {}
    for c in cas or ():
        tech = (c.get('TechnicalReference') or '').strip()
        com = (c.get('CommercialReference') or '').strip()
        if not tech and not com:
            continue
        cle = (tech.upper(), com.upper())
        if cle in vus:
            continue
        vus.add(cle)
        couples.append((tech, com))
        descriptions[(tech, com)] = c.get('Description') or ''
    infos = referentiel(couples) if couples else {}
    resultat = LignesAppareils()
    for tech, com in couples:
        marque_agora, designation = infos.get((tech, com), ('', ''))
        marque = (marque_canonique(marque_agora, marques_connues)
                  or marque_dans_designation(designation, marques_connues))
        # Type : désignation du référentiel, sinon description du cas d'usage
        # (souvent « Cuisiniere électrique », parfois la seule réf. commerciale)
        type_ = type_depuis_designation(designation) or type_depuis_designation(descriptions[(tech, com)])
        resultat.sans_marque += not marque
        resultat.sans_type += not type_
        resultat.lignes.append([tech or com, com, marque, type_])
    return resultat


def libelle_piece(description: str) -> str:
    """Libellé proposé d'après la désignation Agora, à relire : « panneau,blanc »
    → « Panneau » ; « Serrure electro-ma. 0437 » → « Serrure » ; on s'arrête au
    premier code technique (chiffre, / ou \\) et on retire les mots abrégés."""
    d = (description or '').split(',')[0].replace('+', ' + ')
    mots = []
    for mot in d.split():
        if re.search(r'[\d/\\]', mot):
            break
        if mot.endswith('.'):
            continue
        mots.append(mot)
    d = ' '.join(mots).strip(' +')
    if d.isupper():
        d = d.lower()
    return d[:1].upper() + d[1:]


# --- Prix (règles EMG, Pierre-Louis 2026-11-26) ------------------------------------------

COEFFICIENT = 2.0                 # prix de vente TTC = prix d'achat × 2, arrondi au dixième
ELECTROLUX = 3
REMISE_ELECTROLUX = 0.33          # Electrolux : prix d'achat = prix public − 33 %


@dataclass
class Prix:
    achat_ht: Optional[float]
    vente: Optional[float]
    regle: str
    public: Optional[float] = None
    alerte: str = ''


def arrondi_dixieme(valeur: float) -> float:
    """Prix TTC du site, arrondi au dixième (Pierre-Louis, 2026-11-26) : 29,57 → 29,60."""
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(str(valeur)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def prix_emg(info: dict, constructeur: int, coefficient: float = COEFFICIENT) -> Prix:
    """Prix de vente TTC d'une pièce d'après getsparepartinfo."""
    info = info or {}
    public = info.get('PublicPrice')
    if constructeur == ELECTROLUX and public:
        achat, regle = round(public * (1 - REMISE_ELECTROLUX), 4), "prix public − 33 % × 2"
    else:
        achat, regle = info.get('DiscountPrice'), "prix remisé × 2"
    if not achat:
        return Prix(None, None, "aucun prix chez Agora", public)
    vente = arrondi_dixieme(achat * coefficient)
    alerte = ''
    if public and vente > public * 1.3:
        alerte = f"au-dessus du prix public Agora ({public:.2f} €) de plus de 30 %"
    return Prix(achat, vente, regle, public, alerte)


# --- Code produit EMG (= référence PrestaShop = code Cogilog) -----------------------------

def code_emg_propose(ref: str, constructeur: Optional[int], regles=None) -> Optional[str]:
    """Code proposé pour une fiche nouvelle, d'après les règles des codes produit
    (src/utils/agora/codes.py). Modifiable : la référence interne n'est pas
    déductible de façon sûre (CDC reprise § 5.8). None : aucune règle."""
    from .codes import code_produit
    return code_produit(ref, constructeur, regles)
