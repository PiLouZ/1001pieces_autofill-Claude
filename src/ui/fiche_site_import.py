"""
« Lire une fiche du site » : une fiche est un import comme un PDF ou un CSV
(CDC docs/cdc_import_fiches_site.md, § 10.12 à 10.14, PR 2)

1. `SaisieFicheSite` : une seule zone de texte ; un lien seul est téléchargé (hors
   du thread principal), tout autre texte est lu comme la description de la fiche
   (HTML du back-office ou texte).
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
    QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
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
                         suggested_reference=fiche.reference_proposee,
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


def ouvrir_import_lot(main_window, service, lot, plan, fin=None, parent=None):
    """Fenêtre d'import d'un lot de fiches : une carte par fiche (import de plusieurs
    fichiers). `service` : RepriseSiteService ; `fin(ResultatLot)` à la fin de l'import
    réel (thread principal). Retourne les cartes (index de fiche, fiche à importer)."""
    from src.core.import_manager import (FileType, ImportConfiguration, ImportFile,
                                         ImportType)
    from src.utils.text_utils import decouper_refs
    cartes = service.fiches_a_importer(lot, plan)
    fichiers = [ImportFile(path=f.nom_fichier, type=FileType.FICHE_SITE,
                           suggested_reference=f.reference_proposee, suggested_label=f.libelle,
                           data=lignes_import(f.plan), fiche=f) for _, f in cartes]
    config = ImportConfiguration(
        files=fichiers,
        import_type=ImportType.MULTI_FILE if len(fichiers) > 1 else ImportType.SINGLE_FILE)

    etat = {'prepare': False}

    def preparer(validee):
        etat['prepare'] = True
        saisies = validee.saisies_fiches
        if saisies is None:             # une seule fiche : fenêtre d'une fiche
            chemin = fichiers[0].path
            saisies = {chemin: {
                'importer': True, 'ref': validee.individual_references.get(chemin),
                'libelle': validee.individual_labels.get(chemin),
                'remplace': decouper_refs(validee.succession_replaces),
                'remplacee_par': decouper_refs(validee.succession_replaced_by),
                'equivalentes': decouper_refs(validee.equivalence_ref),
                'obsolete': bool(validee.obsolete_refs)}}
        return service.preparer_import_lot(lot, plan, cartes, saisies, fin=fin)

    def apres_import(results):
        if hasattr(main_window, '_on_import_complete'):
            main_window._on_import_complete(results)
        if not etat['prepare'] and fin is not None:
            fin(None)                   # fenêtre d'import fermée sans importer

    e = lot.export
    titre = ("Importer les fiches mises de côté" if lot.fiches_de_cote
             else f"Importer les fiches du site — produits {e.premier_id} à {e.dernier_id}")
    gestionnaire = getattr(main_window, 'import_manager', None)
    if gestionnaire is None:
        from src.core.import_manager import ImportManager
        gestionnaire = ImportManager(service.db, parent_widget=parent)
    gestionnaire.importer_avec_dialogue(config, callback=apres_import, preparer=preparer,
                                        titre=titre)
    return cartes


_LIEN = re.compile(r'^https?://\S+$', re.I)


def est_un_lien(texte: str) -> bool:
    """Un lien seul (http ou https), sans autre texte : à télécharger."""
    return bool(_LIEN.match((texte or '').strip()))


class SaisieFicheSite(QDialog):
    """Une seule zone : le lien d'une fiche ou sa description. « Lire » reconnaît
    un lien (téléchargé) d'un texte (lu comme description), puis ouvre la fenêtre
    d'import."""

    def __init__(self, main_window, url: str = '',
                 service: Optional[EnregistrementFicheService] = None):
        super().__init__(main_window)
        self.main_window = main_window
        self.service = service or EnregistrementFicheService(main_window.db_manager, main_window)
        self.setWindowTitle("Lire une fiche du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(720, 260)
        self._telechargement = None
        self.fiche = None
        self._construire()
        if url:
            self.champ.setPlainText(url.strip())

    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)
        aide = QLabel("Collez le lien d'une fiche de 1001pieces.com, ou sa description (HTML du "
                      "back-office ou texte). La fenêtre d'import s'ouvre ensuite, comme pour un PDF.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(aide)
        self.champ = QPlainTextEdit()
        self.champ.setPlaceholderText("https://www.1001pieces.com/20746-….html\n— ou —\n"
                                      "la description de la fiche")
        racine.addWidget(self.champ, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        fermer = QPushButton("Annuler")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        self.bouton_lire = QPushButton(qta.icon('fa5s.file-import', color='white'), "Lire")
        self.bouton_lire.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_lire.setDefault(True)
        self.bouton_lire.clicked.connect(self.lire)
        pied.addWidget(self.etat, 1)
        pied.addWidget(fermer)
        pied.addWidget(self.bouton_lire)
        racine.addLayout(pied)

    # --- Lecture ----------------------------------------------------------------
    def lire(self):
        """Lien seul : téléchargé ; tout autre texte : lu comme une description."""
        texte = self.champ.toPlainText().strip()
        if not texte:
            return
        if est_un_lien(texte):
            self.lire_lien(texte)
        else:
            self._analyser(lambda: self.service.analyser_description(texte)[1])

    def lire_lien(self, url: str = ''):
        url = (url or self.champ.toPlainText()).strip()
        if not url or self._telechargement is not None:
            return
        self.etat.setText("Téléchargement de la fiche…")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_lire.setEnabled(False)
        self._telechargement = Telechargement(url, self)
        self._telechargement.termine.connect(lambda page, err: self._page_recue(url, page, err))
        self._telechargement.start()

    def _page_recue(self, url: str, page: str, erreur: str):
        self._telechargement = None
        self.bouton_lire.setEnabled(True)
        if erreur:
            self.etat.setText(f"Lien illisible : {erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        self.analyser_page(page, url)

    def analyser_page(self, page: str, url: str = ''):
        """Lecture d'une page publique (appelée aussi par les tests, sans réseau)."""
        self._analyser(lambda: self.service.analyser_page(page, url)[1], url)

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
