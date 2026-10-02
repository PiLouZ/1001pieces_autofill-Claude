"""Barre d'état après une recherche : total RÉEL (celui du tableau), pas celui
du terme seul. Défaut corrigé : une réf. neuve qui remplace d'autres affichait
« Recherche terminée : 0 résultats » au-dessus d'un tableau de 217 lignes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.core.config import Config
from src.services.advanced_search_service import AdvancedSearchService
from src.ui.table_controller import TableController


def _controleur(total, **etat):
    base = dict(_supersession_mode='', _supersession_bypass=False,
                _supersession_expand=False, _supersession_predecessors=[],
                _equivalence_expand=False, _equivalence_group=[])
    base.update(etat)
    tc = SimpleNamespace(total_rows=total, parent_window=SimpleNamespace(statusbar=MagicMock()), **base)
    return tc


def _message(tc, terme):
    TableController._show_search_result_message(tc, terme)
    return tc.parent_window.statusbar


def test_reference_qui_remplace_affiche_le_total_etendu():
    bar = _message(_controleur(217, _supersession_mode='replacing', _supersession_expand=True,
                               _supersession_predecessors=['710901200']), '711115200')
    bar.showMessage.assert_called_once_with(
        "Recherche terminée : 217 résultats (anciennes réf. incluses)",
        Config.SEARCH_STATUS_MESSAGE_TIMEOUT)


def test_remplacement_replie_sans_precision():
    bar = _message(_controleur(0, _supersession_mode='replacing', _supersession_expand=False,
                               _supersession_predecessors=['710901200']), '711115200')
    assert bar.showMessage.call_args[0][0] == "Recherche terminée : 0 résultat"


def test_ancienne_reference_et_equivalents():
    bar = _message(_controleur(1234, _supersession_mode='superseded',
                               _equivalence_expand=True, _equivalence_group=['X']), 'A')
    assert bar.showMessage.call_args[0][0] == \
        "Recherche terminée : 1 234 résultats (chaîne complète, équivalents inclus)"


def test_ancienne_reference_contournee_sans_precision():
    bar = _message(_controleur(5, _supersession_mode='superseded', _supersession_bypass=True), 'A')
    assert bar.showMessage.call_args[0][0] == "Recherche terminée : 5 résultats"


def test_recherche_effacee_retire_le_message_en_cours():
    bar = _message(_controleur(705288), '')
    bar.clearMessage.assert_called_once()
    bar.showMessage.assert_not_called()


def test_duree_affichage_allongee():
    assert Config.SEARCH_STATUS_MESSAGE_TIMEOUT > Config.STATUS_MESSAGE_TIMEOUT


def test_plus_de_recherche_prealable_sur_le_terme_seul():
    """Sa requête n'était lue par personne et son total (terme seul) restait affiché."""
    search_service = MagicMock()
    svc = AdvancedSearchService.__new__(AdvancedSearchService)
    svc.search_service = search_service
    assert svc._safe_execute_search('711115200') == []
    search_service.search.assert_not_called()
