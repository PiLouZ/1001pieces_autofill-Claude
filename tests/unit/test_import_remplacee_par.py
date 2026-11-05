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
        """A remplacée par B (carte), puis A placée dans la lignée de C et B dans
        celle de D : la fin de chaîne B irait vers C et vers D."""
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A"]),
                  Group(KIND_SUCCESSION, courante="D", members=["B"])]
        msgs = conflits_remplacement(groups, [CardData("A", replaced_by="B")])
        assert len(msgs) == 1 and "B" in msgs[0] and "C" in msgs[0] and "D" in msgs[0]

    def test_deux_remplacantes_hors_lignee(self):
        """Ancien comportement conservé pour « remplace » base : OLD → R (carte R)
        et OLD membre d'une lignée de courante C."""
        groups = [Group(KIND_SUCCESSION, courante="C", members=["OLD"])]
        msgs = conflits_remplacement(groups, [CardData("R", base_replaces="OLD")])
        assert len(msgs) == 1 and "OLD" in msgs[0]


# ── Raccord automatique dans la lignée (v3.97.1) ──────────────────────────────

class TestRaccordLignee:

    def _cas_glisse(self):
        """Saisie naturelle : les 3 fichiers glissés dans la lignée, remplaçantes
        uniquement sur les cartes (rien de ressaisi dans la lignée)."""
        cards = [CardData("2808540500", replaced_by="C00904139"),
                 CardData("2808530300", replaced_by="C00923922"),
                 CardData("2808540300", replaced_by="C00904134")]
        groups = [Group(KIND_SUCCESSION, courante="C00904134", members=list(LOT))]
        return groups, cards

    def test_aucun_conflit(self):
        assert conflits_remplacement(*self._cas_glisse()) == []

    def test_meme_resultat_que_la_saisie_complete(self):
        """Glisser les fichiers = saisir les intermédiaires à la main."""
        assert set(successions_prevues(*self._cas_glisse())) == \
            set(successions_prevues(*_cas_beko()))

    def test_apply_et_count_miroirs(self):
        groups, cards = self._cas_glisse()
        planned = count_planned_relations(groups, cards)
        applied = apply_relations(groups, cards, db := FakeDB())
        assert set(db.supersessions) == {
            ("2808540500", "C00904139"), ("2808530300", "C00923922"),
            ("2808540300", "C00904134"),
            ("C00904139", "C00904134"), ("C00923922", "C00904134")}
        assert len(db.supersessions) == 5          # pas de doublon 2808540300 → C00904134
        for cle in ('successions', 'equivalences', 'obsoletes'):
            assert planned[cle] == applied[cle]
        assert set(db.obsoletes) == set(LOT) | {"C00904139", "C00923922"}

    def test_derive_marque_les_fins_obsoletes(self):
        d = derive(*self._cas_glisse(), set(LOT), set())
        assert {"C00904139", "C00923922"} <= d.obsoletes

    def test_raccords_lignee(self):
        from src.services.import_relations import raccords_lignee, remplacantes_des_cartes
        groups, cards = self._cas_glisse()
        r = raccords_lignee(groups[0], remplacantes_des_cartes(cards))
        assert r == {"2808540500": "C00904139", "2808530300": "C00923922",
                     "2808540300": "C00904134"}

    def test_chaine_de_cartes_raccordee_par_sa_fin(self):
        """A → B (carte), B → X (carte), A dans la lignée de C : X → C."""
        cards = [CardData("A", replaced_by="B"), CardData("B", replaced_by="X")]
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A"])]
        assert set(successions_prevues(groups, cards)) == {("A", "B"), ("B", "X"), ("X", "C")}

    def test_membre_sans_carte_inchange(self):
        """Non-régression : membre sans remplaçante → membre → courante."""
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A", "B"])]
        assert successions_prevues(groups, [CardData("A")]) == [("A", "C"), ("B", "C")]

    def test_boucle_de_cartes_non_raccordee(self):
        cards = [CardData("A", replaced_by="B"), CardData("B", replaced_by="A")]
        groups = [Group(KIND_SUCCESSION, courante="C", members=["A"])]
        liens = successions_prevues(groups, cards)
        assert ("A", "C") not in liens and ("B", "C") not in liens
        assert any(m.startswith("Boucle") for m in conflits_remplacement(groups, cards))

    def test_chaine_complete_en_base(self, test_db_manager):
        groups, cards = self._cas_glisse()
        assert apply_relations(groups, cards, test_db_manager)['errors'] == 0
        assert test_db_manager.get_supersession_chain("2808540500") == [
            "2808540500", "C00904139", "C00904134"]


class TestArbre:

    def test_arbre_cas_beko(self):
        from src.services.import_relations import arbre_remplacements
        foret = arbre_remplacements(*_cas_beko())
        assert len(foret) == 1
        racine, enfants = foret[0]
        assert racine == "C00904134"
        assert {e for e, _ in enfants} == {"C00904139", "C00923922", "2808540300"}
        sous = dict(enfants)
        assert [e for e, _ in sous["C00904139"]] == ["2808540500"]
        assert [e for e, _ in sous["C00923922"]] == ["2808530300"]

    def test_arbre_vide_sans_lien(self):
        from src.services.import_relations import arbre_remplacements
        assert arbre_remplacements([], [CardData("A")]) == []

    def test_boucle_absente_de_l_arbre(self):
        from src.services.import_relations import arbre_remplacements
        cards = [CardData("A", replaced_by="B"), CardData("B", replaced_by="A")]
        assert arbre_remplacements([], cards) == []

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

class _AideDialogue:

    def _dialog(self, test_db_manager, refs=LOT):
        from src.core.import_manager import ImportManager, ImportConfiguration, ImportFile, ImportType, FileType
        from src.ui.fenetre_import import ImportDialog
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


class TestDialogue(_AideDialogue):

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


# ── Dialogue : raccord, arbre et glisser-déposer (v3.97.1) ────────────────────

def _deposer(cible, texte):
    """Simuler le dépôt d'un texte venu de l'extérieur des listes (source None)."""
    from PyQt5.QtCore import QMimeData, QPoint, Qt
    from PyQt5.QtGui import QDropEvent
    md = QMimeData()
    md.setText(texte)
    ev = QDropEvent(QPoint(5, 5), Qt.CopyAction | Qt.MoveAction, md, Qt.LeftButton, Qt.NoModifier)
    cible.dropEvent(ev)
    return ev


class TestDialogueRaccord(_AideDialogue):

    def _glisser_lot_dans_lignee(self, dlg):
        z = dlg._relations_groups_zone
        box = z._succ_boxes[0]
        box.courante_input.setText("C00904134")
        z.ajouter_refs(box, list(LOT))
        return z, box

    def _remplir_cartes(self, dlg):
        for ref, n in (("2808540500", "C00904139"), ("2808530300", "C00923922"),
                       ("2808540300", "C00904134")):
            self._champ(dlg, ref).add_refs([n])

    def test_saisie_naturelle_sans_alerte(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        self._remplir_cartes(dlg)
        z, _ = self._glisser_lot_dans_lignee(dlg)
        assert z.warnings() == []
        assert not z.warnings_label.isVisibleTo(z)
        assert z.planned_counts() == {'successions': 5, 'equivalences': 0, 'obsoletes': 5}
        dlg._validate_and_accept()
        assert dlg.result_config is not None

    def test_arbre_affiche(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        assert not z.arbre.isVisibleTo(z)
        self._remplir_cartes(dlg)
        self._glisser_lot_dans_lignee(dlg)
        assert z.arbre.isVisibleTo(z)
        assert z.arbre.topLevelItemCount() == 1
        racine = z.arbre.topLevelItem(0)
        assert racine.text(0) == "C00904134" and "courante" in racine.text(1)
        enfants = {racine.child(i).text(0): racine.child(i) for i in range(racine.childCount())}
        assert set(enfants) == {"C00904139", "C00923922", "2808540300"}
        assert enfants["C00904139"].child(0).text(0) == "2808540500"
        assert "hors lot" in enfants["C00904139"].text(1)
        assert enfants["2808540300"].text(1) == ""

    def test_tuiles_marquees_via(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        self._remplir_cartes(dlg)
        _, box = self._glisser_lot_dans_lignee(dlg)
        tips = {box.members.item(i).text(): box.members.item(i).toolTip()
                for i in range(box.members.count())}
        assert "via C00904139" in tips["2808540500"]
        assert "direct" in tips["2808540300"]
        # Remplaçante retirée → marque retirée
        self._champ(dlg, "2808540500").remove_ref("C00904139")
        tips = {box.members.item(i).text(): box.members.item(i).toolTip()
                for i in range(box.members.count())}
        assert tips["2808540500"] == ""

    def test_depot_sur_champ_remplacee_par(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        chips, obs = self._champ(dlg, "2808540500"), self._obs(dlg, "2808540500")
        _deposer(chips, "C00904139")
        assert chips.refs() == ["C00904139"] and obs.isChecked()
        # Champ plein : la réf déposée remplace l'ancienne
        _deposer(chips, "C00999999")
        assert chips.refs() == ["C00999999"]

    def test_depot_tuile_de_liste_ne_vide_pas_la_source(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        ev = _deposer(self._champ(dlg, "2808540500"), "2808530300")
        from PyQt5.QtCore import Qt
        assert ev.dropAction() == Qt.CopyAction
        assert "2808530300" in dlg._relations_groups_zone.reservoir.refs()

    def test_depot_pastille_dans_lignee(self, qapp, test_db_manager):
        """Pastille d'un champ « Remplacée par » glissée dans une lignée : ajoutée
        comme réf hors lot (italique), le champ garde sa pastille."""
        dlg = self._dialog(test_db_manager)
        self._champ(dlg, "2808540500").add_refs(["C00904139"])
        z = dlg._relations_groups_zone
        box = z._succ_boxes[0]
        _deposer(box.members, "C00904139")
        assert "C00904139" in box.members.refs()
        assert "C00904139" in z.refs_hors_lot()
        assert self._champ(dlg, "2808540500").refs() == ["C00904139"]

    def test_reservoir_refuse_le_depot_externe(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        avant = z.reservoir.refs()
        _deposer(z.reservoir, "C00904139")
        assert z.reservoir.refs() == avant

    def test_mono_fichier_champs_sans_depot(self, qapp, test_db_manager):
        """Non-régression : les champs du fichier unique n'acceptent pas le dépôt."""
        from src.ui.ref_chips_input import RefChipsInput
        assert not RefChipsInput("x", max_refs=1).acceptDrops()


# ── v3.97.2 : double-clic, courante refusée, réservoir réduit ─────────────────

class TestDialogueV3972(_AideDialogue):

    def test_double_clic_pastille_devient_courante(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        box = z._succ_boxes[0]
        z.ajouter_refs(box, list(LOT))
        chips = self._champ(dlg, "2808540300")
        chips.add_refs(["C00904134"])
        chips.pastille_double_cliquee.emit("C00904134")
        assert box.courante_input.text() == "C00904134"

    def test_double_clic_vraie_pastille(self, qapp, test_db_manager):
        """Le signal part bien de la pastille (et pas seulement du champ)."""
        from PyQt5.QtCore import QPoint, Qt, QEvent
        from PyQt5.QtGui import QMouseEvent
        dlg = self._dialog(test_db_manager)
        chips = self._champ(dlg, "2808540300")
        chips.add_refs(["C00904134"])
        pastille = chips._pastilles[0]
        ev = QMouseEvent(QEvent.MouseButtonDblClick, QPoint(3, 3), Qt.LeftButton,
                         Qt.LeftButton, Qt.NoModifier)
        pastille.mouseDoubleClickEvent(ev)
        assert dlg._relations_groups_zone._succ_boxes[0].courante_input.text() == "C00904134"

    def test_double_clic_hors_lignee_premiere_sans_courante(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        assert z.definir_courante("2808540300", "C00904134") is z._succ_boxes[0]
        assert z._succ_boxes[0].courante_input.text() == "C00904134"

    def test_double_clic_sans_lignee_disponible(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        z._succ_boxes[0].courante_input.setText("AUTRE")
        assert z.definir_courante("2808540300", "C00904134") is None
        assert z._succ_boxes[0].courante_input.text() == "AUTRE"

    def test_courante_refusee_comme_ancienne_version(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        box = z._succ_boxes[0]
        box.courante_input.setText("C00904134")
        z.ajouter_refs(box, ["C00904134", "C00904139"])
        assert box.members.refs() == ["C00904139"]

    def test_reservoir_reduit_quand_vide(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        assert z.reservoir.maximumHeight() == z._RESERVOIR_H_MAX
        z.ajouter_refs(z._succ_boxes[0], list(LOT))
        assert z.reservoir.maximumHeight() == z._RESERVOIR_H_VIDE
        z._empty_box(z._succ_boxes[0])
        assert z.reservoir.maximumHeight() == z._RESERVOIR_H_MAX
