"""
FlowLayout : disposition qui place ses éléments en ligne et passe à la ligne
suivante quand la largeur manque (comme des mots dans un paragraphe).

Adaptation de l'exemple « Flow Layout » de la documentation Qt. Sert aux rangées
de puces (variables d'export…) : une QHBoxLayout les compressait sous leur
taille utile, ce qui coupait leur texte (« xport_ref », « anufactur »).
"""

from PyQt5.QtWidgets import QLayout
from .qt_imports import QRect, QSize, QPoint, Qt


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 4):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    # ── API QLayout ─────────────────────────────────────────────────────────

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._disposer(QRect(0, 0, width, 0), appliquer=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._disposer(rect, appliquer=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    # ── Interne ─────────────────────────────────────────────────────────────

    def _disposer(self, rect, appliquer: bool) -> int:
        """Place les éléments ligne par ligne ; renvoie la hauteur utilisée."""
        m = self.contentsMargins()
        zone = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, hauteur_ligne = zone.x(), zone.y(), 0
        for item in self._items:
            taille = item.sizeHint()
            if x + taille.width() > zone.right() + 1 and hauteur_ligne > 0:
                x = zone.x()
                y += hauteur_ligne + self._spacing
                hauteur_ligne = 0
            if appliquer:
                item.setGeometry(QRect(QPoint(x, y), taille))
            x += taille.width() + self._spacing
            hauteur_ligne = max(hauteur_ligne, taille.height())
        return y + hauteur_ligne - rect.y() + m.bottom()
