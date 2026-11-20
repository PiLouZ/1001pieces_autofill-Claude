"""
Tables vides retirées (2026-11-20) : `categories` (menu Affichage → « Catégories »,
liste que rien ne relisait) et `pieces_old` (copie de travail de la migration
vers piece_associations), recréées vides à chaque démarrage.

- une base qui les a encore les perd au démarrage, si elles sont vides ;
- une table non vide est gardée ;
- une base d'avant la normalisation s'ouvre sans laisser de `pieces_old`.
"""

import sqlite3

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager


def _tables(chemin):
    conn = sqlite3.connect(chemin)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


@pytest.fixture
def chemin_base(tmp_path, monkeypatch):
    chemin = str(tmp_path / 'base.db')
    monkeypatch.setattr(Config, 'DB_FILE', chemin)
    monkeypatch.setattr(Config, 'SEARCH_PIECES_ONLY', False)
    return chemin


def _ouvrir(chemin):
    db = DatabaseManager(chemin)
    db.conn.close()


def test_base_neuve_sans_les_tables(chemin_base):
    _ouvrir(chemin_base)
    tables = _tables(chemin_base)
    assert 'pieces' in tables and 'piece_associations' in tables
    assert 'categories' not in tables and 'pieces_old' not in tables


def test_tables_vides_supprimees_au_demarrage(chemin_base):
    _ouvrir(chemin_base)
    conn = sqlite3.connect(chemin_base)
    conn.executescript("""
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                                 description TEXT, created_at TIMESTAMP);
        CREATE TABLE pieces_old (id INTEGER PRIMARY KEY, ref_piece TEXT NOT NULL,
                                 appareil_id INTEGER, description TEXT, created_at TIMESTAMP);
    """)
    conn.close()
    _ouvrir(chemin_base)
    tables = _tables(chemin_base)
    assert 'categories' not in tables and 'pieces_old' not in tables


def test_table_non_vide_conservee(chemin_base):
    _ouvrir(chemin_base)
    conn = sqlite3.connect(chemin_base)
    conn.executescript("""
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        INSERT INTO categories (name) VALUES ('Four');
    """)
    conn.commit()
    conn.close()
    _ouvrir(chemin_base)
    assert 'categories' in _tables(chemin_base)


def test_ancienne_base_sans_table_persistante(chemin_base):
    """Base d'avant la normalisation : une ligne de `pieces` par appareil.

    Constat du 2026-11-20, identique sur `main` avant ce changement : la
    vieille migration ne retrouve plus ces pièces (une étape antérieure du
    démarrage les perd). On vérifie seulement ici que l'ouverture se passe et
    ne laisse pas de `pieces_old` dans la base."""
    conn = sqlite3.connect(chemin_base)
    conn.executescript("""
        CREATE TABLE appareils (id INTEGER PRIMARY KEY, type TEXT, manufacturer TEXT,
                                ref_modele TEXT, commercial_ref TEXT, other_ref TEXT,
                                category TEXT, notes TEXT, created_at TIMESTAMP,
                                updated_at TIMESTAMP);
        CREATE TABLE pieces (id INTEGER PRIMARY KEY, ref_piece TEXT NOT NULL,
                             appareil_id INTEGER, description TEXT, created_at TIMESTAMP);
        INSERT INTO appareils (id, type, ref_modele) VALUES (1, 'Four', 'M1'), (2, 'Four', 'M2');
        INSERT INTO pieces (ref_piece, appareil_id, description) VALUES
            ('P1', 1, 'Joint'), ('P1', 2, NULL), ('P2', 2, 'Résistance');
    """)
    conn.commit()
    conn.close()

    _ouvrir(chemin_base)

    assert 'pieces_old' not in _tables(chemin_base)
