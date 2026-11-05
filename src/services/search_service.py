"""
Search Service - Phase 4 Architecture Refactoring
Sépare la logique de recherche de l'interface utilisateur
"""

from typing import Optional, Dict, Any
from ..data.database_manager import DatabaseManager
from .base_service import BaseService

class SearchService(BaseService):
    """Service dédié aux opérations de recherche"""
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
    
    def parse_advanced_search(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parser une recherche avancée (regex, opérateurs OR, AND, etc.)
        
        MÉTHODE CONSOLIDÉE - PRIORITÉ 2 
        Centralise toute la logique de parsing pour éviter duplications
        """
        from ..core.logger import app_logger
        
        if not text or not text.strip():
            return None
            
        try:
            text = text.strip()
            
            # Regex pattern - format /pattern/
            if text.startswith('/') and text.endswith('/') and len(text) > 2:
                pattern = text[1:-1]  # Enlever les /
                return {
                    'type': 'regex',
                    'pattern': pattern,
                    'original': text
                }
            
            # Détecter le type d'opérateur principal (priorité aux ||)
            if '||' in text and '&&' in text:
                # Recherche mixte - traiter || en priorité (comme AdvancedSearchService)
                return self._parse_or_search(text)
            elif '||' in text:
                # Recherche OR uniquement  
                return self._parse_or_search(text)
            elif '&&' in text:
                # Recherche AND uniquement
                return self._parse_and_search(text)
            elif ' OR ' in text.upper():
                # Support legacy ' OR ' (pour compatibilité)
                return self._parse_or_search_legacy(text)
            elif ' AND ' in text.upper():
                # Support legacy ' AND ' (pour compatibilité)
                return self._parse_and_search_legacy(text)
            else:
                # Pas d'opérateur - recherche simple
                return {
                    'type': 'simple',
                    'terms': [text],
                    'original': text
                }
                
        except Exception as e:
            self.handle_error(e, f"parsing recherche avancée '{text}'")
            # Fallback vers recherche simple pour garantir robustesse
            return {
                'type': 'simple',
                'terms': [text],
                'original': text
            }
    
    def _parse_or_search(self, text: str) -> Dict[str, Any]:
        """Parser recherche avec opérateurs OR (||) - Logique d'AdvancedSearchService"""
        # Diviser par || et nettoyer chaque terme
        or_groups = [term.strip() for term in text.split('||') if term.strip()]
        
        parsed_groups = []
        for group in or_groups:
            if '&&' in group:
                # Groupe avec AND interne
                and_terms = [t.strip() for t in group.split('&&') if t.strip()]
                parsed_groups.append({
                    'type': 'and',
                    'terms': and_terms
                })
            else:
                # Terme simple dans le groupe OR
                parsed_groups.append({
                    'type': 'simple',
                    'terms': [group]
                })
        
        return {
            'type': 'or',
            'groups': parsed_groups,
            'original': text
        }
    
    def _parse_and_search(self, text: str) -> Dict[str, Any]:
        """Parser recherche avec opérateurs AND (&&) - Logique d'AdvancedSearchService"""
        # Diviser par && et nettoyer
        and_terms = [term.strip() for term in text.split('&&') if term.strip()]
        
        return {
            'type': 'and', 
            'terms': and_terms,
            'original': text
        }
    
    def _parse_or_search_legacy(self, text: str) -> Dict[str, Any]:
        """Parser recherche legacy avec ' OR ' (pour compatibilité)"""
        or_parts = [part.strip() for part in text.upper().split(' OR ')]
        groups = []
        
        for part in or_parts:
            if ' AND ' in part.upper():
                and_terms = [term.strip() for term in part.split(' AND ')]
                groups.append({
                    'type': 'and',
                    'terms': and_terms
                })
            else:
                groups.append({
                    'type': 'simple',
                    'terms': [part]
                })
        
        return {
            'type': 'or',
            'groups': groups,
            'original': text
        }
    
    def _parse_and_search_legacy(self, text: str) -> Dict[str, Any]:
        """Parser recherche legacy avec ' AND ' (pour compatibilité)"""
        and_terms = [term.strip() for term in text.split(' AND ')]
        
        return {
            'type': 'and', 
            'terms': and_terms,
            'original': text
        }
    
    def format_search_term_for_display(self, search_term) -> str:
        """
        Formater un terme de recherche pour affichage utilisateur
        
        MÉTHODE CONSOLIDÉE PRIORITÉ 2 - Remplace _get_display_term d'AdvancedSearchService
        """
        if isinstance(search_term, dict):
            return search_term.get('original', str(search_term)[:50] + '...')
        return str(search_term) if search_term else ""
    
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
    
    # ==========================================================================
    # LOGIQUE DE DÉTECTION DES PIÈCES - CENTRALISÉE PRIORITÉ 2
    # Déplacée depuis AdvancedSearchService pour éviter dispersement
    # ==========================================================================
    
    def is_piece_reference_search(self, search_term: str) -> bool:
        """Détecter si la recherche concerne une référence de pièce - Vraie logique avec DB"""
        try:
            if not search_term or not search_term.strip():
                return False
            
            # Détecter les recherches multi-références avec || ou &&
            if '||' in search_term or '&&' in search_term:
                return self._are_all_terms_piece_references(search_term)
            
            # Recherche simple - vérifier si c'est une référence de pièce
            return self._get_piece_description_from_reference(search_term) is not None
        
        except Exception as e:
            return self.handle_error_with_return(e, "vérification référence pièce", False)
    
    def _are_all_terms_piece_references(self, search_term: str) -> bool:
        """Vérifier si tous les termes d'une recherche multi-références sont des références de pièce"""
        try:
            # Diviser selon l'opérateur utilisé
            if '||' in search_term:
                terms = [term.strip() for term in search_term.split('||') if term.strip()]
            elif '&&' in search_term:
                terms = [term.strip() for term in search_term.split('&&') if term.strip()]
            else:
                return False
            
            # Au moins un terme doit être une référence de pièce pour les recherches ||
            # Tous les termes doivent être des références de pièce pour les recherches &&
            if '||' in search_term:
                # Pour ||, au moins une référence valide suffit
                return any(self._get_piece_description_from_reference(term) is not None for term in terms)
            else:  # && 
                # Pour &&, toutes les références doivent être valides
                return all(self._get_piece_description_from_reference(term) is not None for term in terms)
                
        except Exception as e:
            return self.handle_error_with_return(e, "vérification multi-références", False)
    
    def _get_piece_description_from_reference(self, reference: str) -> Optional[str]:
        """Récupérer la description d'une pièce depuis sa référence"""
        try:
            # Rechercher la pièce par référence exacte
            result = self.db_manager.lire_libelle_piece(reference)
            
            if result:
                description = result[0][0]
                # Vérifier que la description n'est pas None ou vide
                if description and description.strip():
                    return description.strip()
                else:
                    # Description vide mais référence existe
                    return ""
            
            return None
            
        except Exception as e:
            return self.handle_error_with_return(e, f"récupération description pièce '{reference}'")