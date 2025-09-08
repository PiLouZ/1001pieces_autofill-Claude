"""
Service pour la gestion des dialogues de l'application
Extrait des classes CategoryDialog et NotesDialog de main_refactored.py
"""

from typing import Optional, List
from PyQt5.QtWidgets import QInputDialog


class CategoryDialog(QInputDialog):
    """Dialogue simplifié pour la gestion des catégories"""
    
    @staticmethod
    def get_categories(parent, current_categories: List[str]) -> Optional[List[str]]:
        """Méthode statique pour obtenir les catégories"""
        text, ok = QInputDialog.getMultiLineText(
            parent, 
            "Gestion des Catégories",
            "Entrez les catégories (une par ligne):",
            '\n'.join(current_categories)
        )
        
        if ok:
            return [line.strip() for line in text.split('\n') if line.strip()]
        return None


class NotesDialog(QInputDialog):
    """Dialogue simplifié pour l'édition des notes"""
    
    @staticmethod
    def get_notes(parent, current_notes: str = "") -> Optional[str]:
        """Méthode statique pour obtenir les notes"""
        text, ok = QInputDialog.getMultiLineText(
            parent,
            "Notes et Commentaires",
            "Entrez vos notes:",
            current_notes
        )
        
        return text if ok else None


class DialogService:
    """Service factory pour l'accès aux dialogues"""
    
    @staticmethod
    def get_category_dialog():
        """Retourne une instance de CategoryDialog"""
        return CategoryDialog()
    
    @staticmethod  
    def get_notes_dialog():
        """Retourne une instance de NotesDialog"""
        return NotesDialog()
    
    @staticmethod
    def get_categories(parent, current_categories: List[str]) -> Optional[List[str]]:
        """Méthode de convenance pour obtenir les catégories"""
        return CategoryDialog.get_categories(parent, current_categories)
    
    @staticmethod
    def get_notes(parent, current_notes: str = "") -> Optional[str]:
        """Méthode de convenance pour obtenir les notes"""
        return NotesDialog.get_notes(parent, current_notes)