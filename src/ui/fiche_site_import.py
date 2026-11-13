"""
« Lire une fiche du site » : une fiche est un import comme un PDF ou un CSV
(CDC docs/cdc_import_fiches_site.md, § 10.12 à 10.14, PR 2)

1. `SaisieFicheSite` : le lien de la page publique (téléchargée hors du thread
   principal) ou la description collée (HTML du back-office ou texte).
2. La fiche est lue, rapprochée et planifiée par les règles de l'import, sans
   question (`EnregistrementFicheService.fiche_a_importer`).
3. `ouvrir_import_fiche` ouvre la fenêtre d'import habituelle (`ImportDialog`) :
   aperçu des lignes, référence et libellé, section « Succession » préremplie,
   bandeau si la fiche est à refaire depuis les PDF. « Importer » lance l'import
   réel, puis l'historique, « Suggestions à valider » et « Auto-complétés à
   vérifier » comme après tout import.

Un lien de 1001pieces.com collé dans le tableau (Cmd+V) ouvre la même saisie,
qui lit aussitôt la fiche (`est_lien_fiche_site`).

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import re
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.enregistrement_fiche_service import (
    EnregistrementFicheService, lignes_import, telecharger_page,
)
from .style_manager import StyleManager

_LIEN_SITE = re.compile(r'^https?://(?:www\.)?1001pieces\.com/\S+$', re.I)


def est_lien_fiche_site(texte: str) -> bool:
    """Le texte collé est-il le lien d'une fiche de 1001pieces.com (et rien d'autre) ?"""
    return bool(_LIEN_SITE.match((texte or '').strip()))


class Telechargement(QThread):
    """Téléchargement de la page publique, hors du thread principal."""
    termine = pyqtSignal(str, str)      # page, erreur

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.termine.emit(telecharger_page(self.url), '')
        except Exception as e:
            self.termine.emit('', str(e))


def ouvrir_import_fiche(main_window, r, url: str = '',
                        service: Optional[EnregistrementFicheService] = None,
                        callback: Optional[Callable] = None):
    """Fenêtre d'import d'une fiche lue (`r` : son rapprochement). Retourne la
    fiche à importer (sa lecture et son plan)."""
    from src.core.import_manager import (FileType, ImportConfiguration, ImportFile,
                                         ImportType)
    service = service or EnregistrementFicheService(main_window.db_manager, main_window)
    fiche = service.fiche_a_importer(r, url)
    fichier = ImportFile(path=fiche.nom_fichier, type=FileType.FICHE_SITE,
                         suggested_reference=fiche.plan.ref_piece,
                         suggested_label=fiche.libelle, data=lignes_import(fiche.plan),
                         fiche=fiche)
    config = ImportConfiguration(files=[fichier], import_type=ImportType.SINGLE_FILE)

    def preparer(validee):
        reelle, resultat = service.preparer_import(fiche, validee)
        return reelle, lambda _results: service.apres_import(resultat)

    def fin(results):
        if callback is not None:
            callback(results)
        elif hasattr(main_window, '_on_import_complete'):
            main_window._on_import_complete(results)
        if results and fiche.plan.ref_piece and hasattr(main_window, '_apres_fiche_site'):
            main_window._apres_fiche_site(fiche.plan.ref_piece, results)

    main_window.import_manager.importer_avec_dialogue(
        config, callback=fin, preparer=preparer, titre="Importer une fiche du site")
    return fiche


class SaisieFicheSite(QDialog):
    """Lien ou description d'une fiche du site, puis fenêtre d'import."""

    def __init__(self, main_window, url: str = '',
                 service: Optional[EnregistrementFicheService] = None):
        super().__init__(main_window)
        self.main_window = main_window
        self.service = service or EnregistrementFicheService(main_window.db_manager, main_window)
        self.setWindowTitle("Lire une fiche du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(760, 160)
        self._telechargement = None
        self.fiche = None
        self._construire()
        if url:
            self.champ_lien.setText(url.strip())

    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)
        aide = QLabel("Une fiche du site s'importe comme un PDF : indiquez son lien, ou collez "
                      "sa description. La fenêtre d'import s'ouvre ensuite.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(aide)

        entree = QHBoxLayout()
        self.champ_lien = QLineEdit()
        self.champ_lien.setPlaceholderText("Lien de la fiche : https://www.1001pieces.com/20746-….html")
        self.champ_lien.returnPressed.connect(self.lire_lien)
        self.bouton_lien = QPushButton(qta.icon('fa5s.globe', color='#555555'), "Lire")
        self.bouton_lien.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_lien.clicked.connect(self.lire_lien)
        self.bouton_coller = QPushButton(qta.icon('fa5s.paste', color='#555555'), "Coller le texte…")
        self.bouton_coller.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_coller.setCheckable(True)
        self.bouton_coller.toggled.connect(lambda actif: self.zone_collage.setVisible(actif))
        entree.addWidget(self.champ_lien, 1)
        entree.addWidget(self.bouton_lien)
        entree.addWidget(self.bouton_coller)
        racine.addLayout(entree)

        self.zone_collage = QWidget()
        collage = QVBoxLayout(self.zone_collage)
        collage.setContentsMargins(0, 0, 0, 0)
        self.champ_description = QPlainTextEdit()
        self.champ_description.setPlaceholderText(
            "Description de la fiche (HTML du back-office ou texte)")
        self.champ_description.setMaximumHeight(160)
        bouton = QPushButton("Lire le texte")
        bouton.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        bouton.clicked.connect(self.lire_description)
        collage.addWidget(self.champ_description)
        collage.addWidget(bouton, 0, Qt.AlignRight)
        self.zone_collage.setVisible(False)
        racine.addWidget(self.zone_collage)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        fermer = QPushButton("Annuler")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        pied.addWidget(fermer)
        racine.addLayout(pied)

    # --- Lecture ----------------------------------------------------------------
    def lire_lien(self):
        url = self.champ_lien.text().strip()
        if not url or self._telechargement is not None:
            return
        self.etat.setText("Téléchargement de la fiche…")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_lien.setEnabled(False)
        self._telechargement = Telechargement(url, self)
        self._telechargement.termine.connect(lambda page, err: self._page_recue(url, page, err))
        self._telechargement.start()

    def _page_recue(self, url: str, page: str, erreur: str):
        self._telechargement = None
        self.bouton_lien.setEnabled(True)
        if erreur:
            self.etat.setText(f"Lien illisible : {erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        self.analyser_page(page, url)

    def analyser_page(self, page: str, url: str = ''):
        """Lecture d'une page publique (appelée aussi par les tests, sans réseau)."""
        self._analyser(lambda: self.service.analyser_page(page, url)[1], url)

    def lire_description(self):
        texte = self.champ_description.toPlainText()
        if texte.strip():
            self._analyser(lambda: self.service.analyser_description(texte)[1])

    def _analyser(self, lire, url: str = ''):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = lire()
        except Exception as e:
            app_logger.error(f"[Fiche site] lecture impossible : {e}")
            self.etat.setText(f"Lecture impossible : {e}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.fiche = ouvrir_import_fiche(self.main_window, r, url, service=self.service)
        self.close()
