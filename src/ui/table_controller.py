"""
Table Controller - Phase 2 Refactoring
Gestion centralisée du tableau, filtres, pagination et tri
"""

from typing import List, Dict, Optional, Tuple, Any
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                            QTableWidgetItem, QLineEdit, QComboBox, QPushButton,
                            QLabel, QProgressDialog, QApplication, QHeaderView)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush

from ..core.config import Config
from ..core.logger import app_logger
from ..data.database_manager import DatabaseManager


class CustomTableWidget(QTableWidget):
    """Table personnalisée avec gestion des touches Delete/Backspace et auto-complétion"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_manager = None
        
    def set_db_manager(self, db_manager):
        """Définir le gestionnaire de base de données pour l'auto-complétion"""
        self.db_manager = db_manager


class TableController:
    """Contrôleur pour la gestion du tableau principal"""
    
    def __init__(self, parent_window, db_manager: DatabaseManager):
        self.parent_window = parent_window
        self.db_manager = db_manager
        
        # Variables de pagination
        self.current_page = 1
        self.page_size = 100
        self.total_pages = 1
        self.total_rows = 0
        
        # Variables de tri
        self.current_sort_column = -1
        self.current_sort_order = Qt.AscendingOrder
        
        # Variables de filtres
        self.filter_widgets = {}
        self.column_filter_timer = QTimer()
        self.column_filter_timer.setSingleShot(True)
        self.column_filter_timer.timeout.connect(self._perform_delayed_column_filter)
        self.pending_column_filter = None
        
        # Référence vers le widget table (sera initialisée par create_table_widget)
        self.table = None
        self.filter_widget = None
        self.filter_layout = None
        
        # Labels de pagination (seront initialisés par create_table_widget)
        self.page_label = None
        self.size_label = None
        
    def create_table_widget(self) -> QWidget:
        """Créer le widget complet du tableau avec filtres et pagination"""
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
        self.table.set_db_manager(self.db_manager)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QTableWidget.DragDropMode.DropOnly)
        
        # Configurer le tri
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_click)
        
        # Appliquer la visibilité des colonnes
        self._apply_column_visibility()
        
        layout.addWidget(self.table)
        
        # Contrôles de pagination
        self._add_pagination_controls(layout)
        
        return widget
    
    def load_data(self, search_term: str = None, is_search: bool = False):
        """Charger les données dans le tableau avec pagination et filtres"""
        import time
        start_time = time.time()
        
        try:
            # Calculer les paramètres de pagination
            if self.page_size == -1:  # "Tout" sélectionné
                limit = None
                offset = None
            else:
                limit = self.page_size
                offset = (self.current_page - 1) * self.page_size
            
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
            incomplete_filter = getattr(self.parent_window, 'show_incomplete_only', False)
            
            # Compter le total pour la pagination
            self.total_rows = self.db_manager.count_data(search_term, column_filters, incomplete_filter=incomplete_filter)
            
            if self.page_size == -1:  # Mode "Tout"
                self.total_pages = 1
                self.current_page = 1
            else:
                self.total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
                if self.current_page > self.total_pages:
                    self.current_page = self.total_pages
            
            # Charger les données
            if self.page_size == -1 and self.total_rows > 5000:
                # Mode "Tout" avec beaucoup de données - utiliser chunked loading
                records = self.db_manager.load_data(search_term, column_filters, limit, offset, 
                                                   self.current_sort_column, self.current_sort_order, incomplete_filter)
                self._fill_table_chunked(records, None, search_term)
            else:
                # Chargement normal
                records = self.db_manager.load_data(search_term, column_filters, limit, offset, 
                                                   self.current_sort_column, self.current_sort_order, incomplete_filter)
                if self.total_rows > 1000:
                    self._fill_table_chunked(records, None, search_term)
                else:
                    self._fill_table_standard(records, None, search_term)
            
            # Mettre à jour les contrôles de pagination
            self._update_pagination_controls()
            
            # Performance logging
            elapsed = time.time() - start_time
            app_logger.debug(f"Table loaded: {len(records) if 'records' in locals() else 0} records in {elapsed:.3f}s")
            
        except Exception as e:
            app_logger.error(f"Erreur lors du chargement des données: {e}")
            self.table.setRowCount(0)
    
    def _fill_table_chunked(self, records: List, progress_dialog, search_term):
        """Remplir le tableau par chunks pour de gros volumes"""
        if not records:
            self.table.setRowCount(0)
            return
            
        self.table.blockSignals(True)
        self.table.setRowCount(len(records))
        
        chunk_size = 100
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            for j, record in enumerate(chunk):
                row_idx = i + j
                self._fill_single_row(row_idx, record, search_term)
            
            # Permettre à l'interface de se mettre à jour
            QApplication.processEvents()
        
        self.table.blockSignals(False)
        self._update_row_numbers()
    
    def _fill_table_standard(self, records: List, progress_dialog, search_term):
        """Remplir le tableau de manière standard"""
        if not records:
            self.table.setRowCount(0)
            return
            
        self.table.blockSignals(True)
        self.table.setRowCount(len(records))
        
        for row_idx, record in enumerate(records):
            self._fill_single_row(row_idx, record, search_term)
        
        self.table.blockSignals(False)
        self._update_row_numbers()
    
    def _fill_single_row(self, row_idx: int, record, search_term):
        """Remplir une seule ligne du tableau"""
        try:
            # Récupérer l'ID de la base de données depuis le record
            db_id = record[0] if len(record) > 0 else -1
            
            # Remplir chaque colonne
            for col_idx in range(min(len(Config.UI_HEADERS), len(record) - 1)):
                # Décaler l'index car record[0] = id
                value_idx = col_idx + 1
                if value_idx < len(record):
                    item = self._create_table_item(record, col_idx, db_id, search_term)
                    self.table.setItem(row_idx, col_idx, item)
        except Exception as e:
            app_logger.error(f"Erreur remplissage ligne {row_idx}: {e}")
    
    def _create_table_item(self, record, col_idx: int, db_id: int, search_term) -> QTableWidgetItem:
        """Créer un item du tableau avec le formatage approprié"""
        value_idx = col_idx + 1  # Décaler car record[0] = id
        value = record[value_idx] if value_idx < len(record) else ""
        
        # Formater la valeur selon le type de colonne
        if col_idx == len(Config.UI_HEADERS) - 1:  # Colonne "Nb Pièces"
            try:
                count = int(value) if value else 0
                display_value = str(count)
            except (ValueError, TypeError):
                display_value = "0"
        else:
            display_value = str(value) if value is not None else ""
        
        item = QTableWidgetItem(display_value)
        item.setData(Qt.UserRole, db_id)  # Stocker l'ID de la DB
        
        # Appliquer la mise en évidence si nécessaire
        if search_term:
            self._apply_search_highlight(item, search_term)
        
        return item
    
    def _apply_search_highlight(self, item: QTableWidgetItem, search_term):
        """Appliquer la mise en évidence pour les termes de recherche"""
        if not search_term or not item.text():
            return
        
        text = item.text().lower()
        search_lower = str(search_term).lower()
        
        if search_lower in text:
            # Surligner en jaune
            item.setBackground(QBrush(QColor(255, 255, 0, 100)))
    
    def _update_row_numbers(self):
        """Mettre à jour les numéros de lignes après un tri"""
        try:
            for row in range(self.table.rowCount()):
                self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
            app_logger.debug(f"Numéros de lignes mis à jour pour {self.table.rowCount()} lignes")
        except Exception as e:
            app_logger.error(f"Erreur lors de la mise à jour des numéros de lignes: {e}")
    
    def _apply_column_visibility(self):
        """Appliquer la visibilité des colonnes selon la configuration"""
        try:
            for col_config in Config.COLUMN_CONFIG:
                col_idx = col_config["index"]
                is_visible = col_config["visible"]
                if col_idx < self.table.columnCount():
                    if is_visible:
                        self.table.showColumn(col_idx)
                    else:
                        self.table.hideColumn(col_idx)
        except Exception as e:
            app_logger.error(f"Erreur application visibilité colonnes: {e}")
    
    def _on_header_click(self, logical_index: int):
        """Gestionnaire de clic sur les en-têtes pour le tri"""
        try:
            if self.current_sort_column == logical_index:
                # Inverser l'ordre si même colonne
                self.current_sort_order = Qt.DescendingOrder if self.current_sort_order == Qt.AscendingOrder else Qt.AscendingOrder
            else:
                # Nouvelle colonne, ordre croissant par défaut
                self.current_sort_column = logical_index
                self.current_sort_order = Qt.AscendingOrder
            
            self._apply_database_sort()
        except Exception as e:
            app_logger.error(f"Erreur lors du tri: {e}")
    
    def _apply_database_sort(self):
        """Appliquer le tri au niveau de la base de données"""
        try:
            # Recharger les données avec le nouveau tri
            search_term = getattr(self.parent_window, 'current_search_term', None)
            self.load_data(search_term)
            self._update_sort_indicators()
        except Exception as e:
            app_logger.error(f"Erreur lors de l'application du tri: {e}")
    
    def _update_sort_indicators(self):
        """Mettre à jour les indicateurs visuels de tri"""
        try:
            if self.current_sort_column >= 0:
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column, self.current_sort_order
                )
        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateurs tri: {e}")
    
    def _add_pagination_controls(self, layout: QVBoxLayout):
        """Ajouter les contrôles de pagination"""
        pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(pagination_widget)
        
        # Bouton page précédente
        prev_btn = QPushButton("◀ Précédent")
        prev_btn.clicked.connect(self._previous_page)
        pagination_layout.addWidget(prev_btn)
        
        # Label page actuelle
        self.page_label = QLabel("Page 1 sur 1")
        pagination_layout.addWidget(self.page_label)
        
        # Bouton page suivante
        next_btn = QPushButton("Suivant ▶")
        next_btn.clicked.connect(self._next_page)
        pagination_layout.addWidget(next_btn)
        
        pagination_layout.addStretch()
        
        # Sélecteur taille de page
        size_label = QLabel("Lignes par page:")
        pagination_layout.addWidget(size_label)
        
        size_combo = QComboBox()
        size_combo.addItems(["25", "50", "100", "200", "500", "Tout"])
        size_combo.setCurrentText("100")
        size_combo.currentTextChanged.connect(self._change_page_size)
        pagination_layout.addWidget(size_combo)
        
        self.size_label = QLabel(f"Total: {self.total_rows} lignes")
        pagination_layout.addWidget(self.size_label)
        
        layout.addWidget(pagination_widget)
    
    def _update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination"""
        try:
            if self.page_label:
                self.page_label.setText(f"Page {self.current_page} sur {self.total_pages}")
            if self.size_label:
                self.size_label.setText(f"Total: {self.total_rows} lignes")
        except Exception as e:
            app_logger.error(f"Erreur mise à jour pagination: {e}")
    
    def _next_page(self):
        """Aller à la page suivante"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            search_term = getattr(self.parent_window, 'current_search_term', None)
            self.load_data(search_term)
    
    def _previous_page(self):
        """Aller à la page précédente"""
        if self.current_page > 1:
            self.current_page -= 1
            search_term = getattr(self.parent_window, 'current_search_term', None)
            self.load_data(search_term)
    
    def _go_to_page(self, page: int):
        """Aller à une page spécifique"""
        if 1 <= page <= self.total_pages:
            self.current_page = page
            search_term = getattr(self.parent_window, 'current_search_term', None)
            self.load_data(search_term)
    
    def _change_page_size(self, size_text: str):
        """Changer la taille de page"""
        if size_text == "Tout":
            self.page_size = -1
        else:
            try:
                self.page_size = int(size_text)
            except ValueError:
                self.page_size = 100
        
        self.current_page = 1  # Reset à la première page
        search_term = getattr(self.parent_window, 'current_search_term', None)
        self.load_data(search_term)
    
    def _apply_column_filter(self, column: int, text: str):
        """Appliquer un filtre sur une colonne avec debounce de 400ms"""
        self.pending_column_filter = (column, text)
        self.column_filter_timer.stop()
        self.column_filter_timer.start(400)  # 400ms de délai
    
    def _perform_delayed_column_filter(self):
        """Exécuter le filtrage de colonne après le délai de debounce"""
        if hasattr(self, 'pending_column_filter') and self.pending_column_filter:
            column, text = self.pending_column_filter
            
            # Effectuer le filtrage réel
            search_term = getattr(self.parent_window, 'current_search_term', None)
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
    
    def clear_column_filters(self):
        """Nettoyer tous les filtres de colonnes"""
        for col_idx, filter_widget in self.filter_widgets.items():
            if filter_widget is not None:  # Skip removed filters
                filter_widget.blockSignals(True)
                if isinstance(filter_widget, QComboBox):
                    filter_widget.setCurrentText("")
                else:  # QLineEdit
                    filter_widget.clear()
                filter_widget.blockSignals(False)
    
    def get_selected_row_ids(self) -> List[int]:
        """Obtenir les IDs des lignes sélectionnées"""
        selected_ids = []
        for item in self.table.selectedItems():
            if item.column() == 0:  # Première colonne
                db_id = item.data(Qt.UserRole)
                if db_id is not None:
                    selected_ids.append(db_id)
        return selected_ids
    
    def get_db_id_from_row(self, row: int) -> int:
        """Récupérer l'ID de base de données d'une ligne"""
        try:
            item = self.table.item(row, 0)
            if item:
                return item.data(Qt.UserRole) or -1
            return -1
        except Exception:
            return -1