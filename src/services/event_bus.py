"""
Simple Event Bus for component decoupling - Phase 4
"""

from typing import Dict, List, Callable, Any
from collections import defaultdict

class EventBus:
    """Système d'événements simple pour découpler les composants"""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._enabled = True
    
    def on(self, event_name: str, callback: Callable) -> None:
        """Écouter un événement"""
        self._listeners[event_name].append(callback)
    
    def off(self, event_name: str, callback: Callable) -> None:
        """Arrêter d'écouter un événement"""
        if callback in self._listeners[event_name]:
            self._listeners[event_name].remove(callback)
    
    def emit(self, event_name: str, data: Any = None) -> None:
        """Émettre un événement"""
        if not self._enabled:
            return
            
        for callback in self._listeners[event_name]:
            try:
                callback(data)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"Erreur callback {event_name}: {e}")
    
    def disable(self) -> None:
        """Désactiver temporairement le bus d'événements"""
        self._enabled = False
    
    def enable(self) -> None:
        """Réactiver le bus d'événements"""
        self._enabled = True
    
    def clear(self) -> None:
        """Vider tous les listeners"""
        self._listeners.clear()

# Instance globale du bus d'événements
event_bus = EventBus()