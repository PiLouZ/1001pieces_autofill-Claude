#!/usr/bin/env python3
"""
Nettoyage ponctuel — supprimer les associations pièce↔appareil orphelines.

Audit du 2026-10-15 (copie de la base, `PRAGMA foreign_key_check`) :
  - 94 905 associations pointent vers une pièce supprimée (96 pièces, ids 1–480) ;
  - 13 de plus pointent vers un appareil supprimé (et une pièce existante).
Toutes datent de juillet à septembre 2025 : défaut ancien, aucun chemin de
suppression actuel n'en crée plus. Les clés étrangères du schéma sont inertes
(`PRAGMA foreign_keys` n'est activé nulle part), d'où leur survie.

Effet visible aujourd'hui : quasi nul (presque toutes les requêtes joignent
`pieces`), sauf 4 pièces dont le gestionnaire surcompte les appareils. L'intérêt
principal est de préparer une éventuelle activation des clés étrangères.

Déroulé :
  1. contrôles — l'app doit être fermée ; comptage des orphelins ; arrêt si le
     total dépasse celui de l'audit (de nouveaux orphelins sont apparus : à
     comprendre avant de supprimer) ;
  2. sauvegarde ponctuelle (réserve « ponctuelle », n'évince pas les copies
     d'import) — en cas d'échec, rien n'est supprimé ;
  3. suppression en une transaction, validée seulement si le nombre de lignes
     supprimées égale le comptage ;
  4. contrôles sur une connexion neuve : 0 violation, intégrité ok, comptes du
     gestionnaire justes, volume attendu.

Retour arrière : Outils → « Restaurer une sauvegarde… » avec la copie de l'étape 2.

Usage :
    python3 scripts/nettoyage_associations_orphelines.py              # simulation, n'écrit rien
    python3 scripts/nettoyage_associations_orphelines.py --ecrire     # applique, après sauvegarde
    python3 scripts/nettoyage_associations_orphelines.py --base chemin.db
"""

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BASE_PAR_DEFAUT = RACINE / "data" / "appareils.db"

# Total mesuré par l'audit du 2026-10-15. Au-delà, de nouveaux orphelins sont
# apparus depuis : le script refuse d'écrire tant que leur origine n'est pas
# comprise. En deçà (base déjà partiellement nettoyée), il poursuit.
ATTENDU_AUDIT = 94_918

# Une association est orpheline si sa pièce OU son appareil n'existe plus.
# Une seule condition : une ligne orpheline des deux côtés n'est comptée qu'une fois.
CONDITION_ORPHELINE = """
    NOT EXISTS (SELECT 1 FROM pieces p WHERE p.id = piece_associations.piece_id)
    OR NOT EXISTS (SELECT 1 FROM appareils a WHERE a.id = piece_associations.appareil_id)
"""

# Pièces dont le gestionnaire (REQUETE_PIECES_COMPLETE) affiche un nombre
# d'appareils différent du nombre d'appareils existants.
REQUETE_COMPTES_FAUX = """
    SELECT p.ref_piece,
           COUNT(DISTINCT pa.appareil_id) AS affiche,
           COUNT(DISTINCT a.id)           AS reel
    FROM pieces p
    LEFT JOIN piece_associations pa ON p.id = pa.piece_id
    LEFT JOIN appareils a ON pa.appareil_id = a.id
    GROUP BY p.id
    HAVING affiche <> reel
    ORDER BY p.ref_piece
"""


def _connexion(chemin):
    # isolation_level=None : les transactions sont ouvertes et closes à la main,
    # pour que le comptage et la suppression vivent dans la même transaction.
    return sqlite3.connect(str(chemin), isolation_level=None)


def autres_processus_ouverts(chemin):
    """PID des autres processus qui tiennent la base ouverte (l'app, typiquement).

    Retourne None si la vérification est impossible (lsof absent)."""
    try:
        sortie = subprocess.run(["lsof", "-t", str(chemin)],
                                capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    moi = os.getpid()
    return sorted({int(p) for p in sortie.stdout.split() if p.isdigit() and int(p) != moi})


def mesurer(conn):
    """État des orphelins : dictionnaire lu par la simulation ET par l'écriture."""
    def un(sql):
        return conn.execute(sql).fetchone()[0]

    return {
        "total_associations": un("SELECT COUNT(*) FROM piece_associations"),
        "vers_piece_absente": un(
            "SELECT COUNT(*) FROM piece_associations WHERE NOT EXISTS "
            "(SELECT 1 FROM pieces p WHERE p.id = piece_associations.piece_id)"),
        "pieces_absentes": un(
            "SELECT COUNT(DISTINCT piece_id) FROM piece_associations WHERE NOT EXISTS "
            "(SELECT 1 FROM pieces p WHERE p.id = piece_associations.piece_id)"),
        "vers_appareil_absent": un(
            "SELECT COUNT(*) FROM piece_associations WHERE NOT EXISTS "
            "(SELECT 1 FROM appareils a WHERE a.id = piece_associations.appareil_id)"),
        "orphelines": un(f"SELECT COUNT(*) FROM piece_associations WHERE {CONDITION_ORPHELINE}"),
        "comptes_faux": conn.execute(REQUETE_COMPTES_FAUX).fetchall(),
    }


def afficher(etat):
    print(f"\n{etat['total_associations']:,} associations en base.".replace(",", " "))
    print(f"  vers une pièce absente   : {etat['vers_piece_absente']:>7}"
          f"  ({etat['pieces_absentes']} pièce(s) supprimée(s))")
    print(f"  vers un appareil absent  : {etat['vers_appareil_absent']:>7}")
    print(f"  à supprimer (sans double compte) : {etat['orphelines']}")
    if etat["comptes_faux"]:
        print(f"\n{len(etat['comptes_faux'])} pièce(s) au compte d'appareils faux "
              "dans le gestionnaire (affiché → réel) :")
        for ref, affiche, reel in etat["comptes_faux"]:
            print(f"  {ref:<16} {affiche} → {reel}")


def supprimer(chemin, attendu):
    """Supprime les orphelines en une transaction, validée seulement si le nombre
    de lignes supprimées égale `attendu` (le comptage de la simulation) et le
    recomptage fait dans la transaction. Retourne le nombre supprimé, ou lève."""
    conn = _connexion(chemin)
    try:
        conn.execute("BEGIN IMMEDIATE")
        recompte = conn.execute(
            f"SELECT COUNT(*) FROM piece_associations WHERE {CONDITION_ORPHELINE}").fetchone()[0]
        supprimees = conn.execute(
            f"DELETE FROM piece_associations WHERE {CONDITION_ORPHELINE}").rowcount
        if not (supprimees == recompte == attendu):
            conn.execute("ROLLBACK")
            raise RuntimeError(
                f"écart de comptage (attendu {attendu}, recompté {recompte}, "
                f"supprimé {supprimees}) — transaction annulée, rien n'a changé")
        conn.execute("COMMIT")
        return supprimees
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def controler(chemin, total_attendu):
    """Contrôles sur une connexion NEUVE (une écriture non commitée n'y serait
    pas visible). Retourne la liste des anomalies, vide si tout va bien."""
    conn = _connexion(chemin)
    try:
        anomalies = []
        violations = conn.execute("PRAGMA foreign_key_check(piece_associations)").fetchall()
        if violations:
            anomalies.append(f"{len(violations)} violation(s) de clé étrangère restante(s)")
        integrite = conn.execute("PRAGMA quick_check").fetchone()[0]
        if integrite != "ok":
            anomalies.append(f"intégrité : {integrite}")
        faux = conn.execute(REQUETE_COMPTES_FAUX).fetchall()
        if faux:
            anomalies.append(f"{len(faux)} pièce(s) au compte encore faux : "
                             + ", ".join(r[0] for r in faux))
        total = conn.execute("SELECT COUNT(*) FROM piece_associations").fetchone()[0]
        if total != total_attendu:
            anomalies.append(f"{total} associations au lieu de {total_attendu}")
        return anomalies
    finally:
        conn.close()


def sauvegarder(chemin):
    """Copie ponctuelle via BackupService. Retourne le chemin, ou None si échec."""
    from src.services.backup_service import BackupService

    class _PorteurDeBase:
        """BackupService lit le chemin via `parent_window.db_manager.db_file`, et
        retombe sinon sur la base de production. Sans ce porteur, un essai sur une
        copie sauvegarderait la vraie base — jamais celle qu'on s'apprête à
        modifier."""
        def __init__(self, db_file):
            self.db_manager = type("_Db", (), {"db_file": str(db_file)})()

    return BackupService(parent_window=_PorteurDeBase(chemin)).create_backup(
        reason="nettoyage_orphelins")


def ecrire(chemin, etat):
    """Étapes 2 à 4. Retourne le code de sortie."""
    print("\nSauvegarde de la base avant écriture…")
    copie = sauvegarder(chemin)
    if not copie:
        print("  ÉCHEC de la sauvegarde — abandon, rien n'a été supprimé.")
        return 1
    print(f"  Copie créée : {copie}")

    try:
        supprimees = supprimer(chemin, etat["orphelines"])
    except Exception as e:
        print(f"\nSuppression annulée : {e}")
        return 1
    print(f"\n{supprimees} association(s) orpheline(s) supprimée(s).")

    anomalies = controler(chemin, etat["total_associations"] - supprimees)
    if anomalies:
        print("\nCONTRÔLES EN ÉCHEC :")
        for a in anomalies:
            print(f"  - {a}")
        print(f"Restaurer si besoin : Outils → « Restaurer une sauvegarde… » ({copie.name})")
        return 1

    print("Contrôles : 0 violation, intégrité ok, comptes du gestionnaire justes, "
          "volume attendu.")
    try:
        from src.core.logger import app_logger
        # Le chemin de la base est indispensable : un essai sur une copie écrit
        # dans le même journal que la production.
        app_logger.info(f"Nettoyage associations orphelines : {supprimees} supprimée(s) "
                        f"dans {chemin}, sauvegarde {copie}")
    except Exception:
        pass   # la trace dans le journal est un plus, pas une condition de succès
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=str(BASE_PAR_DEFAUT),
                        help="chemin de la base SQLite")
    parser.add_argument("--ecrire", action="store_true",
                        help="appliquer réellement (sans ce drapeau : simulation)")
    args = parser.parse_args(argv)

    chemin = Path(args.base)
    if not chemin.exists():
        print(f"Base introuvable : {chemin}")
        return 2

    if args.ecrire:
        autres = autres_processus_ouverts(chemin)
        if autres is None:
            print("Impossible de vérifier que l'application est fermée (lsof absent) — abandon.")
            return 2
        if autres:
            print(f"La base est ouverte par un autre processus (PID {', '.join(map(str, autres))}).")
            print("Fermer l'application puis relancer.")
            return 2

    conn = _connexion(chemin)
    try:
        etat = mesurer(conn)
    finally:
        conn.close()
    afficher(etat)

    if etat["orphelines"] > ATTENDU_AUDIT:
        print(f"\nARRÊT : {etat['orphelines']} orphelines, plus que les {ATTENDU_AUDIT} "
              "de l'audit du 2026-10-15. De nouvelles orphelines sont apparues : "
              "en comprendre l'origine avant de supprimer.")
        return 3

    if not args.ecrire:
        print("\n(simulation — rien n'a été écrit ; fermer l'application puis relancer "
              "avec --ecrire pour appliquer)")
        return 0

    if etat["orphelines"] == 0:
        print("\nRien à supprimer.")
        return 0
    return ecrire(chemin, etat)


if __name__ == "__main__":
    sys.exit(main())
