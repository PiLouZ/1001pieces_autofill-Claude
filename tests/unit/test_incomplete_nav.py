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


class _ControleurPagine:
    """Faux TableController : vraies vue + modèle, pages simulées."""

    def _controller(self, qapp, pages, position=ValueError("tri « Nb pièces »")):
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
        tc.current_search_term = None
        tc.current_sort_column = 0
        from src.ui.qt_imports import Qt
        tc.current_sort_order = Qt.AscendingOrder
        tc.parent_window = Mock(sorting_filtering_service=None, show_incomplete_only=False)
        tc.filter_widgets = {}
        tc.build_effective_search_term = lambda term: term
        tc.db_manager = Mock()
        if isinstance(position, Exception):
            tc.db_manager.find_incomplete_position.side_effect = position
        else:
            tc.db_manager.find_incomplete_position.return_value = position

        def goto(page):
            tc.visited.append(page)
            tc.current_page = page
            tc.model.load_records([make_record(db_id=i, type_=t) for i, t in pages[page]])
            tc._empty_cells_search_exhausted = {'up': False, 'down': False}  # comme load_data
        tc._goto_page_preserving_context = goto
        goto(1)
        tc.visited.clear()
        return tc



class TestRetourAuDepartApresBalayageInfructueux(_ControleurPagine):
    """Repli « parcours des pages » (tri Nb pièces → ValueError) : rien trouvé
    dans la direction demandée, l'utilisateur revient sur sa page et sa cellule
    de départ, au lieu de rester sur la dernière page traversée sans sélection."""

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


class TestSautParPositionSQL(_ControleurPagine):
    """Chemin principal : la page affichée d'abord, puis une requête de position
    → un seul chargement de page, ou aucun si rien n'est trouvé."""

    PAGES = {1: [(1, "Four"), (2, "Four")],
             2: [(3, "Four"), (4, "Four")],
             3: [(5, "Four"), (6, "")]}

    def test_cible_sur_la_page_affichee_aucune_requete(self, qapp):
        tc = self._controller(qapp, {1: [(1, "Four"), (2, "")], 2: [(3, "Four"), (4, "Four")]}, position=3)
        tc.table.setCurrentIndex(tc.model.index(0, 4))
        tc._on_skip_empty_cell('down')
        tc.db_manager.find_incomplete_position.assert_not_called()
        assert tc.visited == []
        assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (1, 0)

    def test_un_seul_chargement_de_page(self, qapp):
        tc = self._controller(qapp, self.PAGES, position=5)  # page 3, rang 1
        tc.table.setCurrentIndex(tc.model.index(0, 4))
        tc._on_skip_empty_cell('down')
        assert tc.visited == [3]  # saut direct, pas de passage par la page 2
        assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (1, 0)
        # Position demandée à partir de la dernière ligne de la page 1
        args = tc.db_manager.find_incomplete_position.call_args[0]
        assert args[-2:] == (1, 'down')

    def test_vers_le_haut_part_du_debut_de_page(self, qapp):
        tc = self._controller(qapp, {1: [(1, ""), (2, "Four")], 2: [(3, "Four"), (4, "Four")]}, position=0)
        tc._goto_page_preserving_context(2)
        tc.visited.clear()
        tc.table.setCurrentIndex(tc.model.index(1, 2))
        tc._on_skip_empty_cell('up')
        assert tc.db_manager.find_incomplete_position.call_args[0][-2:] == (2, 'up')
        assert tc.visited == [1]
        assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (0, 0)

    def test_rien_trouve_aucun_chargement_fleche_grisee(self, qapp):
        tc = self._controller(qapp, self.PAGES, position=None)
        tc.table.setCurrentIndex(tc.model.index(1, 4))
        tc._on_skip_empty_cell('down')
        assert tc.visited == []  # on ne bouge pas du tout
        assert tc.current_page == 1
        assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (1, 4)
        assert tc._empty_cells_search_exhausted['down'] is True

    def test_erreur_sql_repli_sur_parcours(self, qapp):
        import sqlite3
        tc = self._controller(qapp, self.PAGES, position=sqlite3.OperationalError("verrou"))
        tc.table.setCurrentIndex(tc.model.index(0, 4))
        tc._on_skip_empty_cell('down')
        assert tc.visited == [2, 3]  # parcours page par page
        assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (1, 0)
