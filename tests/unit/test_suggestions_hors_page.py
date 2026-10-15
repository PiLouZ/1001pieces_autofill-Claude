"""Suggestions Type/Marque pour des appareils hors de la page chargée (v3.87.1).

Après un import, le tableau est rechargé sans filtre (page 1, tri id DESC) : les
appareils existants touchés par l'import ont d'anciens id et ne sont pas chargés.
La bannière les comptait, la fenêtre de validation les ignorait (70 annoncées,
24 listées sur une copie de la base réelle), et leur validation s'écrivait en base
sans entrée d'historique.
"""
from unittest.mock import MagicMock, Mock

import pytest

from src.data.appareils_table_model import AppareillsTableModel
from src.services.grouped_history_service import GroupedHistoryService


def _record(db_id, type_="", manufacturer="", ref_modele="REF", commercial_ref=""):
    return (db_id, type_, manufacturer, ref_modele, commercial_ref, "", "", "", 0)


def _cand(type_="Four", manufacturer="Bosch", ref="HBA1", score=0.9):
    return {'type': type_, 'manufacturer': manufacturer, 'ref': ref, 'score': score}


@pytest.fixture
def model(qapp):
    m = AppareillsTableModel()
    m.load_records([_record(1, ref_modele="CHARGE1")])
    return m


class TestSnapshotHorsPage:
    def test_appareils_hors_page_relus_et_listes(self, model):
        model.set_pending_suggestions({1: [_cand()], 50: [_cand()], 60: [_cand()]})
        lecteur = Mock(return_value={50: ("", "Bosch", "OLD50", "C50"),
                                     60: ("Four", "", "OLD60", "")})
        snap = model.suggestions_snapshot(lire_hors_page=lecteur)
        lecteur.assert_called_once_with([50, 60])  # seuls les non chargés sont lus
        par_id = {e['db_id']: e for e in snap}
        assert set(par_id) == {1, 50, 60}
        assert len(snap) == model.pending_suggestions_count
        assert par_id[1]['hors_page'] is False
        assert par_id[50]['hors_page'] is True
        assert par_id[50]['ref_modele'] == "OLD50"
        assert par_id[50]['commercial_ref'] == "C50"
        assert par_id[50]['current_manufacturer'] == "Bosch"
        assert par_id[60]['current_type'] == "Four"

    def test_appareil_disparu_retire_des_suggestions(self, model):
        model.set_pending_suggestions({1: [_cand()], 50: [_cand()], 99: [_cand()]})
        snap = model.suggestions_snapshot(
            lire_hors_page=lambda ids: {50: ("", "", "OLD50", "")})
        assert {e['db_id'] for e in snap} == {1, 50}
        # Bannière et fenêtre d'accord : 99 n'est plus compté
        assert model.pending_suggestions_count == 2

    def test_echec_de_lecture_ne_retire_rien(self, model):
        model.set_pending_suggestions({1: [_cand()], 50: [_cand()]})
        snap = model.suggestions_snapshot(lire_hors_page=lambda ids: None)
        assert {e['db_id'] for e in snap} == {1}
        assert model.pending_suggestions_count == 2

    def test_sans_lecteur_comportement_inchange(self, model):
        model.set_pending_suggestions({1: [_cand()], 50: [_cand()]})
        assert {e['db_id'] for e in model.suggestions_snapshot()} == {1}
        assert model.pending_suggestions_count == 2

    def test_tout_charge_aucune_lecture(self, model):
        model.set_pending_suggestions({1: [_cand()]})
        lecteur = Mock()
        model.suggestions_snapshot(lire_hors_page=lecteur)
        lecteur.assert_not_called()


class TestLireAppareilsParId:
    def test_lit_par_lots_et_omet_les_absents(self, test_db_manager):
        ids = [test_db_manager.add_device({'type': 'Four' if i % 2 else '',
                                           'manufacturer': 'Bosch',
                                           'ref_modele': f'R{i}',
                                           'commercial_ref': f'C{i}'})
               for i in range(1900)]  # > 2 lots de 900
        lus = test_db_manager.lire_appareils_par_id(ids + [10 ** 9])
        assert len(lus) == 1900
        assert 10 ** 9 not in lus
        assert lus[ids[3]] == ('Four', 'Bosch', 'R3', 'C3')
        assert lus[ids[0]][0] == ''

    def test_liste_vide(self, test_db_manager):
        assert test_db_manager.lire_appareils_par_id([]) == {}

    def test_echec_renvoie_none(self, test_db_manager):
        test_db_manager.cursor.execute("ALTER TABLE appareils RENAME TO appareils_x")
        try:
            assert test_db_manager.lire_appareils_par_id([1]) is None
        finally:
            test_db_manager.cursor.execute("ALTER TABLE appareils_x RENAME TO appareils")


class TestValidationHorsPage:
    """_apply_suggestion_decisions : historique + provenance hors page, sans Cmd+Z."""

    def _fenetre(self, model, db_manager):
        from src.ui.main_refactored import MainWindow
        fake = MagicMock()
        fake.table_controller.model = model
        fake.db_manager = db_manager
        fake._provenance_suggestion = MainWindow._provenance_suggestion
        fake._get_column_display_name = lambda col: MainWindow._get_column_display_name(fake, col)
        fake._historiser_suggestions_hors_page = (
            lambda hp, upd: MainWindow._historiser_suggestions_hors_page(fake, hp, upd))
        return fake

    def test_hors_page_historise_et_enregistre(self, qapp, test_db_manager):
        from src.ui.main_refactored import MainWindow
        hors = test_db_manager.add_device({'type': '', 'manufacturer': 'Bosch',
                                           'ref_modele': 'OLD1', 'commercial_ref': 'C1'})
        model = AppareillsTableModel()
        model.load_records([_record(hors + 1000, ref_modele="CHARGE")])
        fake = self._fenetre(model, test_db_manager)
        dans_page = hors + 1000
        decisions = [(hors, _cand("Four", "Bosch", ref="HBA1", score=0.95)),
                     (dans_page, _cand("Hotte", "Neff"))]

        assert MainWindow._apply_suggestion_decisions(fake, decisions) == 2

        # Ligne chargée : chemin habituel (setData → historique + Cmd+Z)
        appels = [c.args[2] for c in fake._apply_suggestion_with_provenance.call_args_list]
        assert appels == [dans_page]
        # Hors page : historique groupé avec provenance et référence lisible,
        # Fabricant inchangé (déjà « Bosch ») donc non historisé
        fake.grouped_history_service.add_modification.assert_called_once_with(
            hors, 'Type', '', 'Four',
            source="suggestion réf. HBA1 (score 95%)", reference="OLD1 - C1")
        # Persistance des deux appareils en une transaction
        fake.database_operations_service.save_cells_batch.assert_called_once_with({
            hors: {'type': 'Four', 'manufacturer': 'Bosch'},
            dans_page: {'type': 'Hotte', 'manufacturer': 'Neff'},
        })
        assert model.pending_suggestions_count == 0

    def test_type_de_la_piece_hors_page_garde_sa_provenance(self, qapp, test_db_manager):
        """Candidat « type de la pièce » (3.87.0) : même provenance qu'en page,
        et seul le Type est écrit (pas de marque proposée)."""
        from src.ui.main_refactored import MainWindow
        from src.services.reference_similarity_service import candidat_type_piece
        hors = test_db_manager.add_device({'type': '', 'manufacturer': 'Bosch',
                                           'ref_modele': 'OLD2', 'commercial_ref': ''})
        model = AppareillsTableModel()
        model.load_records([_record(hors + 1000)])
        fake = self._fenetre(model, test_db_manager)
        cand = candidat_type_piece('Four', ['00123456'], 0.97, 12)
        MainWindow._apply_suggestion_decisions(fake, [(hors, cand)])
        kwargs = fake.grouped_history_service.add_modification.call_args.kwargs
        assert kwargs['source'].startswith("type de la pièce")
        assert kwargs['reference'] == "OLD2"
        fake.database_operations_service.save_cells_batch.assert_called_once_with(
            {hors: {'type': 'Four'}})

    def test_tout_dans_la_page_aucune_relecture(self, qapp):
        from src.ui.main_refactored import MainWindow
        model = AppareillsTableModel()
        model.load_records([_record(7)])
        db = Mock()
        fake = self._fenetre(model, db)
        MainWindow._apply_suggestion_decisions(fake, [(7, _cand())])
        db.lire_appareils_par_id.assert_not_called()
        fake.grouped_history_service.add_modification.assert_not_called()


class TestHistoriqueGroupeReference:
    def _service(self):
        uis = Mock()
        uis.main_window = Mock(table=None)
        return GroupedHistoryService(uis), uis

    def test_reference_fournie_utilisee(self, qapp):
        svc, uis = self._service()
        svc.add_modification(42, 'Type', '', 'Four', source="suggestion réf. X (score 90%)",
                             reference="OLD1 - C1")
        svc.flush_all_pending_modifications()
        message = uis.add_to_history.call_args.args[0]
        assert "Modification de l'appareil OLD1 - C1" in message
        assert "(source : suggestion réf. X (score 90%))" in message

    def test_reference_fournie_entree_groupee(self, qapp):
        svc, uis = self._service()
        svc.add_modification(42, 'Type', '', 'Four', reference="OLD1")
        svc.add_modification(42, 'Fabricant', '', 'Bosch')
        svc.force_flush_device(42)
        assert "Modification de l'appareil OLD1" in uis.add_to_history.call_args.args[0]

    def test_sans_reference_repli_inchange(self, qapp):
        svc, uis = self._service()
        svc.add_modification(42, 'Type', '', 'Four')
        svc.flush_all_pending_modifications()
        assert "Modification de l'appareil 42" in uis.add_to_history.call_args.args[0]
