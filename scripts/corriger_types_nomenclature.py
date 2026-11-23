#!/usr/bin/env python3
"""
Corrections de type d'appareils — règles de nomenclature (CDC § 9.1, lot 1).

Applique une liste FIGÉE, relue avec le client : pour chaque appareil, le type
attendu en base et le type qui le remplace. Un appareil dont le type a changé
depuis (à la main, par un import) est ignoré et signalé, jamais écrasé.

Fermer l'application avant d'écrire : elle garde en mémoire les types affichés.

Usage :
    python3 scripts/corriger_types_nomenclature.py              # simulation, n'écrit rien
    python3 scripts/corriger_types_nomenclature.py --ecrire     # applique, après sauvegarde
    python3 scripts/corriger_types_nomenclature.py --annuler    # simulation du retour arrière
    python3 scripts/corriger_types_nomenclature.py --annuler --ecrire
    options : --liste chemin.csv   --base chemin.db   --oui (sans question)

Codes de sortie : 0 = fait (ou simulation), 1 = abandon/erreur, 2 = comptage
par type différent de l'attendu après écriture (le retour arrière est possible).
"""

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_PAR_DEFAUT = RACINE / "data" / "appareils.db"
LISTE_PAR_DEFAUT = RACINE / "data" / "corrections" / "nomenclature_lot1.csv"


class _PorteurDeBase:
    """BackupService lit le chemin via `parent_window.db_manager.db_file`, et
    retombe sinon sur la base de production : sans ce porteur, un essai sur une
    copie sauvegarderait la vraie base, pas celle qu'on modifie."""
    def __init__(self, db_manager):
        self.db_manager = db_manager


def _afficher_bilan(bilan, apercu=8):
    from collections import Counter
    print(f"\nSens : {bilan.sens}")
    print(f"  À corriger    : {len(bilan.a_corriger)}")
    print(f"  Déjà faites   : {len(bilan.deja_faites)}")
    print(f"  Ignorées      : {len(bilan.ignorees)}")
    par_famille = Counter((c.famille, c.type_avant, c.type_apres) for c in bilan.a_corriger)
    if par_famille:
        print("\n  Par famille :")
        for (fam, a, b), n in sorted(par_famille.items(), key=lambda x: (int(x[0][0]) if x[0][0].isdigit() else 99, x[0])):
            print(f"    famille {fam:>3} : {n:>5}  {a} → {b}")
    if bilan.ignorees:
        print("\n  Ignorées (type changé depuis la liste, ou appareil absent) :")
        for c, trouve in bilan.ignorees[:apercu]:
            etat = "absent" if trouve is None else f"type en base « {trouve} »"
            print(f"    id {c.appareil_id} {c.marque} {c.ref_commerciale or c.ref_modele} : "
                  f"attendu « {c.type_avant} », {etat}")
        if len(bilan.ignorees) > apercu:
            print(f"    … et {len(bilan.ignorees) - apercu} autre(s)")
    attendu = bilan.ecart_attendu()
    if attendu:
        print("\n  Comptage par type (avant → attendu) :")
        for t in sorted(attendu):
            avant = bilan.comptage_avant[t]
            print(f"    {t:<18} {avant:>7} → {avant + attendu[t]:>7}  ({attendu[t]:+d})")


def main():
    parser = argparse.ArgumentParser(description="Corrections de type (règles de nomenclature)")
    parser.add_argument('--liste', default=str(LISTE_PAR_DEFAUT))
    parser.add_argument('--base', default=str(BASE_PAR_DEFAUT))
    parser.add_argument('--annuler', action='store_true', help="retour arrière")
    parser.add_argument('--ecrire', action='store_true', help="écrire (sinon simulation)")
    parser.add_argument('--oui', action='store_true', help="ne pas demander confirmation")
    args = parser.parse_args()

    from src.data.database_manager import DatabaseManager
    from src.services.correction_types_service import (
        CorrectionTypesService, SENS_ANNULER, SENS_APPLIQUER, lire_liste)

    try:
        corrections = lire_liste(args.liste)
    except (OSError, ValueError) as e:
        print(f"Liste illisible : {e}")
        return 1
    if not Path(args.base).exists():
        print(f"Base introuvable : {args.base}")
        return 1

    sens = SENS_ANNULER if args.annuler else SENS_APPLIQUER
    # « nomenclature_lot1.csv » → « lot1 » (provenance de l'historique, nom de la sauvegarde)
    lot = Path(args.liste).stem.replace('nomenclature_', '') or 'liste'
    db = DatabaseManager(str(args.base))
    service = CorrectionTypesService(db)

    print(f"Liste : {args.liste} ({len(corrections)} appareils)")
    print(f"Base  : {args.base}")
    bilan = service.preparer(corrections, sens)
    _afficher_bilan(bilan)

    if not args.ecrire:
        print("\nSimulation : rien n'a été écrit (ajouter --ecrire pour appliquer).")
        return 0
    if not bilan.a_corriger:
        print("\nRien à écrire.")
        return 0
    if not args.oui:
        print("\nFermez l'application avant de continuer.")
        if input(f"Écrire {len(bilan.a_corriger)} correction(s) ? [oui/NON] ").strip().lower() != "oui":
            print("Abandon : rien n'a été écrit.")
            return 1

    from src.services.backup_service import BackupService
    print("\nSauvegarde de la base avant écriture…")
    copie = BackupService(parent_window=_PorteurDeBase(db)).create_backup(reason=f"nomenclature_{lot}")
    if not copie:
        print("ÉCHEC de la sauvegarde : abandon, rien n'a été écrit.")
        return 1
    print(f"  Copie : {copie}")

    bilan = service.executer(corrections, sens, provenance=f"règles de nomenclature, {lot}")
    if not bilan.ecrit:
        print("ÉCHEC de l'écriture (voir les journaux) : la base n'a pas été modifiée.")
        return 1
    print(f"\n{len(bilan.a_corriger)} type(s) écrit(s).")
    if not bilan.historique_ecrit:
        print("ATTENTION : l'historique des modifications n'a pas été écrit.")
    if bilan.comptage_conforme:
        print("Comptage par type après écriture : conforme à l'attendu.")
        return 0
    print("ÉCART de comptage par type :")
    print(f"  attendu  : {bilan.ecart_attendu()}")
    print(f"  constaté : {bilan.ecart_constate()}")
    print("Retour arrière possible : relancer avec --annuler --ecrire.")
    return 2


if __name__ == '__main__':
    sys.exit(main())
