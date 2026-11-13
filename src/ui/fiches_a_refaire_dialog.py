"""
Fiches du site à refaire depuis les PDF (CDC docs/cdc_import_fiches_site.md, § 10.14)

Une fiche aux données en vrac (nom mêlé d'une description, n° d'article collé,
mot coupé, en-tête de série pris pour une marque…) n'a pas créé ses appareils
bancals. Elle est listée ici avec la référence de sa pièce : cherchez ses PDF et
importez-les. Un import PDF, CSV ou collage de la référence la retire de la liste
(ImportManager._solder_fiches_a_refaire) ; « Fait » la retire à la main.

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import csv
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.enregistrement_fiche_service import lien_produit
from src.utils.boites import choisir_fichier_a_enregistrer
from .style_manager import StyleManager

_COLONNES = ("Réf. de la pièce", "N° du produit", "Pourquoi", "Exemples", "Relevée le")




def ecrire_csv(chemin: str, fiches: List[dict]) -> None:
    """Liste des fiches à refaire, pour chercher les PDF hors de l'outil."""
    with open(chemin, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(["ref_piece", "id_produit", "lien", "en_vrac", "appareils_non_crees",
                    "appareils_a_creer", "raison", "exemples", "releve_le"])
        for x in fiches:
            w.writerow([x['ref_piece'], x['id_product'] or '',
                        lien_produit(x['id_product']) if x['id_product'] else '',
                        'oui' if x['en_vrac'] else 'non', x['retenues'], x['creations'],
                        x['raison'], (x['exemples'] or '').replace('\n', ' | '),
                        (x['releve_le'] or '').replace('T', ' ')])


class FichesARefaireDialog(QDialog):
    """Liste des fiches du site à refaire depuis les PDF."""

    def __init__(self, db_manager, parent=None, on_change: Optional[Callable] = None):
        super().__init__(parent)
        self.db = db_manager
        self.on_change = on_change
        self.setWindowTitle("Fiches du site à refaire depuis les PDF")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1040, 520)
        self.fiches: List[dict] = []
        self._construire()
        self.charger()

    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)
        aide = QLabel("Ces fiches du site ont des données en vrac : leurs appareils connus ont été "
                      "reliés, mais les appareils bancals n'ont pas été créés. Cherchez les PDF de la "
                      "pièce et importez-les : la fiche sort de la liste d'elle-même.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.BANDEAU_INFO)
        racine.addWidget(aide)
        self.table = QTableWidget(0, len(_COLONNES))
        self.table.setHorizontalHeaderLabels(_COLONNES)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._activer)
        self.table.cellDoubleClicked.connect(lambda *_: self.ouvrir_page())
        racine.addWidget(self.table, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_page = QPushButton(qta.icon('fa5s.globe', color='#555555'), "Ouvrir la page du site")
        self.bouton_page.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_page.clicked.connect(self.ouvrir_page)
        self.bouton_fait = QPushButton(qta.icon('fa5s.check', color='#555555'), "Fait")
        self.bouton_fait.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_fait.setToolTip("Retire les fiches sélectionnées de la liste (fiche refaite).")
        self.bouton_fait.clicked.connect(self.marquer_faites)
        self.bouton_csv = QPushButton(qta.icon('fa5s.file-csv', color='#555555'), "Exporter en CSV…")
        self.bouton_csv.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_csv.clicked.connect(self._exporter)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        for b in (self.bouton_page, self.bouton_fait, self.bouton_csv, fermer):
            pied.addWidget(b)
        racine.addLayout(pied)

    def charger(self):
        self.fiches = self.db.fiches_a_refaire()
        self.table.setRowCount(len(self.fiches))
        for ligne, x in enumerate(self.fiches):
            valeurs = (x['ref_piece'], str(x['id_product'] or ''), x['raison'] or '',
                       (x['exemples'] or '').split('\n')[0], (x['releve_le'] or '').replace('T', ' '))
            for col, valeur in enumerate(valeurs):
                item = QTableWidgetItem(valeur)
                if col == 3:
                    item.setToolTip(x['exemples'] or '')
                self.table.setItem(ligne, col, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(self.table.columnWidth(2), 360))
        en_vrac = sum(1 for x in self.fiches if x['en_vrac'])
        self.etat.setText(f"{len(self.fiches)} fiche(s) à refaire, dont {en_vrac} en vrac "
                          f"(aucun appareil créé)" if self.fiches else "Aucune fiche à refaire.")
        self._activer()

    def _selection(self) -> List[dict]:
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.fiches[i] for i in lignes if i < len(self.fiches)]

    def _activer(self):
        selection = self._selection()
        self.bouton_fait.setEnabled(bool(selection))
        self.bouton_page.setEnabled(any(x['id_product'] for x in selection))
        self.bouton_csv.setEnabled(bool(self.fiches))

    def ouvrir_page(self):
        for x in self._selection()[:5]:
            if x['id_product']:
                QDesktopServices.openUrl(QUrl(lien_produit(x['id_product'])))

    def marquer_faites(self):
        refs = [x['ref_piece'] for x in self._selection()]
        if refs:
            self.db.retirer_fiches_a_refaire(refs)
            app_logger.info(f"[Fiches à refaire] faites : {', '.join(refs)}")
            self.charger()
            if self.on_change is not None:
                self.on_change()

    def _exporter(self):
        choisir_fichier_a_enregistrer(self, "Exporter les fiches à refaire", "fiches_a_refaire.csv",
                                      "Fichiers CSV (*.csv)", self.exporter)

    def exporter(self, chemin: str):
        try:
            ecrire_csv(chemin, self.fiches)
            self.etat.setText(f"Liste exportée : {chemin}")
        except OSError as e:
            self.etat.setText(f"Export impossible : {e}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
