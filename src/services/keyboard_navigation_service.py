"""
Service de navigation clavier enhanced avec architecture modulaire
Gestion avancée des sélections multiples et compatibilité CellEditingService
"""

from typing import Optional, List, Tuple, Dict, Any
from PyQt5.QtWidgets import QTableWidget, QWidget
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtGui import QKeyEvent

from ..core.logger import app_logger


class NavigationMode:
    """Modes de navigation disponibles"""
    STANDARD = "standard"
    CELL_EDITING = "cell_editing"
    MULTI_SELECTION = "multi_selection"


class KeyboardNavigationService(QObject):
    """
    Service de navigation clavier enhanced avec architecture modulaire
    
    Architecture:
    - Modularité: Services séparés pour différents types de navigation
    - Compatibilité: Intégration avec CellEditingService existant
    - Extensibilité: Support pour nouveaux modes de navigation
    """
    
    # Signaux pour communication avec autres services
    navigation_requested = pyqtSignal(int, int)  # row, col
    selection_changed = pyqtSignal(list)  # selected_ranges
    cell_edit_requested = pyqtSignal(int, int)  # row, col
    
    def __init__(self, table_widget: QTableWidget, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.table = table_widget
        self.current_mode = NavigationMode.STANDARD
        
        # Configuration de navigation
        self.config = {
            'wrap_around': True,  # Retour au début/fin
            'skip_empty_cells': False,  # Passer les cellules vides
            'multi_select_enabled': True,  # Sélection multiple
            'edit_on_enter': True,  # Édition sur Entrée
        }
        
        # État de navigation
        self.navigation_state = {
            'last_position': (0, 0),
            'selection_anchor': None,
            'multi_select_active': False
        }
        
        # Mappings de touches personnalisables
        self.key_mappings = {
            Qt.Key_Up: self._navigate_up,
            Qt.Key_Down: self._navigate_down,
            Qt.Key_Left: self._navigate_left,
            Qt.Key_Right: self._navigate_right,
            Qt.Key_Home: self._navigate_home,
            Qt.Key_End: self._navigate_end,
            Qt.Key_PageUp: self._navigate_page_up,
            Qt.Key_PageDown: self._navigate_page_down,
            Qt.Key_Tab: self._navigate_tab,
            Qt.Key_Backtab: self._navigate_backtab,
            Qt.Key_Return: self._handle_enter,
            Qt.Key_Enter: self._handle_enter,
            Qt.Key_Escape: self._handle_escape,
            Qt.Key_Delete: self._handle_delete,
            Qt.Key_F2: self._handle_f2_edit,
        }
        
        app_logger.info("KeyboardNavigationService initialisé")
    
    def set_mode(self, mode: str) -> None:
        """Changer le mode de navigation"""
        if mode in [NavigationMode.STANDARD, NavigationMode.CELL_EDITING, NavigationMode.MULTI_SELECTION]:
            old_mode = self.current_mode
            self.current_mode = mode
            app_logger.debug(f"Mode navigation changé: {old_mode} → {mode}")
        else:
            app_logger.warning(f"Mode navigation invalide: {mode}")
    
    def handle_key_event(self, event: QKeyEvent) -> bool:
        """
        Gérer un événement clavier
        
        Returns:
            bool: True si l'événement a été traité, False sinon
        """
        try:
            key = event.key()
            modifiers = event.modifiers()
            
            # Gestion des modificateurs pour sélection multiple
            if modifiers & Qt.ShiftModifier:
                self._handle_shift_navigation(key, event)
                return True
            elif modifiers & Qt.ControlModifier:
                return self._handle_ctrl_navigation(key, event)
            elif key in self.key_mappings:
                # Navigation standard
                return self.key_mappings[key](event)
            
            return False
            
        except Exception as e:
            app_logger.error(f"Erreur navigation clavier: {e}")
            return False
    
    def _navigate_up(self, event: QKeyEvent) -> bool:
        """Navigation vers le haut"""
        current_row = self.table.currentRow()
        if current_row > 0:
            self._move_to_cell(current_row - 1, self.table.currentColumn())
        elif self.config['wrap_around']:
            self._move_to_cell(self.table.rowCount() - 1, self.table.currentColumn())
        return True
    
    def _navigate_down(self, event: QKeyEvent) -> bool:
        """Navigation vers le bas"""
        current_row = self.table.currentRow()
        if current_row < self.table.rowCount() - 1:
            self._move_to_cell(current_row + 1, self.table.currentColumn())
        elif self.config['wrap_around']:
            self._move_to_cell(0, self.table.currentColumn())
        return True
    
    def _navigate_left(self, event: QKeyEvent) -> bool:
        """Navigation vers la gauche"""
        current_col = self.table.currentColumn()
        if current_col > 0:
            self._move_to_cell(self.table.currentRow(), current_col - 1)
        elif self.config['wrap_around']:
            self._move_to_cell(self.table.currentRow(), self.table.columnCount() - 1)
        return True
    
    def _navigate_right(self, event: QKeyEvent) -> bool:
        """Navigation vers la droite"""
        current_col = self.table.currentColumn()
        if current_col < self.table.columnCount() - 1:
            self._move_to_cell(self.table.currentRow(), current_col + 1)
        elif self.config['wrap_around']:
            self._move_to_cell(self.table.currentRow(), 0)
        return True
    
    def _navigate_home(self, event: QKeyEvent) -> bool:
        """Navigation vers le début de ligne"""
        self._move_to_cell(self.table.currentRow(), 0)
        return True
    
    def _navigate_end(self, event: QKeyEvent) -> bool:
        """Navigation vers la fin de ligne"""
        self._move_to_cell(self.table.currentRow(), self.table.columnCount() - 1)
        return True
    
    def _navigate_page_up(self, event: QKeyEvent) -> bool:
        """Navigation page précédente"""
        current_row = self.table.currentRow()
        visible_rows = self.table.height() // self.table.rowHeight(0)
        new_row = max(0, current_row - visible_rows)
        self._move_to_cell(new_row, self.table.currentColumn())
        return True
    
    def _navigate_page_down(self, event: QKeyEvent) -> bool:
        """Navigation page suivante"""
        current_row = self.table.currentRow()
        visible_rows = self.table.height() // self.table.rowHeight(0)
        new_row = min(self.table.rowCount() - 1, current_row + visible_rows)
        self._move_to_cell(new_row, self.table.currentColumn())
        return True
    
    def _navigate_tab(self, event: QKeyEvent) -> bool:
        """Navigation Tab (cellule suivante)"""
        current_row = self.table.currentRow()
        current_col = self.table.currentColumn()
        
        if current_col < self.table.columnCount() - 1:
            self._move_to_cell(current_row, current_col + 1)
        elif current_row < self.table.rowCount() - 1:
            self._move_to_cell(current_row + 1, 0)
        elif self.config['wrap_around']:
            self._move_to_cell(0, 0)
        
        return True
    
    def _navigate_backtab(self, event: QKeyEvent) -> bool:
        """Navigation Shift+Tab (cellule précédente)"""
        current_row = self.table.currentRow()
        current_col = self.table.currentColumn()
        
        if current_col > 0:
            self._move_to_cell(current_row, current_col - 1)
        elif current_row > 0:
            self._move_to_cell(current_row - 1, self.table.columnCount() - 1)
        elif self.config['wrap_around']:
            self._move_to_cell(self.table.rowCount() - 1, self.table.columnCount() - 1)
        
        return True
    
    def _handle_enter(self, event: QKeyEvent) -> bool:
        """Gestion de la touche Entrée"""
        if self.config['edit_on_enter'] and self.current_mode != NavigationMode.CELL_EDITING:
            # Émettre signal pour édition de cellule
            self.cell_edit_requested.emit(self.table.currentRow(), self.table.currentColumn())
            return True
        else:
            # Navigation standard (ligne suivante)
            return self._navigate_down(event)
    
    def _handle_escape(self, event: QKeyEvent) -> bool:
        """Gestion de la touche Échap"""
        # Annuler sélection multiple ou sortir du mode édition
        if self.navigation_state['multi_select_active']:
            self.table.clearSelection()
            self.navigation_state['multi_select_active'] = False
            return True
        return False
    
    def _handle_delete(self, event: QKeyEvent) -> bool:
        """Gestion de la touche Suppr"""
        # Laisser l'application gérer la suppression
        return False
    
    def _handle_f2_edit(self, event: QKeyEvent) -> bool:
        """Gestion de F2 pour édition"""
        self.cell_edit_requested.emit(self.table.currentRow(), self.table.currentColumn())
        return True
    
    def _handle_shift_navigation(self, key: int, event: QKeyEvent) -> None:
        """Gestion de la navigation avec Shift (sélection multiple)"""
        if not self.config['multi_select_enabled']:
            return
        
        # Initialiser l'ancre de sélection si nécessaire
        if not self.navigation_state['multi_select_active']:
            self.navigation_state['selection_anchor'] = (self.table.currentRow(), self.table.currentColumn())
            self.navigation_state['multi_select_active'] = True
        
        # Effectuer la navigation
        if key == Qt.Key_Up:
            self._extend_selection_up()
        elif key == Qt.Key_Down:
            self._extend_selection_down()
        elif key == Qt.Key_Left:
            self._extend_selection_left()
        elif key == Qt.Key_Right:
            self._extend_selection_right()
    
    def _handle_ctrl_navigation(self, key: int, event: QKeyEvent) -> bool:
        """Gestion de la navigation avec Ctrl"""
        if key == Qt.Key_A:
            # Sélectionner tout
            self.table.selectAll()
            return True
        elif key == Qt.Key_Home:
            # Aller au début du document
            self._move_to_cell(0, 0)
            return True
        elif key == Qt.Key_End:
            # Aller à la fin du document
            self._move_to_cell(self.table.rowCount() - 1, self.table.columnCount() - 1)
            return True
        
        return False
    
    def _extend_selection_up(self) -> None:
        """Étendre la sélection vers le haut"""
        current_row = self.table.currentRow()
        if current_row > 0:
            self._extend_selection_to(current_row - 1, self.table.currentColumn())
    
    def _extend_selection_down(self) -> None:
        """Étendre la sélection vers le bas"""
        current_row = self.table.currentRow()
        if current_row < self.table.rowCount() - 1:
            self._extend_selection_to(current_row + 1, self.table.currentColumn())
    
    def _extend_selection_left(self) -> None:
        """Étendre la sélection vers la gauche"""
        current_col = self.table.currentColumn()
        if current_col > 0:
            self._extend_selection_to(self.table.currentRow(), current_col - 1)
    
    def _extend_selection_right(self) -> None:
        """Étendre la sélection vers la droite"""
        current_col = self.table.currentColumn()
        if current_col < self.table.columnCount() - 1:
            self._extend_selection_to(self.table.currentRow(), current_col + 1)
    
    def _extend_selection_to(self, row: int, col: int) -> None:
        """Étendre la sélection jusqu'à une position donnée"""
        if self.navigation_state['selection_anchor']:
            anchor_row, anchor_col = self.navigation_state['selection_anchor']
            
            # Sélectionner la plage
            top_row = min(anchor_row, row)
            bottom_row = max(anchor_row, row)
            left_col = min(anchor_col, col)
            right_col = max(anchor_col, col)
            
            # Appliquer la sélection
            self.table.setRangeSelected(
                self.table.itemSelectionRange(top_row, left_col, bottom_row, right_col),
                True
            )
            
            # Déplacer le curseur
            self.table.setCurrentCell(row, col)
    
    def _move_to_cell(self, row: int, col: int) -> None:
        """Déplacer le curseur vers une cellule"""
        if 0 <= row < self.table.rowCount() and 0 <= col < self.table.columnCount():
            self.table.setCurrentCell(row, col)
            self.navigation_state['last_position'] = (row, col)
            self.navigation_requested.emit(row, col)
    
    def get_selected_ranges(self) -> List[Tuple[int, int, int, int]]:
        """Obtenir les plages de sélection actuelle"""
        ranges = []
        selection_model = self.table.selectionModel()
        if selection_model:
            for range_item in selection_model.selectedRanges():
                ranges.append((
                    range_item.top(),
                    range_item.left(), 
                    range_item.bottom(),
                    range_item.right()
                ))
        return ranges
    
    def set_config(self, key: str, value: Any) -> None:
        """Modifier la configuration"""
        if key in self.config:
            self.config[key] = value
            app_logger.debug(f"Configuration navigation: {key} = {value}")
        else:
            app_logger.warning(f"Clé configuration inconnue: {key}")
    
    def reset_navigation_state(self) -> None:
        """Réinitialiser l'état de navigation"""
        self.navigation_state = {
            'last_position': (0, 0),
            'selection_anchor': None,
            'multi_select_active': False
        }
        app_logger.debug("État navigation réinitialisé")