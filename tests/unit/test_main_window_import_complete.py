"""
Tests pour MainWindow._find_first_current_ref (v3.60.0) : détermine, parmi les
références pièce importées, la première qui est "courante" (non supersédée),
pour déclencher automatiquement la recherche sur le tableau après import.
"""

import pytest
from unittest.mock import MagicMock

from src.ui.main_refactored import MainWindow


@pytest.fixture
def main_window():
    """Instance MainWindow sans __init__ (évite de monter toute l'UI) —
    seul self.db_manager est nécessaire pour _find_first_current_ref."""
    win = MainWindow.__new__(MainWindow)
    win.db_manager = MagicMock()
    return win


class TestFindFirstCurrentRef:
    def test_liste_vide_retourne_none(self, main_window):
        assert main_window._find_first_current_ref([]) is None

    def test_premiere_ref_courante_retenue(self, main_window):
        main_window.db_manager.get_pieces_statuses_batch.return_value = {
            'REFA': {'status': 'current'},
            'REFB': {'status': 'current'},
        }
        assert main_window._find_first_current_ref(['REFA', 'REFB']) == 'REFA'

    def test_ref_supersedee_ignoree_au_profit_de_la_suivante(self, main_window):
        main_window.db_manager.get_pieces_statuses_batch.return_value = {
            'OLDREF': {'status': 'superseded', 'ref_new': 'NEWREF'},
            'NEWREF': {'status': 'current'},
        }
        assert main_window._find_first_current_ref(['OLDREF', 'NEWREF']) == 'NEWREF'

    def test_toutes_supersedees_retourne_none(self, main_window):
        main_window.db_manager.get_pieces_statuses_batch.return_value = {
            'OLDREF1': {'status': 'superseded', 'ref_new': 'X'},
            'OLDREF2': {'status': 'superseded', 'ref_new': 'Y'},
        }
        assert main_window._find_first_current_ref(['OLDREF1', 'OLDREF2']) is None

    def test_statut_obsolete_ou_replacing_considere_courant(self, main_window):
        """Une pièce obsolète (plus fabriquée) ou qui remplace d'autres refs reste
        une référence "courante" au sens de cette fonction : seule une ref
        remplacée par une plus récente (superseded) est exclue."""
        main_window.db_manager.get_pieces_statuses_batch.return_value = {
            'REFOBS': {'status': 'obsolete'},
        }
        assert main_window._find_first_current_ref(['REFOBS']) == 'REFOBS'

        main_window.db_manager.get_pieces_statuses_batch.return_value = {
            'REFREPL': {'status': 'replacing', 'refs_old': 'OLD1, OLD2'},
        }
        assert main_window._find_first_current_ref(['REFREPL']) == 'REFREPL'


class TestOnImportCompleteExportButtons:
    """NON-RÉGRESSION : après le chargement automatique sur la référence courante,
    les boutons d'export doivent être réactivés — normalement pilotés par
    search_with_debounce (via textChanged), court-circuité ici par blockSignals
    autour de search_input.setText() pour éviter un double chargement."""

    @pytest.fixture
    def main_window_full(self, main_window):
        main_window.search_input = MagicMock()
        main_window.advanced_search_service = MagicMock()
        main_window.table_controller = MagicMock()
        main_window.ui_component_service = MagicMock()
        main_window._show_import_results_new = MagicMock()
        return main_window

    def test_ref_courante_reactive_les_boutons_export(self, main_window_full):
        main_window_full.db_manager.get_pieces_statuses_batch.return_value = {
            'REFA': {'status': 'current'},
        }
        main_window_full._on_import_complete({'imported_refs': ['REFA']})

        main_window_full.table_controller.load_data.assert_called_once_with('REFA', is_search=True)
        main_window_full.ui_component_service.update_export_buttons_state_by_search.assert_called_once_with(True)

    def test_aucune_ref_courante_ne_touche_pas_les_boutons_export(self, main_window_full):
        main_window_full.db_manager.get_pieces_statuses_batch.return_value = {
            'OLDREF': {'status': 'superseded', 'ref_new': 'X'},
        }
        main_window_full._on_import_complete({'imported_refs': ['OLDREF']})

        main_window_full.table_controller.load_data.assert_called_once_with()
        main_window_full.ui_component_service.update_export_buttons_state_by_search.assert_not_called()
