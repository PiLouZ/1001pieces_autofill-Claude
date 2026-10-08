"""
Service de Sauvegarde Événementielle - Factorisation Architecture
Centralise la logique de sauvegarde immédiate dispersée dans l'application
"""

from typing import Any, Dict, Optional, Set, Tuple
from ..ui.qt_imports import QTimer
from ..core.logger import app_logger
from ..core.config import Config
from .base_service import BaseService
from ..utils.error_handler import handle_save_service_errors

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

    @handle_save_service_errors()
    def _initialize_services(self):
        """Initialisation différée des services requis"""
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

    # ================================
    # SAUVEGARDE CELLULES INDIVIDUELLES
    # ================================

    @handle_save_service_errors()
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

        # Validation des prérequis
        if not self._validate_save_requirements():
            return False

        # Récupérer la table si non fournie
        if table_widget is None:
            table_widget = getattr(self.parent_window, 'table', None)

        if not table_widget:
            app_logger.error("save_cell_immediately: Table widget non disponible")
            return False

        # Signaler la sauvegarde en cours
        self._update_save_indicator_pending()

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

    @handle_save_service_errors()
    def save_cells_batch_immediate(self, modified_cells: Set[Tuple[int, int]]) -> bool:
        """
        Sauvegarde immédiate d'un lot de cellules en une seule transaction.

        Utilisé pour les modifications de masse (ex: Suppr sur une sélection de
        plusieurs milliers de cellules) afin d'éviter un commit SQLite par cellule
        — qui gèle l'interface le temps de l'opération.

        Args:
            modified_cells: ensemble de (row, col) modifiées

        Returns:
            bool: True si sauvegarde réussie
        """
        if not self.is_enabled or not modified_cells:
            return False

        if not self._validate_save_requirements():
            return False

        self._update_save_indicator_pending()

        updates_by_db_id = self.database_operations_service._convert_modified_cells_to_updates(modified_cells)
        success = self.database_operations_service.save_cells_batch(updates_by_db_id)

        if success:
            self._update_save_indicator_success()
            app_logger.debug(f"Sauvegarde immédiate réussie ({len(modified_cells)} cellules)")
        else:
            app_logger.warning(f"Échec sauvegarde immédiate ({len(modified_cells)} cellules)")

        return success

    # ================================
    # SAUVEGARDE APRÈS OPÉRATIONS BATCH
    # ================================


    @handle_save_service_errors()
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

        if not self._validate_save_requirements():
            return False

        app_logger.debug(f"Sauvegarde événementielle déclenchée: {event_type}")

        # Pour les imports, pas de modified_cells à sauvegarder car déjà commitées
        # Mais on peut forcer un commit des transactions en attente
        success = self.database_operations_service.auto_save()

        if success:
            self._update_save_indicator_success()
            self._update_incomplete_button_after_operation()
            app_logger.debug(f"Sauvegarde événementielle réussie pour {event_type}")
        else:
            app_logger.warning(f"Échec sauvegarde événementielle pour {event_type}")

        return success

    @handle_save_service_errors()
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

        app_logger.debug(f"Sauvegarde événementielle après suppression de {deleted_count} appareil(s)")

        # Après une suppression, les données sont déjà commitées en base
        # On peut forcer un auto_save pour s'assurer que les transactions en attente sont terminées
        success = self.database_operations_service.auto_save()

        if success:
            self._update_save_indicator_success()
            app_logger.debug(f"Sauvegarde événementielle réussie après suppression")
        else:
            app_logger.warning(f"Échec sauvegarde événementielle après suppression")

        return success

    # ================================
    # GESTION INDICATEURS SAUVEGARDE
    # ================================

    @handle_save_service_errors()
    def _update_save_indicator_pending(self):
        """Afficher 'Sauvegarde…' (orange) avant l'écriture en base"""
        if self.save_indicator:
            self.save_indicator.setText("Sauvegarde…")
            self.save_indicator.setStyleSheet("color: orange;")

    @handle_save_service_errors()
    def _update_save_indicator_success(self):
        """Mettre à jour l'indicateur de sauvegarde en cas de succès"""
        if self.save_indicator:
            self.save_indicator.setText(Config.get_message('save_success'))
            self.save_indicator.setStyleSheet("color: green;")

            # Effacer l'indicateur après 2s (retour à l'état discret)
            QTimer.singleShot(2000, lambda: self._reset_save_indicator())

    @handle_save_service_errors()
    def _reset_save_indicator(self):
        """Effacer l'indicateur de sauvegarde (état discret)"""
        if self.save_indicator:
            self.save_indicator.setText("")
            self.save_indicator.setStyleSheet("color: green;")

    @handle_save_service_errors()
    def _update_incomplete_button_after_operation(self):
        """Mettre à jour le bouton 'lignes à compléter' après une opération"""
        from ..ui.qt_imports import QTimer

        def update_incomplete_button():
            if hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                self.parent_window._update_incomplete_button_visibility()

        # Délai de 100ms pour laisser les autres opérations se terminer
        QTimer.singleShot(100, update_incomplete_button)

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

        return True

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