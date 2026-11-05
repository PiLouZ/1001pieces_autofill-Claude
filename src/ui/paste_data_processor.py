"""
Processeur de données pour le collage depuis le presse-papiers
Extrait de main_refactored.py pour améliorer la maintenabilité
"""

from typing import List


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
    
    