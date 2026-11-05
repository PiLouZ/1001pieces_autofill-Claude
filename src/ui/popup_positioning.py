"""
Positionnement des popups contextuels près du curseur.

Extrait de HistoryDetailPopup et PieceRelationsPopup, qui portaient la même
méthode `show_at_cursor` à 21 lignes de code strictement identiques — le
docstring de la première le reconnaissait d'ailleurs : « Même pattern que
PieceRelationsPopup ». Seule l'explication du QTimer.singleShot(0), présente
dans une des deux copies, valait d'être conservée : elle l'est ici.
"""

from ..utils.qt_imports import QApplication, QCursor, QTimer

# Décalage entre le curseur et le coin du popup, en pixels
MARGE_CURSEUR = 4


class PopupAuCurseurMixin:
    """Affiche un popup près du curseur, replié s'il déborde de l'écran.

    Attendus de la classe hôte :
      - être un QWidget (pour adjustSize / move / show)
      - exposer les attributs de classe WIDTH et MAX_HEIGHT, utilisés comme
        dimensions de repli tant que le widget n'est pas encore dimensionné.

    À placer AVANT la classe Qt dans les bases :
        class MonPopup(PopupAuCurseurMixin, QDialog)
    Le mixin ne définit ni __init__ ni slot Qt : il n'interfère pas avec
    l'initialisation ni avec le système de méta-objets.
    """

    def show_at_cursor(self):
        """
        Positionner le popup près du curseur et l'afficher.

        Le QTimer.singleShot(0) diffère l'affichage d'un tick pour que le clic
        qui a déclenché l'appel soit entièrement consommé avant l'ouverture —
        évite la fermeture immédiate du Qt.Popup sur les parents de haut niveau.
        Le popup est replié au-dessus / à gauche du curseur s'il déborderait
        de l'écran.
        """
        cursor_pos = QCursor.pos()

        def _do_show():
            self.adjustSize()
            pw = self.width()  or self.WIDTH
            ph = self.height() or self.MAX_HEIGHT

            screen = QApplication.screenAt(cursor_pos)
            if screen is None:
                screen = QApplication.primaryScreen()
            avail = screen.availableGeometry()

            x = cursor_pos.x() + MARGE_CURSEUR
            y = cursor_pos.y() + MARGE_CURSEUR

            if x + pw > avail.right():
                x = cursor_pos.x() - pw - MARGE_CURSEUR
            if y + ph > avail.bottom():
                y = cursor_pos.y() - ph - MARGE_CURSEUR

            x = max(avail.left(), x)
            y = max(avail.top(), y)

            self.move(x, y)
            self.show()

        QTimer.singleShot(0, _do_show)
