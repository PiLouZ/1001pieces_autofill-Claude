"""
Syntaxe des champs de filtre au-dessus des colonnes du tableau principal.

    WOI4S              contient WOI4S (comportement historique)
    WOI*               commence par WOI
    *S                 finit par S
    WOI?S*             WOI + un seul caractère + S, puis n'importe quoi
    WOI4S* | WOI5S*    l'un OU l'autre
    WOI* !WOI9*        commence par WOI, SAUF ceux qui commencent par WOI9

Règle : sans joker (* ou ?), un motif cherche « contient » ; avec un joker, il
décrit la valeur entière (comme les filtres d'Excel). Les exclusions « ! »
valent pour tout le champ : (A OU B) ET PAS C ET PAS D.

Le motif est traduit en LIKE (insensible à la casse, comme avant) avec un
caractère d'échappement : « % » et « _ » tapés au clavier sont cherchés tels
quels, ils ne servent plus de jokers cachés.
"""

import re
from typing import List, Optional, Tuple

# Caractère d'échappement des LIKE produits ici
_ECHAPPEMENT = '\\'

# Une exclusion commence par « ! » en début de motif ou après un espace :
# « Attention! » reste un texte ordinaire.
_DEBUT_EXCLUSION = re.compile(r'\s+(?=!)')


def motif_vers_like(motif: str) -> str:
    """Traduire un motif saisi (jokers * et ?) en motif LIKE échappé.

    Sans joker : « contient » (%motif%). Avec joker : valeur entière.
    """
    echappe = (motif.replace(_ECHAPPEMENT, _ECHAPPEMENT * 2)
               .replace('%', _ECHAPPEMENT + '%')
               .replace('_', _ECHAPPEMENT + '_'))
    if '*' in motif or '?' in motif:
        return echappe.replace('*', '%').replace('?', '_')
    return f'%{echappe}%'


def analyser_filtre(texte: str) -> Tuple[List[str], List[str]]:
    """Découper la saisie en (motifs à inclure, motifs à exclure).

    « | » (ou « || ») sépare les alternatives ; un motif précédé de « ! »
    (en début de champ ou après un espace) est une exclusion.
    """
    inclus, exclus = [], []
    for alternative in re.split(r'\|+', texte or ''):
        for morceau in _DEBUT_EXCLUSION.split(alternative.strip()):
            morceau = morceau.strip()
            if morceau.startswith('!'):
                morceau = morceau[1:].strip()
                if morceau:
                    exclus.append(morceau)
            elif morceau:
                inclus.append(morceau)
    return inclus, exclus


def condition_filtre_colonne(colonne_sql: str, texte: str) -> Optional[Tuple[str, List[str]]]:
    """Condition SQL (et ses paramètres) d'un champ de filtre de colonne.

    `colonne_sql` est l'expression de colonne déjà validée par l'appelant
    (ex. « a.[ref_modele] »). Renvoie None si la saisie ne filtre rien
    (vide, « | » ou « ! » seuls).
    """
    inclus, exclus = analyser_filtre(texte)
    morceaux, params = [], []

    if inclus:
        alternatives = [f"{colonne_sql} LIKE ? ESCAPE '{_ECHAPPEMENT}'" for _ in inclus]
        morceaux.append(alternatives[0] if len(alternatives) == 1
                        else '(' + ' OR '.join(alternatives) + ')')
        params.extend(motif_vers_like(m) for m in inclus)

    for motif in exclus:
        # IFNULL : un champ vide (NULL) n'est pas « WOI9… », il reste affiché
        morceaux.append(f"IFNULL({colonne_sql}, '') NOT LIKE ? ESCAPE '{_ECHAPPEMENT}'")
        params.append(motif_vers_like(motif))

    if not morceaux:
        return None
    return ' AND '.join(morceaux), params


# Aide des champs de filtre : bulle au survol d'un champ et fenêtre du bouton « ? »
# (une seule source)
_EXEMPLES_AIDE = [
    ("WOI4S", "contient WOI4S"),
    ("WOI*", "commence par WOI"),
    ("*S", "finit par S"),
    ("WOI?S*", "<code>?</code> = un seul caractère (WOI4S…, WOI5S…)"),
    ("WOI4S* | WOI5S*", "l'un <b>ou</b> l'autre"),
    ("WOI* !WOI9*", "<b>sauf</b> ceux qui commencent par WOI9"),
]

AIDE_FILTRE_COLONNE = (
    "<b>Recherche dans les filtres de colonne</b>"
    "<table cellspacing='0' cellpadding='3' style='margin-top:6px'>"
    + "".join(f"<tr><td><code><b>{saisie}</b></code></td><td>&nbsp;{sens}</td></tr>"
              for saisie, sens in _EXEMPLES_AIDE)
    + "</table>"
    "<p style='margin-top:6px'>Sans <code>*</code> ni <code>?</code> : « contient ».<br>"
    "Avec : le motif décrit la valeur entière<br>"
    "(<code>WOI*S</code> = commence par WOI <b>et</b> finit par S).<br>"
    "Majuscules et minuscules confondues.</p>"
)
