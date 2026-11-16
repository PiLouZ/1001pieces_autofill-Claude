"""
Paires de réf. associées dans les lignes d'une fiche du site
(CDC docs/cdc_import_fiches_site.md, § 5.4)

Sur les lignes « Remplace les références » et « Références équivalentes »,
une référence Whirlpool, Indesit ou Beko suivie d'une référence d'un autre de
ces groupes est sa jumelle : `480132102633 C00323671 480132102002 C00314426`,
ou au milieu d'autres marques, `93467637 72X0079 C00316028 481246688999`.
Chaque paire devient « réf. associées » l'une de l'autre, comme la paire du
code produit.

Lecture par suites : une suite est une série de références Whirlpool / Indesit
/ Beko qui se suivent dans la ligne (une autre marque la coupe). Une suite
est liée deux par deux (1ʳᵉ avec 2ᵉ, 3ᵉ avec 4ᵉ…) si elle a un nombre pair de
références, sans doublon, et que chaque paire réunit deux groupes différents.
Sinon la suite entière n'est pas liée (une référence manquante décalerait
toutes les paires suivantes) ; elle est montrée à l'aperçu avec sa raison.

Dans une paire, la principale est la référence du même groupe que la pièce ;
si la pièce n'est d'aucun des deux groupes, la première dans l'ordre du site.

Sans Qt, sans base.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Sequence, Tuple

from src.utils.rapprochement_fiche.associee import ORIGINES_ASSOCIEES

LIGNES = {'remplace': "Remplace", 'equivalentes': "Équivalentes"}

RAISONS_SUITE = {
    'impair': "nombre impair de références qui se suivent",
    'doublon': "une référence est citée deux fois",
    'meme_groupe': "deux références du même groupe côte à côte",
}

STATUTS_PAIRE = {
    'nouveau': "à lier",
    'deja_present': "déjà liées",
    'conflit': "non liée",
}


@dataclass
class PaireFiche:
    ligne: str                          # 'remplace' ou 'equivalentes'
    principale: str
    associee: str
    statut: str = ''                    # cf. STATUTS_PAIRE
    raison: str = ''                    # d'un conflit


@dataclass
class SuiteNonLiee:
    ligne: str
    references: List[str] = field(default_factory=list)
    raison: str = ''                    # cf. RAISONS_SUITE


def _suites(refs: Sequence[str], origine: Callable[[str], str]) -> List[List[str]]:
    suites, courante = [], []
    for ref in refs:
        if origine(ref) in ORIGINES_ASSOCIEES:
            courante.append(ref)
        elif courante:
            suites.append(courante)
            courante = []
    if courante:
        suites.append(courante)
    return suites


def paires_de_la_ligne(ligne: str, refs: Sequence[str], principale: str,
                       origine: Callable[[str], str]
                       ) -> Tuple[List[PaireFiche], List[SuiteNonLiee]]:
    """(paires, suites non liées) d'une ligne de la fiche. `origine(ref)` :
    étiquette du format (Whirlpool, Indesit, Beko…). Une référence seule
    entre deux autres marques n'est pas une suite à signaler."""
    groupe_piece = origine(principale) if principale else ''
    paires: List[PaireFiche] = []
    non_liees: List[SuiteNonLiee] = []
    vues = {principale} if principale else set()
    for suite in _suites(refs, origine):
        if len(suite) == 1:
            vues.update(suite)
            continue
        raison = ''
        if len(suite) % 2:
            raison = 'impair'
        elif len(set(suite)) != len(suite) or set(suite) & vues:
            raison = 'doublon'
        elif any(origine(suite[i]) == origine(suite[i + 1]) for i in range(0, len(suite), 2)):
            raison = 'meme_groupe'
        vues.update(suite)
        if raison:
            non_liees.append(SuiteNonLiee(ligne, list(suite), raison))
            continue
        for i in range(0, len(suite), 2):
            a, b = suite[i], suite[i + 1]
            if origine(b) == groupe_piece:
                a, b = b, a
            paires.append(PaireFiche(ligne, a, b))
    return paires, non_liees
