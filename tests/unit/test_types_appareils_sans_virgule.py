"""
NON-RÉGRESSION (2026-10-09) : la colonne « Types d'appareils » du gestionnaire de
pièces affichait « Lave-vaisselle, » (virgule finale) quand un appareil associé
avait un type VIDE ('') — cellule vidée par Suppr, ligne Cmd+N non remplie.
GROUP_CONCAT écarte NULL mais pas la chaîne vide.
"""

import sqlite3

from src.data._db_mixins.pieces import REQUETE_PIECES_COMPLETE


def _base():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE pieces (id INTEGER PRIMARY KEY, ref_piece TEXT, description TEXT, is_phantom INTEGER);
        CREATE TABLE appareils (id INTEGER PRIMARY KEY, type TEXT);
        CREATE TABLE piece_associations (piece_id INTEGER, appareil_id INTEGER);
        INSERT INTO pieces VALUES (1, 'P1', 'Joint', 0);
        INSERT INTO appareils VALUES (1, 'Lave-vaisselle'), (2, ''), (3, '  '), (4, NULL), (5, 'Four');
        INSERT INTO piece_associations VALUES (1,1), (1,2), (1,3), (1,4), (1,5);
    """)
    return conn


def test_types_vides_ignores():
    ligne = _base().execute(REQUETE_PIECES_COMPLETE).fetchone()
    ref, _desc, nb, types, _fantome = ligne
    assert ref == "P1"
    assert nb == 5                      # le comptage d'appareils n'est pas touché
    assert sorted(types.split(",")) == ["Four", "Lave-vaisselle"]
    assert not types.startswith(",") and not types.endswith(",") and ",," not in types


def test_seulement_des_types_vides_donne_none():
    conn = _base()
    conn.execute("DELETE FROM piece_associations WHERE appareil_id IN (1, 5)")
    types = conn.execute(REQUETE_PIECES_COMPLETE).fetchone()[3]
    assert types is None                # → affiché « — » par le gestionnaire
