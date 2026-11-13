"""Flèches ▲/▼ « ligne auto-complétée à vérifier » (barre d'état, autour de
« Auto-complétés à vérifier ») : même mécanique que les lignes incomplètes,
avec le critère « porte une trace dans appareils_autocompletes »."""

import random
from unittest.mock import Mock

import pytest

from src.core.config import Config
from src.utils.qt_imports import QToolButton
from src.ui.table_controller import TableController
from tests.unit.test_find_incomplete_position import _pages_concatenees, TRIS


# ── Requête de position SQL ─────────────────────────────────────────────────

@pytest.fixture
def db(test_db_manager):
    rnd = random.Random(7)
    rows = [(rnd.choice(["Four", "Lave-linge"]), rnd.choice(["Bosch", "Miele"]),
             f"REF{rnd.randint(0, 9)}", None, "", rnd.choice(["Cat1", "Cat2"]), None)
            for _ in range(60)]
    test_db_manager.cursor.executemany(
        "INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref,"
        " other_ref, category, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    ids = [r[0] for r in test_db_manager.cursor.execute("SELECT id FROM appareils")]
    traces = []
    for i in rnd.sample(ids, 12):
        champs = rnd.choice([('type',), ('manufacturer',), ('type', 'manufacturer')])
        traces += [(i, c, "x", None, 1, 1, "2026-11-13") for c in champs]
    test_db_manager.cursor.executemany(
        "INSERT INTO appareils_autocompletes (appareil_id, champ, valeur, source,"
        " accord, total, import_ts) VALUES (?, ?, ?, ?, ?, ?, ?)", traces)
    test_db_manager.conn.commit()
    return test_db_manager


@pytest.mark.parametrize("sort_col,order", TRIS)
@pytest.mark.parametrize("filters", [None, {5: "Cat1"}])
def test_position_sql_egale_parcours_des_pages(db, sort_col, order, filters):
    a_verifier = {r[0] for r in db.cursor.execute("SELECT appareil_id FROM appareils_autocompletes")}
    vues = _pages_concatenees(db, sort_col, order, filters, False)
    positions = [i for i, r in enumerate(vues) if r[0] in a_verifier]
    assert positions, "jeu de données sans ligne à vérifier : test inopérant"
    for depart in range(-1, len(vues) + 1):
        attendu_bas = next((p for p in positions if p > depart), None)
        attendu_haut = next((p for p in reversed(positions) if p < depart), None)
        assert db.find_a_verifier_position(None, filters, sort_col, order, False, depart, 'down') == attendu_bas
        assert db.find_a_verifier_position(None, filters, sort_col, order, False, depart, 'up') == attendu_haut


def test_aucune_trace_retourne_none(db):
    db.cursor.execute("DELETE FROM appareils_autocompletes")
    db.conn.commit()
    assert db.find_a_verifier_position(None, None, 0, "ASC", False, -1, 'down') is None


def test_tri_nb_pieces_refuse(db):
    with pytest.raises(ValueError):
        db.find_a_verifier_position(None, None, len(Config.DB_HEADERS), "ASC", False, 0, 'down')


# ── Modèle : recherche dans la page ─────────────────────────────────────────

def _modele(qapp, ids, autocompletes):
    from src.data.appareils_table_model import AppareillsTableModel
    from tests.unit.test_table_model import make_record
    m = AppareillsTableModel()
    m.load_records([make_record(db_id=i) for i in ids])
    m.set_autocompletes(autocompletes)
    return m


def test_ligne_et_colonne_a_controler(qapp):
    m = _modele(qapp, [1, 2, 3, 4], {2: {'manufacturer': (None, 1, 1)},
                                    4: {'type': (None, 1, 1), 'manufacturer': (None, 1, 1)}})
    assert m.find_a_verifier_row(-1, 'down') == (1, 1)    # Fabricant seul
    assert m.find_a_verifier_row(1, 'down') == (3, 0)     # Type d'abord
    assert m.find_a_verifier_row(3, 'down') is None
    assert m.find_a_verifier_row(3, 'up') == (1, 1)
    assert m.find_a_verifier_row(1, 'up') is None


def test_a_des_autocompletes(qapp):
    assert not _modele(qapp, [1], {}).a_des_autocompletes()
    assert _modele(qapp, [1], {99: {'type': (None, 1, 1)}}).a_des_autocompletes()


# ── Contrôleur : saut et état des flèches ───────────────────────────────────

def _controleur(qapp, pages, autocompletes, position=None):
    """Faux TableController paginé (vraies vue + modèle), comme test_incomplete_nav."""
    from src.data.appareils_table_model import AppareillsTableModel
    from PyQt5.QtWidgets import QTableView
    from src.utils.qt_imports import Qt
    from tests.unit.test_table_model import make_record

    tc = TableController.__new__(TableController)
    tc.model = AppareillsTableModel()
    tc.table = QTableView()
    tc.table.setModel(tc.model)
    tc.page_size = 2
    tc.total_pages = len(pages)
    tc._a_verifier_epuise = {'up': False, 'down': False}
    tc._update_a_verifier_buttons_state = Mock()
    tc._update_empty_cell_buttons_state = Mock()
    tc.visited = []
    tc.current_search_term = None
    tc.current_sort_column = 0
    tc.current_sort_order = Qt.AscendingOrder
    tc.parent_window = Mock(sorting_filtering_service=None, show_incomplete_only=False)
    tc.filter_widgets = {}
    tc.build_effective_search_term = lambda term: term
    tc.db_manager = Mock()
    if isinstance(position, Exception):
        tc.db_manager.find_a_verifier_position.side_effect = position
    else:
        tc.db_manager.find_a_verifier_position.return_value = position

    def goto(page):
        tc.visited.append(page)
        tc.current_page = page
        tc.model.load_records([make_record(db_id=i) for i in pages[page]])
        tc._a_verifier_epuise = {'up': False, 'down': False}  # comme load_data
    tc._goto_page_preserving_context = goto
    goto(1)
    tc.model.set_autocompletes(autocompletes)
    tc.visited.clear()
    return tc


PAGES = {1: [1, 2], 2: [3, 4], 3: [5, 6]}
TRACE = {'manufacturer': (None, 1, 1)}


def test_cible_sur_la_page_sans_requete(qapp):
    tc = _controleur(qapp, PAGES, {2: TRACE})
    tc.table.setCurrentIndex(tc.model.index(0, 4))
    tc._sauter_vers('a_verifier', 'down')
    tc.db_manager.find_a_verifier_position.assert_not_called()
    tc.db_manager.find_incomplete_position.assert_not_called()
    assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (1, 1)


def test_saut_direct_vers_une_autre_page(qapp):
    tc = _controleur(qapp, PAGES, {6: TRACE}, position=5)
    tc.table.setCurrentIndex(tc.model.index(0, 4))
    tc._sauter_vers('a_verifier', 'down')
    assert tc.visited == [3]
    assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (1, 1)
    assert tc.db_manager.find_a_verifier_position.call_args[0][-2:] == (1, 'down')
    tc.db_manager.find_incomplete_position.assert_not_called()


def test_rien_trouve_fleche_grisee_sans_bouger(qapp):
    tc = _controleur(qapp, PAGES, {1: TRACE}, position=None)
    tc.table.setCurrentIndex(tc.model.index(1, 4))
    tc._sauter_vers('a_verifier', 'down')
    assert tc.visited == []
    assert tc._a_verifier_epuise['down'] is True
    tc._update_a_verifier_buttons_state.assert_called()
    tc._update_empty_cell_buttons_state.assert_not_called()


def test_repli_parcours_des_pages(qapp):
    import sqlite3
    tc = _controleur(qapp, PAGES, {5: TRACE}, position=sqlite3.OperationalError("verrou"))
    tc.table.setCurrentIndex(tc.model.index(0, 4))
    tc._sauter_vers('a_verifier', 'down')
    assert tc.visited == [2, 3]
    assert (tc.table.currentIndex().row(), tc.table.currentIndex().column()) == (0, 1)


class TestEtatDesFleches:

    def _tc(self, qapp, autocompletes, filtre_incomplet=False):
        tc = _controleur(qapp, PAGES, autocompletes)
        del tc._update_a_verifier_buttons_state   # la vraie méthode
        tc.parent_window.show_incomplete_only = filtre_incomplet
        tc.a_verifier_up_btn, tc.a_verifier_down_btn = QToolButton(), QToolButton()
        return tc

    def test_actives_avec_des_autocompletes(self, qapp):
        tc = self._tc(qapp, {9: TRACE})
        tc._update_a_verifier_buttons_state()
        assert tc.a_verifier_up_btn.isEnabled() and tc.a_verifier_down_btn.isEnabled()

    def test_grisees_sans_autocomplete(self, qapp):
        tc = self._tc(qapp, {})
        tc._update_a_verifier_buttons_state()
        assert not tc.a_verifier_up_btn.isEnabled()

    def test_grisees_sous_filtre_lignes_a_traiter(self, qapp):
        tc = self._tc(qapp, {9: TRACE}, filtre_incomplet=True)
        tc._update_a_verifier_buttons_state()
        assert not tc.a_verifier_down_btn.isEnabled()

    def test_direction_epuisee_puis_oubliee(self, qapp):
        tc = self._tc(qapp, {9: TRACE})
        tc._a_verifier_epuise = {'up': False, 'down': True}
        tc._update_a_verifier_buttons_state()
        assert tc.a_verifier_up_btn.isEnabled() and not tc.a_verifier_down_btn.isEnabled()
        tc.on_autocompletes_changed()
        assert tc.a_verifier_down_btn.isEnabled()


def test_raccourci_suit_l_etat_du_bouton(qapp):
    tc = TableController.__new__(TableController)
    btn = Mock(isEnabled=Mock(return_value=False), isVisible=Mock(return_value=True))
    tc.a_verifier_up_btn = tc.a_verifier_down_btn = btn
    tc._sauter_vers = Mock()
    tc.skip_to_row('a_verifier', 'down')
    tc._sauter_vers.assert_not_called()
    btn.isEnabled.return_value = True
    tc.skip_to_row('a_verifier', 'down')
    tc._sauter_vers.assert_called_once_with('a_verifier', 'down')
