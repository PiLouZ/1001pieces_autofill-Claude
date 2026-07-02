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
