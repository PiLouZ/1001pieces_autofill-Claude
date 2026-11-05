"""
AppExportService — Export portable de l'application

Responsabilités :
- Choix du système du poste cible (Windows / macOS)
- Dialogue de sélection du dossier de destination
- Lancement de l'export dans un thread non-bloquant (QThread)
- Affichage de la progression (QProgressDialog)
- Affichage du résultat (succès / erreur)

Délègue la logique métier à export_app.create_export() (racine du projet).
"""

import importlib.util
import pathlib
import sys

from .base_service import BaseService
from .export_config_service import ExportConfigService
from ..utils.qt_imports import QThread, pyqtSignal, QMessageBox, Qt
from ..ui.progress_dialog import ProgressDialog
from ..ui.message_helper import MessageHelper
from ..ui.style_manager import StyleManager
from ..core.logger import app_logger
from ..utils.boites import choisir_dossier

# Chemin vers le script d'export à la racine du projet
_EXPORT_SCRIPT = pathlib.Path(__file__).parent.parent.parent / 'export_app.py'

CIBLE_WINDOWS = 'windows'
CIBLE_MACOS = 'macos'


def _charger_module_export():
    spec = importlib.util.spec_from_file_location('export_app', _EXPORT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ExportWorker(QThread):
    """Thread d'export — charge et exécute export_app.create_export()."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, output_dir: str, cible: str = CIBLE_WINDOWS):
        super().__init__()
        self._output_dir = output_dir
        self._cible = cible

    def run(self):
        try:
            mod = _charger_module_export()
            result = mod.create_export(
                output_dir=self._output_dir,
                progress_callback=lambda msg: self.progress.emit(msg),
                cible=self._cible,
            )
        except Exception as e:
            app_logger.error(f"Erreur _ExportWorker : {e}")
            result = {'success': False, 'path': '', 'size_mb': 0.0, 'error': str(e)}
        self.finished.emit(result)


class AppExportService(BaseService):
    """
    Service d'export portable de l'application.
    S'instancie avec la fenêtre principale, expose open_dialog().
    """

    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self._worker = None  # Référence pour éviter la GC prématurée
        self._boite_cible = None  # Référence (QMessageBox en show non bloquant)

    def open_dialog(self):
        """
        Demander le système cible, puis le dossier, puis lancer l'export.
        Méthode non-bloquante : l'UI reste responsive pendant l'export.
        """
        parent = self.parent_window

        # Un poste qui a reçu un export n'a pas le script : l'export se fait
        # depuis le poste d'origine (celui qui a les outils de téléchargement)
        if not _EXPORT_SCRIPT.exists():
            MessageHelper.show_info(
                parent,
                "L'export de l'application se fait depuis le poste d'origine.\n\n"
                "Cette copie a elle-même été installée à partir d'un export.",
                "Export de l'application",
            )
            return

        # ── Choix du système cible (non bloquant : show + callback) ─────────
        boite = QMessageBox(parent)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle("Exporter l'application")
        boite.setText("<b>Sur quel système l'application sera-t-elle installée ?</b>")
        boite.setInformativeText(
            "L'export contient l'application, la base de données la plus récente, "
            "le guide d'utilisation et des fichiers de test d'import, dans une "
            "archive .zip.<br><br>"
            "<b>Windows</b> : version portable, Python inclus — dézipper puis "
            "double-cliquer, rien à installer.<br>"
            f"<b>macOS</b> : nécessite Python {sys.version_info.major}."
            f"{sys.version_info.minor} (la version de ce poste) sur le Mac cible.")
        windows = boite.addButton("Windows", QMessageBox.AcceptRole)
        macos = boite.addButton("macOS", QMessageBox.ActionRole)
        boite.addButton("Annuler", QMessageBox.RejectRole)
        windows.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        boite.setDefaultButton(windows)

        def _on_choix(bouton):
            if bouton is windows:
                self._choisir_dossier_et_exporter(CIBLE_WINDOWS)
            elif bouton is macos:
                self._choisir_dossier_et_exporter(CIBLE_MACOS)

        boite.buttonClicked.connect(_on_choix)
        boite.setWindowModality(Qt.WindowModal)
        self._boite_cible = boite
        boite.show()

    def _choisir_dossier_et_exporter(self, cible: str):
        parent = self.parent_window

        # ── Sélection du dossier de destination ─────────────────────────────
        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite(output_dir):
            # ── Barre de progression ─────────────────────────────────────────────
            progress_dlg = ProgressDialog("Export de l'application", None, 0, 0, parent)
            progress_dlg.show()

            # ── Thread d'export ──────────────────────────────────────────────────
            worker = _ExportWorker(output_dir, cible)
            self._worker = worker  # Maintenir la référence

            def _on_progress(msg):
                progress_dlg.setLabelText(msg)

            def _on_finished(result):
                progress_dlg.close()
                self._worker.wait()
                self._worker = None
                if result['success']:
                    # Régénérer aussi le lanceur .app sur la machine source (Mac seulement)
                    if sys.platform == 'darwin':
                        _charger_module_export().create_source_launcher()

                    if cible == CIBLE_WINDOWS:
                        etapes = ("  1. Dézipper l'archive (clic droit → Extraire tout…)\n"
                                  "  2. Double-clic sur 1001pieces_autofill.bat")
                    else:
                        version = f"{sys.version_info.major}.{sys.version_info.minor}"
                        etapes = ("  1. Dézipper l'archive\n"
                                  f"  2. Installer Python {version} s'il est absent\n"
                                  "  3. Double-clic sur install.command   (une seule fois)\n"
                                  "  4. Double-clic sur 1001pieces_autofill.app")
                    MessageHelper.show_info(
                        parent,
                        f"Export terminé avec succès !\n\n"
                        f"Archive : {result['path']}\n"
                        f"Taille  : {result['size_mb']:.0f} Mo\n\n"
                        f"Sur le poste cible :\n{etapes}",
                        "Export réussi",
                    )
                else:
                    MessageHelper.show_error(
                        parent,
                        f"Échec de l'export :\n{result['error']}",
                        "Erreur export",
                    )

            worker.progress.connect(_on_progress)
            worker.finished.connect(_on_finished)
            worker.start()

        choisir_dossier(parent, "Choisir le dossier de destination de l'export", ExportConfigService.get_default_output_dir(), _suite)
