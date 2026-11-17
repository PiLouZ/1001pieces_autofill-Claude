"""
Saisie directe d'une relation dans une carte du gestionnaire de pièces
(≡ Équivalences, ↑ Remplace, ↳ Remplacée par), sans ouvrir de fenêtre.

Le champ de l'import (`RefSaisieLineEdit`) : Espace, Entrée, un choix dans la
complétion ou un collage de plusieurs réfs les valide ; la fenêtre les écrit
aussitôt et elles apparaissent dans les puces de la carte. Quitter le champ ne
valide rien (une réf. tapée à moitié n'est jamais écrite). Sous le champ, une
ligne d'état dit ce qui a été fait, ou l'erreur en rouge.
"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from .ref_chips_input import RefSaisieLineEdit
from .style_manager import StyleManager

AIDE_SAISIE = ("Espace ou Entrée : ajoute la réf. Collez une liste pour en ajouter "
               "plusieurs. Réf. inconnue : créée en fantôme.")


class SaisieRelation(QWidget):
    """Champ de saisie + ligne d'état d'une carte de relations."""

    refs_saisies = pyqtSignal(list)

    def __init__(self, aide: str, parent=None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(1)
        self.champ = RefSaisieLineEdit(valider_en_sortant=False)
        self.champ.setPlaceholderText(aide)
        self.champ.setToolTip(AIDE_SAISIE)
        self.champ.setStyleSheet(StyleManager.SAISIE_RELATION)
        self.champ.refs_saisies.connect(self.refs_saisies)
        disposition.addWidget(self.champ)
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setVisible(False)
        disposition.addWidget(self.etat)

    # --- Champ ----------------------------------------------------------------------
    def definir_aide(self, aide: str, infobulle: str = AIDE_SAISIE):
        self.champ.setPlaceholderText(aide)
        self.champ.setToolTip(infobulle)

    def activer(self, actif: bool, infobulle: str = AIDE_SAISIE):
        self.champ.setEnabled(actif)
        self.champ.setToolTip(infobulle)

    def setCompleter(self, completer):
        self.champ.setCompleter(completer)

    def texte_en_cours(self) -> str:
        return self.champ.text().strip()

    def vider(self):
        self.champ.clear()

    # --- Ligne d'état ---------------------------------------------------------------
    def afficher_bilan(self, ajoutees: list, erreurs: list, fantomes: list):
        """« ✓ 2 ajoutées · X91 créée (fantôme) », ou les erreurs en rouge."""
        if erreurs:
            self.etat.setText("\n".join(erreurs))
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_PETIT)
        elif ajoutees:
            texte = f"✓ {len(ajoutees)} ajoutée{'s' if len(ajoutees) > 1 else ''}"
            if fantomes:
                texte += " · " + ", ".join(fantomes) + (" créées" if len(fantomes) > 1
                                                        else " créée") + " (fantôme)"
            self.etat.setText(texte)
            self.etat.setStyleSheet(StyleManager.SAISIE_RELATION_BILAN)
        else:
            self.effacer_etat()
            return
        self.etat.setVisible(True)

    def effacer_etat(self):
        self.etat.setText("")
        self.etat.setVisible(False)
