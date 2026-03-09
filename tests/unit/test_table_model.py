"""
Tests unitaires pour AppareillsTableModel
Migration QTableWidget → QTableView — Phase 0 (TDD Red)

Ces tests sont écrits AVANT l'implémentation (Phase 1).
Ils doivent tous ÉCHOUER en Phase 0 (ImportError attendu).
Ils doivent tous PASSER en Phase 1.

Structure d'un record : (db_id, type, manufacturer, ref_modele,
                          commercial_ref, other_ref, category, notes, pieces_count)
"""

import pytest
from unittest.mock import MagicMock
from PyQt5.QtCore import Qt, QModelIndex

# ⚠️ Import intentionnellement en échec en Phase 0 — passera au vert en Phase 1
from src.data.appareils_table_model import AppareillsTableModel

from src.core.config import Config


# ── Fixtures ────────────────────────────────────────────────────────────────

def make_record(db_id=1, type_="Lave-vaisselle", manufacturer="Bosch",
                ref_modele="SMS46AW03E", commercial_ref="Serie 4",
                other_ref="TEST-001", category="Electroménager",
                notes="Note test", pieces_count=0):
    """Crée un tuple record au format attendu par la DB."""
    return (db_id, type_, manufacturer, ref_modele, commercial_ref,
            other_ref, category, notes, pieces_count)


@pytest.fixture
def model(qapp):
    """AppareillsTableModel vide, prêt à l'emploi."""
    return AppareillsTableModel()


@pytest.fixture
def model_with_records(qapp):
    """AppareillsTableModel chargé avec 3 enregistrements de test."""
    m = AppareillsTableModel()
    records = [
        make_record(db_id=1, type_="Lave-vaisselle", manufacturer="Bosch", pieces_count=3),
        make_record(db_id=2, type_="Lave-linge", manufacturer="Samsung", pieces_count=0),
        make_record(db_id=3, type_="Micro-ondes", manufacturer="Whirlpool",
                    ref_modele="MWP254W", pieces_count=5),
    ]
    m.load_records(records)
    return m


# ── Phase 0 · Test 1 : load_records déclenche un reset du modèle ─────────────

def test_load_records_emits_model_reset(qapp):
    """load_records() doit émettre modelReset pour que la vue se rafraîchisse."""
    m = AppareillsTableModel()
    reset_fired = []
    m.modelReset.connect(lambda: reset_fired.append(True))

    m.load_records([make_record(db_id=10)])

    assert len(reset_fired) == 1, "modelReset doit être émis une fois après load_records()"


# ── Phase 0 · Test 2 : rowCount après chargement ─────────────────────────────

def test_rowcount_after_load(model_with_records):
    """rowCount() doit correspondre au nombre de records chargés."""
    assert model_with_records.rowCount() == 3


# ── Phase 0 · Test 3 : columnCount = len(UI_HEADERS) ─────────────────────────

def test_columncount_equals_ui_headers(model):
    """columnCount() doit correspondre au nombre de colonnes UI."""
    assert model.columnCount() == len(Config.UI_HEADERS)


# ── Phase 0 · Test 4 : data() DisplayRole retourne une string ────────────────

def test_data_display_role_returns_string(model_with_records):
    """data(index, DisplayRole) doit retourner le texte de la cellule."""
    # Colonne 0 = Type, row 0 = "Lave-vaisselle"
    idx = model_with_records.index(0, 0)
    value = model_with_records.data(idx, Qt.DisplayRole)
    assert value == "Lave-vaisselle"

    # Colonne 1 = Fabricant, row 1 = "Samsung"
    idx = model_with_records.index(1, 1)
    value = model_with_records.data(idx, Qt.DisplayRole)
    assert value == "Samsung"


# ── Phase 0 · Test 5 : data() UserRole retourne le db_id ─────────────────────

def test_data_user_role_returns_db_id(model_with_records):
    """data(index, UserRole) doit retourner le db_id du record.
    Remplace item(row, col).data(Qt.UserRole) dans l'ensemble du code.
    """
    for row in range(3):
        idx = model_with_records.index(row, 0)
        db_id = model_with_records.data(idx, Qt.UserRole)
        assert db_id == row + 1, f"Row {row} : db_id attendu {row + 1}, obtenu {db_id}"


# ── Phase 0 · Test 6 : get_db_id() — API raccourci ───────────────────────────

def test_get_db_id_returns_correct_value(model_with_records):
    """get_db_id(row) doit retourner le db_id sans passer par QModelIndex.
    Remplace item(row, col).data(Qt.UserRole) pour les cas simples.
    """
    assert model_with_records.get_db_id(0) == 1
    assert model_with_records.get_db_id(1) == 2
    assert model_with_records.get_db_id(2) == 3
    assert model_with_records.get_db_id(99) is None  # Hors limites → None


# ── Phase 0 · Test 7 : setData émet cell_edited ──────────────────────────────

def test_setdata_emits_cell_edited(model_with_records):
    """setData() doit émettre cell_edited(row, col, old_value, new_value).
    C'est le signal qui remplace itemChanged de QTableWidget.
    Le EventDrivenSaveService se branchera dessus.
    """
    emitted = []
    model_with_records.cell_edited.connect(
        lambda r, c, old, new: emitted.append((r, c, old, new))
    )

    idx = model_with_records.index(0, 0)  # Row 0, col Type
    result = model_with_records.setData(idx, "Réfrigérateur", Qt.EditRole)

    assert result is True, "setData doit retourner True en cas de succès"
    assert len(emitted) == 1
    row, col, old_val, new_val = emitted[0]
    assert row == 0
    assert col == 0
    assert old_val == "Lave-vaisselle"
    assert new_val == "Réfrigérateur"


# ── Phase 0 · Test 8 : setData émet dataChanged ──────────────────────────────

def test_setdata_emits_dataChanged(qapp):
    """setData() doit émettre dataChanged pour forcer le refresh visuel de la vue."""
    m = AppareillsTableModel()
    m.load_records([make_record(db_id=1)])

    changed = []
    m.dataChanged.connect(lambda tl, br, roles: changed.append((tl.row(), tl.column())))

    idx = m.index(0, 2)  # Référence Modèle
    m.setData(idx, "NEW-REF", Qt.EditRole)

    assert len(changed) == 1
    assert changed[0] == (0, 2)


# ── Phase 0 · Test 9 : colonne Nb Pièces non éditable ────────────────────────

def test_pieces_column_not_editable(model_with_records):
    """La dernière colonne (Nb Pièces) doit être en lecture seule.
    Remplace item.setFlags(flags & ~Qt.ItemIsEditable) de table_fill_service.
    """
    pieces_col = len(Config.DB_HEADERS)  # Index 7 = Nb Pièces

    for row in range(model_with_records.rowCount()):
        idx = model_with_records.index(row, pieces_col)
        flags = model_with_records.flags(idx)
        assert not (flags & Qt.ItemIsEditable), \
            f"Row {row}, col Nb Pièces ne doit PAS être éditable"

    # Vérifier qu'une colonne normale EST éditable
    idx_normal = model_with_records.index(0, 0)
    assert model_with_records.flags(idx_normal) & Qt.ItemIsEditable


# ── Phase 0 · Test 10 : BackgroundRole — couleur Nb Pièces ───────────────────

def test_pieces_background_green_when_nonzero(model_with_records):
    """BackgroundRole doit retourner vert pour pieces_count > 0, gris sinon.
    Remplace item.setBackground() de table_fill_service.
    """
    from PyQt5.QtGui import QColor
    pieces_col = len(Config.DB_HEADERS)

    # Row 0 : pieces_count = 3 → vert clair
    idx_green = model_with_records.index(0, pieces_col)
    bg_green = model_with_records.data(idx_green, Qt.BackgroundRole)
    assert bg_green is not None, "BackgroundRole ne doit pas être None pour pieces > 0"
    color = bg_green.color() if hasattr(bg_green, 'color') else bg_green
    assert color == QColor(220, 248, 198), f"Couleur verte attendue, obtenu {color.name()}"

    # Row 1 : pieces_count = 0 → gris clair
    idx_grey = model_with_records.index(1, pieces_col)
    bg_grey = model_with_records.data(idx_grey, Qt.BackgroundRole)
    assert bg_grey is not None
    color_grey = bg_grey.color() if hasattr(bg_grey, 'color') else bg_grey
    assert color_grey == QColor(248, 248, 248), f"Couleur grise attendue, obtenu {color_grey.name()}"


# ── Phase 0 · Test 11 : setData met à jour le record en mémoire ──────────────

def test_setdata_updates_record_in_memory(model_with_records):
    """Après setData(), data() doit retourner la nouvelle valeur.
    Garantit la cohérence modèle ↔ vue sans rechargement DB.
    """
    idx = model_with_records.index(0, 1)  # Row 0, Fabricant
    model_with_records.setData(idx, "Siemens", Qt.EditRole)

    new_val = model_with_records.data(idx, Qt.DisplayRole)
    assert new_val == "Siemens"


# ── Phase 0 · Test 12 : headerData colonnes ──────────────────────────────────

def test_headerdata_returns_column_names(model):
    """headerData() doit retourner les noms de colonnes de Config.UI_HEADERS."""
    for col, expected_header in enumerate(Config.UI_HEADERS):
        result = model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
        assert result == expected_header, \
            f"Col {col} : header attendu '{expected_header}', obtenu '{result}'"


# ── Phase 0 · Test 13 : headerData lignes (1-indexé) ─────────────────────────

def test_headerdata_rows_are_1indexed(model_with_records):
    """Les en-têtes de ligne doivent afficher '1', '2', '3'...
    Reproduit le comportement de setVerticalHeaderItem(row, QTableWidgetItem(str(row+1))).
    """
    for row in range(model_with_records.rowCount()):
        result = model_with_records.headerData(row, Qt.Vertical, Qt.DisplayRole)
        assert result == str(row + 1), \
            f"Row {row} : header attendu '{row + 1}', obtenu '{result}'"
