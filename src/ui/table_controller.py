"""
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
from ..services.pieces_count_service import PiecesCountService
from ..services.table_widget_service import CustomTableWidget, TableWidgetService




class TableController:
    """Contrôleur pour la gestion du tableau principal"""
    
    def __init__(self, parent_window, db_manager: DatabaseManager):
        self.parent_window = parent_window
        self.db_manager = db_manager
        self.pieces_count_service = PiecesCountService(db_manager)
        self.table_widget_service = TableWidgetService(db_manager)
        
        # Variables de pagination
        self.current_page = 1
        self.page_size = 1000
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
        
        # Timer pour recherche automatique (800ms)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_delayed_search)
        self.pending_search_term = None
        self.current_search_term = None  # Terme de recherche persistant pour pagination
        
        # Référence vers le widget table (sera initialisée par create_table_widget)
        self.table = None
        self.filter_widget = None
        self.filter_layout = None
        
        # Labels de pagination (seront initialisés par create_table_widget)
        self.page_label = None
        self.size_label = None
        
    def create_table_widget(self) -> QWidget:
        """Créer le widget complet du tableau avec barre de recherche, filtres et pagination"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Barre de recherche supprimée d'ici - maintenant sous le tableau
        
        # Filtres par colonne prenant toute la largeur disponible
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(2)  # Petit espacement entre les filtres
        
        for i, header in enumerate(Config.UI_HEADERS):
            # Skip filters for invisible or useless columns
            if i == 7:  # "Nb Pièces" column
                continue
            if i == 5 or i == 6:  # "Catégorie" et "Notes" - inutiles
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
        self.table = self.table_widget_service.create_custom_table()
        self.table.setColumnCount(len(Config.UI_HEADERS))
        self.table.setHorizontalHeaderLabels(Config.UI_HEADERS)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QTableWidget.DragDropMode.DropOnly)
        
        # Configurer le tri
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_click)
        
        # Log des largeurs de colonnes quand elles sont modifiées
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)
        
        # Appliquer la visibilité des colonnes
        self._apply_column_visibility()
        
        # Définir les largeurs par défaut des colonnes
        self._set_default_column_widths()
        
        layout.addWidget(self.table)
        
        # Barre de recherche SOUS le tableau (position correcte)
        search_layout2 = QHBoxLayout()
        search_label2 = QLabel("🔍 Recherche avancée:")
        search_layout2.addWidget(search_label2)
        
        self.advanced_search_input = QLineEdit()
        self.advanced_search_input.setPlaceholderText("Recherche avancée: 'terme1 && terme2' ou 'terme1 || terme2'...")
        # Sera connecté par MainWindow à AdvancedSearchService  
        # self.advanced_search_input.textChanged.connect(self._on_advanced_search_changed)
        search_layout2.addWidget(self.advanced_search_input)
        
        clear_search_btn = QPushButton("Effacer")
        clear_search_btn.clicked.connect(self._clear_advanced_search)
        search_layout2.addWidget(clear_search_btn)
        
        layout.addLayout(search_layout2)
        
        # Boutons d'export (si le service UI est disponible)
        if hasattr(self, 'ui_component_service') and self.ui_component_service:
            self.ui_component_service.add_export_buttons(layout)
        
        # Contrôles de pagination
        self._add_pagination_controls(layout)
        
        # Bouton pour lignes incomplètes
        self._add_incomplete_filter_button(layout)
        
        return widget
    
    def connect_selection_signals(self, on_selection_changed_callback):
        """Connecter les signaux de sélection du tableau à un callback"""
        if self.table:
            self.table.itemSelectionChanged.connect(on_selection_changed_callback)
            self.table.currentCellChanged.connect(lambda: on_selection_changed_callback())
    
    def load_data(self, search_term: str = None, is_search: bool = False):
        """Charger les données dans le tableau avec pagination et filtres"""
        import time
        start_time = time.time()
        
        try:
            # Réinitialiser le tri seulement si c'est une nouvelle recherche ET qu'on n'est pas en train de faire un tri
            # Ne pas réinitialiser si c'est un appel depuis _apply_database_sort
            if (is_search and 
                search_term != getattr(self, 'previous_search_term', None) and 
                not getattr(self, '_sorting_in_progress', False)):
                self.current_sort_column = -1
                self.current_sort_order = Qt.AscendingOrder
                self.previous_search_term = search_term
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
            
            # Gérer les recherches avancées (dict parsé) ou normales (string)
            if search_term and isinstance(search_term, dict):
                # Terme déjà parsé par AdvancedSearchService
                self.total_rows = self.db_manager.count_data(search_term, column_filters, incomplete_filter=incomplete_filter)
            elif search_term and isinstance(search_term, str) and ('&&' in search_term or '||' in search_term):
                # Terme brut à parser 
                if hasattr(self.parent_window, 'advanced_search_service'):
                    parsed_term = self.parent_window.advanced_search_service.parse_advanced_search(search_term)
                    self.total_rows = self.db_manager.count_data(parsed_term, column_filters, incomplete_filter=incomplete_filter)
                else:
                    # Fallback terme brut
                    self.total_rows = self.db_manager.count_data(search_term, column_filters, incomplete_filter=incomplete_filter)
            else:
                # Compter le total pour la pagination (recherche simple)
                self.total_rows = self.db_manager.count_data(search_term, column_filters, incomplete_filter=incomplete_filter)
            
            if self.page_size == -1:  # Mode "Tout"
                self.total_pages = 1
                self.current_page = 1
            else:
                self.total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
                if self.current_page > self.total_pages:
                    self.current_page = self.total_pages
            
            # Charger les données selon le type de recherche (même logique que count)
            if search_term and isinstance(search_term, dict):
                # Terme déjà parsé par AdvancedSearchService
                records = self.db_manager.load_data(search_term, column_filters, limit, offset, 
                                                   self.current_sort_column, self.current_sort_order, incomplete_filter)
            elif search_term and isinstance(search_term, str) and ('&&' in search_term or '||' in search_term):
                # Terme brut à parser
                if hasattr(self.parent_window, 'advanced_search_service'):
                    parsed_term = self.parent_window.advanced_search_service.parse_advanced_search(search_term)
                    records = self.db_manager.load_data(parsed_term, column_filters, limit, offset, 
                                                       self.current_sort_column, self.current_sort_order, incomplete_filter)
                else:
                    # Fallback
                    records = self.db_manager.load_data(search_term, column_filters, limit, offset, 
                                                       self.current_sort_column, self.current_sort_order, incomplete_filter)
            else:
                # Chargement normal via db_manager (recherche simple)
                records = self.db_manager.load_data(search_term, column_filters, limit, offset, 
                                                   self.current_sort_column, self.current_sort_order, incomplete_filter)
            
            # Remplir le tableau
            if self.total_rows > 1000:
                self.parent_window.table_fill_service.fill_table_chunked(self.table, records, None, search_term)
            else:
                self.parent_window.table_fill_service.fill_table_standard(self.table, records, None, search_term)
            
            # Mettre à jour les contrôles de pagination
            self._update_pagination_controls()
            
            # Mettre à jour les indicateurs de tri pour s'assurer qu'ils sont corrects
            self._update_sort_indicators()
            
            # Initialiser les valeurs précédentes pour le tracking des modifications
            if hasattr(self.parent_window, '_init_previous_values'):
                self.parent_window._init_previous_values()
            
            # Performance logging
            elapsed = time.time() - start_time
            app_logger.debug(f"Table loaded: {len(records) if 'records' in locals() else 0} records in {elapsed:.3f}s")
            
        except Exception as e:
            app_logger.error(f"Erreur lors du chargement des données: {e}")
            self.table.setRowCount(0)
    
    
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
    
    def _set_default_column_widths(self):
        """Définir les largeurs par défaut des colonnes"""
        try:
            # Largeurs optimisées selon les préférences utilisateur
            # Basé sur les ajustements manuels : 2025-09-01 09:01:21
            default_widths = {
                0: 120,  # Type
                1: 124,  # Fabricant
                2: 150,  # Référence Modèle
                3: 214,  # Référence Commerciale
                4: 166,  # Autre Référence
                5: 100,  # Catégorie (peut être cachée)
                6: 200,  # Notes (peut être cachée)
                7: 52,   # Nb Pièces
            }
            
            app_logger.debug("Configuration largeurs colonnes par défaut...")
            
            # Appliquer les largeurs
            for col_index, width in default_widths.items():
                if col_index < self.table.columnCount():
                    self.table.setColumnWidth(col_index, width)
                    col_name = Config.UI_HEADERS[col_index] if col_index < len(Config.UI_HEADERS) else f"Col{col_index}"
                    app_logger.debug(f"Largeur définie: {col_name} = {width}px")
            
            # Log des largeurs appliquées
            current_widths = []
            for i in range(self.table.columnCount()):
                width = self.table.columnWidth(i)
                col_name = Config.UI_HEADERS[i] if i < len(Config.UI_HEADERS) else f"Col{i}"
                current_widths.append(f"{col_name}:{width}")
            
            app_logger.debug(f"🎯 LARGEURS PAR DÉFAUT APPLIQUÉES: {', '.join(current_widths)}")
            
        except Exception as e:
            app_logger.error(f"Erreur définition largeurs par défaut: {e}")
    
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
            # Marquer qu'un tri est en cours pour éviter la réinitialisation
            self._sorting_in_progress = True
            
            # Récupérer le terme de recherche actif de manière robuste
            search_term = None
            
            # 1. Essayer pending_search_term (recherche avec opérateurs || &&)
            if hasattr(self.parent_window, 'pending_search_term') and self.parent_window.pending_search_term:
                search_term = self.parent_window.pending_search_term
            # 2. Sinon, utiliser current_search_term persistant du TableController
            elif hasattr(self, 'current_search_term') and self.current_search_term:
                search_term = self.current_search_term
            # 3. En dernier recours, prendre le texte direct de la barre de recherche
            elif hasattr(self.parent_window, 'search_input') and self.parent_window.search_input:
                text = self.parent_window.search_input.text().strip()
                search_term = text if text else None
            
            # Convertir Qt.SortOrder en string pour la DB
            sort_order_str = "ASC" if self.current_sort_order == Qt.AscendingOrder else "DESC"
            print(f"🔄 Tri appliqué avec recherche: '{search_term}' (colonne {self.current_sort_column}, ordre {sort_order_str})")
            
            # Appeler load_data avec les bonnes valeurs
            self._load_data_with_sort(search_term, self.current_sort_column, sort_order_str)
            self._update_sort_indicators()
        except Exception as e:
            app_logger.error(f"Erreur lors de l'application du tri: {e}")
        finally:
            # Nettoyer le flag de tri en cours
            self._sorting_in_progress = False
    
    def _load_data_with_sort(self, search_term: str, sort_column: int, sort_order_str: str):
        """Charger les données avec tri spécifique sans passer par load_data standard"""
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
            
            # Détecter si c'est une recherche avancée parsée (soit dict, soit string contenant 'type': 'or'/'and')
            is_advanced_search = (isinstance(search_term, dict) or 
                                (isinstance(search_term, str) and ("'type': 'or'" in search_term or "'type': 'and'" in search_term)))
            
            if is_advanced_search:
                # Si c'est une string, on doit la reconvertir en dict pour l'utiliser avec la DB
                if isinstance(search_term, str):
                    # Essayer de retrouver le terme parsé original via AdvancedSearchService
                    if hasattr(self.parent_window, 'advanced_search_service'):
                        # Retrouver le terme original depuis la string
                        if "'original':" in search_term:
                            import re
                            match = re.search(r"'original': '([^']+)'", search_term)
                            if match:
                                original_term = match.group(1)
                                search_term = self.parent_window.advanced_search_service.parse_advanced_search(original_term)
                
                # Désactiver temporairement le cache pour cette requête triée
                cache_backup = self.db_manager.search_cache
                self.db_manager.search_cache = None
                
                try:
                    records = self.db_manager.load_data(
                        search_term, column_filters, limit, offset, 
                        sort_column, sort_order_str, incomplete_filter
                    )
                finally:
                    # Restaurer le cache
                    self.db_manager.search_cache = cache_backup
            else:
                # Appel normal avec cache pour les recherches simples
                records = self.db_manager.load_data(
                    search_term, column_filters, limit, offset, 
                    sort_column, sort_order_str, incomplete_filter
                )
            
            # Remplir le tableau
            if self.total_rows > 1000:
                self.parent_window.table_fill_service.fill_table_chunked(self.table, records, None, search_term)
            else:
                self.parent_window.table_fill_service.fill_table_standard(self.table, records, None, search_term)
            
            # Mettre à jour les contrôles de pagination
            self._update_pagination_controls()
            
        except Exception as e:
            app_logger.error(f"Erreur lors du chargement avec tri: {e}")
    
    def _update_sort_indicators(self):
        """Mettre à jour les indicateurs visuels de tri"""
        try:
            if self.current_sort_column >= 0:
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column, self.current_sort_order
                )
        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateurs tri: {e}")

    # === Gestion des mises à jour de la colonne Nb Pièces ===
    
    def find_row_by_db_id(self, db_id: int) -> Optional[int]:
        """Trouver le numéro de ligne correspondant à un ID d'appareil"""
        return self.pieces_count_service.find_row_by_db_id(self.table, db_id)
    
    def update_pieces_count_for_rows(self, rows: set):
        """Mettre à jour la colonne Nb Pièces pour les lignes spécifiées"""
        self.pieces_count_service.update_pieces_count_for_rows(self.table, rows)

    def refresh_pieces_count_column(self):
        """Rafraîchir la colonne Nb Pièces pour toutes les lignes visibles"""
        self.pieces_count_service.refresh_entire_pieces_column(self.table)
    
    def get_pieces_count_summary(self):
        """Obtenir un résumé du comptage des pièces dans le tableau"""
        return self.pieces_count_service.get_pieces_count_summary(self.table)
    
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
        size_combo.addItems(["100", "250", "500", "1000", "2000", "Tout"])
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
            # Utiliser le terme de recherche persistant pour pagination
            search_term = getattr(self, 'current_search_term', None)
            self.load_data(search_term)
    
    def _previous_page(self):
        """Aller à la page précédente"""
        if self.current_page > 1:
            self.current_page -= 1
            # Utiliser le terme de recherche persistant pour pagination
            search_term = getattr(self, 'current_search_term', None)
            self.load_data(search_term)
    
    def _go_to_page(self, page: int):
        """Aller à une page spécifique"""
        if 1 <= page <= self.total_pages:
            self.current_page = page
            # Utiliser le terme de recherche persistant pour pagination
            search_term = getattr(self, 'current_search_term', None)
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
        # Utiliser le terme de recherche persistant pour changement taille page
        search_term = getattr(self, 'current_search_term', None)
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
            
            # Effectuer le filtrage réel - utiliser terme persistant
            search_term = getattr(self, 'current_search_term', None)
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
                try:
                    filter_widget.blockSignals(True)
                    if isinstance(filter_widget, QComboBox):
                        filter_widget.setCurrentText("")
                    else:  # QLineEdit
                        filter_widget.clear()
                    filter_widget.blockSignals(False)
                except RuntimeError:
                    # Le widget a été supprimé, on le retire de la liste
                    self.filter_widgets[col_idx] = None
    
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
    
    def _on_search_text_changed(self, text: str):
        """Gestionnaire de changement du texte de recherche"""
        # Pour l'instant, pas de recherche automatique - seulement sur bouton
        pass
    
    def _perform_search(self):
        """Effectuer la recherche"""
        search_term = self.search_input.text().strip()
        self.load_data(search_term, is_search=True)
    
    def _clear_search(self):
        """Effacer la recherche - délégué vers AdvancedSearchService"""
        if hasattr(self.parent_window, 'advanced_search_service'):
            self.parent_window.advanced_search_service.clear_search_ui(self.parent_window)
        else:
            # Fallback direct si le service n'est pas disponible
            if hasattr(self, 'search_input') and self.search_input is not None:
                try:
                    self.search_input.clear()
                except RuntimeError:
                    # Le widget a été supprimé, on ignore silencieusement
                    pass
            self.load_data(None, is_search=False)
    
    def _add_export_buttons(self, layout):
        """Ajouter les boutons d'export - délégué vers MainWindow"""
        if hasattr(self.parent_window, '_add_export_buttons'):
            self.parent_window._add_export_buttons(layout)
    
    def _on_advanced_search_changed(self, text: str):
        """Gestionnaire de changement du texte de recherche avancée avec timer automatique"""
        search_term = text.strip()
        
        # Stocker le terme original - le parsing sera fait dans load_data si nécessaire
        self.pending_search_term = search_term
            
        self.search_timer.stop()
        self.search_timer.start(800)  # 800ms de délai pour recherche automatique
    
    def _perform_delayed_search(self):
        """Effectuer la recherche après le délai"""
        if self.pending_search_term is not None:
            search_term = self.pending_search_term if self.pending_search_term else None
            # STOCKER le terme pour la pagination AVANT de le remettre à None
            self.current_search_term = search_term
            self.load_data(search_term, is_search=bool(search_term))
            
            # Mettre à jour l'état des boutons d'export via le parent
            if hasattr(self.parent_window, '_update_export_buttons_state'):
                # Passer le terme original pour l'évaluation des boutons d'export
                self.parent_window._update_export_buttons_state(search_term)
            
            self.pending_search_term = None
    
    def _clear_advanced_search(self):
        """Effacer la recherche avancée"""
        # Vérifier si le widget existe encore avant de l'utiliser
        if hasattr(self, 'advanced_search_input') and self.advanced_search_input is not None:
            try:
                self.advanced_search_input.clear()
            except RuntimeError:
                # Le widget a été supprimé, on ignore silencieusement
                pass
        
        self.current_search_term = None  # Nettoyer aussi le terme persistant
        self.load_data(None, is_search=False)
        
        # Désactiver les boutons d'export quand on vide la recherche
        if hasattr(self.parent_window, '_update_export_buttons_state'):
            self.parent_window._update_export_buttons_state("")
    
    def _add_incomplete_filter_button(self, layout):
        """Ajouter le bouton de filtre pour les lignes incomplètes"""
        from PyQt5.QtWidgets import QPushButton, QHBoxLayout
        from ..core.config import pluralize
        
        # Layout centré pour le bouton
        incomplete_layout = QHBoxLayout()
        incomplete_layout.addStretch()  # Centrer le bouton
        
        # Bouton pour afficher seulement les lignes incomplètes
        self.incomplete_filter_btn = QPushButton("📋 Lignes à traiter")
        self.incomplete_filter_btn.setToolTip("Afficher uniquement les lignes avec des champs vides")
        self.incomplete_filter_btn.setCheckable(True)
        self.incomplete_filter_btn.clicked.connect(self.parent_window._toggle_incomplete_filter)
        self.incomplete_filter_btn.setObjectName("incompleteBtn")
        incomplete_layout.addWidget(self.incomplete_filter_btn)
        
        incomplete_layout.addStretch()  # Centrer le bouton
        layout.addLayout(incomplete_layout)
        
        # Mettre à jour la visibilité
        self._update_incomplete_button_visibility()
    
    def _toggle_incomplete_filter(self, checked: bool):
        """Basculer le filtre pour afficher seulement les lignes incomplètes"""
        if hasattr(self.parent_window, 'show_incomplete_only'):
            self.parent_window.show_incomplete_only = checked
            
            # Recharger les données avec le filtre - garder la recherche actuelle
            current_search = getattr(self.parent_window, 'search_input', None)
            search_term = current_search.text() if current_search else None
            
            self.load_data(search_term, is_search=bool(search_term and search_term.strip()))
            self._update_incomplete_button_visibility()
    
    def _update_incomplete_button_visibility(self):
        """Mettre à jour la visibilité du bouton incomplètes selon les données"""
        from ..core.config import pluralize
        try:
            incomplete_count = self.db_manager.count_incomplete_devices() if hasattr(self.db_manager, 'count_incomplete_devices') else 0
            show_incomplete_only = getattr(self.parent_window, 'show_incomplete_only', False)
            
            if hasattr(self, 'incomplete_filter_btn'):
                if incomplete_count > 0:
                    self.incomplete_filter_btn.show()
                    self.incomplete_filter_btn.setChecked(show_incomplete_only)
                    
                    if show_incomplete_only:
                        self.incomplete_filter_btn.setText(f"📋 Filtre actif, plus que {pluralize(incomplete_count, 'ligne')}")
                        self.incomplete_filter_btn.setToolTip(f"Filtre actif - {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                    else:
                        self.incomplete_filter_btn.setText(f"📋 {pluralize(incomplete_count, 'incomplète')}")
                        self.incomplete_filter_btn.setToolTip(f"Afficher uniquement les {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                else:
                    self.incomplete_filter_btn.hide()
        except Exception as e:
            print(f"Erreur mise à jour bouton incomplètes: {e}")
    
    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        """Log des largeurs de colonnes quand elles sont modifiées"""
        try:
            # Récupérer le nom de la colonne
            column_name = Config.UI_HEADERS[logical_index] if logical_index < len(Config.UI_HEADERS) else f"Colonne {logical_index}"
            
            # Log de la modification (niveau DEBUG pour réduire le bruit)
            app_logger.debug(f"LARGEUR COLONNE MODIFIÉE: '{column_name}' (index {logical_index}) = {new_size}px (était {old_size}px)")
            
        except Exception as e:
            app_logger.error(f"Erreur log largeur colonne: {e}")
    
    def cleanup(self):
        """Nettoyage sécurisé des widgets Qt pour éviter les erreurs de destruction"""
        try:
            # Nettoyer les références aux widgets qui pourraient être détruits
            if hasattr(self, 'advanced_search_input'):
                self.advanced_search_input = None
            if hasattr(self, 'search_input'):
                self.search_input = None
            if hasattr(self, 'filter_widgets'):
                self.filter_widgets.clear()
        except Exception as e:
            # Ignore silencieusement les erreurs de nettoyage
            pass
