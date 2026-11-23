"""
Syntaxe des champs de filtre de colonne : jokers * ?, « | » = OU, « ! » = sauf.

Sans joker, le filtre garde le comportement historique « contient » ; les tests
sur base réelle passent par _build_load_conditions (pages, total, export).
"""

import os
import tempfile

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.utils.filtre_colonne import (
    analyser_filtre, condition_filtre_colonne, motif_vers_like)


# ── Traduction des motifs ────────────────────────────────────────────────

@pytest.mark.parametrize('motif,attendu', [
    ('WOI4S', '%WOI4S%'),          # sans joker : contient (historique)
    ('WOI*', 'WOI%'),
    ('*S', '%S'),
    ('WOI?S*', 'WOI_S%'),
    ('*WOI*', '%WOI%'),
    ('A_B', '%A\\_B%'),            # « _ » tapé = caractère, plus un joker caché
    ('50%', '%50\\%%'),
    ('A\\B', '%A\\\\B%'),
])
def test_motif_vers_like(motif, attendu):
    assert motif_vers_like(motif) == attendu


@pytest.mark.parametrize('texte,inclus,exclus', [
    ('WOI4S', ['WOI4S'], []),
    ('WOI4S* | WOI5S*', ['WOI4S*', 'WOI5S*'], []),
    ('WOI4S*||WOI5S*', ['WOI4S*', 'WOI5S*'], []),
    ('WOI* !WOI9*', ['WOI*'], ['WOI9*']),
    ('!WOI9*', [], ['WOI9*']),
    ('A | B !C !D', ['A', 'B'], ['C', 'D']),
    ('Lave linge', ['Lave linge'], []),          # espaces gardés dans le motif
    ('Attention!', ['Attention!'], []),          # « ! » collé = texte
    ('| ! |', [], []),
])
def test_analyser_filtre(texte, inclus, exclus):
    assert analyser_filtre(texte) == (inclus, exclus)


def test_saisie_sans_filtre_effectif():
    assert condition_filtre_colonne('a.[type]', '  |  ') is None
    assert condition_filtre_colonne('a.[type]', '!') is None


def test_sql_produit():
    sql, params = condition_filtre_colonne('a.[ref_modele]', 'A* | B* !C*')
    assert sql == ("(a.[ref_modele] LIKE ? ESCAPE '\\' OR a.[ref_modele] LIKE ? ESCAPE '\\')"
                   " AND IFNULL(a.[ref_modele], '') NOT LIKE ? ESCAPE '\\'")
    assert params == ['A%', 'B%', 'C%']


# ── Sur base réelle ──────────────────────────────────────────────────────

REF = 2  # colonne ref_modele (index Config.DB_HEADERS)


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        conn.executemany(
            "INSERT INTO appareils (id, type, manufacturer, ref_modele, commercial_ref, "
            "other_ref, notes, category) VALUES (?, ?, ?, ?, '', '', ?, '')",
            [(1, 'Lave-linge', 'Whirlpool', 'WOI4S123', 'a_b'),
             (2, 'Lave-linge', 'Whirlpool', 'woi5s77', 'axb'),
             (3, 'Lave-linge', 'Whirlpool', 'WOI9S1', ''),
             (4, 'Sèche-linge', 'Whirlpool', 'WOI12S', None),
             (5, 'Four', 'Bosch', 'XWOI4S', 'remise 50%'),
             (6, 'Four', 'Bosch', 'HBA1', None)])
        conn.commit()
        manager.invalidate_search_cache(invalidate_total_count=True)
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _ids(db, filtres):
    lignes = db._load_data_original(None, filtres, None, None, None, None, False)
    ids = sorted(r[0] for r in lignes)
    # Même périmètre pour le total et l'export
    assert db.count_data(None, filtres) == len(ids)
    assert len(db.get_export_data(None, column_filters=filtres)) == len(ids)
    return ids


@pytest.mark.parametrize('texte,attendus', [
    ('WOI4S', [1, 5]),                  # contient (historique)
    ('WOI4S* | WOI5S*', [1, 2]),        # commence par, insensible à la casse
    ('WOI?S*', [1, 2, 3]),              # un seul caractère
    ('WOI*S', [4]),                     # commence par WOI ET finit par S
    ('*S1', [3]),
    ('WOI* !WOI9*', [1, 2, 4]),
    ('!WOI*', [5, 6]),
])
def test_filtre_ref_modele(db, texte, attendus):
    assert _ids(db, {REF: texte}) == attendus


def test_exclusion_garde_les_champs_vides(db):
    # Notes : NULL et '' ne contiennent pas « 50 », ils restent affichés
    assert _ids(db, {6: '!50'}) == [1, 2, 3, 4, 6]


def test_tiret_bas_et_pourcent_tapes_sont_litteraux(db):
    assert _ids(db, {6: 'a_b'}) == [1]          # plus de joker caché sur « _ »
    assert _ids(db, {6: '50%'}) == [5]


def test_alternative_sur_type_et_combinaison_de_colonnes(db):
    assert _ids(db, {0: 'Lave-linge | Sèche-linge'}) == [1, 2, 3, 4]
    assert _ids(db, {0: 'Lave-linge | Sèche-linge', REF: 'WOI?S*'}) == [1, 2, 3]
