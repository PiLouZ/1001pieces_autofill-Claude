"""Tests de la fenêtre de validation des suggestions Type/Marque.

Couvre la logique (pré-cochage, choix de candidat, édition à la volée, collecte des
décisions, regroupement) sans dépendre d'un affichage réel (offscreen via qapp).
"""

import pytest
from PyQt5.QtCore import Qt

from src.ui.suggestion_validation_dialog import (
    SuggestionValidationDialog, is_safe_default, tier_label, score_color,
    fiability_colors, COL_CHECK, COL_NEW_TYPE, COL_NEW_MFR,
)

_ROLE_DBID = Qt.UserRole
_ROLE_EDITED = Qt.UserRole + 2


def _cand(type_="Four", mfr="Balay", score=1.0, tier="A_suffix_variant", ref="R/58"):
    return {'ref': ref, 'type': type_, 'manufacturer': mfr, 'score': score,
            'source': 'ref_modele', 'confidence_tier': tier}


def _entry(db_id, candidates, ref="R/01", comm="", cur_type="", cur_mfr=""):
    return {'db_id': db_id, 'ref_modele': ref, 'commercial_ref': comm,
            'current_type': cur_type, 'current_manufacturer': cur_mfr,
            'candidates': candidates}


def _leaf_by_dbid(dlg, db_id):
    return next(lf for lf in dlg._leaves if lf.data(COL_CHECK, _ROLE_DBID) == db_id)


# ── Helpers purs ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_tier_label_mapping(self):
        assert tier_label('A_suffix_variant') == "Quasi-certain"
        assert tier_label('B_fuzzy_alpha') == "Probable"
        assert tier_label('B_fuzzy_numeric') == "Probable"
        assert tier_label('C_prefix_consensus') == "À vérifier"

    def test_score_color_thresholds(self):
        assert score_color(0.95).name() == "#2e7d32"   # vert (fort)
        assert score_color(0.88).name() == "#b06a00"   # ambre (moyen)
        assert score_color(0.85).name() == "#c0392b"   # rouge (faible)
        assert score_color(0.50).name() == "#c0392b"   # rouge

    def test_fiability_colors_red_when_low(self):
        # Score faible (≤ 0,85, ex. consensus de préfixe) → badge ROUGE, pas gris
        assert fiability_colors(1.0) == ("#E8F5E9", "#2e7d32")    # vert
        assert fiability_colors(0.88) == ("#FFF8E1", "#b06a00")   # ambre
        assert fiability_colors(0.85) == ("#FDECEA", "#c0392b")   # rouge

    def test_safe_default_candidat_unique_palier_a(self):
        assert is_safe_default(_entry(1, [_cand(tier='A_suffix_variant', score=1.0)]))

    def test_safe_default_candidat_unique_score_eleve(self):
        assert is_safe_default(_entry(1, [_cand(tier='B_fuzzy_alpha', score=0.95)]))

    def test_pas_safe_si_score_faible(self):
        assert not is_safe_default(_entry(1, [_cand(tier='C_prefix_consensus', score=0.85)]))

    def test_pas_safe_si_concurrence(self):
        assert not is_safe_default(_entry(1, [_cand(score=1.0), _cand(mfr='Siemens', score=0.92)]))


# ── Fenêtre ───────────────────────────────────────────────────────────────────

class TestDialog:
    def _make(self, qapp, snapshot, value_picker=None):
        captured = {}
        dlg = SuggestionValidationDialog(
            None, snapshot, lambda d: captured.setdefault('d', d), value_picker=value_picker)
        return dlg, captured

    def test_precochage_par_defaut(self, qapp):
        snap = [
            _entry(1, [_cand(tier='A_suffix_variant', score=1.0)]),       # sûr → coché
            _entry(2, [_cand(score=0.92), _cand(mfr='Siemens', score=0.88)]),  # concurrence → décoché
            _entry(3, [_cand(tier='C_prefix_consensus', score=0.85)]),    # À vérifier → décoché
        ]
        dlg, _ = self._make(qapp, snap)
        states = {lf.data(COL_CHECK, _ROLE_DBID): lf.checkState(COL_CHECK) == Qt.Checked
                  for lf in dlg._leaves}
        assert states == {1: True, 2: False, 3: False}

    def test_choix_candidat_via_cmdd_remplit_paire_et_coche(self, qapp):
        # value_picker renvoie un candidat (dict) → remplit Type ET Marque
        siemens = _cand(type_='Lave-vaisselle', mfr='Siemens', score=0.88, ref='B/41',
                        tier='B_fuzzy_alpha')
        snap = [_entry(2, [_cand(type_='Lave-vaisselle', mfr='Bosch', score=0.92, ref='A/41'),
                           siemens])]
        dlg, _ = self._make(qapp, snap, value_picker=lambda f, cur, cands: siemens)
        leaf = _leaf_by_dbid(dlg, 2)
        dlg._on_item_double_clicked(leaf, COL_NEW_MFR)
        assert leaf.text(COL_NEW_TYPE) == "Lave-vaisselle"
        assert leaf.text(COL_NEW_MFR) == "Siemens"
        assert leaf.checkState(COL_CHECK) == Qt.Checked

    def test_valeur_libre_via_cmdd_coche_et_marque_modifie(self, qapp):
        # value_picker renvoie une str (valeur libre) → seule la colonne éditée, score neutralisé
        snap = [_entry(3, [_cand(mfr='Balay', tier='C_prefix_consensus', score=0.85)])]
        dlg, _ = self._make(qapp, snap, value_picker=lambda f, cur, cands: "Bosch")
        leaf = _leaf_by_dbid(dlg, 3)
        assert leaf.checkState(COL_CHECK) == Qt.Unchecked
        dlg._on_item_double_clicked(leaf, COL_NEW_MFR)
        assert leaf.text(COL_NEW_MFR) == "Bosch"
        assert leaf.checkState(COL_CHECK) == Qt.Checked
        assert bool(leaf.data(COL_CHECK, _ROLE_EDITED)) is True

    def test_double_clic_sans_picker_ne_plante_pas(self, qapp):
        snap = [_entry(1, [_cand()])]
        dlg, _ = self._make(qapp, snap)  # value_picker=None
        dlg._on_item_double_clicked(_leaf_by_dbid(dlg, 1), COL_NEW_TYPE)  # no-op

    def test_collecte_decisions_seulement_cochees(self, qapp):
        snap = [
            _entry(1, [_cand(type_='Four', mfr='Balay', score=1.0, ref='HE/58')]),
            _entry(2, [_cand(mfr='Bosch', score=0.92), _cand(mfr='Siemens', score=0.88)]),
        ]
        dlg, captured = self._make(qapp, snap)
        # 1 est pré-coché (sûr), 2 non → seule la décision sur db_id 1 doit sortir
        dlg._on_validate_clicked()
        decisions = dict((db, c) for db, c in captured['d'])
        assert set(decisions) == {1}
        assert decisions[1]['type'] == 'Four'
        assert decisions[1]['manufacturer'] == 'Balay'
        assert decisions[1]['ref'] == 'HE/58'

    def test_provenance_suit_le_candidat_choisi(self, qapp):
        siemens = _cand(type_='Lave-vaisselle', mfr='Siemens', score=0.88, ref='B/41',
                        tier='B_fuzzy_alpha')
        snap = [_entry(2, [_cand(type_='Lave-vaisselle', mfr='Bosch', score=0.92, ref='A/41'),
                           siemens])]
        dlg, captured = self._make(qapp, snap, value_picker=lambda f, cur, cands: siemens)
        leaf = _leaf_by_dbid(dlg, 2)
        dlg._on_item_double_clicked(leaf, COL_NEW_MFR)
        dlg._on_validate_clicked()
        decisions = dict((db, c) for db, c in captured['d'])
        assert decisions[2]['manufacturer'] == 'Siemens'
        assert decisions[2]['ref'] == 'B/41'

    def test_regroupement_conserve_les_feuilles(self, qapp):
        snap = [
            _entry(1, [_cand(tier='A_suffix_variant', score=1.0)]),
            _entry(2, [_cand(tier='B_fuzzy_alpha', score=0.92)]),
            _entry(3, [_cand(tier='C_prefix_consensus', score=0.85)]),
        ]
        dlg, _ = self._make(qapp, snap)
        dlg._group_combo.setCurrentIndex(1)  # par fiabilité
        assert len(dlg._leaves) == 3
        # 3 nœuds-groupes au premier niveau
        root = dlg._tree.invisibleRootItem()
        assert root.childCount() == 3

    def test_copie_des_references_selectionnees(self, qapp):
        from PyQt5.QtWidgets import QApplication
        snap = [_entry(1, [_cand()], ref='HBA572EM3/01'),
                _entry(2, [_cand()], ref='AD249XE11'),
                _entry(3, [_cand()], ref='AHLN6W5E1')]
        dlg, _ = self._make(qapp, snap)
        # Sélectionner deux feuilles puis copier
        _leaf_by_dbid(dlg, 1).setSelected(True)
        _leaf_by_dbid(dlg, 3).setSelected(True)
        assert dlg._selected_refs() == ['HBA572EM3/01', 'AHLN6W5E1']
        dlg._copy_selected_refs()
        assert QApplication.clipboard().text() == 'HBA572EM3/01\nAHLN6W5E1'

    def test_tout_cocher_decocher(self, qapp):
        snap = [_entry(i, [_cand(score=0.92, tier='B_fuzzy_alpha')]) for i in (1, 2, 3)]
        dlg, _ = self._make(qapp, snap)
        dlg._set_all_checked(True)
        assert all(lf.checkState(COL_CHECK) == Qt.Checked for lf in dlg._leaves)
        dlg._set_all_checked(False)
        assert all(lf.checkState(COL_CHECK) == Qt.Unchecked for lf in dlg._leaves)
