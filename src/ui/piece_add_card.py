"""
Carte « nouvelle pièce » du panneau des pièces (fenêtre principale).

Remplace l'ancien formulaire empilé (2 champs + bouton « Ajouter » pleine largeur).
Même forme qu'une pièce de la liste : référence en gras, libellé à côté. Indique à
combien d'appareils la pièce sera ajoutée (l'ajout porte sur toute la sélection).

Clavier : Entrée ajoute, Échap annule. La carte se referme après un ajout réussi
(c'est l'appelant qui décide, via close_card) et reste ouverte en cas d'erreur
pour que la saisie ne soit pas perdue.
"""

from PyQt5.QtWidgets import QShortcut
from .qt_imports import (QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
                         QPushButton, QSizePolicy, Qt, QKeySequence)
from .style_manager import StyleManager
from ..core.config import pluralize


class PieceAddCard(QFrame):
    """Carte de saisie d'une nouvelle pièce, masquée par défaut."""

    def __init__(self, on_submit, parent=None):
        """
        Args:
            on_submit: appelé sans argument quand l'utilisateur valide (bouton ou
                       Entrée). Les valeurs se lisent dans ref_input / libelle_input.
        """
        super().__init__(parent)
        self.setObjectName("pieceAddCard")
        self.setStyleSheet(StyleManager.PIECE_ADD_CARD)
        self._on_submit = on_submit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Ligne 1 : référence (gras, comme dans la liste) + libellé
        fields = QHBoxLayout()
        fields.setSpacing(6)
        self.ref_input = QLineEdit()
        self.ref_input.setObjectName("pieceAddRef")
        self.ref_input.setPlaceholderText("Référence")
        self.ref_input.setFixedWidth(130)
        self.ref_input.returnPressed.connect(self._submit)
        fields.addWidget(self.ref_input)

        self.libelle_input = QLineEdit()
        self.libelle_input.setPlaceholderText("Libellé (optionnel)")
        self.libelle_input.returnPressed.connect(self._submit)
        fields.addWidget(self.libelle_input, 1)
        layout.addLayout(fields)

        # Ligne 2 : cible, rappel clavier, actions
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.target_label = QLabel("")
        self.target_label.setObjectName("pieceAddTarget")
        actions.addWidget(self.target_label)

        hint = QLabel("Entrée pour ajouter · Échap pour annuler")
        hint.setObjectName("pieceAddHint")
        # Se rétrécit (texte coupé) plutôt que d'élargir le panneau
        hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        actions.addWidget(hint, 1)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setObjectName("pieceAddCancel")
        cancel_btn.clicked.connect(self.close_card)
        actions.addWidget(cancel_btn)

        add_btn = QPushButton("Ajouter")
        add_btn.setObjectName("pieceAddSubmit")
        add_btn.clicked.connect(self._submit)
        actions.addWidget(add_btn)
        layout.addLayout(actions)

        # Échap : seulement quand le focus est dans la carte
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.setContext(Qt.WidgetWithChildrenShortcut)
        esc.activated.connect(self.close_card)

        self.setVisible(False)

    # ── API ───────────────────────────────────────────────────────────────

    def open_card(self, target_count: int):
        """Afficher la carte, cibles à jour, curseur dans la référence."""
        self.set_target_count(target_count)
        self.setVisible(True)
        self.ref_input.setFocus()

    def close_card(self):
        """Refermer la carte et vider la saisie."""
        self.ref_input.clear()
        self.libelle_input.clear()
        self.setVisible(False)

    def toggle(self, target_count: int):
        """Bouton ＋ : ouvrir, ou refermer si déjà ouverte."""
        if self.isVisible():
            self.close_card()
        else:
            self.open_card(target_count)

    def set_target_count(self, count: int):
        """Mettre à jour la pastille « → N appareils »."""
        self.target_label.setText(f"→ {pluralize(count, 'appareil')}" if count else "Aucun appareil")

    # ── Interne ───────────────────────────────────────────────────────────

    def _submit(self):
        self._on_submit()
