"""Flèches ▲/▼ « ligne incomplète » (toolbar, autour de « Lignes à traiter ») :
visibilité liée au compteur et raccourcis ⌥⌘↑/⌥⌘↓ alignés sur l'état des boutons."""

from unittest.mock import Mock

import pytest

from src.services.incomplete_button_service import IncompleteButtonService
from src.ui.qt_imports import QPushButton, QToolButton
from src.ui.table_controller import TableController


@pytest.fixture
def service(qapp):
    svc = IncompleteButtonService(db_manager=Mock())
    svc.set_button(QPushButton("Lignes à traiter"))
    return svc


class TestFlechesSuiventLeCompteur:

    def test_masquees_sans_ligne_incomplete(self, service):
        up, down = QToolButton(), QToolButton()
        service.set_companions((up, down))
        service._update_button_display(0)
        assert up.isHidden() and down.isHidden()

    def test_affichees_avec_lignes_incompletes(self, service):
        up, down = QToolButton(), QToolButton()
        service.set_companions((up, down))
        service._update_button_display(0)
        service._update_button_display(3)
        assert not up.isHidden() and not down.isHidden()


class TestRaccourciSuitLEtatDuBouton:
    """skip_to_incomplete_row (⌥⌘↑/⌥⌘↓) ne doit rien faire quand la flèche est
    grisée (direction épuisée) — sinon le clavier relancerait un balayage
    complet des pages que le bouton interdit."""

    def _controller(self, enabled: bool, visible: bool = True):
        tc = TableController.__new__(TableController)
        btn = Mock()
        btn.isEnabled.return_value = enabled
        btn.isVisible.return_value = visible
        tc.skip_empty_up_btn = btn
        tc.skip_empty_down_btn = btn
        tc._on_skip_empty_cell = Mock()
        return tc

    def test_fleche_active_declenche_le_saut(self):
        tc = self._controller(enabled=True)
        tc.skip_to_incomplete_row('down')
        tc._on_skip_empty_cell.assert_called_once_with('down')

    def test_fleche_grisee_ne_fait_rien(self):
        tc = self._controller(enabled=False)
        tc.skip_to_incomplete_row('up')
        tc._on_skip_empty_cell.assert_not_called()

    def test_fleche_masquee_ne_fait_rien(self):
        tc = self._controller(enabled=True, visible=False)
        tc.skip_to_incomplete_row('down')
        tc._on_skip_empty_cell.assert_not_called()

    def test_fleches_non_branchees_ne_plante_pas(self):
        tc = TableController.__new__(TableController)
        tc._on_skip_empty_cell = Mock()
        tc.skip_to_incomplete_row('down')
        tc._on_skip_empty_cell.assert_not_called()
