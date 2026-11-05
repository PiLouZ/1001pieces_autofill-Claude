"""
Service de traitement des fichiers - Phase 2.7
Extrait de main_refactored.py pour centraliser la logique de traitement des fichiers

Responsabilités:
- Traitement des imports PDF avec progress tracking
- Gestion des fallbacks ImportManager vers système legacy
- Validation et extraction des données de fichiers
- Interface standardisée pour le traitement de fichiers
"""

from typing import List
from src.core.logger import app_logger


class FileProcessingService:
    """
    Service spécialisé pour le traitement des fichiers et imports
    
    Responsabilités:
    - Import PDF (glisser-déposer) via ImportManager, avec signalement des échecs
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        # L'import_manager sera accessible via self.main_window.import_manager quand nécessaire
        
    def import_pdf_files(self, file_paths: List[str]) -> bool:
        """
        Importer un ou plusieurs fichiers PDF depuis des chemins donnés
        
        Args:
            file_paths: Liste des chemins des fichiers PDF à traiter
            
        Returns:
            bool: True si l'import a réussi, False sinon
        """
        try:
            # Assurer que file_paths est une liste
            if isinstance(file_paths, str):
                file_paths = [file_paths]
            
            # PHASE 2.2 OPTIMISATION: Utiliser callback pour dialogue non-bloquant
            self.main_window.import_manager.import_from_drag_drop(
                file_paths,
                callback=self.main_window._on_import_complete
            )
            return True  # Retour immédiat, résultat via callback
        except Exception as e:
            # L'ancien « repli legacy » appelait des méthodes de MainWindow disparues
            # (_process_import, _show_error) : il ouvrait la fenêtre d'options puis
            # plantait. Retiré ; l'échec est désormais signalé tel quel.
            app_logger.error(f"Échec de l'import PDF via ImportManager : {e}")
            service = getattr(self.main_window, 'user_interaction_service', None)
            if service is not None:
                service.show_error(f"Erreur lors de l'import PDF : {e}")
            return False
    