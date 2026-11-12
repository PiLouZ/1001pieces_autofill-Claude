#!/usr/bin/env python3
"""
Mesure du rapprochement des fiches avec la base (CDC § 10.2, étape 2)

Lit un échantillon de l'export CSV des produits du site (mêmes colonnes que
scripts/mesurer_lecteur_fiches.py), rapproche chaque fiche avec la base ouverte
en LECTURE SEULE (de préférence une copie faite avec l'API backup de sqlite3)
et rapporte :
- la répartition des appareils par niveau, par lien et par statut de pièce ;
- la part des marques déduites pour les lignes sans en-tête (« annonces ») ;
- les remplacements et équivalences par statut, la référence interne ;
- les doutes par catégorie (fiches et occurrences), le temps par fiche.

L'export des produits ne porte pas la table des compatibilités : le type vient
ici de la ligne, de la base ou de la catégorie.

Usage :
    python3.13 scripts/mesurer_rapprochement_fiches.py export_produits.csv copie.db \\
        --config data/export_config.json [--pas 20] [--limite 0] [--rapport rapport.md]
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from src.utils.lecteur_fiche import lire_description, modeles_depuis_config  # noqa: E402
from src.utils.rapprochement_fiche import (  # noqa: E402
    CATEGORIES_DOUTES, LIENS, NIVEAUX, AccesBaseLecture, charger_configuration, rapprocher,
)


def mesurer(args):
    config_export = json.loads(Path(args.config).read_text(encoding='utf-8'))
    modeles = modeles_depuis_config(config_export)
    config = charger_configuration(args.reprise) if args.reprise else charger_configuration()
    csv.field_size_limit(sys.maxsize)
    c = Counter()
    niveaux, liens, statuts_piece, ref_interne = Counter(), Counter(), Counter(), Counter()
    remplacements, equivalences = Counter(), Counter()
    doutes, doutes_fiches, exemples = Counter(), Counter(), {}
    sources_marque = Counter()
    durees = []
    with AccesBaseLecture.ouvrir(args.base) as acces:
        marques = list(acces.marques().values())
        types = list(acces.types().values())
        debut = time.time()
        with open(args.csv, encoding=args.encodage, newline='') as f:
            for n, ligne in enumerate(csv.DictReader(f, delimiter=';', quotechar='"')):
                if n % args.pas:
                    continue
                if args.limite and c['fiches'] >= args.limite:
                    break
                desc = ligne.get('description') or ''
                if not desc.strip():
                    continue
                lecture = lire_description(desc, modeles, marques, types, ligne.get('marque') or '')
                if not lecture.appareils and not lecture.code_produit:
                    continue
                t = time.time()
                r = rapprocher(lecture, acces, config,
                               ref_interne=ligne.get('reference') or '',
                               ean=ligne.get('ean') or '', categorie=ligne.get('categorie') or '',
                               id_product=int(ligne['id_produit']) if (ligne.get('id_produit') or '').isdigit() else None)
                durees.append(time.time() - t)
                c['fiches'] += 1
                c['lignes'] += len(r.appareils)
                c['fiches_tronquees'] += r.liste_tronquee
                statuts_piece[r.identite.statut or '(sans pièce)'] += 1
                ref_interne[r.identite.statut_ref_interne or '(aucune)'] += 1
                for a in r.appareils:
                    niveaux[a.niveau] += 1
                    liens[a.lien] += 1
                    if a.marque_fiche == '' and a.provenance != 'table':
                        sources_marque[a.source_marque] += 1
                        sources_marque['trouvees'] += a.niveau != 'absent'
                c['fiches_annonces'] += any(a.marque_fiche == '' for a in r.appareils)
                remplacements.update(x.statut for x in r.remplacements)
                equivalences.update(x.statut for x in r.equivalences)
                for cat, liste in r.doutes_par_categorie().items():
                    doutes[cat] += len(liste)
                    doutes_fiches[cat] += 1
                    exemples.setdefault(cat, f"{ligne.get('id_produit')} : {liste[0].message[:110]}")
                c['fiches_sans_doute_appareil'] += not any(a.doutes for a in r.appareils)
        c['duree_s'] = round(time.time() - debut, 1)
    durees.sort()
    c['mediane_ms'] = round(1000 * durees[len(durees) // 2]) if durees else 0
    c['max_ms'] = round(1000 * durees[-1]) if durees else 0
    return dict(c=c, niveaux=niveaux, liens=liens, statuts_piece=statuts_piece,
                ref_interne=ref_interne, remplacements=remplacements, equivalences=equivalences,
                doutes=doutes, doutes_fiches=doutes_fiches, exemples=exemples,
                sources_marque=sources_marque)


def _pct(a, b):
    return f"{100 * a / b:.1f} %" if b else "—"


def _table(titre, compteur, total, libelles=None):
    l = [f"## {titre}", "", "| | Nombre | Part |", "|---|---|---|"]
    for cle, v in compteur.most_common():
        nom = f"{cle or '(vide)'}" + (f" — {libelles[cle]}" if libelles and cle in libelles else '')
        l.append(f"| {nom} | {v} | {_pct(v, total)} |")
    return l + [""]


def rapport(m, args) -> str:
    c = m['c']
    n, lignes = c['fiches'], c['lignes']
    a_deduire = m['sources_marque']['deduite'] + m['sources_marque']['a_choisir']
    l = ["# Mesure du rapprochement des fiches", "",
         f"- Échantillon : 1 produit sur {args.pas}" + (f", {args.limite} au plus" if args.limite else ''),
         f"- **Fiches rapprochées : {n}**, {lignes} lignes d'appareils, {c['duree_s']} s "
         f"(médiane {c['mediane_ms']} ms par fiche, maximum {c['max_ms']} ms)",
         f"- Fiches sans aucun doute sur les appareils : {c['fiches_sans_doute_appareil']} "
         f"({_pct(c['fiches_sans_doute_appareil'], n)})",
         f"- Listes probablement réduites : {c['fiches_tronquees']}",
         f"- **Lignes sans en-tête de marque (« annonces ») : {a_deduire} dans "
         f"{c['fiches_annonces']} fiches, marque déduite pour "
         f"{m['sources_marque']['deduite']} ({_pct(m['sources_marque']['deduite'], a_deduire)}) ; "
         f"parmi les {m['sources_marque']['trouvees']} lignes trouvées en base sous une marque, "
         f"déduite pour {_pct(m['sources_marque']['deduite'], m['sources_marque']['trouvees'])} "
         f"(les autres : plusieurs marques possibles, ou une marque du groupe non annoncée)**",
         ""]
    l += _table("Appareils par niveau", m['niveaux'], lignes, NIVEAUX)
    l += _table("Appareils par lien", m['liens'], lignes, LIENS)
    l += _table("Lignes sans en-tête : marque",
                Counter({k: v for k, v in m['sources_marque'].items() if k != 'trouvees'}), a_deduire)
    l += _table("Pièce de la fiche", m['statuts_piece'], n)
    l += _table("Référence interne / code produit", m['ref_interne'], n)
    l += _table("Remplacements", m['remplacements'], sum(m['remplacements'].values()))
    l += _table("Équivalences", m['equivalences'], sum(m['equivalences'].values()))
    l += ["## Doutes par catégorie", "", "| Catégorie | Fiches | Occurrences | Exemple |",
          "|---|---|---|---|"]
    for cat in CATEGORIES_DOUTES:
        if cat in m['doutes']:
            l.append(f"| {cat} — {CATEGORIES_DOUTES[cat]} | {m['doutes_fiches'][cat]} | "
                     f"{m['doutes'][cat]} | {m['exemples'][cat].replace('|', '/')} |")
    return "\n".join(l) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    p.add_argument('csv')
    p.add_argument('base', help='appareils.db (copie), ouverte en lecture seule')
    p.add_argument('--config', default=str(RACINE / 'data' / 'export_config.json'))
    p.add_argument('--reprise', help='configuration de la reprise (défaut : data/reprise_fiches.json)')
    p.add_argument('--rapport', help='rapport Markdown (sinon : sortie standard)')
    p.add_argument('--encodage', default='utf-8-sig')
    p.add_argument('--pas', type=int, default=1, help='un produit sur N')
    p.add_argument('--limite', type=int, default=0, help='nombre maximal de fiches rapprochées')
    args = p.parse_args()
    texte = rapport(mesurer(args), args)
    if args.rapport:
        Path(args.rapport).write_text(texte, encoding='utf-8')
    else:
        print(texte)


if __name__ == '__main__':
    main()
