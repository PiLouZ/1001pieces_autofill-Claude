#!/usr/bin/env python3
"""
Mesure du lecteur de fiches sur l'export des descriptions du site (CDC § 10.1)

Lit chaque description de l'export CSV PrestaShop (séparateur `;`, champs
entre `"`, en-têtes en 1ʳᵉ ligne : id_produit, reference, nom_produit, marque,
ean, categorie, actif, description) avec TOUS les profils Fiche de la
configuration, puis rapporte :
- la part lue correctement (critères en tête du rapport) ;
- les profils retenus, les blocs lus seulement par le repérage par texte ;
- les variantes de libellés et de balises rencontrées, par fréquence ;
- ce qui n'a pas été compris, avec des exemples.

Lecture seule : rien n'est écrit en base. `--base` (facultatif) ouvre
appareils.db en LECTURE SEULE pour connaître les marques de l'outil.

Usage :
    python3.13 scripts/mesurer_lecteur_fiches.py export_produits.csv \\
        --config data/export_config.json --rapport rapport.md --detail detail.csv \\
        [--base data/appareils.db] [--limite 500]
"""

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from src.utils.lecteur_fiche import (  # noqa: E402
    NATURES_NON_COMPRIS, lire_description, modeles_depuis_config, normaliser,
)

# Ce qui empêche de dire qu'une fiche est « lue correctement » (une liste sans
# titre, un profil ambigu ou une liste réduite sont lus : ce sont des doutes)
NATURES_GRAVES = {
    'bloc_non_lu', 'ligne_non_lue', 'appareil_sans_marque', 'lecture_divergente',
    'code_produit_absent', 'code_produit_multiple',
}
_CHIFFRES = re.compile(r'\d')


def _forme(texte: str, longueur: int = 70) -> str:
    """Texte réduit à sa forme (chiffres → 9) pour regrouper les exemples."""
    return _CHIFFRES.sub('9', texte)[:longueur]


def _signature(bloc) -> str:
    classes = '.'.join(sorted(bloc.classes))
    return f"<{bloc.balise}{'.' + classes if classes else ''}{' id' if bloc.id else ''}>"


def _valeurs_base(chemin: str, colonne: str):
    """Valeurs distinctes d'une colonne d'appareils (base ouverte en lecture seule)."""
    uri = f"file:{Path(chemin).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as cnx:
        return [r[0] for r in cnx.execute(
            f"SELECT DISTINCT {colonne} FROM appareils WHERE {colonne} <> ''")]


def _a_une_liste(desc: str, lecture) -> bool:
    return bool(lecture.titre_liste or lecture.appareils or 'class_perso5' in desc)


def mesurer(args):
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    modeles = modeles_depuis_config(config)
    marques = _valeurs_base(args.base, 'manufacturer') if args.base else []
    types = _valeurs_base(args.base, 'type') if args.base else []
    graves = NATURES_GRAVES | ({'marque_inconnue'} if marques else set())
    csv.field_size_limit(sys.maxsize)

    c = Counter()
    profils, sources_texte = Counter(), Counter()
    libelles = defaultdict(Counter)
    balises = defaultdict(Counter)
    natures, natures_fiches = Counter(), Counter()
    exemples = defaultdict(Counter)
    formats, troncatures = Counter(), Counter()
    detail = []
    debut = time.time()

    with open(args.csv, encoding=args.encodage, newline='') as f:
        lecteur_csv = csv.DictReader(f, delimiter=';', quotechar='"')
        for n, ligne in enumerate(lecteur_csv):
            if args.limite and n >= args.limite:
                break
            desc = ligne.get('description') or ''
            c['produits'] += 1
            if not desc.strip():
                c['sans_description'] += 1
                continue
            d = lire_description(desc, modeles, marques, types, ligne.get('marque') or '')
            if not _a_une_liste(desc, d):
                c['sans_liste'] += 1
                if d.code_produit:
                    c['sans_liste_avec_code'] += 1
                continue
            c['avec_liste'] += 1
            c['lignes'] += d.nb_lignes
            c['refs_par_marque'] += bool(d.references_par_marque)
            c['toutes_marques'] += d.toutes_marques
            c['annonce_produit'] += d.source_annonce == 'produit'
            c['remplacee_par'] += bool(d.remplacee_par)
            c['textes_libres'] += bool(d.textes_libres)
            c['marque_par_annonce'] += any(a.source_marque == 'annonce' for a in d.appareils)
            c['marque_a_deduire'] += any(a.source_marque == 'annonces' for a in d.appareils)
            c['lignes_typees'] += sum(1 for a in d.appareils if a.type_ligne)
            profils[d.profil or '(repérage par texte)'] += 1
            if d.profil_ambigu:
                c['profil_ambigu'] += 1
            for bloc, source in d.sources.items():
                libelles[bloc][(source, d.libelles.get(bloc, ''))] += 1
                if source == 'texte':
                    sources_texte[bloc] += 1
            # Balises des repères, en-têtes de marque et lignes d'appareil
            blocs = normaliser(desc)
            for bloc, index in d.blocs_reperes.items():
                balises[bloc][_signature(blocs[index])] += 1
            noms_marques = set(d.marques)
            vus = set()
            for b in blocs:
                if b.texte in noms_marques and b.texte not in vus:
                    vus.add(b.texte)
                    balises['entete_marque'][_signature(b)] += 1
            if d.appareils:
                balises['ligne_appareil'][_signature(blocs[d.appareils[0].bloc])] += 1
            for a in d.appareils:
                formats[a.format] += 1
            for motif in d.motifs_troncature:
                troncatures[motif] += 1
            if d.liste_tronquee:
                c['tronquees'] += 1
            vues = set()
            for nc in d.non_compris:
                natures[nc.nature] += 1
                if nc.nature not in vues:
                    natures_fiches[nc.nature] += 1
                    vues.add(nc.nature)
                exemples[nc.nature][_forme(nc.texte or nc.detail)] += 1
            # Contrôle : référence interne = code produit, préfixe retiré (§ 5.1)
            ref = (ligne.get('reference') or '').strip()
            principale = d.reference_principale or ''
            if principale and ref:
                if ref == principale:
                    c['ref_egale'] += 1
                elif ref.endswith(principale):
                    c['ref_prefixee'] += 1
                else:
                    c['ref_differente'] += 1
            correcte = bool(d.code_produit and d.appareils) and not (vues & graves)
            c['correctes'] += correcte
            if not correcte or d.profil_ambigu or d.liste_tronquee:
                detail.append({
                    'id_produit': ligne.get('id_produit'), 'reference': ref,
                    'code_produit': ' '.join(d.code_produit), 'lignes': d.nb_lignes,
                    'profil': d.profil or '', 'correcte': int(correcte),
                    'natures': ' '.join(sorted(vues)),
                    'exemple': next((nc.texte[:120] for nc in d.non_compris
                                     if nc.nature in graves and nc.texte), ''),
                })
    c['duree_s'] = round(time.time() - debut, 1)
    return c, profils, sources_texte, libelles, balises, natures, natures_fiches, \
        exemples, formats, troncatures, detail, bool(marques)


def _pct(a, b):
    return f"{100 * a / b:.1f} %" if b else "—"


def rapport(resultats) -> str:
    (c, profils, sources_texte, libelles, balises, natures, natures_fiches, exemples,
     formats, troncatures, detail, avec_base) = resultats
    n = c['avec_liste']
    l = ["# Mesure du lecteur de fiches", "",
         f"- Produits lus : {c['produits']} ({c['sans_description']} sans description, "
         f"{c['sans_liste']} sans liste d'appareils dont {c['sans_liste_avec_code']} avec un code produit)",
         f"- **Descriptions avec liste : {n}**, {c['lignes']} lignes d'appareils, {c['duree_s']} s",
         f"- **Lues correctement : {c['correctes']} ({_pct(c['correctes'], n)})** — code produit, "
         f"au moins un appareil, et aucun de : {', '.join(sorted(NATURES_GRAVES))}"
         + (", marque_inconnue (marques de la base chargées)" if avec_base else
            " (marques de la base non chargées : marque_inconnue hors critère)"),
         f"- Profil ambigu : {c['profil_ambigu']} ; listes probablement réduites : {c['tronquees']}",
         f"- Marque à déduire parmi plusieurs marques annoncées (lignes sans en-tête de marque, "
         f"rapprochement de l'étape 2) : {c['marque_a_deduire']} fiches",
         f"- Marque des lignes tirée de la seule marque annoncée : {c['marque_par_annonce']} fiches ; "
         f"lignes avec un type écrit : {c['lignes_typees']} ; « Réf. fabricant » par marque : "
         f"{c['refs_par_marque']} fiches ; « toutes marques » : {c['toutes_marques']} ; "
         f"texte libre dans l'en-tête : {c['textes_libres']} fiches",
         f"- Marques prises de la marque du produit (aucune annonce dans la description) : "
         f"{c['annonce_produit']} fiches ; « Remplacé par » : {c['remplacee_par']} fiches",
         f"- Référence interne / code produit : égale {c['ref_egale']}, préfixée {c['ref_prefixee']}, "
         f"différente {c['ref_differente']}", ""]
    l += ["## Profils retenus", "", "| Profil | Fiches |", "|---|---|"]
    l += [f"| {p} | {v} |" for p, v in profils.most_common()]
    l += ["", "## Blocs lus seulement par le repérage par texte", "", "| Bloc | Fiches |", "|---|---|"]
    l += [f"| {b} | {v} |" for b, v in sources_texte.most_common()] or ["| — | 0 |"]
    l += ["", "## Variantes de libellés", ""]
    for bloc, compteur in libelles.items():
        l += [f"**{bloc}**", "", "| Source | Libellé | Fiches |", "|---|---|---|"]
        l += [f"| {s} | `{lib}` | {v} |" for (s, lib), v in compteur.most_common(15)]
        l.append("")
    l += ["## Variantes de balises", ""]
    for bloc, compteur in balises.items():
        l += [f"**{bloc}** : " + ", ".join(f"`{sig}` × {v}" for sig, v in compteur.most_common(8)), ""]
    l += ["## Formats de lignes d'appareils", "", "| Format | Lignes |", "|---|---|"]
    l += [f"| {f} | {v} |" for f, v in formats.most_common()]
    l += ["", "## Listes probablement réduites (motifs)", "", "| Motif | Fiches |", "|---|---|"]
    l += [f"| {m} | {v} |" for m, v in troncatures.most_common()] or ["| — | 0 |"]
    l += ["", "## Non compris", "", "| Nature | Fiches | Occurrences | Exemples (chiffres → 9) |",
          "|---|---|---|---|"]
    for nature, v in natures_fiches.most_common():
        ex = " · ".join(f"`{t}` ×{k}" for t, k in exemples[nature].most_common(5) if t)
        l.append(f"| {nature} ({NATURES_NON_COMPRIS.get(nature, '')}) | {v} | {natures[nature]} | {ex} |")
    return "\n".join(l) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    p.add_argument('csv')
    p.add_argument('--config', default=str(RACINE / 'data' / 'export_config.json'))
    p.add_argument('--rapport', help='rapport Markdown (sinon : sortie standard)')
    p.add_argument('--detail', help='CSV des fiches non lues correctement, ambiguës ou réduites')
    p.add_argument('--base', help='appareils.db, ouverte en lecture seule (marques connues)')
    p.add_argument('--encodage', default='utf-8-sig')
    p.add_argument('--limite', type=int, default=0, help='nombre maximal de produits lus')
    args = p.parse_args()
    resultats = mesurer(args)
    texte = rapport(resultats)
    if args.rapport:
        Path(args.rapport).write_text(texte, encoding='utf-8')
    else:
        print(texte)
    if args.detail:
        detail = resultats[10]
        with open(args.detail, 'w', encoding='utf-8', newline='') as f:
            champs = ['id_produit', 'reference', 'code_produit', 'lignes', 'profil',
                      'correcte', 'natures', 'exemple']
            w = csv.DictWriter(f, fieldnames=champs, delimiter=';')
            w.writeheader()
            w.writerows(detail)


if __name__ == '__main__':
    main()
