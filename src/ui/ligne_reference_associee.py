"""
Ligne « Réf. associée » du gestionnaire de pièces, en tête de la carte
« ≡ Équivalences » : la jumelle Whirlpool / Indesit / Beko de la pièce affichée
(la même notion que le champ « Réf. associée » de l'import).

Quatre états, la fenêtre choisit lequel afficher (`afficher`) :
- JUMELLE  : la paire, principale d'abord (ordre du code produit), chaque réf.
             avec son rôle ; la pièce affichée est grisée « (cette pièce) » ;
             clic sur la jumelle = recherche, ⇄ inverse les rôles, ✕ retire ;
- PROPOSEE : l'équivalente de code produit d'une fiche reprise, pas encore
             confirmée — ✓ confirme, ✕ refuse ;
- AUCUNE   : « aucune » mémorisée — ✕ oublie la réponse ;
- VIDE     : rien de connu — + choisit, « Aucune » mémorise l'absence.
Le widget n'écrit rien : il émet un signal, la fenêtre agit.
"""

from typing import Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)
import qtawesome as qta

from .style_manager import StyleManager

JUMELLE, PROPOSEE, AUCUNE, VIDE = 'jumelle', 'proposee', 'aucune', 'vide'

_VIOLET = '#8e44ad'


class LigneReferenceAssociee(QWidget):
    """Réf. associée de la pièce affichée, avec ses actions."""

    ajouter = pyqtSignal()
    retirer = pyqtSignal()
    inverser = pyqtSignal()
    confirmer = pyqtSignal()
    refuser = pyqtSignal()
    marquer_aucune = pyqtSignal()
    oublier_aucune = pyqtSignal()
    ref_clicked = pyqtSignal(str)
    ref_right_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.etat: Optional[str] = None
        self.reference = ''
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 2)
        disposition.setSpacing(1)

        self.titre = QLabel("Réf. associée :")
        self.titre.setStyleSheet(StyleManager.REF_ASSOCIEE_TITRE)
        disposition.addWidget(self.titre)

        # Une ou deux lignes (la paire) ; `_ligne` = disposition de la ligne en cours
        self._contenu = QWidget()
        self._contenu.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._lignes = QVBoxLayout(self._contenu)
        self._lignes.setContentsMargins(0, 0, 0, 0)
        self._lignes.setSpacing(0)
        self._ligne: Optional[QHBoxLayout] = None
        disposition.addWidget(self._contenu)

        trait = QFrame()
        trait.setFrameShape(QFrame.HLine)
        trait.setStyleSheet(StyleManager.REF_ASSOCIEE_TRAIT)
        disposition.addWidget(trait)
        self.setVisible(False)

    # --- Affichage ------------------------------------------------------------------
    def masquer(self):
        self.etat, self.reference = None, ''
        self.setVisible(False)

    def afficher(self, etat: str, origine: str, autres: str, reference: str = '',
                 libelle: str = '', role: str = '', piece: str = ''):
        """`origine` : groupe de la pièce affichée (« Whirlpool ») ; `autres` :
        « Indesit ou Beko ». JUMELLE : `piece` = la pièce affichée, `role` = son
        rôle (« principale » / « associée »), `reference` = sa jumelle."""
        self.etat, self.reference = etat, reference or ''
        self._vider()
        self.titre.setText("Réf. associées" if etat == JUMELLE else "Réf. associée :")
        self.titre.setToolTip(f"Référence jumelle {autres} de cette pièce {origine}. "
                              f"La principale vient en premier dans le code produit de la "
                              f"Fiche complète, l'associée à sa suite.")
        self._nouvelle_ligne()
        if etat == JUMELLE:
            # Principale d'abord : l'ordre du code produit
            if role == "principale":
                self._ligne_piece("Principale", piece)
                self._nouvelle_ligne()
                self._ligne_jumelle("Associée", reference, libelle)
            else:
                self._ligne_jumelle("Principale", reference, libelle)
                self._nouvelle_ligne()
                self._ligne_piece("Associée", piece)
        elif etat == PROPOSEE:
            self._puce(reference, libelle, italique=True,
                       aide="Proposée par la fiche du site (2ᵉ réf. du code produit)")
            self._bouton('fa5s.check', "Confirmer : c'est bien la réf. associée", self.confirmer,
                         couleur='#2e7d32')
            self._croix("Ce n'est pas la réf. associée (elle reste équivalente)", self.refuser)
        elif etat == AUCUNE:
            self._texte("aucune (l'import ne la demandera plus)")
            self._ligne.addStretch(1)
            self._croix("Oublier la réponse : l'import redemandera la réf. associée",
                        self.oublier_aucune)
        else:
            self._texte("non renseignée")
            self._ligne.addStretch(1)
            self._bouton('fa5s.plus', "Choisir la réf. associée", self.ajouter)
            lien = QPushButton("Aucune")
            lien.setStyleSheet(StyleManager.REF_ASSOCIEE_LIEN)
            lien.setCursor(Qt.PointingHandCursor)
            lien.setToolTip("Cette pièce n'a pas de jumelle : l'import ne la demandera plus")
            lien.clicked.connect(lambda *_: self.marquer_aucune.emit())
            self._ligne.addWidget(lien)
        self.setVisible(True)

    # --- Briques --------------------------------------------------------------------
    def _vider(self):
        while self._lignes.count():
            item = self._lignes.takeAt(0)
            if item.widget():
                item.widget().hide()            # pas de reste visible avant la suppression
                item.widget().deleteLater()
        self._ligne = None

    def _nouvelle_ligne(self):
        ligne = QWidget()
        ligne.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._ligne = QHBoxLayout(ligne)
        self._ligne.setContentsMargins(8, 0, 6, 0)
        self._ligne.setSpacing(6)
        self._lignes.addWidget(ligne)

    def _role(self, role: str):
        lbl = QLabel(role)
        lbl.setStyleSheet(StyleManager.REF_ASSOCIEE_ROLE)
        lbl.setFixedWidth(62)
        self._ligne.addWidget(lbl)

    def _ligne_piece(self, role: str, piece: str):
        """La pièce affichée : grisée, non cliquable (on est déjà dessus)."""
        self._role(role)
        lbl = QLabel(f"{piece} <span style='font-family: sans-serif; font-weight: normal;"
                     f" font-style: italic'>(cette pièce)</span>")
        lbl.setStyleSheet(StyleManager.REF_ASSOCIEE_PIECE)
        self._ligne.addWidget(lbl)
        self._ligne.addStretch(1)

    def _ligne_jumelle(self, role: str, reference: str, libelle: str):
        self._role(role)
        self._puce(reference, libelle, italique=False)
        self._bouton('fa5s.exchange-alt', "Inverser : la principale devient l'associée et "
                     "inversement (la principale vient en premier dans le code produit)",
                     self.inverser)
        self._croix("Retirer la réf. associée (l'équivalence est conservée)", self.retirer)

    def _puce(self, reference: str, libelle: str, italique: bool, aide: str = ''):
        style = StyleManager.ref_associee_puce(_VIOLET, italique)
        ref_lbl = QLabel(reference)
        ref_lbl.setStyleSheet(style)
        # Jamais rognée par le libellé : largeur mesurée une fois le style (gras,
        # monospace) appliqué, sinon elle l'est avec la police par défaut
        ref_lbl.ensurePolished()
        ref_lbl.setMinimumWidth(ref_lbl.sizeHint().width() + 2)
        ref_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        ref_lbl.setCursor(Qt.PointingHandCursor)
        ref_lbl.setToolTip(aide or f"Cliquer pour rechercher '{reference}'")

        def _clic(event, r=reference):
            if event.button() == Qt.LeftButton:
                self.ref_clicked.emit(r)
            elif event.button() == Qt.RightButton:
                self.ref_right_clicked.emit(r)
        ref_lbl.mousePressEvent = _clic
        self._ligne.addWidget(ref_lbl)
        if libelle:
            lib = QLabel(libelle)
            lib.setStyleSheet(StyleManager.LIBELLE_PETIT_GRIS_TRANSPARENT)
            lib.setMaximumWidth(200)
            self._ligne.addWidget(lib, 1)
        else:
            self._ligne.addStretch(1)

    def _texte(self, texte: str):
        lbl = QLabel(texte)
        lbl.setStyleSheet(StyleManager.REF_ASSOCIEE_ETAT)
        self._ligne.addWidget(lbl)

    def _bouton(self, icone: str, aide: str, signal, couleur: str = _VIOLET):
        bouton = QPushButton(qta.icon(icone, color=couleur), '')
        bouton.setIconSize(QSize(11, 11))
        bouton.setStyleSheet(StyleManager.PANEL_ICON_BUTTON)
        bouton.setToolTip(aide)
        bouton.clicked.connect(lambda *_: signal.emit())
        self._ligne.addWidget(bouton)

    def _croix(self, aide: str, signal):
        # Même croix que les puces RefTagList (QLabel : pas de hauteur minimale macOS)
        croix = QLabel("<b>✕</b>")
        croix.setStyleSheet(StyleManager.REF_ASSOCIEE_CROIX)
        croix.setToolTip(aide)
        croix.setCursor(Qt.PointingHandCursor)
        croix.mousePressEvent = lambda event: signal.emit()
        self._ligne.addWidget(croix)
