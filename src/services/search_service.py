"""
Search Service - Phase 4 Architecture Refactoring
Sépare la logique de recherche de l'interface utilisateur
"""

from typing import List, Optional, Dict, Any, Tuple
from ..data.database_manager import DatabaseManager
from .event_bus import event_bus


class SearchService:
    """Service dédié aux opérations de recherche"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._current_search = None
        self._last_results = []
    
    def search(self, term: str, 
               column_filters: Optional[Dict[int, str]] = None,
               sort_column: Optional[int] = None,
               sort_order: Optional[str] = None,
               limit: Optional[int] = None,
               offset: Optional[int] = None,
               incomplete_filter: bool = False) -> List[Tuple]:
        """Effectuer une recherche optimisée"""
        
        # Normaliser le terme pour éviter les objets complexes dans le cache
        normalized_term = self._normalize_search_term(term)
        
        # Convertir terme complexe en string pour l'affichage
        display_term = normalized_term if isinstance(normalized_term, str) else str(normalized_term)
        if isinstance(term, dict):
            display_term = term.get('original', str(term)[:50] + '...')
        
        # Émettre événement de début de recherche
        event_bus.emit('search.started', {
            'term': display_term,
            'has_filters': bool(column_filters),
            'has_sort': sort_column is not None
        })
        
        try:
            # Utiliser le terme original pour la DB, qui sait traiter les objets complexes
            results = self.db_manager.load_data(
                search_term=term,
                column_filters=column_filters,
                limit=limit,
                offset=offset,
                sort_column=sort_column,
                sort_order=sort_order,
                incomplete_filter=incomplete_filter
            )
            
            self._current_search = term
            self._last_results = results
            
            # Émettre événement de fin de recherche
            event_bus.emit('search.completed', {
                'term': term,
                'results_count': len(results),
                'has_cache_hit': '🎯 CACHE HIT' in str(results) if results else False
            })
            
            return results
            
        except Exception as e:
            event_bus.emit('search.error', {
                'term': term,
                'error': str(e)
            })
            raise
    
    def count_results(self, term: str,
                     column_filters: Optional[Dict[int, str]] = None,
                     incomplete_filter: bool = False) -> int:
        """Compter les résultats de recherche sans les charger"""
        return self.db_manager.count_data(
            search_term=term,
            column_filters=column_filters,
            incomplete_filter=incomplete_filter
        )
    
    def get_suggestions(self, term: str, limit: int = 10) -> List[str]:
        """Obtenir des suggestions de recherche (références similaires)"""
        if len(term) < 2:
            return []
        
        try:
            # Rechercher dans les références existantes
            query = """
                SELECT DISTINCT ref_modele FROM appareils 
                WHERE ref_modele LIKE ? AND ref_modele != ''
                UNION
                SELECT DISTINCT commercial_ref FROM appareils 
                WHERE commercial_ref LIKE ? AND commercial_ref != ''
                UNION  
                SELECT DISTINCT ref_piece FROM pieces 
                WHERE ref_piece LIKE ? AND ref_piece != ''
                ORDER BY 1
                LIMIT ?
            """
            
            like_term = f"{term}%"
            results = self.db_manager.execute_query(
                query, [like_term, like_term, like_term, limit]
            )
            
            return [row[0] for row in results]
            
        except Exception as e:
            print(f"⚠️ Erreur suggestions: {e}")
            return []
    
    def parse_advanced_search(self, text: str) -> Optional[Dict[str, Any]]:
        """Parser une recherche avancée (regex, opérateurs OR, etc.)"""
        if not text or not text.strip():
            return None
            
        text = text.strip()
        
        # Regex pattern
        if text.startswith('/') and text.endswith('/') and len(text) > 2:
            pattern = text[1:-1]  # Enlever les /
            return {
                'type': 'regex',
                'pattern': pattern,
                'original': text
            }
        
        # OR groups (support both ' OR ' and '||' separators)
        if ' OR ' in text.upper() or '||' in text:
            groups = []
            if '||' in text:
                # Split by || first
                or_parts = [part.strip() for part in text.split('||')]
            else:
                # Split by OR
                or_parts = [part.strip() for part in text.upper().split(' OR ')]
            
            for part in or_parts:
                if ' AND ' in part.upper() or '&&' in part:
                    # Groupe AND (support both ' AND ' and '&&')
                    if '&&' in part:
                        and_terms = [term.strip() for term in part.split('&&')]
                    else:
                        and_terms = [term.strip() for term in part.split(' AND ')]
                    groups.append({
                        'type': 'and',
                        'terms': and_terms
                    })
                else:
                    # Terme simple
                    groups.append({
                        'type': 'simple',
                        'terms': [part]
                    })
            
            return {
                'type': 'or',
                'groups': groups,
                'original': text
            }
        
        # Simple search
        return {
            'type': 'simple',
            'terms': [text],
            'original': text
        }
    
    def get_current_search(self) -> Optional[str]:
        """Obtenir la recherche courante"""
        return self._current_search
    
    def get_last_results_count(self) -> int:
        """Obtenir le nombre de résultats de la dernière recherche"""
        return len(self._last_results)
    
    def clear_cache(self) -> None:
        """Vider le cache de recherche"""
        if hasattr(self.db_manager, 'search_cache') and self.db_manager.search_cache:
            self.db_manager.search_cache.clear()
            event_bus.emit('search.cache_cleared', None)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques du cache"""
        if hasattr(self.db_manager, 'search_cache') and self.db_manager.search_cache:
            return self.db_manager.search_cache.get_stats()
        return {'enabled': False}
    
    def _normalize_search_term(self, term):
        """Normaliser le terme de recherche pour le cache et la DB"""
        if isinstance(term, str):
            return term
        elif isinstance(term, dict):
            # Pour les recherches complexes, utiliser le terme original pour le cache
            if 'original' in term:
                return term['original']
            elif 'terms' in term and isinstance(term['terms'], list):
                # Pour les groupes OR/AND, joindre les termes
                return ' '.join(term['terms'])
            else:
                # Fallback pour autres structures
                return str(term).replace('{', '').replace('}', '').replace("'", '')[:50]
        else:
            # Pour tout autre type, convertir en string simple
            return str(term)
    
    def extract_first_term(self, search_text: str) -> str:
        """
        Extraire le premier terme d'une recherche (avant || ou &&)
        
        Args:
            search_text: Texte de recherche à analyser
            
        Returns:
            str: Premier terme extrait
        """
        if not search_text:
            return ""
        
        # Séparer par || d'abord, puis par &&
        for separator in ['||', '&&']:
            if separator in search_text:
                return search_text.split(separator)[0].strip()
        
        # Si pas d'opérateur, retourner tel quel
        return search_text.strip()