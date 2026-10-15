"""
Tests — Activation des clés étrangères SQLite (v3.85.0)

Jusqu'à la v3.84.x, `PRAGMA foreign_keys` n'était activé nulle part : les
FOREIGN KEY du schéma étaient purement déclaratives. 94 918 associations
orphelines s'étaient accumulées en 2025 sans que rien ne le signale (nettoyées
par `scripts/nettoyage_associations_orphelines.py`).

Activer les clés a révélé deux choses, couvertes ici :
  - sur une base NEUVE, `piece_associations.piece_id` pointait vers
    `pieces_new(id)`, table inexistante (reliquat de migration) ;
  - renommer une pièce liée par une relation violait la contrainte le temps
    d'une instruction : la vérification est différée jusqu'au COMMIT.
"""

import sqlite3

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager


def _fk(db):
    return db.conn.execute("PRAGMA foreign_keys").fetchone()[0]


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


@pytest.fixture
def appareil(db):
    db.conn.execute("INSERT INTO appareils (ref_modele) VALUES ('MODELE_FK')")
    db.conn.commit()
    return db.conn.execute("SELECT id FROM appareils WHERE ref_modele = 'MODELE_FK'").fetchone()[0]


class TestActivation:

    def test_actives_par_defaut(self, db):
        assert Config.FOREIGN_KEYS is True
        assert _fk(db) == 1

    def test_interrupteur_desactive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, "FOREIGN_KEYS", False)
        db = DatabaseManager(str(tmp_path / "sans_cles.db"))
        try:
            assert _fk(db) == 0
        finally:
            db.conn.close()

    def test_migrations_tournent_cles_desactivees(self, tmp_path, monkeypatch):
        """Les migrations de l'ancien schéma font DROP TABLE pieces : clés actives,
        les ON DELETE CASCADE videraient les associations. Elles doivent donc
        s'exécuter AVANT l'activation."""
        etats = []
        originale = DatabaseManager._setup_database

        def espion(self):
            etats.append(self.conn.execute("PRAGMA foreign_keys").fetchone()[0])
            return originale(self)

        monkeypatch.setattr(DatabaseManager, "_setup_database", espion)
        db = DatabaseManager(str(tmp_path / "ordre.db"))
        try:
            assert etats == [0]
            assert _fk(db) == 1
        finally:
            db.conn.close()


class TestSchemaNeuf:

    def test_toutes_les_cles_visent_une_table_existante(self, db):
        """Base neuve : `piece_associations.piece_id` visait `pieces_new`."""
        tables = {r[0] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        cibles = {}
        for table in tables:
            for r in db.conn.execute(f"PRAGMA foreign_key_list('{table}')"):
                cibles[f"{table}.{r[3]}"] = r[2]
        assert cibles["piece_associations.piece_id"] == "pieces"
        absentes = {k: v for k, v in cibles.items() if v not in tables}
        assert absentes == {}

    def test_aucune_violation_sur_base_neuve(self, db):
        assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []


class TestRejet:

    def test_association_vers_piece_absente_refusee(self, db, appareil):
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)",
                (999_999, appareil))
        db.conn.rollback()

    def test_association_vers_appareil_absent_refusee(self, db):
        db.create_piece_standalone("PIECE_FK", "")
        piece_id = db.conn.execute(
            "SELECT id FROM pieces WHERE ref_piece = 'PIECE_FK'").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)",
                (piece_id, 999_999))
        db.conn.rollback()

    def test_chemin_normal_accepte(self, db, appareil):
        assert db.add_piece("PIECE_OK", appareil, "Joint") > 0
        assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []


class TestRenommage:

    def test_renommage_d_une_piece_en_succession_et_equivalence(self, db):
        assert _fk(db) == 1
        for ref in ("ANCIENNE", "NOUVELLE", "EQUIV"):
            db.create_piece_standalone(ref, "")
        assert db.add_supersession("ANCIENNE", "NOUVELLE")[0]
        assert db.add_equivalence("ANCIENNE", "EQUIV")[0]

        assert db.rename_piece_catalog("ANCIENNE", "ANCIENNE_V2", "Libellé") is True

        assert db.conn.execute(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old = 'ANCIENNE_V2'"
        ).fetchone() == ("NOUVELLE",)
        assert db.conn.execute(
            "SELECT COUNT(*) FROM piece_equivalence_groups WHERE ref_piece = 'ANCIENNE_V2'"
        ).fetchone()[0] == 1
        assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_le_report_ne_survit_pas_au_renommage(self, db):
        """`defer_foreign_keys` se remet à OFF au COMMIT : les opérations
        suivantes sont de nouveau vérifiées immédiatement."""
        db.create_piece_standalone("A_RENOMMER", "")
        assert db.rename_piece_catalog("A_RENOMMER", "RENOMMEE", "") is True
        assert db.conn.execute("PRAGMA defer_foreign_keys").fetchone()[0] == 0


class TestSuppression:

    def test_supprimer_un_appareil_ne_laisse_pas_d_orphelin(self, db, appareil):
        db.add_piece("PIECE_A", appareil, "")
        assert db.delete_appareil(appareil) is True
        assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_supprimer_une_piece_liee(self, db, appareil):
        db.add_piece("PIECE_LIEE", appareil, "")
        db.add_supersession("PIECE_LIEE", "REMPLACANTE")
        db.delete_piece_catalog("PIECE_LIEE")
        assert db.conn.execute(
            "SELECT COUNT(*) FROM piece_associations").fetchone()[0] == 0
        assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []
