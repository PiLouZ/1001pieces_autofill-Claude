"""
Service Undo Manager - Phase 2.18 Refactoring
Extrait de main_refactored.py pour centraliser la logique d'annulation/rétablissement

Responsabilités:
- Gestion de l'historique des actions utilisateur
- Mécanisme d'undo/redo avec limite configurable
- Interface simple pour ajouter, annuler et rétablir des actions
- Intégration avec la configuration globale
"""

from typing import Optional, Dict, Any

from ..core.config import Config

class UndoRedoManager:
    """Gestionnaire simplifié d'annulation/rétablissement"""
    
    def __init__(self, max_history: int = None):
        self.history = []
        self.current_index = -1
        self.max_history = max_history or Config.UNDO_HISTORY_SIZE
    
    def add_action(self, action: Dict[str, Any]):
        """Ajouter une action à l'historique"""
        self.history = self.history[:self.current_index + 1]
        self.history.append(action)
        
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.current_index += 1
    
    def can_undo(self) -> bool:
        return self.current_index >= 0
    
    def can_redo(self) -> bool:
        return self.current_index < len(self.history) - 1
    
    def undo(self) -> Optional[Dict[str, Any]]:
        if self.can_undo():
            action = self.history[self.current_index]
            self.current_index -= 1
            return action
        return None
    
    def redo(self) -> Optional[Dict[str, Any]]:
        if self.can_redo():
            self.current_index += 1
            action = self.history[self.current_index]
            return action
        return None

# PHASE 6 CONSOLIDATION - UndoManagerService supprimé car redondant
# Utiliser directement UndoRedoManager qui gère déjà la configuration