"""
Barre d'état dont les messages temporaires ne masquent pas les widgets de gauche.

QStatusBar.showMessage() masque tous les widgets « normaux » (zone gauche)
pendant l'affichage du message. Or le groupe « ▲ [n incomplètes] ▼ » vit à
gauche, sous le tableau, et l'application affiche des messages en permanence
(« N lignes chargées » après chaque chargement) : il disparaîtrait 2 s après
chaque saut. Ici, les messages sont écrits dans un libellé placé APRÈS les
widgets de tête — les ~36 appels à showMessage() restent inchangés.
"""

from ..utils.qt_imports import QStatusBar, QLabel, QTimer, QSizePolicy


class MessageStatusBar(QStatusBar):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._message_label = QLabel()
        # Ignored : un message long est tronqué au lieu d'élargir la fenêtre
        self._message_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._message_label.setContentsMargins(4, 0, 0, 0)
        self.addWidget(self._message_label, 1)

        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self.clearMessage)

    def add_leading_widget(self, widget):
        """Widget toujours visible en tête de barre (à gauche, sous le tableau),
        avant la zone des messages."""
        self.insertWidget(0, widget)

    # ── API QStatusBar redéfinie ──────────────────────────────────────────────

    def showMessage(self, message: str, timeout: int = 0):
        self._message_timer.stop()
        self._message_label.setText(message)
        if timeout > 0:
            self._message_timer.start(timeout)
        self.messageChanged.emit(message)

    def clearMessage(self):
        self._message_timer.stop()
        if self._message_label.text():
            self._message_label.clear()
            self.messageChanged.emit("")

    def currentMessage(self) -> str:
        return self._message_label.text()
