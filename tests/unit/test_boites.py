"""
src/utils/boites.py : équivalents non bloquants des boîtes statiques de Qt.
Chaque fonction rend la main avant la réponse ; le rappel ne part qu'à la validation.
"""

import os
import tempfile

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from src.utils import boites


def _vider(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)


@pytest.fixture
def parent(qapp):
    w = QWidget()
    yield w
    _vider(qapp)


@pytest.mark.parametrize('bouton,oui,non', [(QMessageBox.Yes, [1], []), (QMessageBox.No, [], [1])])
def test_oui_non(parent, bouton, oui, non):
    o, n = [], []
    b = boites.demander_oui_non(parent, "T", "Sûr ?", lambda: o.append(1), lambda: n.append(1))
    assert b.isVisible() and b.isModal() and (o, n) == ([], [])
    b.button(bouton).click()
    assert (o, n) == (oui, non)


def test_oui_non_defaut_et_echap(parent):
    o, n = [], []
    b = boites.demander_oui_non(parent, "T", "M", lambda: o.append(1), lambda: n.append(1))
    assert b.defaultButton() is b.button(QMessageBox.No)
    assert b.escapeButton() is b.button(QMessageBox.No)     # Échap vaut « Non »
    b.reject()                                              # la croix aussi
    assert (o, n) == ([], [1])


def test_oui_non_sans_defaut_laisse_qt_choisir(parent):
    b = boites.demander_oui_non(parent, "T", "M", lambda: None, defaut=None)
    b.show()
    assert b.defaultButton() is not b.button(QMessageBox.No) or b.defaultButton() is None
    b.button(QMessageBox.No).click()


def test_saisie_texte(parent):
    recus = []
    d = boites.saisir_texte(parent, "T", "Libellé", "initial", recus.append)
    assert d.isVisible() and d.isModal() and d.textValue() == "initial" and recus == []
    d.setTextValue("nouveau")
    d.accept()
    assert recus == ["nouveau"]


def test_saisie_multiligne_annulee(parent):
    recus = []
    d = boites.saisir_texte(parent, "T", "L", "a\nb", recus.append, multiligne=True)
    assert d.textValue() == "a\nb"
    d.reject()
    assert recus == []


def test_choix_element(parent):
    recus = []
    d = boites.choisir_element(parent, "T", "L", ["un", "deux", "trois"], recus.append,
                               courant=1, modifiable=False)
    assert d.textValue() == "deux" and not d.isComboBoxEditable()
    d.setTextValue("trois")
    d.accept()
    assert recus == ["trois"]


def test_fichier_a_enregistrer(parent):
    recus = []
    dossier = tempfile.mkdtemp()
    d = boites.choisir_fichier_a_enregistrer(parent, "T", os.path.join(dossier, "x.csv"),
                                             "CSV (*.csv)", recus.append)
    assert d.isModal() and recus == []
    d.selectFile(os.path.join(dossier, "export.csv"))
    d.accept()
    assert recus and recus[0].endswith("export.csv")


def test_fichier_a_ouvrir_annule(parent):
    recus = []
    d = boites.choisir_fichier_a_ouvrir(parent, "T", "", "Tous (*)", recus.append)
    d.reject()
    assert recus == []


def test_dossier(parent):
    recus = []
    dossier = tempfile.mkdtemp()
    d = boites.choisir_dossier(parent, "T", dossier, recus.append)
    assert d.testOption(d.ShowDirsOnly)
    d.selectFile(dossier)
    d.accept()
    assert recus and os.path.realpath(recus[0]) == os.path.realpath(dossier)


@pytest.mark.parametrize('natif', [True, False])
def test_dossier_natif_ou_dessine_par_qt(parent, natif):
    d = boites.choisir_dossier(parent, "T", tempfile.mkdtemp(), lambda _c: None, natif=natif)
    assert d.testOption(d.DontUseNativeDialog) is (not natif)
    assert d.testOption(d.ShowDirsOnly) and d.isModal()
    d.reject()


def test_selecteur_dessine_par_qt_en_francais(parent):
    from PyQt5.QtWidgets import QFileDialog
    d = boites.choisir_dossier(parent, "T", tempfile.mkdtemp(), lambda _c: None, natif=False)
    assert d.labelText(QFileDialog.Accept) == "Choisir"
    assert d.labelText(QFileDialog.Reject) == "Annuler"
    d.reject()
    d = boites.choisir_fichier_a_ouvrir(parent, "T", "", "Tous (*)", lambda _c: None, natif=False)
    assert d.labelText(QFileDialog.Accept) == "Ouvrir"
    d.reject()
