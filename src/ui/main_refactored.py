"""
Application de gestion d'appareils - Version refactorisée
Architecture modulaire avec séparation des responsabilités
"""

import sys
from typing import Optional, Dict, Any, List, Tuple

from .qt_imports import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QLabel, QPushButton, QHBoxLayout,
    QMessageBox, QLineEdit,
    QAction, QStatusBar, QSplitter, QTabWidget,
    QListWidgetItem, QFileDialog, QComboBox,
    QCheckBox, QMenu, QDialog, QTextEdit, QTextBrowser,
    QColor,
    Qt, QTimer, QSettings, QEvent, QMimeData, QUrl, QSizePolicy, QFrame, QSize
)

# Imports Python standard consolidés
import os
from pathlib import Path
from datetime import datetime

# Helpers et utilitaires refactorisés
from .message_helper import MessageHelper, CommonMessages, show_success, show_error, ask_confirmation
from .dialog_manager import DialogManager
from ..utils.error_handler import (
    handle_errors, handle_database_errors,
    handle_ui_errors, handle_ui_column_errors,
    handle_database_operation_errors, handle_ui_operation_errors,
    handle_table_operations_errors, handle_navigation_errors,
    handle_export_errors, handle_import_errors,
    handle_log_viewer_errors,
    handle_data_management_errors, handle_drag_operation_errors,
    handle_event_handler_errors, handle_ui_update_errors
)
from ..core.constants import UIConfig, Messages, DatabaseConfig

from ..services import SearchService, ImportService
from ..services.advanced_search_service import AdvancedSearchService
from ..services.event_bus import event_bus
from ..core.constants import ExportFormat
from ..services.navigation_service import NavigationService
from ..services.cell_editing_service import CellEditingService
# PHASE 4 : Remplacement par ExportManagerService unifié
from ..services.export_manager import ExportManagerService, ExportType
from ..services.device_manager import DeviceManager
from ..services.paste_results_service import PasteResultsService

# Imports des modules refactorisés
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config, pluralize
from src.core.logger import app_logger
from src.core.import_manager import ImportManager
from src.data.database_manager import DatabaseManager, DatabaseError
from src.data.data_validator import DataValidator, ValidationResult
from .style_manager import StyleManager
from .table_controller import TableController
from .paste_data_processor import PasteDataProcessor
from .data_management_service import DataManagementService, FieldCompletionResult
from .user_interaction_service import UserInteractionService
from .log_viewer import LogViewer
from .piece_management_service import PieceManagementService
from .seo_service import SEOService
from .pieces_list_service import PiecesListService
from ..services.grouped_history_service import GroupedHistoryService
from ..services.history_service import HistoryService
from ..services.drag_handle_service import DragHandle, DragHandleService
from ..services.undo_manager import UndoRedoManager
from ..services.app_export_service import AppExportService
# Supprimé: remplacé par DialogManager dans les imports centralisés
from ..services.event_handlers_service import EventHandlersService
from ..services.table_fill_service import TableFillService

import qtawesome as qta


class StatusLabel(QWidget):
    """
    Widget drop-in remplaçant QLabel dans la statusbar.
    Expose setText/setStyleSheet identiques à QLabel pour compatibilité totale.
    Affiche une icône qtawesome colorée à gauche du texte.
    """

    def __init__(self, icon_name: str, text: str, color: str = 'green', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        self._icon_name = icon_name
        self._icon_label = QLabel()
        self._text_label = QLabel(text)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label)
        self._update_icon(color)

    def setText(self, text: str) -> None:
        self._text_label.setText(text)

    def setStyleSheet(self, style: str) -> None:
        self._text_label.setStyleSheet(style)
        if 'orange' in style:
            self._update_icon('orange')
        else:
            self._update_icon('green')

    def _update_icon(self, color: str) -> None:
        icon = qta.icon(self._icon_name, color=color)
        self._icon_label.setPixmap(icon.pixmap(12, 12))


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

        # Service de config des exports (doit être créé avant HtmlExportService)
        from ..services.export_config_service import ExportConfigService
        from ..services.html_export_service import HtmlExportService as _HtmlExportService
        self.export_config_service = ExportConfigService(self)
        _HtmlExportService.set_config_service(self.export_config_service)

        self.device_manager = DeviceManager(self.db_manager)

        # Sauvegarde automatique avant opérations destructives (nettoyage, import)
        from ..services.backup_service import BackupService
        self.backup_service = BackupService(self)

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

        # import_manager et file_processing_service créés en premier
        # car les initialize_services() suivants en ont besoin via parent_window
        self.import_manager = ImportManager(self.db_manager, parent_widget=self)

        from .file_processing_service import FileProcessingService
        self.file_processing_service = FileProcessingService(self)

        # PHASE 3.2 : Service unifié d'import/export
        from ..services.import_export_service import ImportExportService
        self.import_export_service = ImportExportService(self)
        self.import_export_service.initialize_services()
        app_logger.debug("ImportExportService initialisé")

        # PHASE 3.3 : Service unifié des opérations de base de données
        from ..services.database_operations_service import DatabaseOperationsService
        self.database_operations_service = DatabaseOperationsService(self)
        self.database_operations_service.initialize_services()

        # PHASE 3.4 : Service unifié de gestion de l'état UI
        from ..services.ui_state_management_service import UIStateManagementService
        self.ui_state_management_service = UIStateManagementService(self)
        self.ui_state_management_service.initialize_services()

        # PHASE 3.5 : Service unifié des raccourcis clavier
        from ..services.keyboard_shortcut_service import KeyboardShortcutService
        self.keyboard_shortcut_service = KeyboardShortcutService(self)
        self.keyboard_shortcut_service.initialize_services()
    
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
        self.history_service = HistoryService(self)
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
        self.app_export_service = AppExportService(self)

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

        # PHASE 3.1: Service de tri et filtrage
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
        self.setWindowTitle(Config.WINDOW_TITLE)
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
        # self.incomplete_filter_btn est défini dans _setup_statusbar (groupe sous le tableau)

        # PHASE 5: Configuration des services centralisés
        self.cell_editing_service.table = self.table

        # PHASE 3.1: Initialiser le service de tri et filtrage
        if hasattr(self, 'sorting_filtering_service'):
            from ..services.sorting_filtering_service import SortingFilteringService
            self.sorting_filtering_service = SortingFilteringService(
                table_widget=self.table,
                table_controller=self.table_controller,
                parent=self
            )
        
        # Configurer le service de navigation avec les widgets de pagination
        if hasattr(self.table_controller, 'page_input'):
            self.navigation_service.set_pagination_widgets(
                self.table_controller.page_label,
                self.table_controller.prev_button,
                self.table_controller.next_button,
                self.table_controller.page_size_combo,
                first_button=getattr(self.table_controller, 'first_button', None),
                last_button=getattr(self.table_controller, 'last_button', None),
                page_input=self.table_controller.page_input,
                page_total_label=getattr(self.table_controller, 'page_total_label', None)
            )
            # Établir la liaison bidirectionnelle
            self.table_controller.set_navigation_service(self.navigation_service)

        # Appliquer la position de recherche mémorisée (défaut : sous le tableau)
        if hasattr(self, 'settings') and hasattr(self.table_controller, 'set_search_position'):
            if self.settings.value("ui/search_position", "bottom") == "top":
                self.table_controller.set_search_position("top")
        
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
        m = layout.contentsMargins()
        layout.setContentsMargins(m.left(), 0, m.right(), 0)

        # Splitter vertical pour diviser en deux parties
        pieces_splitter = QSplitter(Qt.Vertical)

        # Partie haute - Onglets pour les pièces
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)  # retire le double niveau de marges internes
        top_layout.setSpacing(2)
        
        # ── En-tête : nom appareil + bouton rafraîchir ──────────────────────
        header_widget = QWidget()
        header_widget.setFixedHeight(30)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(4)

        self.pieces_header_label = QLabel("")
        self.pieces_header_label.setStyleSheet(
            "color: #343a40; font-size: 11px;"
        )
        self.pieces_header_label.setWordWrap(False)
        self.pieces_header_label.setMinimumWidth(0)
        self.pieces_header_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        header_layout.addWidget(self.pieces_header_label, 1)

        self.pieces_count_label = QLabel("")
        self.pieces_count_label.setStyleSheet(
            "color: #6c757d; font-size: 10px;"
        )
        header_layout.addWidget(self.pieces_count_label)

        _btn_style = """
            QPushButton {
                background-color: transparent;
                color: #6c757d;
                border: 1px solid #ced4da;
                border-radius: 3px;
                font-size: 13px;
                font-weight: bold;
                min-width: 22px;
                max-width: 22px;
                min-height: 20px;
                max-height: 20px;
                padding: 0px;
            }
            QPushButton:hover { background-color: #e9ecef; color: #343a40; }
        """

        refresh_btn = QPushButton("↺")
        refresh_btn.setToolTip("Rafraîchir la liste des pièces")
        refresh_btn.setStyleSheet(_btn_style)
        refresh_btn.clicked.connect(lambda: self.pieces_panel_service.update_pieces_panel())
        header_layout.addWidget(refresh_btn)

        add_toggle_btn = QPushButton("＋")
        add_toggle_btn.setToolTip("Ajouter une pièce")
        add_toggle_btn.setStyleSheet(_btn_style)
        header_layout.addWidget(add_toggle_btn)

        top_layout.addWidget(header_widget)

        # Liste des pièces directement (plus de QTabWidget)
        self.pieces_list = self.pieces_list_service.create_pieces_list_widget()
        top_layout.addWidget(self.pieces_list, 1)

        # Formulaire d'ajout de pièce (masqué par défaut, toggle via ＋)
        pieces_add_widget = QWidget()
        pieces_add_widget.setVisible(False)
        pieces_add_layout = QVBoxLayout(pieces_add_widget)
        pieces_add_layout.setContentsMargins(4, 4, 4, 4)
        pieces_add_layout.setSpacing(4)

        self.piece_input = QLineEdit()
        self.piece_input.setPlaceholderText("Référence de la pièce...")
        pieces_add_layout.addWidget(self.piece_input)

        self.piece_libelle_input = QLineEdit()
        self.piece_libelle_input.setPlaceholderText("Libellé de la pièce (optionnel)...")
        pieces_add_layout.addWidget(self.piece_libelle_input)

        add_piece_btn = QPushButton("Ajouter")
        add_piece_btn.clicked.connect(self._add_piece)
        pieces_add_layout.addWidget(add_piece_btn)

        add_toggle_btn.clicked.connect(
            lambda: pieces_add_widget.setVisible(not pieces_add_widget.isVisible())
        )
        top_layout.addWidget(pieces_add_widget)
        pieces_splitter.addWidget(top_widget)

        # Partie basse - Historique des modifications
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        
        # Titre avec séparateurs latéraux : ───── Historique des opérations ─────
        history_header_layout = QHBoxLayout()
        history_header_layout.setContentsMargins(0, 4, 0, 4)
        history_header_layout.setSpacing(6)

        def _make_separator():
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Plain)
            line.setStyleSheet("color: #ced4da;")
            return line

        history_header_layout.addWidget(_make_separator(), 1)

        history_label = QLabel("Historique des opérations")
        history_label.setObjectName("historyTitle")
        history_label.setAlignment(Qt.AlignCenter)
        history_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        history_header_layout.addWidget(history_label)

        history_open_btn = QPushButton()
        history_open_btn.setIcon(qta.icon('fa5s.external-link-alt', color='#999'))
        history_open_btn.setIconSize(QSize(10, 10))
        history_open_btn.setFixedSize(18, 18)
        history_open_btn.setToolTip("Ouvrir l'historique persistant")
        history_open_btn.setFlat(True)
        history_open_btn.setStyleSheet(StyleManager.FLAT_TRANSPARENT_BUTTON)
        history_open_btn.clicked.connect(self._open_history_view)
        history_header_layout.addWidget(history_open_btn, 0, Qt.AlignVCenter)

        history_header_layout.addWidget(_make_separator(), 1)

        history_layout.addLayout(history_header_layout)
        history_layout.setContentsMargins(8, 12, 8, 0)  # Padding moderne, sans marge basse
        
        self.history_list = QTextBrowser()
        self.history_list.setOpenExternalLinks(False)  # Gérer les liens nous-mêmes
        # Sans ceci, QTextBrowser tente aussi d'OUVRIR le lien cliqué comme une page
        # (setSource) : un lien d'action « libelle:… » viderait l'historique affiché.
        self.history_list.setOpenLinks(False)
        
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

        # Menu contextuel étendu : rechercher le texte sélectionné (ou le mot sous le
        # curseur à défaut) directement dans le champ Recherche par pièce.
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(
            self._show_history_context_menu
        )

        history_layout.addWidget(self.history_list)
        
        pieces_splitter.addWidget(history_widget)
        
        # Configuration du splitter (50% haut, 50% bas pour plus d'espace à l'historique)
        pieces_splitter.setSizes([200, 200])
        
        # Permettre au widget historique de grandir plus facilement
        pieces_splitter.setStretchFactor(1, 1)  # Historique peut grandir
        
        layout.addWidget(pieces_splitter)

        # Boutons d'export en bas de la colonne de droite (sous l'historique).
        # Disposition inchangée (CSV/HTML Marques/HTML Détails, puis Méta Title/Desc) ;
        # seul l'emplacement change, pour dégager totalement le bas du tableau.
        if hasattr(self, 'ui_component_service') and self.ui_component_service:
            self.ui_component_service.add_export_buttons(layout)

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

        # Connecter le service d'indication des doublons au bouton dédié
        # "Nettoyer les doublons" (devient rouge quand des doublons sont en attente)
        if hasattr(self, 'duplicate_indicator_service') and hasattr(self.toolbar_service, 'clean_duplicates_btn'):
            self.duplicate_indicator_service.set_buttons(
                self.toolbar_service.clean_duplicates_btn,
                self.toolbar_service.clean_duplicates_action
            )
            from ..core.logger import app_logger
            app_logger.info("✅ Service d'indication des doublons connecté aux boutons")

        self._update_toolbar_states()

    def _setup_statusbar(self):
        """Configurer la barre de statut"""
        from .message_status_bar import MessageStatusBar
        from .incomplete_nav_widget import IncompleteNavWidget
        self.statusbar = MessageStatusBar()
        self.setStatusBar(self.statusbar)

        # « ▲ Lignes à traiter ▼ » en tête de barre, sous le tableau. Hauteur de
        # barre figée sur celle des boutons : elle ne change pas quand le groupe
        # se masque (aucune ligne incomplète) → le contenu de la fenêtre ne bouge pas.
        self.incomplete_nav_widget = IncompleteNavWidget(self)
        self.statusbar.add_leading_widget(self.incomplete_nav_widget)
        self.statusbar.setFixedHeight(self.incomplete_nav_widget.content_height() + 6)
        self._wire_incomplete_nav()
        
        self.save_indicator = StatusLabel('fa5s.save', Config.get_message('save_success'), color='green')
        self.statusbar.addPermanentWidget(self.save_indicator)

        # Connecter l'indicateur au service de sauvegarde événementielle (créé avant la statusbar)
        if hasattr(self, 'event_driven_save_service') and self.event_driven_save_service:
            self.event_driven_save_service.save_indicator = self.save_indicator

        # Feature Flag: AutoSaveManager - Initialisation retardée + Configuration indicateur UI
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            from ..services.auto_save_manager import AutoSaveManager
            self.auto_save_manager = AutoSaveManager(
                self.db_manager,
                self.user_interaction_service,
                self.statusbar
            )
            self.auto_save_manager.setup_ui_indicator(self.save_indicator)

        self.connection_indicator = StatusLabel('fa5s.circle', Config.get_message('connected'), color='green')
        self.statusbar.addPermanentWidget(self.connection_indicator)

    def _wire_incomplete_nav(self):
        """Exposer « Lignes à traiter » et le câbler au service de visibilité/
        compteur et aux flèches du TableController (barre d'état créée après
        la toolbar et le tableau : tous les services sont prêts ici)."""
        nav = self.incomplete_nav_widget
        self.incomplete_filter_btn = nav.filter_btn
        nav_buttons = (nav.prev_btn, nav.next_btn)
        if hasattr(self, 'table_controller'):
            self.table_controller.incomplete_filter_btn = self.incomplete_filter_btn
            # Flèches ▲/▼ « ligne incomplète » autour du bouton
            self.table_controller.set_incomplete_nav_buttons(*nav_buttons)
        if hasattr(self, 'incomplete_button_service'):
            self.incomplete_button_service.set_button(self.incomplete_filter_btn)
            self.incomplete_button_service.set_companions(nav_buttons)
            if hasattr(self, 'table_controller'):
                # Flèches réévaluées à chaque changement du compteur (elles
                # apparaissent actives, pas seulement au chargement suivant)
                self.incomplete_button_service.count_changed.connect(
                    self.table_controller.on_incomplete_count_changed)
            self.incomplete_button_service.set_filter_active(self.show_incomplete_only)
        self._update_incomplete_button_visibility()

    def _init_connections(self):
        """Initialiser les connexions de signaux"""
        pass  # Les connexions sont déjà configurées dans les méthodes de création
    
    def _setup_paste_cleanup_for_search_input(self):
        """Configure l'interception du collage pour le champ de recherche"""
        from .qt_imports import QLineEdit
        from .qt_imports import QEvent

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
            new_input.setClearButtonEnabled(True)  # Bouton × natif intégré au champ
            
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


    def _get_modern_style(self) -> str:
        """Retourne le CSS moderne de l'application via StyleManager"""
        return StyleManager.get_modern_style()
    
    @handle_ui_errors(log_prefix="Erreur mise à jour pagination", show_message=False)
    def _update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination - PHASE 5: Délégation vers NavigationService"""
        if hasattr(self, 'navigation_service'):
            # Mettre à jour le total des lignes dans le service
            self.navigation_service.update_total_rows(getattr(self, 'total_rows', 0))
            # Le service gère automatiquement la mise à jour des contrôles
        else:
            app_logger.warning("NavigationService non disponible, pagination manuelle non implémentée")
    
    
    def _next_page(self):
        """Aller à la page suivante - PHASE 5: Délégation vers NavigationService"""
        self.navigation_service.next_page()
    
    
    
    
    
    
    def _navigate_to_empty_cell(self, direction='down'):
        """Navigation intelligente - PHASE 5: Délégation vers CellEditingService"""
        return self.cell_editing_service.navigate_to_empty_cell(direction)

    @handle_ui_errors(log_prefix="Erreur affichage valeurs colonne", show_message=True)
    def _show_column_values_list(self, prefill: str = ""):
        """Afficher la fenêtre d'auto-complétion selon la colonne (Cmd+D) - Délégation au service"""
        current_item = self.table.currentItem()
        current_col = self.table.currentColumn()

        selected_value = self.autocompletion_service.show_column_values_dialog(
            self.table, current_item, current_col, prefill=prefill
        )

        if selected_value is not None:
            # Écrire dans le modèle → cell_edited → pipeline complet (save, undo, etc.)
            row = self.table.currentRow()
            model = self.table_controller.model
            if model:
                model.setData(model.index(row, current_col), selected_value, Qt.EditRole)

    def _apply_suggestion_decisions(self, decisions):
        """Cœur batché partagé : applique une liste de décisions [(db_id, candidat)]
        en UNE seule transaction (collecteur `_bulk_edit_collector` →
        `save_cells_batch_immediate`), dissipe les indicateurs appliqués et rafraîchit
        la bannière. Utilisé par le bouton « sans concurrence » ET par la fenêtre de
        validation (un seul chemin d'écriture = pas de divergence).

        `candidat` porte au minimum 'type'/'manufacturer' (valeurs retenues, possiblement
        éditées) et idéalement 'ref'/'score' pour la provenance dans l'historique groupé.
        Retourne le nombre d'appareils effectivement traités.
        """
        model = self.table_controller.model
        if not model or not decisions:
            return 0

        # Au-delà de ce seuil, l'application (setData ×2 + undo + historique par
        # appareil, sur le thread UI) prend assez de temps pour donner l'impression
        # d'un gel : on affiche alors une ProgressDialog rafraîchie via processEvents.
        BULK_PROGRESS_THRESHOLD = 50
        total = len(decisions)
        progress = None
        if total > BULK_PROGRESS_THRESHOLD:
            from .progress_dialog import ProgressDialog
            # Pas de bouton Annuler : une application partielle serait incohérente.
            progress = ProgressDialog("Application des suggestions", None, 0, total, self)
            progress.show()
            QApplication.processEvents()
        # Throttle du rafraîchissement (~1 % ou tous les 50 items, au moins 1).
        step = max(1, total // 100, 50)

        # Application en mémoire (UI + undo + historique + provenance) via setData →
        # cell_edited → _apply_cell_edit_logic. Le collecteur est armé pour que ce
        # tronc commun n'enclenche PAS une sauvegarde par cellule (chemin (row,col)
        # fragile au virtual scroll) ; la persistance réelle se fait ensuite par db_id.
        self._bulk_edit_collector = set()
        updates_by_db_id = {}
        try:
            for idx, (db_id, cand) in enumerate(decisions):
                self._apply_suggestion_with_provenance(cand, model, db_id)
                fields = {}
                if (cand.get('type') or '').strip():
                    fields['type'] = cand['type']
                if (cand.get('manufacturer') or '').strip():
                    fields['manufacturer'] = cand['manufacturer']
                if fields:
                    updates_by_db_id[db_id] = fields
                if progress is not None and (idx % step == 0 or idx == total - 1):
                    done = idx + 1
                    progress.setValue(done)
                    progress.setLabelText(f"Application des suggestions… ({done}/{total})")
                    QApplication.processEvents()
        finally:
            self._bulk_edit_collector = None

        # Persistance directe par db_id en UNE transaction : indépendante de la
        # pagination (une ligne hors page virtuelle est sauvegardée correctement,
        # là où la conversion (row,col)→item() la perdait silencieusement).
        if progress is not None:
            progress.setLabelText("Enregistrement…")
            QApplication.processEvents()
        db_ops = getattr(self, 'database_operations_service', None)
        if db_ops is not None and updates_by_db_id:
            db_ops.save_cells_batch(updates_by_db_id)

        # Dissiper les indicateurs appliqués + rafraîchir la bannière.
        for db_id, _ in decisions:
            model.clear_suggestion(db_id)
        self.table_controller._update_similarity_banner()
        if progress is not None:
            progress.close()
        return len(decisions)

    def _open_suggestion_validation_dialog(self):
        """Ouvre la fenêtre de validation polyvalente des suggestions Type/Marque.

        Tableau de synthèse de TOUTES les suggestions (y compris à plusieurs candidats
        concurrents) : cases à cocher, choix du candidat, édition à la volée, scores.
        Validation = applique les seules lignes cochées via `_apply_suggestion_decisions`
        (batché, historisé). Non bloquant (show() + callback).
        """
        model = self.table_controller.model
        if not model or not hasattr(model, 'suggestions_snapshot'):
            return
        snapshot = model.suggestions_snapshot()
        if not snapshot:
            self.user_interaction_service.add_to_history(
                "Validation des suggestions : aucune suggestion en attente.")
            return
        from .suggestion_validation_dialog import SuggestionValidationDialog

        def _on_validate(decisions):
            applied = self._apply_suggestion_decisions(decisions)
            if applied:
                self.user_interaction_service.add_to_history(
                    f"Suggestions validées via la fenêtre : "
                    f"{pluralize(applied, 'appareil')} complété{'s' if applied > 1 else ''}.")

        def _pick_value(db_field, current_value, candidates):
            # Réutilise la fenêtre Cmd+D (valeurs existantes + suggestions) du tableau.
            return self.autocompletion_service.show_field_values_dialog(
                db_field, current_value, suggestions=candidates
            )

        self._suggestion_validation_dialog = SuggestionValidationDialog(
            self, snapshot, on_validate=_on_validate, value_picker=_pick_value
        )
        self._suggestion_validation_dialog.show()

    def _apply_suggestion_with_provenance(self, candidate, model, db_id):
        """Applique un candidat en marquant la provenance pour l'historique groupé
        (visible dans l'entrée comme « source : suggestion réf. X (score Y) »)."""
        self._suggestion_provenance = (
            f"suggestion réf. {candidate.get('ref', '')} (score {candidate.get('score', 0):.0%})"
        )
        try:
            return self.autocompletion_service.apply_suggestion_pair(candidate, model, db_id)
        finally:
            self._suggestion_provenance = None

    def _resolve_suggestion_inline(self, index, suggestions):
        """Clic sur l'icône de suggestion (delegate) : application rapide.

        - 1 seul candidat → appliquer directement Type+Marque (pas de dialogue).
        - Plusieurs candidats en concurrence → ouvrir le chooser pour décider.
        """
        if not suggestions:
            return
        model = self.table_controller.model
        if not model:
            return
        db_id = model.get_db_id(index.row())
        if db_id is None:
            return
        if len(suggestions) == 1:
            self._apply_suggestion_with_provenance(suggestions[0], model, db_id)
            self.table_controller.clear_similarity_suggestion(db_id)
        else:
            self._show_suggestion_dialog(index, suggestions, db_id)

    def _show_suggestion_dialog(self, index, suggestions, db_id):
        """Ouvre le dialogue d'autocomplétion enrichi des suggestions, au clic sur une
        cellule Type/Marque ayant une suggestion par similarité en attente.

        Le dialogue renvoie soit un dict (candidat choisi → application en paire),
        soit un str (valeur libre saisie → écriture de la seule colonne cliquée).
        """
        col = index.column()
        current_item = self.table.currentItem() if hasattr(self.table, 'currentItem') else None
        result = self.autocompletion_service.show_column_values_dialog(
            self.table, current_item, col, suggestions=suggestions
        )
        if result is None:
            return
        model = self.table_controller.model
        if not model:
            return
        if isinstance(result, dict):
            # Candidat choisi : appliquer Type + Marque, puis dissiper l'indicateur.
            self._apply_suggestion_with_provenance(result, model, db_id)
            self.table_controller.clear_similarity_suggestion(db_id)
        else:
            # Valeur libre : écrire uniquement la colonne cliquée (pipeline complet).
            model.setData(model.index(index.row(), col), result, Qt.EditRole)

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

    
    
    def _init_previous_values(self):
        """Initialiser les valeurs précédentes pour toutes les cellules après le chargement"""
        return self._safe_init_previous_values()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur initialisation valeurs précédentes")
    def _safe_init_previous_values(self):
        """Helper sécurisé pour initialiser les valeurs précédentes"""
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self.previous_values[(row, col)] = self._get_cell_text(row, col)
    

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

        # Dissiper l'indicateur de suggestion dès que l'utilisateur renseigne Type/Marque
        # (manuellement ou via une suggestion appliquée) — la ligne n'est plus « à compléter ».
        if col in (0, 1) and new_value.strip() and db_id is not None:
            if hasattr(self.table_controller, 'clear_similarity_suggestion'):
                self.table_controller.clear_similarity_suggestion(db_id)

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
            bulk_collector = getattr(self, '_bulk_edit_collector', None)
            if bulk_collector is not None:
                # Effacement multi-cellules (Suppr) : la sauvegarde est différée et
                # regroupée en une seule transaction par l'appelant (cf. CustomTableView)
                bulk_collector.add((row, col))
            elif hasattr(self, 'event_driven_save_service') and self.event_driven_save_service:
                self.event_driven_save_service.handle_cell_changed(row, col, new_value, self.table)

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

    def _export_data(self, export_format: ExportFormat, profile_name: str = None):
        """Export avec sélection de référence - PHASE 4 : Service unifié"""
        # Pour les exports HTML, utiliser l'export rapide sans dialogue de référence
        if export_format in [ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS]:
            return self.export_manager.export_data(export_format, ExportType.QUICK,
                                                   profile_name=profile_name)
        else:
            return self.export_manager.export_data(export_format, ExportType.MAIN)


    # --- Méthodes utilitaires ---

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur ajout historique groupé")
    def _safe_add_to_grouped_history(self, row: int, col: int, old_value: str, new_value: str):
        """Helper sécurisé pour ajouter à l'historique groupé avec fallback"""
        # Obtenir le nom de la colonne
        column_name = self._get_column_display_name(col)

        # Provenance transitoire (ex: application d'une suggestion par similarité).
        source = getattr(self, '_suggestion_provenance', None)

        # Utiliser le service de groupement d'historique
        if getattr(self, 'auto_save_enabled', True):
            try:
                db_id = self.table_fill_service.get_db_id_from_row(self.table, row)
                self.grouped_history_service.add_modification(db_id, column_name, old_value, new_value, source=source)
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
        # Filtrer les colonnes masquées pour éviter que visualRect() retourne un rect invalide
        visible_indexes = [idx for idx in selected if not self.table.isColumnHidden(idx.column())]
        if not visible_indexes:
            self.drag_handle.hide()
            return
        bottom_row = max(idx.row() for idx in visible_indexes)
        right_col = max(idx.column() for idx in visible_indexes)
        # Masquer la poignée sur les colonnes où le drag est interdit
        if right_col in {2, 3, 4}:
            self.drag_handle.hide()
            return
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


    def _auto_save(self):
        """Sauvegarde automatique optimisée par lots"""
        # PHASE 3.3: Déléguer au DatabaseOperationsService
        if hasattr(self, 'database_operations_service') and self.database_operations_service:
            self.database_operations_service.auto_save()
            return

        # Feature Flag: AutoSaveManager fallback
        if Config.USE_NEW_AUTO_SAVE_MANAGER:
            self.auto_save_manager.perform_auto_save(self.table)

    def _manual_save(self):
        """Sauvegarde manuelle"""
        # PHASE 3.3: Déléguer au DatabaseOperationsService
        if hasattr(self, 'database_operations_service') and self.database_operations_service:
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
            cells_to_clean = [
                (row, col)
                for row in modified_rows
                for col in range(start_col, end_col + 1)
            ]

            if cells_to_clean and hasattr(self, 'database_operations_service') and self.database_operations_service:
                self.event_driven_save_service._update_save_indicator_pending()

                updates_by_db_id = self.database_operations_service._convert_modified_cells_to_updates(cells_to_clean)
                success = self.database_operations_service.save_cells_batch(updates_by_db_id)

                if success:
                    self.event_driven_save_service._update_save_indicator_success()
                    # Nettoyer les cellules de modified_cells pour éviter les sauvegardes répétées
                    if hasattr(self, 'modified_cells'):
                        for cell_coords in cells_to_clean:
                            self.modified_cells.discard(cell_coords)

        finally:
            # Reprendre les invalidations avec une invalidation globale
            if hasattr(self, 'db_manager'):
                cache_service = getattr(self.db_manager, 'cache_invalidation', None)
                if cache_service:
                    cache_service.resume_invalidation(force_invalidate=True)

    

    @handle_navigation_errors(return_value=None, title="Erreur traitement lien historique")
    def _safe_handle_history_link(self, url_str: str):
        """Gérer les clics sur les liens dans l'historique - Version sécurisée"""
        from src.core.constants import UIConfig
        if url_str.startswith(UIConfig.LIEN_HISTORIQUE_LIBELLE):
            from urllib.parse import unquote
            ref = unquote(url_str[len(UIConfig.LIEN_HISTORIQUE_LIBELLE):])
            self.piece_management_service.completer_libelle(ref)
            return
        self.user_interaction_service.show_error(f"Lien non reconnu: {url_str}")

    def _handle_history_link(self, url):
        """Gérer les clics sur les liens dans l'historique"""
        from .qt_imports import QUrl
        # FullyEncoded : la référence reste encodée telle qu'écrite dans le lien
        # (« / », « # », espaces…) et n'est décodée qu'une fois, par le gestionnaire.
        url_str = url.toString(QUrl.FullyEncoded) if isinstance(url, QUrl) else str(url)
        self._safe_handle_history_link(url_str)

    def _show_history_context_menu(self, pos):
        """Menu contextuel du panneau Historique : ajoute une entrée pour rechercher
        le texte sélectionné (ou, à défaut, le mot sous le curseur) dans le champ
        Recherche par pièce — sans dupliquer le menu standard (copier, tout
        sélectionner...) fourni nativement par QTextBrowser."""
        from .qt_imports import QTextCursor

        cursor = self.history_list.textCursor()
        term = cursor.selectedText().strip()
        if not term:
            cursor = self.history_list.cursorForPosition(pos)
            cursor.select(QTextCursor.WordUnderCursor)
            term = cursor.selectedText().strip()

        menu = self.history_list.createStandardContextMenu(pos)
        if term:
            menu.addSeparator()
            search_action = menu.addAction(f"Rechercher « {term} » dans le champ pièce")
            search_action.triggered.connect(
                lambda checked=False, t=term: self._search_piece_from_history(t)
            )
        menu.exec_(self.history_list.viewport().mapToGlobal(pos))

    def _search_piece_from_history(self, term: str):
        """Reporter un terme de l'historique dans le champ Recherche par pièce et
        déclencher la recherche — chemin normal (textChanged → search_with_debounce),
        pas de blockSignals : le comportement (croix native, boutons liés) reste
        identique à une saisie manuelle."""
        if not hasattr(self, 'search_input') or not self.search_input:
            return
        self.search_input.setText(term)
        self.search_input.setFocus()

    def _add_piece(self):
        """Ajouter une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.add_piece()

    def _edit_piece(self, item: QListWidgetItem):
        """Éditer une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.edit_piece(item)

    def _delete_piece(self, item: QListWidgetItem):
        """Supprimer une pièce - Phase 2.14: Délégation vers PieceManagementService"""
        self.piece_management_service.delete_piece(item)
    
    
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

        # Rafraîchir le compteur de lignes incomplètes : la complétion a écrit
        # Type/Marque directement en base (update_device_info), donc le décompte
        # « X incomplète(s) » doit être recalculé, sinon il reste figé sur l'ancienne
        # valeur et donne l'impression que rien ne s'est passé.
        self._update_incomplete_button_visibility()

        # Afficher le résultat
        if result.errors:
            error_msg = f"Erreurs lors de l'auto-complétion:\n" + "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                error_msg += f"\n... et {len(result.errors) - 5} autres erreurs"
            self.user_interaction_service.show_error(error_msg)

        if result.completed_count > 0:
            self.user_interaction_service.show_info(
                f"Auto-complétion réussie !\n\n"
                f"{pluralize(result.completed_count, 'ligne complétée', 'lignes complétées')}\n"
                f"{pluralize(result.total_rows_processed, 'ligne traitée', 'lignes traitées')}")
            self.user_interaction_service.add_to_history(
                f"Autocomplétion: "
                f"{pluralize(result.completed_count, 'appareil complété', 'appareils complétés')} "
                f"sur {result.total_rows_processed} traité{'s' if result.total_rows_processed > 1 else ''}"
            )
            self._auto_save()
        else:
            self.user_interaction_service.show_info("Aucun champ à compléter automatiquement.\n\n"
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
    
    def _on_search_position_toggled(self, checked: bool):
        """Basculer la position de la barre de recherche pièce (haut/bas) et mémoriser."""
        position = "top" if checked else "bottom"
        if hasattr(self, 'settings'):
            self.settings.setValue("ui/search_position", position)
        if hasattr(self, 'table_controller') and hasattr(self.table_controller, 'set_search_position'):
            self.table_controller.set_search_position(position)

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
        # PHASE 3.2: Déléguer au ImportExportService
        if hasattr(self, 'import_export_service') and self.import_export_service:
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
        summary = f"Import {method} — résumé :\n"
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
        summary = f"Import {source}"
        if ref_piece:
            summary += f" (pièce: {ref_piece})"
        summary += ":\n"
        
        # Si c'est un import PDF et qu'on a des informations sur les fichiers, les ajouter
        if pdf_files_info:
            for file_info in pdf_files_info:
                summary += f"Fichier PDF {file_info['filename']} : {file_info['lines_extracted']} lignes extraites\n"
        
        # Ligne principale - total des lignes du fichier original
        # Le vrai total = lignes traitées + doublons ignorés dans le fichier
        total_processed = results.get('total_imported', 0)
        duplicates_ignored = results.get('duplicates_in_file', 0)
        # Utiliser le nombre de lignes originales si disponible, sinon calculer
        original_line_count = results.get('original_line_count', total_processed + duplicates_ignored)
        summary += f"Lignes traitées : {original_line_count}\n"

        alerte = results.get('alerte_mapping')
        if alerte:
            summary += f"[!] {alerte}\n"

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
            # Recherche exacte par défaut (pas de résultats parasites par ref contenant
            # le terme) : la case reste réinitialisée après import, mais l'affichage
            # post-import n'est plus une recherche automatique (cf. ci-dessous).
            if hasattr(self.table_controller, 'extend_search_btn'):
                self.table_controller.extend_search_btn.blockSignals(True)
                self.table_controller.extend_search_btn.setChecked(False)
                self.table_controller.extend_search_btn.blockSignals(False)
                self.table_controller._extend_search_active = False

            self.table_controller.load_data()  # Rafraîchir l'affichage sans filtres

            # Installer les suggestions Type/Marque par similarité calculées pendant
            # l'import (indicateur + bannière conditionnelle). Stockées par db_id :
            # s'affichent dès que les lignes concernées deviennent visibles.
            if hasattr(self.table_controller, 'set_similarity_suggestions'):
                self.table_controller.set_similarity_suggestions(results.get('similarity_suggestions'))

    def _show_import_results_new(self, results):
        """Traiter les résultats d'import du nouveau système ImportManager - SEULEMENT dans l'historique"""
        return self._safe_show_import_results_new(results)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur affichage résultats import")
    def _safe_show_import_results_new(self, results):
        """Helper sécurisé pour afficher les résultats d'import"""
        # Vérifier les erreurs - les afficher si critique
        # Liste bornée : sur un lot de plusieurs centaines de fichiers, tout afficher
        # produirait une boîte de dialogue illisible. Le détail complet reste en logs.
        if results.get('errors'):
            erreurs = results['errors']
            apercu = erreurs[:15]
            error_msg = "Erreurs lors de l'import:\n" + "\n".join(apercu)
            if len(erreurs) > len(apercu):
                error_msg += (f"\n\n… et {len(erreurs) - len(apercu)} autre(s). "
                              f"Détail complet dans data/logs/errors.log")
            QMessageBox.warning(self, "Erreurs d'import", error_msg)

        # Créer un résumé détaillé EXACTEMENT comme l'ancien format
        # Note: _add_to_history ajoute automatiquement le timestamp, pas besoin de le faire ici

        # Déterminer le type d'import et ajouter le nom de fichier
        if results.get('total_files', 0) > 1:
            import_type = f"Import Multi-fichiers ({results['total_files']} fichiers)"
        else:
            # Pour l'import simple, récupérer le nom du fichier
            file_details = results.get('file_details', [])
            if file_details:
                first_file = file_details[0]
                filename = first_file.get('filename', 'fichier')
                import_type = f"Import {filename}"
            else:
                import_type = "Import"

        # Commencer le résumé
        summary = f"{import_type}:\n"

        # Si c'est multi-fichiers, lister les fichiers avec leurs détails
        if results.get('total_files', 0) > 1:
            file_details = results.get('file_details', [])
            for detail in file_details:
                summary += f"Fichier {detail['type']} {detail['filename']} : {detail['lines_processed']} lignes extraites\n"
        else:
            # Pour l'import simple, afficher aussi le détail du fichier
            file_details = results.get('file_details', [])
            if file_details:
                detail = file_details[0]
                summary += f"Fichier {detail['type']} : {detail['lines_processed']} lignes extraites\n"

        # Calculer le total des lignes extraites de tous les fichiers
        file_details = results.get('file_details', [])
        total_lines_extracted = sum(detail['lines_processed'] for detail in file_details)

        # Si pas de détails de fichiers (import simple), utiliser total_imported + duplicates
        if not file_details:
            total_lines_extracted = results.get('total_imported', 0) + results.get('duplicates_in_file', 0)

        summary += f"     ==> Lignes traitées : {total_lines_extracted}\n"

        # Signal de mapping suspect : remonté ici et non plus seulement en log.
        # 25 des 495 imports de l'historique le déclenchaient sans que rien ne
        # l'affiche — un import silencieusement faux passait inaperçu.
        alerte = results.get('alerte_mapping')
        if alerte:
            summary += f"     [!] {alerte}\n"
        # Pages vides d'un PDF (contenu perdu à l'impression) : la fourchette de
        # références permet de retrouver à la main les appareils manquants.
        # Préfixe « ==> » : seul retrait que conserve le rendu HTML de l'historique.
        alertes_pages_vides = results.get('alerte_pages_vides', [])
        for titre, *fourchettes in alertes_pages_vides:
            summary += f"     [!] {titre}\n"
            for fourchette in fourchettes:
                summary += f"     ==> {fourchette}\n"
        if alertes_pages_vides:
            # Cas réel 805101 : la version triée à l'envers coupe ailleurs, et les
            # deux fichiers réunis redonnent les 370 appareils (357 et 354 seuls)
            summary += ("     ==> Conseil : régénérez le PDF avec le tri inversé et "
                        "importez-le en complément — ses coupures tombent ailleurs\n")
        summary += "\n"

        # Section Appareils (format exact)
        summary += "Appareils :\n"
        summary += f"     ==> Créés : {results.get('new_entries', 0)}\n"
        summary += f"     ==> Déjà en base : {results.get('matches_found', 0)}\n"
        summary += f"     ==> À compléter : {results.get('manual_completion', 0)}\n"
        summary += f"     ==> Doublons traités : {results.get('duplicates_in_file', 0)}\n"

        # Section Associations de pièce (format exact)
        summary += "Associations de pièce :\n"
        summary += f"     ==> Nouvelles : {results.get('associations_created', 0)}\n"
        summary += f"     ==> Déjà associées : {results.get('associations_existing', 0)}"

        # Ajouter SEULEMENT à l'historique (timestamp ajouté automatiquement)
        duration_ms = results.get('processing_time_ms')
        self.user_interaction_service.add_to_history(summary, duration_ms=duration_ms)

    
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
                    self.incomplete_filter_btn.setText(f"Filtre actif, plus que {pluralize(incomplete_count, 'ligne')}")
                    self.incomplete_filter_btn.setToolTip(f"Filtre actif - {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                else:
                    self.incomplete_filter_btn.setText(f"{pluralize(incomplete_count, 'incomplète')}")
                    self.incomplete_filter_btn.setToolTip(f"Afficher uniquement les {pluralize(incomplete_count, 'ligne')} avec des champs vides")
            else:
                self.incomplete_filter_btn.hide()
                if self.show_incomplete_only:
                    self.show_incomplete_only = False
                    self.table_controller.load_data()

    def _toggle_incomplete_filter(self, checked: bool):
        """Basculer le filtre pour afficher seulement les lignes incomplètes"""
        # PHASE 3.1: Déléguer au service de tri/filtrage
        if hasattr(self, 'sorting_filtering_service') and self.sorting_filtering_service:
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
        if (hasattr(self, 'sorting_filtering_service') and
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
        if clear_filters and hasattr(self, 'sorting_filtering_service'):
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

    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur affichage guide local")
    def _safe_show_local_guide(self):
        """Afficher un guide d'utilisation local (version protégée)"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton

        dialog = QDialog(self)
        dialog.setWindowTitle("Guide d'utilisation - 1001pieces.com")
        dialog.resize(820, 640)

        layout = QVBoxLayout()

        # Contenu du guide
        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        guide_path = Path(__file__).parent.parent.parent / "docs" / "guide_utilisation.html"
        try:
            guide_content = guide_path.read_text(encoding='utf-8')
        except (FileNotFoundError, IOError) as e:
            app_logger.warning(f"Guide d'utilisation non trouvé ({guide_path}): {e}")
            guide_content = "<html><body><h1>Guide d'utilisation</h1><p>Guide non disponible.</p></body></html>"
        guide_text.setHtml(guide_content)
        layout.addWidget(guide_text)

        # Bouton de fermeture
        close_button = QPushButton("Fermer")
        close_button.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        )
        close_button.clicked.connect(dialog.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_button)
        layout.addLayout(btn_row)

        dialog.setLayout(layout)
        dialog.exec_()

    def _show_local_guide(self):
        """Afficher un guide d'utilisation local en cas d'erreur"""
        self._safe_show_local_guide()

    def _open_export_config(self):
        """Ouvrir le dialogue de configuration des exports CSV + HTML"""
        from .export_config_dialog import ExportConfigDialog
        dialog = ExportConfigDialog(self.export_config_service, parent=self)
        dialog.finished.connect(lambda _: self.ui_component_service._refresh_html_details_menu())
        dialog.show()

    def _open_history_view(self):
        """Ouvrir le dialogue de consultation de l'historique persistant."""
        from .history_view_dialog import HistoryViewDialog
        dialog = HistoryViewDialog(self.history_service, parent=self)
        dialog.show()

    def _export_supersession_chains(self):
        """Exporter les chaînes de supersession en CSV (F8)"""
        from ..services.supersession_report_service import SupersessionReportService
        if not hasattr(self, 'supersession_report_service'):
            self.supersession_report_service = SupersessionReportService(self)
        path = self.supersession_report_service.export_chains_csv()
        if path:
            self.user_interaction_service.show_info(
                f"Chaînes de supersession exportées :\n{path}")
        else:
            self.user_interaction_service.show_info(
                "Aucune supersession enregistrée — rien à exporter.")

    def _open_restore_backup_dialog(self):
        """Ouvrir le dialogue de restauration depuis une sauvegarde (data/backups/)"""
        self._safe_open_restore_backup_dialog()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur dialogue de restauration")
    def _safe_open_restore_backup_dialog(self):
        """Dialogue de sélection et restauration d'une sauvegarde de la base"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget

        from ..services.restore_service import RestoreService
        if not hasattr(self, 'restore_service'):
            self.restore_service = RestoreService(self)

        backups = self.restore_service.list_backups()

        dialog = QDialog(self)
        dialog.setWindowTitle("Restaurer une sauvegarde")
        dialog.setModal(True)
        dialog.resize(480, 320)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title_label = QLabel("<b>Restaurer la base depuis une sauvegarde</b>")
        title_label.setStyleSheet("font-size: 14px; margin-bottom: 4px;")
        layout.addWidget(title_label)

        info_label = QLabel(
            "La restauration remplace la base actuelle par la copie sélectionnée, "
            "puis ferme l'application (à relancer manuellement).\n"
            "Une sauvegarde de l'état actuel est créée automatiquement avant l'écrasement."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        list_widget = QListWidget()
        for path, mtime, size_bytes in backups:
            size_mb = size_bytes / (1024 * 1024)
            item_text = f"{mtime.strftime('%d/%m/%Y %H:%M:%S')}  —  {size_mb:.0f} Mo  —  {path.name}"
            list_widget.addItem(item_text)
        if not backups:
            list_widget.addItem("Aucune sauvegarde disponible dans data/backups/")
            list_widget.setEnabled(False)
        layout.addWidget(list_widget)

        buttons_layout = QHBoxLayout()
        _compact = (
            "QPushButton { padding: 3px 10px; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); }"
        )

        restore_btn = QPushButton("Restaurer")
        restore_btn.setIcon(qta.icon('fa5s.history', color='#dc3545'))
        restore_btn.setIconSize(QSize(12, 12))
        restore_btn.setStyleSheet(_compact)
        restore_btn.setEnabled(False)
        buttons_layout.addWidget(restore_btn)

        buttons_layout.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet(_compact)
        cancel_btn.clicked.connect(dialog.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

        list_widget.currentRowChanged.connect(
            lambda row: restore_btn.setEnabled(row >= 0 and bool(backups))
        )

        def do_restore():
            row = list_widget.currentRow()
            if row < 0 or row >= len(backups):
                return
            backup_path, mtime, _ = backups[row]
            confirmed = self.user_interaction_service.show_confirmation(
                "Confirmer la restauration",
                f"Restaurer la base depuis la sauvegarde du "
                f"{mtime.strftime('%d/%m/%Y %H:%M:%S')} ?\n\n"
                "Toutes les modifications effectuées depuis cette date seront perdues.\n"
                "L'application va se fermer après la restauration."
            )
            if not confirmed:
                return

            error = self.restore_service.restore_and_quit(backup_path)
            if error:
                QMessageBox.critical(dialog, "Erreur de restauration",
                                     f"La restauration a échoué :\n{error}")
            else:
                dialog.accept()

        restore_btn.clicked.connect(do_restore)

        dialog.exec_()

    def _open_fts5_manager(self):
        """Ouvrir le gestionnaire d'index FTS5"""
        self._safe_open_fts5_manager()

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur gestionnaire FTS5")
    def _safe_open_fts5_manager(self):
        """Dialogue de gestion de l'index de recherche FTS5"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressDialog
        from ..core.config import Config

        dialog = QDialog(self)
        dialog.setWindowTitle("Index de recherche FTS5")
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
            "<b>La construction prend ~2 secondes. L'application reste responsive.</b>"
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
                    active_str = "Actif" if active else "Construit mais non activé"
                    return f"Statut : {active_str} — {count:,} enregistrements indexés".replace(",", " ")
                else:
                    return "Statut : Index non construit"
            except Exception as e:
                return f"Statut : Erreur — {e}"

        status_label = QLabel(get_status_text())
        status_label.setStyleSheet("font-weight: bold; padding: 6px; background: #f0f0f0; border-radius: 4px;")
        layout.addWidget(status_label)

        layout.addStretch()

        # Boutons
        buttons_layout = QHBoxLayout()

        _compact = (
            "QPushButton { padding: 3px 10px; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); }"
        )
        rebuild_btn = QPushButton("Construire / Reconstruire l'index")
        rebuild_btn.setIcon(qta.icon('fa5s.cog', color='#495057'))
        rebuild_btn.setIconSize(QSize(12, 12))
        rebuild_btn.setStyleSheet(_compact)
        rebuild_btn.setToolTip("Lance la construction complète de l'index FTS5 (~2 secondes)")

        def do_rebuild():
            rebuild_btn.setEnabled(False)
            rebuild_btn.setText("Construction en cours…")
            rebuild_btn.setIcon(qta.icon('fa5s.circle-notch', color='#495057',
                                         animation=qta.Spin(rebuild_btn)))
            QApplication.processEvents()

            try:
                count = self.db_manager.rebuild_fts5()
                Config.USE_FTS5 = True
                status_label.setText(
                    f"Statut : Actif — {count:,} enregistrements indexés".replace(",", " ")
                )
                rebuild_btn.setText("Index construit")
                rebuild_btn.setIcon(qta.icon('fa5s.check', color='#27ae60'))
                if hasattr(self, 'statusBar'):
                    self.statusBar().showMessage(
                        f"Index FTS5 construit ({count:,} enregistrements) — Recherche accélérée activée".replace(",", " "),
                        6000
                    )
            except Exception as e:
                rebuild_btn.setEnabled(True)
                rebuild_btn.setText("Construire / Reconstruire l'index")
                rebuild_btn.setIcon(qta.icon('fa5s.cog', color='#495057'))
                QMessageBox.critical(dialog, "Erreur FTS5", f"Échec de la construction de l'index :\n{e}")

        rebuild_btn.clicked.connect(do_rebuild)
        buttons_layout.addWidget(rebuild_btn)

        buttons_layout.addStretch()

        close_btn = QPushButton("Fermer")
        close_btn.setIcon(qta.icon('fa5s.times', color='#495057'))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setStyleSheet(_compact)
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

    def _export_application(self):
        """Lancer l'export portable de l'application — délégué à AppExportService."""
        self.app_export_service.open_dialog()

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
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel, QSize

        dialog = QDialog(self)
        dialog.setWindowTitle("Configuration des colonnes")
        dialog.resize(360, 300)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(6)

        # Titre
        title_label = QLabel("Colonnes à afficher :")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #343a40;")
        layout.addWidget(title_label)

        # Checkboxes pour chaque colonne
        checkboxes = {}
        for col in Config.COLUMN_CONFIG:
            checkbox = QCheckBox(col['name'])
            checkbox.setChecked(self.visible_columns[col['index']])
            checkbox.setEnabled(not col['mandatory'])
            if col['mandatory']:
                checkbox.setToolTip("Cette colonne est obligatoire et ne peut pas être cachée")
            checkboxes[col['index']] = checkbox
            layout.addWidget(checkbox)

        # Boutons
        _compact = "QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        button_layout = QHBoxLayout()

        reset_btn = QPushButton("Réinitialiser")
        reset_btn.setStyleSheet(_compact)
        reset_btn.clicked.connect(lambda: self._reset_column_defaults(checkboxes))
        button_layout.addWidget(reset_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet(_compact)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Appliquer")
        apply_btn.setIcon(qta.icon('fa5s.check', color='white'))
        apply_btn.setIconSize(QSize(12, 12))
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background-color: #218838; }"
        )
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
                self.drag_overlay_label = QLabel("Déposer votre fichier CSV/PDF ici", self.table)
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
        selected_rows = list(set([item.row() for item in self.table.selectedItems()]))
        if not selected_rows:
            return

        clicked_index = self.table.indexAt(position)
        context_menu = QMenu(self)

        # — Copier la valeur de la cellule cliquée ——————————————
        if clicked_index.isValid():
            cell_value = (self.table.model().data(clicked_index, Qt.DisplayRole) or "")
            copy_cell_action = QAction("Copier la valeur de la cellule", self)
            copy_cell_action.triggered.connect(
                lambda checked=False, v=cell_value: QApplication.clipboard().setText(v)
            )
            context_menu.addAction(copy_cell_action)

        # — Copier toute la ligne (tab-séparé) ———————————————————
        if len(selected_rows) == 1:
            row = selected_rows[0]
            mdl = self.table.model()
            row_values = [
                mdl.data(mdl.index(row, c), Qt.DisplayRole) or ""
                for c in range(mdl.columnCount())
            ]
            row_text = "\t".join(row_values)
            copy_row_action = QAction("Copier toute la ligne", self)
            copy_row_action.triggered.connect(
                lambda checked=False, t=row_text: QApplication.clipboard().setText(t)
            )
            context_menu.addAction(copy_row_action)

        # — Copier la sélection complète (comportement existant) ——
        copy_action = QAction("Copier la sélection", self)
        copy_action.triggered.connect(self._handle_copy)
        context_menu.addAction(copy_action)

        # — Filtrer sur la valeur de la cellule ———————————————————
        if clicked_index.isValid():
            col = clicked_index.column()
            cell_value = (self.table.model().data(clicked_index, Qt.DisplayRole) or "")
            has_filter_widget = col in getattr(self.table_controller, 'filter_widgets', {})
            if has_filter_widget and cell_value:
                label = cell_value if len(cell_value) <= 22 else cell_value[:20] + "…"
                filter_action = QAction(f"Filtrer sur \"{label}\"", self)
                filter_action.triggered.connect(
                    lambda checked=False, c=col, v=cell_value: self._set_column_filter(c, v)
                )
                context_menu.addAction(filter_action)

        # — Suggérer Type/Marque par similarité (si lignes incomplètes) ————
        mdl = self.table.model()
        has_incomplete = any(
            not ((mdl.data(mdl.index(r, 0), Qt.DisplayRole) or '').strip()
                 and (mdl.data(mdl.index(r, 1), Qt.DisplayRole) or '').strip())
            for r in selected_rows
        )
        if has_incomplete:
            suggest_action = QAction("Suggérer Type/Marque par similarité", self)
            suggest_action.triggered.connect(
                lambda checked=False, rows=list(selected_rows): self._suggest_similarity_for_rows(rows)
            )
            context_menu.addAction(suggest_action)

        context_menu.addSeparator()

        # — Supprimer ——————————————————————————————————————————————
        delete_action = QAction("Supprimer la/les ligne(s) sélectionnée(s)", self)
        delete_action.triggered.connect(lambda: self._delete_selected_rows(selected_rows))
        context_menu.addAction(delete_action)

        context_menu.exec_(self.table.mapToGlobal(position))

    def _suggest_similarity_for_rows(self, selected_rows):
        """Calcule à la demande des suggestions Type/Marque pour les lignes
        sélectionnées incomplètes (déclenchement manuel, hors import).

        Utilise une requête CIBLÉE par préfixe de référence (pas l'index complet
        des 655k lignes) pour rester instantané sur un clic droit.
        """
        model = self.table_controller.model
        if not model:
            return

        # Collecter les lignes incomplètes + leurs références
        incomplete = []   # (db_id, ref_modele, commercial_ref)
        prefixes = set()
        for row in selected_rows:
            db_id = model.get_db_id(row)
            if db_id is None:
                continue
            type_v = (model.data(model.index(row, 0), Qt.DisplayRole) or '').strip()
            mfr_v = (model.data(model.index(row, 1), Qt.DisplayRole) or '').strip()
            if type_v and mfr_v:
                continue
            ref_modele = (model.data(model.index(row, 2), Qt.DisplayRole) or '').strip()
            commercial_ref = (model.data(model.index(row, 3), Qt.DisplayRole) or '').strip()
            incomplete.append((db_id, ref_modele, commercial_ref))
            for ref in (ref_modele, commercial_ref):
                if len(ref) >= 3:
                    prefixes.add(ref[:3].lower())

        if not incomplete or not prefixes:
            self.user_interaction_service.add_to_history(
                "Suggestions similarité : aucune ligne incomplète dans la sélection.")
            return

        found = self._compute_similarity_suggestions(incomplete, prefixes)
        if found:
            model.add_pending_suggestions(found)
            self.table_controller._update_similarity_banner()
            self.user_interaction_service.add_to_history(
                f"Suggestions similarité : {pluralize(len(found), 'proposition')} sur "
                f"{pluralize(len(incomplete), 'ligne incomplète sélectionnée', 'lignes incomplètes sélectionnées')}"
                f" — cellules surlignées.")
        else:
            self.user_interaction_service.add_to_history(
                f"Suggestions similarité : aucune proposition sur "
                f"{pluralize(len(incomplete), 'ligne incomplète sélectionnée', 'lignes incomplètes sélectionnées')}.")

    @staticmethod
    def _requete_index_similarite(prefixes):
        """Requête sélectionnant les références partageant l'un des préfixes de
        3 caractères, parmi les appareils déjà renseignés.

        La version d'origine enchaînait une paire de « OR … LIKE ? » par préfixe.
        Deux défauts, tous deux mesurés (v3.71.1) :

        - **coût super-linéaire** — l'évaluation de l'arbre de OR dominait tout le
          reste : 8,9 s pour 300 préfixes, contre 0,5 s ici (×17) ;
        - **échec silencieux** au-delà d'environ 500 préfixes — SQLite refusait la
          requête (« Expression tree is too large », profondeur maximale 1000) et
          `execute_query` avalait l'exception. L'utilisateur lisait « aucune
          proposition » alors que 272 ou 586 l'attendaient.

        Un `IN (…)` est un nœud d'expression unique : la limite de profondeur ne
        s'applique plus. Résultat strictement identique, vérifié sur la base réelle
        (52 136 lignes des deux côtés, 0 écart).

        Effet de bord souhaitable : `LIKE 'k3_%'` traitait « _ » comme un joker,
        ce que cette forme ne fait pas — les références « K3_TYP… » sont désormais
        comparées à la lettre.

        Returns:
            (requête SQL, liste de paramètres)
        """
        prefixes = list(prefixes)
        marqueurs = ",".join("?" * len(prefixes))
        query = (
            "SELECT id, ref_modele, commercial_ref, type, manufacturer FROM appareils "
            "WHERE (type IS NOT NULL AND type != '' OR manufacturer IS NOT NULL AND manufacturer != '') "
            f"AND (LOWER(SUBSTR(ref_modele, 1, 3)) IN ({marqueurs}) "
            f"OR LOWER(SUBSTR(commercial_ref, 1, 3)) IN ({marqueurs}))"
        )
        return query, prefixes + prefixes

    def _compute_similarity_suggestions(self, incomplete, prefixes):
        """Cœur partagé (menu contextuel + scan global) : construit un index CIBLÉ
        par préfixe de référence puis calcule les candidats.

        incomplete : [(db_id, ref_modele, commercial_ref)] ; prefixes : set de préfixes
        de 3 caractères (minuscules). Retourne {db_id: [candidat_dict, ...]}.
        """
        from ..services.reference_similarity_service import ReferenceSimilarityService
        query, params = self._requete_index_similarite(prefixes)
        rows = self.db_manager.execute_query(query, params) or []
        index = ReferenceSimilarityService.build_reference_index(rows)
        svc = ReferenceSimilarityService(
            allow_numeric_fuzzy=Config.SIMILARITY_ALLOW_NUMERIC_FUZZY,
            fuzzy_threshold=Config.SIMILARITY_FUZZY_THRESHOLD,
            enable_prefix_consensus=Config.SIMILARITY_PREFIX_CONSENSUS,
            enforce_shape_compatibility=Config.SIMILARITY_ENFORCE_SHAPE,
        )
        found = {}
        for db_id, ref_modele, commercial_ref in incomplete:
            cands = svc.find_candidates(ref_modele, commercial_ref, index, exclude_db_id=db_id)
            if cands:
                found[db_id] = [c.to_dict() for c in cands]
        return found

    def _scan_all_for_suggestions(self):
        """Action menu Données : re-scanne TOUTES les lignes incomplètes chargées
        et propose des suggestions Type/Marque (utile après avoir complété des
        références de comparaison, ou pour des lignes hors période d'import)."""
        model = self.table_controller.model
        if not model:
            return
        incomplete = model.incomplete_records()
        prefixes = set()
        for _, ref_modele, commercial_ref in incomplete:
            for ref in (ref_modele, commercial_ref):
                if len(ref) >= 3:
                    prefixes.add(ref[:3].lower())
        if not incomplete or not prefixes:
            self.user_interaction_service.add_to_history(
                "Suggestions similarité (scan global) : aucune ligne incomplète dans l'affichage courant.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            found = self._compute_similarity_suggestions(incomplete, prefixes)
        finally:
            QApplication.restoreOverrideCursor()

        if found:
            model.add_pending_suggestions(found)
            self.table_controller._update_similarity_banner()
            self.user_interaction_service.add_to_history(
                f"Suggestions similarité (scan global) : {pluralize(len(found), 'proposition')} sur "
                f"{pluralize(len(incomplete), 'ligne incomplète', 'lignes incomplètes')} — cellules surlignées.")
        else:
            self.user_interaction_service.add_to_history(
                f"Suggestions similarité (scan global) : aucune proposition parmi "
                f"{pluralize(len(incomplete), 'ligne incomplète', 'lignes incomplètes')}.")

    def _set_column_filter(self, col: int, value: str):
        """Injecte une valeur dans le widget filtre de la colonne correspondante."""
        from PyQt5.QtWidgets import QComboBox, QLineEdit
        widget = self.table_controller.filter_widgets.get(col)
        if widget is None:
            return
        if isinstance(widget, QComboBox):
            widget.lineEdit().setText(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(value)
    
    def _delete_selected_rows(self, selected_rows):
        """Supprimer les lignes sélectionnées"""
        # PHASE 3.3: Déléguer au DatabaseOperationsService
        if hasattr(self, 'database_operations_service') and self.database_operations_service:
            # Ne pas passer selected_rows car ce sont des numéros de ligne, pas des IDs d'appareils
            # Le service va récupérer les vrais IDs via _get_selected_device_ids()
            self.database_operations_service.delete_selected_devices()

    def keyPressEvent(self, event):
        """Gestion des raccourcis clavier - avec délégation conditionnelle au service"""
        # PHASE 3.5: Déléguer au KeyboardShortcutService
        if self.keyboard_shortcut_service:
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
        # PHASE 3.3: Déléguer au DatabaseOperationsService
        if hasattr(self, 'database_operations_service') and self.database_operations_service:
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
                "Format de collage invalide !\n\n"
                "Le collage nécessite au minimum 1 colonne :\n"
                "• 1 colonne : Référence modèle\n"
                "• 2 colonnes : Référence modèle + Référence commerciale\n"
                "• 3 colonnes : Référence modèle + Référence commerciale + Description/Autre\n\n"
                f"Détecté : {pluralize(detected_columns, 'colonne')}\n\n"
                "💡 Astuce : Copiez les données depuis un tableur (Excel, Calc, etc.) "
                "pour conserver la séparation par tabulations."
            )
            return

        # Parser les données avec le nouveau processeur
        rows = self.paste_processor.parse_clipboard_data(clipboard_text)
        if not rows:
            return

        # Ouvrir ImportDialog avec les données du presse-papiers (v3.31.0)
        self.import_manager.import_from_clipboard(rows, callback=self._on_import_complete)



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
            f"Copié: {pluralize(len(clipboard_data), 'ligne')}",
            Config.STATUS_MESSAGE_TIMEOUT
        )

    def _handle_copy(self):
        """Gestion de la copie des données sélectionnées"""
        selected = self.table.selectedRanges()
        if not selected:
            QMessageBox.information(self, "Copie", "Aucune cellule sélectionnée")
            return

        self._safe_copy_selected_data(selected)

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

        # Arrêt propre : workers de fond stoppés + base fermée (checkpoint WAL)
        self._shutdown_cleanly()

        event.accept()

    def _shutdown_cleanly(self):
        """Séquence d'arrêt propre, idempotente, partagée par closeEvent ET par
        QApplication.aboutToQuit.

        Sur macOS, Cmd+Q déclenche aboutToQuit mais PAS toujours closeEvent : sans
        ce câblage, la base n'était jamais fermée proprement au quit (workers de
        fond encore actifs, WAL non replié) — facteur de corruption. Cette méthode
        garantit, quel que soit le chemin de sortie :
          1. l'arrêt des QThread de fond (query/prefetch via table_controller,
             import via import_manager) — plus aucune écriture en vol ;
          2. la fermeture de la base avec checkpoint WAL.
        """
        if getattr(self, '_shutdown_done', False):
            return
        self._shutdown_done = True

        # 1. Stopper les workers de fond AVANT de toucher à la connexion DB
        if hasattr(self, 'table_controller'):
            self._safe_cleanup_table_controller()
        import_worker = getattr(getattr(self, 'import_manager', None), '_import_worker', None)
        if import_worker is not None:
            try:
                if hasattr(import_worker, 'cancel'):
                    import_worker.cancel()
                if import_worker.isRunning():
                    import_worker.wait()
            except Exception:
                pass

        # Nettoyer le service d'historique groupé (flush des modifs en attente)
        if hasattr(self, 'grouped_history_service'):
            self._safe_cleanup_grouped_history()

        # 2. Fermer la base de données (checkpoint WAL + optimize, idempotent)
        if hasattr(self, 'db_manager') and self.db_manager is not None:
            self.db_manager.close()

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
    
    
    def _try_auto_complete(self, device_data: Dict[str, str]) -> bool:
        """Déléguer vers DeviceManager"""
        return self.device_manager.try_auto_complete(device_data)
    
    def _needs_manual_completion(self, device_data: Dict[str, str]) -> bool:
        """Déléguer vers DeviceManager"""
        return self.device_manager.needs_manual_completion(device_data)
    
    
    def _update_device_info(self, device_id: int, updates: Dict[str, str]) -> bool:
        """Déléguer vers DeviceManager"""
        return self.device_manager.update_device_info(device_id, updates)

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
    # Fermeture propre garantie même sur Cmd+Q (macOS) : aboutToQuit est émis dans
    # tous les cas de sortie, contrairement à closeEvent. _shutdown_cleanly est
    # idempotent → aucun double-close si les deux chemins se déclenchent.
    app.aboutToQuit.connect(window._shutdown_cleanly)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
