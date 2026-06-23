"""Tests du cœur logique des relations d'import (Lot 1, sans UI).

Couvre la dérivation pure des états (chaînes, têtes/courantes multiples, cycles,
doublons de prédécesseur, groupes d'équivalence) et l'orchestration d'application.
"""

import pytest

from src.services.import_relations import (
    RefRelation, recompute_relations, apply_relations,
)


def _rel(ref, **kw):
    return RefRelation(ref=ref, **kw)


# ── Dérivation pure ───────────────────────────────────────────────────────────

class TestRecompute:
    def test_chaine_simple_et_tete(self):
        # B2 suit B1, B3 suit B2  →  B1 → B2 → B3, tête = B3
        rels = [_rel("B1"), _rel("B2", suit_ref="B1"), _rel("B3", suit_ref="B2")]
        d = recompute_relations(rels)
        assert d.heads == {"B3"}
        assert d.chains == [["B1", "B2", "B3"]]
        assert d.chain_id_by_ref["B1"] == d.chain_id_by_ref["B3"]
        assert d.in_chain == {"B1", "B2", "B3"}
        assert d.warnings == []

    def test_multi_courantes_deux_chaines(self):
        rels = [
            _rel("B1"), _rel("B2", suit_ref="B1"), _rel("B3", suit_ref="B2"),
            _rel("S1"), _rel("S2", suit_ref="S1"),
        ]
        d = recompute_relations(rels)
        assert d.heads == {"B3", "S2"}                     # multi-courantes
        assert d.chain_id_by_ref["B1"] != d.chain_id_by_ref["S1"]   # 2 composantes
        assert sorted(map(len, d.chains)) == [2, 3]

    def test_ref_isolee_pas_de_tete(self):
        # Une réf sans aucun lien n'est pas « dans une chaîne » → pas de badge courante
        d = recompute_relations([_rel("Z")])
        assert d.heads == set()
        assert d.in_chain == set()

    def test_cycle_detecte_et_invalide(self):
        rels = [_rel("A", suit_ref="B"), _rel("B", suit_ref="A")]
        d = recompute_relations(rels)
        assert "A" in d.invalid_suit and "B" in d.invalid_suit
        assert any("Boucle" in msg for _, msg in d.warnings)

    def test_doublon_predecesseur_invalide(self):
        # B2 et B3 suivent tous deux B1 → conflit (un seul successeur possible)
        rels = [_rel("B1"), _rel("B2", suit_ref="B1"), _rel("B3", suit_ref="B1")]
        d = recompute_relations(rels)
        assert {"B2", "B3"} <= d.invalid_suit
        assert any("une seule possible" in msg for _, msg in d.warnings)

    def test_suit_ref_inconnue(self):
        d = recompute_relations([_rel("X", suit_ref="ABSENT")])
        assert "X" in d.invalid_suit
        assert any("absente du lot" in msg for _, msg in d.warnings)

    def test_remplacee_par_base_retire_le_statut_de_tete(self):
        # B2 suit B1 (B2 serait tête), mais B2 est remplacée par une réf base → plus tête
        rels = [_rel("B1"), _rel("B2", suit_ref="B1", base_replaced_by="C9")]
        d = recompute_relations(rels)
        assert "B2" not in d.heads
        assert "B2" in d.in_chain   # impliquée via lien base

    def test_groupes_equivalence(self):
        rels = [
            _rel("B3", equiv_group=1), _rel("S2", equiv_group=1),
            _rel("X", equiv_group=2), _rel("Y", equiv_group=2),
        ]
        d = recompute_relations(rels)
        assert sorted(d.equiv_groups[1]) == ["B3", "S2"]
        assert sorted(d.equiv_groups[2]) == ["X", "Y"]

    def test_avertissement_equivalent_non_tete(self):
        # B2 (milieu de chaîne) rattachée à un groupe → avertissement doux
        rels = [_rel("B1"), _rel("B2", suit_ref="B1", equiv_group=1),
                _rel("B3", suit_ref="B2"), _rel("S2", equiv_group=1)]
        d = recompute_relations(rels)
        assert any("plus récente de sa chaîne" in msg for ref, msg in d.warnings if ref == "B2")


# ── Orchestration d'application ───────────────────────────────────────────────

class FakeDB:
    def __init__(self):
        self.supersessions = []
        self.equivalences = []
        self.obsoletes = []

    def add_supersession(self, old, new):
        self.supersessions.append((old, new))
        return True, ""

    def add_equivalence(self, a, b):
        self.equivalences.append((a, b))
        return True, ""

    def mark_obsolete(self, ref):
        self.obsoletes.append(ref)
        return True


class TestApply:
    def test_applique_chaine_intra_lot(self):
        rels = [_rel("B1"), _rel("B2", suit_ref="B1"), _rel("B3", suit_ref="B2")]
        db = FakeDB()
        counts = apply_relations(rels, db)
        assert set(db.supersessions) == {("B1", "B2"), ("B2", "B3")}
        assert counts['successions'] == 2

    def test_applique_liens_base(self):
        rels = [_rel("imp", base_replaces="OLD", base_replaced_by="NEW")]
        db = FakeDB()
        apply_relations(rels, db)
        assert ("OLD", "imp") in db.supersessions      # imp remplace OLD
        assert ("imp", "NEW") in db.supersessions      # imp remplacée par NEW

    def test_applique_obsolete(self):
        db = FakeDB()
        apply_relations([_rel("A", is_obsolete=True), _rel("B")], db)
        assert db.obsoletes == ["A"]

    def test_applique_groupe_equivalence_par_paires(self):
        rels = [_rel("A", equiv_group=1), _rel("B", equiv_group=1), _rel("C", equiv_group=1)]
        db = FakeDB()
        counts = apply_relations(rels, db)
        assert set(db.equivalences) == {("A", "B"), ("A", "C")}   # ancre A ↔ autres
        assert counts['equivalences'] == 2

    def test_lien_invalide_non_applique(self):
        # Cycle → aucun add_supersession intra-lot
        rels = [_rel("A", suit_ref="B"), _rel("B", suit_ref="A")]
        db = FakeDB()
        apply_relations(rels, db)
        assert db.supersessions == []


# ── Bout-en-bout sur base temporaire ─────────────────────────────────────────

class TestApplyRealDB:
    def test_persistance_succession_equivalence_obsolete(self, test_db_manager):
        # L'import crée les pièces AVANT d'appliquer les relations → on simule.
        for ref in ("R1", "R2", "R3", "R4", "R5"):
            test_db_manager.execute_query(
                "INSERT OR IGNORE INTO pieces(ref_piece) VALUES (?)", [ref])
        test_db_manager.conn.commit()
        rels = [
            _rel("R1"), _rel("R2", suit_ref="R1"),                 # R1 → R2
            _rel("R3", base_replaces="OLDBASE"),                   # OLDBASE → R3
            _rel("R4", is_obsolete=True, equiv_group=1),           # obsolète + équivalence
            _rel("R5", equiv_group=1),
        ]
        counts = apply_relations(rels, test_db_manager)
        assert counts['errors'] == 0
        # Succession R1 → R2 persistée
        row = test_db_manager.execute_query(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", ["R1"])
        assert row and row[0][0] == "R2"
        # Lien base OLDBASE → R3
        row = test_db_manager.execute_query(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", ["OLDBASE"])
        assert row and row[0][0] == "R3"
        # Obsolète
        row = test_db_manager.execute_query(
            "SELECT is_obsolete FROM pieces WHERE ref_piece = ?", ["R4"])
        assert row and row[0][0] == 1
        # Équivalence R4 ≡ R5 (même group_id)
        g = test_db_manager.execute_query(
            "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece IN ('R4','R5')")
        assert len({r[0] for r in g}) == 1 and len(g) == 2
