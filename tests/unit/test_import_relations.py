"""Tests du cœur logique des relations d'import (modèle étoile, sans UI).

Modèle : une réf est « Courante » (is_current) OU « ancienne version de » une réf
récente (newer_ref) — jamais les deux. Topologie en étoile : pas de cycle possible.
"""

import pytest

from src.services.import_relations import (
    RefRelation, recompute_relations, apply_relations,
)


def _rel(ref, **kw):
    return RefRelation(ref=ref, **kw)


# ── Dérivation pure ───────────────────────────────────────────────────────────

class TestRecompute:
    def test_lignee_simple(self):
        # B1, B2 anciennes versions de B3 (courante)
        rels = [_rel("B3", is_current=True),
                _rel("B1", newer_ref="B3"), _rel("B2", newer_ref="B3")]
        d = recompute_relations(rels)
        assert d.heads == {"B3"}
        assert d.in_chain == {"B1", "B2", "B3"}
        assert d.chain_id_by_ref["B1"] == d.chain_id_by_ref["B3"]
        assert d.chains == [["B1", "B2", "B3"]]
        assert d.warnings == []

    def test_multi_courantes(self):
        rels = [
            _rel("B3", is_current=True), _rel("B1", newer_ref="B3"),
            _rel("S2", is_current=True), _rel("S1", newer_ref="S2"),
        ]
        d = recompute_relations(rels)
        assert d.heads == {"B3", "S2"}
        assert d.chain_id_by_ref["B1"] != d.chain_id_by_ref["S1"]

    def test_ref_isolee_pas_de_chaine(self):
        d = recompute_relations([_rel("Z")])
        assert d.heads == set() and d.in_chain == set()

    def test_courante_et_ancienne_incoherent(self):
        d = recompute_relations([_rel("A", is_current=True, newer_ref="B"), _rel("B", is_current=True)])
        assert any("Courante ET ancienne" in m for _, m in d.warnings)

    def test_self_reference(self):
        d = recompute_relations([_rel("A", newer_ref="A")])
        assert any("sa propre version" in m for _, m in d.warnings)

    def test_double_recente_lot_et_base(self):
        d = recompute_relations([_rel("A", newer_ref="B", base_replaced_by="C"), _rel("B", is_current=True)])
        assert any("Deux réfs récentes" in m for _, m in d.warnings)

    def test_groupes_equivalence(self):
        rels = [_rel("B3", is_current=True, equiv_group=1),
                _rel("S2", is_current=True, equiv_group=1),
                _rel("X", equiv_group=2), _rel("Y", equiv_group=2)]
        d = recompute_relations(rels)
        assert sorted(d.equiv_groups[1]) == ["B3", "S2"]
        assert sorted(d.equiv_groups[2]) == ["X", "Y"]

    def test_newer_ref_hors_lot_ok(self):
        # « ancienne version de » une réf absente du lot (base/fantôme) : valide, pas d'erreur
        d = recompute_relations([_rel("A", newer_ref="REF_BASE")])
        assert "A" in d.in_chain
        assert d.warnings == []


# ── Orchestration d'application ───────────────────────────────────────────────

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
    def test_lignee_etoile(self):
        rels = [_rel("B3", is_current=True), _rel("B1", newer_ref="B3"), _rel("B2", newer_ref="B3")]
        db = FakeDB()
        apply_relations(rels, db)
        assert set(db.supersessions) == {("B1", "B3"), ("B2", "B3")}   # chaque ancienne → courante

    def test_liens_base(self):
        apply_relations([_rel("imp", base_replaces="OLD", base_replaced_by="NEW")], db := FakeDB())
        assert ("OLD", "imp") in db.supersessions and ("imp", "NEW") in db.supersessions

    def test_newer_ref_hors_base(self):
        # « ancienne version de » une réf libre (pas en base) → supersession quand même
        apply_relations([_rel("A", newer_ref="LIBRE999")], db := FakeDB())
        assert ("A", "LIBRE999") in db.supersessions

    def test_obsolete(self):
        apply_relations([_rel("A", is_obsolete=True), _rel("B")], db := FakeDB())
        assert db.obsoletes == ["A"]

    def test_groupe_par_paires(self):
        rels = [_rel("A", equiv_group=1), _rel("B", equiv_group=1), _rel("C", equiv_group=1)]
        apply_relations(rels, db := FakeDB())
        assert set(db.equivalences) == {("A", "B"), ("A", "C")}


class TestApplyRealDB:
    def test_persistance(self, test_db_manager):
        for ref in ("R1", "R2", "R3", "R4", "R5"):
            test_db_manager.execute_query("INSERT OR IGNORE INTO pieces(ref_piece) VALUES (?)", [ref])
        test_db_manager.conn.commit()
        rels = [
            _rel("R2", is_current=True), _rel("R1", newer_ref="R2"),   # R1 → R2
            _rel("R3", base_replaces="OLDBASE"),                       # OLDBASE → R3
            _rel("R4", is_obsolete=True, equiv_group=1),
            _rel("R5", equiv_group=1),
        ]
        counts = apply_relations(rels, test_db_manager)
        assert counts['errors'] == 0
        row = test_db_manager.execute_query(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", ["R1"])
        assert row and row[0][0] == "R2"
        row = test_db_manager.execute_query(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", ["OLDBASE"])
        assert row and row[0][0] == "R3"
        row = test_db_manager.execute_query(
            "SELECT is_obsolete FROM pieces WHERE ref_piece = ?", ["R4"])
        assert row and row[0][0] == 1
        g = test_db_manager.execute_query(
            "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece IN ('R4','R5')")
        assert len({r[0] for r in g}) == 1 and len(g) == 2
