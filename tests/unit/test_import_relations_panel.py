"""Tests du panneau de relations d'import (Lot 2) — logique de dérivation visuelle.

Offscreen via la fixture qapp. Vérifie les options « Suit » (anti-cycle,
prédécesseur unique), les multi-courantes, l'allocation de groupe d'équivalence,
l'avertissement fantôme et le récap.
"""

import pytest

from src.ui.import_relations_panel import RelationsPanel, _EQUIV_NEW


def _panel(qapp, refs=None, base=None):
    refs = refs or [("B1", "b1"), ("B2", "b2"), ("B3", "b3"), ("S1", "s1"), ("S2", "s2")]
    return RelationsPanel(refs, is_solo=False, base_refs=base or [])


def _set_suit(card, pred):
    card.suit_combo.setCurrentIndex(card.suit_combo.findData(pred))


def _cards(panel):
    return {c.ref: c for c in panel.cards}


class TestPanel:
    def test_multi_courantes_dans_recap(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        _set_suit(c["B2"], "B1"); _set_suit(c["B3"], "B2"); _set_suit(c["S2"], "S1")
        panel.recompute()
        assert "2 courantes (B3, S2)" in panel.recap.text()
        assert "2 chaînes" in panel.recap.text()

    def test_suit_exclut_soi_et_descendants(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        _set_suit(c["B2"], "B1"); _set_suit(c["B3"], "B2")
        panel.recompute()
        # B1 ne doit pas pouvoir « suivre » ses descendants B2/B3, ni soi-même
        opts = [c["B1"].suit_combo.itemData(i) for i in range(c["B1"].suit_combo.count())]
        assert "B1" not in opts and "B2" not in opts and "B3" not in opts
        assert "S1" in opts and "S2" in opts

    def test_predecesseur_unique(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        _set_suit(c["B2"], "B1")
        panel.recompute()
        # B1 est pris comme prédécesseur par B2 → plus proposé aux autres cartes…
        opts_s2 = [c["S2"].suit_combo.itemData(i) for i in range(c["S2"].suit_combo.count())]
        assert "B1" not in opts_s2
        # … mais reste l'option courante de B2 lui-même
        opts_b2 = [c["B2"].suit_combo.itemData(i) for i in range(c["B2"].suit_combo.count())]
        assert "B1" in opts_b2

    def test_allocation_nouveau_groupe(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        c["B3"].equiv_combo.setCurrentIndex(c["B3"].equiv_combo.findData(_EQUIV_NEW))
        panel.recompute()
        gid = c["B3"].get_relation().equiv_group
        assert isinstance(gid, int) and gid >= 1
        # Le nouveau groupe devient sélectionnable par une autre carte
        opts_s2 = [c["S2"].equiv_combo.itemData(i) for i in range(c["S2"].equiv_combo.count())]
        assert gid in opts_s2

    def test_avertissement_fantome(self, qapp):
        panel = _panel(qapp, base=["EXISTE"])
        c = _cards(panel)
        c["B1"].replaces_input.setText("ABSENTE")
        panel.recompute()
        # isHidden() reflète l'état explicite (le panneau n'est pas affiché en test)
        assert not c["B1"].phantom_warn.isHidden()
        assert "fantôme" in panel.recap.text()
        # Une réf base existante ne déclenche pas d'avertissement
        c["B2"].replaces_input.setText("EXISTE")
        panel.recompute()
        assert c["B2"].phantom_warn.isHidden()

    def test_courante_plus_obsolete_autorise(self, qapp):
        panel = _panel(qapp)
        c = _cards(panel)
        _set_suit(c["B2"], "B1")            # B2 = tête
        c["B2"].obsolete_check.setChecked(True)
        panel.recompute()
        rel = {r.ref: r for r in panel.get_relations()}["B2"]
        assert rel.is_obsolete is True       # autorisé, aucune exclusion
        assert "1 obsolète" in panel.recap.text()

    def test_mode_solo_masque_chainage(self, qapp):
        panel = RelationsPanel([("A", "a")], is_solo=True, base_refs=[])
        card = panel.cards[0]
        assert card.suit_combo is None and card.equiv_combo is None
        # En solo on garde Obsolète + liens base
        assert card.obsolete_check is not None
        card.replaces_input.setText("X")
        assert panel.get_relations()[0].base_replaces == "X"
