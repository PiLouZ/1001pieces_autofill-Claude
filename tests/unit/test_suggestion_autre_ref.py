"""
Tests — Suggestion « Autre référence » (v3.98.0)

La colonne « Autre référence » porte souvent la désignation du fichier
fournisseur (« Lave-vaisselle tout-intégrable », « Side by side »). Mesure du
2026-10-23 (appris avant le 2026-09-01, vérifié sur les 24 069 appareils
importés depuis) : le type des appareils au même texte est juste à 99,6 % sur
53 % des lignes, quand il couvre ≥ 95 % d'au moins 5 appareils.

Un indice, pas une certitude : « Hotte encastrable » figure sur des lave-linge
d'un fichier mal étiqueté — le seuil de part l'écarte. Type seul, jamais écrit
sans validation, en concurrent des autres paliers.
"""

import types

import pytest

from src.core.config import Config
from src.core.import_manager import (
    ImportConfiguration, ImportFile, ImportManager, ImportType, FileType,
)
from src.services.reference_similarity_service import (
    LIBELLE_PREUVE, TIER_AUTRE_REF, candidat_autre_ref, candidat_type_piece,
    decrire_candidat, est_autre_ref, est_type_piece, est_type_seul,
    fusionner_autre_ref, infobulle_candidat, provenance_candidat,
    risques_suggestion, texte_preuve,
)
from src.ui.main_refactored import MainWindow
from src.ui.suggestion_validation_dialog import is_safe_default, tier_label


TEXTE = "Lave-vaisselle tout-intégrable"


# ── Fonctions pures ───────────────────────────────────────────────────────────

class TestFusion:

    TYPES = {TEXTE: {"Lave-vaisselle": 19, "Four": 1}}

    def test_type_dominant_ajoute(self):
        (cand,) = fusionner_autre_ref([], TEXTE, self.TYPES, 0.95, 5)
        assert est_autre_ref(cand) and est_type_seul(cand) and not est_type_piece(cand)
        assert cand['type'] == "Lave-vaisselle" and cand['manufacturer'] == ''
        assert cand['ref'] == TEXTE and cand['score'] == 0.95 and cand['nb_appareils'] == 20

    def test_texte_entoure_d_espaces(self):
        assert fusionner_autre_ref([], f"  {TEXTE} ", self.TYPES, 0.95, 5)[0]['ref'] == TEXTE

    def test_fichier_mal_etiquete_ecarte(self):
        """Cas réel : « Hotte encastrable » sur 237 hottes et 49 lave-linge,
        sèche-linge, réfrigérateurs (83 %)."""
        types_ = {"Hotte encastrable": {"Hotte": 237, "Lave-linge": 22, "Sèche-linge": 19,
                                        "Réfrigérateur": 8}}
        assert fusionner_autre_ref([], "Hotte encastrable", types_, 0.95, 5) is None

    def test_texte_inconnu_vide_ou_trop_rare(self):
        assert fusionner_autre_ref([], "sLFT11012", self.TYPES, 0.95, 5) is None
        assert fusionner_autre_ref([], "", self.TYPES, 0.95, 5) is None
        assert fusionner_autre_ref([], None, self.TYPES, 0.95, 5) is None
        assert fusionner_autre_ref([], "X", {"X": {"Four": 4}}, 0.95, 5) is None

    def test_meme_type_deja_propose_pas_de_doublon(self):
        sim = [{'type': 'lave-vaisselle', 'manufacturer': 'Bosch', 'score': 0.9,
                'confidence_tier': 'B_fuzzy_alpha'}]
        assert fusionner_autre_ref(sim, TEXTE, self.TYPES, 0.95, 5) is None

    def test_type_different_ajoute_en_concurrent(self):
        piece = candidat_type_piece("Four", ["PF"], 1.0, 6)
        res = fusionner_autre_ref([piece], TEXTE, self.TYPES, 0.95, 5)
        assert [c['type'] for c in res] == ["Four", "Lave-vaisselle"]
        assert not is_safe_default({'candidates': res})          # plus pré-coché
        assert "2 candidats concurrents (types différents)" in risques_suggestion(res)

    def test_entree_non_modifiee(self):
        existants = [{'type': 'Four', 'manufacturer': 'Smeg'}]
        fusionner_autre_ref(existants, TEXTE, self.TYPES, 0.95, 5)
        assert len(existants) == 1


class TestLibelles:

    CAND = candidat_autre_ref("Réfrigérateur", "Side by side", 0.99, 945)

    def test_libelles(self):
        assert decrire_candidat(self.CAND) == "Réfrigérateur  (autre réf. « Side by side », 99%)"
        assert provenance_candidat(self.CAND) == "autre réf. « Side by side » (99%)"
        assert "99% des 945 appareils dont l'autre réf. est « Side by side »" \
            in infobulle_candidat(self.CAND)
        assert texte_preuve(self.CAND) == "autre réf. 936/945"
        assert LIBELLE_PREUVE[TIER_AUTRE_REF] == "Autre référence"

    def test_pas_de_risque_de_ressemblance(self):
        assert risques_suggestion([self.CAND]) == []

    def test_fenetre_de_validation(self):
        assert tier_label(TIER_AUTRE_REF) == "Autre référence"
        assert is_safe_default({'candidates': [self.CAND]})       # seul et ≥ 95 %


# ── Import ────────────────────────────────────────────────────────────────────

@pytest.fixture
def manager(test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _appareils(manager, texte, types_):
    """Un appareil complet par type donné, tous au même texte « Autre réf. »."""
    return manager._batch_insert_devices([{
        'type': t, 'manufacturer': 'Bosch', 'ref_modele': f'ZQA{abs(hash(texte)) % 997}{i:03d}',
        'commercial_ref': '', 'other_ref': texte, 'notes': '', 'category': '',
    } for i, t in enumerate(types_)])


def _importer(manager, lignes, ref_piece="PZZ"):
    manager._preload_existing_devices()
    config = ImportConfiguration(
        files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                          suggested_reference=ref_piece, suggested_label=ref_piece,
                          data=lignes)],
        import_type=ImportType.SINGLE_FILE,
        # Mapping que pose la fenêtre d'import pour 3 colonnes (combo rapide)
        column_mapping={3: ['ref_modele', 'commercial_ref', 'other_ref']},
    )
    return manager._run_import_files(config)


def _suggestions_autre_ref(results):
    return {db_id: [c for c in cands if est_autre_ref(c)]
            for db_id, cands in (results.get('similarity_suggestions') or {}).items()
            if any(est_autre_ref(c) for c in cands)}


class TestImport:

    def test_ligne_sans_type_recoit_le_type_du_texte(self, manager):
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        results = _importer(manager, [['QQWK9001', 'QQWK9001C', TEXTE]])
        (cands,) = _suggestions_autre_ref(results).values()
        assert cands[0]['type'] == "Lave-vaisselle" and cands[0]['manufacturer'] == ''
        assert cands[0]['ref'] == TEXTE and cands[0]['nb_appareils'] == 6

    def test_chemin_batch_gros_import(self, manager):
        """≥ 50 lignes : chemin batch (celui des PDF), distinct du chemin standard."""
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        lignes = [[f'QQWL{i:04d}', f'QQWL{i:04d}C', TEXTE] for i in range(55)]
        trouvees = _suggestions_autre_ref(_importer(manager, lignes))
        assert len(trouvees) == 55
        assert {c[0]['type'] for c in trouvees.values()} == {"Lave-vaisselle"}

    def test_jamais_ecrit_en_base(self, manager):
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        _importer(manager, [['QQWK9001', 'QQWK9001C', TEXTE]])
        rows = manager.db_manager.execute_query(
            "SELECT COALESCE(type, ''), other_ref FROM appareils WHERE ref_modele = 'QQWK9001'")
        assert rows == [('', TEXTE)]

    def test_part_insuffisante(self, manager):
        _appareils(manager, "Hotte encastrable", ["Hotte"] * 5 + ["Lave-linge"])   # 83 %
        results = _importer(manager, [['QQWK9002', 'QQWK9002C', "Hotte encastrable"]])
        assert _suggestions_autre_ref(results) == {}

    def test_interrupteur(self, manager, monkeypatch):
        monkeypatch.setattr(Config, "ENABLE_AUTRE_REF_SUGGESTION", False)
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        results = _importer(manager, [['QQWK9001', 'QQWK9001C', TEXTE]])
        assert _suggestions_autre_ref(results) == {}

    def test_ligne_typee_ignoree(self, manager):
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        d = {'id': 4242, 'ref_modele': 'QQWJ9009', 'type': 'Four', 'other_ref': TEXTE}
        manager._pending_similarity_candidates = [d]
        assert manager._ajouter_suggestions_autre_ref({}) == {}

    def test_erreur_de_lecture_non_bloquante(self, manager, monkeypatch):
        def boom(_textes):
            raise RuntimeError("base indisponible")
        monkeypatch.setattr(manager.db_manager, 'compter_types_par_autre_ref', boom)
        manager._pending_similarity_candidates = [{'id': 1, 'type': '', 'other_ref': TEXTE}]
        deja = {1: [{'type': 'Four'}]}
        assert manager._ajouter_suggestions_autre_ref(deja) == deja


# ── Hors import : clic droit / bouton Suggestions ─────────────────────────────

def _fenetre(db_manager):
    return types.SimpleNamespace(db_manager=db_manager)


class TestHorsImport:

    def test_lectures_groupees(self, manager):
        ids = _appareils(manager, TEXTE, ["Lave-vaisselle"] * 3)
        (sans,) = _appareils(manager, "", [""])
        db = manager.db_manager
        assert db.compter_types_par_autre_ref([TEXTE, "INCONNU", ""]) == {
            TEXTE: {"Lave-vaisselle": 3}}
        assert db.lire_autres_refs_par_id(ids[:1] + [sans, 999999]) == {ids[0]: TEXTE}

    def test_appareil_sans_type_recoit_le_type_du_texte(self, manager):
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        (cible,) = _appareils(manager, TEXTE, [""])
        found = MainWindow._ajouter_suggestions_autre_ref(_fenetre(manager.db_manager), {}, [cible])
        (cand,) = found[cible]
        assert est_autre_ref(cand) and cand['type'] == "Lave-vaisselle"
        assert cand['nb_appareils'] == 6             # l'appareil lui-même ne vote pas

    def test_appareil_deja_type_ignore(self, manager):
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        (cible,) = _appareils(manager, TEXTE, ["Four"])
        assert MainWindow._ajouter_suggestions_autre_ref(
            _fenetre(manager.db_manager), {}, [cible]) == {}

    def test_desactivable(self, manager, monkeypatch):
        monkeypatch.setattr(Config, 'ENABLE_AUTRE_REF_SUGGESTION', False)
        _appareils(manager, TEXTE, ["Lave-vaisselle"] * 6)
        (cible,) = _appareils(manager, TEXTE, [""])
        assert MainWindow._ajouter_suggestions_autre_ref(
            _fenetre(manager.db_manager), {}, [cible]) == {}

    def test_erreur_de_lecture_non_bloquante(self):
        def boom(_ids):
            raise RuntimeError("base indisponible")
        fenetre = _fenetre(types.SimpleNamespace(lire_appareils_par_id=boom))
        deja = {1: [{'type': 'Four'}]}
        assert MainWindow._ajouter_suggestions_autre_ref(fenetre, deja, [1]) == deja


# ── Fenêtre de validation ─────────────────────────────────────────────────────

class TestFenetreValidation:

    def test_ligne_autre_ref(self, qapp):
        from src.ui.fenetre_revue import COL_ETAT, VALIDE, entree
        from src.ui.suggestion_validation_dialog import (
            COL_PREUVE, SuggestionValidationDialog,
        )
        cand = candidat_autre_ref("Réfrigérateur", "Side by side", 1.0, 12)
        snap = [{'db_id': 7, 'ref_modele': '858617701001', 'commercial_ref': '',
                 'current_type': '', 'current_manufacturer': '', 'candidates': [cand]}]
        recus = {}
        dlg = SuggestionValidationDialog(None, snap, lambda d: recus.setdefault('v', d))
        (feuille,) = dlg._feuilles
        assert dlg.etat(feuille) == VALIDE
        assert feuille.text(COL_PREUVE) == "autre réf. 12/12"
        assert dlg._boutons_puces['P_autre_ref'].text().endswith("1")
        assert dlg._cle_groupe(entree(feuille), 'voisin') == (1, "Autre réf. « Side by side »")
        assert dlg._cle_groupe(entree(feuille), 'preuve') == (2, "Autre référence")
        phrase = SuggestionValidationDialog._phrase_preuve(cand)
        assert "12 des 12 appareils typés" in phrase and "pas une certitude" in phrase
        ((db_id, decision),) = dlg.collecter_decisions([feuille])
        assert db_id == 7 and decision['type'] == "Réfrigérateur"
        assert est_autre_ref(decision) and decision['nb_appareils'] == 12
        assert provenance_candidat(decision) == "autre réf. « Side by side » (100%)"
