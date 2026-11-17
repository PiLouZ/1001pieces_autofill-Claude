"""
Réf. associée (jumelle Whirlpool / Indesit / Beko) gérée depuis le gestionnaire
de pièces : ligne « Réf. associée » en tête de la carte ≡ Équivalences, et
bouton « Lier comme réf. associées » pour deux pièces sélectionnées.

- base : lier (mêmes effets que l'import), refus motivés, retirer (l'équivalence
  reste, la ligne 0 part), inverser (la ligne 0 suit l'associée), refuser une
  proposée, « aucune » ; retirer une pièce de son groupe défait sa paire ;
  renommage et suppression suivent l'associée ;
- fenêtre : les quatre états, la jumelle n'est pas répétée dans les puces, le
  sélecteur (show + callback) lie la pièce choisie.
"""

import os
import tempfile

import pytest
from PyQt5.QtWidgets import QApplication

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.ui.ligne_reference_associee import AUCUNE, JUMELLE, PROPOSEE, VIDE

WP, WP2 = '481246688999', '481010595162'      # Whirlpool
IND, IND2 = 'C00316028', 'C00111222'            # Indesit
BEKO = '1734560100'                             # Beko
BSH = '11051894'                                # hors des trois groupes
LE = '2026-11-17T10:00:00'


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        for ref, libelle in ((WP, 'Courroie'), (WP2, 'Courroie'), (IND, 'Courroie'),
                             (IND2, 'Pompe'), (BEKO, 'Pompe'), (BSH, 'Joint')):
            manager.create_piece_standalone(ref, libelle)
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _ligne_fiche(db, ref):
    row = db.conn.execute("SELECT ligne_fiche FROM piece_equivalence_groups WHERE ref_piece = ?",
                          [ref]).fetchone()
    return row[0] if row else 'hors groupe'


# ── Base ─────────────────────────────────────────────────────────────────────

class TestBase:

    def test_lier_comme_l_import(self, db):
        assert db.lier_reference_associee(WP, IND, LE) == (True, "")
        assert db.reference_associee(WP) == (True, IND)
        assert db.reference_principale_de(IND) == WP
        assert IND in db.get_equivalents(WP)
        assert _ligne_fiche(db, IND) == 0

    @pytest.mark.parametrize("principale, associee, motif", [
        (WP, WP2, "Deux réf. Whirlpool ne peuvent pas être jumelles"),
        (WP, 'C00999999', "n'existe pas dans les pièces"),
        (WP, BSH, "ni Whirlpool, ni Indesit, ni Beko"),
        (WP, WP, "deux références différentes"),
    ])
    def test_refus_motives(self, db, principale, associee, motif):
        ok, message = db.lier_reference_associee(principale, associee, LE)
        assert not ok and motif in message
        assert db.get_equivalents(WP) == []

    def test_refus_si_deja_une_autre_jumelle(self, db):
        db.lier_reference_associee(WP, IND, LE)
        ok, message = db.lier_reference_associee(WP2, IND, LE)
        assert not ok and f"{IND} est déjà liée à {WP}" in message
        ok, message = db.lier_reference_associee(WP, BEKO, LE)
        assert not ok and "Retirez d'abord ce lien" in message
        # Relier la même paire : rien à faire, pas d'erreur
        assert db.lier_reference_associee(WP, IND, LE) == (True, "")

    def test_le_lien_explicite_remplace_aucune(self, db):
        db.definir_references_associees([(WP, None), (IND, None)], LE)
        assert db.lier_reference_associee(WP, IND, LE)[0]
        assert db.reference_associee(WP) == (True, IND)
        assert db.reference_associee(IND) == (False, None)   # plus de « aucune »

    def test_retirer_garde_l_equivalence_et_enleve_la_ligne_0(self, db):
        db.lier_reference_associee(WP, IND, LE)
        assert db.retirer_reference_associee(IND) == WP       # depuis l'associée aussi
        assert db.reference_associee(WP) == (False, None)     # plus proposée
        assert IND in db.get_equivalents(WP)
        assert _ligne_fiche(db, IND) is None
        assert db.retirer_reference_associee(WP) is None

    def test_inverser_deplace_la_ligne_0(self, db):
        db.lier_reference_associee(WP, IND, LE)
        assert db.inverser_reference_associee(WP, LE)
        assert db.reference_associee(IND) == (True, WP)
        assert db.reference_principale_de(WP) == IND
        assert (_ligne_fiche(db, WP), _ligne_fiche(db, IND)) == (0, None)

    def test_inverser_une_paire_de_fiche_sans_ligne_0(self, db):
        db.lier_paires_fiche([(WP, IND)], LE)
        assert db.inverser_reference_associee(IND, LE)
        assert db.reference_associee(IND) == (True, WP)
        assert (_ligne_fiche(db, WP), _ligne_fiche(db, IND)) == (None, None)

    def test_refuser_la_proposee(self, db):
        db.add_equivalence(WP, IND)
        db.conn.execute("UPDATE piece_equivalence_groups SET ligne_fiche = 0 WHERE ref_piece = ?",
                        [IND])
        db.conn.commit()
        assert db.reference_associee(WP) == (False, IND)
        db.refuser_reference_proposee(IND)
        assert db.reference_associee(WP) == (False, None)
        assert IND in db.get_equivalents(WP)

    def test_aucune_puis_oubli(self, db):
        db.definir_references_associees([(WP, None)], LE)
        assert db.reference_associee(WP) == (True, None)
        db.oublier_reponse_aucune(WP)
        assert db.reference_associee(WP) == (False, None)

    def test_retirer_du_groupe_defait_la_paire(self, db):
        """Bug d'avant : la paire survivait au retrait de l'équivalence et imposait
        encore son ordre dans la Fiche complète."""
        db.lier_reference_associee(WP, IND, LE)
        db.definir_references_associees([(BEKO, None)], LE)
        db.add_equivalence(WP, BEKO)
        db.remove_equivalence(IND)
        assert db.references_associees_de(WP) == set()
        assert db.reference_principale_de(IND) is None
        assert db.reference_associee(BEKO) == (True, None)    # « aucune » gardée

    def test_renommage_et_suppression_suivent_l_associee(self, db):
        db.lier_reference_associee(WP, IND, LE)
        assert db.rename_piece_catalog(IND, 'C00316029', 'Courroie')
        assert db.reference_associee(WP) == (True, 'C00316029')
        db.delete_piece_catalog('C00316029')
        assert db.references_associees_de(WP) == set()


# ── Fenêtre ──────────────────────────────────────────────────────────────────

def _vider_boucle(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)
    qapp.processEvents()


@pytest.fixture
def fenetre(qapp, db, monkeypatch):
    import src.ui.pieces_manager as pm
    ouverts, avertis = [], []
    monkeypatch.setattr(pm, 'ouvrir_modal',
                        lambda dlg, sur_accepte=None, **k: ouverts.append((dlg, sur_accepte)))
    monkeypatch.setattr(pm, 'demander_oui_non',
                        lambda parent, titre, message, sur_oui, *a, **k: sur_oui())
    monkeypatch.setattr(pm.QMessageBox, 'warning',
                        lambda parent, titre, message, *a: avertis.append(message))
    fen = pm.PiecesManagerWindow(None, db)
    fen._notify_history = lambda *a: None
    fen._load_pieces_data = lambda *a, **k: None

    def choisir(*refs):
        fen._get_selected_refs = lambda: sorted(refs)
        fen._current_ref_piece = refs[0]
        fen._refresh_equivalence_panel(refs[0])

    fen.choisir = choisir
    yield fen, ouverts, avertis
    fen.close()
    _vider_boucle(qapp)


def _lignes(ligne):
    """Textes de chaque ligne de la paire : [[rôle, réf., …], …]."""
    from PyQt5.QtWidgets import QLabel
    import re
    lignes = []
    for i in range(ligne._lignes.count()):
        w = ligne._lignes.itemAt(i).widget()
        lignes.append([re.sub('<[^>]+>', '', l.text()) for l in w.findChildren(QLabel)
                       if l.text() and '✕' not in l.text()])
    return lignes


class TestFenetre:

    def test_quatre_etats_et_piece_hors_groupes(self, fenetre, db):
        fen, _, _ = fenetre
        ligne = fen.ligne_associee
        fen.choisir(WP)
        assert (ligne.etat, ligne.isHidden()) == (VIDE, False)
        fen.choisir(BSH)
        assert ligne.isHidden()
        db.definir_references_associees([(WP, None)], LE)
        fen.choisir(WP)
        assert ligne.etat == AUCUNE
        db.oublier_reponse_aucune(WP)
        db.add_equivalence(WP, IND)
        db.conn.execute("UPDATE piece_equivalence_groups SET ligne_fiche = 0 WHERE ref_piece = ?",
                        [IND])
        db.conn.commit()
        fen.choisir(WP)
        assert (ligne.etat, ligne.reference) == (PROPOSEE, IND)
        fen._on_confirmer_associee()
        assert (ligne.etat, ligne.reference) == (JUMELLE, IND)
        # La jumelle est en tête, pas répétée dans les puces
        assert IND not in fen.equiv_tag_list._refs
        fen.choisir(IND)
        assert (ligne.etat, ligne.reference) == (JUMELLE, WP)
        # Principale d'abord, chaque réf. avec son rôle ; la pièce affichée grisée
        assert _lignes(ligne) == [['Principale', WP, 'Courroie'],
                                  ['Associée', f'{IND} (cette pièce)']]
        fen.choisir(WP)
        assert _lignes(ligne) == [['Principale', f'{WP} (cette pièce)'],
                                  ['Associée', IND, 'Courroie']]

    def test_pas_de_proposee_deja_jumelle_d_une_autre(self, fenetre, db):
        """La ligne 0 vaut pour le groupe : la jumelle de WP n'est pas proposée à
        BEKO, équivalente du même groupe."""
        fen, _, _ = fenetre
        db.lier_reference_associee(WP, IND, LE)
        db.add_equivalence(WP, BEKO)
        fen.choisir(BEKO)
        assert fen.ligne_associee.etat == VIDE

    def test_ajouter_par_le_selecteur(self, fenetre, db):
        fen, ouverts, avertis = fenetre
        fen.choisir(WP)
        fen._on_ajouter_associee()
        (dlg, sur_accepte), = ouverts
        assert dlg.windowTitle() == f"Réf. associée de {WP} (Indesit ou Beko)"
        dlg.selected_ref = lambda: WP2
        sur_accepte()
        assert avertis and "Deux réf. Whirlpool" in avertis[0]
        dlg.selected_ref = lambda: BEKO
        sur_accepte()
        assert db.reference_associee(WP) == (True, BEKO)
        assert fen.ligne_associee.etat == JUMELLE

    def test_retirer_inverser_aucune(self, fenetre, db):
        fen, _, _ = fenetre
        db.lier_reference_associee(WP, IND, LE)
        fen.choisir(WP)
        fen._on_inverser_associee()
        assert db.reference_associee(IND) == (True, WP)
        assert _lignes(fen.ligne_associee)[0] == ['Principale', IND, 'Courroie']
        fen._on_retirer_associee()
        assert fen.ligne_associee.etat == VIDE
        assert IND in fen.equiv_tag_list._refs                # reste équivalente
        fen._on_marquer_aucune_associee()
        assert fen.ligne_associee.etat == AUCUNE

    def test_lier_deux_pieces_selectionnees(self, fenetre, db):
        fen, _, _ = fenetre
        fen.choisir(IND, WP)
        assert not fen.btn_lier_associees.isHidden()
        fen._on_lier_associees()
        assert db.reference_associee(IND) == (True, WP)       # la pièce affichée = principale
        fen.choisir(WP, WP2)
        assert fen.btn_lier_associees.isHidden()              # même groupe : pas de bouton
