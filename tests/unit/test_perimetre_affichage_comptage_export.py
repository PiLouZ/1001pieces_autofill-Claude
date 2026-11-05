"""
Un seul périmètre pour l'affichage, le comptage et l'export

`_load_data_original` (les pages), `_count_data_core` (« N résultats ») et
`get_export_data` (CSV, HTML Marques / Détails) recopiaient chacun le calcul des
conditions WHERE. Ils passent désormais tous par `_build_load_conditions` ; ces
tests vérifient qu'ils désignent toujours les mêmes appareils, quels que soient la
recherche et les filtres.
"""

import os
import tempfile

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.services.search_service import SearchService


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
             (5, 'Hotte', 'Elica', 'EL9', 'C5')])
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


TERMES = ['JOINT01', 'MOTEUR77', 'MOT', 'JOINT01 || MOTEUR77', 'MOTEUR77 && EL', 'INCONNU']
FILTRES = [({}, False), ({1: 'bosch'}, False), ({0: 'four'}, False), ({}, True)]


@pytest.mark.parametrize('terme', TERMES)
@pytest.mark.parametrize('filtres,incompletes', FILTRES)
def test_affichage_comptage_et_export_designent_les_memes_appareils(db, terme, filtres, incompletes):
    recherche = SearchService(db).parse_advanced_search(terme) or terme
    pages = db._load_data_original(recherche, filtres or None, None, None, None, None, incompletes)
    total = db.count_data(recherche, filtres or None, incomplete_filter=incompletes)
    export = db.get_export_data(recherche, column_filters=filtres or None,
                                incomplete_filter=incompletes)

    assert total == len(pages)
    assert {tuple(r[1:6]) for r in pages} == {tuple(r[:5]) for r in export}


def test_le_perimetre_n_est_pas_trivial(db):
    # Garde-fou du test ci-dessus : les cas couvrent des résultats non vides,
    # filtrés différemment, et pas seulement « tout » ou « rien ».
    recherche = SearchService(db).parse_advanced_search('MOTEUR77') or 'MOTEUR77'
    assert db.count_data(recherche) == 3
    assert db.count_data(recherche, {1: 'siemens'}) == 1
    assert db.count_data(recherche, incomplete_filter=True) == 1


def test_terme_brut_avec_operateur_decoupe_par_l_export(db):
    # Seule différence voulue : l'export découpe lui-même un terme brut « a || b »
    # (le tableau reçoit toujours un terme déjà analysé).
    assert len(db.get_export_data('JOINT01 || MOTEUR77')) == 5
