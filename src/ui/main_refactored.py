"""
Application de gestion d'appareils - Version refactorisée
Architecture modulaire avec séparation des responsabilités
"""

import sys
from typing import Optional, Dict, Any, List, Tuple

from .qt_imports import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QLabel, QPushButton, QHBoxLayout,
    QInputDialog, QMessageBox, QLineEdit, QTableWidgetSelectionRange,
    QToolBar, QAction, QStatusBar, QSplitter, QTabWidget,
    QListWidget, QListWidgetItem, QFileDialog, QComboBox,
    QProgressDialog, QCheckBox, QMenu, QDialog, QCompleter, QTextEdit, QTextBrowser,
    QKeySequence, QPainter, QPen, QColor, QDragEnterEvent, QDropEvent, QBrush, QKeyEvent, QFont,
    Qt, QTimer, QSettings, QEvent, QSize, QMimeData, QUrl, QStringListModel
)

# Imports Python standard consolidés
import os
import csv  
import webbrowser
from datetime import datetime

# Helpers et utilitaires refactorisés
from .message_helper import MessageHelper, CommonMessages, show_success, show_error, ask_confirmation
from .dialog_manager import DialogManager
from ..utils.error_handler import (
    handle_errors, handle_database_errors, SafeOperation,
    handle_ui_errors, handle_ui_column_errors,
    handle_database_operation_errors, handle_ui_operation_errors,
    handle_table_operations_errors, handle_navigation_errors,
    handle_export_errors, handle_import_errors, handle_validation_errors,
    handle_file_errors, handle_log_viewer_errors, handle_export_operation_errors,
    handle_data_management_errors, handle_drag_operation_errors,
    handle_event_handler_errors, handle_ui_update_errors
)
from ..core.constants import UIConfig, Messages, DatabaseConfig, FileExtensions

from ..services import SearchService, ImportService
from ..services.advanced_search_service import AdvancedSearchService
from ..services.event_bus import event_bus
from ..services.export_service import ExportFormat
from ..services.navigation_service import NavigationService
from ..services.cell_editing_service import CellEditingService
# PHASE 4 : Remplacement par ExportManagerService unifié
from ..services.export_manager import ExportManagerService, ExportType
from ..services.device_manager import DeviceManager
from ..services.paste_results_service import PasteResultsService

# Imports des modules refactorisés
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config
from src.core.logger import app_logger
from src.core.import_manager import ImportManager
from src.data.database_manager import DatabaseManager, DatabaseError
from src.data.data_validator import DataValidator, ValidationResult
from src.data.data_exporter import DataExporter, ExportError
from .style_manager import StyleManager
from .table_controller import TableController
from .paste_data_processor import PasteDataProcessor, PasteProcessingResult
from .data_management_service import DataManagementService, FieldCompletionResult
from .user_interaction_service import UserInteractionService
from .log_viewer import LogViewer
from .piece_management_service import PieceManagementService
from .seo_service import SEOService
from .pieces_list_service import PiecesListService
from ..services.table_widget_service import CustomTableWidget, TableWidgetService
from ..services.grouped_history_service import GroupedHistoryService
from ..services.drag_handle_service import DragHandle, DragHandleService
from ..services.undo_manager import UndoRedoManager
# Supprimé: remplacé par DialogManager dans les imports centralisés
from ..services.event_handlers_service import EventHandlersService
from ..services.table_fill_service import TableFillService

class MainWindow(QMainWindow):
    """Fenêtre principale refactorisée"""
    
    def __init__(self):
        super().__init__()
        
        # Initialisation des composants
        self._init_components()
        self._init_column_visibility()
        self._init_ui()
        self._init_connections()

        # Configuration du nettoyage automatique pour le champ de recherche (après init UI)
        self._setup_paste_cleanup_for_search_input()

        # Chargement initial des données
        self.table_controller.load_data()

        # S'assurer que les services d'indication sont mis à jour après l'initialisation
        self._update_incomplete_button_visibility()

        # Déclencher la détection initiale des doublons
        if hasattr(self, 'duplicate_indicator_service'):
            self.duplicate_indicator_service.schedule_update()

    @handle_database_errors("Erreur d'initialisation des composants")
    def _init_components(self):
        """Initialiser les composants principaux - Version refactorisée"""
        self._init_core_managers()
        self._init_search_services()
        self._init_import_export_services()
        self._init_business_services()
        self._init_ui_services()
        self._init_advanced_features()
        self._init_app_state()
    
    def _init_core_managers(self):
        """Initialiser les gestionnaires de base"""
        self.db_manager = DatabaseManager()
        self.validator = DataValidator()
        self.exporter = DataExporter(self.db_manager)
        self.device_manager = DeviceManager(self.db_manager)
    
    def _init_search_services(self):
        """Initialiser les services de recherche"""
        self.search_service = SearchService(self.db_manager)
        self.advanced_search_service = AdvancedSearchService(self.search_service, self)
        
        from ..services.autocompletion_service import AutoCompletionService
        self.autocompletion_service = AutoCompletionService(self.db_manager, self)
    
    def _init_import_export_services(self):
        """Initialiser les services d'import/export - PHASE 4 : Service unifié"""
        # PHASE 4 : Nouveau service d'export unifié
        self.export_manager = ExportManagerService(self)

        # Services d'import conservés
        self.import_service = ImportService(self.db_manager)

        # PHASE 3.2 : Service unifié d'import/export (avec feature flag)
        if Config.USE_NEW_IMPORT_EXPORT_SERVICE:
            from ..services.import_export_service import ImportExportService
            self.import_export_service = ImportExportService(self)
            self.import_export_service.initialize_services()
            app_logger.debug("ImportExportService activé via feature flag")
        else:
            self.import_export_service = None

        # PHASE 3.3 : Service unifié des opérations de base de données (avec feature flag)
        if Config.USE_NEW_DATABASE_OPERATIONS_SERVICE:
            from ..services.database_operations_service import DatabaseOperationsService
            self.database_operations_service = DatabaseOperationsService(self)
            self.database_operations_service.initialize_services()
        else:
            self.database_operations_service = None

        # PHASE 3.4 : Service unifié de gestion de l'état UI (avec feature flag)
        if Config.USE_NEW_UI_STATE_MANAGEMENT_SERVICE:
            from ..services.ui_state_management_service import UIStateManagementService
            self.ui_state_management_service = UIStateManagementService(self)
            self.ui_state_management_service.initialize_services()
        else:
            self.ui_state_management_service = None

        # PHASE 3.5 : Service unifié des raccourcis clavier (avec feature flag)
        if Config.USE_NEW_KEYBOARD_SHORTCUT_SERVICE:
            from ..services.keyboard_shortcut_service import KeyboardShortcutService
            self.keyboard_shortcut_service = KeyboardShortcutService(self)
            self.keyboard_shortcut_service.initialize_services()
        else:
            self.keyboard_shortcut_service = None

        self.import_manager = ImportManager(self.db_manager, parent_widget=self)
        
        from .file_processing_service import FileProcessingService
        self.file_processing_service = FileProcessingService(self)
    
    def _init_business_services(self):
        """Initialiser les services métier"""
        self.paste_results_service = PasteResultsService(self)
        self.event_handlers_service = EventHandlersService(self)
        self.table_fill_service = TableFillService(self)
        
        # Processeurs de données
        self.paste_processor = PasteDataProcessor(self.db_manager, self.validator, self)
        self.data_management_service = DataManagementService(self.db_manager, self)
        
        # Services spécialisés
        self.user_interaction_service = UserInteractionService(self)
        self.grouped_history_service = GroupedHistoryService(self.user_interaction_service)
        self.piece_management_service = PieceManagementService(self)
        self.seo_service = SEOService(self)
        self.pieces_list_service = PiecesListService(self)

        # Service de sauvegarde événementielle (Phase 4 - Factorisation)
        from ..services.event_driven_save_service import EventDrivenSaveService
        self.event_driven_save_service = EventDrivenSaveService(self)
    
    def _init_ui_services(self):
        """Initialiser les services d'interface utilisateur"""
        from .toolbar_service import ToolbarService
        self.toolbar_service = ToolbarService(self)

        self.dialog_manager = DialogManager(self)

        from ..services.unified_dialog_service import UnifiedDialogService
        self.dialog_service = UnifiedDialogService(self)

        # Service optimisé pour le bouton des lignes incomplètes
        from ..services.incomplete_button_service import IncompleteButtonService
        self.incomplete_button_service = IncompleteButtonService(self.db_manager, self)

        # Service optimisé pour l'indication des doublons
        from ..services.duplicate_indicator_service import DuplicateIndicatorService
        self.duplicate_indicator_service = DuplicateIndicatorService(self.db_manager, self)

        from .custom_reference_service import CustomReferenceService
        self.custom_reference_service = CustomReferenceService(self)

        from ..services.paste_cleanup_service import PasteCleanupService
        self.paste_cleanup_service = PasteCleanupService(self)

        # Note: AutoSaveManager est initialisé dans _setup_statusbar() pour ordre correct

        # PHASE 3.1: Service de tri et filtrage avec feature flag
        if Config.USE_NEW_SORTING_FILTERING_SERVICE:
            from ..services.sorting_filtering_service import SortingFilteringService
            self.sorting_filtering_service = None  # Sera initialisé après création de la table
        
        from .pieces_panel_service import PiecesPanelService
        self.pieces_panel_service = PiecesPanelService(self)
        
        from .ui_component_service import UIComponentService
        self.ui_component_service = UIComponentService(self)
        
        # PHASE 5: Services de navigation et édition centralisés
        # Imports déplacés vers le haut du fichier
    
    def _init_advanced_features(self):
        """Initialiser les fonctionnalités avancées"""
        self.drag_handle_service = DragHandleService()
        self.undo_manager = UndoRedoManager()
        
        # Configuration des signaux avancés
        self._connect_advanced_search_signals()
        
        # Contrôleur principal de table
        self.table_controller = TableController(self, self.db_manager)

        # Connecter le signal d'auto-désactivation du filtre après initialisation du table_controller
        if hasattr(self, 'incomplete_button_service'):
            self.incomplete_button_service.filter_auto_disabled.connect(self._on_incomplete_filter_auto_disabled)
            app_logger.info("✅ Signal filter_auto_disabled connecté après initialisation table_controller")

        # PHASE 5: Initialisation des services centralisés
        self.navigation_service = NavigationService(self.table_controller, self)
        self.cell_editing_service = CellEditingService(
            None,  # sera défini après _create_table_widget
            self.db_manager, 
            self.validator, 
            self
        )
        
        # Configuration des événements des services
        self._setup_service_events()
    
    def _init_app_state(self):
        """Initialiser l'état de l'application"""
        self.settings = QSettings("DeviceManager", "MainApp")
        
        # Variables d'état
        self.previous_values = {}  # Tracker des valeurs précédentes (drag handle)
        self.drag_overlay_active = False  # État du drag&drop overlay
        self._piece_description_decisions = {}  # Cache des décisions de description import
        self.show_incomplete_only = False  # Filtre lignes incomplètes
        self.use_pagination = True  # Contrôle pagination
        self.modified_cells = set()
        self.log_viewer = None
        
        # Configuration des timers
        self._setup_timers()
    
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
        # Feature Flag: AutoSaveManager - Phase 1 Refactoring
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            self.auto_save_manager.setup_auto_save()
        elif not Config.ENABLE_EVENT_DRIVEN_SAVE:
            # Ancien système timer-based (pour rollback)
            self.auto_save_timer = QTimer()
            self.auto_save_timer.timeout.connect(self._auto_save)
            self.auto_save_timer.start(Config.AUTO_SAVE_INTERVAL)
        # Sinon: système événementiel (pas de timer)

        # PHASE 2.3: Recherche gérée par AdvancedSearchService
        # Plus besoin de timer local - géré par le service

        # Timers de filtres maintenant dans TableController

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
        """Phase 4+5: Configuration des événements des services"""
        # Événements de recherche
        event_bus.on('search.started', self.event_handlers_service.on_search_started)
        event_bus.on('search.completed', self.event_handlers_service.on_search_completed) 
        event_bus.on('search.error', self.event_handlers_service.on_search_error)
        
        # Événements d'export
        event_bus.on('export.started', self.event_handlers_service.on_export_started)
        event_bus.on('export.completed', self.event_handlers_service.on_export_completed)
        event_bus.on('export.error', self.event_handlers_service.on_export_error)
        
        # PHASE 5: Événements des services centralisés
        if hasattr(self, 'navigation_service'):
            self.navigation_service.page_changed.connect(self._on_navigation_page_changed)
            self.navigation_service.page_size_changed.connect(self._on_navigation_page_size_changed)
            
        if hasattr(self, 'cell_editing_service'):
            self.cell_editing_service.cell_updated.connect(self._on_cell_editing_updated)
            self.cell_editing_service.cell_validation_failed.connect(self._on_cell_validation_failed)
    
    # PHASE 5: Callbacks pour les événements des services centralisés
    def _on_navigation_page_changed(self, page: int):
        """Callback pour changement de page — remet le scroll en haut du tableau."""
        table = self.table_controller.table
        if table is not None:
            table.scrollToTop()
        
    def _on_navigation_page_size_changed(self, new_size: int):
        """Callback pour changement de taille de page"""
        app_logger.debug(f"Taille de page changée: {new_size}")
        # Mettre à jour les variables d'état locales si nécessaire
        self.page_size = new_size
        
    def _on_cell_editing_updated(self, item, old_value: str, new_value: str):
        """Callback pour mise à jour de cellule"""
        # Gérer les actions spécifiques à l'interface principale
        self._handle_successful_cell_update(item, old_value, new_value, False)
        
    def _on_cell_validation_failed(self, item, error_message: str):
        """Callback pour échec de validation de cellule"""
        from .message_helper import show_error
        show_error(self, "Erreur de validation", error_message)
    
    def _connect_advanced_search_signals(self):
        """PHASE 2.3: Connecter les signaux du service de recherche avancé"""
        if hasattr(self, 'advanced_search_service'):
            self.advanced_search_service.search_started.connect(self.event_handlers_service.on_advanced_search_started)
            self.advanced_search_service.search_completed.connect(self.event_handlers_service.on_advanced_search_completed)
            self.advanced_search_service.search_error.connect(self.event_handlers_service.on_advanced_search_error)
            self.advanced_search_service.export_buttons_update.connect(self.event_handlers_service.on_export_buttons_update)
        
        # Événements d'import
        event_bus.on('import.started', self.event_handlers_service.on_import_started)
        event_bus.on('import.completed', self.event_handlers_service.on_import_completed)
        event_bus.on('import.error', self.event_handlers_service.on_import_error)

    def _create_table_widget(self) -> QWidget:
        """Créer le widget du tableau via TableController"""
        # Passer le service UI au TableController pour qu'il puisse ajouter les boutons d'export
        self.table_controller.ui_component_service = self.ui_component_service
        
        table_widget = self.table_controller.create_table_widget()
        
        # Garder des références pour la compatibilité
        self.table = self.table_controller.table
        self.search_input = self.table_controller.advanced_search_input  # Le vrai search input
        self.incomplete_filter_btn = self.table_controller.incomplete_filter_btn  # Référence au bouton lignes à compléter
        
        # PHASE 5: Configuration des services centralisés
        self.cell_editing_service.table = self.table

        # PHASE 3.1: Initialiser le service de tri et filtrage si activé
        if Config.USE_NEW_SORTING_FILTERING_SERVICE and hasattr(self, 'sorting_filtering_service'):
            from ..services.sorting_filtering_service import SortingFilteringService
            self.sorting_filtering_service = SortingFilteringService(
                table_widget=self.table,
                table_controller=self.table_controller,
                parent=self
            )
        
        # Configurer le service de navigation avec les widgets de pagination
        if hasattr(self.table_controller, 'page_label'):
            self.navigation_service.set_pagination_widgets(
                self.table_controller.page_label,
                self.table_controller.prev_button,
                self.table_controller.next_button,
                self.table_controller.page_size_combo
            )
            # Établir la liaison bidirectionnelle
            self.table_controller.set_navigation_service(self.navigation_service)
        
        # Connecter les signaux de sélection pour le panneau des pièces
        self.table_controller.connect_selection_signals(self._on_selection_changed)
        
        # Connecter cell_edited du modèle → handler de modification
        if self.table_controller.model is not None:
            self.table_controller.model.cell_edited.connect(self._on_cell_changed_model)
        
        # Configurer la poignée de duplication après création du tableau
        self._setup_drag_handle()
        
        # Configurer le menu contextuel du tableau
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        
        # CRUCIAL: Connecter la barre de recherche à AdvancedSearchService pour activation des boutons
        self.search_input.textChanged.connect(self.advanced_search_service.search_with_debounce)
        
        return table_widget

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
        # Correction largeur onglet: empêcher le texte bold qui déborde
        self.pieces_tabs.setStyleSheet("""
            QTabBar::tab:selected {
                font-weight: normal;  /* Enlever le bold par défaut pour éviter débordement */
            }
        """)
        
        # Liste des pièces avec boutons d'action au survol - Phase 2.16: Délégation vers PiecesListService
        self.pieces_list = self.pieces_list_service.create_pieces_list_widget()
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

    def _setup_drag_handle(self):
        """Configurer la poignée de glisser-déposer"""
        self.drag_handle = self.drag_handle_service.create_drag_handle(
            parent=self.table.viewport(), 
            table=self.table, 
            main_window=self
        )
        self.table.viewport().installEventFilter(self)

    def _setup_toolbar(self):
        """Configurer la barre d'outils moderne - Phase 2.5d"""
        # Déléguer la configuration au service spécialisé
        self.toolbar = self.toolbar_service.setup_toolbar()

        # Connecter le service d'indication des doublons aux boutons
        if hasattr(self, 'duplicate_indicator_service') and hasattr(self.toolbar_service, 'action_button'):
            self.duplicate_indicator_service.set_buttons(
                self.toolbar_service.action_button,
                self.toolbar_service.clean_duplicates_action
            )
            from ..core.logger import app_logger
            app_logger.info("✅ Service d'indication des doublons connecté aux boutons")

        self._update_toolbar_states()

    def _setup_statusbar(self):
        """Configurer la barre de statut"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        self.save_indicator = QLabel(Config.get_message('save_success'))
        self.save_indicator.setStyleSheet("color: green;")
        self.statusbar.addPermanentWidget(self.save_indicator)

        # Feature Flag: AutoSaveManager - Initialisation retardée + Configuration indicateur UI
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            from ..services.auto_save_manager import AutoSaveManager
            self.auto_save_manager = AutoSaveManager(
                self.db_manager,
                self.user_interaction_service,
                self.statusbar
            )
            self.auto_save_manager.setup_ui_indicator(self.save_indicator)

        self.connection_indicator = QLabel(Config.get_message('connected'))
        self.connection_indicator.setStyleSheet("color: green;")
        self.statusbar.addPermanentWidget(self.connection_indicator)

    def _init_connections(self):
        """Initialiser les connexions de signaux"""
        pass  # Les connexions sont déjà configurées dans les méthodes de création
    
    def _setup_paste_cleanup_for_search_input(self):
        """Configure l'interception du collage pour le champ de recherche"""
        from .qt_imports import QLineEdit
        from .qt_imports import QEvent
        from .qt_imports import QClipboard
        
        class PasteInterceptor(QLineEdit):
            def __init__(self, parent_window, paste_service):
                super().__init__()
                self.parent_window = parent_window
                self.paste_service = paste_service
                
            def keyPressEvent(self, event):
                # Intercepter Cmd+V (ou Ctrl+V) - Code 86 pour V, modifiers 0x10000000 pour Cmd
                if (event.modifiers() & 0x10000000) and event.key() == 86:  # Cmd+V sur macOS
                    self._handle_paste_event()
                    return
                elif (event.modifiers() & 0x04000000) and event.key() == 86:  # Ctrl+V sur autres OS
                    self._handle_paste_event()
                    return
                    
                super().keyPressEvent(event)
                
            def insertFromMimeData(self, source):
                # Méthode alternative pour intercepter le collage
                if source.hasText():
                    original_text = source.text()
                    cleaned_text = self.paste_service.process_paste_content(
                        original_text, self.parent_window
                    )
                    
                    if cleaned_text != original_text:
                        # Créer un nouveau MimeData avec le texte nettoyé
                        from .qt_imports import QMimeData
                        clean_mime = QMimeData()
                        clean_mime.setText(cleaned_text)
                        super().insertFromMimeData(clean_mime)
                        return
                        
                super().insertFromMimeData(source)
                
            def _handle_paste_event(self):
                """Gère l'événement de collage avec nettoyage"""
                from .qt_imports import QApplication
                clipboard = QApplication.clipboard()
                original_text = clipboard.text()
                
                if original_text:
                    cleaned_text = self.paste_service.process_paste_content(
                        original_text, self.parent_window
                    )
                    
                    if cleaned_text != original_text:
                        # Remplacer le texte dans le champ
                        cursor_pos = self.cursorPosition()
                        selected_text = self.selectedText()
                        
                        if selected_text:
                            # Remplacer le texte sélectionné
                            self.insert(cleaned_text)
                        else:
                            # Insérer à la position du curseur
                            self.insert(cleaned_text)
                    else:
                        # Collage normal
                        self.paste()
        
        # Remplacer le QLineEdit standard par notre interceptor
        if hasattr(self, 'search_input') and self.search_input:
            # Sauvegarder les propriétés existantes
            parent = self.search_input.parent()
            text = self.search_input.text()
            placeholder = self.search_input.placeholderText()
            
            # Créer le nouvel input avec interception
            new_input = PasteInterceptor(self, self.paste_cleanup_service)
            new_input.setText(text)
            new_input.setPlaceholderText(placeholder)
            
            # Remplacer dans le layout
            if parent and hasattr(parent, 'layout') and parent.layout():
                layout = parent.layout()
                
                # Tentative 1: Recherche directe
                search_found = False
                for i in range(layout.count()):
                    if layout.itemAt(i).widget() == self.search_input:
                        # Déconnecter les anciens signaux
                        self._safe_disconnect_search_signals()
                        
                        # Supprimer l'ancien widget
                        layout.removeWidget(self.search_input)
                        self.search_input.deleteLater()
                        
                        # Ajouter le nouveau
                        layout.insertWidget(i, new_input)
                        self.search_input = new_input
                        
                        # Reconnecter les signaux
                        self.search_input.textChanged.connect(
                            self.advanced_search_service.search_with_debounce
                        )
                        search_found = True
                        break
                
                # Tentative 2: Si pas trouvé, chercher dans les sous-layouts
                if not search_found:
                    def find_and_replace_in_layout(layout_to_search, level=0):
                        for i in range(layout_to_search.count()):
                            item = layout_to_search.itemAt(i)
                            if item.widget() == self.search_input:
                                # Déconnecter signaux
                                self._safe_disconnect_search_signals()
                                
                                # Remplacer dans ce layout
                                layout_to_search.removeWidget(self.search_input)
                                self.search_input.deleteLater()
                                layout_to_search.insertWidget(i, new_input)
                                
                                # Mettre à jour la référence 
                                self.search_input = new_input
                                
                                # Reconnecter signaux
                                self.search_input.textChanged.connect(
                                    self.advanced_search_service.search_with_debounce
                                )
                                return True
                            
                            # Si c'est un widget avec un layout, chercher récursivement
                            widget = item.widget()
                            if widget and hasattr(widget, 'layout') and widget.layout():
                                if find_and_replace_in_layout(widget.layout(), level + 1):
                                    return True
                            
                            # Si c'est un layout item direct
                            if item.layout():
                                if find_and_replace_in_layout(item.layout(), level + 1):
                                    return True
                        
                        return False
                    
                    # Chercher récursivement
                    if find_and_replace_in_layout(layout):
                        search_found = True
                    
                # Tentative 3: Fallback setParent si toujours pas trouvé
                if not search_found:
                    self._safe_fallback_replace_search_input(new_input, parent)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur remplacement fallback search_input")
    def _safe_fallback_replace_search_input(self, new_input, parent):
        """Helper sécurisé pour remplacement fallback du search_input"""
        # Déconnecter les anciens signaux
        try:
            self.search_input.textChanged.disconnect()
        except:
            pass

        # Garder les propriétés originales
        size_hint = self.search_input.sizeHint()
        min_size = self.search_input.minimumSize()
        max_size = self.search_input.maximumSize()

        # Configurer le nouveau avec les mêmes propriétés
        new_input.setParent(parent)
        new_input.setMinimumSize(min_size)
        new_input.setMaximumSize(max_size)
        new_input.resize(size_hint)

        # Supprimer l'ancien et montrer le nouveau
        self.search_input.hide()
        self.search_input.deleteLater()
        new_input.show()

        # Remplacer la référence
        self.search_input = new_input

        # Reconnecter les signaux
        self.search_input.textChanged.connect(
            self.advanced_search_service.search_with_debounce
        )

    # --- Méthodes de gestion des données ---

    def _on_header_clicked(self, logical_index: int):
        """Gérer le clic sur un header pour trier"""
        # PHASE 3.1: Déléguer au service de tri
        if Config.USE_NEW_SORTING_FILTERING_SERVICE and hasattr(self, 'sorting_filtering_service') and self.sorting_filtering_service:
            self.sorting_filtering_service.on_header_clicked(logical_index)

    def _get_modern_style(self) -> str:
        """Retourne le CSS moderne de l'application via StyleManager"""
        return StyleManager.get_modern_style()
    
    @handle_ui_errors(log_prefix="Erreur mise à jour numéros de lignes", show_message=False)
    def _update_row_numbers(self):
        """Mettre à jour les numéros de lignes après un tri"""
        for row in range(self.table.rowCount()):
            self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
        app_logger.debug(f"Numéros de lignes mis à jour pour {self.table.rowCount()} lignes")
    
    @handle_ui_errors(log_prefix="Erreur mise à jour pagination", show_message=False)
    def _update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination - PHASE 5: Délégation vers NavigationService"""
        if hasattr(self, 'navigation_service'):
            # Mettre à jour le total des lignes dans le service
            self.navigation_service.update_total_rows(getattr(self, 'total_rows', 0))
            # Le service gère automatiquement la mise à jour des contrôles
        else:
            app_logger.warning("NavigationService non disponible, pagination manuelle non implémentée")
    
    def _reload_current_search(self):
        """Recharger les données avec la recherche et filtres actuels (factorisation pagination)"""
        search_term = self.advanced_search_service.get_current_search_term_with_fallback(self)
        self.table_controller.load_data(search_term, is_search=bool(search_term))
    
    def _next_page(self):
        """Aller à la page suivante - PHASE 5: Délégation vers NavigationService"""
        self.navigation_service.next_page()
    
    def _previous_page(self):
        """Aller à la page précédente - PHASE 5: Délégation vers NavigationService"""
        self.navigation_service.previous_page()
    
    def _go_to_page(self, page: int):
        """Aller à une page spécifique - PHASE 5: Délégation vers NavigationService"""
        self.navigation_service.go_to_page(page)
    
    def _go_to_last_page(self):
        """Aller à la dernière page - PHASE 5: Délégation vers NavigationService"""
        self.navigation_service.go_to_last_page()
    
    def _change_page_size(self, size_text: str):
        """Changer la taille de page - PHASE 5: Délégation vers NavigationService"""
        self.navigation_service.change_page_size(size_text)
    
    def _toggle_show_all(self):
        """Basculer entre affichage paginé et affichage de toutes les lignes"""
        return self._safe_toggle_show_all()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur basculement affichage")
    def _safe_toggle_show_all(self):
        """Helper sécurisé pour basculer entre affichage paginé et affichage de toutes les lignes"""
        if self.use_pagination:
            # Passer en mode "Toutes les lignes"
            message = (f"Voulez-vous afficher toutes les {self.total_rows} lignes?\n\n"
                      "⚠️ Cela peut être lent si vous avez beaucoup de données.")

            if MessageHelper.ask_question(self, message, "Afficher toutes les lignes"):
                self.use_pagination = False
                self.show_all_btn.setText("📄 Pagination")
                self.show_all_btn.setToolTip("Revenir à l'affichage paginé")
                self.table_controller.load_data()
        else:
            # Revenir en mode pagination
            self.use_pagination = True
            self.show_all_btn.setText("📋 Toutes les lignes")
            self.show_all_btn.setToolTip("Afficher toutes les lignes (peut être lent)")
            if hasattr(self.table_controller, 'current_page'):
                self.table_controller.current_page = 0
            self.table_controller.load_data()
    
    def _navigate_to_empty_cell(self, direction='down'):
        """Navigation intelligente - PHASE 5: Délégation vers CellEditingService"""
        return self.cell_editing_service.navigate_to_empty_cell(direction)

    @handle_ui_errors(log_prefix="Erreur affichage valeurs colonne", show_message=True)
    def _show_column_values_list(self):
        """Afficher la fenêtre d'auto-complétion selon la colonne (Cmd+D) - Délégation au service"""
        current_item = self.table.currentItem()
        current_col = self.table.currentColumn()

        selected_value = self.autocompletion_service.show_column_values_dialog(
            self.table, current_item, current_col
        )

        if selected_value is not None:
            # Écrire dans le modèle → cell_edited → pipeline complet (save, undo, etc.)
            row = self.table.currentRow()
            model = self.table_controller.model
            if model:
                model.setData(model.index(row, current_col), selected_value, Qt.EditRole)

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

    # ── Helpers table unifiés (QTableWidget / QTableView) ───────────────────

    def _get_cell_text(self, row: int, col: int) -> str:
        """Lire le texte d'une cellule — fonctionne en mode QTableWidget et QTableView."""
        model = self.table_controller.model
        if model:
            return model.data(model.index(row, col), Qt.DisplayRole) or ""
        return ""

    def _set_cell_value_in_table(self, row: int, col: int, value: str) -> None:
        """Écrire une valeur dans la table sans déclencher les signaux d'édition.

        Bloque les signaux du modèle pour éviter le déclenchement de cell_edited
        (undo/redo silencieux). Émet dataChanged manuellement pour rafraîchir la vue.
        """
        model = self.table_controller.model
        if model:
            model.blockSignals(True)
            model.setData(model.index(row, col), value)
            model.blockSignals(False)
            # Notifier la vue manuellement (dataChanged était bloqué)
            idx = model.index(row, col)
            model.dataChanged.emit(idx, idx, [Qt.DisplayRole])

    # ────────────────────────────────────────────────────────────────────────

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
        return self._safe_init_previous_values()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur initialisation valeurs précédentes")
    def _safe_init_previous_values(self):
        """Helper sécurisé pour initialiser les valeurs précédentes"""
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self.previous_values[(row, col)] = self._get_cell_text(row, col)
    
    def _on_cell_changed(self, item: QTableWidgetItem):
        """Gérer les modifications de cellules (mode QTableWidget)."""
        if self.table.signalsBlocked():
            return

        row, col = item.row(), item.column()
        new_value = item.text()

        # Obtenir l'ancienne valeur
        key = (row, col)
        old_value = self.previous_values.get(key, '')

        if old_value == new_value:
            return

        # Colonne Nb Pièces — lecture seule : restaurer et ignorer
        if col == len(Config.DB_HEADERS):
            item.setText(old_value)
            return

        # Validation
        field_name = self._get_db_field_name(col)
        if field_name:
            validation_result = self.validator.validate_field(field_name, new_value)
            if not validation_result.is_valid:
                MessageHelper.show_warning(self, validation_result.error_message, Messages.TITLE_WARNING)
                item.setText(old_value)
                return

        db_id_str = self.table.verticalHeaderItem(row).text() if self.table.verticalHeaderItem(row) else None
        self._apply_cell_edit_logic(row, col, old_value, new_value, db_id_str)

    def _on_cell_changed_model(self, row: int, col: int, old_value: str, new_value: str):
        """Gérer les modifications de cellules (mode QTableView).
        Reçoit (row, col, old_value, new_value) depuis AppareillsTableModel.cell_edited.
        """
        model = self.table_controller.model if hasattr(self.table_controller, 'model') else None
        if model and model.signalsBlocked():
            return

        if old_value == new_value:
            return

        # Validation (les colonnes read-only sont filtrées en amont par flags() du modèle)
        field_name = self._get_db_field_name(col)
        if field_name:
            validation_result = self.validator.validate_field(field_name, new_value)
            if not validation_result.is_valid:
                MessageHelper.show_warning(self, validation_result.error_message, Messages.TITLE_WARNING)
                if model:
                    model.blockSignals(True)
                    model.setData(model.index(row, col), old_value)
                    model.blockSignals(False)
                    idx = model.index(row, col)
                    model.dataChanged.emit(idx, idx, [Qt.DisplayRole])
                return

        db_id = model.get_db_id(row) if model else None
        self._apply_cell_edit_logic(row, col, old_value, new_value, db_id)

    def _apply_cell_edit_logic(self, row: int, col: int, old_value: str, new_value: str, db_id):
        """Tronc commun post-validation : sauvegarde, historique et mises à jour UI."""
        # Sauvegarde
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            self.auto_save_manager.mark_cell_modified(row, col, self.table)
        elif not Config.ENABLE_EVENT_DRIVEN_SAVE:
            self.modified_cells.add((row, col))
            self.save_indicator.setText(Config.get_message('save_pending'))
            self.save_indicator.setStyleSheet("color: orange;")
        else:
            if hasattr(self, 'event_driven_save_service') and self.event_driven_save_service:
                self.event_driven_save_service.handle_cell_changed(row, col, new_value, self.table)
            else:
                app_logger.warning("EventDrivenSaveService non disponible, fallback vers méthode locale")
                self._save_cell_immediately(row, col, new_value)

        # Historique undo
        self.undo_manager.add_action({
            'type': 'cell_edit',
            'row': row,
            'col': col,
            'old_value': old_value,
            'new_value': new_value,
            'db_id': db_id,
        })
        self._safe_add_to_grouped_history(row, col, old_value, new_value)

        # Mettre à jour la valeur précédente
        self.previous_values[(row, col)] = new_value

        self._update_toolbar_states()
        self._update_incomplete_button_visibility()
        if hasattr(self, 'duplicate_indicator_service'):
            self.duplicate_indicator_service.schedule_update()

    def _on_selection_changed(self):
        """Gérer le changement de sélection"""
        self._position_drag_handle()
        self.pieces_panel_service.update_pieces_panel()

    # --- Méthodes utilitaires ---

    @handle_ui_column_errors(return_value="Colonne inconnue")
    def _get_column_display_name(self, col_index):
        """
        Récupère le nom d'affichage d'une colonne basé sur son index

        Args:
            col_index (int): Index de la colonne (0-based)

        Returns:
            str: Nom d'affichage de la colonne
        """
        if 0 <= col_index < len(Config.UI_HEADERS):
            return Config.UI_HEADERS[col_index]
        else:
            return f"Colonne {col_index + 1}"

    # --- Méthodes d'export ---

    def _export_data(self, export_format: ExportFormat):
        """Export avec sélection de référence - PHASE 4 : Service unifié"""
        # Pour les exports HTML, utiliser l'export rapide sans dialogue de référence
        if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
            return self.export_manager.export_data(export_format, ExportType.QUICK)
        else:
            return self.export_manager.export_data(export_format, ExportType.MAIN)

    def _export_data_legacy(self, export_format: ExportFormat):
        """Export legacy - PHASE 4 : Service unifié avec fallbacks"""
        return self.export_manager.export_data(export_format, ExportType.LEGACY)

    # --- Méthodes utilitaires ---

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur ajout historique groupé")
    def _safe_add_to_grouped_history(self, row: int, col: int, old_value: str, new_value: str):
        """Helper sécurisé pour ajouter à l'historique groupé avec fallback"""
        # Obtenir le nom de la colonne
        column_name = self._get_column_display_name(col)

        # Utiliser le service de groupement d'historique
        if getattr(self, 'auto_save_enabled', True):
            try:
                db_id = self.table_fill_service.get_db_id_from_row(self.table, row)
                self.grouped_history_service.add_modification(db_id, column_name, old_value, new_value)
            except Exception as e:
                # Fallback vers historique normal en cas d'erreur
                app_logger.warning(f"Erreur historique groupé dans _on_cell_editing_updated, fallback: {e}")
                self.user_interaction_service.add_to_history(f"Modification {column_name}: '{old_value}' → '{new_value}'")

    def _update_toolbar_states(self):
        """Mettre à jour l'état des boutons"""
        self.undo_action.setEnabled(self.undo_manager.can_undo())
        self.redo_action.setEnabled(self.undo_manager.can_redo())

    @handle_drag_operation_errors(return_value=None, title="Erreur vérification sélection")
    def _safe_check_selection(self):
        """Vérifier la sélection et cacher le drag handle si vide"""
        sm = self.table.selectionModel()
        if not sm or not sm.hasSelection():
            self.drag_handle.hide()
            return None
        return sm.selectedIndexes()

    @handle_drag_operation_errors(return_value=None, title="Erreur positionnement drag handle")
    def _safe_position_drag_handle_at_selection(self, selected):
        """Positionner le drag handle à la sélection"""
        # selected = liste de QModelIndex (depuis selectionModel().selectedIndexes())
        bottom_row = max(idx.row() for idx in selected)
        right_col = max(idx.column() for idx in selected)
        model_idx = self.table.model().index(bottom_row, right_col)
        rect = self.table.visualRect(model_idx)

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

    def _position_drag_handle(self):
        """Positionner la poignée de glisser-déposer"""
        # Vérifier si tous les objets existent encore
        if not hasattr(self, 'table') or self.table is None:
            return

        if not hasattr(self, 'drag_handle') or self.drag_handle is None:
            return

        selected = self._safe_check_selection()
        if selected is None:
            return

        self._safe_position_drag_handle_at_selection(selected)

    # --- Méthodes d'action (stubs pour les fonctionnalités à implémenter) ---

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur peuplement dropdown")
    def _safe_populate_dropdown_values(self, combo_widget: QComboBox, column_index: int, db_field: str):
        """Peupler les valeurs du dropdown avec les données uniques (version protégée)"""
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

    def _populate_dropdown_values(self, combo_widget: QComboBox, column_index: int):
        """Peupler les valeurs du dropdown avec les données uniques de la BDD"""
        # Déterminer le champ de base de données selon l'index de colonne
        if column_index == 0:  # Type
            db_field = "type"
        elif column_index == 1:  # Fabricant
            db_field = "manufacturer"
        else:
            return  # Ne pas traiter d'autres colonnes

        self._safe_populate_dropdown_values(combo_widget, column_index, db_field)

    def _auto_save(self):
        """Sauvegarde automatique optimisée par lots"""
        # PHASE 3.3: Déléguer au DatabaseOperationsService si activé
        if Config.USE_NEW_DATABASE_OPERATIONS_SERVICE and hasattr(self, 'database_operations_service') and self.database_operations_service:
            self.database_operations_service.auto_save()
            return

        # Feature Flag: AutoSaveManager fallback
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            self.auto_save_manager.perform_auto_save(self.table)

    def _manual_save(self):
        """Sauvegarde manuelle"""
        # PHASE 3.3: Déléguer au DatabaseOperationsService si activé
        if Config.USE_NEW_DATABASE_OPERATIONS_SERVICE and hasattr(self, 'database_operations_service') and self.database_operations_service:
            success = self.database_operations_service.manual_save()
            if success:
                self.statusbar.showMessage(Config.get_message('auto_save_done'), Config.STATUS_MESSAGE_TIMEOUT)
                self.user_interaction_service.add_to_history("Sauvegarde manuelle effectuée")
            return

        # Feature Flag: AutoSaveManager fallback
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            self.auto_save_manager.trigger_manual_save()
        else:
            self._auto_save()
            self.statusbar.showMessage(Config.get_message('auto_save_done'), Config.STATUS_MESSAGE_TIMEOUT)
            self.user_interaction_service.add_to_history("Sauvegarde manuelle effectuée")

    def _save_cell_immediately(self, row: int, col: int, new_value: str):
        """
        [DEPRECATED - Phase 4 Factorisation] Sauvegarde immédiate d'une cellule

        MIGRATION: Cette méthode a été migrée vers EventDrivenSaveService.save_cell_immediately()
        UTILISATION: Fallback temporaire uniquement
        TODO: Supprimer après validation complète du service
        """
        return self._safe_save_cell_immediately(row, col, new_value)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur sauvegarde cellule")
    def _safe_save_cell_immediately(self, row: int, col: int, new_value: str):
        """Helper sécurisé pour la sauvegarde immédiate d'une cellule"""
        # Utiliser le DatabaseOperationsService pour sauvegarde immédiate
        if Config.USE_NEW_DATABASE_OPERATIONS_SERVICE and hasattr(self, 'database_operations_service'):
            # Créer un set avec la cellule modifiée pour utiliser l'API existante
            modified_cells = {(row, col)}

            # Convertir vers le format attendu par save_cells_batch
            updates_by_db_id = self.database_operations_service._convert_modified_cells_to_updates(modified_cells, self.table)

            # Sauvegarder immédiatement
            success = self.database_operations_service.save_cells_batch(updates_by_db_id)

            if success:
                # Mettre à jour l'indicateur de sauvegarde
                self.save_indicator.setText(Config.get_message('save_success'))
                self.save_indicator.setStyleSheet("color: green;")

                # Remettre l'indicateur à l'état normal après un délai
                QTimer.singleShot(2000, lambda: self._reset_save_indicator())
            else:
                app_logger.warning(f"Échec sauvegarde immédiate cellule ({row}, {col})")

    def _reset_save_indicator(self):
        """
        [DEPRECATED - Phase 4 Factorisation] Remettre l'indicateur à l'état normal

        MIGRATION: Cette méthode a été migrée vers EventDrivenSaveService._reset_save_indicator()
        UTILISATION: Fallback temporaire uniquement
        TODO: Supprimer après validation complète du service
        """
        return self._safe_reset_save_indicator()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur réinitialisation indicateur sauvegarde")
    def _safe_reset_save_indicator(self):
        """Helper sécurisé pour remettre l'indicateur à l'état normal"""
        self.save_indicator.setText(Config.get_message('connected'))
        self.save_indicator.setStyleSheet("color: green;")

    def _get_cell_db_info(self, item: QTableWidgetItem) -> Tuple[Optional[int], Optional[str]]:
        """Récupérer les informations DB d'une cellule - PHASE 5: Délégation vers CellEditingService"""
        return self.cell_editing_service.get_cell_db_info(item)
        
        # Récupérer le nom de colonne
        column_name = self._get_db_field_name(col)
        
        return db_id, column_name

    def _update_cell_in_db(self, item: QTableWidgetItem, skip_history: bool = False):
        """Mettre à jour une cellule - PHASE 5: Délégation vers CellEditingService"""
        return self.cell_editing_service.update_cell_in_db(item, skip_history)
    
    def _handle_successful_cell_update(self, item: QTableWidgetItem, old_value: str, new_value: str, skip_history: bool):
        """Gérer les actions post mise à jour - PHASE 5: Appel délégué + actions spécifiques"""
        return self._safe_handle_successful_cell_update(item, old_value, new_value, skip_history)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur traitement mise à jour cellule")
    def _safe_handle_successful_cell_update(self, item: QTableWidgetItem, old_value: str, new_value: str, skip_history: bool):
        """Helper sécurisé pour gérer les actions post mise à jour"""
        row, col = item.row(), item.column()

        # Actions spécifiques à l'interface principale
        if old_value != new_value and not skip_history:
            # NOUVEAU: Utiliser le service de groupement d'historique (helper factorisé)
            self._safe_add_to_grouped_history(row, col, old_value, new_value)
        
        self.modified_cells.discard((row, col))
        item.setBackground(QColor(255, 255, 255))  # Blanc
        
        # Mettre à jour l'indicateur de sauvegarde
        if not self.modified_cells:
            self.save_indicator.setText(Config.get_message('save_success'))
            self.save_indicator.setStyleSheet("color: green;")

    def _save_drag_changes(self):
        """Sauvegarder les modifications du glisser-déposer"""
        return self._safe_save_drag_changes()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur sauvegarde changements drag")
    def _safe_save_drag_changes(self):
        """Helper sécurisé pour sauvegarder les modifications du glisser-déposer"""
        if not (hasattr(self, 'drag_handle') and self.drag_handle.orig_selection):
            return

        selection = self.drag_handle.orig_selection

        # CORRECTION: Utiliser uniquement les lignes réellement modifiées (comme double-clic)
        # Au lieu de sauvegarder TOUTES les lignes dans la direction du drag
        modified_rows = sorted(list(self.drag_handle.modified_rows_set))

        if not modified_rows:
            return

        # Réutiliser la logique du double-clic pour une sauvegarde optimisée
        self._save_specific_rows(modified_rows, selection.leftColumn(), selection.rightColumn())
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur sauvegarde lignes spécifiques")
    def _save_specific_rows(self, modified_rows, start_col, end_col):
        """Sauvegarder uniquement les lignes modifiées (logique réutilisée du double-clic)"""
        # Suspendre les invalidations de cache pendant la sauvegarde
        if hasattr(self, 'db_manager'):
            cache_service = getattr(self.db_manager, 'cache_invalidation', None)
            if cache_service:
                cache_service.suspend_invalidation("drag & drop - lignes modifiées")

        try:
            saved_count = 0
            cells_to_clean = []  # Cellules à nettoyer de modified_cells

            for row in modified_rows:
                for col in range(start_col, end_col + 1):
                    if hasattr(self, 'event_driven_save_service') and self.event_driven_save_service:
                        new_value = self._get_cell_text(row, col)
                        self.event_driven_save_service.handle_cell_changed(row, col, new_value, self.table)
                        saved_count += 1
                        cells_to_clean.append((row, col))

            # Nettoyer les cellules de modified_cells pour éviter les sauvegardes répétées
            if hasattr(self, 'modified_cells') and cells_to_clean:
                for cell_coords in cells_to_clean:
                    self.modified_cells.discard(cell_coords)

        finally:
            # Reprendre les invalidations avec une invalidation globale
            if hasattr(self, 'db_manager'):
                cache_service = getattr(self.db_manager, 'cache_invalidation', None)
                if cache_service:
                    cache_service.resume_invalidation(force_invalidate=True)

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
                stripped_line.startswith('Déjà associées :')):
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

    @handle_navigation_errors(return_value=None, title="Erreur traitement lien historique")
    def _safe_handle_history_link(self, url_str: str):
        """Gérer les clics sur les liens dans l'historique - Version sécurisée"""
        self.user_interaction_service.show_error(f"Lien non reconnu: {url_str}")

    def _handle_history_link(self, url):
        """Gérer les clics sur les liens dans l'historique"""
        from .qt_imports import QUrl
        url_str = url.toString() if isinstance(url, QUrl) else str(url)
        self._safe_handle_history_link(url_str)

    def _add_piece(self):
        """Ajouter une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.add_piece()

    def _edit_piece(self, item: QListWidgetItem):
        """Éditer une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.edit_piece(item)

    def _delete_piece(self, item: QListWidgetItem):
        """Supprimer une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.delete_piece(item)
    
    def _copy_piece(self, item: QListWidgetItem):
        """Copier une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.copy_piece(item)
    
    def _delete_piece_from_selected(self, item: QListWidgetItem):
        """Supprimer une pièce des appareils sélectionnés - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.delete_piece_from_selected(item)

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

    @handle_navigation_errors(return_value=False, title="Erreur mise à jour DB lors du undo")
    def _safe_update_db_for_undo(self, db_id: str, col: int, old_value: str) -> bool:
        """Mettre à jour la DB lors d'un undo - Version sécurisée"""
        field_name = self._get_db_field_name(col)
        if field_name:
            self.db_manager.update_cell(int(db_id), field_name, old_value)
        return True

    @handle_navigation_errors(return_value=False, title="Erreur mise à jour DB lors du redo")
    def _safe_update_db_for_redo(self, db_id: str, col: int, new_value: str) -> bool:
        """Mettre à jour la DB lors d'un redo - Version sécurisée"""
        field_name = self._get_db_field_name(col)
        if field_name:
            self.db_manager.update_cell(int(db_id), field_name, new_value)
        return True

    def _apply_undo_action(self, action: Dict[str, Any]):
        """Appliquer une action d'annulation"""
        if action['type'] == 'cell_edit':
            row, col = action['row'], action['col']
            self._apply_undo_redo_cell(row, col, action['old_value'], action.get('db_id'),
                                       self._safe_update_db_for_undo)

    def _apply_redo_action(self, action: Dict[str, Any]):
        """Appliquer une action de rétablissement"""
        if action['type'] == 'cell_edit':
            row, col = action['row'], action['col']
            self._apply_undo_redo_cell(row, col, action['new_value'], action.get('db_id'),
                                       self._safe_update_db_for_redo)

    def _apply_undo_redo_cell(self, row: int, col: int, value: str, db_id, db_updater) -> None:
        """Tronc commun undo/redo : écriture silencieuse + mise à jour DB + UI."""
        self._set_cell_value_in_table(row, col, value)
        if db_id:
            db_updater(db_id, col, value)
        self.previous_values[(row, col)] = value
        self._update_toolbar_states()
        self._update_incomplete_button_visibility()
        if hasattr(self, 'duplicate_indicator_service'):
            self.duplicate_indicator_service.schedule_update()

    def _fill_empty_fields(self):
        """Compléter les champs vides - Version refactorisée Phase 2.5c"""
        return self._safe_fill_empty_fields()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur complétion champs vides")
    def _safe_fill_empty_fields(self):
        """Helper sécurisé pour compléter les champs vides"""
        total_rows = self.table.rowCount()

        if total_rows == 0:
            self.user_interaction_service.show_info("Aucune donnée à compléter")
            return

        # Préparer les données pour le service
        table_data = []

        # Bloquer les signaux du modèle pendant la complétion
        if self.table_controller.model:
            self.table_controller.model.blockSignals(True)

        # Collecter les données de toutes les lignes
        for row in range(total_rows):
            header_item = self.table.verticalHeaderItem(row)
            if not header_item:
                continue

            db_id = self.table_fill_service.get_db_id_from_row(self.table, row)

            # Récupérer les données actuelles de la ligne
            appareil_data = {}
            for ui_col_idx in range(self.table.columnCount()):
                db_field = self._get_db_field_name(ui_col_idx)
                if db_field:  # Ignorer pieces_count
                    appareil_data[db_field] = self._get_cell_text(row, ui_col_idx)

            table_data.append({
                'id': db_id,
                'row': row,
                'data': appareil_data
            })

        result = self.data_management_service.auto_complete_empty_fields(table_data)

        # Débloquer les signaux du modèle
        if self.table_controller.model:
            self.table_controller.model.blockSignals(False)

        # Recharger les données pour refléter les changements
        self.table_controller.load_data()

        # Afficher le résultat
        if result.errors:
            error_msg = f"Erreurs lors de l'auto-complétion:\n" + "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                error_msg += f"\n... et {len(result.errors) - 5} autres erreurs"
            self.user_interaction_service.show_error(error_msg)

        if result.completed_count > 0:
            self.user_interaction_service.show_info(f"✅ Auto-complétion réussie !\n\n"
                           f"🎯 {result.completed_count} ligne(s) complétée(s)\n"
                           f"📊 {result.total_rows_processed} ligne(s) traitée(s)")
            self.user_interaction_service.add_to_history(
                f"Autocomplétion: {result.completed_count} appareil(s) complété(s) "
                f"sur {result.total_rows_processed} traité(s)"
            )
            self._auto_save()
        else:
            self.user_interaction_service.show_info("ℹ️ Aucun champ à compléter automatiquement.\n\n"
                           "Tous les appareils ont déjà un Type et un Fabricant, "
                           "ou aucune référence similaire n'a été trouvée.")

    def _clean_data(self):
        """Nettoyer les données avec prévisualisation détaillée - Version refactorisée Phase 2.5c"""
        return self._safe_clean_data()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur nettoyage données")
    def _safe_clean_data(self):
        """Helper sécurisé pour nettoyer les données"""
        # Ouvrir la fenêtre de nettoyage refactorisée qui gère tout
        result = self.data_management_service.prepare_data_cleaning()

        if result is None:
            # L'utilisateur a annulé ou il y a eu une erreur
            return

        # La fenêtre refactorisée gère tout le processus
        # Si on arrive ici, le nettoyage a été effectué avec succès

        if result.get('user_choice') == 'applied':
            # Rafraîchir l'affichage après nettoyage
            self._force_refresh_display()

            # Invalider le cache des doublons après nettoyage
            if hasattr(self, 'duplicate_indicator_service'):
                self.duplicate_indicator_service.invalidate_cache("nettoyage doublons")
    
    def _manage_categories(self):
        """Gérer les catégories"""
        return self._safe_manage_categories()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur gestion catégories")
    def _safe_manage_categories(self):
        """Helper sécurisé pour gérer les catégories"""
        current_categories = self.db_manager.get_categories()
        new_categories = self.dialog_service.get_categories(self, current_categories)

        if new_categories is not None:
            self.db_manager.update_categories(new_categories)
            self.statusbar.showMessage(
                Config.get_message('categories_updated'),
                Config.STATUS_MESSAGE_TIMEOUT
            )
    
    def _import_file(self):
        """Importer un fichier CSV ou PDF - Nouvelle version avec ImportManager"""
        # PHASE 3.2: Déléguer au ImportExportService si activé
        if Config.USE_NEW_IMPORT_EXPORT_SERVICE and hasattr(self, 'import_export_service') and self.import_export_service:
            self.import_export_service.import_file()
            return

        # Ancien système (pour compatibilité/rollback)
        from .qt_imports import QFileDialog
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Importer fichier(s)", "",
            "Fichiers supportés (*.csv *.pdf);;Fichiers CSV (*.csv);;Fichiers PDF (*.pdf)"
        )

        if filenames:
            # PHASE 2.2 OPTIMISATION: Utiliser callback pour dialogue non-bloquant
            self.import_manager.import_files(
                filenames,
                show_dialog=True,
                callback=self._on_import_complete
            )
    
    def _get_import_options_unified(self, detected_columns=None, default_ref_piece=None, import_method="CSV", sample_data=None):
        """Dialogue unifié pour choisir les options d'import - Phase 2.6"""
        # Déléguer au service DialogService
        result = self.dialog_service.get_import_options_unified(
            detected_columns=detected_columns,
            default_ref_piece=default_ref_piece,
            import_method=import_method,
            sample_data=sample_data
        )
        
        # Convertir le dictionnaire en tuple pour compatibilité avec le code existant
        if result is None:
            return None
        
        # Extraire les valeurs du dictionnaire et les retourner comme tuple
        return (
            result.get('mode', 0),  # import_type (mode d'import)
            result.get('reference', ''),  # ref_piece
            None,  # third_column_choice (pas utilisé dans cette version)
            False,  # has_headers (pas utilisé dans cette version)  
            ''  # libelle_piece (pas utilisé dans cette version)
        )

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
        
        self.user_interaction_service.show_info(summary)
    
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
        
        # Doublons traités dans le fichier
        if duplicates_ignored > 0:
            summary += f"==> Doublons traités : {duplicates_ignored}\n"
        
        # Section Associations de pièce
        summary += "Associations de pièce :\n"
        
        # Nouvelles associations
        associations_created = results.get('associations_created', 0)
        associations_existing = results.get('associations_existing', 0)
        summary += f"==> Nouvelles : {associations_created}\n"
        summary += f"==> Déjà associées : {associations_existing}"
        
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
        self.user_interaction_service.add_to_history(console_summary)
    
    def _on_import_complete(self, results):
        """
        Callback appelé quand l'import est terminé (mode non-bloquant)

        PHASE 2.2: Cette méthode est appelée par ImportManager après validation
        du dialogue et exécution de l'import.
        """
        if results:
            self._show_import_results_new(results)

            # Réinitialiser tous les champs de recherche après import
            if hasattr(self, 'search_input') and self.search_input:
                self.search_input.blockSignals(True)
                self.search_input.clear()
                self.search_input.blockSignals(False)
            if hasattr(self, 'advanced_search_service'):
                self.advanced_search_service.clear_search()
            self.table_controller.clear_column_filters()

            self.table_controller.load_data()  # Rafraîchir l'affichage sans filtres

    def _show_import_results_new(self, results):
        """Traiter les résultats d'import du nouveau système ImportManager - SEULEMENT dans l'historique"""
        return self._safe_show_import_results_new(results)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur affichage résultats import")
    def _safe_show_import_results_new(self, results):
        """Helper sécurisé pour afficher les résultats d'import"""
        # Vérifier les erreurs - les afficher si critique
        if results.get('errors'):
            error_msg = "Erreurs lors de l'import:\n" + "\n".join(results['errors'])
            QMessageBox.warning(self, "Erreurs d'import", error_msg)

        # Créer un résumé détaillé EXACTEMENT comme l'ancien format
        # Note: _add_to_history ajoute automatiquement le timestamp, pas besoin de le faire ici

        # Déterminer le type d'import et ajouter le nom de fichier
        if results.get('total_files', 0) > 1:
            import_type = f"📊 Import Multi-fichiers ({results['total_files']} fichiers)"
        else:
            # Pour l'import simple, récupérer le nom du fichier
            file_details = results.get('file_details', [])
            if file_details:
                first_file = file_details[0]
                filename = first_file.get('filename', 'fichier')
                import_type = f"📊 Import {filename}"
            else:
                import_type = "📊 Import"

        # Commencer le résumé
        summary = f"{import_type}:\n"

        # Si c'est multi-fichiers, lister les fichiers avec leurs détails
        if results.get('total_files', 0) > 1:
            file_details = results.get('file_details', [])
            for detail in file_details:
                summary += f"📄 Fichier {detail['type']} {detail['filename']}: {detail['lines_processed']} lignes extraites\n"
        else:
            # Pour l'import simple, afficher aussi le détail du fichier
            file_details = results.get('file_details', [])
            if file_details:
                detail = file_details[0]
                summary += f"📄 Fichier {detail['type']}: {detail['lines_processed']} lignes extraites\n"

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
        summary += f"     ==> Doublons traités : {results.get('duplicates_in_file', 0)}\n"

        # Section Associations de pièce (format exact)
        summary += "Associations de pièce :\n"
        summary += f"     ==> Nouvelles : {results.get('associations_created', 0)}\n"
        summary += f"     ==> Déjà associées : {results.get('associations_existing', 0)}"

        # Ajouter SEULEMENT à l'historique (timestamp ajouté automatiquement)
        duration_ms = results.get('processing_time_ms')
        self.user_interaction_service.add_to_history(summary, duration_ms=duration_ms)

    def _validate_and_detect_inconsistencies(self):
        """Ouvrir la fenêtre interactive de validation et incohérences"""
        return self._safe_validate_and_detect_inconsistencies()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur ouverture validation")
    def _safe_validate_and_detect_inconsistencies(self):
        """Helper sécurisé pour ouvrir la fenêtre de validation"""
        if not hasattr(self, 'validation_window') or not self.validation_window:
            self.validation_window = ValidationWindow(self)

        self.validation_window.show()
        self.validation_window.raise_()
        self.validation_window.activateWindow()
    
    def _open_pieces_manager(self):
        """Ouvrir la fenêtre de gestion des pièces - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.open_pieces_manager()

    def _update_incomplete_button_visibility(self):
        """Mettre à jour la visibilité du bouton incomplètes selon les données"""
        return self._safe_update_incomplete_button_visibility()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mise à jour bouton incomplètes")
    def _safe_update_incomplete_button_visibility(self):
        """Helper sécurisé pour mise à jour visibilité bouton incomplètes"""
        # Utiliser le service optimisé au lieu de l'ancienne méthode
        if hasattr(self, 'incomplete_button_service'):
            # Programmer une mise à jour différée pour éviter les appels répétés
            self.incomplete_button_service.schedule_update()
        else:
            # Fallback vers l'ancienne méthode si le service n'est pas encore initialisé
            self._update_incomplete_button_visibility_legacy()

    def _update_incomplete_button_visibility_legacy(self):
        """Ancienne méthode de mise à jour (fallback)"""
        return self._safe_update_incomplete_button_visibility_legacy()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mise à jour bouton incomplètes (legacy)")
    def _safe_update_incomplete_button_visibility_legacy(self):
        """Helper sécurisé pour mise à jour legacy du bouton incomplètes"""
        incomplete_count = self.db_manager.count_incomplete_devices()
        if hasattr(self, 'incomplete_filter_btn'):
            if incomplete_count > 0:
                self.incomplete_filter_btn.show()
                from src.core.config import pluralize
                if self.show_incomplete_only:
                    self.incomplete_filter_btn.setText(f"📋 Filtre actif, plus que {pluralize(incomplete_count, 'ligne')}")
                    self.incomplete_filter_btn.setToolTip(f"Filtre actif - {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                else:
                    self.incomplete_filter_btn.setText(f"📋 {pluralize(incomplete_count, 'incomplète')}")
                    self.incomplete_filter_btn.setToolTip(f"Afficher uniquement les {pluralize(incomplete_count, 'ligne')} avec des champs vides")
            else:
                self.incomplete_filter_btn.hide()
                if self.show_incomplete_only:
                    self.show_incomplete_only = False
                    self.table_controller.load_data()

    def _toggle_incomplete_filter(self, checked: bool):
        """Basculer le filtre pour afficher seulement les lignes incomplètes"""
        # PHASE 3.1: Déléguer au service de tri/filtrage si activé
        if Config.USE_NEW_SORTING_FILTERING_SERVICE and hasattr(self, 'sorting_filtering_service') and self.sorting_filtering_service:
            # Synchroniser l'état du filtre avec IncompleteButtonService
            if hasattr(self, 'incomplete_button_service'):
                self.incomplete_button_service.set_filter_active(checked)
                app_logger.info(f"🔄 Synchronisation incomplete_button_service: filtre {'activé' if checked else 'désactivé'}")

            self.sorting_filtering_service.toggle_incomplete_filter()
            return

        # Legacy fallback (conservé temporairement)
        self.show_incomplete_only = checked
        if hasattr(self, 'incomplete_button_service'):
            self.incomplete_button_service.set_filter_active(checked)
        if checked:
            self.search_input.clear()
        search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
        self.table_controller.load_data(search_term)

    def _on_incomplete_filter_auto_disabled(self):
        """Gérer la désactivation automatique du filtre lignes incomplètes"""
        return self._safe_on_incomplete_filter_auto_disabled()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur rechargement après désactivation filtre")
    def _safe_on_incomplete_filter_auto_disabled(self):
        """Helper sécurisé pour désactivation automatique du filtre"""
        app_logger.info("🔄 SIGNAL REÇU: Rechargement des données après désactivation auto du filtre")

        # Désactiver le filtre dans tous les systèmes
        self.show_incomplete_only = False

        # Désactiver le bouton dans l'interface
        if (hasattr(self, 'table_controller') and
            hasattr(self.table_controller, 'incomplete_filter_btn')):
            self.table_controller.incomplete_filter_btn.setChecked(False)
            app_logger.info("✅ Bouton désactivé dans l'interface")
        else:
            app_logger.warning("⚠️ Bouton incomplete_filter_btn non trouvé")

        # Désactiver dans le service de tri/filtrage si disponible
        if (Config.USE_NEW_SORTING_FILTERING_SERVICE and
            hasattr(self, 'sorting_filtering_service') and
            self.sorting_filtering_service):
            self.sorting_filtering_service.incomplete_filter_active = False
            app_logger.info("✅ Filtre désactivé dans sorting_filtering_service")

        # Informer l'utilisateur de la désactivation automatique
        if hasattr(self, 'statusbar'):
            self.statusbar.showMessage(
                "Tous les appareils sont complets — filtre désactivé",
                Config.STATUS_MESSAGE_TIMEOUT
            )

        # Forcer un rechargement complet en supprimant tous les filtres
        app_logger.info("🔄 Rechargement complet avec clear_filters=True")
        self._force_refresh_display(reset_page=False, clear_filters=True)
        app_logger.info("✅ Rechargement terminé via _force_refresh_display")

    def _force_refresh_display(self, reset_page=False, clear_filters=False):
        """Forcer le rafraîchissement complet de l'affichage du tableau"""
        return self._safe_force_refresh_display(reset_page, clear_filters)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur rafraîchissement forcé")
    def _safe_force_refresh_display(self, reset_page=False, clear_filters=False):
        """Helper sécurisé pour rafraîchissement complet de l'affichage"""
        # Sauvegarder l'état de recherche actuel - prioriser table_controller.pending_search_term
        temp_search = None
        if hasattr(self, 'table_controller') and hasattr(self.table_controller, 'pending_search_term'):
            temp_search = self.table_controller.pending_search_term
        elif hasattr(self, 'pending_search_term'):
            temp_search = self.pending_search_term

        # Si pas de recherche dans pending_search_term, essayer de récupérer depuis search_input
        if not temp_search and hasattr(self, 'search_input') and self.search_input.text().strip():
            temp_search = self.search_input.text().strip()

        # Retourner à la première page si demandé (après modifications globales)
        if reset_page:
            if hasattr(self.table_controller, 'current_page'):
                self.table_controller.current_page = 0

        # Nettoyer les filtres de colonnes si demandé
        if clear_filters and Config.USE_NEW_SORTING_FILTERING_SERVICE and hasattr(self, 'sorting_filtering_service'):
            self.sorting_filtering_service.clear_column_filters()

        # Débloquer les signaux du modèle si nécessaire pour éviter les blocages
        if self.table_controller.model and self.table_controller.model.signalsBlocked():
            self.table_controller.model.blockSignals(False)

        # Recharger avec les critères appropriés
        self.table_controller.load_data(temp_search)

        # Forcer la mise à jour de l'interface
        self.table.viewport().update()
        self.table.update()

        # Redimensionner les colonnes
        self.table.resizeColumnsToContents()

        # Mettre à jour le compteur
        self.user_interaction_service.update_counter()

        # Mettre à jour la visibilité du bouton incomplètes après rafraîchissement
        self._update_incomplete_button_visibility()

        # Repositionner la poignée de drag
        self._position_drag_handle()

        current_page = getattr(self.table_controller, 'current_page', 0) if hasattr(self, 'table_controller') else 0
        app_logger.debug(f"Rafraîchissement forcé terminé - Page: {current_page} - Critères: '{temp_search}' - Lignes affichées: {self.table.rowCount()}")

    @handle_log_viewer_errors(return_value=None, title="Erreur ouverture visualiseur logs")
    def _safe_open_log_viewer(self):
        """Ouvrir le visualiseur de logs (version protégée)"""
        if not hasattr(self, 'log_viewer') or not self.log_viewer:
            self.log_viewer = LogViewer(self)

        self.log_viewer.show()
        self.log_viewer.raise_()
        self.log_viewer.activateWindow()

    def _open_log_viewer(self):
        """Ouvrir le visualiseur de logs"""
        self._safe_open_log_viewer()
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur ouverture guide utilisateur")
    def _safe_open_user_guide(self):
        """Ouvrir le guide d'utilisation (version protégée)"""
        # URL du guide d'utilisation (vous pouvez la modifier selon vos besoins)
        guide_url = "https://github.com/PiLouZ/1001pieces_autofill-Claude/blob/main/README.md"

        # Message informatif avec options
        from .qt_imports import QMessageBox
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

    def _open_user_guide(self):
        """Ouvrir le guide d'utilisation"""
        self._safe_open_user_guide()
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur affichage guide local")
    def _safe_show_local_guide(self):
        """Afficher un guide d'utilisation local (version protégée)"""
        from .qt_imports import QDialog, QVBoxLayout, QTextEdit, QPushButton

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
2. **Collage** : Copiez des données depuis Excel/Calc et collez avec Cmd+V
3. **Référence de pièce** : Lors de l'import, la référence de pièce est automatiquement remplie avec le nom du fichier

### Navigation et édition
- **Double-clic** sur une cellule pour l'éditer
- **Entrée** : Valider et descendre à la cellule suivante
- **Suppr / Retour arrière** : Effacer les cellules sélectionnées

### Gestion des pièces
- **Gestionnaire de pièces** : Accessible via Gestion → 🔧 Pièces
- **Sélection multiple** : Cmd+Clic pour sélectionner plusieurs pièces à supprimer

### Fonctionnalités avancées
- **Glisser/Déposer** : Déposez des fichiers CSV directement sur le tableau
- **Auto-complétion** : Les champs vides sont automatiquement complétés via Action → Autocomplétion
- **Recherche avancée** : Utilisez `&&` (ET) et `||` (OU) dans la barre de recherche

---

## ⌨️ Raccourcis clavier

### Édition
| Raccourci | Action |
|-----------|--------|
| Cmd+N | Ajouter une nouvelle ligne |
| Cmd+Z | Annuler la dernière action |
| Cmd+Y | Rétablir l'action annulée |
| Cmd+C | Copier la sélection |
| Cmd+V | Coller depuis le presse-papiers |
| Cmd+S | Sauvegarder toutes les modifications |
| Cmd+D | Afficher les valeurs existantes de la colonne (autocomplétion) |

### Navigation
| Raccourci | Action |
|-----------|--------|
| Cmd+↑ | Aller à la cellule vide précédente (ou tout en haut) |
| Cmd+↓ | Aller à la cellule vide suivante (ou tout en bas) |
| Ctrl+→ | Page suivante |
| Ctrl+← | Page précédente |
| Ctrl+Début | Première page |
| Ctrl+Fin | Dernière page |

### Recherche et affichage
| Raccourci | Action |
|-----------|--------|
| Cmd+F | Ouvrir la barre de recherche |
| Échap | Effacer la recherche |
| F5 | Actualiser l'affichage |
| F12 | Ouvrir le visualiseur de logs |

---

## 🔧 Dépannage

### Problèmes d'import
- Vérifiez l'encodage du fichier (UTF-8 recommandé)
- Assurez-vous que le fichier CSV a au moins 2 colonnes
- Première ligne = en-têtes (ignorée lors de l'import)

### Performance
- L'application pagine automatiquement les gros datasets
- Utilisez les filtres de colonnes pour affiner l'affichage

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

    def _show_local_guide(self):
        """Afficher un guide d'utilisation local en cas d'erreur"""
        self._safe_show_local_guide()

    def _open_fts5_manager(self):
        """Ouvrir le gestionnaire d'index FTS5"""
        self._safe_open_fts5_manager()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur gestionnaire FTS5")
    def _safe_open_fts5_manager(self):
        """Dialogue de gestion de l'index de recherche FTS5"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressDialog
        from ..core.config import Config

        dialog = QDialog(self)
        dialog.setWindowTitle("🔍 Index de recherche FTS5")
        dialog.setModal(True)
        dialog.resize(480, 280)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        # Titre
        title_label = QLabel("<b>Gestion de l'index de recherche plein texte (FTS5)</b>")
        title_label.setStyleSheet("font-size: 14px; margin-bottom: 4px;")
        layout.addWidget(title_label)

        # Explication
        info_text = (
            "L'index FTS5 accélère drastiquement les recherches en remplaçant les\n"
            "requêtes <code>LIKE '%terme%'</code> (full table scan) par une recherche\n"
            "indexée par trigrammes. Résultat : ~10× plus rapide sur 600k enregistrements.\n\n"
            "<b>⚠️ La construction prend ~2 secondes. L'application reste responsive.</b>"
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Statut de l'index
        def get_status_text():
            try:
                populated = self.db_manager.is_fts5_populated()
                active = Config.USE_FTS5
                if populated:
                    count = self.db_manager.get_fts5_row_count()
                    active_str = "✅ Actif" if active else "⚠️ Construit mais non activé"
                    return f"Statut : {active_str} — {count:,} enregistrements indexés".replace(",", " ")
                else:
                    return "Statut : ❌ Index non construit"
            except Exception as e:
                return f"Statut : Erreur — {e}"

        status_label = QLabel(get_status_text())
        status_label.setStyleSheet("font-weight: bold; padding: 6px; background: #f0f0f0; border-radius: 4px;")
        layout.addWidget(status_label)

        layout.addStretch()

        # Boutons
        buttons_layout = QHBoxLayout()

        rebuild_btn = QPushButton("⚙️ Construire / Reconstruire l'index")
        rebuild_btn.setToolTip("Lance la construction complète de l'index FTS5 (~2 secondes)")

        def do_rebuild():
            rebuild_btn.setEnabled(False)
            rebuild_btn.setText("⏳ Construction en cours…")
            QApplication.processEvents()

            try:
                count = self.db_manager.rebuild_fts5()
                Config.USE_FTS5 = True
                status_label.setText(
                    f"Statut : ✅ Actif — {count:,} enregistrements indexés".replace(",", " ")
                )
                rebuild_btn.setText("✅ Index construit")
                if hasattr(self, 'statusBar'):
                    self.statusBar().showMessage(
                        f"Index FTS5 construit ({count:,} enregistrements) — Recherche accélérée activée".replace(",", " "),
                        6000
                    )
            except Exception as e:
                rebuild_btn.setEnabled(True)
                rebuild_btn.setText("⚙️ Construire / Reconstruire l'index")
                QMessageBox.critical(dialog, "Erreur FTS5", f"Échec de la construction de l'index :\n{e}")

        rebuild_btn.clicked.connect(do_rebuild)
        buttons_layout.addWidget(rebuild_btn)

        buttons_layout.addStretch()

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.accept)
        buttons_layout.addWidget(close_btn)

        layout.addLayout(buttons_layout)

        # Note persistance
        persist_note = QLabel(
            "<i>Note : l'activation est en mémoire pour cette session. "
            "Pour la rendre permanente, définir <code>USE_FTS5 = True</code> dans <code>src/core/config.py</code>.</i>"
        )
        persist_note.setWordWrap(True)
        persist_note.setStyleSheet("color: #666; font-size: 11px; margin-top: 8px;")
        layout.addWidget(persist_note)

        dialog.exec_()

    def _apply_column_visibility(self):
        """Appliquer la visibilité des colonnes au tableau"""
        for col_idx, visible in self.visible_columns.items():
            self.table.setColumnHidden(col_idx, not visible)
            # Masquer aussi les filtres correspondants via TableController
            if hasattr(self, 'table_controller') and hasattr(self.table_controller, 'filter_widgets'):
                if col_idx in self.table_controller.filter_widgets:
                    self.table_controller.filter_widgets[col_idx].setVisible(visible)
    
    def _configure_columns(self):
        """Ouvrir la boîte de dialogue de configuration des colonnes"""
        return self._safe_configure_columns()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur configuration colonnes")
    def _safe_configure_columns(self):
        """Helper sécurisé pour configurer les colonnes"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel

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
    
    def _reset_column_defaults(self, checkboxes):
        """Réinitialiser les colonnes aux valeurs par défaut"""
        for col in Config.COLUMN_CONFIG:
            if not col['mandatory']:
                checkboxes[col['index']].setChecked(col['visible'])
    
    def _apply_column_config(self, checkboxes, dialog):
        """Appliquer la nouvelle configuration des colonnes"""
        return self._safe_apply_column_config(checkboxes, dialog)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur application config colonnes")
    def _safe_apply_column_config(self, checkboxes, dialog):
        """Helper sécurisé pour appliquer la configuration des colonnes"""
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

    # --- Méthodes d'événements ---

    @handle_event_handler_errors(return_value=False, title="Erreur récupération viewport")
    def _safe_get_viewport(self):
        """Récupérer le viewport de la table (version protégée)"""
        viewport = self.table.viewport()
        if viewport is None:
            return None
        return viewport

    def eventFilter(self, source, event):
        """Filtrer les événements pour la gestion du drag handle"""
        # Vérifier si l'objet table existe encore
        if not hasattr(self, 'table') or self.table is None:
            return super().eventFilter(source, event)

        # Vérifier si l'objet viewport existe encore
        viewport = self._safe_get_viewport()
        if viewport is None:
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
                # PHASE 2.2 OPTIMISATION: Utiliser callback pour dialogue non-bloquant
                self.import_manager.import_files(
                    supported_files,
                    show_dialog=True,
                    callback=self._on_import_complete
                )

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
        """Importer un fichier CSV depuis un chemin donné (utilisé pour le glisser/déposer)"""
        # PHASE 3.2: Déléguer au ImportExportService
        if Config.USE_NEW_IMPORT_EXPORT_SERVICE and hasattr(self, 'import_export_service') and self.import_export_service:
            self.import_export_service.import_csv_from_path(file_path)
    
    def _import_pdf_from_path(self, file_paths):
        """Importer un ou plusieurs fichiers PDF depuis des chemins donnés - Phase 2.7"""
        # Déléguer au service FileProcessingService
        return self.file_processing_service.import_pdf_files(file_paths)

    def _get_import_options_pdf(self, suggested_ref_piece=None):
        """Dialogue pour choisir les options d'import PDF"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox
        
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
        # PHASE 3.3: Déléguer au DatabaseOperationsService si activé
        if Config.USE_NEW_DATABASE_OPERATIONS_SERVICE and hasattr(self, 'database_operations_service') and self.database_operations_service:
            # Ne pas passer selected_rows car ce sont des numéros de ligne, pas des IDs d'appareils
            # Le service va récupérer les vrais IDs via _get_selected_device_ids()
            self.database_operations_service.delete_selected_devices()

    def keyPressEvent(self, event):
        """Gestion des raccourcis clavier - avec délégation conditionnelle au service"""
        # PHASE 3.5: Déléguer au KeyboardShortcutService si activé
        if Config.USE_NEW_KEYBOARD_SHORTCUT_SERVICE and self.keyboard_shortcut_service:
            handled = self.keyboard_shortcut_service.handle_key_press_event(event)
            if handled:
                return

        # Fallback pour événements non gérés par le service
        super().keyPressEvent(event)

    def _add_new_row(self):
        """Ajouter une nouvelle ligne"""
        return self._safe_add_new_row()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur ajout nouvelle ligne")
    def _safe_add_new_row(self):
        """Helper sécurisé pour ajouter une nouvelle ligne"""
        # PHASE 3.3: Déléguer au DatabaseOperationsService si activé
        if Config.USE_NEW_DATABASE_OPERATIONS_SERVICE and hasattr(self, 'database_operations_service') and self.database_operations_service:
            device_id = self.database_operations_service.add_new_device()
            if not device_id:
                app_logger.error("Échec de l'ajout de nouvelle ligne")
        else:
            app_logger.warning("DatabaseOperationsService non disponible")

    def _handle_paste(self):
        """Gestion du collage de données depuis le presse-papiers - Version refactorisée Phase 2.5"""
        return self._safe_handle_paste()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur collage données")
    def _safe_handle_paste(self):
        """Helper sécurisé pour gestion du collage"""
        # Vider le cache des décisions de description au début de chaque import
        self._piece_description_decisions.clear()

        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text.strip():
            QMessageBox.information(self, "Collage", "Aucune donnée dans le presse-papiers")
            return

        # Optimisation pour gros volumes - détection limitée sur échantillon
        text_length = len(clipboard_text)
        if text_length > 100000:  # > 100KB de données collées
            app_logger.info(f"🚀 Gros volume de données collées ({text_length} chars), optimisation activée")
            # Détecter sur échantillon pour éviter freeze
            sample_text = clipboard_text[:10000]  # Premier 10KB
            detected_columns = self.paste_processor.detect_columns_count(sample_text)
        else:
            detected_columns = self.paste_processor.detect_columns_count(clipboard_text)

        # Vérifier si on a au moins 1 colonne
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

        # Parser les données avec le nouveau processeur
        rows = self.paste_processor.parse_clipboard_data(clipboard_text)
        if not rows:
            return

        # Préparer les données d'exemple pour l'aperçu
        sample_data = self.paste_processor.prepare_sample_data(rows)

        # Demander les options d'import avec la fenêtre unifiée et aperçu
        import_type, ref_piece, third_column_choice, has_headers, libelle_piece = self._get_import_options_unified(detected_columns, None, "COLLAGE", sample_data)
        if import_type is None:
            return

        # Le collage n'utilise pas import_type mais on récupère les autres paramètres
        category = ""  # Pas de catégorie dans la fenêtre unifiée pour l'instant
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
            QApplication.processEvents()

        # Traitement des données via le processeur spécialisé
        self._safe_process_paste_batch(rows, ref_piece, third_column_choice, libelle_piece, category, total_rows, progress_dialog)

    def _detect_paste_columns(self, clipboard_text: str) -> int:
        """Méthode de compatibilité - délègue au processeur"""
        return self.paste_processor.detect_columns_count(clipboard_text)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur traitement batch collage")
    def _safe_process_paste_batch(self, rows, ref_piece, third_column_choice, libelle_piece, category, total_rows, progress_dialog):
        """Helper sécurisé pour le traitement batch du collage"""
        try:
            result = self.paste_processor.process_rows_batch(
                rows, ref_piece, third_column_choice,
                libelle_piece, category,
                self._piece_description_decisions
            )

            # Recharger les données dans le tableau pour refléter les nouveaux ajouts
            self.table_controller.load_data()

            # Feature Flag: Phase 4 - Sauvegarde événementielle après collage (délégation service)
            if Config.ENABLE_EVENT_DRIVEN_SAVE:
                if hasattr(self, 'event_driven_save_service') and self.event_driven_save_service:
                    self.event_driven_save_service.handle_paste_completed(result)
                else:
                    # Fallback si service pas encore initialisé
                    app_logger.warning("EventDrivenSaveService non disponible, fallback méthode locale")
                    self._trigger_event_driven_save_after_paste(result)

            # Log les résultats dans l'historique et afficher le résumé via le service
            self.paste_results_service.log_paste_results(
                result.inserted_count, result.updated_count, result.ignored_count,
                result.associations_created, result.duplicates_skipped,
                result.manual_completion_count, result.descriptions_updated,
                total_rows, ref_piece
            )

            # Afficher le résumé
            self.paste_results_service.show_paste_summary(
                result.inserted_count, result.updated_count, result.ignored_count,
                result.associations_created, result.duplicates_skipped,
                result.manual_completion_count, result.descriptions_updated,
                total_rows
            )

        finally:
            # Toujours fermer la barre de progression
            if progress_dialog:
                progress_dialog.close()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur copie de données")
    def _safe_copy_selected_data(self, selected):
        """Copier les données sélectionnées vers le presse-papier"""
        clipboard_data = []
        for r in range(selected[0].topRow(), selected[0].bottomRow() + 1):
            row_data = [self._get_cell_text(r, c)
                        for c in range(selected[0].leftColumn(), selected[0].rightColumn() + 1)]
            clipboard_data.append("\t".join(row_data))

        clipboard_string = "\n".join(clipboard_data)
        QApplication.clipboard().setText(clipboard_string)

        self.statusbar.showMessage(
            f"📋 Copié: {len(clipboard_data)} ligne(s)",
            Config.STATUS_MESSAGE_TIMEOUT
        )

    def _handle_copy(self):
        """Gestion de la copie des données sélectionnées"""
        selected = self.table.selectedRanges()
        if not selected:
            QMessageBox.information(self, "Copie", "Aucune cellule sélectionnée")
            return

        self._safe_copy_selected_data(selected)

    def _needs_manual_completion(self, appareil_data: dict) -> bool:
        """Vérifier si un appareil a besoin d'une complétion manuelle (ni type ni fabricant)"""
        type_val = appareil_data.get('type') or ''
        manufacturer_val = appareil_data.get('manufacturer') or ''
        type_empty = not str(type_val).strip()
        manufacturer_empty = not str(manufacturer_val).strip()
        return type_empty and manufacturer_empty

    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur auto-completion")
    def _safe_try_auto_complete(self, appareil_data: dict, original_data: dict):
        """Essayer de compléter automatiquement Type et Fabricant (version protégée)"""
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

    def _try_auto_complete(self, appareil_data: dict):
        """Essayer de compléter automatiquement Type et Fabricant à partir des références

        Returns:
            bool: True si l'auto-complétion a réussi, False sinon
        """
        original_data = appareil_data.copy()
        return self._safe_try_auto_complete(appareil_data, original_data)

    def _refresh_application(self):
        """Rafraîchir l'application - CORRECTION: utiliser la même logique que F5"""
        # Utiliser la même logique que F5 (raccourci clavier) pour cohérence
        if hasattr(self, 'advanced_search_service') and hasattr(self, 'table_controller'):
            search_term = self.advanced_search_service.get_current_search_term_with_fallback(self)
            self.table_controller.load_data(search_term)
        else:
            # Fallback vers ancienne logique si services indisponibles
            search_term = self.pending_search_term if hasattr(self, 'pending_search_term') else None
            self.table_controller.load_data(search_term)
        self.statusbar.showMessage("Application rafraîchie", Config.STATUS_MESSAGE_TIMEOUT)
    
    def _refresh_pieces_count_column(self):
        """Rafraîchir la colonne Nb Pièces pour toutes les lignes visibles"""
        self.table_controller.refresh_pieces_count_column()

    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur nettoyage eventFilter")
    def _safe_remove_event_filter(self) -> bool:
        """Retirer l'eventFilter de manière sécurisée"""
        self.table.viewport().removeEventFilter(self)
        return True

    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur nettoyage table_controller")
    def _safe_cleanup_table_controller(self) -> bool:
        """Nettoyer le table_controller de manière sécurisée"""
        self.table_controller.cleanup()
        return True

    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur nettoyage grouped_history_service")
    def _safe_cleanup_grouped_history(self) -> bool:
        """Nettoyer le grouped_history_service de manière sécurisée"""
        self.grouped_history_service.cleanup()
        return True

    def closeEvent(self, event):
        """Gestion de la fermeture"""
        # Sauvegarder les modifications en attente
        if self.modified_cells:
            reply = self.user_interaction_service.show_save_confirmation(
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
            self._safe_remove_event_filter()

        # Nettoyer le TableController
        if hasattr(self, 'table_controller'):
            self._safe_cleanup_table_controller()

        # Nettoyer le service d'historique groupé
        if hasattr(self, 'grouped_history_service'):
            self._safe_cleanup_grouped_history()

        # Fermer la base de données
        if hasattr(self, 'db_manager'):
            self.db_manager.close()

        event.accept()

    # Méthodes SEO - Phase 2.15: Délégation vers SEOService
    def _generate_meta_title(self):
        """Générer et copier un méta titre SEO optimisé - Phase 2.15: Délégation vers SEOService"""
        self.seo_service.generate_meta_title()
    
    def _generate_meta_description(self):
        """Générer et copier une méta description SEO - Phase 2.15: Délégation vers SEOService"""
        self.seo_service.generate_meta_description()
    
    def _is_piece_reference_search(self) -> bool:
        """Vérifier si la recherche actuelle est une référence de pièce - Support multi-références"""
        return self._safe_is_piece_reference_search()

    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur vérification référence pièce")
    def _safe_is_piece_reference_search(self) -> bool:
        """Helper sécurisé pour vérifier référence pièce"""
        search_term = self.search_input.text().strip()
        if not search_term:
            return False

        # Détecter les recherches multi-références avec || ou &&
        if '||' in search_term or '&&' in search_term:
            return self.advanced_search_service._are_all_terms_piece_references(search_term)

        # Recherche simple - vérifier si c'est une référence de pièce
        return self.advanced_search_service._get_piece_description_from_reference(search_term) is not None

    # --- Méthodes de gestion des dispositifs pour le collage (délégation vers DeviceManager) ---
    
    def _find_existing_device_by_refs(self, ref_modele: str, commercial_ref: str, 
                                    device_type: str = "", manufacturer: str = "") -> Optional[Dict]:
        """Déléguer vers DeviceManager"""
        return self.device_manager.find_existing_device_by_refs(ref_modele, commercial_ref, device_type, manufacturer)
    
    def _try_auto_complete(self, device_data: Dict[str, str]) -> bool:
        """Déléguer vers DeviceManager"""
        return self.device_manager.try_auto_complete(device_data)
    
    def _needs_manual_completion(self, device_data: Dict[str, str]) -> bool:
        """Déléguer vers DeviceManager"""
        return self.device_manager.needs_manual_completion(device_data)
    
    def _create_new_device(self, device_data: Dict[str, str]) -> Optional[int]:
        """Déléguer vers DeviceManager"""
        return self.device_manager.create_new_device(device_data)
    
    def _update_device_info(self, device_id: int, updates: Dict[str, str]) -> bool:
        """Déléguer vers DeviceManager"""
        return self.device_manager.update_device_info(device_id, updates)

    def _trigger_event_driven_save_after_paste(self, result):
        """
        [DEPRECATED - Phase 4 Factorisation] Sauvegarde événementielle après collage

        MIGRATION: Cette méthode a été migrée vers EventDrivenSaveService.save_after_paste()
        UTILISATION: Fallback temporaire uniquement
        TODO: Supprimer après validation complète du service
        """
        return self._safe_trigger_event_driven_save_after_paste(result)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur sauvegarde événementielle")
    def _safe_trigger_event_driven_save_after_paste(self, result):
        """Helper sécurisé pour sauvegarde événementielle"""
        if (hasattr(self, 'database_operations_service') and
            self.database_operations_service and
            Config.USE_NEW_DATABASE_OPERATIONS_SERVICE):

            total_changes = result.inserted_count + result.updated_count
            app_logger.debug(f"Sauvegarde événementielle après collage: {total_changes} modifications")

            # Après un collage, les données sont déjà commitées en base
            # On peut forcer un auto_save pour s'assurer que les transactions en attente sont terminées
            success = self.database_operations_service.auto_save()

            if success:
                app_logger.debug(f"Sauvegarde événementielle réussie après collage")
                # Mettre à jour l'indicateur de sauvegarde
                if hasattr(self, 'save_indicator'):
                    self.save_indicator.setText(Config.get_message('save_success'))
                    self.save_indicator.setStyleSheet("color: green;")
            else:
                app_logger.warning(f"Échec sauvegarde événementielle après collage")

    # Les méthodes _log_paste_results et _show_paste_summary ont été déplacées vers PasteResultsService

    @handle_ui_operation_errors(return_value=None)
    def _safe_disconnect_search_signals(self):
        """Déconnecter les signaux de search_input en toute sécurité"""
        if hasattr(self, 'search_input') and self.search_input:
            self.search_input.textChanged.disconnect()

def main():
    """Point d'entrée de l'application"""
    app = QApplication(sys.argv)

    # Supprimer les warnings macOS inutiles
    app.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    app.setQuitOnLastWindowClosed(True)

    _safe_launch_main_window(app)

@handle_ui_operation_errors(return_value=None, log_prefix="ERREUR CRITIQUE: Démarrage application")
def _safe_launch_main_window(app):
    """Helper sécurisé pour lancement de la fenêtre principale"""
    window = MainWindow()
    # Appliquer les styles CSS globalement pour toutes les fenêtres
    app.setStyleSheet(window._get_modern_style())
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
