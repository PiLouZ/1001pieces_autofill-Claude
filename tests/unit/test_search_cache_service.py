"""
Tests essentiels pour SearchCacheService
Focus sur l'invalidation du cache et la performance
"""

import pytest
from unittest.mock import Mock, MagicMock

from src.services.search_cache_service import SearchCacheInvalidationService


@pytest.mark.unit
@pytest.mark.critical
class TestSearchCacheService:
    """Tests critiques pour SearchCacheInvalidationService"""

    @pytest.fixture
    def mock_db_manager_with_cache(self):
        """Fixture DatabaseManager avec cache mockée"""
        db_manager = Mock()

        # Mock du cache de recherche
        mock_cache = Mock()
        mock_cache.cache = {'key1': 'value1', 'key2': 'value2'}

        db_manager.search_cache = mock_cache
        return db_manager

    @pytest.fixture
    def mock_db_manager_without_cache(self):
        """Fixture DatabaseManager sans cache"""
        db_manager = Mock()
        db_manager.search_cache = None
        return db_manager

    @pytest.fixture
    def cache_service(self, mock_db_manager_with_cache):
        """Fixture service de cache"""
        return SearchCacheInvalidationService(mock_db_manager_with_cache)

    def test_service_initialization(self, cache_service, mock_db_manager_with_cache):
        """Test initialisation du service"""
        assert cache_service.db_manager == mock_db_manager_with_cache
        assert cache_service.invalidation_callbacks == []
        assert not cache_service.invalidation_suspended
        assert cache_service.pending_invalidation_reason is None
        assert isinstance(cache_service.invalidation_stats, dict)

    def test_register_invalidation_callback(self, cache_service):
        """Test enregistrement de callback"""
        callback = Mock()
        callback.__name__ = "test_callback"

        cache_service.register_invalidation_callback(callback)

        assert callback in cache_service.invalidation_callbacks
        assert len(cache_service.invalidation_callbacks) == 1

    def test_invalidate_search_cache_success(self, cache_service):
        """Test invalidation réussie du cache"""
        # État initial
        initial_size = len(cache_service.db_manager.search_cache.cache)
        assert initial_size == 2

        # Invalider le cache
        cleared_entries = cache_service.invalidate_search_cache("test reason")

        # Vérifications
        assert cleared_entries == initial_size
        cache_service.db_manager.search_cache.cache.clear.assert_called_once()
        assert cache_service.invalidation_stats['total_invalidations'] == 1

    def test_invalidate_search_cache_with_callbacks(self, cache_service):
        """Test invalidation avec callbacks"""
        # Enregistrer des callbacks
        callback1 = Mock()
        callback2 = Mock()
        callback1.__name__ = "callback1"
        callback2.__name__ = "callback2"

        cache_service.register_invalidation_callback(callback1)
        cache_service.register_invalidation_callback(callback2)

        # Invalider le cache
        cache_service.invalidate_search_cache("test with callbacks")

        # Vérifier que les callbacks ont été appelés
        callback1.assert_called_once_with("test with callbacks")
        callback2.assert_called_once_with("test with callbacks")

    def test_invalidate_search_cache_callback_error(self, cache_service):
        """Test gestion d'erreur dans callback"""
        # Callback qui lève une exception
        failing_callback = Mock(side_effect=Exception("Callback error"))
        failing_callback.__name__ = "failing_callback"

        # Callback normal
        normal_callback = Mock()
        normal_callback.__name__ = "normal_callback"

        cache_service.register_invalidation_callback(failing_callback)
        cache_service.register_invalidation_callback(normal_callback)

        # Invalider le cache - ne doit pas planter
        cleared_entries = cache_service.invalidate_search_cache("test error handling")

        # Vérifier que l'invalidation a quand même fonctionné
        assert cleared_entries == 2
        # Le callback normal doit avoir été appelé
        normal_callback.assert_called_once_with("test error handling")

    def test_suspend_and_resume_invalidation(self, cache_service):
        """Test suspension et reprise des invalidations"""
        # Suspendre
        cache_service.suspend_invalidation("test suspension")

        assert cache_service.invalidation_suspended
        assert cache_service.pending_invalidation_reason == "test suspension"

        # Invalider pendant suspension - doit être ignoré
        cleared_entries = cache_service.invalidate_search_cache("ignored invalidation")

        assert cleared_entries == 0
        assert cache_service.invalidation_stats['suspended_invalidations'] == 1
        assert cache_service.invalidation_stats['total_invalidations'] == 0

        # Reprendre avec invalidation forcée
        cache_service.resume_invalidation(force_invalidate=True)

        assert not cache_service.invalidation_suspended
        assert cache_service.pending_invalidation_reason is None
        assert cache_service.invalidation_stats['total_invalidations'] == 1

    def test_resume_invalidation_without_force(self, cache_service):
        """Test reprise sans invalidation forcée"""
        # Suspendre
        cache_service.suspend_invalidation("test")

        # Reprendre sans forcer l'invalidation
        cache_service.resume_invalidation(force_invalidate=False)

        assert not cache_service.invalidation_suspended
        assert cache_service.invalidation_stats['total_invalidations'] == 0

    def test_invalidate_after_import(self, cache_service):
        """Test invalidation après import"""
        import_results = {
            'associations_created': 5,
            'new_entries': 3
        }

        cleared_entries = cache_service.invalidate_after_import(import_results)

        assert cleared_entries == 2  # Taille du cache mock
        assert cache_service.invalidation_stats['import_invalidations'] == 1
        assert cache_service.invalidation_stats['total_invalidations'] == 1

    def test_invalidate_after_import_no_changes(self, cache_service):
        """Test pas d'invalidation après import sans changements"""
        import_results = {
            'associations_created': 0,
            'new_entries': 0
        }

        cleared_entries = cache_service.invalidate_after_import(import_results)

        assert cleared_entries == 0
        assert cache_service.invalidation_stats['import_invalidations'] == 0
        assert cache_service.invalidation_stats['total_invalidations'] == 0

    def test_invalidate_after_piece_modification(self, cache_service):
        """Test invalidation après modification de pièce"""
        cleared_entries = cache_service.invalidate_after_piece_modification(
            "ajout", "PIECE-001", 1
        )

        assert cleared_entries == 2
        assert cache_service.invalidation_stats['piece_modification_invalidations'] == 1
        assert cache_service.invalidation_stats['total_invalidations'] == 1

    def test_invalidate_after_device_modification(self, cache_service):
        """Test invalidation après modification d'appareil"""
        cleared_entries = cache_service.invalidate_after_device_modification(
            "modification", 3
        )

        assert cleared_entries == 2
        assert cache_service.invalidation_stats['device_modification_invalidations'] == 1
        assert cache_service.invalidation_stats['total_invalidations'] == 1

    def test_invalidate_without_cache(self):
        """Test invalidation sans cache disponible"""
        # Service avec DB manager sans cache
        db_manager = Mock()
        db_manager.search_cache = None
        service = SearchCacheInvalidationService(db_manager)

        cleared_entries = service.invalidate_search_cache("test no cache")

        assert cleared_entries == 0
        assert service.invalidation_stats['total_invalidations'] == 1

    def test_invalidate_with_cache_without_search_cache_attribute(self):
        """Test invalidation avec DB manager sans attribut search_cache"""
        db_manager = Mock()
        # Pas d'attribut search_cache du tout
        del db_manager.search_cache
        service = SearchCacheInvalidationService(db_manager)

        cleared_entries = service.invalidate_search_cache("test no attribute")

        assert cleared_entries == 0

    def test_invalidation_statistics(self, cache_service):
        """Test des statistiques d'invalidation"""
        # État initial
        stats = cache_service.invalidation_stats
        assert stats['total_invalidations'] == 0
        assert stats['import_invalidations'] == 0
        assert stats['piece_modification_invalidations'] == 0
        assert stats['device_modification_invalidations'] == 0
        assert stats['suspended_invalidations'] == 0

        # Effectuer différents types d'invalidations
        cache_service.invalidate_after_import({'associations_created': 1, 'new_entries': 0})
        cache_service.invalidate_after_piece_modification("ajout", "PIECE-001")
        cache_service.invalidate_after_device_modification("modification", 1)

        # Suspension et invalidation ignorée
        cache_service.suspend_invalidation("test")
        cache_service.invalidate_search_cache("suspended")
        cache_service.resume_invalidation(force_invalidate=False)

        # Vérifier les statistiques
        stats = cache_service.invalidation_stats
        assert stats['total_invalidations'] == 3  # 3 invalidations réussies
        assert stats['import_invalidations'] == 1
        assert stats['piece_modification_invalidations'] == 1
        assert stats['device_modification_invalidations'] == 1
        assert stats['suspended_invalidations'] == 1

    def test_multiple_suspension_resume_cycles(self, cache_service):
        """Test cycles multiples de suspension/reprise"""
        # Premier cycle
        cache_service.suspend_invalidation("cycle 1")
        cache_service.invalidate_search_cache("ignored 1")
        cache_service.resume_invalidation(force_invalidate=True)

        # Deuxième cycle
        cache_service.suspend_invalidation("cycle 2")
        cache_service.invalidate_search_cache("ignored 2")
        cache_service.resume_invalidation(force_invalidate=True)

        # Vérifications
        assert cache_service.invalidation_stats['suspended_invalidations'] == 2
        assert cache_service.invalidation_stats['total_invalidations'] == 2

    def test_edge_case_empty_cache(self, mock_db_manager_without_cache):
        """Test cas limite avec cache vide"""
        # Cache avec dictionnaire vide
        mock_cache = Mock()
        mock_cache.cache = {}
        mock_db_manager_without_cache.search_cache = mock_cache

        service = SearchCacheInvalidationService(mock_db_manager_without_cache)
        cleared_entries = service.invalidate_search_cache("empty cache")

        assert cleared_entries == 0
        mock_cache.cache.clear.assert_called_once()
        assert service.invalidation_stats['total_invalidations'] == 1