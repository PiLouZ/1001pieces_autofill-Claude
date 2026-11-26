"""
Appareil ajouté pendant une recherche : épinglé en tête du tableau

Cmd+N créait la ligne, puis le rechargement gardait la recherche et les filtres :
la ligne vide n'y correspondait pas et restait invisible. Les appareils épinglés
échappent désormais à la recherche et aux filtres de colonne (pas au filtre
« Lignes à traiter »), viennent en tête quel que soit le tri, sont comptés dans
« N résultats » et trouvés par le saut ▲/▼, mais jamais exportés.
"""

import os
import tempfile
from types import SimpleNamespace

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.services.search_service import SearchService
from src.ui.table_controller import TableController


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        conn.executemany(
            "INSERT INTO appareils (id, type, manufacturer, ref_modele, commercial_ref, "
            "other_ref, notes, category) VALUES (?, ?, ?, ?, ?, '', '', '')",
            [(1, 'Four', 'Bosch', 'HBA123', 'C1'),
             (2, 'Four', 'Siemens', 'HBA456', 'C2'),
             (3, '', 'Bosch', 'WAE100', 'C3'),
             (4, 'Lave-linge', '', 'WAE200', 'C4'),
             (5, 'Hotte', 'Elica', 'EL9', 'C5'),
             # 6 et 7 : lignes « Cmd+N », vides, hors de toute recherche
             (6, '', '', '', ''),
             (7, 'Four', 'Bosch', 'ZZZ1', '')])
        conn.executemany("INSERT INTO pieces (id, ref_piece) VALUES (?, ?)",
                         [(1, 'JOINT01'), (2, 'MOTEUR77')])
        conn.executemany("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)",
                         [(1, 1), (1, 3), (2, 2), (2, 4), (2, 5)])
        conn.commit()
        manager.invalidate_search_cache(invalidate_total_count=True)
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _ids(rows):
    return [r[0] for r in rows]


def _pages(db, terme=None, filtres=None, tri=None, sens=None, incompletes=False, epingles=None):
    return _ids(db._load_data_original(terme, filtres, None, None, tri, sens, incompletes, epingles))


# ── Sans épingle : rien ne change ────────────────────────────────────────────

@pytest.mark.parametrize('filtres', [None, {1: 'bosch'}, {2: 'HBA'}])
@pytest.mark.parametrize('tri,sens', [(None, None), (0, 'ASC'), (2, 'DESC'), (7, 'ASC')])
def test_sans_epingle_resultat_identique(db, filtres, tri, sens):
    assert _pages(db, None, filtres, tri, sens) == _pages(db, None, filtres, tri, sens, epingles=[])


def test_sans_epingle_sql_identique():
    assert DatabaseManager._build_load_order_by(0, 'ASC') == DatabaseManager._build_load_order_by(0, 'ASC', [])
    assert DatabaseManager._build_load_order_by(None, None) == " ORDER BY a.id DESC"


# ── Avec épingle ─────────────────────────────────────────────────────────────

def test_ligne_epinglee_visible_malgre_le_filtre(db):
    assert _pages(db, filtres={2: 'A694645.00'}) == []
    assert _pages(db, filtres={2: 'A694645.00'}, epingles=[6]) == [6]


def test_ligne_epinglee_visible_malgre_la_recherche_par_piece(db):
    terme = SearchService(db).parse_advanced_search('JOINT01') or 'JOINT01'
    assert 6 not in _pages(db, terme)
    lignes = _pages(db, terme, epingles=[6])
    assert lignes[0] == 6 and sorted(lignes[1:]) == [1, 3]


@pytest.mark.parametrize('tri,sens', [(None, None), (0, 'ASC'), (0, 'DESC'), (2, 'ASC'), (7, 'DESC')])
def test_ligne_epinglee_en_tete_quel_que_soit_le_tri(db, tri, sens):
    lignes = _pages(db, filtres={1: 'bosch'}, tri=tri, sens=sens, epingles=[6])
    assert lignes[0] == 6
    # Le reste garde l'ordre du tri demandé
    assert lignes[1:] == _pages(db, filtres={1: 'bosch'}, tri=tri, sens=sens)


def test_plusieurs_epingles_le_plus_recent_en_tete(db):
    lignes = _pages(db, filtres={2: 'HBA'}, tri=0, sens='ASC', epingles=[6, 7])
    assert lignes[:2] == [7, 6]


def test_epinglee_deja_dans_le_resultat_pas_de_doublon(db):
    lignes = _pages(db, filtres={1: 'bosch'}, epingles=[7])
    assert lignes.count(7) == 1 and lignes[0] == 7


def test_filtre_lignes_a_traiter_reste_applique(db):
    # 6 est incomplète : affichée ; 7 est complète : le filtre l'écarte
    assert 6 in _pages(db, filtres={2: 'HBA'}, incompletes=True, epingles=[6])
    assert 7 not in _pages(db, filtres={2: 'HBA'}, incompletes=True, epingles=[7])


def test_comptage_compte_les_epingles(db):
    assert db.count_data(None, {2: 'A694645.00'}) == 0
    assert db.count_data(None, {2: 'A694645.00'}, ids_epingles=[6]) == 1
    assert db.count_data(None, {1: 'bosch'}, ids_epingles=[6]) == len(_pages(db, filtres={1: 'bosch'}, epingles=[6]))


def test_pages_paginees_et_cache(db):
    """load_data public (cache LRU) : la clé tient compte des épingles."""
    sans = _ids(db.load_data(None, None, 3, 0))
    avec = _ids(db.load_data(None, None, 3, 0, 0, 'ASC', False, ids_epingles=[3]))
    assert avec[0] == 3
    assert _ids(db.load_data(None, None, 3, 0)) == sans


def test_export_ignore_les_epingles(db):
    """L'export n'en reçoit jamais : la ligne épinglée est montrée, pas exportée."""
    conditions, _ = db._build_load_conditions(None, {2: 'A694645.00'}, False)
    assert 'a.id IN' not in ' '.join(conditions)


def test_position_sql_suit_l_ordre_affiche(db):
    """Saut ▲/▼ : la position calculée en SQL désigne la ligne des pages."""
    lignes = _pages(db, filtres={1: 'bosch'}, tri=2, sens='ASC', epingles=[6])
    incompletes_attendues = [i for i, id_ in enumerate(lignes) if id_ in (3, 6)]
    pos = db.find_incomplete_position(None, {1: 'bosch'}, 2, 'ASC', False, -1, 'down', ids_epingles=[6])
    assert pos == incompletes_attendues[0] == 0
    suivante = db.find_incomplete_position(None, {1: 'bosch'}, 2, 'ASC', False, pos, 'down', ids_epingles=[6])
    assert suivante == incompletes_attendues[1]


# ── Durée de l'épinglage (contrôleur) ────────────────────────────────────────

def _controleur(ids, contexte):
    return SimpleNamespace(_ids_epingles=list(ids), _contexte_epinglage=contexte,
                           _contexte_affichage=TableController._contexte_affichage)


def test_epingles_gardes_si_meme_recherche():
    ctx = TableController._contexte_affichage('JOINT01', {2: 'HBA'}, False)
    c = _controleur([6], ctx)
    assert TableController._ids_epingles_pour(c, ' JOINT01 ', {2: 'HBA'}, False) == [6]


@pytest.mark.parametrize('terme,filtres,incompletes', [
    ('AUTRE', {2: 'HBA'}, False),
    ('JOINT01', {2: 'HB'}, False),
    ('JOINT01', {}, False),
    ('JOINT01', {2: 'HBA'}, True),
])
def test_epingles_oublies_si_la_recherche_change(terme, filtres, incompletes):
    ctx = TableController._contexte_affichage('JOINT01', {2: 'HBA'}, False)
    c = _controleur([6], ctx)
    assert TableController._ids_epingles_pour(c, terme, filtres, incompletes) == []
    assert c._ids_epingles == [] and c._contexte_epinglage is None
