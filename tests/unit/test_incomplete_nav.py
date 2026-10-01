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


class TestRetourAuDepartApresBalayageInfructueux:
    """Rien trouvé dans la direction demandée : l'utilisateur revient sur sa
    page et sa cellule de départ, au lieu de rester sur la dernière page
    traversée sans sélection."""

    def _controller(self, qapp, pages):
        from src.data.appareils_table_model import AppareillsTableModel
        from PyQt5.QtWidgets import QTableView
        from tests.unit.test_table_model import make_record

        tc = TableController.__new__(TableController)
        tc.model = AppareillsTableModel()
        tc.table = QTableView()
        tc.table.setModel(tc.model)
        tc.page_size = 2
        tc.total_pages = len(pages)
        tc._empty_cells_search_exhausted = {'up': False, 'down': False}
        tc._update_empty_cell_buttons_state = Mock()
        tc.visited = []

        def goto(page):
            tc.visited.append(page)
            tc.current_page = page
            tc.model.load_records([make_record(db_id=i, type_=t) for i, t in pages[page]])
            tc._empty_cells_search_exhausted = {'up': False, 'down': False}  # comme load_data
        tc._goto_page_preserving_context = goto
        goto(1)
        tc.visited.clear()
        return tc

    def test_retour_page_et_cellule_de_depart(self, qapp):
        tc = self._controller(qapp, {1: [(1, "Four"), (2, "Four")],
                                     2: [(3, "Four"), (4, "Four")],
                                     3: [(5, "Four"), (6, "Four")]})
        tc.table.setCurrentIndex(tc.model.index(1, 4))
        tc._on_skip_empty_cell('down')
        assert tc.visited == [2, 3, 1]  # balayage complet, puis retour
        assert tc.current_page == 1
        idx = tc.table.currentIndex()
        assert (idx.row(), idx.column()) == (1, 4)
        assert tc._empty_cells_search_exhausted['down'] is True  # posé APRÈS le retour

    def test_trouve_sur_une_autre_page_pas_de_retour(self, qapp):
        tc = self._controller(qapp, {1: [(1, "Four"), (2, "Four")],
                                     2: [(3, "Four"), (4, "")]})
        tc.table.setCurrentIndex(tc.model.index(0, 3))
        tc._on_skip_empty_cell('down')
        assert tc.visited == [2] and tc.current_page == 2
        idx = tc.table.currentIndex()
        assert (idx.row(), idx.column()) == (1, 0)

    def test_rien_a_traverser_reste_en_place_sans_recharger(self, qapp):
        tc = self._controller(qapp, {1: [(1, "Four"), (2, "Four")]})
        tc.table.setCurrentIndex(tc.model.index(0, 2))
        tc._on_skip_empty_cell('up')
        assert tc.visited == []
        assert tc._empty_cells_search_exhausted['up'] is True
