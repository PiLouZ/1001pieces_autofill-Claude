"""
Script d'export de l'application 1001pieces_autofill.

Crée un dossier auto-suffisant pour installation sur une autre machine macOS.
Inclut le code source, la base de données et toutes les dépendances pip (wheels).

Usage CLI :
    python3 export_app.py
    python3 export_app.py --output ~/Bureau/mon_export
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent

# Dossiers à exclure de la copie du code source
EXCLUDE_DIRS = {
    '.git', '__pycache__', '.claude', 'tests',
}

# Fichiers / patterns à exclure
EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.db-shm', '.db-wal'}
EXCLUDE_FILES    = {'export_app.py', '.DS_Store'}

# Fichiers data à exclure (les journaux sont régénérés au lancement)
EXCLUDE_DATA_SUBDIRS = {'logs'}


def _should_exclude(path: Path, rel: Path) -> bool:
    """Retourne True si ce chemin doit être ignoré lors de la copie."""
    parts = rel.parts
    if parts[0] in EXCLUDE_DIRS:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    # Exclure data/logs/
    if len(parts) >= 2 and parts[0] == 'data' and parts[1] in EXCLUDE_DATA_SUBDIRS:
        return True
    return False


def _copy_source(dest: Path, progress_callback=None) -> int:
    """Copie le code source vers dest/. Retourne le nombre de fichiers copiés."""
    count = 0
    for src_file in ROOT.rglob('*'):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(ROOT)
        if _should_exclude(src_file, rel):
            continue
        dst_file = dest / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        count += 1
        if progress_callback:
            progress_callback(f"Copie : {rel}")
    return count


def _freeze_requirements(dest: Path) -> Path:
    """
    Génère requirements_frozen.txt avec les versions exactes installées,
    filtré sur les dépendances directes + transitives de requirements.txt.
    Retourne le chemin du fichier généré.
    """
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'freeze'],
        capture_output=True, text=True, check=True
    )
    frozen_path = dest / 'requirements_frozen.txt'
    frozen_path.write_text(result.stdout, encoding='utf-8')
    return frozen_path


def _download_wheels(frozen_req: Path, wheels_dir: Path, progress_callback=None) -> bool:
    """
    Télécharge les wheels pour toutes les dépendances dans wheels_dir.
    Utilise requirements_frozen.txt (versions exactes).
    Retourne True si succès.
    """
    wheels_dir.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback("Téléchargement des wheels pip (peut prendre 1-2 minutes)…")

    cmd = [
        sys.executable, '-m', 'pip', 'download',
        '-r', str(frozen_req),
        '-d', str(wheels_dir),
        '--quiet',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Tentative sans --quiet pour avoir le détail de l'erreur
        print(f"[WARN] pip download : {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _write_install_script(dest: Path):
    """Crée install.sh sur la machine cible."""
    content = """\
#!/usr/bin/env bash
# install.sh — Installation de 1001pieces_autofill sur cette machine
set -e
cd "$(dirname "$0")"

echo "==> Vérification de Python 3…"
if ! command -v python3 &>/dev/null; then
    echo "ERREUR : Python 3 n'est pas installé. Installez-le via https://python.org ou brew."
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_VER" -lt 10 ]; then
    echo "ERREUR : Python 3.10+ requis (version détectée : 3.$PY_VER)."
    exit 1
fi

echo "==> Création de l'environnement virtuel…"
python3 -m venv venv

echo "==> Installation des dépendances (hors réseau)…"
venv/bin/pip install --quiet --no-index --find-links=wheels -r requirements_frozen.txt

echo ""
echo "✅ Installation terminée."
echo "   Pour lancer l'application : double-cliquez sur 1001pieces_autofill.command"
echo ""
read -n 1 -s -r -p "Appuyez sur une touche pour fermer cette fenêtre…"
"""
    for name in ('install.command',):
        script = dest / name
        script.write_text(content, encoding='utf-8')
        script.chmod(0o755)


def _inject_icon(app_path: Path, icon_png: Path) -> bool:
    """
    Convertit icon_png en .icns et l'injecte dans le bundle .app.
    Utilise sips (redimensionnement) + iconutil (compilation icns).
    Retourne True si succès.
    """
    import tempfile

    iconset_dir = Path(tempfile.mkdtemp()) / 'app.iconset'
    iconset_dir.mkdir()

    try:
        # Étape 1 — image carrée 1024×1024 (padding blanc si nécessaire)
        square = iconset_dir.parent / 'square.png'
        subprocess.run(['sips', '--padToHeightWidth', '1024', '1024',
                        '--padColor', 'FFFFFF', str(icon_png), '-o', str(square)],
                       capture_output=True)
        subprocess.run(['sips', '-z', '1024', '1024', str(square), '-o', str(square)],
                       capture_output=True)

        # Étape 2 — générer toutes les tailles requises
        sizes = [
            ('icon_16x16.png',      16),   ('icon_16x16@2x.png',    32),
            ('icon_32x32.png',      32),   ('icon_32x32@2x.png',     64),
            ('icon_128x128.png',   128),   ('icon_128x128@2x.png',  256),
            ('icon_256x256.png',   256),   ('icon_256x256@2x.png',  512),
            ('icon_512x512.png',   512),   ('icon_512x512@2x.png', 1024),
        ]
        for filename, px in sizes:
            subprocess.run(['sips', '-z', str(px), str(px), str(square),
                            '--out', str(iconset_dir / filename)],
                           capture_output=True)

        # Étape 3 — compiler en .icns
        icns_path = iconset_dir.parent / 'app_icon.icns'
        result = subprocess.run(['iconutil', '-c', 'icns', str(iconset_dir),
                                  '-o', str(icns_path)],
                                 capture_output=True)
        if result.returncode != 0:
            return False

        # Étape 4 — injecter dans le bundle
        dest_icns = app_path / 'Contents' / 'Resources' / 'applet.icns'
        shutil.copy2(icns_path, dest_icns)
        return True

    except Exception:
        return False
    finally:
        shutil.rmtree(str(iconset_dir.parent), ignore_errors=True)


# Chemin de l'icône PNG du projet (inclus dans les exports)
_ICON_PNG = ROOT / 'app_icon.png'


def _compile_app_launcher(dest: Path, use_venv: bool) -> bool:
    """
    Compile le lanceur AppleScript en vrai bundle .app via osacompile.

    Le script AppleScript détecte son propre dossier parent au moment de
    l'exécution (pas de chemin codé en dur). Il lance Python en arrière-plan
    via un login shell pour bénéficier du PATH complet de l'utilisateur.
    Aucune fenêtre Terminal n'est ouverte.

    Retourne True si succès.
    """
    import tempfile

    if use_venv:
        launch_cmd = "source venv/bin/activate && nohup python3 run.py > /dev/null 2>&1 &"
    else:
        launch_cmd = "nohup python3 run.py > /dev/null 2>&1 &"

    # Le script est écrit dans un fichier temporaire pour éviter les problèmes
    # d'échappement des guillemets avec les chemins contenant des espaces.
    #
    # Stratégie de quoting :
    #   • quoted form of appFolder  → guillemets simples : '/chemin avec espaces'
    #   • La commande bash -c est délimitée par des guillemets DOUBLES (\" ... \")
    #     afin que les guillemets simples de quoted form puissent y être insérés
    #     sans conflit.
    #   Résultat : /bin/bash -l -c "cd '/chemin avec espaces' && ..."
    applescript = f"""\
set appPath to POSIX path of (path to me)
set appFolder to do shell script "dirname " & quoted form of appPath
do shell script "/bin/bash -l -c \\"cd " & quoted form of appFolder & " && {launch_cmd}\\""
"""
    app_path = dest / '1001pieces_autofill.app'

    with tempfile.NamedTemporaryFile(suffix='.applescript', mode='w',
                                     encoding='utf-8', delete=False) as f:
        f.write(applescript)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ['osacompile', '-o', str(app_path), tmp_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return False
        # Injecter l'icône personnalisée si disponible
        icon_png = dest / 'app_icon.png' if use_venv else _ICON_PNG
        if icon_png.exists():
            _inject_icon(app_path, icon_png)
        return True
    finally:
        os.unlink(tmp_path)


def create_source_launcher(project_root: Path | str | None = None) -> bool:
    """
    Crée (ou recrée) le lanceur 1001pieces_autofill.app dans le dossier du projet.
    À appeler sur la machine source (sans venv).
    Retourne True si succès.
    """
    if project_root is None:
        project_root = ROOT
    project_root = Path(project_root)
    return _compile_app_launcher(project_root, use_venv=False)


def _write_readme(dest: Path, export_date: str):
    """Crée README_INSTALL.md dans le dossier d'export."""
    content = f"""\
# 1001pieces_autofill — Guide d'installation

Export généré le : **{export_date}**

---

## Prérequis

- macOS 12 (Monterey) ou supérieur
- **Python 3.10+** — vérifiez avec `python3 --version`
  - Si absent : <https://www.python.org/downloads/> ou `brew install python`

---

## Installation (une seule fois)

**Double-cliquez sur `install.command`** dans le Finder.

Une fenêtre Terminal s'ouvre, installe les dépendances et se ferme automatiquement.
Aucune connexion internet nécessaire (les fichiers `.whl` sont inclus dans `wheels/`).

---

## Lancement

**Double-cliquez sur `1001pieces_autofill.app`** dans le Finder (aucune console).

---

## Contenu du dossier

| Élément | Description |
|---------|-------------|
| `src/` | Code source de l'application |
| `data/appareils.db` | Base de données (598 000+ enregistrements) |
| `wheels/` | Dépendances pip pré-téléchargées |
| `requirements_frozen.txt` | Versions exactes des dépendances |
| `install.command` | Installation (double-clic, une seule fois) |
| `1001pieces_autofill.app` | Lancement (double-clic, sans Terminal) |

---

## Dépannage

- **"venv absent"** → double-cliquez à nouveau sur `install.command`
- **Erreur PyQt5** → assurez-vous d'utiliser Python 3.10+
- **Base de données absente** → vérifiez que `data/appareils.db` est présent
"""
    (dest / 'README_INSTALL.md').write_text(content, encoding='utf-8')


def create_export(output_dir: Path | str | None = None,
                  progress_callback=None) -> dict:
    """
    Crée le dossier d'export complet.

    Args:
        output_dir : dossier parent dans lequel créer l'export.
                     Par défaut : Bureau de l'utilisateur.
        progress_callback : callable(message: str) appelé à chaque étape.

    Returns:
        {'success': bool, 'path': str, 'size_mb': float, 'error': str}
    """
    try:
        if output_dir is None:
            output_dir = Path.home() / 'Desktop'
        output_dir = Path(output_dir)

        export_date = datetime.now().strftime('%Y%m%d_%H%M')
        dest = output_dir / f'1001pieces_export_{export_date}'

        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)

        # ── 1. Copie du code source ──────────────────────────────────────────
        if progress_callback:
            progress_callback("Copie du code source…")
        nb_files = _copy_source(dest, progress_callback)

        # ── 2. requirements_frozen.txt ───────────────────────────────────────
        if progress_callback:
            progress_callback("Génération de requirements_frozen.txt…")
        frozen_req = _freeze_requirements(dest)

        # ── 3. Téléchargement des wheels ─────────────────────────────────────
        wheels_dir = dest / 'wheels'
        ok = _download_wheels(frozen_req, wheels_dir, progress_callback)
        if not ok:
            return {
                'success': False,
                'path': str(dest),
                'size_mb': 0.0,
                'error': "Échec du téléchargement des wheels pip. "
                         "Vérifiez la connexion internet.",
            }

        # ── 4. Script install + lanceur .app ─────────────────────────────────
        if progress_callback:
            progress_callback("Génération du script install.command et du lanceur .app…")
        _write_install_script(dest)
        _compile_app_launcher(dest, use_venv=True)
        _write_readme(dest, datetime.now().strftime('%d/%m/%Y %H:%M'))

        # ── 5. Calcul de la taille totale ────────────────────────────────────
        total_bytes = sum(f.stat().st_size for f in dest.rglob('*') if f.is_file())
        size_mb = total_bytes / (1024 * 1024)

        if progress_callback:
            progress_callback(f"Export terminé — {nb_files} fichiers, {size_mb:.0f} Mo")

        return {
            'success': True,
            'path': str(dest),
            'size_mb': size_mb,
            'error': '',
        }

    except Exception as e:
        return {
            'success': False,
            'path': '',
            'size_mb': 0.0,
            'error': str(e),
        }


# ── Entrée CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Exporter 1001pieces_autofill vers un dossier portable."
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help="Dossier parent de l'export (défaut : Bureau)"
    )
    args = parser.parse_args()

    def _print(msg):
        print(f"  {msg}")

    print("\n=== Export 1001pieces_autofill ===\n")
    result = create_export(
        output_dir=args.output,
        progress_callback=_print,
    )

    if result['success']:
        print(f"\n✅ Succès !")
        print(f"   Dossier : {result['path']}")
        print(f"   Taille  : {result['size_mb']:.0f} Mo")
        print(f"\n   Sur le poste cible :")
        print(f"     bash install.sh   # une seule fois")
        print(f"     bash launch.sh    # pour lancer\n")
    else:
        print(f"\n❌ Échec : {result['error']}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
