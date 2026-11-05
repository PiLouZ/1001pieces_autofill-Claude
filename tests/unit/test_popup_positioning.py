"""
Tests — Positionnement des popups au curseur

`HistoryDetailPopup` et `PieceRelationsPopup` portaient la même méthode
`show_at_cursor`, 21 lignes de code strictement identiques — le docstring de la
première le reconnaissait : « Même pattern que PieceRelationsPopup ». Elle vit
désormais dans `PopupAuCurseurMixin`.

Ces tests fixent le comportement de positionnement, y compris les replis de bord
d'écran qui ne sont visibles qu'en poussant le curseur dans les coins.
"""

import pytest
from unittest.mock import patch

from src.utils.qt_imports import QApplication, QDialog, QPoint, Qt
from src.ui.popup_positioning import PopupAuCurseurMixin, MARGE_CURSEUR


class PopupDeTest(PopupAuCurseurMixin, QDialog):
    """Popup minimal : mêmes attentes que les deux vrais popups du projet."""
    WIDTH = 200
    MAX_HEIGHT = 150

    def __init__(self):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(self.WIDTH, self.MAX_HEIGHT)


@pytest.fixture
def ecran(qapp):
    return QApplication.primaryScreen().availableGeometry()


def _position_pour(qapp, curseur):
    """Position finale du popup pour un curseur donné."""
    with patch('PyQt5.QtGui.QCursor.pos', return_value=curseur):
        popup = PopupDeTest()
        popup.show_at_cursor()
        qapp.processEvents()          # exécute le QTimer.singleShot(0)
        position = (popup.x(), popup.y())
        popup.close()
    return position


class TestPositionNominale:

    def test_le_popup_se_pose_sous_le_curseur(self, qapp, ecran):
        curseur = QPoint(ecran.center())
        x, y = _position_pour(qapp, curseur)
        assert (x, y) == (curseur.x() + MARGE_CURSEUR, curseur.y() + MARGE_CURSEUR)


class TestRepliDeBord:
    """Le popup bascule de l'autre côté du curseur plutôt que de déborder."""

    def test_repli_a_gauche_sur_le_bord_droit(self, qapp, ecran):
        curseur = QPoint(ecran.right() - 10, ecran.center().y())
        x, _ = _position_pour(qapp, curseur)
        assert x == curseur.x() - PopupDeTest.WIDTH - MARGE_CURSEUR
        assert x + PopupDeTest.WIDTH <= ecran.right()

    def test_repli_au_dessus_sur_le_bord_bas(self, qapp, ecran):
        curseur = QPoint(ecran.center().x(), ecran.bottom() - 10)
        _, y = _position_pour(qapp, curseur)
        assert y == curseur.y() - PopupDeTest.MAX_HEIGHT - MARGE_CURSEUR
        assert y + PopupDeTest.MAX_HEIGHT <= ecran.bottom()

    def test_double_repli_dans_le_coin(self, qapp, ecran):
        curseur = QPoint(ecran.right() - 2, ecran.bottom() - 2)
        x, y = _position_pour(qapp, curseur)
        assert x + PopupDeTest.WIDTH <= ecran.right()
        assert y + PopupDeTest.MAX_HEIGHT <= ecran.bottom()


class TestMaintienDansLEcran:

    def test_jamais_au_dela_du_bord_haut_gauche(self, qapp, ecran):
        """Un curseur au coin haut-gauche ne doit pas pousser le popup hors champ."""
        x, y = _position_pour(qapp, QPoint(ecran.left(), ecran.top()))
        assert x >= ecran.left()
        assert y >= ecran.top()


class TestIntegrationDesDeuxPopups:
    """Les deux popups du projet doivent réellement utiliser le mixin."""

    def test_history_detail_popup(self, qapp):
        from src.ui.history_view_dialog import HistoryDetailPopup
        assert issubclass(HistoryDetailPopup, PopupAuCurseurMixin)
        assert 'show_at_cursor' not in vars(HistoryDetailPopup), \
            "la méthode a été redéfinie localement — la duplication est revenue"

    def test_piece_relations_popup(self, qapp):
        from src.ui.pieces_list_service import PieceRelationsPopup
        assert issubclass(PieceRelationsPopup, PopupAuCurseurMixin)
        assert 'show_at_cursor' not in vars(PieceRelationsPopup), \
            "la méthode a été redéfinie localement — la duplication est revenue"

    def test_le_mixin_precede_la_classe_qt(self, qapp):
        """L'ordre des bases compte : le mixin doit gagner sur QDialog."""
        from src.ui.history_view_dialog import HistoryDetailPopup
        bases = HistoryDetailPopup.__mro__
        assert bases.index(PopupAuCurseurMixin) < bases.index(QDialog)


class TestInnocuiteDuMixin:
    """Le mixin ne doit pas interférer avec l'initialisation Qt."""

    def test_pas_d_init_propre(self):
        assert '__init__' not in vars(PopupAuCurseurMixin)

    def test_n_apporte_que_show_at_cursor(self):
        publiques = {n for n in vars(PopupAuCurseurMixin) if not n.startswith('__')}
        assert publiques == {'show_at_cursor'}
