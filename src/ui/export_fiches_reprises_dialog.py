"""
Fenêtre « Exporter les fiches reprises (EveryParts) » (CDC docs/cdc_import_fiches_site.md,
§ 10.19)

- La liste des produits du site repris : référence produit (1ʳᵉ colonne de l'export),
  n° du produit, pièce, lu le, exporté le. Par défaut, ceux à exporter (jamais
  exportés, ou relus depuis) ; « Tous » montre le reste. Une recherche filtre.
- La sélection (toute la liste par défaut) s'exporte au format CSV EveryParts de
  la configuration des exports, appareils de la pièce et de ses anciennes
  références compris : un fichier par produit, ou un seul fichier.
- Le dossier est celui des exports ; « Changer… » en choisit un autre pour cet export.

Non bloquant : show() + callbacks, jamais exec_() ; l'export tourne dans un thread.
"""

import threading
from typing import List, Optional

from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.export_fiches_reprises_service import ExportFichesReprisesService
from src.utils.boites import choisir_dossier
from .style_manager import StyleManager

_COLONNES = ("Réf. produit (EveryParts)", "N° du produit", "Pièce", "Lu le", "Exporté le")
_A_EXPORTER, _TOUS = "À exporter (jamais exportés, ou relus depuis)", "Tous les produits repris"


class _Export(QThread):
    progression = pyqtSignal(int, int, str)
    termine = pyqtSignal(object, str)

    def __init__(self, fonction, parent=None):
        super().__init__(parent)
        self.fonction = fonction
        self.arret = threading.Event()

    def run(self):
        try:
            self.termine.emit(self.fonction(lambda i, n, t: self.progression.emit(i, n, t),
                                            self.arret.is_set), '')
        except Exception as e:
            app_logger.error(f"[Export EveryParts fiches reprises] {type(e).__name__} : {e}")
            self.termine.emit(None, f"{type(e).__name__} : {e}")


def _date(texte) -> str:
    return (texte or '').replace('T', ' ')[:16]


class ExportFichesReprisesDialog(QDialog):
    """Export EveryParts des fiches reprises du site."""

    def __init__(self, db_manager, main_window=None,
                 service: Optional[ExportFichesReprisesService] = None):
        super().__init__(main_window)
        self.main_window = main_window
        self.service = service or ExportFichesReprisesService(db_manager, main_window)
        self.setWindowTitle("Exporter les fiches reprises (EveryParts)")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(980, 600)
        self.produits: List[dict] = []
        self.affiches: List[dict] = []
        self.dossier = self.service.dossier()
        self._export: Optional[_Export] = None
        self._construire()
        self.charger()

    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)
        aide = QLabel("Chaque produit du site repris donne ses compatibilités au format EveryParts de "
                      "la configuration des exports : sa référence produit en 1ʳᵉ colonne, et les "
                      "appareils de la pièce et de ses anciennes références.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.BANDEAU_INFO)
        racine.addWidget(aide)

        filtres = QHBoxLayout()
        self.filtre = QComboBox()
        self.filtre.addItems([_A_EXPORTER, _TOUS])
        self.filtre.currentIndexChanged.connect(lambda *_: self.charger())
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher une réf. produit, un n° ou une pièce")
        self.recherche.textChanged.connect(lambda *_: self._afficher())
        filtres.addWidget(self.filtre)
        filtres.addWidget(self.recherche, 1)
        racine.addLayout(filtres)

        self.table = QTableWidget(0, len(_COLONNES))
        self.table.setHorizontalHeaderLabels(_COLONNES)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._activer)
        racine.addWidget(self.table, 1)

        options = QHBoxLayout()
        self.un_seul = QCheckBox("Un seul fichier pour toute la sélection")
        self.un_seul.setToolTip("Sinon : un fichier par produit, nommé d'après sa référence produit "
                                "(modèle de nom de la configuration des exports).")
        options.addWidget(self.un_seul)
        options.addStretch(1)
        self.texte_dossier = QLabel()
        self.texte_dossier.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        changer = QPushButton(qta.icon('fa5s.folder-open', color='#555555'), "Changer…")
        changer.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        changer.clicked.connect(self._changer_dossier)
        options.addWidget(self.texte_dossier)
        options.addWidget(changer)
        racine.addLayout(options)

        self.barre = QProgressBar()
        self.barre.setStyleSheet(StyleManager.BARRE_PROGRESSION_DISCRETE)
        self.barre.setTextVisible(False)
        self.barre.setFixedHeight(8)
        self.barre.setVisible(False)
        racine.addWidget(self.barre)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_dossier = QPushButton(qta.icon('fa5s.folder', color='#555555'), "Ouvrir le dossier")
        self.bouton_dossier.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_dossier.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.dossier)))
        self.bouton_exporter = QPushButton(qta.icon('fa5s.file-csv', color='white'), "Exporter")
        self.bouton_exporter.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_exporter.clicked.connect(self.exporter)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        for b in (self.bouton_dossier, self.bouton_exporter, fermer):
            pied.addWidget(b)
        racine.addLayout(pied)
        self._maj_dossier()

    # --- Liste -------------------------------------------------------------------
    def charger(self):
        self.produits = self.service.produits(non_exportes=self.filtre.currentText() == _A_EXPORTER)
        self._afficher()

    def _afficher(self):
        texte = self.recherche.text().strip().lower()
        self.affiches = [p for p in self.produits if not texte or any(
            texte in str(p[c] or '').lower() for c in ('ref_interne', 'id_product', 'ref_piece'))]
        self.table.setRowCount(len(self.affiches))
        for ligne, p in enumerate(self.affiches):
            for col, valeur in enumerate((p['ref_interne'], str(p['id_product'] or ''), p['ref_piece'],
                                          _date(p['lu_le']), _date(p['exporte_le']) or '—')):
                self.table.setItem(ligne, col, QTableWidgetItem(valeur))
        self.table.resizeColumnsToContents()
        self.table.clearSelection()
        self._activer()

    def selection(self) -> List[dict]:
        """Lignes sélectionnées ; aucune : toute la liste affichée."""
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.affiches[i] for i in lignes] if lignes else list(self.affiches)

    def _activer(self):
        n = len(self.selection())
        occupe = self._export is not None
        self.bouton_exporter.setText(f"Exporter ({n})")
        self.bouton_exporter.setEnabled(bool(n) and not occupe)
        if not occupe:
            self.etat.setText(f"{len(self.affiches)} produit(s) dans la liste ; sans sélection, "
                              f"toute la liste est exportée." if self.affiches
                              else "Aucun produit à exporter.")
            self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)

    # --- Dossier -----------------------------------------------------------------
    def _maj_dossier(self):
        self.texte_dossier.setText(f"Dossier : {self.dossier}")
        self.texte_dossier.setToolTip(self.dossier)

    def _changer_dossier(self):
        choisir_dossier(self, "Dossier de l'export EveryParts", self.dossier, self._dossier_choisi)

    def _dossier_choisi(self, chemin: str):
        self.dossier = chemin
        self._maj_dossier()

    # --- Export ------------------------------------------------------------------
    def exporter(self):
        produits = self.selection()
        if not produits or self._export is not None:
            return
        dossier, un_seul = self.dossier, self.un_seul.isChecked()
        self._export = _Export(lambda prog, annule: self.service.exporter(
            produits, dossier, un_seul, prog, annule), self)
        self._export.progression.connect(self._progresser)
        self._export.termine.connect(self._termine)
        self.barre.setVisible(True)
        self.barre.setRange(0, len(produits))
        self._activer()
        self.etat.setText("Export en cours…")
        self._export.start()

    def _progresser(self, i: int, n: int, texte: str):
        self.barre.setRange(0, max(n, 1))
        self.barre.setValue(i)
        self.etat.setText(f"Export : {texte}")

    def _termine(self, res, erreur: str):
        self._export = None
        self.barre.setVisible(False)
        if res is None:
            self.etat.setText(f"Export impossible : {erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            self.bouton_exporter.setEnabled(True)
            return
        message = f"Export EveryParts des fiches reprises : {res.resume()} → {self.dossier}"
        historique = getattr(getattr(self.main_window, 'user_interaction_service', None),
                             'add_to_history', None)
        if callable(historique):
            historique(message)
        self.charger()
        self.etat.setText(message)

    def closeEvent(self, event):
        if self._export is not None:
            self._export.arret.set()
            self._export.wait(5000)
        super().closeEvent(event)
