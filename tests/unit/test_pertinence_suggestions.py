"""
Tests — Pertinence des suggestions Type/Marque (v3.93.0)

1. Garde « groupe du code numérique » : un long code numérique de fabricant
   désigne un groupe industriel. Un candidat dont la marque n'a jamais été vue
   sur la famille du code (≥ 20 appareils) est écarté. Mesure sur la base réelle
   (4 000 appareils masqués) : cf. CHANGELOG 3.93.0.
2. Palier « type de la pièce » étendu au clic droit et au scan global : mêmes
   seuils et même fusion que l'import (fonction commune fusionner_type_piece).
"""

import types

import pytest

from src.core.config import Config
from src.core.import_manager import ImportManager
from src.services.reference_similarity_service import (
    ReferenceSimilarityService, est_type_piece, fusionner_type_piece,
    signature_code_numerique,
)
from src.ui.main_refactored import MainWindow


# ── 1. Groupe du code numérique ───────────────────────────────────────────────

class TestSignatureCode:

    def test_code_long_entierement_numerique(self):
        assert signature_code_numerique("7786187805") == (10, "778")
        assert signature_code_numerique(" 854664522730 ") == (12, "854")

    def test_hors_signature(self):
        assert signature_code_numerique("1234567") is None        # trop court
        assert signature_code_numerique("FSS63010DW") is None
        assert signature_code_numerique("7786187805/01") is None  # pas que des chiffres
        assert signature_code_numerique("") is None


def _rows_famille(n_beko=25):
    """Famille de codes Beko 77…(10 chiffres) + un appareil AEG au préfixe FSS."""
    rows = [(i, f"77861{i:05d}", f"BKX{i:04d}", "Four", "Beko") for i in range(1, n_beko + 1)]
    rows.append((900, "91160000000", "FSS63010DX", "Lave-vaisselle", "AEG"))
    return rows


def _candidats(rows, garde):
    svc = ReferenceSimilarityService(fuzzy_threshold=0.80, enforce_code_group=garde)
    index = ReferenceSimilarityService.build_reference_index(rows)
    return svc.find_candidates("7786187805", "FSS63010DW", index)


class TestGroupeCode:

    def test_index_compte_les_marques_par_famille(self):
        index = ReferenceSimilarityService.build_reference_index(_rows_famille())
        assert index.marques_par_code[(10, "778")]["beko"] == 25
        assert index.marques_par_code[(11, "911")]["aeg"] == 1

    def test_marque_etrangere_au_groupe_ecartee(self):
        assert [c.manufacturer for c in _candidats(_rows_famille(), garde=False)] == ["AEG"]
        assert _candidats(_rows_famille(), garde=True) == []

    def test_famille_trop_petite_rien_n_est_ecarte(self):
        assert [c.manufacturer for c in _candidats(_rows_famille(n_beko=5), garde=True)] == ["AEG"]

    def test_marque_du_groupe_conservee(self):
        rows = _rows_famille() + [(901, "11111111", "FSS63011DW", "Four", "Beko")]
        assert "Beko" in {c.manufacturer for c in _candidats(rows, garde=True)}

    def test_desactivee_par_defaut_dans_le_module(self):
        assert ReferenceSimilarityService().enforce_code_group is False

    def test_activee_dans_l_application(self):
        assert Config.SIMILARITY_GROUPE_CODE is True


# ── 2. Type de la pièce : fusion commune ──────────────────────────────────────

class TestFusionTypePiece:

    TYPES = {"P1": {"Four": 4}, "P2": {"Four": 3, "Hotte": 0}}

    def test_type_ajoute_en_concurrent(self):
        existants = [{'type': 'Four vapeur', 'manufacturer': 'Bosch', 'score': 0.9,
                      'confidence_tier': 'B_fuzzy_alpha'}]
        fusion = fusionner_type_piece(existants, ["P1", "P2"], self.TYPES, 0.95, 5)
        assert len(fusion) == 2 and est_type_piece(fusion[1])
        assert fusion[1]['type'] == "Four" and fusion[1]['nb_appareils'] == 7
        assert existants[0] is fusion[0] and len(existants) == 1   # entrée non modifiée

    def test_type_deja_propose(self):
        existants = [{'type': 'four', 'manufacturer': 'Bosch'}]
        assert fusionner_type_piece(existants, ["P1", "P2"], self.TYPES, 0.95, 5) is None

    def test_pas_de_type_dominant(self):
        assert fusionner_type_piece([], ["P1"], {"P1": {"Four": 3, "Hotte": 3}}, 0.95, 5) is None
        assert fusionner_type_piece([], ["P1"], self.TYPES, 0.95, 5) is None   # 4 < 5


# ── 2. Type de la pièce : clic droit / scan global ────────────────────────────

@pytest.fixture
def manager(test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _appareils(manager, specs, ref_piece):
    ids = manager._batch_insert_devices([{
        'type': t, 'manufacturer': m, 'ref_modele': ref, 'commercial_ref': '',
        'other_ref': '', 'notes': '', 'category': '',
    } for (ref, t, m) in specs])
    for appareil_id in ids:
        manager.db_manager.add_piece(ref_piece, appareil_id, "")
    return ids


def _fenetre(db_manager):
    return types.SimpleNamespace(db_manager=db_manager)


class TestHorsImport:

    def test_lectures_groupees(self, manager):
        ids = _appareils(manager, [(f"ZQF{i}", "Four", "Smeg") for i in range(3)], "PF")
        db = manager.db_manager
        assert db.compter_types_par_piece(["PF", "INCONNUE"]) == {"PF": {"Four": 3}}
        assert db.lire_refs_pieces_par_appareil(ids[:2] + [999999]) == {ids[0]: ["PF"], ids[1]: ["PF"]}

    def test_appareil_sans_type_recoit_le_type_de_ses_pieces(self, manager):
        _appareils(manager, [(f"ZQF{i}", "Four", "Smeg") for i in range(6)], "PF")
        (cible,) = _appareils(manager, [("ZQCIBLE", "", "")], "PF")
        found = MainWindow._ajouter_suggestions_type_piece(_fenetre(manager.db_manager), {}, [cible])
        (cand,) = found[cible]
        assert est_type_piece(cand) and cand['type'] == "Four" and cand['nb_appareils'] == 6

    def test_appareil_deja_type_ignore(self, manager):
        _appareils(manager, [(f"ZQF{i}", "Four", "Smeg") for i in range(6)], "PF")
        (cible,) = _appareils(manager, [("ZQCIBLE", "Hotte", "")], "PF")
        found = MainWindow._ajouter_suggestions_type_piece(_fenetre(manager.db_manager), {}, [cible])
        assert found == {}

    def test_concurrent_de_la_similarite(self, manager):
        _appareils(manager, [(f"ZQF{i}", "Four", "Smeg") for i in range(6)], "PF")
        (cible,) = _appareils(manager, [("ZQCIBLE", "", "")], "PF")
        sim = {'type': 'Four vapeur', 'manufacturer': 'Smeg', 'confidence_tier': 'B_fuzzy_alpha'}
        found = MainWindow._ajouter_suggestions_type_piece(
            _fenetre(manager.db_manager), {cible: [sim]}, [cible])
        assert [c['type'] for c in found[cible]] == ["Four vapeur", "Four"]

    def test_desactivable(self, manager, monkeypatch):
        monkeypatch.setattr(Config, 'ENABLE_TYPE_PIECE_SUGGESTION', False)
        _appareils(manager, [(f"ZQF{i}", "Four", "Smeg") for i in range(6)], "PF")
        (cible,) = _appareils(manager, [("ZQCIBLE", "", "")], "PF")
        assert MainWindow._ajouter_suggestions_type_piece(
            _fenetre(manager.db_manager), {}, [cible]) == {}

    def test_erreur_de_lecture_non_bloquante(self):
        def boom(_ids):
            raise RuntimeError("base indisponible")
        fenetre = _fenetre(types.SimpleNamespace(lire_appareils_par_id=boom))
        deja = {1: [{'type': 'Four'}]}
        assert MainWindow._ajouter_suggestions_type_piece(fenetre, deja, [1]) == deja
