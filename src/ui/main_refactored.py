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
from PyQt5.QtGui import QKeySequence, QPainter, QPen, QColor
from PyQt5.QtCore import QSize
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

    def _init_ui(self):
        """Initialiser l'interface utilisateur moderne"""
        self.setWindowTitle("📊 " + Config.WINDOW_TITLE)
        self.resize(Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)
        
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
            filter_input.setPlaceholderText(f"Filtrer {header}...")
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
        self.search_input.setPlaceholderText("Rechercher dans tous les champs et pièces...")
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
        self.pieces_tabs.addTab(self.pieces_list, "Pièces Associées")
        
        # Ajout de pièce
        pieces_add_widget = QWidget()
        pieces_add_layout = QVBoxLayout(pieces_add_widget)
        
        self.piece_input = QLineEdit()
        self.piece_input.setPlaceholderText("Référence de la pièce...")
        pieces_add_layout.addWidget(self.piece_input)
        
        add_piece_btn = QPushButton("Ajouter Pièce")
        add_piece_btn.clicked.connect(self._add_piece)
        pieces_add_layout.addWidget(add_piece_btn)
        
        pieces_add_layout.addStretch()
        self.pieces_tabs.addTab(pieces_add_widget, "Ajouter Pièce")
        
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
        
        # Bouton moderne pour rafraîchir
        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.setToolTip("Rafraîchir l'application")
        refresh_btn.clicked.connect(self._refresh_application)
        history_header_layout.addWidget(refresh_btn)
        
        history_layout.addLayout(history_header_layout)
        history_layout.setContentsMargins(8, 8, 8, 8)  # Padding moderne
        
        self.history_list = QListWidget()
        # Supprimer la limitation de hauteur pour permettre l'étirement
        # self.history_list.setMaximumHeight(150) 
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
        
        fill_btn = QPushButton("Compléter Type/Fabricant")
        fill_btn.clicked.connect(self._fill_empty_fields)
        btn_layout.addWidget(fill_btn)
        
        clean_btn = QPushButton("Supprimer Doublons/Lignes Vides")
        clean_btn.clicked.connect(self._clean_data)
        btn_layout.addWidget(clean_btn)
        
        # Bouton moderne pour afficher seulement les lignes incomplètes
        incomplete_btn = QPushButton("📋 Incomplètes")
        incomplete_btn.setToolTip("Afficher uniquement les lignes avec des champs vides")
        incomplete_btn.setCheckable(True)
        incomplete_btn.clicked.connect(self._toggle_incomplete_filter)
        incomplete_btn.setObjectName("incompleteBtn")
        btn_layout.addWidget(incomplete_btn)
        self.incomplete_filter_btn = incomplete_btn
        
        # Variable pour le filtre des incomplètes
        self.show_incomplete_only = False
        
        self.counter_label = QLabel("Lignes : 0")
        btn_layout.addWidget(self.counter_label)
        
        layout.addLayout(btn_layout)
        
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
        
        # Sélecteur de taille de page moderne
        size_label = QLabel("Afficher:")
        size_label.setObjectName("inlineLabel")
        pagination_layout.addWidget(size_label)
        
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["500", "1000", "2000", "5000", "Tout"])
        self.page_size_combo.setCurrentText(str(Config.DEFAULT_PAGE_SIZE))
        self.page_size_combo.currentTextChanged.connect(self._change_page_size)
        pagination_layout.addWidget(self.page_size_combo)
        
        pagination_layout.addStretch()
        
        # Indicateur de performance
        self.perf_label = QLabel("⚡ Prêt")
        self.perf_label.setObjectName("perfLabel")
        pagination_layout.addWidget(self.perf_label)
        
        pagination_section_layout.addLayout(pagination_layout)
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
        
        # Groupe Gestion
        categories_action = QAction("🏷️ Catégories", self)
        categories_action.setToolTip("Gérer les catégories d'appareils")
        categories_action.triggered.connect(self._manage_categories)
        toolbar.addAction(categories_action)
        
        notes_action = QAction("📄 Notes", self)
        notes_action.setToolTip("Éditer les notes de l'appareil sélectionné")
        notes_action.triggered.connect(self._edit_notes)
        toolbar.addAction(notes_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Données
        import_action = QAction("📈 Import", self)
        import_action.setToolTip("Importer des données depuis un fichier CSV")
        import_action.triggered.connect(self._import_csv)
        toolbar.addAction(import_action)
        
        validate_action = QAction("🔍 Valider & Incohérences", self)
        validate_action.setToolTip("Valider la cohérence de la base et détecter les incohérences")
        validate_action.triggered.connect(self._validate_and_detect_inconsistencies)
        toolbar.addAction(validate_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Outils
        logs_action = QAction("📊 Journal", self)
        logs_action.setToolTip("Ouvrir le visualiseur de logs")
        logs_action.triggered.connect(self._open_log_viewer)
        toolbar.addAction(logs_action)
        
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

    def load_data(self, search_term: str = None):
        """Charger les données depuis la base avec pagination"""
        import time
        start_time = time.time()
        
        try:
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
            
            # Déterminer si utiliser la pagination
            if self.use_pagination and self.total_rows > Config.MAX_DISPLAY_ROWS:
                # Calculer offset pour la pagination
                offset = self.current_page * self.page_size
                limit = self.page_size
                
                # Charger seulement la page courante avec tri
                records = self.db_manager.load_data(search_term, column_filters, limit, offset, sort_column, sort_order, incomplete_filter)
            else:
                # Charger toutes les données (pour les petites bases ou recherches) avec tri
                records = self.db_manager.load_data(search_term, column_filters, None, None, sort_column, sort_order, incomplete_filter)
            
            # Remplir le tableau
            self.table.setRowCount(len(records))
            for row_idx, record in enumerate(records):
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
            
            self.table.resizeColumnsToContents()
            self._update_counter()
            self._update_pagination_controls()
            
            # Afficher les performances
            load_time = time.time() - start_time
            if hasattr(self, 'perf_label'):
                self.perf_label.setText(f"⚡ {load_time:.2f}s ({len(records)} lignes)")
            
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
            padding: 4px 0px;
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
        }
        
        QComboBox:hover {
            border-color: #80bdff;
        }
        
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        
        QComboBox::down-arrow {
            image: none;
            border: 2px solid #6c757d;
            width: 6px;
            height: 6px;
            border-top: none;
            border-left: none;
        }
        
        /* ComboBox dropdown styles */
        QComboBox QAbstractItemView {
            background-color: white;
            border: 1px solid #ced4da;
            border-radius: 6px;
            outline: none;
            selection-background-color: #007bff;
        }
        
        QComboBox QAbstractItemView::item {
            padding: 4px 8px;
            border: none;
            color: #212529 !important;
            background-color: transparent;
        }
        
        QComboBox QAbstractItemView::item:selected {
            background-color: #007bff;
            color: white !important;
        }
        
        QComboBox QAbstractItemView::item:hover {
            background-color: #f8f9fa;
            color: #212529 !important;
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
                self.load_data(self.search_input.text())
    
    def _previous_page(self):
        """Aller à la page précédente"""
        if self.current_page > 0:
            self.current_page -= 1
            self.load_data(self.search_input.text())
    
    def _go_to_page(self, page: int):
        """Aller à une page spécifique"""
        if self.total_rows > 0:
            total_pages = (self.total_rows + self.page_size - 1) // self.page_size
            if 0 <= page < total_pages:
                self.current_page = page
                self.load_data(self.search_input.text())
    
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
            self.load_data(self.search_input.text())
            
        except ValueError:
            pass  # Ignorer les valeurs non valides
    
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
                2: 'ref_modele',     # Colonne C -> Référence Modèle
                3: 'commercial_ref', # Colonne D -> Référence Commerciale ✅
                4: 'other_ref',      # Colonne E -> Autre Référence
                5: 'category',       # Colonne F -> Catégorie
                6: 'notes'           # Colonne G -> Notes
            }
            return column_mapping.get(ui_column)
        else:
            # Colonne 7 = Nb Pièces (lecture seule, pas de champ DB correspondant)
            return None

    def _on_current_item_changed(self, current, previous):
        """Capturer la valeur précédente avant modification"""
        if previous:
            key = (previous.row(), previous.column())
            self.previous_values[key] = previous.text()
    
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
        """Rechercher dans le tableau"""
        search_term = text.strip()
        self.load_data(search_term if search_term else None)
        
        # Activer/désactiver les boutons d'export
        has_search = bool(search_term)
        self.export_csv_btn.setEnabled(has_search)
        self.export_html_brands_btn.setEnabled(has_search)
        self.export_html_details_btn.setEnabled(has_search)

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
        """Mettre à jour le panneau des pièces"""
        self.pieces_list.clear()
        
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        
        try:
            db_id = self._get_db_id_from_row(current_row)
            pieces = self.db_manager.get_pieces_for_appareil(db_id)
            
            for ref_piece, description in pieces:
                item_text = ref_piece
                if description:
                    item_text += f" - {description}"
                
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, ref_piece)
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
                    
                    # Ajouter la pièce sans description
                    self.db_manager.add_piece(ref_piece, db_id, None)
                    added_count += 1
                    
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
                history_message = f"Pièce '{ref_piece}' ajoutée à {added_count} appareil(s)"
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
                # Logique d'import à implémenter
                self._show_info("Fonctionnalité d'import à implémenter")
            except Exception as e:
                self._show_error(f"Erreur lors de l'import: {e}")

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
                "Entrer une référence de pièce pour ce lot (optionnel):"
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
                    ["Autre Référence", "Notes", "Ignorer"], 0, False
                )
                if not ok3:
                    return
                if choice == "Autre Référence":
                    third_column_choice = "other_ref"
                elif choice == "Notes":
                    third_column_choice = "notes"
                else:  # Ignorer
                    third_column_choice = "ignore"

            # Insérer les données
            inserted_count = 0
            ignored_count = 0
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
                    print(f"⚠️ Ligne {row_idx + 1} ignorée : {num_cols} colonne(s) non supportée(s) (attendu: 2-3 ou 4+)")
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
                    print(f"⚠️ Ligne {row_idx + 1}: {validation_result.error_message} - Continuant l'import...")
                    # Continue au lieu d'arrêter l'import
                
                # Essayer de compléter automatiquement Type et Fabricant si vides
                if not appareil_data.get('type') or not appareil_data.get('manufacturer'):
                    self._try_auto_complete(appareil_data)
                
                # Insérer l'appareil
                appareil_id = self.db_manager.insert_appareil(appareil_data)
                inserted_count += 1
                
                # Ajouter la pièce si spécifiée
                if ref_piece and ref_piece.strip():
                    self.db_manager.add_piece(ref_piece.strip(), appareil_id)
            
            # Fermer la barre de progression
            if progress_dialog:
                progress_dialog.setValue(total_rows)
                progress_dialog.close()
            
            # Forcer le rafraîchissement et afficher le résultat
            self._force_refresh_display(reset_page=True, clear_filters=True)
            self.statusbar.showMessage(
                f"✅ {inserted_count} ligne(s) ajoutée(s) depuis le presse-papiers", 
                Config.LONG_STATUS_MESSAGE_TIMEOUT
            )
            
            # Ajouter à l'historique
            history_message = f"Collage: {inserted_count} appareil(s) ajouté(s)"
            if ignored_count > 0:
                history_message += f", {ignored_count} ligne(s) ignorée(s)"
            if ref_piece:
                history_message += f", pièce '{ref_piece}' associée"
            if category:
                history_message += f", catégorie '{category}'"
            
            self._add_to_history(history_message)
            
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