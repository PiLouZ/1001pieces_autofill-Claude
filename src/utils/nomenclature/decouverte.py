"""
Découverte automatique de règles candidates (CDC § 6.3).

Pour chaque marque, puis chaque groupe de marques, et pour chacune des deux
clés : descente dans l'arbre des préfixes ; on s'arrête au premier préfixe
assez pur. Les candidates sortent en statut « proposée » : elles ne typent
rien tant qu'un humain ne les a pas validées (D4, D7).

Garde-fous :
- préfixe ≥ 2 caractères pour une marque, ≥ 3 pour un groupe ; préfixe
  numérique (clé `code`) ≥ 4 chiffres ;
- ≥ 20 appareils et ≥ 95 % de pureté, tenus sur chacune des deux moitiés
  (validation croisée : la moitié paire des identifiants apprend, l'impaire
  vérifie, et réciproquement) ;
- pas de règle « contient » : préfixes et positions seulement ;
- zone grise : un préfixe (à longueur utile) sans type > 85 % n'engendre
  aucune règle à son niveau, ni règle de position : il attend une source
  extérieure (§ 9). La descente continue (« AK » mélangé n'empêche pas
  « AKP » pur), mais une règle trouvée en dessous porte le nom de sa zone
  grise (`zone_grise`), pour que la revue la regarde de près ;
- entre 85 % et 95 % : on cherche un caractère, à une position proche, qui
  départage les types (« EW?F* », « HBC??D* ») ;
- types accessoires (D9) : ni sources, ni résultats.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ...core.constants import TypesAppareils
from ..lecteur_fiche.lecteur import cle_marque
from .cles import CLE_CODE, CLE_NOM
from .moteur import PORTEE_GROUPE, PORTEE_MARQUE

SEUIL_PURETE = 0.95
SEUIL_ZONE_GRISE = 0.85
APPAREILS_MIN = 20
LONGUEUR_MIN = {(PORTEE_MARQUE, CLE_NOM): 2, (PORTEE_GROUPE, CLE_NOM): 3,
                (PORTEE_MARQUE, CLE_CODE): 4, (PORTEE_GROUPE, CLE_CODE): 4}
LONGUEUR_MAX = {CLE_NOM: 8, CLE_CODE: 10}
# Positions essayées après le préfixe pour départager des types (EW + ? + F)
ECART_POSITION_MAX = 3
# Part du préfixe que les règles de position doivent couvrir pour être retenues
COUVERTURE_POSITION_MIN = 0.90

# (identifiant, clé, type)
Element = Tuple[int, str, str]


@dataclass(frozen=True)
class RegleCandidate:
    portee: str
    cible: str
    cle: str
    motif: str
    type_resultat: str
    couverture: int
    accord: int
    zone_grise: str = ''      # préfixe mélangé au-dessus de la règle ('' = aucun)

    @property
    def purete(self) -> float:
        return self.accord / self.couverture if self.couverture else 0.0


@dataclass(frozen=True)
class ZoneGrise:
    portee: str
    cible: str
    cle: str
    prefixe: str
    repartition: Tuple[Tuple[str, int], ...]


def _majoritaire(elements: List[Element]) -> Tuple[str, int]:
    return Counter(t for _, _, t in elements).most_common(1)[0]


def _tient_en_validation_croisee(elements: List[Element], type_attendu: str) -> bool:
    """Le type majoritaire et la pureté tiennent sur chaque moitié."""
    for reste in (0, 1):
        moitie = [e for e in elements if e[0] % 2 == reste]
        if len(moitie) < APPAREILS_MIN // 2:
            return False
        type_m, nb = _majoritaire(moitie)
        if type_m != type_attendu or nb / len(moitie) < SEUIL_PURETE:
            return False
    return True


def _regle_si_pure(elements: List[Element]) -> Optional[Tuple[str, int]]:
    if len(elements) < APPAREILS_MIN:
        return None
    type_m, nb = _majoritaire(elements)
    if nb / len(elements) >= SEUIL_PURETE and _tient_en_validation_croisee(elements, type_m):
        return type_m, nb
    return None


class _Descente:
    def __init__(self, portee: str, cible: str, cle: str):
        self.portee, self.cible, self.cle = portee, cible, cle
        self.lmin = LONGUEUR_MIN[(portee, cle)]
        self.lmax = LONGUEUR_MAX[cle]
        self.regles: List[RegleCandidate] = []
        self.zones: List[ZoneGrise] = []

    def _ajouter(self, motif: str, elements: List[Element], type_m: str, nb: int, zone: str):
        self.regles.append(RegleCandidate(self.portee, self.cible, self.cle, motif, type_m,
                                          len(elements), nb, zone))

    def _positions(self, prefixe: str, elements: List[Element], zone: str) -> bool:
        """Règles « prefixe + ?… + caractère » si une position départage le préfixe."""
        long = len(prefixe)
        for j in range(long, min(long + ECART_POSITION_MAX, self.lmax)):
            par_car: Dict[str, List[Element]] = {}
            for e in elements:
                if len(e[1]) > j:
                    par_car.setdefault(e[1][j], []).append(e)
            trouvees = []
            for car, sous in par_car.items():
                pure = _regle_si_pure(sous)
                if pure:
                    trouvees.append((prefixe + '?' * (j - long) + car + '*', sous, *pure))
            couvert = sum(len(s) for _, s, _, _ in trouvees)
            if len({t for _, _, t, _ in trouvees}) >= 2 and couvert >= COUVERTURE_POSITION_MIN * len(elements):
                for motif, sous, type_m, nb in trouvees:
                    self._ajouter(motif, sous, type_m, nb, zone)
                return True
        return False

    def descendre(self, prefixe: str, elements: List[Element], zone: str = ''):
        if len(elements) < APPAREILS_MIN:
            return
        if len(prefixe) >= self.lmin:
            type_m, nb = _majoritaire(elements)
            part = nb / len(elements)
            if part >= SEUIL_PURETE:
                if _tient_en_validation_croisee(elements, type_m):
                    self._ajouter(prefixe + '*', elements, type_m, nb, zone)
                    return
            elif part < SEUIL_ZONE_GRISE:
                self.zones.append(ZoneGrise(
                    self.portee, self.cible, self.cle, prefixe,
                    tuple(Counter(t for _, _, t in elements).most_common())))
                zone = zone or prefixe
            elif self._positions(prefixe, elements, zone):
                return
        if len(prefixe) >= self.lmax:
            return
        enfants: Dict[str, List[Element]] = {}
        long = len(prefixe)
        for e in elements:
            if len(e[1]) > long:
                enfants.setdefault(e[1][long], []).append(e)
        for car in sorted(enfants):
            self.descendre(prefixe + car, enfants[car], zone)


def decouvrir(appareils: Iterable[Tuple[int, str, str, str, str]],
              groupe_de: Callable[[str], str]) -> Tuple[List[RegleCandidate], List[ZoneGrise]]:
    """Règles candidates et zones grises.

    Args:
        appareils: (id, marque, type, clé nom, clé code), clés déjà normalisées.
        groupe_de: marque → nom de son groupe ('' si aucun).
    """
    par_cible: Dict[Tuple[str, str, str], List[Element]] = {}
    noms: Dict[Tuple[str, str], str] = {}   # (portée, clé de marque) → nom affiché
    for ident, marque, type_app, k_nom, k_code in appareils:
        type_app = (type_app or '').strip()
        if not marque or not type_app or type_app in TypesAppareils.ACCESSOIRES:
            continue
        m = cle_marque(marque)
        noms.setdefault((PORTEE_MARQUE, m), marque)
        groupe = groupe_de(marque)
        if groupe:
            noms.setdefault((PORTEE_GROUPE, cle_marque(groupe)), groupe)
        for cle, valeur in ((CLE_NOM, k_nom), (CLE_CODE, k_code)):
            if not valeur:
                continue
            par_cible.setdefault((PORTEE_MARQUE, m, cle), []).append((ident, valeur, type_app))
            if groupe:
                par_cible.setdefault((PORTEE_GROUPE, cle_marque(groupe), cle), []).append(
                    (ident, valeur, type_app))
    regles: List[RegleCandidate] = []
    zones: List[ZoneGrise] = []
    for (portee, cible, cle), elements in sorted(par_cible.items()):
        if len(elements) < APPAREILS_MIN:
            continue
        descente = _Descente(portee, noms[(portee, cible)], cle)
        descente.descendre('', elements)
        regles += descente.regles
        zones += descente.zones
    return regles, zones
