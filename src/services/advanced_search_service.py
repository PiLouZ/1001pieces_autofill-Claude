"""
Advanced Search Service - Phase 2.3 Refactoring  
Centralise toute la logique de recherche avancée avec opérateurs && et ||
"""

import re
from typing import Optional, Dict, Any, Callable, List
from PyQt5.QtCore import QTimer, QObject, pyqtSignal
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QColor

from .search_service import SearchService
from ..core.logger import app_logger


class AdvancedSearchService(QObject):
    """Service de recherche avancé avec support opérateurs && et ||, débounce et mise en évidence"""
    
    # Signaux pour communiquer avec l'interface
    search_started = pyqtSignal(str)  # Recherche commencée
    search_completed = pyqtSignal(object, str)  # Résultats, terme
    search_error = pyqtSignal(str)  # Erreur
    export_buttons_update = pyqtSignal(bool)  # État boutons export
    
    def __init__(self, search_service: SearchService, parent=None):
        super().__init__(parent)
        self.search_service = search_service
        
        # Timer pour débounce (500ms)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._execute_search)
        
        # État de recherche
        self.pending_search_term = None
        self.current_search_term = None
        
        # Cache pour éviter les recherches répétées
        self._last_processed_term = None
    
    def search_with_debounce(self, text: str, debounce_ms: int = 500):
        """Lancer une recherche avec débounce (attendre avant d'exécuter)"""
        search_term = text.strip()
        
        # Parser la recherche avancée si opérateurs détectés
        if search_term and ('&&' in search_term or '||' in search_term):
            parsed_search = self.parse_advanced_search(search_term)
            self.pending_search_term = parsed_search
        else:
            # Terme simple - utiliser directement pour éviter problèmes de cache
            self.pending_search_term = search_term
        
        # Émettre signal pour boutons export (basé sur détection référence pièce)
        is_piece_search = self._is_piece_reference_search(search_term)
        self.export_buttons_update.emit(is_piece_search)
        
        # Débounce : arrêter timer précédent et redémarrer
        self.search_timer.stop()
        if search_term:  # Seulement si pas vide
            self.search_timer.start(debounce_ms)
        else:
            # Recherche vide = afficher tout immédiatement
            self.pending_search_term = None
            self._execute_search()
    
    def _execute_search(self):
        """Exécuter la recherche différée via SearchService"""
        if not hasattr(self, 'pending_search_term'):
            return
            
        search_term = self.pending_search_term
        
        # Éviter les recherches identiques répétées
        if search_term == self._last_processed_term:
            return
        self._last_processed_term = search_term
        
        try:
            # Émettre signal de début
            display_term = self._get_display_term(search_term)
            self.search_started.emit(display_term)
            
            # Exécuter via SearchService avec pagination
            if search_term:
                # Compter d'abord pour décider pagination
                total_results = self.search_service.count_results(search_term)
                
                # Pagination conditionnelle (> 10000 résultats)
                limit = 1000 if total_results > 10000 else None
                offset = 0 if limit else None
                
                results = self.search_service.search(
                    term=search_term,
                    limit=limit,
                    offset=offset
                )
            else:
                # Pas de terme = afficher tout (avec limite raisonnable)
                results = self.search_service.search(term=None, limit=1000)
            
            # Stocker terme actuel et émettre résultats
            self.current_search_term = search_term
            self.search_completed.emit(results, search_term)
            
        except Exception as e:
            error_msg = f"Erreur recherche: {e}"
            app_logger.error(error_msg)
            self.search_error.emit(error_msg)
    
    def parse_advanced_search(self, text: str) -> Optional[Dict[str, Any]]:
        """Parser la recherche avancée avec opérateurs && et ||"""
        if not text.strip():
            return None
        
        try:
            # Nettoyer le texte d'entrée
            text = text.strip()
            
            # Détecter le type d'opérateur principal
            if '||' in text and '&&' in text:
                # Recherche mixte - traiter || en priorité
                return self._parse_or_search(text)
            elif '||' in text:
                # Recherche OR uniquement
                return self._parse_or_search(text)
            elif '&&' in text:
                # Recherche AND uniquement
                return self._parse_and_search(text)
            else:
                # Pas d'opérateur - recherche simple
                return {
                    'type': 'simple',
                    'terms': [text],
                    'original': text
                }
        except Exception as e:
            app_logger.error(f"Erreur parsing recherche avancée '{text}': {e}")
            # Fallback vers recherche simple
            return {
                'type': 'simple', 
                'terms': [text],
                'original': text
            }
    
    def _parse_or_search(self, text: str) -> Dict[str, Any]:
        """Parser recherche avec opérateurs OR (||)"""
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
        """Parser recherche avec opérateurs AND (&&)"""
        # Diviser par && et nettoyer
        and_terms = [term.strip() for term in text.split('&&') if term.strip()]
        
        return {
            'type': 'and', 
            'terms': and_terms,
            'original': text
        }
    
    def apply_search_highlight(self, item: QTableWidgetItem, search_term) -> bool:
        """Appliquer la mise en évidence de recherche sur un item"""
        if not search_term:
            return False
            
        item_text = str(item.text()).lower()
        should_highlight = False
        
        try:
            if isinstance(search_term, str):
                # Recherche simple (chaîne)
                should_highlight = search_term.lower() in item_text
            elif isinstance(search_term, dict):
                # Recherche parsée (dictionnaire)
                if search_term.get('type') == 'simple':
                    # Recherche simple parsée
                    terms = search_term.get('terms', [])
                    if terms:
                        should_highlight = terms[0].lower() in item_text
                elif search_term.get('type') == 'regex':
                    # Recherche par expression régulière
                    pattern = search_term.get('pattern', '')
                    should_highlight = bool(re.search(pattern, item_text, re.IGNORECASE))
                elif search_term.get('type') == 'and':
                    # Recherche AND - tous les termes doivent être présents
                    terms = search_term.get('terms', [])
                    should_highlight = all(term.lower() in item_text for term in terms)
                elif search_term.get('type') == 'or':
                    # Recherche OR - au moins un terme des groupes doit matcher
                    for group in search_term.get('groups', []):
                        if group.get('type') == 'and':
                            # Groupe AND dans OR
                            if all(term.lower() in item_text for term in group.get('terms', [])):
                                should_highlight = True
                                break
                        elif group.get('type') == 'simple':
                            # Terme simple dans OR
                            terms = group.get('terms', [])
                            if terms and terms[0].lower() in item_text:
                                should_highlight = True
                                break
            
            # Appliquer le style si match
            if should_highlight:
                item.setBackground(QColor(255, 255, 0, 100))  # Jaune translucide
                return True
            else:
                item.setBackground(QColor())  # Transparent/défaut
                return False
                
        except Exception as e:
            app_logger.error(f"Erreur mise en évidence recherche: {e}")
            return False
    
    def _is_piece_reference_search(self, search_term: str) -> bool:
        """Détecter si la recherche concerne une référence de pièce"""
        if not search_term:
            return False
        
        # Recherche multi-références avec || ou &&
        if '||' in search_term or '&&' in search_term:
            # Pour multi-références, considérer comme référence de pièce
            return True
        
        # Pour recherche simple, vérifier format référence
        # Logique simplifiée : au moins 2 caractères, pas que des espaces
        clean_term = search_term.strip()
        return len(clean_term) >= 2
    
    def _get_display_term(self, search_term) -> str:
        """Obtenir terme lisible pour affichage"""
        if isinstance(search_term, dict):
            return search_term.get('original', str(search_term)[:50] + '...')
        return str(search_term) if search_term else ""
    
    def get_current_search_term(self):
        """Obtenir le terme de recherche actuellement actif"""
        return self.current_search_term
    
    def clear_search(self):
        """Nettoyer l'état de recherche"""
        self.search_timer.stop()
        self.pending_search_term = None
        self.current_search_term = None
        self._last_processed_term = None
    
    def force_search(self, search_term=None):
        """Forcer une recherche immédiate (sans débounce)"""
        if search_term is not None:
            self.pending_search_term = search_term
        self._execute_search()