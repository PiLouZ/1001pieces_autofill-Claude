"""
Lecture des deux exports CSV PrestaShop de la reprise (CDC § 3.1, étape 4)

- Produits : id_produit, reference, nom_produit, marque, ean, categorie, actif,
  description.
- Compatibilités : id_produit, reference_appareil, modele_appareil
  (« RÉF - NOM »), marque_appareil, type_appareil.

Séparateur `;`, champs entre `"`, en-têtes en 1ʳᵉ ligne. Les deux fichiers sont
triés par id_produit : ils se lisent **ensemble**, en avançant dans les deux à
la fois (jointure par fusion). Un produit et ses compatibilités sont seuls en
mémoire : les ≈ 7 millions de lignes de compatibilités ne sont jamais chargées.
Un fichier mal trié est refusé (`ExportNonTrie`) : la reprise par
« dernier id_produit traité » n'aurait plus de sens.
"""

import csv
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Set

from src.utils.lecteur_fiche.page_publique import LigneTableSite

COLONNES_PRODUITS = ('id_produit', 'reference', 'nom_produit', 'marque', 'ean', 'categorie',
                     'actif', 'description')
COLONNES_COMPATIBILITES = ('id_produit', 'reference_appareil', 'modele_appareil',
                           'marque_appareil', 'type_appareil')


class ExportInvalide(ValueError):
    """Export illisible : colonnes manquantes, id_produit non numérique."""


class ExportNonTrie(ExportInvalide):
    """Export non trié par id_produit."""


@dataclass
class ProduitExport:
    id_produit: int
    reference: str = ''
    nom: str = ''
    marque: str = ''
    ean: str = ''
    categorie: str = ''
    actif: bool = True
    description: str = ''
    compatibilites: List[LigneTableSite] = field(default_factory=list)

    @property
    def a_contenu(self) -> bool:
        """Une description ou des compatibilités : sinon rien à reprendre."""
        return bool(self.description.strip() or self.compatibilites)


@dataclass
class SignatureExport:
    """Ce qui identifie un export : chemins, tailles et date (date du fichier)."""
    chemin_produits: str
    chemin_compatibilites: str = ''
    taille_produits: int = 0
    taille_compatibilites: int = 0
    date_export: str = ''               # ISO, la plus récente des deux dates de fichier

    @classmethod
    def de(cls, chemin_produits, chemin_compatibilites=None) -> 'SignatureExport':
        p = Path(chemin_produits)
        dates = [p.stat().st_mtime]
        s = cls(str(p), taille_produits=p.stat().st_size)
        if chemin_compatibilites:
            c = Path(chemin_compatibilites)
            s.chemin_compatibilites = str(c)
            s.taille_compatibilites = c.stat().st_size
            dates.append(c.stat().st_mtime)
        s.date_export = datetime.fromtimestamp(max(dates)).isoformat(timespec='seconds')
        return s

    def meme_export(self, autre: 'SignatureExport') -> bool:
        return (self.date_export, self.taille_produits, self.taille_compatibilites) == \
               (autre.date_export, autre.taille_produits, autre.taille_compatibilites)


def ligne_compatibilite(ligne: dict) -> LigneTableSite:
    """Ligne de l'export des compatibilités → ligne de la table du site.
    `modele_appareil` vaut « RÉF - NOM » : le nom est la partie après « - »."""
    ref = (ligne.get('reference_appareil') or '').strip()
    modele = (ligne.get('modele_appareil') or '').strip()
    tete, sep, nom = modele.partition(' - ')
    if not ref:
        ref = tete.strip()
    return LigneTableSite((ligne.get('type_appareil') or '').strip(),
                          (ligne.get('marque_appareil') or '').strip(),
                          ref, nom.strip() if sep else '')


def _id(ligne: dict, fichier: str) -> int:
    valeur = (ligne.get('id_produit') or '').strip()
    if not valeur.isdigit():
        raise ExportInvalide(f"{fichier} : id_produit non numérique « {valeur} »")
    return int(valeur)


def _lecteur(chemin, colonnes, nom) -> Iterator[dict]:
    csv.field_size_limit(sys.maxsize)
    with open(chemin, encoding='utf-8-sig', newline='') as f:
        lecteur = csv.DictReader(f, delimiter=';', quotechar='"')
        manquantes = [c for c in colonnes if c not in (lecteur.fieldnames or ())]
        if manquantes:
            raise ExportInvalide(f"{nom} : colonne(s) manquante(s) : {', '.join(manquantes)}")
        yield from lecteur


def lire_exports(chemin_produits, chemin_compatibilites=None, apres_id: int = 0,
                 seulement: Optional[Set[int]] = None) -> Iterator[ProduitExport]:
    """
    Produits de l'export, dans l'ordre de id_produit, avec leurs compatibilités.

    apres_id : reprendre après ce produit (exclu).
    seulement : ne rendre que ces id_produit (fiches mises de côté).

    Le générateur se garde d'un lot à l'autre (`prochain_lot` le consomme par
    tranches) : seul le premier lot d'une session repasse les produits déjà
    traités (≈ 15 s sur l'export complet).
    """
    compat = _lecteur(chemin_compatibilites, COLONNES_COMPATIBILITES, "export des compatibilités") \
        if chemin_compatibilites else iter(())
    suivante = next(compat, None)
    id_suivant = _id(suivante, "compatibilités") if suivante else None
    precedent = -1
    for ligne in _lecteur(chemin_produits, COLONNES_PRODUITS, "export des produits"):
        ident = _id(ligne, "produits")
        if ident <= precedent:
            raise ExportNonTrie(f"export des produits non trié par id_produit "
                                f"({precedent} puis {ident})")
        precedent = ident
        # Compatibilités des produits précédents (ou d'un produit absent de l'export) : passées
        lignes: List[LigneTableSite] = []
        while id_suivant is not None and id_suivant <= ident:
            if id_suivant == ident:
                lignes.append(ligne_compatibilite(suivante))
            suivante = next(compat, None)
            nouvel = _id(suivante, "compatibilités") if suivante else None
            if nouvel is not None and nouvel < id_suivant:
                raise ExportNonTrie(f"export des compatibilités non trié par id_produit "
                                    f"({id_suivant} puis {nouvel})")
            id_suivant = nouvel
        if ident <= apres_id or (seulement is not None and ident not in seulement):
            continue
        yield ProduitExport(
            id_produit=ident, reference=(ligne.get('reference') or '').strip(),
            nom=(ligne.get('nom_produit') or '').strip(), marque=(ligne.get('marque') or '').strip(),
            ean=(ligne.get('ean') or '').strip(), categorie=(ligne.get('categorie') or '').strip(),
            actif=(ligne.get('actif') or '1').strip() != '0',
            description=ligne.get('description') or '', compatibilites=lignes)


@dataclass
class LotExport:
    """Produits d'un lot : `produits` ont un contenu ; `dernier_id` est le dernier
    id_produit lu (produits sans contenu compris), où reprendra le lot suivant."""
    produits: List[ProduitExport]
    premier_id: int
    dernier_id: int
    sans_contenu: int = 0
    fin_export: bool = False


def prochain_lot(produits: Iterable[ProduitExport], taille: int = 100) -> Optional[LotExport]:
    """Lit le lot suivant : `taille` produits ayant un contenu (une description ou
    des compatibilités). None quand l'export est épuisé."""
    lot: List[ProduitExport] = []
    premier = dernier = None
    sans_contenu = 0
    iterateur = iter(produits)
    for p in iterateur:
        premier = p.id_produit if premier is None else premier
        dernier = p.id_produit
        if p.a_contenu:
            lot.append(p)
        else:
            sans_contenu += 1
        if len(lot) >= taille:
            return LotExport(lot, premier, dernier, sans_contenu)
    if premier is None:
        return None
    return LotExport(lot, premier, dernier, sans_contenu, fin_export=True)


def taille_fichier(chemin) -> int:
    try:
        return os.path.getsize(chemin)
    except OSError:
        return 0
