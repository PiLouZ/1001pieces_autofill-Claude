"""
Service de Sauvegarde Événementielle - Factorisation Architecture
Centralise la logique de sauvegarde immédiate dispersée dans l'application
"""

from typing import Any, Dict, Optional, Set, Tuple
from PyQt5.QtCore import QTimer
from ..core.logger import app_logger
from ..core.config import Config
from .base_service import BaseService

class EventDrivenSaveService(BaseService):
    """
    Service centralisé pour la sauvegarde événementielle

    Responsabilités:
    - Sauvegarde immédiate des cellules modifiées
    - Sauvegarde après opérations batch (paste, import, delete)
    - Gestion des indicateurs de sauvegarde
    - Centralisation de la logique événementielle
    """

    def __init__(self, parent_window, parent=None):
        """
        Initialiser le service de sauvegarde événementielle

        Args:
            parent_window: Référence vers la fenêtre principale
            parent: Parent Qt (optionnel)
        """
        super().__init__(parent_window, parent)

        # Références critiques pour la sauvegarde
        self.database_operations_service = None
        self.save_indicator = None

        # État interne
        self.is_enabled = False

        # Initialisation différée des services
        self._initialize_services()

    def _initialize_services(self):
        """Initialisation différée des services requis"""
        try:
            # Récupérer le service de base de données
            if hasattr(self.parent_window, 'database_operations_service'):
                self.database_operations_service = self.parent_window.database_operations_service

            # Récupérer l'indicateur de sauvegarde
            if hasattr(self.parent_window, 'save_indicator'):
                self.save_indicator = self.parent_window.save_indicator

            # Vérifier si le service est activé
            self.is_enabled = Config.ENABLE_EVENT_DRIVEN_SAVE

            if self.is_enabled:
                app_logger.debug("EventDrivenSaveService: Service activé")
            else:
                app_logger.debug("EventDrivenSaveService: Service désactivé (fallback timer)")

        except Exception as e:
            app_logger.error(f"Erreur initialisation EventDrivenSaveService: {e}")

    # ================================
    # SAUVEGARDE CELLULES INDIVIDUELLES
    # ================================

    def save_cell_immediately(self, row: int, col: int, new_value: str, table_widget=None) -> bool:
        """
        Sauvegarde immédiate d'une cellule modifiée (< 100ms)

        Args:
            row: Numéro de ligne
            col: Numéro de colonne
            new_value: Nouvelle valeur
            table_widget: Widget table (optionnel, déduit du parent)

        Returns:
            bool: True si sauvegarde réussie
        """
        if not self.is_enabled:
            return False

        try:
            # Validation des prérequis
            if not self._validate_save_requirements():
                return False

            # Récupérer la table si non fournie
            if table_widget is None:
                table_widget = getattr(self.parent_window, 'table', None)

            if not table_widget:
                app_logger.error("save_cell_immediately: Table widget non disponible")
                return False

            # Créer un set avec la cellule modifiée pour utiliser l'API existante
            modified_cells = {(row, col)}

            # Convertir vers le format attendu par save_cells_batch
            updates_by_db_id = self.database_operations_service._convert_modified_cells_to_updates(modified_cells)

            # Sauvegarder immédiatement
            success = self.database_operations_service.save_cells_batch(updates_by_db_id)

            if success:
                # Mettre à jour l'indicateur de sauvegarde
                self._update_save_indicator_success()
                app_logger.debug(f"Sauvegarde immédiate réussie cellule ({row}, {col})")
            else:
                app_logger.warning(f"Échec sauvegarde immédiate cellule ({row}, {col})")

            return success

        except Exception as e:
            app_logger.error(f"Erreur sauvegarde immédiate cellule ({row}, {col}): {e}")
            return False

    # ================================
    # SAUVEGARDE APRÈS OPÉRATIONS BATCH
    # ================================

    def save_after_paste(self, result) -> bool:
        """
        Sauvegarde événementielle après opération de collage

        Args:
            result: Résultat du processus de collage avec inserted_count/updated_count

        Returns:
            bool: True si sauvegarde réussie
        """
        if not self.is_enabled:
            return False

        try:
            if not self._validate_save_requirements():
                return False

            total_changes = getattr(result, 'inserted_count', 0) + getattr(result, 'updated_count', 0)
            app_logger.debug(f"Sauvegarde événementielle après collage: {total_changes} modifications")

            # Après un collage, les données sont déjà commitées en base
            # On peut forcer un auto_save pour s'assurer que les transactions en attente sont terminées
            success = self.database_operations_service.auto_save()

            if success:
                self._update_save_indicator_success()
                self._update_incomplete_button_after_operation()
                app_logger.debug(f"Sauvegarde événementielle réussie après collage")
            else:
                app_logger.warning(f"Échec sauvegarde événementielle après collage")

            return success

        except Exception as e:
            app_logger.error(f"Erreur sauvegarde événementielle après collage: {e}")
            return False

    def save_after_import(self, event_type: str = "import_completed") -> bool:
        """
        Sauvegarde événementielle après opération d'import

        Args:
            event_type: Type d'événement import

        Returns:
            bool: True si sauvegarde réussie
        """
        if not self.is_enabled:
            return False

        try:
            if not self._validate_save_requirements():
                return False

            app_logger.debug(f"Sauvegarde événementielle déclenchée: {event_type}")

            # Pour les imports, pas de modified_cells à sauvegarder car déjà commitées
            # Mais on peut forcer un commit des transactions en attente
            success = self.database_operations_service.auto_save()

            if success:
                self._update_incomplete_button_after_operation()
                app_logger.debug(f"Sauvegarde événementielle réussie pour {event_type}")
            else:
                app_logger.warning(f"Échec sauvegarde événementielle pour {event_type}")

            return success

        except Exception as e:
            app_logger.error(f"Erreur sauvegarde événementielle {event_type}: {e}")
            return False

    def save_after_deletion(self, deleted_count: int) -> bool:
        """
        Sauvegarde événementielle après suppression d'appareils

        Args:
            deleted_count: Nombre d'appareils supprimés

        Returns:
            bool: True si sauvegarde réussie
        """
        if not self.is_enabled:
            return False

        try:
            app_logger.debug(f"Sauvegarde événementielle après suppression de {deleted_count} appareil(s)")

            # Après une suppression, les données sont déjà commitées en base
            # On peut forcer un auto_save pour s'assurer que les transactions en attente sont terminées
            success = self.database_operations_service.auto_save()

            if success:
                app_logger.debug(f"Sauvegarde événementielle réussie après suppression")
            else:
                app_logger.warning(f"Échec sauvegarde événementielle après suppression")

            return success

        except Exception as e:
            app_logger.error(f"Erreur sauvegarde événementielle après suppression: {e}")
            return False

    # ================================
    # GESTION INDICATEURS SAUVEGARDE
    # ================================

    def _update_save_indicator_success(self):
        """Mettre à jour l'indicateur de sauvegarde en cas de succès"""
        try:
            if self.save_indicator:
                self.save_indicator.setText(Config.get_message('save_success'))
                self.save_indicator.setStyleSheet("color: green;")

                # Remettre l'indicateur à l'état normal après un délai
                QTimer.singleShot(2000, lambda: self._reset_save_indicator())

        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateur succès: {e}")

    def _reset_save_indicator(self):
        """Remettre l'indicateur de sauvegarde à l'état normal"""
        try:
            if self.save_indicator:
                self.save_indicator.setText(Config.get_message('connected'))
                self.save_indicator.setStyleSheet("color: green;")

        except Exception as e:
            app_logger.error(f"Erreur reset indicateur sauvegarde: {e}")

    def update_save_indicator(self, status: str, color: str = "green"):
        """
        Mettre à jour l'indicateur de sauvegarde avec un statut personnalisé

        Args:
            status: Texte à afficher
            color: Couleur CSS (green, orange, red)
        """
        try:
            if self.save_indicator:
                self.save_indicator.setText(status)
                self.save_indicator.setStyleSheet(f"color: {color};")

        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateur: {e}")

    def _update_incomplete_button_after_operation(self):
        """Mettre à jour le bouton 'lignes à compléter' après une opération"""
        try:
            from PyQt5.QtCore import QTimer

            def update_incomplete_button():
                if hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                    self.parent_window._update_incomplete_button_visibility()

            # Délai de 100ms pour laisser les autres opérations se terminer
            QTimer.singleShot(100, update_incomplete_button)

        except Exception as e:
            app_logger.error(f"Erreur mise à jour bouton incomplet: {e}")

    # ================================
    # VALIDATION ET UTILS
    # ================================

    def _validate_save_requirements(self) -> bool:
        """
        Valider que tous les prérequis pour la sauvegarde sont disponibles

        Returns:
            bool: True si tous les prérequis sont OK
        """
        if not self.database_operations_service:
            app_logger.error("EventDrivenSaveService: database_operations_service non disponible")
            return False

        if not Config.USE_NEW_DATABASE_OPERATIONS_SERVICE:
            app_logger.debug("EventDrivenSaveService: USE_NEW_DATABASE_OPERATIONS_SERVICE désactivé")
            return False

        return True

    def is_event_driven_enabled(self) -> bool:
        """
        Vérifier si le système événementiel est activé

        Returns:
            bool: True si le système événementiel est actif
        """
        return self.is_enabled and Config.ENABLE_EVENT_DRIVEN_SAVE

    def get_service_status(self) -> Dict[str, Any]:
        """
        Obtenir le statut complet du service pour diagnostics

        Returns:
            Dict: Statut détaillé du service
        """
        return {
            'enabled': self.is_enabled,
            'config_flag': Config.ENABLE_EVENT_DRIVEN_SAVE,
            'database_service_available': self.database_operations_service is not None,
            'save_indicator_available': self.save_indicator is not None,
            'use_database_operations': Config.USE_NEW_DATABASE_OPERATIONS_SERVICE,
            'service_initialized': True
        }

    # ================================
    # API PUBLIQUE POUR INTÉGRATION
    # ================================

    def handle_cell_changed(self, row: int, col: int, new_value: str, table_widget=None) -> bool:
        """
        API publique: Gérer la modification d'une cellule

        Args:
            row: Numéro de ligne
            col: Numéro de colonne
            new_value: Nouvelle valeur
            table_widget: Widget table (optionnel)

        Returns:
            bool: True si traité avec succès
        """
        return self.save_cell_immediately(row, col, new_value, table_widget)

    def handle_paste_completed(self, result) -> bool:
        """
        API publique: Gérer la fin d'une opération de collage

        Args:
            result: Résultat de l'opération de collage

        Returns:
            bool: True si traité avec succès
        """
        return self.save_after_paste(result)

    def handle_import_completed(self) -> bool:
        """
        API publique: Gérer la fin d'une opération d'import

        Returns:
            bool: True si traité avec succès
        """
        return self.save_after_import("import_completed")

    def handle_deletion_completed(self, deleted_count: int) -> bool:
        """
        API publique: Gérer la fin d'une opération de suppression

        Args:
            deleted_count: Nombre d'éléments supprimés

        Returns:
            bool: True si traité avec succès
        """
        return self.save_after_deletion(deleted_count)