"""
Paste Results Service - Phase 2.16
Service dédié à la gestion des résultats de collage

Responsabilités:
- Affichage des résumés de collage
- Logging des résultats dans l'historique
- Formatage des statistiques de collage
"""

from typing import Optional
from ..ui.qt_imports import QMessageBox
from ..core.logger import app_logger

class PasteResultsService:
    """
    Service de gestion des résultats de collage
    
    Responsabilités:
    - Formatage et affichage des résumés de collage
    - Logging des résultats dans l'historique utilisateur
    - Présentation des statistiques de manière claire
    """
    
    def __init__(self, main_window):
        self.main_window = main_window