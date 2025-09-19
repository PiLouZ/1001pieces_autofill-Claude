"""
Service de gestion du cache de recherche - Phase 2.3+
Gère l'invalidation intelligente du cache lors des modifications de données
"""

from typing import Set, List, Optional, Callable, Dict, Any
from ..core.logger import app_logger
from ..core.config import Config


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

            app_logger.info(f"🗑️ Cache de recherche invalidé: {reason} ({old_size} entrées supprimées)")

            # Notifier les callbacks
            for callback in self.invalidation_callbacks:
                try:
                    callback(reason)
                except Exception as e:
                    app_logger.error(f"Erreur callback invalidation {callback.__name__}: {e}")

            return old_size
        return 0
    
    def invalidate_after_import(self, import_results: Dict[str, Any]):
        """Invalidation après import de données"""
        if import_results.get('associations_created', 0) > 0 or import_results.get('new_entries', 0) > 0:
            self.invalidation_stats['import_invalidations'] += 1
            entries_cleared = self.invalidate_search_cache("import de données")
            
            app_logger.info(f"📥 Cache invalidé après import: {import_results.get('associations_created', 0)} associations, "
                          f"{import_results.get('new_entries', 0)} nouveaux appareils")
            return entries_cleared
        return 0
    
    def invalidate_after_piece_modification(self, operation: str, piece_ref: str, device_count: int = 1):
        """Invalidation après modification de pièces"""
        self.invalidation_stats['piece_modification_invalidations'] += 1
        entries_cleared = self.invalidate_search_cache(f"{operation} pièce: {piece_ref}")

        # Ne logger que si l'invalidation a réellement eu lieu
        if entries_cleared > 0:
            app_logger.info(f"🔧 Cache invalidé après {operation} pièce '{piece_ref}' ({device_count} appareils affectés)")

        return entries_cleared
    
    def invalidate_after_device_modification(self, operation: str, device_count: int = 1):
        """Invalidation après modification d'appareils"""
        self.invalidation_stats['device_modification_invalidations'] += 1
        entries_cleared = self.invalidate_search_cache(f"{operation} appareil(s)")

        # Ne logger que si l'invalidation a réellement eu lieu
        if entries_cleared > 0:
            app_logger.info(f"📱 Cache invalidé après {operation} de {device_count} appareil(s)")

        return entries_cleared
    
    def invalidate_manual(self, reason: str = "manuel"):
        """Invalidation manuelle par l'utilisateur"""
        self.invalidation_stats['manual_invalidations'] += 1
        entries_cleared = self.invalidate_search_cache(f"invalidation {reason}")
        
        app_logger.info(f"👤 Cache invalidé manuellement: {reason}")
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
    
    def should_invalidate_for_search_term(self, search_term: str) -> bool:
        """Déterminer si le cache doit être invalidé pour un terme spécifique"""
        # Pour l'instant, invalidation globale uniquement
        # Future amélioration: invalidation sélective par terme
        return False
    
    def optimize_cache_settings(self) -> Dict[str, Any]:
        """Optimiser automatiquement les paramètres de cache"""
        if not hasattr(self.db_manager, 'search_cache') or not self.db_manager.search_cache:
            return {'status': 'cache_disabled'}
        
        cache = self.db_manager.search_cache
        stats = self.get_cache_statistics()
        
        # Calculer hit rate
        total_requests = stats['cache']['cache_hits'] + stats['cache']['cache_misses']
        hit_rate = stats['cache']['cache_hits'] / total_requests if total_requests > 0 else 0
        
        recommendations = []
        
        if hit_rate < 0.3:  # Moins de 30% hit rate
            recommendations.append("Cache peu efficace - considérer augmenter la taille")
        elif hit_rate > 0.8:  # Plus de 80% hit rate
            recommendations.append("Cache très efficace - taille optimale")
        
        if stats['invalidations']['total_invalidations'] > 100:
            recommendations.append("Beaucoup d'invalidations - données fréquemment modifiées")
        
        return {
            'status': 'analyzed',
            'hit_rate': hit_rate,
            'recommendations': recommendations,
            'stats': stats
        }
    
    def create_cache_report(self) -> str:
        """Créer rapport complet du cache pour debugging"""
        stats = self.get_cache_statistics()
        
        report = "=== RAPPORT CACHE DE RECHERCHE ===\n"
        report += f"État: {'Activé' if stats['cache']['cache_enabled'] else 'Désactivé'}\n"
        
        if stats['cache']['cache_enabled']:
            report += f"Taille actuelle: {stats['cache']['cache_size']}/{stats['cache']['cache_max_size']}\n"
            report += f"Hits: {stats['cache']['cache_hits']}\n"
            report += f"Misses: {stats['cache']['cache_misses']}\n"
            
            total = stats['cache']['cache_hits'] + stats['cache']['cache_misses']
            if total > 0:
                hit_rate = stats['cache']['cache_hits'] / total * 100
                report += f"Taux de réussite: {hit_rate:.1f}%\n"
            
            report += "\n=== INVALIDATIONS ===\n"
            inv_stats = stats['invalidations']
            report += f"Total: {inv_stats['total_invalidations']}\n"
            report += f"Imports: {inv_stats['import_invalidations']}\n"
            report += f"Modifications pièces: {inv_stats['piece_modification_invalidations']}\n"
            report += f"Modifications appareils: {inv_stats['device_modification_invalidations']}\n"
            report += f"Manuelles: {inv_stats['manual_invalidations']}\n"
        
        return report