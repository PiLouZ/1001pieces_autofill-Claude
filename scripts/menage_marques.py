#!/usr/bin/env python3
"""
Ménage des marques (2026-11-24) — liste figée, puis application.

- marque collée retirée des références (« SMEG ST995 » → « ST995 ») ;
- écritures de marque ramenées à leur nom (« Glem » → « Glem Gas »,
  « Concord » → « Concorde ») ;
- doublons ainsi révélés fusionnés (pièces transférées, doublon retiré).

Fermer l'application avant d'écrire : elle garde en mémoire les valeurs affichées.

Usage :
    python3 scripts/menage_marques.py liste              # (re)calcule la liste depuis la base, n'écrit pas la base
    python3 scripts/menage_marques.py                    # simulation de la liste figée
    python3 scripts/menage_marques.py --ecrire           # applique, après sauvegarde
    python3 scripts/menage_marques.py --annuler [--ecrire]   # retour arrière (hors fusions)
    options : --liste chemin.csv   --base chemin.db   --oui (sans question)

Codes de sortie : 0 = fait (ou simulation), 1 = abandon/erreur, 2 = écart de
comptage après écriture.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_PAR_DEFAUT = RACINE / "data" / "appareils.db"
LISTE_PAR_DEFAUT = RACINE / "data" / "corrections" / "menage_marques.csv"


class _PorteurDeBase:
    """BackupService lit le chemin via `parent_window.db_manager.db_file`, et
    retombe sinon sur la base de production (voir corriger_types_nomenclature)."""
    def __init__(self, db_manager):
        self.db_manager = db_manager


def _resume_liste(lignes, apercu=6):
    from src.services.menage_marques_service import (
        NATURE_FUSION, NATURE_MARQUE, NATURE_REFERENCE)
    par_nature = Counter(l.nature for l in lignes)
    print(f"  Références nettoyées : {par_nature[NATURE_REFERENCE]} "
          f"({len({l.appareil_id for l in lignes if l.nature == NATURE_REFERENCE})} appareils)")
    print(f"  Marques renommées    : {par_nature[NATURE_MARQUE]}")
    print(f"  Fusions              : {par_nature[NATURE_FUSION]}")
    par_marque = Counter(l.marque for l in lignes if l.nature == NATURE_REFERENCE)
    print("  Références par marque : " + ", ".join(f"{m} {n}" for m, n in par_marque.most_common(12))
          + (" …" if len(par_marque) > 12 else ""))
    renommees = Counter((l.avant, l.apres) for l in lignes if l.nature == NATURE_MARQUE)
    for (a, b), n in renommees.items():
        print(f"    marque « {a} » → « {b} » : {n}")
    for l in [l for l in lignes if l.nature == NATURE_FUSION][:apercu]:
        print(f"    fusion : id {l.appareil_id} ({l.marque} {l.avant}) → id {l.cible}")


def _afficher_bilan(bilan, apercu=8):
    print(f"\nSens : {bilan.sens}")
    print(f"  À faire       : {len(bilan.a_faire)}  {dict(bilan.par_nature())}")
    print(f"  Déjà faites   : {len(bilan.deja_faites)}")
    print(f"  Ignorées      : {len(bilan.ignorees)}")
    for l, raison in bilan.ignorees[:apercu]:
        print(f"    {l.nature} id {l.appareil_id} {l.champ} : {raison}")
    if len(bilan.ignorees) > apercu:
        print(f"    … et {len(bilan.ignorees) - apercu} autre(s)")


def main():
    parser = argparse.ArgumentParser(description="Ménage des marques")
    parser.add_argument('commande', nargs='?', choices=['liste'], help="liste = calculer la liste figée")
    parser.add_argument('--liste', default=str(LISTE_PAR_DEFAUT))
    parser.add_argument('--base', default=str(BASE_PAR_DEFAUT))
    parser.add_argument('--annuler', action='store_true', help="retour arrière (hors fusions)")
    parser.add_argument('--ecrire', action='store_true', help="écrire (sinon simulation)")
    parser.add_argument('--oui', action='store_true', help="ne pas demander confirmation")
    args = parser.parse_args()

    if not Path(args.base).exists():
        print(f"Base introuvable : {args.base}")
        return 1

    from src.data.database_manager import DatabaseManager
    from src.services.menage_marques_service import (
        MenageMarquesService, SENS_ANNULER, SENS_APPLIQUER, calculer_liste, ecrire_liste, lire_liste)

    db = DatabaseManager(str(args.base))
    service = MenageMarquesService(db)
    print(f"Base  : {args.base}")

    if args.commande == 'liste':
        lignes = calculer_liste(service.lire_appareils())
        ecrire_liste(args.liste, lignes)
        print(f"Liste écrite : {args.liste} ({len(lignes)} lignes) — la base n'a pas été modifiée")
        _resume_liste(lignes)
        return 0

    try:
        lignes = lire_liste(args.liste)
    except (OSError, ValueError) as e:
        print(f"Liste illisible : {e}")
        return 1
    print(f"Liste : {args.liste} ({len(lignes)} lignes)")
    sens = SENS_ANNULER if args.annuler else SENS_APPLIQUER
    bilan = service.preparer(lignes, sens)
    _afficher_bilan(bilan)

    if not args.ecrire:
        print("\nSimulation : rien n'a été écrit (ajouter --ecrire pour appliquer).")
        return 0
    if not bilan.a_faire:
        print("\nRien à écrire.")
        return 0
    if not args.oui:
        print("\nFermez l'application avant de continuer.")
        if input(f"Écrire {len(bilan.a_faire)} changement(s) ? [oui/NON] ").strip().lower() != "oui":
            print("Abandon : rien n'a été écrit.")
            return 1

    from src.services.backup_service import BackupService
    print("\nSauvegarde de la base avant écriture…")
    copie = BackupService(parent_window=_PorteurDeBase(db)).create_backup(reason="menage_marques")
    if not copie:
        print("ÉCHEC de la sauvegarde : abandon, rien n'a été écrit.")
        return 1
    print(f"  Copie : {copie}")

    bilan = service.executer(lignes, sens)
    if not bilan.ecrit:
        print("ÉCHEC de l'écriture (voir les journaux) : la base n'a pas été modifiée.")
        return 1
    print(f"\nÉcrit : {dict(bilan.par_nature())} ; fusions réussies : {bilan.fusions_ecrites}")
    if not bilan.historique_ecrit:
        print("ATTENTION : l'historique des modifications n'a pas été écrit.")
    if bilan.comptage_conforme:
        print(f"Appareils : {bilan.nb_appareils_avant} → {bilan.nb_appareils_apres} (conforme aux fusions).")
        return 0
    print(f"ÉCART : appareils {bilan.nb_appareils_avant} → {bilan.nb_appareils_apres}, "
          f"fusions écrites {bilan.fusions_ecrites}. Restaurer la sauvegarde si besoin : {copie}")
    return 2


if __name__ == '__main__':
    sys.exit(main())
