"""
Service de navigation et pagination
Centralise toute la logique de navigation entre pages et gestion de la pagination
"""

from typing import Optional, Callable, Dict, Any
from ..ui.qt_imports import QWidget, QLabel, QPushButton, QComboBox, QObject, pyqtSignal

from ..core.logger import app_logger
from ..core.constants import UIConfig
from .base_service import BaseService
from ..utils.error_handler import handle_navigation_errors

class NavigationService(QObject):
    """Service centralisé pour la gestion de la navigation et pagination"""
    
    # Signaux pour notifier les changements
    page_changed = pyqtSignal(int)  # nouvelle page
    page_size_changed = pyqtSignal(int)  # nouvelle taille de page
    navigation_requested = pyqtSignal(str)  # direction: 'next', 'previous', 'first', 'last'
    
    def __init__(self, table_controller, parent=None):
        super().__init__(parent)
        self._base_service = BaseService(parent_window=parent)
        self.table_controller = table_controller
        self.parent_window = parent
        
        # État de la pagination
        self.current_page = 1
        self.page_size = UIConfig.DEFAULT_PAGE_SIZE
        self.total_rows = 0
        
        # Widgets de pagination (seront définis par set_pagination_widgets)
        self.page_label = None
        self.prev_button = None
        self.next_button = None
        self.page_size_combo = None
        # Saut de page direct (optionnels)
        self.page_input = None          # QLineEdit éditable : numéro de page courant
        self.page_total_label = None    # QLabel "/ N"
        self.first_button = None        # ««
        self.last_button = None         # »»

    def set_pagination_widgets(self, page_label: QLabel, prev_button: QPushButton,
                              next_button: QPushButton, page_size_combo: QComboBox,
                              first_button: QPushButton = None, last_button: QPushButton = None,
                              page_input=None, page_total_label: QLabel = None):
        """Configurer les widgets de pagination.

        `page_label` reste accepté pour compatibilité ; si `page_input` +
        `page_total_label` sont fournis, le saut de page direct est activé.
        """
        self.page_label = page_label
        self.prev_button = prev_button
        self.next_button = next_button
        self.page_size_combo = page_size_combo
        self.first_button = first_button
        self.last_button = last_button
        self.page_input = page_input
        self.page_total_label = page_total_label

        # Connecter les signaux
        if self.prev_button:
            self.prev_button.clicked.connect(self.previous_page)
        if self.next_button:
            self.next_button.clicked.connect(self.next_page)
        if self.first_button:
            self.first_button.clicked.connect(self.go_to_first_page)
        if self.last_button:
            self.last_button.clicked.connect(self.go_to_last_page)
        if self.page_input is not None:
            # Saut quand l'utilisateur valide (Entrée ou perte de focus)
            self.page_input.editingFinished.connect(self._submit_page_input)
        if self.page_size_combo:
            self.page_size_combo.currentTextChanged.connect(self.change_page_size)

    def _submit_page_input(self):
        """Aller à la page saisie dans le champ (clampée ; restaurée si invalide)."""
        if self.page_input is None:
            return
        text = self.page_input.text().strip()
        try:
            page = int(text)
        except (ValueError, TypeError):
            # Saisie invalide : restaurer l'affichage courant
            self.update_pagination_controls()
            return
        # go_to_page clampe déjà à [1, total_pages] ; on rafraîchit ensuite pour
        # refléter la valeur réellement atteinte (ex. saisie hors bornes)
        self.go_to_page(page)
        self.update_pagination_controls()
            
    def update_total_rows(self, total_rows: int):
        """Mettre à jour le nombre total de lignes"""
        self.total_rows = total_rows
        self.update_pagination_controls()
        
    def get_total_pages(self) -> int:
        """Calculer le nombre total de pages"""
        if self.total_rows <= 0 or self.page_size <= 0 or self.page_size == -1:
            return 1  # Mode "Tout" = 1 page ou cas limite
        return (self.total_rows + self.page_size - 1) // self.page_size
        
    def next_page(self):
        """Aller à la page suivante"""
        total_pages = self.get_total_pages()
        if self.current_page < total_pages:
            self.go_to_page(self.current_page + 1)
            self.navigation_requested.emit("next")
                    
    def previous_page(self):
        """Aller à la page précédente"""
        if self.current_page > 1:
            self.go_to_page(self.current_page - 1)
            self.navigation_requested.emit("previous")
            
    def go_to_page(self, page: int):
        """Aller à une page spécifique (page base 1)"""
        total_pages = self.get_total_pages()
        if 1 <= page <= total_pages:
            self.current_page = page
            if hasattr(self.table_controller, 'current_page'):
                self.table_controller.current_page = page
            # Recharger avec le terme de recherche courant
            if hasattr(self.table_controller, 'load_data'):
                search_term = getattr(self.table_controller, 'current_search_term', None)
                self.table_controller.load_data(search_term)
            self.update_pagination_controls()
            self.page_changed.emit(page)
            app_logger.debug(f"Navigation vers page {page}/{total_pages}")
                
    def go_to_first_page(self):
        """Aller à la première page"""
        self.go_to_page(1)
        self.navigation_requested.emit("first")
        
    def go_to_last_page(self):
        """Aller à la dernière page"""
        total_pages = self.get_total_pages()
        self.go_to_page(total_pages)
        self.navigation_requested.emit("last")
            
    @handle_navigation_errors()
    def change_page_size(self, size_text: str):
        """Changer la taille de page"""
        if size_text == "Tout":
            new_size = -1  # Utiliser -1 comme TableController
            show_all = True
        else:
            new_size = int(size_text)
            show_all = False

        if new_size != self.page_size:
            self.page_size = new_size

            # Mettre à jour le contrôleur de table
            if hasattr(self.table_controller, 'page_size'):
                self.table_controller.page_size = new_size

            # Réinitialiser à la première page lors du changement de taille
            self.current_page = 1
            if hasattr(self.table_controller, 'current_page'):
                self.table_controller.current_page = 1

            # Recharger les données avec le terme de recherche courant
            if hasattr(self.table_controller, 'load_data'):
                # Utiliser la méthode centralisée pour récupérer le terme de recherche
                search_term = None
                if (hasattr(self.parent_window, 'advanced_search_service') and
                    hasattr(self.parent_window.advanced_search_service, 'get_current_search_term_with_fallback')):
                    search_term = self.parent_window.advanced_search_service.get_current_search_term_with_fallback(self.parent_window)
                else:
                    # Fallback vers current_search_term du table_controller
                    search_term = getattr(self.table_controller, 'current_search_term', None)

                self.table_controller.load_data(search_term)
            self.update_pagination_controls()

            # Émettre le signal
            self.page_size_changed.emit(new_size)

            # Notifier le parent si nécessaire
            if hasattr(self.parent_window, 'incomplete_button_service'):
                self.parent_window.incomplete_button_service.invalidate_cache("changement pagination")
            elif hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                self.parent_window._update_incomplete_button_visibility()

            app_logger.debug(f"Taille de page changée: {new_size} ({'Tout' if show_all else 'Paginé'})")
            
    @handle_navigation_errors()
    def update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination"""
        if not all([self.prev_button, self.next_button]):
            return

        current_page = self.current_page
        total_pages = self.get_total_pages()
        if self.total_rows == 0:
            current_page, total_pages = 1, 1

        # Saut de page direct (champ éditable + total) si présent, sinon label texte
        if self.page_input is not None:
            # blockSignals : éviter de redéclencher editingFinished pendant la MAJ
            blocked = self.page_input.blockSignals(True)
            self.page_input.setText(str(current_page))
            self.page_input.blockSignals(blocked)
            if self.page_total_label is not None:
                self.page_total_label.setText(f"/ {total_pages}")
        elif self.page_label:
            self.page_label.setText(f"Page {current_page} sur {total_pages}")

        # Activation/désactivation des boutons
        self.prev_button.setEnabled(current_page > 1)
        self.next_button.setEnabled(current_page < total_pages)
        if self.first_button:
            self.first_button.setEnabled(current_page > 1)
        if self.last_button:
            self.last_button.setEnabled(current_page < total_pages)

        app_logger.debug(f"Contrôles pagination mis à jour: {current_page}/{total_pages}")
            
    def get_current_page_info(self) -> Dict[str, Any]:
        """Obtenir les informations de la page courante"""
        current_page = self.current_page
        total_pages = self.get_total_pages()

        # Protection pour les cas limites
        if self.page_size <= 0:
            start_row = 1
            end_row = self.total_rows
        else:
            start_row = ((current_page - 1) * self.page_size) + 1
            end_row = min(current_page * self.page_size, self.total_rows)

        return {
            'current_page': current_page,
            'total_pages': total_pages,
            'page_size': self.page_size,
            'total_rows': self.total_rows,
            'start_row': start_row,
            'end_row': end_row
        }
        
    def reset_pagination(self):
        """Réinitialiser la pagination à l'état initial"""
        self.current_page = 1
        self.total_rows = 0
        if hasattr(self.table_controller, 'current_page'):
            self.table_controller.current_page = 1
        
    def handle_navigation_shortcut(self, key_combination: str):
        """Gérer les raccourcis clavier de navigation"""
        shortcuts_map = {
            'Ctrl+Right': self.next_page,
            'Ctrl+Left': self.previous_page,
            'Ctrl+Home': self.go_to_first_page,
            'Ctrl+End': self.go_to_last_page
        }
        
        if key_combination in shortcuts_map:
            shortcuts_map[key_combination]()
            return True
        return False