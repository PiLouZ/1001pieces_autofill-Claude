"""
Carte « nouvelle pièce » du panneau Pièces : sans appareil sélectionné, la pièce
est créée seule au catalogue (plus besoin d'ouvrir le gestionnaire de pièces).
Avec un ou plusieurs appareils, le comportement d'avant est inchangé.
"""

from unittest.mock import MagicMock

import pytest

from src.ui.piece_management_service import PieceManagementService


def _piece(db, ref):
    db.cursor.execute(
        "SELECT is_phantom, description FROM pieces WHERE ref_piece = ?", (ref,))
    return db.cursor.fetchone()


def _nb_associations(db, ref):
    db.cursor.execute(
        "SELECT COUNT(*) FROM piece_associations pa JOIN pieces p ON p.id = pa.piece_id "
        "WHERE p.ref_piece = ?", (ref,))
    return db.cursor.fetchone()[0]


# ── Base : creer_piece_seule ─────────────────────────────────────────────

def test_creation_piece_seule(test_db_manager):
    assert test_db_manager.creer_piece_seule('PS-001', '  Joint de hublot ') == 'creee'
    assert _piece(test_db_manager, 'PS-001') == (0, 'Joint de hublot')
    assert _nb_associations(test_db_manager, 'PS-001') == 0


def test_creation_sans_libelle(test_db_manager):
    assert test_db_manager.creer_piece_seule('PS-002', '   ') == 'creee'
    assert _piece(test_db_manager, 'PS-002') == (0, None)


def test_piece_existante_non_modifiee(test_db_manager):
    test_db_manager.creer_piece_seule('PS-003', 'Libellé d\'origine')
    assert test_db_manager.creer_piece_seule('PS-003', 'Autre libellé') == 'existante'
    assert _piece(test_db_manager, 'PS-003') == (0, "Libellé d'origine")


def test_fantome_promue(test_db_manager):
    test_db_manager.cursor.execute(
        "INSERT INTO pieces(ref_piece, is_phantom) VALUES ('PS-FANT', 1)")
    test_db_manager.conn.commit()
    assert test_db_manager.creer_piece_seule('PS-FANT', 'Moteur') == 'promue'
    assert _piece(test_db_manager, 'PS-FANT') == (0, 'Moteur')


def test_fantome_promue_garde_son_libelle(test_db_manager):
    test_db_manager.cursor.execute(
        "INSERT INTO pieces(ref_piece, is_phantom, description) VALUES ('PS-FANT2', 1, 'Pompe')")
    test_db_manager.conn.commit()
    assert test_db_manager.creer_piece_seule('PS-FANT2', 'Autre') == 'promue'
    assert _piece(test_db_manager, 'PS-FANT2') == (0, 'Pompe')


# ── Service : add_piece selon la sélection ───────────────────────────────

def _fenetre(db, ref, libelle='', lignes=(), ids=None):
    """Fenêtre principale factice : tableau avec la sélection donnée."""
    mw = MagicMock()
    mw.db_manager = db
    mw.piece_input.text.return_value = ref
    mw.piece_libelle_input.text.return_value = libelle
    if lignes:
        plage = MagicMock()
        plage.topRow.return_value = min(lignes)
        plage.bottomRow.return_value = max(lignes)
        mw.table.selectedRanges.return_value = [plage]
    else:
        mw.table.selectedRanges.return_value = []
        mw.table.currentRow.return_value = -1
    ids = ids or {}
    mw.table_fill_service.get_db_id_from_row.side_effect = lambda _t, row: ids.get(row)
    return mw


def test_service_sans_appareil_cree_la_piece(test_db_manager):
    mw = _fenetre(test_db_manager, 'PS-010', 'Courroie')
    assert PieceManagementService(mw).add_piece() is True
    assert _piece(test_db_manager, 'PS-010') == (0, 'Courroie')
    assert _nb_associations(test_db_manager, 'PS-010') == 0
    mw.user_interaction_service.add_to_history.assert_called_once()
    assert 'sans appareil' in mw.user_interaction_service.add_to_history.call_args[0][0]


def test_service_sans_appareil_ref_existante(test_db_manager):
    test_db_manager.creer_piece_seule('PS-011', 'X')
    mw = _fenetre(test_db_manager, 'PS-011')
    assert PieceManagementService(mw).add_piece() is False
    mw.user_interaction_service.show_info.assert_called_once()
    mw.user_interaction_service.add_to_history.assert_not_called()


@pytest.mark.parametrize('ref', ['', 'A||B', 'A&&B'])
def test_service_sans_appareil_ref_invalide(test_db_manager, ref):
    mw = _fenetre(test_db_manager, ref)
    assert PieceManagementService(mw).add_piece() is False
    test_db_manager.cursor.execute("SELECT COUNT(*) FROM pieces")
    assert test_db_manager.cursor.fetchone()[0] == 0


def test_service_un_appareil_inchange(test_db_manager, sample_device_data):
    dev = test_db_manager.insert_appareil(sample_device_data)
    mw = _fenetre(test_db_manager, 'PS-020', 'Filtre', lignes=(0,), ids={0: dev})
    assert PieceManagementService(mw).add_piece() is True
    assert _nb_associations(test_db_manager, 'PS-020') == 1
    assert 'ajoutée' in mw.user_interaction_service.add_to_history.call_args[0][0]
    mw.pieces_panel_service.update_pieces_panel.assert_called_once()


def test_service_plusieurs_appareils_inchange(test_db_manager, multiple_devices_data):
    ids = {i: test_db_manager.insert_appareil(d) for i, d in enumerate(multiple_devices_data[:3])}
    mw = _fenetre(test_db_manager, 'PS-021', lignes=(0, 1, 2), ids=ids)
    assert PieceManagementService(mw).add_piece() is True
    assert _nb_associations(test_db_manager, 'PS-021') == 3


# ── Carte : libellés selon la cible ──────────────────────────────────────

def test_carte_libelles(qapp):
    from src.ui.piece_add_card import PieceAddCard
    carte = PieceAddCard(on_submit=lambda: None)
    carte.set_target_count(0)
    assert carte.target_label.text() == 'Pièce seule'
    assert carte.add_btn.text() == 'Créer'
    carte.set_target_count(3)
    assert carte.target_label.text() == '→ 3 appareils'
    assert carte.add_btn.text() == 'Ajouter'
