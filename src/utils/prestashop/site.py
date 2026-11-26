"""
Le site vu par l'outil : référentiels (catégories, fabricants, caractéristiques,
réglages d'une fiche récente), anti-doublon par référence et création d'une fiche.

Une fiche est créée **désactivée**, avec la cover par défaut d'EMG
(data/cover_par_defaut.jpg) en attendant les photos du studio. Le stock reste à
Cogilog. Les références lues ou écrites sont celles du site (code produit EMG).
"""

import collections
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from .client import ClientPrestaShop

ID_LANGUE = 1                 # français, seule langue du site
CARACTERISTIQUE_TYPE_PIECE = 42
CARACTERISTIQUE_TYPE_APPAREIL = 47
MAX_REFS_DOUBLON = 12


def cle(texte: str) -> str:
    return re.sub(r'[^a-z0-9]', '', ''.join(
        c for c in unicodedata.normalize('NFD', (texte or '').lower()) if unicodedata.category(c) != 'Mn'))


def lien_reecrit(nom: str) -> str:
    """URL simplifiée de la fiche, comme PrestaShop la calcule depuis le nom
    (« Relais pour réfrigérateur Beko - C00866459 » → « relais-pour-refrigerateur-beko-c00866459 »)."""
    sans = ''.join(c for c in unicodedata.normalize('NFD', (nom or '').lower())
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '-', sans).strip('-')[:128]


@dataclass
class ProduitSite:
    id: int
    reference: str
    actif: bool
    nom: str = ''


@dataclass
class Referentiels:
    categories: Dict[str, int] = field(default_factory=dict)       # nom → id (actives)
    fabricants: Dict[str, int] = field(default_factory=dict)       # nom → id
    types_piece: Dict[str, int] = field(default_factory=dict)      # valeur → id (caractéristique 42)
    types_appareil: Dict[str, int] = field(default_factory=dict)   # valeur → id (caractéristique 47)
    modele: Dict[str, str] = field(default_factory=dict)           # réglages d'une fiche récente

    def id_categorie(self, nom: str) -> Optional[int]:
        return self.categories.get(nom) or next(
            (i for n, i in self.categories.items() if cle(n) == cle(nom)), None)

    def id_fabricant(self, nom: str) -> Optional[int]:
        return self.fabricants.get(nom) or next(
            (i for n, i in self.fabricants.items() if cle(n) == cle(nom)), None)

    def id_type_appareil(self, type_appareil: str) -> Optional[int]:
        """« Plaque » → « Plaque de cuisson » : égalité, sinon une valeur qui commence pareil."""
        c = cle(type_appareil)
        if not c:
            return None
        for valeur, i in self.types_appareil.items():
            if cle(valeur) == c:
                return i
        return next((i for v, i in self.types_appareil.items() if cle(v).startswith(c)), None)


class SitePrestaShop:
    def __init__(self, client: Optional[ClientPrestaShop] = None):
        self.client = client or ClientPrestaShop()
        self._referentiels: Optional[Referentiels] = None

    # --- Lecture -----------------------------------------------------------------------
    def referentiels(self) -> Referentiels:
        if self._referentiels is None:
            c, r = self.client, Referentiels()
            r.categories = {x['name']: int(x['id']) for x in c.lister('categories', '[id,name,active]')
                            if str(x.get('active')) == '1' and x.get('name')}
            r.fabricants = {x['name']: int(x['id']) for x in c.lister('manufacturers', '[id,name]')
                            if x.get('name')}
            for id_car, cible in ((CARACTERISTIQUE_TYPE_PIECE, r.types_piece),
                                  (CARACTERISTIQUE_TYPE_APPAREIL, r.types_appareil)):
                cible.update({x['value']: int(x['id']) for x in c.lister(
                    'product_feature_values', '[id,value]', {'id_feature': f'[{id_car}]'}) if x.get('value')})
            r.modele = self._reglages_recents()
            self._referentiels = r
        return self._referentiels

    def _reglages_recents(self) -> Dict[str, str]:
        """Réglages des fiches récentes, repris à la création : groupe de taxe le plus
        fréquent, délais et mentions de disponibilité de la dernière fiche active."""
        recents = self.client.lister('products', '[id,id_tax_rules_group,active]', tri='[id_DESC]',
                                     limite='100')
        taxes = collections.Counter(p['id_tax_rules_group'] for p in recents if str(p.get('active')) == '1')
        modele = {'id_tax_rules_group': taxes.most_common(1)[0][0] if taxes else '1'}
        actif = next((p for p in recents if str(p.get('active')) == '1'), None)
        if actif:
            p = self.client.lire('products', actif['id'])
            for champ in ('additional_delivery_times', 'delivery_out_stock', 'delivery_in_stock',
                          'available_now', 'available_later'):
                if p.get(champ) not in (None, ''):
                    modele[champ] = p[champ]
        return modele

    def produits_existants(self, references: List[str]) -> List[ProduitSite]:
        """Produits du site dont la référence contient une des références (code produit
        EMG = préfixe + référence) : l'anti-doublon avant de créer une fiche."""
        trouves: Dict[int, ProduitSite] = {}
        for ref in [r for r in dict.fromkeys(cle(x).upper() for x in references) if len(r) >= 5][:MAX_REFS_DOUBLON]:
            for p in self.client.lister('products', '[id,reference,active,name]', {'reference': f'%[{ref}]%'},
                                        limite='20'):
                if re.search(rf'{re.escape(ref)}$', cle(p.get('reference')).upper()):
                    trouves[int(p['id'])] = ProduitSite(int(p['id']), p.get('reference', ''),
                                                       str(p.get('active')) == '1', _texte(p.get('name')))
        return list(trouves.values())

    def type_piece_propose(self, id_categorie: int) -> Optional[str]:
        """Type de pièce le plus fréquent parmi les fiches de la catégorie."""
        produits = self.client.lister('products', 'full', {'id_category_default': f'[{int(id_categorie)}]'},
                                      limite='60')
        compte = collections.Counter(
            int(f['id_feature_value']) for p in produits
            for f in (p.get('associations') or {}).get('product_features') or []
            if int(f.get('id', 0)) == CARACTERISTIQUE_TYPE_PIECE)
        if not compte:
            return None
        valeurs = {i: v for v, i in self.referentiels().types_piece.items()}
        return valeurs.get(compte.most_common(1)[0][0])

    # --- Création ------------------------------------------------------------------------
    def creer_fiche(self, fiche, id_categorie: int, id_fabricant: Optional[int],
                    caracteristiques: List[Tuple[int, int]], cover: Optional[bytes]) -> int:
        """Crée la fiche désactivée (et sa cover) ; retourne l'id du produit.
        Refus si un produit du site porte déjà ce code."""
        if self.client.lister('products', '[id]', {'reference': f'[{fiche.code}]'}):
            raise ValueError(f"le code {fiche.code} existe déjà sur le site")
        xml = xml_produit(fiche, id_categorie, id_fabricant, caracteristiques, self.referentiels().modele)
        id_produit = self.client.creer('products', xml)
        if cover:
            self.client.envoyer_image(id_produit, cover)
        return id_produit


def _texte(valeur) -> str:
    """Champ multilingue lu en JSON : chaîne, ou [{'id': 1, 'value': …}]."""
    if isinstance(valeur, list):
        return next((str(v.get('value', '')) for v in valeur if str(v.get('id')) == str(ID_LANGUE)), '')
    return str(valeur or '')


def _cdata(texte: str) -> str:
    return '<![CDATA[' + (texte or '').replace(']]>', ']]]]><![CDATA[>') + ']]>'


def _langue(balise: str, texte: str) -> str:
    return f'<{balise}><language id="{ID_LANGUE}">{_cdata(texte)}</language></{balise}>'


def xml_produit(fiche, id_categorie: int, id_fabricant: Optional[int],
                caracteristiques: List[Tuple[int, int]], modele: Dict[str, str]) -> str:
    """Corps XML de la création (fiche désactivée, produit standard, état neuf)."""
    simples = {
        'id_manufacturer': id_fabricant or 0, 'id_category_default': id_categorie,
        'id_tax_rules_group': modele.get('id_tax_rules_group', '1'),
        'reference': fiche.code, 'supplier_reference': fiche.ref_fournisseur or fiche.reference,
        'ean13': fiche.ean or '', 'price': f"{fiche.prix_ht:.6f}" if fiche.prix_ht else '0',
        'active': 0, 'state': 1, 'visibility': 'both', 'condition': 'new', 'show_price': 1,
        'available_for_order': 1, 'indexed': 1, 'minimal_quantity': 1, 'product_type': 'standard',
        'additional_delivery_times': modele.get('additional_delivery_times', '1'),
    }
    lignes = [f'<{k}>{_cdata(str(v))}</{k}>' for k, v in simples.items()]
    lignes += [_langue('name', fiche.nom[:128]), _langue('link_rewrite', lien_reecrit(fiche.nom)),
               _langue('description', fiche.description),
               _langue('meta_title', fiche.meta_title[:255]),
               _langue('meta_description', fiche.meta_description[:512])]
    for champ in ('delivery_out_stock', 'delivery_in_stock', 'available_now', 'available_later'):
        if modele.get(champ):
            lignes.append(_langue(champ, _texte(modele[champ])))
    assoc = f'<categories><category><id>{int(id_categorie)}</id></category></categories>'
    if caracteristiques:
        assoc += '<product_features>' + ''.join(
            f'<product_feature><id>{int(f)}</id><id_feature_value>{int(v)}</id_feature_value></product_feature>'
            for f, v in caracteristiques) + '</product_features>'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<prestashop xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<product>' + ''.join(lignes) + f'<associations>{assoc}</associations></product></prestashop>')


__all__ = ['SitePrestaShop', 'Referentiels', 'ProduitSite', 'xml_produit', 'lien_reecrit', 'escape']
