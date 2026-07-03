"""
Tests pour EmptyCellNavigationService : saut vers la prochaine/précédente
cellule vide (Type/Fabricant) depuis une ligne donnée.
"""

import pytest

from src.services.empty_cell_navigation_service import EmptyCellNavigationService


@pytest.fixture
def nav_service(test_db_manager):
    return EmptyCellNavigationService(test_db_manager, parent_window=None)


def _insert(db_manager, ref_modele, type_='', manufacturer=''):
    return db_manager.insert_appareil({
        'ref_modele': ref_modele, 'commercial_ref': '',
        'type': type_, 'manufacturer': manufacturer,
        'other_ref': '', 'notes': '', 'category': '',
    })


class TestEmptyCellNavigationService:
    def test_find_next_down_type_vide(self, nav_service, test_db_manager):
        id1 = _insert(test_db_manager, 'A', type_='Four', manufacturer='Bosch')
        id2 = _insert(test_db_manager, 'B', type_='', manufacturer='Bosch')
        id3 = _insert(test_db_manager, 'C', type_='Lave-linge', manufacturer='Bosch')

        found = nav_service.find_next_empty('type', id1, direction='down')
        assert found is not None
        assert found[0] == id2
        assert found[1] == 'B'

    def test_find_next_up(self, nav_service, test_db_manager):
        id1 = _insert(test_db_manager, 'A', type_='', manufacturer='Bosch')
        id2 = _insert(test_db_manager, 'B', type_='Four', manufacturer='Bosch')
        id3 = _insert(test_db_manager, 'C', type_='', manufacturer='Bosch')

        found = nav_service.find_next_empty('type', id2, direction='up')
        assert found is not None
        assert found[0] == id1

    def test_aucune_cellule_vide_retourne_none(self, nav_service, test_db_manager):
        id1 = _insert(test_db_manager, 'A', type_='Four', manufacturer='Bosch')
        id2 = _insert(test_db_manager, 'B', type_='Lave-linge', manufacturer='Whirlpool')

        assert nav_service.find_next_empty('type', id1, direction='down') is None

    def test_manufacturer_vide_independant_de_type(self, nav_service, test_db_manager):
        """Une ligne avec type rempli mais manufacturer vide ne doit remonter
        que pour la colonne manufacturer, pas pour type."""
        id1 = _insert(test_db_manager, 'A', type_='Four', manufacturer='Bosch')
        id2 = _insert(test_db_manager, 'B', type_='Lave-linge', manufacturer='')

        assert nav_service.find_next_empty('type', id1, direction='down') is None
        found = nav_service.find_next_empty('manufacturer', id1, direction='down')
        assert found is not None
        assert found[0] == id2

    def test_ligne_avec_suggestion_en_attente_reste_vide(self, nav_service, test_db_manager):
        """Une ligne avec suggestion en attente a nécessairement type/manufacturer
        vides en base (les suggestions ne sont calculées que pour les lignes
        restées incomplètes) : elle doit donc être trouvée, sans logique dédiée."""
        id1 = _insert(test_db_manager, 'A', type_='Four', manufacturer='Bosch')
        id2 = _insert(test_db_manager, 'B/58', type_='', manufacturer='')  # aurait une suggestion en attente côté UI

        found = nav_service.find_next_empty('type', id1, direction='down')
        assert found is not None
        assert found[0] == id2

    def test_colonne_invalide_retourne_none(self, nav_service, test_db_manager):
        id1 = _insert(test_db_manager, 'A', type_='', manufacturer='')
        assert nav_service.find_next_empty('ref_modele', id1, direction='down') is None
        assert nav_service.find_next_empty('type', id1, direction='sideways') is None
