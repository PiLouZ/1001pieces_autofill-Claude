"""
Application de gestion d'appareils - Version refactorisée
Architecture modulaire avec séparation des responsabilités
"""

import sys
import platform
from typing import Optional, Dict, Any, List
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

# Imports des modules refactorisés
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config
from src.core.logger import app_logger
from src.data.database_manager import DatabaseManager, DatabaseError
from src.data.data_validator import DataValidator, ValidationResult
from src.data.data_exporter import DataExporter, ExportFormat, ExportError
from src.ui.log_viewer import LogViewer
from src.ui.validation_window import ValidationWindow


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
            self._show_completion_popup()
            return
        
        # Appeler la méthode parent pour les autres touches
        super().keyPressEvent(event)
    
    def _show_completion_popup(self):
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
        search_input.setText(current_item.text())  # Préremplir avec la valeur actuelle
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
        self.setToolTip("Tirer pour recopier la valeur de la cellule")
        self.dragging = False
        self.start_pos = None
        self.orig_selection = None
        self.drag_direction = None
        self.history_pending = False
        
        # Variables pour le défilement automatique
        self.auto_scroll_timer = None
        self.auto_scroll_direction = None
        self.auto_scroll_zone = 50  # pixels depuis le bord pour déclencher le défilement

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

    def _create_table_widget(self) -> QWidget:
        """Créer le widget du tableau"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Filtres par colonne
        filter_layout = QHBoxLayout()
        for i, header in enumerate(Config.UI_HEADERS):
            filter_input = QLineEdit()
            filter_input.setPlaceholderText(f"{header}...")
            filter_input.textChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
            self.filter_widgets[i] = filter_input
            filter_layout.addWidget(filter_input)
        layout.addLayout(filter_layout)
        
        # Sauvegarder la référence du layout des filtres pour la visibilité
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
                font-family: monospace;
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
        export_layout = QHBoxLayout()
        
        self.export_csv_btn = QPushButton("Exporter CSV")
        self.export_csv_btn.clicked.connect(lambda: self._export_data(ExportFormat.CSV))
        self.export_csv_btn.setEnabled(False)
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
        self.page_size_combo.addItems(["500", "1000", "2000", "5000", "Tout"])
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
        import_action.triggered.connect(self._import_csv)
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
                filter_text = filter_widget.text().strip()
                if filter_text:
                    column_filters[col_idx] = filter_text
            
            # Ajouter le filtre des lignes incomplètes si activé
            incomplete_filter = getattr(self, 'show_incomplete_only', False)
            
            # Préparer les paramètres de tri
            sort_column = self.current_sort_column if hasattr(self, 'current_sort_column') and self.current_sort_column >= 0 else None
            sort_order = "ASC" if hasattr(self, 'current_sort_order') and self.current_sort_order == Qt.SortOrder.AscendingOrder else "DESC"
            
            # Compter le total de lignes
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
            
            # Déterminer si utiliser la pagination
            if self.use_pagination and self.total_rows > Config.MAX_DISPLAY_ROWS:
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
            
            # Remplir le tableau
            self.table.setRowCount(len(records))
            
            self._update_progress_with_debounce(progress_dialog, 60, "Remplissage du tableau...")
            
            for row_idx, record in enumerate(records):
                # Mise à jour de la progression pour les gros volumes (moins fréquente)
                if progress_dialog and row_idx % 5000 == 0:  # Réduire la fréquence des mises à jour
                    if progress_dialog.wasCanceled():
                        break
                    progress_value = 60 + (row_idx / len(records)) * 35  # 60% -> 95%
                    self._update_progress_with_debounce(progress_dialog, int(progress_value), 
                                                       f"Remplissage du tableau... {row_idx}/{len(records)} lignes")
                db_id = record[0]
                # Ne plus utiliser les en-têtes verticaux pour stocker db_id
                self.table.setVerticalHeaderItem(row_idx, QTableWidgetItem(str(row_idx + 1)))
                
                # Traiter toutes les colonnes UI (8 colonnes maintenant, AVEC Nb Pièces)
                for col_idx in range(len(Config.UI_HEADERS)):
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
                    
                    # Mise en évidence des résultats de recherche (sauf pour la colonne Nb Pièces)
                    if search_term and col_idx < len(Config.DB_HEADERS):
                        # Gérer les différents types de search_term
                        if isinstance(search_term, str):
                            # Recherche simple (chaîne)
                            if search_term.lower() in str(item.text()).lower():
                                item.setBackground(QColor(*Config.SEARCH_HIGHLIGHT_COLOR))
                        elif isinstance(search_term, dict):
                            # Recherche parsée (dictionnaire)
                            should_highlight = False
                            item_text = str(item.text()).lower()
                            
                            if search_term.get('type') == 'simple':
                                # Recherche simple parsée
                                terms = search_term.get('terms', [])
                                if terms and terms[0].lower() in item_text:
                                    should_highlight = True
                            elif search_term.get('type') == 'regex':
                                # Recherche par expression régulière
                                try:
                                    import re
                                    pattern = search_term.get('pattern', '')
                                    if re.search(pattern, item_text, re.IGNORECASE):
                                        should_highlight = True
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
                    
                    self.table.setItem(row_idx, col_idx, item)
            
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
            # Mettre à jour l'indicateur visuel de tri
            self.table.horizontalHeader().setSortIndicator(
                self.current_sort_column, 
                self.current_sort_order
            )
            
            # Recharger les données avec le nouveau tri
            # Utiliser la recherche parsée actuelle
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.load_data(search_term)
            
        except Exception as e:
            app_logger.error(f"Erreur lors de l'application du tri: {e}")
    
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
        """Naviguer vers la prochaine cellule vide dans la colonne actuelle"""
        try:
            current_item = self.table.currentItem()
            if not current_item:
                return
                
            current_row = self.table.currentRow()
            current_col = self.table.currentColumn()
            
            # Rechercher dans la direction spécifiée
            if direction == 'down':
                # Chercher vers le bas
                for row in range(current_row + 1, self.table.rowCount()):
                    item = self.table.item(row, current_col)
                    if not item or not item.text().strip():
                        self.table.setCurrentCell(row, current_col)
                        self.table.editItem(self.table.item(row, current_col) or QTableWidgetItem(""))
                        return
                        
                # Si aucune cellule vide trouvée, aller à la fin
                last_row = self.table.rowCount() - 1
                if last_row >= 0:
                    self.table.setCurrentCell(last_row, current_col)
                    
            elif direction == 'up':
                # Chercher vers le haut
                for row in range(current_row - 1, -1, -1):
                    item = self.table.item(row, current_col)
                    if not item or not item.text().strip():
                        self.table.setCurrentCell(row, current_col)
                        self.table.editItem(self.table.item(row, current_col) or QTableWidgetItem(""))
                        return
                        
                # Si aucune cellule vide trouvée, aller au début
                self.table.setCurrentCell(0, current_col)
                
        except Exception as e:
            app_logger.error(f"Erreur navigation cellule vide: {e}")
    
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
            
            # Ajouter le message à l'historique
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
        """Exporter les données dans le format spécifié"""
        search_term = self.search_input.text().strip()
        if not search_term:
            QMessageBox.information(self, "Information", "Veuillez entrer un terme de recherche")
            return
        
        try:
            result = self.exporter.export_search_results(search_term, export_format)
            
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
        """Appliquer un filtre sur une colonne"""
        # Utiliser la recherche parsée actuelle
        search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
        self.load_data(search_term)

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
        
        # Parser la recherche avancée
        parsed_search = self._parse_advanced_search(search_term) if search_term else None
        self.pending_search_term = parsed_search
        
        # Arrêter le timer précédent et démarrer un nouveau délai
        self.search_timer.stop()
        self.search_timer.start(300)  # Attendre 300ms avant de lancer la recherche
        
        # Activer/désactiver les boutons d'export immédiatement
        has_search = bool(search_term)
        self.export_csv_btn.setEnabled(has_search)
        self.export_html_brands_btn.setEnabled(has_search)
        self.export_html_details_btn.setEnabled(has_search)
    
    def _perform_delayed_search(self):
        """Effectuer la recherche après le délai de débounce"""
        if hasattr(self, 'pending_search_term'):
            self.load_data(self.pending_search_term, is_search=True)

    def _auto_save(self):
        """Sauvegarde automatique"""
        if not self.modified_cells:
            return
        
        try:
            for row, col in list(self.modified_cells):
                item = self.table.item(row, col)
                if item:
                    self._update_cell_in_db(item)
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
        
        # Ajouter le nouveau message au début de la liste
        self._history_messages.insert(0, f"[{timestamp}] {message}")
        
        # Limiter à 50 entrées
        if len(self._history_messages) > 50:
            self._history_messages = self._history_messages[:50]
        
        # Reconstruire tout le HTML
        html_content = """<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: monospace; font-size: 12px; margin: 4px; padding: 4px; }
        p { margin: 2px 0; }
        .timestamp { color: #666; }
        .message { color: #333; }
    </style>
</head>
<body>
"""
        
        # Ajouter tous les messages
        for msg in self._history_messages:
            # Séparer timestamp et contenu pour styling
            if msg.startswith('[') and '] ' in msg:
                parts = msg.split('] ', 1)
                timestamp_part = parts[0] + ']'
                content_part = parts[1] if len(parts) > 1 else ''
                # Convertir les retours à la ligne en HTML
                content_part = content_part.replace('\n', '<br>')
                html_content += f"<p style='margin: 6px 0; line-height: 1.4; padding: 2px 0;'><span class='timestamp'>{timestamp_part}</span> <span class='message'>{content_part}</span></p>\n"
            else:
                # Convertir les retours à la ligne en HTML
                msg_html = msg.replace('\n', '<br>')
                html_content += f"<p style='margin: 6px 0; line-height: 1.4; padding: 2px 0;' class='message'>{msg_html}</p>\n"
        
        html_content += """</body>
</html>"""
        
        # Définir le contenu HTML en une fois
        self.history_list.setHtml(html_content)
        
        # Positionner en haut pour voir la dernière entrée
        cursor = self.history_list.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.history_list.setTextCursor(cursor)


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

    def _import_csv(self):
        """Importer un fichier CSV"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Importer CSV", "", "Fichiers CSV (*.csv)"
        )
        
        if filename:
            try:
                import csv
                import os
                from datetime import datetime
                
                # D'abord, analyser le fichier pour détecter le nombre de colonnes
                detected_columns = self._detect_csv_columns(filename)
                if detected_columns is None:
                    return
                
                # Extraire le nom du fichier sans extension pour la référence de pièce
                filename_without_ext = os.path.splitext(os.path.basename(filename))[0]
                
                # Dialogue pour choisir le type d'import (avec référence pré-remplie)
                import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(detected_columns, filename_without_ext, "CSV")
                if import_type is None:
                    return
                
                # Lire le fichier CSV avec détection automatique du séparateur et de l'encodage
                encoding = self._detect_file_encoding(filename)
                imported_data = []
                with open(filename, 'r', encoding=encoding) as file:
                    # Lire un échantillon pour détecter le séparateur
                    sample = file.read(1024)
                    file.seek(0)
                    
                    # Détecter le séparateur le plus probable
                    sniffer = csv.Sniffer()
                    try:
                        dialect = sniffer.sniff(sample, delimiters=',;\t')
                        reader = csv.reader(file, dialect)
                    except csv.Error:
                        # Fallback: essayer les séparateurs dans l'ordre de préférence
                        if sample.count(';') > sample.count(',') and sample.count(';') > sample.count('\t'):
                            reader = csv.reader(file, delimiter=';')
                        elif sample.count('\t') > sample.count(','):
                            reader = csv.reader(file, delimiter='\t')
                        else:
                            reader = csv.reader(file, delimiter=',')
                    
                    for row_index, row in enumerate(reader):
                        if row_index == 0 and has_headers:  # Ignorer la ligne d'en-tête seulement si spécifié
                            continue
                        if len(row) >= 2 and any(str(cell).strip() for cell in row):  # Au moins 2 colonnes avec des données
                            imported_data.append(row)
                
                if not imported_data:
                    self._show_error("Aucune donnée valide trouvée dans le fichier CSV")
                    return
                
                # Créer une barre de progression pour les gros imports
                progress_dialog = None
                if len(imported_data) >= 1000:
                    progress_dialog = QProgressDialog(
                        f"Traitement des lignes... 0 / {len(imported_data)}",
                        "Annuler",
                        0, len(imported_data),
                        self
                    )
                    progress_dialog.setWindowTitle("Import CSV")
                    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                    progress_dialog.show()
                    QApplication.processEvents()
                
                # Traiter l'import
                results = self._process_import(imported_data, import_type, ref_piece, third_column_choice, progress_dialog, libelle_piece)
                
                # Fermer la barre de progression
                if progress_dialog:
                    progress_dialog.setValue(len(imported_data))
                    progress_dialog.close()
                
                # Afficher la synthèse
                
                # Enregistrer dans l'historique
                self._log_import_to_history(results, ref_piece, f"CSV ({filename})")
                
                
                # Actualiser l'affichage
                self._force_refresh_display(reset_page=True, clear_filters=True)
                
            except Exception as e:
                self._show_error(f"Erreur lors de l'import: {e}")
    
    def _get_import_options(self, detected_columns=None, default_ref_piece=None):
        """Dialogue pour choisir les options d'import"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Options d'import")
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # Type d'import (adapté au nombre de colonnes détecté)
        if detected_columns:
            info_label = QLabel(f"📊 Fichier détecté: {detected_columns} colonnes")
            info_label.setStyleSheet("color: #28a745; font-weight: bold; margin: 5px;")
            layout.addWidget(info_label)
        
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type d'import:"))
        type_combo = QComboBox()
        
        # Adapter les options selon le nombre de colonnes détecté
        if detected_columns == 2:
            type_combo.addItems(["2 colonnes (ref_modele, commercial_ref)"])
        elif detected_columns == 3:
            type_combo.addItems(["3 colonnes (ref_modele, commercial_ref, autre)"])
        else:
            # Cas général ou non détecté
            type_combo.addItems(["2 colonnes (ref_modele, commercial_ref)", "3 colonnes (ref_modele, commercial_ref, autre)"])
        
        type_layout.addWidget(type_combo)
        layout.addLayout(type_layout)
        
        # Référence de pièce (optionnelle)
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence de pièce (optionnelle):"))
        ref_input = QLineEdit()
        ref_input.setText(default_ref_piece if default_ref_piece else "")  # Pré-remplir avec le nom du fichier
        ref_layout.addWidget(ref_input)
        layout.addLayout(ref_layout)
        
        # Case à cocher pour les en-têtes
        headers_checkbox = QCheckBox("Le fichier contient une ligne d'en-têtes (ignorer la première ligne)")
        headers_checkbox.setChecked(False)  # Par défaut, pas d'en-têtes
        headers_checkbox.setToolTip("Cochez cette case si la première ligne de votre fichier contient les noms des colonnes")
        layout.addWidget(headers_checkbox)
        
        # Gestion de la 3ème colonne (seulement si nécessaire)
        third_col_layout = None
        third_col_combo = None
        
        if detected_columns == 3 or detected_columns is None:  # Montrer si 3 colonnes ou indéterminé
            third_col_layout = QHBoxLayout()
            label_text = "Stocker la 3ème colonne dans:" if detected_columns == 3 else "Si 3 colonnes, stocker la 3ème dans:"
            third_col_layout.addWidget(QLabel(label_text))
            third_col_combo = QComboBox()
            third_col_combo.addItems(["Ignorer", "Autre référence", "Notes"])
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
            # Déterminer le nombre de colonnes
            if detected_columns == 2:
                result[0] = 2
            elif detected_columns == 3:
                result[0] = 3
            else:
                result[0] = type_combo.currentIndex() + 2  # 2 ou 3 colonnes
            
            result[1] = ref_input.text().strip() if ref_input.text().strip() else None
            
            # Choix pour la 3ème colonne (seulement si applicable)
            if third_col_combo:
                third_choice = third_col_combo.currentText()
                if third_choice == "Ignorer":
                    result[2] = "ignore"
                elif third_choice == "Autre référence":
                    result[2] = "other_ref"
                elif third_choice == "Notes":
                    result[2] = "notes"
                else:
                    result[2] = "ignore"
            else:
                result[2] = "ignore"  # Par défaut pour 2 colonnes
            
            # Récupérer l'option d'en-têtes
            result[3] = headers_checkbox.isChecked()
            dialog.accept()
        
        def on_cancel():
            dialog.reject()
        
        ok_button.clicked.connect(on_ok)
        cancel_button.clicked.connect(on_cancel)
        
        if dialog.exec_() == QDialog.Accepted:
            return result[0], result[1], result[2], result[3]
        return None, None, None, None
    
    def _detect_csv_columns(self, filename):
        """Détecter automatiquement le nombre de colonnes du fichier CSV"""
        try:
            import csv
            
            # Détecter l'encodage automatiquement
            encoding = self._detect_file_encoding(filename)
            
            with open(filename, 'r', encoding=encoding) as file:
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
        # Encodages courants à tester
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']
        
        # D'abord essayer avec chardet si disponible
        try:
            import chardet
            with open(filename, 'rb') as file:
                raw_data = file.read(10000)  # Lire les premiers 10KB
                detected = chardet.detect(raw_data)
                if detected and detected['encoding'] and detected['confidence'] > 0.7:
                    return detected['encoding']
        except (ImportError, Exception):
            pass
        
        # Sinon, tester manuellement les encodages courants
        for encoding in encodings_to_try:
            try:
                with open(filename, 'r', encoding=encoding) as file:
                    file.read(1000)  # Essayer de lire le début du fichier
                    return encoding
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        
        # Par défaut, retourner latin-1 qui peut lire tous les bytes
        return 'latin-1'
    
    def _detect_separator(self, filename):
        """Détecter automatiquement le séparateur CSV"""
        try:
            import csv
            
            # Détecter l'encodage d'abord
            encoding = self._detect_file_encoding(filename)
            
            with open(filename, 'r', encoding=encoding) as file:
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
    
    def _process_import(self, imported_data, import_type, ref_piece, third_column_choice="ignore", progress_dialog=None, libelle_piece=None):
        """Traiter les données d'import"""
        # Vider le cache des décisions de description au début de chaque import
        self._piece_description_decisions.clear()
        
        results = {
            'total_imported': 0,
            'matches_found': 0,
            'manual_completion': 0,
            'duplicates_skipped': 0,
            'new_entries': 0,
            'associations_created': 0,
            'descriptions_updated': 0
        }
        
        # Log de démarrage avec format unifié
        print(f"\n🔍 Début du traitement de {len(imported_data)} lignes d'import")
        
        for row_idx, row in enumerate(imported_data):
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
                    ref_modele = row[0].strip() if len(row) > 0 else ""
                    commercial_ref = ""
                elif import_type == 2:
                    # 2 colonnes: ref_modele, commercial_ref (colonnes C et D)
                    ref_modele = row[0].strip() if len(row) > 0 else ""
                    commercial_ref = row[1].strip() if len(row) > 1 else ""
                elif import_type == 3:
                    # 3 colonnes: ref_modele, commercial_ref, 3ème colonne selon choix
                    ref_modele = row[0].strip() if len(row) > 0 else ""
                    commercial_ref = row[1].strip() if len(row) > 1 else ""
                    third_value = row[2].strip() if len(row) > 2 else ""
                    
                    # Gérer la 3ème colonne selon le choix utilisateur
                    other_ref = third_value if third_column_choice == "other_ref" else ""
                    notes = third_value if third_column_choice == "notes" else ""
                    # Si "ignore", les deux restent vides
                elif import_type >= 4:
                    # 4+ colonnes: type, manufacturer, ref_modele, commercial_ref, other_ref, ...
                    type_val = row[0].strip() if len(row) > 0 else ""
                    manufacturer = row[1].strip() if len(row) > 1 else ""
                    ref_modele = row[2].strip() if len(row) > 2 else ""
                    commercial_ref = row[3].strip() if len(row) > 3 else ""
                    other_ref = row[4].strip() if len(row) > 4 else ""
                    # notes peuvent être en colonne 5 si présentes
                
                # Log de la ligne en cours
                print(f"\n🔵 Ligne {row_idx + 1}: {len(row)} colonnes - {row[:4]}{'...' if len(row) > 4 else ''}")
                
                # Chercher l'appareil existant par ses références (colonnes C et D)
                existing_device = self._find_existing_device_by_refs(ref_modele, commercial_ref)
                
                if existing_device:
                    # Appareil existant trouvé - compléter avec les infos importées
                    device_id = existing_device['id']
                    print(f"  ✅ Appareil existant trouvé par combinaison exacte: {ref_modele} + {commercial_ref}")
                    print(f"🔄 Ligne {row_idx + 1}: Appareil existant trouvé (ID: {device_id})")
                    
                    # Mettre à jour les champs si nécessaire
                    updates = {}
                    if type_val and not existing_device.get('type'):
                        updates['type'] = type_val
                    if manufacturer and not existing_device.get('manufacturer'):
                        updates['manufacturer'] = manufacturer
                    if ref_modele and not existing_device.get('ref_modele'):
                        updates['ref_modele'] = ref_modele
                    if commercial_ref:
                        updates['commercial_ref'] = commercial_ref
                    if other_ref and not existing_device.get('other_ref'):
                        updates['other_ref'] = other_ref
                    if notes and not existing_device.get('notes'):
                        updates['notes'] = notes
                    
                    # Appliquer les mises à jour
                    if updates:
                        self._update_device_info(device_id, updates)
                        print(f"  ⚙️ Mis à jour: {list(updates.keys())}")
                    
                    # Créer association si référence de pièce fournie
                    if ref_piece and ref_piece.strip():
                        try:
                            if not self._piece_already_associated(device_id, ref_piece.strip()):
                                _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), device_id, libelle_piece, self._confirm_piece_description_update)
                                results['associations_created'] += 1
                                if desc_updated:
                                    results['descriptions_updated'] += 1
                                print(f"  🔗 Pièce {ref_piece.strip()} associée")
                            else:
                                # Pièce déjà associée, mais vérifier le libellé si fourni
                                if libelle_piece and libelle_piece.strip():
                                    _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), device_id, libelle_piece, self._confirm_piece_description_update)
                                    if desc_updated:
                                        results['descriptions_updated'] += 1
                                    print(f"  📝 Libellé vérifié pour pièce {ref_piece.strip()} déjà associée")
                                results['duplicates_skipped'] += 1
                                print(f"  ⚠️ Pièce {ref_piece.strip()} déjà associée")
                                
                                # Collecter les détails du doublon pour CSV/PDF
                                if not hasattr(self, '_current_import_duplicates'):
                                    self._current_import_duplicates = []
                                self._current_import_duplicates.append({
                                    'ligne': row_idx + 1,
                                    'appareil_id': device_id,
                                    'ref_piece': ref_piece.strip(),
                                    'appareil_data': {
                                        'ref_modele': existing_device.get('ref_modele', ''),
                                        'commercial_ref': existing_device.get('commercial_ref', ''),
                                        'type': existing_device.get('type', ''),
                                        'manufacturer': existing_device.get('manufacturer', '')
                                    }
                                })
                        except Exception as piece_error:
                            print(f"❌ Échec association pièce {ref_piece.strip()} avec appareil {device_id}: {piece_error}")
                            app_logger.error(f"Échec association pièce {ref_piece.strip()} avec appareil {device_id}: {piece_error}")
                    else:
                        # Ligne sans référence de pièce - compter dans les associations manquantes
                        results['no_piece_ref'] = results.get('no_piece_ref', 0) + 1
                        print(f"  ⚠️ Ligne {row_idx + 1}: Appareil traité mais pas de référence de pièce")
                    
                    # Vérifier si l'appareil nécessite encore une complétion manuelle
                    # (basé sur l'état d'origine avant mise à jour)
                    if self._needs_manual_completion(existing_device):
                        results['manual_completion'] += 1
                    
                    results['matches_found'] += 1
                    results['total_imported'] += 1  # Compter après succès
                    # NE PAS créer de nouvelle ligne dans le tableau
                else:
                    # Nouvel appareil - utiliser la même logique harmonisée que le collage
                    if ref_modele.strip() or commercial_ref.strip():
                        print(f"✨ Ligne {row_idx + 1}: Création d'un nouvel appareil")
                        # Préparer les données d'appareil comme dans _handle_paste
                        appareil_data = {
                            'type': type_val.strip(),
                            'manufacturer': manufacturer.strip(),
                            'ref_modele': ref_modele.strip(),
                            'commercial_ref': commercial_ref.strip(),
                            'other_ref': other_ref.strip(),
                            'category': '',
                            'notes': notes.strip()
                        }
                        
                        # Vérifier si l'appareil nécessite une complétion manuelle AVANT auto-complétion
                        needs_completion = self._needs_manual_completion(appareil_data)
                        
                        # Essayer l'auto-complétion
                        if not appareil_data.get('type') or not appareil_data.get('manufacturer'):
                            self._try_auto_complete(appareil_data)
                        
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
                                results['total_imported'] += 1  # Compter après succès
                                print(f"  ✅ Nouvel appareil créé (ID: {device_id})")
                                if ref_piece and ref_piece.strip():
                                    try:
                                        if not self._piece_already_associated(device_id, ref_piece.strip()):
                                            _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), device_id, libelle_piece, self._confirm_piece_description_update)
                                            results['associations_created'] += 1
                                            if desc_updated:
                                                results['descriptions_updated'] += 1
                                            print(f"  🔗 Pièce {ref_piece.strip()} associée")
                                        else:
                                            # Pièce déjà associée, mais vérifier le libellé si fourni
                                            if libelle_piece and libelle_piece.strip():
                                                _, desc_updated = self.db_manager.add_or_update_piece_with_description(ref_piece.strip(), device_id, libelle_piece, self._confirm_piece_description_update)
                                                if desc_updated:
                                                    results['descriptions_updated'] += 1
                                                print(f"  📝 Libellé vérifié pour pièce {ref_piece.strip()} déjà associée")
                                            results['duplicates_skipped'] += 1
                                            print(f"  ⚠️ Pièce {ref_piece.strip()} déjà associée")
                                            
                                            # Collecter les détails du doublon pour CSV/PDF
                                            if not hasattr(self, '_current_import_duplicates'):
                                                self._current_import_duplicates = []
                                            self._current_import_duplicates.append({
                                                'ligne': row_idx + 1,
                                                'appareil_id': device_id,
                                                'ref_piece': ref_piece.strip(),
                                                'appareil_data': {
                                                    'ref_modele': ref_modele.strip(),
                                                    'commercial_ref': commercial_ref.strip(),
                                                    'type': type_val.strip(),
                                                    'manufacturer': manufacturer.strip()
                                                }
                                            })
                                    except Exception as piece_error:
                                        print(f"❌ Échec association pièce {ref_piece.strip()} avec nouvel appareil {device_id}: {piece_error}")
                                        app_logger.error(f"Échec association pièce {ref_piece.strip()} avec nouvel appareil {device_id}: {piece_error}")
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
        
        # Résumé final unifié
        print(f"\n📊 Résumé du traitement:")
        print(f"  Lignes traitées : {results['total_imported']}")
        print(f"  Appareils créés : {results['new_entries']}")
        print(f"  Appareils mis à jour : {results['matches_found']}")
        print(f"  Associations créées : {results['associations_created']}")
        
        duplicates_skipped = results.get('duplicates_skipped', 0)
        if duplicates_skipped > 0:
            print(f"  Associations déjà existantes : {duplicates_skipped}")
        
        # Informations liées aux pièces
        manual_completion = results.get('manual_completion', 0)
        if manual_completion > 0:
            print(f"  Appareils à compléter : {manual_completion}")
            
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

    def _find_existing_device_by_refs(self, ref_modele, commercial_ref):
        """Chercher un appareil existant par ses références (colonnes C et D) avec détection de références partielles"""
        try:
            # NOUVELLE LOGIQUE: Recherche exacte puis fuzzy par ref_modele ET commercial_ref
            # Pour éviter les faux doublons avec références commerciales partagées
            
            # 1. Si on a les deux références, chercher la combinaison exacte
            if ref_modele and ref_modele.strip() and commercial_ref and commercial_ref.strip():
                query = """SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes 
                          FROM appareils 
                          WHERE ref_modele = ? AND commercial_ref = ?"""
                params = [ref_modele.strip(), commercial_ref.strip()]
                result = self.db_manager.execute_query(query, params)
                if result:
                    print(f"  ✅ Appareil existant trouvé par combinaison exacte: {ref_modele} + {commercial_ref}")
                    return {
                        'id': result[0][0], 
                        'type': result[0][1], 
                        'manufacturer': result[0][2],
                        'ref_modele': result[0][3],
                        'commercial_ref': result[0][4],
                        'other_ref': result[0][5],
                        'category': result[0][6],
                        'notes': result[0][7]
                    }
            
            # 2. Recherche par ref_modele avec fuzzy matching (références partielles)
            if ref_modele and ref_modele.strip():
                # Normaliser la référence recherchée
                normalized_ref = self._normalize_reference(ref_modele)
                
                # Recherche exacte d'abord
                query = "SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes FROM appareils WHERE ref_modele = ?"
                params = [ref_modele.strip()]
                result = self.db_manager.execute_query(query, params)
                if result:
                    print(f"  ✅ Appareil existant trouvé par ref_modele exact: {ref_modele}")
                    return {
                        'id': result[0][0], 
                        'type': result[0][1], 
                        'manufacturer': result[0][2],
                        'ref_modele': result[0][3],
                        'commercial_ref': result[0][4],
                        'other_ref': result[0][5],
                        'category': result[0][6],
                        'notes': result[0][7]
                    }
                
                # Recherche fuzzy DÉSACTIVÉE pour éviter les faux positifs
                # Exemple: Q1457ATGW ne doit PAS matcher Q1457ATGW/XEN
                print(f"  ❌ Aucun appareil trouvé pour ref_modele exact: {ref_modele}")
                # Pas de recherche fuzzy pour éviter les matches incorrects
            
            # 3. Recherche par commercial_ref avec fuzzy matching
            if commercial_ref and commercial_ref.strip():
                # Normaliser la référence recherchée
                normalized_ref = self._normalize_reference(commercial_ref)
                
                # Recherche exacte d'abord
                query = "SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes FROM appareils WHERE commercial_ref = ?"
                params = [commercial_ref.strip()]
                result = self.db_manager.execute_query(query, params)
                if result:
                    print(f"  ✅ Appareil existant trouvé par commercial_ref exact: {commercial_ref}")
                    return {
                        'id': result[0][0], 
                        'type': result[0][1], 
                        'manufacturer': result[0][2],
                        'ref_modele': result[0][3],
                        'commercial_ref': result[0][4],
                        'other_ref': result[0][5],
                        'category': result[0][6],
                        'notes': result[0][7]
                    }
                
                # Recherche fuzzy DÉSACTIVÉE pour éviter les faux positifs
                print(f"  ❌ Aucun appareil trouvé pour commercial_ref exact: {commercial_ref}")
                # Pas de recherche fuzzy pour éviter les matches incorrects
            
            # Aucun appareil existant trouvé
            print(f"  🆕 Aucun appareil existant pour: ref_modele='{ref_modele}', commercial_ref='{commercial_ref}'")
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
            return len(result) > 0
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

    def _get_import_options_unified(self, detected_columns=None, default_ref_piece=None, import_method="CSV"):
        """Dialogue unifié pour choisir les options d'import (CSV, PDF, COLLAGE)"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Options d'import {import_method}")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)
        
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
    
    def _generate_console_summary(self, results, ref_piece, source):
        """Générer la synthèse dans le même format que la console"""
        summary = f"📊 Import {source}"
        if ref_piece:
            summary += f" (pièce: {ref_piece})"
        summary += ":\n"
        
        # Utiliser le même format simplifié que la console
        summary += f"  Lignes traitées : {results.get('total_imported', 0)}\n"
        summary += f"  Appareils créés : {results.get('new_entries', 0)}\n"
        summary += f"  Appareils mis à jour : {results.get('matches_found', 0)}\n"
        summary += f"  Associations créées : {results.get('associations_created', 0)}"
        
        duplicates_skipped = results.get('duplicates_skipped', 0)
        if duplicates_skipped > 0:
            summary += f"\n  Associations déjà existantes : {duplicates_skipped}"
        
        # Informations liées aux pièces
        manual_completion = results.get('manual_completion', 0)
        if manual_completion > 0:
            summary += f"\n  Appareils à compléter : {manual_completion}"
            
        descriptions_updated = results.get('descriptions_updated', 0)
        if descriptions_updated > 0:
            summary += f"\n  Libellés mis à jour : {descriptions_updated}"
            
        no_piece_ref = results.get('no_piece_ref', 0)
        if no_piece_ref > 0:
            summary += f"\n  Lignes sans référence pièce : {no_piece_ref}"
        
        return summary

    def _log_import_to_history(self, results, ref_piece, source):
        """Enregistrer l'import dans l'historique avec format console"""
        from datetime import datetime
        
        # Générer la synthèse dans le format console
        console_summary = self._generate_console_summary(results, ref_piece, source)
        
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
            filter_widget.blockSignals(True)
            filter_widget.clear()
            filter_widget.blockSignals(False)
    
    def _toggle_incomplete_filter(self, checked: bool):
        """Basculer le filtre pour afficher seulement les lignes incomplètes"""
        self.show_incomplete_only = checked
        
        if checked:
            # Activer le filtre - nettoyer les autres filtres d'abord
            self._clear_column_filters()
            self.search_input.clear()
            self.incomplete_filter_btn.setText("📋 Actives")
            # Le style est géré par le CSS moderne via :checked
        else:
            # Désactiver le filtre
            self.incomplete_filter_btn.setText("📋 Incomplètes")
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
            dialog.setWindowTitle("📖 Guide d'utilisation - 1001 Pièces")
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            
            # Contenu du guide
            guide_text = QTextEdit()
            guide_text.setReadOnly(True)
            guide_content = """
# Guide d'utilisation - 1001 Pièces

## 🚀 Démarrage rapide

### Import de données
1. **Import CSV** : Utilisez le bouton "📈 Import" ou glissez/déposez un fichier CSV sur le tableau
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
        """Gérer le déposer d'un ou plusieurs fichiers CSV ou PDF"""
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
        """Importer un fichier CSV depuis un chemin donné (utilisé pour le glisser/déposer)"""
        try:
            import csv
            from datetime import datetime
            
            # D'abord, analyser le fichier pour détecter le nombre de colonnes
            detected_columns = self._detect_csv_columns(file_path)
            if detected_columns is None:
                return
            
            # Extraire le nom du fichier sans extension pour la référence de pièce
            import os
            filename_without_ext = os.path.splitext(os.path.basename(file_path))[0]
            
            # Dialogue pour choisir le type d'import (avec référence pré-remplie)
            import_type, ref_piece, third_column_choice, has_headers = self._get_import_options(detected_columns, filename_without_ext)
            if import_type is None:
                return
            
            # Le reste du traitement est identique à _import_csv
            separator = self._detect_separator(file_path)
            encoding = self._detect_file_encoding(file_path)
            
            # Utiliser la même logique que l'import CSV classique : passer des listes brutes
            imported_data = []
            with open(file_path, 'r', encoding=encoding) as file:
                csv_reader = csv.reader(file, delimiter=separator)
                
                for row_index, row in enumerate(csv_reader):
                    if row_index == 0 and has_headers:  # Header (seulement si spécifié)
                        continue
                    
                    if len(row) >= 2 and any(str(cell).strip() for cell in row):  # Au moins 2 colonnes avec des données
                        imported_data.append(row)
            
            if not imported_data:
                QMessageBox.warning(self, "Import CSV", "Aucune donnée valide trouvée dans le fichier.")
                return
            
            # Traitement de l'import (utiliser import_type)
            results = self._process_import(imported_data, import_type, ref_piece, third_column_choice, None, libelle_piece)
            
            # Affichage du résumé et ajout à l'historique
            self._log_import_to_history(results, ref_piece, f"CSV (Glisser/Déposer - {os.path.basename(file_path)})")
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'import CSV par glisser/déposer: {e}")
    
    def _import_pdf_from_path(self, file_paths):
        """Importer un ou plusieurs fichiers PDF depuis des chemins donnés"""
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
            
            # Afficher la boîte de dialogue d'options d'import
            import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(3, suggested_ref_piece, "PDF")
            if import_type is None:
                return
            
            # Créer l'extracteur Camelot
            extractor = CamelotPDFExtractor()
            
            # Traiter tous les fichiers
            all_converted_data = []
            processed_files = []
            
            # Créer une barre de progression pour l'import PDF
            total_files = len(file_paths)
            progress_dialog = QProgressDialog(
                f"Import PDF en cours... 0 / {total_files} fichier(s)",
                "Annuler",
                0, total_files,
                self
            )
            progress_dialog.setWindowTitle("Import PDF")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
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
                    
                    # Debug : afficher le nombre de lignes extraites
                    print(f"📄 Fichier PDF {os.path.basename(file_path)}: {len(extracted_data)} lignes extraites")
                    
                    # Convertir les données extraites en format compatible avec _process_import
                    for row in extracted_data:
                        # Les données PDF sont déjà en format [ref_technique, ref_commerciale, description]
                        # On les convertit selon le choix de l'utilisateur
                        if third_column_choice == "notes":
                            all_converted_data.append([row[0], row[1], "", row[2]])  # [ref_modele, commercial_ref, other_ref, notes]
                        elif third_column_choice == "other_ref":
                            all_converted_data.append([row[0], row[1], row[2], ""])  # [ref_modele, commercial_ref, other_ref, notes]
                        else:  # ignore
                            all_converted_data.append([row[0], row[1], "", ""])  # [ref_modele, commercial_ref, other_ref, notes]
                    
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
            
            self._log_import_to_history(results, ref_piece, source_info)
            
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
            # Séparer les lignes et colonnes
            rows = [row.split('\t') for row in clipboard_text.strip().split('\n')]
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
            
            # Demander les options d'import avec la fenêtre unifiée
            import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(detected_columns, None, "COLLAGE")
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
                    appareil_data.get('commercial_ref', '')
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
                    # (basé sur l'état d'origine avant mise à jour)
                    if self._needs_manual_completion(existing_device):
                        manual_completion_count += 1
                    
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
                            
                            # Compter si nécessite complétion manuelle (basé sur l'état d'origine)
                            if needs_completion:
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
            
            # Résumé détaillé pour debugging uniquement
            from src.core.config import pluralize
            detailed_summary = f"📊 Résumé de l'import par collage:\n"
            detailed_summary += f"  Total {pluralize(total_rows, 'ligne traitée')}\n"
            detailed_summary += f"  {pluralize(ignored_count, 'ligne rejetée')}\n"
            detailed_summary += f"  {pluralize(inserted_count, 'appareil nouveau', 'appareils nouveaux')}\n"
            detailed_summary += f"  {pluralize(updated_count, 'appareil mis à jour')}\n"
            detailed_summary += f"  {pluralize(associations_created, 'association créée')}\n"
            detailed_summary += f"  Associations déjà existantes : {duplicates_skipped}\n"
            detailed_summary += f"  {pluralize(no_piece_ref_count, 'ligne sans référence de pièce')}"
            
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
        type_empty = not appareil_data.get('type', '').strip()
        manufacturer_empty = not appareil_data.get('manufacturer', '').strip()
        return type_empty and manufacturer_empty

    def _try_auto_complete(self, appareil_data: dict):
        """Essayer de compléter automatiquement Type et Fabricant à partir des références"""
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
                return
            
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
                return  # Aucune référence pour faire la recherche
            
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


def main():
    """Point d'entrée de l'application"""
    app = QApplication(sys.argv)
    
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