"""
Une référence n'est que dans un groupe d'équivalence.

Cas réel du 2026-11-17 : import de C00871425 (jumelle 264440188), remplaçante de
C00962305 (jumelle 264440194). La réf. associée C00962305 ≡ 264440194 a créé un
groupe ; l'équivalence C00871425 ≡ 264440188, un autre, où la propagation des
anciennes versions a rangé C00962305 une 2ᵉ fois. La Fiche complète de C00871425
ne lisait que ce groupe : « Remplace » montrait C00962305 sans sa jumelle.

- la propagation fusionne le groupe de l'ancienne version au lieu de la ranger
  dans deux groupes (add_equivalence et add_supersession) ;
- une base déjà scindée est réparée à l'ouverture ;
- la Fiche complète met la jumelle à la suite de l'ancienne référence.
"""

from types import SimpleNamespace

import pytest

from src.ui.fiche_produit_service import FicheProduitService

LE = '2026-11-17T12:14:09'


def _groupes(db, ref):
    return {r[0] for r in db.cursor.execute(
        "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref])}


def _scindees(db):
    return db.cursor.execute(
        "SELECT ref_piece FROM piece_equivalence_groups GROUP BY ref_piece "
        "HAVING COUNT(DISTINCT group_id) > 1").fetchall()


def _fiche(db, ref):
    service = FicheProduitService.__new__(FicheProduitService)
    service.main_window = SimpleNamespace(
        db_manager=db, seo_service=SimpleNamespace(_count_compatible_models=lambda l: 0))
    return service.references_fiche(ref)


def _import_du_17(db):
    assert db.add_supersession('C00962305', 'C00871425')[0]
    db.definir_references_associees([('C00962305', '264440194'),
                                     ('C00871425', '264440188')], LE)


def test_import_reel_un_seul_groupe(test_db_manager):
    db = test_db_manager
    _import_du_17(db)
    assert _scindees(db) == []
    assert _groupes(db, '264440194') == _groupes(db, 'C00871425')


def test_import_reel_fiche_complete(test_db_manager):
    db = test_db_manager
    _import_du_17(db)
    fiche = _fiche(db, 'C00871425')
    assert fiche['code_produit'] == ['C00871425', '264440188']
    assert fiche['remplace'] == ['C00962305', '264440194']


def test_supersession_apres_coup_fusionne(test_db_manager):
    """X ≡ J et N ≡ M existent ; X remplacée par N : J suit X dans le groupe de N."""
    db = test_db_manager
    assert db.add_equivalence('X1', 'J1')[0]
    assert db.add_equivalence('N1', 'M1')[0]
    assert db.add_supersession('X1', 'N1')[0]
    assert _scindees(db) == []
    assert _groupes(db, 'J1') == _groupes(db, 'N1')


def test_propagation_en_cascade(test_db_manager):
    """La fusion apporte une réf. qui a elle-même une ancienne version : elle suit."""
    db = test_db_manager
    assert db.add_supersession('A0', 'X2')[0]
    assert db.add_equivalence('X2', 'J2')[0]          # groupe {X2, J2, A0}
    assert db.add_supersession('B0', 'J2')[0]         # B0 entre aussi
    assert db.add_supersession('X2', 'N2')[0]
    assert db.add_equivalence('N2', 'M2')[0]
    assert _scindees(db) == []
    assert _groupes(db, 'B0') == _groupes(db, 'A0') == _groupes(db, 'M2')


def test_fusion_de_deux_groupes_partageant_une_ref(test_db_manager):
    """add_equivalence entre deux groupes qui ont déjà une réf. en commun : pas
    d'erreur de clé, un seul groupe à l'arrivée."""
    db = test_db_manager
    assert db.add_equivalence('P1', 'Q1')[0]
    assert db.add_equivalence('R1', 'S1')[0]
    gid_p, gid_r = _groupes(db, 'P1').pop(), _groupes(db, 'R1').pop()
    db.cursor.execute("INSERT INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)",
                      [gid_r, 'Q1'])                # Q1 scindée (base d'avant)
    db.conn.commit()
    assert db.add_equivalence('P1', 'R1')[0]
    assert _scindees(db) == []
    assert len(db.get_equivalents('P1')) == 3


def test_reparation_a_l_ouverture(test_db_manager):
    db = test_db_manager
    _import_du_17(db)
    # État de la base avant le correctif : C00962305 dans deux groupes
    gid = _groupes(db, 'C00871425').pop()
    db.cursor.execute("DELETE FROM piece_equivalence_groups WHERE ref_piece = '264440194'")
    db.cursor.execute("INSERT INTO piece_equivalence_groups(group_id, ref_piece, origine) "
                      "VALUES (?, 'C00962305', NULL), (?, '264440194', 'Beko')",
                      [gid + 100, gid + 100])
    db.conn.commit()
    assert _scindees(db) == [('C00962305',)]
    db._reparer_groupes_scindes()
    assert _scindees(db) == []
    assert _fiche(db, 'C00871425')['remplace'] == ['C00962305', '264440194']
    # Origine gardée par la fusion
    assert db.cursor.execute("SELECT origine FROM piece_equivalence_groups "
                             "WHERE ref_piece = '264440194'").fetchone()[0] == 'Beko'
    db._reparer_groupes_scindes()                     # sans effet la 2ᵉ fois
    assert _scindees(db) == []
