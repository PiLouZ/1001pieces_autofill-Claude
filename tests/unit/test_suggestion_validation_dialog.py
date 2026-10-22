"""Tests de la fenêtre « Valider les suggestions » (refonte v3.94.0).

Couvre la logique (état initial, choix de candidat, correction, collecte des
décisions et des refus, regroupement, puces, raccourcis, panneau de détail,
application sans fermeture) sans affichage réel (offscreen via qapp).
"""

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication

from src.services.reference_similarity_service import (
    pourcent, risques_suggestion, texte_preuve,
)
from src.ui.fenetre_revue import (
    VALIDE, REFUSE, ATTENTE, COL_ETAT, entree, lignes_vote, phrase_abstention, verdict_pieces,
)
from src.ui.suggestion_validation_dialog import (
    SuggestionValidationDialog, is_safe_default, tier_label, score_color,
    fiability_colors, COL_REF, COL_NEW_TYPE, COL_NEW_MFR, COL_PREUVE, COL_RISQUE,
)


def _cand(type_="Four", mfr="Balay", score=1.0, tier="A_suffix_variant", ref="R/58", **extra):
    return dict({'ref': ref, 'type': type_, 'manufacturer': mfr, 'score': score,
                 'source': 'ref_modele', 'confidence_tier': tier}, **extra)


def _entry(db_id, candidates, ref="R/01", comm="", cur_type="", cur_mfr=""):
    return {'db_id': db_id, 'ref_modele': ref, 'commercial_ref': comm,
            'current_type': cur_type, 'current_manufacturer': cur_mfr,
            'candidates': candidates}


def _feuille(dlg, db_id):
    return next(it for it in dlg._feuilles if entree(it)['db_id'] == db_id)


def _etats(dlg):
    return {entree(it)['db_id']: dlg.etat(it) for it in dlg._feuilles}


def _touche(dlg, touche, mods=Qt.NoModifier):
    dlg._arbre.setFocus()
    QApplication.sendEvent(dlg._arbre, QKeyEvent(QEvent.KeyPress, touche, mods))


# ── Helpers purs ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_tier_label_mapping(self):
        assert tier_label('A_suffix_variant') == "Quasi-certain"
        assert tier_label('B_fuzzy_alpha') == "Probable"
        assert tier_label('B_fuzzy_numeric') == "Probable"
        assert tier_label('C_prefix_consensus') == "À vérifier"

    def test_score_color_thresholds(self):
        assert score_color(0.95).name() == "#2e7d32"
        assert score_color(0.88).name() == "#b06a00"
        assert score_color(0.85).name() == "#c0392b"
        assert score_color(0.50).name() == "#c0392b"

    def test_fiability_colors_red_when_low(self):
        assert fiability_colors(1.0) == ("#E8F5E9", "#2e7d32")
        assert fiability_colors(0.88) == ("#FFF8E1", "#b06a00")
        assert fiability_colors(0.85) == ("#FDECEA", "#c0392b")

    def test_safe_default_candidat_unique_palier_a(self):
        assert is_safe_default(_entry(1, [_cand(tier='A_suffix_variant', score=1.0)]))

    def test_safe_default_candidat_unique_score_eleve(self):
        assert is_safe_default(_entry(1, [_cand(tier='B_fuzzy_alpha', score=0.95)]))

    def test_pas_safe_si_score_faible(self):
        assert not is_safe_default(_entry(1, [_cand(tier='C_prefix_consensus', score=0.85)]))

    def test_pas_safe_si_concurrence(self):
        assert not is_safe_default(_entry(1, [_cand(score=1.0), _cand(mfr='Siemens', score=0.92)]))

    def test_texte_preuve_avec_unite(self):
        assert pourcent(0.92) == "92 %"
        assert texte_preuve(_cand()) == "même réf."
        assert texte_preuve(_cand(tier='B_fuzzy_alpha', score=0.92)) == "réf. 92 %"
        assert texte_preuve(_cand(tier='C_prefix_consensus', score=0.85, nb_accord=18,
                                  nb_famille=19, prefixe='FSS6')) == "préfixe 18/19"
        assert texte_preuve(_cand(tier='P_type_piece', score=1.0, nb_appareils=12)) == "pièce 12/12"

    def test_risques(self):
        assert risques_suggestion([_cand()]) == []
        assert risques_suggestion([_cand(), _cand(type_='Hotte', mfr='Elica')]) == [
            "2 candidats concurrents (types et marques différents)"]
        assert "famille de références" in risques_suggestion(
            [_cand(tier='C_prefix_consensus', score=0.85)])[0]
        assert risques_suggestion([_cand(tier='B_fuzzy_alpha', score=0.82)]) == [
            "ressemblance de référence faible"]

    def test_verdict_des_pieces(self):
        preuves = {'nb_pieces': 3, 'paires': [('Four vapeur', 'Bosch', 12), ('Four', 'Bosch', 1)]}
        assert verdict_pieces('Four', preuves)[0] == 'contredit'
        assert verdict_pieces('four vapeur', preuves)[0] == 'confirme'
        assert verdict_pieces('Bosch', preuves, 'manufacturer')[0] == 'confirme'
        partage = {'nb_pieces': 2, 'paires': [('Four', 'X', 5), ('Hotte', 'Y', 5)]}
        assert verdict_pieces('Four', partage)[0] is None
        assert verdict_pieces('Four', {'nb_pieces': 0, 'paires': []}) == (None, None, 0.0, 0)

    def test_verdict_s_abstient_sous_5_appareils(self):
        """3 appareils à 67 % ne prouvent rien (même seuil que le palier « type de la pièce »)."""
        peu = {'nb_pieces': 1, 'paires': [('Lave-linge', 'W', 2), ('Four', 'B', 1), ('', '', 4)]}
        assert verdict_pieces('Four', peu)[0] is None
        assert phrase_abstention(0.67, 3) == "trop peu d'appareils typés pour trancher (3)"
        assert phrase_abstention(0.5, 10) == "vote trop partagé pour trancher"
        assert lignes_vote(peu) == "Lave-linge / W (2), Four / B (1)"     # sans les appareils vides


# ── Fenêtre ───────────────────────────────────────────────────────────────────

class TestDialog:
    def _make(self, qapp, snapshot, value_picker=None, preuves=None):
        recus = {}
        dlg = SuggestionValidationDialog(
            None, snapshot, lambda d: recus.setdefault('valides', d), value_picker=value_picker,
            on_refuse=lambda r: recus.setdefault('refus', r), preuves=preuves)
        return dlg, recus

    def test_etat_initial(self, qapp):
        snap = [_entry(1, [_cand(tier='A_suffix_variant', score=1.0)]),
                _entry(2, [_cand(score=0.92), _cand(mfr='Siemens', score=0.88)]),
                _entry(3, [_cand(tier='C_prefix_consensus', score=0.85)])]
        dlg, _ = self._make(qapp, snap)
        assert _etats(dlg) == {1: VALIDE, 2: ATTENTE, 3: ATTENTE}
        assert dlg._btn_appliquer.text() == "Appliquer (1)"

    def test_choix_candidat_via_cmdd_remplit_paire_et_valide(self, qapp):
        siemens = _cand(type_='Lave-vaisselle', mfr='Siemens', score=0.88, ref='B/41',
                        tier='B_fuzzy_alpha')
        snap = [_entry(2, [_cand(type_='Lave-vaisselle', mfr='Bosch', score=0.92, ref='A/41'),
                           siemens])]
        dlg, _ = self._make(qapp, snap, value_picker=lambda f, cur, cands: siemens)
        feuille = _feuille(dlg, 2)
        dlg._on_double_clic(feuille, COL_NEW_MFR)
        assert (feuille.text(COL_NEW_TYPE), feuille.text(COL_NEW_MFR)) == ("Lave-vaisselle", "Siemens")
        assert dlg.etat(feuille) == VALIDE

    def test_valeur_libre_marque_corrige(self, qapp):
        snap = [_entry(3, [_cand(mfr='Balay', tier='C_prefix_consensus', score=0.85)])]
        dlg, _ = self._make(qapp, snap, value_picker=lambda f, cur, cands: "Bosch")
        feuille = _feuille(dlg, 3)
        dlg._on_double_clic(feuille, COL_NEW_MFR)
        assert feuille.text(COL_NEW_MFR) == "Bosch"
        assert dlg.etat(feuille) == VALIDE
        assert feuille.text(COL_PREUVE) == "corrigé"

    def test_entree_corrige_le_type(self, qapp):
        champs = []
        snap = [_entry(1, [_cand(tier='B_fuzzy_alpha', score=0.92)])]
        dlg, _ = self._make(qapp, snap, value_picker=lambda f, cur, c: champs.append(f) or "Hotte")
        dlg._arbre.setCurrentItem(_feuille(dlg, 1))
        _touche(dlg, Qt.Key_Return)
        assert champs == ['type'] and _feuille(dlg, 1).text(COL_NEW_TYPE) == "Hotte"

    def test_double_clic_sans_picker_ne_plante_pas(self, qapp):
        dlg, _ = self._make(qapp, [_entry(1, [_cand()])])
        dlg._on_double_clic(_feuille(dlg, 1), COL_NEW_TYPE)

    def test_appliquer_remet_valides_et_refus_sans_fermer(self, qapp):
        snap = [_entry(1, [_cand(type_='Four', mfr='Balay', score=1.0, ref='HE/58')]),
                _entry(2, [_cand(mfr='Bosch', score=0.92), _cand(mfr='Siemens', score=0.88)]),
                _entry(3, [_cand(tier='B_fuzzy_alpha', score=0.88)])]
        dlg, recus = self._make(qapp, snap)
        dlg.show()
        dlg.decider(REFUSE, [_feuille(dlg, 2)])
        dlg._on_appliquer()
        assert [(db, c['manufacturer'], c['ref']) for db, c in recus['valides']] == [(1, 'Balay', 'HE/58')]
        assert [(db, len(cands)) for db, cands in recus['refus']] == [(2, 2)]
        assert dlg.isVisible() and _etats(dlg) == {3: ATTENTE}   # décidées retirées
        assert dlg._titre.text().endswith("1 suggestion")

    def test_derniere_decision_ferme_la_fenetre(self, qapp):
        dlg, recus = self._make(qapp, [_entry(1, [_cand()])])
        dlg.show()
        dlg._on_appliquer()
        assert not dlg.isVisible() and len(recus['valides']) == 1

    def test_provenance_suit_le_candidat_choisi(self, qapp):
        siemens = _cand(type_='Lave-vaisselle', mfr='Siemens', score=0.88, ref='B/41',
                        tier='B_fuzzy_alpha')
        snap = [_entry(2, [_cand(type_='Lave-vaisselle', mfr='Bosch', score=0.92, ref='A/41'),
                           siemens])]
        dlg, recus = self._make(qapp, snap, value_picker=lambda f, cur, cands: siemens)
        dlg._on_double_clic(_feuille(dlg, 2), COL_NEW_MFR)
        dlg._on_appliquer()
        (db, cand), = recus['valides']
        assert (cand['manufacturer'], cand['ref']) == ('Siemens', 'B/41')

    def test_type_de_la_piece_garde_sa_provenance(self, qapp):
        piece = _cand(type_='Four', mfr='', score=1.0, tier='P_type_piece', ref='PF', nb_appareils=6)
        dlg, recus = self._make(qapp, [_entry(1, [piece])])
        dlg._on_appliquer()
        (_, cand), = recus['valides']
        assert cand['confidence_tier'] == 'P_type_piece' and cand['nb_appareils'] == 6

    def test_prendre_un_autre_candidat(self, qapp):
        snap = [_entry(1, [_cand(type_='Four', mfr='Bosch', tier='B_fuzzy_alpha', score=0.92),
                           _cand(type_='Four vapeur', mfr='', tier='P_type_piece', ref='P1',
                                 nb_appareils=12)])]
        dlg, _ = self._make(qapp, snap)
        feuille = _feuille(dlg, 1)
        assert "prendre:1" in dlg._html_detail(feuille, None)
        assert "prendre:0" not in dlg._html_detail(feuille, None)   # le retenu n'est pas « autre »
        dlg._on_lien('prendre:1', feuille)
        assert feuille.text(COL_NEW_TYPE) == "Four vapeur" and dlg.etat(feuille) == VALIDE

    def test_regroupement_par_preuve_par_defaut(self, qapp):
        snap = [_entry(1, [_cand(tier='A_suffix_variant')]),
                _entry(2, [_cand(tier='B_fuzzy_alpha', score=0.92)]),
                _entry(3, [_cand(tier='C_prefix_consensus', score=0.85)])]
        dlg, _ = self._make(qapp, snap)
        racine = dlg._arbre.invisibleRootItem()
        assert [racine.child(i).text(COL_ETAT) for i in range(racine.childCount())] == [
            "Même référence à un suffixe près — 1", "Référence voisine — 1",
            "Famille de préfixe — 1"]
        dlg._combo_groupe.setCurrentIndex(3)   # Aucun
        assert racine.childCount() == 3 and len(dlg._feuilles) == 3

    def test_decision_sur_un_groupe(self, qapp):
        snap = [_entry(i, [_cand(tier='B_fuzzy_alpha', score=0.88)]) for i in (1, 2)] + \
               [_entry(3, [_cand(tier='C_prefix_consensus', score=0.85)])]
        dlg, _ = self._make(qapp, snap)
        groupe = dlg._arbre.invisibleRootItem().child(0)
        dlg._arbre.setCurrentItem(groupe)
        groupe.setSelected(True)
        _touche(dlg, Qt.Key_V)
        assert _etats(dlg) == {1: VALIDE, 2: VALIDE, 3: ATTENTE}

    def test_regroupement_conserve_les_decisions(self, qapp):
        snap = [_entry(i, [_cand(tier='B_fuzzy_alpha', score=0.88)]) for i in (1, 2)]
        dlg, _ = self._make(qapp, snap)
        dlg.decider(REFUSE, [_feuille(dlg, 2)])
        dlg._combo_groupe.setCurrentIndex(1)
        assert _etats(dlg) == {1: ATTENTE, 2: REFUSE}

    def test_raccourcis_et_ligne_suivante(self, qapp):
        snap = [_entry(i, [_cand(tier='B_fuzzy_alpha', score=0.88)]) for i in (1, 2, 3)]
        dlg, _ = self._make(qapp, snap)
        dlg._arbre.setCurrentItem(_feuille(dlg, 1))
        _touche(dlg, Qt.Key_R)
        assert dlg.etat(_feuille(dlg, 1)) == REFUSE
        assert dlg._arbre.currentItem() is _feuille(dlg, 2)        # en attente suivante
        _touche(dlg, Qt.Key_Space)
        assert dlg.etat(_feuille(dlg, 2)) == VALIDE
        dlg._arbre.setCurrentItem(_feuille(dlg, 1))
        _touche(dlg, Qt.Key_U)
        assert dlg.etat(_feuille(dlg, 1)) == ATTENTE

    def test_clic_sur_l_etat_fait_tourner(self, qapp):
        dlg, _ = self._make(qapp, [_entry(1, [_cand(tier='B_fuzzy_alpha', score=0.88)])])
        feuille = _feuille(dlg, 1)
        vus = []
        for _ in range(3):
            dlg._on_clic(feuille, COL_ETAT)
            vus.append(dlg.etat(feuille))
        assert vus == [VALIDE, REFUSE, ATTENTE]

    def test_puces_filtrent_et_comptent(self, qapp):
        snap = [_entry(1, [_cand(tier='A_suffix_variant')]),
                _entry(2, [_cand(tier='B_fuzzy_alpha', score=0.92), _cand(mfr='X', score=0.9)]),
                _entry(3, [_cand(tier='C_prefix_consensus', score=0.85)])]
        dlg, _ = self._make(qapp, snap)
        assert dlg._boutons_puces['risque'].text() == "⚠ À risque  2"
        assert dlg._boutons_puces['P_type_piece'].isHidden()
        dlg._choisir_puce('risque')
        assert {entree(it)['db_id'] for it in dlg._feuilles
                if not it.isHidden()} == {2, 3}
        assert _feuille(dlg, 2).text(COL_RISQUE) == "⚠"

    def test_filtre_texte_cherche_aussi_le_voisin(self, qapp):
        snap = [_entry(1, [_cand(ref='VOISIN-XYZ')]), _entry(2, [_cand(ref='AUTRE')])]
        dlg, _ = self._make(qapp, snap)
        dlg._filtre.setText("xyz")
        assert [it.isHidden() for it in (_feuille(dlg, 1), _feuille(dlg, 2))] == [False, True]

    def test_detail_preuve_et_pieces_paresseuses(self, qapp):
        lus = []

        def preuves(entree):
            lus.append(entree['db_id'])
            return {'nb_pieces': 6, 'paires': [('Four vapeur', 'Bosch', 12), ('Four', 'Bosch', 1)]}
        snap = [_entry(1, [_cand(tier='C_prefix_consensus', score=0.85, ref='FSS6302',
                                 nb_accord=18, nb_famille=19, prefixe='FSS6')])]
        dlg, _ = self._make(qapp, snap, preuves=preuves)
        texte = dlg._detail.toPlainText()
        assert "18 appareils sur 19" in texte and "Contredisent" in texte
        dlg._maj_detail(_feuille(dlg, 1))
        assert lus == [1]                                        # une seule lecture (cache)

    def test_copie_des_references_selectionnees(self, qapp):
        snap = [_entry(1, [_cand()], ref='HBA572EM3/01'), _entry(2, [_cand()], ref='AD249XE11'),
                _entry(3, [_cand()], ref='AHLN6W5E1')]
        dlg, _ = self._make(qapp, snap)
        dlg._arbre.clearSelection()
        _feuille(dlg, 1).setSelected(True)
        _feuille(dlg, 3).setSelected(True)
        assert dlg._references_selectionnees() == ['HBA572EM3/01', 'AHLN6W5E1']
        dlg._copier_references()
        assert QApplication.clipboard().text() == 'HBA572EM3/01\nAHLN6W5E1'

    def test_fermer_avec_decisions_demande_confirmation(self, qapp):
        dlg, recus = self._make(qapp, [_entry(1, [_cand(tier='B_fuzzy_alpha', score=0.88)])])
        dlg.show()
        dlg.reject()                                    # rien décidé : ferme
        assert not dlg.isVisible()
        dlg, recus = self._make(qapp, [_entry(1, [_cand(tier='B_fuzzy_alpha', score=0.88)])])
        dlg.show()
        dlg.decider(VALIDE, [_feuille(dlg, 1)])
        dlg.reject()
        assert dlg.isVisible() and dlg._confirmation.isVisible()
        appliquer = dlg._confirmation.buttons()[0]
        dlg._confirmation.buttonClicked.emit(appliquer)
        assert not dlg.isVisible() and len(recus['valides']) == 1
