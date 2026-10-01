"""MessageStatusBar : les messages temporaires ne masquent plus les widgets de
tête (« ▲ Lignes à traiter ▼ », sous le tableau) — avec QStatusBar standard, ils
disparaissaient pendant chaque « N lignes chargées »."""

from src.ui.message_status_bar import MessageStatusBar
from src.ui.qt_imports import QLabel, QStatusBar, QWidget


def _barre(qapp):
    bar = MessageStatusBar()
    tete = QLabel("tête")
    bar.add_leading_widget(tete)
    bar.show()
    qapp.processEvents()
    return bar, tete


def test_widget_de_tete_reste_visible_pendant_un_message(qapp):
    bar, tete = _barre(qapp)
    bar.showMessage("269 lignes chargées", 2000)
    qapp.processEvents()
    assert tete.isVisible()
    assert bar.currentMessage() == "269 lignes chargées"


def test_contre_epreuve_qstatusbar_standard_masque_la_tete(qapp):
    """Le défaut que la classe corrige : sans elle, la tête disparaît."""
    bar = QStatusBar()
    tete = QLabel("tête")
    bar.addWidget(tete)
    bar.show()
    bar.showMessage("269 lignes chargées", 2000)
    qapp.processEvents()
    assert not tete.isVisible()


def test_message_apres_la_tete(qapp):
    bar, tete = _barre(qapp)
    bar.resize(600, 30)
    bar.showMessage("message")
    qapp.processEvents()
    assert bar._message_label.x() > tete.x()


def test_expiration_et_effacement(qapp):
    from PyQt5.QtTest import QTest
    bar, _ = _barre(qapp)
    recus = []
    bar.messageChanged.connect(recus.append)
    bar.showMessage("bref", 50)
    QTest.qWait(120)
    assert bar.currentMessage() == ""
    bar.showMessage("persistant")
    QTest.qWait(80)
    assert bar.currentMessage() == "persistant"
    bar.clearMessage()
    assert bar.currentMessage() == ""
    assert recus == ["bref", "", "persistant", ""]


def test_nouveau_message_annule_l_expiration_du_precedent(qapp):
    from PyQt5.QtTest import QTest
    bar, _ = _barre(qapp)
    bar.showMessage("premier", 50)
    bar.showMessage("second")  # sans délai : ne doit pas être effacé par le 1er
    QTest.qWait(120)
    assert bar.currentMessage() == "second"
