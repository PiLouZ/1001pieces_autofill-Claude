"""
Tests — Zones des modèles HTML (configuration des exports, v3.99.2)

Le code englobant (143 caractères chez l'utilisateur) était à moitié caché dans
un champ d'une ligne. Zone multi-ligne qui s'agrandit (4 lignes au plus), mais
le modèle reste sur UNE ligne logique : les exports ne changent pas.
"""

import pytest
from PyQt5.QtCore import Qt, QMimeData
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from src.ui.champ_modele_html import ChampModeleHtml


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def champ(app):
    c = ChampModeleHtml()
    c.resize(430, 30)
    c.show()
    app.processEvents()
    yield c
    c.close()


def test_interface_comme_qlineedit(champ):
    champ.setText("<div>{appareils}</div>")
    assert champ.text() == "<div>{appareils}</div>"
    champ.moveCursor(11)  # fin
    champ.insert("{marque}")
    assert champ.text() == "<div>{appareils}</div>{marque}"


def test_entree_n_ajoute_pas_de_saut_de_ligne(champ):
    champ.setText("<div>")
    champ.setFocus()
    QTest.keyClick(champ, Qt.Key_Return)
    QTest.keyClick(champ, Qt.Key_Enter)
    assert champ.text() == "<div>"


def test_sauts_de_ligne_remplaces_par_des_espaces(champ):
    champ.setText("<p>\nA\r\nB</p>")
    assert champ.text() == "<p> A B</p>"
    donnees = QMimeData()
    donnees.setText("\n<i>x</i>\n")
    champ.insertFromMimeData(donnees)
    assert "\n" not in champ.text()


def test_hauteur_suit_le_contenu_jusqu_a_4_lignes(app, champ):
    champ.setText("<div>")
    app.processEvents()
    une_ligne = champ.height()
    champ.setText('<div>&nbsp;</div><div class="class_perso4">Appareils compatibles :</div>'
                  '<div>&nbsp;</div><div class="class_perso5"><div>{appareils}</div></div>')
    app.processEvents()
    assert 1 < champ._nb_lignes_affichees() <= 4
    assert champ.height() > une_ligne
    champ.setText("x" * 2000)
    app.processEvents()
    assert champ._nb_lignes_affichees() > 4
    quatre = champ.height()
    champ.setText("x" * 4000)
    app.processEvents()
    assert champ.height() == quatre
