"""
Service Drag Handle - Phase 2.18 Refactoring
Extrait de main_refactored.py pour centraliser la logique de glisser-déposer

Responsabilités:
- Gestion de la poignée drag & drop pour recopie de cellules
- Gestion du défilement automatique durant le drag
- Duplication automatique vers le bas/haut avec patterns
- Optimisation des performances avec throttling
- Intégration avec l'historique des actions utilisateur
"""

import time
from typing import Optional

from PyQt5.QtCore import QItemSelection, QItemSelectionModel
from ..ui.qt_imports import (QWidget, Qt, QTimer, QPainter, QPen, QColor)

from ..core.config import Config
from ..core.logger import app_logger
from ..utils.error_handler import handle_drag_operation_errors

class DragHandle(QWidget):
    """Poignée de glisser-déposer pour la recopie de cellules"""
    
    def __init__(self, parent=None, table=None, main_window=None):
        super().__init__(parent)
        self.table = table
        self.main_window = main_window
        self.setFixedSize(Config.DRAG_HANDLE_SIZE, Config.DRAG_HANDLE_SIZE)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Tirer pour recopier | Double-clic pour remplir automatiquement vers le bas (ou vers le haut si le bas est déjà rempli)")
        self.dragging = False
        self.start_pos = None
        self.orig_selection = None
        self.drag_direction = None
        self.history_pending = False
        self.modified_rows_set = set()  # Tracker les lignes réellement modifiées

        # Variables pour le défilement automatique
        self.auto_scroll_timer = None
        self.auto_scroll_direction = None
        self.auto_scroll_zone = 50  # pixels depuis le bord pour déclencher le défilement
        
        # Variables pour optimiser les performances
        self.last_update_time = 0
        self.update_throttle_ms = 50  # Limite les mises à jour à 20 FPS

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(Qt.black))
        painter.setBrush(QColor(*Config.DRAG_HANDLE_COLOR))
        painter.drawRect(0, 0, Config.DRAG_HANDLE_SIZE - 1, Config.DRAG_HANDLE_SIZE - 1)

    # ── Helpers d'accès table unifiés (QTableWidget / QTableView) ───────────

    def _read_cell(self, row: int, col: int) -> str:
        """Lire la valeur d'une cellule depuis le modèle."""
        model = self.table.model()
        return (model.data(model.index(row, col), Qt.DisplayRole) or "") if model else ""

    def _write_cell(self, row: int, col: int, value: str) -> bool:
        """Écrire une valeur dans une cellule via model.setData() → émet cell_edited → sauvegarde auto."""
        model = self.table.model()
        if not model:
            return False
        idx = model.index(row, col)
        return bool(
            idx.isValid()
            and (model.flags(idx) & Qt.ItemIsEditable)
            and model.setData(idx, value, Qt.EditRole)
        )

    def _get_current_selection(self):
        """Retourne la sélection courante (objet avec topRow/bottomRow/leftColumn/rightColumn), ou None."""
        sm = self.table.selectionModel()
        if not sm or not sm.hasSelection():
            return None
        indexes = sm.selectedIndexes()
        if not indexes:
            return None
        rows = [idx.row() for idx in indexes]
        cols = [idx.column() for idx in indexes]
        from ..ui.custom_table_view import _SelectionRangeCompat
        return _SelectionRangeCompat(min(rows), min(cols), max(rows), max(cols))

    def _apply_selection(self, top: int, left: int, bottom: int, right: int) -> None:
        """Sélectionner une plage de cellules via QItemSelection."""
        model = self.table.model()
        sm = self.table.selectionModel()
        if not model or not sm:
            return
        sel = QItemSelection(model.index(top, left), model.index(bottom, right))
        sm.select(sel, QItemSelectionModel.ClearAndSelect)

    # ────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Vérifier si la sélection contient des colonnes interdites (C=2, D=3)
            current_sel = self._get_current_selection()
            if current_sel:
                forbidden_cols = {2, 3, 4}  # Colonnes C, D et E (références importantes)
                selected_cols = set(range(current_sel.leftColumn(), current_sel.rightColumn() + 1))
                if forbidden_cols.intersection(selected_cols):
                    return

            self.dragging = True
            self.start_pos = event.globalPos()
            self.orig_selection = self._get_current_selection()
            self.drag_direction = None
            self.modified_rows_set.clear()  # Réinitialiser le tracker de lignes modifiées
            # Ne pas bloquer les signaux pour permettre la capture de l'historique
            # self.table.blockSignals(True)

    def mouseMoveEvent(self, event):
        if not self.dragging or not self.orig_selection or self.table.rowCount() == 0:
            return

        # Throttle des mises à jour pour éviter les gels
        current_time = time.time() * 1000
        if current_time - self.last_update_time < self.update_throttle_ms:
            return
        self.last_update_time = current_time

        # Stocker la position actuelle pour la duplication continue
        self.last_mouse_pos = event.globalPos()

        # Vérifier si le défilement automatique est nécessaire
        self._check_auto_scroll(event)

        delta_y = event.globalPos().y() - self.start_pos.y()
        row_height = self.table.rowHeight(0) or 24
        
        if abs(delta_y) > row_height / 2:
            self._handle_drag_fill(delta_y, row_height)

    def _handle_drag_fill(self, delta_y: int, row_height: int):
        """Gérer le remplissage par glisser-déposer"""
        if delta_y > 0:  # Vers le bas
            self.drag_direction = "down"
            num_rows_to_fill = max(1, round(delta_y / row_height))
            self._fill_cells_down(num_rows_to_fill)
        else:  # Vers le haut
            self.drag_direction = "up"
            num_rows_to_fill = max(1, round(-delta_y / row_height))
            self._fill_cells_up(num_rows_to_fill)

    def _fill_cells_down(self, num_rows: int):
        """Remplir les cellules vers le bas"""
        if num_rows <= 0 or not self.orig_selection:
            return

        # Récupérer les valeurs source (en excluant la colonne Nb Pièces)
        source_data = []
        for row in range(self.orig_selection.topRow(), self.orig_selection.bottomRow() + 1):
            row_data = []
            for col in range(self.orig_selection.leftColumn(), self.orig_selection.rightColumn() + 1):
                if col == 5:  # Colonne Nb Pièces - ne pas copier
                    continue
                row_data.append((col, self._read_cell(row, col)))
            source_data.append(row_data)

        source_height = len(source_data)
        dest_start_row = self.orig_selection.bottomRow() + 1
        dest_end_row = min(dest_start_row + num_rows - 1, self.table.rowCount() - 1)

        duplicated_cells = 0

        for dest_row in range(dest_start_row, dest_end_row + 1):
            source_row_idx = (dest_row - dest_start_row) % source_height
            row_modified = False
            for dest_col, source_value in source_data[source_row_idx]:
                if dest_col == 5:
                    continue
                if self._write_cell(dest_row, dest_col, source_value):
                    duplicated_cells += 1
                    row_modified = True
            if row_modified:
                self.modified_rows_set.add(dest_row)

        if duplicated_cells > 0:
            self.history_pending = True

        if dest_end_row >= dest_start_row:
            self._apply_selection(
                self.orig_selection.topRow(), self.orig_selection.leftColumn(),
                dest_end_row, self.orig_selection.rightColumn()
            )

    def _fill_cells_up(self, num_rows: int):
        """Remplir les cellules vers le haut"""
        if num_rows <= 0 or not self.orig_selection:
            return

        # Récupérer les valeurs source (en excluant la colonne Nb Pièces)
        source_data = []
        for row in range(self.orig_selection.topRow(), self.orig_selection.bottomRow() + 1):
            row_data = []
            for col in range(self.orig_selection.leftColumn(), self.orig_selection.rightColumn() + 1):
                if col == 5:  # Colonne Nb Pièces - ne pas copier
                    continue
                row_data.append((col, self._read_cell(row, col)))
            source_data.append(row_data)

        source_height = len(source_data)
        dest_end_row = self.orig_selection.topRow() - 1
        dest_start_row = max(dest_end_row - num_rows + 1, 0)

        duplicated_cells = 0

        for dest_row in range(dest_start_row, dest_end_row + 1):
            distance = dest_end_row - dest_row
            source_row_idx = distance % source_height
            row_modified = False
            for dest_col, source_value in source_data[source_row_idx]:
                if dest_col == 5:
                    continue
                if self._write_cell(dest_row, dest_col, source_value):
                    duplicated_cells += 1
                    row_modified = True
            if row_modified:
                self.modified_rows_set.add(dest_row)

        if duplicated_cells > 0:
            self.history_pending = True

        if dest_start_row <= dest_end_row:
            self._apply_selection(
                dest_start_row, self.orig_selection.leftColumn(),
                self.orig_selection.bottomRow(), self.orig_selection.rightColumn()
            )

    def mouseReleaseEvent(self, event):
        if not self.dragging:
            return

        # Sauvegarder et ajouter à l'historique uniquement au relâchement (pour drag, pas double-clic)
        if self.history_pending and self.main_window and self.drag_direction:
            direction_text = "vers le bas" if self.drag_direction == "down" else "vers le haut"
            self.main_window.user_interaction_service.add_to_history(f"Duplication {direction_text}")
            # Sauvegarder les modifications dans la base de données
            self.main_window._save_drag_changes()

            # Plus besoin de recharger la colonne Nb Pièces (supprimée)

        self.dragging = False
        self.history_pending = False
        self.drag_direction = None
        self.modified_rows_set.clear()  # Nettoyer le tracker après sauvegarde

        # Arrêter le défilement automatique
        self._stop_auto_scroll()
    
    def mouseDoubleClickEvent(self, event):
        """Gérer le double-clic sur la poignée pour duplication automatique (bas, sinon haut)"""
        if event.button() != Qt.LeftButton:
            return

        selection = self._get_current_selection()
        if not selection:
            return

        # Vérifier si la sélection contient des colonnes interdites (C=2, D=3, E=4)
        forbidden_cols = {2, 3, 4}
        selected_cols = set(range(selection.leftColumn(), selection.rightColumn() + 1))
        if forbidden_cols.intersection(selected_cols):
            return

        self._auto_fill()
    
    def _auto_fill(self):
        """Dupliquer automatiquement jusqu'aux cellules non vides.

        Vers le bas d'abord (comportement historique). Vers le haut seulement
        si rien n'est à remplir en bas : case du dessous déjà remplie, ou
        sélection sur la dernière ligne chargée.
        """
        selection = self._get_current_selection()
        if not selection:
            return

        # Collecter les données source
        source_data = []
        for row in range(selection.topRow(), selection.bottomRow() + 1):
            row_data = []
            for col in range(selection.leftColumn(), selection.rightColumn() + 1):
                row_data.append((col, self._read_cell(row, col)))
            source_data.append(row_data)

        if not source_data:
            return

        source_row_count = len(source_data)

        start_row = selection.bottomRow() + 1
        end_row = self._find_fill_end_row(selection, start_row)

        if start_row <= end_row:
            direction_text = "vers le bas"
            # Ligne de destination → index source : le motif se prolonge depuis le haut
            dest_rows = [(row, (row - start_row) % source_row_count)
                         for row in range(start_row, end_row + 1)]
            sel_top, sel_bottom = selection.topRow(), end_row
        else:
            end_row = selection.topRow() - 1
            start_row = self._find_fill_start_row_up(selection, end_row)
            if start_row > end_row:
                return
            direction_text = "vers le haut"
            # Distance d (0 = juste au-dessus) → source[(N - 1 - d) % N] :
            # le motif A, B se prolonge en … A, B au-dessus de la sélection.
            dest_rows = [(row, (source_row_count - 1 - (end_row - row)) % source_row_count)
                         for row in range(start_row, end_row + 1)]
            sel_top, sel_bottom = start_row, selection.bottomRow()

        duplicated_cells = 0
        modified_rows = []

        for dest_row, source_row_idx in dest_rows:
            row_modified = False
            for col_idx, source_value in source_data[source_row_idx]:
                if dest_row < self.table.rowCount():
                    if self._write_cell(dest_row, col_idx, source_value):
                        duplicated_cells += 1
                        row_modified = True
            if row_modified:
                modified_rows.append(dest_row)

        if duplicated_cells > 0 and self.main_window:
            self._apply_selection(
                sel_top, selection.leftColumn(),
                sel_bottom, selection.rightColumn()
            )
            self.main_window.user_interaction_service.add_to_history(
                f"Duplication automatique {direction_text}")
            self._save_auto_fill_changes(modified_rows, selection.leftColumn(), selection.rightColumn())
    
    @handle_drag_operation_errors()
    def _save_auto_fill_changes(self, modified_rows, start_col, end_col):
        """Sauvegarder uniquement les cellules modifiées par auto-fill (double-clic)"""
        # Suspendre les invalidations de cache pendant l'auto-fill
        if hasattr(self.main_window, 'db_manager'):
            cache_service = getattr(self.main_window.db_manager, 'cache_invalidation', None)
            if cache_service:
                cache_service.suspend_invalidation("auto-fill double-clic")

        # Note: try/finally nécessaire pour garantir la reprise des invalidations
        try:
            cells_to_clean = set()  # Cellules à nettoyer de modified_cells

            for row in modified_rows:
                for col in range(start_col, end_col + 1):
                    cells_to_clean.add((row, col))

            save_service = getattr(self.main_window, 'event_driven_save_service', None)
            if save_service and cells_to_clean:
                # Sauvegarde en une seule transaction (évite un commit SQLite par cellule)
                save_service.save_cells_batch_immediate(cells_to_clean)

            # Nettoyer les cellules de modified_cells pour éviter les sauvegardes répétées
            if hasattr(self.main_window, 'modified_cells') and cells_to_clean:
                for cell_coords in cells_to_clean:
                    self.main_window.modified_cells.discard(cell_coords)

        finally:
            # Reprendre les invalidations avec une invalidation globale
            if hasattr(self.main_window, 'db_manager'):
                cache_service = getattr(self.main_window.db_manager, 'cache_invalidation', None)
                if cache_service:
                    cache_service.resume_invalidation(force_invalidate=True)

    def _find_fill_end_row(self, selection, start_row):
        """Trouver la dernière ligne à remplir (tant que les cellules sont vides dans la sélection)"""
        for row in range(start_row, self.table.rowCount()):
            has_non_empty = any(
                self._read_cell(row, col).strip()
                for col in range(selection.leftColumn(), selection.rightColumn() + 1)
            )
            if has_non_empty:
                return row - 1
        return self.table.rowCount() - 1
    
    def _find_fill_start_row_up(self, selection, end_row):
        """Trouver la première ligne à remplir vers le haut (tant que les cellules sont vides dans la sélection)"""
        for row in range(end_row, -1, -1):
            has_non_empty = any(
                self._read_cell(row, col).strip()
                for col in range(selection.leftColumn(), selection.rightColumn() + 1)
            )
            if has_non_empty:
                return row + 1
        return 0
    
    def _check_auto_scroll(self, event):
        """Vérifier si le défilement automatique est nécessaire"""
        if not self.table:
            return
        
        # Convertir la position globale en position locale du viewport
        viewport_pos = self.table.viewport().mapFromGlobal(event.globalPos())
        viewport_rect = self.table.viewport().rect()
        
        # Zone étendue plus large pour éviter l'arrêt quand la souris sort
        extended_rect = viewport_rect.adjusted(-60, -60, 60, 60)  # Zone étendue augmentée
        
        if extended_rect.contains(viewport_pos):
            # Calculer la distance du bord pour ajuster la vitesse
            if viewport_pos.y() < self.auto_scroll_zone:
                # Zone de défilement vers le haut
                distance_from_edge = max(0, viewport_pos.y())
                speed = max(15, 80 - (distance_from_edge * 2))  # Plus rapide
                self._start_auto_scroll('up', speed)
            elif viewport_pos.y() > viewport_rect.height() - self.auto_scroll_zone:
                # Zone de défilement vers le bas
                distance_from_edge = max(0, viewport_rect.height() - viewport_pos.y())
                speed = max(15, 80 - (distance_from_edge * 2))  # Plus rapide
                self._start_auto_scroll('down', speed)
            else:
                # Arrêter le défilement si on n'est plus dans une zone de défilement
                self._stop_auto_scroll()
        else:
            # Arrêter le défilement si on sort de la zone étendue
            self._stop_auto_scroll()
    
    def _start_auto_scroll(self, direction, speed=100):
        """Démarrer le défilement automatique"""
        if self.auto_scroll_direction == direction and self.auto_scroll_timer:
            # Ajuster la vitesse si nécessaire
            if hasattr(self, 'current_scroll_speed') and self.current_scroll_speed != speed:
                self.auto_scroll_timer.setInterval(speed)
                self.current_scroll_speed = speed
            return
        
        # Arrêter l'ancien timer s'il existe
        self._stop_auto_scroll()
        
        self.auto_scroll_direction = direction
        self.current_scroll_speed = speed
        self.auto_scroll_timer = QTimer()
        self.auto_scroll_timer.timeout.connect(self._auto_scroll_step)
        self.auto_scroll_timer.start(speed)
    
    def _stop_auto_scroll(self):
        """Arrêter le défilement automatique"""
        if self.auto_scroll_timer:
            self.auto_scroll_timer.stop()
            self._safe_disconnect_timer()
            self.auto_scroll_timer.deleteLater()
            self.auto_scroll_timer = None

    @handle_drag_operation_errors()
    def _safe_disconnect_timer(self):
        """Déconnecter le timer de manière sécurisée"""
        self.auto_scroll_timer.disconnect()
        self.auto_scroll_direction = None
        # Forcer le nettoyage
        if hasattr(self, 'current_scroll_speed'):
            delattr(self, 'current_scroll_speed')
    
    def _auto_scroll_step(self):
        """Effectuer une étape de défilement automatique"""
        if not self.table or not self.auto_scroll_direction or not self.dragging:
            # Arrêter le défilement si les conditions ne sont plus remplies
            self._stop_auto_scroll()
            return
        
        scroll_bar = self.table.verticalScrollBar()
        current_value = scroll_bar.value()
        
        # Défilement plus rapide pour une meilleure réactivité
        step_size = 8  # Augmenter le pas de défilement pour plus de rapidité
        
        if self.auto_scroll_direction == 'up':
            new_value = max(0, current_value - step_size)
        else:  # down
            new_value = min(scroll_bar.maximum(), current_value + step_size)
        
        if new_value != current_value:
            scroll_bar.setValue(new_value)
            
            # Continuer la duplication pendant le défilement
            if self.dragging and self.orig_selection:
                self._continue_drag_fill()
            
            # Repositionner la poignée après le défilement
            if self.main_window and hasattr(self.main_window, '_position_drag_handle'):
                self.main_window._position_drag_handle()
        else:
            # Si on ne peut plus défiler, arrêter le défilement automatique
            self._stop_auto_scroll()
    
    @handle_drag_operation_errors()
    def _continue_drag_fill(self):
        """Continuer la duplication pendant le défilement"""
        # Recalculer la position pour continuer la duplication
        if hasattr(self, 'last_mouse_pos') and self.start_pos:
            # Simuler un mouseMoveEvent pour continuer la duplication
            delta_y = self.last_mouse_pos.y() - self.start_pos.y()
            row_height = self.table.rowHeight(0) or 24

            if abs(delta_y) > row_height / 2:
                self._handle_drag_fill(delta_y, row_height)

class DragHandleService:
    """
    Service pour la gestion des poignées de glisser-déposer
    
    Responsabilités:
    - Créer et configurer les poignées de drag & drop
    - Connecter les poignées aux tables et fenêtres principales
    - Gérer le cycle de vie des composants drag & drop
    """
    
    def __init__(self):
        pass
    
    def create_drag_handle(self, parent=None, table=None, main_window=None) -> DragHandle:
        """
        Créer une poignée de glisser-déposer configurée
        
        Args:
            parent: Widget parent
            table: Table associée à la poignée
            main_window: Fenêtre principale pour l'historique
        
        Returns:
            DragHandle: Poignée configurée avec tous les événements
        """
        handle = DragHandle(parent=parent, table=table, main_window=main_window)
        return handle