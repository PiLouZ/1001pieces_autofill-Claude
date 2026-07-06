"""Tests du cœur logique « par groupes » des relations d'import (sans UI).

Lignées de succession (courante + membres → obsolètes), groupes d'équivalence
(tous valides), checkbox « équivalente entre groupes » (relie les courantes).
"""

import pytest

from src.services.import_relations import (
    Group, CardData, derive, apply_relations,
    KIND_SUCCESSION, KIND_EQUIVALENCE,
)


def _cards(*refs):
    return [CardData(ref=r) for r in refs]


# ── Dérivation ────────────────────────────────────────────────────────────────

class TestDerive:
    def test_lignee_courante_lot(self):
        g = Group(KIND_SUCCESSION, courante="B3", members=["B1", "B2"])
        d = derive([g], _cards("B1", "B2", "B3"), {"B1", "B2", "B3"}, set())
        assert d.courantes == {"B3"}
        assert d.obsoletes == {"B1", "B2"}            # membres ≠ courante
        assert d.succ_group_of == {"B1": 0, "B2": 0}
        assert d.phantoms == set() and d.warnings == []

    def test_lignee_courante_externe_fantome(self):
        g = Group(KIND_SUCCESSION, courante="EXT", members=["B1", "B2"])
        d = derive([g], _cards("B1", "B2"), {"B1", "B2"}, base_refs=set())
        assert "EXT" not in d.courantes            # pas de carte → pas de badge
        assert "EXT" in d.phantoms                 # externe + hors base → fantôme
        assert d.obsoletes == {"B1", "B2"}

    def test_lignee_courante_en_base_pas_fantome(self):
        g = Group(KIND_SUCCESSION, courante="EXISTE", members=["B1"])
        d = derive([g], _cards("B1"), {"B1"}, base_refs={"EXISTE"})
        assert d.phantoms == set()

    def test_groupe_equivalence_sans_obsolescence(self):
        g = Group(KIND_EQUIVALENCE, members=["X", "Y", "Z"])
        d = derive([g], _cards("X", "Y", "Z"), {"X", "Y", "Z"}, set())
        assert d.obsoletes == set()
        assert d.equiv_group_of == {"X": 0, "Y": 0, "Z": 0}

    def test_cross_equivalent_courantes(self):
        g1 = Group(KIND_SUCCESSION, courante="B3", members=["B1"], cross_equivalent=True)
        g2 = Group(KIND_SUCCESSION, courante="S2", members=["S1"], cross_equivalent=True)
        d = derive([g1, g2], _cards("B1", "B3", "S1", "S2"), {"B1", "B3", "S1", "S2"}, set())
        assert sorted(d.cross_courantes) == ["B3", "S2"]

    def test_warning_lignee_sans_courante(self):
        d = derive([Group(KIND_SUCCESSION, courante=None, members=["B1"])],
                   _cards("B1"), {"B1"}, set())
        assert any("sans courante" in m for _, m in d.warnings)

    def test_warning_cross_seul(self):
        d = derive([Group(KIND_SUCCESSION, courante="B3", members=["B1"], cross_equivalent=True)],
                   _cards("B1", "B3"), {"B1", "B3"}, set())
        assert any("au moins deux" in m for _, m in d.warnings)


# ── Application ───────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self):
        self.supersessions, self.equivalences, self.obsoletes = [], [], []

    def add_supersession(self, old, new):
        self.supersessions.append((old, new)); return True, ""

    def add_equivalence(self, a, b):
        self.equivalences.append((a, b)); return True, ""

    def mark_obsolete(self, ref):
        self.obsoletes.append(ref); return True


class TestApply:
    def test_lignee(self):
        g = Group(KIND_SUCCESSION, courante="EXT", members=["B1", "B2"])
        apply_relations([g], _cards("B1", "B2"), db := FakeDB())
        assert set(db.supersessions) == {("B1", "EXT"), ("B2", "EXT")}
        assert set(db.obsoletes) == {"B1", "B2"}

    def test_equivalence_par_paires(self):
        g = Group(KIND_EQUIVALENCE, courante="C", members=["A", "B"])
        apply_relations([g], _cards("A", "B"), db := FakeDB())
        assert set(db.equivalences) == {("C", "A"), ("C", "B")}   # ancre = courante repère
        assert db.obsoletes == []

    def test_cross_equivalent(self):
        g1 = Group(KIND_SUCCESSION, courante="B3", members=["B1"], cross_equivalent=True)
        g2 = Group(KIND_SUCCESSION, courante="S2", members=["S1"], cross_equivalent=True)
        apply_relations([g1, g2], _cards("B1", "S1"), db := FakeDB())
        assert ("B3", "S2") in db.equivalences

    def test_carte_obsolete_et_remplace(self):
        cards = [CardData("R", is_obsolete=True, base_replaces="OLD")]
        apply_relations([], cards, db := FakeDB())
        assert "R" in db.obsoletes
        assert ("OLD", "R") in db.supersessions


class TestApplyRealDB:
    def test_persistance(self, test_db_manager):
        for ref in ("B1", "B2", "B3", "S1", "S2"):
            test_db_manager.execute_query("INSERT OR IGNORE INTO pieces(ref_piece) VALUES (?)", [ref])
        test_db_manager.conn.commit()
        groups = [
            Group(KIND_SUCCESSION, courante="B3", members=["B1", "B2"], cross_equivalent=True),
            Group(KIND_SUCCESSION, courante="S2", members=["S1"], cross_equivalent=True),
        ]
        counts = apply_relations(groups, _cards("B1", "B2", "B3", "S1", "S2"), test_db_manager)
        assert counts['errors'] == 0
        # B1 → B3 (succession)
        row = test_db_manager.execute_query(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", ["B1"])
        assert row and row[0][0] == "B3"
        # B1, B2, S1 obsolètes
        for r in ("B1", "B2", "S1"):
            o = test_db_manager.execute_query("SELECT is_obsolete FROM pieces WHERE ref_piece=?", [r])
            assert o and o[0][0] == 1
        # B3 ≡ S2 (cross-équivalence)
        g = test_db_manager.execute_query(
            "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece IN ('B3','S2')")
        assert len({x[0] for x in g}) == 1 and len(g) == 2


class TestCountPlanned:
    """count_planned_relations = miroir sans écriture d'apply_relations (v3.62.0).
    Alimente le récap en direct du panneau et le garde-fou à la validation."""

    def test_miroir_apply_relations(self):
        from src.services.import_relations import count_planned_relations
        groups = [
            Group(KIND_SUCCESSION, courante="B3", members=["B1", "B2"], cross_equivalent=True),
            Group(KIND_SUCCESSION, courante="S2", members=["S1"], cross_equivalent=True),
            Group(KIND_EQUIVALENCE, members=["E1", "E2", "E3"]),
        ]
        cards = [CardData("B1"), CardData("X", is_obsolete=True, base_replaces="OLD")]
        planned = count_planned_relations(groups, cards)
        applied = apply_relations(groups, cards, FakeDB())
        assert planned['successions'] == applied['successions'] == 4   # B1,B2,S1 + OLD→X
        assert planned['equivalences'] == applied['equivalences'] == 3  # E1≡E2≡E3 (2) + B3≡S2 (1)
        assert planned['obsoletes'] == applied['obsoletes'] == 4        # B1,B2,S1,X

    def test_cas_sans_effet(self):
        """Les déclarations « sans effet » comptent bien 0 (base du garde-fou)."""
        from src.services.import_relations import count_planned_relations
        # Lignée sans courante → 0 succession ; cross coché sur UNE seule lignée → 0 équiv ;
        # groupe d'équivalence à une réf → 0 équiv.
        groups = [
            Group(KIND_SUCCESSION, courante=None, members=["B1", "B2"]),
            Group(KIND_SUCCESSION, courante="S2", members=["S1"], cross_equivalent=True),
            Group(KIND_EQUIVALENCE, members=["E1"]),
        ]
        planned = count_planned_relations(groups, [])
        assert planned['equivalences'] == 0
        assert planned['successions'] == 1        # S1 → S2 uniquement
        assert planned['obsoletes'] == 1          # S1

    def test_courante_membre_et_doublons(self):
        """Courante listée parmi les membres : ni comptée en succession ni en équiv double."""
        from src.services.import_relations import count_planned_relations
        groups = [
            Group(KIND_SUCCESSION, courante="B2", members=["B1", "B2"]),
            Group(KIND_EQUIVALENCE, courante="E1", members=["E1", "E2", "E2"]),
        ]
        planned = count_planned_relations(groups, [])
        assert planned['successions'] == 1        # B1 → B2 (B2 == courante ignorée)
        assert planned['equivalences'] == 1       # E1 ≡ E2 (doublon E2 dédupliqué)
