"""Tests — « Remplacée par » sur les cartes de l'import multi-fichiers (v3.97.0).

Cas réel du 2026-10-23 : trois PDF Beko importés ensemble, chacun remplacé par
une réf différente, toutes menant au final à C00904134 :
    2808540500 → C00904139 → C00904134
    2808530300 → C00923922 → C00904134
    2808540300 → C00904134
Avant, une lignée reliait toutes les réfs directement à la courante : l'étape
intermédiaire (C00904139, C00923922) était perdue. Le premier niveau se saisit
désormais sur la carte, le second par une lignée dont les intermédiaires sont
les anciennes versions saisies hors lot.
"""

import pytest

from src.services.import_relations import (
    Group, CardData, derive, apply_relations, count_planned_relations,
    conflits_remplacement, successions_prevues, KIND_SUCCESSION,
)

LOT = ("2808540500", "2808530300", "2808540300")


def _cas_beko():
    cards = [CardData("2808540500", replaced_by="C00904139"),
             CardData("2808530300", replaced_by="C00923922"),
             CardData("2808540300", replaced_by="C00904134")]
    groups = [Group(KIND_SUCCESSION, courante="C00904134",
                    members=["C00904139", "C00923922"])]
    return groups, cards


class FakeDB:
    def __init__(self, refus=()):
        self.supersessions, self.equivalences, self.obsoletes = [], [], []
        self.refus = set(refus)

    def add_supersession(self, old, new):
        if (old, new) in self.refus:
            return False, "cycle"
        self.supersessions.append((old, new)); return True, ""

    def add_equivalence(self, a, b):
        self.equivalences.append((a, b)); return True, ""

    def mark_obsolete(self, ref):
        self.obsoletes.append(ref); return True


# ── Modèle ────────────────────────────────────────────────────────────────────

class TestModele:

    def test_apply_cas_beko(self):
        groups, cards = _cas_beko()
        counts = apply_relations(groups, cards, db := FakeDB())
        assert set(db.supersessions) == {
            ("2808540500", "C00904139"), ("2808530300", "C00923922"),
            ("2808540300", "C00904134"),
            ("C00904139", "C00904134"), ("C00923922", "C00904134")}
        assert set(db.obsoletes) == set(LOT) | {"C00904139", "C00923922"}
        assert counts['successions'] == 5 and counts['obsoletes'] == 5

    def test_count_miroir_apply(self):
        groups, cards = _cas_beko()
        planned = count_planned_relations(groups, cards)
        applied = apply_relations(groups, cards, FakeDB())
        for cle in ('successions', 'equivalences', 'obsoletes'):
            assert planned[cle] == applied[cle]

    def test_derive_obsoletes_et_fantomes(self):
        groups, cards = _cas_beko()
        d = derive(groups, cards, set(LOT), base_refs=set())
        assert d.obsoletes == set(LOT) | {"C00904139", "C00923922"}
        assert d.phantoms == {"C00904139", "C00923922", "C00904134"}
        assert d.warnings == []

    def test_remplacee_par_elle_meme_ignoree(self):
        cards = [CardData("A", replaced_by="A")]
        assert count_planned_relations([], cards)['successions'] == 0
        apply_relations([], cards, db := FakeDB())
        assert db.supersessions == [] and db.obsoletes == []

    def test_carte_sans_remplacante_inchangee(self):
        """Non-régression : une carte sans « Remplacée par » ne crée rien de plus."""
        apply_relations([], [CardData("A"), CardData("B", is_obsolete=True)], db := FakeDB())
        assert db.supersessions == [] and db.obsoletes == ["B"]

    def test_journal(self):
        groups, cards = _cas_beko()
        journal = []
        apply_relations(groups, cards, FakeDB(refus={("2808540300", "C00904134")}),
                        journal=journal)
        assert "2808540500 → C00904139" in journal
        assert "2808540300 → C00904134 refusé : cycle" in journal

    def test_successions_prevues_sans_doublon(self):
        """Carte « remplacée par » = courante de la lignée où elle figure : un seul lien."""
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A"])]
        cards = [CardData("A", replaced_by="C")]
        assert successions_prevues(groups, cards) == [("A", "C")]


class TestConflits:

    def test_aucun_conflit_cas_beko(self):
        assert conflits_remplacement(*_cas_beko()) == []

    def test_meme_remplacante_deux_fois_pas_un_conflit(self):
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A"])]
        assert conflits_remplacement(groups, [CardData("A", replaced_by="C")]) == []

    def test_deux_remplacantes(self):
        """Carte « remplacée par B » mais placée dans une lignée de courante C."""
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A"])]
        msgs = conflits_remplacement(groups, [CardData("A", replaced_by="B")])
        assert len(msgs) == 1 and "A" in msgs[0] and "B" in msgs[0] and "C" in msgs[0]

    def test_boucle(self):
        cards = [CardData("A", replaced_by="B"), CardData("B", replaced_by="A")]
        msgs = conflits_remplacement([], cards)
        assert len(msgs) == 1 and msgs[0].startswith("Boucle")

    def test_boucle_via_lignee(self):
        groups = [Group(KIND_SUCCESSION, courante="A", members=["B"])]
        msgs = conflits_remplacement(groups, [CardData("A", replaced_by="B")])
        assert any(m.startswith("Boucle") for m in msgs)

    def test_derive_remonte_les_conflits(self):
        cards = [CardData("A", replaced_by="B"), CardData("B", replaced_by="A")]
        d = derive([], cards, {"A", "B"}, set())
        assert any(m.startswith("Boucle") for _, m in d.warnings)


class TestBaseReelle:

    def test_chaine_complete_conservee(self, test_db_manager):
        groups, cards = _cas_beko()
        counts = apply_relations(groups, cards, test_db_manager)
        assert counts['errors'] == 0
        assert test_db_manager.get_supersession_chain("2808540500") == [
            "2808540500", "C00904139", "C00904134"]
        assert test_db_manager.get_supersession_chain("2808530300") == [
            "2808530300", "C00923922", "C00904134"]
        assert test_db_manager.get_supersession_chain("2808540300") == [
            "2808540300", "C00904134"]
        assert set(test_db_manager.get_all_predecessors("C00904134")) == \
            set(LOT) | {"C00904139", "C00923922"}
        obs = dict(test_db_manager.execute_query(
            "SELECT ref_piece, is_obsolete FROM pieces") or [])
        assert obs["C00904134"] == 0
        assert all(obs[r] == 1 for r in set(LOT) | {"C00904139", "C00923922"})


# ── Dialogue d'import ─────────────────────────────────────────────────────────

class TestDialogue:

    def _dialog(self, test_db_manager, refs=LOT):
        from src.core.import_manager import (
            ImportManager, ImportDialog, ImportConfiguration, ImportFile,
            ImportType, FileType)
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        files = [ImportFile(f'/{r}.pdf', FileType.CSV, r) for r in refs]
        # Données pré-renseignées : évite la lecture disque du chargement différé.
        for f in files:
            f.data = [['Référence', 'Type', 'Marque'], [f.suggested_reference, 'Lave-linge', 'Beko']]
        cfg = ImportConfiguration(files=files, import_type=ImportType.MULTI_FILE)
        dlg = ImportDialog(None, cfg, im)
        dlg.auto_file_references_checkbox.setChecked(True)
        # Les cartes de fichiers naissent au chargement différé (QTimer) :
        # le déclencher tout de suite.
        dlg._load_data_deferred()
        return dlg

    def _champ(self, dlg, ref):
        for chips, f in dlg._remplacee_par_inputs:
            if f.suggested_reference == ref:
                return chips
        raise AssertionError(ref)

    def _obs(self, dlg, ref):
        for check, f in dlg._obsolete_checkboxes:
            if f.suggested_reference == ref:
                return check
        raise AssertionError(ref)

    def test_un_champ_par_carte(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        assert len(dlg._remplacee_par_inputs) == 3

    def test_obsolete_d_office_puis_rendue(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        chips, obs = self._champ(dlg, "2808540500"), self._obs(dlg, "2808540500")
        assert not obs.isChecked() and obs.isEnabled()
        chips.add_refs(["C00904139"])
        assert obs.isChecked() and not obs.isEnabled()
        chips.remove_ref("C00904139")
        assert not obs.isChecked() and obs.isEnabled()

    def test_obsolete_cochee_avant_reste_cochee(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        chips, obs = self._champ(dlg, "2808540500"), self._obs(dlg, "2808540500")
        obs.setChecked(True)
        chips.add_refs(["C00904139"])
        chips.remove_ref("C00904139")
        assert obs.isChecked() and obs.isEnabled()

    def test_une_seule_remplacante(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        chips = self._champ(dlg, "2808540500")
        chips.add_refs(["C00904139", "C00904134"])
        assert chips.refs() == ["C00904139"]

    def test_recap_compte_les_remplacements(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        assert z.planned_counts()['successions'] == 0
        self._champ(dlg, "2808540500").add_refs(["C00904139"])
        assert z.planned_counts()['successions'] == 1
        assert "1 succession" in z.recap_label.text()

    def test_validation_collecte_replaced_by(self, qapp, test_db_manager):
        from src.services.import_relations import KIND_SUCCESSION
        dlg = self._dialog(test_db_manager)
        for ref, nouvelle in (("2808540500", "C00904139"), ("2808530300", "C00923922"),
                              ("2808540300", "C00904134")):
            self._champ(dlg, ref).add_refs([nouvelle])
        z = dlg._relations_groups_zone
        box = z._succ_boxes[0]
        box.courante_input.setText("C00904134")
        z.ajouter_refs(box, ["C00904139", "C00923922"])
        dlg._validate_and_accept()
        rc = dlg.result_config
        assert rc is not None
        assert {c.ref: c.replaced_by for c in rc.relations_cards} == {
            "2808540500": "C00904139", "2808530300": "C00923922",
            "2808540300": "C00904134"}
        assert count_planned_relations(rc.relations_groups, rc.relations_cards) == {
            'successions': 5, 'equivalences': 0, 'obsoletes': 5}

    def test_texte_tape_non_valide_collecte(self, qapp, test_db_manager):
        """Réf tapée sans Espace ni Entrée avant « Importer » : pas perdue."""
        dlg = self._dialog(test_db_manager)
        self._champ(dlg, "2808540500").line_edit.setText("C00904139")
        dlg._validate_and_accept()
        cartes = {c.ref: c.replaced_by for c in dlg.result_config.relations_cards}
        assert cartes["2808540500"] == "C00904139"

    def test_conflit_bloque_la_validation(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        self._champ(dlg, "2808540500").add_refs(["2808530300"])
        self._champ(dlg, "2808530300").add_refs(["2808540500"])
        z = dlg._relations_groups_zone
        assert z.warnings_label.isVisibleTo(z)
        assert "Boucle" in z.warnings_label.text()
        dlg._validate_and_accept()
        assert dlg.result_config is None
