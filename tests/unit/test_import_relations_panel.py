"""Tests du panneau « par groupes » (Lot 2). Offscreen via qapp.

Le drag-drop réel étant lourd, on simule le drop (retrait du réservoir + ajout à la
liste membres d'une boîte), puis on resynchronise.
"""

import pytest
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
        box.courante_combo.setCurrentText("B3")
        _move(panel, "B1", box)
        _move(panel, "B2", box)
        g = panel.get_groups()[0]
        assert g.kind == KIND_SUCCESSION and g.courante == "B3"
        assert sorted(g.members) == ["B1", "B2"]
        # B3 = courante (couronne), B1/B2 deviendront obsolètes
        assert not _cards(panel)["B3"].head_badge.pixmap().isNull()
        assert "courantes : B3" in panel.recap.text()
        assert "2 obsolètes" in panel.recap.text()

    def test_courante_externe_fantome(self, qapp):
        panel = _panel(qapp, base=["EXISTE"])
        box = panel.groups_zone.add_group(KIND_SUCCESSION)
        box.courante_combo.setCurrentText("EXT_HORS_BASE")
        _move(panel, "B1", box)
        assert "fantôme" in panel.recap.text()
        # une courante déjà en base ne crée pas de fantôme
        box.courante_combo.setCurrentText("EXISTE")
        panel.recompute()
        assert "fantôme" not in panel.recap.text()


class TestEquivalence:
    def test_groupe_sans_obsolescence(self, qapp):
        panel = _panel(qapp)
        box = panel.groups_zone.add_group(KIND_EQUIVALENCE)
        _move(panel, "S1", box)
        _move(panel, "S2", box)
        g = panel.get_groups()[0]
        assert g.kind == KIND_EQUIVALENCE and sorted(g.members) == ["S1", "S2"]
        assert "obsolète" not in panel.recap.text()
        assert not _cards(panel)["S1"].equiv_badge.text() == ""   # pastille présente


class TestCross:
    def test_cross_equivalent_courantes(self, qapp):
        panel = _panel(qapp)
        b1 = panel.groups_zone.add_group(KIND_SUCCESSION)
        b1.courante_combo.setCurrentText("B3"); _move(panel, "B1", b1)
        b1.cross_check.setChecked(True)
        b2 = panel.groups_zone.add_group(KIND_SUCCESSION)
        b2.courante_combo.setCurrentText("S2"); _move(panel, "S1", b2)
        b2.cross_check.setChecked(True)
        panel.recompute()
        assert "équiv. croisée : B3, S2" in panel.recap.text()


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
        assert panel.get_groups() == []


class TestSolo:
    def test_solo_sans_groupes(self, qapp):
        panel = RelationsPanel([("A", "a")], is_solo=True, base_refs=[])
        assert panel.groups_zone is None
        card = panel.cards[0]
        card.obsolete_check.setChecked(True)
        card.replaces_input.setText("OLD")
        cd = panel.get_cards()[0]
        assert cd.is_obsolete and cd.base_replaces == "OLD"
