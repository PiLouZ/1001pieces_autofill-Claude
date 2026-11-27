"""
« Mettre à jour la fiche n° … » : une fiche déjà en ligne, mise à jour bloc par bloc
depuis la fiche préparée par l'outil (src/ui/agora_fiche.py).

Avant / après pour chaque bloc (nom, description, métas, prix, catégorie) ; seuls
les blocs cochés sont écrits, les autres restent tels qu'ils sont sur le site
(retouches du back-office comprises). La fiche est relue juste avant l'écriture.
Jamais de changement d'activation, d'URL, d'images ni de stock.
Non bloquant : show() + callbacks, threads pour le réseau (conventions du projet).
"""

from typing import Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from src.core.logger import app_logger
from .style_manager import StyleManager

A_COCHER_SOI_MEME = ('nom', 'description')


class MiseAJourFicheDialog(QDialog):
    def __init__(self, parent, site, id_produit: int, fiche, id_categorie: Optional[int],
                 historique=None):
        super().__init__(parent)
        self.site, self.id_produit, self.fiche, self.id_categorie = site, id_produit, fiche, id_categorie
        self.historique = historique
        self.cases: Dict[str, QCheckBox] = {}
        env = site.client.environnement
        self.setWindowTitle(f"Mettre à jour la fiche n° {id_produit} ({env}) — {fiche.code}")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1000, 640)
        racine = QVBoxLayout(self)
        aide = QLabel("Cochez les blocs à remplacer par la version de l'outil. Les blocs décochés restent "
                      "tels qu'ils sont sur le site. L'activation, l'adresse de la page, les images et le stock "
                      "ne sont jamais modifiés.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(aide)
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.contenu = QWidget()
        self.grille = QGridLayout(self.contenu)
        self.grille.addWidget(QLabel("<b>Sur le site</b>"), 0, 1)
        self.grille.addWidget(QLabel("<b>Version de l'outil</b>"), 0, 2)
        self.zone.setWidget(self.contenu)
        racine.addWidget(self.zone, 1)
        pied = QHBoxLayout()
        self.etat = QLabel("Lecture de la fiche en ligne…")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        pied.addWidget(self.etat, 1)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        self.bouton = QPushButton("Mettre à jour")
        self.bouton.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton.setEnabled(False)
        self.bouton.clicked.connect(self.mettre_a_jour)
        pied.addWidget(fermer)
        pied.addWidget(self.bouton)
        racine.addLayout(pied)
        from .agora_fiche import lancer_tache
        lancer_tache(lambda: site.comparer_fiche(id_produit, fiche), self._compare, self)

    @staticmethod
    def _texte(contenu: str, hauteur: int) -> QPlainTextEdit:
        zone = QPlainTextEdit(contenu)
        zone.setReadOnly(True)
        zone.setFixedHeight(hauteur)
        return zone

    def _compare(self, blocs, erreur: str):
        if erreur:
            self.etat.setText(f"Fiche en ligne illisible : {erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        for i, b in enumerate(blocs, start=1):
            case = QCheckBox(b.libelle)
            # Nom et description, les plus souvent retouchés dans le back-office : à cocher
            # soi-même ; les autres blocs modifiés sont cochés d'office
            case.setChecked(b.different and b.cle not in A_COCHER_SOI_MEME)
            case.setEnabled(b.different)
            if not b.different:
                case.setText(f"{b.libelle} (identique)")
            case.toggled.connect(self._maj_bouton)
            self.cases[b.cle] = case
            hauteur = 160 if b.cle == 'description' else 56
            self.grille.addWidget(case, i, 0, Qt.AlignTop)
            self.grille.addWidget(self._texte(b.avant, hauteur), i, 1)
            self.grille.addWidget(self._texte(b.apres, hauteur), i, 2)
        self.grille.setRowStretch(len(blocs) + 1, 1)
        if 'categorie' in self.cases and not self.id_categorie:
            self.cases['categorie'].setChecked(False)
            self.cases['categorie'].setEnabled(False)
            self.cases['categorie'].setText("Catégorie (inconnue du site)")
        self.etat.setText("Fiche en ligne relue." if any(b.different for b in blocs)
                          else "La fiche en ligne est identique à celle de l'outil.")
        self._maj_bouton()

    def _choisis(self):
        return [cle for cle, case in self.cases.items() if case.isChecked() and case.isEnabled()]

    def _maj_bouton(self, *_):
        n = len(self._choisis())
        self.bouton.setEnabled(n > 0)
        self.bouton.setText(f"Mettre à jour ({n} bloc{'s' if n > 1 else ''})" if n else "Mettre à jour")

    def mettre_a_jour(self):
        blocs = self._choisis()
        if not blocs:
            return
        if self.site.client.environnement == 'production':
            from src.utils.boites import demander_oui_non
            demander_oui_non(self, "Mettre à jour une fiche en production",
                             f"Remplacer {len(blocs)} bloc(s) de la fiche n° {self.id_produit} sur www.1001pieces.com ?",
                             lambda: self._ecrire(blocs))
        else:
            self._ecrire(blocs)

    def _ecrire(self, blocs):
        from .agora_fiche import lancer_tache
        self.bouton.setEnabled(False)
        self.etat.setText("Mise à jour…")
        site, ident, fiche, cat = self.site, self.id_produit, self.fiche, self.id_categorie
        lancer_tache(lambda: site.mettre_a_jour_fiche(ident, fiche, blocs, cat), self._ecrit, self)

    def _ecrit(self, ecrits, erreur: str):
        env = self.site.client.environnement
        if erreur:
            app_logger.warning(f"[Site] mise à jour du produit n° {self.id_produit} refusée : {erreur}")
            self.etat.setText(f"Mise à jour refusée : {erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            self._maj_bouton()
            return
        libelles = dict((c, case.text()) for c, case in self.cases.items())
        resume = ', '.join(libelles.get(b, b) for b in ecrits)
        self.etat.setText(f"Fiche n° {self.id_produit} ({env}) mise à jour : {resume}.")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton.setText("Mise à jour faite")
        if self.historique is not None:
            self.historique(f"Fiche mise à jour sur PrestaShop ({env}) : {self.fiche.code}, "
                            f"produit n° {self.id_produit}\n==> {resume}")
