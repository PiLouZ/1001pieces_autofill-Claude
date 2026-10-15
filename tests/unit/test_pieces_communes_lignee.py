"""
Tests — Pièces communes par lignée (sélection multiple, panneau des pièces)

**Cas réel du 2026-10-15.** Six centrales vapeur Moulinex sélectionnées : le panneau
affiche « Aucune pièce commune aux 6 appareils sélectionnés ». Pourtant toutes
portent la cartouche anti-calcaire, sous deux références d'une même lignée :

    FS-9100017944  →  XD9030E0

    2 appareils : FS-9100017944 seule
    1 appareil  : XD9030E0 seule
    3 appareils : les deux

L'intersection se faisait sur les références brutes. Elle se fait désormais aussi
sur la tête de lignée de chaque référence, et la pièce s'affiche sous sa
référence courante avec la mention « Commune par lignée ».
"""

from unittest.mock import Mock

import pytest

from src.ui.pieces_panel_service import PiecesPanelService
from src.ui.pieces_list_service import PiecesListWidget, PiecesListService


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


def _appareil(db, ref_modele, pieces):
    db_id = db.insert_appareil({'type': 'Centrale vapeur', 'manufacturer': 'Moulinex',
                                'ref_modele': ref_modele})
    for ref in pieces:
        db.add_piece(ref, db_id, 'Cartouches anti-calcaire x2')
    return db_id


class _FausseFenetre:
    """Juste ce que PiecesPanelService lit de la fenêtre principale."""

    def __init__(self, db, ids):
        self.db_manager = db
        self.pieces_list = PiecesListWidget()
        self.table = Mock()
        self.table.selectedRanges.return_value = [
            Mock(topRow=Mock(return_value=0), bottomRow=Mock(return_value=len(ids) - 1))]
        self.table_fill_service = Mock()
        self.table_fill_service.get_db_id_from_row.side_effect = lambda _t, row: ids[row]
        self.pieces_header_label = Mock()
        self.pieces_count_label = Mock()


def _panneau(db, ids):
    fenetre = _FausseFenetre(db, ids)
    PiecesPanelService(fenetre).update_pieces_panel()
    lignes = []
    for i in range(fenetre.pieces_list.count()):
        item = fenetre.pieces_list.item(i)
        widget = fenetre.pieces_list.itemWidget(item)
        lignes.append((item.data(0x0100), widget))  # Qt.UserRole
    return fenetre, lignes


# ── Résolution en lot ────────────────────────────────────────────────────────

class TestResolutionEnLot:

    def test_meme_resultat_que_la_version_unitaire(self, db):
        db.add_supersession('A', 'B')
        db.add_supersession('B', 'C')
        db.add_supersession('X', 'Y')
        refs = ['A', 'B', 'C', 'X', 'Y', 'SEULE', 'INCONNUE']
        lot = db.resolve_current_refs_batch(refs)
        assert lot == {r: db.resolve_current_ref(r) for r in refs}
        assert lot['A'] == 'C'

    def test_plus_de_500_refs(self, db):
        db.add_supersession('R0', 'TETE')
        refs = [f'R{i}' for i in range(1200)]
        lot = db.resolve_current_refs_batch(refs)
        assert len(lot) == 1200
        assert lot['R0'] == 'TETE'
        assert lot['R1199'] == 'R1199'

    def test_liste_vide(self, db):
        assert db.resolve_current_refs_batch([]) == {}


# ── Panneau des pièces ───────────────────────────────────────────────────────

class TestPanneauCommunesParLignee:

    def test_cas_reel_moulinex(self, db, qapp):
        db.add_supersession('FS-9100017944', 'XD9030E0')
        ids = [
            _appareil(db, '1830005978', ['FS-9100017944']),
            _appareil(db, '1830005384', ['FS-9100017944']),
            _appareil(db, '1830006916', ['XD9030E0']),
            _appareil(db, '1830006252', ['XD9030E0', 'FS-9100017944']),
            _appareil(db, '1830005544', ['XD9030E0', 'FS-9100017944']),
            _appareil(db, '1830005526', ['XD9030E0', 'FS-9100017944']),
        ]
        fenetre, lignes = _panneau(db, ids)

        assert [ref for ref, _ in lignes] == ['XD9030E0']
        widget = lignes[0][1]
        assert widget._status_info['commune_par_lignee'] == {'FS-9100017944': 2}
        assert widget._delete_btn not in widget._hover_btns
        fenetre.pieces_count_label.setText.assert_called_with("1 pièce")

    def test_commune_a_l_identique_inchangee(self, db, qapp):
        """Zéro régression : une réf commune à tous s'affiche comme avant."""
        db.add_supersession('OLD', 'NEW')
        ids = [_appareil(db, 'M1', ['OLD', 'P']), _appareil(db, 'M2', ['OLD', 'P'])]
        _, lignes = _panneau(db, ids)

        # OLD commune à l'identique : pas de doublon NEW par lignée
        assert [ref for ref, _ in lignes] == ['OLD', 'P']
        for _, widget in lignes:
            assert 'commune_par_lignee' not in widget._status_info
            assert widget._delete_btn in widget._hover_btns

    def test_tete_absente_de_tous_les_appareils(self, db, qapp):
        """Deux anciennes réf. distinctes remplacées par la même : la courante s'affiche."""
        db.add_supersession('A1', 'C')
        db.add_supersession('A2', 'C')
        ids = [_appareil(db, 'M1', ['A1']), _appareil(db, 'M2', ['A2'])]
        _, lignes = _panneau(db, ids)

        assert [ref for ref, _ in lignes] == ['C']
        assert lignes[0][1]._status_info['commune_par_lignee'] == {'A1': 1, 'A2': 1}

    def test_aucune_commune_meme_par_lignee(self, db, qapp):
        ids = [_appareil(db, 'M1', ['P1']), _appareil(db, 'M2', ['P2'])]
        fenetre, lignes = _panneau(db, ids)

        assert lignes[0][1] is None  # item texte « Aucune pièce commune… »
        assert 'Aucune pièce commune' in fenetre.pieces_list.item(0).text()

    def test_equivalence_hors_perimetre(self, db, qapp):
        """Une équivalente n'est pas la même pièce : pas de mise en commun."""
        db.add_equivalence('E1', 'E2')
        ids = [_appareil(db, 'M1', ['E1']), _appareil(db, 'M2', ['E2'])]
        fenetre, _ = _panneau(db, ids)

        assert 'Aucune pièce commune' in fenetre.pieces_list.item(0).text()

    def test_menu_contextuel_sans_suppression_pour_la_lignee(self, db, qapp):
        db.add_supersession('OLD', 'NEW')
        ids = [_appareil(db, 'M1', ['OLD']), _appareil(db, 'M2', ['NEW'])]
        fenetre, lignes = _panneau(db, ids)
        fenetre._delete_piece_from_selected = Mock()
        fenetre.pieces_list.itemAt = Mock(return_value=fenetre.pieces_list.item(0))

        # Le menu ne doit même pas être construit : retour avant QMenu
        import src.ui.pieces_list_service as module
        module_qmenu = module.QMenu
        module.QMenu = Mock(side_effect=AssertionError("menu construit"))
        try:
            PiecesListService(fenetre)._show_pieces_context_menu(None)
        finally:
            module.QMenu = module_qmenu
