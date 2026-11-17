"""
Saisie des relations dans le gestionnaire de pièces : les cartouches de l'import.

- Lot 1, saisie directe dans les cartes (≡ Équivalences, ↑ Remplace, ↳ Remplacée
  par) : Espace / Entrée / collage écrit aussitôt, ligne d'état (ajoutées,
  fantômes créés, erreurs en rouge) ; quitter le champ n'écrit rien ;
  « Remplace » réservée à une seule pièce (bug d'avant : à plusieurs pièces,
  chaque réf. finissait remplacée par la dernière) ; « Remplacée par » demande
  confirmation avant de changer une remplaçante ; complétion sur toutes les réfs.
- Lot 2, fenêtre de sélection avec panier : la recherche ne vide pas le panier,
  double-clic / Entrée ajoutent, panier à une réf. remplacé, réfs inconnues
  signalées, refus affiché sans fermer, filtre des groupes pour la réf. associée.
"""

import os
import tempfile

import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QFocusEvent
from PyQt5.QtWidgets import QApplication

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.ui.piece_picker_dialog import PiecePickerDialog

WP, WP2, IND = '481246688999', '481010595162', 'C00316028'


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        for ref, libelle in (('NEW1', 'Pompe'), ('ANC1', ''), ('ANC2', ''), ('EQ1', 'Joint'),
                             ('EQ2', 'Joint porte'), ('AUTRE', 'Pompe'),
                             (WP, 'Courroie'), (WP2, 'Courroie'), (IND, 'Courroie')):
            manager.create_piece_standalone(ref, libelle)
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
    ouverts, questions, avertis = [], [], []
    monkeypatch.setattr(pm, 'ouvrir_modal',
                        lambda dlg, sur_accepte=None, **k: ouverts.append((dlg, sur_accepte)))
    monkeypatch.setattr(pm, 'demander_oui_non',
                        lambda parent, titre, message, sur_oui, *a, **k:
                        questions.append((message, sur_oui)))
    monkeypatch.setattr(pm.QMessageBox, 'warning',
                        lambda parent, titre, message, *a: avertis.append(message))
    fen = pm.PiecesManagerWindow(None, db)
    fen._notify_history = lambda *a: None
    fen._load_pieces_data = lambda *a, **k: None
    fen.all_statuses = {}

    def choisir(*refs):
        fen._get_selected_refs = lambda: sorted(refs)
        fen._current_ref_piece = refs[0]
        fen._refresh_succession_panel(refs[0])
        fen._refresh_equivalence_panel(refs[0])

    fen.choisir = choisir
    fen.ouverts, fen.questions, fen.avertis = ouverts, questions, avertis
    yield fen
    fen.close()
    _vider_boucle(qapp)


def _taper(saisie, texte):
    saisie.champ.setText(texte)
    saisie.champ.valider_saisie()


# ── Lot 1 : saisie directe ───────────────────────────────────────────────────

class TestSaisieDirecte:

    def test_remplace_ecrit_aussitot_et_fait_le_bilan(self, fenetre, db):
        fenetre.choisir('NEW1')
        _taper(fenetre.saisie_remplace, 'ANC1 X91')
        assert db.get_piece_status('ANC1')['ref_new'] == 'NEW1'
        assert db.get_piece_status('X91')['ref_new'] == 'NEW1'      # créée en fantôme
        bilan = fenetre.saisie_remplace.etat.text()
        assert bilan.startswith('✓ 2 ajoutées') and 'X91 créée (fantôme)' in bilan
        assert fenetre.saisie_remplace.texte_en_cours() == ''
        assert 'X91' in fenetre._modele_completion().stringList()   # complétion rechargée
        # Le rafraîchissement qui suit le rechargement garde le bilan…
        fenetre.choisir('NEW1')
        assert fenetre.saisie_remplace.etat.text() == bilan
        # … changer de pièce l'efface
        fenetre.choisir('AUTRE')
        assert fenetre.saisie_remplace.etat.isHidden()

    def test_equivalences_et_remplacee_par(self, fenetre, db):
        fenetre.choisir('EQ1')
        _taper(fenetre.saisie_equiv, 'EQ2')
        assert 'EQ2' in db.get_equivalents('EQ1')
        assert 'EQ2' in fenetre.equiv_tag_list._refs
        fenetre.choisir('ANC1')
        _taper(fenetre.saisie_remplacee_par, 'NEW1')
        assert db.get_piece_status('ANC1')['ref_new'] == 'NEW1'

    def test_erreur_en_rouge_sans_boite(self, fenetre, db):
        fenetre.choisir('ANC1')
        _taper(fenetre.saisie_remplacee_par, 'NEW1 AUTRE')
        assert "une seule réf" in fenetre.saisie_remplacee_par.etat.text()
        assert fenetre.avertis == []
        assert not db.get_piece_status('ANC1').get('ref_new')

    def test_changer_de_remplacante_demande_confirmation(self, fenetre, db):
        db.add_supersession('ANC1', 'NEW1')
        fenetre.choisir('ANC1')
        _taper(fenetre.saisie_remplacee_par, 'AUTRE')
        (message, sur_oui), = fenetre.questions
        assert 'ANC1 : NEW1 → AUTRE' in message
        assert db.get_piece_status('ANC1')['ref_new'] == 'NEW1'      # rien avant le oui
        sur_oui()
        assert db.get_piece_status('ANC1')['ref_new'] == 'AUTRE'

    def test_quitter_le_champ_n_ecrit_rien(self, fenetre, db, qapp):
        fenetre.choisir('NEW1')
        fenetre.saisie_remplace.champ.setText('ANC1')
        QApplication.sendEvent(fenetre.saisie_remplace.champ, QFocusEvent(QEvent.FocusOut))
        assert not db.get_piece_status('ANC1').get('ref_new')
        assert fenetre.saisie_remplace.texte_en_cours() == 'ANC1'

    def test_plusieurs_pieces_remplace_desactivee(self, fenetre, db):
        """Bug d'avant : ANC1 finissait remplacée par la dernière pièce, sans message."""
        fenetre.choisir('NEW1', 'AUTRE')
        assert not fenetre.saisie_remplace.champ.isEnabled()
        assert not fenetre.btn_mark_replaces.isEnabled()
        lignes, erreurs, _ = fenetre._ecrire_relation(fenetre.REMPLACE, ['ANC1'])
        assert lignes == [] and "sélectionnez une seule pièce" in erreurs[0]
        # « Remplacée par » vaut pour toutes les pièces sélectionnées
        assert fenetre.saisie_remplacee_par.champ.isEnabled()
        _taper(fenetre.saisie_remplacee_par, 'EQ1')
        assert db.get_piece_status('NEW1')['ref_new'] == 'EQ1'
        assert db.get_piece_status('AUTRE')['ref_new'] == 'EQ1'

    def test_sans_selection_tout_est_desactive(self, fenetre):
        fenetre._get_selected_refs = lambda: []
        fenetre._current_ref_piece = None
        fenetre._refresh_equivalence_panel(None)
        assert not any(s.champ.isEnabled() for s in fenetre._saisies_relation.values())


def test_completion_sans_limite_a_5000(db):
    db.conn.executemany("INSERT INTO pieces (ref_piece) VALUES (?)",
                        [(f"Z{i:05d}",) for i in range(5100)])
    db.conn.commit()
    refs = db.lister_toutes_refs_pieces()
    assert len(refs) > 5100 and 'Z05099' in refs


# ── Lot 2 : fenêtre avec panier ──────────────────────────────────────────────

def _ligne(dlg, ref):
    proxy = dlg._proxy
    for r in range(proxy.rowCount()):
        if proxy.index(r, 0).data() == ref:
            return proxy.index(r, 0)
    return None


class TestFenetrePanier:

    def test_la_recherche_ne_vide_pas_le_panier(self, qapp, db):
        dlg = PiecePickerDialog(db, None, exclude_ref='NEW1', multi_select=True)
        dlg._recherche.setText('anc1')
        dlg._filtrer()
        assert dlg._proxy.rowCount() == 1
        dlg._ajouter_ligne(_ligne(dlg, 'ANC1'))
        dlg._recherche.setText('joint porte')              # recherche par libellé, espaces
        dlg._filtrer()
        assert [dlg._proxy.index(r, 0).data() for r in range(dlg._proxy.rowCount())] == ['EQ2']
        dlg._entree_recherche()                            # une seule ligne : Entrée l'ajoute
        assert dlg.selected_refs() == ['ANC1', 'EQ2']
        assert dlg._ok_btn.text() == 'Ajouter 2 références'
        dlg._recherche.clear()
        dlg._filtrer()
        assert _ligne(dlg, 'ANC1').siblingAtColumn(2).data() == 'Ajoutée'
        assert _ligne(dlg, 'NEW1') is None                 # la pièce elle-même exclue
        dlg.close()

    def test_coller_plusieurs_et_inconnues_signalees(self, qapp, db):
        dlg = PiecePickerDialog(db, None, multi_select=True)
        assert not dlg._ok_btn.isEnabled()
        dlg._panier.line_edit.setText('ANC1 X91 X92')      # collage : découpé à l'espace
        assert dlg.selected_refs() == ['ANC1', 'X91', 'X92']
        assert '2 inconnues' in dlg._etat.text() and 'X91, X92' in dlg._etat.text()
        dlg.close()

    def test_panier_a_une_ref_remplace(self, qapp, db):
        dlg = PiecePickerDialog(db, None)
        dlg._ajouter_ligne(_ligne(dlg, 'ANC1'))
        dlg._ajouter_ligne(_ligne(dlg, 'NEW1'))
        assert dlg.selected_refs() == ['NEW1'] and dlg._ok_btn.text() == 'Choisir'
        dlg.close()

    def test_refus_affiche_sans_fermer(self, qapp, db):
        dlg = PiecePickerDialog(db, None, valider=lambda refs: "Refusée." if refs == ['ANC1']
                                else '')
        dlg.show()
        dlg._panier.set_refs(['ANC1'])
        dlg.accept()
        assert dlg.isVisible() and dlg._erreur.text() == 'Refusée.'
        dlg._panier.set_refs(['NEW1'])
        dlg.accept()
        assert not dlg.isVisible() and dlg.result() == dlg.Accepted
        _vider_boucle(qapp)

    def test_reference_associee_filtre_les_groupes(self, fenetre, db):
        fenetre.choisir(WP)
        fenetre._on_ajouter_associee()
        (dlg, sur_accepte), = fenetre.ouverts
        assert _ligne(dlg, IND) is not None
        assert _ligne(dlg, WP2) is None and _ligne(dlg, 'ANC1') is None
        dlg._panier.set_refs([IND])
        dlg.show()
        dlg.accept()
        sur_accepte()
        assert db.reference_associee(WP) == (True, IND)

    def test_plus_d_une_carte_ouvre_la_fenetre_avec_le_texte_tape(self, fenetre, db):
        fenetre.choisir('NEW1')
        fenetre.saisie_remplace.champ.setText('anc')
        fenetre._on_mark_replaces()
        (dlg, sur_accepte), = fenetre.ouverts
        assert dlg.windowTitle() == 'Ajouter des réf. remplacées par NEW1'
        assert dlg._recherche.text() == 'anc' and dlg._proxy.rowCount() == 2
        dlg._panier.set_refs(['ANC1', 'ANC2'])
        sur_accepte()
        assert db.get_piece_status('ANC2')['ref_new'] == 'NEW1'
        assert fenetre.saisie_remplace.texte_en_cours() == ''
