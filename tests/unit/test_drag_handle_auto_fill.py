"""
Tests du double-clic sur la poignée de recopie (DragHandle._auto_fill).

Règle : remplir vers le bas tant que les cellules sont vides ; si rien n'est
à remplir en bas, remplir vers le haut.
"""

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QItemSelection, QItemSelectionModel
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QApplication, QTableView

from src.services.drag_handle_service import DragHandle


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Table(QTableView):
    """QTableView avec l'API rowCount() utilisée par la poignée (comme CustomTableView)."""

    def rowCount(self):
        return self.model().rowCount()


def _double_clic(grid, top, bottom, col=0):
    """Sélectionner [top..bottom] sur une colonne, lancer l'auto-remplissage."""
    model = QStandardItemModel(len(grid), 1)
    for r, v in enumerate(grid):
        model.setItem(r, 0, QStandardItem(v))
    table = _Table()
    table.setModel(model)
    handle = DragHandle(table=table, main_window=MagicMock())
    table.selectionModel().select(
        QItemSelection(model.index(top, col), model.index(bottom, col)),
        QItemSelectionModel.ClearAndSelect,
    )
    handle._auto_fill()
    valeurs = [model.data(model.index(r, 0)) or "" for r in range(len(grid))]
    historique = [c.args[0] for c in
                  handle.main_window.user_interaction_service.add_to_history.call_args_list]
    sel = handle._get_current_selection()
    return valeurs, historique, (sel.topRow(), sel.bottomRow())


def test_bas_inchange(app):
    valeurs, hist, sel = _double_clic(["A", "", "", "Z"], 0, 0)
    assert valeurs == ["A", "A", "A", "Z"]
    assert hist == ["Duplication automatique vers le bas"]
    assert sel == (0, 2)


def test_bas_prioritaire_quand_haut_et_bas_vides(app):
    valeurs, hist, _ = _double_clic(["", "A", ""], 1, 1)
    assert valeurs == ["", "A", "A"]
    assert hist == ["Duplication automatique vers le bas"]


def test_haut_si_dessous_rempli(app):
    valeurs, hist, sel = _double_clic(["Z", "", "", "A", "B"], 3, 3)
    assert valeurs == ["Z", "A", "A", "A", "B"]
    assert hist == ["Duplication automatique vers le haut"]
    assert sel == (1, 3)


def test_haut_si_derniere_ligne(app):
    valeurs, hist, _ = _double_clic(["", "", "A"], 2, 2)
    assert valeurs == ["A", "A", "A"]
    assert hist == ["Duplication automatique vers le haut"]


def test_haut_prolonge_le_motif(app):
    """Sélection A, B → au-dessus : … A, B (et non B, A, A, B)."""
    valeurs, _, _ = _double_clic(["", "", "", "A", "B"], 3, 4)
    assert valeurs == ["B", "A", "B", "A", "B"]


def test_rien_si_haut_et_bas_remplis(app):
    valeurs, hist, _ = _double_clic(["Z", "A", "Y"], 1, 1)
    assert valeurs == ["Z", "A", "Y"]
    assert hist == []


def test_rien_si_premiere_ligne_et_dessous_rempli(app):
    valeurs, hist, _ = _double_clic(["A", "Y"], 0, 0)
    assert valeurs == ["A", "Y"]
    assert hist == []


# ── Glisser vers le haut (DragHandle._fill_cells_up) ────────────────────────

def _glisser_haut(grid, top, bottom, nb_lignes):
    """Simuler un glisser de nb_lignes vers le haut depuis la sélection [top..bottom]."""
    model = QStandardItemModel(len(grid), 1)
    for r, v in enumerate(grid):
        model.setItem(r, 0, QStandardItem(v))
    table = _Table()
    table.setModel(model)
    handle = DragHandle(table=table, main_window=MagicMock())
    table.selectionModel().select(
        QItemSelection(model.index(top, 0), model.index(bottom, 0)),
        QItemSelectionModel.ClearAndSelect,
    )
    handle.orig_selection = handle._get_current_selection()
    handle._fill_cells_up(nb_lignes)
    return [model.data(model.index(r, 0)) or "" for r in range(len(grid))]


def test_glisser_haut_une_ligne_inchange(app):
    assert _glisser_haut(["", "", "A", "Z"], 2, 2, 2) == ["A", "A", "A", "Z"]


def test_glisser_haut_prolonge_le_motif(app):
    """Sélection A, B → au-dessus : … A, B (avant le correctif : B, A, A, B)."""
    assert _glisser_haut(["", "", "", "A", "B"], 3, 4, 3) == ["B", "A", "B", "A", "B"]


def test_glisser_haut_motif_trois_lignes(app):
    assert _glisser_haut(["", "", "", "", "A", "B", "C"], 4, 6, 4) == \
        ["C", "A", "B", "C", "A", "B", "C"]
