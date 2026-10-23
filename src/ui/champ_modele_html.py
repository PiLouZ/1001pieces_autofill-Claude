"""
Champ de saisie d'un modèle HTML (configuration des exports, v3.99.2)

Remplace un QLineEdit là où les modèles sont longs (code englobant de
143 caractères : plus de la moitié cachée). Zone qui passe à la ligne et
s'agrandit avec son contenu, de 1 à MAX_LIGNES lignes, puis défile ; police à
chasse fixe. Le texte reste sur UNE ligne logique : Entrée ne fait rien et un
collage multi-ligne est mis bout à bout — les exports restent identiques.

Même interface que QLineEdit pour l'usage qu'en fait le dialogue : text(),
setText(), insert() (puces de variables), textChanged, setPlaceholderText().
"""

from .qt_imports import QPlainTextEdit, QFrame, QFontDatabase, QTextOption, QSizePolicy, Qt


class ChampModeleHtml(QPlainTextEdit):
    """Zone de modèle HTML sur une ligne logique, affichée sur 1 à 4 lignes."""

    MAX_LIGNES = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        # La police passe par la feuille de style : le style global de
        # l'application (font-family sur tous les widgets) l'emporte sur setFont()
        police = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(2)
        # Même habillage que les champs d'une ligne (style global des QLineEdit)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"QPlainTextEdit {{ font-family: '{police}', Menlo, monospace; font-size: 12px;"
            " border: 1px solid #ced4da; border-radius: 4px;"
            " padding: 3px 6px; background-color: white; color: #495057;"
            " selection-background-color: #0d6efd; }"
            "QPlainTextEdit:hover { border-color: #adb5bd; }"
            "QPlainTextEdit:focus { border-color: #80bdff; }"
        )
        self.textChanged.connect(self._ajuster_hauteur)
        self._ajuster_hauteur()

    # ─── Interface QLineEdit ─────────────────────────────────────────────────

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, texte: str) -> None:
        self.setPlainText(self._une_ligne(texte or ""))

    def insert(self, texte: str) -> None:
        self.insertPlainText(self._une_ligne(texte))

    # ─── Une seule ligne logique ─────────────────────────────────────────────

    @staticmethod
    def _une_ligne(texte: str) -> str:
        # Comme QLineEdit au collage : les sauts de ligne deviennent des espaces
        return texte.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(self._une_ligne(source.text()))

    # ─── Hauteur selon le contenu ────────────────────────────────────────────

    def _nb_lignes_affichees(self) -> int:
        lignes = 0
        bloc = self.document().begin()
        while bloc.isValid():
            lignes += max(1, bloc.layout().lineCount())
            bloc = bloc.next()
        return max(1, lignes)

    def _ajuster_hauteur(self) -> None:
        lignes = min(self._nb_lignes_affichees(), self.MAX_LIGNES)
        marges = self.contentsMargins()
        hauteur = (lignes * self.fontMetrics().lineSpacing()
                   + 2 * self.document().documentMargin()
                   + marges.top() + marges.bottom())
        self.setFixedHeight(int(hauteur) + 2)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if self._nb_lignes_affichees() > self.MAX_LIGNES
            else Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # La largeur change le nombre de lignes après retour à la ligne
        self._ajuster_hauteur()
