"""
Libellé de pièce tiré du titre d'une fiche du site : coupe à « pour <type> »

Le titre d'une fiche cite l'appareil (« Pompe de vidange R2.5Y pour machine à
laver (pièce générique) »). Repris tel quel comme libellé, le type se répète
dans les exports (Titre, métas, Fiche complète), qui l'ajoutent déjà. On ne
garde donc que ce qui précède « pour <type d'appareil> ».

Types reconnus : ceux de l'onglet Appareils et toutes leurs appellations
(« machine à laver » = lave-linge), au singulier ou au pluriel, tiret ou
espace, sans tenir compte des accents ni de la casse. Les types bruts de la
base (« Porte », « Filtre », « Accessoires ») ne servent pas : « Joint pour
porte de four » n'est pas coupé.

Ce qui suit le type est retiré (« (pièce générique) », « et cuisinière »,
« à induction »), sauf une caractéristique chiffrée hors parenthèses, gardée
à la suite (décision du 2026-11-12, choix B) : « Résistance pour sèche linge
1900W » → « Résistance 1900W ».

Mesure sur l'export complet (2026-11-12) : 8 960 titres coupés sur 13 296.
Sans Qt, sans base : testable seul.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Any, Iterable, Optional, Tuple

_ARTICLES = r"(?:(?:les?|la|l'|un|une|des|votre|vos|tous\s+les|toutes\s+les|tout|toute)\s*)?"
# Après le type : rien, un blanc ou une ponctuation (pas « fours » pour « four » + s :
# le pluriel est dans le motif du terme)
_FIN_TERME = r"(?=$|[\s,.;:()/\-+])"
_PARENTHESES = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def sans_accents(texte: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texte)
                   if unicodedata.category(c) != 'Mn')


def termes_appareils(appellations: Any = None) -> Tuple[str, ...]:
    """Types et appellations (actives ou non) de l'onglet Appareils.

    appellations : config `synonymes_appareils` (dict), objet `Appellations`,
    liste de termes, ou None (liste par défaut)."""
    from src.utils.appellations_appareils import Appellations, nettoyer_config
    if isinstance(appellations, (list, tuple, set, frozenset)):
        return tuple(sorted({str(t) for t in appellations if str(t).strip()}))
    config = appellations.config if isinstance(appellations, Appellations) \
        else nettoyer_config(appellations)
    termes = set()
    for a in config['appareils']:
        termes.add(a['type'])
        termes.update(v['terme'] for v in a.get('variantes') or [])
    return tuple(sorted(t for t in termes if t.strip()))


def _motif_terme(terme: str) -> str:
    mots = [m for m in re.split(r"[\s\-]+", sans_accents(terme).lower()) if m]
    return r"[\s\-]+".join(re.escape(m) + r"(?:s|x)?" for m in mots)


@lru_cache(maxsize=8)
def _expression(termes: Tuple[str, ...]) -> Tuple[re.Pattern, re.Pattern]:
    alternatives = '|'.join(sorted((_motif_terme(t) for t in termes), key=len, reverse=True))
    coupe = re.compile(r"\s+pour\s+" + _ARTICLES + r"(?:" + alternatives + r")" + _FIN_TERME,
                       re.I)
    # Suite du type : « et cuisinière », « / congélateur », « ou four »…
    enchaine = re.compile(r"^\s*(?:et|ou|/|&|,)\s*" + _ARTICLES + r"(?:" + alternatives + r")"
                          + _FIN_TERME, re.I)
    return coupe, enchaine


def couper_au_type(titre: str, appellations: Any = None,
                   termes: Optional[Iterable[str]] = None) -> str:
    """Libellé : ce qui précède « pour <type> », plus une caractéristique chiffrée
    qui suivrait le type. Titre sans type reconnu : inchangé."""
    titre = ' '.join((titre or '').split())
    if not titre:
        return ''
    liste = tuple(sorted(set(termes))) if termes is not None else termes_appareils(appellations)
    if not liste:
        return titre
    coupe, enchaine = _expression(liste)
    # Recherche sur le texte sans accents : même longueur que l'original pour
    # les lettres latines (les accents combinants sont retirés un à un)
    plat = _aplatir(titre)
    m = coupe.search(plat)
    if not m:
        return titre
    debut = titre[:m.start()].strip(' -–,;:')
    if not debut:
        return titre
    reste = plat[m.end():]
    decale = m.end()
    while True:
        e = enchaine.match(reste)
        if not e:
            break
        reste, decale = reste[e.end():], decale + e.end()
    reste_original = _PARENTHESES.sub(' ', titre[decale:])
    reste_original = ' '.join(reste_original.split()).strip(' -–,;:/')
    if any(c.isdigit() for c in reste_original):
        separateur = ', ' if titre[decale:].lstrip().startswith(',') else ' '
        return f"{debut}{separateur}{reste_original}"
    return debut


def _aplatir(texte: str) -> str:
    """Texte sans accents, de même longueur (un caractère pour un caractère)."""
    return ''.join(sans_accents(c) or c for c in texte)
