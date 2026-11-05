"""
ouvrir_modal : dialogue modal sans boucle d'événements imbriquée (show, jamais exec_).
"""

from PyQt5.QtWidgets import QApplication, QDialog, QLineEdit, QWidget

from src.ui import ouverture_modale
from src.ui.ouverture_modale import ouvrir_modal


class _Saisie(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.champ = QLineEdit(self)


def _vider_boucle(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)   # exécute les deleteLater
    qapp.processEvents()


def test_rend_la_main_et_reste_modal(qapp):
    dlg = ouvrir_modal(_Saisie())
    assert dlg.isVisible() and dlg.isModal()   # affiché, sans attendre la fermeture
    dlg.reject()
    _vider_boucle(qapp)


def test_accepte_lit_le_dialogue_puis_le_libere(qapp):
    lu, fin = [], []
    dlg = _Saisie()                       # sans parent : gardé en vie par le module
    ouvrir_modal(dlg, sur_accepte=lambda: lu.append(dlg.champ.text()),
                 sur_fin=fin.append)
    dlg.champ.setText("AS001")
    dlg.accept()
    assert lu == ["AS001"] and fin == [QDialog.Accepted]
    _vider_boucle(qapp)
    assert dlg not in ouverture_modale._ouverts


def test_annule_n_appelle_pas_sur_accepte(qapp):
    lu, fin = [], []
    dlg = ouvrir_modal(_Saisie(), sur_accepte=lambda: lu.append(1), sur_fin=fin.append)
    dlg.reject()
    assert lu == [] and fin == [QDialog.Rejected]
    _vider_boucle(qapp)


def test_dialogue_sans_parent_survit_a_l_appelant(qapp):
    lu = []

    def appelant():
        # La variable locale disparaît au retour : seul _ouverts retient le dialogue
        d = _Saisie()
        ouvrir_modal(d, sur_accepte=lambda: lu.append(d.champ.text()))
        return id(d)

    appelant()
    import gc
    gc.collect()
    ouverts = [d for d in ouverture_modale._ouverts if isinstance(d, _Saisie)]
    assert len(ouverts) == 1
    ouverts[0].champ.setText("encore là")
    ouverts[0].accept()
    assert lu == ["encore là"]
    _vider_boucle(qapp)


def test_dialogue_avec_parent(qapp):
    parent = QWidget()
    lu = []
    dlg = _Saisie(parent)
    ouvrir_modal(dlg, sur_accepte=lambda: lu.append(dlg.parent() is parent))
    dlg.accept()
    assert lu == [True]
    _vider_boucle(qapp)
