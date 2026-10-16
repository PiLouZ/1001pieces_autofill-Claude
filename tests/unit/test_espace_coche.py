"""
Touche Espace = cocher/décocher la case de la ligne courante (v3.89.1)

Généralisation du comportement de la fenêtre des doublons à toutes les vues à
cases, quelle que soit la colonne courante. Seule la ligne courante bascule.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem

from src.services.cleanup_ui_service import KeyboardTreeWidget
from src.ui.espace_coche import activer_espace_coche


def _arbre_doublons():
    """Groupe sans case + 2 appareils cochables, comme la fenêtre des doublons."""
    arbre = KeyboardTreeWidget()
    arbre.setColumnCount(3)
    groupe = QTreeWidgetItem(arbre, ["", "Groupe"])
    appareils = []
    for nom in ("A1", "A2"):
        item = QTreeWidgetItem(groupe, ["", nom, "Four"])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Unchecked)
        appareils.append(item)
    groupe.setExpanded(True)
    return arbre, groupe, appareils


def test_doublons_appareil_bascule_depuis_une_autre_colonne(qapp):
    arbre, _, (a1, a2) = _arbre_doublons()
    arbre.setCurrentItem(a1, 2)                 # colonne Type, pas celle de la case
    QTest.keyClick(arbre, Qt.Key_Space)
    assert a1.checkState(0) == Qt.Checked
    assert a2.checkState(0) == Qt.Unchecked     # seule la ligne courante
    QTest.keyClick(arbre, Qt.Key_Space)
    assert a1.checkState(0) == Qt.Unchecked


def test_doublons_groupe_sans_case_reste_sans_case(qapp):
    arbre, groupe, _ = _arbre_doublons()
    arbre.setCurrentItem(groupe, 1)
    QTest.keyClick(arbre, Qt.Key_Space)
    assert groupe.data(0, Qt.CheckStateRole) is None


def test_maj_espace_ne_coche_pas(qapp):
    arbre, _, (a1, _) = _arbre_doublons()
    arbre.setCurrentItem(a1, 1)
    QTest.keyClick(arbre, Qt.Key_Space, Qt.ShiftModifier)
    assert a1.checkState(0) == Qt.Unchecked


def test_references_distinctes_elements_de_premier_niveau(qapp):
    """Arbre « Références distinctes » : cases sur des éléments sans parent,
    que l'ancien code ignorait."""
    arbre = KeyboardTreeWidget()
    arbre.setColumnCount(2)
    item = QTreeWidgetItem(arbre, ["", "REF1"])
    item.setCheckState(0, Qt.Unchecked)
    arbre.setCurrentItem(item, 1)
    QTest.keyClick(arbre, Qt.Key_Space)
    assert item.checkState(0) == Qt.Checked


def test_tableau_a_cases(qapp):
    """QTableWidget (pièces en double) : case en colonne 0, curseur en colonne 1."""
    table = QTableWidget(2, 2)
    for ligne in range(2):
        case = QTableWidgetItem()
        case.setFlags((case.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
        case.setCheckState(Qt.Unchecked)
        table.setItem(ligne, 0, case)
        table.setItem(ligne, 1, QTableWidgetItem(f"P{ligne}"))
    activer_espace_coche(table)
    table.setCurrentCell(1, 1)
    QTest.keyClick(table, Qt.Key_Space)
    assert table.item(1, 0).checkState() == Qt.Checked
    assert table.item(0, 0).checkState() == Qt.Unchecked


def test_vue_sans_cases_touche_non_consommee(qapp):
    arbre = QTreeWidget()
    item = QTreeWidgetItem(arbre, ["texte"])
    activer_espace_coche(arbre)
    arbre.setCurrentItem(item)
    QTest.keyClick(arbre, Qt.Key_Space)
    assert item.data(0, Qt.CheckStateRole) is None


def test_fenetre_suggestions(qapp):
    from src.ui.suggestion_validation_dialog import SuggestionValidationDialog, COL_CHECK, COL_REF
    entree = {'db_id': 1, 'ref_modele': 'R1', 'commercial_ref': '', 'candidates': [
        {'type': 'Four', 'manufacturer': 'Bosch', 'score': 0.87, 'ref': 'X',
         'confidence_tier': 'B_fuzzy_alpha'}]}
    fenetre = SuggestionValidationDialog(None, [entree], on_validate=None)
    feuille = fenetre._leaves[0]
    avant = feuille.checkState(COL_CHECK)
    fenetre._tree.setCurrentItem(feuille, COL_REF)
    QTest.keyClick(fenetre._tree, Qt.Key_Space)
    assert feuille.checkState(COL_CHECK) != avant
    assert fenetre._validate_btn.text().endswith(
        f"({1 if feuille.checkState(COL_CHECK) == Qt.Checked else 0})")


def test_fenetre_autocompletes(qapp):
    from src.ui.autocompletion_review_dialog import (
        AutocompletionReviewDialog, regrouper_traces, COL_CHECK, COL_REF)
    lignes = [(1, 'R1', '', 'Four', 'Bosch', 'type', 'Four', 'S', 1, 1, '2026-10-16 08:00:00')]
    fenetre = AutocompletionReviewDialog(None, regrouper_traces(lignes), on_validate=None)
    item = fenetre._items[0]
    fenetre._tree.setCurrentItem(item, COL_REF)
    QTest.keyClick(fenetre._tree, Qt.Key_Space)        # coché d'office → décoché
    assert item.checkState(COL_CHECK) == Qt.Unchecked
    assert fenetre._validate_btn.text() == "Marquer comme vérifiés (0)"
