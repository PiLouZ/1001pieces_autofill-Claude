"""
Normalisation du HTML d'une fiche avant lecture (CDC import fiches site, § 4.3)

La fiche et les gabarits sont réduits à la même forme : une suite de BLOCS.
- on garde le découpage en blocs (div, p, br, titres, li…), les classes, l'id
  et le texte ;
- on ignore les balises de mise en forme (b, u, strong, em, span, a…) et les
  attributs style : leur texte rejoint le bloc qui les contient ;
- les espaces multiples et les &nbsp; sont ramenés à un seul espace.

Les textes des liens <a> sont aussi notés à part (ligne « Compatible avec »).
Sans Qt ni base.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import FrozenSet, List, Optional, Tuple

# Balises qui découpent le texte en blocs
BALISES_BLOC = frozenset({
    'div', 'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'ul', 'ol',
    'section', 'article', 'table', 'tr', 'td', 'th', 'tbody', 'thead',
    'header', 'footer', 'nav', 'blockquote', 'hr', 'dl', 'dt', 'dd', 'main',
})
# Balises dont le contenu n'est pas du texte de fiche
BALISES_IGNOREES = frozenset({'script', 'style', 'noscript', 'template', 'svg'})
# Balises sans fermeture
BALISES_VIDES = frozenset({'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr', 'col', 'area'})

_ESPACES = re.compile(r'\s+')


def nettoyer_texte(texte: str) -> str:
    """&nbsp; et espaces multiples → un espace ; bords retirés."""
    return _ESPACES.sub(' ', (texte or '').replace('\xa0', ' ')).strip()


@dataclass(frozen=True)
class Bloc:
    """Un bloc de texte de la fiche, avec l'élément de bloc qui le porte."""
    index: int                      # position dans la fiche (0, 1, …)
    balise: str                     # balise de bloc porteuse ('div', 'h2'…)
    classes: FrozenSet[str]         # classes de cette balise
    id: str                         # id de cette balise ('' sinon)
    texte: str                      # texte normalisé, jamais vide
    classes_parents: FrozenSet[str] = frozenset()   # classes des blocs englobants
    liens: Tuple[str, ...] = ()     # textes des liens <a> du bloc

    def a_les_classes(self, classes: FrozenSet[str]) -> bool:
        """Toutes les `classes` attendues sont portées par le bloc."""
        return classes <= self.classes


@dataclass
class _Element:
    balise: str
    classes: FrozenSet[str]
    id: str


class _Normaliseur(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocs: List[Bloc] = []
        self._pile: List[_Element] = [_Element('', frozenset(), '')]
        self._morceaux: List[str] = []
        self._liens: List[str] = []
        self._lien_en_cours: Optional[List[str]] = None
        self._ignore = 0

    # --- Émission d'un bloc --------------------------------------------
    def _vider(self):
        texte = nettoyer_texte(''.join(self._morceaux))
        self._morceaux = []
        liens = tuple(t for t in (nettoyer_texte(x) for x in self._liens) if t)
        self._liens = []
        if not texte:
            return
        porteur = self._pile[-1]
        parents = frozenset().union(*(e.classes for e in self._pile[:-1]))
        self.blocs.append(Bloc(len(self.blocs), porteur.balise or 'texte', porteur.classes,
                               porteur.id, texte, parents, liens))

    # --- Analyse -----------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in BALISES_IGNOREES:
            self._ignore += 1
            return
        if self._ignore:
            return
        if tag == 'a':
            self._lien_en_cours = []
            return
        if tag not in BALISES_BLOC:
            return
        self._vider()
        if tag in BALISES_VIDES:
            return
        attributs = dict(attrs)
        classes = frozenset((attributs.get('class') or '').split())
        self._pile.append(_Element(tag, classes, (attributs.get('id') or '').strip()))

    def handle_startendtag(self, tag, attrs):
        # <br/>, <div/> : coupure sans ouverture durable
        tag = tag.lower()
        if self._ignore or tag in BALISES_IGNOREES:
            return
        if tag in BALISES_BLOC:
            self._vider()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in BALISES_IGNOREES:
            self._ignore = max(0, self._ignore - 1)
            return
        if self._ignore:
            return
        if tag == 'a':
            if self._lien_en_cours is not None:
                self._liens.append(''.join(self._lien_en_cours))
            self._lien_en_cours = None
            return
        if tag not in BALISES_BLOC or tag in BALISES_VIDES:
            return
        self._vider()
        # Fermer jusqu'à la balise correspondante (HTML mal fermé toléré)
        for i in range(len(self._pile) - 1, 0, -1):
            if self._pile[i].balise == tag:
                del self._pile[i:]
                break

    def handle_data(self, data):
        if self._ignore:
            return
        self._morceaux.append(data)
        if self._lien_en_cours is not None:
            self._lien_en_cours.append(data)

    def close(self):
        super().close()
        self._vider()


def normaliser(html_fiche: str) -> List[Bloc]:
    """Fiche (ou gabarit) HTML → blocs normalisés. Texte brut accepté (lignes = blocs)."""
    contenu = html_fiche or ''
    if '<' not in contenu:
        # Description collée en texte : une ligne = un bloc
        contenu = '<br>'.join(_echapper(l) for l in contenu.splitlines())
    analyseur = _Normaliseur()
    analyseur.feed(contenu)
    analyseur.close()
    return analyseur.blocs


def _echapper(ligne: str) -> str:
    return ligne.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def longueur_visible(html_fiche: str) -> int:
    """Caractères visibles, comptés comme l'export (balises retirées, rien d'autre)."""
    return len(re.sub(r'<[^>]*>', '', html_fiche or ''))
