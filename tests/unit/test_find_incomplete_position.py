"""find_incomplete_position : la position SQL de la prochaine ligne incomplète
doit désigner EXACTEMENT la ligne que l'utilisateur verrait en parcourant les
pages (LIMIT/OFFSET de load_data), pour tous les tris — y compris avec des
milliers d'ex-æquo, des NULL et des chaînes vides dans la colonne triée."""

import random

import pytest

from src.core.config import Config

PAGE = 7
TYPES = ["Four", "Lave-linge", "", None]
FABS = ["Bosch", "Miele", "", None]


@pytest.fixture
def db(test_db_manager):
    rnd = random.Random(42)
    rows = []
    for i in range(80):
        rows.append((
            rnd.choice(TYPES) if rnd.random() < 0.2 else rnd.choice(TYPES[:2]),
            rnd.choice(FABS) if rnd.random() < 0.2 else rnd.choice(FABS[:2]),
            f"REF{rnd.randint(0, 9)}",            # beaucoup d'ex-æquo
            rnd.choice(["A", "B", None]),
            rnd.choice(["X", ""]),
            rnd.choice(["Cat1", "Cat2"]),
            rnd.choice(["note", "", None]),       # tri sans index
        ))
    test_db_manager.cursor.executemany(
        "INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref,"
        " other_ref, category, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    test_db_manager.conn.commit()
    return test_db_manager


def _pages_concatenees(db, sort_col, order, filters, inc):
    """Ce que l'utilisateur voit en tournant les pages une à une."""
    lignes, offset = [], 0
    while True:
        page = db.load_data(None, filters, PAGE, offset, sort_col, order, inc)
        if not page:
            return lignes
        lignes.extend(page)
        offset += PAGE


def _incomplete(rec):
    return not (rec[1] or '').strip() or not (rec[2] or '').strip()


TRIS = [(None, None)] + [(c, o) for c in range(len(Config.DB_HEADERS)) for o in ("ASC", "DESC")]


@pytest.mark.parametrize("sort_col,order", TRIS)
@pytest.mark.parametrize("filters,inc", [(None, False), ({5: "Cat1"}, False), (None, True)])
def test_position_sql_egale_parcours_des_pages(db, sort_col, order, filters, inc):
    vues = _pages_concatenees(db, sort_col, order, filters, inc)
    positions = [i for i, r in enumerate(vues) if _incomplete(r)]
    assert positions, "jeu de données sans ligne incomplète : test inopérant"
    for depart in range(-1, len(vues) + 1):
        attendu_bas = next((p for p in positions if p > depart), None)
        attendu_haut = next((p for p in reversed(positions) if p < depart), None)
        assert db.find_incomplete_position(None, filters, sort_col, order, inc, depart, 'down') == attendu_bas
        assert db.find_incomplete_position(None, filters, sort_col, order, inc, depart, 'up') == attendu_haut


def test_aucune_ligne_incomplete_retourne_none(db):
    db.cursor.execute("UPDATE appareils SET type = 'Four', manufacturer = 'Bosch'")
    db.conn.commit()
    assert db.find_incomplete_position(None, None, 0, "ASC", False, -1, 'down') is None
    assert db.find_incomplete_position(None, None, 0, "ASC", False, 10_000, 'up') is None


def test_tri_nb_pieces_refuse(db):
    """Tri « Nb pièces » : ValueError, et surtout pas None (qui griserait la flèche)."""
    with pytest.raises(ValueError):
        db.find_incomplete_position(None, None, len(Config.DB_HEADERS), "ASC", False, 0, 'down')


def test_tri_par_colonne_departage_par_id(db):
    """Les pages et la position SQL partagent un ORDER BY départagé par id."""
    assert db._build_load_order_by(0, "ASC") == " ORDER BY a.[type] ASC, a.id ASC"
    assert db._build_load_order_by(6, "DESC") == " ORDER BY a.[notes] DESC, a.id DESC"
    assert db._build_load_order_by(None, None) == " ORDER BY a.id DESC"
    assert db._build_load_order_by(len(Config.DB_HEADERS), "ASC") == " ORDER BY pieces_count ASC"
