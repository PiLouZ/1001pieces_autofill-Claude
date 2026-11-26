"""
Fiche nouvelle pour le site : une ligne d'import PrestaShop et une ligne d'import
Cogilog, ajoutées aux fichiers du jour.

- Code produit EMG = référence PrestaShop = code Cogilog (préfixe + référence
  constructeur, proposé puis vérifié par l'utilisateur).
- Prix : prix de vente TTC (règle EMG), HT = TTC / 1,2.
- Cogilog : matrice d'EMG (Code ; Libellé ; Site web1 ; Internet HT ; Internet
  TTC ; Photo ; Famille ; Code EAN), « ; », Windows-1252, virgule décimale.
- PrestaShop : colonnes de l'import CSV natif ; fiche inactive (photo à faire
  au studio d'EMG, jamais récupérée ailleurs).

Les fichiers du jour (`fiches_prestashop_AAAAMMJJ.csv`, `fiches_cogilog_AAAAMMJJ.csv`)
s'enrichissent fiche après fiche ; une fiche exportée deux fois remplace sa ligne.
"""

import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from .conversion import sans_accents

TVA = 1.20

COLONNES_PRESTASHOP = [
    'Active (0/1)', 'Name *', 'Categories (x,y,z...)', 'Price tax excluded', 'Tax rules ID',
    'Reference #', 'Supplier reference #', 'Supplier', 'Manufacturer', 'EAN13', 'Weight',
    'Quantity', 'Short description', 'Description', 'Meta title', 'Meta description',
    'Image URLs (x,y,z...)', 'Condition']
COLONNES_COGILOG = ['Code', 'Libellé', 'Site web1', 'Internet HT', 'Internet TTC', 'Photo',
                    'Famille', 'Code EAN']

# Fabricant PrestaShop (groupe de marques du site) par préfixe de code, relevé dans
# le catalogue ('' = sans préfixe : Whirlpool)
FABRICANTS_SITE = {
    '': 'Whirlpool Laden Ignis Bauknecht', 'SCS': 'Indesit Ariston Scholtès Hotpoint',
    'EL': 'Electrolux Zanussi Arthur Martin Faure AEG', 'GAU': 'Bosch Siemens Neff Gaggenau Viva',
    'BEO': 'Beko', 'LH': 'Liebherr', 'ROS': 'Candy Hoover Iberna Rosieres', 'MIE': '1001pièces',
    'FAR': 'Fagor Brandt Vedette De Dietrich Sauter Thermor',
}


def cle_categorie(texte: str) -> str:
    return re.sub(r'[^a-z]', '', sans_accents((texte or '').lower()))


def prefixe_du_code(code: str) -> str:
    m = re.match(r'^([A-Z]+?)(?=\d)', code or '')
    return m.group(1) if m and m.group(1) in FABRICANTS_SITE else ''


# Constructeur Agora → fabricant du site (prime sur le préfixe : une pièce Beko
# numérotée C00… garde le fabricant Beko)
FABRICANTS_PAR_CONSTRUCTEUR = {
    2: FABRICANTS_SITE[''], 3: FABRICANTS_SITE['EL'], 4: FABRICANTS_SITE['GAU'], 5: FABRICANTS_SITE['MIE'],
    17: 'Beko', 22: 'Liebherr', 33: FABRICANTS_SITE['ROS'], 37: 'Liebherr',
}


def fabricant_site(code: str, constructeur: Optional[int] = None) -> str:
    if constructeur in FABRICANTS_PAR_CONSTRUCTEUR:
        return FABRICANTS_PAR_CONSTRUCTEUR[constructeur]
    return FABRICANTS_SITE.get(prefixe_du_code(code), '')


class CategoriesSite:
    """Catégories « Famille - Type » du site (data/categories_site.json)."""

    def __init__(self, chemin: Optional[str] = None):
        self.categories: List[str] = []
        self.par_libelle_type: Dict[str, str] = {}
        if chemin is None:
            from src.core.config import Config
            chemin = os.path.join(os.path.dirname(os.path.abspath(Config.DB_FILE)), 'categories_site.json')
        if os.path.exists(chemin):
            with open(chemin, encoding='utf-8') as f:
                d = json.load(f)
            self.categories = d.get('categories') or []
            self.par_libelle_type = d.get('par_libelle_type') or {}

    def proposer(self, libelle: str, type_appareil: str) -> str:
        """Catégorie la plus fréquente pour ce libellé et ce type, sinon une catégorie
        existante « … - Type » dont la famille commence comme le libellé, sinon ''."""
        mot = cle_categorie((libelle or '').split(' ')[0])
        type_cle = cle_categorie(type_appareil)
        trouvee = self.par_libelle_type.get(f"{mot}|{type_cle}")
        if trouvee:
            return trouvee
        for cat in self.categories:
            famille, _, type_cat = cat.rpartition(' - ')
            if cle_categorie(type_cat) == type_cle and mot and cle_categorie(famille).startswith(mot[:5]):
                return cat
        divers = f"Divers - {type_appareil}"
        return divers if divers in self.categories else ''


@dataclass
class FicheSite:
    code: str
    nom: str
    libelle: str                  # libellé de la pièce (désignation)
    reference: str                # référence constructeur publiée
    prix_ttc: Optional[float]
    categorie: str = ''
    fabricant: str = ''
    ref_fournisseur: str = ''
    fournisseur: str = 'Agora'
    description: str = ''
    meta_title: str = ''
    meta_description: str = ''
    ean: str = ''

    @property
    def prix_ht(self) -> Optional[float]:
        return round(self.prix_ttc / TVA, 6) if self.prix_ttc else None

    def manques(self) -> List[str]:
        return [nom for nom, v in (("code produit", self.code), ("nom", self.nom),
                                   ("prix", self.prix_ttc), ("catégorie", self.categorie),
                                   ("description", self.description)) if not v]

    def ligne_prestashop(self) -> List[str]:
        return ['0', self.nom, self.categorie, f"{self.prix_ht:.6f}" if self.prix_ht else '', '1',
                self.code, self.ref_fournisseur or self.reference, self.fournisseur, self.fabricant,
                self.ean, '', '0', '', self.description, self.meta_title, self.meta_description,
                '', 'new']

    def ligne_cogilog(self) -> List[str]:
        virgule = lambda x, n: f"{x:.{n}f}".replace('.', ',') if x else ''
        libelle = f"{(self.libelle or '').upper()} {self.reference}".strip()
        return [self.code, libelle, 'PrestaShop', virgule(self.prix_ht, 6), virgule(self.prix_ttc, 2),
                'pam', 'Apieces', self.ean]


def chemins_du_jour(dossier: str, jour: Optional[date] = None) -> Tuple[str, str]:
    j = (jour or date.today()).strftime('%Y%m%d')
    return (os.path.join(dossier, f"fiches_prestashop_{j}.csv"),
            os.path.join(dossier, f"fiches_cogilog_{j}.csv"))


def _ajouter(chemin: str, entetes: List[str], ligne: List[str], col_code: int, encodage: str) -> int:
    lignes: List[List[str]] = []
    if os.path.exists(chemin):
        with open(chemin, encoding=encodage, newline='') as f:
            lignes = [r for r in csv.reader(f, delimiter=';')][1:]
    lignes = [r for r in lignes if len(r) > col_code and r[col_code] != ligne[col_code]] + [ligne]
    with open(chemin, 'w', encoding=encodage, errors='replace', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(entetes)
        w.writerows(lignes)
    return len(lignes)


def ajouter_aux_fichiers_du_jour(fiche: FicheSite, dossier: str,
                                 jour: Optional[date] = None) -> Dict[str, object]:
    """Ajoute (ou remplace) la fiche dans les deux fichiers du jour."""
    os.makedirs(dossier, exist_ok=True)
    presta, cogilog = chemins_du_jour(dossier, jour)
    n = _ajouter(presta, COLONNES_PRESTASHOP, fiche.ligne_prestashop(), 5, 'utf-8')
    _ajouter(cogilog, COLONNES_COGILOG, fiche.ligne_cogilog(), 0, 'cp1252')
    return {'prestashop': presta, 'cogilog': cogilog, 'fiches': n}
