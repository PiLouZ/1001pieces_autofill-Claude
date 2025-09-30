"""
Simple Event Bus for component decoupling - Phase 4
"""

from typing import Dict, List, Callable, Any
from collections import defaultdict
from ..utils.error_handler import handle_event_bus_errors

class EventBus:
    """Système d'événements simple pour découpler les composants"""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._enabled = True
        # Import tardif pour éviter les dépendances circulaires
        self._base_service = None
    
    def on(self, event_name: str, callback: Callable) -> None:
        """Écouter un événement"""
        self._listeners[event_name].append(callback)
    
    def off(self, event_name: str, callback: Callable) -> None:
        """Arrêter d'écouter un événement"""
        if callback in self._listeners[event_name]:
            self._listeners[event_name].remove(callback)

    @handle_event_bus_errors()
    def _safe_call_callback(self, callback: Callable, data: Any) -> None:
        """Appeler un callback de manière sécurisée"""
        callback(data)

    def emit(self, event_name: str, data: Any = None) -> None:
        """Émettre un événement"""
        if not self._enabled:
            return

        for callback in self._listeners[event_name]:
            self._safe_call_callback(callback, data)
    
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