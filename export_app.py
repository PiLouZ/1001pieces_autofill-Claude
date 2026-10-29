"""
Script d'export de l'application 1001pieces_autofill.

Crée une archive .zip auto-suffisante pour installer l'application sur un autre
poste, au choix :

- **Windows** : version portable. Python 3.12 « embeddable » officiel et toutes
  les dépendances sont inclus ; sur le poste cible, on dézippe puis on
  double-clique sur 1001pieces_autofill.bat. Rien à installer.
- **macOS** : code + dépendances (wheels) ; install.command crée un
  environnement virtuel avec le Python du poste cible, de la même version
  (et architecture) que le Python qui exporte, seul compatible avec les wheels.

N'est copié que le nécessaire pour faire tourner l'application (liste blanche) :
code, icône, guide d'utilisation, réglages d'export et UNE base de données, la
plus récente — instantané cohérent et compacté (VACUUM INTO). Les sauvegardes,
journaux, tests, documents de développement et caches restent sur ce poste.

Usage CLI :
    python3 export_app.py                       # cible Windows, sur le Bureau
    python3 export_app.py --cible macos
    python3 export_app.py --output ~/Bureau/mon_export
"""

import os
import re
import sys
import json
import shutil
import sqlite3
import hashlib
import zipfile
import tempfile
import subprocess
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent

CIBLE_WINDOWS = 'windows'
CIBLE_MACOS = 'macos'
CIBLES = (CIBLE_WINDOWS, CIBLE_MACOS)

# ── Liste blanche : seuls ces fichiers partent dans l'export ─────────────────
# (chemins relatifs à la racine du projet ; src/ est copié à part, .py seuls)
FICHIERS_EXPORTES = (
    'run.py',
    'app_icon.png',
    'requirements.txt',
    'docs/guide_utilisation.html',
)

# Fichiers d'exemple pour essayer l'import sur le poste cible (PDF fournisseur,
# CSV) : copiés à plat dans fichiers_test_import/ (< 1 Mo)
DOSSIER_TESTS_IMPORT = 'fichiers_test_import'
SOURCES_TESTS_IMPORT = (
    'tests/fixtures/pdf_samples/*.pdf',
    'tests/fixtures/whirlpool_suggestions_test.csv',
)

# Dépendances directes de l'application (les transitives s'en déduisent).
# camelot-py tire pandas, numpy, opencv… ; chardet et pdfminer.six sont aussi
# importés directement par le code.
DEPENDANCES_DIRECTES = ('PyQt5', 'QtAwesome', 'camelot-py', 'chardet', 'pdfminer.six')

# ── Python embarqué pour Windows ─────────────────────────────────────────────
# Distribution « embeddable » officielle de python.org : un dossier autonome,
# sans installation ni droits administrateur. Empreinte SHA-256 relevée sur
# le fichier officiel : un téléchargement altéré ou tronqué est refusé.
PYTHON_WIN_VERSION = '3.12.10'
PYTHON_WIN_URL = (f'https://www.python.org/ftp/python/{PYTHON_WIN_VERSION}/'
                  f'python-{PYTHON_WIN_VERSION}-embed-amd64.zip')
PYTHON_WIN_SHA256 = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
PYTHON_WIN_TAG = '312'   # python312._pth, wheels cp312

# Épinglages à ne pas reporter sur Windows : PyQt5-Qt5 5.15.2 est la dernière
# version publiée pour Windows (les suivantes n'existent que pour macOS/Linux).
NON_EPINGLES_WINDOWS = {'pyqt5-qt5'}
# Dépendances propres à Windows, absentes de l'environnement macOS (marqueur
# platform_system == "Windows" de click) : ajoutées explicitement.
DEPENDANCES_WINDOWS_SEULEMENT = ('colorama',)

# Cache des téléchargements entre deux exports (Python embarqué)
CACHE_DIR = Path.home() / '.cache' / '1001pieces_export'


def _notifier(progress_callback, message: str):
    if progress_callback:
        progress_callback(message)


def _nom_normalise(nom: str) -> str:
    """Nom de paquet normalisé (PEP 503) : « PyQt5_sip » == « pyqt5-sip »."""
    return re.sub(r'[-_.]+', '-', nom).lower()


# ── 1. Code source ───────────────────────────────────────────────────────────

def _copy_source(dest: Path, progress_callback=None) -> int:
    """Copie le strict nécessaire (liste blanche) vers dest/.

    src/ : uniquement les .py (ni __pycache__, ni .DS_Store). Retourne le
    nombre de fichiers copiés.
    """
    fichiers = [ROOT / rel for rel in FICHIERS_EXPORTES]
    fichiers += sorted(p for p in (ROOT / 'src').rglob('*.py')
                       if '__pycache__' not in p.parts)
    count = 0
    for src_file in fichiers:
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(ROOT)
        dst_file = dest / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        count += 1
        # « Étape — détail » : le journal de progression met à jour la ligne
        # « Copie du code source » au lieu d'ajouter une ligne par fichier
        _notifier(progress_callback, f"Copie du code source — {rel}")
    return count


def _copy_test_import_files(dest: Path) -> int:
    """Copie les fichiers d'exemple d'import dans dest/fichiers_test_import/."""
    cible = dest / DOSSIER_TESTS_IMPORT
    count = 0
    for motif in SOURCES_TESTS_IMPORT:
        for src_file in sorted(ROOT.glob(motif)):
            cible.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, cible / src_file.name)
            count += 1
    return count


def _write_export_config(dest: Path):
    """Réglages d'export (profils CSV/HTML) recopiés, dossier de sortie vidé.

    Le dossier de sortie est un chemin propre à ce poste (ex. /Users/…) :
    vidé, il retombe sur le Bureau du poste cible.
    """
    source = ROOT / 'data' / 'export_config.json'
    if not source.exists():
        source = ROOT / 'data' / 'export_config.example.json'
    if not source.exists():
        return
    config = json.loads(source.read_text(encoding='utf-8'))
    config['output_dir'] = ''
    cible = dest / 'data' / 'export_config.json'
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')


# ── 2. Base de données ───────────────────────────────────────────────────────

def _snapshot_database(dest: Path, progress_callback=None,
                       db_path: Path | None = None) -> Path:
    """Instantané de la base via VACUUM INTO.

    Une simple copie de fichier perdrait les écritures encore dans le journal
    -wal et pourrait capturer une base à mi-écriture. VACUUM INTO, lancé sur
    une connexion en lecture seule, produit une copie cohérente qui inclut le
    WAL, sans toucher à la base de travail, et compactée au passage.
    """
    if db_path is None:
        db_path = ROOT / 'data' / 'appareils.db'
    if not db_path.exists():
        raise FileNotFoundError(f"Base de données introuvable : {db_path}")
    cible = dest / 'data' / 'appareils.db'
    cible.parent.mkdir(parents=True, exist_ok=True)
    _notifier(progress_callback, "Copie de la base de données (1 à 2 minutes)…")
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        conn.execute('VACUUM INTO ?', (str(cible),))
    finally:
        conn.close()
    return cible


# ── 3. Dépendances ───────────────────────────────────────────────────────────

def _dependances_epinglees() -> dict:
    """{nom normalisé: 'Nom==version'} des dépendances de l'application.

    Fermeture des dépendances directes dans l'environnement courant : les
    versions exactes, éprouvées ici, sans les outils de développement (pytest,
    py-spy…) qu'un « pip freeze » emporterait.
    """
    from importlib import metadata
    from packaging.requirements import Requirement

    pins, a_voir = {}, list(DEPENDANCES_DIRECTES)
    while a_voir:
        nom = a_voir.pop()
        cle = _nom_normalise(nom)
        if cle in pins:
            continue
        try:
            dist = metadata.distribution(nom)
        except metadata.PackageNotFoundError:
            continue  # dépendance conditionnelle absente de ce poste
        pins[cle] = f"{dist.metadata['Name']}=={dist.version}"
        for exigence in dist.requires or []:
            req = Requirement(exigence)
            # Extras : seul camelot-py[cv] est demandé (requirements.txt)
            env = {'extra': 'cv' if cle == 'camelot-py' else ''}
            if req.marker is None or req.marker.evaluate(env):
                a_voir.append(req.name)
    return pins


def _freeze_requirements(dest: Path) -> Path:
    """Écrit requirements_frozen.txt : dépendances de l'application, épinglées."""
    frozen_path = dest / 'requirements_frozen.txt'
    lignes = sorted(_dependances_epinglees().values(), key=str.lower)
    frozen_path.write_text('\n'.join(lignes) + '\n', encoding='utf-8')
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


def _python_requis() -> tuple:
    """(version « 3.13 », architecture « arm64 ») du Python qui exporte.

    Les wheels sont téléchargés par ce Python : ils ne s'installent qu'avec la
    même version mineure et la même architecture sur le Mac cible.
    """
    import platform
    return f"{sys.version_info.major}.{sys.version_info.minor}", platform.machine()


def _write_install_script(dest: Path):
    """Crée install.command sur la machine cible.

    Cherche le Python de la version des wheels (pas le premier python3 venu),
    lève la quarantaine macOS du dossier (sinon le lanceur .app téléchargé est
    bloqué) et recrée le venv à chaque passage (un essai raté ne gêne pas).
    """
    version, arch = _python_requis()
    content = """\
#!/usr/bin/env bash
# install.command — Installation de 1001pieces_autofill sur cette machine
cd "$(dirname "$0")"

PY_REQUIS="@VERSION@"
ARCH_REQUISE="@ARCH@"

pause_et_quitter() {
    echo ""
    read -n 1 -s -r -p "Appuyez sur une touche pour fermer cette fenêtre…"
    echo ""
    exit "$1"
}

echo "==> Déblocage du dossier (quarantaine macOS)…"
xattr -dr com.apple.quarantine . 2>/dev/null || true

echo "==> Recherche de Python $PY_REQUIS ($ARCH_REQUISE)…"
PYTHON=""
for candidat in "python$PY_REQUIS" \\
                "/opt/homebrew/bin/python$PY_REQUIS" \\
                "/usr/local/bin/python$PY_REQUIS" \\
                "/Library/Frameworks/Python.framework/Versions/$PY_REQUIS/bin/python$PY_REQUIS" \\
                python3; do
    chemin=$(command -v "$candidat" 2>/dev/null) || continue
    infos=$("$chemin" -c 'import sys, platform; print("%d.%d %s" % (sys.version_info[0], sys.version_info[1], platform.machine()))' 2>/dev/null) || continue
    if [ "$infos" = "$PY_REQUIS $ARCH_REQUISE" ]; then
        PYTHON="$chemin"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    if [ "$(uname -m)" != "$ARCH_REQUISE" ]; then
        echo "ERREUR : cet export est prévu pour un Mac $ARCH_REQUISE, ce Mac est $(uname -m)."
        echo "         Demandez un export fait depuis un Mac du même type."
    else
        echo "ERREUR : Python $PY_REQUIS est introuvable sur ce Mac."
        echo "         Les dépendances fournies (dossier wheels) ne fonctionnent qu'avec cette version."
        echo ""
        echo "   Pour l'installer, au choix :"
        echo "     • Homebrew : brew install python@$PY_REQUIS"
        echo "     • python.org : https://www.python.org/downloads/ (dernière version $PY_REQUIS.x)"
        echo ""
        echo "   Puis double-cliquez à nouveau sur install.command."
    fi
    pause_et_quitter 1
fi
echo "    Python trouvé : $PYTHON"

echo "==> Création de l'environnement virtuel…"
rm -rf venv
if ! "$PYTHON" -m venv venv; then
    echo "ERREUR : impossible de créer l'environnement virtuel (dossier venv)."
    pause_et_quitter 1
fi

echo "==> Installation des dépendances (hors réseau)…"
if ! venv/bin/python -m pip install --quiet --no-index --find-links=wheels -r requirements_frozen.txt; then
    echo ""
    echo "ERREUR : l'installation des dépendances a échoué (détail ci-dessus)."
    pause_et_quitter 1
fi

echo ""
echo "✅ Installation terminée."
echo "   Pour lancer l'application : double-cliquez sur 1001pieces_autofill.app"
pause_et_quitter 0
""".replace('@VERSION@', version).replace('@ARCH@', arch)
    script = dest / 'install.command'
    script.write_text(content, encoding='utf-8')
    script.chmod(0o755)


def _write_console_launcher(dest: Path):
    """Crée 1001pieces_autofill_console.command : lancement avec console.

    Recours quand le lanceur .app ne s'ouvre pas : la fenêtre Terminal
    affiche le message d'erreur de l'application.
    """
    content = """\
#!/usr/bin/env bash
# Lance 1001pieces_autofill avec une console (messages d'erreur visibles)
cd "$(dirname "$0")"
if [ ! -x venv/bin/python ]; then
    echo "L'installation n'est pas faite : double-cliquez d'abord sur install.command."
else
    echo "=== 1001pieces_autofill — console ==="
    venv/bin/python run.py
    echo ""
    echo "=== Application terminée ==="
fi
read -n 1 -s -r -p "Appuyez sur une touche pour fermer cette fenêtre…"
echo ""
"""
    script = dest / '1001pieces_autofill_console.command'
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
        # Python du venv appelé directement : pas de dépendance au python3
        # du PATH, qui peut être une autre version que celle des wheels.
        launch_cmd = "nohup ./venv/bin/python run.py > /dev/null 2>&1"
        # Sans venv (install.command pas encore lancé), dire quoi faire
        # plutôt que de ne rien ouvrir.
        garde_venv = """\
try
    do shell script "test -x " & quoted form of (appFolder & "/venv/bin/python")
on error
    display dialog "L'installation n'est pas faite." & return & return & "Double-cliquez d'abord sur install.command (une seule fois), puis relancez l'application." buttons {"OK"} default button "OK" with icon caution with title "1001pieces_autofill"
    return
end try
"""
    else:
        launch_cmd = "nohup python3 run.py > /dev/null 2>&1"
        garde_venv = ""

    # Le script est écrit dans un fichier temporaire pour éviter les problèmes
    # d'échappement des guillemets avec les chemins contenant des espaces.
    #
    # Stratégie de quoting :
    #   • quoted form of appFolder  → guillemets simples : '/chemin avec espaces'
    #   • La commande bash -c est délimitée par des guillemets DOUBLES (\" ... \")
    #     afin que les guillemets simples de quoted form puissent y être insérés
    #     sans conflit.
    #   Résultat : /bin/bash -l -c "cd '/chemin avec espaces' && ..." > /dev/null 2>&1 &
    #
    # Mise en arrière-plan À L'EXTÉRIEUR de bash -c, sorties redirigées :
    # `do shell script` attend que plus aucun processus ne tienne sa sortie.
    # Avec le `&` à l'intérieur (« cd … && nohup … & »), bash mettait toute la
    # liste dans un sous-shell qui gardait cette sortie jusqu'à la fermeture de
    # l'application : le lanceur restait ouvert, d'où une 2ᵉ icône dans le Dock.
    applescript = f"""\
set appPath to POSIX path of (path to me)
set appFolder to do shell script "dirname " & quoted form of appPath
{garde_venv}do shell script "/bin/bash -l -c \\"cd " & quoted form of appFolder & " && {launch_cmd}\\" > /dev/null 2>&1 &"
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
        return _signer_bundle(app_path)
    finally:
        os.unlink(tmp_path)


def _signer_bundle(app_path: Path) -> bool:
    """Re-signe le bundle (signature ad hoc) puis vérifie son sceau.

    osacompile signe le bundle ; remplacer l'icône ensuite casse ce sceau.
    Sur le poste source rien ne se voit, mais sur un Mac où l'archive arrive
    téléchargée (quarantaine), macOS déclare l'application « endommagée ».
    """
    signe = subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app_path)],
                           capture_output=True, text=True)
    if signe.returncode != 0:
        print(f"[WARN] codesign : {signe.stderr.strip()}", file=sys.stderr)
        return False
    verifie = subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app_path)],
                             capture_output=True, text=True)
    if verifie.returncode != 0:
        print(f"[WARN] codesign --verify : {verifie.stderr.strip()}", file=sys.stderr)
        return False
    return True


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
    """Crée README_INSTALL.md dans le dossier d'export (cible macOS)."""
    version, arch = _python_requis()
    type_mac = 'Apple Silicon' if arch == 'arm64' else 'Intel'
    content = f"""\
# 1001pieces_autofill — Guide d'installation (macOS)

Export généré le : **{export_date}**

---

## Prérequis

- macOS 12 (Monterey) ou supérieur
- Un Mac **{arch}** ({type_mac})
- **Python {version}** exactement (les dépendances fournies sont prévues pour cette version)
  - Si absent : `brew install python@{version}` ou <https://www.python.org/downloads/> (dernière {version}.x)
  - `install.command` le cherche tout seul et indique quoi faire s'il ne le trouve pas

---

## Installation (une seule fois)

**Double-cliquez sur `install.command`** dans le Finder.

Une fenêtre Terminal s'ouvre, débloque le dossier (quarantaine macOS) et installe
les dépendances ; appuyez sur une touche pour la fermer.
Aucune connexion internet nécessaire (les fichiers `.whl` sont inclus dans `wheels/`).

---

## Lancement

**Double-cliquez sur `1001pieces_autofill.app`** dans le Finder (aucune console).

---

## Contenu du dossier

| Élément | Description |
|---------|-------------|
| `src/` | Code source de l'application |
| `data/appareils.db` | Base de données (copie la plus récente) |
| `docs/guide_utilisation.html` | Guide d'utilisation (aussi via le bouton Guide) |
| `fichiers_test_import/` | Fichiers PDF et CSV pour essayer l'import |
| `wheels/` | Dépendances pip pré-téléchargées |
| `requirements_frozen.txt` | Versions exactes des dépendances |
| `install.command` | Installation (double-clic, une seule fois) |
| `1001pieces_autofill.app` | Lancement (double-clic, sans Terminal) |
| `1001pieces_autofill_console.command` | Lancement avec console (messages d'erreur visibles) |

---

## Dépannage

- **« L'installation n'est pas faite »** → double-cliquez sur `install.command`
- **« Python {version} est introuvable »** → installez-le (voir Prérequis), puis relancez `install.command`
- **L'application ne s'ouvre pas** → double-cliquez sur `1001pieces_autofill_console.command` pour voir le message d'erreur
- **Base de données absente** → vérifiez que `data/appareils.db` est présent
"""
    (dest / 'README_INSTALL.md').write_text(content, encoding='utf-8')


# ── Cible Windows ────────────────────────────────────────────────────────────

def _contexte_ssl():
    """Contexte SSL avec un magasin de certificats utilisable.

    Le Python de python.org sur macOS n'a pas de certificats tant que
    « Install Certificates.command » n'a pas été lancé (CERTIFICATE_VERIFY_FAILED).
    pip embarque le magasin certifi : on s'en sert, comme pip le fait.
    """
    import ssl
    for module in ('certifi', 'pip._vendor.certifi'):
        try:
            certifi = __import__(module, fromlist=['where'])
            return ssl.create_default_context(cafile=certifi.where())
        except (ImportError, OSError):
            continue
    return ssl.create_default_context()


def _telecharger_python_windows(progress_callback=None) -> Path:
    """Zip du Python embarqué Windows, depuis le cache ou python.org (vérifié)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / Path(PYTHON_WIN_URL).name

    def _empreinte(chemin: Path) -> str:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()

    if archive.exists() and _empreinte(archive) == PYTHON_WIN_SHA256:
        return archive

    _notifier(progress_callback, f"Téléchargement de Python {PYTHON_WIN_VERSION} pour Windows…")
    partiel = archive.with_suffix('.part')
    with urllib.request.urlopen(PYTHON_WIN_URL, timeout=120,
                                context=_contexte_ssl()) as reponse, \
            open(partiel, 'wb') as sortie:
        shutil.copyfileobj(reponse, sortie)
    if _empreinte(partiel) != PYTHON_WIN_SHA256:
        partiel.unlink(missing_ok=True)
        raise RuntimeError("Le Python pour Windows téléchargé est altéré "
                           "(empreinte inattendue). Réessayez l'export.")
    partiel.replace(archive)
    return archive


def _preparer_python_windows(dest: Path, archive: Path) -> Path:
    """Décompresse Python dans dest/python et règle son chemin d'import.

    Le fichier python312._pth fixe sys.path (le dossier du script n'y est PAS
    ajouté automatiquement) : on y déclare Lib\\site-packages pour les
    dépendances et « .. » (la racine de l'application) pour `import src…`.
    """
    dossier = dest / 'python'
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dossier)
    (dossier / 'Lib' / 'site-packages').mkdir(parents=True, exist_ok=True)
    pth = dossier / f'python{PYTHON_WIN_TAG}._pth'
    pth.write_text(
        f"python{PYTHON_WIN_TAG}.zip\r\n"
        ".\r\n"
        "Lib\\site-packages\r\n"
        "..\r\n"
        "import site\r\n",
        encoding='utf-8')
    return dossier


def _ecrire_exigences_windows(dossier: Path) -> tuple:
    """(exigences directes, contraintes) pour le pip download Windows.

    Les dépendances directes sont demandées, les versions éprouvées sur ce
    poste servent de contraintes (pip ignore celles qui ne servent pas).
    """
    pins = _dependances_epinglees()
    directes = [pins.get(_nom_normalise(n), n) for n in DEPENDANCES_DIRECTES]
    directes += list(DEPENDANCES_WINDOWS_SEULEMENT)
    contraintes = [v for k, v in pins.items() if k not in NON_EPINGLES_WINDOWS]
    req = dossier / 'exigences.txt'
    cst = dossier / 'contraintes.txt'
    req.write_text('\n'.join(directes) + '\n', encoding='utf-8')
    cst.write_text('\n'.join(sorted(contraintes, key=str.lower)) + '\n', encoding='utf-8')
    return req, cst


def _installer_dependances_windows(python_dir: Path, progress_callback=None):
    """Télécharge les wheels Windows (cp312, 64 bits) et les décompresse.

    Un wheel est une archive zip prête à poser dans site-packages : pas besoin
    de pip sur le poste cible. Les répertoires *.data/ (scripts en ligne de
    commande) ne servent pas à l'application et sont ignorés.
    """
    _notifier(progress_callback, "Téléchargement des dépendances Windows (1 à 2 minutes)…")
    site_packages = python_dir / 'Lib' / 'site-packages'
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        req, cst = _ecrire_exigences_windows(tmp)
        wheels = tmp / 'wheels'
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'download',
             '-r', str(req), '-c', str(cst), '-d', str(wheels),
             '--only-binary=:all:', '--platform', 'win_amd64',
             '--python-version', PYTHON_WIN_VERSION.rsplit('.', 1)[0],
             '--implementation', 'cp', '--quiet'],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("Échec du téléchargement des dépendances Windows. "
                               "Vérifiez la connexion internet.\n"
                               + result.stderr.strip()[-800:])
        _notifier(progress_callback, "Installation des dépendances dans le Python embarqué…")
        for wheel in sorted(wheels.glob('*.whl')):
            with zipfile.ZipFile(wheel) as zf:
                for membre in zf.infolist():
                    if membre.filename.split('/', 1)[0].endswith('.data'):
                        continue
                    zf.extract(membre, site_packages)


def _ecrire_lanceurs_windows(dest: Path):
    """Lanceurs .bat (fins de ligne CRLF, texte ASCII pour cmd.exe).

    - 1001pieces_autofill.bat : lance sans console (pythonw).
    - 1001pieces_autofill_console.bat : même chose avec console visible, pour
      lire un message d'erreur au démarrage.
    """
    lanceur = (
        "@echo off\r\n"
        "rem Lance 1001pieces_autofill sans fenetre de console\r\n"
        "cd /d \"%~dp0\"\r\n"
        "start \"\" \"%~dp0python\\pythonw.exe\" \"%~dp0run.py\"\r\n"
    )
    console = (
        "@echo off\r\n"
        "rem Lance 1001pieces_autofill avec la console (diagnostic)\r\n"
        "chcp 65001 >nul\r\n"
        "set PYTHONUTF8=1\r\n"
        "cd /d \"%~dp0\"\r\n"
        "\"%~dp0python\\python.exe\" \"%~dp0run.py\"\r\n"
        "echo.\r\n"
        "pause\r\n"
    )
    (dest / '1001pieces_autofill.bat').write_bytes(lanceur.encode('ascii'))
    (dest / '1001pieces_autofill_console.bat').write_bytes(console.encode('ascii'))


def _write_readme_windows(dest: Path, export_date: str):
    """LISEZMOI.txt pour le poste Windows (texte brut, CRLF)."""
    content = f"""\
1001pieces_autofill - Installation sur Windows
===============================================

Export genere le : {export_date}

Rien a installer : Python et toutes les dependances sont inclus.

1. Dezipper l'archive
   - Si l'archive vient d'un e-mail ou d'Internet : clic droit sur le .zip,
     Proprietes, cocher "Debloquer", OK (sinon Windows peut bloquer le lancement).
   - Clic droit sur le .zip, "Extraire tout...", choisir un dossier court
     (par exemple C:\\1001pieces ou le dossier Documents).
     Ne pas lancer l'application depuis l'interieur du .zip.

2. Lancer l'application
   - Double-clic sur 1001pieces_autofill.bat
   - Au premier lancement, si Windows affiche "Windows a protege votre
     ordinateur" : cliquer "Informations complementaires" puis "Executer quand meme".
   - Pour l'avoir sur le Bureau : clic droit sur 1001pieces_autofill.bat,
     "Afficher d'autres options", "Envoyer vers", "Bureau (creer un raccourci)".

3. En cas de probleme
   - Double-clic sur 1001pieces_autofill_console.bat : la meme application,
     avec une fenetre noire qui affiche les messages d'erreur.
   - Les journaux sont dans le dossier data\\logs.

Contenu du dossier
------------------
  1001pieces_autofill.bat          Lancement (double-clic)
  1001pieces_autofill_console.bat  Lancement avec messages de diagnostic
  data\\appareils.db                Base de donnees (copie la plus recente)
  docs\\guide_utilisation.html      Guide d'utilisation (aussi via le bouton Guide)
  fichiers_test_import\\            Fichiers PDF et CSV pour essayer l'import
  python\\                          Python {PYTHON_WIN_VERSION} et dependances (ne pas modifier)
  src\\, run.py                     Code de l'application

Raccourcis clavier : le guide indique Cmd (Mac) ; sous Windows c'est Ctrl.
"""
    (dest / 'LISEZMOI.txt').write_bytes(content.replace('\n', '\r\n').encode('utf-8'))


# ── Archive finale ───────────────────────────────────────────────────────────

def _zipper(dossier: Path, progress_callback=None) -> Path:
    """Compresse dossier/ en dossier.zip (dossier racine inclus) puis le supprime.

    La base de données se compresse très bien (~1/6). Les droits Unix sont
    conservés (install.command et le lanceur .app restent exécutables sur Mac).
    """
    archive = dossier.with_suffix('.zip')
    _notifier(progress_callback, "Compression de l'archive (1 à 2 minutes)…")
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for chemin in sorted(dossier.rglob('*')):
            if chemin.is_dir() or chemin.is_symlink():
                continue
            zf.write(chemin, (Path(dossier.name) / chemin.relative_to(dossier)).as_posix())
    shutil.rmtree(dossier)
    return archive


def create_export(output_dir: Path | str | None = None,
                  progress_callback=None,
                  cible: str = CIBLE_WINDOWS) -> dict:
    """
    Crée l'archive d'export pour le système cible.

    Args:
        output_dir : dossier parent dans lequel créer l'export.
                     Par défaut : Bureau de l'utilisateur.
        progress_callback : callable(message: str) appelé à chaque étape.
        cible : 'windows' (version portable, Python inclus) ou 'macos'.

    Returns:
        {'success': bool, 'path': str, 'size_mb': float, 'error': str, 'cible': str}
    """
    dest = None
    try:
        if cible not in CIBLES:
            raise ValueError(f"Cible d'export inconnue : {cible}")
        if output_dir is None:
            output_dir = Path.home() / 'Desktop'
        output_dir = Path(output_dir)

        export_date = datetime.now().strftime('%Y%m%d_%H%M')
        dest = output_dir / f'1001pieces_export_{cible}_{export_date}'
        if dest.exists():
            shutil.rmtree(dest)
        dest.with_suffix('.zip').unlink(missing_ok=True)
        dest.mkdir(parents=True)
        date_lisible = datetime.now().strftime('%d/%m/%Y %H:%M')

        # ── 1. Code, guide, réglages, fichiers de test ──────────────────────
        _notifier(progress_callback, "Copie du code source…")
        nb_files = _copy_source(dest, progress_callback)
        _write_export_config(dest)
        nb_files += _copy_test_import_files(dest)

        # ── 2. Base de données (instantané le plus récent) ──────────────────
        _snapshot_database(dest, progress_callback)

        # ── 3. Python / dépendances + lanceurs ──────────────────────────────
        if cible == CIBLE_WINDOWS:
            archive_py = _telecharger_python_windows(progress_callback)
            python_dir = _preparer_python_windows(dest, archive_py)
            _installer_dependances_windows(python_dir, progress_callback)
            _ecrire_lanceurs_windows(dest)
            _write_readme_windows(dest, date_lisible)
        else:
            _notifier(progress_callback, "Génération de requirements_frozen.txt…")
            frozen_req = _freeze_requirements(dest)
            if not _download_wheels(frozen_req, dest / 'wheels', progress_callback):
                raise RuntimeError("Échec du téléchargement des wheels pip. "
                                   "Vérifiez la connexion internet.")
            _notifier(progress_callback,
                      "Génération du script install.command et du lanceur .app…")
            _write_install_script(dest)
            _write_console_launcher(dest)
            if not _compile_app_launcher(dest, use_venv=True):
                raise RuntimeError("Le lanceur 1001pieces_autofill.app n'a pas pu être "
                                   "créé ou signé (osacompile / codesign).")
            _write_readme(dest, date_lisible)

        # ── 4. Archive .zip ─────────────────────────────────────────────────
        archive = _zipper(dest, progress_callback)
        size_mb = archive.stat().st_size / (1024 * 1024)
        _notifier(progress_callback, f"Export terminé — {nb_files} fichiers, {size_mb:.0f} Mo")

        return {
            'success': True,
            'path': str(archive),
            'size_mb': size_mb,
            'error': '',
            'cible': cible,
        }

    except Exception as e:
        # Pas de dossier à moitié rempli laissé derrière soi
        if dest is not None and dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return {
            'success': False,
            'path': '',
            'size_mb': 0.0,
            'error': str(e),
            'cible': cible,
        }


# ── Entrée CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Exporter 1001pieces_autofill vers une archive portable."
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help="Dossier parent de l'export (défaut : Bureau)"
    )
    parser.add_argument(
        '--cible', '-c',
        choices=CIBLES,
        default=CIBLE_WINDOWS,
        help="Système du poste cible (défaut : windows)"
    )
    args = parser.parse_args()

    def _print(msg):
        print(f"  {msg}")

    print(f"\n=== Export 1001pieces_autofill ({args.cible}) ===\n")
    result = create_export(
        output_dir=args.output,
        progress_callback=_print,
        cible=args.cible,
    )

    if result['success']:
        print(f"\n✅ Succès !")
        print(f"   Archive : {result['path']}")
        print(f"   Taille  : {result['size_mb']:.0f} Mo")
        print(f"\n   Sur le poste cible :")
        if args.cible == CIBLE_WINDOWS:
            print(f"     1. Dézipper l'archive")
            print(f"     2. Double-clic sur 1001pieces_autofill.bat\n")
        else:
            print(f"     1. Dézipper l'archive")
            print(f"     2. Installer Python {_python_requis()[0]} s'il est absent")
            print(f"     3. Double-clic sur install.command   (une seule fois)")
            print(f"     4. Double-clic sur 1001pieces_autofill.app\n")
    else:
        print(f"\n❌ Échec : {result['error']}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
