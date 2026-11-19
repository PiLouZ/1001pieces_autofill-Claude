"""
Jumelle d'une équivalente : elle reste sur la ligne de sa pièce, pas dans le code produit.

Cas réel C00140702 (thermostat Ranco K59L2176) : la fiche du site donne
« Code produit : C00140702 482000029514 » et « Références équivalentes : C00537573 ».
Lier ensuite 488000537573 comme réf. associée de C00537573 la marquait « ligne 0 »
(règle : principale non remplacée → code produit), et l'export de la fiche la
montait dans le code produit, loin de sa jumelle.

- écriture : la jumelle prend la ligne de sa pièce (0 pour la pièce du produit du
  site, N pour une équivalente de la ligne N, rien pour une ancienne référence) ;
- réparation à l'ouverture des marques « ligne 0 » déjà posées à tort ;
- garde-fou de l'export : une « ligne 0 » dont la jumelle n'est pas du code produit
  reste avec elle.
"""

import pytest

from tests.unit.test_fiche_export_site import _fiche_service
from tests.unit.test_reprise_site import Construite

PIECE, JUMELLE = 'C00140702', '482000029514'
EQUIV, JUMELLE_EQUIV = 'C00537573', '488000537573'
ANCIENNE, JUMELLE_ANCIENNE = 'C00140721', '482000046917'
LE = '2026-11-19T10:30:00'


def _ligne(db, ref):
    return db.conn.execute("SELECT ligne_fiche FROM piece_equivalence_groups WHERE ref_piece = ?",
                           [ref]).fetchone()[0]


@pytest.fixture
def db(tmp_path):
    """La base telle qu'après la reprise de la fiche de C00140702, avant les liens à la main."""
    b = Construite(tmp_path)
    db = b.db
    for ref in (PIECE, JUMELLE, EQUIV, JUMELLE_EQUIV, ANCIENNE, JUMELLE_ANCIENNE):
        db.create_piece_standalone(ref, 'Thermostat ranco K59L2176')
    db.add_supersession(ANCIENNE, PIECE)
    db.add_supersession(JUMELLE_ANCIENNE, JUMELLE)
    for ref in (JUMELLE, EQUIV, JUMELLE_EQUIV):
        assert db.add_equivalence(PIECE, ref)[0]
    db.conn.execute("INSERT INTO produits_site (ref_interne, id_product, ref_piece) "
                    "VALUES ('SCS140702', 18709, ?)", [PIECE])
    db.conn.executemany(
        "UPDATE piece_equivalence_groups SET origine = ?, ligne_fiche = ? WHERE ref_piece = ?",
        [('Whirlpool', 0, JUMELLE), ('Indesit', 1, EQUIV), ('Whirlpool', 1, JUMELLE_EQUIV)])
    db.conn.commit()
    db.definir_references_associees([(PIECE, JUMELLE)], LE, {JUMELLE: 'Whirlpool'})
    yield db
    db.close()


def _fiche_attendue(db):
    refs = _fiche_service(db).references_fiche(PIECE)
    assert refs['code_produit'] == [PIECE, JUMELLE]
    assert refs['remplace'] == [ANCIENNE, JUMELLE_ANCIENNE]
    assert refs['lignes_equivalentes'] == [[EQUIV, JUMELLE_EQUIV]]


def test_lier_la_jumelle_d_une_equivalente_garde_sa_ligne(db):
    assert db.lier_reference_associee(EQUIV, JUMELLE_EQUIV, LE) == (True, "")
    assert db.lier_reference_associee(ANCIENNE, JUMELLE_ANCIENNE, LE) == (True, "")
    assert _ligne(db, JUMELLE_EQUIV) == 1
    assert _ligne(db, JUMELLE) == 0                       # la paire du code produit, inchangée
    _fiche_attendue(db)


def test_regles_de_ligne_de_la_jumelle(db):
    assert db._ligne_de_la_jumelle(PIECE) == 0            # pièce du produit du site
    assert db._ligne_de_la_jumelle(EQUIV) == 1            # équivalente de la ligne 1
    assert db._ligne_de_la_jumelle(ANCIENNE) is None      # ancienne : « Remplace »
    assert db._ligne_de_la_jumelle(JUMELLE_ANCIENNE) is None


def _marque_fausse(db):
    """État de la base du 19/11 : la jumelle de l'équivalente marquée « ligne 0 »."""
    db.lier_reference_associee(EQUIV, JUMELLE_EQUIV, LE)
    db.lier_reference_associee(ANCIENNE, JUMELLE_ANCIENNE, LE)
    db.conn.execute("UPDATE piece_equivalence_groups SET ligne_fiche = 0 WHERE ref_piece = ?",
                    [JUMELLE_EQUIV])
    db.conn.commit()


def test_reparation_a_l_ouverture(db):
    _marque_fausse(db)
    assert db._reparer_jumelles_d_equivalentes() == 1
    assert _ligne(db, JUMELLE_EQUIV) == 1
    assert _ligne(db, JUMELLE) == 0                       # la vraie ligne 0 n'est pas touchée
    assert db._reparer_jumelles_d_equivalentes() == 0     # rien de plus au 2ᵉ passage
    _fiche_attendue(db)


def test_garde_fou_de_l_export_sans_reparation(db):
    _marque_fausse(db)
    _fiche_attendue(db)


def test_jumelle_de_la_piece_toujours_au_code_produit(db):
    """Sans jumelle : une équivalente de ligne 0 monte toujours au code produit."""
    db.conn.execute("DELETE FROM references_associees")
    db.conn.commit()
    assert _fiche_service(db).references_fiche(PIECE)['code_produit'] == [PIECE, JUMELLE]
