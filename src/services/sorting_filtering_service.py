"""
Service de gestion du tri et filtrage de table
Extrait de main_refactored.py pour centraliser la logique de tri et filtrage
"""

from typing import Optional, Dict, Any
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QTableWidget

from ..core.logger import app_logger
from ..core.config import Config


class SortingFilteringService(QObject):
    """Service centralisé pour le tri et filtrage de table"""

    # Signaux pour notifier les changements
    sort_changed = pyqtSignal(int, Qt.SortOrder)  # column, order
    filter_applied = pyqtSignal(str)  # filter_description

    def __init__(self, table_widget: QTableWidget, table_controller, parent=None):
        super().__init__(parent)
        self.table = table_widget
        self.table_controller = table_controller
        self.parent_window = parent

        # État du tri
        self.current_sort_column = -1
        self.current_sort_order = Qt.SortOrder.AscendingOrder

        # Filtres de colonne avec debounce
        self.column_filter_timer = QTimer()
        self.column_filter_timer.timeout.connect(self._perform_delayed_column_filter)
        self.column_filter_timer.setSingleShot(True)
        self.pending_column_filter = {'column': None, 'text': ''}

        # État des filtres
        self.active_column_filters = {}  # {column_index: filter_text}
        self.incomplete_filter_active = False

    def setup_sorting(self):
        """Configurer le tri sur la table"""
        try:
            # Connecter le signal de clic sur header
            if hasattr(self.table, 'horizontalHeader'):
                header = self.table.horizontalHeader()
                header.sectionClicked.connect(self.on_header_clicked)
                app_logger.debug("Tri configuré sur la table")
        except Exception as e:
            app_logger.error(f"Erreur configuration tri: {e}")

    def on_header_clicked(self, logical_index: int):
        """Gérer le clic sur un header pour trier"""
        try:
            # Déterminer l'ordre de tri
            if self.current_sort_column == logical_index:
                # Basculer l'ordre si même colonne
                if self.current_sort_order == Qt.SortOrder.AscendingOrder:
                    self.current_sort_order = Qt.SortOrder.DescendingOrder
                else:
                    self.current_sort_order = Qt.SortOrder.AscendingOrder
            else:
                # Nouvelle colonne, commencer par ASC
                self.current_sort_column = logical_index
                self.current_sort_order = Qt.SortOrder.AscendingOrder

            # Appliquer le tri
            self.apply_database_sort()

            # Émettre le signal
            self.sort_changed.emit(self.current_sort_column, self.current_sort_order)

        except Exception as e:
            app_logger.error(f"Erreur lors du tri: {e}")

    def apply_database_sort(self):
        """Appliquer le tri via une nouvelle requête SQL"""
        try:
            # Mettre à jour les indicateurs visuels
            self.update_sort_indicators()

            # Synchroniser avec TableController
            if hasattr(self.table_controller, 'current_sort_column'):
                self.table_controller.current_sort_column = self.current_sort_column
                self.table_controller.current_sort_order = self.current_sort_order

            # Recharger les données avec le tri
            self._reload_with_current_filters()

            app_logger.debug(f"Tri appliqué: colonne {self.current_sort_column}, ordre {self.current_sort_order}")

        except Exception as e:
            app_logger.error(f"Erreur lors de l'application du tri: {e}")

    def update_sort_indicators(self):
        """Mettre à jour les indicateurs de tri dans les en-têtes"""
        try:
            # Récupérer les en-têtes originaux
            original_headers = Config.DB_HEADERS + ["Nb Pièces"]

            # Mettre à jour tous les en-têtes
            for i, header_text in enumerate(original_headers):
                if i == self.current_sort_column:
                    # Ajouter la flèche pour la colonne triée
                    if self.current_sort_order == Qt.SortOrder.AscendingOrder:
                        arrow = " ↑"
                    else:
                        arrow = " ↓"
                    new_header = f"{header_text}{arrow}"
                else:
                    new_header = header_text

                self.table.setHorizontalHeaderItem(i,
                    self.table.horizontalHeaderItem(i).__class__(new_header))

        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateurs tri: {e}")

    def apply_column_filter(self, column_index: int, filter_text: str):
        """Appliquer un filtre sur une colonne avec debounce"""
        try:
            # Sauvegarder le filtre en attente
            self.pending_column_filter = {
                'column': column_index,
                'text': filter_text.strip()
            }

            # Redémarrer le timer de debounce
            self.column_filter_timer.start(300)  # 300ms de délai

        except Exception as e:
            app_logger.error(f"Erreur application filtre colonne: {e}")

    def _perform_delayed_column_filter(self):
        """Exécuter le filtrage de colonne après délai"""
        try:
            column = self.pending_column_filter['column']
            text = self.pending_column_filter['text']

            if column is not None:
                if text:
                    self.active_column_filters[column] = text
                    app_logger.debug(f"Filtre appliqué sur colonne {column}: '{text}'")
                else:
                    # Supprimer le filtre si texte vide
                    self.active_column_filters.pop(column, None)
                    app_logger.debug(f"Filtre supprimé sur colonne {column}")

                # Recharger avec les filtres
                self._reload_with_current_filters()

                # Émettre le signal
                filter_desc = f"Colonne {column}: {text}" if text else f"Filtre colonne {column} supprimé"
                self.filter_applied.emit(filter_desc)

        except Exception as e:
            app_logger.error(f"Erreur exécution filtre colonne: {e}")

    def clear_column_filters(self):
        """Nettoyer tous les filtres de colonnes"""
        try:
            if self.active_column_filters:
                self.active_column_filters.clear()
                app_logger.debug("Tous les filtres de colonnes supprimés")

                # Recharger sans filtres
                self._reload_with_current_filters()

                # Émettre le signal
                self.filter_applied.emit("Tous les filtres supprimés")

        except Exception as e:
            app_logger.error(f"Erreur suppression filtres: {e}")

    def toggle_incomplete_filter(self):
        """Activer/désactiver le filtre lignes incomplètes"""
        try:
            self.incomplete_filter_active = not self.incomplete_filter_active

            app_logger.debug(f"Filtre incomplet: {'activé' if self.incomplete_filter_active else 'désactivé'}")

            # Recharger avec le nouveau filtre
            self._reload_with_current_filters()

            # Émettre le signal
            filter_desc = "Filtre lignes incomplètes " + ("activé" if self.incomplete_filter_active else "désactivé")
            self.filter_applied.emit(filter_desc)

        except Exception as e:
            app_logger.error(f"Erreur basculement filtre incomplet: {e}")

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
            app_logger.error(f"Erreur rechargement avec filtres: {e}")

    def get_current_sort_state(self) -> Dict[str, Any]:
        """Obtenir l'état actuel du tri"""
        return {
            'column': self.current_sort_column,
            'order': self.current_sort_order,
            'column_name': Config.DB_HEADERS[self.current_sort_column] if (
                0 <= self.current_sort_column < len(Config.DB_HEADERS)
            ) else None
        }

    def get_active_filters(self) -> Dict[str, Any]:
        """Obtenir les filtres actifs"""
        return {
            'column_filters': self.active_column_filters.copy(),
            'incomplete_filter': self.incomplete_filter_active,
            'filter_count': len(self.active_column_filters) + (1 if self.incomplete_filter_active else 0)
        }

    def reset_sorting(self):
        """Réinitialiser le tri"""
        try:
            self.current_sort_column = -1
            self.current_sort_order = Qt.SortOrder.AscendingOrder

            # Mettre à jour les indicateurs
            self.update_sort_indicators()

            # Recharger sans tri
            self._reload_with_current_filters()

            app_logger.debug("Tri réinitialisé")

        except Exception as e:
            app_logger.error(f"Erreur réinitialisation tri: {e}")

    def set_sort(self, column: int, order: Qt.SortOrder):
        """Définir un tri spécifique"""
        try:
            self.current_sort_column = column
            self.current_sort_order = order

            # Appliquer le tri
            self.apply_database_sort()

        except Exception as e:
            app_logger.error(f"Erreur définition tri: {e}")