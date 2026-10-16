"""Libellé d'appareil dans l'historique groupé, au-delà des lignes affichées (v3.91.3).

Validation en masse de 1858 suggestions (production, 2026-10-16 14:39) : 124 entrées
d'historique portaient l'id numérique (« 788245 ») au lieu de « réf. modèle - réf.
commerciale ». Ces appareils étaient chargés dans la page mais au-delà des
FETCH_INITIAL lignes exposées par le défilement virtuel : `table.rowCount()` et
`table.item()` ne voient que les lignes affichées. Les valeurs en base étaient justes,
seul le libellé était faux.
"""
from unittest.mock import MagicMock

import pytest

from src.core.config import Config
from src.data.appareils_table_model import AppareillsTableModel
from src.services.grouped_history_service import GroupedHistoryService
from src.ui.custom_table_view import CustomTableView


def _record(db_id, ref_modele, commercial_ref="", type_="", manufacturer="", autre=""):
    return (db_id, type_, manufacturer, ref_modele, commercial_ref, autre, "", "", 0)


@pytest.fixture
def contexte(qapp, monkeypatch):
    monkeypatch.setattr(Config, 'USE_VIRTUAL_SCROLL', True)
    monkeypatch.setattr(Config, 'FETCH_INITIAL', 200)
    model = AppareillsTableModel()
    model.load_records([_record(1000 + i, f"MOD{i}", f"COM{i}") for i in range(300)])
    assert model.rowCount() == 200 and model.loaded_record_count() == 300
    table = CustomTableView()
    table.setModel(model)

    fenetre = MagicMock()
    fenetre.table = table
    fenetre.db_manager.lire_appareils_par_id.return_value = {}
    uis = MagicMock()
    uis.main_window = fenetre
    groupe = GroupedHistoryService(uis)
    yield groupe, uis, fenetre, model
    groupe.flush_timer.stop()
    table.deleteLater()


def _messages(uis):
    return [c.args[0] for c in uis.add_to_history.call_args_list]


class TestLibelleHorsAffichage:
    def test_ligne_chargee_non_affichee_flush_groupe(self, contexte):
        groupe, uis, _, _ = contexte
        groupe.add_modification(1250, "Type", "", "Four")      # ligne 250 > 200
        groupe.add_modification(1250, "Fabricant", "", "Bosch")
        groupe.add_modification(1010, "Type", "", "Four")      # ligne 10, affichée
        groupe.flush_all_pending_modifications()
        messages = _messages(uis)
        assert any("appareil MOD250 - COM250" in m for m in messages)
        assert any("appareil MOD10 - COM10" in m for m in messages)
        assert not any("appareil 1250" in m for m in messages)

    def test_ligne_chargee_non_affichee_flush_isole(self, contexte):
        groupe, uis, _, _ = contexte
        groupe.add_modification(1299, "Type", "", "Four")
        groupe.force_flush_device(1299)
        assert "appareil MOD299 - COM299" in _messages(uis)[0]

    def test_replis_lus_hors_affichage(self, contexte):
        groupe, uis, _, model = contexte
        model._records[260] = _record(1260, "", "", autre="AUTRE260")
        model._records[270] = _record(1270, "", "", type_="Four", manufacturer="Bosch")
        groupe.add_modification(1260, "Type", "", "Four")
        groupe.add_modification(1270, "Type", "Four", "Plaque")
        groupe.flush_all_pending_modifications()
        messages = _messages(uis)
        assert any("appareil AUTRE260" in m for m in messages)
        assert any("appareil Four Bosch" in m for m in messages)

    def test_appareil_absent_du_tableau_lu_en_base_en_une_requete(self, contexte):
        groupe, uis, fenetre, _ = contexte
        fenetre.db_manager.lire_appareils_par_id.return_value = {
            788245: ("", "", "3EP700S/03", "3EP700S"),
            788246: ("", "", "SEULE", ""),
        }
        for db_id in (788245, 788246, 788247, 1005):
            groupe.add_modification(db_id, "Type", "", "Plaque")
        groupe.add_modification(1500, "Type", "", "Four", reference="FOURNIE")
        groupe.flush_all_pending_modifications()
        # Une seule lecture, limitée aux appareils introuvables et sans libellé fourni
        fenetre.db_manager.lire_appareils_par_id.assert_called_once()
        assert sorted(fenetre.db_manager.lire_appareils_par_id.call_args.args[0]) == \
            [788245, 788246, 788247]
        messages = _messages(uis)
        assert any("appareil 3EP700S/03 - 3EP700S" in m for m in messages)
        assert any("appareil SEULE\n" in m for m in messages)
        assert any("appareil 788247\n" in m for m in messages)   # disparu : id
        assert any("appareil MOD5 - COM5" in m for m in messages)
        assert any("appareil FOURNIE" in m for m in messages)

    def test_echec_de_lecture_en_base_retombe_sur_l_id(self, contexte):
        groupe, uis, fenetre, _ = contexte
        fenetre.db_manager.lire_appareils_par_id.return_value = None
        groupe.add_modification(788245, "Type", "", "Plaque")
        groupe.flush_all_pending_modifications()
        assert "appareil 788245\n" in _messages(uis)[0]

    def test_tout_trouve_aucune_lecture_en_base(self, contexte):
        groupe, _, fenetre, _ = contexte
        groupe.add_modification(1250, "Type", "", "Four")
        groupe.flush_all_pending_modifications()
        fenetre.db_manager.lire_appareils_par_id.assert_not_called()
