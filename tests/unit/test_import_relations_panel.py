"""Tests du panneau de relations d'import (Lot 2, modèle étoile + zone groupes).

Offscreen via qapp. La simulation du drag-drop réel étant lourde, on manipule
directement l'état des listes (ce que le drop produit) puis on resynchronise.
"""

import pytest
from PyQt5.QtWidgets import QListWidgetItem

from src.ui.import_relations_panel import RelationsPanel


def _panel(qapp, refs=None, base=None):
    refs = refs or [("B1", "b1"), ("B2", "b2"), ("B3", "b3"), ("S1", "s1"), ("S2", "s2")]
    return RelationsPanel(refs, is_solo=False, base_refs=base or [])


def _cards(panel):
    return {c.ref: c for c in panel.cards}


def _move_to_group(panel, ref, gid):
    """Simule le drop : retire la réf du réservoir, l'ajoute à la liste du groupe."""
    res = panel.groups_zone.reservoir
    for i in range(res.count()):
        if res.item(i).text() == ref:
            res.takeItem(i)
            break
    panel.groups_zone._group_lists[gid].addItem(QListWidgetItem(ref))
    panel.groups_zone._on_change()


class TestSuccession:
    def test_courante_et_ancienne_version(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        c["B3"].radio_current.setChecked(True)
        c["B1"].radio_old.setChecked(True)
        c["B1"].newer_combo.setCurrentText("B3")
        panel.recompute()
        rels = {r.ref: r for r in panel.get_relations()}
        assert rels["B3"].is_current is True
        assert rels["B1"].newer_ref == "B3"
        assert "1 courante (B3)" in panel.recap.text()

    def test_radios_exclusifs_par_carte(self, qapp):
        panel = _panel(qapp)
        card = _cards(panel)["B1"]
        card.radio_current.setChecked(True)
        card.radio_old.setChecked(True)        # bascule
        assert not card.radio_current.isChecked()
        assert card.newer_combo.isEnabled()    # combo actif sur « ancienne version de »

    def test_combo_newer_editable_libre_fantome(self, qapp):
        panel = _panel(qapp, base=["EXISTE"])
        card = _cards(panel)["B1"]
        card.radio_old.setChecked(True)
        card.newer_combo.setCurrentText("PAS_EN_BASE")   # saisie libre, hors base
        panel.recompute()
        assert panel.get_relations()[0].newer_ref == "PAS_EN_BASE"
        assert "fantôme" in panel.recap.text()

    def test_multi_courantes(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        c["B3"].radio_current.setChecked(True)
        c["S2"].radio_current.setChecked(True)
        panel.recompute()
        assert "2 courantes (B3, S2)" in panel.recap.text()


class TestEquivalence:
    def test_creation_et_affectation_groupe(self, qapp):
        panel = _panel(qapp)
        gid = panel.groups_zone.add_group()
        _move_to_group(panel, "B3", gid)
        _move_to_group(panel, "S2", gid)
        panel.recompute()
        assign = panel.groups_zone.assignments()
        assert assign == {"B3": gid, "S2": gid}
        assert f"Éq. A : B3, S2" in panel.recap.text()
        # Pastille affichée sur la carte
        assert "Éq. A" in _cards(panel)["B3"].equiv_badge.text()

    def test_une_ref_un_seul_groupe(self, qapp):
        panel = _panel(qapp)
        g1 = panel.groups_zone.add_group()
        g2 = panel.groups_zone.add_group()
        _move_to_group(panel, "B3", g1)
        # Déplacer B3 vers g2 : le drop l'aurait retiré de g1 ; on simule
        panel.groups_zone._group_lists[g1].takeItem(0)
        _move_to_group(panel, "B3", g2)
        assert panel.groups_zone.assignments() == {"B3": g2}

    def test_vider_groupe_renvoie_au_reservoir(self, qapp):
        panel = _panel(qapp)
        gid = panel.groups_zone.add_group()
        _move_to_group(panel, "B3", gid)
        panel.groups_zone._empty_group(gid)
        assert panel.groups_zone.assignments() == {}
        assert "B3" in panel.groups_zone.reservoir.refs()


class TestSolo:
    def test_mode_solo_sans_chainage_ni_groupes(self, qapp):
        panel = RelationsPanel([("A", "a")], is_solo=True, base_refs=[])
        card = panel.cards[0]
        assert card.radio_current is None and card.newer_combo is None
        assert panel.groups_zone is None
        # On garde Obsolète + lien base « remplace »
        card.obsolete_check.setChecked(True)
        card.replaces_input.setText("OLD")
        rel = panel.get_relations()[0]
        assert rel.is_obsolete and rel.base_replaces == "OLD"
