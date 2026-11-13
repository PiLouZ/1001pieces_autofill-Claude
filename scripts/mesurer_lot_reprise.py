#!/usr/bin/env python3
"""
Mesure d'un lot de la reprise des fiches du site (CDC § 7.4, étape 4)

Sur une COPIE de la base (faite avec l'API backup de sqlite3, jamais cp) :
1. adopte l'export (deux CSV) en repartant de zéro ;
2. analyse le 1er lot (taille réglable) : durée, part déjà en base, doutes ;
3. planifie par les règles de l'import, sans question (§ 10.12 à 10.14 : lignes
   non tranchées non importées, créations bancales retenues), enregistre :
   durée, croissance de la base ;
4. relance le MÊME lot (état remis au début du lot) : aucun appareil, lien ni
   relation ne doit être ajouté.

Usage :
    python3.13 scripts/mesurer_lot_reprise.py copie.db produits.csv compatibilites.csv \\
        --config data/export_config.json [--taille 100] [--lots 1] [--rapport rapport.json]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.data.database_manager import DatabaseManager  # noqa: E402
from src.services.reprise_site_service import RepriseSiteService, taille_base  # noqa: E402
from src.utils.lecteur_fiche import modeles_depuis_config  # noqa: E402
from src.utils.reprise_site import mesures_lot  # noqa: E402


def compter(db):
    q = lambda t: db.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    return {t: q(t) for t in ('appareils', 'pieces', 'piece_associations', 'piece_supersessions',
                              'piece_equivalence_groups', 'produits_site')}


def par_regles(lot):
    """Règles de l'import (§ 10.12) : aucune question, lignes non tranchées non importées."""
    plan = lot.planifier_par_regles()
    stats = {'non_importees': {'fiches': len(plan.non_importees),
                               'lignes': sum(len(v) for v in plan.non_importees.values())},
             'de_cote': [lot.fiches[i].raison_de_cote for i in plan.de_cote]}
    return plan, stats


def un_lot(service, db, taille, journal):
    t = time.time()
    lot = service.analyser_lot_suivant(taille)
    if lot is None:
        return None
    analyse = time.time() - t
    plan, stats_q = par_regles(lot)
    lignes_de_cote = stats_q['non_importees']['lignes']
    avant = compter(db)
    taille_avant = taille_base(db.db_file)
    res = service.enregistrer_lot(lot, plan)
    service.apres_lot(res)          # champs d'appareils pris sur le site (noms complétés…)
    apres = compter(db)
    m = mesures_lot(lot, plan)
    m.update({
        'premier_id': lot.export.premier_id, 'dernier_id': lot.export.dernier_id,
        'produits_sans_contenu': lot.export.sans_contenu, 'analyse_totale_s': round(analyse, 1),
        'ecriture_s': round(res.ecriture_s, 1), 'ok': res.ok, 'erreur': res.erreur,
        'lignes_mises_de_cote': lignes_de_cote, 'fiches_de_cote': len(plan.de_cote),
        'croissance_mo': round((taille_base(db.db_file) - taille_avant) / 1e6, 1),
        'ajouts': {k: apres[k] - avant[k] for k in apres},
        'fiches_a_refaire': len(plan.a_refaire),
        'resultat': res.resume(),
        'champs_pris_sur_le_site': res.champs_modifies,
        'regles': stats_q,
        'import': {k: (res.resultats_import or {}).get(k) for k in (
            'new_entries', 'matches_found', 'associations_created', 'associations_existing',
            'duplicates_in_file', 'autocompletes_a_verifier')},
        'suggestions_appareils': len((res.resultats_import or {}).get('similarity_suggestions') or {}),
    })
    journal.append(m)
    print(json.dumps(m, ensure_ascii=False, indent=1))
    return lot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('base')
    ap.add_argument('produits')
    ap.add_argument('compatibilites')
    ap.add_argument('--config', default=str(RACINE / 'data' / 'export_config.json'))
    ap.add_argument('--taille', type=int, default=100)
    ap.add_argument('--lots', type=int, default=1)
    ap.add_argument('--rapport', default='')
    ap.add_argument('--sans-relance', action='store_true')
    args = ap.parse_args()

    t = time.time()
    db = DatabaseManager(args.base)
    print(f"Base ouverte (migration comprise) : {time.time() - t:.1f} s, "
          f"{taille_base(db.db_file) / 1e6:.1f} Mo")
    service = RepriseSiteService(db)
    if Path(args.config).exists():
        service._modeles = modeles_depuis_config(json.loads(Path(args.config).read_text('utf-8')))
    signature, statut = service.examiner_export(args.produits, args.compatibilites)
    service.adopter_export(signature, repartir_de_zero=True)
    journal = []
    premier = None
    for _ in range(args.lots):
        lot = un_lot(service, db, args.taille, journal)
        if lot is None:
            break
        premier = premier or lot

    if premier is not None and not args.sans_relance:
        # Relance du 1er lot : l'état est remis juste avant lui
        db.conn.execute("UPDATE reprise_site_etat SET dernier_id = ? WHERE cle = 'courant'",
                        [premier.export.premier_id - 1])
        db.conn.commit()
        service._lecteur = None
        print("\n=== Relance du 1er lot ===")
        avant = compter(db)
        lot = service.analyser_lot_suivant(args.taille)
        plan, _ = par_regles(lot)
        res = service.enregistrer_lot(lot, plan)
        apres = compter(db)
        relance = {'ajouts': {k: apres[k] - avant[k] for k in apres}, 'resultat': res.resume(),
                   'niveaux': mesures_lot(lot)['niveaux'], 'liens': mesures_lot(lot)['liens']}
        print(json.dumps(relance, ensure_ascii=False, indent=1))
        journal.append({'relance': relance})
    service.fermer()
    if args.rapport:
        Path(args.rapport).write_text(json.dumps(journal, ensure_ascii=False, indent=1), 'utf-8')


if __name__ == '__main__':
    main()
