"""
Tests — Suggestion « type de la pièce importée » (v3.87.0)

Mesure du 2026-10-15 : 98 % des éditions sont des saisies de Type/Fabricant, et
les suggestions par similarité ne couvrent que 41 % des lignes incomplètes. Or le
type que portent déjà les appareils d'une pièce est le bon dans 94 % des cas
quand il couvre ≥ 95 % d'au moins 5 appareils (68 % entre 80 et 95 %).

La suggestion ne propose que le Type (marque vide, jamais écrite), passe par le
même mécanisme que la similarité, et n'est jamais appliquée sans validation.
"""

import pytest

from src.core.config import Config
from src.core.import_manager import (
    ImportConfiguration, ImportFile, ImportManager, ImportType, FileType,
)
from src.services.reference_similarity_service import (
    TIER_TYPE_PIECE, candidat_type_piece, decrire_candidat, est_type_piece,
    infobulle_candidat, provenance_candidat, type_majoritaire,
)
from src.ui.suggestion_validation_dialog import is_safe_default, tier_label


# ── Fonctions pures ───────────────────────────────────────────────────────────

class TestTypeMajoritaire:

    def test_dominant_retenu(self):
        assert type_majoritaire({"Four": 19, "Hotte": 1}, 0.95, 5) == ("Four", 0.95, 20)

    def test_sous_le_seuil_de_part(self):
        assert type_majoritaire({"Four": 18, "Hotte": 2}, 0.95, 5) is None

    def test_trop_peu_d_appareils(self):
        assert type_majoritaire({"Four": 4}, 0.95, 5) is None

    def test_vide(self):
        assert type_majoritaire({}, 0.95, 5) is None


class TestLibelles:

    CAND = candidat_type_piece("Four", ["00650715"], 0.98, 1230)

    def test_format_du_candidat(self):
        assert self.CAND['manufacturer'] == ''
        assert est_type_piece(self.CAND)
        assert self.CAND['confidence_tier'] == TIER_TYPE_PIECE

    def test_libelles(self):
        assert decrire_candidat(self.CAND) == "Four  (type de la pièce 00650715, 98%)"
        assert provenance_candidat(self.CAND) == "type de la pièce 00650715 (98%)"
        assert "98% des 1230 appareils de la pièce 00650715" in infobulle_candidat(self.CAND)

    def test_libelles_similarite_inchanges(self):
        sim = {'type': 'Four', 'manufacturer': 'Smeg', 'score': 1.0, 'ref': 'SF64M3VB',
               'confidence_tier': 'A_suffix_variant'}
        assert provenance_candidat(sim) == "suggestion réf. SF64M3VB (score 100%)"
        assert decrire_candidat(sim) == "Four / Smeg  (score 100%, réf. SF64M3VB)"

    def test_fenetre_de_validation(self):
        assert tier_label(TIER_TYPE_PIECE) == "Type de la pièce"
        assert is_safe_default({'candidates': [self.CAND]})        # seul et ≥ 95 % : pré-coché
        concurrent = {'type': 'Hotte', 'manufacturer': 'X', 'score': 0.92,
                      'confidence_tier': 'B_fuzzy_alpha'}
        assert not is_safe_default({'candidates': [concurrent, self.CAND]})


# ── Import ────────────────────────────────────────────────────────────────────

@pytest.fixture
def manager(test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _piece_avec_appareils(manager, ref_piece, types):
    """Rattache à ref_piece un appareil complet par type donné."""
    ids = manager._batch_insert_devices([{
        'type': t, 'manufacturer': 'Smeg', 'ref_modele': f'ZQX{ref_piece}{i:03d}',
        'commercial_ref': '', 'other_ref': '', 'notes': '', 'category': '',
    } for i, t in enumerate(types)])
    for appareil_id in ids:
        manager.db_manager.add_piece(ref_piece, appareil_id, "")


def _importer(manager, ref_piece, lignes):
    manager._preload_existing_devices()
    config = ImportConfiguration(
        files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                          suggested_reference=ref_piece, suggested_label=ref_piece,
                          data=lignes)],
        import_type=ImportType.SINGLE_FILE,
    )
    return manager._run_import_files(config)


def _suggestions_type_piece(results):
    return {db_id: [c for c in cands if est_type_piece(c)]
            for db_id, cands in (results.get('similarity_suggestions') or {}).items()
            if any(est_type_piece(c) for c in cands)}


class TestImport:

    def test_ligne_sans_type_recoit_le_type_de_la_piece(self, manager):
        _piece_avec_appareils(manager, "PFOUR", ["Four"] * 6)
        results = _importer(manager, "PFOUR", [['QQWJ9001', 'QQWJ9001C']])
        trouvees = _suggestions_type_piece(results)
        assert len(trouvees) == 1
        cand = next(iter(trouvees.values()))[0]
        assert cand['type'] == "Four" and cand['manufacturer'] == ''
        assert cand['score'] == 1.0 and cand['nb_appareils'] == 6
        assert cand['ref'] == "PFOUR"

    def test_chemin_batch_gros_import(self, manager):
        """≥ 50 lignes : chemin batch (celui des PDF), distinct du chemin standard."""
        _piece_avec_appareils(manager, "PFOUR", ["Four"] * 6)
        lignes = [[f'QQWB{i:04d}', f'QQWB{i:04d}C'] for i in range(55)]
        results = _importer(manager, "PFOUR", lignes)
        trouvees = _suggestions_type_piece(results)
        assert len(trouvees) == 55
        assert {c[0]['type'] for c in trouvees.values()} == {"Four"}

    def test_jamais_ecrit_en_base(self, manager):
        _piece_avec_appareils(manager, "PFOUR", ["Four"] * 6)
        _importer(manager, "PFOUR", [['QQWJ9001', 'QQWJ9001C']])
        rows = manager.db_manager.execute_query(
            "SELECT COALESCE(type, '') FROM appareils WHERE ref_modele = 'QQWJ9001'")
        assert rows == [('',)]

    def test_part_insuffisante(self, manager):
        _piece_avec_appareils(manager, "PMIXTE", ["Four"] * 5 + ["Hotte"])   # 83 %
        results = _importer(manager, "PMIXTE", [['QQWJ9002', 'QQWJ9002C']])
        assert _suggestions_type_piece(results) == {}

    def test_trop_peu_d_appareils(self, manager):
        _piece_avec_appareils(manager, "PPETITE", ["Four"] * 4)
        results = _importer(manager, "PPETITE", [['QQWJ9003', 'QQWJ9003C']])
        assert _suggestions_type_piece(results) == {}

    def test_interrupteur(self, manager, monkeypatch):
        monkeypatch.setattr(Config, "ENABLE_TYPE_PIECE_SUGGESTION", False)
        _piece_avec_appareils(manager, "PFOUR", ["Four"] * 6)
        results = _importer(manager, "PFOUR", [['QQWJ9001', 'QQWJ9001C']])
        assert _suggestions_type_piece(results) == {}


class TestFusion:
    """_ajouter_suggestions_type_piece sur un état préparé à la main."""

    @pytest.fixture
    def ligne(self, manager):
        _piece_avec_appareils(manager, "PFOUR", ["Four"] * 6)
        d = {'id': 4242, 'ref_modele': 'QQWJ9009', 'type': ''}
        manager._pending_similarity_candidates = [d]
        manager._refs_pieces_candidats = {id(d): ["PFOUR"]}
        return d

    def test_meme_type_deja_propose_pas_de_doublon(self, manager, ligne):
        sim = [{'type': 'four', 'manufacturer': 'Smeg', 'score': 0.9,
                'confidence_tier': 'B_fuzzy_alpha'}]
        assert manager._ajouter_suggestions_type_piece({4242: list(sim)}) == {4242: sim}

    def test_type_different_ajoute_en_concurrent(self, manager, ligne):
        sim = {'type': 'Hotte', 'manufacturer': 'Smeg', 'score': 0.9,
               'confidence_tier': 'B_fuzzy_alpha'}
        res = manager._ajouter_suggestions_type_piece({4242: [sim]})
        assert [c['type'] for c in res[4242]] == ["Hotte", "Four"]
        assert est_type_piece(res[4242][1])

    def test_ligne_deja_typee_ignoree(self, manager, ligne):
        ligne['type'] = 'Hotte'
        assert manager._ajouter_suggestions_type_piece({}) == {}

    def test_plusieurs_pieces_cumulees(self, manager, ligne):
        """Référence commune + référence du fichier : les comptes s'additionnent."""
        _piece_avec_appareils(manager, "PAUTRE", ["Four"] * 2)
        manager._refs_pieces_candidats = {id(ligne): ["PFOUR", "PAUTRE"]}
        res = manager._ajouter_suggestions_type_piece({})
        assert res[4242][0]['nb_appareils'] == 8
        assert res[4242][0]['ref'] == "PFOUR, PAUTRE"
