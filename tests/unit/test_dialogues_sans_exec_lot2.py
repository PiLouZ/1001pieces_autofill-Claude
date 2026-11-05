"""
Dialogues dont le résultat remontait à l'appelant, convertis de exec_() à
show() + rappel (ouvrir_modal) : confirmations, valeurs de cellule (Cmd+D),
nettoyage du collage, nettoyage des doublons, erreur détaillée.

Pour chacun : l'appel rend la main AVANT la réponse, le dialogue est modal, et
le rappel reçoit la réponse — rien (ou la valeur neutre) à l'annulation.
"""

import os
import tempfile
import types

import pytest
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from src.core.config import Config


def _vider_boucle(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)
    qapp.processEvents()


@pytest.fixture
def espion_modal(monkeypatch):
    """Remplace ouvrir_modal dans un module par un espion qui l'exécute réellement."""
    import src.utils.ouverture_modale as om
    ouverts = []
    vrai = om.ouvrir_modal

    def poser(module):
        monkeypatch.setattr(module, 'ouvrir_modal',
                            lambda d, **k: (ouverts.append(d), vrai(d, **k))[1])
        return ouverts
    return poser


# ─── Confirmation Oui / Non ──────────────────────────────────────────────────

def _service_interaction(parent):
    from src.ui.user_interaction_service import UserInteractionService
    service = UserInteractionService.__new__(UserInteractionService)
    service.main_window = parent
    return service


@pytest.mark.parametrize('bouton,attendu', [("Oui", [1]), ("Non", [])])
def test_confirmation_rend_la_main_puis_repond(qapp, espion_modal, bouton, attendu):
    import src.ui.user_interaction_service as module
    ouverts = espion_modal(module)
    parent = QWidget()
    oui = []
    _service_interaction(parent).demander_confirmation("Titre", "Sûr ?", lambda: oui.append(1))
    boite, = ouverts
    assert boite.isVisible() and boite.isModal() and oui == []
    [b for b in boite.buttons() if b.text() == bouton][0].click()
    assert oui == attendu
    _vider_boucle(qapp)


def test_confirmation_non_par_defaut(qapp, espion_modal):
    import src.ui.user_interaction_service as module
    ouverts = espion_modal(module)
    parent = QWidget()          # référence gardée : un parent détruit détruit le dialogue
    _service_interaction(parent).demander_confirmation("T", "M", lambda: None)
    boite, = ouverts
    assert boite.defaultButton().text() == "Non"
    boite.reject()
    _vider_boucle(qapp)


def test_suppression_piece_seulement_apres_oui(qapp):
    from src.ui.piece_management_service import PieceManagementService
    rappels, supprimes = [], []
    mw = types.SimpleNamespace(
        user_interaction_service=types.SimpleNamespace(
            demander_confirmation=lambda t, m, sur_oui, default_yes=False: rappels.append(sur_oui),
            show_error=lambda *a: None, add_to_history=lambda *a: None,
            show_status_message=lambda *a: None),
        table=types.SimpleNamespace(currentRow=lambda: 0),
        table_fill_service=types.SimpleNamespace(get_db_id_from_row=lambda t, r: 42),
        db_manager=types.SimpleNamespace(delete_piece=lambda ref, db_id: supprimes.append((ref, db_id)) or True),
        pieces_panel_service=types.SimpleNamespace(update_pieces_panel=lambda: None),
        _refresh_pieces_count_column=lambda: None)
    service = PieceManagementService.__new__(PieceManagementService)
    service.main_window = mw
    item = types.SimpleNamespace(data=lambda role: 'AS001')
    service.delete_piece(item)
    assert supprimes == [] and len(rappels) == 1      # rien avant la réponse
    rappels[0]()                                       # « Oui »
    assert supprimes == [('AS001', 42)]


# ─── Valeurs de cellule (Cmd+D) ──────────────────────────────────────────────

@pytest.fixture
def db():
    from src.data.database_manager import DatabaseManager
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        conn.executemany(
            "INSERT INTO appareils (id, type, manufacturer, ref_modele, commercial_ref, "
            "other_ref, notes, category) VALUES (?, ?, ?, ?, ?, '', '', '')",
            [(1, 'Four', 'Bosch', 'A1', 'C1'), (2, 'Hotte', 'Elica', 'A2', 'C2')])
        conn.commit()
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


@pytest.mark.parametrize('accepter,attendu', [(True, ["Lave-linge"]), (False, [])])
def test_valeurs_champ_rend_la_main_puis_rappelle(qapp, db, espion_modal, accepter, attendu):
    import src.services.autocompletion_service as module
    from PyQt5.QtWidgets import QLineEdit
    ouverts = espion_modal(module)
    service = module.AutoCompletionService(db, QWidget())
    recus = []
    service.show_field_values_dialog('type', "", sur_resultat=recus.append)
    dlg, = ouverts
    assert dlg.isVisible() and dlg.isModal() and recus == []
    dlg.findChild(QLineEdit).setText("Lave-linge")
    dlg.accept() if accepter else dlg.reject()
    assert recus == attendu
    _vider_boucle(qapp)


# ─── Nettoyage du collage ────────────────────────────────────────────────────

def _service_collage():
    from src.services.paste_cleanup_service import PasteCleanupService
    return PasteCleanupService()


def test_collage_sans_extension_rappel_immediat(qapp):
    recus = []
    _service_collage().process_paste_content("AS001 || AS002", None, recus.append)
    assert recus == ["AS001 || AS002"]


def test_collage_choix_memorise_rappel_immediat(qapp):
    service = _service_collage()
    service.configure_defaults('||', ask_confirmation=False)
    recus = []
    service.process_paste_content("AS001.pdf AS002.pdf", None, recus.append)
    assert len(recus) == 1 and ".pdf" not in recus[0]


@pytest.mark.parametrize('annuler', [False, True])
def test_collage_avec_dialogue(qapp, espion_modal, annuler):
    import src.services.paste_cleanup_service as module
    ouverts = espion_modal(module)
    service = _service_collage()
    recus = []
    parent = QWidget()          # référence gardée : un parent détruit détruit le dialogue
    service.process_paste_content("AS001.pdf AS002.pdf", parent, recus.append)
    dlg, = ouverts
    assert dlg.isVisible() and dlg.isModal() and recus == []
    if annuler:
        dlg.reject()
        assert recus == ["AS001.pdf AS002.pdf"]          # texte d'origine
    else:
        dlg.set_choice('or')
        assert recus and ".pdf" not in recus[0] and "||" in recus[0]
    _vider_boucle(qapp)


# ─── Nettoyage des doublons ──────────────────────────────────────────────────

class _FenetreNettoyageFactice(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_choice = None

    def get_user_choice(self):
        return self.user_choice


def _service_nettoyage(monkeypatch, espion_modal):
    import src.ui.cleanup_preview_refactored as cpr
    import src.ui.data_management_service as module
    monkeypatch.setattr(cpr, 'CleanupPreviewDialog', _FenetreNettoyageFactice)
    ouverts = espion_modal(module)
    invalides = []
    mw = QWidget()
    mw.duplicate_indicator_service = types.SimpleNamespace(invalidate_cache=invalides.append)
    return module.DataManagementService(None, mw), ouverts, invalides


def test_nettoyage_applique(qapp, monkeypatch, espion_modal):
    service, ouverts, invalides = _service_nettoyage(monkeypatch, espion_modal)
    recus = []
    service.prepare_data_cleaning(sur_resultat=recus.append)
    dlg, = ouverts
    assert dlg.isModal() and recus == [] and invalides == []
    dlg.user_choice = 'applied'
    dlg.accept()
    assert recus == [{'dialog_completed': True, 'user_choice': 'applied'}]
    assert invalides == ["nettoyage doublons"]
    _vider_boucle(qapp)


def test_nettoyage_annule_invalide_quand_meme(qapp, monkeypatch, espion_modal):
    service, ouverts, invalides = _service_nettoyage(monkeypatch, espion_modal)
    recus = []
    service.prepare_data_cleaning(sur_resultat=recus.append)
    dlg, = ouverts
    dlg.reject()
    assert recus == [] and invalides == ["nettoyage doublons"]
    _vider_boucle(qapp)


def test_croix_de_la_fenetre_de_nettoyage_emet_finished(qapp, monkeypatch):
    # La vraie fenêtre lance une analyse en arrière-plan : on court-circuite son
    # constructeur pour ne tester que closeEvent (la croix doit valoir reject()).
    from src.ui.cleanup_preview_refactored import CleanupPreviewDialog

    def init_minimal(self, parent=None):
        QDialog.__init__(self, parent)
        self._loading_timer = None
        self.analysis_service = None
        self.user_choice = None

    monkeypatch.setattr(CleanupPreviewDialog, '__init__', init_minimal)
    dlg = CleanupPreviewDialog()
    fins = []
    dlg.finished.connect(fins.append)
    dlg.show()
    dlg.close()
    assert fins == [QDialog.Rejected] and dlg.get_user_choice() == 'cancelled'
    dlg.deleteLater()
    _vider_boucle(qapp)


# ─── Erreur détaillée ────────────────────────────────────────────────────────

def test_erreur_detaillee_modale_non_bloquante(qapp, espion_modal):
    import src.ui.message_helper as module
    ouverts = espion_modal(module)
    module.MessageHelper.show_detailed_error(None, "Message", "Trace", "Titre")
    boite, = ouverts
    assert isinstance(boite, QMessageBox) and boite.isVisible() and boite.isModal()
    assert boite.text() == "Message" and boite.detailedText() == "Trace"
    boite.accept()
    _vider_boucle(qapp)


# ─── Import PDF : l'ancien repli cassé est retiré ────────────────────────────

def test_echec_import_pdf_signale(qapp):
    from src.ui.file_processing_service import FileProcessingService
    erreurs = []

    def echoue(*a, **k):
        raise RuntimeError("boum")

    mw = types.SimpleNamespace(
        import_manager=types.SimpleNamespace(import_from_drag_drop=echoue),
        _on_import_complete=None,
        user_interaction_service=types.SimpleNamespace(show_error=erreurs.append))
    assert FileProcessingService(mw).import_pdf_files(["/tmp/x.pdf"]) is False
    assert erreurs and "boum" in erreurs[0]
