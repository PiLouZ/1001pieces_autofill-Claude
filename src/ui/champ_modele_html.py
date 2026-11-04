"""
Champ de saisie d'un modèle HTML (configuration des exports, v3.99.2)

Remplace un QLineEdit là où les modèles sont longs (code englobant de
143 caractères : plus de la moitié cachée). Zone qui passe à la ligne et
s'agrandit avec son contenu, de 1 à MAX_LIGNES lignes, puis défile ; police à
chasse fixe.

Code coloré (balises, attributs, valeurs, entités, {variables}) et indenté À
L'ÉCRAN : passage à la ligne là où deux balises de bloc se touchent (« >< »),
avec retrait selon l'imbrication ; pas entre deux balises de mise en forme
(<b><u>…</u></b> reste sur une ligne). Le modèle enregistré reste sur UNE ligne logique,
identique au caractère près : text() retire exactement les sauts de ligne et
retraits ajoutés. C'est sûr parce qu'un modèle enregistré ne contient jamais de
saut de ligne (un collage multi-ligne est mis bout à bout).

Entrée ne passe à la ligne qu'entre deux balises (« >|< ») : ailleurs, le saut
de ligne disparaîtrait à l'enregistrement avec l'espace qui le suit. En
quittant la zone, l'indentation est refaite.

Même interface que QLineEdit pour l'usage qu'en fait le dialogue : text(),
setText(), insert() (puces de variables), textChanged, setPlaceholderText().
"""

import re

from .qt_imports import (QPlainTextEdit, QFrame, QFontDatabase, QTextOption, QSizePolicy, Qt,
                         QSyntaxHighlighter, QTextCharFormat, QColor, QFont)


# Balises sans fermeture : n'augmentent pas l'indentation
_BALISES_VIDES = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                  'link', 'meta', 'source', 'track', 'wbr'}
# Balises de mise en forme : restent sur la ligne de leur bloc (<b><u>…</u></b>)
_BALISES_EN_LIGNE = {'a', 'abbr', 'b', 'em', 'i', 'small', 'span', 'strong', 'sub', 'sup', 'u'}
_BALISE = re.compile(r'<(/?)([A-Za-z][\w:-]*)[^>]*?(/?)>')
_NOM_AVANT = re.compile(r'<\/?([A-Za-z][\w:-]*)[^<>]*>$')
_NOM_APRES = re.compile(r'^<\/?([A-Za-z][\w:-]*)')
_RETRAIT = "  "


def _coupure_entre_blocs(avant: str, apres: str) -> bool:
    """Passer à la ligne entre deux balises qui se touchent, sauf entre deux
    balises de mise en forme (<b><u>, </u></b>)."""
    m_avant, m_apres = _NOM_AVANT.search(avant), _NOM_APRES.match(apres)
    return not (m_avant and m_apres
                and m_avant.group(1).lower() in _BALISES_EN_LIGNE
                and m_apres.group(1).lower() in _BALISES_EN_LIGNE)


def formater_html(texte: str) -> str:
    """Affichage indenté d'un modèle sur une ligne : saut de ligne entre deux
    balises de bloc qui se touchent, retrait de deux espaces par niveau."""
    morceaux, debut = [], 0
    for m in re.finditer(r'>(?=<)', texte):
        if _coupure_entre_blocs(texte[debut:m.end()], texte[m.end():]):
            morceaux.append(texte[debut:m.end()])
            debut = m.end()
    segments = morceaux + [texte[debut:]]
    lignes = []
    profondeur = 0
    for segment in segments:
        ouvertures = 0
        for fermeture, nom, auto in _BALISE.findall(segment):
            if fermeture:
                ouvertures -= 1
            elif not auto and nom.lower() not in _BALISES_VIDES:
                ouvertures += 1
        if segment.startswith('</'):
            profondeur = max(0, profondeur - 1)
            ouvertures += 1
        lignes.append(_RETRAIT * profondeur + segment if lignes else segment)
        profondeur = max(0, profondeur + ouvertures)
    return '\n'.join(lignes)


def compacter_html(texte: str) -> str:
    """Inverse de formater_html : retire chaque saut de ligne et le retrait qui suit."""
    return re.sub(r'\r?\n[ \t]*', '', texte)


class ColorationHtml(QSyntaxHighlighter):
    """Couleurs d'un modèle HTML ; les {variables} ressortent sur fond jaune."""

    def __init__(self, document):
        super().__init__(document)

        def fmt(couleur, gras=False, fond=None):
            f = QTextCharFormat()
            f.setForeground(QColor(couleur))
            if gras:
                f.setFontWeight(QFont.Bold)
            if fond:
                f.setBackground(QColor(fond))
            return f

        self._balise = fmt('#0550ae')
        self._attribut = fmt('#953800')
        self._valeur = fmt('#116329')
        self._entite = fmt('#8250df')
        self._variable = fmt('#9a3412', gras=True, fond='#fff3bf')

    def highlightBlock(self, texte):
        for m in re.finditer(r'<[^>]*>?', texte):
            debut = m.start()
            self.setFormat(debut, len(m.group()), self._balise)
            for a in re.finditer(r'\s([\w:-]+)(?==)', m.group()):
                self.setFormat(debut + a.start(1), len(a.group(1)), self._attribut)
            for v in re.finditer(r'"[^"]*"?|\'[^\']*\'?', m.group()):
                self.setFormat(debut + v.start(), len(v.group()), self._valeur)
        for m in re.finditer(r'&#?\w+;', texte):
            self.setFormat(m.start(), len(m.group()), self._entite)
        for m in re.finditer(r'\{\w+\}', texte):
            self.setFormat(m.start(), len(m.group()), self._variable)


class ChampModeleHtml(QPlainTextEdit):
    """Zone de modèle HTML sur une ligne logique, colorée et indentée à l'écran."""

    MAX_LIGNES = 8

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
        self._coloration = ColorationHtml(self.document())
        self.textChanged.connect(self._ajuster_hauteur)
        self._ajuster_hauteur()

    # ─── Interface QLineEdit ─────────────────────────────────────────────────

    def text(self) -> str:
        return compacter_html(self.toPlainText())

    def setText(self, texte: str) -> None:
        self.setPlainText(formater_html(self._une_ligne(texte or "")))

    def insert(self, texte: str) -> None:
        self.insertPlainText(self._une_ligne(texte))

    # ─── Une seule ligne logique ─────────────────────────────────────────────

    @staticmethod
    def _une_ligne(texte: str) -> str:
        # Saut de ligne entre deux balises (HTML collé indenté) : retiré avec
        # son retrait ; ailleurs, comme QLineEdit au collage : une espace
        texte = re.sub(r'>[ \t]*(?:\r?\n[ \t]*)+<', '><', texte)
        return texte.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            # Passage à la ligne seulement entre deux balises (« >|< »)
            curseur = self.textCursor()
            if not curseur.hasSelection():
                texte = self.toPlainText()
                pos = curseur.position()
                if 0 < pos < len(texte) and texte[pos - 1] == '>' and texte[pos] == '<':
                    self.insertPlainText("\n")
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(self._une_ligne(source.text()))

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Indentation refaite en quittant la zone (le texte enregistré ne change pas)
        affiche = formater_html(self.text())
        if affiche != self.toPlainText():
            self.setPlainText(affiche)

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
