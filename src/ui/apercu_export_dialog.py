"""
Fenêtre d'aperçu d'export (clic sur la flèche de Titre, Fiche complète, HTML Détails)

À gauche les gabarits du bouton (filtre, gabarit par défaut en tête, marqué ★),
à droite l'export du gabarit sélectionné sur la VRAIE recherche en cours :
onglet Rendu (tel qu'affiché sur le site) et onglet Code (coloré, indenté).
Copier (ou double-clic) copie exactement ce qui est affiché, avec l'historique
habituel du bouton, puis ferme la fenêtre et rend la main à la fenêtre principale.

Les données de la recherche sont préparées une fois (contexte), puis chaque
gabarit est rendu à la demande. La fenêtre ne bloque pas l'application : une
nouvelle recherche met l'aperçu à jour (sans boîte de choix pendant la saisie ;
« Actualiser » la propose pour une recherche multi-références).
"""

import html
from typing import Any, Dict, List, Optional

from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QTabWidget, QTextBrowser, QPlainTextEdit, QSplitter, QWidget,
    QTimer, QEvent, Qt, QFont, QFontDatabase
)
from src.core.constants import ExportFormat
from src.core.logger import app_logger
from src.services.html_export_service import HtmlExportService
from src.utils.text_utils import cle_tri_naturel, strip_accents
from .champ_modele_html import ColorationHtml, formater_html
from .style_manager import StyleManager


# ─── Sources : un bouton à gabarits = une source ─────────────────────────────

class SourceTitre:
    genre, libelle = 'titre', "Titre"

    def __init__(self, mw):
        self.mw = mw

    def noms(self) -> List[str]:
        return self.mw.export_config_service.get_titre_profile_names()

    def defaut(self) -> str:
        return self.mw.export_config_service.get_default_titre_profile_name()

    def contexte(self, interactif):
        return self.mw.titre_produit_service.contexte(interactif=interactif)

    def rendre(self, contexte, nom):
        return self.mw.titre_produit_service.rendre(contexte, nom)

    def copier(self, contexte, nom):
        self.mw.titre_produit_service.copier(contexte, nom)


class SourceFiche(SourceTitre):
    genre, libelle = 'fiche', "Fiche complète"

    def noms(self):
        return self.mw.export_config_service.get_fiche_profile_names()

    def defaut(self):
        return self.mw.export_config_service.get_default_fiche_profile_name()

    def contexte(self, interactif):
        return self.mw.fiche_produit_service.contexte(interactif=interactif)

    def rendre(self, contexte, nom):
        return self.mw.fiche_produit_service.rendre(contexte, nom)

    def copier(self, contexte, nom):
        self.mw.fiche_produit_service.copier(contexte, nom)


class SourceHtmlDetails(SourceTitre):
    genre, libelle = 'html_details', "HTML Détails"

    def noms(self):
        return self.mw.export_config_service.get_details_profile_names()

    def defaut(self):
        return self.mw.export_config_service.get_default_details_profile_name()

    def contexte(self, interactif):
        appareils = self.mw.export_manager.donnees_tableau()
        if not appareils:
            self.mw.seo_service.raison_refus = "Aucun appareil affiché dans le tableau"
            return None
        terme = self.mw.search_input.text().strip()
        return {'appareils': appareils, 'reference': terme}

    def rendre(self, contexte, nom):
        appareils = contexte['appareils']
        contenu = HtmlExportService.generate_html_details(appareils, profile_name=nom)
        limite = self.mw.export_config_service.get_html_details_config(nom).get(
            'char_limit', HtmlExportService.CHAR_LIMIT)
        from .fiche_produit_service import FicheProduitService
        resume = (f"{HtmlExportService.count_non_html_chars(contenu)} car. / {limite} · "
                  f"{FicheProduitService._resume_appareils(appareils)}")
        reduction = FicheProduitService._reduction(contenu, HtmlExportService.last_strategy_used)
        if reduction:
            resume += f" · {reduction}"
        return {'html': contenu, 'resume': resume}

    def copier(self, contexte, nom):
        # Chemin habituel du bouton : mêmes messages d'historique
        self.mw._export_data(ExportFormat.HTML_DETAILS, profile_name=nom)


SOURCES = {'titre': SourceTitre, 'fiche': SourceFiche, 'html_details': SourceHtmlDetails}


# ─── Fenêtre ─────────────────────────────────────────────────────────────────

class ApercuExportDialog(QDialog):
    """Aperçu des gabarits d'un bouton d'export sur la recherche en cours."""

    DELAI_RECHERCHE_MS = 700

    def __init__(self, main_window, genre: str, parent=None):
        super().__init__(parent)
        self.mw = main_window
        self.source = SOURCES[genre](main_window)
        self._contexte: Optional[Dict[str, Any]] = None
        self._rendus: Dict[str, Dict[str, Any]] = {}

        self.setWindowTitle(f"Aperçu d'export — {self.source.libelle}")
        self.setModal(False)
        self.setMinimumSize(760, 480)
        self.resize(1000, 680)
        self._build_ui()

        # Nouvelle recherche : aperçu mis à jour après la saisie
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(self.DELAI_RECHERCHE_MS)
        self._minuterie.timeout.connect(lambda: self.recharger(interactif=False))
        self.mw.search_input.textChanged.connect(self._minuterie.start)

        self._remplir_liste()
        # Sans boîte de choix à l'ouverture : « Actualiser » la propose au besoin
        self.recharger(interactif=False)

    # ─── Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        entete = QHBoxLayout()
        self.titre_label = QLabel()
        police = QFont()
        police.setBold(True)
        self.titre_label.setFont(police)
        entete.addWidget(self.titre_label, 1)
        actualiser = QPushButton("Actualiser")
        actualiser.setToolTip("Relire la recherche en cours")
        actualiser.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        actualiser.clicked.connect(lambda: self.recharger(interactif=True))
        entete.addWidget(actualiser)
        layout.addLayout(entete)

        separateur = QSplitter(Qt.Horizontal)
        gauche = QWidget()
        gauche_layout = QVBoxLayout(gauche)
        gauche_layout.setContentsMargins(0, 0, 0, 0)
        self.filtre = QLineEdit()
        self.filtre.setPlaceholderText("Filtrer…")
        self.filtre.setClearButtonEnabled(True)
        self.filtre.textChanged.connect(self._filtrer)
        gauche_layout.addWidget(self.filtre)
        self.liste = QListWidget()
        self.liste.currentItemChanged.connect(lambda *_: self._afficher())
        self.liste.itemDoubleClicked.connect(lambda *_: self._copier())
        gauche_layout.addWidget(self.liste)
        separateur.addWidget(gauche)

        self.onglets = QTabWidget()
        self.rendu = QTextBrowser()
        self.rendu.setOpenLinks(False)
        self.rendu.setStyleSheet("background: white; border: none;")
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        police_code = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()
        self.code.setStyleSheet(f"QPlainTextEdit {{ font-family: '{police_code}', Menlo, monospace;"
                                " font-size: 12px; background: white; border: none; }")
        self._coloration = ColorationHtml(self.code.document())
        self.onglets.addTab(self.rendu, "Rendu")
        self.onglets.addTab(self.code, "Code")
        separateur.addWidget(self.onglets)
        separateur.setStretchFactor(0, 0)
        separateur.setStretchFactor(1, 1)
        separateur.setSizes([230, 770])
        layout.addWidget(separateur, 1)

        self.resume_label = QLabel()
        self.resume_label.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.resume_label.setWordWrap(True)
        layout.addWidget(self.resume_label)

        pied = QHBoxLayout()
        pied.addStretch()
        self.modifier_btn = QPushButton("Modifier le modèle…")
        self.modifier_btn.setToolTip("Ouvrir ce gabarit dans la configuration des exports")
        self.modifier_btn.clicked.connect(self._modifier)
        self.defaut_btn = QPushButton("Par défaut")
        self.defaut_btn.setToolTip("Utiliser ce gabarit au clic sur le bouton")
        self.defaut_btn.clicked.connect(self._definir_defaut)
        self.copier_btn = QPushButton("Copier")
        self.copier_btn.setDefault(True)
        self.copier_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.copier_btn.clicked.connect(lambda: self._copier())
        fermer = QPushButton("Fermer")
        fermer.clicked.connect(self.close)
        for bouton in (self.modifier_btn, self.defaut_btn, self.copier_btn, fermer):
            pied.addWidget(bouton)
        layout.addLayout(pied)

    # ─── Liste des gabarits ──────────────────────────────────────────────

    def _remplir_liste(self, garder: Optional[str] = None):
        """Gabarit par défaut en tête (★), puis les autres par ordre alphanumérique."""
        defaut = self.source.defaut()
        noms = [n for n in self.source.noms() if n != defaut]
        noms.sort(key=cle_tri_naturel)
        choisi = garder if garder in noms + [defaut] else defaut
        self.liste.blockSignals(True)
        self.liste.clear()
        for nom in [defaut] + noms:
            item = QListWidgetItem(f"★ {nom}" if nom == defaut else nom)
            item.setData(Qt.UserRole, nom)
            if nom == defaut:
                item.setToolTip("Gabarit du clic sur le bouton")
            self.liste.addItem(item)
            if nom == choisi:
                self.liste.setCurrentItem(item)
        self.liste.blockSignals(False)
        self._filtrer(self.filtre.text())

    def _filtrer(self, texte):
        mots = strip_accents(texte).casefold().split()
        for i in range(self.liste.count()):
            item = self.liste.item(i)
            nom = strip_accents(item.data(Qt.UserRole)).casefold()
            item.setHidden(not all(m in nom for m in mots))
        courant = self.liste.currentItem()
        if courant is None or courant.isHidden():
            visibles = [self.liste.item(i) for i in range(self.liste.count())
                        if not self.liste.item(i).isHidden()]
            if visibles:
                self.liste.setCurrentItem(visibles[0])
        self._afficher()

    def nom_courant(self) -> Optional[str]:
        item = self.liste.currentItem()
        return item.data(Qt.UserRole) if item is not None and not item.isHidden() else None

    # ─── Données ─────────────────────────────────────────────────────────

    def recharger(self, interactif: bool = False):
        """Relire la recherche en cours (contexte) et réafficher le gabarit choisi."""
        self.mw.seo_service.raison_refus = None
        try:
            self._contexte = self.source.contexte(interactif)
        except Exception as e:
            app_logger.error(f"Aperçu d'export : lecture de la recherche échouée : {e}", exc_info=True)
            self._contexte = None
            self.mw.seo_service.raison_refus = f"Lecture de la recherche impossible : {e}"
        self._rendus = {}
        reference = (self._contexte or {}).get('reference') or self.mw.search_input.text().strip()
        self.titre_label.setText(f"Aperçu d'export — {self.source.libelle}"
                                 + (f" · {reference}" if reference else ""))
        self._afficher()

    def _rendu_courant(self) -> Optional[Dict[str, Any]]:
        nom = self.nom_courant()
        if nom is None or self._contexte is None:
            return None
        if nom not in self._rendus:
            self._rendus[nom] = self.source.rendre(self._contexte, nom)
        return self._rendus[nom]

    def _afficher(self):
        try:
            rendu = self._rendu_courant()
        except Exception as e:
            app_logger.error(f"Aperçu d'export : rendu échoué : {e}", exc_info=True)
            rendu, raison = None, f"Aperçu impossible : {e}"
        else:
            raison = (self.mw.seo_service.raison_refus
                      or ("Aucun gabarit ne correspond au filtre" if self.nom_courant() is None
                          else "Aucune recherche par pièce en cours"))
        actif = rendu is not None
        self.copier_btn.setEnabled(actif)
        self.defaut_btn.setEnabled(self.nom_courant() not in (None, self.source.defaut()))
        self.modifier_btn.setEnabled(self.nom_courant() is not None)
        if not actif:
            message = f"<p style='color:#6c757d; padding:12px;'>{html.escape(raison)}</p>"
            self.rendu.setHtml(message)
            self.code.setPlainText("")
            self.resume_label.setText(raison)
            return
        self.rendu.setHtml(f"<html><body style='font-size:13px; padding:8px;'>{rendu['html']}</body></html>")
        self.code.setPlainText(formater_html(rendu['html']))
        self.resume_label.setText(rendu['resume'])

    # ─── Actions ─────────────────────────────────────────────────────────

    def _copier(self):
        """Copier puis revenir sur la fenêtre principale (le code va être collé ailleurs)."""
        nom = self.nom_courant()
        if nom is None or self._contexte is None:
            return
        self.source.copier(self._contexte, nom)
        self.close()
        principale = self.mw
        if hasattr(principale, 'activateWindow'):
            principale.raise_()
            principale.activateWindow()

    def _definir_defaut(self):
        nom = self.nom_courant()
        if nom is None:
            return
        if self.mw.export_config_service.definir_profil_par_defaut(self.source.genre, nom):
            self.mw.ui_component_service.refresh_profile_menus()
            self._remplir_liste(garder=nom)

    def _modifier(self):
        nom = self.nom_courant()
        if nom is not None:
            self.mw._open_export_config(self.source.genre, nom)

    # ─── Fenêtre ─────────────────────────────────────────────────────────

    def changeEvent(self, event):
        super().changeEvent(event)
        # Retour sur la fenêtre (après la configuration des exports) : gabarits à jour
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            noms = set(self.source.noms())
            affiches = {self.liste.item(i).data(Qt.UserRole) for i in range(self.liste.count())}
            if noms != affiches or self.liste.count() and \
                    self.liste.item(0).data(Qt.UserRole) != self.source.defaut():
                self._remplir_liste(garder=self.nom_courant())
            else:
                self._rendus = {}
                self._afficher()

    def closeEvent(self, event):
        try:
            self.mw.search_input.textChanged.disconnect(self._minuterie.start)
        except (TypeError, RuntimeError):
            pass
        self._minuterie.stop()
        super().closeEvent(event)
