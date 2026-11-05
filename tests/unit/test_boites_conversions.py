"""
Boîtes statiques bloquantes (QMessageBox.question, QFileDialog.get…,
QInputDialog.get…) converties en équivalents non bloquants (src/utils/boites.py) :
les cas qui ont demandé une adaptation à la main.
"""

import types
from unittest.mock import patch

import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QWidget


def _vider(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)


# ─── SEO : choix de la référence par réappel de l'action ─────────────────────

def _seo(multi):
    from src.ui.seo_service import SEOService
    seo = SEOService.__new__(SEOService)
    seo.main_window = QWidget()
    seo.raison_refus = None
    seo._refus_silencieux = False
    seo._get_multi_reference_terms = lambda: list(multi)
    seo._get_current_search_data_for_reference = lambda ref: {'choisie': ref}
    seo._get_current_search_data = lambda: {'choisie': None}
    seo._signaler_absence_de_donnees = lambda genre: None
    return seo


def test_seo_plusieurs_references_relance_avec_le_choix(qapp, monkeypatch):
    import src.ui.seo_service as module
    seo = _seo(["A1", "B2"])
    demandes, vus = [], []
    monkeypatch.setattr(module, 'choisir_element',
                        lambda p, t, m, elements, sur_element, courant=0, modifiable=True:
                        demandes.append((elements, sur_element, modifiable)))
    # La suite de la préparation n'est pas l'objet du test : on la court-circuite
    seo._get_current_search_data_for_reference = lambda ref: None

    def action():
        vus.append(seo._reference_choisie)
        return seo.preparer_donnees_fiche("title", "Réf.", relancer=action)

    assert action() is None                  # 1er passage : boîte ouverte, action stoppée
    (elements, sur_element, modifiable), = demandes
    assert elements == ["A1", "B2"] and modifiable is False
    sur_element("B2")                        # l'utilisateur choisit → relance
    assert vus == [None, "B2"]
    assert seo._reference_choisie is None    # choix consommé, pas de fuite


def test_seo_choix_vide_ne_relance_pas(qapp, monkeypatch):
    import src.ui.seo_service as module
    seo = _seo(["A1", "B2"])
    demandes, relances = [], []
    monkeypatch.setattr(module, 'choisir_element',
                        lambda p, t, m, e, sur_element, **k: demandes.append(sur_element))
    seo.preparer_donnees_fiche("title", "Réf.", relancer=lambda: relances.append(1))
    demandes[0]("")
    assert relances == []


def test_seo_non_interactif_sans_boite(qapp, monkeypatch):
    import src.ui.seo_service as module
    seo = _seo(["A1", "B2"])
    monkeypatch.setattr(module, 'choisir_element', lambda *a, **k: pytest.fail("boîte ouverte"))
    assert seo.preparer_donnees_fiche("title", "Réf.", interactif=False) is None
    assert "Plusieurs références" in seo.raison_refus


# ─── Catégories ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('valider', [True, False])
def test_categories(qapp, valider):
    import src.utils.ouverture_modale as om
    from src.services.unified_dialog_service import SimpleDialogs
    parent, recus = QWidget(), []
    avant = set(om._ouverts)
    SimpleDialogs.get_categories(parent, ["Four", "Hotte"], recus.append)
    dlg, = set(om._ouverts) - avant
    assert dlg.isModal() and dlg.textValue() == "Four\nHotte" and recus == []
    dlg.setTextValue("Four\n\n  Lave-linge  \n")
    dlg.accept() if valider else dlg.reject()
    assert recus == ([["Four", "Lave-linge"]] if valider else [])
    _vider(qapp)


# ─── Configuration des exports : dossier inutilisable ────────────────────────

def _dialogue_config(dossier):
    from src.ui.export_config_dialog import ExportConfigDialog
    d = ExportConfigDialog.__new__(ExportConfigDialog)
    QDialog.__init__(d)
    d._output_dir = dossier
    return d


def test_dossier_utilisable_enregistre_tout_de_suite(qapp, tmp_path, monkeypatch):
    import src.ui.export_config_dialog as module
    monkeypatch.setattr(module, 'demander_oui_non', lambda *a, **k: pytest.fail("question posée"))
    ok = []
    _dialogue_config(str(tmp_path))._confirmer_dossier_export(lambda: ok.append(1))
    _dialogue_config("")._confirmer_dossier_export(lambda: ok.append(2))
    assert ok == [1, 2]


def test_dossier_inutilisable_demande_puis_enregistre(qapp, monkeypatch):
    import src.ui.export_config_dialog as module
    questions, ok = [], []
    monkeypatch.setattr(module, 'demander_oui_non',
                        lambda p, t, m, sur_oui, defaut=None: questions.append((t, sur_oui)))
    _dialogue_config("/chemin/inexistant/zzz")._confirmer_dossier_export(lambda: ok.append(1))
    (titre, sur_oui), = questions
    assert titre == "Dossier d'export" and ok == []
    sur_oui()
    assert ok == [1]


# ─── Rappels décorés : la fenêtre d'erreur garde son parent ──────────────────

def test_erreur_dans_un_rappel_garde_le_widget_pour_parent(qapp, monkeypatch):
    # delete_piece est décoré @handle_ui_errors(show_message=True) ; son rappel
    # aussi, et reçoit self en 1er argument pour que la fenêtre d'erreur soit
    # parentée au service comme avant (et non orpheline).
    from src.ui.piece_management_service import PieceManagementService
    import src.ui.message_helper as mh
    parents = []
    monkeypatch.setattr(mh.MessageHelper, 'show_error', staticmethod(lambda p, *a: parents.append(p)))
    rappels = []

    class _Service(PieceManagementService, QWidget):
        pass

    service = _Service.__new__(_Service)
    QWidget.__init__(service)

    def explose():
        raise RuntimeError("boum")

    service.main_window = types.SimpleNamespace(
        user_interaction_service=types.SimpleNamespace(
            demander_confirmation=lambda t, m, sur_oui, default_yes=False: rappels.append(sur_oui)),
        table=types.SimpleNamespace(currentRow=explose))
    service.delete_piece(types.SimpleNamespace(data=lambda role: 'AS001'))
    rappels[0]()
    assert parents == [service]
