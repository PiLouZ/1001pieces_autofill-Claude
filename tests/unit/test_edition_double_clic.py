"""Édition du tableau principal : double-clic ou F2, jamais un clic simple (3.77.1).

Depuis mars 2026, un clic sur la cellule DÉJÀ sélectionnée ouvrait l'éditeur
(surcharge de mousePressEvent, « comme le Finder »). Retour utilisateur : ce
deuxième clic dérange, il faut un vrai double-clic. Clics réels via QTest.
"""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAbstractItemView

from src.ui.custom_table_view import CustomTableView


@pytest.fixture
def table(qapp):
    model = QStandardItemModel(3, 3)
    for r in range(3):
        for c in range(3):
            model.setItem(r, c, QStandardItem(f"v{r}{c}"))
    view = CustomTableView()
    view.setModel(model)
    # Mêmes déclencheurs que table_controller.py
    view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
    view.resize(400, 200)
    view.show()
    QTest.qWaitForWindowExposed(view)
    yield view
    view.close()


def _centre(view, row, col):
    return view.visualRect(view.model().index(row, col)).center()


def _en_edition(view):
    return view.state() == QAbstractItemView.EditingState


def test_clic_sur_la_cellule_deja_selectionnee_n_edite_pas(table):
    pos = _centre(table, 1, 1)
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=pos)
    assert table.currentIndex() == table.model().index(1, 1)
    QTest.qWait(600)            # au-delà de l'intervalle de double-clic
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=pos)
    assert not _en_edition(table)


def test_double_clic_edite(table):
    # Séquence réelle d'un double-clic : appui, relâche, double-clic, relâche.
    # (En Qt 5, QTest.mouseDClick seul n'envoie pas l'appui initial, dont
    # QAbstractItemView a besoin pour accepter le double-clic.)
    pos = _centre(table, 2, 0)
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=pos)
    QTest.mouseDClick(table.viewport(), Qt.LeftButton, pos=pos)
    assert _en_edition(table)
    assert table.currentIndex() == table.model().index(2, 0)


def test_f2_edite(table):
    table.setCurrentIndex(table.model().index(0, 2))
    QTest.keyClick(table, Qt.Key_F2)
    assert _en_edition(table)


def test_frappe_sur_cellule_remplie_n_edite_pas(table):
    """Comportement volontaire (évite les modifications non désirées)."""
    table.setCurrentIndex(table.model().index(0, 0))
    QTest.keyClick(table, Qt.Key_X)
    assert not _en_edition(table)
    assert table.model().index(0, 0).data() == "v00"
