"""
Mesure de la migration de l'étape 3 (reprise des fiches du site) sur une COPIE
de la vraie base, faite par l'API backup de sqlite3 (jamais cp : WAL possible).

    python3.13 scripts/mesurer_migration_fiches.py data/appareils.db /chemin/copie.db [--fiches]

- durée de l'ouverture par DatabaseManager (création des tables et colonnes
  du § 9) et taille avant / après ;
- avec --fiches : les 3 fiches d'exemple (tests/fixtures/fiches_site) sont
  rapprochées, enregistrées « tout validé », puis relues : la relecture ne doit
  rien ajouter. La vraie base n'est jamais ouverte en écriture.
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def copier(source: Path, cible: Path):
    if cible.exists():
        cible.unlink()
    src = sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)
    dst = sqlite3.connect(cible)
    src.backup(dst)
    dst.close()
    src.close()


def compter(cnx):
    return {t: cnx.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ('appareils', 'pieces', 'piece_associations', 'piece_supersessions',
                      'piece_equivalence_groups', 'produits_site')}


def main():
    source, cible = Path(sys.argv[1]), Path(sys.argv[2])
    t0 = time.perf_counter()
    copier(source, cible)
    print(f"copie (backup) : {time.perf_counter() - t0:.1f} s")
    taille = cible.stat().st_size

    from src.data.database_manager import DatabaseManager
    t0 = time.perf_counter()
    db = DatabaseManager(str(cible))
    duree = time.perf_counter() - t0
    print(f"ouverture + migration : {duree:.2f} s ; taille {taille / 1e6:.1f} → "
          f"{cible.stat().st_size / 1e6:.1f} Mo")
    print("provenance renseignée :", db.conn.execute(
        "SELECT COUNT(*) FROM piece_associations WHERE provenance IS NOT NULL").fetchone()[0])

    if '--fiches' not in sys.argv:
        return
    from src.services.enregistrement_fiche_service import EnregistrementFicheService
    from src.utils.rapprochement_fiche.decisions import (
        ChoixAppareil, DecisionsFiche, categorie_appareil, planifier)
    service = EnregistrementFicheService(db)
    fixtures = RACINE / 'tests' / 'fixtures' / 'fiches_site'

    def lire(n):
        page = (fixtures / f'produit_{n}.html').read_text(encoding='utf-8')
        return service.analyser_page(page, f'https://www.1001pieces.com/{n}-fiche.html')[1]

    def decisions(r):
        d = DecisionsFiche()
        d.valider_tout(r)
        for i, a in enumerate(r.appareils):
            if categorie_appareil(a) == 'a_valider' and a.candidats and \
                    a.appareil_id is None and a.proposition is None:
                d.appareils[i] = ChoixAppareil(appareil_id=a.candidats[0].id)
        return d

    for n in (7285, 20746, 20744):
        t0 = time.perf_counter()
        r = lire(n)
        plan = planifier(r, decisions(r))
        print(f"{n} : {r.resume()['liens']} ; plan {plan.resume()} ; à compléter "
              f"{len(plan.a_completer)} ({time.perf_counter() - t0:.2f} s)")
        if plan.pret:
            print("   ", service.enregistrer(plan).resume())
    avant = compter(db.conn)
    for n in (7285, 20746, 20744):
        r = lire(n)
        plan = planifier(r, decisions(r))
        print(f"relecture {n} : rien à ajouter = {plan.vide} ; absents de la fiche "
              f"{len(r.absents_de_la_fiche)}")
        if plan.pret:
            service.enregistrer(plan)
    print("relecture sans ajout :", compter(db.conn) == avant, compter(db.conn))


if __name__ == '__main__':
    main()
