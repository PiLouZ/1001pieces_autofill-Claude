#!/usr/bin/env python3
"""
Mesure d'un lot de la reprise des fiches du site (CDC § 7.4, étape 4)

Sur une COPIE de la base (faite avec l'API backup de sqlite3, jamais cp) :
1. adopte l'export (deux CSV) en repartant de zéro ;
2. analyse le 1er lot (taille réglable) : durée, part déjà en base, doutes ;
3. valide tout en bloc (propositions des catégories et des groupes de doutes),
   met de côté les lignes à compléter, enregistre : durée, croissance de la base ;
4. relance le MÊME lot (état remis au début du lot) : aucun appareil, lien ni
   relation ne doit être ajouté.

Les décisions « tout valider » donnent la borne haute de la croissance : un
utilisateur laisse en général des doutes de côté.

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


def tout_decider(lot):
    lot.tout_valider()
    for g in lot.groupes_doutes():
        lot.choisir_groupe(g, g.choix[0])
    lignes = lot.lignes_a_completer_de_cote()
    plan = lot.planifier()
    return plan, lignes


def un_lot(service, db, taille, journal):
    t = time.time()
    lot = service.analyser_lot_suivant(taille)
    if lot is None:
        return None
    analyse = time.time() - t
    plan, lignes_de_cote = tout_decider(lot)
    avant = compter(db)
    taille_avant = taille_base(db.db_file)
    res = service.enregistrer_lot(lot, plan)
    apres = compter(db)
    m = mesures_lot(lot, plan)
    m.update({
        'premier_id': lot.export.premier_id, 'dernier_id': lot.export.dernier_id,
        'produits_sans_contenu': lot.export.sans_contenu, 'analyse_totale_s': round(analyse, 1),
        'ecriture_s': round(res.ecriture_s, 1), 'ok': res.ok, 'erreur': res.erreur,
        'lignes_mises_de_cote': lignes_de_cote, 'fiches_de_cote': len(plan.de_cote),
        'croissance_mo': round((taille_base(db.db_file) - taille_avant) / 1e6, 1),
        'ajouts': {k: apres[k] - avant[k] for k in apres},
        'groupes_doutes': [(g.genre, g.forme, g.fiches) for g in lot.groupes_doutes()][:15],
        'resultat': res.resume(),
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
        plan, _ = tout_decider(lot)
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
