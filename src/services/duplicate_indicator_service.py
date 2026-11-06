"""
Service optimisé pour l'indication visuelle des doublons
Utilise un cache intelligent pour éviter les requêtes SQL répétées
Basé sur le modèle d'IncompleteButtonService
"""

from typing import List, Tuple
from ..utils.qt_imports import QObject, pyqtSignal, QTimer, QPushButton, QAction

from ..core.logger import app_logger

class DuplicateIndicatorService(QObject):
    """Service optimisé pour l'indication visuelle des doublons"""

    # Signal émis quand le compteur de doublons change
    duplicates_count_changed = pyqtSignal(int, int)  # (nb_groups, nb_total_devices)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.action_button = None
        self.clean_action = None

        # Cache intelligent
        self._cached_duplicates = None
        self._cache_valid = False
        self._last_update_time = 0

        # Timer pour les mises à jour différées
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_delayed_update)

        # Compteur pour éviter les calculs inutiles
        self._pending_updates = 0

        # Styles centralisés dans StyleManager (cluster "santé des données") : géométrie
        # partagée avec le bouton "Lignes à traiter" → les deux boutons ont exactement les
        # mêmes dimensions ; seule la couleur varie selon l'état. Source unique de vérité.
        from ..ui.style_manager import StyleManager
        self._normal_style = StyleManager.HEALTH_BTN_NEUTRAL
        self._warning_style = StyleManager.HEALTH_BTN_ALERT

        # Style pour le menu quand il y a des alertes
        self._menu_warning_style = """
            QMenu {
                background-color: #fff5f0;
                border: 2px solid #ff6b35;
            }
            QMenu::item {
                padding: 6px 20px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #ffe6d9;
                color: #d9480f;
            }
            QAction[hasWarning="true"] {
                background-color: #ff6b35;
                color: white;
                font-weight: bold;
            }
        """

    def set_buttons(self, action_button: QPushButton, clean_action: QAction):
        """Associer les boutons à gérer"""
        self.action_button = action_button
        self.clean_action = clean_action
        if action_button and clean_action:
            self.duplicates_count_changed.connect(self._update_visual_indicators)
            app_logger.info("[OK] Signal duplicates_count_changed connecté à _update_visual_indicators")

    def invalidate_cache(self, reason: str = "modification"):
        """Invalider le cache (à appeler lors des modifications de données)"""
        if self._cache_valid:
            self._cache_valid = False

            # Programmer une mise à jour différée pour éviter les rafraîchissements excessifs
            self.schedule_update()

    def schedule_update(self, delay_ms: int = 100):
        """Programmer une mise à jour différée du cache"""
        self._pending_updates += 1

        # Différer pour regrouper les mises à jour
        if not self._update_timer.isActive():
            self._update_timer.start(delay_ms)

    def _perform_delayed_update(self):
        """Effectuer la mise à jour différée"""
        if self._pending_updates > 0:
            self._pending_updates = 0
            self.get_duplicates_count(force_refresh=True)

    def get_duplicates_count(self, force_refresh: bool = False) -> Tuple[int, int]:
        """Obtenir le nombre de doublons (avec cache)

        Returns:
            Tuple[int, int]: (nb_groups_doublons, nb_total_appareils_en_doublon)
        """
        import time
        current_time = time.time()

        # Utiliser le cache si valide et pas de forçage
        if not force_refresh and self._cache_valid and self._cached_duplicates is not None:
            # Cache valide pendant 5 secondes pour les appels répétés
            if current_time - self._last_update_time < 5.0:
                return self._cached_duplicates

        # Recalculer depuis la base de données
        try:
            # Utiliser une requête personnalisée qui exclut les appareils marqués DISTINCT
            duplicates_list = self._get_real_duplicates()

            nb_groups = len(duplicates_list)
            nb_total = sum(count for ref, count in duplicates_list)

            app_logger.info(f" Comptage doublons DB: {nb_groups} groupes, {nb_total} appareils total")

            # Mettre à jour le cache
            old_duplicates = self._cached_duplicates
            self._cached_duplicates = (nb_groups, nb_total)
            self._cache_valid = True
            self._last_update_time = current_time

            # Émettre le signal si le compteur a changé
            if old_duplicates != self._cached_duplicates:
                app_logger.info(f" Changement doublons détecté: {old_duplicates} → {self._cached_duplicates}")
                self.duplicates_count_changed.emit(nb_groups, nb_total)

            return self._cached_duplicates

        except Exception as e:
            app_logger.error(f"Erreur calcul doublons: {e}")
            return self._cached_duplicates or (0, 0)

    def _update_visual_indicators(self, nb_groups: int, nb_total: int):
        """Mettre à jour les indicateurs visuels"""
        if not self.action_button or not self.clean_action:
            app_logger.warning("[!] Boutons non définis pour mise à jour indicateurs doublons")
            return

        if nb_groups > 0:
            # Doublons détectés - Affichage en warning
            app_logger.info(f" Doublons détectés: {nb_groups} groupes ({nb_total} appareils)")

            # Style du bouton Action
            self.action_button.setStyleSheet(self._warning_style)
            self.action_button.setToolTip(f"[!] {nb_groups} groupes de doublons détectés ({nb_total} appareils)")

            # Texte de l'action Nettoyer (éviter les emojis problématiques)
            from ..core.config import pluralize
            self.clean_action.setText(f"Nettoyer les doublons ({pluralize(nb_groups, 'groupe')})")
            self.clean_action.setToolTip(f"ATTENTION: {pluralize(nb_groups, 'groupe')} de doublons détectés - {pluralize(nb_total, 'appareil')} concerné")

            # Appliquer un style d'alerte à l'action (setProperty est safe)
            self.clean_action.setProperty("hasWarning", True)

        else:
            # Aucun doublon - Affichage normal
            app_logger.info("[OK] Aucun doublon détecté")

            # Réinitialiser le style du bouton Action
            self.action_button.setStyleSheet(self._normal_style)
            self.action_button.setToolTip("Actions sur les données")

            # Réinitialiser le texte de l'action Nettoyer
            self.clean_action.setText("Nettoyer les doublons")
            self.clean_action.setToolTip("Rechercher et nettoyer les appareils en doublon")

            # Enlever le style d'alerte (setProperty est safe)
            self.clean_action.setProperty("hasWarning", False)

    def _get_real_duplicates(self) -> List[Tuple[str, int]]:
        """Obtenir les vrais doublons en excluant les appareils marqués DISTINCT"""
        try:
            # Doublons hors ref_modele marquées DISTINCT
            result = self.db_manager.compter_vrais_doublons()
            return result if result else []

        except Exception as e:
            app_logger.error(f"Erreur requête doublons réels: {e}")
            # Fallback sur la méthode standard si erreur
            return self.db_manager.get_duplicate_ref_modeles()