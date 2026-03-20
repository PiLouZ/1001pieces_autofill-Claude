"""
AppExportService — Export portable de l'application

Responsabilités :
- Dialogue de sélection du dossier de destination
- Lancement de l'export dans un thread non-bloquant (QThread)
- Affichage de la progression (QProgressDialog)
- Affichage du résultat (succès / erreur)

Délègue la logique métier à export_app.create_export() (racine du projet).
"""

import importlib.util
import pathlib

from .base_service import BaseService
from ..ui.qt_imports import QThread, pyqtSignal, QFileDialog, Qt
from ..ui.progress_dialog import ProgressDialog
from ..ui.message_helper import MessageHelper
from ..core.logger import app_logger

# Chemin vers le script d'export à la racine du projet
_EXPORT_SCRIPT = pathlib.Path(__file__).parent.parent.parent / 'export_app.py'


class _ExportWorker(QThread):
    """Thread d'export — charge et exécute export_app.create_export()."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, output_dir: str):
        super().__init__()
        self._output_dir = output_dir

    def run(self):
        try:
            spec = importlib.util.spec_from_file_location('export_app', _EXPORT_SCRIPT)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod.create_export(
                output_dir=self._output_dir,
                progress_callback=lambda msg: self.progress.emit(msg),
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

    def open_dialog(self):
        """
        Ouvrir le dialogue de sélection du dossier puis lancer l'export.
        Méthode non-bloquante : l'UI reste responsive pendant l'export.
        """
        parent = self.parent_window

        # ── Sélection du dossier de destination ─────────────────────────────
        output_dir = QFileDialog.getExistingDirectory(
            parent,
            "Choisir le dossier de destination de l'export",
            str(pathlib.Path.home() / 'Desktop'),
        )
        if not output_dir:
            return

        # ── Barre de progression ─────────────────────────────────────────────
        progress_dlg = ProgressDialog("Export de l'application", None, 0, 0, parent)
        progress_dlg.show()

        # ── Thread d'export ──────────────────────────────────────────────────
        worker = _ExportWorker(output_dir)
        self._worker = worker  # Maintenir la référence

        def _on_progress(msg):
            progress_dlg.setLabelText(msg)

        def _on_finished(result):
            progress_dlg.close()
            if result['success']:
                # Régénérer aussi le lanceur .app sur la machine source
                spec = importlib.util.spec_from_file_location('export_app', _EXPORT_SCRIPT)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.create_source_launcher()

                MessageHelper.show_info(
                    parent,
                    f"Export terminé avec succès !\n\n"
                    f"Dossier : {result['path']}\n"
                    f"Taille  : {result['size_mb']:.0f} Mo\n\n"
                    f"Sur le poste cible :\n"
                    f"  1. Double-clic sur install.command   (une seule fois)\n"
                    f"  2. Double-clic sur 1001pieces_autofill.app",
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
