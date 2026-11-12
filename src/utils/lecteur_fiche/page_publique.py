"""
Lecture d'une page publique de fiche 1001pieces.com (CDC § 3.2, § 5.8)

Extrait, sans accès à la base du site :
- la description (bloc .product-description), lue par lire_description ;
- la référence produit interne (.js-product-reference, sinon sku / mpn) ;
- l'id_product du site (début du nom de la page : …/20746-regulateur….html) ;
- l'EAN (gtin13, clé de contrôle vérifiée), la catégorie et le nom (JSON-LD) ;
- les caractéristiques techniques (table data-sheet) ;
- la table des compatibilités EveryParts (bloc ucpt-table) quand elle existe.
  La page n'en montre que la 1ʳᵉ page (20 lignes) : le nombre total de pages
  est relevé et `table_complete` le signale.
"""

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from src.utils.lecteur_fiche.lecteur import LectureFiche, lire_description
from src.utils.lecteur_fiche.modeles import ModeleLecture
from src.utils.lecteur_fiche.normalisation import nettoyer_texte

_CANONIQUE = re.compile(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', re.I)
_OG_URL = re.compile(r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"', re.I)
_ID_DANS_URL = re.compile(r'/(\d+)-[^/]*\.html')
_ID_PARAM = re.compile(r'[?&]id_product=(\d+)')
_REF_INTERNE = re.compile(r'class="js-product-reference"[^>]*>\s*([^<]*?)\s*<', re.I)
_JSON_LD = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
# Classe exacte « product-description » (pas product-description-nav…)
_DEBUT_DESCRIPTION = re.compile(
    r'<div[^>]+class="(?:[^"]*\s)?product-description(?:\s[^"]*)?"[^>]*>', re.I)
_DIV = re.compile(r'<(/?)div\b[^>]*>', re.I)
_DATA_SHEET = re.compile(
    r'<td[^>]*class="name"[^>]*>(.*?)</td>\s*<td[^>]*class="value[^"]*"[^>]*>(.*?)</td>', re.I | re.S)
_UCPT_RESULTATS = re.compile(r'id="ucpt-compatibilities-results"', re.I)
_UCPT_LIGNE = re.compile(r'<div class="ucpt-table__item">(.*?)</div>', re.I | re.S)
_UCPT_CRITERE = re.compile(r'<span class="ucpt-table__criterion">(.*?)</span>', re.I | re.S)
_UCPT_PAGINATION = re.compile(
    r'id="ucpt-compatibilities-pagination"[^>]*?data-items_per_page="(\d+)"[^>]*?'
    r'data-total_pages="(\d+)"', re.I)
_BALISE = re.compile(r'<[^>]+>')


def ean13_valide(ean: str) -> bool:
    """Clé de contrôle EAN-13 (13 chiffres, somme pondérée 1-3)."""
    if not ean or not re.fullmatch(r'\d{13}', ean):
        return False
    chiffres = [int(c) for c in ean]
    somme = sum(c * (3 if i % 2 else 1) for i, c in enumerate(chiffres[:12]))
    return (10 - somme % 10) % 10 == chiffres[12]


def id_product_depuis_url(url: str) -> Optional[int]:
    """id_product du site : …/20746-nom-de-la-page.html ou ?id_product=20746."""
    if not url:
        return None
    m = _ID_DANS_URL.search(url) or _ID_PARAM.search(url)
    return int(m.group(1)) if m else None


@dataclass
class LigneTableSite:
    type_appareil: str
    marque: str
    ref_modele: str
    nom: str


@dataclass
class PagePublique:
    url: str = ''
    id_product: Optional[int] = None
    ref_interne: str = ''
    source_ref_interne: str = ''        # 'product-reference', 'sku', 'mpn'
    ean: str = ''
    ean_valide: Optional[bool] = None   # None = pas d'EAN
    categorie: str = ''
    nom: str = ''
    marque: str = ''
    caracteristiques: Dict[str, str] = field(default_factory=dict)
    table_site: List[LigneTableSite] = field(default_factory=list)
    table_presente: bool = False
    table_pages: int = 0                # pages de la table EveryParts sur le site
    table_lignes_par_page: int = 0
    description_html: str = ''
    description: Optional[LectureFiche] = None
    non_compris: List[str] = field(default_factory=list)

    @property
    def table_complete(self) -> bool:
        """La page montre toute la table (une seule page)."""
        return self.table_presente and self.table_pages <= 1


def _texte(fragment: str) -> str:
    return nettoyer_texte(html.unescape(_BALISE.sub(' ', fragment or '')))


def _contenu_div(page: str, debut: int) -> str:
    """HTML intérieur d'une div ouverte juste avant `debut` (divs équilibrées)."""
    profondeur = 1
    for d in _DIV.finditer(page, debut):
        profondeur += -1 if d.group(1) else 1
        if profondeur == 0:
            return page[debut:d.start()]
    return page[debut:]


def extraire_description(page: str) -> str:
    """
    HTML intérieur du bloc .product-description de la description longue :
    celui marqué --main, sinon le premier non vide (la description courte,
    souvent vide, porte la même classe).
    """
    blocs = [(m, _contenu_div(page, m.end())) for m in _DEBUT_DESCRIPTION.finditer(page or '')]
    for m, contenu in blocs:
        if 'product-description--main' in m.group(0) and contenu.strip():
            return contenu
    return next((contenu for _, contenu in blocs if contenu.strip()), '')


def _produit_json_ld(page: str) -> Dict[str, Any]:
    for m in _JSON_LD.finditer(page or ''):
        try:
            donnees = json.loads(m.group(1))
        except (ValueError, TypeError):
            continue
        for objet in (donnees if isinstance(donnees, list) else [donnees]):
            if isinstance(objet, dict) and objet.get('@type') == 'Product':
                return objet
    return {}


def _table_site(page: str, p: PagePublique):
    debut = _UCPT_RESULTATS.search(page)
    if not debut:
        return
    p.table_presente = True
    fin = page.find('id="ucpt-compatibilities-pagination"', debut.end())
    zone = page[debut.end():fin if fin > 0 else len(page)]
    for ligne in _UCPT_LIGNE.finditer(zone):
        criteres = [_texte(c) for c in _UCPT_CRITERE.findall(ligne.group(1))]
        if len(criteres) < 3:
            p.non_compris.append('ligne de table illisible : ' + ' | '.join(criteres))
            continue
        type_app, marque, modele = criteres[0], criteres[1], criteres[2]
        ref, _, nom = modele.partition(' - ')
        p.table_site.append(LigneTableSite(type_app, marque, ref.strip(), nom.strip()))
    pagination = _UCPT_PAGINATION.search(page)
    if pagination:
        p.table_lignes_par_page = int(pagination.group(1))
        p.table_pages = int(pagination.group(2))
    else:
        p.table_pages = 1 if p.table_site else 0


def lire_page_publique(page: str, url: str = '', modeles: Iterable[ModeleLecture] = (),
                       marques_connues: Iterable[str] = (),
                       types_connus: Iterable[str] = ()) -> PagePublique:
    """Lit la page HTML publique d'une fiche ; `url` sert si la page n'a pas de lien canonique."""
    page = page or ''
    p = PagePublique()
    m = _CANONIQUE.search(page) or _OG_URL.search(page)
    p.url = html.unescape(m.group(1)) if m else (url or '')
    p.id_product = id_product_depuis_url(p.url) or id_product_depuis_url(url)
    if p.id_product is None:
        p.non_compris.append("id_product introuvable dans le nom de la page")

    produit = _produit_json_ld(page)
    m = _REF_INTERNE.search(page)
    if m and m.group(1).strip():
        p.ref_interne, p.source_ref_interne = html.unescape(m.group(1).strip()), 'product-reference'
    else:
        for cle in ('sku', 'mpn'):
            if str(produit.get(cle) or '').strip():
                p.ref_interne, p.source_ref_interne = str(produit[cle]).strip(), cle
                break
    if not p.ref_interne:
        p.non_compris.append("référence interne introuvable")
    elif produit.get('sku') and str(produit['sku']).strip() != p.ref_interne:
        p.non_compris.append(f"sku ({produit['sku']}) différent de la référence affichée")

    p.ean = str(produit.get('gtin13') or '').strip()
    p.ean_valide = ean13_valide(p.ean) if p.ean else None
    if p.ean and not p.ean_valide:
        p.non_compris.append(f"clé de contrôle EAN fausse : {p.ean}")
    p.categorie = nettoyer_texte(str(produit.get('category') or ''))
    p.nom = nettoyer_texte(str(produit.get('name') or ''))
    marque = produit.get('brand')
    p.marque = nettoyer_texte(str(marque.get('name') if isinstance(marque, dict) else marque or ''))

    for nom, valeur in _DATA_SHEET.findall(page):
        p.caracteristiques[_texte(nom)] = _texte(valeur)

    _table_site(page, p)

    p.description_html = extraire_description(page)
    if p.description_html:
        p.description = lire_description(p.description_html, modeles, marques_connues,
                                         types_connus, p.marque)
    else:
        p.non_compris.append("description introuvable")
    return p
