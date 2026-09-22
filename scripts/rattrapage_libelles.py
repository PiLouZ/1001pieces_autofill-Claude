#!/usr/bin/env python3
"""
Rattrapage ponctuel — propager les libellés aux références restées anonymes.

Les lots 1 à 3 empêchent le problème de se reproduire, mais ne réparent rien :
`propagate_description` ne s'exécute qu'au moment où une relation est créée, et
les références déjà en base ont vu la leur créée il y a des mois. Ce script est
la passe de rattrapage correspondante.

Règle appliquée — volontairement prudente :
  - une référence sans libellé hérite de celui de ses voisines (équivalence, ou
    succession dans les deux sens) ;
  - seulement si toutes ses voisines nommées portent LE MÊME libellé. Deux
    voisines qui divergent sont une ambiguïté que ce script ne tranche pas :
    elle est signalée, et l'harmonisation du gestionnaire permet de choisir ;
  - un libellé existant n'est jamais écrasé (garanti une seconde fois par
    `propagate_description`, qui fait l'écriture réelle) ;
  - plusieurs passes : réparer une référence peut en rendre une autre réparable
    le long d'une chaîne de succession.

Usage :
    python3 scripts/rattrapage_libelles.py                 # simulation, n'écrit rien
    python3 scripts/rattrapage_libelles.py --ecrire        # applique, après sauvegarde
    python3 scripts/rattrapage_libelles.py --base chemin.db
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_PAR_DEFAUT = RACINE / "data" / "appareils.db"
MAX_PASSES = 10


def _connexion(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    return conn


def charger_libelles(conn):
    """ref → libellé nettoyé (chaîne vide si absent)."""
    return {
        r["ref_piece"]: (r["description"] or "").strip()
        for r in conn.execute("SELECT ref_piece, COALESCE(description, '') AS description FROM pieces")
    }


def charger_voisinage(conn):
    """ref → set des refs qui lui sont liées, tous types de relation confondus.

    Le voisinage est symétrique : une référence remplacée et sa remplaçante se
    valent ici, puisque le libellé peut légitimement voyager dans les deux sens.
    """
    voisins = {}

    def lier(a, b):
        if not a or not b or a == b:
            return
        voisins.setdefault(a, set()).add(b)
        voisins.setdefault(b, set()).add(a)

    for r in conn.execute(
        "SELECT ref_old, ref_new FROM piece_supersessions WHERE ref_new IS NOT NULL"
    ):
        lier(r["ref_old"], r["ref_new"])

    for r in conn.execute(
        """SELECT g1.ref_piece AS a, g2.ref_piece AS b
           FROM piece_equivalence_groups g1
           JOIN piece_equivalence_groups g2
             ON g1.group_id = g2.group_id AND g1.ref_piece < g2.ref_piece"""
    ):
        lier(r["a"], r["b"])

    return voisins


def calculer_reparations(libelles, voisins):
    """Retourne (reparations, ambigues, sans_source).

    reparations : liste de (ref, libellé, source, numéro de passe)
    ambigues    : liste de (ref, [libellés candidats])
    sans_source : liste des refs anonymes sans aucune voisine nommée
    """
    libelles = dict(libelles)          # copie : la simulation ne touche pas l'original
    reparations, ambigues = [], []
    deja_ambigues = set()

    for passe in range(1, MAX_PASSES + 1):
        anonymes = [ref for ref, lib in libelles.items() if not lib]
        progres = False

        for ref in anonymes:
            candidats = {}
            for voisine in voisins.get(ref, ()):
                lib = libelles.get(voisine, "")
                if lib:
                    candidats.setdefault(lib, voisine)

            if not candidats:
                continue
            if len(candidats) > 1:
                if ref not in deja_ambigues:
                    deja_ambigues.add(ref)
                    ambigues.append((ref, sorted(candidats)))
                continue

            libelle, source = next(iter(candidats.items()))
            libelles[ref] = libelle
            reparations.append((ref, libelle, source, passe))
            progres = True

        if not progres:
            break

    sans_source = sorted(
        ref for ref, lib in libelles.items()
        if not lib and ref not in deja_ambigues
    )
    return reparations, ambigues, sans_source


def afficher(reparations, ambigues, sans_source, total_anonymes):
    print(f"\n{total_anonymes} référence(s) sans libellé en base.\n")

    if reparations:
        print(f"── {len(reparations)} réparation(s) proposée(s) " + "─" * 40)
        largeur = max(len(r[0]) for r in reparations)
        for ref, libelle, source, passe in reparations:
            suffixe = f"   [passe {passe}]" if passe > 1 else ""
            print(f"  {ref:<{largeur}}  ←  « {libelle} »   (via {source}){suffixe}")
    else:
        print("Aucune réparation possible.")

    if ambigues:
        print(f"\n── {len(ambigues)} ambiguïté(s), non traitée(s) " + "─" * 30)
        print("  Voisines nommées différemment : à trancher dans le gestionnaire")
        print("  (filtre « Libellés incohérents » → bouton « Harmoniser »).")
        for ref, candidats in ambigues:
            print(f"  {ref}  ←  " + "  |  ".join(f"« {c} »" for c in candidats))

    if sans_source:
        print(f"\n── {len(sans_source)} référence(s) sans voisine nommée " + "─" * 22)
        print("  Aucun libellé à propager : saisie manuelle requise")
        print("  (filtre « Sans libellé » du gestionnaire).")
        apercu = ", ".join(sans_source[:12])
        reste = f", … et {len(sans_source) - 12} autre(s)" if len(sans_source) > 12 else ""
        print(f"  {apercu}{reste}")


def ecrire(chemin_base, reparations):
    """Applique les réparations via `propagate_description`, la primitive du lot 1.

    Passer par elle plutôt que par un UPDATE direct garantit que le rattrapage
    obéit exactement à la règle du code corrigé, y compris la non-écrasure.
    """
    from src.data.database_manager import DatabaseManager
    from src.services.backup_service import BackupService

    db = DatabaseManager(str(chemin_base))

    class _PorteurDeBase:
        """BackupService lit le chemin via `parent_window.db_manager.db_file`, et
        retombe sinon sur la base de production. Sans ce porteur, un essai sur une
        copie sauvegarderait la vraie base — jamais celle qu'on s'apprête à
        modifier."""
        def __init__(self, db_manager):
            self.db_manager = db_manager

    print("\nSauvegarde de la base avant écriture…")
    sauvegarde = BackupService(
        parent_window=_PorteurDeBase(db)
    ).create_backup(reason="rattrapage_libelles")
    if sauvegarde:
        print(f"  Copie créée : {sauvegarde}")
    else:
        print("  ATTENTION : la sauvegarde a échoué ou a été sautée.")
        if input("  Continuer quand même ? [oui/NON] ").strip().lower() != "oui":
            print("  Abandon — rien n'a été écrit.")
            return 1

    appliquees = 0
    for ref, libelle, source, _passe in reparations:
        if db.propagate_description(source, ref):
            appliquees += 1
        else:
            print(f"  Ignorée : {ref} (via {source}) — refusée par propagate_description")

    print(f"\n{appliquees} libellé(s) propagé(s) sur {len(reparations)} proposition(s).")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=str(BASE_PAR_DEFAUT),
                        help="chemin de la base SQLite")
    parser.add_argument("--ecrire", action="store_true",
                        help="appliquer réellement (sans ce drapeau : simulation)")
    args = parser.parse_args()

    chemin = Path(args.base)
    if not chemin.exists():
        print(f"Base introuvable : {chemin}")
        return 2

    conn = _connexion(chemin)
    try:
        libelles = charger_libelles(conn)
        voisins = charger_voisinage(conn)
    finally:
        conn.close()

    total_anonymes = sum(1 for lib in libelles.values() if not lib)
    reparations, ambigues, sans_source = calculer_reparations(libelles, voisins)
    afficher(reparations, ambigues, sans_source, total_anonymes)

    if not args.ecrire:
        print("\n(simulation — rien n'a été écrit ; relancer avec --ecrire pour appliquer)")
        return 0

    if not reparations:
        return 0
    return ecrire(chemin, reparations)


if __name__ == "__main__":
    sys.exit(main())
