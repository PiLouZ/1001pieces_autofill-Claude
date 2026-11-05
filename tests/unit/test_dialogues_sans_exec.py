"""
Dialogues convertis de exec_() à show() + callbacks (ouvrir_modal)

Pour chaque dialogue : la méthode rend la main AVANT la décision de
l'utilisateur (plus de boucle d'événements imbriquée), le dialogue est modal, et
l'effet attendu se produit à l'acceptation — rien à l'annulation.
"""

import os
import tempfile
import types

import pytest
from PyQt5.QtWidgets import QApplication, QDialog

from src.core.config import Config
from src.data.database_manager import DatabaseManager


def _vider_boucle(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)
    qapp.processEvents()


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        conn.executemany("INSERT INTO pieces (id, ref_piece) VALUES (?, ?)",
                         [(1, 'ANC1'), (2, 'NEW1'), (3, 'EQ1'), (4, 'EQ2')])
        conn.commit()
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


@pytest.fixture
def capture(monkeypatch):
    """Intercepte ouvrir_modal tout en l'exécutant : donne accès au dialogue ouvert."""
    import src.utils.ouverture_modale as om
    ouverts = []
    vrai = om.ouvrir_modal

    def espion(dialogue, *a, **k):
        ouverts.append(dialogue)
        return vrai(dialogue, *a, **k)

    return ouverts, espion


# ─── Gestionnaire de pièces : trois sélecteurs PiecePickerDialog ─────────────

@pytest.fixture
def fenetre_pieces(qapp, db, capture, monkeypatch):
    import src.ui.pieces_manager as pm
    ouverts, espion = capture
    monkeypatch.setattr(pm, 'ouvrir_modal', espion)
    fen = pm.PiecesManagerWindow(None, db)
    fen._notify_history = lambda *a: None
    yield fen, ouverts
    fen.close()
    _vider_boucle(qapp)


def _choisir(dlg, refs):
    dlg.selected_ref = lambda: refs[0]
    dlg.selected_refs = lambda: list(refs)


def test_remplacee_par_rend_la_main_puis_applique(fenetre_pieces, db, qapp):
    fen, ouverts = fenetre_pieces
    fen._get_selected_refs = lambda: ['ANC1']
    fen._on_mark_superseded()
    dlg, = ouverts
    assert dlg.isVisible() and dlg.isModal()
    assert db.get_supersession_chain('ANC1') in ([], ['ANC1'])   # rien encore
    _choisir(dlg, ['NEW1'])
    dlg.accept()
    assert 'NEW1' in db.get_supersession_chain('ANC1')


def test_remplace_rend_la_main_puis_applique(fenetre_pieces, db, qapp):
    fen, ouverts = fenetre_pieces
    fen._get_selected_refs = lambda: ['NEW1']
    fen._on_mark_replaces()
    dlg, = ouverts
    assert dlg.isVisible() and dlg.isModal()
    _choisir(dlg, ['ANC1'])
    dlg.accept()
    assert 'NEW1' in db.get_supersession_chain('ANC1')


def test_equivalence_rend_la_main_puis_applique(fenetre_pieces, db, qapp):
    fen, ouverts = fenetre_pieces
    fen._current_ref_piece = 'EQ1'
    fen._on_link_equiv()
    dlg, = ouverts
    assert dlg.isVisible() and dlg.isModal()
    assert 'EQ2' not in str(db.get_equivalents('EQ1'))
    _choisir(dlg, ['EQ2'])
    dlg.accept()
    assert 'EQ2' in str(db.get_equivalents('EQ1'))


def test_annuler_ne_change_rien(fenetre_pieces, db, qapp):
    fen, ouverts = fenetre_pieces
    fen._get_selected_refs = lambda: ['ANC1']
    fen._on_mark_superseded()
    dlg, = ouverts
    _choisir(dlg, ['NEW1'])
    dlg.reject()
    assert 'NEW1' not in db.get_supersession_chain('ANC1')


# ─── Configuration du nettoyage du collage (barre d'outils) ─────────────────

def test_config_collage_rend_la_main_puis_applique(qapp, monkeypatch):
    import src.utils.ouverture_modale as om
    from src.ui.toolbar_service import ToolbarService
    from PyQt5.QtWidgets import QMainWindow
    ouverts = []
    vrai = om.ouvrir_modal
    monkeypatch.setattr(om, 'ouvrir_modal', lambda d, **k: (ouverts.append(d), vrai(d, **k))[1])

    appliques = []
    fen = QMainWindow()
    fen.paste_cleanup_service = types.SimpleNamespace(
        _ask_confirmation=True, _remember_choice=False, _default_replacement='||',
        clear_memory=lambda: None,
        configure_defaults=lambda *a: appliques.append(a))
    service = ToolbarService.__new__(ToolbarService)
    service.main_window = fen

    service._configure_paste_cleanup()
    dlg, = ouverts
    assert dlg.isVisible() and dlg.isModal() and appliques == []
    dlg.accept()
    assert len(appliques) == 1
    _vider_boucle(qapp)


# ─── Fenêtres de la fenêtre principale (résultat non utilisé) ────────────────
# Une vraie MainWindow, dans un sous-processus : ses minuteries survivent à sa
# fermeture et feraient planter les tests suivants du même processus.

_SCRIPT_FENETRE_PRINCIPALE = r"""
import json, os, sys, tempfile
sys.path.insert(0, os.getcwd())
from src.core.config import Config
Config.DB_FILE = tempfile.mktemp(suffix='.db')
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
app = QApplication(sys.argv)
from src.ui.main_refactored import MainWindow
fen = MainWindow()

def dialogues():
    return {d for d in fen.findChildren(QDialog) if d.isVisible()}

res = {}
for methode in sys.argv[1:]:
    avant = dialogues()
    getattr(fen, methode)()                     # doit rendre la main (pas d'exec_)
    nouveaux = dialogues() - avant
    modal = [d.isModal() for d in nouveaux]
    for d in nouveaux:
        d.reject()
    for _ in range(3):
        app.processEvents()
    QApplication.sendPostedEvents(None, 0)
    res[methode] = {'ouverts': len(nouveaux), 'modal': modal, 'restants': len(dialogues() - avant)}
print('RESULTAT ' + json.dumps(res), flush=True)
os._exit(0)
"""

METHODES = ['_safe_show_local_guide', '_safe_open_restore_backup_dialog',
            '_safe_open_fts5_manager', '_safe_configure_columns']


def test_fenetres_principales_modales_sans_exec():
    import json
    import subprocess
    import sys
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    sortie = subprocess.run([sys.executable, '-c', _SCRIPT_FENETRE_PRINCIPALE, *METHODES],
                            capture_output=True, text=True, timeout=120, env=env,
                            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    ligne = [l for l in sortie.stdout.splitlines() if l.startswith('RESULTAT ')]
    assert ligne, sortie.stderr[-2000:]
    res = json.loads(ligne[0][len('RESULTAT '):])
    for methode in METHODES:
        assert res[methode] == {'ouverts': 1, 'modal': [True], 'restants': 0}, methode
