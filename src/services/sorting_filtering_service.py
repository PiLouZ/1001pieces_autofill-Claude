"""
Service des filtres de table : bascule « lignes incomplètes » et remise à zéro
des filtres de colonne.

Le tri (clic sur un en-tête, flèches) est géré par TableController ; l'ancienne
version de ce service, qui le dupliquait, a été retirée.
"""

from ..utils.qt_imports import pyqtSignal, QTableWidget

from .base_service import BaseService, service_operation

class SortingFilteringService(BaseService):
    """Filtres de table (lignes incomplètes, filtres de colonne)"""

    # Signal pour notifier les changements
    filter_applied = pyqtSignal(str)  # filter_description

    def __init__(self, table_widget: QTableWidget, table_controller, parent_window=None, parent=None):
        super().__init__(parent_window=parent_window, parent=parent)
        self.table = table_widget
        self.table_controller = table_controller

        # Services requis pour l'injection automatique
        self._required_services = ['advanced_search_service']

        # État des filtres
        self.active_column_filters = {}  # {column_index: filter_text}
        self.incomplete_filter_active = False

    @service_operation("suppression_filtres")
    def clear_column_filters(self):
        """Nettoyer tous les filtres de colonnes"""
        if self.active_column_filters:
            self.active_column_filters.clear()
            self.log_operation("clear_column_filters", "Tous les filtres de colonnes supprimés", "debug")

            # Recharger sans filtres
            self._reload_with_current_filters()

            # Émettre le signal
            self.filter_applied.emit("Tous les filtres supprimés")

    @service_operation("basculement_filtre_incomplet")
    def toggle_incomplete_filter(self):
        """Activer/désactiver le filtre lignes incomplètes"""
        self.incomplete_filter_active = not self.incomplete_filter_active

        status = 'activé' if self.incomplete_filter_active else 'désactivé'
        self.log_operation("toggle_incomplete_filter", f"Filtre incomplet: {status}", "debug")

        # Recharger avec le nouveau filtre
        self._reload_with_current_filters()

        # Émettre le signal
        filter_desc = f"Filtre lignes incomplètes {status}"
        self.filter_applied.emit(filter_desc)

    def _reload_with_current_filters(self):
        """Recharger les données avec les filtres et tri actuels"""
        try:
            # Obtenir le terme de recherche actuel depuis la fenêtre parent
            search_term = None
            if (hasattr(self.parent_window, 'advanced_search_service') and
                self.parent_window.advanced_search_service):
                search_term = self.parent_window.advanced_search_service.get_current_search_term_with_fallback(
                    self.parent_window)

            # Passer les filtres au TableController
            if hasattr(self.table_controller, 'load_data'):
                # Mettre à jour les filtres dans le contrôleur
                if hasattr(self.table_controller, 'column_filters'):
                    self.table_controller.column_filters = self.active_column_filters.copy()
                if hasattr(self.table_controller, 'incomplete_filter'):
                    self.table_controller.incomplete_filter = self.incomplete_filter_active

                # Charger les données
                self.table_controller.load_data(search_term, is_search=bool(search_term))

        except Exception as e:
            self.handle_error(e, "rechargement avec filtres")
