"""
Paires de « Remplace les références » (CDC docs/cdc_import_fiches_site.md, § 5.4)

Quand le code produit est une paire Whirlpool / Indesit / Beko
(`481010467690 C00380758`), la ligne « Remplace les références » d'une fiche
bien écrite va aussi par paires, dans l'ordre : la 1ʳᵉ référence avec la 2ᵉ,
la 3ᵉ avec la 4ᵉ, etc. (`480132102633 C00323671 480132102002 C00314426 …`).
Chaque paire est une référence et sa jumelle : elles deviennent « réf.
associées » l'une de l'autre, comme la paire du code produit.

Règle stricte, toute la ligne ou rien :
- le code produit compte exactement deux références, de deux groupes
  différents parmi Whirlpool, Indesit, Beko ;
- la ligne compte un nombre pair de références, sans doublon ;
- chaque paire (1-2, 3-4…) a une référence de chacun de ces deux groupes,
  dans un ordre ou dans l'autre.
Sinon, aucune paire n'est liée : une seule référence manquante décalerait
toutes les paires suivantes.

Dans une paire retenue, la référence du même groupe que la pièce est la
principale, l'autre l'associée (même sens que la paire du code produit).

Sans Qt, sans base.
"""

from dataclasses import dataclass
from typing import Callable, List, Sequence, Tuple

from src.utils.rapprochement_fiche.associee import ORIGINES_ASSOCIEES

# Pourquoi la ligne n'est pas lue par paires ('' = elle l'est)
RAISONS_SANS_PAIRES = {
    'code_produit': "le code produit n'est pas une paire Whirlpool / Indesit / Beko",
    'impair': "nombre impair de références",
    'doublon': "une référence est citée deux fois",
    'formes': "une paire n'a pas une référence de chaque marque du code produit",
}

STATUTS_PAIRE = {
    'nouveau': "paire à lier",
    'deja_present': "déjà liées",
    'conflit': "l'une des deux a déjà une autre réf. associée (ou « aucune »)",
}


@dataclass
class PaireRemplace:
    principale: str                     # même groupe que la pièce
    associee: str
    statut: str = ''                    # cf. STATUTS_PAIRE
    raison: str = ''


def paires_de_la_ligne(code_produit: Sequence[str], remplace: Sequence[str],
                       principale: str, origine: Callable[[str], str]
                       ) -> Tuple[List[PaireRemplace], str]:
    """(paires, raison) : les paires de la ligne « Remplace », ou [] et le code de
    la raison (cf. RAISONS_SANS_PAIRES). `origine(ref)` : étiquette du format
    (Whirlpool, Indesit, Beko…). Ligne vide : ([], '')."""
    if not remplace:
        return [], ''
    code = list(code_produit)
    origines_code = [origine(r) for r in code]
    if (len(code) != 2 or origines_code[0] == origines_code[1]
            or any(o not in ORIGINES_ASSOCIEES for o in origines_code)):
        return [], 'code_produit'
    groupe_piece = origine(principale)
    if groupe_piece not in origines_code:
        return [], 'code_produit'
    if len(remplace) % 2:
        return [], 'impair'
    if len(set(remplace)) != len(remplace) or set(remplace) & set(code):
        return [], 'doublon'
    attendues = set(origines_code)
    paires = []
    for i in range(0, len(remplace), 2):
        a, b = remplace[i], remplace[i + 1]
        oa, ob = origine(a), origine(b)
        if {oa, ob} != attendues:
            return [], 'formes'
        paires.append(PaireRemplace(a, b) if oa == groupe_piece else PaireRemplace(b, a))
    return paires, ''
