"""Tests du panneau « par groupes » (Lot 2). Offscreen via qapp.

Le drag-drop réel étant lourd, on simule le drop (retrait du réservoir + ajout à la
liste membres d'une boîte), puis on resynchronise.
"""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QListWidgetItem

from src.ui.import_relations_panel import RelationsPanel
from src.services.import_relations import KIND_SUCCESSION, KIND_EQUIVALENCE


def _panel(qapp, refs=None, base=None):
    refs = refs or [("B1", "b1"), ("B2", "b2"), ("B3", "b3"), ("S1", "s1"), ("S2", "s2")]
    return RelationsPanel(refs, is_solo=False, base_refs=base or [])


def _cards(panel):
    return {c.ref: c for c in panel.cards}


def _move(panel, ref, box):
    res = panel.groups_zone.reservoir
    for i in range(res.count()):
        if res.item(i).text() == ref:
            res.takeItem(i)
            break
    box.members.addItem(QListWidgetItem(ref))
    panel.recompute()


class TestSuccession:
    def test_lignee_courante_lot(self, qapp):
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        box.courante_input.setText("B3")
        _move(panel, "B1", box)
        _move(panel, "B2", box)
        g = box.to_group()
        assert g.kind == KIND_SUCCESSION and g.courante == "B3"
        assert sorted(g.members) == ["B1", "B2"]
        # B3 = courante (couronne), B1/B2 deviendront obsolètes
        assert not _cards(panel)["B3"].head_badge.pixmap().isNull()
        assert "courantes : B3" in panel.recap.text()
        assert "2 obsolètes" in panel.recap.text()

    def test_courante_externe_fantome(self, qapp):
        panel = _panel(qapp, base=["EXISTE"])
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        box.courante_input.setText("EXT_HORS_BASE")
        _move(panel, "B1", box)
        assert "fantôme" in panel.recap.text()
        # une courante déjà en base ne crée pas de fantôme
        box.courante_input.setText("EXISTE")
        panel.recompute()
        assert "fantôme" not in panel.recap.text()

    def test_double_clic_membre_promu_courante(self, qapp):
        """Double-clic → renseigne la courante SANS retirer le chip de la zone ;
        la courante listée parmi les membres n'est pas marquée obsolète."""
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        _move(panel, "B1", box)
        _move(panel, "B2", box)
        item = box.members.findItems("B2", Qt.MatchExactly)[0]
        box._promote_member(item)
        g = box.to_group()
        assert g.courante == "B2"
        assert sorted(g.members) == ["B1", "B2"]      # B2 reste visible dans la zone
        # B2 (courante) n'est pas obsolète ; seul B1 l'est
        from src.services.import_relations import derive
        dd = derive(panel.get_groups(), panel.get_cards(), {"B1", "B2", "B3", "S1", "S2"}, set())
        assert dd.obsoletes == {"B1"}

    def test_drop_sur_courante(self, qapp):
        """Lot 6 : réf glissée sur le champ Courante → renseigne sans vider la source."""
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        _move(panel, "B1", box)
        box._on_courante_dropped("B3")
        assert box.to_group().courante == "B3"
        assert box.members.refs() == ["B1"]   # membres inchangés


class TestEquivalence:
    def test_groupe_sans_obsolescence(self, qapp):
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_EQUIVALENCE)
        _move(panel, "S1", box)
        _move(panel, "S2", box)
        g = box.to_group()
        assert g.kind == KIND_EQUIVALENCE and sorted(g.members) == ["S1", "S2"]
        assert "obsolète" not in panel.recap.text()
        assert not _cards(panel)["S1"].equiv_badge.text() == ""   # pastille présente

    def test_groupe_equivalence_sans_courante_avec_cross(self, qapp):
        """Un groupe d'équivalence n'a pas de « courante », mais porte la case
        « Équivalent aux lignées cochées » (décochée par défaut)."""
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_EQUIVALENCE)
        assert box.courante_input is None
        assert box.cross_check is not None and not box.cross_check.isChecked()
        assert box.to_group().courante is None and box.to_group().cross_equivalent is False


class TestCross:
    def test_cross_equivalent_courantes(self, qapp):
        panel = _panel(qapp)
        b1 = panel.groups_zone.add_group(KIND_SUCCESSION)
        b1.courante_input.setText("B3"); _move(panel, "B1", b1)
        b1.cross_check.setChecked(True)
        b2 = panel.groups_zone.add_group(KIND_SUCCESSION)
        b2.courante_input.setText("S2"); _move(panel, "S1", b2)
        b2.cross_check.setChecked(True)
        panel.recompute()
        assert "équiv. croisée : B3, S2" in panel.recap.text()

    def test_cross_groupe_equivalence_vers_lignee(self, qapp):
        """Cas réel 2026-10-08 : un groupe d'équivalence coché rejoint la lignée cochée."""
        panel = _panel(qapp)
        z = panel.groups_zone
        lig = z.add_group(KIND_SUCCESSION)
        lig.courante_input.setText("B3"); _move(panel, "B1", lig)
        lig.cross_check.setChecked(True)
        grp = z.add_group(KIND_EQUIVALENCE)
        _move(panel, "S1", grp); _move(panel, "S2", grp)
        grp.cross_check.setChecked(True)
        panel.recompute()
        assert "équiv. croisée : B3, S1" in panel.recap.text()
        assert z.planned_counts()['equivalences'] == 2          # S1≡S2 + B3≡S1
        assert z.warnings() == []

    def test_toutes_lignees_ne_coche_pas_les_groupes(self, qapp):
        """« Toutes les lignées équivalentes » reste limitée aux lignées."""
        panel = _panel(qapp)
        z = panel.groups_zone
        grp = z.add_group(KIND_EQUIVALENCE)
        z.all_equiv_check.setChecked(True)
        assert not grp.cross_check.isChecked()

    def test_warning_groupe_coche_seul(self, qapp):
        panel = _panel(qapp)
        z = panel.groups_zone
        grp = z.add_group(KIND_EQUIVALENCE)
        _move(panel, "S1", grp); _move(panel, "S2", grp)
        grp.cross_check.setChecked(True)
        z._update_recap()
        assert "aucune équivalence croisée" in z.warnings_label.text()

    def test_checkbox_toutes_lignees_equivalentes(self, qapp):
        """La checkbox coche les lignées existantes ET pré-coche les futures."""
        panel = _panel(qapp)
        z = panel.groups_zone
        b1 = z.add_group(KIND_SUCCESSION)
        b2 = z.add_group(KIND_SUCCESSION)
        assert not b1.cross_check.isChecked() and not b2.cross_check.isChecked()
        z.all_equiv_check.setChecked(True)
        assert b1.cross_check.isChecked() and b2.cross_check.isChecked()
        # une lignée créée APRÈS coche est pré-cochée
        b3 = z.add_group(KIND_SUCCESSION)
        assert b3.cross_check.isChecked()
        # décoche → toutes les lignées existantes décochées
        z.all_equiv_check.setChecked(False)
        assert not b1.cross_check.isChecked() and not b3.cross_check.isChecked()


class TestAllEquiv:
    def test_toutes_equivalentes_non_groupees(self, qapp):
        """Lot 7 : ne regroupe que les réfs du réservoir, laisse la lignée intacte."""
        panel = _panel(qapp)
        succ = panel.groups_zone.add_group(KIND_SUCCESSION)
        succ.courante_input.setText("B3")
        _move(panel, "B1", succ)          # B1 dans une lignée → non concerné
        box = panel.groups_zone.add_all_to_new_equivalence()
        assert box is not None and box.kind == KIND_EQUIVALENCE
        # réservoir vidé, lignée (membre B1) préservée. B3 = courante par son nom
        # mais reste un chip non groupé du réservoir → inclus dans « non groupées ».
        assert panel.groups_zone.reservoir.refs() == []
        assert sorted(box.members.refs()) == ["B2", "B3", "S1", "S2"]   # pas B1 (membre de lignée)
        assert succ.members.refs() == ["B1"]
        # décochage : retire le groupe auto, réfs de retour au réservoir
        panel.groups_zone.remove_auto_equivalence_group(box)
        assert sorted(panel.groups_zone.reservoir.refs()) == ["B2", "B3", "S1", "S2"]

    def test_toutes_equivalentes_reservoir_vide(self, qapp):
        panel = _panel(qapp, refs=[("B1", "b1")])
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        _move(panel, "B1", box)
        assert panel.groups_zone.add_all_to_new_equivalence() is None


class TestPreseed:
    def test_une_lignee_et_un_groupe_pre_crees(self, qapp):
        """À la construction du panneau multi-fichiers, une lignée vide et un
        groupe d'équivalence vide existent déjà (l'utilisateur peut glisser
        directement sans cliquer sur « + »)."""
        panel = _panel(qapp)
        z = panel.groups_zone
        assert len(z._succ_boxes) == 1
        assert len(z._equiv_boxes) == 1
        assert z._succ_boxes[0].kind == KIND_SUCCESSION
        assert z._equiv_boxes[0].kind == KIND_EQUIVALENCE

    def test_groupes_pre_crees_vides_sans_effet(self, qapp):
        """apply_relations() sur les deux groupes pré-créés (vides) ne génère
        aucune entrée : zone vide = ignorée."""
        from src.services.import_relations import apply_relations

        class _NoopDb:
            def add_supersession(self, *a): raise AssertionError("ne doit pas être appelé")
            def add_equivalence(self, *a): raise AssertionError("ne doit pas être appelé")
            def mark_obsolete(self, *a): raise AssertionError("ne doit pas être appelé")

        panel = _panel(qapp)
        counts = apply_relations(panel.get_groups(), panel.get_cards(), _NoopDb())
        assert counts == {'successions': 0, 'equivalences': 0, 'obsoletes': 0, 'errors': 0}


class TestZone:
    def test_vider_groupe_renvoie_au_reservoir(self, qapp):
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        _move(panel, "B1", box)
        panel.groups_zone._empty_box(box)
        assert box.members.refs() == []
        assert "B1" in panel.groups_zone.reservoir.refs()

    def test_supprimer_groupe_renvoie_au_reservoir(self, qapp):
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_EQUIVALENCE)
        _move(panel, "S1", box)
        panel.groups_zone._remove_box(box)
        assert "S1" in panel.groups_zone.reservoir.refs()
        assert box not in panel.groups_zone.all_boxes()
        # Seules les 2 boîtes pré-créées (vides) subsistent
        assert all(not g.members and not g.courante for g in panel.get_groups())


class TestSolo:
    def test_solo_sans_groupes(self, qapp):
        panel = RelationsPanel([("A", "a")], is_solo=True, base_refs=[])
        assert panel.groups_zone is None
        card = panel.cards[0]
        card.obsolete_check.setChecked(True)
        card.replaces_input.setText("OLD")
        cd = panel.get_cards()[0]
        assert cd.is_obsolete and cd.base_replaces == "OLD"


class TestRecapEtGardesFous:
    """v3.62.0 : récap en direct + avertissements + grisage des cases sans effet
    (les déclarations d'équivalence ne doivent plus se perdre en silence)."""

    def test_recap_compte_les_equivalences(self, qapp):
        panel = _panel(qapp)
        z = panel.groups_zone
        box = z.add_group(KIND_EQUIVALENCE)
        _move(panel, "S1", box)
        _move(panel, "S2", box)
        z._update_recap()
        assert "1 équivalence" in z.recap_label.text()
        assert not z.warnings_label.isVisible() or z.warnings_label.text() == ""

    def test_warning_lignee_sans_courante(self, qapp):
        panel = _panel(qapp)
        z = panel.groups_zone
        box = z.add_group(KIND_SUCCESSION)
        _move(panel, "B1", box)
        z._update_recap()
        assert "0 succession" in z.recap_label.text()
        assert "pas de courante" in z.warnings_label.text()

    def test_warning_toutes_lignees_equivalentes_sans_deux_courantes(self, qapp):
        """Le no-op silencieux du rapport utilisateur (import 06/07 14:49) :
        case cochée, mais < 2 lignées avec courante → 0 équivalence, désormais signalé."""
        panel = _panel(qapp)
        z = panel.groups_zone
        z.all_equiv_check.setChecked(True)
        z._update_recap()
        assert "0 équivalence" in z.recap_label.text()
        assert "aucune équivalence" in z.warnings_label.text()

    def test_warning_cross_une_seule_lignee(self, qapp):
        panel = _panel(qapp)
        z = panel.groups_zone
        box = z.add_group(KIND_SUCCESSION)
        box.courante_input.setText("B3")
        _move(panel, "B1", box)
        box.cross_check.setChecked(True)
        z._update_recap()
        assert "aucune équivalence croisée" in z.warnings_label.text()

    def test_grisage_toutes_lignees_equivalentes(self, qapp):
        """Grisée sous 2 lignées à courante ; réactivée à 2 ; jamais verrouillée cochée."""
        panel = _panel(qapp)
        z = panel.groups_zone
        z._update_recap()
        assert not z.all_equiv_check.isEnabled()          # 0 courante
        b1 = z.add_group(KIND_SUCCESSION); b1.courante_input.setText("B3")
        z._update_recap()
        assert not z.all_equiv_check.isEnabled()          # 1 courante
        b2 = z.add_group(KIND_SUCCESSION); b2.courante_input.setText("S2")
        z._update_recap()
        assert z.all_equiv_check.isEnabled()              # 2 courantes
        # cochée puis courantes retirées → reste décochable (jamais grisée cochée)
        z.all_equiv_check.setChecked(True)
        b2.courante_input.setText("")
        z._update_recap()
        assert z.all_equiv_check.isEnabled()

    def test_recap_reagit_a_la_coche_globale(self, qapp):
        """_on_all_equiv_toggled émet changed même sans lignée : le récap se met à jour."""
        panel = _panel(qapp)
        z = panel.groups_zone
        z.all_equiv_check.setChecked(True)
        assert "aucune équivalence" in z.warnings_label.text()
        z.all_equiv_check.setChecked(False)
        assert z.warnings_label.text() == ""
