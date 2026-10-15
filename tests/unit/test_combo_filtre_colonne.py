"""Tests de la liste de filtre Type/Marque (ComboFiltreColonne).

Régression visée : le bouton RAZ appelait setCurrentIndex(0) sur une liste
modifiable vide → sans effet, le texte du filtre Type restait en place.
"""
import pytest

from src.ui.table_controller import ComboFiltreColonne


@pytest.fixture
def combo(qapp):
    valeurs = ["Aspirateur", "Lave-linge", "Sèche-linge"]
    c = ComboFiltreColonne(lambda: list(valeurs))
    c.valeurs = valeurs
    c.rafraichir_valeurs()
    return c


def test_liste_complete_sans_selection_initiale(combo):
    assert [combo.itemText(i) for i in range(combo.count())] == combo.valeurs
    assert combo.currentText() == ""


def test_vider_saisie_apres_selection(combo):
    combo.setCurrentIndex(1)
    assert combo.currentText() == "Lave-linge"
    combo.vider_saisie()
    assert combo.currentText() == ""


def test_vider_saisie_apres_frappe_libre(combo):
    combo.setEditText("lin")
    combo.vider_saisie()
    assert combo.currentText() == ""


def test_rechargement_conserve_le_texte_saisi(combo):
    combo.setEditText("Lave-linge")
    emis = []
    combo.currentTextChanged.connect(emis.append)
    combo.valeurs.append("Four")
    combo.rafraichir_valeurs()
    assert combo.findText("Four") >= 0
    assert combo.currentText() == "Lave-linge"
    assert emis == []  # pas de filtrage parasite pendant le rechargement


def test_entree_n_ajoute_pas_la_saisie(combo):
    from PyQt5.QtTest import QTest
    from PyQt5.QtCore import Qt
    combo.setEditText("bo")
    QTest.keyClick(combo.lineEdit(), Qt.Key_Return)
    assert combo.count() == 3
    assert combo.currentText() == "bo"


def test_completion_par_sous_chaine(combo):
    completer = combo.completer()
    completer.setCompletionPrefix("linge")
    trouves = [completer.completionModel().index(i, 0).data()
               for i in range(completer.completionCount())]
    assert trouves == ["Lave-linge", "Sèche-linge"]
