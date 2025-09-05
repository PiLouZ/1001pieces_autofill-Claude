"""
Service pour la gestion des gestionnaires d'événements de l'application
Extrait des méthodes _on_* de main_refactored.py
"""

from typing import Any, Dict
from src.core.logger import app_logger
from src.core.config import Config


class EventHandlersService:
    """Service pour gérer tous les gestionnaires d'événements"""
    
    def __init__(self, main_window):
        """
        Initialise le service avec référence à la fenêtre principale
        
        Args:
            main_window: Instance de MainWindow
        """
        self.main_window = main_window
    
    # === GESTIONNAIRES DE RECHERCHE ===
    
    def on_search_started(self, data: Dict[str, Any]):
        """Gestionnaire événement début de recherche"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"🔍 Recherche en cours: '{data['term']}'...")
    
    def on_search_completed(self, data: Dict[str, Any]):
        """Gestionnaire événement fin de recherche"""
        if hasattr(self.main_window, 'statusbar'):
            cache_info = " (cache)" if data.get('has_cache_hit') else ""
            self.main_window.statusbar.showMessage(
                f"✅ Recherche terminée: {data['results_count']} résultats{cache_info}", 
                3000
            )
    
    def on_search_error(self, data: Dict[str, Any]):
        """Gestionnaire événement erreur de recherche"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"❌ Erreur recherche: {data['error']}", 5000)
    
    # === GESTIONNAIRES DE RECHERCHE AVANCÉE ===
    
    def on_advanced_search_started(self, term: str):
        """Gestionnaire début recherche avancée"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"🔍 Recherche avancée: '{term}'...")
    
    def on_advanced_search_completed(self, results, search_term: str):
        """Gestionnaire fin recherche avancée - afficher résultats"""
        try:
            # Stocker le terme de recherche dans le controller pour la pagination
            self.main_window.table_controller.current_search_term = search_term
            
            # Réinitialiser pagination à la première page
            self.main_window.table_controller.current_page = 1
            
            # Utiliser les résultats déjà trouvés par AdvancedSearchService
            # au lieu de relancer une recherche
            self.main_window.table_controller.total_rows = len(results)
            self.main_window.table_controller.total_pages = max(1, (self.main_window.table_controller.total_rows + self.main_window.table_controller.page_size - 1) // self.main_window.table_controller.page_size)
            
            # Remplir le tableau directement avec les résultats
            if self.main_window.table_controller.total_rows > 1000:
                self.main_window.table_controller._fill_table_chunked(results, None, search_term)
            else:
                self.main_window.table_controller._fill_table_standard(results, None, search_term)
            
            # Mettre à jour les contrôles de pagination
            self.main_window.table_controller._update_pagination_controls()
            
            # Message status
            if hasattr(self.main_window, 'statusbar'):
                self.main_window.statusbar.showMessage(
                    f"✅ Recherche terminée: {len(results)} résultats", 
                    Config.STATUS_MESSAGE_TIMEOUT
                )
        except Exception as e:
            app_logger.error(f"Erreur affichage résultats recherche: {e}")
    
    def on_advanced_search_error(self, error_msg: str):
        """Gestionnaire erreur recherche avancée"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"❌ {error_msg}", 5000)
    
    def on_export_buttons_update(self, is_piece_search: bool):
        """Gestionnaire mise à jour boutons export selon recherche"""
        # Déléguer au service UI qui gère maintenant les boutons
        self.main_window.ui_component_service.update_export_buttons_state_by_search(is_piece_search)
        
        # Boutons SEO également limités aux références de pièce - Phase 2.15: Délégation vers SEOService
        self.main_window.seo_service.update_seo_buttons_state()
    
    # === GESTIONNAIRES D'EXPORT ===
    
    def on_export_started(self, data: Dict[str, Any]):
        """Gestionnaire événement début d'export"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"📤 Export {data['format']} en cours...")
    
    def on_export_completed(self, data: Dict[str, Any]):
        """Gestionnaire événement fin d'export"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(
                f"✅ Export terminé: {data['count']} lignes → {data['output_file']}", 
                5000
            )
    
    def on_export_error(self, data: Dict[str, Any]):
        """Gestionnaire événement erreur d'export"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"❌ Erreur export: {data['error']}", 5000)
    
    # === GESTIONNAIRES D'IMPORT ===
    
    def on_import_started(self, data: Dict[str, Any]):
        """Gestionnaire événement début d'import"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"📥 Import de {data['file_count']} fichier(s)...")
    
    def on_import_completed(self, data: Dict[str, Any]):
        """Gestionnaire événement fin d'import"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(
                f"✅ Import terminé: {data['total_imported']} lignes traitées", 
                5000
            )
    
    def on_import_error(self, data: Dict[str, Any]):
        """Gestionnaire événement erreur d'import"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"❌ Erreur import: {data['error']}", 5000)