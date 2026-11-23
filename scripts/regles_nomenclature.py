#!/usr/bin/env python3
"""
Règles de nomenclature — moteur sans écran (CDC docs/cdc_regles_nomenclature.md, lot 3).

Trois commandes, en simulation par défaut (rien n'est écrit sans --ecrire) :

    python3 scripts/regles_nomenclature.py catalogue [--ecrire]
        contrôle le catalogue versionné data/regles_nomenclature.csv et, avec
        --ecrire, l'ajoute à la table des règles (une règle déjà en base n'est
        jamais écrasée) ;
    python3 scripts/regles_nomenclature.py proposer [--ecrire]
        résout chaque appareil par les règles VALIDÉES et affiche les
        propositions de type ; avec --ecrire, les range dans propositions_type
        avec les mesures des règles. Aucun type d'appareil n'est modifié ;
    python3 scripts/regles_nomenclature.py decouvrir [--ecrire]
        cherche des règles candidates ; avec --ecrire, les ajoute en statut
        « proposée » (elles ne typent rien sans validation).

Options : --base chemin.db  --catalogue chemin.csv  --apercu N

Seules les deux tables du moteur sont écrites : la table appareils n'est jamais
touchée (l'application des propositions passera par la revue, lot 4).
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_PAR_DEFAUT = RACINE / "data" / "appareils.db"


def _catalogue(service, args) -> int:
    bilan = service.charger_catalogue(args.catalogue, ecrire=args.ecrire)
    print(f"Catalogue : {bilan.lues} règle(s) lue(s)")
    print(f"  {'Ajoutées' if args.ecrire else 'À ajouter'} : {bilan.ajoutees}")
    print(f"  Déjà en base : {bilan.deja_presentes}")
    print(f"  Refusées : {len(bilan.refusees)}")
    for ligne, erreurs in bilan.refusees:
        print(f"    {ligne.get('cible')} {ligne.get('motif')} → {ligne.get('type_resultat')} : "
              f"{' ; '.join(erreurs)}")
    return 1 if bilan.refusees else 0


def _proposer(service, args) -> int:
    debut = time.time()
    bilan = service.calculer_propositions(ecrire=args.ecrire)
    if bilan.erreur and not bilan.propositions:
        print(f"Échec : {bilan.erreur}")
        return 1
    regles = {r.id: r for r in service.regles()}
    print(f"Appareils : {bilan.appareils} ; couverts par une règle validée : {bilan.couverts} "
          f"({time.time() - debut:.1f} s)")
    print(f"Propositions : {len(bilan.propositions)} "
          f"(fortes {bilan.par_force()['forte']}, simples {bilan.par_force()['simple']}) ; "
          f"écartées par un refus : {bilan.refusees} ; conflits entre clés : {len(bilan.conflits)}")
    for (regle_id, avant, apres), n in bilan.par_regle().most_common():
        r = regles.get(regle_id)
        print(f"  {n:>6}  {r.cible if r else '?'} {r.motif if r else regle_id} : "
              f"{avant or '(vide)'} → {apres}")
    for ident, r_nom, r_code in bilan.conflits[:args.apercu]:
        print(f"  conflit appareil {ident} : {r_nom} / {r_code}")
    if bilan.types_hors_liste:
        print("Types en base hors de la liste des types autorisés :")
        for t, n in bilan.types_hors_liste.most_common():
            print(f"  {n:>6}  {t}")
    if args.ecrire:
        print("Écrit." if bilan.ecrit else f"ÉCHEC de l'écriture : {bilan.erreur}")
        return 0 if bilan.ecrit else 1
    print("\nSimulation : rien n'a été écrit (ajouter --ecrire pour ranger les propositions).")
    return 0


def _decouvrir(service, args) -> int:
    debut = time.time()
    bilan = service.decouvrir_regles(ecrire=args.ecrire)
    print(f"Découverte : {len(bilan.candidates)} règle(s) candidate(s), "
          f"{len(bilan.nouvelles)} nouvelle(s), {len(bilan.zones_grises)} zone(s) grise(s) "
          f"({time.time() - debut:.1f} s)")
    par_cle = Counter((c.portee, c.cle) for c in bilan.nouvelles)
    for (portee, cle), n in sorted(par_cle.items()):
        print(f"  {portee:<7} {cle:<5} {n:>5}")
    for c in sorted(bilan.nouvelles, key=lambda c: -c.couverture)[:args.apercu]:
        print(f"  {c.portee}:{c.cible} {c.cle} {c.motif} → {c.type_resultat} "
              f"({c.accord}/{c.couverture})")
    if args.ecrire:
        print(f"Ajoutées en statut « proposée » : {bilan.ajoutees}")
    else:
        print("\nSimulation : rien n'a été écrit (ajouter --ecrire pour les ranger).")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Règles de nomenclature (moteur sans écran)")
    parser.add_argument('commande', choices=('catalogue', 'proposer', 'decouvrir'))
    parser.add_argument('--base', default=str(BASE_PAR_DEFAUT))
    parser.add_argument('--catalogue', default=None)
    parser.add_argument('--ecrire', action='store_true', help="écrire (sinon simulation)")
    parser.add_argument('--apercu', type=int, default=15)
    args = parser.parse_args()

    if not Path(args.base).exists():
        print(f"Base introuvable : {args.base}")
        return 1
    from src.data.database_manager import DatabaseManager
    from src.services.regle_nomenclature_service import RegleNomenclatureService
    db = DatabaseManager(str(args.base))
    try:
        service = RegleNomenclatureService(db)
        if not service.types_autorises:
            print("Liste des types autorisés illisible : abandon.")
            return 1
        print(f"Base : {args.base}")
        return {'catalogue': _catalogue, 'proposer': _proposer,
                'decouvrir': _decouvrir}[args.commande](service, args)
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
