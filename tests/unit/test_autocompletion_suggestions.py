"""
Tests de l'application d'une suggestion Type/Marque (Phase 3).

Valide apply_suggestion_pair : écriture via le pipeline model.setData (jamais
d'accès DB direct), n'écrit que les champs non vides du candidat.
"""

import pytest
from unittest.mock import Mock
from PyQt5.QtCore import Qt

from src.data.appareils_table_model import AppareillsTableModel
from src.services.autocompletion_service import AutoCompletionService


def _model_one_row(db_id=5):
    m = AppareillsTableModel()
    m.load_records([(db_id, "", "", f"REF{db_id}", f"COM{db_id}", "", "Cat", "", 0)])
    return m


@pytest.mark.unit
class TestApplySuggestionPair:
    def _service(self):
        return AutoCompletionService(Mock(), None)

    def test_applique_type_et_marque(self, qapp):
        m = _model_one_row(5)
        ok = self._service().apply_suggestion_pair(
            {'type': 'Lave-vaisselle', 'manufacturer': 'Bosch'}, m, db_id=5)
        assert ok is True
        assert m.data(m.index(0, 0), Qt.DisplayRole) == 'Lave-vaisselle'
        assert m.data(m.index(0, 1), Qt.DisplayRole) == 'Bosch'

    def test_db_id_absent_retourne_false(self, qapp):
        m = _model_one_row(5)
        ok = self._service().apply_suggestion_pair(
            {'type': 'X', 'manufacturer': 'Y'}, m, db_id=999)
        assert ok is False

    def test_champ_vide_non_ecrit(self, qapp):
        m = _model_one_row(5)
        ok = self._service().apply_suggestion_pair(
            {'type': '', 'manufacturer': 'Bosch'}, m, db_id=5)
        assert ok is True
        assert m.data(m.index(0, 0), Qt.DisplayRole) == ''       # Type reste vide
        assert m.data(m.index(0, 1), Qt.DisplayRole) == 'Bosch'  # Marque écrite


@pytest.mark.unit
class TestResolveSuggestionInline:
    """Routage du clic-icône : 1 candidat → application directe ; plusieurs → chooser.

    Teste la logique de _resolve_suggestion_inline isolément (self mocké) — pas
    d'accès à la vraie base ni de dialogue réel.
    """

    def _fake_window(self, db_id=7):
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.table_controller.model.get_db_id.return_value = db_id
        idx = MagicMock()
        idx.row.return_value = 0
        return fake, idx

    def test_un_candidat_applique_directement(self):
        from src.ui.main_refactored import MainWindow
        fake, idx = self._fake_window(db_id=7)
        cand = {'type': 'Four', 'manufacturer': 'Siemens'}
        MainWindow._resolve_suggestion_inline(fake, idx, [cand])
        fake.autocompletion_service.apply_suggestion_pair.assert_called_once()
        fake.table_controller.clear_similarity_suggestion.assert_called_once_with(7)
        fake._show_suggestion_dialog.assert_not_called()

    def test_plusieurs_candidats_ouvre_chooser(self):
        from src.ui.main_refactored import MainWindow
        fake, idx = self._fake_window(db_id=7)
        cands = [{'type': 'Four', 'manufacturer': 'Siemens'},
                 {'type': 'Four', 'manufacturer': 'Bosch'}]
        MainWindow._resolve_suggestion_inline(fake, idx, cands)
        fake._show_suggestion_dialog.assert_called_once()
        fake.autocompletion_service.apply_suggestion_pair.assert_not_called()

    def test_liste_vide_ne_fait_rien(self):
        from src.ui.main_refactored import MainWindow
        fake, idx = self._fake_window()
        MainWindow._resolve_suggestion_inline(fake, idx, [])
        fake.autocompletion_service.apply_suggestion_pair.assert_not_called()
        fake._show_suggestion_dialog.assert_not_called()
