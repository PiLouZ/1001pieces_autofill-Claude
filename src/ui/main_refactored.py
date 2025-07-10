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
    QProgressDialog, QCheckBox, QMenu
)
from PyQt5.QtGui import QKeySequence, QPainter, QPen, QColor, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import QSize, QMimeData, QUrl
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
        self._setup_menubar()
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
        
        # Tableau principal
        self.table = QTableWidget()
        self.table.setColumnCount(len(Config.UI_HEADERS))
        self.table.setHorizontalHeaderLabels(Config.UI_HEADERS)
        self.table.setAcceptDrops(True)  # Activer le glisser/déposer pour les fichiers CSV
        self.table.setDragDropMode(QTableWidget.DragDropMode.DropOnly)  # Seulement accepter les drops
        
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
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Recherche globale (appareils et pièces)...")
        self.search_input.textChanged.connect(self._search_table)
        search_section_layout.addWidget(self.search_input)
        
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
        
        self.history_list = QListWidget()
        # Supprimer la limitation de hauteur pour permettre l'étirement
        # self.history_list.setMaximumHeight(150) 
        
        # Forcer le retour à la ligne et supprimer l'ascenseur horizontal
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_list.setWordWrap(True)
        
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
        
        # Groupe Données
        import_action = QAction("📈 Import", self)
        import_action.setToolTip("Importer des données depuis un fichier CSV")
        import_action.triggered.connect(self._import_csv)
        toolbar.addAction(import_action)
        
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
    
    def _setup_menubar(self):
        """Configurer la barre de menu"""
        menubar = self.menuBar()
        
        # Forcer l'affichage de la barre de menu sur macOS
        menubar.setNativeMenuBar(False)
        
        # Menu Gestion
        gestion_menu = menubar.addMenu("Gestion")
        
        categories_action = QAction("🏷️ Catégories", self)
        categories_action.setToolTip("Gérer les catégories d'appareils")
        categories_action.triggered.connect(self._manage_categories)
        gestion_menu.addAction(categories_action)
        
        pieces_action = QAction("🔧 Pièces", self)
        pieces_action.setToolTip("Gérer les références de pièces et détecter les orphelines")
        pieces_action.triggered.connect(self._open_pieces_manager)
        gestion_menu.addAction(pieces_action)
        
        validate_action = QAction("🔍 Incohérences", self)
        validate_action.setToolTip("Valider la cohérence de la base et détecter les incohérences")
        validate_action.triggered.connect(self._validate_and_detect_inconsistencies)
        gestion_menu.addAction(validate_action)
        
        # Menu Action  
        action_menu = menubar.addMenu("Action")
        
        autocomplete_action = QAction("≔ Autocomplétion", self)
        autocomplete_action.setToolTip("Complète automatiquement les champs vides")
        autocomplete_action.triggered.connect(self._fill_empty_fields)
        action_menu.addAction(autocomplete_action)
        
        clean_action = QAction("🧹 Nettoyer les doublons", self)
        clean_action.setToolTip("Nettoyer et optimiser la base de données")
        clean_action.triggered.connect(self._clean_data)
        action_menu.addAction(clean_action)
    
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
                    if search_term and col_idx < len(Config.DB_HEADERS) and search_term.lower() in str(item.text()).lower():
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
            current_search = self.search_input.text().strip()
            self.load_data(current_search if current_search else None)
            
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
                search_text = self.search_input.text()
                self.load_data(search_text, is_search=bool(search_text.strip()))
    
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
                search_text = self.search_input.text()
                self.load_data(search_text, is_search=bool(search_text.strip()))
    
    def _go_to_last_page(self):
        """Aller à la dernière page"""
        if self.total_rows > 0:
            total_pages = (self.total_rows + self.page_size - 1) // self.page_size
            self.current_page = max(0, total_pages - 1)
            self.load_data(self.search_input.text())
    
    def _change_page_size(self, size_text: str):
        """Changer la taille de page"""
        try:
            if size_text == "Tout":
                self.use_pagination = False
            else:
                self.use_pagination = True
                self.page_size = int(size_text)
                
            self.current_page = 0  # Retour à la première page
            search_text = self.search_input.text()
            self.load_data(search_text, is_search=bool(search_text.strip()))
            
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
        selected = self.table.selectedRanges()
        if not selected:
            self.drag_handle.hide()
            return
        
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

    # --- Méthodes d'action (stubs pour les fonctionnalités à implémenter) ---

    def _apply_column_filter(self, column: int, text: str):
        """Appliquer un filtre sur une colonne"""
        self.load_data(self.search_input.text())

    def _search_table(self, text: str):
        """Rechercher dans le tableau avec débounce"""
        search_term = text.strip()
        self.pending_search_term = search_term if search_term else None
        
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
    
    def _add_to_history(self, message: str):
        """Ajouter un message à l'historique"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        history_item = QListWidgetItem(f"[{timestamp}] {message}")
        self.history_list.insertItem(0, history_item)  # Ajouter en haut
        
        # Limiter l'historique à 50 entrées
        if self.history_list.count() > 50:
            self.history_list.takeItem(self.history_list.count() - 1)
    
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
        
        ref_piece = self.piece_input.text().strip()
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
                        # Ajouter la pièce sans description
                        self.db_manager.add_piece(ref_piece, db_id, None)
                        added_count += 1
                    else:
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
        """Nettoyer les données"""
        try:
            result = self.db_manager.clean_data()
            
            # Message détaillé avec fusion des données
            message_parts = []
            if result['deleted_empty'] > 0:
                message_parts.append(f"{result['deleted_empty']} lignes vides supprimées")
            if result['deleted_duplicates'] > 0:
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
        except DatabaseError as e:
            self._show_error(f"Erreur lors du nettoyage: {e}")
    
    def _clean_data(self):
        """Nettoyer les données (cumuler doublons et supprimer lignes vides)"""
        reply = QMessageBox.question(
            self, 
            "Nettoyer les données",
            "Cette opération va :\n"
            "• Cumuler les appareils en doublon (garder le plus ancien)\n"
            "• Transférer les pièces vers l'appareil conservé\n"
            "• Cumuler les références de pièces dupliquées\n"
            "• Supprimer les lignes vides\n\n"
            "Cette action est irréversible. Continuer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            # Nettoyer les doublons d'appareils
            devices_deleted = self.db_manager.remove_duplicate_devices()
            
            # Nettoyer les doublons de pièces
            pieces_deleted = self.db_manager.remove_duplicate_pieces()
            
            # Nettoyer les données (fonction originale)
            result = self.db_manager.clean_data()
            
            # Message de résultat
            message_parts = []
            if devices_deleted > 0:
                message_parts.append(f"{devices_deleted} appareils dupliqués cumulés")
            if pieces_deleted > 0:
                message_parts.append(f"{pieces_deleted} références de pièces dupliquées cumulées")
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
                import_type, ref_piece, third_column_choice, has_headers = self._get_import_options(detected_columns, filename_without_ext)
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
                
                # Traiter l'import
                results = self._process_import(imported_data, import_type, ref_piece, third_column_choice)
                
                # Afficher la synthèse
                self._show_import_summary(results, ref_piece)
                
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
    
    def _process_import(self, imported_data, import_type, ref_piece, third_column_choice="ignore"):
        """Traiter les données d'import"""
        results = {
            'total_imported': 0,
            'matches_found': 0,
            'manual_completion': 0,
            'duplicates_skipped': 0,
            'new_entries': 0,
            'associations_created': 0
        }
        
        for row in imported_data:
            try:
                # Initialiser les variables par défaut
                type_val = ""
                manufacturer = ""
                ref_modele = ""
                commercial_ref = ""
                other_ref = ""
                notes = ""
                
                if import_type == 2:
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
                
                # Chercher l'appareil existant par ses références (colonnes C et D)
                existing_device = self._find_existing_device_by_refs(ref_modele, commercial_ref)
                
                if existing_device:
                    # Appareil existant trouvé - compléter avec les infos importées
                    device_id = existing_device['id']
                    
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
                    
                    # Créer association si référence de pièce fournie
                    if ref_piece:
                        if not self._piece_already_associated(device_id, ref_piece):
                            self.db_manager.add_piece(ref_piece, device_id, "")
                            results['associations_created'] += 1
                        else:
                            results['duplicates_skipped'] += 1
                    
                    results['matches_found'] += 1
                    # NE PAS créer de nouvelle ligne dans le tableau
                else:
                    # Nouvel appareil - utiliser la même logique harmonisée que le collage
                    if ref_modele.strip() or commercial_ref.strip():
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
                                if ref_piece:
                                    self.db_manager.add_piece(ref_piece, device_id, "")
                                    results['associations_created'] += 1
                                else:
                                    results['manual_completion'] += 1
                
                # Compter chaque ligne traitée
                results['total_imported'] += 1
                
            except Exception as e:
                print(f"Erreur lors du traitement de la ligne {row}: {e}")
                continue
        
        return results
    
    def _find_existing_device_by_refs(self, ref_modele, commercial_ref):
        """Chercher un appareil existant par ses références (colonnes C et D)"""
        try:
            # NOUVELLE LOGIQUE: Recherche exacte par ref_modele ET commercial_ref
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
            
            # 2. Sinon, recherche par ref_modele uniquement (si c'est la seule référence disponible)
            if ref_modele and ref_modele.strip() and (not commercial_ref or not commercial_ref.strip()):
                query = "SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes FROM appareils WHERE ref_modele = ?"
                params = [ref_modele.strip()]
                result = self.db_manager.execute_query(query, params)
                if result:
                    print(f"  ✅ Appareil existant trouvé par ref_modele seul: {ref_modele}")
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
            
            # 3. Recherche par commercial_ref uniquement (si c'est la seule référence disponible)
            if commercial_ref and commercial_ref.strip() and (not ref_modele or not ref_modele.strip()):
                query = "SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes FROM appareils WHERE commercial_ref = ?"
                params = [commercial_ref.strip()]
                result = self.db_manager.execute_query(query, params)
                if result:
                    print(f"  ✅ Appareil existant trouvé par commercial_ref seul: {commercial_ref}")
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
            
            # Aucun appareil existant trouvé
            print(f"  🆕 Aucun appareil existant pour: ref_modele='{ref_modele}', commercial_ref='{commercial_ref}'")
            return None
        except Exception as e:
            print(f"Erreur recherche appareil: {e}")
            return None
    
    def _piece_already_associated(self, device_id, ref_piece):
        """Vérifier si la pièce est déjà associée à l'appareil"""
        try:
            query = "SELECT id FROM pieces WHERE appareil_id = ? AND ref_piece = ?"
            result = self.db_manager.execute_query(query, [device_id, ref_piece])
            return len(result) > 0
        except:
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
    
    def _show_import_summary(self, results, ref_piece):
        """Afficher la synthèse d'import"""
        summary = f"{results['total_imported']} appareils importés"
        if ref_piece:
            summary += f" et associés à la référence {ref_piece}"
        summary += f"\n→ {results['matches_found']} correspondances trouvées"
        summary += f"\n→ {results['manual_completion']} appareils à compléter manuellement"
        
        if results['duplicates_skipped'] > 0:
            summary += f"\n→ {results['duplicates_skipped']} associations dupliquées ignorées"
        
        if results['new_entries'] > 0:
            summary += f"\n→ {results['new_entries']} nouveaux appareils créés"
        
        if results['associations_created'] > 0:
            summary += f"\n→ {results['associations_created']} associations créées"
        
        self._show_info(summary)
    
    def _log_import_to_history(self, results, ref_piece, source):
        """Enregistrer l'import dans l'historique avec format détaillé (CSV ou Collage)"""
        from datetime import datetime
        from src.core.config import pluralize
        
        # Créer un résumé détaillé comme pour le collage
        detailed_summary = f"📊 Résumé de l'import {source}"
        if ref_piece:
            detailed_summary += f" - Référence pièce: {ref_piece}"
        detailed_summary += ":\n"
        
        # Calculer le total traité
        total_processed = results.get('total_imported', 0) + results.get('duplicates_skipped', 0)
        
        detailed_summary += f"  Total {pluralize(total_processed, 'ligne traitée')}\n"
        
        # Nouveaux appareils créés
        new_entries = results.get('new_entries', 0)
        if new_entries > 0:
            detailed_summary += f"  {pluralize(new_entries, 'appareil nouveau', 'appareils nouveaux')}\n"
        
        # Appareils mis à jour (correspondances trouvées)
        matches_found = results.get('matches_found', 0)
        if matches_found > 0:
            detailed_summary += f"  {pluralize(matches_found, 'appareil mis à jour')}\n"
        
        # Associations créées
        associations_created = results.get('associations_created', 0)
        if associations_created > 0:
            detailed_summary += f"  {pluralize(associations_created, 'association créée')}\n"
        
        # Doublons ignorés
        duplicates_skipped = results.get('duplicates_skipped', 0)
        if duplicates_skipped > 0:
            detailed_summary += f"  {pluralize(duplicates_skipped, 'doublon ignoré')}\n"
        
        # Appareils nécessitant complétion manuelle
        manual_completion = results.get('manual_completion', 0)
        if manual_completion > 0:
            detailed_summary += f"  {pluralize(manual_completion, 'appareil à compléter manuellement')}"
        else:
            # Supprimer le dernier \n si pas de complétion manuelle
            detailed_summary = detailed_summary.rstrip('\n')
        
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
                    'summary': detailed_summary
                }
            )
        
        # Ajouter à l'historique des actions
        self.undo_manager.add_action({
            'type': operation_type,
            'description': f"Import {source}: {detailed_summary.split(':')[0]}",
            'before_data': None,
            'after_data': results,
            'source': source
        })
        
        # Ajouter à l'historique visible avec le format détaillé
        self._add_to_history(detailed_summary)

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
        self.load_data()
    
    def _force_refresh_display(self, reset_page=False, clear_filters=False):
        """Forcer le rafraîchissement complet de l'affichage du tableau"""
        try:
            # Sauvegarder l'état de recherche actuel
            current_search = self.search_input.text().strip()
            temp_search = current_search if current_search else None
            
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
        if source is self.table.viewport():
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
            # Vérifier si au moins un fichier est un CSV
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith('.csv'):
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        """Gérer le mouvement d'un glisser/déposer"""
        if event.mimeData().hasUrls():
            # Vérifier si au moins un fichier est un CSV
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith('.csv'):
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event):
        """Gérer le déposer d'un fichier CSV"""
        if event.mimeData().hasUrls():
            csv_files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith('.csv'):
                        csv_files.append(file_path)
            
            if csv_files:
                # Traiter le premier fichier CSV trouvé
                self._import_csv_from_path(csv_files[0])
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
            results = self._process_import(imported_data, import_type, ref_piece, third_column_choice)
            
            # Affichage du résumé et ajout à l'historique
            self._show_import_summary(results, ref_piece)
            self._log_import_to_history(results, ref_piece, f"CSV (Glisser/Déposer - {os.path.basename(file_path)})")
            
        except Exception as e:
            self._show_error(f"Erreur lors de l'import CSV par glisser/déposer: {e}")

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
            self.load_data(self.search_input.text())
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
            self.load_data(self.search_input.text())
            
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
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text.strip():
            QMessageBox.information(self, "Collage", "Aucune donnée dans le presse-papiers")
            return
        
        try:
            # Séparer les lignes et colonnes
            rows = [row.split('\t') for row in clipboard_text.strip().split('\n')]
            if not rows:
                return

            # Demander une référence de pièce optionnelle
            ref_piece, ok1 = QInputDialog.getText(
                self, "Pièce Associée", 
                "Associer une référence de pièce pour ce lot (optionnel) :"
            )
            if not ok1:
                return
            
            # Récupérer les catégories disponibles
            categories = self.db_manager.get_categories()
            
            category = ""
            if categories:
                category, ok2 = QInputDialog.getItem(
                    self, "Catégorie", 
                    "Sélectionner une catégorie (optionnel):",
                    [""] + categories, 0, True
                )
                if not ok2:
                    return

            # Vérifier si on a 3 colonnes et demander le choix de destination
            third_column_choice = "other_ref"  # Valeur par défaut
            if any(len(row.split('\t')) == 3 for row in clipboard_text.strip().split('\n')):
                choice, ok3 = QInputDialog.getItem(
                    self, "3ème Colonne", 
                    "Où stocker la 3ème colonne ?",
                    ["Ignorer", "Autre référence", "Notes"], 0, False
                )
                if not ok3:
                    return
                if choice == "Ignorer":
                    third_column_choice = "ignore"
                elif choice == "Autre référence":
                    third_column_choice = "other_ref"
                elif choice == "Notes":
                    third_column_choice = "notes"
                else:  # Fallback
                    third_column_choice = "ignore"

            # Insérer les données
            inserted_count = 0
            updated_count = 0
            ignored_count = 0
            associations_created = 0  # Compter les vraies associations créées
            duplicates_skipped = 0   # Compter les associations déjà existantes
            total_rows = len(rows)
            
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
                    print(f"❌ REJET #{ignored_count + 1} - Ligne {row_idx + 1}: {num_cols} colonne(s) non supportée(s) (attendu: 2-3 ou 4+)")
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
                            self.db_manager.add_piece(ref_piece.strip(), appareil_id, "")
                            associations_created += 1
                            print(f"  🔗 Pièce {ref_piece.strip()} associée")
                        else:
                            duplicates_skipped += 1
                            print(f"  ⚠️ Pièce {ref_piece.strip()} déjà associée")
                    
                    updated_count += 1
                    
                else:
                    # Nouvel appareil - utiliser la même logique que l'import CSV
                    # Créer avec seulement les références essentielles pour éviter les appareils vides
                    ref_modele = appareil_data.get('ref_modele', '').strip()
                    commercial_ref = appareil_data.get('commercial_ref', '').strip()
                    
                    # Vérifier qu'on a au moins une référence valide
                    if ref_modele or commercial_ref:
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
                            
                            # Ajouter la pièce si spécifiée
                            if ref_piece and ref_piece.strip():
                                self.db_manager.add_piece(ref_piece.strip(), appareil_id, "")
                                associations_created += 1
                                print(f"  🔗 Pièce {ref_piece.strip()} associée")
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
            
            # Résumé détaillé pour debugging ET historique
            from src.core.config import pluralize
            detailed_summary = f"📊 Résumé de l'import par collage:\n"
            detailed_summary += f"  Total {pluralize(total_rows, 'ligne traitée')}\n"
            detailed_summary += f"  {pluralize(ignored_count, 'ligne rejetée')}\n"
            detailed_summary += f"  {pluralize(inserted_count, 'appareil nouveau', 'appareils nouveaux')}\n"
            detailed_summary += f"  {pluralize(updated_count, 'appareil mis à jour')}\n"
            detailed_summary += f"  {pluralize(associations_created, 'association créée')}\n"
            detailed_summary += f"  {pluralize(duplicates_skipped, 'doublon ignoré')}"
            
            print(f"\n{detailed_summary}")
            
            # Ajouter le résumé détaillé directement à l'historique
            self._add_to_history(detailed_summary)
            
            # Afficher la synthèse comme pour l'import CSV
            results = {
                'total_imported': total_rows - ignored_count,
                'matches_found': updated_count,
                'manual_completion': inserted_count if not ref_piece or not ref_piece.strip() else 0,
                'duplicates_skipped': duplicates_skipped,
                'new_entries': inserted_count,
                'associations_created': associations_created
            }
            
            # Utiliser la même méthode d'affichage que l'import CSV
            self._show_import_summary(results, ref_piece.strip() if ref_piece else None)
            
            # Note: Ne pas appeler _log_import_to_history ici pour éviter la duplication avec detailed_summary
            
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
        current_search = self.search_input.text()
        self.load_data(current_search)
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