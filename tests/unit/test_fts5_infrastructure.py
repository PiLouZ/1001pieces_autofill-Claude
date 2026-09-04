"""
Tests — L'infrastructure FTS5 n'existe que si elle sert

L'index FTS5 couvre les colonnes d'appareils. Quand `Config.SEARCH_PIECES_ONLY`
vaut `True` — la configuration de production — la recherche porte sur
`pieces.ref_piece` et l'index est **inatteignable** : il l'a d'ailleurs toujours
été, la garde existant dès le commit qui l'a introduit (v3.18.0, 2026-03-11,
deux jours après le passage à SEARCH_PIECES_ONLY).

Le maintenir coûtait ~20 % du poids de la base et des écritures ~6,7× plus
lentes, les trois triggers se déclenchant à chaque import. Il est désormais créé
seulement s'il peut servir, et retiré sinon — « Construire l'index » du menu le
recrée intégralement le jour où le drapeau repasse à False.
"""

import pytest

from src.core.config import Config


def _objets_fts5(db):
    """Tables et triggers FTS5 présents dans la base."""
    lignes = db.execute_query(
        "SELECT name FROM sqlite_master "
        "WHERE name LIKE 'appareils_fts%' OR name LIKE '%_fts_a%'"
    ) or []
    return {l[0] for l in lignes}


class TestPredicatPartage:
    """La règle « FTS5 utilisable » ne doit exister qu'à un seul endroit."""

    def test_inutilisable_en_mode_pieces_only(self, test_db_manager):
        origine = Config.SEARCH_PIECES_ONLY, Config.USE_FTS5
        try:
            Config.SEARCH_PIECES_ONLY, Config.USE_FTS5 = True, True
            assert test_db_manager.fts5_utilisable() is False
        finally:
            Config.SEARCH_PIECES_ONLY, Config.USE_FTS5 = origine

    def test_inutilisable_si_desactive(self, test_db_manager):
        origine = Config.SEARCH_PIECES_ONLY, Config.USE_FTS5
        try:
            Config.SEARCH_PIECES_ONLY, Config.USE_FTS5 = False, False
            assert test_db_manager.fts5_utilisable() is False
        finally:
            Config.SEARCH_PIECES_ONLY, Config.USE_FTS5 = origine

    def test_utilisable_uniquement_si_actif_et_hors_pieces_only(self, test_db_manager):
        origine = Config.SEARCH_PIECES_ONLY, Config.USE_FTS5
        try:
            Config.SEARCH_PIECES_ONLY, Config.USE_FTS5 = False, True
            assert test_db_manager.fts5_utilisable() is True
        finally:
            Config.SEARCH_PIECES_ONLY, Config.USE_FTS5 = origine


class TestSynchronisation:
    """L'infrastructure suit ce que la configuration permet."""

    def test_creee_quand_utilisable(self, test_db_manager):
        """La fixture tourne avec SEARCH_PIECES_ONLY=False : l'index existe."""
        assert Config.SEARCH_PIECES_ONLY is False, "prérequis de la fixture"
        test_db_manager._synchroniser_infrastructure_fts5()
        objets = _objets_fts5(test_db_manager)
        assert 'appareils_fts' in objets
        assert {'appareils_fts_ai', 'appareils_fts_ad', 'appareils_fts_au'} <= objets

    def test_retiree_quand_inutilisable(self, test_db_manager):
        test_db_manager._synchroniser_infrastructure_fts5()
        assert 'appareils_fts' in _objets_fts5(test_db_manager)

        origine = Config.SEARCH_PIECES_ONLY
        try:
            Config.SEARCH_PIECES_ONLY = True
            test_db_manager._synchroniser_infrastructure_fts5()
        finally:
            Config.SEARCH_PIECES_ONLY = origine

        objets = _objets_fts5(test_db_manager)
        assert 'appareils_fts' not in objets
        assert not {'appareils_fts_ai', 'appareils_fts_ad', 'appareils_fts_au'} & objets

    def test_suppression_idempotente(self, test_db_manager):
        """Retirer une infrastructure déjà absente ne doit pas échouer."""
        test_db_manager._supprimer_infrastructure_fts5()
        test_db_manager._supprimer_infrastructure_fts5()
        assert 'appareils_fts' not in _objets_fts5(test_db_manager)


class TestReconstruction:
    """« Construire l'index » doit repartir de zéro, même après suppression."""

    def test_rebuild_recree_l_infrastructure_absente(self, test_db_manager):
        test_db_manager.insert_appareil({'type': 'Aspirateur', 'manufacturer': 'Samsung',
                                         'ref_modele': 'SC4520'})
        test_db_manager._supprimer_infrastructure_fts5()
        assert 'appareils_fts' not in _objets_fts5(test_db_manager)

        indexes = test_db_manager.rebuild_fts5()

        assert 'appareils_fts' in _objets_fts5(test_db_manager)
        assert indexes >= 1
        assert test_db_manager.is_fts5_populated() is True

    def test_statut_lisible_sans_infrastructure(self, test_db_manager):
        """Le menu interroge l'index : sans table, il doit lire « non construit »."""
        test_db_manager._supprimer_infrastructure_fts5()
        assert test_db_manager.get_fts5_row_count() == 0
        assert test_db_manager.is_fts5_populated() is False


class TestEcritures:
    """Sans triggers, les écritures ne paient plus l'indexation."""

    def test_insertion_possible_sans_infrastructure(self, test_db_manager):
        test_db_manager._supprimer_infrastructure_fts5()
        device_id = test_db_manager.insert_appareil(
            {'type': 'Four', 'manufacturer': 'Bosch', 'ref_modele': 'HBA0001'})
        assert device_id
        lignes = test_db_manager.execute_query(
            "SELECT ref_modele FROM appareils WHERE id = ?", [device_id])
        assert lignes[0][0] == 'HBA0001'
