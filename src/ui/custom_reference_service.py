"""
Service de référence personnalisée - Phase 2.9
Extrait de main_refactored.py pour centraliser la logique d'export CSV personnalisé

Responsabilités:
- Export CSV avec référence personnalisée et données de recherche complexe
- Gestion des recherches multi-références (|| et && operators)
- Création de CSV de fallback minimal en cas d'erreur
- Interface standardisée pour les exports avec références customisées
"""

import csv
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.core.logger import app_logger
from ..utils.error_handler import handle_export_errors

class CustomReferenceService:
    """
    Service spécialisé pour l'export CSV avec références personnalisées
    
    Responsabilités:
    - Export CSV avec référence custom et données complètes de recherche
    - Gestion des opérateurs de recherche multiple (|| = OR, && = AND)
    - Traitement des filtres de colonnes et de lignes incomplètes
    - Fallback vers CSV minimal en cas d'erreur
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
    
    def _get_active_column_filters(self) -> Dict[int, str]:
        """
        Récupérer les filtres de colonnes actifs
        
        Returns:
            Dict: Mapping colonne -> filtre actif
        """
        column_filters = {}
        
        if (hasattr(self.main_window, 'table_controller') and 
            hasattr(self.main_window.table_controller, 'filter_widgets')):
            
            for col_idx, filter_widget in self.main_window.table_controller.filter_widgets.items():
                if filter_widget is not None:  # Skip removed filters
                    from .qt_imports import QComboBox
                    if isinstance(filter_widget, QComboBox):
                        filter_text = filter_widget.currentText().strip()
                    else:  # QLineEdit
                        filter_text = filter_widget.text().strip()
                    
                    if filter_text:
                        column_filters[col_idx] = filter_text
        
        return column_filters
    
    
    
    