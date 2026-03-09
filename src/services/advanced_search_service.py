"""
Advanced Search Service - Phase 2.3 Refactoring  
Centralise toute la logique de recherche avancée avec opérateurs && et ||
"""

import re
from typing import Optional, Dict, Any, Callable, List
from ..ui.qt_imports import QTimer, QObject, pyqtSignal
from ..ui.qt_imports import QTableWidgetItem
from ..ui.qt_imports import QColor

from .search_service import SearchService
from ..core.logger import app_logger
from ..core.config import Config
from .base_service import BaseService
from ..utils.error_handler import handle_search_errors, handle_highlight_errors

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
        self._base_service = BaseService(parent_window=parent)
        
        # Timer pour débounce (500ms)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._execute_search)
        
        # État de recherche
        self.pending_search_term = None
        self.current_search_term = None
        
        # Cache pour éviter les recherches répétées
        self._last_processed_term = None

    @handle_search_errors(return_value=None)
    def _safe_execute_search(self, search_term):
        """Exécuter la recherche de manière sécurisée"""
        if search_term:
            return self.search_service.search(term=search_term)
        else:
            # Pas de terme = afficher tout
            return self.search_service.search(term=None)
    
    def search_with_debounce(self, text: str, debounce_ms: int = 500):
        """Lancer une recherche avec débounce (attendre avant d'exécuter)"""
        search_term = text.strip()
        
        # CORRECTION FINALE: Ne plus parser ici, laisser le table_controller s'en charger
        # Passer le terme brut au table_controller qui fera le parsing avec SearchService
        self.pending_search_term = search_term
        
        # Émettre signal pour boutons export (basé sur détection référence pièce)
        is_piece_search = self.search_service.is_piece_reference_search(search_term)
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
        
        # Émettre signal de début
        display_term = self.search_service.format_search_term_for_display(search_term)
        self.search_started.emit(display_term)

        # Exécuter la recherche avec gestion d'erreur centralisée
        results = self._safe_execute_search(search_term)

        if results is not None:
            # Stocker terme actuel et émettre résultats
            self.current_search_term = search_term
            # Convertir search_term en string pour le signal
            search_term_str = str(search_term) if isinstance(search_term, dict) else search_term
            self.search_completed.emit(results, search_term_str)
        else:
            # Erreur gérée par le décorateur, émettre signal d'erreur
            error_msg = f"Erreur recherche: {search_term}"
            self.search_error.emit(error_msg)
    
    def parse_advanced_search(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parser la recherche avancée avec opérateurs && et || 
        
        PHASE 6 CONSOLIDÉ - Délègue entièrement à SearchService
        """
        return self.search_service.parse_advanced_search(text)

    @handle_highlight_errors(return_value=False)
    def apply_search_highlight(self, item: QTableWidgetItem, search_term) -> bool:
        """Appliquer la mise en évidence de recherche sur un item"""
        if not search_term:
            return False
            
        item_text = str(item.text()).lower()
        should_highlight = False
        
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
            # Utiliser la couleur configurée avec une opacité réduite pour éviter le problème de lisibilité
            highlight_color = Config.SEARCH_HIGHLIGHT_COLOR
            if len(highlight_color) == 4:  # RGBA
                # Réduire l'opacité pour éviter que le texte devienne illisible
                r, g, b, a = highlight_color
                item.setBackground(QColor(r, g, b, min(a, 50)))  # Max 50 sur 255 pour plus de lisibilité
            else:  # RGB
                r, g, b = highlight_color
                item.setBackground(QColor(r, g, b, 50))  # Opacité 50 sur 255
            return True
        else:
            # Remettre la couleur par défaut explicitement (blanc)
            item.setBackground(QColor(255, 255, 255))  # Blanc par défaut
            return False

    def get_current_search_term(self):
        """Obtenir le terme de recherche actuellement actif"""
        return self.current_search_term
        
    def get_current_search_term_with_fallback(self, main_window):
        """Récupérer le terme de recherche actuel avec fallback intelligent - SOURCE DE VÉRITÉ = champ de recherche visible"""
        from ..core.logger import app_logger
        
        # SOURCE DE VÉRITÉ: Le champ de recherche visible par l'utilisateur
        if hasattr(main_window, 'search_input') and main_window.search_input:
            visible_term = main_window.search_input.text().strip()
            if visible_term:
                return visible_term
        
        # Fallback 1: TableController car c'est lui qui gère les recherches
        if hasattr(main_window, 'table_controller') and hasattr(main_window.table_controller, 'pending_search_term'):
            term = main_window.table_controller.pending_search_term
            if term:
                return term
                
        # Fallback 2: AdvancedSearchService  
        term = self.get_current_search_term()
        if term:
            return term
        
        # Fallback 3: current_search_term de main_refactored
        term = getattr(main_window, 'current_search_term', None)
        return term
    
    def clear_search(self):
        """Nettoyer l'état de recherche"""
        self.search_timer.stop()
        self.pending_search_term = None
        self.current_search_term = None
        self._last_processed_term = None
        
    def clear_search_ui(self, main_window):
        """Effacer le champ de recherche principal et tous les filtres"""
        # Nettoyer l'état de recherche interne
        self.clear_search()
        
        # Nettoyer l'interface utilisateur
        if hasattr(main_window, 'search_input') and main_window.search_input:
            main_window.search_input.clear()
            
        # Effacer aussi tous les filtres de colonnes via TableController
        # Déléguer à _clear_all_column_filters qui gère correctement QComboBox (setCurrentIndex(0))
        # et QLineEdit (clear()) — évite le bug QComboBox.clear() qui détruit tous les items
        if hasattr(main_window, 'table_controller'):
            tc = main_window.table_controller
            if hasattr(tc, '_clear_all_column_filters'):
                tc._clear_all_column_filters()
                return  # _clear_all_column_filters appelle déjà load_data()
            # Fallback si méthode absente
            main_window.table_controller.load_data()
    
    def force_search(self, search_term=None):
        """Forcer une recherche immédiate (sans débounce)"""
        if search_term is not None:
            self.pending_search_term = search_term
        self._execute_search()