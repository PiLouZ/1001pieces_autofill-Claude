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

from PyQt5.QtWidgets import (QWidget, QTableWidgetItem, QTableWidgetSelectionRange)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPen, QColor

from ..core.config import Config
from ..core.logger import app_logger

class DragHandle(QWidget):
    """Poignée de glisser-déposer pour la recopie de cellules"""
    
    def __init__(self, parent=None, table=None, main_window=None):
        super().__init__(parent)
        self.table = table
        self.main_window = main_window
        self.setFixedSize(Config.DRAG_HANDLE_SIZE, Config.DRAG_HANDLE_SIZE)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Tirer pour recopier | Double-clic pour remplir automatiquement vers le bas")
        self.dragging = False
        self.start_pos = None
        self.orig_selection = None
        self.drag_direction = None
        self.history_pending = False
        
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Vérifier si la sélection contient des colonnes interdites (C=2, D=3)
            if self.table.selectedRanges():
                selection = self.table.selectedRanges()[0]
                forbidden_cols = {2, 3, 4}  # Colonnes C, D et E (références importantes)
                selected_cols = set(range(selection.leftColumn(), selection.rightColumn() + 1))
                
                if forbidden_cols.intersection(selected_cols):
                    # Ne pas activer le drag sur les colonnes interdites
                    return
            
            self.dragging = True
            self.start_pos = event.globalPos()
            self.orig_selection = self.table.selectedRanges()[0] if self.table.selectedRanges() else None
            self.drag_direction = None
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
        
        # Récupérer les valeurs source une seule fois (en excluant la colonne Nb Pièces)
        source_data = []
        for row in range(self.orig_selection.topRow(), self.orig_selection.bottomRow() + 1):
            row_data = []
            for col in range(self.orig_selection.leftColumn(), self.orig_selection.rightColumn() + 1):
                if col == 5:  # Colonne Nb Pièces - ne pas copier
                    continue
                item = self.table.item(row, col)
                row_data.append((col, item.text() if item else ""))
            source_data.append(row_data)
        
        source_height = len(source_data)
        
        # Calculer la plage de destination
        dest_start_row = self.orig_selection.bottomRow() + 1
        dest_end_row = min(dest_start_row + num_rows - 1, self.table.rowCount() - 1)
        
        # Compter les cellules dupliquées
        duplicated_cells = 0
        
        # Remplir les cellules de destination
        for dest_row in range(dest_start_row, dest_end_row + 1):
            source_row_idx = (dest_row - dest_start_row) % source_height
            for dest_col, source_value in source_data[source_row_idx]:
                if dest_col == 5:  # Ne pas toucher à la colonne Nb Pièces
                    continue
                    
                # Créer et insérer l'item
                new_item = QTableWidgetItem(source_value)
                self.table.setItem(dest_row, dest_col, new_item)
                duplicated_cells += 1
        
        # Marquer qu'une entrée d'historique est en attente
        if duplicated_cells > 0:
            self.history_pending = True
        
        # Mettre à jour la sélection
        if dest_end_row >= dest_start_row:
            new_selection = QTableWidgetSelectionRange(
                self.orig_selection.topRow(), self.orig_selection.leftColumn(),
                dest_end_row, self.orig_selection.rightColumn()
            )
            self.table.setRangeSelected(new_selection, True)

    def _fill_cells_up(self, num_rows: int):
        """Remplir les cellules vers le haut"""
        if num_rows <= 0 or not self.orig_selection:
            return
        
        # Récupérer les valeurs source une seule fois (en excluant la colonne Nb Pièces)
        source_data = []
        for row in range(self.orig_selection.topRow(), self.orig_selection.bottomRow() + 1):
            row_data = []
            for col in range(self.orig_selection.leftColumn(), self.orig_selection.rightColumn() + 1):
                if col == 5:  # Colonne Nb Pièces - ne pas copier
                    continue
                item = self.table.item(row, col)
                row_data.append((col, item.text() if item else ""))
            source_data.append(row_data)
        
        source_height = len(source_data)
        
        # Calculer la plage de destination
        dest_end_row = self.orig_selection.topRow() - 1
        dest_start_row = max(dest_end_row - num_rows + 1, 0)
        
        # Compter les cellules dupliquées
        duplicated_cells = 0
        
        # Remplir les cellules de destination
        for dest_row in range(dest_start_row, dest_end_row + 1):
            distance = dest_end_row - dest_row
            source_row_idx = distance % source_height
            for dest_col, source_value in source_data[source_row_idx]:
                if dest_col == 5:  # Ne pas toucher à la colonne Nb Pièces
                    continue
                    
                # Créer et insérer l'item
                new_item = QTableWidgetItem(source_value)
                self.table.setItem(dest_row, dest_col, new_item)
                duplicated_cells += 1
        
        # Marquer qu'une entrée d'historique est en attente
        if duplicated_cells > 0:
            self.history_pending = True
        
        # Mettre à jour la sélection
        if dest_start_row <= dest_end_row:
            new_selection = QTableWidgetSelectionRange(
                dest_start_row, self.orig_selection.leftColumn(),
                self.orig_selection.bottomRow(), self.orig_selection.rightColumn()
            )
            self.table.setRangeSelected(new_selection, True)

    def mouseReleaseEvent(self, event):
        if not self.dragging:
            return
            
        # Sauvegarder et ajouter à l'historique uniquement au relâchement
        if self.history_pending and self.main_window and self.drag_direction:
            direction_text = "vers le bas" if self.drag_direction == "down" else "vers le haut"
            self.main_window.user_interaction_service.add_to_history(f"Duplication {direction_text}")
            # Sauvegarder les modifications dans la base de données
            self.main_window._save_drag_changes()
            
            # Plus besoin de recharger la colonne Nb Pièces (supprimée)
        
        self.dragging = False
        self.history_pending = False
        self.drag_direction = None
        
        # Arrêter le défilement automatique
        self._stop_auto_scroll()
    
    def mouseDoubleClickEvent(self, event):
        """Gérer le double-clic sur la poignée pour duplication automatique vers le bas"""
        if event.button() != Qt.LeftButton:
            return
            
        # Vérifier qu'on a une sélection valide
        if not self.table.selectedRanges():
            return
            
        selection = self.table.selectedRanges()[0]
        
        # Vérifier si la sélection contient des colonnes interdites (C=2, D=3, E=4)
        forbidden_cols = {2, 3, 4}  # Colonnes C, D et E (références importantes)
        selected_cols = set(range(selection.leftColumn(), selection.rightColumn() + 1))
        
        if forbidden_cols.intersection(selected_cols):
            # Ne pas permettre la duplication automatique sur les colonnes interdites
            return
        
        # Effectuer la duplication automatique vers le bas
        self._auto_fill_down()
    
    def _auto_fill_down(self):
        """Dupliquer automatiquement vers le bas jusqu'aux cellules vides"""
        if not self.table.selectedRanges():
            return
            
        selection = self.table.selectedRanges()[0]
        
        # Collecter les données source
        source_data = []
        for row in range(selection.topRow(), selection.bottomRow() + 1):
            row_data = []
            for col in range(selection.leftColumn(), selection.rightColumn() + 1):
                item = self.table.item(row, col)
                row_data.append((col, item.text() if item else ""))
            source_data.append(row_data)
        
        if not source_data:
            return
        
        # Chercher jusqu'où dupliquer (s'arrêter aux cellules vides)
        start_row = selection.bottomRow() + 1
        end_row = self._find_fill_end_row(selection, start_row)
        
        if start_row > end_row:
            return  # Aucune ligne à remplir
        
        # Calculer le nombre de lignes à dupliquer
        num_rows = end_row - start_row + 1
        source_row_count = len(source_data)
        
        # Effectuer la duplication
        duplicated_cells = 0
        for i in range(num_rows):
            dest_row = start_row + i
            source_row_idx = i % source_row_count  # Répéter le pattern source
            
            for col_idx, source_value in source_data[source_row_idx]:
                if dest_row < self.table.rowCount():
                    new_item = QTableWidgetItem(source_value)
                    self.table.setItem(dest_row, col_idx, new_item)
                    duplicated_cells += 1
        
        # Marquer la modification pour l'historique
        if duplicated_cells > 0:
            # Sélectionner la nouvelle plage
            new_selection = QTableWidgetSelectionRange(
                selection.topRow(), selection.leftColumn(),
                end_row, selection.rightColumn()
            )
            self.table.setRangeSelected(new_selection, True)
            
            # La sauvegarde et l'historique sont gérés par mouseReleaseEvent
    
    def _find_fill_end_row(self, selection, start_row):
        """Trouver la dernière ligne à remplir (tant que les cellules sont vides dans la sélection)"""
        # Regarder dans toutes les colonnes de la sélection
        for row in range(start_row, self.table.rowCount()):
            # Vérifier si TOUTES les cellules de cette ligne dans la sélection sont vides
            has_non_empty = False
            for col in range(selection.leftColumn(), selection.rightColumn() + 1):
                item = self.table.item(row, col)
                if item and item.text().strip():
                    has_non_empty = True
                    break
            
            # Si on trouve une cellule non-vide, s'arrêter avant cette ligne
            if has_non_empty:
                return row - 1
        
        # Si toutes les lignes jusqu'à la fin sont vides, aller jusqu'à la fin du tableau
        return self.table.rowCount() - 1
    
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
            try:
                self.auto_scroll_timer.disconnect()
            except:
                pass
            self.auto_scroll_timer.deleteLater()
            self.auto_scroll_timer = None
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
    
    def _continue_drag_fill(self):
        """Continuer la duplication pendant le défilement"""
        try:
            # Recalculer la position pour continuer la duplication
            if hasattr(self, 'last_mouse_pos') and self.start_pos:
                # Simuler un mouseMoveEvent pour continuer la duplication
                delta_y = self.last_mouse_pos.y() - self.start_pos.y()
                row_height = self.table.rowHeight(0) or 24
                
                if abs(delta_y) > row_height / 2:
                    self._handle_drag_fill(delta_y, row_height)
        except Exception as e:
            app_logger.error(f"Erreur continue drag: {e}")

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