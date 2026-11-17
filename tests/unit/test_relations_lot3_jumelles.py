"""
Gestionnaire de pièces, avant livraison : « Retirer du groupe » en multi-sélection,
filtre « Jumelle à renseigner », glisser une réf. d'une carte à l'autre et
raccourcis clavier (⌘1 / ⌘2 / ⌘3, ⌘F, Échap).
"""

import os
import tempfile

import pytest
from PyQt5.QtCore import QMimeData, QPoint, Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QKeySequence
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication, QShortcut

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.ui.piece_picker_dialog import RefTagList

WP, WP2, WP3, IND, IND2 = '481246688999', '481010595162', '481010000001', 'C00316028', 'C00111222'
LE = '2026-11-17T12:00:00'


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        for ref in ('NEW1', 'ANC1', 'EQ1', 'EQ2', 'EQ3', 'SEULE', WP, WP2, WP3, IND, IND2):
            manager.create_piece_standalone(ref, 'Pièce')
        manager.conn.execute("INSERT INTO pieces (ref_piece, is_phantom) VALUES ('481099999999', 1)")
        manager.conn.commit()
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _vider_boucle(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)
    qapp.processEvents()


@pytest.fixture
def fenetre(qapp, db, monkeypatch):
    import src.ui.pieces_manager as pm
    questions = []
    monkeypatch.setattr(pm, 'demander_oui_non',
                        lambda parent, titre, message, sur_oui, *a, **k:
                        questions.append((message, sur_oui)))
    fen = pm.PiecesManagerWindow(None, db)
    fen._notify_history = lambda *a: None
    fen._load_pieces_data = lambda *a, **k: None
    fen.all_statuses = {}

    def choisir(*refs):
        fen._get_selected_refs = lambda: sorted(refs)
        fen._current_ref_piece = refs[0]
        fen._refresh_succession_panel(refs[0])
        fen._refresh_equivalence_panel(refs[0])

    fen.choisir, fen.questions = choisir, questions
    yield fen
    fen.close()
    _vider_boucle(qapp)


# ── Retirer du groupe ────────────────────────────────────────────────────────

def test_retirer_du_groupe_toutes_les_pieces_selectionnees(fenetre, db):
    """Il ne retirait que la pièce affichée, alors que le bouton n'apparaît qu'en
    multi-sélection."""
    db.add_equivalence('EQ1', 'EQ2')
    db.add_equivalence('EQ1', 'EQ3')
    fenetre.choisir('EQ1', 'EQ2', 'SEULE')
    assert not fenetre.btn_unlink_equiv.isHidden()
    fenetre._on_unlink_equiv()
    (message, sur_oui), = fenetre.questions
    assert 'ces 2 pièces' in message and 'EQ1, EQ2' in message
    assert '1 pièce sélectionnée sans équivalence ne change pas' in message
    sur_oui()
    assert db.get_equivalents('EQ1') == [] and db.get_equivalents('EQ2') == []
    assert db.get_equivalents('EQ3') == []          # groupe dissous (un seul membre)


# ── Filtre « Jumelle à renseigner » ──────────────────────────────────────────

def test_filtre_jumelle_a_renseigner(fenetre, db):
    db.lier_reference_associee(WP, IND, LE)
    db.definir_references_associees([(WP2, None)], LE)
    fenetre._load_pieces_data_full()
    fenetre._active_filter = 'twin_missing'
    refs = sorted(r[0] for r in fenetre._get_filtered_data())
    # Ni la paire WP ⇄ IND, ni WP2 (« aucune »), ni le fantôme, ni les autres marques
    assert refs == sorted([WP3, IND2])
    assert 'twin_missing' in fenetre._filter_btns


# ── Glisser une réf. d'une carte à l'autre ───────────────────────────────────

def _mime(texte):
    mime = QMimeData()
    mime.setText(texte)
    return mime


def _deposer(carte, texte):
    mime = _mime(texte)
    entree = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(carte, entree)
    accepte = entree.isAccepted()
    if accepte:
        QApplication.sendEvent(carte, QDropEvent(QPoint(5, 5), Qt.CopyAction, mime,
                                                 Qt.LeftButton, Qt.NoModifier))
    return accepte


def test_deposer_une_ref_sur_une_carte(fenetre, db, qapp):
    db.add_supersession('ANC1', 'NEW1')
    fenetre.choisir('NEW1')
    assert _deposer(fenetre.equiv_section, 'ANC1')
    _vider_boucle(qapp)
    assert 'ANC1' in db.get_equivalents('NEW1')
    assert db.get_piece_status('ANC1')['ref_new'] == 'NEW1'      # copie : le lien reste
    assert fenetre.saisie_equiv.etat.text().startswith('✓ 1 ajoutée')
    # Remplace désactivée en multi-sélection : la carte refuse le dépôt
    fenetre.choisir('NEW1', 'EQ1')
    assert not _deposer(fenetre.replaces_section, 'ANC1')


def test_puce_glissable_clic_au_relachement(qapp):
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QLabel
    liste = RefTagList()
    liste.rendre_glissable()
    liste.set_refs(['ANC1'])
    clics = []
    liste.ref_clicked.connect(clics.append)
    lbl = next(l for l in liste.findChildren(QLabel) if l.text() == 'ANC1')
    appui = QMouseEvent(QEvent.MouseButtonPress, QPoint(2, 2), Qt.LeftButton, Qt.LeftButton,
                        Qt.NoModifier)
    lbl.mousePressEvent(appui)
    assert clics == []                         # rien à l'appui : peut-être un glisser
    lbl.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPoint(2, 2), Qt.LeftButton,
                                      Qt.NoButton, Qt.NoModifier))
    assert clics == ['ANC1']
    # Sans l'option : clic à l'appui, comme avant
    autre = RefTagList()
    autre.set_refs(['EQ1'])
    autre.ref_clicked.connect(clics.append)
    next(l for l in autre.findChildren(QLabel) if l.text() == 'EQ1').mousePressEvent(appui)
    assert clics == ['ANC1', 'EQ1']


# ── Raccourcis ───────────────────────────────────────────────────────────────

def test_raccourcis_et_echap(fenetre, qapp):
    touches = {s.key().toString() for s in fenetre.findChildren(QShortcut)}
    assert {'Ctrl+1', 'Ctrl+2', 'Ctrl+3', QKeySequence(QKeySequence.Find).toString()} <= touches
    fenetre.choisir('NEW1')
    assert fenetre.saisie_remplace.prendre_le_curseur()
    assert 'Raccourci' in fenetre.saisie_remplace.champ.toolTip()
    fenetre.saisie_remplace.champ.setText('ANC')
    echap = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    QApplication.sendEvent(fenetre.saisie_remplace.champ, echap)
    assert fenetre.saisie_remplace.texte_en_cours() == ''
    fenetre.choisir('NEW1', 'EQ1')
    assert not fenetre.saisie_remplace.prendre_le_curseur()     # désactivée : rien


# ── Ouverture avec le style global de l'application ──────────────────────────

def test_ouverture_avec_le_style_global(qapp, db):
    """Plantage du 2026-11-17 : avec la feuille de style globale (posée par la
    fenêtre principale), les cartes reçoivent des événements dès que le filtre de
    glisser-déposer est installé, avant que `_floating_actions` existe ;
    l'exception dans eventFilter faisait avorter PyQt à l'ouverture."""
    import src.ui.pieces_manager as pm
    from src.ui.style_manager import StyleManager
    ancien = qapp.styleSheet()
    qapp.setStyleSheet(StyleManager.get_modern_style())
    try:
        fen = pm.PiecesManagerWindow(None, db)
        fen.show()
        _vider_boucle(qapp)
        assert fen.isVisible()
        fen.close()
        _vider_boucle(qapp)
    finally:
        qapp.setStyleSheet(ancien)
