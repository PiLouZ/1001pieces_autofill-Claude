"""
Validation de l'export « Windows portable » sans vrai PC Windows.

Lancé par le workflow GitHub Actions .github/workflows/valider-export-windows.yml
sur un runner windows-latest. Quatre sous-commandes, une par étape :

    construire DEST           (Python du runner)   arborescence portable, comme
                                                   create_export() mais sans zip
    creer-base                (Python EMBARQUÉ)    petite base de test dans
                                                   DEST/data/appareils.db
    demarrer DEST [--duree N] (Python du runner)   lance l'application via le
                                                   Python embarqué, en offscreen,
                                                   puis vérifie errors.log
    importer-pdf PDF          (Python EMBARQUÉ)    extraction camelot + écriture
                                                   en base

Les sous-commandes « Python EMBARQUÉ » s'exécutent avec DEST\\python\\python.exe :
son fichier python312._pth place la racine de l'application dans sys.path,
d'où `import src…` sans rien régler. Elles n'importent pas export_app (resté
dans le dépôt, hors de l'arborescence exportée).
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE_DEPOT = Path(__file__).resolve().parents[2]

# Versions éprouvées sur le poste de référence (Mac) : l'export réel les sert de
# contraintes à `pip download --platform win_amd64`. Sur le runner, rien n'est
# installé : on rejoue ces mêmes contraintes plutôt que celles du runner.
VERSIONS_REFERENCE = Path(__file__).with_name('versions_reference.txt')


def _versions_reference() -> dict:
    """{nom normalisé: 'Nom==version'} lu dans versions_reference.txt."""
    import export_app
    pins = {}
    for ligne in VERSIONS_REFERENCE.read_text(encoding='utf-8').splitlines():
        ligne = ligne.split('#', 1)[0].strip()
        if ligne:
            pins[export_app._nom_normalise(ligne.split('==', 1)[0])] = ligne
    return pins


# ── construire ───────────────────────────────────────────────────────────────

def construire(dest: Path):
    """Mêmes étapes que create_export(cible='windows'), base et zip exceptés."""
    sys.path.insert(0, str(RACINE_DEPOT))
    import export_app
    export_app._dependances_epinglees = _versions_reference

    def _progres(message):
        print(f"  {message}", flush=True)

    if dest.exists():
        raise SystemExit(f"Dossier déjà présent : {dest}")
    dest.mkdir(parents=True)
    nb = export_app._copy_source(dest)
    export_app._write_export_config(dest)
    nb += export_app._copy_test_import_files(dest)
    print(f"  {nb} fichiers de l'application copiés")
    archive = export_app._telecharger_python_windows(_progres)
    python_dir = export_app._preparer_python_windows(dest, archive)
    export_app._installer_dependances_windows(python_dir, _progres)
    export_app._ecrire_lanceurs_windows(dest)
    export_app._write_readme_windows(dest, 'validation CI')

    taille = sum(p.stat().st_size for p in dest.rglob('*') if p.is_file())
    print(f"  Arborescence prête : {dest} ({taille / 1024 / 1024:.0f} Mo)")
    paquets = sorted(p.name for p in (python_dir / 'Lib' / 'site-packages').glob('*.dist-info'))
    print("  Paquets installés :\n    " + "\n    ".join(paquets))


# ── creer-base (Python embarqué) ─────────────────────────────────────────────

def creer_base():
    """Base neuve créée par l'application elle-même (schéma + migrations)."""
    from src.core.config import Config
    from src.data.database_manager import DatabaseManager

    chemin = Path(Config.DB_FILE).resolve()
    if chemin.exists():
        raise SystemExit(f"Base déjà présente : {chemin}")
    db = DatabaseManager(str(chemin))
    for i, (type_, fabricant) in enumerate([('Lave-linge', 'Whirlpool'),
                                            ('Four', 'Bosch'),
                                            ('Réfrigérateur', 'Électrolux')], 1):
        appareil_id = db.insert_appareil({'type': type_, 'manufacturer': fabricant,
                                          'ref_modele': f'CI-MODELE-{i}',
                                          'commercial_ref': f'CI-COM-{i}'})
        db.add_piece(f'CI-PIECE-{i}', appareil_id, f'Pièce de test {i}')
    db.conn.commit()
    nb = db.conn.execute('SELECT COUNT(*) FROM appareils').fetchone()[0]
    db.conn.close()
    print(f"  Base de test créée : {chemin} ({nb} appareils)")


# ── demarrer (Python du runner, pilote le Python embarqué) ───────────────────

def _lire_errors_log(dest: Path) -> str:
    chemin = dest / 'data' / 'logs' / 'errors.log'
    return chemin.read_text(encoding='utf-8', errors='replace') if chemin.exists() else ''


def demarrer(dest: Path, duree: int) -> int:
    """Lance l'application comme les deux lanceurs .bat, vérifie errors.log.

    - pythonw.exe : ce que lance 1001pieces_autofill.bat (aucune console) ;
    - python.exe + PYTHONUTF8=1 : ce que lance la version « console », dont on
      garde la sortie pour le diagnostic.
    L'application doit être encore en vie après `duree` secondes.
    """
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    env.pop('AUTOFILL_LOG_DIR', None)
    python = dest / 'python'
    echecs = 0
    for nom, exe, extra in (('pythonw (lanceur principal)', python / 'pythonw.exe', {}),
                            ('python (lanceur console)', python / 'python.exe',
                             {'PYTHONUTF8': '1'})):
        print(f"\n== Démarrage via {nom}, {duree} s ==", flush=True)
        sortie = dest / f'sortie_{exe.stem}.txt'
        with open(sortie, 'wb') as f:
            proc = subprocess.Popen([str(exe), str(dest / 'run.py')], cwd=dest,
                                    env={**env, **extra}, stdin=subprocess.DEVNULL,
                                    stdout=f, stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=duree)
                print(f"ÉCHEC : l'application s'est arrêtée d'elle-même (code {code})")
                echecs += 1
            except subprocess.TimeoutExpired:
                print(f"OK : toujours en marche après {duree} s")
                proc.kill()
                proc.wait()
        texte = sortie.read_text(encoding='utf-8', errors='replace').strip()
        if texte:
            print(f"-- sortie --\n{texte[-4000:]}")
        erreurs = _lire_errors_log(dest)
        if erreurs.strip():
            print(f"ÉCHEC : data\\logs\\errors.log n'est pas vide :\n{erreurs[-6000:]}")
            echecs += 1
        else:
            print("OK : data\\logs\\errors.log vide")
    journaux = dest / 'data' / 'logs'
    if journaux.exists():
        print("\nJournaux produits : " + ", ".join(sorted(p.name for p in journaux.iterdir())))
    return 1 if echecs else 0


# ── importer-pdf (Python embarqué) ───────────────────────────────────────────

def importer_pdf(pdf: Path) -> int:
    """Extraction camelot d'un PDF fournisseur puis écriture des pièces en base."""
    from src.core.config import Config
    from src.data.database_manager import DatabaseManager
    from src.data.pdf_extractor_camelot import CamelotPDFExtractor

    debut = time.perf_counter()
    lignes = CamelotPDFExtractor().extract_data(str(pdf))
    print(f"  {len(lignes)} lignes extraites de {pdf.name} "
          f"en {time.perf_counter() - debut:.1f} s")
    if not lignes:
        print("ÉCHEC : aucune ligne extraite (voir data\\logs\\errors.log)")
        return 1
    for ligne in lignes[:5]:
        print(f"    {ligne}")

    # Un PDF fournisseur = une pièce (nom du fichier) et les appareils qui
    # l'utilisent : [réf. modèle, réf. commerciale, type]
    db = DatabaseManager(str(Path(Config.DB_FILE).resolve()))
    for ref_modele, ref_commerciale, type_ in lignes:
        appareil_id = db.insert_appareil({'type': type_, 'manufacturer': 'Import CI',
                                          'ref_modele': ref_modele,
                                          'commercial_ref': ref_commerciale})
        db.add_piece(pdf.stem, appareil_id)
    db.conn.commit()
    nb = db.conn.execute(
        'SELECT COUNT(*) FROM piece_associations pa JOIN pieces p ON p.id = pa.piece_id '
        'WHERE p.ref_piece = ?', (pdf.stem,)).fetchone()[0]
    integrite = db.conn.execute('PRAGMA integrity_check').fetchone()[0]
    violations = db.conn.execute('PRAGMA foreign_key_check').fetchall()
    db.conn.close()
    print(f"  Pièce {pdf.stem} associée à {nb} appareils, intégrité : {integrite}, "
          f"violations de clés étrangères : {len(violations)}")
    return 0 if nb == len(lignes) and integrite == 'ok' and not violations else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sous = parser.add_subparsers(dest='commande', required=True)
    p = sous.add_parser('construire')
    p.add_argument('dest', type=Path)
    sous.add_parser('creer-base')
    p = sous.add_parser('demarrer')
    p.add_argument('dest', type=Path)
    p.add_argument('--duree', type=int, default=30)
    p = sous.add_parser('importer-pdf')
    p.add_argument('pdf', type=Path)
    args = parser.parse_args()

    if args.commande == 'construire':
        construire(args.dest.resolve())
        return 0
    if args.commande == 'creer-base':
        creer_base()
        return 0
    if args.commande == 'demarrer':
        return demarrer(args.dest.resolve(), args.duree)
    return importer_pdf(args.pdf.resolve())


if __name__ == '__main__':
    sys.exit(main())
