"""
Processeur de données pour le collage depuis le presse-papiers
Extrait de main_refactored.py pour améliorer la maintenabilité
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from src.core.config import Config
from src.core.logger import app_logger
from src.services.base_service import safe_operation


@dataclass
class PasteProcessingResult:
    """Résultat du traitement des données collées"""
    inserted_count: int = 0
    updated_count: int = 0
    ignored_count: int = 0
    associations_created: int = 0
    duplicates_skipped: int = 0
    manual_completion_count: int = 0
    no_piece_ref_count: int = 0
    descriptions_updated: int = 0
    duplicates_list: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.duplicates_list is None:
            self.duplicates_list = []


class PasteDataProcessor:
    """
    Processeur spécialisé pour le traitement des données d'import (collage + CSV/PDF)
    
    Responsabilités:
    - Parser et nettoyer les données du presse-papiers
    - Traiter les imports de fichiers CSV/PDF  
    - Mapper les colonnes selon les règles métier
    - Traiter les données par lots pour optimiser les performances
    - Gérer la logique de validation et de déduplication
    """
    
    def __init__(self, db_manager, validator, main_window=None):
        self.db_manager = db_manager
        self.validator = validator
        self.main_window = main_window  # Pour accès aux méthodes helper existantes
        
    def detect_separator(self, clipboard_text: str) -> str:
        """Détecter le séparateur utilisé dans les données"""
        return '\t' if '\t' in clipboard_text else ';'
    
    def detect_columns_count(self, clipboard_text: str) -> int:
        """Détecter le nombre de colonnes des données collées"""
        lines = clipboard_text.strip().split('\n')
        if not lines:
            return 0
            
        separator = self.detect_separator(clipboard_text)
        column_counts = []
        
        # Analyser les 5 premières lignes pour détecter la structure
        for line in lines[:5]:
            if line.strip():
                columns = len(line.split(separator))
                column_counts.append(columns)
        
        if not column_counts:
            return 0
            
        # Prendre le nombre de colonnes le plus fréquent
        return max(set(column_counts), key=column_counts.count)
    
    def parse_clipboard_data(self, clipboard_text: str) -> List[List[str]]:
        """Parser les données du presse-papiers en lignes et colonnes"""
        lines = clipboard_text.strip().split('\n')
        separator = self.detect_separator(clipboard_text)
        rows = [line.split(separator) for line in lines]
        
        # Nettoyer les données
        cleaned_rows = []
        for row in rows:
            clean_row = []
            for cell in row:
                if cell:
                    # Supprimer les caractères de contrôle dangereux
                    cleaned_cell = ''.join(
                        char for char in cell 
                        if char not in ['\0', '\r', '\n', '\t']
                    ).strip()
                    clean_row.append(cleaned_cell)
                else:
                    clean_row.append('')
            cleaned_rows.append(clean_row)
        
        return cleaned_rows
    
    
    def validate_device_data(self, device_data: Dict[str, Any], row_idx: int) -> bool:
        """
        Valider les données d'un appareil
        
        Args:
            device_data: Données de l'appareil à valider
            row_idx: Index de la ligne pour les logs
            
        Returns:
            True si valide, False sinon (mais continue l'import avec avertissement)
        """
        validation_result = self.validator.validate_record(device_data)
        if not validation_result.is_valid:
            app_logger.warning(
                f"Données ligne {row_idx + 1} avec avertissement: {validation_result.error_message}"
            )
            app_logger.warning(f"⚠️ Ligne {row_idx + 1}: VALIDATION: {validation_result.error_message} - Continuant l'import...")
            app_logger.warning(f"    Données concernées: {device_data}")
            return False  # Mais on continue l'import
        return True
    

    def _needs_manual_completion(self, device_data: Dict[str, str]) -> bool:
        """
        Vérifier si l'appareil nécessite une complétion manuelle
        
        Args:
            device_data: Données de l'appareil
            
        Returns:
            bool: True si complétion manuelle nécessaire
        """
        # Vérifier si les champs obligatoires sont vides
        return not (device_data.get('type', '').strip() and device_data.get('manufacturer', '').strip())

    
    
    
    