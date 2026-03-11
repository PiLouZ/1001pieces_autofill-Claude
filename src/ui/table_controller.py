"""
Gestion centralisée du tableau, filtres, pagination et tri
"""

from typing import List, Dict, Optional, Tuple, Any
from .qt_imports import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                            QTableWidgetItem, QLineEdit, QComboBox, QPushButton,
                            QLabel, QProgressDialog, QApplication, QHeaderView,
                            Qt, QTimer, QThread, pyqtSignal, QObject, QColor, QBrush,
                            QSizePolicy, QMenu, QAction, QPoint, QAbstractItemView)

from ..core.config import Config
from ..core.logger import app_logger
from ..core.constants import UIConfig
from ..utils.error_handler import (
    handle_table_operations_errors, handle_async_worker_errors,
    handle_database_operation_errors, handle_ui_operation_errors
)
from ..data.database_manager import DatabaseManager
from ..services.pieces_count_service import PiecesCountService
from ..services.table_widget_service import CustomTableWidget, TableWidgetService

class DatabaseQueryWorker(QThread):
    """Worker thread pour les requêtes DB async - Phase 2c"""

    # Signaux pour communication avec UI thread
    data_loaded = pyqtSignal(list)  # Données chargées
    error_occurred = pyqtSignal(str)  # Erreur survenue

    def __init__(self, db_manager, search_term=None, column_filters=None,
                 limit=None, offset=None, sort_column=None, sort_order=None,
                 incomplete_filter=False):
        super().__init__()
        self.db_manager = db_manager
        self.search_term = search_term
        self.column_filters = column_filters
        self.limit = limit
        self.offset = offset
        self.sort_column = sort_column
        self.sort_order = sort_order
        self.incomplete_filter = incomplete_filter

    @handle_async_worker_errors(log_prefix="Erreur DatabaseQueryWorker")
    def run(self):
        """Exécuter la requête DB dans le thread séparé"""
        # IDENTIQUE à load_data() - même appel DB
        records = self.db_manager.load_data(
            self.search_term,
            self.column_filters,
            self.limit,
            self.offset,
            self.sort_column,
            self.sort_order,
            self.incomplete_filter
        )
        self.data_loaded.emit(records)

class TableController:
    """Contrôleur pour la gestion du tableau principal"""
    
    def __init__(self, parent_window, db_manager: DatabaseManager):
        self.parent_window = parent_window
        self.db_manager = db_manager
        self.pieces_count_service = PiecesCountService(db_manager)
        self.table_widget_service = TableWidgetService(db_manager)
        
        # Variables de pagination
        self.current_page = 1
        self.page_size = UIConfig.DEFAULT_PAGE_SIZE  # Utiliser la constante commune
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

        # Phase 2c: Worker thread pour async operations
        self.query_worker = None
        self.loading_in_progress = False

        # Historique des recherches (max 10, le plus récent en premier)
        self.search_history = []
        self.history_btn = None

        # Préchargement page suivante
        self.prefetch_cache = {}  # {cache_key: records}
        self.prefetch_worker = None  # Worker distinct de query_worker pour ne pas bloquer load_data_async
        self._prefetch_db_manager = None  # Connexion SQLite dédiée au prefetch (évite partage de connexion)
        self._pending_prefetch_params = None
        self.prefetch_timer = QTimer()
        self.prefetch_timer.setSingleShot(True)
        self.prefetch_timer.timeout.connect(self._execute_prefetch)
        
        # Référence vers le widget table (sera initialisée par create_table_widget)
        self.table = None
        self.model = None  # AppareillsTableModel — initialisé par create_table_widget()
        self.filter_widget = None
        self.filter_layout = None
        
        # Labels et contrôles de pagination (seront initialisés par create_table_widget)
        self.page_label = None
        self.size_label = None
        self.prev_button = None
        self.next_button = None
        self.page_size_combo = None
        
        # Référence vers NavigationService (sera définie par set_navigation_service)
        self.navigation_service = None
        
    def set_navigation_service(self, navigation_service):
        """Définir le service de navigation pour la synchronisation"""
        self.navigation_service = navigation_service
        
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
                filter_combo.setStyleSheet("""
                    QComboBox {
                        padding: 2px 8px;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        background-color: white;
                    }
                    QComboBox:focus {
                        border-color: #0078d4;
                    }
                """)
                filter_combo.currentTextChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
                self.filter_widgets[i] = filter_combo
                self._populate_dropdown_values(filter_combo, i)
                filter_layout.addWidget(filter_combo, 1)  # stretch factor 1
            else:
                # Champs texte avec même style que les dropdowns
                filter_input = QLineEdit()
                filter_input.setPlaceholderText(f"{header}...")
                filter_input.textChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
                filter_input.setStyleSheet("""
                    QLineEdit {
                        padding: 2px 8px;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        background-color: white;
                    }
                    QLineEdit:focus {
                        border-color: #0078d4;
                        outline: none;
                    }
                """)
                self.filter_widgets[i] = filter_input
                filter_layout.addWidget(filter_input, 1)  # stretch factor 1

        # Bouton RAZ pour vider tous les filtres colonne
        raz_btn = QPushButton("×")
        raz_btn.setFixedWidth(32)
        raz_btn.setToolTip("Réinitialiser tous les filtres")
        raz_btn.setStyleSheet("""
            QPushButton {
                background-color: #e53935;
                color: white;
                border: 1px solid #c62828;
                border-radius: 3px;
                font-weight: bold;
                font-size: 16px;
                min-height: 0px;
                max-height: 22px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)
        raz_btn.clicked.connect(self._clear_all_column_filters)
        filter_layout.addWidget(raz_btn)

        layout.addWidget(filter_widget)
        
        # Sauvegarder les références pour la visibilité
        self.filter_widget = filter_widget
        self.filter_layout = filter_layout
        
        # Tableau principal — QTableView + AppareillsTableModel
        from ..data.appareils_table_model import AppareillsTableModel
        from .custom_table_view import CustomTableView
        self.model = AppareillsTableModel(self.parent_window)
        self.table = CustomTableView()
        self.table.setModel(self.model)
        # Headers gérés par model.headerData() — pas de setHorizontalHeaderLabels()

        # Configuration QTableView
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

        # Tri géré manuellement (désactiver le tri automatique Qt)
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
        search_label2 = QLabel("🔍 Recherche par pièce:")
        search_layout2.addWidget(search_label2, 0, Qt.AlignVCenter)

        self.advanced_search_input = QLineEdit()
        self.advanced_search_input.setPlaceholderText("Référence pièce (ex: AS6015830, ou plusieurs: ref1 || ref2)...")
        # Sera connecté par MainWindow à AdvancedSearchService
        # self.advanced_search_input.textChanged.connect(self._on_advanced_search_changed)
        search_layout2.addWidget(self.advanced_search_input, 1, Qt.AlignVCenter)

        # Bouton historique des recherches
        self.history_btn = QPushButton("▾")
        self.history_btn.setFixedWidth(28)
        self.history_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.history_btn.setToolTip("Historique des recherches")
        self.history_btn.setStyleSheet("""
            QPushButton {
                background-color: #546e7a;
                color: white;
                border: 1px solid #37474f;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #37474f;
            }
            QPushButton:pressed {
                background-color: #263238;
            }
            QPushButton:disabled {
                background-color: #b0bec5;
                border-color: #90a4ae;
            }
        """)
        self.history_btn.setEnabled(False)  # Désactivé jusqu'à ce qu'il y ait un historique
        self.history_btn.clicked.connect(self._show_search_history)
        search_layout2.addWidget(self.history_btn, 0, Qt.AlignVCenter)

        clear_search_btn = QPushButton("×")
        clear_search_btn.setFixedWidth(32)
        # Expanding vertical: le bouton s'aligne automatiquement sur la hauteur de l'input
        clear_search_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        clear_search_btn.setToolTip("Effacer la recherche par pièce")
        clear_search_btn.setStyleSheet("""
            QPushButton {
                background-color: #e53935;
                color: white;
                border: 1px solid #c62828;
                border-radius: 3px;
                font-weight: bold;
                font-size: 16px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)
        clear_search_btn.clicked.connect(self._clear_advanced_search)
        search_layout2.addWidget(clear_search_btn, 0, Qt.AlignVCenter)
        
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
        if not self.table:
            return
        # QTableView : signaux via selectionModel()
        self.table.selectionModel().selectionChanged.connect(
            lambda selected, deselected: on_selection_changed_callback()
        )
        self.table.selectionModel().currentChanged.connect(
            lambda current, previous: on_selection_changed_callback()
        )
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur chargement données tableau")
    def load_data(self, search_term: str = None, is_search: bool = False):
        """Charger les données dans le tableau avec pagination et filtres"""
        import time
        start_time = time.time()

        # CORRECTION: Mettre à jour current_search_term pour tous les appels load_data
        self.current_search_term = search_term

        # Annuler tout prefetch planifié (le worker en cours finira sur sa propre connexion)
        self.prefetch_timer.stop()
        self._pending_prefetch_params = None

        # Enregistrer dans l'historique si c'est une vraie recherche (terme non vide)
        if is_search and search_term:
            self._add_to_search_history(search_term)

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
        # CORRECTION: Utiliser le service de tri/filtrage si disponible
        if (hasattr(self.parent_window, 'sorting_filtering_service') and
            self.parent_window.sorting_filtering_service):
            incomplete_filter = self.parent_window.sorting_filtering_service.incomplete_filter_active
        else:
            incomplete_filter = getattr(self.parent_window, 'show_incomplete_only', False)

        # SOLUTION FINALE: Parser avec SearchService directement sans condition (UNIVERSALE)
        effective_search_term = search_term
        if search_term and isinstance(search_term, str) and hasattr(self.parent_window, 'search_service'):
            # Toujours parser avec SearchService pour uniformité && et ||
            parsed_term = self.parent_window.search_service.parse_advanced_search(search_term)
            if parsed_term:  # Si parsing réussi, utiliser le terme parsé
                effective_search_term = parsed_term

        # Compter le total avec le terme unifié
        self.total_rows = self.db_manager.count_data(effective_search_term, column_filters, incomplete_filter=incomplete_filter)

        if self.page_size == -1:  # Mode "Tout"
            self.total_pages = 1
            self.current_page = 1
        else:
            self.total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
            if self.current_page > self.total_pages:
                self.current_page = self.total_pages

        # Convertir l'enum Qt en string attendue par db_manager ("ASC"/"DESC")
        sort_order_str = "ASC" if self.current_sort_order == Qt.AscendingOrder else "DESC"

        # Charger les données — vérifier le cache de préchargement d'abord
        cache_key = (str(effective_search_term), str(column_filters), limit, offset,
                     self.current_sort_column, sort_order_str, incomplete_filter)
        if cache_key in self.prefetch_cache:
            records = self.prefetch_cache.pop(cache_key)
            app_logger.debug(f"[Prefetch] Cache HIT page {self.current_page} ({len(records)} lignes)")
        else:
            records = self.db_manager.load_data(effective_search_term, column_filters, limit, offset,
                                               self.current_sort_column, sort_order_str, incomplete_filter)

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

        # Planifier le préchargement de la page suivante (100ms après le rendu)
        if self.page_size != -1 and self.current_page < self.total_pages:
            next_offset = self.current_page * self.page_size
            self._pending_prefetch_params = (
                effective_search_term, column_filters, limit, next_offset,
                self.current_sort_column, sort_order_str, incomplete_filter  # sort_order_str = "ASC"/"DESC"
            )
            self.prefetch_timer.start(100)
        else:
            self._pending_prefetch_params = None
            self.prefetch_timer.stop()

        # Performance logging
        elapsed = time.time() - start_time
        app_logger.debug(f"Table loaded: {len(records) if 'records' in locals() else 0} records in {elapsed:.3f}s")

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur démarrage load_data_async")
    def load_data_async(self, search_term: str = None, is_search: bool = False):
        """Version asynchrone de load_data() - Phase 2c

        ATTENTION: Même logique que load_data() mais avec requête DB en arrière-plan
        pour éviter le gel de l'UI. Résultats identiques garantis.
        """
        import time
        start_time = time.time()

        # Empêcher les requêtes multiples simultanées
        if self.loading_in_progress:
            app_logger.debug("Requête async déjà en cours, ignorée")
            return

        # IDENTIQUE à load_data() - même logique de préparation
        self.current_search_term = search_term

        # Réinitialiser le tri pour nouvelle recherche (même logique)
        if (is_search and
            search_term != getattr(self, 'previous_search_term', None) and
            not getattr(self, '_sorting_in_progress', False)):
            self.current_sort_column = -1
            self.current_sort_order = Qt.AscendingOrder
            self.previous_search_term = search_term

        # Calculer pagination (même logique)
        if self.page_size == -1:
            limit = None
            offset = None
        else:
            limit = self.page_size
            offset = (self.current_page - 1) * self.page_size

        # Obtenir filtres colonnes (même logique)
        column_filters = {}
        for col_idx, filter_widget in self.filter_widgets.items():
            if filter_widget is not None:
                if isinstance(filter_widget, QComboBox):
                    filter_text = filter_widget.currentText().strip()
                else:
                    filter_text = filter_widget.text().strip()
                if filter_text:
                    column_filters[col_idx] = filter_text

        # Filtre lignes incomplètes (même logique)
        if (hasattr(self.parent_window, 'sorting_filtering_service') and
            self.parent_window.sorting_filtering_service):
            incomplete_filter = self.parent_window.sorting_filtering_service.incomplete_filter_active
        else:
            incomplete_filter = getattr(self.parent_window, 'show_incomplete_only', False)

        # DIFFÉRENCE: Nettoyer thread précédent s'il existe
        if self.query_worker is not None:
            self.query_worker.quit()
            self.query_worker.wait()
            self.query_worker = None

        # Créer et configurer le worker thread
        sort_order_str_async = "ASC" if self.current_sort_order == Qt.AscendingOrder else "DESC"
        self.query_worker = DatabaseQueryWorker(
            self.db_manager,
            search_term,
            column_filters,
            limit,
            offset,
            self.current_sort_column,
            sort_order_str_async,
            incomplete_filter
        )

        # Connecter les signaux
        self.query_worker.data_loaded.connect(self._on_async_data_loaded)
        self.query_worker.error_occurred.connect(self._on_async_error)

        # Marquer comme en cours et démarrer
        self.loading_in_progress = True

        # Optionnel: Indicateur visuel de chargement
        if hasattr(self.parent_window, 'statusbar'):
            self.parent_window.statusbar.showMessage("🔄 Chargement des données...")

        self.query_worker.start()

        # Log de performance pour comparaison
        prep_time = (time.time() - start_time) * 1000
        app_logger.debug(f"load_data_async préparé en {prep_time:.1f}ms (worker démarré)")

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur _on_async_data_loaded")
    def _on_async_data_loaded(self, records):
        """Callback quand les données async sont chargées"""
        # IDENTIQUE à load_data() - même logique de remplissage
        if records is None:
            records = []

        # Compter total pour pagination (même logique que sync)
        if not hasattr(self, '_counting_in_progress'):
            # Utiliser count_data avec fallback sur len(records) si échec
            count_result = self.db_manager.count_data(
                self.current_search_term,
                self.filter_widgets,
                getattr(self.parent_window, 'show_incomplete_only', False)
            )
            self.total_rows = count_result if count_result is not None else len(records)

        # Calculer pagination (même logique)
        if self.page_size == -1:
            self.total_pages = 1
            self.current_page = 1
        else:
            self.total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
            if self.current_page > self.total_pages:
                self.current_page = self.total_pages

        # Remplir tableau (même logique que sync)
        if self.total_rows > 1000:
            self.parent_window.table_fill_service.fill_table_chunked(self.table, records, None, self.current_search_term)
        else:
            self.parent_window.table_fill_service.fill_table_standard(self.table, records, None, self.current_search_term)

        # Mettre à jour contrôles (même logique)
        self._update_pagination_controls()
        self._update_sort_indicators()

        # Init valeurs précédentes (même logique)
        if hasattr(self.parent_window, '_init_previous_values'):
            self.parent_window._init_previous_values()

        # Nettoyer et finaliser
        self.loading_in_progress = False
        if hasattr(self.parent_window, 'statusbar'):
            self.parent_window.statusbar.showMessage(f"✅ {len(records)} lignes chargées", Config.STATUS_MESSAGE_TIMEOUT)

        app_logger.debug(f"load_data_async terminé: {len(records)} résultats")

    def _on_async_error(self, error_msg):
        """Callback en cas d'erreur async"""
        app_logger.error(f"Erreur requête async: {error_msg}")
        self.loading_in_progress = False
        self.table.setRowCount(0)
        if hasattr(self.parent_window, 'statusbar'):
            self.parent_window.statusbar.showMessage(f"❌ Erreur DB: {error_msg}", Config.STATUS_MESSAGE_TIMEOUT)

    @handle_table_operations_errors(log_prefix="Erreur mise à jour numéros de lignes")
    def _update_row_numbers(self):
        """Mettre à jour les numéros de lignes après un tri"""
        for row in range(self.table.rowCount()):
            self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
        app_logger.debug(f"Numéros de lignes mis à jour pour {self.table.rowCount()} lignes")
    
    @handle_table_operations_errors(log_prefix="Erreur application visibilité colonnes")
    def _apply_column_visibility(self):
        """Appliquer la visibilité des colonnes selon la configuration"""
        for col_config in Config.COLUMN_CONFIG:
            col_idx = col_config["index"]
            is_visible = col_config["visible"]
            if col_idx < self.table.columnCount():
                if is_visible:
                    self.table.showColumn(col_idx)
                else:
                    self.table.hideColumn(col_idx)
    
    @handle_table_operations_errors(log_prefix="Erreur définition largeurs par défaut")
    def _set_default_column_widths(self):
        """Définir les largeurs par défaut des colonnes"""
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

        # Appliquer les largeurs
        for col_index, width in default_widths.items():
            if col_index < self.table.columnCount():
                self.table.setColumnWidth(col_index, width)
    
    @handle_table_operations_errors(log_prefix="Erreur gestionnaire clic en-tête")
    def _on_header_click(self, logical_index: int):
        """Gestionnaire de clic sur les en-têtes pour le tri"""
        if self.current_sort_column == logical_index:
            # Inverser l'ordre si même colonne
            self.current_sort_order = Qt.DescendingOrder if self.current_sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            # Nouvelle colonne, ordre croissant par défaut
            self.current_sort_column = logical_index
            self.current_sort_order = Qt.AscendingOrder

        self._apply_database_sort()
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur application tri base de données")
    def _apply_database_sort(self):
        """Appliquer le tri au niveau de la base de données"""
        # Marquer qu'un tri est en cours pour éviter la réinitialisation
        self._sorting_in_progress = True

        try:
            # CORRECTION: Utiliser la même logique que F5 et bouton toolbar
            search_term = None
            if (hasattr(self.parent_window, 'advanced_search_service') and
                hasattr(self.parent_window.advanced_search_service, 'get_current_search_term_with_fallback')):
                search_term = self.parent_window.advanced_search_service.get_current_search_term_with_fallback(self.parent_window)
            else:
                # Fallback vers ancienne logique si service indisponible
                if hasattr(self.parent_window, 'pending_search_term') and self.parent_window.pending_search_term:
                    search_term = self.parent_window.pending_search_term
                elif hasattr(self, 'current_search_term') and self.current_search_term:
                    search_term = self.current_search_term
                elif hasattr(self.parent_window, 'search_input') and self.parent_window.search_input:
                    text = self.parent_window.search_input.text().strip()
                    search_term = text if text else None

            # Convertir Qt.SortOrder en string pour la DB
            sort_order_str = "ASC" if self.current_sort_order == Qt.AscendingOrder else "DESC"

            # Appeler load_data avec les bonnes valeurs
            self._load_data_with_sort(search_term, self.current_sort_column, sort_order_str)
            self._update_sort_indicators()
        finally:
            # Nettoyer le flag de tri en cours
            self._sorting_in_progress = False
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur chargement avec tri")
    def _load_data_with_sort(self, search_term: str, sort_column: int, sort_order_str: str):
        """Charger les données avec tri spécifique sans passer par load_data standard"""
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
        # CORRECTION: Utiliser le service de tri/filtrage si disponible
        if (hasattr(self.parent_window, 'sorting_filtering_service') and
            self.parent_window.sorting_filtering_service):
            incomplete_filter = self.parent_window.sorting_filtering_service.incomplete_filter_active
        else:
            incomplete_filter = getattr(self.parent_window, 'show_incomplete_only', False)

        # CORRECTION: Parser le terme de recherche si nécessaire
        parsed_search_term = search_term
        if isinstance(search_term, str) and search_term and hasattr(self.parent_window, 'advanced_search_service'):
            # Essayer de parser la string comme recherche avancée
            parsed_result = self.parent_window.advanced_search_service.parse_advanced_search(search_term)
            if parsed_result:
                parsed_search_term = parsed_result

        # Détecter si c'est une recherche avancée
        is_advanced_search = isinstance(parsed_search_term, dict)

        if is_advanced_search:
            # Désactiver temporairement le cache pour cette requête triée
            cache_backup = self.db_manager.search_cache
            self.db_manager.search_cache = None

            try:
                records = self.db_manager.load_data(
                    parsed_search_term, column_filters, limit, offset,
                    sort_column, sort_order_str, incomplete_filter
                )
            finally:
                # Restaurer le cache
                self.db_manager.search_cache = cache_backup
        else:
            # Appel normal avec cache pour les recherches simples
            records = self.db_manager.load_data(
                parsed_search_term, column_filters, limit, offset,
                sort_column, sort_order_str, incomplete_filter
            )

        # Remplir le tableau
        if self.total_rows > 1000:
            self.parent_window.table_fill_service.fill_table_chunked(self.table, records, None, search_term)
        else:
            self.parent_window.table_fill_service.fill_table_standard(self.table, records, None, search_term)

        # Mettre à jour les contrôles de pagination
        self._update_pagination_controls()

        # Réinitialiser les valeurs précédentes après tri (comme load_data le fait)
        if hasattr(self.parent_window, '_init_previous_values'):
            self.parent_window._init_previous_values()

    @handle_table_operations_errors(log_prefix="Erreur mise à jour indicateurs tri")
    def _update_sort_indicators(self):
        """Mettre à jour les indicateurs visuels de tri"""
        if self.current_sort_column >= 0:
            self.table.horizontalHeader().setSortIndicator(
                self.current_sort_column, self.current_sort_order
            )

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
        self.pagination_widget = pagination_widget
        pagination_layout = QHBoxLayout(pagination_widget)
        
        # Bouton page précédente
        self.prev_button = QPushButton("◀ Précédent")
        # Navigation gérée par NavigationService
        pagination_layout.addWidget(self.prev_button)
        
        # Label page actuelle
        self.page_label = QLabel("Page 1 sur 1")
        pagination_layout.addWidget(self.page_label)
        
        # Bouton page suivante
        self.next_button = QPushButton("Suivant ▶")
        # Navigation gérée par NavigationService
        pagination_layout.addWidget(self.next_button)
        
        pagination_layout.addStretch()
        
        # Sélecteur taille de page
        size_label = QLabel("Lignes par page:")
        pagination_layout.addWidget(size_label)
        
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["100", "250", "500", "1000", "2000", "Tout"])
        self.page_size_combo.setCurrentText("100")
        # Changement de taille géré par NavigationService
        pagination_layout.addWidget(self.page_size_combo)
        
        self.size_label = QLabel(f"Total: {self.total_rows} lignes")
        pagination_layout.addWidget(self.size_label)
        
        layout.addWidget(pagination_widget)
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mise à jour pagination")
    def _update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination"""
        if self.page_label:
            self.page_label.setText(f"Page {self.current_page} sur {self.total_pages}")
        if self.size_label:
            self.size_label.setText(f"Total: {self.total_rows} lignes")

        # Masquer la zone de navigation page si une seule page
        if hasattr(self, 'pagination_widget') and self.pagination_widget:
            single_page = self.total_pages <= 1 and self.page_size != -1
            self.prev_button.setVisible(not single_page)
            self.next_button.setVisible(not single_page)
            self.page_label.setVisible(not single_page)

        # Synchroniser avec NavigationService si disponible
        if self.navigation_service:
            self.navigation_service.update_total_rows(self.total_rows)
    
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
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur peuplement dropdown")
    def _populate_dropdown_values(self, combo_widget: QComboBox, column_index: int):
        """Peupler les valeurs du dropdown avec les données uniques de la BDD"""
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
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur nettoyage filtres colonnes")
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
    
    @handle_table_operations_errors(log_prefix="Erreur récupération ID base de données")
    def get_db_id_from_row(self, row: int) -> int:
        """Récupérer l'ID de base de données d'une ligne"""
        item = self.table.item(row, 0)
        if item:
            return item.data(Qt.UserRole) or -1
        return -1
    
    def _on_search_text_changed(self, text: str):
        """Gestionnaire de changement du texte de recherche"""
        # Pour l'instant, pas de recherche automatique - seulement sur bouton
        pass
    
    def _perform_search(self):
        """Effectuer la recherche"""
        search_term = self.search_input.text().strip()
        self.load_data(search_term, is_search=True)
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur effacement recherche")
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
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur RAZ filtres colonne")
    def _clear_all_column_filters(self, checked=False):
        """Vider tous les filtres par colonne et recharger les données"""
        # Bloquer les signaux pour éviter N rechargements consécutifs
        for widget in self.filter_widgets.values():
            if widget is None:
                continue
            widget.blockSignals(True)
            try:
                if isinstance(widget, QComboBox):
                    widget.setCurrentIndex(0)
                else:
                    widget.clear()
            except RuntimeError:
                pass
            finally:
                widget.blockSignals(False)

        # Un seul rechargement après RAZ de tous les champs
        self.load_data(self.current_search_term, is_search=bool(self.current_search_term))

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
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur effacement recherche avancée")
    def _clear_advanced_search(self, checked=False):
        """Effacer la recherche avancée"""
        # Utiliser la référence principale dans MainWindow (compatible avec PasteInterceptor)
        if hasattr(self.parent_window, 'search_input') and self.parent_window.search_input is not None:
            try:
                self.parent_window.search_input.clear()
            except RuntimeError:
                # Le widget a été supprimé, on ignore silencieusement
                pass
        # Fallback vers l'ancienne méthode si nécessaire
        elif hasattr(self, 'advanced_search_input') and self.advanced_search_input is not None:
            try:
                self.advanced_search_input.clear()
            except RuntimeError:
                pass

        self.current_search_term = None  # Nettoyer aussi le terme persistant
        self.load_data(None, is_search=False)

        # Désactiver les boutons d'export quand on vide la recherche
        if hasattr(self.parent_window, '_update_export_buttons_state'):
            self.parent_window._update_export_buttons_state("")

    def _execute_prefetch(self):
        """Lancer le préchargement de la page suivante en arrière-plan"""
        if not self._pending_prefetch_params:
            return
        # Ne pas lancer si un prefetch est déjà en cours
        if self.prefetch_worker and self.prefetch_worker.isRunning():
            return

        effective_search_term, column_filters, limit, next_offset, sort_col, sort_order, incomplete_filter = self._pending_prefetch_params
        # sort_order est déjà une string "ASC"/"DESC" (stocké ainsi dans _pending_prefetch_params)
        cache_key = (str(effective_search_term), str(column_filters), limit, next_offset,
                     sort_col, sort_order, incomplete_filter)

        if cache_key in self.prefetch_cache:
            return  # Déjà en cache, rien à faire

        # Utiliser une connexion SQLite dédiée au prefetch pour éviter tout partage
        # avec le thread principal (db_manager.conn) → plus de freeze, plus de lock
        if self._prefetch_db_manager is None:
            from ..data.database_manager import DatabaseManager
            self._prefetch_db_manager = DatabaseManager()

        self.prefetch_worker = DatabaseQueryWorker(
            self._prefetch_db_manager, effective_search_term, column_filters,
            limit, next_offset, sort_col, sort_order, incomplete_filter
        )
        self.prefetch_worker.data_loaded.connect(
            lambda records, key=cache_key: self._on_prefetch_done(records, key)
        )
        self.prefetch_worker.start()
        app_logger.debug(f"[Prefetch] Démarré pour offset={next_offset}")

    def _on_prefetch_done(self, records: list, cache_key: tuple):
        """Stocker les données préchargées dans le cache (max 5 entrées)"""
        if len(self.prefetch_cache) >= 5:
            # Supprimer l'entrée la plus ancienne
            oldest = next(iter(self.prefetch_cache))
            del self.prefetch_cache[oldest]
        self.prefetch_cache[cache_key] = records
        app_logger.debug(f"[Prefetch] Stocké: {len(records)} lignes (cache size={len(self.prefetch_cache)})")

    def _add_to_search_history(self, term: str):
        """Ajouter un terme à l'historique des recherches (max 10, FIFO, sans doublons)"""
        if not term or not term.strip():
            return
        term = term.strip()
        # Retirer les doublons existants (comparaison insensible à la casse)
        self.search_history = [h for h in self.search_history if h.lower() != term.lower()]
        # Insérer en tête (plus récent en premier)
        self.search_history.insert(0, term)
        # Limiter à 10 entrées
        self.search_history = self.search_history[:10]
        # Activer le bouton historique
        if self.history_btn:
            self.history_btn.setEnabled(True)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur affichage historique recherche")
    def _show_search_history(self, checked=False):
        """Afficher le menu déroulant de l'historique des recherches"""
        if not self.search_history:
            return

        menu = QMenu(self.history_btn)
        menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px;
            }
            QMenu::item {
                padding: 5px 16px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
                color: #1565c0;
            }
        """)

        for term in self.search_history:
            display = term if len(term) <= 60 else term[:57] + "…"
            action = QAction(display, menu)
            action.setData(term)
            menu.addAction(action)

        chosen = menu.exec(self.history_btn.mapToGlobal(QPoint(0, self.history_btn.height())))
        if chosen:
            selected_term = chosen.data()
            # Remplir le champ de recherche (utiliser la référence principale)
            search_input = getattr(self.parent_window, 'search_input', None) or self.advanced_search_input
            if search_input:
                search_input.setText(selected_term)
                search_input.setFocus()

    def _add_incomplete_filter_button(self, layout):
        """Ajouter le bouton de filtre pour les lignes incomplètes"""
        from .qt_imports import QPushButton, QHBoxLayout
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

        # Associer le bouton au service optimisé
        if hasattr(self.parent_window, 'incomplete_button_service'):
            self.parent_window.incomplete_button_service.set_button(self.incomplete_filter_btn)
            self.parent_window.incomplete_button_service.set_filter_active(self.parent_window.show_incomplete_only)

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
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mise à jour visibilité bouton incomplètes")
    def _update_incomplete_button_visibility(self):
        """Mettre à jour la visibilité du bouton incomplètes selon les données"""
        from ..core.config import pluralize

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
    
    @handle_table_operations_errors(log_prefix="Erreur log largeur colonne")
    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        """Log des largeurs de colonnes quand elles sont modifiées"""
        # Récupérer le nom de la colonne
        column_name = Config.UI_HEADERS[logical_index] if logical_index < len(Config.UI_HEADERS) else f"Colonne {logical_index}"
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur nettoyage widgets")
    def cleanup(self):
        """Nettoyage sécurisé des widgets Qt pour éviter les erreurs de destruction"""
        # Nettoyer les références aux widgets qui pourraient être détruits
        if hasattr(self, 'advanced_search_input'):
            self.advanced_search_input = None
        if hasattr(self, 'search_input'):
            self.search_input = None
        if hasattr(self, 'filter_widgets'):
            self.filter_widgets.clear()
