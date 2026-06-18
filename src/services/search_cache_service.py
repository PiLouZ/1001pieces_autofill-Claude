"""
Service de gestion du cache de recherche - Phase 2.3+
Gère l'invalidation intelligente du cache lors des modifications de données
"""

from typing import Set, List, Optional, Callable, Dict, Any
from ..core.logger import app_logger
from ..core.config import Config
from ..utils.error_handler import handle_cache_callback_errors

class SearchCacheInvalidationService:
    """Service d'invalidation intelligente du cache de recherche"""
    
    def __init__(self, database_manager):
        self.db_manager = database_manager

        # Callbacks à notifier lors d'invalidation
        self.invalidation_callbacks: List[Callable] = []

        # OPTIMISATION: Suspension des invalidations pendant imports
        self.invalidation_suspended = False
        self.pending_invalidation_reason = None

        # Statistiques d'invalidation
        self.invalidation_stats = {
            'total_invalidations': 0,
            'import_invalidations': 0,
            'piece_modification_invalidations': 0,
            'device_modification_invalidations': 0,
            'manual_invalidations': 0,
            'suspended_invalidations': 0
        }
    
    def register_invalidation_callback(self, callback: Callable):
        """Enregistrer un callback à appeler lors d'invalidation"""
        self.invalidation_callbacks.append(callback)

    @handle_cache_callback_errors()
    def _safe_call_invalidation_callback(self, callback: Callable, reason: str) -> None:
        """Appeler un callback d'invalidation de manière sécurisée"""
        callback(reason)

    def suspend_invalidation(self, reason: str = "import en cours"):
        """Suspendre temporairement les invalidations de cache (utile pendant les imports)"""
        self.invalidation_suspended = True
        self.pending_invalidation_reason = reason

    def resume_invalidation(self, force_invalidate: bool = True):
        """Reprendre les invalidations et optionnellement invalider le cache"""
        was_suspended = self.invalidation_suspended
        self.invalidation_suspended = False

        if was_suspended and force_invalidate:
            reason = self.pending_invalidation_reason or "reprise après suspension"
            self.invalidate_search_cache(f"reprise après {reason}")

        self.pending_invalidation_reason = None
    
    def invalidate_search_cache(self, reason: str = "modification"):
        """Invalider complètement le cache de recherche"""
        # OPTIMISATION: Vérifier si les invalidations sont suspendues
        if self.invalidation_suspended:
            self.invalidation_stats['suspended_invalidations'] += 1
            return 0

        if hasattr(self.db_manager, 'search_cache') and self.db_manager.search_cache:
            old_size = len(self.db_manager.search_cache.cache)
            self.db_manager.search_cache.cache.clear()

            self.invalidation_stats['total_invalidations'] += 1

            app_logger.info(f" Cache de recherche invalidé: {reason} ({old_size} entrées supprimées)")

            # Notifier les callbacks
            for callback in self.invalidation_callbacks:
                self._safe_call_invalidation_callback(callback, reason)

            return old_size
        return 0
    
    def invalidate_after_import(self, import_results: Dict[str, Any]):
        """Invalidation après import de données"""
        if import_results.get('associations_created', 0) > 0 or import_results.get('new_entries', 0) > 0:
            self.invalidation_stats['import_invalidations'] += 1
            entries_cleared = self.invalidate_search_cache("import de données")
            
            app_logger.info(f" Cache invalidé après import: {import_results.get('associations_created', 0)} associations, "
                          f"{import_results.get('new_entries', 0)} nouveaux appareils")
            return entries_cleared
        return 0
    
    def invalidate_after_piece_modification(self, operation: str, piece_ref: str, device_count: int = 1):
        """Invalidation après modification de pièces"""
        self.invalidation_stats['piece_modification_invalidations'] += 1
        entries_cleared = self.invalidate_search_cache(f"{operation} pièce: {piece_ref}")

        # Ne logger que si l'invalidation a réellement eu lieu
        if entries_cleared > 0:
            app_logger.info(f" Cache invalidé après {operation} pièce '{piece_ref}' ({device_count} appareils affectés)")

        return entries_cleared
    
    def invalidate_after_device_modification(self, operation: str, device_count: int = 1):
        """Invalidation après modification d'appareils"""
        self.invalidation_stats['device_modification_invalidations'] += 1
        entries_cleared = self.invalidate_search_cache(f"{operation} appareil(s)")

        # Ne logger que si l'invalidation a réellement eu lieu
        if entries_cleared > 0:
            app_logger.info(f" Cache invalidé après {operation} de {device_count} appareil(s)")

        return entries_cleared
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Obtenir statistiques du cache et invalidations"""
        cache_stats = {
            'cache_enabled': hasattr(self.db_manager, 'search_cache') and self.db_manager.search_cache is not None,
            'cache_size': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'cache_max_size': 0
        }
        
        if hasattr(self.db_manager, 'search_cache') and self.db_manager.search_cache:
            cache = self.db_manager.search_cache
            cache_stats.update({
                'cache_size': len(cache.cache),
                'cache_hits': getattr(cache, 'hits', 0),
                'cache_misses': getattr(cache, 'misses', 0),
                'cache_max_size': getattr(cache, 'max_size', 0)
            })
        
        return {
            'cache': cache_stats,
            'invalidations': self.invalidation_stats.copy()
        }