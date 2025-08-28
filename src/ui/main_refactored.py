"""
Application de gestion d'appareils - Version refactorisée
Architecture modulaire avec séparation des responsabilités
"""

import sys
from typing import Optional, Dict, Any, List, Tuple
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
    QVBoxLayout, QWidget, QLabel, QPushButton, QHBoxLayout,
    QInputDialog, QMessageBox, QLineEdit, QTableWidgetSelectionRange,
    QToolBar, QAction, QStatusBar, QSplitter, QTabWidget, 
    QListWidget, QListWidgetItem, QFileDialog, QComboBox,
    QProgressDialog, QCheckBox, QMenu, QDialog, QCompleter, QTextEdit, QTextBrowser
)
from PyQt5.QtGui import QKeySequence, QPainter, QPen, QColor, QDragEnterEvent, QDropEvent, QBrush, QKeyEvent, QFont
from PyQt5.QtCore import QSize, QMimeData, QUrl, QStringListModel
from PyQt5.QtCore import Qt, QTimer, QSettings, QEvent

# Phase 4: Import des services pour l'architecture découplée
from ..services import SearchService, ExportService, ImportService, EventBus
from ..services.event_bus import event_bus
from ..services.export_service import ExportFormat

# Imports des modules refactorisés
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config
from src.core.logger import app_logger
from src.core.import_manager import ImportManager
from src.data.database_manager import DatabaseManager, DatabaseError
from src.data.data_validator import DataValidator, ValidationResult
from src.data.data_exporter import DataExporter, ExportError
from src.utils.seo_generator import SEOGenerator


class CustomTableWidget(QTableWidget):
    """Table personnalisée avec gestion des touches Delete/Backspace et auto-complétion"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_manager = None
        
    def set_db_manager(self, db_manager):
        """Définir le gestionnaire de base de données pour l'auto-complétion"""
        self.db_manager = db_manager
    
    def keyPressEvent(self, event: QKeyEvent):
        """Gestion des événements clavier"""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # Effacer le contenu des cellules sélectionnées
            selected_items = self.selectedItems()
            if selected_items:
                for item in selected_items:
                    if item:
                        item.setText("")
                return
        
        # Popup avec liste complète via Cmd+D (ou Ctrl+D sur Windows/Linux)
        if event.key() == Qt.Key_D and (event.modifiers() & Qt.MetaModifier or event.modifiers() & Qt.ControlModifier):
            # Récupérer le texte en cours d'édition si possible
            current_editor_text = None
            if self.state() == QTableWidget.EditingState:
                # La table est en mode édition, récupérer le texte de l'éditeur actuel
                focus_widget = QApplication.focusWidget()
                if focus_widget and hasattr(focus_widget, 'text'):
                    current_editor_text = focus_widget.text()
            
            self._show_completion_popup(current_editor_text)
            return
        
        # Appeler la méthode parent pour les autres touches
        super().keyPressEvent(event)
    
    def _show_completion_popup(self, editor_text=None):
        """Afficher popup avec auto-complétion avancée via Cmd+D"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem
        
        current_item = self.currentItem()
        if not current_item or not self.db_manager:
            return
            
        column = current_item.column()
        
        # Popup seulement pour les colonnes 0 (Type) et 1 (Fabricant)
        if column == 0:  # Colonne Type
            suggestions = self._get_all_types()
            column_name = "Type"
        elif column == 1:  # Colonne Fabricant
            suggestions = self._get_all_manufacturers()
            column_name = "Fabricant"
        else:
            return
        
        if not suggestions:
            return
        
        # Créer une boîte de dialogue personnalisée
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Auto-complétion {column_name}")
        dialog.setModal(True)
        dialog.resize(300, 400)
        
        layout = QVBoxLayout()
        
        # Champ de recherche
        search_input = QLineEdit()
        search_input.setPlaceholderText(f"Tapez pour filtrer les {column_name.lower()}s...")
        
        # Utiliser le texte de l'éditeur s'il est fourni, sinon le texte sauvegardé
        if editor_text is not None:
            current_text = editor_text
        else:
            current_text = current_item.text()
        
        search_input.setText(current_text)
        layout.addWidget(search_input)
        
        # Liste des suggestions
        suggestions_list = QListWidget()
        layout.addWidget(suggestions_list)
        
        # Fonction pour filtrer les suggestions
        def filter_suggestions():
            text = search_input.text().lower()
            suggestions_list.clear()
            
            for suggestion in suggestions:
                if text in suggestion.lower():
                    item = QListWidgetItem(suggestion)
                    suggestions_list.addItem(item)
            
            # Sélectionner automatiquement le premier élément
            if suggestions_list.count() > 0:
                suggestions_list.setCurrentRow(0)
                # Ne pas donner le focus à la liste pour garder le focus sur le champ de saisie
        
        # Fonction pour appliquer la sélection
        def apply_selection():
            current_list_item = suggestions_list.currentItem()
            if current_list_item:
                current_item.setText(current_list_item.text())
                dialog.accept()
            elif search_input.text():
                current_item.setText(search_input.text())
                dialog.accept()
        
        # Gestion des touches clavier pour la navigation
        def handle_key_press(event):
            if event.key() == Qt.Key_Down:
                if suggestions_list.currentRow() < suggestions_list.count() - 1:
                    suggestions_list.setCurrentRow(suggestions_list.currentRow() + 1)
                suggestions_list.setFocus()  # Donner le focus seulement quand on navigue
            elif event.key() == Qt.Key_Up:
                if suggestions_list.currentRow() > 0:
                    suggestions_list.setCurrentRow(suggestions_list.currentRow() - 1)
                suggestions_list.setFocus()  # Donner le focus seulement quand on navigue
            elif event.key() in [Qt.Key_Return, Qt.Key_Enter]:
                apply_selection()
            else:
                QLineEdit.keyPressEvent(search_input, event)
        
        search_input.keyPressEvent = handle_key_press
        
        # Gestion des touches pour la liste
        def handle_list_key_press(event):
            if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
                apply_selection()
            elif event.key() == Qt.Key_Escape:
                dialog.reject()
            else:
                QListWidget.keyPressEvent(suggestions_list, event)
        
        suggestions_list.keyPressEvent = handle_list_key_press
        
        # Connecter les événements
        search_input.textChanged.connect(filter_suggestions)
        suggestions_list.itemDoubleClicked.connect(apply_selection)
        
        # Filtrer initialement
        filter_suggestions()
        
        dialog.setLayout(layout)
        search_input.setFocus()
        search_input.selectAll()
        
        dialog.exec_()
    
    
    def _get_type_suggestions(self, partial_text: str) -> List[str]:
        """Obtenir des suggestions pour la colonne Type"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT type FROM appareils 
                WHERE type LIKE ? AND type != '' 
                ORDER BY type
                LIMIT 20
            """, (f"{partial_text}%",))
            
            return [row[0] for row in result]
        except Exception:
            return []
    
    def _get_manufacturer_suggestions(self, partial_text: str) -> List[str]:
        """Obtenir des suggestions pour la colonne Fabricant"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT manufacturer FROM appareils 
                WHERE manufacturer LIKE ? AND manufacturer != '' 
                ORDER BY manufacturer
                LIMIT 20
            """, (f"{partial_text}%",))
            
            return [row[0] for row in result]
        except Exception:
            return []
    
    def _get_all_types(self) -> List[str]:
        """Obtenir toutes les valeurs Type disponibles"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT type FROM appareils 
                WHERE type != '' 
                ORDER BY type
            """)
            
            return [row[0] for row in result]
        except Exception:
            return []
    
    def _get_all_manufacturers(self) -> List[str]:
        """Obtenir toutes les valeurs Fabricant disponibles"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT manufacturer FROM appareils 
                WHERE manufacturer != '' 
                ORDER BY manufacturer
            """)
            
            return [row[0] for row in result]
        except Exception:
            return []


class UndoRedoManager:
    """Gestionnaire simplifié d'annulation/rétablissement"""
    
    def __init__(self, max_history: int = None):
        self.history = []
        self.current_index = -1
        self.max_history = max_history or Config.UNDO_HISTORY_SIZE
    
    def add_action(self, action: Dict[str, Any]):
        """Ajouter une action à l'historique"""
        self.history = self.history[:self.current_index + 1]
        self.history.append(action)
        
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.current_index += 1
    
    def can_undo(self) -> bool:
        return self.current_index >= 0
    
    def can_redo(self) -> bool:
        return self.current_index < len(self.history) - 1
    
    def undo(self) -> Optional[Dict[str, Any]]:
        if self.can_undo():
            action = self.history[self.current_index]
            self.current_index -= 1
            return action
        return None
    
    def redo(self) -> Optional[Dict[str, Any]]:
        if self.can_redo():
            self.current_index += 1
            action = self.history[self.current_index]
            return action
        return None


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
        import time
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
            self.main_window._add_to_history(f"Duplication {direction_text}")
            
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
            
            # Ajouter à l'historique
            if self.main_window:
                self.main_window._add_to_history(f"Duplication automatique ({duplicated_cells} cellules)")
                self.main_window._save_drag_changes()
    
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
        from PyQt5.QtCore import QTimer
        
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
            print(f"Erreur continue drag: {e}")


class CategoryDialog(QInputDialog):
    """Dialogue simplifié pour la gestion des catégories"""
    
    @staticmethod
    def get_categories(parent, current_categories: List[str]) -> Optional[List[str]]:
        """Méthode statique pour obtenir les catégories"""
        text, ok = QInputDialog.getMultiLineText(
            parent, 
            "Gestion des Catégories",
            "Entrez les catégories (une par ligne):",
            '\n'.join(current_categories)
        )
        
        if ok:
            return [line.strip() for line in text.split('\n') if line.strip()]
        return None


class NotesDialog(QInputDialog):
    """Dialogue simplifié pour l'édition des notes"""
    
    @staticmethod
    def get_notes(parent, current_notes: str = "") -> Optional[str]:
        """Méthode statique pour obtenir les notes"""
        text, ok = QInputDialog.getMultiLineText(
            parent,
            "Notes et Commentaires",
            "Entrez vos notes:",
            current_notes
        )
        
        return text if ok else None


class MainWindow(QMainWindow):
    """Fenêtre principale refactorisée"""
    
    def __init__(self):
        super().__init__()
        
        # Initialisation des composants
        self._init_components()
        self._init_column_visibility()
        self._init_ui()
        self._init_connections()
        
        # Chargement initial des données
        self.load_data()

    def _init_components(self):
        """Initialiser les composants principaux"""
        try:
            # Gestionnaires métier
            self.db_manager = DatabaseManager()
            self.validator = DataValidator()
            self.exporter = DataExporter(self.db_manager)
            
            # Phase 4: Services découplés
            self.search_service = SearchService(self.db_manager)
            self.export_service = ExportService(self.db_manager)
            self.import_service = ImportService(self.db_manager)
            
            # Écouter les événements des services
            self._setup_service_events()
            self.seo_generator = SEOGenerator()
            
            # Nouveau gestionnaire d'import unifié
            self.import_manager = ImportManager(self.db_manager, parent_widget=self)
            
            # Gestionnaires UI
            self.undo_manager = UndoRedoManager()
            self.settings = QSettings("DeviceManager", "MainApp")
            
            # État de l'application
            self.modified_cells = set()
            self.filter_widgets = {}
            self.log_viewer = None
            
            # Timers
            self._setup_timers()
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'initialisation", f"Impossible d'initialiser l'application: {e}")
            sys.exit(1)
    
    def _init_column_visibility(self):
        """Initialiser la configuration de visibilité des colonnes"""
        self.settings = QSettings("1001pieces", "autofill")
        
        # Charger les préférences de colonnes ou utiliser les valeurs par défaut
        self.visible_columns = {}
        for col in Config.COLUMN_CONFIG:
            saved_state = self.settings.value(f"column_{col['index']}_visible", col['visible'])
            self.visible_columns[col['index']] = saved_state if isinstance(saved_state, bool) else col['visible']

    def _setup_timers(self):
        """Configurer les timers"""
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save)
        self.auto_save_timer.start(Config.AUTO_SAVE_INTERVAL)
        
        # Timer pour débounce de la recherche
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_delayed_search)
        self.pending_search_term = None
        
        # Timer pour débounce des filtres de colonnes (400ms)
        self.column_filter_timer = QTimer()
        self.column_filter_timer.setSingleShot(True)
        self.column_filter_timer.timeout.connect(self._perform_delayed_column_filter)
        self.pending_column_filter = None
        
        # Gestion débouncing des barres de progression
        self.last_progress_update = 0
        self.progress_update_interval = 100  # ms minimum entre les mises à jour

    def _init_ui(self):
        """Initialiser l'interface utilisateur moderne"""
        self.setWindowTitle("📊 " + Config.WINDOW_TITLE)
        self.resize(Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)
        self.setAcceptDrops(True)  # Activer le glisser/déposer pour les fichiers CSV
        
        # Style moderne global (appliqué à l'application entière dans main())
        
        # Restaurer la géométrie
        geometry = self.settings.value("geometry", b"")
        if geometry:
            self.restoreGeometry(geometry)
        
        self._setup_central_widget()
        self._setup_toolbar()
        self._setup_statusbar()

    def _setup_central_widget(self):
        """Configurer le widget central"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Partie gauche - tableau principal
        left_widget = self._create_table_widget()
        
        # Partie droite - panneau des pièces
        right_widget = self._create_pieces_widget()
        
        # Configuration du splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([800, 400])
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.addWidget(main_splitter)
    
    def _setup_service_events(self):
        """Phase 4: Configuration des événements des services"""
        # Événements de recherche
        event_bus.on('search.started', self._on_search_started)
        event_bus.on('search.completed', self._on_search_completed) 
        event_bus.on('search.error', self._on_search_error)
        
        # Événements d'export
        event_bus.on('export.started', self._on_export_started)
        event_bus.on('export.completed', self._on_export_completed)
        event_bus.on('export.error', self._on_export_error)
        
        # Événements d'import
        event_bus.on('import.started', self._on_import_started)
        event_bus.on('import.completed', self._on_import_completed)
        event_bus.on('import.error', self._on_import_error)
    
    def _on_search_started(self, data):
        """Gestionnaire événement début de recherche"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(f"🔍 Recherche en cours: '{data['term']}'...")
    
    def _on_search_completed(self, data):
        """Gestionnaire événement fin de recherche"""
        if hasattr(self, 'statusbar'):
            cache_info = " (cache)" if data.get('has_cache_hit') else ""
            self.statusbar.showMessage(
                f"✅ Recherche terminée: {data['results_count']} résultats{cache_info}", 
                3000
            )
    
    def _on_search_error(self, data):
        """Gestionnaire événement erreur de recherche"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(f"❌ Erreur recherche: {data['error']}", 5000)
    
    def _on_export_started(self, data):
        """Gestionnaire événement début d'export"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(f"📤 Export {data['format']} en cours...")
    
    def _on_export_completed(self, data):
        """Gestionnaire événement fin d'export"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(
                f"✅ Export terminé: {data['count']} lignes → {data['output_file']}", 
                5000
            )
    
    def _on_export_error(self, data):
        """Gestionnaire événement erreur d'export"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(f"❌ Erreur export: {data['error']}", 5000)
    
    def _on_import_started(self, data):
        """Gestionnaire événement début d'import"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(f"📥 Import de {data['file_count']} fichier(s)...")
    
    def _on_import_completed(self, data):
        """Gestionnaire événement fin d'import"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(
                f"✅ Import terminé: {data['total_imported']} lignes traitées", 
                5000
            )
    
    def _on_import_error(self, data):
        """Gestionnaire événement erreur d'import"""
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(f"❌ Erreur import: {data['error']}", 5000)

    def _create_table_widget(self) -> QWidget:
        """Créer le widget du tableau"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Filtres par colonne prenant toute la largeur disponible
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(2)  # Petit espacement entre les filtres
        
        for i, header in enumerate(Config.UI_HEADERS):
            # Skip filter for "Nb Pièces" column (index 7) - pas de spacer
            if i == 7:  # "Nb Pièces" column
                continue
            
            # Create dropdown filters for Type (index 0) and Fabricant (index 1)
            if i == 0 or i == 1:  # Type or Fabricant columns
                filter_combo = QComboBox()
                filter_combo.setEditable(True)
                filter_combo.lineEdit().setPlaceholderText(f"{header}...")
                filter_combo.currentTextChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
                self.filter_widgets[i] = filter_combo
                self._populate_dropdown_values(filter_combo, i)
                filter_layout.addWidget(filter_combo, 1)  # stretch factor 1
            else:
                # Champs texte avec même style que les dropdowns
                filter_input = QLineEdit()
                filter_input.setPlaceholderText(f"{header}...")
                filter_input.textChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
                # Appliquer le même style visuel que les QComboBox
                filter_input.setStyleSheet("""
                    QLineEdit {
                        padding: 4px 8px;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        background-color: white;
                        min-height: 20px;
                    }
                    QLineEdit:focus {
                        border-color: #0078d4;
                        outline: none;
                    }
                """)
                self.filter_widgets[i] = filter_input
                filter_layout.addWidget(filter_input, 1)  # stretch factor 1
        
        layout.addWidget(filter_widget)
        
        # Sauvegarder les références pour la visibilité
        self.filter_widget = filter_widget
        self.filter_layout = filter_layout
        
        # Tableau principal avec gestion des touches
        self.table = CustomTableWidget()
        self.table.setColumnCount(len(Config.UI_HEADERS))
        self.table.setHorizontalHeaderLabels(Config.UI_HEADERS)
        self.table.set_db_manager(self.db_manager)  # Configurer l'auto-complétion
        self.table.setAcceptDrops(True)  # Activer le glisser/déposer pour les fichiers CSV
        self.table.setDragDropMode(QTableWidget.DragDropMode.DropOnly)  # Seulement accepter les drops
        
        # Variables pour l'effet visuel de drag-and-drop
        self.drag_overlay_active = False
        
        # Configurer le menu contextuel
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        
        # Appliquer la visibilité des colonnes
        self._apply_column_visibility()
        
        # Désactiver le tri automatique de Qt pour éviter les problèmes d'affichage
        # Nous implémenterons notre propre tri via la base de données
        self.table.setSortingEnabled(False)
        
        # Activer les indicateurs de tri dans les en-têtes
        self.table.horizontalHeader().setSortIndicatorShown(True)
        
        # Variables pour le tri manuel
        self.current_sort_column = -1
        self.current_sort_order = Qt.SortOrder.DescendingOrder  # Par défaut: ID DESC
        
        # Connecter les signaux pour capturer les modifications
        self.table.itemChanged.connect(self._on_cell_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.currentItemChanged.connect(self._on_current_item_changed)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        # Connecter le signal de clic sur header pour notre tri personnalisé
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        layout.addWidget(self.table)
        
        # Dictionnaire pour stocker les valeurs précédentes
        self.previous_values = {}
        
        # Variables de pagination
        self.current_page = 0
        self.page_size = Config.DEFAULT_PAGE_SIZE
        self.total_rows = 0
        self.use_pagination = True
        
        # Cache des décisions utilisateur pour les conflits de description
        self._piece_description_decisions = {}
        
        # Section recherche moderne
        search_section = QWidget()
        search_section.setObjectName("searchSection")
        search_section_layout = QHBoxLayout(search_section)
        search_section_layout.setContentsMargins(12, 8, 12, 8)
        search_section_layout.setSpacing(8)
        
        search_icon = QLabel("🔍")
        search_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        search_icon.setStyleSheet("padding: 4px;")
        search_section_layout.addWidget(search_icon)
        
        # Conteneur pour la barre de recherche et les options
        search_container = QVBoxLayout()
        search_container.setSpacing(4)
        
        # Première ligne : barre de recherche
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Recherche avancée : terme1 && terme2, terme3 || terme4...")
        self.search_input.textChanged.connect(self._search_table)
        search_row.addWidget(self.search_input)
        
        # Case à cocher pour les expressions régulières
        self.regex_checkbox = QCheckBox("RegEx")
        self.regex_checkbox.setToolTip("Activer les expressions régulières")
        self.regex_checkbox.setStyleSheet("QCheckBox { color: #6c757d; font-size: 11px; }")
        search_row.addWidget(self.regex_checkbox)
        
        search_container.addLayout(search_row)
        
        # Deuxième ligne : aide sur la syntaxe
        help_text = QLabel("💡 Opérateurs : && (ET), || (OU), RegEx activable")
        help_text.setStyleSheet("QLabel { color: #6c757d; font-size: 10px; font-style: italic; }")
        help_text.setWordWrap(True)
        search_container.addWidget(help_text)
        
        # Ajouter le conteneur à la section de recherche
        search_section_layout.addLayout(search_container)
        
        # Bouton de réinitialisation de la recherche
        search_clear_btn = QPushButton("×")
        search_clear_btn.setFixedSize(24, 24)
        search_clear_btn.setToolTip("Effacer la recherche (Échap)")
        search_clear_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                color: #6c757d;
                font-size: 16px;
                font-weight: bold;
                text-align: center;
                padding: 0px;
                margin: 0px;
                vertical-align: middle;
            }
            QPushButton:hover {
                background-color: #f8f9fa;
                color: #dc3545;
            }
        """)
        search_clear_btn.clicked.connect(self._clear_search)
        search_section_layout.addWidget(search_clear_btn)
        
        layout.addWidget(search_section)
        
        # Boutons d'export
        self._add_export_buttons(layout)
        
        # Boutons d'action
        self._add_action_buttons(layout)
        
        # Drag handle
        self._setup_drag_handle()
        
        return widget

    def _create_pieces_widget(self) -> QWidget:
        """Créer le widget des pièces"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Splitter vertical pour diviser en deux parties
        pieces_splitter = QSplitter(Qt.Vertical)
        
        # Partie haute - Onglets pour les pièces
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        self.pieces_tabs = QTabWidget()
        
        # Liste des pièces
        self.pieces_list = QListWidget()
        self.pieces_list.itemDoubleClicked.connect(self._edit_piece)
        self.pieces_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pieces_list.customContextMenuRequested.connect(self._show_pieces_context_menu)
        self.pieces_tabs.addTab(self.pieces_list, "Liste des pièces associées")
        
        # Ajout de pièce
        pieces_add_widget = QWidget()
        pieces_add_layout = QVBoxLayout(pieces_add_widget)
        
        self.piece_input = QLineEdit()
        self.piece_input.setPlaceholderText("Référence de la pièce...")
        pieces_add_layout.addWidget(self.piece_input)
        
        self.piece_libelle_input = QLineEdit()
        self.piece_libelle_input.setPlaceholderText("Libellé de la pièce (optionnel)...")
        pieces_add_layout.addWidget(self.piece_libelle_input)
        
        add_piece_btn = QPushButton("Ajouter")
        add_piece_btn.clicked.connect(self._add_piece)
        pieces_add_layout.addWidget(add_piece_btn)
        
        pieces_add_layout.addStretch()
        self.pieces_tabs.addTab(pieces_add_widget, "+")
        
        top_layout.addWidget(self.pieces_tabs)
        pieces_splitter.addWidget(top_widget)
        

        # Partie basse - Historique des modifications
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        
        # Titre moderne collé à la fenêtre historique
        history_header_layout = QHBoxLayout()
        history_header_layout.setContentsMargins(0, 0, 0, 5)  # Collé au widget
        
        history_label = QLabel("📜 Historique des modifications")
        history_label.setObjectName("historyTitle")
        history_header_layout.addWidget(history_label)
        
        # Le bouton rafraîchir est maintenant dans la toolbar
        
        history_layout.addLayout(history_header_layout)
        history_layout.setContentsMargins(8, 8, 8, 8)  # Padding moderne
        
        self.history_list = QTextBrowser()
        self.history_list.setOpenExternalLinks(False)  # Gérer les liens nous-mêmes
        
        # Style pour ressembler à une liste
        self.history_list.setStyleSheet("""
            QTextBrowser {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 4px;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                font-size: 12px;
            }
        """)
        
        # Connecter la gestion des liens
        self.history_list.anchorClicked.connect(self._handle_history_link)
        
        history_layout.addWidget(self.history_list)
        
        pieces_splitter.addWidget(history_widget)
        
        # Configuration du splitter (50% haut, 50% bas pour plus d'espace à l'historique)
        pieces_splitter.setSizes([200, 200])
        
        # Permettre au widget historique de grandir plus facilement
        pieces_splitter.setStretchFactor(1, 1)  # Historique peut grandir
        
        layout.addWidget(pieces_splitter)
        return widget

    def _add_export_buttons(self, layout: QVBoxLayout):
        """Ajouter les boutons d'export"""
        # Ligne 1: Boutons d'export traditionnels
        export_layout = QHBoxLayout()
        
        self.export_csv_btn = QPushButton("Exporter CSV")
        self.export_csv_btn.clicked.connect(lambda: self._export_data(ExportFormat.CSV))
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.setStyleSheet("""
            QPushButton { 
                background-color: #134c4d; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #11403f; 
            }
            QPushButton:disabled { 
                background-color: #cccccc; 
                color: #666666; 
            }
        """)
        export_layout.addWidget(self.export_csv_btn)
        
        self.export_html_brands_btn = QPushButton("HTML Marques")
        self.export_html_brands_btn.clicked.connect(lambda: self._export_data(ExportFormat.HTML_BRANDS))
        self.export_html_brands_btn.setEnabled(False)
        export_layout.addWidget(self.export_html_brands_btn)
        
        self.export_html_details_btn = QPushButton("HTML Détails")
        self.export_html_details_btn.clicked.connect(lambda: self._export_data(ExportFormat.HTML_DETAILS))
        self.export_html_details_btn.setEnabled(False)
        export_layout.addWidget(self.export_html_details_btn)
        
        layout.addLayout(export_layout)
        
        # Ligne 2: Boutons SEO métadonnées (alignés sous les boutons HTML)
        seo_layout = QHBoxLayout()
        
        self.meta_title_btn = QPushButton("📝 Méta Title")
        self.meta_title_btn.clicked.connect(self._generate_meta_title)
        self.meta_title_btn.setEnabled(False)
        self.meta_title_btn.setToolTip("Générer un méta titre SEO optimisé (60 caractères max)")
        self.meta_title_btn.setStyleSheet("""
            QPushButton { 
                background-color: #fd7e14; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #e5711f; 
            }
            QPushButton:disabled { 
                background-color: #cccccc; 
                color: #666666; 
            }
        """)
        seo_layout.addWidget(self.meta_title_btn)
        
        self.meta_desc_btn = QPushButton("📋 Méta Desc")
        self.meta_desc_btn.clicked.connect(self._generate_meta_description)
        self.meta_desc_btn.setEnabled(False)
        self.meta_desc_btn.setToolTip("Générer une méta description SEO aléatoire (150 caractères max)")
        self.meta_desc_btn.setStyleSheet("""
            QPushButton { 
                background-color: #ffc107; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #e6ad06; 
            }
            QPushButton:disabled { 
                background-color: #cccccc; 
                color: #666666; 
            }
        """)
        seo_layout.addWidget(self.meta_desc_btn)
        
        # Laisser les boutons alignés à gauche naturellement (sous les boutons HTML)
        
        layout.addLayout(seo_layout)

    def _add_action_buttons(self, layout: QVBoxLayout):
        """Ajouter les boutons d'action"""
        btn_layout = QHBoxLayout()
        
        # Les boutons Autocomplétion et Nettoyer doublons sont maintenant dans le menu Action
        # Le bouton Incomplète est déplacé dans la zone de pagination
        
        # Variable pour le filtre des incomplètes
        self.show_incomplete_only = False
        
        # Tous les boutons sont maintenant dans les menus ou la zone de pagination
        # layout.addLayout(btn_layout)  # Commenté car plus de boutons dans cette section
        
        # Ajouter les contrôles de pagination
        self._add_pagination_controls(layout)

    def _add_pagination_controls(self, layout: QVBoxLayout):
        """Ajouter les contrôles de pagination modernes"""
        
        # Section pagination moderne
        pagination_section = QWidget()
        pagination_section.setObjectName("paginationSection")
        pagination_section_layout = QVBoxLayout(pagination_section)
        pagination_section_layout.setContentsMargins(12, 8, 12, 8)
        
        pagination_layout = QHBoxLayout()
        pagination_layout.setSpacing(4)
        
        # Boutons de navigation
        self.first_page_btn = QPushButton("««")
        self.first_page_btn.setObjectName("paginationBtn")
        self.first_page_btn.setToolTip("Première page")
        self.first_page_btn.clicked.connect(lambda: self._go_to_page(0))
        pagination_layout.addWidget(self.first_page_btn)
        
        self.prev_page_btn = QPushButton("«")
        self.prev_page_btn.setObjectName("paginationBtn")
        self.prev_page_btn.setToolTip("Page précédente")
        self.prev_page_btn.clicked.connect(self._previous_page)
        pagination_layout.addWidget(self.prev_page_btn)
        
        # Indicateur de page
        self.page_info_label = QLabel("Page 1 / 1")
        pagination_layout.addWidget(self.page_info_label)
        
        self.next_page_btn = QPushButton("»")
        self.next_page_btn.setObjectName("paginationBtn")
        self.next_page_btn.setToolTip("Page suivante")
        self.next_page_btn.clicked.connect(self._next_page)
        pagination_layout.addWidget(self.next_page_btn)
        
        self.last_page_btn = QPushButton("»»")
        self.last_page_btn.setObjectName("paginationBtn")
        self.last_page_btn.setToolTip("Dernière page")
        self.last_page_btn.clicked.connect(self._go_to_last_page)
        pagination_layout.addWidget(self.last_page_btn)
        
        pagination_layout.addWidget(QLabel("|  "))
        
        pagination_layout.addStretch()
        
        # Sélecteur de taille de page aligné à droite
        size_label = QLabel("Afficher:")
        size_label.setObjectName("inlineLabel")
        pagination_layout.addWidget(size_label)
        
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["500", "1000", "2000", "5000", "10000", "Tout"])
        self.page_size_combo.setCurrentText(str(Config.DEFAULT_PAGE_SIZE))
        self.page_size_combo.currentTextChanged.connect(self._change_page_size)
        pagination_layout.addWidget(self.page_size_combo)
        
        pagination_section_layout.addLayout(pagination_layout)
        
        # Deuxième ligne avec bouton Incomplète centré et informations à droite
        pagination_layout_2 = QHBoxLayout()
        pagination_layout_2.setSpacing(4)
        
        # Espace pour centrer le bouton Incomplète
        pagination_layout_2.addStretch()
        
        # Bouton pour afficher seulement les lignes incomplètes (centré)
        incomplete_btn = QPushButton("📋 Lignes à traiter")
        incomplete_btn.setToolTip("Afficher uniquement les lignes avec des champs vides")
        incomplete_btn.setCheckable(True)
        incomplete_btn.clicked.connect(self._toggle_incomplete_filter)
        incomplete_btn.setObjectName("incompleteBtn")
        pagination_layout_2.addWidget(incomplete_btn)
        self.incomplete_filter_btn = incomplete_btn
        
        # Vérifier et masquer le bouton si aucun appareil incomplet
        self._update_incomplete_button_visibility()
        
        # Espace pour centrer le bouton et pousser les infos à droite
        pagination_layout_2.addStretch()
        
        # Compteur de lignes et indicateur de performance alignés à droite
        self.counter_label = QLabel("Lignes : 0")
        self.counter_label.setObjectName("counterLabel")
        pagination_layout_2.addWidget(self.counter_label)
        
        pagination_layout_2.addWidget(QLabel("  |  "))
        
        # Indicateur de performance
        self.perf_label = QLabel("⚡ Prêt")
        self.perf_label.setObjectName("perfLabel")
        pagination_layout_2.addWidget(self.perf_label)
        
        # Bouton pour afficher toutes les lignes (masqué car option "Tout" existe dans la selectlist)
        self.show_all_btn = QPushButton("📋 Toutes les lignes")
        self.show_all_btn.setObjectName("paginationBtn")
        self.show_all_btn.setToolTip("Afficher toutes les lignes (peut être lent)")
        self.show_all_btn.clicked.connect(self._toggle_show_all)
        self.show_all_btn.setVisible(False)  # Masqué
        pagination_layout_2.addWidget(self.show_all_btn)
        
        pagination_section_layout.addLayout(pagination_layout_2)
        layout.addWidget(pagination_section)

    def _setup_drag_handle(self):
        """Configurer la poignée de glisser-déposer"""
        self.drag_handle = DragHandle(self.table.viewport(), self.table, self)
        self.table.viewport().installEventFilter(self)

    def _setup_toolbar(self):
        """Configurer la barre d'outils moderne"""
        toolbar = QToolBar()
        toolbar.setObjectName("modernToolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setMovable(False)  # Fixer la barre pour un look plus moderne
        toolbar.setIconSize(QSize(20, 20))  # Icônes de taille uniforme
        self.addToolBar(toolbar)
        
        # Groupe Actualisation
        refresh_action = QAction("↻", self)
        refresh_action.setShortcut("F5")
        refresh_action.setToolTip("Rafraîchir l'application (F5)")
        refresh_action.triggered.connect(self._refresh_application)
        toolbar.addAction(refresh_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Édition
        self.undo_action = QAction("←", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setToolTip("Annuler la dernière action (Cmd+Z)")
        self.undo_action.triggered.connect(self._undo)
        toolbar.addAction(self.undo_action)
        
        self.redo_action = QAction("→", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setToolTip("Rétablir l'action annulée (Cmd+Y)")
        self.redo_action.triggered.connect(self._redo)
        toolbar.addAction(self.redo_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Presse-papiers
        copy_action = QAction("📋", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setToolTip("Copier la sélection (Cmd+C)")
        copy_action.triggered.connect(self._handle_copy)
        toolbar.addAction(copy_action)
        
        paste_action = QAction("📥", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.setToolTip("Coller depuis le presse-papiers (Cmd+V)")
        paste_action.triggered.connect(self._handle_paste)
        toolbar.addAction(paste_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Sauvegarde
        save_action = QAction("💾", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setToolTip("Sauvegarder toutes les modifications (Cmd+S)")
        save_action.triggered.connect(self._manual_save)
        toolbar.addAction(save_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Menus déroulants
        # Menu Gestion dans la toolbar
        gestion_btn = QPushButton("Gestion")
        gestion_btn.setObjectName("menuButton")
        gestion_menu = QMenu()
        
        categories_action = QAction("🏷️ Catégories", self)
        categories_action.triggered.connect(self._manage_categories)
        gestion_menu.addAction(categories_action)
        
        pieces_action = QAction("🔧 Pièces", self) 
        pieces_action.triggered.connect(self._open_pieces_manager)
        gestion_menu.addAction(pieces_action)
        
        validate_action = QAction("🔍 Incohérences", self)
        validate_action.triggered.connect(self._validate_and_detect_inconsistencies)
        gestion_menu.addAction(validate_action)
        
        gestion_btn.setMenu(gestion_menu)
        toolbar.addWidget(gestion_btn)
        
        # Menu Action dans la toolbar
        action_btn = QPushButton("Action")
        action_btn.setObjectName("menuButton")
        action_menu = QMenu()
        
        import_action = QAction("📈 Import", self)
        import_action.triggered.connect(self._import_file)
        action_menu.addAction(import_action)
        
        action_menu.addSeparator()
        
        autocomplete_action = QAction("🗯️ Autocomplétion", self)
        autocomplete_action.triggered.connect(self._fill_empty_fields)
        action_menu.addAction(autocomplete_action)
        
        clean_action = QAction("🧹 Nettoyer les doublons", self)
        clean_action.triggered.connect(self._clean_data)
        action_menu.addAction(clean_action)
        
        action_btn.setMenu(action_menu)
        toolbar.addWidget(action_btn)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Outils
        logs_action = QAction("📊 Journal", self)
        logs_action.setToolTip("Ouvrir le visualiseur de logs")
        logs_action.triggered.connect(self._open_log_viewer)
        toolbar.addAction(logs_action)
        
        guide_action = QAction("📖 Guide", self)
        guide_action.setToolTip("Ouvrir le guide d'utilisation")
        guide_action.triggered.connect(self._open_user_guide)
        toolbar.addAction(guide_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Bouton configuration des colonnes
        columns_action = QAction("☰ Colonnes", self)
        columns_action.setToolTip("Configurer l'affichage des colonnes")
        columns_action.triggered.connect(self._configure_columns)
        toolbar.addAction(columns_action)
        
        self._update_toolbar_states()
    
    def _add_toolbar_separator(self, toolbar):
        """Ajouter un séparateur moderne à la toolbar"""
        separator = toolbar.addSeparator()
        # Le style du séparateur est géré par le CSS
        return separator

    def _setup_statusbar(self):
        """Configurer la barre de statut"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        self.save_indicator = QLabel(Config.get_message('save_success'))
        self.save_indicator.setStyleSheet("color: green;")
        self.statusbar.addPermanentWidget(self.save_indicator)
        
        self.connection_indicator = QLabel(Config.get_message('connected'))
        self.connection_indicator.setStyleSheet("color: green;")
        self.statusbar.addPermanentWidget(self.connection_indicator)

    def _init_connections(self):
        """Initialiser les connexions de signaux"""
        pass  # Les connexions sont déjà configurées dans les méthodes de création

    # --- Méthodes de gestion des données ---

    def load_data(self, search_term: str = None, is_search: bool = False):
        """Charger les données depuis la base avec pagination"""
        import time
        start_time = time.time()
        
        # FIXME: Désactiver auto-save pendant chargement pour éviter historique parasites
        old_auto_save_enabled = getattr(self, 'auto_save_enabled', True)
        self.auto_save_enabled = False
        
        try:
            # Indicateur de chargement intelligent - seulement pour les opérations non-recherche
            # ou les recherches avec beaucoup de données
            show_loading_indicator = not is_search
            if is_search:
                # Pour les recherches, estimer si ce sera long
                estimated_rows = self.db_manager.count_data(search_term) if search_term else self.total_rows if hasattr(self, 'total_rows') else 0
                show_loading_indicator = estimated_rows > 5000  # Seuil pour afficher l'indicateur lors des recherches
            
            if show_loading_indicator:
                self.perf_label.setText("⏳ Chargement...")
                self.statusbar.showMessage("⏳ Chargement des données en cours...")
                QApplication.processEvents()  # Forcer l'affichage
            
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            
            # Obtenir les filtres de colonnes
            column_filters = {}
            for col_idx, filter_widget in self.filter_widgets.items():
                if filter_widget is not None:  # Skip removed filters
                    if isinstance(filter_widget, QComboBox):
                        filter_text = filter_widget.currentText().strip()
                    else:  # QLineEdit
                        filter_text = filter_widget.text().strip()
                    if filter_text:
                        column_filters[col_idx] = filter_text
            
            # Ajouter le filtre des lignes incomplètes si activé
            incomplete_filter = getattr(self, 'show_incomplete_only', False)
            
            # Préparer les paramètres de tri
            sort_column = self.current_sort_column if hasattr(self, 'current_sort_column') and self.current_sort_column >= 0 else None
            sort_order = "ASC" if hasattr(self, 'current_sort_order') and self.current_sort_order == Qt.SortOrder.AscendingOrder else "DESC"
            
            # Compter le total de lignes (seulement si pas déjà calculé par SearchService)
            if not hasattr(self, 'total_rows') or not is_search:
                self.total_rows = self.db_manager.count_data(search_term, column_filters, incomplete_filter=incomplete_filter)
            
            # Préparer une barre de progression pour les gros volumes
            progress_dialog = None
            if self.total_rows > 100000 and not is_search:  # Seuil augmenté pour éviter affichage trop fréquent
                progress_dialog = QProgressDialog(
                    f"Chargement de {self.total_rows} lignes...",
                    "Annuler",
                    0, 100,
                    self
                )
                progress_dialog.setWindowTitle("Chargement des données")
                progress_dialog.setWindowModality(Qt.WindowModal)
                progress_dialog.show()
                QApplication.processEvents()
            
            # Optimisation Phase 2: Pagination intelligente automatique
            # FIXME: Respecter le choix utilisateur "Tout" 
            user_wants_all = getattr(self, 'page_size', 0) == -1 or not self.use_pagination
            should_paginate = (self.use_pagination and self.total_rows > Config.MAX_DISPLAY_ROWS) and not user_wants_all
            
            if should_paginate:
                # Activer automatiquement la pagination si nécessaire
                if not self.use_pagination and self.total_rows > Config.PAGINATION_THRESHOLD:
                    print(f"🚀 Pagination automatique activée pour {self.total_rows} lignes (seuil: {Config.PAGINATION_THRESHOLD})")
                    self.use_pagination = True
                    self._update_pagination_controls()  # Montrer les contrôles
                
                # Calculer offset pour la pagination
                offset = self.current_page * self.page_size
                limit = self.page_size
                
                self._update_progress_with_debounce(progress_dialog, 50, f"Chargement page {self.current_page + 1}...")
                
                # Charger seulement la page courante avec tri
                records = self.db_manager.load_data(search_term, column_filters, limit, offset, sort_column, sort_order, incomplete_filter)
            else:
                self._update_progress_with_debounce(progress_dialog, 20, f"Chargement de toutes les {self.total_rows} lignes...")
                
                # Charger toutes les données (pour les petites bases ou recherches) avec tri
                records = self.db_manager.load_data(search_term, column_filters, None, None, sort_column, sort_order, incomplete_filter)
            
            # Remplir le tableau avec optimisation par chunks
            self.table.setRowCount(len(records))
            
            self._update_progress_with_debounce(progress_dialog, 60, "Remplissage du tableau...")
            
            # Optimisation Phase 2: Remplissage par chunks pour améliorer la responsivité
            if len(records) > Config.CHUNK_SIZE:
                self._fill_table_chunked(records, progress_dialog, search_term)
            else:
                self._fill_table_standard(records, progress_dialog, search_term)
            
            # Finalisation
            self._update_progress_with_debounce(progress_dialog, 95, "Finalisation...")
            
            self.table.resizeColumnsToContents()
            self._update_counter()
            self._update_pagination_controls()
            
            # Initialiser les valeurs précédentes pour le tracking des modifications
            self._init_previous_values()
            
            # Fermer la barre de progression
            self._update_progress_with_debounce(progress_dialog, 100, "Terminé")
            if progress_dialog:
                progress_dialog.close()
            
            # Afficher les performances avec plus de détails
            load_time = time.time() - start_time
            if hasattr(self, 'perf_label'):
                # Déterminer la couleur en fonction du temps de chargement
                if load_time < 0.5:
                    color = "#28a745"  # Vert - Très rapide
                    icon = "🚀"
                elif load_time < 2.0:
                    color = "#ffc107"  # Jaune - Correct
                    icon = "⚡"
                else:
                    color = "#dc3545"  # Rouge - Lent
                    icon = "🐌"
                
                # Message détaillé
                perf_text = f"{icon} {load_time:.2f}s"
                if len(records) < self.total_rows:
                    perf_text += f" ({len(records)}/{self.total_rows} lignes)"
                else:
                    perf_text += f" ({len(records)} lignes)"
                
                # Ajouter des détails si c'est lent
                if load_time > 2.0:
                    perf_text += " - Chargement lent"
                
                self.perf_label.setText(perf_text)
                self.perf_label.setStyleSheet(f"color: {color}; font-weight: bold;")
                
                # Message dans la barre de statut - seulement si l'indicateur était affiché ou si c'est lent
                if show_loading_indicator or load_time > 1.0:
                    status_msg = f"✅ Chargement terminé en {load_time:.2f}s"
                    if len(records) < self.total_rows:
                        status_msg += f" - Page {self.current_page + 1} ({len(records)} lignes affichées sur {self.total_rows} total)"
                    else:
                        status_msg += f" - {len(records)} lignes affichées"
                    
                    timeout = 1500 if is_search else 3000  # Timeout plus court pour les recherches
                    self.statusbar.showMessage(status_msg, timeout)
            
        except DatabaseError as e:
            self._show_error(f"Erreur de base de données: {e}")
        except Exception as e:
            self._show_error(f"Erreur inattendue: {e}")
        finally:
            self.table.blockSignals(False)
            self._position_drag_handle()
            # FIXME: Restaurer l'état d'auto-save
            self.auto_save_enabled = old_auto_save_enabled
    
    def _fill_table_chunked(self, records: List, progress_dialog, search_term):
        """Remplissage optimisé par chunks pour améliorer la responsivité"""
        import time
        
        chunk_size = Config.CHUNK_SIZE
        total_chunks = (len(records) + chunk_size - 1) // chunk_size
        
        self.table.blockSignals(True)  # Bloquer les signaux pendant le remplissage
        
        try:
            last_update_time = time.time()
            
            for chunk_idx in range(total_chunks):
                start_idx = chunk_idx * chunk_size
                end_idx = min(start_idx + chunk_size, len(records))
                chunk_records = records[start_idx:end_idx]
                
                # Traitement du chunk
                for local_idx, record in enumerate(chunk_records):
                    row_idx = start_idx + local_idx
                    self._fill_single_row(row_idx, record, search_term)
                
                # Mise à jour responsive de l'interface
                current_time = time.time()
                if (current_time - last_update_time) * 1000 > Config.RESPONSIVE_UPDATE_INTERVAL:
                    QApplication.processEvents()  # Maintenir la responsivité
                    last_update_time = current_time
                
                # Progression
                if progress_dialog:
                    if progress_dialog.wasCanceled():
                        break
                    progress_value = 60 + ((chunk_idx + 1) / total_chunks) * 35  # 60% -> 95%
                    self._update_progress_with_debounce(
                        progress_dialog, 
                        int(progress_value), 
                        f"Remplissage optimisé... {end_idx}/{len(records)} lignes"
                    )
        
        finally:
            self.table.blockSignals(False)  # Réactiver les signaux
    
    def _fill_table_standard(self, records: List, progress_dialog, search_term):
        """Remplissage standard pour les petites tables"""
        for row_idx, record in enumerate(records):
            if progress_dialog and progress_dialog.wasCanceled():
                break
            
            self._fill_single_row(row_idx, record, search_term)
            
            # Mise à jour de progression moins fréquente pour petites tables
            if progress_dialog and row_idx % 100 == 0:
                progress_value = 60 + (row_idx / len(records)) * 35
                self._update_progress_with_debounce(
                    progress_dialog,
                    int(progress_value),
                    f"Remplissage du tableau... {row_idx}/{len(records)} lignes"
                )
    
    def _fill_single_row(self, row_idx: int, record, search_term):
        """Remplir une seule ligne de manière optimisée"""
        db_id = record[0]
        
        # En-tête vertical optimisé 
        self.table.setVerticalHeaderItem(row_idx, QTableWidgetItem(str(row_idx + 1)))
        
        # Traitement optimisé des colonnes par batch
        items_to_set = []  # Liste des (row, col, item) à traiter ensemble
        
        # Traiter toutes les colonnes UI (8 colonnes maintenant, AVEC Nb Pièces)
        for col_idx in range(len(Config.UI_HEADERS)):
            item = self._create_table_item(record, col_idx, db_id, search_term)
            items_to_set.append((row_idx, col_idx, item))
        
        # Appel groupé de setItem pour cette ligne (plus efficace)
        for row, col, item in items_to_set:
            self.table.setItem(row, col, item)
    
    def _create_table_item(self, record, col_idx: int, db_id: int, search_term) -> QTableWidgetItem:
        """Créer un item de table optimisé"""
        if col_idx < len(Config.DB_HEADERS):
            # Colonnes normales de la DB: record[0] = id, record[1..7] = données colonnes
            if col_idx + 1 < len(record):
                actual_data = record[col_idx + 1]  # record[0] = db_id, donc col_idx + 1
                item = QTableWidgetItem(str(actual_data or ""))
            else:
                item = QTableWidgetItem("")
        else:
            # Dernière colonne: Nb Pièces (record[-1] = pieces_count)
            pieces_count = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
            item = QTableWidgetItem(str(pieces_count))
            # Colonne lecture seule pour le nombre de pièces
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            # Style spécial pour la colonne Nb Pièces
            if pieces_count > 0:
                item.setBackground(QColor(220, 248, 198))  # Vert clair
                item.setToolTip(f"{pieces_count} pièce(s) associée(s)")
            else:
                item.setBackground(QColor(248, 248, 248))  # Gris clair
                item.setToolTip("Aucune pièce associée")
        
        # Stocker le db_id dans chaque cellule via UserRole
        item.setData(Qt.ItemDataRole.UserRole, db_id)
        
        # Optimisation: Mise en évidence des résultats de recherche (sauf pour la colonne Nb Pièces)
        if search_term and col_idx < len(Config.DB_HEADERS):
            self._apply_search_highlight(item, search_term)
        
        return item
    
    def _apply_search_highlight(self, item: QTableWidgetItem, search_term):
        """Appliquer la mise en évidence de recherche de manière optimisée"""
        item_text = str(item.text()).lower()
        should_highlight = False
        
        if isinstance(search_term, str):
            # Recherche simple (chaîne)
            should_highlight = search_term.lower() in item_text
        elif isinstance(search_term, dict):
            # Recherche parsée (dictionnaire)
            if search_term.get('type') == 'simple':
                # Recherche simple parsée
                terms = search_term.get('terms', [])
                if terms:
                    should_highlight = terms[0].lower() in item_text
            elif search_term.get('type') == 'regex':
                # Recherche par expression régulière
                try:
                    import re
                    pattern = search_term.get('pattern', '')
                    should_highlight = bool(re.search(pattern, item_text, re.IGNORECASE))
                except:
                    pass
            elif search_term.get('type') == 'or':
                # Recherche avec opérateurs OR
                for group in search_term.get('groups', []):
                    if group.get('type') == 'and':
                        # Tous les termes doivent être présents
                        if all(term.lower() in item_text for term in group.get('terms', [])):
                            should_highlight = True
                            break
        
        if should_highlight:
            item.setBackground(QColor(*Config.SEARCH_HIGHLIGHT_COLOR))

    def _get_db_id_from_row(self, row: int) -> int:
        """Récupérer le db_id depuis la première cellule de la ligne"""
        # Chercher dans la première cellule non-vide de la ligne
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item and item.data(Qt.ItemDataRole.UserRole) is not None:
                return int(item.data(Qt.ItemDataRole.UserRole))
        raise ValueError(f"Aucun db_id trouvé pour la ligne {row}")
    
    def _on_header_clicked(self, logical_index: int):
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
            
            # Appliquer le tri via la base de données
            self._apply_database_sort()
            
        except Exception as e:
            app_logger.error(f"Erreur lors du tri: {e}")
    
    def _apply_database_sort(self):
        """Appliquer le tri via une nouvelle requête SQL"""
        try:
            # Mettre à jour les indicateurs visuels de tri avec des flèches Unicode
            self._update_sort_indicators()
            
            # Recharger les données avec le nouveau tri
            # Utiliser la recherche parsée actuelle
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term)
            
        except Exception as e:
            app_logger.error(f"Erreur lors de l'application du tri: {e}")
    
    def _update_sort_indicators(self):
        """Mettre à jour les indicateurs de tri dans les en-têtes avec des flèches Unicode"""
        try:
            # Récupérer les en-têtes originaux sans flèches
            original_headers = Config.DB_HEADERS + ["Nb Pièces"]
            
            # Mettre à jour tous les en-têtes
            for col_idx, header_text in enumerate(original_headers):
                if col_idx == self.current_sort_column:
                    # Ajouter la flèche appropriée
                    if self.current_sort_order == Qt.SortOrder.AscendingOrder:
                        header_with_arrow = f"{header_text} ↑"
                    else:
                        header_with_arrow = f"{header_text} ↓"
                    self.table.horizontalHeaderItem(col_idx).setText(header_with_arrow)
                else:
                    # Enlever toute flèche existante
                    self.table.horizontalHeaderItem(col_idx).setText(header_text)
                    
        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateurs tri: {e}")
    
    def _get_modern_style(self) -> str:
        """Retourne le CSS moderne dans l'esprit Bootstrap"""
        return """
        /* Style général moderne */
        QMainWindow {
            background-color: #f8f9fa;
            color: #212529;
        }
        
        /* Tableaux */
        QTableWidget {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            selection-background-color: #007bff;
            gridline-color: #e9ecef;
        }
        
        QHeaderView::section {
            background-color: #e9ecef;
            color: #495057;
            padding: 8px 12px;
            border: none;
            border-right: 1px solid #dee2e6;
            font-weight: 600;
        }
        
        QHeaderView::section:hover {
            background-color: #dee2e6;
        }
        
        /* Indicateurs de tri dans les en-têtes - Utilisera des caractères Unicode */
        QHeaderView::up-arrow {
            width: 0px;
            height: 0px;
        }
        
        QHeaderView::down-arrow {
            width: 0px;
            height: 0px;
        }
        
        /* Boutons modernes */
        QPushButton {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
            min-height: 20px;
        }
        
        QPushButton:hover {
            background-color: #0056b3;
        }
        
        QPushButton:pressed {
            background-color: #004085;
        }
        
        QPushButton:disabled {
            background-color: #6c757d;
            color: #adb5bd;
        }
        
        /* Bouton Incomplètes spécial */
        QPushButton#incompleteBtn {
            background-color: #ffc107;
            color: #212529;
        }
        
        QPushButton#incompleteBtn:hover {
            background-color: #e0a800;
        }
        
        QPushButton#incompleteBtn:checked {
            background-color: #fd7e14;
            color: white;
        }
        
        /* Bouton de validation des incohérences */
        QPushButton#validationBtn {
            background-color: #17a2b8;
            color: white;
            border: none;
            padding: 8px 16px;
            font-weight: 500;
        }
        
        QPushButton#validationBtn:hover {
            background-color: #138496;
        }
        
        QPushButton#validationBtn:pressed {
            background-color: #0c5460;
        }
        
        /* Bouton refresh moderne */
        QPushButton#refreshBtn {
            background-color: transparent;
            color: #6c757d;
            border: 1px solid #dee2e6;
            padding: 4px 8px;
            font-size: 14px;
            min-width: 24px;
            max-width: 24px;
        }
        
        QPushButton#refreshBtn:hover {
            background-color: #e9ecef;
            color: #495057;
        }
        
        /* Boutons de pagination */
        QPushButton#paginationBtn {
            background-color: white;
            color: #007bff;
            border: 1px solid #dee2e6;
            padding: 4px 8px;
            margin: 2px;
            min-width: 24px;
            max-width: 32px;
        }
        
        QPushButton#paginationBtn:hover {
            background-color: #e9ecef;
            border-color: #007bff;
        }
        
        QPushButton#paginationBtn:disabled {
            background-color: #f8f9fa;
            color: #6c757d;
            border-color: #dee2e6;
        }
        
        /* Champs de saisie */
        QLineEdit {
            background-color: white;
            border: 1px solid #ced4da;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 14px;
        }
        
        QLineEdit:focus {
            border-color: #80bdff;
            background-color: #fff;
        }
        
        /* Titre historique */
        QLabel#historyTitle {
            font-weight: 600;
            color: #495057;
            font-size: 14px;
            padding: 2px 0px;
        }
        
        /* Listes */
        QListWidget {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 4px;
        }
        
        QListWidget::item {
            padding: 2px 8px;
            border-radius: 4px;
            margin: 0px;
            line-height: 1.2;
        }
        
        QListWidget::item:selected {
            background-color: #007bff;
            color: white;
        }
        
        QListWidget::item:hover {
            background-color: #f8f9fa;
            color: #212529;
        }
        
        /* ComboBox */
        QComboBox {
            background-color: white;
            border: 1px solid #ced4da;
            border-radius: 6px;
            padding: 6px 30px 6px 12px;
            min-width: 80px;
            color: #212529;
            font-size: 14px;
        }
        
        QComboBox:hover {
            border-color: #80bdff;
            background-color: #f8f9fa;
        }
        
        QComboBox:focus {
            border-color: #007bff;
            background-color: white;
            outline: none;
        }
        
        QComboBox:disabled {
            background-color: #e9ecef;
            color: #6c757d;
            border-color: #dee2e6;
        }
        
        QComboBox::drop-down {
            border: none;
            width: 20px;
            background-color: transparent;
        }
        
        QComboBox::down-arrow {
            image: none;
            border: 2px solid #495057;
            width: 6px;
            height: 6px;
            border-top: none;
            border-left: none;
            margin-right: 4px;
        }
        
        QComboBox::down-arrow:hover {
            border-color: #007bff;
        }
        
        /* ComboBox dropdown styles améliorés */
        QComboBox QAbstractItemView {
            background-color: white;
            border: 1px solid #ced4da;
            border-radius: 6px;
            outline: none;
            selection-background-color: #007bff;
            selection-color: white;
        }
        
        QComboBox QAbstractItemView::item {
            padding: 8px 12px;
            border: none;
            color: #212529;
            background-color: transparent;
            min-height: 20px;
        }
        
        QComboBox QAbstractItemView::item:selected {
            background-color: #007bff;
            color: white;
        }
        
        QComboBox QAbstractItemView::item:hover {
            background-color: #e9ecef;
            color: #212529;
        }
        
        QComboBox QAbstractItemView::item:alternate {
            background-color: #f8f9fa;
        }
        
        /* Labels */
        QLabel {
            color: #495057;
        }
        
        /* Statut bar */
        QStatusBar {
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
            color: #6c757d;
        }
        
        /* Sections modernes */
        QWidget#filterSection, QWidget#searchSection, QWidget#paginationSection {
            background-color: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            margin: 4px 0px;
        }
        
        QLabel#sectionTitle {
            font-weight: 600;
            color: #495057;
            font-size: 13px;
            margin-bottom: 4px;
        }
        
        QLabel#perfLabel {
            color: #28a745;
            font-weight: 500;
            font-size: 12px;
        }
        
        QLabel#counterLabel {
            color: #6c757d;
            font-weight: 500;
            font-size: 12px;
        }
        
        QLabel#inlineLabel {
            color: #6c757d;
            font-size: 13px;
        }
        
        /* Page indicator */
        QLabel {
            color: #495057;
        }
        
        /* Toolbar moderne */
        QToolBar#modernToolbar {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: none;
            border-bottom: 1px solid #dee2e6;
            padding: 4px 8px;
            spacing: 8px;
        }
        
        QToolBar#modernToolbar QToolButton {
            background-color: transparent;
            color: #495057;
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 4px 8px;
            margin: 2px;
            font-weight: 500;
        }
        
        QToolBar#modernToolbar QToolButton:hover {
            background-color: #e9ecef;
            border-color: #adb5bd;
        }
        
        QToolBar#modernToolbar QToolButton:pressed {
            background-color: #dee2e6;
            border-color: #6c757d;
        }
        
        QToolBar#modernToolbar QToolButton:disabled {
            color: #adb5bd;
            background-color: transparent;
        }
        
        QToolBar::separator {
            background-color: #dee2e6;
            width: 1px;
            margin: 8px 4px;
        }
        
        /* Tabs modernes */
        QTabWidget::pane {
            border: 1px solid #dee2e6;
            border-radius: 6px;
            background-color: white;
        }
        
        QTabBar::tab {
            background-color: #f8f9fa;
            color: #495057;
            padding: 8px 16px;
            border: 1px solid #dee2e6;
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }
        
        QTabBar::tab:selected {
            background-color: white;
            color: #007bff;
            border-bottom: 2px solid #007bff;
        }
        
        QTabBar::tab:hover:!selected {
            background-color: #e9ecef;
        }
        
        """
    
    def _update_row_numbers(self):
        """Mettre à jour les numéros de lignes après un tri"""
        try:
            for row in range(self.table.rowCount()):
                self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
            app_logger.debug(f"Numéros de lignes mis à jour pour {self.table.rowCount()} lignes")
        except Exception as e:
            app_logger.error(f"Erreur lors de la mise à jour des numéros de lignes: {e}")
    
    def _update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination"""
        if not hasattr(self, 'page_info_label'):
            return
            
        try:
            if self.use_pagination and self.total_rows > Config.MAX_DISPLAY_ROWS:
                total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
                current_page_display = self.current_page + 1
                
                self.page_info_label.setText(f"Page {current_page_display} / {total_pages}")
                
                # Activer/désactiver les boutons
                self.first_page_btn.setEnabled(self.current_page > 0)
                self.prev_page_btn.setEnabled(self.current_page > 0)
                self.next_page_btn.setEnabled(self.current_page < total_pages - 1)
                self.last_page_btn.setEnabled(self.current_page < total_pages - 1)
                
                # Afficher les contrôles
                for btn in [self.first_page_btn, self.prev_page_btn, self.next_page_btn, self.last_page_btn]:
                    btn.show()
                self.page_info_label.show()
            else:
                # Masquer les contrôles si pas de pagination
                self.page_info_label.setText("Tout affiché")
                for btn in [self.first_page_btn, self.prev_page_btn, self.next_page_btn, self.last_page_btn]:
                    btn.hide()
                    
        except Exception as e:
            app_logger.error(f"Erreur mise à jour pagination: {e}")
    
    def _next_page(self):
        """Aller à la page suivante"""
        if self.total_rows > 0:
            total_pages = (self.total_rows + self.page_size - 1) // self.page_size
            if self.current_page < total_pages - 1:
                self.current_page += 1
                # Utiliser la recherche parsée actuelle
                search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
                self.load_data(search_term, is_search=bool(search_term))
    
    def _previous_page(self):
        """Aller à la page précédente"""
        if self.current_page > 0:
            self.current_page -= 1
            search_text = self.search_input.text()
            self.load_data(search_text, is_search=bool(search_text.strip()))
    
    def _go_to_page(self, page: int):
        """Aller à une page spécifique"""
        if self.total_rows > 0:
            total_pages = (self.total_rows + self.page_size - 1) // self.page_size
            if 0 <= page < total_pages:
                self.current_page = page
                # Utiliser la recherche parsée actuelle
                search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
                self.load_data(search_term, is_search=bool(search_term))
    
    def _go_to_last_page(self):
        """Aller à la dernière page"""
        if self.total_rows > 0:
            total_pages = (self.total_rows + self.page_size - 1) // self.page_size
            self.current_page = max(0, total_pages - 1)
            # Utiliser la recherche parsée actuelle
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term)
    
    def _change_page_size(self, size_text: str):
        """Changer la taille de page"""
        try:
            if size_text == "Tout":
                self.use_pagination = False
            else:
                self.use_pagination = True
                self.page_size = int(size_text)
                
            self.current_page = 0  # Retour à la première page
            # Utiliser la recherche parsée actuelle
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term, is_search=bool(search_term))
            
        except ValueError:
            pass  # Ignorer les valeurs non valides
    
    def _toggle_show_all(self):
        """Basculer entre affichage paginé et affichage de toutes les lignes"""
        try:
            if self.use_pagination:
                # Passer en mode "Toutes les lignes"
                reply = QMessageBox.question(
                    self,
                    "Afficher toutes les lignes",
                    f"Voulez-vous afficher toutes les {self.total_rows} lignes?\n\n"
                    "⚠️ Cela peut être lent si vous avez beaucoup de données.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.use_pagination = False
                    self.show_all_btn.setText("📄 Pagination")
                    self.show_all_btn.setToolTip("Revenir à l'affichage paginé")
                    self.load_data()
            else:
                # Revenir en mode pagination
                self.use_pagination = True
                self.show_all_btn.setText("📋 Toutes les lignes")
                self.show_all_btn.setToolTip("Afficher toutes les lignes (peut être lent)")
                self.current_page = 0
                self.load_data()
                
        except Exception as e:
            app_logger.error(f"Erreur basculement affichage: {e}")
    
    def _navigate_to_empty_cell(self, direction='down'):
        """Navigation intelligente : 
        - Si sur case vide → aller à la case pleine la plus proche
        - Si sur case pleine → aller à la case vide la plus proche"""
        try:
            current_item = self.table.currentItem()
            if not current_item:
                return
                
            current_row = self.table.currentRow()
            current_col = self.table.currentColumn()
            
            # Déterminer si la cellule actuelle est vide ou pleine
            current_text = current_item.text().strip()
            is_current_empty = not current_text
            
            # Rechercher dans la direction spécifiée
            if direction == 'down':
                # Chercher vers le bas
                for row in range(current_row + 1, self.table.rowCount()):
                    item = self.table.item(row, current_col)
                    item_text = item.text().strip() if item else ""
                    is_target_empty = not item_text
                    
                    # Si on est sur une case vide, chercher une case pleine
                    # Si on est sur une case pleine, chercher une case vide
                    if (is_current_empty and not is_target_empty) or (not is_current_empty and is_target_empty):
                        self.table.setCurrentCell(row, current_col)
                        if is_target_empty:  # Si on navigue vers une case vide, l'éditer
                            self.table.editItem(self.table.item(row, current_col) or QTableWidgetItem(""))
                        return
                        
                # Si aucune cellule appropriée trouvée, aller à la fin
                last_row = self.table.rowCount() - 1
                if last_row >= 0:
                    self.table.setCurrentCell(last_row, current_col)
                    
            elif direction == 'up':
                # Chercher vers le haut
                for row in range(current_row - 1, -1, -1):
                    item = self.table.item(row, current_col)
                    item_text = item.text().strip() if item else ""
                    is_target_empty = not item_text
                    
                    # Si on est sur une case vide, chercher une case pleine
                    # Si on est sur une case pleine, chercher une case vide
                    if (is_current_empty and not is_target_empty) or (not is_current_empty and is_target_empty):
                        self.table.setCurrentCell(row, current_col)
                        if is_target_empty:  # Si on navigue vers une case vide, l'éditer
                            self.table.editItem(self.table.item(row, current_col) or QTableWidgetItem(""))
                        return
                        
                # Si aucune cellule appropriée trouvée, aller au début
                if self.table.rowCount() > 0:
                    self.table.setCurrentCell(0, current_col)
                
        except Exception as e:
            app_logger.error(f"Erreur navigation cellule: {e}")
    
    def _show_column_values_list(self):
        """Afficher une liste des valeurs existantes dans la colonne courante (Cmd+D)"""
        try:
            current_item = self.table.currentItem()
            if not current_item:
                return
                
            current_col = self.table.currentColumn()
            if current_col < 0:
                return
                
            # Récupérer le nom du champ DB
            db_field = self._get_db_field_name(current_col)
            if not db_field:
                return
                
            # Récupérer toutes les valeurs uniques de cette colonne depuis la DB
            query = f"SELECT DISTINCT [{db_field}] FROM appareils WHERE [{db_field}] IS NOT NULL AND [{db_field}] != '' ORDER BY [{db_field}] LIMIT 100"
            
            try:
                results = self.db_manager.execute_custom_query(query)
                values = [row[0] for row in results if row[0] and row[0].strip()]
                
                if not values:
                    QMessageBox.information(self, "Valeurs de colonne", "Aucune valeur trouvée dans cette colonne")
                    return
                    
                # Limiter à 100 valeurs pour la performance
                if len(values) > 100:
                    values = values[:100]
                    values.append("... (plus de valeurs disponibles)")
                
                # Afficher la liste de sélection
                selected_value, ok = QInputDialog.getItem(
                    self, 
                    f"Valeurs de la colonne '{Config.UI_HEADERS[current_col]}'",
                    f"Choisir une valeur ({len(values)} disponible(s)):",
                    values,
                    0,
                    True  # Editable
                )
                
                if ok and selected_value and not selected_value.startswith("..."):
                    # Appliquer la valeur sélectionnée
                    current_item.setText(selected_value)
                    
                    # Déclencher la sauvegarde
                    self._on_cell_changed(current_item)
                    
            except Exception as e:
                app_logger.error(f"Erreur récupération valeurs colonne: {e}")
                QMessageBox.warning(self, "Erreur", f"Impossible de récupérer les valeurs: {e}")
                
        except Exception as e:
            app_logger.error(f"Erreur affichage valeurs colonne: {e}")
    
    def _get_db_field_name(self, ui_column: int) -> str:
        """Mapper l'index de colonne UI vers le nom de champ DB"""
        # Mapping avec la nouvelle colonne Nb Pièces
        # UI: Type(0), Fabricant(1), Ref_Modele(2), Commercial_Ref(3), Other_Ref(4), Category(5), Notes(6), Nb_Pieces(7)
        # DB: type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes
        if ui_column < len(Config.DB_HEADERS):
            column_mapping = {
                0: 'type',           # Colonne A -> Type
                1: 'manufacturer',   # Colonne B -> Fabricant  
                2: 'ref_modele',     # Colonne C -> Référence modèle
                3: 'commercial_ref', # Colonne D -> Référence commerciale ✅
                4: 'other_ref',      # Colonne E -> Autre référence
                5: 'category',       # Colonne F -> Catégorie
                6: 'notes'           # Colonne G -> Notes
            }
            return column_mapping.get(ui_column)
        else:
            # Colonne 7 = Nb pièces (lecture seule, pas de champ DB correspondant)
            return None

    def _on_current_item_changed(self, current, previous):
        """Capturer la valeur précédente avant modification"""
        if previous:
            key = (previous.row(), previous.column())
            self.previous_values[key] = previous.text()
        
        # Capturer aussi la valeur de la cellule actuelle
        if current:
            key = (current.row(), current.column())
            self.previous_values[key] = current.text()
    
    def _on_item_double_clicked(self, item):
        """Capturer la valeur avant l'édition lors du double-clic"""
        if item:
            key = (item.row(), item.column())
            self.previous_values[key] = item.text()
    
    def _init_previous_values(self):
        """Initialiser les valeurs précédentes pour toutes les cellules après le chargement"""
        try:
            for row in range(self.table.rowCount()):
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        key = (row, col)
                        self.previous_values[key] = item.text()
        except Exception as e:
            print(f"Erreur lors de l'initialisation des valeurs précédentes: {e}")
    
    def _on_cell_changed(self, item: QTableWidgetItem):
        """Gérer les modifications de cellules"""
        if self.table.signalsBlocked():
            return

        row, col = item.row(), item.column()
        new_value = item.text()
        
        # Auto-complétion désactivée temporairement pour éviter les plantages
        # if col in [0, 1] and new_value and (row, col) not in getattr(self.table, 'active_combos', {}):  # Colonnes Type (0) et Fabricant (1)
        #     self.table._activate_autocomplete_cell(row, col)
        
        # Obtenir l'ancienne valeur
        key = (row, col)
        old_value = self.previous_values.get(key, '')
        
        # Ne pas traiter si la valeur n'a pas changé
        if old_value == new_value:
            return
        
        # Validation (en excluant la colonne Nb Pièces)
        if col == len(Config.DB_HEADERS):  # Dernière colonne "Nb Pièces" - lecture seule
            item.setText(old_value)  # Restaurer l'ancienne valeur
            return
            
        # Mapper l'index de colonne vers le nom de champ DB
        field_name = self._get_db_field_name(col)
        
        if field_name:
            validation_result = self.validator.validate_field(field_name, new_value)
            if not validation_result.is_valid:
                QMessageBox.warning(self, "Validation", validation_result.error_message)
                item.setText(old_value)  # Restaurer l'ancienne valeur
                return
        
        # Marquer comme modifié (sans mise en évidence visuelle)
        self.modified_cells.add((row, col))
        
        # Mettre à jour l'indicateur
        self.save_indicator.setText(Config.get_message('save_pending'))
        self.save_indicator.setStyleSheet("color: orange;")
        
        # Enregistrer dans l'historique
        self.undo_manager.add_action({
            'type': 'cell_edit',
            'row': row,
            'col': col,
            'old_value': old_value,
            'new_value': new_value,
            'db_id': self.table.verticalHeaderItem(row).text() if self.table.verticalHeaderItem(row) else None
        })
        
        # Ajouter à l'historique enrichi
        try:
            # Obtenir le nom de la colonne
            column_name = self._get_column_display_name(col)
            
            # Obtenir la référence de l'appareil
            appareil_ref = ""
            try:
                db_id = self._get_db_id_from_row(row)
                # Logique pour obtenir la référence (comme dans _edit_piece)
                ref_modele_item = self.table.item(row, 2)
                if ref_modele_item and ref_modele_item.text().strip():
                    appareil_ref = ref_modele_item.text().strip()
                else:
                    commercial_ref_item = self.table.item(row, 3)
                    if commercial_ref_item and commercial_ref_item.text().strip():
                        appareil_ref = commercial_ref_item.text().strip()
                    else:
                        appareil_ref = f"ID:{db_id}"
            except Exception:
                appareil_ref = f"Ligne {row + 1}"
            
            # Formater les valeurs pour affichage
            old_display = f"'{old_value}'" if old_value else "vide"
            new_display = f"'{new_value}'" if new_value else "vide"
            
            # Ajouter le message à l'historique seulement si auto-save activé
            if getattr(self, 'auto_save_enabled', True):
                self._add_to_history(
                    f"Modification cellule: {column_name} - Appareil: {appareil_ref} - {old_display} → {new_display}"
                )
        except Exception as e:
            print(f"Erreur ajout historique: {e}")
        
        # Mettre à jour la valeur précédente
        self.previous_values[key] = new_value
        
        self._update_toolbar_states()

    def _on_selection_changed(self):
        """Gérer le changement de sélection"""
        self._position_drag_handle()
        self._update_pieces_panel()

    # --- Méthodes utilitaires ---

    def _get_column_display_name(self, col_index):
        """
        Récupère le nom d'affichage d'une colonne basé sur son index
        
        Args:
            col_index (int): Index de la colonne (0-based)
            
        Returns:
            str: Nom d'affichage de la colonne
        """
        try:
            if 0 <= col_index < len(Config.UI_HEADERS):
                return Config.UI_HEADERS[col_index]
            else:
                return f"Colonne {col_index + 1}"
        except Exception as e:
            return f"Colonne {col_index + 1}"

    # --- Méthodes d'export ---

    def _export_data(self, export_format: ExportFormat):
        """Export avec sélection de référence (comportement original)"""
        search_term = self.search_input.text().strip()
        if not search_term:
            QMessageBox.information(self, "Information", "Veuillez entrer un terme de recherche")
            return
        
        try:
            # Détecter si c'est une recherche multiple OR pour proposer sélection de référence
            parsed_term = getattr(self, 'pending_search_term', search_term)
            
            # Gérer différemment selon le format d'export
            if export_format == ExportFormat.CSV:
                # Pour CSV : demander sélection de référence pour recherches multiples
                if isinstance(parsed_term, dict) and parsed_term.get('type') == 'or':
                    # Extraire tous les termes de la recherche OR
                    terms = []
                    for group in parsed_term.get('groups', []):
                        terms.extend(group.get('terms', []))
                    
                    if terms:
                        # Demander à l'utilisateur de choisir une référence
                        selected_reference = self._show_reference_selection_dialog(
                            "Référence pour l'export CSV",
                            f"Recherche multiple détectée ({len(terms)} références).\n"
                            f"Termes: {', '.join(terms)}\n"
                            f"Choisissez la référence à utiliser pour l'export :",
                            terms[0]  # Premier terme par défaut
                        )
                        
                        if not selected_reference:
                            return  # Utilisateur a annulé
                        
                        export_data_term = parsed_term
                        export_reference = selected_reference
                    else:
                        export_data_term = search_term
                        export_reference = search_term
                else:
                    # Recherche simple - TOUJOURS demander confirmation de la référence
                    selected_reference = self._show_reference_selection_dialog(
                        "Référence pour l'export CSV",
                        f"Référence détectée : {search_term}\n"
                        f"Confirmez ou modifiez la référence à utiliser pour la première colonne :",
                        search_term  # Terme de recherche actuel par défaut
                    )
                    
                    if not selected_reference:
                        return  # Utilisateur a annulé
                        
                    export_data_term = search_term 
                    export_reference = selected_reference
            else:
                # Pour HTML : pas de demande de confirmation, utiliser directement tous les résultats
                export_data_term = parsed_term if isinstance(parsed_term, dict) else search_term
                export_reference = "recherche_multiple"  # Nom générique pour HTML
            
            # Charger les résultats pour vérification
            results = self.db_manager.load_data(search_term=parsed_term)
            if not results:
                QMessageBox.information(self, "Information", "Aucun résultat trouvé pour cette recherche")
                return
            
            # Exporter avec tous les résultats mais utiliser la référence sélectionnée pour le fichier
            success = self._export_with_custom_reference(export_data_term, export_reference, export_format, len(results))
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'export: {e}")
    
    def _export_with_custom_reference(self, search_data_term, reference_for_file: str, export_format: ExportFormat, results_count: int) -> bool:
        """Exporter avec tous les résultats mais utiliser une référence spécifique pour le nom et la première colonne"""
        try:
            # Récupérer toutes les données avec la recherche complète
            if isinstance(search_data_term, dict):
                # Recherche complexe - utiliser get_export_data avec fallback
                data = self.db_manager.get_export_data(search_data_term)
            else:
                # Recherche simple
                data = self.db_manager.get_export_data(search_data_term)
            
            if not data:
                raise Exception(f"Aucune donnée trouvée pour la recherche")
            
            # Créer un filename personnalisé avec la référence sélectionnée
            if export_format == ExportFormat.CSV:
                filename = f"{reference_for_file}_everyParts.csv"
                success = self._export_csv_with_reference(data, filename, reference_for_file)
                if success:
                    self._add_to_history(f"Export CSV: {filename} ({len(data)} lignes)")
                return success
            elif export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
                success = self._export_html_with_reference(data, reference_for_file, export_format)
                if success:
                    format_name = "HTML Marques" if export_format == ExportFormat.HTML_BRANDS else "HTML Détails"
                    self._add_to_history(f"Export {format_name}: {len(data)} résultats copiés")
                return success
            else:
                # Autres formats non supportés pour export avec référence personnalisée
                raise Exception(f"Format d'export {export_format} non supporté avec référence personnalisée")
                
        except Exception as e:
            raise Exception(f"Erreur lors de l'export personnalisé: {e}")
    
    def _export_csv_with_reference(self, data, filename: str, reference: str) -> bool:
        """Exporter en CSV avec format exact spécifié"""
        try:
            import csv
            import os
            
            # Chemin vers le Bureau
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            full_path = os.path.join(desktop_path, filename)
            
            with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                # En-têtes exacts selon spécification
                headers = ['product', 'type', 'manufacturer', 'modele_name', 'reference_modele', 'commercial_reference']
                writer.writerow(headers)
                
                # Données selon le format spécifié
                for row in data:
                    # get_export_data structure: [type, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece]
                    # Indexes:                     0     1            2           3               4          5
                    
                    type_val = row[0] if len(row) > 0 else ''
                    manufacturer_val = row[1] if len(row) > 1 else ''
                    ref_modele_val = row[2] if len(row) > 2 else ''
                    commercial_ref_val = row[3] if len(row) > 3 else ''
                    
                    # modele_name = "Référence Modèle - Référence Commerciale"
                    modele_name = f"{ref_modele_val} - {commercial_ref_val}".strip(' -')
                    
                    csv_row = [
                        reference,                    # product: Référence confirmée
                        type_val,                     # type: Type  
                        manufacturer_val,             # manufacturer: Fabricant
                        modele_name,                  # modele_name: "Référence Modèle - Référence Commerciale"
                        ref_modele_val,               # reference_modele: Référence Modèle
                        commercial_ref_val            # commercial_reference: Référence Commerciale
                    ]
                    writer.writerow(csv_row)
            
            return True
            
        except Exception as e:
            raise Exception(f"Erreur export CSV: {e}")
    
    def _export_html_with_reference(self, data, reference: str, export_format: ExportFormat) -> bool:
        """Exporter en HTML avec référence personnalisée"""
        try:
            if export_format == ExportFormat.HTML_BRANDS:
                # Extraire les marques uniques
                brands = set()
                for record in data:
                    manufacturer = record[1]  # Index 1 = manufacturer
                    if manufacturer and manufacturer.strip():
                        brands.add(manufacturer.strip())
                
                # Générer les liens HTML
                html_links = []
                for brand in sorted(brands):
                    html_links.append(f'<a href="#{brand}">{brand}</a>')
                
                result = ' '.join(html_links)
            else:  # HTML_DETAILS
                # Version simplifiée des détails HTML
                brands_data = {}
                for record in data:
                    manufacturer = record[1]  # Index 1 = manufacturer
                    ref_modele = record[2]    # Index 2 = ref_modele
                    commercial_ref = record[3] # Index 3 = commercial_ref
                    
                    if manufacturer and manufacturer.strip():
                        if manufacturer not in brands_data:
                            brands_data[manufacturer] = []
                        brands_data[manufacturer].append({
                            'ref_modele': ref_modele or '',
                            'commercial_ref': commercial_ref or ''
                        })
                
                # Générer HTML simplifié
                html_parts = []
                for brand in sorted(brands_data.keys()):
                    html_parts.append(f'<h3>{brand}</h3>')
                    for item in brands_data[brand]:
                        ref_text = f"{item['ref_modele']} - {item['commercial_ref']}" if item['ref_modele'] and item['commercial_ref'] else (item['ref_modele'] or item['commercial_ref'])
                        html_parts.append(f'<p>{ref_text}</p>')
                
                result = '\n'.join(html_parts)
            
            # Copier dans le presse-papiers
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(result)
            
            return True
            
        except Exception as e:
            raise Exception(f"Erreur export HTML: {e}")
    
    def _export_data_legacy(self, export_format: ExportFormat):
        """Ancienne méthode d'export (fallback)"""
        
        # Sauvegarder le terme de recherche original avant modification
        original_search_term = search_term
        is_multi_reference_export = False
        
        # Afficher dialogue de sélection de référence pour TOUS les exports CSV
        if export_format == ExportFormat.CSV:
            multi_terms = self._get_multi_reference_terms()
            if multi_terms:
                is_multi_reference_export = True
                # Demander à l'utilisateur de confirmer/choisir la référence pour CSV multi-références
                selected_reference = self._show_reference_selection_dialog(
                    "Référence pour l'export CSV",
                    f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                    f"Choisissez la référence à utiliser pour la première colonne :",
                    multi_terms[0]  # Premier terme par défaut
                )
            else:
                # Recherche simple - TOUJOURS afficher le dialogue pour confirmer la référence
                selected_reference = self._show_reference_selection_dialog(
                    "Référence pour l'export CSV",
                    f"Référence détectée : {search_term}\n"
                    f"Confirmez ou modifiez la référence à utiliser pour la première colonne :",
                    search_term  # Terme de recherche actuel par défaut
                )
                
            if not selected_reference:
                return  # Annulé par l'utilisateur
            
            # Pas de validation - l'utilisateur peut saisir une référence non présente en BDD
            
            # Remplacer le search_term par la référence sélectionnée pour l'export CSV
            search_term = selected_reference
        
        try:
            # Récupérer les filtres de colonnes actifs
            column_filters = {}
            for col_idx, filter_widget in self.filter_widgets.items():
                if filter_widget is not None:  # Skip removed filters
                    if isinstance(filter_widget, QComboBox):
                        filter_text = filter_widget.currentText().strip()
                    else:  # QLineEdit
                        filter_text = filter_widget.text().strip()
                    if filter_text:
                        column_filters[col_idx] = filter_text
            
            # Récupérer le filtre des lignes incomplètes si activé
            incomplete_filter = getattr(self, 'show_incomplete_only', False)
            
            # Pour les exports CSV, utiliser une méthode simplifiée qui exporte directement le tableau
            if export_format == ExportFormat.CSV:
                try:
                    result = self._export_displayed_table_as_csv(search_term)
                    if result:
                        self._add_to_history(f"Export CSV: {result}")
                    return  # Sortir ici pour éviter le code complexe
                except Exception as csv_error:
                    import traceback
                    traceback.print_exc()
                    QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export CSV:\n{csv_error}")
                    return
            
            # Pour les autres formats, utiliser l'ancien système
            use_custom_export = False
            
            if use_custom_export:
                try:
                    # Export personnalisé - utiliser les données de recherche avec référence custom
                    result = self._export_custom_reference_csv_with_current_data(search_term, original_search_term)
                except Exception as e:
                    app_logger.error(f"Erreur export référence personnalisée: {e}")
                    # Fallback simple: créer un CSV minimal avec juste la référence personnalisée
                    try:
                        result = self._create_minimal_csv_fallback(search_term)
                        QMessageBox.information(self, "Export de secours", 
                                              f"L'export personnalisé a échoué.\n"
                                              f"Un fichier CSV minimal a été créé avec votre référence.")
                    except Exception as e2:
                        app_logger.error(f"Erreur fallback export: {e2}")
                        QMessageBox.warning(self, "Erreur d'export", 
                                          f"Impossible d'exporter les données.\n"
                                          f"Erreur: {e}\n"
                                          f"Erreur fallback: {e2}")
                        return
            else:
                # Pour les exports HTML, utiliser le terme de recherche original pour préserver les opérateurs || et &&
                export_search_term = original_search_term if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS] else search_term
                result = self.exporter.export_search_results(export_search_term, export_format, 
                                                           column_filters=column_filters, 
                                                           incomplete_filter=incomplete_filter)
            
            if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
                # Copier dans le presse-papiers
                QApplication.clipboard().setText(result)
                
                # Afficher les informations sur le format utilisé pour HTML Détails
                if export_format == ExportFormat.HTML_DETAILS:
                    export_info = self.exporter.get_last_export_info()
                    if export_info:
                        format_msg = f"Export HTML copié ({export_info['description']}) - {export_info['char_count']:,} caractères"
                        if export_info['format_used'] != 'complet':
                            format_msg += f" (limite: {export_info['char_limit']:,})"
                        self.statusbar.showMessage(format_msg, Config.LONG_STATUS_MESSAGE_TIMEOUT * 2)
                    else:
                        self.statusbar.showMessage(Config.get_message('data_copied'), Config.STATUS_MESSAGE_TIMEOUT)
                else:
                    self.statusbar.showMessage(Config.get_message('data_copied'), Config.STATUS_MESSAGE_TIMEOUT)
            else:
                self.statusbar.showMessage(result, Config.LONG_STATUS_MESSAGE_TIMEOUT)
                
                # Ajouter l'export dans l'historique avec le chemin du fichier
                if export_format == ExportFormat.CSV:
                    self._add_to_history(f"Export CSV: {result}")
                else:
                    self._add_to_history(f"Export {export_format.value}: {result}")
                
        except ExportError as e:
            self._show_error(f"Erreur d'export: {e}")

    # --- Méthodes utilitaires ---

    def _show_error(self, message: str):
        """Afficher une erreur"""
        QMessageBox.critical(self, "Erreur", message)

    def _show_info(self, message: str):
        """Afficher une information"""
        QMessageBox.information(self, "Information", message)
    
    def _show_confirmation(self, title: str, message: str, default_yes: bool = False) -> bool:
        """Afficher une confirmation avec support des raccourcis clavier (Entrée/Échap)"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        
        # Créer les boutons
        yes_btn = msg_box.addButton("Oui", QMessageBox.YesRole)
        no_btn = msg_box.addButton("Non", QMessageBox.NoRole)
        
        # Configurer le bouton par défaut
        if default_yes:
            msg_box.setDefaultButton(yes_btn)
            yes_btn.setDefault(True)
        else:
            msg_box.setDefaultButton(no_btn)
            no_btn.setDefault(True)
        
        # Configurer les raccourcis clavier
        yes_btn.setShortcut("Return")  # Entrée
        no_btn.setShortcut("Escape")   # Échap
        
        # Afficher et récupérer le résultat
        result = msg_box.exec_()
        return msg_box.clickedButton() == yes_btn
    
    def _show_save_confirmation(self, title: str, message: str):
        """Afficher une confirmation Oui/Non/Annuler avec raccourcis clavier"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        
        # Créer les boutons
        yes_btn = msg_box.addButton("Oui", QMessageBox.YesRole)
        no_btn = msg_box.addButton("Non", QMessageBox.NoRole) 
        cancel_btn = msg_box.addButton("Annuler", QMessageBox.RejectRole)
        
        # Configurer le bouton par défaut
        msg_box.setDefaultButton(yes_btn)
        yes_btn.setDefault(True)
        
        # Configurer les raccourcis clavier
        yes_btn.setShortcut("Return")  # Entrée pour Oui (sauvegarder)
        cancel_btn.setShortcut("Escape")  # Échap pour Annuler
        # N pour Non
        no_btn.setShortcut("N")
        
        # Afficher et récupérer le résultat
        result = msg_box.exec_()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == yes_btn:
            return "yes"
        elif clicked_button == no_btn:
            return "no"
        else:  # cancel_btn ou fermeture
            return "cancel"

    def _update_counter(self):
        """Mettre à jour le compteur de lignes"""
        displayed_count = self.table.rowCount()
        
        if hasattr(self, 'total_rows') and self.use_pagination and self.total_rows > Config.MAX_DISPLAY_ROWS:
            self.counter_label.setText(f"Affichées : {displayed_count} / Total : {self.total_rows:,}")
        else:
            self.counter_label.setText(f"Lignes : {displayed_count:,}")

    def _update_toolbar_states(self):
        """Mettre à jour l'état des boutons"""
        self.undo_action.setEnabled(self.undo_manager.can_undo())
        self.redo_action.setEnabled(self.undo_manager.can_redo())

    def _position_drag_handle(self):
        """Positionner la poignée de glisser-déposer"""
        # Vérifier si tous les objets existent encore
        if not hasattr(self, 'table') or self.table is None:
            return
        
        if not hasattr(self, 'drag_handle') or self.drag_handle is None:
            return
        
        try:
            selected = self.table.selectedRanges()
            if not selected:
                self.drag_handle.hide()
                return
        except RuntimeError:
            # L'objet table a été détruit
            return
        
        try:
            sel_range = selected[0]
            bottom_right_item = self.table.item(sel_range.bottomRow(), sel_range.rightColumn())
            
            if bottom_right_item:
                rect = self.table.visualItemRect(bottom_right_item)
                if rect.isValid():
                    handle_x = rect.right() - self.drag_handle.width() + 1
                    handle_y = rect.bottom() - self.drag_handle.height() + 1
                    
                    viewport_rect = self.table.viewport().rect()
                    if (handle_x >= 0 and handle_y >= 0 and 
                        handle_x < viewport_rect.width() and 
                        handle_y < viewport_rect.height()):
                        self.drag_handle.move(handle_x, handle_y)
                        self.drag_handle.show()
                    else:
                        self.drag_handle.hide()
                else:
                    self.drag_handle.hide()
            else:
                self.drag_handle.hide()
        except RuntimeError:
            # L'objet table ou drag_handle a été détruit
            return

    # --- Méthodes d'action (stubs pour les fonctionnalités à implémenter) ---

    def _apply_column_filter(self, column: int, text: str):
        """Appliquer un filtre sur une colonne avec debounce de 400ms"""
        # Stocker les informations de filtrage en attente
        self.pending_column_filter = (column, text)
        
        # Redémarrer le timer de debounce
        self.column_filter_timer.stop()
        self.column_filter_timer.start(400)  # 400ms de délai

    def _perform_delayed_column_filter(self):
        """Exécuter le filtrage de colonne après le délai de debounce"""
        if hasattr(self, 'pending_column_filter') and self.pending_column_filter:
            column, text = self.pending_column_filter
            
            # Effectuer le filtrage réel
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term)
            
            # Nettoyer
            self.pending_column_filter = None

    def _populate_dropdown_values(self, combo_widget: QComboBox, column_index: int):
        """Peupler les valeurs du dropdown avec les données uniques de la BDD"""
        try:
            # Déterminer le champ de base de données selon l'index de colonne
            if column_index == 0:  # Type
                db_field = "type"
            elif column_index == 1:  # Fabricant
                db_field = "manufacturer"
            else:
                return  # Ne pas traiter d'autres colonnes
            
            # Requête pour obtenir les valeurs distinctes, non vides, triées
            query = f"""
                SELECT DISTINCT {db_field} 
                FROM appareils 
                WHERE {db_field} IS NOT NULL AND {db_field} != '' 
                ORDER BY {db_field}
            """
            
            results = self.db_manager.execute_query(query)
            
            # Ajouter une option vide en premier
            combo_widget.addItem("")
            
            # Ajouter les valeurs uniques
            for row in results:
                value = row[0]
                if value and value.strip():  # S'assurer que la valeur n'est pas vide
                    combo_widget.addItem(value.strip())
                    
        except Exception as e:
            print(f"⚠️ Erreur lors du peuplement du dropdown colonne {column_index}: {e}")
            # En cas d'erreur, transformer le combo en champ texte basique
            combo_widget.setEditable(True)

    def _parse_advanced_search(self, text: str):
        """Parser la recherche avancée avec opérateurs && et ||"""
        import re
        
        if not text.strip():
            return None
        
        # Vérifier si c'est une expression régulière
        if self.regex_checkbox.isChecked():
            try:
                # Tester la validité de l'expression régulière
                re.compile(text)
                return {
                    'type': 'regex',
                    'pattern': text
                }
            except re.error:
                # Expression régulière invalide, traiter comme recherche normale
                return {
                    'type': 'simple',
                    'terms': [text.strip()]
                }
        
        # Parser les opérateurs logiques
        # Diviser d'abord par || (OU)
        or_groups = text.split('||')
        
        parsed_groups = []
        for group in or_groups:
            group = group.strip()
            if not group:
                continue
                
            # Diviser chaque groupe par && (ET)
            and_terms = [term.strip() for term in group.split('&&') if term.strip()]
            if and_terms:
                parsed_groups.append({
                    'type': 'and',
                    'terms': and_terms
                })
        
        if not parsed_groups:
            # Pas d'opérateurs trouvés, recherche simple
            return {
                'type': 'simple',
                'terms': [text.strip()]
            }
        
        return {
            'type': 'or',
            'groups': parsed_groups
        }
    
    def _search_table(self, text: str):
        """Rechercher dans le tableau avec débounce et support avancé"""
        search_term = text.strip()
        
        # Phase 4: Parser la recherche avancée mais garder terme simple si pas d'opérateurs
        if search_term and ('&&' in search_term or '||' in search_term):
            parsed_search = self._parse_advanced_search(search_term)
            self.pending_search_term = parsed_search
        else:
            # Terme simple - utiliser directement pour éviter problèmes de cache
            self.pending_search_term = search_term
        
        # Arrêter le timer précédent et démarrer un nouveau délai
        self.search_timer.stop()
        self.search_timer.start(500)  # Attendre 500ms avant de lancer la recherche
        
        # Activer/désactiver les boutons d'export et SEO uniquement pour les références de pièce
        has_search = bool(search_term)
        is_piece_search = has_search and self._is_piece_reference_search()
        
        # Tous les boutons d'export nécessitent une référence de pièce
        self.export_csv_btn.setEnabled(is_piece_search)
        self.export_html_brands_btn.setEnabled(is_piece_search)
        self.export_html_details_btn.setEnabled(is_piece_search)
        
        # Boutons SEO également limités aux références de pièce
        self.meta_title_btn.setEnabled(is_piece_search)
        self.meta_desc_btn.setEnabled(is_piece_search)
    
    def _perform_delayed_search(self):
        """Phase 4: Effectuer la recherche via le service avec pagination correcte"""
        if hasattr(self, 'pending_search_term') and self.pending_search_term:
            try:
                # D'abord compter le nombre total pour décider de la pagination
                total_results = self.search_service.count_results(self.pending_search_term)
                
                # Calculer limit et offset seulement si nécessaire
                limit = None
                offset = None
                should_paginate = (self.use_pagination and 
                                 total_results > Config.MAX_DISPLAY_ROWS and 
                                 hasattr(self, 'page_size') and self.page_size > 0)
                
                if should_paginate:
                    limit = self.page_size
                    offset = getattr(self, 'current_page', 0) * self.page_size
                
                # Utiliser le service de recherche avec pagination
                results = self.search_service.search(
                    term=self.pending_search_term,
                    column_filters=getattr(self, '_current_column_filters', None),
                    sort_column=getattr(self, 'current_sort_column', None),
                    sort_order=getattr(self, 'current_sort_order', None),
                    limit=limit,
                    offset=offset
                )
                
                # Mettre à jour l'affichage avec les résultats
                self._display_search_results(results, self.pending_search_term)
                
            except Exception as e:
                print(f"⚠️ Erreur service recherche: {e}")
                # Fallback vers l'ancienne méthode
                self.load_data(self.pending_search_term, is_search=True)
    
    def _display_search_results(self, results: List, search_term: str):
        """Phase 4: Afficher les résultats de recherche du service"""
        # FIXME: Désactiver l'auto-sauvegarde pendant l'affichage
        old_auto_save_enabled = getattr(self, 'auto_save_enabled', True)
        self.auto_save_enabled = False
        
        try:
            # Mettre à jour le compteur total pour la pagination (important!)
            if hasattr(self, 'search_service'):
                self.total_rows = self.search_service.count_results(search_term)
            
            # Réutiliser la logique d'affichage existante mais avec résultats du service
            self.table.setRowCount(len(results))
            
            # Utiliser la logique optimisée Phase 2
            if len(results) > Config.CHUNK_SIZE:
                self._fill_table_chunked(results, None, search_term)
            else:
                self._fill_table_standard(results, None, search_term)
            
            # Finalisation
            self.table.resizeColumnsToContents()
            self._update_counter()
            self._update_pagination_controls()
            self._init_previous_values()
            
        finally:
            # Réactiver l'auto-sauvegarde
            self.auto_save_enabled = old_auto_save_enabled

    def _auto_save(self):
        """Sauvegarde automatique optimisée par lots"""
        # FIXME: Éviter auto-save pendant chargement/recherche
        if not self.modified_cells or not getattr(self, 'auto_save_enabled', True):
            return
        
        try:
            # Regrouper les modifications par ligne (db_id) pour optimiser les transactions
            updates_by_db_id = {}
            
            for row, col in list(self.modified_cells):
                item = self.table.item(row, col)
                if item:
                    db_id = item.data(Qt.ItemDataRole.UserRole)
                    if db_id is None:
                        db_id = self._get_db_id_from_row(row)
                    else:
                        db_id = int(db_id)
                    
                    if db_id not in updates_by_db_id:
                        updates_by_db_id[db_id] = {}
                    
                    column_name = self._get_db_field_name(col)
                    if column_name:
                        updates_by_db_id[db_id][column_name] = item.text()
            
            # Exécuter les mises à jour par lots
            if updates_by_db_id:
                self.db_manager.update_multiple_cells_batch(updates_by_db_id)
                
            # Mettre à jour les valeurs précédentes et nettoyer modified_cells
            for row, col in list(self.modified_cells):
                item = self.table.item(row, col)
                if item:
                    self.previous_values[(row, col)] = item.text()
            
            self.modified_cells.clear()
            
            # Mettre à jour l'indicateur
            self.save_indicator.setText(Config.get_message('auto_save_done'))
            self.save_indicator.setStyleSheet("color: green;")
            
            # Mettre à jour le bouton incomplète si nécessaire
            self._update_incomplete_button_visibility()
            
        except Exception as e:
            self._show_error(f"Erreur lors de la sauvegarde automatique: {e}")

    def _manual_save(self):
        """Sauvegarde manuelle"""
        self._auto_save()
        self.statusbar.showMessage(Config.get_message('auto_save_done'), Config.STATUS_MESSAGE_TIMEOUT)
        # Ajouter à l'historique
        self._add_to_history("Sauvegarde manuelle effectuée")

    def _update_cell_in_db(self, item: QTableWidgetItem):
        """Mettre à jour une cellule dans la base de données"""
        try:
            row, col = item.row(), item.column()
            new_value = item.text()

            # Récupérer l'ancienne valeur depuis self.previous_values
            old_value = self.previous_values.get((row, col), '')

            # Récupérer le db_id depuis les données de l'item
            db_id = item.data(Qt.ItemDataRole.UserRole)
            if db_id is None:
                # Fallback : chercher dans une autre cellule de la ligne
                db_id = self._get_db_id_from_row(row)
            else:
                db_id = int(db_id)
            
            # Mapping direct et simple UI vers DB
            column_name = self._get_db_field_name(col)
            
            # Toutes les colonnes sont maintenant éditables
            if not column_name:
                return False
            
            success = self.db_manager.update_cell(db_id, column_name, new_value)
            
            if success:
                # Ajouter à l'historique seulement si la valeur a réellement changé
                if old_value != new_value:
                    # Nom de la colonne plus convivial
                    column_display_name = self._get_column_display_name(col)
                    self._add_to_history(f"Modification {column_display_name}: '{old_value}' → '{new_value}'")
                
                # Retirer de la liste des modifications
                self.modified_cells.discard((row, col))
                item.setBackground(QColor(255, 255, 255))  # Blanc
                
                if not self.modified_cells:
                    self.save_indicator.setText(Config.get_message('save_success'))
                    self.save_indicator.setStyleSheet("color: green;")
                    
        except Exception as e:
            self._show_error(f"Erreur lors de la mise à jour: {e}")

    def _save_drag_changes(self):
        """Sauvegarder les modifications du glisser-déposer"""
        try:
            # Marquer toutes les cellules modifiées pour sauvegarde
            if hasattr(self, 'drag_handle') and self.drag_handle.orig_selection:
                selection = self.drag_handle.orig_selection
                direction = self.drag_handle.drag_direction
                
                if direction == "down":
                    # Sauvegarder les cellules ajoutées vers le bas
                    start_row = selection.bottomRow() + 1
                    for row in range(start_row, self.table.rowCount()):
                        for col in range(selection.leftColumn(), selection.rightColumn() + 1):
                            item = self.table.item(row, col)
                            if item:
                                self._update_cell_in_db(item)
                                
                elif direction == "up":
                    # Sauvegarder les cellules ajoutées vers le haut
                    end_row = selection.topRow() - 1
                    for row in range(0, end_row + 1):
                        for col in range(selection.leftColumn(), selection.rightColumn() + 1):
                            item = self.table.item(row, col)
                            if item:
                                self._update_cell_in_db(item)
                                
        except Exception as e:
            self._show_error(f"Erreur lors de la sauvegarde du glisser-déposer: {e}")

    def _update_pieces_panel(self):
        """Mettre à jour le panneau des pièces (communes pour sélection multiple)"""
        self.pieces_list.clear()
        
        # Récupérer toutes les lignes sélectionnées
        selected_rows = set()
        selected_ranges = self.table.selectedRanges()
        
        if selected_ranges:
            # Utiliser les plages sélectionnées
            for range_sel in selected_ranges:
                for row in range(range_sel.topRow(), range_sel.bottomRow() + 1):
                    selected_rows.add(row)
        else:
            # Fallback sur la ligne courante si aucune sélection
            current_row = self.table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)
        
        if not selected_rows:
            return
        
        try:
            if len(selected_rows) == 1:
                # Un seul appareil sélectionné - comportement normal
                row = list(selected_rows)[0]
                db_id = self._get_db_id_from_row(row)
                pieces = self.db_manager.get_pieces_for_appareil(db_id)
                
                for ref_piece, description in pieces:
                    item_text = ref_piece
                    if description:
                        item_text += f" - {description}"
                    
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, ref_piece)
                    self.pieces_list.addItem(item)
            
            else:
                # Plusieurs appareils sélectionnés - afficher seulement les pièces communes
                all_pieces_sets = []
                
                for row in selected_rows:
                    try:
                        db_id = self._get_db_id_from_row(row)
                        pieces = self.db_manager.get_pieces_for_appareil(db_id)
                        # Créer un set des références de pièces pour cet appareil
                        piece_refs = {ref_piece for ref_piece, description in pieces}
                        all_pieces_sets.append(piece_refs)
                    except Exception:
                        continue
                
                if all_pieces_sets:
                    # Calculer l'intersection de tous les sets (pièces communes)
                    common_pieces = set.intersection(*all_pieces_sets)
                    
                    if common_pieces:
                        # Récupérer les descriptions des pièces communes
                        # Prendre la description du premier appareil qui contient la pièce
                        for common_ref in sorted(common_pieces):
                            description = ""
                            for row in selected_rows:
                                try:
                                    db_id = self._get_db_id_from_row(row)
                                    pieces = self.db_manager.get_pieces_for_appareil(db_id)
                                    for ref_piece, desc in pieces:
                                        if ref_piece == common_ref and desc:
                                            description = desc
                                            break
                                    if description:
                                        break
                                except Exception:
                                    continue
                            
                            item_text = f"{common_ref} (commune à {len(selected_rows)} appareils)"
                            if description:
                                item_text = f"{common_ref} - {description} (commune à {len(selected_rows)} appareils)"
                            
                            item = QListWidgetItem(item_text)
                            item.setData(Qt.UserRole, common_ref)
                            # Marquer visuellement les pièces communes
                            item.setBackground(QColor(240, 248, 255))  # Bleu très clair
                            self.pieces_list.addItem(item)
                    else:
                        # Aucune pièce commune
                        item = QListWidgetItem(f"Aucune pièce commune aux {len(selected_rows)} appareils sélectionnés")
                        item.setForeground(QColor(108, 117, 125))  # Gris
                        self.pieces_list.addItem(item)
                
        except Exception as e:
            self._show_error(f"Erreur lors de la mise à jour des pièces: {e}")
    
    def _confirm_piece_description_update(self, ref_piece: str, existing_desc: str, new_desc: str) -> str:
        """
        Demander à l'utilisateur de confirmer la mise à jour d'une description de pièce.
        Retourne la description finale à utiliser.
        Utilise un cache pour éviter de redemander pour la même référence.
        """
        # Vérifier si on a déjà une décision pour cette référence + nouvelle description
        cache_key = f"{ref_piece}|{existing_desc}|{new_desc}"
        if cache_key in self._piece_description_decisions:
            return self._piece_description_decisions[cache_key]
        
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Conflit de description de pièce")
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Message d'information
        info_label = QLabel(f"La référence <b>{ref_piece}</b> possède déjà un libellé.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Description existante
        layout.addWidget(QLabel("Libellé actuel :"))
        existing_label = QLabel(f"<i>{existing_desc}</i>")
        existing_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc;")
        existing_label.setWordWrap(True)
        layout.addWidget(existing_label)
        
        # Nouvelle description éditable
        layout.addWidget(QLabel("Nouveau libellé (éditable) :"))
        new_desc_input = QLineEdit()
        new_desc_input.setText(new_desc)
        new_desc_input.selectAll()  # Sélectionner tout le texte
        layout.addWidget(new_desc_input)
        
        # Boutons
        button_layout = QHBoxLayout()
        
        keep_existing_btn = QPushButton("Conserver l'actuel")
        keep_existing_btn.clicked.connect(lambda: dialog.done(0))
        
        use_new_btn = QPushButton("Utiliser le nouveau")
        use_new_btn.clicked.connect(lambda: dialog.done(1))
        use_new_btn.setDefault(True)
        
        button_layout.addWidget(keep_existing_btn)
        button_layout.addWidget(use_new_btn)
        layout.addLayout(button_layout)
        
        # Afficher le dialogue
        result = dialog.exec()
        
        if result == 1:  # Utiliser le nouveau
            final_desc = new_desc_input.text().strip()
            if final_desc:
                # Mettre à jour toutes les entrées de cette référence
                try:
                    update_query = "UPDATE pieces SET description = ? WHERE ref_piece = ?"
                    self.db_manager.cursor.execute(update_query, (final_desc, ref_piece))
                    self.db_manager.conn.commit()
                    print(f"  📝 Toutes les descriptions mises à jour pour {ref_piece}")
                    
                    # Mettre en cache la décision
                    self._piece_description_decisions[cache_key] = final_desc
                    return final_desc
                except Exception as e:
                    print(f"Erreur mise à jour globale: {e}")
                    self._piece_description_decisions[cache_key] = existing_desc
                    return existing_desc
            else:
                self._piece_description_decisions[cache_key] = existing_desc
                return existing_desc
        else:  # Conserver l'existant
            self._piece_description_decisions[cache_key] = existing_desc
            return existing_desc
    
    def _add_to_history(self, message: str):
        """Ajouter un message à l'historique"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Initialiser ou récupérer la liste des messages d'historique
        if not hasattr(self, '_history_messages'):
            self._history_messages = []
        
        # Appliquer le formatage spécialisé pour les messages d'import
        formatted_message = self._format_message_for_history(message, timestamp)
        
        # Ajouter le nouveau message au début de la liste
        self._history_messages.insert(0, formatted_message)
        
        # Limiter à 50 entrées
        if len(self._history_messages) > 50:
            self._history_messages = self._history_messages[:50]
        
        # Reconstruire tout le HTML
        html_content = """<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 12px; margin: 4px; padding: 4px; }
        p { margin: 1px 0; line-height: 1.0; }
        p.message-block { margin: 1px 0; line-height: 1.0; }
        p.separator { margin: 4px 0; }
        .timestamp { color: #666; }
        .message { color: #333; }
        .indented { margin-left: 20px; }
        .import-header { font-weight: bold; color: #2c5282; }
        .import-section { margin-left: 20px; color: #555; }
        .import-summary { margin-left: 20px; color: #2d5a87; font-weight: 500; }
        .entry-separator { height: 8px; margin: 4px 0; }
    </style>
</head>
<body>
"""
        
        # Ajouter tous les messages
        for i, msg in enumerate(self._history_messages):
            # Séparer timestamp et contenu pour styling
            if msg.startswith('[') and '] ' in msg:
                parts = msg.split('] ', 1)
                timestamp_part = parts[0] + ']'
                content_part = parts[1] if len(parts) > 1 else ''
                # Convertir les retours à la ligne en HTML et appliquer l'indentation CSS
                content_part = self._apply_css_indentation(content_part)
                # Cadre rouge (timestamp) : bien séparé du contenu suivant  
                html_content += f"<p class='separator'><span class='timestamp'>{timestamp_part}</span> <span class='message'>{content_part}</span></p>\n"
            else:
                # Convertir les retours à la ligne en HTML avec interligne minimal et indentation CSS
                msg_html = self._apply_css_indentation(msg)
                html_content += f"<p class='message-block'>{msg_html}</p>\n"
            
            # Ajouter une ligne vide sous chaque entrée d'historique (sauf la dernière)
            if i < len(self._history_messages) - 1:
                html_content += "<br>\n"
        
        html_content += """</body>
</html>"""
        
        # Définir le contenu HTML en une fois
        self.history_list.setHtml(html_content)
        
        # Positionner en haut pour voir la dernière entrée
        cursor = self.history_list.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.history_list.setTextCursor(cursor)
    
    def _apply_css_indentation(self, content: str) -> str:
        """Appliquer l'indentation avec des espaces non-sécables pour les lignes ==>"""
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            stripped_line = line.strip()
            
            if (stripped_line.startswith('==> ') or 
                stripped_line.startswith('Créés :') or 
                stripped_line.startswith('Complétion automatique :') or 
                stripped_line.startswith('À compléter :') or 
                stripped_line.startswith('Doublon ignoré :') or 
                stripped_line.startswith('Nouvelles :') or 
                stripped_line.startswith('Déjà associés :')):
                # Utiliser des espaces non-sécables pour l'indentation
                processed_lines.append(f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line.strip()}')
            else:
                processed_lines.append(line)
        
        # Convertir les retours à la ligne en HTML
        return '<br>'.join(processed_lines)
    
    def _format_message_for_history(self, message: str, timestamp: str) -> str:
        """Formater les messages pour un affichage optimisé dans l'historique"""
        
        # Si c'est un message d'import PDF, appliquer le formatage spécialisé
        if "📊 Import" in message:
            lines = message.strip().split('\n')
            formatted_lines = []
            
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                
                # En-tête d'import : garder tel quel mais sans timestamp redondant
                if line.startswith("📊 Import"):
                    formatted_lines.append(line)
                    continue
                
                # Messages PDF : enlever les préfixes de fichier et nettoyer
                if "📄 Fichier PDF" in line and "lignes extraites" in line:
                    # Format: "📄 Fichier PDF filename.pdf: N lignes extraites"
                    # On veut garder juste cette information
                    formatted_lines.append(line)
                    continue
                
                # Lignes traitées : ajouter le préfixe ==>
                if line.startswith("Lignes traitées"):
                    formatted_lines.append(f"==> {line}")
                    continue
                
                # Titres de sections : ajouter interligne seulement avant "Appareils :"
                if line.endswith("Appareils :"):
                    formatted_lines.append("")  # Interligne avant première section
                    formatted_lines.append(line)
                    continue
                elif line.endswith("Associations de pièce :"):
                    formatted_lines.append(line)  # Pas d'interligne supplémentaire
                    continue
                
                # Éléments de synthèse : garder tels quels (l'indentation sera gérée par CSS)
                if line.strip().startswith("==> ") or line.strip().startswith("Créés :") or line.strip().startswith("Complétion automatique :"):
                    formatted_lines.append(line.strip())
                    continue
                
                # Autres lignes : garder telles quelles
                formatted_lines.append(line)
            
            # Reconstruire le message avec le formatage appliqué
            formatted_content = '\n'.join(formatted_lines)
            return f"[{timestamp}] {formatted_content}"
        
        # Pour les autres messages, format standard
        return f"[{timestamp}] {message}"


    def _handle_history_link(self, url):
        """Gérer les clics sur les liens dans l'historique"""
        from PyQt5.QtCore import QUrl
        
        url_str = url.toString() if isinstance(url, QUrl) else str(url)
        
        try:
            self._show_error(f"Lien non reconnu: {url_str}")
        except Exception as e:
            self._show_error(f"Erreur lors du traitement du lien: {e}")

    
    def _update_pieces_count_for_rows(self, rows: set):
        """Mettre à jour la colonne Nb Pièces pour les lignes spécifiées"""
        for row in rows:
            try:
                db_id = self._get_db_id_from_row(row)
                pieces_count = self.db_manager.get_pieces_count_for_appareil(db_id)
                
                # Plus de mise à jour de la colonne Nb Pièces (supprimée)
                
            except Exception as e:
                print(f"Erreur mise à jour Nb Pièces ligne {row}: {e}")

    def _add_piece(self):
        """Ajouter une pièce"""
        # Récupérer la référence et le libellé
        ref_piece = self.piece_input.text().strip()
        libelle_piece = self.piece_libelle_input.text().strip()
        
        # Récupérer toutes les lignes sélectionnées
        selected_rows = set()
        selected_ranges = self.table.selectedRanges()
        
        if selected_ranges:
            # Utiliser les plages sélectionnées
            for range_sel in selected_ranges:
                for row in range(range_sel.topRow(), range_sel.bottomRow() + 1):
                    selected_rows.add(row)
        else:
            # Fallback sur la ligne courante si aucune sélection
            current_row = self.table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)
        
        if not selected_rows:
            self._show_info(Config.get_message('no_selection'))
            return
        
        if not ref_piece:
            self._show_info(Config.get_message('no_piece_ref'))
            return
        
        # Validation
        validation_result = self.validator.validate_piece_reference(ref_piece)
        if not validation_result.is_valid:
            QMessageBox.warning(self, "Validation", validation_result.error_message)
            return
        
        try:
            # Ajouter la pièce à tous les appareils sélectionnés (sans description)
            added_count = 0
            error_count = 0
            
            for row in selected_rows:
                try:
                    db_id = self._get_db_id_from_row(row)
                    
                    # Vérifier si la pièce n'est pas déjà associée
                    if not self._piece_already_associated(db_id, ref_piece):
                        # Ajouter la pièce avec libellé optionnel
                        _, _ = self.db_manager.add_or_update_piece_with_description(ref_piece, db_id, libelle_piece, self._confirm_piece_description_update)
                        added_count += 1
                    else:
                        # Pièce déjà associée, mais vérifier le libellé si fourni
                        if libelle_piece and libelle_piece.strip():
                            _, _ = self.db_manager.add_or_update_piece_with_description(ref_piece, db_id, libelle_piece, self._confirm_piece_description_update)
                            print(f"Libellé vérifié pour pièce {ref_piece} déjà associée ligne {row}")
                        error_count += 1
                        print(f"Pièce {ref_piece} déjà associée à l'appareil ligne {row}")
                    
                except (ValueError, DatabaseError) as e:
                    error_count += 1
                    print(f"Erreur lors de l'ajout de la pièce à la ligne {row}: {e}")
                    continue
            
            # Nettoyer et mettre à jour
            self.piece_input.clear()
            self._update_pieces_panel()
            
            # Mettre à jour la colonne Nb Pièces pour les lignes concernées
            self._update_pieces_count_for_rows(selected_rows)
            
            # Forcer le rafraîchissement pour corriger les couleurs
            # Plus besoin de rafraîchir la colonne Nb Pièces (supprimée)
            
            # Ajouter à l'historique
            if added_count > 0:
                from src.core.config import pluralize
                history_message = f"Pièce '{ref_piece}' ajoutée à {pluralize(added_count, 'appareil')}"
                if error_count > 0:
                    history_message += f" ({error_count} erreur(s))"
                self._add_to_history(history_message)
                
                self.statusbar.showMessage(history_message, Config.STATUS_MESSAGE_TIMEOUT)
                
                # Vider les champs après ajout réussi
                self.piece_input.clear()
                self.piece_libelle_input.clear()
            else:
                self._add_to_history(f"Erreur: Aucune pièce n'a pu être ajoutée pour '{ref_piece}'")
            
        except Exception as e:
            error_msg = f"Erreur lors de l'ajout de la pièce: {e}"
            self._add_to_history(error_msg)
            self._show_error(error_msg)

    def _edit_piece(self, item: QListWidgetItem):
        """Éditer une pièce"""
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        
        # Obtenir l'ID de l'appareil actuel
        current_row = self.table.currentRow()
        if current_row < 0:
            self._show_error("Aucun appareil sélectionné")
            return
        
        try:
            # Récupérer l'ID de l'appareil
            appareil_id = self._get_db_id_from_row(current_row)
            
            # Récupérer les informations actuelles de la pièce
            piece_info = self.db_manager.get_piece_info(ref_piece, appareil_id)
            if not piece_info:
                self._show_error(f"Pièce '{ref_piece}' introuvable")
                return
                
            current_ref, current_desc = piece_info
            
            # Obtenir la référence de l'appareil pour l'historique
            appareil_ref = ""
            try:
                # Essayer d'obtenir la référence modèle (colonne 2)
                ref_modele_item = self.table.item(current_row, 2)
                if ref_modele_item and ref_modele_item.text().strip():
                    appareil_ref = ref_modele_item.text().strip()
                else:
                    # Sinon, utiliser la référence commerciale (colonne 3)
                    commercial_ref_item = self.table.item(current_row, 3)
                    if commercial_ref_item and commercial_ref_item.text().strip():
                        appareil_ref = commercial_ref_item.text().strip()
                    else:
                        # En dernier recours, utiliser l'ID
                        appareil_ref = f"ID:{appareil_id}"
            except Exception:
                appareil_ref = f"ID:{appareil_id}"
            
            # Demander la nouvelle description (pré-remplir avec la description actuelle)
            new_desc, ok = QInputDialog.getText(
                self, "Modifier la pièce", 
                f"Description pour '{ref_piece}':",
                text=current_desc or ""
            )
            
            if ok:
                new_desc_stripped = new_desc.strip() if new_desc else None
                
                # Vérifier si la description a réellement changé
                if new_desc_stripped != current_desc:
                    success = self.db_manager.update_piece(ref_piece, new_desc_stripped)
                    if success:
                        self._update_pieces_panel()
                        self.statusbar.showMessage(
                            Config.get_message('piece_updated') + f": {ref_piece}", 
                            Config.STATUS_MESSAGE_TIMEOUT
                        )
                        
                        # Ajouter à l'historique avec les détails de la modification
                        old_desc_display = f"'{current_desc}'" if current_desc else "vide"
                        new_desc_display = f"'{new_desc_stripped}'" if new_desc_stripped else "vide"
                        self._add_to_history(
                            f"Modification de pièce: {ref_piece} (appareil: {appareil_ref}) - "
                            f"Description: {old_desc_display} → {new_desc_display}"
                        )
                    else:
                        self._show_error("Erreur lors de la modification de la pièce")
                else:
                    # Aucune modification, pas besoin de mettre à jour
                    self.statusbar.showMessage(
                        f"Aucune modification pour la pièce: {ref_piece}", 
                        Config.STATUS_MESSAGE_TIMEOUT
                    )
                    
        except DatabaseError as e:
            self._show_error(f"Erreur lors de la modification: {e}")
        except Exception as e:
            self._show_error(f"Erreur inattendue: {e}")
    
    def _show_pieces_context_menu(self, position):
        """Afficher le menu contextuel pour les pièces"""
        item = self.pieces_list.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        # Action modifier
        edit_action = menu.addAction("✏️ Modifier")
        edit_action.triggered.connect(lambda: self._edit_piece(item))
        
        # Action copier
        copy_action = menu.addAction("📋 Copier")
        copy_action.triggered.connect(lambda: self._copy_piece(item))
        
        # Action supprimer
        delete_action = menu.addAction("🗑️ Supprimer")
        delete_action.triggered.connect(lambda: self._delete_piece(item))
        
        # Vérifier s'il y a plusieurs appareils sélectionnés
        selected_ranges = self.table.selectedRanges()
        multiple_selection = len(selected_ranges) > 0 and sum(
            range_sel.bottomRow() - range_sel.topRow() + 1 
            for range_sel in selected_ranges
        ) > 1
        
        if multiple_selection:
            menu.addSeparator()
            delete_from_all_action = menu.addAction("🗑️ Supprimer de tous les appareils sélectionnés")
            delete_from_all_action.triggered.connect(lambda: self._delete_piece_from_selected(item))
        
        # Afficher le menu
        menu.exec_(self.pieces_list.mapToGlobal(position))
    
    def _delete_piece(self, item: QListWidgetItem):
        """Supprimer une pièce avec confirmation"""
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        
        # Demander confirmation avec raccourcis clavier
        confirmed = self._show_confirmation(
            "Confirmer la suppression",
            f"Êtes-vous sûr de vouloir supprimer la pièce '{ref_piece}' ?",
            default_yes=False
        )
        
        if confirmed:
            try:
                # Obtenir l'ID de l'appareil sélectionné
                current_row = self.table.currentRow()
                if current_row < 0:
                    self._show_error("Aucun appareil sélectionné")
                    return
                
                # Obtenir l'ID de l'appareil à partir de la ligne courante
                appareil_id = self._get_db_id_from_row(current_row)
                
                # Obtenir la référence de l'appareil pour l'historique
                appareil_ref = ""
                try:
                    # Essayer d'obtenir la référence modèle (colonne 2)
                    ref_modele_item = self.table.item(current_row, 2)
                    if ref_modele_item and ref_modele_item.text().strip():
                        appareil_ref = ref_modele_item.text().strip()
                    else:
                        # Sinon, utiliser la référence commerciale (colonne 3)
                        commercial_ref_item = self.table.item(current_row, 3)
                        if commercial_ref_item and commercial_ref_item.text().strip():
                            appareil_ref = commercial_ref_item.text().strip()
                        else:
                            # En dernier recours, utiliser l'ID
                            appareil_ref = f"ID:{appareil_id}"
                except Exception:
                    appareil_ref = f"ID:{appareil_id}"
                
                # Supprimer la pièce
                success = self.db_manager.delete_piece(ref_piece, appareil_id)
                if success:
                    self._update_pieces_panel()
                    self.statusbar.showMessage(
                        f"Pièce supprimée: {ref_piece}", 
                        Config.STATUS_MESSAGE_TIMEOUT
                    )
                    
                    # Ajouter à l'historique avec la référence de l'appareil
                    self._add_to_history(f"Suppression de pièce: {ref_piece} (appareil: {appareil_ref})")
                else:
                    self._show_error("Erreur lors de la suppression de la pièce")
                    
            except DatabaseError as e:
                self._show_error(f"Erreur lors de la suppression: {e}")
            except Exception as e:
                app_logger.error(f"Erreur inattendue lors de la suppression de pièce: {e}")
                self._show_error(f"Erreur inattendue: {e}")
    
    def _copy_piece(self, item: QListWidgetItem):
        """Copier une pièce dans le presse-papiers"""
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        
        # Copier la référence de la pièce dans le presse-papiers
        clipboard = QApplication.clipboard()
        clipboard.setText(ref_piece)
        
        # Afficher un message de confirmation
        self.statusbar.showMessage(
            f"Pièce copiée: {ref_piece}", 
            Config.STATUS_MESSAGE_TIMEOUT
        )
    
    def _delete_piece_from_selected(self, item: QListWidgetItem):
        """Supprimer une pièce de tous les appareils sélectionnés"""
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        
        # Récupérer les appareils sélectionnés
        selected_rows = set()
        selected_ranges = self.table.selectedRanges()
        
        if selected_ranges:
            for range_sel in selected_ranges:
                for row in range(range_sel.topRow(), range_sel.bottomRow() + 1):
                    selected_rows.add(row)
        
        if len(selected_rows) <= 1:
            # Fallback vers la suppression normale si un seul appareil
            self._delete_piece(item)
            return
        
        # Demander confirmation
        confirmed = self._show_confirmation(
            "Confirmer la suppression multiple",
            f"Êtes-vous sûr de vouloir supprimer la pièce '{ref_piece}' de {len(selected_rows)} appareils ?",
            default_yes=False
        )
        
        if confirmed:
            try:
                # Récupérer les IDs des appareils sélectionnés
                appareil_ids = []
                for row in selected_rows:
                    try:
                        appareil_id = self._get_db_id_from_row(row)
                        appareil_ids.append(appareil_id)
                    except (ValueError, IndexError):
                        continue
                
                if not appareil_ids:
                    self._show_error("Aucun appareil valide sélectionné")
                    return
                
                # Supprimer la pièce de tous les appareils
                deleted_count = self.db_manager.delete_piece_from_multiple_appareils(ref_piece, appareil_ids)
                
                if deleted_count > 0:
                    # Mettre à jour l'interface
                    self._update_pieces_panel()
                    self.statusbar.showMessage(
                        f"Pièce '{ref_piece}' supprimée de {deleted_count} appareils", 
                        Config.STATUS_MESSAGE_TIMEOUT
                    )
                    
                    # Ajouter à l'historique
                    self.undo_manager.add_action({
                        'type': 'delete_piece_multiple',
                        'ref_piece': ref_piece,
                        'appareil_ids': appareil_ids,
                        'deleted_count': deleted_count,
                        'description': f"Suppression multiple de pièce: {ref_piece} ({deleted_count} appareils)"
                    })
                else:
                    self._show_error("Aucune pièce n'a été supprimée")
                    
            except DatabaseError as e:
                self._show_error(f"Erreur lors de la suppression multiple: {e}")
            except Exception as e:
                app_logger.error(f"Erreur inattendue lors de la suppression multiple: {e}")
                self._show_error(f"Erreur inattendue: {e}")

    def _undo(self):
        """Annuler la dernière action"""
        action = self.undo_manager.undo()
        if action:
            self._apply_undo_action(action)
            self._update_toolbar_states()

    def _redo(self):
        """Rétablir l'action annulée"""
        action = self.undo_manager.redo()
        if action:
            self._apply_redo_action(action)
            self._update_toolbar_states()

    def _apply_undo_action(self, action: Dict[str, Any]):
        """Appliquer une action d'annulation"""
        if action['type'] == 'cell_edit':
            row, col = action['row'], action['col']
            item = self.table.item(row, col)
            if item:
                # Bloquer les signaux pour éviter les boucles
                self.table.blockSignals(True)
                item.setText(action['old_value'])
                self.table.blockSignals(False)
                
                # Mettre à jour dans la base si on a l'ID
                if action.get('db_id'):
                    try:
                        field_name = self._get_db_field_name(col)
                        if field_name:
                            self.db_manager.update_cell(int(action['db_id']), field_name, action['old_value'])
                    except Exception as e:
                        print(f"Erreur undo: {e}")
                
                # Mettre à jour la valeur précédente
                key = (row, col)
                self.previous_values[key] = action['old_value']

    def _apply_redo_action(self, action: Dict[str, Any]):
        """Appliquer une action de rétablissement"""
        if action['type'] == 'cell_edit':
            row, col = action['row'], action['col']
            item = self.table.item(row, col)
            if item:
                # Bloquer les signaux pour éviter les boucles
                self.table.blockSignals(True)
                item.setText(action['new_value'])
                self.table.blockSignals(False)
                
                # Mettre à jour dans la base si on a l'ID
                if action.get('db_id'):
                    try:
                        field_name = self._get_db_field_name(col)
                        if field_name:
                            self.db_manager.update_cell(int(action['db_id']), field_name, action['new_value'])
                    except Exception as e:
                        print(f"Erreur redo: {e}")
                
                # Mettre à jour la valeur précédente
                key = (row, col)
                self.previous_values[key] = action['new_value']

    def _fill_empty_fields(self):
        """Compléter les champs vides"""
        try:
            # Compter les champs complétés
            completed_count = 0
            total_rows = self.table.rowCount()
            
            if total_rows == 0:
                self._show_info("Aucune donnée à compléter")
                return
            
            # Bloquer les signaux pendant la complétion
            self.table.blockSignals(True)
            
            # Parcourir toutes les lignes
            for row in range(total_rows):
                header_item = self.table.verticalHeaderItem(row)
                if not header_item:
                    continue
                
                try:
                    db_id = self._get_db_id_from_row(row)
                    
                    # Récupérer les données actuelles de la ligne avec mapping correct
                    appareil_data = {}
                    
                    # Parcourir toutes les colonnes UI et mapper vers DB
                    for ui_col_idx in range(self.table.columnCount()):
                        db_field = self._get_db_field_name(ui_col_idx)
                        if db_field:  # Ignorer pieces_count (index 5)
                            item = self.table.item(row, ui_col_idx)
                            cell_value = item.text() if item else ""
                            appareil_data[db_field] = cell_value
                            
                            # Debug pour la colonne D (maintenant index 3)
                            if db_field == 'commercial_ref':
                                app_logger.debug(f"ROW {row}, COL {ui_col_idx}: commercial_ref = '{cell_value}'")
                    
                    # Vérifier si Type ou Fabricant sont vides
                    type_empty = not appareil_data.get('type', '').strip()
                    manufacturer_empty = not appareil_data.get('manufacturer', '').strip()
                    
                    if type_empty or manufacturer_empty:
                        # Essayer de compléter automatiquement
                        original_data = appareil_data.copy()
                        
                        # Log de l'opération de complétion
                        app_logger.log_user_action("fill_empty_fields", {
                            "row": row,
                            "db_id": db_id,
                            "type_empty": type_empty,
                            "manufacturer_empty": manufacturer_empty,
                            "original_data": original_data
                        })
                        
                        self._try_auto_complete(appareil_data)
                        
                        # Récupérer les items du tableau pour mise à jour
                        type_item = self.table.item(row, 0)  # Colonne A (Type)
                        manufacturer_item = self.table.item(row, 1)  # Colonne B (Manufacturer)
                        
                        # Mettre à jour les cellules si des champs ont été complétés
                        if type_empty and appareil_data.get('type', '').strip():
                            # Vérifier si on va écraser des données existantes
                            current_type = type_item.text() if type_item else ""
                            if current_type.strip():
                                app_logger.warning(f"ATTENTION: Type existant détecté lors de la complétion! Ligne {row}, DB_ID {db_id}: '{current_type}' -> '{appareil_data['type']}'")
                            
                            # Mettre à jour Type dans la base et l'interface
                            self.db_manager.update_cell(db_id, 'type', appareil_data['type'])
                            
                            # Log de l'opération de mise à jour
                            app_logger.log_data_operation(
                                "UPDATE_TYPE_AUTOCOMPLETE",
                                {"field": "type", "old_value": current_type, "new_value": appareil_data['type']},
                                table_id=db_id,
                                success=True
                            )
                            
                            if type_item:
                                type_item.setText(appareil_data['type'])
                            completed_count += 1
                        
                        if manufacturer_empty and appareil_data.get('manufacturer', '').strip():
                            # Vérifier si on va écraser des données existantes
                            current_manufacturer = manufacturer_item.text() if manufacturer_item else ""
                            if current_manufacturer.strip():
                                app_logger.warning(f"ATTENTION: Fabricant existant détecté lors de la complétion! Ligne {row}, DB_ID {db_id}: '{current_manufacturer}' -> '{appareil_data['manufacturer']}'")
                            
                            # Mettre à jour Fabricant dans la base et l'interface
                            self.db_manager.update_cell(db_id, 'manufacturer', appareil_data['manufacturer'])
                            
                            # Log de l'opération de mise à jour
                            app_logger.log_data_operation(
                                "UPDATE_MANUFACTURER_AUTOCOMPLETE",
                                {"field": "manufacturer", "old_value": current_manufacturer, "new_value": appareil_data['manufacturer']},
                                table_id=db_id,
                                success=True
                            )
                            
                            if manufacturer_item:
                                manufacturer_item.setText(appareil_data['manufacturer'])
                            completed_count += 1
                
                except (ValueError, DatabaseError) as e:
                    print(f"Erreur lors de la complétion de la ligne {row}: {e}")
                    continue
            
            # Réactiver les signaux et forcer le rafraîchissement (retour première page)
            self.table.blockSignals(False)
            self._force_refresh_display(reset_page=True, clear_filters=True)
            
            # Afficher le résultat
            if completed_count > 0:
                message = f"Complétion automatique: {completed_count} champ(s) complété(s)"
                self._add_to_history(message)
                self.statusbar.showMessage(message, Config.LONG_STATUS_MESSAGE_TIMEOUT)
            else:
                message = "Complétion automatique: Aucun champ à compléter trouvé"
                self._add_to_history(message)
                
        except Exception as e:
            self.table.blockSignals(False)  # S'assurer que les signaux sont réactivés
            self._show_error(f"Erreur lors de la complétion: {e}")

    def _clean_data(self):
        """Nettoyer les données avec prévisualisation détaillée"""
        from .cleanup_preview import CleanupPreviewDialog
        
        # Ouvrir la fenêtre de prévisualisation
        preview_dialog = CleanupPreviewDialog(self)
        
        if preview_dialog.exec_() != QDialog.Accepted:
            return
        
        # Récupérer les options de nettoyage
        cleanup_options = preview_dialog.get_cleanup_options()
        
        # Si aucun doublon trouvé, ne rien faire
        if not cleanup_options['analysis_data'] or \
           (cleanup_options['analysis_data']['statistics']['total_devices_to_delete'] == 0 and \
            cleanup_options['analysis_data']['statistics']['total_duplicate_pieces'] == 0 and \
            cleanup_options['analysis_data']['statistics']['inconsistencies_count'] == 0):
            self._show_info("✅ Aucun doublon trouvé ! La base de données est déjà propre.")
            return
        
        # Confirmation finale
        stats = cleanup_options['analysis_data']['statistics']
        operations = []
        
        if cleanup_options['clean_devices'] and stats['total_devices_to_delete'] > 0:
            operations.append(f"• Supprimer {stats['total_devices_to_delete']} appareils en doublon")
            operations.append(f"• Transférer {stats['total_pieces_to_transfer']} pièces associées")
        
        if cleanup_options['clean_pieces'] and stats['total_duplicate_pieces'] > 0:
            operations.append(f"• Supprimer {stats['total_duplicate_pieces']} références de pièces dupliquées")
        
        if cleanup_options['clean_inconsistencies'] and stats['inconsistencies_count'] > 0:
            inconsistencies_to_merge = 0
            for group_data in cleanup_options.get('inconsistencies_fusion_data', []):
                if group_data.get('master_device'):
                    # Compter les appareils qui seront fusionnés (tous sauf le maître)
                    inconsistencies_to_merge += len(group_data['devices']) - 1
            if inconsistencies_to_merge > 0:
                operations.append(f"• Fusionner {inconsistencies_to_merge} appareils avec doublons de références")
        
        if not operations:
            # Message plus informatif selon le contexte
            debug_info = []
            if stats['total_devices_to_delete'] > 0:
                debug_info.append(f"Appareils en doublon: {stats['total_devices_to_delete']} (option cochée: {cleanup_options['clean_devices']})")
            if stats['total_duplicate_pieces'] > 0:
                debug_info.append(f"Pièces dupliquées: {stats['total_duplicate_pieces']} (option cochée: {cleanup_options['clean_pieces']})")
            if stats['inconsistencies_count'] > 0:
                fusion_count = len(cleanup_options.get('inconsistencies_fusion_data', []))
                debug_info.append(f"Doublons de références: {stats['inconsistencies_count']} détectés, {fusion_count} avec sélection (option cochée: {cleanup_options['clean_inconsistencies']})")
            
            message = "Aucune opération sélectionnée.\n\n"
            if debug_info:
                message += "État actuel:\n" + "\n".join(f"• {info}" for info in debug_info)
                message += "\n\nVeuillez cocher les options de nettoyage souhaitées et/ou sélectionner des appareils à fusionner."
            else:
                message += "Veuillez cocher au moins une option de nettoyage."
            
            self._show_info(message)
            return
        
        final_confirmation = QMessageBox.question(
            self,
            "Confirmation finale",
            "Opérations à effectuer :\n\n" + "\n".join(operations) + 
            "\n\n⚠️ Cette action est IRRÉVERSIBLE !\n\nÊtes-vous absolument certain ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if final_confirmation != QMessageBox.Yes:
            return
        
        try:
            devices_deleted = 0
            pieces_deleted = 0
            
            # Nettoyer selon les options choisies
            if cleanup_options['clean_devices'] and stats['total_devices_to_delete'] > 0:
                devices_deleted = self.db_manager.remove_duplicate_devices()
            
            if cleanup_options['clean_pieces'] and stats['total_duplicate_pieces'] > 0:
                pieces_deleted = self.db_manager.remove_duplicate_pieces()
            
            # Fusionner les doublons de références selon les choix utilisateur
            inconsistencies_merged = 0
            if cleanup_options['clean_inconsistencies'] and stats['inconsistencies_count'] > 0:
                for group_data in cleanup_options.get('inconsistencies_fusion_data', []):
                    master_device = group_data.get('master_device')
                    if not master_device:
                        continue
                        
                    master_id = master_device['id']
                    
                    # Appliquer les modifications du maître s'il y en a
                    if master_device.get('modified', False):
                        current_data = master_device['current_data']
                        for field, value in current_data.items():
                            if field in ['type', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref', 'category', 'notes']:
                                self.db_manager.update_cell(master_id, field, value)
                    
                    # Fusionner tous les autres appareils vers le maître
                    for device in group_data['devices']:
                        if device['id'] != master_id and not device.get('is_master', False):
                            # Transférer les pièces vers l'appareil maître
                            self.db_manager.transfer_pieces(device['id'], master_id)
                            # Supprimer l'appareil
                            self.db_manager.delete_appareils([device['id']])
                            inconsistencies_merged += 1
            
            # Nettoyer les données (fonction originale)
            result = self.db_manager.clean_data()
            
            # Message de résultat
            message_parts = []
            if devices_deleted > 0:
                message_parts.append(f"{devices_deleted} appareils dupliqués cumulés")
            if pieces_deleted > 0:
                message_parts.append(f"{pieces_deleted} références de pièces dupliquées cumulées")
            if inconsistencies_merged > 0:
                message_parts.append(f"{inconsistencies_merged} appareils avec incohérences fusionnés")
            if result.get('deleted_empty', 0) > 0:
                message_parts.append(f"{result['deleted_empty']} lignes vides supprimées")
            if result.get('deleted_duplicates', 0) > 0:
                message_parts.append(f"{result['deleted_duplicates']} doublons supprimés")
            if result.get('merged_notes', 0) > 0:
                message_parts.append(f"{result['merged_notes']} notes fusionnées")
            
            if message_parts:
                message = f"Nettoyage terminé: {', '.join(message_parts)}"
            else:
                message = "Nettoyage terminé: Aucun problème détecté"
            
            self._add_to_history(message)
            self.statusbar.showMessage(message, Config.LONG_STATUS_MESSAGE_TIMEOUT)
            self._force_refresh_display(reset_page=True, clear_filters=True)
            
            # Actualiser la fenêtre de validation si elle est ouverte
            if hasattr(self, 'validation_window') and self.validation_window:
                self.validation_window._load_data()
                
        except DatabaseError as e:
            self._show_error(f"Erreur lors du nettoyage: {e}")
    
    def _clean_duplicate_devices(self):
        """Supprimer seulement les doublons d'appareils"""
        reply = QMessageBox.question(
            self, 
            "Supprimer doublons d'appareils",
            "Cette opération va supprimer les appareils en doublon en gardant le plus ancien.\n"
            "Les pièces seront transférées vers l'appareil conservé.\n\n"
            "Cette action est irréversible. Continuer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            deleted_count = self.db_manager.remove_duplicate_devices()
            
            if deleted_count > 0:
                message = f"Nettoyage terminé: {deleted_count} appareils en doublon supprimés"
            else:
                message = "Nettoyage terminé: Aucun doublon d'appareil détecté"
            
            self._add_to_history(message)
            self.statusbar.showMessage(message, Config.LONG_STATUS_MESSAGE_TIMEOUT)
            self._force_refresh_display(reset_page=True, clear_filters=True)
            
        except DatabaseError as e:
            self._show_error(f"Erreur lors de la suppression des doublons d'appareils: {e}")
    
    def _clean_duplicate_pieces(self):
        """Supprimer seulement les doublons de pièces"""
        reply = QMessageBox.question(
            self, 
            "Supprimer doublons de pièces",
            "Cette opération va supprimer les références de pièces dupliquées.\n"
            "Seule la première occurrence de chaque référence sera conservée.\n\n"
            "Cette action est irréversible. Continuer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            deleted_count = self.db_manager.remove_duplicate_pieces()
            
            if deleted_count > 0:
                message = f"Nettoyage terminé: {deleted_count} références de pièces dupliquées supprimées"
            else:
                message = "Nettoyage terminé: Aucun doublon de pièce détecté"
            
            self._add_to_history(message)
            self.statusbar.showMessage(message, Config.LONG_STATUS_MESSAGE_TIMEOUT)
            self._update_pieces_panel()  # Actualiser le panneau des pièces
            
        except DatabaseError as e:
            self._show_error(f"Erreur lors de la suppression des doublons de pièces: {e}")

    def _manage_categories(self):
        """Gérer les catégories"""
        try:
            current_categories = self.db_manager.get_categories()
            new_categories = CategoryDialog.get_categories(self, current_categories)
            
            if new_categories is not None:
                self.db_manager.update_categories(new_categories)
                self.statusbar.showMessage(
                    Config.get_message('categories_updated'), 
                    Config.STATUS_MESSAGE_TIMEOUT
                )
        except DatabaseError as e:
            self._show_error(f"Erreur lors de la gestion des catégories: {e}")

    def _edit_notes(self):
        """Éditer les notes"""
        current_row = self.table.currentRow()
        if current_row < 0:
            self._show_info(Config.get_message('no_selection'))
            return
        
        try:
            db_id = self._get_db_id_from_row(current_row)
            
            # Récupérer les notes actuelles (simplification)
            current_notes = ""
            notes_item = self.table.item(current_row, 6)  # Colonne notes (maintenant à l'index 6)
            if notes_item:
                current_notes = notes_item.text()
            
            new_notes = NotesDialog.get_notes(self, current_notes)
            
            if new_notes is not None:
                success = self.db_manager.update_cell(db_id, 'notes', new_notes)
                if success:
                    if notes_item:
                        preview = new_notes[:Config.NOTES_PREVIEW_LENGTH]
                        if len(new_notes) > Config.NOTES_PREVIEW_LENGTH:
                            preview += "..."
                        notes_item.setText(preview)
                    
                    self.statusbar.showMessage(
                        Config.get_message('notes_updated'), 
                        Config.STATUS_MESSAGE_TIMEOUT
                    )
                    
        except DatabaseError as e:
            self._show_error(f"Erreur lors de l'édition des notes: {e}")

    def _import_file(self):
        """Importer un fichier CSV ou PDF - Nouvelle version avec ImportManager"""
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Importer fichier(s)", "", 
            "Fichiers supportés (*.csv *.pdf);;Fichiers CSV (*.csv);;Fichiers PDF (*.pdf)"
        )
        
        if filenames:
            # Utiliser le nouveau gestionnaire unifié
            results = self.import_manager.import_files(filenames, show_dialog=True)
            
            if results:
                self._show_import_results_new(results)
                self.load_data()  # Rafraîchir l'affichage
        
    
    def _detect_csv_columns(self, filename):
        """Détecter automatiquement le nombre de colonnes du fichier CSV (fallback legacy)"""
        try:
            import csv
            
            # Détecter l'encodage automatiquement
            encoding = self._detect_file_encoding(filename)
            
            with open(filename, 'r', encoding=encoding, errors='replace') as file:
                # Lire un échantillon pour détecter le séparateur
                sample = file.read(1024)
                file.seek(0)
                
                # Détecter le séparateur
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample, delimiters=',;\t')
                    reader = csv.reader(file, dialect)
                except csv.Error:
                    if sample.count(';') > sample.count(',') and sample.count(';') > sample.count('\t'):
                        reader = csv.reader(file, delimiter=';')
                    elif sample.count('\t') > sample.count(','):
                        reader = csv.reader(file, delimiter='\t')
                    else:
                        reader = csv.reader(file, delimiter=',')
                
                # Analyser les premières lignes pour déterminer le nombre de colonnes
                column_counts = []
                for i, row in enumerate(reader):
                    if i >= 5:  # Analyser les 5 premières lignes
                        break
                    if row:  # Ignorer les lignes vides
                        column_counts.append(len(row))
                
                if not column_counts:
                    QMessageBox.warning(self, "Fichier vide", "Le fichier CSV semble être vide.")
                    return None
                
                # Prendre le nombre de colonnes le plus fréquent
                most_common_columns = max(set(column_counts), key=column_counts.count)
                
                return most_common_columns
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'analyse", f"Erreur lors de l'analyse du fichier: {e}")
            return None
    
    def _detect_file_encoding(self, filename):
        """Détecter automatiquement l'encodage d'un fichier"""
        # Encodages courants à tester dans l'ordre de priorité
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1252', 'latin-1', 'iso-8859-1', 'iso-8859-15', 'windows-1252', 'utf-16']
        
        # D'abord essayer avec chardet si disponible
        try:
            import chardet
            with open(filename, 'rb') as file:
                raw_data = file.read(50000)  # Lire plus de données pour une meilleure détection
                detected = chardet.detect(raw_data)
                if detected and detected['encoding'] and detected['confidence'] > 0.5:  # Seuil réduit
                    encoding = detected['encoding'].lower()
                    # Mapper certains encodages vers des versions plus compatibles
                    if encoding in ['windows-1252', 'cp1252']:
                        return 'cp1252'
                    elif encoding in ['iso-8859-1', 'latin-1']:
                        return 'latin-1' 
                    elif encoding.startswith('utf-8'):
                        return 'utf-8'
                    elif encoding.startswith('utf-16'):
                        return 'utf-16'
                    else:
                        return detected['encoding']
        except (ImportError, Exception) as e:
            app_logger.debug(f"Chardet non disponible ou erreur: {e}")
        
        # Sinon, tester manuellement les encodages courants en lisant tout le fichier
        for encoding in encodings_to_try:
            try:
                with open(filename, 'r', encoding=encoding, errors='replace') as file:
                    file.read()  # Lire tout le fichier pour s'assurer que l'encodage fonctionne
                    app_logger.debug(f"Encodage détecté avec succès: {encoding}")
                    return encoding
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        
        # Par défaut, retourner latin-1 qui peut lire tous les bytes
        app_logger.warning(f"Aucun encodage détecté pour {filename}, utilisation de latin-1")
        return 'latin-1'
    
    def _detect_separator(self, filename):
        """Détecter automatiquement le séparateur CSV"""
        try:
            import csv
            
            # Détecter l'encodage d'abord
            encoding = self._detect_file_encoding(filename)
            
            with open(filename, 'r', encoding=encoding, errors='replace') as file:
                sample = file.read(1024)
                
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample, delimiters=',;\t')
                    return dialect.delimiter
                except csv.Error:
                    if sample.count(';') > sample.count(',') and sample.count(';') > sample.count('\t'):
                        return ';'
                    elif sample.count('\t') > sample.count(','):
                        return '\t'
                    else:
                        return ','
                        
        except Exception as e:
            return ','  # Default fallback
    
    def _create_progress_dialog(self, title, total_items, label_template="Traitement... {} / {} éléments"):
        """Factory method pour créer des dialogues de progression cohérents"""
        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        
        progress_dialog = QProgressDialog(
            label_template.format(0, total_items),
            "Annuler", 0, total_items, self
        )
        progress_dialog.setWindowTitle(title)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.show()
        QApplication.processEvents()
        return progress_dialog
    
    def _prepare_csv_sample_data(self, file_path, max_lines=3):
        """Préparer les données d'exemple pour l'aperçu CSV (fallback legacy)"""
        sample_data = []
        try:
            import csv
            encoding = self._detect_file_encoding(file_path)
            separator = self._detect_separator(file_path)
            
            with open(file_path, 'r', encoding=encoding, errors='replace') as file:
                reader = csv.reader(file, delimiter=separator)
                for i, row in enumerate(reader):
                    if i < max_lines and row:
                        sample_data.append(row)
                    elif i >= max_lines:
                        break
        except Exception as e:
            print(f"Erreur lecture aperçu CSV: {e}")
        return sample_data
    
    def _detect_column_mapping(self, sample_data):
        """Détecter automatiquement l'ordre des colonnes en analysant le contenu"""
        if not sample_data or len(sample_data) == 0:
            return None
            
        mapping = {}
        
        # Analyser chaque colonne pour détecter son type
        num_cols = max(len(row) for row in sample_data if row)
        
        for col_idx in range(num_cols):
            # Extraire les valeurs de cette colonne (non vides)
            col_values = []
            for row in sample_data:
                if len(row) > col_idx and row[col_idx] is not None:
                    val = str(row[col_idx]).strip()
                    if val:
                        col_values.append(val)
            
            if not col_values:
                continue
                
            # Analyser les patterns de cette colonne
            col_type = self._analyze_column_content(col_values)
            
            # Assigner le type détecté à cette colonne
            if col_type == 'ref_modele' and 'ref_modele' not in mapping:
                mapping['ref_modele'] = col_idx
            elif col_type == 'commercial_ref' and 'commercial_ref' not in mapping:
                mapping['commercial_ref'] = col_idx  
            elif col_type == 'type' and 'type' not in mapping:
                mapping['type'] = col_idx
            elif col_type == 'manufacturer' and 'manufacturer' not in mapping:
                mapping['manufacturer'] = col_idx
            else:
                # Colonne non identifiée
                if 'other' not in mapping:
                    mapping['other'] = col_idx
        
        return mapping if mapping else None
    
    def _analyze_column_content(self, values):
        """Analyser le contenu d'une colonne pour déterminer son type"""
        if not values:
            return 'unknown'
            
        # Compter les patterns
        patterns = {
            'ref_modele': 0,      # GK 200, GK 215, etc.
            'commercial_ref': 0,  # 090990201, 090267006, etc. (chiffres)
            'type': 0,           # RÉFRIGÉRATEUR, MODÈLE, TABLE-TOP, etc. (mots longs)
            'manufacturer': 0     # Noms de marque
        }
        
        for value in values[:5]:  # Analyser seulement les 5 premiers
            value = value.upper().strip()
            
            # Pattern ref_modele: lettres + chiffres, court (ex: GK 200, GK215)
            if len(value) <= 10 and any(c.isalpha() for c in value) and any(c.isdigit() for c in value):
                patterns['ref_modele'] += 2
                
            # Pattern commercial_ref: principalement chiffres, long (ex: 090990201)
            elif len(value) >= 6 and value.replace(' ', '').isdigit():
                patterns['commercial_ref'] += 2
                
            # Pattern type: mots longs avec tirets/espaces (ex: RÉFRIGÉRATEUR-MODÈLE TABLE-TOP)
            elif len(value) > 15 and ('-' in value or len(value.split()) > 2):
                patterns['type'] += 2
                
            # Pattern manufacturer: mots courts, noms propres
            elif len(value) <= 15 and value.isalpha():
                patterns['manufacturer'] += 1
                
            # Fallback: longueur comme indicateur
            if len(value) <= 8:
                patterns['ref_modele'] += 0.5
            elif 8 < len(value) <= 15:
                patterns['commercial_ref'] += 0.5
            else:
                patterns['type'] += 0.5
        
        # Retourner le type avec le score le plus élevé
        best_type = max(patterns, key=patterns.get)
        return best_type if patterns[best_type] > 0 else 'other'
    
    def _process_import(self, imported_data, import_type, ref_piece, third_column_choice="ignore", progress_dialog=None, libelle_piece=None):
        """Traiter les données d'import avec détection intelligente des colonnes"""
        # Stocker la référence de pièce pour vérification post-import
        self.last_imported_piece_ref = ref_piece
        
        # Vider le cache des décisions de description au début de chaque import
        self._piece_description_decisions.clear()
        
        results = {
            'total_imported': 0,
            'matches_found': 0,
            'manual_completion': 0,
            'duplicates_skipped': 0,
            'new_entries': 0,
            'associations_created': 0,
            'descriptions_updated': 0,
            'duplicates_in_file': 0,
            'auto_completed': 0,
            'original_line_count': len(imported_data)  # Nombre réel de lignes dans le fichier
        }
        
        # Set pour tracker les doublons dans le fichier
        seen_device_refs = set()
        
        # Note: La détection automatique des colonnes est désactivée pour les PDF
        # Les PDF suivent toujours la logique fixe: col0->ref_modele, col1->commercial_ref, col2->choix utilisateur
        column_mapping = None
        
        # Log de démarrage avec format unifié
        print(f"\n🔍 Début du traitement de {len(imported_data)} lignes d'import")
        
        for row_idx, row in enumerate(imported_data):
            # Compter TOUTES les lignes traitées (même en cas d'erreur)
            results['total_imported'] += 1
            
            # Mettre à jour la barre de progression
            if progress_dialog:
                if progress_dialog.wasCanceled():
                    break
                progress_dialog.setValue(row_idx)
                progress_dialog.setLabelText(f"Traitement des lignes... {row_idx + 1} / {len(imported_data)}")
                if row_idx % 100 == 0:  # Traiter les événements toutes les 100 lignes
                    QApplication.processEvents()
            
            try:
                # Initialiser les variables par défaut
                type_val = ""
                manufacturer = ""
                ref_modele = ""
                commercial_ref = ""
                other_ref = ""
                notes = ""
                
                if import_type == 1:
                    # 1 colonne: importer dans ref_modele uniquement
                    ref_modele = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
                    commercial_ref = ""
                elif import_type == 2:
                    # 2 colonnes: ref_modele, commercial_ref (colonnes C et D)
                    ref_modele = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
                    commercial_ref = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
                elif import_type == 3:
                    # 3 colonnes PDF: logique fixe
                    # col0 → ref_modele (colonne C), col1 → commercial_ref (colonne D), col2 → selon choix
                    ref_modele = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
                    commercial_ref = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
                    third_value = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
                    
                    # Les colonnes A (type) et B (manufacturer) restent vides pour les PDF
                    # sauf si la 3ème colonne contient des informations pertinentes
                    type_val = ""
                    manufacturer = ""
                    
                    # Gérer la 3ème colonne selon le choix utilisateur
                    if third_column_choice == "other_ref":
                        other_ref = third_value
                        notes = ""
                    elif third_column_choice == "notes":
                        other_ref = ""
                        notes = third_value
                    else:
                        # Si "ignore", les deux restent vides
                        other_ref = ""
                        notes = ""
                elif import_type >= 4:
                    # 4+ colonnes: type, manufacturer, ref_modele, commercial_ref, other_ref, ...
                    type_val = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
                    manufacturer = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
                    ref_modele = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
                    commercial_ref = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
                    other_ref = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""
                    # notes peuvent être en colonne 5 si présentes
                
                # Log de la ligne en cours
                print(f"\n🔵 Ligne {row_idx + 1}: {len(row)} colonnes - {row[:4]}{'...' if len(row) > 4 else ''}")
                
                # Vérifier si c'est un doublon dans le fichier
                # Créer une clé unique basée sur les références principales
                device_key = f"{ref_modele.strip().lower()}|{commercial_ref.strip().lower()}"
                if device_key in seen_device_refs and (ref_modele.strip() or commercial_ref.strip()):
                    results['duplicates_in_file'] += 1
                    print(f"  🔄 Doublon dans le fichier ignoré - Ligne {row_idx + 1}: {ref_modele} | {commercial_ref}")
                    continue
                elif ref_modele.strip() or commercial_ref.strip():
                    seen_device_refs.add(device_key)
                
                # Chercher l'appareil existant par ses références avec logique intelligente
                existing_device = self._find_existing_device_by_refs(ref_modele, commercial_ref, type_val, manufacturer)
                
                if existing_device:
                    # Appareil existant trouvé - compléter avec les infos importées
                    device_id = existing_device['id']
                    print(f"  ✅ Appareil existant trouvé par combinaison exacte: {ref_modele} + {commercial_ref}")
                    print(f"🔄 Ligne {row_idx + 1}: Appareil existant trouvé (ID: {device_id})")
                    
                    # Mettre à jour les champs avec les nouvelles valeurs (logique import)
                    updates = {}
                    # Pour les imports, on met à jour si une nouvelle valeur est fournie
                    if type_val:
                        updates['type'] = type_val
                    if manufacturer:
                        updates['manufacturer'] = manufacturer
                    if ref_modele:
                        updates['ref_modele'] = ref_modele
                    if commercial_ref:
                        updates['commercial_ref'] = commercial_ref
                    if other_ref:
                        updates['other_ref'] = other_ref
                    if notes:
                        updates['notes'] = notes
                    
                    # Appliquer les mises à jour
                    if updates:
                        self._update_device_info(device_id, updates)
                        print(f"  ⚙️ Mis à jour: {list(updates.keys())}")
                    
                    # Créer association si référence de pièce fournie
                    if ref_piece and str(ref_piece).strip():
                        try:
                            ref_piece_safe = str(ref_piece).strip() if ref_piece else ''
                            already_associated = self._piece_already_associated(device_id, ref_piece_safe)
                            if ref_piece_safe and not already_associated:
                                _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece_safe, device_id, libelle_piece, self._confirm_piece_description_update)
                                results['associations_created'] += 1
                                if desc_updated:
                                    results['descriptions_updated'] += 1
                                print(f"  🔗 Pièce {ref_piece_safe} associée")
                                
                                # Vérifier immédiatement après création que l'association existe
                                if not self._piece_already_associated(device_id, ref_piece_safe):
                                    print(f"  ❌ ERREUR: Association {ref_piece_safe} -> {device_id} créée mais non trouvée!")
                                    
                            else:
                                # Pièce déjà associée, mais vérifier le libellé si fourni
                                if libelle_piece and str(libelle_piece).strip():
                                    _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece_safe, device_id, libelle_piece, self._confirm_piece_description_update)
                                    if desc_updated:
                                        results['descriptions_updated'] += 1
                                    print(f"  📝 Libellé vérifié pour pièce {ref_piece_safe} déjà associée")
                                results['duplicates_skipped'] += 1
                                print(f"  ⚠️ Pièce {ref_piece_safe} déjà associée (appareil {device_id})")
                                
                                # Collecter les détails du doublon pour CSV/PDF
                                if not hasattr(self, '_current_import_duplicates'):
                                    self._current_import_duplicates = []
                                self._current_import_duplicates.append({
                                    'ligne': row_idx + 1,
                                    'appareil_id': device_id,
                                    'ref_piece': str(ref_piece).strip() if ref_piece else '',
                                    'appareil_data': {
                                        'ref_modele': existing_device.get('ref_modele', '') or '',
                                        'commercial_ref': existing_device.get('commercial_ref', '') or '',
                                        'type': existing_device.get('type', '') or '',
                                        'manufacturer': existing_device.get('manufacturer', '') or ''
                                    }
                                })
                        except Exception as piece_error:
                            ref_piece_safe = str(ref_piece).strip() if ref_piece else 'N/A'
                            print(f"❌ Échec association pièce {ref_piece_safe} avec appareil {device_id}: {piece_error}")
                            app_logger.error(f"Échec association pièce {ref_piece_safe} avec appareil {device_id}: {piece_error}")
                    else:
                        # Ligne sans référence de pièce - compter dans les associations manquantes
                        results['no_piece_ref'] = results.get('no_piece_ref', 0) + 1
                        print(f"  ⚠️ Ligne {row_idx + 1}: Appareil traité mais pas de référence de pièce")
                    
                    # Vérifier si l'appareil nécessite encore une complétion manuelle
                    # après mise à jour (seuls ceux sans type ET fabricant)
                    final_device_data = dict(existing_device)
                    final_device_data.update(updates)
                    if self._needs_manual_completion(final_device_data):
                        results['manual_completion'] += 1
                    
                    # Compter comme "mis à jour" seulement si les colonnes importantes (A et B) ont été modifiées
                    important_updates = [k for k in updates.keys() if k in ['type', 'manufacturer']]
                    if important_updates:
                        results['matches_found'] += 1
                    # NE PAS créer de nouvelle ligne dans le tableau
                else:
                    # Nouvel appareil - utiliser la même logique harmonisée que le collage
                    if (ref_modele and str(ref_modele).strip()) or (commercial_ref and str(commercial_ref).strip()):
                        print(f"✨ Ligne {row_idx + 1}: Création d'un nouvel appareil")
                        # Préparer les données d'appareil comme dans _handle_paste
                        appareil_data = {
                            'type': str(type_val).strip() if type_val else '',
                            'manufacturer': str(manufacturer).strip() if manufacturer else '',
                            'ref_modele': str(ref_modele).strip() if ref_modele else '',
                            'commercial_ref': str(commercial_ref).strip() if commercial_ref else '',
                            'other_ref': str(other_ref).strip() if other_ref else '',
                            'category': '',
                            'notes': str(notes).strip() if notes else ''
                        }
                        
                        # Essayer l'auto-complétion AVANT de vérifier si complétion manuelle nécessaire
                        auto_completion_success = False
                        if not appareil_data.get('type') or not appareil_data.get('manufacturer'):
                            auto_completion_success = self._try_auto_complete(appareil_data)
                        
                        # Filtrer les données vides comme dans _handle_paste
                        filtered_data = {}
                        for field, value in appareil_data.items():
                            if value and str(value).strip():
                                filtered_data[field] = value
                        
                        # S'assurer qu'on a les références essentielles
                        if 'ref_modele' not in filtered_data and ref_modele.strip():
                            filtered_data['ref_modele'] = ref_modele.strip()
                        if 'commercial_ref' not in filtered_data and commercial_ref.strip():
                            filtered_data['commercial_ref'] = commercial_ref.strip()
                        
                        if filtered_data:
                            device_id = self.db_manager.insert_appareil(filtered_data)
                            if device_id:
                                results['new_entries'] += 1
                                print(f"  ✅ Nouvel appareil créé (ID: {device_id})")
                                
                                # Incrémenter auto_completed si l'auto-complétion a réussi
                                if auto_completion_success:
                                    results['auto_completed'] += 1
                                
                                # Vérifier si l'appareil nécessite une complétion manuelle APRÈS création
                                # (utiliser les données filtrées qui incluent l'auto-complétion)
                                if self._needs_manual_completion(filtered_data):
                                    results['manual_completion'] += 1
                                if ref_piece and str(ref_piece).strip():
                                    try:
                                        ref_piece_safe = str(ref_piece).strip() if ref_piece else ''
                                        already_associated = self._piece_already_associated(device_id, ref_piece_safe)
                                        if ref_piece_safe and not already_associated:
                                            _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece_safe, device_id, libelle_piece, self._confirm_piece_description_update)
                                            results['associations_created'] += 1
                                            if desc_updated:
                                                results['descriptions_updated'] += 1
                                            print(f"  🔗 Pièce {ref_piece_safe} associée")
                                            
                                            # Vérifier immédiatement après création que l'association existe
                                            if not self._piece_already_associated(device_id, ref_piece_safe):
                                                print(f"  ❌ ERREUR: Association {ref_piece_safe} -> {device_id} créée mais non trouvée!")
                                                
                                        else:
                                            # Pièce déjà associée, mais vérifier le libellé si fourni
                                            if libelle_piece and libelle_piece.strip():
                                                _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece_safe, device_id, libelle_piece, self._confirm_piece_description_update)
                                                if desc_updated:
                                                    results['descriptions_updated'] += 1
                                                print(f"  📝 Libellé vérifié pour pièce {ref_piece_safe} déjà associée")
                                            results['duplicates_skipped'] += 1
                                            print(f"  ⚠️ Pièce {ref_piece_safe} déjà associée (appareil {device_id})")
                                            
                                            # IMPORTANT: Vérifier si l'appareil associé à cette pièce nécessite complétion
                                            # Ceci peut arriver quand l'appareil existe mais n'est pas trouvé par notre recherche
                                            try:
                                                query = """SELECT a.id, a.type, a.manufacturer, a.ref_modele, a.commercial_ref, a.other_ref, a.category, a.notes 
                                                          FROM appareils a 
                                                          JOIN piece_associations pa ON a.id = pa.appareil_id 
                                                          JOIN pieces p ON pa.piece_id = p.id 
                                                          WHERE p.ref_piece = ? LIMIT 1"""
                                                existing_result = self.db_manager.execute_query(query, [ref_piece_safe])
                                                if existing_result:
                                                    existing_appareil = {
                                                        'id': existing_result[0][0],
                                                        'type': existing_result[0][1],
                                                        'manufacturer': existing_result[0][2],
                                                        'ref_modele': existing_result[0][3],
                                                        'commercial_ref': existing_result[0][4],
                                                        'other_ref': existing_result[0][5],
                                                        'category': existing_result[0][6],
                                                        'notes': existing_result[0][7]
                                                    }
                                                    if self._needs_manual_completion(existing_appareil):
                                                        results['manual_completion'] += 1
                                                        print(f"  📝 Appareil associé nécessite complétion manuelle")
                                            except Exception as e:
                                                print(f"❌ Erreur vérification appareil associé: {e}")
                                            
                                            # Collecter les détails du doublon pour CSV/PDF
                                            if not hasattr(self, '_current_import_duplicates'):
                                                self._current_import_duplicates = []
                                            self._current_import_duplicates.append({
                                                'ligne': row_idx + 1,
                                                'appareil_id': device_id,
                                                'ref_piece': ref_piece_safe,
                                                'appareil_data': {
                                                    'ref_modele': str(ref_modele).strip() if ref_modele else '',
                                                    'commercial_ref': str(commercial_ref).strip() if commercial_ref else '',
                                                    'type': str(type_val).strip() if type_val else '',
                                                    'manufacturer': str(manufacturer).strip() if manufacturer else ''
                                                }
                                            })
                                    except Exception as piece_error:
                                        ref_piece_safe_err = str(ref_piece).strip() if ref_piece else 'N/A'
                                        print(f"❌ Échec association pièce {ref_piece_safe_err} avec nouvel appareil {device_id}: {piece_error}")
                                        app_logger.error(f"Échec association pièce {ref_piece_safe_err} avec nouvel appareil {device_id}: {piece_error}")
                                else:
                                    # Nouvel appareil sans référence de pièce - compter dans les associations manquantes
                                    results['no_piece_ref'] = results.get('no_piece_ref', 0) + 1
                                    print(f"  ⚠️ Ligne {row_idx + 1}: Nouvel appareil créé mais pas de référence de pièce")
                                
                                # Compter si nécessite complétion manuelle (basé sur l'état d'origine)
                                if needs_completion:
                                    results['manual_completion'] += 1
                            else:
                                # Échec de l'insertion, logger l'erreur
                                print(f"❌ Échec insertion appareil: {filtered_data}")
                                app_logger.error(f"Échec insertion appareil: {filtered_data}")
                        else:
                            # Pas de données valides, logger l'erreur
                            print(f"❌ Aucune donnée valide pour ligne: {row}")
                            app_logger.error(f"Aucune donnée valide pour ligne: {row}")
                
            except Exception as e:
                print(f"❌ ERREUR lors du traitement de la ligne {row}: {e}")
                app_logger.error(f"Erreur traitement ligne {row}: {e}")
                # Ne pas compter cette ligne comme traitée si elle échoue
                continue
        
        # Utiliser le nouveau format de résumé unifié
        source = "CSV" if import_type == "csv" else "Collage"
        console_summary = self._generate_console_summary(results, ref_piece, source)
        print(f"\n{console_summary}")
        
        # Informations complémentaires spécifiques
        descriptions_updated = results.get('descriptions_updated', 0)
        if descriptions_updated > 0:
            print(f"  Libellés mis à jour : {descriptions_updated}")
            
        no_piece_ref = results.get('no_piece_ref', 0)
        if no_piece_ref > 0:
            print(f"  Lignes sans référence pièce : {no_piece_ref}")
        
        # Ajouter les doublons collectés aux résultats
        if hasattr(self, '_current_import_duplicates'):
            results['duplicates_list'] = self._current_import_duplicates
            delattr(self, '_current_import_duplicates')  # Nettoyer
        
        return results
    
    def _normalize_reference(self, ref):
        """Normaliser une référence pour la comparaison fuzzy"""
        if not ref:
            return ""
        
        # Supprimer les espaces et convertir en majuscules
        normalized = str(ref).strip().upper()
        
        # Supprimer les zéros initiaux mais garder au moins un chiffre
        if normalized.isdigit():
            normalized = normalized.lstrip('0') or '0'
        
        return normalized

    def _find_existing_device_by_refs(self, ref_modele, commercial_ref, type_val="", manufacturer=""):
        """
        Chercher un appareil existant selon la logique corrigée:
        1. Chercher par ref_modele + commercial_ref (colonnes C et D)
        2. Si trouvé ET que A et B sont fournies dans l'import:
           - A et B vides dans la base → compléter
           - A et B identiques → mettre à jour  
           - A et B différentes → créer nouveau
        3. Si trouvé MAIS A et B ne sont PAS fournies dans l'import:
           - Utiliser l'appareil existant (association simple)
        """
        try:
            # Chercher d'abord par les références (colonnes C et D)
            if ref_modele and ref_modele.strip() and commercial_ref and commercial_ref.strip():
                query = """SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes 
                          FROM appareils 
                          WHERE ref_modele = ? AND commercial_ref = ?"""
                params = [ref_modele.strip(), commercial_ref.strip()]
                result = self.db_manager.execute_query(query, params)
                
                if result:
                    existing = {
                        'id': result[0][0], 
                        'type': result[0][1] or '', 
                        'manufacturer': result[0][2] or '',
                        'ref_modele': result[0][3],
                        'commercial_ref': result[0][4],
                        'other_ref': result[0][5],
                        'category': result[0][6],
                        'notes': result[0][7]
                    }
                    
                    # Vérifier si A et B sont fournies dans l'import
                    import_has_type_manufacturer = bool(type_val and type_val.strip()) or bool(manufacturer and manufacturer.strip())
                    
                    if not import_has_type_manufacturer:
                        # Import sans A et B (CSV 2 colonnes, PDF 3 colonnes) → Association simple
                        print(f"  ✅ Appareil trouvé par C+D, import sans A+B → association directe")
                        return existing
                    
                    # Import avec A et B → Appliquer la logique de comparaison
                    existing_type = existing['type'].strip()
                    existing_manufacturer = existing['manufacturer'].strip()
                    import_type = type_val.strip() if type_val else ""
                    import_manufacturer = manufacturer.strip() if manufacturer else ""
                    
                    # Cas 1: A et B vides dans la base → compléter
                    if not existing_type and not existing_manufacturer:
                        print(f"  ✅ Appareil trouvé avec A et B vides → complétion possible")
                        return existing
                    
                    # Cas 2: A et B identiques → mise à jour
                    elif (existing_type == import_type and existing_manufacturer == import_manufacturer):
                        print(f"  ✅ Appareil trouvé avec A et B identiques → mise à jour")
                        return existing
                    
                    # Cas 3: A et B différentes → ne pas utiliser l'existant (créer nouveau)
                    else:
                        print(f"  ⚠️ Appareil trouvé mais A et B différentes ({existing_type}/{existing_manufacturer} vs {import_type}/{import_manufacturer}) → créer nouveau")
                        return None
                    
            return None
        except Exception as e:
            print(f"Erreur recherche appareil: {e}")
            return None
    
    def _piece_already_associated(self, device_id, ref_piece):
        """Vérifier si la pièce est déjà associée à l'appareil (nouvelle structure)"""
        try:
            query = """
                SELECT pa.id 
                FROM piece_associations pa
                JOIN pieces p ON pa.piece_id = p.id
                WHERE pa.appareil_id = ? AND p.ref_piece = ? 
                LIMIT 1
            """
            result = self.db_manager.execute_query(query, [device_id, ref_piece])
            is_associated = len(result) > 0
            
            # Debug: Log pour traquer les fausses détections
            if is_associated:
                pass  # Appareil déjà associé
            else:
                pass  # Appareil pas associé
                
            return is_associated
        except Exception as e:
            print(f"Erreur lors de la vérification de l'association: {e}")
            return False
    
    def _create_new_device(self, device_type, manufacturer, ref_modele):
        """Créer un nouvel appareil"""
        try:
            query = "INSERT INTO appareils (type, manufacturer, ref_modele) VALUES (?, ?, ?)"
            return self.db_manager.execute_insert(query, [device_type, manufacturer, ref_modele])
        except Exception as e:
            print(f"Erreur création appareil: {e}")
            return None
    
    # Méthode supprimée - logique harmonisée avec _handle_paste dans _process_import
    
    def _update_device_info(self, device_id, updates):
        """Mettre à jour les informations d'un appareil"""
        try:
            if not updates:
                return
            
            set_clauses = []
            params = []
            
            for field, value in updates.items():
                set_clauses.append(f"{field} = ?")
                params.append(value)
            
            params.append(device_id)
            query = f"UPDATE appareils SET {', '.join(set_clauses)} WHERE id = ?"
            
            self.db_manager.cursor.execute(query, params)
            self.db_manager.conn.commit()
            
        except Exception as e:
            print(f"Erreur mise à jour appareil: {e}")
    


    def _detect_paste_columns(self, clipboard_text):
        """Détecter le nombre de colonnes dans les données collées"""
        rows = clipboard_text.strip().split('\n')
        if not rows:
            return 0
            
        # Compter les colonnes de chaque ligne
        column_counts = []
        for row in rows:
            if row.strip():  # Ignorer les lignes vides
                columns = row.split('\t')
                column_counts.append(len(columns))
        
        if not column_counts:
            return 0
            
        # Retourner le nombre de colonnes le plus fréquent
        most_common_count = max(set(column_counts), key=column_counts.count)
        return most_common_count

    def _get_import_options_unified(self, detected_columns=None, default_ref_piece=None, import_method="CSV", sample_data=None):
        """Dialogue unifié pour choisir les options d'import (fallback legacy)"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Options d'import {import_method}")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)  # Fenêtre plus large pour l'aperçu
        
        layout = QVBoxLayout()
        
        # Information sur les colonnes détectées
        if detected_columns:
            if import_method == "CSV":
                info_label = QLabel(f"📊 Fichier détecté: {detected_columns} colonnes")
            elif import_method == "PDF":
                info_label = QLabel(f"📄 Données PDF détectées: {detected_columns} colonnes")
            else:  # COLLAGE
                info_label = QLabel(f"📋 Données détectées: {detected_columns} colonnes")
            info_label.setStyleSheet("color: #28a745; font-weight: bold; margin: 5px;")
            layout.addWidget(info_label)
        
        # Description du format
        format_label = QLabel("Format reconnu:")
        format_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(format_label)
        
        if detected_columns == 1:
            format_desc = QLabel("• 1 colonne → Réf. Modèle uniquement")
        elif detected_columns == 2:
            format_desc = QLabel("• 2 colonnes → Réf. Modèle + Réf. Commerciale")
        elif detected_columns == 3:
            if import_method == "PDF":
                format_desc = QLabel("• 3 colonnes → Réf. technique + Réf. commerciale + Description")
            else:
                format_desc = QLabel("• 3 colonnes → Réf. Modèle + Réf. Commerciale + Autre")
        elif detected_columns >= 4:
            format_desc = QLabel("• 4+ colonnes → Format complet (Type, Fabricant, Réf. Modèle, Réf. Commerciale, ...)")
        else:
            format_desc = QLabel("• Format non reconnu")
        
        format_desc.setStyleSheet("color: #6c757d; margin-left: 20px;")
        layout.addWidget(format_desc)
        
        # Aperçu des données (si disponible)
        if sample_data and len(sample_data) > 0:
            preview_label = QLabel("Aperçu des données:")
            preview_label.setStyleSheet("font-weight: bold; margin-top: 15px;")
            layout.addWidget(preview_label)
            
            # Créer un aperçu formaté des 3 premières lignes
            preview_text = QTextEdit()
            preview_text.setMaximumHeight(120)
            preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; font-family: 'Monaco', 'Menlo', 'Courier New', monospace; font-size: 11px;")
            preview_text.setReadOnly(True)
            
            # Formatage de l'aperçu
            preview_content = ""
            max_lines_to_show = min(3, len(sample_data))
            
            # En-têtes de colonnes
            if detected_columns:
                header_line = ""
                for i in range(detected_columns):
                    header_line += f"Col{i+1:<15} "
                preview_content += f"{'='*60}\n{header_line}\n{'='*60}\n"
            
            # Données d'exemple
            for i in range(max_lines_to_show):
                row = sample_data[i]
                line = ""
                for j in range(min(detected_columns or len(row), len(row))):
                    cell_value = str(row[j])[:12] + "..." if len(str(row[j])) > 12 else str(row[j])
                    line += f"{cell_value:<15} "
                preview_content += f"{line}\n"
                
            if len(sample_data) > 3:
                preview_content += f"\n... et {len(sample_data) - 3} autres lignes"
                
            preview_text.setPlainText(preview_content)
            layout.addWidget(preview_text)
        
        # Référence de pièce (optionnelle)
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence de pièce (optionnelle):"))
        ref_input = QLineEdit()
        ref_input.setText(default_ref_piece if default_ref_piece else "")
        ref_input.setPlaceholderText("Référence de la pièce à associer à tous les appareils")
        ref_layout.addWidget(ref_input)
        layout.addLayout(ref_layout)
        
        # Libellé de la pièce (optionnel)
        libelle_layout = QHBoxLayout()
        libelle_layout.addWidget(QLabel("Libellé de la pièce (optionnel):"))
        libelle_input = QLineEdit()
        libelle_input.setPlaceholderText("Description/libellé de la pièce")
        libelle_layout.addWidget(libelle_input)
        layout.addLayout(libelle_layout)
        
        # Case à cocher pour les en-têtes (CSV uniquement)
        headers_checkbox = None
        if import_method == "CSV":
            headers_checkbox = QCheckBox("Le fichier contient une ligne d'en-têtes (ignorer la première ligne)")
            headers_checkbox.setChecked(False)
            headers_checkbox.setToolTip("Cochez cette case si la première ligne de votre fichier contient les noms des colonnes")
            layout.addWidget(headers_checkbox)
        
        # Gestion de la 3ème colonne (seulement si 3 colonnes)
        third_col_combo = None
        if detected_columns == 3:
            third_col_layout = QHBoxLayout()
            if import_method == "PDF":
                third_col_layout.addWidget(QLabel("Destination Description:"))
            else:
                third_col_layout.addWidget(QLabel("Destination 3ème colonne:"))
            third_col_combo = QComboBox()
            third_col_combo.addItems(["Ignorer", "Autre référence", "Notes"])
            third_col_combo.setCurrentIndex(0)  # Par défaut "Ignorer"
            third_col_layout.addWidget(third_col_combo)
            layout.addLayout(third_col_layout)
        
        # Boutons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("Importer")
        ok_button.setDefault(True)
        ok_button.setStyleSheet("QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 8px 16px; }")
        cancel_button = QPushButton("Annuler")
        cancel_button.setStyleSheet("QPushButton { padding: 8px 16px; }")
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Connexions des boutons
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        
        # Afficher le dialogue
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Déterminer le type d'import
            import_type = detected_columns if detected_columns else 3
            
            # Mapper le choix de la 3ème colonne
            third_column_choice = "ignore"  # Valeur par défaut
            if third_col_combo:
                choice = third_col_combo.currentText()
                if choice == "Ignorer":
                    third_column_choice = "ignore"
                elif choice == "Autre référence":
                    third_column_choice = "other_ref"
                elif choice == "Notes":
                    third_column_choice = "notes"
            
            # Récupérer l'option d'en-têtes (CSV uniquement)
            has_headers = headers_checkbox.isChecked() if headers_checkbox else False
            
            return import_type, ref_input.text().strip(), third_column_choice, has_headers, libelle_input.text().strip()
        
        return None, None, None, None, None

    def _show_import_summary(self, results, ref_piece, method="CSV"):
        """Afficher la synthèse d'import avec le nouveau format unifié"""
        # Calculer le total traité
        total_processed = results.get('total_imported', 0) + results.get('duplicates_skipped', 0)
        
        # Nouveau format unifié
        summary = f"📊 Résumé de l'import {method} :\n"
        summary += f"  Total {total_processed} lignes traitées\n"
        
        # Nouveaux appareils
        new_entries = results.get('new_entries', 0)
        if new_entries > 0:
            summary += f"  {new_entries} nouveaux appareils\n"
            
            # Détail des nouveaux appareils
            auto_completed = results.get('auto_completed', 0)
            manual_completion = results.get('manual_completion', 0)
            
            if auto_completed > 0:
                summary += f"   -> {auto_completed} completés automatiquement\n"
            if manual_completion > 0:
                summary += f"   -> {manual_completion} à compléter manuellement\n"
        
        # Appareils mis à jour
        matches_found = results.get('matches_found', 0)
        if matches_found > 0:
            summary += f"  {matches_found} appareils mis à jours\n"
        
        # Associations créées
        associations_created = results.get('associations_created', 0)
        if associations_created > 0:
            summary += f"  {associations_created} associations de pièce créées\n"
        
        # Doublons ignorés
        duplicates_skipped = results.get('duplicates_skipped', 0)
        if duplicates_skipped > 0:
            summary += f"  Associations déjà existantes : {duplicates_skipped}\n"
        
        # Lignes rejetées
        rejected_lines = results.get('rejected_lines', 0)
        if rejected_lines > 0:
            summary += f"  {rejected_lines} ligne rejetée\n"
        else:
            summary += f"  0 ligne rejetée\n"
        
        # Lignes sans référence de pièce
        no_piece_ref = results.get('no_piece_ref', 0)
        if no_piece_ref > 0:
            summary += f"  {no_piece_ref} ligne sans référence de pièce\n"
        
        self._show_info(summary)
    
    def _generate_console_summary(self, results, ref_piece, source, pdf_files_info=None):
        """Générer la synthèse dans le format console standardisé"""
        summary = f"📊 Import {source}"
        if ref_piece:
            summary += f" (pièce: {ref_piece})"
        summary += ":\n"
        
        # Si c'est un import PDF et qu'on a des informations sur les fichiers, les ajouter
        if pdf_files_info:
            for file_info in pdf_files_info:
                summary += f"📄 Fichier PDF {file_info['filename']}: {file_info['lines_extracted']} lignes extraites\n"
        
        # Ligne principale - total des lignes du fichier original
        # Le vrai total = lignes traitées + doublons ignorés dans le fichier
        total_processed = results.get('total_imported', 0)
        duplicates_ignored = results.get('duplicates_in_file', 0)
        # Utiliser le nombre de lignes originales si disponible, sinon calculer
        original_line_count = results.get('original_line_count', total_processed + duplicates_ignored)
        summary += f"Lignes traitées : {original_line_count}\n"
        
        # Section Appareils avec sous-détails
        summary += "Appareils :\n"
        
        # Créés
        new_entries = results.get('new_entries', 0)
        summary += f"==> Créés : {new_entries}\n"
        
        # Complétion automatique (nouveaux appareils dont type et fabricant ont été auto-complétés)
        auto_completed = results.get('auto_completed', 0)
        # Pour les appareils existants mis à jour
        matches_found = results.get('matches_found', 0)
        total_auto_completed = auto_completed + matches_found
        summary += f"==> Complétion automatique : {total_auto_completed}\n"
        
        # À compléter (nouveaux appareils qui manquent encore de type/fabricant)
        manual_completion = results.get('manual_completion', 0)
        summary += f"==> À compléter : {manual_completion}\n"
        
        # Doublons ignorés dans le fichier
        if duplicates_ignored > 0:
            summary += f"==> Doublon ignoré : {duplicates_ignored}\n"
        
        # Section Associations de pièce
        summary += "Associations de pièce :\n"
        
        # Nouvelles associations
        associations_created = results.get('associations_created', 0)
        associations_existing = results.get('associations_existing', 0)
        summary += f"==> Nouvelles : {associations_created}\n"
        summary += f"==> Déjà associés : {associations_existing}"
        
        return summary

    def _log_import_to_history(self, results, ref_piece, source, pdf_files_info=None):
        """Enregistrer l'import dans l'historique avec format console"""
        from datetime import datetime
        
        # Générer la synthèse dans le format console
        console_summary = self._generate_console_summary(results, ref_piece, source, pdf_files_info)
        
        # Déterminer le type d'opération
        operation_type = "import_csv" if source != "Collage" else "import_paste"
        
        # Enregistrer dans les logs
        if hasattr(self, 'logger'):
            self.logger.log_data_operation(
                operation_type,
                {
                    'source': source,
                    'ref_piece': ref_piece,
                    'results': results,
                    'summary': console_summary
                }
            )
        
        # Ajouter à l'historique des actions
        self.undo_manager.add_action({
            'type': operation_type,
            'description': f"Import {source}: {console_summary.split(':')[0]}",
            'before_data': None,
            'after_data': results,
            'source': source
        })
        
        # Ajouter à l'historique visible avec le format console
        self._add_to_history(console_summary)
    
    def _show_import_results_new(self, results):
        """Traiter les résultats d'import du nouveau système ImportManager - SEULEMENT dans l'historique"""
        try:
            # Vérifier les erreurs - les afficher si critique
            if results.get('errors'):
                error_msg = "Erreurs lors de l'import:\n" + "\n".join(results['errors'])
                QMessageBox.warning(self, "Erreurs d'import", error_msg)
            
            # Créer un résumé détaillé EXACTEMENT comme l'ancien format
            # Note: _add_to_history ajoute automatiquement le timestamp, pas besoin de le faire ici
            
            # Déterminer le type d'import
            if results.get('total_files', 0) > 1:
                import_type = f"📊 Import Multi-fichiers ({results['total_files']} fichiers)"
            else:
                import_type = "📊 Import"
            
            # Commencer le résumé
            summary = f"{import_type}:\n"
            
            # Si c'est multi-fichiers, lister les fichiers avec leurs détails
            if results.get('total_files', 0) > 1:
                file_details = results.get('file_details', [])
                for detail in file_details:
                    summary += f"📄 Fichier {detail['type']} {detail['filename']}: {detail['lines_processed']} lignes extraites\n"
            
            # Calculer le total des lignes extraites de tous les fichiers
            file_details = results.get('file_details', [])
            total_lines_extracted = sum(detail['lines_processed'] for detail in file_details)
            
            # Si pas de détails de fichiers (import simple), utiliser total_imported + duplicates
            if not file_details:
                total_lines_extracted = results.get('total_imported', 0) + results.get('duplicates_in_file', 0)
            
            summary += f"     ==> Lignes traitées : {total_lines_extracted}\n\n"
            
            # Section Appareils (format exact)
            summary += "Appareils :\n"
            summary += f"     ==> Créés : {results.get('new_entries', 0)}\n"
            summary += f"     ==> Complétion automatique : {results.get('matches_found', 0)}\n"
            summary += f"     ==> À compléter : {results.get('manual_completion', 0)}\n"
            summary += f"     ==> Doublon ignoré : {results.get('duplicates_in_file', 0)}\n"
            
            # Section Associations de pièce (format exact)
            summary += "Associations de pièce :\n"
            summary += f"     ==> Nouvelles : {results.get('associations_created', 0)}\n"
            summary += f"     ==> Déjà associés : {results.get('associations_existing', 0)}"
            
            # Ajouter SEULEMENT à l'historique (timestamp ajouté automatiquement)
            self._add_to_history(summary)
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'affichage", f"Impossible de traiter les résultats: {e}")
            # En cas d'erreur, au moins ajouter un message basique à l'historique
            try:
                basic_msg = f"📥 Import effectué (erreur d'affichage des détails)"
                self._add_to_history(basic_msg)
            except:
                pass  # Si même l'historique échoue, on ne peut rien faire

    def _validate_and_detect_inconsistencies(self):
        """Ouvrir la fenêtre interactive de validation et incohérences"""
        try:
            if not hasattr(self, 'validation_window') or not self.validation_window:
                self.validation_window = ValidationWindow(self)
            
            self.validation_window.show()
            self.validation_window.raise_()
            self.validation_window.activateWindow()
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'ouverture de la validation: {e}")
    
    def _open_pieces_manager(self):
        """Ouvrir la fenêtre de gestion des pièces"""
        try:
            from .pieces_manager import PiecesManagerWindow
            if not hasattr(self, 'pieces_manager') or not self.pieces_manager:
                self.pieces_manager = PiecesManagerWindow(self, self.db_manager)
            
            self.pieces_manager.show()
            self.pieces_manager.raise_()
            self.pieces_manager.activateWindow()
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'ouverture du gestionnaire de pièces: {e}")
    
    def _clear_column_filters(self):
        """Nettoyer tous les filtres de colonnes"""
        for col_idx, filter_widget in self.filter_widgets.items():
            if filter_widget is not None:  # Skip removed filters
                filter_widget.blockSignals(True)
                if isinstance(filter_widget, QComboBox):
                    filter_widget.setCurrentText("")
                else:  # QLineEdit
                    filter_widget.clear()
                filter_widget.blockSignals(False)
    
    def _update_incomplete_button_visibility(self):
        """Mettre à jour la visibilité du bouton incomplètes selon les données"""
        try:
            incomplete_count = self.db_manager.count_incomplete_devices()
            if hasattr(self, 'incomplete_filter_btn'):
                if incomplete_count > 0:
                    self.incomplete_filter_btn.show()
                    from src.core.config import pluralize
                    if self.show_incomplete_only:
                        # Si le filtre est actif, mettre à jour avec le nombre restant
                        self.incomplete_filter_btn.setText(f"📋 Filtre actif, plus que {pluralize(incomplete_count, 'ligne')}")
                        self.incomplete_filter_btn.setToolTip(f"Filtre actif - {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                    else:
                        # Si le filtre n'est pas actif, afficher le nombre total
                        self.incomplete_filter_btn.setText(f"📋 {pluralize(incomplete_count, 'incomplète')}")
                        self.incomplete_filter_btn.setToolTip(f"Afficher uniquement les {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                else:
                    self.incomplete_filter_btn.hide()
                    # Désactiver le filtre si il n'y a plus d'appareils incomplets
                    if self.show_incomplete_only:
                        self.show_incomplete_only = False
                        self.load_data()
        except Exception as e:
            print(f"Erreur lors de la mise à jour du bouton incomplètes: {e}")

    def _toggle_incomplete_filter(self, checked: bool):
        """Basculer le filtre pour afficher seulement les lignes incomplètes"""
        self.show_incomplete_only = checked
        
        if checked:
            # Activer le filtre - nettoyer les autres filtres d'abord
            self._clear_column_filters()
            self.search_input.clear()
            
            # Compter et afficher le nombre de lignes filtrées
            incomplete_count = self.db_manager.count_incomplete_devices()
            from src.core.config import pluralize
            self.incomplete_filter_btn.setText(f"📋 Filtre actif, plus que {pluralize(incomplete_count, 'ligne')}")
            # Le style est géré par le CSS moderne via :checked
        else:
            # Désactiver le filtre et mettre à jour le texte avec le nombre
            incomplete_count = self.db_manager.count_incomplete_devices()
            from src.core.config import pluralize
            self.incomplete_filter_btn.setText(f"📋 {pluralize(incomplete_count, 'incomplète')}")
            # Le style est géré par le CSS moderne
        
        # Recharger les données avec ou sans filtre
        self.current_page = 0  # Retour à la première page
        # Utiliser la recherche parsée actuelle
        search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
        self.load_data(search_term)
    
    def _force_refresh_display(self, reset_page=False, clear_filters=False):
        """Forcer le rafraîchissement complet de l'affichage du tableau"""
        try:
            # Sauvegarder l'état de recherche actuel
            temp_search = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            
            # Retourner à la première page si demandé (après modifications globales)
            if reset_page:
                self.current_page = 0
            
            # Nettoyer les filtres de colonnes si demandé
            if clear_filters:
                self._clear_column_filters()
            
            # Débloquer les signaux si nécessaire pour éviter les blocages
            was_blocked = self.table.signalsBlocked()
            if was_blocked:
                self.table.blockSignals(False)
            
            # Recharger avec les critères appropriés
            self.load_data(temp_search)
            
            # Forcer la mise à jour de l'interface
            self.table.viewport().update()
            self.table.update()
            
            # Redimensionner les colonnes
            self.table.resizeColumnsToContents()
            
            # Mettre à jour le compteur
            self._update_counter()
            
            # Mettre à jour la visibilité du bouton incomplètes après rafraîchissement
            self._update_incomplete_button_visibility()
            
            # Repositionner la poignée de drag
            self._position_drag_handle()
            
            app_logger.debug(f"Rafraîchissement forcé terminé - Page: {self.current_page} - Critères: '{temp_search}' - Lignes affichées: {self.table.rowCount()}")
            
        except Exception as e:
            app_logger.error(f"Erreur lors du rafraîchissement forcé: {e}")
            self._show_error(f"Erreur lors du rafraîchissement: {e}")
    
    
    def _open_log_viewer(self):
        """Ouvrir le visualiseur de logs"""
        try:
            if not hasattr(self, 'log_viewer') or not self.log_viewer:
                self.log_viewer = LogViewer(self)
            
            self.log_viewer.show()
            self.log_viewer.raise_()
            self.log_viewer.activateWindow()
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'ouverture du visualiseur de logs: {e}")
    
    def _open_user_guide(self):
        """Ouvrir le guide d'utilisation"""
        try:
            # URL du guide d'utilisation (vous pouvez la modifier selon vos besoins)
            guide_url = "https://github.com/username/repository/wiki/Guide-Utilisation"
            
            # Message informatif avec options
            from PyQt5.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 
                "Guide d'utilisation",
                "Le guide d'utilisation sera ouvert dans votre navigateur web.\n\n"
                "📖 Contenu du guide :\n"
                "• Import de fichiers CSV et collage de données\n"
                "• Gestion des pièces et associations\n"
                "• Fonctionnalités avancées et raccourcis\n"
                "• Résolution des problèmes courants\n\n"
                "Souhaitez-vous continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                import webbrowser
                webbrowser.open(guide_url)
                
        except Exception as e:
            # En cas d'erreur, afficher un guide local simple
            self._show_local_guide()
    
    def _show_local_guide(self):
        """Afficher un guide d'utilisation local en cas d'erreur"""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
            
            dialog = QDialog(self)
            dialog.setWindowTitle("📖 Guide d'utilisation - 1001pieces.com")
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            
            # Contenu du guide
            guide_text = QTextEdit()
            guide_text.setReadOnly(True)
            guide_content = """
# Guide d'utilisation - 1001pieces.com

## 🚀 Démarrage rapide

### Import de données
1. **Import de fichiers** : Utilisez le bouton "📈 Import" ou glissez/déposez un fichier CSV ou PDF sur le tableau
2. **Collage** : Copiez des données depuis Excel/Calc et collez avec Ctrl+V
3. **Référence de pièce** : Lors de l'import, la référence de pièce est automatiquement remplie avec le nom du fichier

### Navigation et édition
- **Double-clic** sur une cellule pour l'éditer
- **Ctrl+N** : Ajouter une nouvelle ligne
- **Ctrl+S** : Sauvegarder
- **Ctrl+Z/Y** : Annuler/Refaire
- **Ctrl+F** : Rechercher

### Gestion des pièces
- **Gestionnaire de pièces** : Accessible via l'icône 🔧 dans la barre d'outils
- **Sélection multiple** : Ctrl+Clic pour sélectionner plusieurs pièces à supprimer
- **Filtrage** : Recherche et filtre des pièces orphelines

### Fonctionnalités avancées
- **Glisser/Déposer** : Déposez des fichiers CSV directement sur le tableau
- **Auto-complétion** : Les champs vides sont automatiquement complétés
- **Historique** : Toutes les modifications sont tracées dans l'historique
- **Validation** : Détection automatique des doublons et inconsistances

## 🔧 Dépannage

### Problèmes d'import
- Vérifiez l'encodage du fichier (UTF-8 recommandé)
- Assurez-vous que le fichier CSV a au moins 2 colonnes
- Première ligne = en-têtes (ignorée lors de l'import)

### Performance
- L'application pagine automatiquement les gros datasets
- Utilisez les filtres pour réduire l'affichage
- La recherche est limitée à 5000 résultats

## 📞 Support
En cas de problème, consultez les logs via "📊 Journal" dans la barre d'outils.
            """
            guide_text.setMarkdown(guide_content)
            layout.addWidget(guide_text)
            
            # Bouton de fermeture
            close_button = QPushButton("Fermer")
            close_button.clicked.connect(dialog.close)
            layout.addWidget(close_button)
            
            dialog.setLayout(layout)
            dialog.exec_()
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'affichage du guide local: {e}")
    
    def _apply_column_visibility(self):
        """Appliquer la visibilité des colonnes au tableau"""
        for col_idx, visible in self.visible_columns.items():
            self.table.setColumnHidden(col_idx, not visible)
            # Masquer aussi les filtres correspondants
            if col_idx in self.filter_widgets:
                self.filter_widgets[col_idx].setVisible(visible)
    
    def _configure_columns(self):
        """Ouvrir la boîte de dialogue de configuration des colonnes"""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel
            
            dialog = QDialog(self)
            dialog.setWindowTitle("⚙️ Configuration des colonnes")
            dialog.resize(400, 300)
            
            layout = QVBoxLayout(dialog)
            
            # Titre
            title_label = QLabel("Choisissez les colonnes à afficher :")
            title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
            layout.addWidget(title_label)
            
            # Checkboxes pour chaque colonne
            checkboxes = {}
            for col in Config.COLUMN_CONFIG:
                checkbox = QCheckBox(col['name'])
                checkbox.setChecked(self.visible_columns[col['index']])
                checkbox.setEnabled(not col['mandatory'])  # Les colonnes obligatoires ne peuvent pas être cachées
                if col['mandatory']:
                    checkbox.setToolTip("Cette colonne est obligatoire et ne peut pas être cachée")
                checkboxes[col['index']] = checkbox
                layout.addWidget(checkbox)
            
            # Boutons
            button_layout = QHBoxLayout()
            
            reset_btn = QPushButton("Réinitialiser")
            reset_btn.clicked.connect(lambda: self._reset_column_defaults(checkboxes))
            button_layout.addWidget(reset_btn)
            
            button_layout.addStretch()
            
            cancel_btn = QPushButton("Annuler")
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)
            
            apply_btn = QPushButton("Appliquer")
            apply_btn.setObjectName("primaryBtn")
            apply_btn.clicked.connect(lambda: self._apply_column_config(checkboxes, dialog))
            button_layout.addWidget(apply_btn)
            
            layout.addLayout(button_layout)
            
            dialog.exec_()
            
        except Exception as e:
            self._show_error(f"Erreur lors de la configuration des colonnes: {e}")
    
    def _reset_column_defaults(self, checkboxes):
        """Réinitialiser les colonnes aux valeurs par défaut"""
        for col in Config.COLUMN_CONFIG:
            if not col['mandatory']:
                checkboxes[col['index']].setChecked(col['visible'])
    
    def _apply_column_config(self, checkboxes, dialog):
        """Appliquer la nouvelle configuration des colonnes"""
        try:
            # Sauvegarder les nouveaux paramètres
            for col_idx, checkbox in checkboxes.items():
                self.visible_columns[col_idx] = checkbox.isChecked()
                self.settings.setValue(f"column_{col_idx}_visible", checkbox.isChecked())
            
            # Appliquer au tableau
            self._apply_column_visibility()
            
            # Fermer la boîte de dialogue
            dialog.accept()
            
            # Rafraîchir l'affichage
            self.statusbar.showMessage("Configuration des colonnes mise à jour", Config.STATUS_MESSAGE_TIMEOUT)
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'application de la configuration: {e}")
    
    def _clear_search(self):
        """Effacer le champ de recherche principal et tous les filtres"""
        self.search_input.clear()
        # Effacer aussi tous les filtres de colonnes
        for filter_widget in self.filter_widgets.values():
            filter_widget.clear()
        self.load_data()

    # --- Méthodes d'événements ---

    def eventFilter(self, source, event):
        """Filtrer les événements pour la gestion du drag handle"""
        # Vérifier si l'objet table existe encore
        if not hasattr(self, 'table') or self.table is None:
            return super().eventFilter(source, event)
        
        # Vérifier si l'objet viewport existe encore
        try:
            viewport = self.table.viewport()
            if viewport is None:
                return super().eventFilter(source, event)
        except RuntimeError:
            # L'objet C++ a été détruit
            return super().eventFilter(source, event)
        
        if source is viewport:
            if event.type() in [QEvent.Type.Resize, QEvent.Type.Paint]:
                self._position_drag_handle()
        return super().eventFilter(source, event)
    
    def _update_progress_with_debounce(self, progress_dialog, value, text=None):
        """Mettre à jour la barre de progression avec débouncing"""
        if not progress_dialog:
            return
            
        current_time = __import__('time').time() * 1000  # Convertir en ms
        
        # Forcer la mise à jour pour 0% et 100%, sinon respecter l'intervalle
        if value == 0 or value >= progress_dialog.maximum() or (current_time - self.last_progress_update) >= self.progress_update_interval:
            progress_dialog.setValue(value)
            if text:
                progress_dialog.setLabelText(text)
            QApplication.processEvents()
            self.last_progress_update = current_time

    def dragEnterEvent(self, event):
        """Gérer l'entrée d'un glisser/déposer"""
        if event.mimeData().hasUrls():
            # Vérifier si au moins un fichier est un CSV ou PDF
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.csv', '.pdf')):
                        event.acceptProposedAction()
                        self._show_drag_overlay()
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        """Gérer le mouvement d'un glisser/déposer"""
        if event.mimeData().hasUrls():
            # Vérifier si au moins un fichier est un CSV ou PDF
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.csv', '.pdf')):
                        event.acceptProposedAction()
                        return
        event.ignore()
        
    def dragLeaveEvent(self, event):
        """Gérer la sortie d'un glisser/déposer"""
        self._hide_drag_overlay()
        event.accept()

    def dropEvent(self, event):
        """Gérer le déposer d'un ou plusieurs fichiers CSV ou PDF - Version améliorée"""
        self._hide_drag_overlay()
        
        if event.mimeData().hasUrls():
            supported_files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.csv', '.pdf')):
                        supported_files.append(file_path)
            
            if supported_files:
                # Utiliser le nouveau gestionnaire unifié
                results = self.import_manager.import_files(supported_files, show_dialog=True)
                
                if results:
                    self._show_import_results_new(results)
                    self.load_data()  # Rafraîchir l'affichage
                
                event.acceptProposedAction()
                return
        
        event.ignore()
        
    def dropEvent_legacy(self, event):
        """Ancienne méthode de drag & drop - gardée pour référence"""
        self._hide_drag_overlay()
        
        if event.mimeData().hasUrls():
            csv_files = []
            pdf_files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith('.csv'):
                        csv_files.append(file_path)
                    elif file_path.lower().endswith('.pdf'):
                        pdf_files.append(file_path)
            
            # Priorité aux fichiers CSV (un seul à la fois)
            if csv_files:
                self._import_csv_from_path(csv_files[0])
                event.acceptProposedAction()
                return
            elif pdf_files:
                # Supporter plusieurs fichiers PDF
                self._import_pdf_from_path(pdf_files)
                event.acceptProposedAction()
                return
        event.ignore()

    def _import_csv_from_path(self, file_path):
        """Importer un fichier CSV depuis un chemin donné (utilisé pour le glisser/déposer)
        
        MIGRATION: Utilise ImportManager pour le drag&drop avec fallback vers ancien système
        """
        try:
            # NOUVEAU : Utiliser ImportManager pour drag&drop
            results = self.import_manager.import_from_drag_drop([file_path])
            if results:
                self._show_import_results_new(results)
                self.load_data()
                return
        except Exception as e:
            app_logger.warning(f"Échec ImportManager drag&drop CSV, fallback vers ancien système: {e}")
        
        # FALLBACK : Code legacy en cas d'échec ImportManager
        try:
            import csv
            from datetime import datetime
            
            # Utiliser ImportManager pour analyse et dialogue
            try:
                # Chargement et analyse avec ImportManager
                sample_data = self.import_manager.load_csv_data(file_path, max_rows=5)
                detected_columns = len(sample_data[0]) if sample_data else 0
                
                if detected_columns == 0:
                    self._show_error("Impossible de détecter les colonnes du fichier CSV")
                    return
                
                # Extraire référence depuis nom de fichier
                import os
                filename_without_ext = os.path.splitext(os.path.basename(file_path))[0]
                
                # Utiliser dialogue deprecated (sera supprimé en Phase 4.4)
                import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(detected_columns, filename_without_ext, "CSV", sample_data)
                if import_type is None:
                    return
                    
            except Exception as e:
                self._show_error(f"Erreur lors de l'analyse du fichier CSV: {e}")
                return
            
            # Le reste du traitement est identique à _import_csv
            separator = self._detect_separator(file_path)
            encoding = self._detect_file_encoding(file_path)
            
            # Utiliser la même logique que l'import CSV classique : passer des listes brutes
            imported_data = []
            with open(file_path, 'r', encoding=encoding, errors='replace') as file:
                csv_reader = csv.reader(file, delimiter=separator)
                
                for row_index, row in enumerate(csv_reader):
                    if row_index == 0 and has_headers:  # Header (seulement si spécifié)
                        continue
                    
                    if len(row) >= 2 and any(str(cell).strip() for cell in row):  # Au moins 2 colonnes avec des données
                        imported_data.append(row)
            
            if not imported_data:
                QMessageBox.warning(self, "Import CSV", "Aucune donnée valide trouvée dans le fichier.")
                return
            
            # Créer une barre de progression pour les gros imports
            progress_dialog = None
            if len(imported_data) >= 1000:
                progress_dialog = QProgressDialog(
                    f"Import CSV en cours... 0 / {len(imported_data)} lignes",
                    "Annuler",
                    0, len(imported_data),
                    self
                )
                progress_dialog.setWindowTitle("Import CSV - Glisser/Déposer")
                progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                progress_dialog.show()
                QApplication.processEvents()
            
            # Traitement de l'import (utiliser import_type)
            results = self._process_import(imported_data, import_type, ref_piece, third_column_choice, progress_dialog, libelle_piece)
            
            # Fermer la barre de progression
            if progress_dialog:
                progress_dialog.setValue(len(imported_data))
                progress_dialog.close()
            
            # Affichage du résumé et ajout à l'historique
            self._log_import_to_history(results, ref_piece, f"CSV (Glisser/Déposer - {os.path.basename(file_path)})")
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'import CSV par glisser/déposer: {e}")
    
    def _import_pdf_from_path(self, file_paths):
        """Importer un ou plusieurs fichiers PDF depuis des chemins donnés
        
        MIGRATION: Utilise ImportManager pour le drag&drop avec fallback vers ancien système
        """
        try:
            # Assurer que file_paths est une liste
            if isinstance(file_paths, str):
                file_paths = [file_paths]
            
            # NOUVEAU : Utiliser ImportManager pour drag&drop
            results = self.import_manager.import_from_drag_drop(file_paths)
            if results:
                self._show_import_results_new(results)
                self.load_data()
                return
        except Exception as e:
            app_logger.warning(f"Échec ImportManager drag&drop PDF, fallback vers ancien système: {e}")
        
        # FALLBACK : Code legacy en cas d'échec ImportManager
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor, PDFExtractionError
            import os
            
            # Assurer que file_paths est une liste
            if isinstance(file_paths, str):
                file_paths = [file_paths]
            
            # Extraire le nom du fichier pour la référence de pièce (si un seul fichier)
            suggested_ref_piece = None
            if len(file_paths) == 1:
                suggested_ref_piece = os.path.splitext(os.path.basename(file_paths[0]))[0]
            
            # Utiliser ImportManager pour analyser le PDF
            sample_data = []
            if len(file_paths) > 0:
                try:
                    sample_data = self.import_manager.load_pdf_data(file_paths[0], max_rows=3)
                except Exception as e:
                    print(f"Erreur lecture aperçu PDF: {e}")
                    sample_data = []
            
            # Afficher la boîte de dialogue d'options d'import avec aperçu
            import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(3, suggested_ref_piece, "PDF", sample_data)
            if import_type is None:
                return
            
            # Créer l'extracteur Camelot
            extractor = CamelotPDFExtractor()
            
            # Traiter tous les fichiers
            all_converted_data = []
            processed_files = []
            pdf_files_info = []  # Pour collecter les informations des fichiers PDF
            
            # Créer une barre de progression pour l'import PDF
            total_files = len(file_paths)
            progress_dialog = self._create_progress_dialog("Import PDF", total_files, "Import PDF en cours... {} / {} fichier(s)")
            progress_dialog.show()
            QApplication.processEvents()  # Forcer l'affichage
            
            for file_idx, file_path in enumerate(file_paths):
                # Mettre à jour la barre de progression
                if progress_dialog.wasCanceled():
                    break
                    
                progress_dialog.setValue(file_idx)
                progress_dialog.setLabelText(f"Traitement: {os.path.basename(file_path)} ({file_idx + 1} / {total_files})")
                QApplication.processEvents()
                try:
                    # Valider la compatibilité
                    is_compatible, error_msg = extractor.validate_pdf_compatibility(file_path)
                    if not is_compatible:
                        self._show_error(f"PDF non compatible ({os.path.basename(file_path)}): {error_msg}")
                        continue
                    
                    # Extraire les données
                    extracted_data = extractor.extract_data(file_path)
                    
                    if not extracted_data:
                        self._show_error(f"Aucune donnée extraite du fichier PDF: {os.path.basename(file_path)}")
                        continue
                    
                    # Collecter les informations du fichier PDF pour l'historique
                    pdf_files_info.append({
                        'filename': os.path.basename(file_path),
                        'lines_extracted': len(extracted_data)
                    })
                    
                    # Convertir les données extraites en format 3 colonnes pour import_type = 3
                    for row in extracted_data:
                        # Les données PDF sont en format [ref_technique, ref_commerciale, description]
                        # On les garde en 3 colonnes selon le choix de l'utilisateur
                        if third_column_choice == "notes":
                            all_converted_data.append([row[0], row[1], row[2]])  # [ref_modele, commercial_ref, notes]
                        elif third_column_choice == "other_ref":
                            all_converted_data.append([row[0], row[1], row[2]])  # [ref_modele, commercial_ref, other_ref]
                        else:  # ignore
                            all_converted_data.append([row[0], row[1], ""])  # [ref_modele, commercial_ref, ignored]
                    
                    processed_files.append(os.path.basename(file_path))
                    
                except Exception as e:
                    self._show_error(f"Erreur lors du traitement de {os.path.basename(file_path)}: {e}")
                    continue
            
            # Fermer la barre de progression
            if progress_dialog:
                progress_dialog.setValue(total_files)
                progress_dialog.close()
            
            if not all_converted_data:
                self._show_error("Aucune donnée extraite des fichiers PDF")
                return
            
            # Debug : afficher le total des lignes converties
            print(f"📊 Total des lignes converties pour traitement: {len(all_converted_data)}")
            
            # Créer une barre de progression pour le traitement des lignes
            lines_progress = None
            if len(all_converted_data) >= 1000:  # Seulement pour les gros imports
                lines_progress = QProgressDialog(
                    f"Traitement des lignes... 0 / {len(all_converted_data)}",
                    "Annuler",
                    0, len(all_converted_data),
                    self
                )
                lines_progress.setWindowTitle("Traitement des données")
                lines_progress.setWindowModality(Qt.WindowModality.WindowModal)
                lines_progress.show()
                QApplication.processEvents()
            
            # Traiter l'import avec la même logique que CSV
            results = self._process_import(all_converted_data, import_type, ref_piece, third_column_choice, lines_progress, libelle_piece)
            
            # Fermer la barre de progression des lignes
            if lines_progress:
                lines_progress.setValue(len(all_converted_data))
                lines_progress.close()
            
            # Afficher la synthèse
            
            # Enregistrer dans l'historique
            if len(processed_files) == 1:
                source_info = f"PDF ({processed_files[0]})"
            else:
                source_info = f"PDF ({len(processed_files)} fichiers)"
            
            self._log_import_to_history(results, ref_piece, source_info, pdf_files_info)
            
            # Gérer les doublons s'il y en a
            
            # Actualiser l'affichage
            self._force_refresh_display(reset_page=True, clear_filters=True)
            
        except PDFExtractionError as e:
            self._show_error(f"Erreur d'extraction PDF: {e}")
        except Exception as e:
            self._show_error(f"Erreur lors de l'import PDF: {e}")
    

    def _get_import_options_pdf(self, suggested_ref_piece=None):
        """Dialogue pour choisir les options d'import PDF"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Options d'import PDF")
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # Information sur le PDF
        info_label = QLabel("📄 Données PDF détectées: 3 colonnes (Réf. technique, Réf. commerciale, Description)")
        info_label.setStyleSheet("color: #28a745; font-weight: bold; margin: 5px;")
        layout.addWidget(info_label)
        
        # Référence de pièce (optionnelle) - pré-remplie avec le nom du fichier
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence de pièce (optionnelle):"))
        ref_input = QLineEdit()
        if suggested_ref_piece:
            ref_input.setText(suggested_ref_piece)
        ref_layout.addWidget(ref_input)
        layout.addLayout(ref_layout)
        
        # Gestion de la 3ème colonne (Description)
        third_col_layout = QHBoxLayout()
        third_col_layout.addWidget(QLabel("Stocker la Description dans:"))
        third_col_combo = QComboBox()
        third_col_combo.addItems(["Ignorer", "Autre référence", "Notes"])
        third_col_combo.setCurrentIndex(0)  # Ignorer par défaut
        third_col_layout.addWidget(third_col_combo)
        layout.addLayout(third_col_layout)
        
        # Boutons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Annuler")
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        result = [None, None, None, None]
        
        def on_ok():
            result[0] = 3  # Toujours 3 colonnes pour PDF
            result[1] = ref_input.text().strip() if ref_input.text().strip() else None
            
            third_choice = third_col_combo.currentText()
            if third_choice == "Ignorer":
                result[2] = "ignore"
            elif third_choice == "Autre référence":
                result[2] = "other_ref"
            elif third_choice == "Notes":
                result[2] = "notes"
            else:
                result[2] = "ignore"  # Par défaut
            
            result[3] = False  # Pas d'en-têtes dans les données extraites
            dialog.accept()
        
        def on_cancel():
            dialog.reject()
        
        ok_button.clicked.connect(on_ok)
        cancel_button.clicked.connect(on_cancel)
        
        if dialog.exec_() == QDialog.Accepted:
            return result[0], result[1], result[2], result[3]
        return None, None, None, None
    
    def _show_drag_overlay(self):
        """Afficher l'overlay de glisser/déposer"""
        if not self.drag_overlay_active:
            self.drag_overlay_active = True
            self.table.setStyleSheet(self.table.styleSheet() + """
                QTableWidget {
                    background-color: rgba(0, 123, 255, 0.1);
                    border: 2px dashed #007bff;
                }
                QTableWidget::item {
                    background-color: rgba(0, 123, 255, 0.05);
                }
            """)
            
            # Créer ou mettre à jour le label d'overlay
            if not hasattr(self, 'drag_overlay_label'):
                self.drag_overlay_label = QLabel("📁 Déposer votre fichier CSV/PDF ici", self.table)
                self.drag_overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.drag_overlay_label.setStyleSheet("""
                    QLabel {
                        background-color: rgba(0, 123, 255, 0.9);
                        color: white;
                        font-size: 18px;
                        font-weight: bold;
                        padding: 20px;
                        border-radius: 10px;
                        border: 2px solid #007bff;
                    }
                """)
            
            # Positionner le label au centre du tableau
            self.drag_overlay_label.resize(400, 100)
            table_center = self.table.rect().center()
            label_center = self.drag_overlay_label.rect().center()
            self.drag_overlay_label.move(table_center - label_center)
            self.drag_overlay_label.show()
    
    def _hide_drag_overlay(self):
        """Masquer l'overlay de glisser/déposer"""
        if self.drag_overlay_active:
            self.drag_overlay_active = False
            # Restaurer le style original du tableau
            self.table.setStyleSheet(self.table.styleSheet().replace("""
                QTableWidget {
                    background-color: rgba(0, 123, 255, 0.1);
                    border: 2px dashed #007bff;
                }
                QTableWidget::item {
                    background-color: rgba(0, 123, 255, 0.05);
                }
            """, ""))
            
            # Masquer le label d'overlay
            if hasattr(self, 'drag_overlay_label'):
                self.drag_overlay_label.hide()
    
    def _show_table_context_menu(self, position):
        """Afficher le menu contextuel du tableau"""
        # Vérifier qu'il y a des lignes sélectionnées
        selected_rows = list(set([item.row() for item in self.table.selectedItems()]))
        
        if not selected_rows:
            return
        
        # Créer le menu contextuel
        context_menu = QMenu(self)
        
        # Action pour supprimer les lignes
        delete_action = QAction("🗑️ Supprimer la/les ligne(s) sélectionnée(s)", self)
        delete_action.triggered.connect(lambda: self._delete_selected_rows(selected_rows))
        context_menu.addAction(delete_action)
        
        # Ajouter un séparateur
        context_menu.addSeparator()
        
        # Action pour copier les données
        copy_action = QAction("📋 Copier", self)
        copy_action.triggered.connect(self._handle_copy)
        context_menu.addAction(copy_action)
        
        # Afficher le menu
        context_menu.exec_(self.table.mapToGlobal(position))
    
    def _delete_selected_rows(self, selected_rows):
        """Supprimer les lignes sélectionnées"""
        if not selected_rows:
            return
        
        # Trier les lignes par ordre décroissant pour éviter les décalages d'index
        selected_rows.sort(reverse=True)
        
        # Confirmation
        from src.core.config import pluralize
        row_count = len(selected_rows)
        
        if row_count == 1:
            message = f"Supprimer la ligne sélectionnée ?"
        else:
            message = f"Supprimer les {row_count} lignes sélectionnées ?"
        
        message += "\n\nCette action est irréversible."
        
        reply = QMessageBox.question(
            self, "Confirmation de suppression",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            deleted_count = 0
            deleted_ids = []
            
            for row in selected_rows:
                # Récupérer l'ID de l'appareil
                db_id = self._get_db_id_from_row(row)
                if db_id:
                    # Supprimer de la base de données
                    success = self.db_manager.delete_appareil(db_id)
                    if success:
                        deleted_count += 1
                        deleted_ids.append(db_id)
                        
                        # Supprimer la ligne du tableau
                        self.table.removeRow(row)
            
            # Message de confirmation
            if deleted_count > 0:
                if deleted_count == 1:
                    message = f"1 ligne supprimée"
                else:
                    message = f"{deleted_count} lignes supprimées"
                
                self.statusbar.showMessage(message, Config.STATUS_MESSAGE_TIMEOUT)
                
                # Ajouter à l'historique
                self._add_to_history(f"🗑️ Suppression de {pluralize(deleted_count, 'ligne')}")
                
                # Actualiser l'affichage
                self._force_refresh_display()
            else:
                self._show_error("Aucune ligne n'a pu être supprimée")
                
        except Exception as e:
            self._show_error(f"Erreur lors de la suppression des lignes: {e}")

    def keyPressEvent(self, event):
        """Gestion des raccourcis clavier"""
        # Sur macOS, Qt mappe Cmd vers ControlModifier dans certains contextes
        # Nous testons les deux pour être sûr
        has_cmd_modifier = False
        if sys.platform == 'darwin':
            # Sur macOS, tester les deux possibilités
            has_cmd_modifier = bool(event.modifiers() & (Qt.MetaModifier | Qt.ControlModifier))
        else:
            # Sur Windows/Linux, utiliser ControlModifier
            has_cmd_modifier = bool(event.modifiers() & Qt.ControlModifier)
        
        if has_cmd_modifier:
            if event.key() == Qt.Key.Key_N:
                self._add_new_row()
            elif event.matches(QKeySequence.StandardKey.Save):
                self._manual_save()
            elif event.matches(QKeySequence.StandardKey.Find):
                self.search_input.setFocus()
                self.search_input.selectAll()
            elif event.matches(QKeySequence.StandardKey.Paste):
                self._handle_paste()
            elif event.matches(QKeySequence.StandardKey.Copy):
                self._handle_copy()
            elif event.matches(QKeySequence.StandardKey.Undo):
                self._undo()
            elif event.matches(QKeySequence.StandardKey.Redo):
                self._redo()
            elif event.key() == Qt.Key.Key_Z:
                self._undo()
            elif event.key() == Qt.Key.Key_Y:
                self._redo()
            elif event.key() == Qt.Key.Key_D:
                self._show_column_values_list()
            elif event.key() == Qt.Key.Key_Up:
                self._navigate_to_empty_cell(direction='up')
            elif event.key() == Qt.Key.Key_Down:
                self._navigate_to_empty_cell(direction='down')
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_F5:
            # Utiliser la recherche parsée actuelle
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term)
        elif event.key() == Qt.Key.Key_F12:
            self._open_log_viewer()
        elif event.key() == Qt.Key.Key_Escape:
            self._clear_search()
        else:
            super().keyPressEvent(event)

    def _add_new_row(self):
        """Ajouter une nouvelle ligne"""
        try:
            # Créer un dictionnaire vide pour les données
            empty_data = {header: '' for header in Config.DB_HEADERS}
            db_id = self.db_manager.insert_appareil(empty_data)
            
            # Recharger et se positionner sur la nouvelle ligne
            # Utiliser la recherche parsée actuelle
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term)
            
            if self.table.rowCount() > 0:
                self.table.setCurrentCell(0, 0)  # Première ligne (tri DESC)
                item = self.table.item(0, 0)
                if item:
                    self.table.editItem(item)
            
            # Ajouter à l'historique
            self._add_to_history(f"Nouvel appareil ajouté (ID: {db_id})")
            
            self.statusbar.showMessage(
                Config.get_message('new_row_added'), 
                Config.STATUS_MESSAGE_TIMEOUT
            )
            
        except DatabaseError as e:
            self._show_error(f"Erreur lors de l'ajout d'une nouvelle ligne: {e}")

    def _handle_paste(self):
        """Gestion du collage de données depuis le presse-papiers"""
        # Vider le cache des décisions de description au début de chaque import
        self._piece_description_decisions.clear()
        
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text.strip():
            QMessageBox.information(self, "Collage", "Aucune donnée dans le presse-papiers")
            return
        
        try:
            # Séparer les lignes et colonnes proprement
            lines = clipboard_text.strip().split('\n')
            rows = [line.split('\t') for line in lines]
            
            if not rows:
                return

            # Analyser les données pour déterminer le nombre de colonnes
            detected_columns = self._detect_paste_columns(clipboard_text)
            
            # Vérifier si on a au moins 1 colonne (modifié pour accepter 1 colonne)
            if detected_columns < 1:
                QMessageBox.warning(
                    self, 
                    "Format de données invalide", 
                    "❌ Format de collage invalide !\n\n"
                    "Le collage nécessite au minimum 1 colonne :\n"
                    "• 1 colonne : Référence modèle\n"
                    "• 2 colonnes : Référence modèle + Référence commerciale\n"
                    "• 3 colonnes : Référence modèle + Référence commerciale + Description/Autre\n\n"
                    f"Détecté : {detected_columns} colonne(s)\n\n"
                    "💡 Astuce : Copiez les données depuis un tableur (Excel, Calc, etc.) "
                    "pour conserver la séparation par tabulations."
                )
                return
            
            # Préparer les données d'exemple pour l'aperçu 
            sample_data = []
            try:
                for i in range(min(3, len(rows))):  # Maximum 3 lignes pour l'aperçu
                    if rows[i] and any(cell.strip() for cell in rows[i]):
                        sample_data.append(rows[i])
            except Exception as e:
                print(f"Erreur préparation aperçu COLLAGE: {e}")
                sample_data = []
            
            # Demander les options d'import avec la fenêtre unifiée et aperçu
            import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(detected_columns, None, "COLLAGE", sample_data)
            if import_type is None:
                return
                
            # Le collage n'utilise pas import_type mais on récupère les autres paramètres
            category = ""  # Pas de catégorie dans la fenêtre unifiée pour l'instant

            # Insérer les données
            inserted_count = 0
            updated_count = 0
            ignored_count = 0
            associations_created = 0  # Compter les vraies associations créées
            duplicates_skipped = 0   # Compter les associations déjà existantes
            manual_completion_count = 0  # Compter les appareils nécessitant complétion manuelle
            no_piece_ref_count = 0  # Compter les lignes sans référence de pièce
            descriptions_updated = 0  # Compter les mises à jour de libellés
            total_rows = len(rows)
            duplicates_list = []  # Liste des doublons pour intervention manuelle
            
            # Créer une barre de progression pour les gros imports (10K+ lignes)
            progress_dialog = None
            if total_rows >= 10000:
                progress_dialog = QProgressDialog(
                    f"Import en cours... 0 / {total_rows} lignes",
                    "Annuler",
                    0, total_rows,
                    self
                )
                progress_dialog.setWindowTitle("Import de données")
                progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                progress_dialog.show()
                QApplication.processEvents()  # Forcer l'affichage
            
            print(f"\n🔍 Début du traitement de {len(rows)} lignes d'import par collage")
            for row_idx, row_data in enumerate(rows):
                # Mettre à jour la barre de progression
                if progress_dialog:
                    if progress_dialog.wasCanceled():
                        break
                    
                    progress_dialog.setValue(row_idx)
                    progress_dialog.setLabelText(f"Import en cours... {row_idx + 1} / {total_rows} lignes")
                    
                    # Traiter les événements de l'interface toutes les 100 lignes
                    if row_idx % 100 == 0:
                        QApplication.processEvents()
                # Nettoyer les données de façon robuste
                clean_row = []
                for cell in row_data:
                    if cell:
                        # Supprimer les caractères de contrôle dangereux mais garder tout le reste
                        cleaned_cell = ''.join(char for char in cell if char not in ['\0', '\r', '\n', '\t']).strip()
                        clean_row.append(cleaned_cell)
                    else:
                        clean_row.append('')
                
                num_cols = len(clean_row)
                print(f"\n🔵 Ligne {row_idx + 1}: {num_cols} colonnes - {clean_row[:4]}{'...' if len(clean_row) > 4 else ''}")
                
                # Appliquer les règles de mapping selon le nombre de colonnes
                appareil_data = {}
                
                if num_cols >= 4:
                    # 4+ colonnes : insérer à partir de la colonne A (Type, Fabricant, Ref_Modele, Commercial_Ref, Other_Ref, etc.)
                    for i, header in enumerate(Config.DB_HEADERS):
                        if i < len(clean_row):
                            appareil_data[header] = clean_row[i]
                        else:
                            appareil_data[header] = ''
                            
                elif num_cols == 1:
                    # 1 colonne : mapper sur ref_modele uniquement
                    # Laisser tous les autres champs vides pour auto-completion
                    appareil_data['type'] = ''
                    appareil_data['manufacturer'] = ''
                    appareil_data['ref_modele'] = clean_row[0]
                    appareil_data['commercial_ref'] = ''
                    appareil_data['other_ref'] = ''
                    appareil_data['category'] = ''
                    appareil_data['notes'] = ''
                    
                elif num_cols == 2 or num_cols == 3:
                    # 2-3 colonnes : insérer à partir de la colonne C (Ref_Modele, Commercial_Ref, Other_Ref/Notes)
                    # Laisser Type et Fabricant vides pour auto-completion
                    appareil_data['type'] = ''  # Colonne A vide
                    appareil_data['manufacturer'] = ''  # Colonne B vide
                    
                    # Mapper à partir de la colonne C (ref_modele)
                    if num_cols == 2:
                        mapping_headers = ['ref_modele', 'commercial_ref']
                    else:  # num_cols == 3
                        if third_column_choice == "ignore":
                            mapping_headers = ['ref_modele', 'commercial_ref']
                        else:
                            mapping_headers = ['ref_modele', 'commercial_ref', third_column_choice]
                    
                    for i, value in enumerate(clean_row):
                        if i < len(mapping_headers):
                            appareil_data[mapping_headers[i]] = value
                    
                    # Compléter les autres champs
                    remaining_headers = ['other_ref', 'category', 'notes']
                    for header in remaining_headers:
                        if header not in appareil_data:
                            appareil_data[header] = ''
                            
                else:
                    # Nombre de colonnes non supporté
                    print(f"❌ REJET #{ignored_count + 1} - Ligne {row_idx + 1}: {num_cols} colonne(s) non supportée(s) (attendu: 1, 2-3 ou 4+)")
                    print(f"    Données: {clean_row}")
                    ignored_count += 1
                    continue
                
                # Ajouter la catégorie si sélectionnée (écrase la catégorie des données)
                if category:
                    appareil_data['category'] = category
                
                # Valider les données avec approche plus permissive
                validation_result = self.validator.validate_record(appareil_data)
                if not validation_result.is_valid:
                    # Log l'erreur mais continue l'import avec un avertissement
                    app_logger.warning(f"Données ligne {row_idx + 1} avec avertissement: {validation_result.error_message}")
                    print(f"⚠️ Ligne {row_idx + 1}: VALIDATION: {validation_result.error_message} - Continuant l'import...")
                    print(f"    Données concernées: {appareil_data}")
                    # Continue au lieu d'arrêter l'import
                
                # Chercher d'abord si l'appareil existe déjà
                existing_device = self._find_existing_device_by_refs(
                    appareil_data.get('ref_modele', ''), 
                    appareil_data.get('commercial_ref', ''),
                    appareil_data.get('type', ''),
                    appareil_data.get('manufacturer', '')
                )
                
                if existing_device:
                    # Appareil existant trouvé - mettre à jour les champs manquants
                    appareil_id = existing_device['id']
                    print(f"🔄 Ligne {row_idx + 1}: Appareil existant trouvé (ID: {appareil_id})")
                    
                    # Préparer les mises à jour nécessaires
                    updates = {}
                    for field in ['type', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref', 'category', 'notes']:
                        new_value = appareil_data.get(field, '').strip()
                        if new_value and not existing_device.get(field):
                            updates[field] = new_value
                    
                    # Appliquer les mises à jour
                    if updates:
                        self._update_device_info(appareil_id, updates)
                        print(f"  ⚙️ Mis à jour: {list(updates.keys())}")
                    
                    # Ajouter la pièce si spécifiée
                    if ref_piece and ref_piece.strip():
                        if not self._piece_already_associated(appareil_id, ref_piece.strip()):
                            _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), appareil_id, libelle_piece, self._confirm_piece_description_update)
                            associations_created += 1
                            if desc_updated:
                                descriptions_updated += 1
                            print(f"  🔗 Pièce {ref_piece.strip()} associée")
                        else:
                            # Pièce déjà associée, mais vérifier le libellé si fourni
                            if libelle_piece and libelle_piece.strip():
                                _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), appareil_id, libelle_piece, self._confirm_piece_description_update)
                                if desc_updated:
                                    descriptions_updated += 1
                                print(f"  📝 Libellé vérifié pour pièce {ref_piece.strip()} déjà associée")
                            duplicates_skipped += 1
                            # Enregistrer les détails du doublon
                            duplicates_list.append({
                                'ligne': row_idx + 1,
                                'appareil_id': appareil_id,
                                'ref_piece': ref_piece.strip(),
                                'appareil_data': {
                                    'ref_modele': existing_device.get('ref_modele', ''),
                                    'commercial_ref': existing_device.get('commercial_ref', ''),
                                    'type': existing_device.get('type', ''),
                                    'manufacturer': existing_device.get('manufacturer', '')
                                }
                            })
                            print(f"  ⚠️ Pièce {ref_piece.strip()} déjà associée")
                    else:
                        # Ligne sans référence de pièce - compter dans les associations manquantes
                        no_piece_ref_count += 1
                        print(f"  ⚠️ Ligne {row_idx + 1}: Appareil traité mais pas de référence de pièce")
                    
                    # Vérifier si l'appareil nécessite encore une complétion manuelle
                    # après mise à jour (seuls ceux sans type ET fabricant)
                    final_device_data = dict(existing_device)
                    final_device_data.update(updates)
                    if self._needs_manual_completion(final_device_data):
                        manual_completion_count += 1
                    
                    # Compter comme "mis à jour" seulement si les colonnes importantes (A et B) ont été modifiées
                    important_updates = [k for k in updates.keys() if k in ['type', 'manufacturer']]
                    if important_updates:
                        updated_count += 1
                    
                else:
                    # Nouvel appareil - utiliser la même logique que l'import CSV
                    # Créer avec seulement les références essentielles pour éviter les appareils vides
                    ref_modele = appareil_data.get('ref_modele', '').strip()
                    commercial_ref = appareil_data.get('commercial_ref', '').strip()
                    
                    # Vérifier qu'on a au moins une référence valide
                    if ref_modele or commercial_ref:
                        # Vérifier si l'appareil nécessite une complétion manuelle AVANT auto-complétion
                        needs_completion = self._needs_manual_completion(appareil_data)
                        
                        # Essayer d'abord l'auto-complétion avec les références
                        if not appareil_data.get('type') or not appareil_data.get('manufacturer'):
                            self._try_auto_complete(appareil_data)
                        
                        # Créer l'appareil avec les données disponibles (non vides seulement)
                        filtered_data = {}
                        for field, value in appareil_data.items():
                            if value and str(value).strip():  # Seulement les valeurs non vides
                                filtered_data[field] = value
                        
                        # S'assurer qu'on a au moins les références
                        if 'ref_modele' not in filtered_data and ref_modele:
                            filtered_data['ref_modele'] = ref_modele
                        if 'commercial_ref' not in filtered_data and commercial_ref:
                            filtered_data['commercial_ref'] = commercial_ref
                        
                        if filtered_data:  # Seulement si on a des données réelles
                            appareil_id = self.db_manager.insert_appareil(filtered_data)
                            inserted_count += 1
                            print(f"✨ Ligne {row_idx + 1}: Nouvel appareil créé (ID: {appareil_id})")
                            
                            # Vérifier si l'appareil nécessite une complétion manuelle
                            # après auto-complétion (seuls ceux sans type ET fabricant)
                            if self._needs_manual_completion(filtered_data):
                                manual_completion_count += 1
                            
                            # Ajouter la pièce si spécifiée
                            if ref_piece and ref_piece.strip():
                                _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), appareil_id, libelle_piece, self._confirm_piece_description_update)
                                associations_created += 1
                                if desc_updated:
                                    descriptions_updated += 1
                                print(f"  🔗 Pièce {ref_piece.strip()} associée")
                            else:
                                # Nouvel appareil sans référence de pièce - compter dans les associations manquantes
                                no_piece_ref_count += 1
                                print(f"  ⚠️ Ligne {row_idx + 1}: Nouvel appareil créé mais pas de référence de pièce")
                        else:
                            print(f"❌ REJET #{ignored_count + 1} - Ligne {row_idx + 1}: aucune donnée valide détectée après filtrage")
                            print(f"    Données filtrées vides: {appareil_data}")
                            ignored_count += 1
                    else:
                        print(f"❌ REJET #{ignored_count + 1} - Ligne {row_idx + 1}: aucune référence valide")
                        print(f"    ref_modele: '{ref_modele}', commercial_ref: '{commercial_ref}'")
                        print(f"    Données complètes: {appareil_data}")
                        ignored_count += 1
            
            # Fermer la barre de progression
            if progress_dialog:
                progress_dialog.setValue(total_rows)
                progress_dialog.close()
            
            # Forcer le rafraîchissement et afficher le résultat
            self._force_refresh_display(reset_page=True, clear_filters=True)
            
            # Résumé selon le format standardisé
            from src.core.config import pluralize
            detailed_summary = f"📊 Import Collage"
            if ref_piece and ref_piece.strip():
                detailed_summary += f" (pièce: {ref_piece})"
            detailed_summary += ":\n"
            detailed_summary += f"Lignes traitées : {total_rows - ignored_count}\n"
            detailed_summary += f"Appareils créés : {inserted_count}\n"
            # TOUJOURS afficher les sous-détails même si 0
            detailed_summary += f"  ==> Mis à jour : {updated_count}\n"
            detailed_summary += f"  ==> À compléter : {manual_completion_count}\n"
            detailed_summary += f"Associations créées : {associations_created}\n"
            # TOUJOURS afficher même si 0
            detailed_summary += f"Associations déjà existantes : {duplicates_skipped}"
            
            print(f"\n{detailed_summary}")
            
            
            # Afficher la synthèse comme pour l'import CSV
            results = {
                'total_imported': total_rows - ignored_count,
                'matches_found': updated_count,
                'manual_completion': manual_completion_count,
                'duplicates_skipped': duplicates_skipped,
                'new_entries': inserted_count,
                'associations_created': associations_created,
                'rejected_lines': ignored_count,
                'no_piece_ref': no_piece_ref_count,
                'descriptions_updated': descriptions_updated
            }
            
            # Utiliser la même méthode d'affichage que l'import CSV
            
            # Ajouter à l'historique avec le bon format
            self._log_import_to_history(results, ref_piece.strip() if ref_piece else None, "par collage")
            
            # Gérer les doublons s'il y en a
            if duplicates_list:
                # Ajouter aux résultats pour traitement unifié
                results['duplicates_list'] = duplicates_list
            
        except DatabaseError as e:
            self._show_error(f"Erreur lors du collage: {e}")
        except Exception as e:
            self._show_error(f"Erreur inattendue lors du collage: {e}")

    def _handle_copy(self):
        """Gestion de la copie des données sélectionnées"""
        selected = self.table.selectedRanges()
        if not selected:
            QMessageBox.information(self, "Copie", "Aucune cellule sélectionnée")
            return
        
        try:
            clipboard_data = []
            for r in range(selected[0].topRow(), selected[0].bottomRow() + 1):
                row_data = []
                for c in range(selected[0].leftColumn(), selected[0].rightColumn() + 1):
                    item = self.table.item(r, c)
                    row_data.append(item.text() if item else "")
                clipboard_data.append("\t".join(row_data))
            
            clipboard_string = "\n".join(clipboard_data)
            QApplication.clipboard().setText(clipboard_string)
            
            self.statusbar.showMessage(
                f"📋 Copié: {len(clipboard_data)} ligne(s)", 
                Config.STATUS_MESSAGE_TIMEOUT
            )
            
        except Exception as e:
            self._show_error(f"Erreur lors de la copie: {e}")

    def _needs_manual_completion(self, appareil_data: dict) -> bool:
        """Vérifier si un appareil a besoin d'une complétion manuelle (ni type ni fabricant)"""
        type_val = appareil_data.get('type') or ''
        manufacturer_val = appareil_data.get('manufacturer') or ''
        type_empty = not str(type_val).strip()
        manufacturer_empty = not str(manufacturer_val).strip()
        return type_empty and manufacturer_empty

    def _try_auto_complete(self, appareil_data: dict):
        """Essayer de compléter automatiquement Type et Fabricant à partir des références
        
        Returns:
            bool: True si l'auto-complétion a réussi, False sinon
        """
        original_data = appareil_data.copy()
        
        try:
            # Log du début de l'opération
            app_logger.debug(f"Début auto-complétion pour: {appareil_data}")
            
            # Vérifier d'abord si les champs sont vides
            type_empty = not appareil_data.get('type', '').strip()
            manufacturer_empty = not appareil_data.get('manufacturer', '').strip()
            
            # Si les deux champs sont remplis, pas besoin d'auto-complétion
            if not type_empty and not manufacturer_empty:
                app_logger.debug("Auto-complétion ignorée: type et manufacturer déjà remplis")
                return False
            
            # Ordre de priorité des références à vérifier (colonne C puis D)
            refs_to_check = []
            
            # 1. D'abord la référence modèle (colonne C)
            ref_modele = appareil_data.get('ref_modele', '').strip()
            if ref_modele:
                refs_to_check.append(ref_modele)
            
            # 2. Ensuite la référence commerciale (colonne D)
            commercial_ref = appareil_data.get('commercial_ref', '').strip()
            if commercial_ref:
                refs_to_check.append(commercial_ref)
            
            if not refs_to_check:
                app_logger.warning("Auto-complétion: aucune référence disponible pour la recherche")
                return False  # Aucune référence pour faire la recherche
            
            app_logger.debug(f"Références à vérifier: {refs_to_check}")
            
            # Chercher dans la base des appareils existants avec ces références
            total_matches = 0
            for ref in refs_to_check:
                query = """
                    SELECT type, manufacturer 
                    FROM appareils 
                    WHERE (ref_modele = ? OR commercial_ref = ?)
                    AND type IS NOT NULL AND type != '' 
                    AND manufacturer IS NOT NULL AND manufacturer != ''
                    LIMIT 1
                """
                
                app_logger.debug(f"Recherche avec référence: {ref}")
                self.db_manager.cursor.execute(query, (ref, ref))
                result = self.db_manager.cursor.fetchone()
                
                if result:
                    total_matches += 1
                    found_type, found_manufacturer = result
                    
                    app_logger.debug(f"Correspondance trouvée: Type='{found_type}', Fabricant='{found_manufacturer}'")
                    
                    # Compléter seulement les champs vides
                    if type_empty:
                        appareil_data['type'] = found_type
                        app_logger.info(f"Type complété: '' -> '{found_type}'")
                    
                    if manufacturer_empty:
                        appareil_data['manufacturer'] = found_manufacturer
                        app_logger.info(f"Fabricant complété: '' -> '{found_manufacturer}'")
                    
                    # Arrêter après la première correspondance trouvée
                    app_logger.debug("Auto-complétion terminée: correspondance trouvée")
                    break
                else:
                    app_logger.debug(f"Aucune correspondance pour la référence: {ref}")
            
            # Log final de l'opération
            app_logger.log_auto_complete(
                row_id=appareil_data.get('id', 'unknown'),
                original_data=original_data,
                completed_data=appareil_data,
                search_criteria={'references': refs_to_check},
                matches_found=total_matches,
                success=True
            )
            
            # Retourner True si au moins un champ a été complété avec succès
            return total_matches > 0
                        
        except Exception as e:
            # En cas d'erreur, continuer sans auto-completion
            app_logger.error(f"Erreur auto-completion: {e}")
            app_logger.log_auto_complete(
                row_id=appareil_data.get('id', 'unknown'),
                original_data=original_data,
                completed_data=appareil_data,
                search_criteria={'references': refs_to_check if 'refs_to_check' in locals() else []},
                matches_found=0,
                success=False,
                error_msg=str(e)
            )
            return False

    def _refresh_application(self):
        """Rafraîchir l'application"""
        # Utiliser la recherche parsée actuelle
        search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
        self.load_data(search_term)
        self.statusbar.showMessage("Application rafraîchie", Config.STATUS_MESSAGE_TIMEOUT)
    
    def _refresh_pieces_count_column(self):
        """Méthode désactivée - colonne Nb Pièces supprimée"""
        pass  # Ne fait plus rien

    def closeEvent(self, event):
        """Gestion de la fermeture"""
        # Sauvegarder les modifications en attente
        if self.modified_cells:
            reply = self._show_save_confirmation(
                "Modifications non sauvegardées", 
                "Des modifications ne sont pas sauvegardées. Les sauvegarder avant de quitter ?"
            )
            
            if reply == "cancel":
                event.ignore()
                return
            elif reply == "yes":
                self._auto_save()
        
        # Sauvegarder les paramètres
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        
        # Désinstaller l'eventFilter pour éviter les erreurs lors de la fermeture
        if hasattr(self, 'table') and self.table is not None:
            try:
                self.table.viewport().removeEventFilter(self)
            except (RuntimeError, AttributeError):
                pass  # L'objet est peut-être déjà détruit
        
        # Fermer la base de données
        if hasattr(self, 'db_manager'):
            self.db_manager.close()
        
        event.accept()

    # Méthodes pour les fonctionnalités SEO
    def _generate_meta_title(self):
        """Générer et copier un méta titre SEO optimisé"""
        try:
            # Gérer les recherches multi-références
            multi_terms = self._get_multi_reference_terms()
            if multi_terms:
                # Demander à l'utilisateur de choisir la référence pour la génération SEO
                selected_reference = self._show_reference_selection_dialog(
                    "Référence pour Méta Title",
                    f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                    f"Choisissez la référence à utiliser pour la génération SEO :",
                    multi_terms[0]  # Premier terme par défaut
                )
                
                if not selected_reference:
                    return  # Annulé par l'utilisateur
                
                # Pas de validation - l'utilisateur peut saisir une référence non présente en BDD
                
                # Récupérer les données pour la référence sélectionnée
                search_data = self._get_current_search_data_for_reference(selected_reference)
            else:
                # Récupérer les données de recherche actuelles (comportement normal)
                search_data = self._get_current_search_data()
            
            if not search_data:
                self.statusbar.showMessage("Aucune recherche active pour générer le méta titre", 3000)
                return
            
            # Générer le méta titre
            result = self.seo_generator.generate_meta_title(
                reference=search_data['reference'],
                description=search_data['description'], 
                type_appareil=search_data['type_appareil'],
                fabricants=search_data['fabricants']
            )
            
            # Copier dans le presse-papiers
            QApplication.clipboard().setText(result['title'])
            
            # Message de statut avec informations détaillées
            length = result['length']
            color = "green" if length <= 60 else "red"
            fabricants_info = f"({result['info']['fabricants_count']} fabricants)" if result['info']['fabricants_count'] > 0 else ""
            
            status_msg = f"Méta titre copié ({length}/60 caractères) {fabricants_info}"
            if result['info']['truncated']:
                status_msg += " [Tronqué]"
            
            self.statusbar.showMessage(status_msg, 5000)
            
        except Exception as e:
            self.statusbar.showMessage(f"Erreur génération méta titre: {e}", 3000)
            app_logger.error(f"Erreur génération méta titre: {e}")
    
    def _generate_meta_description(self):
        """Générer et copier une méta description SEO aléatoire"""
        try:
            # Gérer les recherches multi-références
            multi_terms = self._get_multi_reference_terms()
            if multi_terms:
                # Demander à l'utilisateur de choisir la référence pour la génération SEO
                selected_reference = self._show_reference_selection_dialog(
                    "Référence pour Méta Description",
                    f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                    f"Choisissez la référence à utiliser pour la génération SEO :",
                    multi_terms[0]  # Premier terme par défaut
                )
                
                if not selected_reference:
                    return  # Annulé par l'utilisateur
                
                # Pas de validation - l'utilisateur peut saisir une référence non présente en BDD
                
                # Récupérer les données pour la référence sélectionnée
                search_data = self._get_current_search_data_for_reference(selected_reference)
            else:
                # Récupérer les données de recherche actuelles (comportement normal)
                search_data = self._get_current_search_data()
            
            if not search_data:
                self.statusbar.showMessage("Aucune recherche active pour générer la méta description", 3000)
                return
            
            # Générer la méta description
            result = self.seo_generator.generate_meta_description(
                reference=search_data['reference'],
                description=search_data['description'],
                type_appareil=search_data['type_appareil'],
                fabricants=search_data['fabricants']
            )
            
            # Copier dans le presse-papiers
            QApplication.clipboard().setText(result['description'])
            
            # Message de statut avec informations détaillées
            length = result['length']
            status_msg = f"Méta description copiée ({length}/150 caractères)"
            if result['info']['truncated']:
                status_msg += " [Tronquée]"
            
            self.statusbar.showMessage(status_msg, 5000)
            
        except Exception as e:
            self.statusbar.showMessage(f"Erreur génération méta description: {e}", 3000)
            app_logger.error(f"Erreur génération méta description: {e}")
    
    def _get_current_search_data(self) -> Optional[Dict[str, any]]:
        """Extraire les données de la recherche actuelle pour la génération SEO"""
        try:
            # Récupérer le terme de recherche actuel
            search_term = self.search_input.text().strip()
            if not search_term:
                return None
            
            # Pour les recherches multi-références, utiliser le premier terme
            if '||' in search_term:
                terms = [term.strip() for term in search_term.split('||')]
                if terms:
                    search_term = terms[0]
            
            # Vérifier si c'est une référence de pièce (recherche dans la table pieces)
            piece_description = self._get_piece_description_from_reference(search_term)
            if not piece_description:
                return None  # Ne pas activer les boutons SEO si ce n'est pas une référence de pièce
            
            # Analyser les données du tableau pour extraire les informations des appareils
            if self.table.rowCount() == 0:
                return None
            
            # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
            # (Pas seulement ceux visibles dans le tableau)
            types_appareil = set()
            fabricants = set()
            
            # Requête pour récupérer tous les fabricants et types d'appareils pour cette pièce
            fabricants_query = "SELECT DISTINCT a.type, a.manufacturer FROM appareils a JOIN piece_associations pa ON a.id = pa.appareil_id JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece = ? AND a.type IS NOT NULL AND a.type != '' AND a.manufacturer IS NOT NULL AND a.manufacturer != ''"
            
            try:
                all_data = self.db_manager.execute_custom_query(fabricants_query, [search_term])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil.add(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        fabricants.add(manufacturer.strip())
                        
            except Exception as e:
                app_logger.error(f"Erreur récupération fabricants pour {search_term}: {e}")
                
                # Fallback: utiliser les données visibles du tableau si la requête échoue
                for row in range(min(self.table.rowCount(), 20)):
                    if not self.table.isRowHidden(row):
                        # Type appareil (colonne 0)
                        type_item = self.table.item(row, 0)
                        if type_item and type_item.text().strip():
                            types_appareil.add(type_item.text().strip())
                        
                        # Fabricant (colonne 1)
                        fabricant_item = self.table.item(row, 1)
                        if fabricant_item and fabricant_item.text().strip():
                            fabricants.add(fabricant_item.text().strip())
            
            # Utiliser la référence de recherche et la vraie description de la pièce
            reference = search_term
            description = piece_description
            
            # Prendre le type le plus fréquent ou le premier
            type_appareil = list(types_appareil)[0] if types_appareil else "appareil électroménager"
            
            # Convertir les sets en listes
            fabricants_list = sorted(list(fabricants)) if fabricants else ["multi-marques"]
            
            return {
                'reference': reference,
                'description': description,
                'type_appareil': type_appareil,
                'fabricants': fabricants_list
            }
            
        except Exception as e:
            app_logger.error(f"Erreur extraction données recherche: {e}")
            return None
    
    def _get_current_search_data_for_reference(self, specific_reference: str) -> Optional[Dict[str, any]]:
        """
        Extraire les données pour une référence spécifique (utilisé pour les multi-références)
        """
        try:
            # Récupérer le terme de recherche original
            original_search_term = self.search_input.text().strip()
            
            # Si c'est une recherche multi-références, utiliser les données d'une référence existante
            if '||' in original_search_term or '&&' in original_search_term:
                # Diviser selon l'opérateur utilisé
                if '||' in original_search_term:
                    references = [ref.strip() for ref in original_search_term.split('||') if ref.strip()]
                else:  # && présent
                    references = [ref.strip() for ref in original_search_term.split('&&') if ref.strip()]
                    
                app_logger.info(f"Génération méta pour multi-références: {references}")
                
                # Essayer de trouver une référence qui existe en BDD pour récupérer les vraies données
                real_reference_data = None
                for ref in references:
                    piece_description = self._get_piece_description_from_reference(ref)
                    if piece_description:
                        app_logger.info(f"Utilisation des données de la référence existante: {ref}")
                        real_reference_data = self._get_search_data_for_existing_reference(ref, piece_description)
                        break
                
                if real_reference_data:
                    # Utiliser les vraies données mais avec la référence personnalisée
                    real_reference_data['reference'] = specific_reference
                    return real_reference_data
                else:
                    app_logger.warning("Aucune référence valide trouvée dans la recherche multi-références")
            
            # Vérifier si c'est une référence de pièce valide (cas normal)
            piece_description = self._get_piece_description_from_reference(specific_reference)
            
            # Si la référence n'existe pas en BDD, créer des données par défaut
            if not piece_description:
                return {
                    'reference': specific_reference,
                    'description': f"Pièce détachée {specific_reference}",
                    'type_appareil': "appareil électroménager", 
                    'fabricants': ["multi-marques"]
                }
            
            # Analyser les données du tableau pour extraire les informations des appareils
            if self.table.rowCount() == 0:
                return None
            
            # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
            types_appareil = set()
            fabricants = set()
            
            # Requête pour récupérer tous les fabricants et types d'appareils pour cette pièce
            fabricants_query = "SELECT DISTINCT a.type, a.manufacturer FROM appareils a JOIN piece_associations pa ON a.id = pa.appareil_id JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece = ? AND a.type IS NOT NULL AND a.type != '' AND a.manufacturer IS NOT NULL AND a.manufacturer != ''"
            
            try:
                all_data = self.db_manager.execute_custom_query(fabricants_query, [specific_reference])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil.add(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        fabricants.add(manufacturer.strip())
                        
            except Exception as e:
                app_logger.error(f"Erreur récupération fabricants pour {specific_reference}: {e}")
                
                # Fallback: utiliser les données visibles du tableau si la requête échoue
                for row in range(min(self.table.rowCount(), 20)):
                    if not self.table.isRowHidden(row):
                        # Type appareil (colonne 0)
                        type_item = self.table.item(row, 0)
                        if type_item and type_item.text().strip():
                            types_appareil.add(type_item.text().strip())
                        
                        # Fabricant (colonne 1)
                        fabricant_item = self.table.item(row, 1)
                        if fabricant_item and fabricant_item.text().strip():
                            fabricants.add(fabricant_item.text().strip())
            
            # Prendre le type le plus fréquent ou le premier
            type_appareil = list(types_appareil)[0] if types_appareil else "appareil électroménager"
            
            # Convertir les sets en listes
            fabricants_list = sorted(list(fabricants)) if fabricants else ["multi-marques"]
            
            return {
                'reference': specific_reference,
                'description': piece_description,
                'type_appareil': type_appareil,
                'fabricants': fabricants_list
            }
            
        except Exception as e:
            app_logger.error(f"Erreur récupération données référence spécifique: {e}")
            return None
    
    def _get_search_data_for_existing_reference(self, reference: str, piece_description: str) -> Dict[str, any]:
        """
        Récupérer les vraies données SEO pour une référence existante en BDD
        """
        try:
            # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
            types_appareil = set()
            fabricants = set()
            
            # Requête pour récupérer tous les fabricants et types d'appareils pour cette pièce
            fabricants_query = "SELECT DISTINCT a.type, a.manufacturer FROM appareils a JOIN piece_associations pa ON a.id = pa.appareil_id JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece = ? AND a.type IS NOT NULL AND a.type != '' AND a.manufacturer IS NOT NULL AND a.manufacturer != ''"
            
            try:
                all_data = self.db_manager.execute_custom_query(fabricants_query, [reference])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil.add(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        fabricants.add(manufacturer.strip())
                        
            except Exception as e:
                app_logger.error(f"Erreur récupération fabricants pour {reference}: {e}")
                # Fallback minimal
                types_appareil.add("appareil électroménager")
                fabricants.add("multi-marques")
            
            # Prendre le type le plus fréquent ou le premier
            type_appareil = list(types_appareil)[0] if types_appareil else "appareil électroménager"
            
            # Convertir les sets en listes
            fabricants_list = sorted(list(fabricants)) if fabricants else ["multi-marques"]
            
            return {
                'reference': reference,  # Sera remplacé par la référence personnalisée plus tard
                'description': piece_description,
                'type_appareil': type_appareil,
                'fabricants': fabricants_list
            }
            
        except Exception as e:
            app_logger.error(f"Erreur récupération données SEO pour {reference}: {e}")
            return {
                'reference': reference,
                'description': f"Pièce détachée {reference}",
                'type_appareil': "appareil électroménager", 
                'fabricants': ["multi-marques"]
            }
    
    def _get_displayed_table_data(self) -> List[Tuple]:
        """Récupérer les données actuellement affichées dans le tableau"""
        data = []
        
        if not hasattr(self, 'table') or self.table.rowCount() == 0:
            return data
        
        # Parcourir chaque ligne du tableau
        for row in range(self.table.rowCount()):
            row_data = []
            # Récupérer les données de chaque colonne (sauf la dernière "Nb Pièces")
            for col in range(len(Config.DB_HEADERS)):  # Exclure colonne "Nb Pièces"
                item = self.table.item(row, col)
                if item:
                    row_data.append(item.text())
                else:
                    row_data.append("")
            
            # Récupérer le db_id depuis UserRole de la première cellule
            first_item = self.table.item(row, 0)
            if first_item:
                db_id = first_item.data(Qt.ItemDataRole.UserRole)
                if db_id:
                    # Ajouter l'ID en première position (comme dans les requêtes DB)
                    row_data.insert(0, db_id)
                    data.append(tuple(row_data))
        
        return data

    def _get_all_search_data(self) -> List[Tuple]:
        """Récupérer TOUTES les données correspondant à la recherche actuelle (sans pagination)"""
        try:
            # Récupérer les paramètres de recherche actuels depuis le champ de saisie
            current_search = self.search_input.text().strip() if hasattr(self, 'search_input') else ''
            
            incomplete_filter = getattr(self, 'show_incomplete_only', False)
            
            if not current_search:
                return []
            
            # Parser la recherche comme dans _parse_advanced_search
            try:
                parsed_search = self._parse_advanced_search(current_search)
            except Exception as parse_error:
                # En cas d'erreur de parsing, utiliser une recherche simple
                parsed_search = {'SIMPLE': current_search}
            
            if not parsed_search:
                return []
            
            # Obtenir les filtres de colonnes (si applicable)
            column_filters = {}
            if hasattr(self, 'filter_widgets'):
                for col_idx, filter_widget in self.filter_widgets.items():
                    if filter_widget is not None:  # Skip removed filters
                        if isinstance(filter_widget, QComboBox):
                            filter_text = filter_widget.currentText().strip()
                        else:  # QLineEdit
                            filter_text = filter_widget.text().strip()
                        if filter_text:
                            column_filters[col_idx] = filter_text
            
            # Utiliser load_data sans limites
            all_results = self.db_manager.load_data(
                search_term=parsed_search,
                column_filters=column_filters,
                limit=None,  # Aucune limite = récupérer tout
                offset=None,  # Pas d'offset = depuis le début
                sort_column=None,  # Pas de tri spécifique
                sort_order="ASC",  # Ordre croissant par défaut
                incomplete_filter=incomplete_filter
            )
            
            return all_results if all_results else []
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return []

    def _export_displayed_table_as_csv(self, custom_reference: str) -> str:
        """Exporter TOUTES les données de la recherche vers un fichier CSV (pas seulement celles affichées)"""
        try:
            import csv
            import os
            from datetime import datetime
            
            # Récupérer TOUTES les données de la recherche actuelle, pas seulement celles affichées
            data = self._get_all_search_data()
            
            if not data:
                raise Exception("Aucune donnée trouvée pour la recherche actuelle")
            
            # Générer le nom de fichier
            filename = f"{custom_reference}_everyParts.csv"
            filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)
            
            # Créer le fichier CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                # En-têtes
                headers = [
                    'product',
                    'type', 
                    'manufacturer',
                    'modele_name',
                    'reference_modele',
                    'commercial_reference'
                ]
                writer.writerow(headers)
                
                # Écrire les données
                processed_count = 0
                for record in data:
                    try:
                        if len(record) >= 5:  # Au minimum 5 champs requis
                            db_id, type_app, manufacturer, ref_modele, commercial_ref = record[:5]
                            modele_complet = f"{ref_modele or ''} - {commercial_ref or ''}".strip(' -')
                            
                            writer.writerow([
                                custom_reference,  # product (référence personnalisée)
                                type_app or '',
                                manufacturer or '',
                                modele_complet,
                                ref_modele or '',
                                commercial_ref or ''
                            ])
                            processed_count += 1
                    except Exception as record_error:
                        print(f"📊 ERREUR sur l'enregistrement {processed_count}: {record_error}")
                        print(f"📊 Record problématique: {record}")
                        continue
            return filepath
            
        except Exception as e:
            raise Exception(f"Erreur lors de l'export CSV: {e}")

    def _export_custom_reference_csv_with_current_data(self, custom_reference: str, original_search_term: str = None) -> str:
        """Créer un export CSV avec toutes les données de la recherche mais avec une référence personnalisée"""
        try:
            import csv
            import os
            from datetime import datetime
            
            # Générer un nom de fichier simplifié
            filename = f"{custom_reference}_everyParts.csv"
            filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)
            
            # Utiliser les données actuellement affichées dans le tableau
            # au lieu de refaire une requête en base de données
            data = self._get_displayed_table_data()
            
            if not data:
                raise Exception("Aucune donnée affichée dans le tableau à exporter")
            
            # Plus besoin de récupérer les filtres - on utilise directement les données affichées
            
            # Récupérer le filtre des lignes incomplètes si activé
            incomplete_filter = getattr(self, 'show_incomplete_only', False)
            
            # Vérifier que le db_manager existe
            if not hasattr(self, 'db_manager') or self.db_manager is None:
                raise Exception("Database manager non disponible")
            
            # Vérifier si c'est une recherche multi-références
            if '||' in original_search_term or '&&' in original_search_term:
                # Diviser les références selon l'opérateur utilisé
                if '||' in original_search_term:
                    references = [ref.strip() for ref in original_search_term.split('||') if ref.strip()]
                    # Opérateur OR: union de tous les résultats (sans doublons)
                    all_data = []
                    seen_records = set()
                    
                    for ref in references:
                        ref_data = self.db_manager.get_export_data(ref, column_filters, incomplete_filter)
                        if ref_data:
                            for record in ref_data:
                                # Créer une clé unique pour chaque appareil (sans la référence de pièce)
                                record_key = (record[0], record[1], record[2], record[3], record[4])  # type, manufacturer, ref_modele, commercial_ref, other_ref
                                if record_key not in seen_records:
                                    seen_records.add(record_key)
                                    all_data.append(record)
                    
                    data = all_data
                else:  # && présent
                    references = [ref.strip() for ref in original_search_term.split('&&') if ref.strip()]
                    # Opérateur AND: intersection - appareils qui contiennent TOUTES les pièces
                    if references:
                        # Commencer avec les données de la première référence
                        first_ref = references[0]
                        data = self.db_manager.get_export_data(first_ref, column_filters, incomplete_filter)
                        
                        # Pour chaque référence suivante, garder seulement les appareils qui la contiennent aussi
                        for ref in references[1:]:
                            ref_data = self.db_manager.get_export_data(ref, column_filters, incomplete_filter)
                            if ref_data:
                                # Créer un set des IDs d'appareils de cette référence
                                ref_appareil_ids = set()
                                for record in ref_data:
                                    # Construire un identifiant unique pour chaque appareil
                                    appareil_id = (record[0], record[1], record[2], record[3])  # type, manufacturer, ref_modele, commercial_ref
                                    ref_appareil_ids.add(appareil_id)
                                
                                # Filtrer data pour garder seulement les appareils présents dans ref_data
                                data = [record for record in data 
                                       if (record[0], record[1], record[2], record[3]) in ref_appareil_ids]
                            else:
                                # Si une référence n'a pas de données, l'intersection est vide
                                data = []
                                break
                    else:
                        data = []
            else:
                # Recherche simple
                data = self.db_manager.get_export_data(original_search_term, column_filters, incomplete_filter)
            
            if not data:
                raise Exception(f"Aucune donnée trouvée pour la recherche: {original_search_term}")
            
            # Créer le fichier CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                # En-têtes
                headers = [
                    'product',
                    'type', 
                    'manufacturer',
                    'modele_name',
                    'reference_modele',
                    'commercial_reference'
                ]
                writer.writerow(headers)
                
                # Écrire les données en remplaçant la référence par la référence personnalisée
                for record in data:
                    type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record
                    modele_complet = f"{ref_modele or ''} - {commercial_ref or ''}".strip(' -')
                    
                    writer.writerow([
                        custom_reference,  # product (référence personnalisée au lieu de ref_piece)
                        type_app or '',
                        manufacturer or '',
                        modele_complet,
                        ref_modele or '',
                        commercial_ref or ''
                    ])
            
            return f"Fichier CSV créé: {filepath}"
            
        except Exception as e:
            app_logger.error(f"Erreur export CSV personnalisé: {e}")
            raise Exception(f"Erreur lors de l'export CSV personnalisé: {e}")
    
    def _create_minimal_csv_fallback(self, custom_reference: str) -> str:
        """Créer un CSV minimal en cas d'erreur avec l'export personnalisé"""
        try:
            import csv
            import os
            from datetime import datetime
            
            filename = f"{custom_reference}_everyParts.csv"
            filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                headers = ['product', 'type', 'manufacturer', 'modele_name', 'reference_modele', 'commercial_reference']
                writer.writerow(headers)
                
                # Une seule ligne avec la référence personnalisée
                writer.writerow([
                    custom_reference,
                    'appareil électroménager',
                    'multi-marques',
                    f'Modèle compatible {custom_reference}',
                    custom_reference,
                    custom_reference
                ])
            
            return f"Fichier CSV de secours créé: {filepath}"
            
        except Exception as e:
            raise Exception(f"Erreur création CSV fallback: {e}")
    
    def _get_piece_description_from_reference(self, reference: str) -> Optional[str]:
        """Récupérer la description d'une pièce depuis sa référence"""
        try:
            # Rechercher la pièce par référence exacte
            query = "SELECT description FROM pieces WHERE ref_piece = ? LIMIT 1"
            result = self.db_manager.execute_custom_query(query, [reference])
            
            if result:
                description = result[0][0]
                # Vérifier que la description n'est pas None ou vide
                if description and description.strip():
                    return description.strip()
                else:
                    # Si la description est vide, utiliser une description générique
                    return "pièce détachée"
            
            # Essayer une recherche partielle si la recherche exacte échoue
            query_partial = "SELECT description FROM pieces WHERE ref_piece LIKE ? LIMIT 1"
            result_partial = self.db_manager.execute_custom_query(query_partial, [f"%{reference}%"])
            
            if result_partial:
                description = result_partial[0][0]
                if description and description.strip():
                    return description.strip()
                else:
                    return "pièce détachée"
            
            return None  # Aucune pièce trouvée
            
        except Exception as e:
            app_logger.error(f"Erreur récupération description pièce: {e}")
            return None
    
    def _is_piece_reference_search(self) -> bool:
        """
        Vérifier si la recherche actuelle correspond à une référence de pièce
        Supporte maintenant les recherches multi-références avec || et &&
        """
        search_term = self.search_input.text().strip()
        if not search_term:
            return False
        
        # Détecter les recherches multi-références avec || ou &&
        if '||' in search_term or '&&' in search_term:
            return self._are_all_terms_piece_references(search_term)
        
        # Recherche simple (comportement existant)
        return self._get_piece_description_from_reference(search_term) is not None
    
    def _are_all_terms_piece_references(self, search_term: str) -> bool:
        """
        Vérifier que tous les termes d'une recherche multi-références sont valides
        Format attendu: "REF001 || REF002 || REF003" ou "REF001 && REF002 && REF003"
        """
        # Diviser par || ou && et nettoyer les espaces
        if '||' in search_term:
            terms = [term.strip() for term in search_term.split('||')]
        elif '&&' in search_term:
            terms = [term.strip() for term in search_term.split('&&')]
        else:
            return False  # Pas d'opérateur multi-références
        
        # Vérifier que tous les termes sont des références valides
        for term in terms:
            if not term:  # Terme vide
                return False
            if self._get_piece_description_from_reference(term) is None:
                return False
        
        return len(terms) > 1  # Au moins 2 références pour être considéré comme multi-référence
    
    def _get_multi_reference_terms(self) -> Optional[List[str]]:
        """
        Extraire les termes d'une recherche multi-références
        Retourne None si ce n'est pas une recherche multi-références valide
        Support des opérateurs || et &&
        """
        search_term = self.search_input.text().strip()
        if not search_term:
            return None
        
        # Vérifier la présence des opérateurs || ou &&
        if '||' not in search_term and '&&' not in search_term:
            return None
            
        if not self._are_all_terms_piece_references(search_term):
            return None
        
        # Diviser selon l'opérateur présent
        if '||' in search_term:
            return [term.strip() for term in search_term.split('||')]
        else:  # && est présent
            return [term.strip() for term in search_term.split('&&')]
    
    def _show_reference_selection_dialog(self, title: str, message: str, default_reference: str) -> Optional[str]:
        """
        Afficher une fenêtre de sélection de référence pour les exports multi-références
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.resize(450, 200)  # Augmenter la hauteur pour améliorer la lisibilité
        
        layout = QVBoxLayout()
        
        # Message d'explication
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Champ de saisie avec la référence par défaut
        self.reference_input = QLineEdit(default_reference)
        self.reference_input.selectAll()  # Sélectionner tout le texte
        layout.addWidget(self.reference_input)
        
        # Boutons
        button_layout = QHBoxLayout()
        
        confirm_btn = QPushButton("Confirmer")
        confirm_btn.clicked.connect(dialog.accept)
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet("""
            QPushButton { 
                background-color: #28a745; 
                color: white; 
                font-weight: bold; 
                padding: 8px 16px; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #218838; 
            }
        """)
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setStyleSheet("""
            QPushButton { 
                background-color: #6c757d; 
                color: white; 
                font-weight: bold; 
                padding: 8px 16px; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #5a6268; 
            }
        """)
        
        button_layout.addWidget(confirm_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Afficher et récupérer le résultat
        if dialog.exec_() == QDialog.Accepted:
            selected_reference = self.reference_input.text().strip()
            if selected_reference:
                return selected_reference
        
        return None


def main():
    """Point d'entrée de l'application"""
    app = QApplication(sys.argv)
    
    # Supprimer les warnings macOS inutiles
    app.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    app.setQuitOnLastWindowClosed(True)
    
    try:
        window = MainWindow()
        # Appliquer les styles CSS globalement pour toutes les fenêtres
        app.setStyleSheet(window._get_modern_style())
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        QMessageBox.critical(None, "Erreur critique", f"Impossible de démarrer l'application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()