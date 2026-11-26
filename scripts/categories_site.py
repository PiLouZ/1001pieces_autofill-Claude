"""
Catégories du site pour les fiches nouvelles (Agora) : data/categories_site.json.

Lit un export des produits du site (celui de la reprise des fiches : colonnes
`nom_produit` et `categorie`, ou `categorie_defaut`) et en tire :
- la liste des catégories « Famille - Type » des produits actifs ;
- la catégorie la plus fréquente par couple (1er mot du nom, type cité après
  « pour ») : « Relais pour réfrigérateur Beko » → Relais / réfrigérateur.

Usage : python3 scripts/categories_site.py <export_produits.csv>
"""

import collections
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.utils.agora.fiche import cle_categorie  # noqa: E402


def main(chemin: str) -> None:
    csv.field_size_limit(10 ** 9)
    with open(chemin, 'rb') as f:
        debut = f.read(1 << 20)
    try:
        debut.decode('utf-8')
        encodage = 'utf-8'
    except UnicodeDecodeError:
        encodage = 'latin-1'
    categories, couples = collections.Counter(), collections.defaultdict(collections.Counter)
    with open(chemin, encoding=encodage, newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            if str(r.get('actif', '1')).strip() not in ('1', 'true', 'True'):
                continue
            cat = (r.get('categorie') or r.get('categorie_defaut') or '').strip()
            if ' - ' not in cat:
                continue
            categories[cat] += 1
            m = re.search(r' pour ([^\s]+(?:-[^\s]+)?)', (r.get('nom_produit') or '').lower())
            mot = cle_categorie((r.get('nom_produit') or '').split(' ')[0])
            if m and mot:
                couples[f"{mot}|{cle_categorie(m.group(1))}"][cat] += 1
    sortie = {
        '_commentaire': "Généré par scripts/categories_site.py depuis l'export des produits du site.",
        'categories': sorted(categories),
        'par_libelle_type': {k: v.most_common(1)[0][0] for k, v in sorted(couples.items())},
    }
    cible = os.path.join(os.path.dirname(__file__), '..', 'data', 'categories_site.json')
    with open(cible, 'w', encoding='utf-8') as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
    print(f"{len(categories)} catégories, {len(couples)} couples → {os.path.normpath(cible)}")


if __name__ == '__main__':
    main(sys.argv[1])
