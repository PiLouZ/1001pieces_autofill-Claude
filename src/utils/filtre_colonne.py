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


# ── Motifs des règles de nomenclature (CDC docs/cdc_regles_nomenclature.md § 6.1) ──
#
# Mêmes jokers que les filtres (« ? » = un caractère, « * » = n'importe quoi),
# plus « # » = un chiffre, « @ » = une lettre et les classes « [3-6] », « [KEP] ».
# Un motif de règle décrit une clé normalisée (majuscules, sans espaces ni
# ponctuation) : il est TOUJOURS ancré au début, « * » n'est admis qu'à la fin,
# et sans « * » il décrit la clé entière (gabarit). Pas de « | » ni de « ! » :
# une règle = un motif ; une exception s'écrit par une règle plus précise.

FORME_PREFIXE = 'prefixe'     # AKZ*
FORME_POSITION = 'position'   # EW?F*, HBC8[3-6][KEP]*
FORME_GABARIT = 'gabarit'     # HSG###@@#  (clé entière)
# Rang de spécificité : gabarit > position > préfixe (§ 6.2)
RANG_FORME = {FORME_PREFIXE: 0, FORME_POSITION: 1, FORME_GABARIT: 2}

_MOTIF_REGLE = re.compile(r'(?:[A-Z0-9#@?]|\[(?:[A-Z0-9](?:-[A-Z0-9])?)+\])+\*?')


class MotifRegleInvalide(ValueError):
    """Motif de règle hors syntaxe (message en français)."""


def valider_motif_regle(motif: str) -> str:
    """Motif normalisé (majuscules, sans espaces), ou MotifRegleInvalide."""
    m = (motif or '').strip().upper()
    if not m or m == '*':
        raise MotifRegleInvalide("motif vide")
    if not _MOTIF_REGLE.fullmatch(m):
        raise MotifRegleInvalide(
            f"motif « {motif} » invalide : lettres, chiffres, # @ ? et classes [..], "
            "« * » seulement à la fin")
    for classe in re.findall(r'\[([^\]]*)\]', m):
        for debut, fin in re.findall(r'(\w)-(\w)', classe):
            if debut > fin or debut.isdigit() != fin.isdigit():
                raise MotifRegleInvalide(f"classe « [{classe}] » invalide dans « {motif} »")
    return m


def forme_motif_regle(motif: str) -> str:
    """Forme d'un motif valide : préfixe, position ou gabarit."""
    m = valider_motif_regle(motif)
    if not m.endswith('*'):
        return FORME_GABARIT
    return FORME_POSITION if re.search(r'[#@?\[]', m) else FORME_PREFIXE


def longueur_motif_regle(motif: str) -> int:
    """Nombre de caractères décrits (une classe compte pour un) : à forme égale,
    le motif le plus long gagne (§ 6.2)."""
    m = valider_motif_regle(motif)
    return len(re.sub(r'\[[^\]]*\]', 'x', m).rstrip('*'))


def motif_regle_vers_regex(motif: str) -> 're.Pattern':
    """Expression régulière d'un motif de règle, à appliquer par `fullmatch`
    sur une clé normalisée."""
    m = valider_motif_regle(motif)
    morceaux, i = [], 0
    while i < len(m):
        c = m[i]
        if c == '[':
            fin = m.index(']', i)
            morceaux.append(m[i:fin + 1])
            i = fin + 1
            continue
        morceaux.append({'#': '[0-9]', '@': '[A-Z]', '?': '.', '*': '.*'}.get(c, re.escape(c)))
        i += 1
    return re.compile(''.join(morceaux))


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
