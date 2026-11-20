"""
Origine déclarée d'une référence hors des formats connus (CDC fiches du site
§ 10.17 bis).

Cas réel du 2026-11-20 : import de C00869049 (Indesit), 210480241 et S210480241
(Beko, 9 chiffres en 21 : forme absente de la table des formats). La réf. Beko ne
pouvait recevoir de réf. associée ni à l'import (champ masqué) ni dans le
gestionnaire de pièces (« n'est ni Whirlpool, ni Indesit, ni Beko »).

- la base mémorise le groupe déclaré (Whirlpool / Indesit / Beko) d'une réf. et
  le remet dans le registre de `associee.py` à l'ouverture ;
- la déclaration l'emporte sur la forme ; elle suit le renommage, part avec la
  suppression, s'oublie ;
- l'import écrit les groupes choisis avant les paires ;
- le champ de l'import propose « Associer… » pour une réf. de forme inconnue,
  et le choix du groupe d'une réf. associée de forme inconnue ;
- le gestionnaire affiche « forme non reconnue », déclare, lie une associée de
  forme inconnue après avoir demandé son groupe.
"""

import os
import tempfile
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.utils.rapprochement_fiche.associee import (definir_origines_declarees,
                                                    origine_associable, origine_declaree)

IND = 'C00869049'                       # Indesit
BEKO_INCONNUE = '210480241'             # Beko, forme inconnue
BEKO_S = 'S210480241'                   # Beko, forme inconnue
WP = '481246688999'                     # Whirlpool
ELECTROLUX = '1400810100'               # lue Electrolux par sa forme
LE = '2026-11-20T12:00:00'


@pytest.fixture(autouse=True)
def registre_vide():
    definir_origines_declarees({})
    yield
    definir_origines_declarees({})


@pytest.fixture
def chemin():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    yield chemin
    Config.DB_FILE = origine
    if os.path.exists(chemin):
        os.remove(chemin)


@pytest.fixture
def db(chemin):
    manager = DatabaseManager()
    for ref in (IND, BEKO_INCONNUE, BEKO_S, WP, ELECTROLUX):
        manager.create_piece_standalone(ref, 'Pompe')
    yield manager
    manager.close()


# ── Base ─────────────────────────────────────────────────────────────────────

class TestBase:

    def test_declarer_rend_la_ref_associable(self, db):
        assert origine_associable(BEKO_INCONNUE) == ''
        assert db.declarer_origines({BEKO_INCONNUE: 'Beko', BEKO_S: 'Beko'}, LE) == 2
        assert origine_associable(BEKO_INCONNUE) == 'Beko'
        assert origine_associable(BEKO_S) == 'Beko'

    def test_relu_a_l_ouverture(self, db, chemin):
        db.declarer_origines({BEKO_INCONNUE: 'Beko'}, LE)
        definir_origines_declarees({})                # registre perdu (relance)
        assert origine_associable(BEKO_INCONNUE) == ''
        autre = DatabaseManager()
        try:
            assert origine_associable(BEKO_INCONNUE) == 'Beko'
        finally:
            autre.close()

    def test_la_declaration_l_emporte_sur_la_forme(self, db):
        assert origine_associable(ELECTROLUX) == ''
        db.declarer_origines({ELECTROLUX: 'Beko'}, LE)
        assert origine_associable(ELECTROLUX) == 'Beko'

    def test_groupe_hors_des_trois_ignore(self, db):
        assert db.declarer_origines({BEKO_INCONNUE: 'Electrolux', '': 'Beko'}, LE) == 0
        assert origine_associable(BEKO_INCONNUE) == ''

    def test_lier_apres_declaration(self, db):
        ok, motif = db.lier_reference_associee(IND, BEKO_INCONNUE, LE)
        assert not ok and "déclarez d'abord son groupe" in motif
        # Groupe à venir (choisi juste après dans le gestionnaire) : accepté
        assert db.motif_refus_associee(IND, BEKO_INCONNUE, origine_associee='Beko') == ''
        assert "ne peuvent pas être jumelles" in db.motif_refus_associee(
            IND, BEKO_INCONNUE, origine_associee='Indesit')
        db.declarer_origines({BEKO_INCONNUE: 'Beko'}, LE)
        assert db.lier_reference_associee(IND, BEKO_INCONNUE, LE) == (True, "")
        assert db.reference_associee(IND) == (True, BEKO_INCONNUE)
        assert BEKO_INCONNUE in db.get_equivalents(IND)
        row = db.conn.execute("SELECT origine FROM piece_equivalence_groups WHERE ref_piece = ?",
                              [BEKO_INCONNUE]).fetchone()
        assert row == ('Beko',)

    def test_oublier(self, db):
        db.declarer_origines({BEKO_INCONNUE: 'Beko'}, LE)
        assert db.oublier_origine_declaree(BEKO_INCONNUE)
        assert origine_associable(BEKO_INCONNUE) == ''
        assert not db.oublier_origine_declaree(BEKO_INCONNUE)

    def test_renommage_et_suppression(self, db):
        db.declarer_origines({BEKO_INCONNUE: 'Beko'}, LE)
        assert db.rename_piece_catalog(BEKO_INCONNUE, '210480242', 'Pompe')
        assert origine_declaree(BEKO_INCONNUE) == ''
        assert origine_declaree('210480242') == 'Beko'
        db._safe_delete_piece_catalog('210480242')
        assert origine_declaree('210480242') == ''
        assert db.conn.execute("SELECT COUNT(*) FROM origines_declarees").fetchone() == (0,)


# ── Import ───────────────────────────────────────────────────────────────────

class TestImport:

    def test_groupes_ecrits_avant_les_paires(self, db):
        from src.core.import_manager import ImportManager
        config = SimpleNamespace(references_associees={BEKO_INCONNUE: IND},
                                 origines_declarees={BEKO_INCONNUE: 'Beko'})
        results = {}
        ImportManager._appliquer_references_associees(SimpleNamespace(db_manager=db),
                                                      config, results)
        assert results['origines_declarees'] == {BEKO_INCONNUE: 'Beko'}
        assert db.reference_associee(BEKO_INCONNUE) == (True, IND)
        assert origine_associable(BEKO_INCONNUE) == 'Beko'

    def test_sans_groupe_declare_rien_ne_change(self, db):
        from src.core.import_manager import ImportManager
        config = SimpleNamespace(references_associees={IND: WP}, origines_declarees=None)
        results = {}
        ImportManager._appliquer_references_associees(SimpleNamespace(db_manager=db),
                                                      config, results)
        assert 'origines_declarees' not in results
        assert db.reference_associee(IND) == (True, WP)


class TestChampImport:

    @staticmethod
    def _champ(qapp, inversion=None):
        from src.ui.champ_reference_associee import ChampReferenceAssociee
        return ChampReferenceAssociee(lambda ref: (False, None), inversion=inversion)

    def test_ref_connue_inchangee(self, qapp):
        champ = self._champ(qapp)
        champ.definir_reference(IND)
        assert not champ.isHidden() and not champ.champ.isHidden()
        assert champ.lien_associer.isHidden() and champ.groupe_piece.isHidden()
        assert champ.origines_declarees() == {}

    def test_associer_une_ref_de_forme_inconnue(self, qapp):
        champ = self._champ(qapp)
        champ.definir_reference(BEKO_INCONNUE)
        assert not champ.isHidden()
        assert not champ.lien_associer.isHidden() and champ.champ.isHidden()
        assert champ.reponse() == (False, None)
        champ._sur_associer()
        assert champ.lien_associer.isHidden() and not champ.groupe_piece.isHidden()
        assert champ.champ.isHidden()                    # groupe pas encore choisi
        champ.groupe_piece.setCurrentIndex(champ.groupe_piece.findData('Beko'))
        assert not champ.champ.isHidden()
        assert champ.champ._placeholder == "Réf. Whirlpool ou Indesit"
        champ.champ.set_refs([IND])
        assert champ.groupe_associee.isHidden()          # Indesit : forme connue
        assert champ.reponse() == (True, IND)
        assert champ.origines_declarees() == {BEKO_INCONNUE: 'Beko'}

    def test_associee_de_forme_inconnue(self, qapp):
        champ = self._champ(qapp)
        champ.definir_reference(IND)
        champ.champ.set_refs([BEKO_INCONNUE])
        assert not champ.groupe_associee.isHidden()
        groupes = [champ.groupe_associee.itemData(i)
                   for i in range(champ.groupe_associee.count())]
        assert groupes == ['', 'Whirlpool', 'Beko']
        assert champ.origines_declarees() == {}          # rien de choisi
        champ.groupe_associee.setCurrentIndex(groupes.index('Beko'))
        assert champ.reponse() == (True, BEKO_INCONNUE)
        assert champ.origines_declarees() == {BEKO_INCONNUE: 'Beko'}

    def test_inversion_garde_le_groupe_choisi(self, qapp):
        inversions = []
        champ = self._champ(qapp, inversion=lambda n, a: inversions.append((n, a)))
        champ.definir_reference(IND)
        champ.champ.set_refs([BEKO_INCONNUE])
        champ.groupe_associee.setCurrentIndex(champ.groupe_associee.findData('Beko'))
        champ.inverser()
        assert inversions == [(BEKO_INCONNUE, IND)]
        assert champ.reference == BEKO_INCONNUE
        assert not champ.groupe_piece.isHidden()
        assert champ.groupe_piece.currentData() == 'Beko'
        assert champ.reponse() == (True, IND)
        assert champ.origines_declarees() == {BEKO_INCONNUE: 'Beko'}

    def test_ref_deja_declaree_affiche_le_champ(self, qapp, db):
        db.declarer_origines({BEKO_INCONNUE: 'Beko'}, LE)
        champ = self._champ(qapp)
        champ.definir_reference(BEKO_INCONNUE)
        assert not champ.champ.isHidden() and champ.lien_associer.isHidden()
        assert champ.groupe_piece.isHidden()             # déjà mémorisé
        champ.champ.set_refs([IND])
        assert champ.origines_declarees() == {}


# ── Gestionnaire de pièces ───────────────────────────────────────────────────

def _vider_boucle(qapp):
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)
    qapp.processEvents()


@pytest.fixture
def fenetre(qapp, db, monkeypatch):
    import src.ui.pieces_manager as pm
    ouverts, choix, avertis = [], [], []
    monkeypatch.setattr(pm, 'ouvrir_modal',
                        lambda dlg, sur_accepte=None, **k: ouverts.append((dlg, sur_accepte)))
    monkeypatch.setattr(pm, 'choisir_element',
                        lambda parent, titre, libelle, elements, sur_element, **k:
                        choix.append((elements, sur_element)))
    monkeypatch.setattr(pm.QMessageBox, 'warning',
                        lambda parent, titre, message, *a: avertis.append(message))
    fen = pm.PiecesManagerWindow(None, db)
    fen._notify_history = lambda *a: None
    fen._load_pieces_data = lambda *a, **k: None

    def choisir(ref):
        fen._get_selected_refs = lambda: [ref]
        fen._current_ref_piece = ref
        fen._refresh_equivalence_panel(ref)

    fen.choisir = choisir
    yield fen, ouverts, choix, avertis
    fen.close()
    _vider_boucle(qapp)


class TestGestionnaire:

    def test_declarer_puis_oublier(self, fenetre, db):
        from src.ui.ligne_reference_associee import INCONNUE, VIDE
        fen, _, choix, _ = fenetre
        fen.choisir(BEKO_INCONNUE)
        assert (fen.ligne_associee.etat, fen.ligne_associee.isHidden()) == (INCONNUE, False)
        fen._on_declarer_groupe()
        (elements, sur_element), = choix
        assert elements == ['Whirlpool', 'Indesit', 'Beko']
        sur_element('Beko')
        assert fen.ligne_associee.etat == VIDE
        assert origine_associable(BEKO_INCONNUE) == 'Beko'
        fen._on_oublier_groupe()
        assert fen.ligne_associee.etat == INCONNUE

    def test_associee_de_forme_inconnue_par_le_selecteur(self, fenetre, db, qapp):
        from src.ui.ligne_reference_associee import JUMELLE
        fen, ouverts, choix, avertis = fenetre
        fen.choisir(IND)
        fen._on_ajouter_associee()
        (dlg, sur_accepte), = ouverts
        # Réf. de forme inconnue : seulement quand on la cherche
        visibles = lambda: {dlg._proxy.index(i, 0).data() for i in range(dlg._proxy.rowCount())}
        assert visibles() == {WP}
        dlg._recherche.setText('2104')
        dlg._filtrer()
        assert visibles() == {BEKO_INCONNUE, BEKO_S}
        dlg.selected_ref = lambda: BEKO_INCONNUE
        sur_accepte()
        _vider_boucle(qapp)                               # choix du groupe différé
        (elements, sur_element), = choix
        assert elements == ['Whirlpool', 'Beko']
        sur_element('Beko')
        assert not avertis
        assert db.reference_associee(IND) == (True, BEKO_INCONNUE)
        assert fen.ligne_associee.etat == JUMELLE

    def test_jumelle_d_une_ref_redevenue_inconnue_reste_affichee(self, fenetre, db):
        from src.ui.ligne_reference_associee import JUMELLE
        fen, _, _, _ = fenetre
        db.declarer_origines({BEKO_INCONNUE: 'Beko'}, LE)
        db.lier_reference_associee(IND, BEKO_INCONNUE, LE)
        db.oublier_origine_declaree(BEKO_INCONNUE)
        fen.choisir(BEKO_INCONNUE)
        assert (fen.ligne_associee.etat, fen.ligne_associee.reference) == (JUMELLE, IND)
