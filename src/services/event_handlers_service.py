"""
Service pour la gestion des gestionnaires d'événements de l'application
Extrait des méthodes _on_* de main_refactored.py
"""

from typing import Any, Dict
from src.core.logger import app_logger
from src.core.config import Config, pluralize
from src.utils.error_handler import handle_event_handler_errors

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
    
    def on_search_error(self, data: Dict[str, Any]):
        """Gestionnaire événement erreur de recherche"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"[ERR] Erreur recherche: {data['error']}", 5000)
    
    # === GESTIONNAIRES DE RECHERCHE AVANCÉE ===
    
    def on_advanced_search_started(self, term: str):
        """Gestionnaire début recherche avancée"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f" Recherche avancée: '{term}'...")
    
    @handle_event_handler_errors()
    def on_advanced_search_completed(self, results, search_term: str):
        """Gestionnaire fin recherche avancée - déléguer à table_controller pour pagination"""
        # Déléguer entièrement au table_controller qui sait gérer la pagination
        # Le parsing a déjà été fait par AdvancedSearchService, on passe le terme
        try:
            self.main_window.table_controller.load_data(search_term, is_search=True)
        except Exception as e:
            # Remplace « Recherche avancée : '…' » (sinon affiché indéfiniment)
            self.on_search_error({'term': search_term, 'error': str(e)})
            raise
    
    def on_advanced_search_error(self, error_msg: str):
        """Gestionnaire erreur recherche avancée"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"[ERR] {error_msg}", 5000)
    
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
            self.main_window.statusbar.showMessage(f" Export {data['format']} en cours...")
    
    def on_export_completed(self, data: Dict[str, Any]):
        """Gestionnaire événement fin d'export"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(
                f"[OK] Export terminé: {data['count']} lignes → {data['output_file']}", 
                5000
            )
    
    def on_export_error(self, data: Dict[str, Any]):
        """Gestionnaire événement erreur d'export"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"[ERR] Erreur export: {data['error']}", 5000)
    
    # === GESTIONNAIRES D'IMPORT ===
    
    def on_import_started(self, data: Dict[str, Any]):
        """Gestionnaire événement début d'import"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f" Import de {pluralize(data['file_count'], 'fichier')}...")
    
    def on_import_completed(self, data: Dict[str, Any]):
        """Gestionnaire événement fin d'import"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(
                f"[OK] Import terminé: {data['total_imported']} lignes traitées",
                5000
            )

        # Feature Flag: Phase 4 - Sauvegarde événementielle après import (délégation service)
        if Config.ENABLE_EVENT_DRIVEN_SAVE:
            if hasattr(self.main_window, 'event_driven_save_service') and self.main_window.event_driven_save_service:
                self.main_window.event_driven_save_service.handle_import_completed()
            else:
                # Fallback si service pas encore initialisé
                app_logger.warning("EventDrivenSaveService non disponible, fallback méthode locale")
                self._trigger_event_driven_save("import_completed")

    @handle_event_handler_errors()
    def _trigger_event_driven_save(self, event_type: str):
        """Déclencher sauvegarde événementielle"""
        if (hasattr(self.main_window, 'database_operations_service') and
            self.main_window.database_operations_service and
            Config.USE_NEW_DATABASE_OPERATIONS_SERVICE):

            app_logger.debug(f"Sauvegarde événementielle déclenchée: {event_type}")
            # Pour les imports, pas de modified_cells à sauvegarder car déjà commitées
            # Mais on peut forcer un commit des transactions en attente
            success = self.main_window.database_operations_service.auto_save()

            if success:
                app_logger.debug(f"Sauvegarde événementielle réussie pour {event_type}")
            else:
                app_logger.warning(f"Échec sauvegarde événementielle pour {event_type}")
    
    def on_import_error(self, data: Dict[str, Any]):
        """Gestionnaire événement erreur d'import"""
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(f"[ERR] Erreur import: {data['error']}", 5000)