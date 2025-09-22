"""
Service optimisé pour la gestion du bouton des lignes incomplètes
Utilise un cache intelligent pour éviter les requêtes SQL répétées
"""

from typing import Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QPushButton

from ..core.logger import app_logger

class IncompleteButtonService(QObject):
    """Service optimisé pour le bouton des lignes incomplètes"""

    # Signal émis quand le compteur change
    count_changed = pyqtSignal(int)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.button = None
        self.show_incomplete_only = False

        # Cache intelligent
        self._cached_count = None
        self._cache_valid = False
        self._last_update_time = 0

        # Timer pour les mises à jour différées
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_delayed_update)

        # Compteur pour éviter les calculs inutiles
        self._pending_updates = 0

    def set_button(self, button: QPushButton):
        """Associer le bouton à gérer"""
        self.button = button
        if button:
            self.count_changed.connect(self._update_button_display)

    def invalidate_cache(self, reason: str = "modification"):
        """Invalider le cache (à appeler lors des modifications de données)"""
        if self._cache_valid:
            self._cache_valid = False

            # Programmer une mise à jour différée pour éviter les rafraîchissements excessifs
            self.schedule_update()

    def schedule_update(self, delay_ms: int = 100):
        """Programmer une mise à jour différée du bouton"""
        self._pending_updates += 1

        # Différer pour regrouper les mises à jour
        if not self._update_timer.isActive():
            self._update_timer.start(delay_ms)

    def _perform_delayed_update(self):
        """Effectuer la mise à jour différée"""
        if self._pending_updates > 0:
            self._pending_updates = 0
            self.get_incomplete_count(force_refresh=True)

    def get_incomplete_count(self, force_refresh: bool = False) -> int:
        """Obtenir le nombre de lignes incomplètes (avec cache)"""
        import time
        current_time = time.time()

        # Utiliser le cache si valide et pas de forçage
        if not force_refresh and self._cache_valid and self._cached_count is not None:
            # Cache valide pendant 5 secondes pour les appels répétés
            if current_time - self._last_update_time < 5.0:
                return self._cached_count

        # Recalculer depuis la base de données
        try:
            new_count = self.db_manager.count_incomplete_devices()

            # Mettre à jour le cache
            old_count = self._cached_count
            self._cached_count = new_count
            self._cache_valid = True
            self._last_update_time = current_time

            # Émettre le signal si le compteur a changé
            if old_count != new_count:
                self.count_changed.emit(new_count)

            return new_count

        except Exception as e:
            app_logger.error(f"Erreur calcul lignes incomplètes: {e}")
            return self._cached_count or 0

    def _update_button_display(self, count: int):
        """Mettre à jour l'affichage du bouton"""
        if not self.button:
            return

        try:
            if count > 0:
                self.button.show()
                from ..core.config import pluralize

                if self.show_incomplete_only:
                    # Filtre actif
                    self.button.setText(f"📋 Filtre actif, plus que {pluralize(count, 'ligne')}")
                    self.button.setToolTip(f"Filtre actif - {pluralize(count, 'ligne')} avec des champs vides")
                else:
                    # Filtre inactif
                    self.button.setText(f"📋 {pluralize(count, 'incomplète')}")
                    self.button.setToolTip(f"Afficher uniquement les {pluralize(count, 'ligne')} avec des champs vides")
            else:
                self.button.hide()
                # Auto-désactiver le filtre si plus de lignes incomplètes
                if self.show_incomplete_only:
                    self.show_incomplete_only = False
                    # Signal pour recharger les données si nécessaire
                    app_logger.info("🔄 Plus de lignes incomplètes - désactivation auto du filtre")

        except Exception as e:
            app_logger.error(f"Erreur mise à jour affichage bouton: {e}")

    def set_filter_active(self, active: bool):
        """Définir l'état du filtre"""
        if self.show_incomplete_only != active:
            self.show_incomplete_only = active
            # Mettre à jour immédiatement l'affichage
            if self._cached_count is not None:
                self._update_button_display(self._cached_count)

    def get_statistics(self) -> dict:
        """Obtenir les statistiques du service"""
        return {
            'cached_count': self._cached_count,
            'cache_valid': self._cache_valid,
            'pending_updates': self._pending_updates,
            'filter_active': self.show_incomplete_only
        }