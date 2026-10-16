"""
Saisie de plusieurs références de pièces sous forme de pastilles.

- `RefSaisieLineEdit` : champ qui transforme sa saisie en références dès
  l'espace, l'Entrée, un choix dans la complétion ou un collage contenant des
  espaces, et les émet par `refs_saisies(list)`. Réutilisé tel quel par les
  cadres de relations de l'import multi-fichiers (import_relations_panel.py).
- `RefChipsInput` : ce champ + les pastilles des réfs déjà saisies (✕ pour en
  retirer une, Retour arrière dans le champ vide retire la dernière). Sert aux
  champs « Succession » de l'import d'un seul fichier.

Les pastilles reprennent le style des réfs de l'import multi-fichiers
(`_RefList` : badge blanc arrondi).
"""

from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QTimer
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton,
)

from ..utils.text_utils import decouper_refs
from .flow_layout import FlowLayout

# Style des pastilles : identique aux réfs du réservoir multi-fichiers (_RefList)
_STYLE_PASTILLE = ("QFrame#pastilleRef { background: #ffffff; border: 1px solid #cfd8dc;"
                   " border-radius: 10px; }")


class RefSaisieLineEdit(QLineEdit):
    """QLineEdit qui découpe sa saisie en références (séparateur : espace).

    Espace / Entrée / Tab-collage / choix de complétion → `refs_saisies(list)`
    puis le champ se vide. L'Entrée n'est consommée que si le champ contient du
    texte : un champ vide la laisse passer (bouton par défaut du dialogue).
    """
    refs_saisies = pyqtSignal(list)
    retour_arriere_vide = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self._sur_texte_change)

    def setCompleter(self, completer):
        super().setCompleter(completer)
        if completer is not None:
            # Différé : QLineEdit recopie la complétion dans le champ via sa propre
            # connexion ; on valide une fois ce texte en place.
            completer.activated[str].connect(
                lambda *_: QTimer.singleShot(0, self.valider_saisie))

    def valider_saisie(self):
        """Transformer le texte en cours en références. Renvoie la liste émise."""
        refs = decouper_refs(self.text())
        if refs:
            self.blockSignals(True)
            self.clear()
            self.blockSignals(False)
            self.refs_saisies.emit(refs)
        return refs

    def _sur_texte_change(self, texte):
        # Collage contenant des espaces (ou des retours à la ligne)
        if texte and any(c.isspace() for c in texte.strip()):
            self.valider_saisie()

    def keyPressEvent(self, event):
        key = event.key()
        popup = self.completer().popup() if self.completer() is not None else None
        popup_visible = popup is not None and popup.isVisible()
        if key == Qt.Key_Space and not popup_visible:
            self.valider_saisie()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not popup_visible and self.text().strip():
            self.valider_saisie()
            event.accept()
            return
        if key == Qt.Key_Backspace and not self.text():
            self.retour_arriere_vide.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # Ne rien laisser en suspens si l'utilisateur quitte le champ sans espace
        # (sauf vers le popup de complétion, qui prend le focus un instant).
        popup = self.completer().popup() if self.completer() is not None else None
        if popup is None or not popup.isVisible():
            self.valider_saisie()
        super().focusOutEvent(event)


class _PastilleRef(QFrame):
    """Une référence saisie : texte + bouton ✕."""
    retrait_demande = pyqtSignal(str)

    def __init__(self, ref, parent=None):
        super().__init__(parent)
        self.ref = ref
        self.setObjectName("pastilleRef")
        self.setStyleSheet(_STYLE_PASTILLE)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 1, 3, 1)
        lay.setSpacing(2)
        lbl = QLabel(ref)
        lbl.setStyleSheet("border: none; background: transparent; color: #263238;")
        lay.addWidget(lbl)
        btn = QToolButton()
        btn.setText("✕")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(f"Retirer {ref}")
        btn.setAutoRaise(True)
        btn.setStyleSheet("QToolButton { border: none; background: transparent;"
                          " color: #90a4ae; font-size: 10px; padding: 0 2px; }"
                          "QToolButton:hover { color: #c0392b; }")
        btn.clicked.connect(lambda: self.retrait_demande.emit(self.ref))
        lay.addWidget(btn)


class RefChipsInput(QFrame):
    """Champ de saisie de références multiples, affichées en pastilles.

    Args:
        placeholder: texte d'aide du champ (affiché tant qu'aucune réf n'est saisie).
        max_refs: nombre maximal de réfs (None = illimité). Atteint, le champ se
            masque ; retirer une pastille le fait réapparaître.
    """
    changed = pyqtSignal()

    def __init__(self, placeholder="", max_refs=None, parent=None):
        super().__init__(parent)
        self._refs = []
        self._max = max_refs
        self._placeholder = placeholder
        self.setObjectName("refChipsInput")
        self.setStyleSheet("QFrame#refChipsInput { background: white; border: 1px solid #ced4da;"
                           " border-radius: 4px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(3)

        self._zone_pastilles = QWidget()
        self._zone_pastilles.setStyleSheet("background: transparent; border: none;")
        self._flow = FlowLayout(self._zone_pastilles, spacing=4)
        self._zone_pastilles.setVisible(False)
        lay.addWidget(self._zone_pastilles)

        self.line_edit = RefSaisieLineEdit()
        self.line_edit.setMinimumHeight(22)
        self.line_edit.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 2px 2px; }")
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.refs_saisies.connect(self.add_refs)
        self.line_edit.retour_arriere_vide.connect(self._retirer_derniere)
        lay.addWidget(self.line_edit)

        # Clic dans le cadre (hors champ) → focus dans le champ
        self.setCursor(Qt.IBeamCursor)

    # ── API ─────────────────────────────────────────────────────────────────

    def refs(self):
        """Réfs saisies, y compris le texte tapé mais pas encore validé (aucune
        perte si l'utilisateur clique « Importer » sans appuyer sur Espace)."""
        refs = list(self._refs)
        for r in decouper_refs(self.line_edit.text()):
            if r not in refs and (self._max is None or len(refs) < self._max):
                refs.append(r)
        return refs

    def add_refs(self, refs):
        ajout = False
        for r in decouper_refs(refs):
            if r in self._refs:
                continue
            if self._max is not None and len(self._refs) >= self._max:
                break
            self._refs.append(r)
            ajout = True
        if ajout:
            self._reconstruire()
            self.changed.emit()

    def set_refs(self, refs):
        self._refs = []
        self.line_edit.clear()
        self.add_refs(refs)
        self._reconstruire()

    def remove_ref(self, ref):
        if ref in self._refs:
            self._refs.remove(ref)
            self._reconstruire()
            self.changed.emit()

    def setCompleter(self, completer):
        self.line_edit.setCompleter(completer)

    def text(self):
        """Compatibilité avec l'ancien QLineEdit : réfs séparées par un espace."""
        return " ".join(self.refs())

    # ── Interne ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self.line_edit.isVisible():
            self.line_edit.setFocus()
        super().mousePressEvent(event)

    def _retirer_derniere(self):
        if self._refs:
            self.remove_ref(self._refs[-1])

    def _reconstruire(self):
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for r in self._refs:
            p = _PastilleRef(r)
            p.retrait_demande.connect(self.remove_ref)
            self._flow.addWidget(p)
        self._zone_pastilles.setVisible(bool(self._refs))
        plein = self._max is not None and len(self._refs) >= self._max
        self.line_edit.setVisible(not plein)
        self.line_edit.setPlaceholderText("" if self._refs else self._placeholder)
        self._zone_pastilles.updateGeometry()
        self.updateGeometry()
