"""
Gestion centralisée du tableau, filtres, pagination et tri
"""

import html as _html

from typing import List, Optional
from ..utils.qt_imports import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QToolButton,
    QLabel,
    Qt,
    QTimer,
    QThread,
    pyqtSignal,
    QMenu,
    QAction,
    QPoint,
    QAbstractItemView,
    QSize,
    QHeaderView,
    QCompleter
)

from ..core.config import Config
from ..core.logger import app_logger
from ..core.constants import UIConfig
from ..utils.error_handler import (
    handle_table_operations_errors, handle_async_worker_errors,
    handle_database_operation_errors, handle_ui_operation_errors
)
from ..data.database_manager import DatabaseManager
from ..services.pieces_count_service import PiecesCountService
from .pieces_list_service import PieceRelationsPopup
from .style_manager import StyleManager

class ComboFiltreColonne(QComboBox):
    """Liste de filtre (Type, Marque) : toutes les valeurs en base, filtrées à la frappe.

    `charger_valeurs` est appelée à l'ouverture de la liste et à la prise de focus,
    pour que les types/marques ajoutés depuis le lancement apparaissent sans relancer.
    Le texte saisi est conservé lors du rechargement (sinon Qt sélectionnerait
    le 1er élément et appliquerait un filtre non voulu).
    """

    def __init__(self, charger_valeurs, parent=None):
        super().__init__(parent)
        self._charger_valeurs = charger_valeurs
        self.setEditable(True)
        # Entrée ne doit pas ajouter la saisie comme nouvel élément de la liste
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(25)
        # Complétion sur le modèle de la liste elle-même : une seule source de valeurs.
        # Filtrage par sous-chaîne, cohérent avec la requête LIKE '%text%' du filtre.
        completer = QCompleter(self.model(), self)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setMaxVisibleItems(20)
        self.setCompleter(completer)

    def rafraichir_valeurs(self):
        """Recharger la liste depuis la base en conservant le texte saisi."""
        valeurs = self._charger_valeurs() or []
        if valeurs == [self.itemText(i) for i in range(self.count())]:
            return
        texte = self.currentText()
        self.blockSignals(True)
        try:
            self.clear()
            self.addItems(valeurs)
            self.setCurrentIndex(-1)
            self.setEditText(texte)
        finally:
            self.blockSignals(False)
        # La liste prend par défaut la largeur du champ (alignée sur la colonne) et
        # tronquait les libellés (« Cent…sage ») : largeur calée sur le plus long.
        if valeurs:
            largeur = max(self.view().fontMetrics().horizontalAdvance(v) for v in valeurs) + 40
            self.view().setMinimumWidth(largeur)
            self.completer().popup().setMinimumWidth(largeur)

    def vider_saisie(self):
        """Vider le texte du filtre (setCurrentIndex(0) ne vide pas une liste modifiable)."""
        self.setCurrentIndex(-1)
        self.setEditText("")

    def showPopup(self):
        self.rafraichir_valeurs()
        super().showPopup()

    def focusInEvent(self, event):
        self.rafraichir_valeurs()
        super().focusInEvent(event)


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
        
        # Variables de pagination
        self.current_page = 1
        self.page_size = UIConfig.DEFAULT_PAGE_SIZE  # Utiliser la constante commune
        self.total_pages = 1
        self.total_rows = 0

        # Navigation cellule vide (Type/Fabricant) : direction(s) où le balayage
        # complet (toutes pages, contexte courant) n'a rien trouvé — remis à False
        # à chaque changement de contexte (recherche/tri/filtres), voir load_data()
        # et _on_header_click().
        self._empty_cells_search_exhausted = {'up': False, 'down': False}
        # Balayage de pages en cours par _on_skip_empty_cell : suspend la
        # réévaluation des flèches à chaque page traversée.
        self._incomplete_scan_in_progress = False
        # Flèches « ligne incomplète » (toolbar), branchées par set_incomplete_nav_buttons()
        self.skip_empty_up_btn = None
        self.skip_empty_down_btn = None
        
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
        # Dernière demande de recherche async mise en attente pendant un chargement
        # (coalescing) — rejouée à la fin du worker courant.
        self._pending_async_request = None

        # Historique des recherches (max 10, le plus récent en premier)
        self.search_history = []
        self.history_btn = None

        # Préchargement page suivante
        self.prefetch_cache = {}  # {cache_key: records}
        self.prefetch_worker = None  # Worker distinct de query_worker pour ne pas bloquer load_data_async
        self._prefetch_db_manager = None  # Connexion SQLite dédiée au prefetch (évite partage de connexion)

        # Vider le cache de préchargement à chaque invalidation (ajout/modif/suppression)
        # pour éviter qu'une page rechargée (F5) ne réaffiche des lignes obsolètes/supprimées
        if hasattr(self.db_manager, 'cache_invalidation'):
            self.db_manager.cache_invalidation.register_invalidation_callback(
                lambda reason: self.prefetch_cache.clear()
            )
        self._pending_prefetch_params = None
        self.prefetch_timer = QTimer()
        self.prefetch_timer.setSingleShot(True)
        self.prefetch_timer.timeout.connect(self._execute_prefetch)
        
        # Bypass supersession : si True, la recherche ignore la résolution via chaîne (mode "superseded")
        self._supersession_bypass = False
        self._supersession_term = None
        self._supersession_chain = []
        # Mode "replacing" : term est une ref courante qui remplace d'autres refs
        self._supersession_mode = ''          # 'superseded' | 'replacing' | ''
        self._supersession_predecessors = []  # prédécesseurs dans le mode "replacing"
        self._supersession_expand = False     # True = inclure les appareils des prédécesseurs
        self._supersession_siblings = []      # Autres prédécesseurs de la ref courante (sœurs)
        # Équivalence : term fait partie d'un groupe d'équivalence
        self._equivalence_expand = False      # True = inclure les appareils des équivalents
        self._equivalence_term = None
        self._equivalence_group = []          # autres membres du groupe (sans le term) — sert à l'extension
        self._equivalence_display = []        # sous-ensemble affiché : hors chaîne de succession

        # Recherche étendue : False (défaut) = ref_piece exacte, True = LIKE '%term%'
        # (inclut les refs contenant le terme, ex: "086565" matche aussi "C00865650")
        self._extend_search_active = False

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
        m = layout.contentsMargins()
        layout.setContentsMargins(m.left(), 0, 0, 0)  # droite : l'espace est la poignée (8 px)
        layout.setSpacing(6)

        # Barre de recherche supprimée d'ici - maintenant sous le tableau
        
        # Hauteurs naturelles selon le widget de référence de chaque ligne (macOS-safe)
        _filter_btn_h = QComboBox().sizeHint().height()   # ligne filtres — dominée par QComboBox (32px)
        _search_btn_h = QLineEdit().sizeHint().height()   # ligne recherche — dominée par QLineEdit (21px)

        # Filtres par colonne alignés sur les colonnes du tableau
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(0)  # Aligné aux colonnes : pas d'espacement

        # Bouton entonnoir 'Filtres' calé sur la largeur de la colonne des n° de ligne
        # (en-tête vertical). Toujours visible : il pilote l'affichage des filtres.
        # Sa largeur est synchronisée dans _sync_filter_alignment().
        import qtawesome as _qta_f
        self.filters_toggle_btn = QToolButton()
        self.filters_toggle_btn.setCheckable(True)
        self.filters_toggle_btn.setIcon(_qta_f.icon('fa5s.filter', color='#555555'))
        self.filters_toggle_btn.setToolTip("Afficher / masquer les filtres par colonne")
        self.filters_toggle_btn.setStyleSheet(
            StyleManager.BOUTON_OUTIL_BASCULE
        )
        self.filters_toggle_btn.toggled.connect(self._toggle_column_filters)
        filter_layout.addWidget(self.filters_toggle_btn, 0, Qt.AlignVCenter)

        for i, header in enumerate(Config.UI_HEADERS):
            # Skip filters for invisible or useless columns
            if i == 7:  # "Nb Pièces" column
                continue
            if i == 5 or i == 6:  # "Catégorie" et "Notes" - inutiles
                continue
            
            # Create dropdown filters for Type (index 0) and Fabricant (index 1)
            if i == 0 or i == 1:  # Type or Fabricant columns
                filter_combo = ComboFiltreColonne(
                    lambda col=i: self._valeurs_filtre_colonne(col))
                filter_combo.lineEdit().setPlaceholderText(f"{header}...")
                filter_combo.setStyleSheet("""
                    QComboBox {
                        margin: 0 2px;
                        padding: 2px 8px;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        background-color: white;
                    }
                    QComboBox:focus {
                        border-color: #0d6efd;
                    }
                """)
                # Liste complète (flèche) + complétion par sous-chaîne dès le 1er
                # caractère : cf. ComboFiltreColonne. Valeurs chargées ici puis
                # relues à l'ouverture de la liste et à la prise de focus.
                filter_combo.rafraichir_valeurs()
                filter_combo.currentTextChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
                self.filter_widgets[i] = filter_combo
                filter_layout.addWidget(filter_combo)  # largeur fixée au sync (alignée colonne)
            else:
                # Champs texte avec même style que les dropdowns
                filter_input = QLineEdit()
                filter_input.setPlaceholderText(f"{header}...")
                filter_input.textChanged.connect(lambda text, col=i: self._apply_column_filter(col, text))
                filter_input.setStyleSheet("""
                    QLineEdit {
                        margin: 0 2px;
                        padding: 2px 8px;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        background-color: white;
                    }
                    QLineEdit:focus {
                        border-color: #0d6efd;
                        outline: none;
                    }
                """)
                self.filter_widgets[i] = filter_input
                # Colonne 4 = colonne en stretch du tableau → le filtre stretch aussi
                # (évite la boucle de rétroaction d'une largeur fixe qui chasse le stretch)
                filter_layout.addWidget(filter_input, 1 if i == 4 else 0)

        # Bouton RAZ pour vider tous les filtres colonne
        raz_btn = QPushButton()
        raz_btn.setIcon(_qta_f.icon('fa5s.times', color='#868e96'))
        raz_btn.setIconSize(QSize(10, 10))
        # Largeur fixe ; hauteur calée sur celle des champs dans _sync_filter_alignment
        # (la hauteur d'une QComboBox mesurée à la construction, avant le style
        # global, rendait le bouton plus haut que les champs)
        raz_btn.setFixedSize(28, _filter_btn_h)
        raz_btn.setToolTip("Réinitialiser tous les filtres")
        raz_btn.setStyleSheet(StyleManager.CLEAR_FILTERS_BUTTON)
        raz_btn.clicked.connect(self._clear_all_column_filters)
        self.raz_btn = raz_btn

        # Zone au-dessus de la colonne figée « Pièces » (+ ascenseur + cadre) : le
        # bouton RAZ y est CENTRÉ sur la colonne. Avant, il était placé juste avant
        # cette zone (31 px à gauche du centre, au-dessus d'« Autre référence ») et
        # privait le filtre de la colonne 4 de 15 px. Largeurs : _sync_filter_alignment.
        self.filter_trailing_spacer = QWidget()
        _zone = QHBoxLayout(self.filter_trailing_spacer)
        _zone.setContentsMargins(0, 0, 0, 0)
        _zone.setSpacing(0)
        _zone.addWidget(raz_btn, 0, Qt.AlignCenter)
        self._raz_zone_layout = _zone
        self.filter_trailing_spacer.setFixedWidth(52)
        filter_layout.addWidget(self.filter_trailing_spacer)

        # Étirement final : actif UNIQUEMENT en replié (pour packer le bouton à gauche).
        # Déplié, c'est le filtre col 4 qui prend l'étirement (cf. _apply_column_filters_visibility).
        filter_layout.addStretch(0)
        self._filter_trailing_stretch_index = filter_layout.count() - 1

        layout.addWidget(filter_widget)

        # Sauvegarder les références pour la visibilité
        self.filter_widget = filter_widget
        self.filter_layout = filter_layout
        
        # Tableau principal — QTableView + AppareillsTableModel
        from ..data.appareils_table_model import AppareillsTableModel, PiecesCountDelegate, SuggestionCellDelegate
        from .custom_table_view import CustomTableView
        self.model = AppareillsTableModel(self.parent_window)
        self.table = CustomTableView()
        self.table.setModel(self.model)
        self.table.main_window = self.parent_window
        # Delegate des colonnes Type/Marque : suggestion en case + icône cliquable.
        self._suggestion_delegate = SuggestionCellDelegate(self.table)
        self._suggestion_delegate.accept_handler = self._on_suggestion_icon_clicked
        self._suggestion_delegate.verify_handler = self._on_verify_icon_clicked
        self.table.setItemDelegateForColumn(0, self._suggestion_delegate)
        self.table.setItemDelegateForColumn(1, self._suggestion_delegate)
        # Headers gérés par model.headerData() — pas de setHorizontalHeaderLabels()

        # Configuration QTableView
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

        # Édition par double-clic ou F2 uniquement : un clic simple ne fait que
        # sélectionner (le « 2e clic sur la cellule courante → édition » de mars
        # 2026 a été retiré en 3.77.1, il ouvrait l'éditeur sans le vouloir).
        # Pas de SelectedClicked ni AnyKeyPressed : la frappe sur une cellule
        # remplie ne l'édite volontairement pas (évite les modifications non désirées).
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed
        )

        # Tri géré manuellement (désactiver le tri automatique Qt)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_click)

        # Log des largeurs de colonnes quand elles sont modifiées
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)
        # Réaligner les filtres sur les colonnes quand une colonne est redimensionnée
        self.table.horizontalHeader().sectionResized.connect(lambda *a: self._sync_filter_alignment())

        # Appliquer la visibilité des colonnes
        self._apply_column_visibility()

        # Définir les largeurs par défaut des colonnes
        self._set_default_column_widths()

        # Colonne Nb Pièces figée à droite (badge pill, hors scroll horizontal)
        self.table.freeze_right_column(len(Config.DB_HEADERS), PiecesCountDelegate(self.table))

        # Une ligne sur deux légèrement teintée (alternate-background-color du
        # style global) : aide l'œil à suivre une ligne sur toute la largeur.
        self.table.setAlternatingRowColors(True)
        self.set_row_height(UIConfig.ROW_HEIGHTS[UIConfig.DEFAULT_ROW_HEIGHT][1])
        # Réf. Modèle et Réf. Commerciale s'ajustent automatiquement à la largeur du tableau
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        layout.addWidget(self.table)
        self.table_widget_layout = layout  # réf. pour repositionner la recherche

        # Conteneur [recherche + bannières] repositionnable (haut/bas du tableau).
        # Les bannières supersession/équivalence restent SOLIDAIRES de la recherche
        # (elles lisent le terme courant) : on les groupe pour éviter toute régression.
        # Les bannières sont toujours ENTRE la recherche et le tableau : l'ordre
        # interne du conteneur s'inverse avec la position (cf. set_search_position).
        self.search_container = QWidget()
        _sc_layout = QVBoxLayout(self.search_container)
        _sc_layout.setContentsMargins(0, 0, 0, 0)
        _sc_layout.setSpacing(6)

        # Barre de recherche (dans le conteneur) — portée par un widget sans marges
        # pour pouvoir la déplacer avant/après les bannières
        self.search_bar_widget = QWidget()
        search_layout2 = QHBoxLayout(self.search_bar_widget)
        search_layout2.setContentsMargins(0, 0, 0, 0)
        import qtawesome as qta
        search_icon_label = QLabel()
        search_icon_label.setPixmap(qta.icon('fa5s.search', color='#555555').pixmap(14, 14))
        search_layout2.addWidget(search_icon_label, 0, Qt.AlignVCenter)
        search_label2 = QLabel("Recherche par pièce :")
        search_layout2.addWidget(search_label2, 0, Qt.AlignVCenter)

        self.advanced_search_input = QLineEdit()
        self.advanced_search_input.setPlaceholderText("Référence pièce (ex: AS6015830, ou plusieurs: ref1 || ref2)...")
        self.advanced_search_input.setClearButtonEnabled(True)  # Bouton × natif intégré au champ
        # Connecté par MainWindow à AdvancedSearchService
        search_layout2.addWidget(self.advanced_search_input, 1, Qt.AlignVCenter)

        # Bouton "Étendre la recherche" : par défaut, la recherche par référence est
        # exacte (ref_piece = terme). Coché, elle redevient partielle (LIKE '%terme%'),
        # ce qui peut inclure des références plus longues contenant le terme recherché.
        self.extend_search_btn = QToolButton()
        self.extend_search_btn.setCheckable(True)
        self.extend_search_btn.setIcon(qta.icon('fa5s.search-plus', color='#555555'))
        self.extend_search_btn.setToolTip(
            "Étendre la recherche : inclure les références contenant le terme recherché\n"
            "(par défaut, seule la référence exacte est recherchée)"
        )
        self.extend_search_btn.setStyleSheet(
            StyleManager.BOUTON_OUTIL_BASCULE
        )
        self.extend_search_btn.toggled.connect(self._toggle_extend_search)
        search_layout2.addWidget(self.extend_search_btn, 0, Qt.AlignVCenter)

        # Bouton historique des recherches
        self.history_btn = QToolButton()
        self.history_btn.setText("▾")
        self.history_btn.setFixedSize(28, _search_btn_h)
        self.history_btn.setToolTip("Historique des recherches")
        self.history_btn.setStyleSheet("""
            QToolButton {
                background-color: #546e7a;
                color: white;
                border: 1px solid #37474f;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
                padding: 0px;
            }
            QToolButton:hover {
                background-color: #37474f;
            }
            QToolButton:pressed {
                background-color: #263238;
            }
            QToolButton:disabled {
                background-color: #b0bec5;
                border-color: #90a4ae;
            }
        """)
        self.history_btn.setEnabled(False)  # Désactivé jusqu'à ce qu'il y ait un historique
        self.history_btn.clicked.connect(self._show_search_history)
        search_layout2.addWidget(self.history_btn, 0, Qt.AlignVCenter)


        # Bandeau de notification supersession (caché par défaut)
        self.supersession_banner = QWidget()
        self.supersession_banner.setVisible(False)
        self.supersession_banner.setStyleSheet(
            "QWidget { background-color: #E3F2FD; border: 1px solid #64B5F6; border-radius: 3px; }"
        )
        banner_layout = QHBoxLayout(self.supersession_banner)
        banner_layout.setContentsMargins(8, 3, 8, 3)
        banner_layout.setSpacing(8)

        self.supersession_banner_label = QLabel()
        self.supersession_banner_label.setStyleSheet("color: #0D47A1; font-size: 12px; border: none; background: transparent;")
        self.supersession_banner_label.setTextFormat(Qt.RichText)
        self.supersession_banner_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.supersession_banner_label.linkActivated.connect(self._on_supersession_ref_clicked)
        banner_layout.addWidget(self.supersession_banner_label)

        # Bouton overflow "… +N" — visible uniquement quand les refs sont tronquées.
        # Séparé du label pour éviter le bug d'alignement Qt (RichText + <a href>
        # active le moteur QTextDocument qui ignore Qt.AlignVCenter sur le label).
        self.supersession_overflow_btn = QPushButton()
        self.supersession_overflow_btn.setFlat(True)
        self.supersession_overflow_btn.setStyleSheet(
            "QPushButton { color: #1565C0; font-size: 12px; border: none; background: transparent; padding: 0px; }"
            "QPushButton:hover { color: #0D47A1; text-decoration: underline; }"
        )
        self.supersession_overflow_btn.setCursor(Qt.PointingHandCursor)
        self.supersession_overflow_btn.setVisible(False)
        self.supersession_overflow_btn.clicked.connect(lambda: self._show_supersession_popup())
        banner_layout.addWidget(self.supersession_overflow_btn)
        banner_layout.addStretch()

        self.supersession_bypass_btn = QPushButton()
        self.supersession_bypass_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #1565C0;
                border: 1px solid #90CAF9;
                border-radius: 3px;
                font-size: 11px;
                padding: 1px 6px;
            }
            QPushButton:hover { background-color: #90CAF9; }
        """)
        self.supersession_bypass_btn.clicked.connect(self._toggle_supersession_bypass)
        banner_layout.addWidget(self.supersession_bypass_btn)

        _sc_layout.addWidget(self.supersession_banner)

        # Bandeau équivalence (caché par défaut, fond violet clair)
        self.equivalence_banner = QWidget()
        self.equivalence_banner.setVisible(False)
        self.equivalence_banner.setStyleSheet(
            "QWidget { background-color: #F3E5F5; border: 1px solid #CE93D8; border-radius: 3px; }"
        )
        equiv_banner_layout = QHBoxLayout(self.equivalence_banner)
        equiv_banner_layout.setContentsMargins(8, 3, 8, 3)
        equiv_banner_layout.setSpacing(8)

        self.equivalence_banner_label = QLabel()
        self.equivalence_banner_label.setStyleSheet(
            "color: #6A1B9A; font-size: 12px; border: none; background: transparent;"
        )
        self.equivalence_banner_label.setTextFormat(Qt.RichText)
        self.equivalence_banner_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        # Pas de setAlignment : RichText + <a href> active QTextDocument qui ignore AlignVCenter.
        # Le centrage vertical est assuré par le HBoxLayout parent.
        self.equivalence_banner_label.linkActivated.connect(self._on_equivalence_ref_clicked)
        equiv_banner_layout.addWidget(self.equivalence_banner_label)

        # Bouton overflow "… +N" — visible uniquement quand les refs sont tronquées.
        # Séparé du label pour éviter le bug d'alignement Qt (même raison que supersession_overflow_btn).
        self.equivalence_overflow_btn = QPushButton()
        self.equivalence_overflow_btn.setFlat(True)
        self.equivalence_overflow_btn.setStyleSheet(
            "QPushButton { color: #6A1B9A; font-size: 12px; border: none; background: transparent; padding: 0px; }"
            "QPushButton:hover { color: #4A148C; text-decoration: underline; }"
        )
        self.equivalence_overflow_btn.setCursor(Qt.PointingHandCursor)
        self.equivalence_overflow_btn.setVisible(False)
        self.equivalence_overflow_btn.clicked.connect(lambda: self._show_equivalence_popup())
        equiv_banner_layout.addWidget(self.equivalence_overflow_btn)
        equiv_banner_layout.addStretch()

        self.equivalence_expand_btn = QPushButton()
        self.equivalence_expand_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #6A1B9A;
                border: 1px solid #CE93D8;
                border-radius: 3px;
                font-size: 11px;
                padding: 1px 6px;
            }
            QPushButton:hover { background-color: #CE93D8; }
        """)
        self.equivalence_expand_btn.clicked.connect(self._toggle_equivalence_expand)
        equiv_banner_layout.addWidget(self.equivalence_expand_btn)
        _sc_layout.addWidget(self.equivalence_banner)

        # Les suggestions Type/Marque n'ont plus de bandeau ici (v3.92.0) : elles
        # sont signalées par le bouton « Suggestions à valider (N) » de la barre
        # d'état (cf. MainWindow._rafraichir_bouton_suggestions).

        # Position par défaut (sous le tableau) : bannières puis recherche,
        # la recherche restant juste au-dessus de la navigation
        _sc_layout.addWidget(self.search_bar_widget)

        # Ajouter le conteneur recherche au layout (position par défaut : sous le tableau)
        layout.addWidget(self.search_container)

        # Boutons d'export : déplacés en bas de la colonne de droite
        # (cf. main_refactored._create_pieces_widget) pour dégager le bas du tableau.

        # Contrôles de pagination
        self._add_pagination_controls(layout)
        
        # Le bouton "Lignes à traiter" est désormais créé dans la toolbar
        # (toolbar_service), à gauche de "Nettoyer les doublons".

        # Appliquer l'état mémorisé des filtres colonnes (défaut : masqués)
        _show_filters = False
        if hasattr(self.parent_window, 'settings'):
            _show_filters = self.parent_window.settings.value("ui/show_column_filters", False, type=bool)
        self.filters_toggle_btn.blockSignals(True)
        self.filters_toggle_btn.setChecked(_show_filters)
        self.filters_toggle_btn.blockSignals(False)
        self._apply_column_filters_visibility(_show_filters)
        self._sync_filter_alignment()  # caler le bouton/filtres dès la construction

        return widget

    def _toggle_column_filters(self, checked: bool):
        """Afficher/masquer la rangée de filtres par colonne + mémoriser l'état."""
        self._apply_column_filters_visibility(checked)
        if hasattr(self.parent_window, 'settings'):
            self.parent_window.settings.setValue("ui/show_column_filters", checked)

    def _apply_column_filters_visibility(self, visible: bool):
        """Afficher/masquer les CHAMPS de filtre (le bouton entonnoir reste visible).

        La rangée `filter_widget` reste affichée en permanence (elle porte le bouton
        entonnoir qui pilote le repli) ; seuls les champs de filtre et le bouton RAZ
        apparaissent/disparaissent.
        """
        for w in getattr(self, 'filter_widgets', {}).values():
            if w is not None:
                w.setVisible(visible)
        if getattr(self, 'filter_trailing_spacer', None) is not None:
            self.filter_trailing_spacer.setVisible(visible)

        # Gestion de l'étirement : déplié → la colonne 4 prend l'étirement (elle remplit) ;
        # replié → l'étirement final prend le relais pour packer le bouton entonnoir à gauche.
        layout = getattr(self, 'filter_layout', None)
        f4 = getattr(self, 'filter_widgets', {}).get(4)
        if layout is not None:
            if f4 is not None:
                idx4 = layout.indexOf(f4)
                if idx4 >= 0:
                    layout.setStretch(idx4, 1 if visible else 0)
            ts = getattr(self, '_filter_trailing_stretch_index', -1)
            if ts >= 0:
                layout.setStretch(ts, 0 if visible else 1)

        if visible:
            # Réaligner les champs sur les colonnes au moment de l'affichage,
            # puis une 2e fois après stabilisation du layout (colonne 4 en stretch)
            self._sync_filter_alignment()
            QTimer.singleShot(0, self._sync_filter_alignment)

    def _sync_filter_alignment(self):
        """Caler le bouton entonnoir et chaque champ de filtre sur la largeur de sa colonne.

        - Bouton entonnoir = largeur de l'en-tête vertical (colonne des n° de ligne).
        - Champ i = largeur de la colonne i du tableau.
        Resynchronisé sur `sectionResized` (col. 4 en stretch bouge au redimensionnement).
        """
        if getattr(self, 'table', None) is None:
            return
        vh = self.table.verticalHeader().width()
        if getattr(self, 'filters_toggle_btn', None) is not None and vh > 0:
            self.filters_toggle_btn.setFixedWidth(vh)
        for i, w in getattr(self, 'filter_widgets', {}).items():
            if w is None or self.table.isColumnHidden(i):
                continue
            if i == 4:
                # Colonne en stretch : largeur libre (le filtre stretch via le layout),
                # sinon une largeur fixe chasserait sans fin le stretch (boucle).
                w.setMinimumWidth(0)
                w.setMaximumWidth(16777215)
                continue
            col_w = self.table.columnWidth(i)
            if col_w > 0:
                w.setFixedWidth(col_w)
        # Zone de droite = colonne figée « Pièces » + ascenseur + cadre du tableau ;
        # le bouton RAZ est centré sur la colonne (marge droite = ascenseur + cadre)
        if getattr(self, 'filter_trailing_spacer', None) is not None:
            frozen_w = getattr(self.table, '_frozen_col_width', 52) or 52
            reste = self.table.verticalScrollBar().sizeHint().width() + self.table.frameWidth()
            self.filter_trailing_spacer.setFixedWidth(frozen_w + reste)
            if getattr(self, '_raz_zone_layout', None) is not None:
                self._raz_zone_layout.setContentsMargins(0, 0, reste, 0)
        # Bouton RAZ à la hauteur des champs de filtre
        if getattr(self, 'raz_btn', None) is not None:
            hauteurs = [w.sizeHint().height() for w in getattr(self, 'filter_widgets', {}).values()
                        if w is not None]
            if hauteurs:
                self.raz_btn.setFixedHeight(min(hauteurs))

    def set_row_height(self, height: int):
        """Appliquer une hauteur de ligne au tableau ET à sa colonne figée.

        Les deux vues ont chacune leur en-tête vertical : sans synchronisation,
        les pastilles « Pièces » se décaleraient des lignes qu'elles décrivent.
        La hauteur minimale est abaissée d'abord, sinon Qt refuse les valeurs
        sous le minimum déduit du style (padding de l'en-tête).
        """
        views = [self.table]
        frozen = getattr(self.table, '_frozen_view', None)
        if frozen is not None:
            views.append(frozen)
        for view in views:
            vh = view.verticalHeader()
            vh.setMinimumSectionSize(min(height, vh.minimumSectionSize()))
            vh.setDefaultSectionSize(height)

    def set_search_position(self, position: str):
        """Repositionner le conteneur recherche (+ bannières) au-dessus ou sous le tableau.

        position : "top" (au-dessus du tableau) ou "bottom" (sous le tableau, défaut).
        """
        if getattr(self, 'search_container', None) is None:
            return
        layout = getattr(self, 'table_widget_layout', None)
        if layout is None:
            return
        layout.removeWidget(self.search_container)
        # Bannières toujours entre la recherche et le tableau : la barre de
        # recherche passe en tête (haut) ou en fin (bas) du conteneur
        sc_layout = self.search_container.layout()
        sc_layout.removeWidget(self.search_bar_widget)
        if position == "top":
            # Tout en haut, AU-DESSUS des filtres colonnes (qui restent juste au-dessus du tableau)
            sc_layout.insertWidget(0, self.search_bar_widget)
            layout.insertWidget(0, self.search_container)
        else:
            # Sous le tableau (position par défaut), recherche juste au-dessus de la navigation
            sc_layout.addWidget(self.search_bar_widget)
            table_idx = layout.indexOf(self.table)
            layout.insertWidget(table_idx + 1, self.search_container)
        self.search_container.setVisible(True)
    
    def connect_selection_signals(self, on_selection_changed_callback):
        """Connecter les signaux de sélection du tableau à un callback"""
        if not self.table:
            return
        # QTableView : signaux via selectionModel()
        self.table.selectionModel().selectionChanged.connect(
            lambda selected, _: on_selection_changed_callback()
        )
        self.table.selectionModel().currentChanged.connect(
            lambda current, previous: on_selection_changed_callback()
        )
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur chargement données tableau")
    def build_effective_search_term(self, search_term: str = None):
        """
        Construire le terme de recherche effectif (parsing && / || + injection des
        flags de supersession/équivalence actifs sur le tableau : bypass_supersession,
        expand_predecessors, expand_equivalents).

        Centralisé ici pour que d'autres consommateurs (ex: export) reproduisent
        exactement le même périmètre de résultats que celui affiché dans le tableau.
        """
        # SOLUTION FINALE: Parser avec SearchService directement sans condition (UNIVERSALE)
        effective_search_term = search_term
        if search_term and isinstance(search_term, str) and hasattr(self.parent_window, 'search_service'):
            # Toujours parser avec SearchService pour uniformité && et ||
            parsed_term = self.parent_window.search_service.parse_advanced_search(search_term)
            if parsed_term:  # Si parsing réussi, utiliser le terme parsé
                effective_search_term = parsed_term

        # Injecter le flag de recherche étendue si actif (case à cocher)
        if self._extend_search_active and isinstance(effective_search_term, dict):
            effective_search_term = dict(effective_search_term)
            effective_search_term['extend_search'] = True

        # Injecter le flag bypass supersession si actif (mode "superseded")
        if self._supersession_bypass and isinstance(effective_search_term, dict):
            effective_search_term = dict(effective_search_term)
            effective_search_term['bypass_supersession'] = True

        # Injecter les références sœurs en mode "superseded" sans bypass
        # (tous les prédécesseurs de la ref courante, ex : REF_B et REF_C quand on cherche REF_A)
        if (not self._supersession_bypass
                and self._supersession_siblings
                and self._supersession_mode == 'superseded'
                and isinstance(effective_search_term, dict)):
            effective_search_term = dict(effective_search_term)
            existing = list(effective_search_term.get('expand_predecessors', []))
            for r in self._supersession_siblings:
                if r not in existing:
                    existing.append(r)
            effective_search_term['expand_predecessors'] = existing

        # Injecter les prédécesseurs si expansion active (mode "replacing")
        if self._supersession_expand and self._supersession_predecessors and isinstance(effective_search_term, dict):
            effective_search_term = dict(effective_search_term)
            effective_search_term['expand_predecessors'] = self._supersession_predecessors

        # Injecter les équivalents si expansion active
        if self._equivalence_expand and self._equivalence_group and isinstance(effective_search_term, dict):
            effective_search_term = dict(effective_search_term)
            effective_search_term['expand_equivalents'] = self._equivalence_group

        return effective_search_term

    def load_data(self, search_term: str = None, is_search: bool = False):
        """Charger les données dans le tableau avec pagination et filtres"""
        import time
        start_time = time.time()

        # CORRECTION: Mettre à jour current_search_term pour tous les appels load_data
        self.current_search_term = search_term

        # Nouveau contexte affiché (recherche/filtres) : les directions
        # précédemment marquées épuisées peuvent de nouveau contenir des
        # cellules vides (ex: nouveau terme de recherche moins restrictif).
        # _on_skip_empty_cell() re-marque la direction concernée juste après
        # son propre balayage complet, donc pas d'interférence avec les
        # rechargements de page qu'il déclenche lui-même en cours de route.
        self._empty_cells_search_exhausted = {'up': False, 'down': False}

        # Cacher les bannières (supersession + équivalence) si aucune recherche active
        if not search_term:
            self._hide_supersession_banner()
            self._hide_equivalence_banner()
        else:
            # Nouveau terme : les réf. ajoutées par les bandeaux (anciennes réf.,
            # équivalents) appartiennent à la recherche précédente. Les oublier AVANT
            # de construire la requête, sinon une réf. sans bandeau affichait les
            # lignes de la recherche d'avant (le bandeau n'était caché qu'après le
            # remplissage, sans relance). Même terme (pagination, tri, filtres,
            # cases des bandeaux) : états conservés.
            terme = search_term.strip() if isinstance(search_term, str) else search_term
            if self._supersession_term is not None and terme != self._supersession_term:
                self._hide_supersession_banner()
            if self._equivalence_term is not None and terme != self._equivalence_term:
                self._hide_equivalence_banner()

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
        incomplete_filter = self._current_incomplete_filter()

        effective_search_term = self.build_effective_search_term(search_term)

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

        # Informer l'utilisateur si la recherche a remonté via une chaîne de supersession
        if is_search and search_term and isinstance(search_term, str):
            self._check_supersession_banner(search_term.strip())

        # Mettre à jour les contrôles de pagination
        self._update_pagination_controls()

        if is_search:
            self._show_search_result_message(search_term)

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

        # Panneau pièces : vider si aucune ligne sélectionnée après chargement
        # (couvre : 0 résultat, RAZ colonne, nouvelle recherche, tri — dans tous ces cas
        #  la sélection est perdue et le panneau ne doit pas afficher les vieilles pièces)
        if self.table.currentRow() < 0 and hasattr(self.parent_window, 'pieces_panel_service'):
            self.parent_window.pieces_panel_service.update_pieces_panel()

        # Performance logging
        elapsed = time.time() - start_time
        app_logger.debug(f"Table loaded: {len(records) if 'records' in locals() else 0} records in {elapsed:.3f}s")

    def _show_search_result_message(self, search_term):
        """Barre d'état : total RÉEL de la recherche, une fois le tableau rempli.

        Appelé après _check_supersession_banner, qui relance le chargement avec
        les références ajoutées (anciennes réf., chaîne, équivalents) : total_rows
        est alors celui affiché sous le tableau, pas celui du terme seul.
        """
        if not hasattr(self.parent_window, 'statusbar'):
            return
        if not (search_term and str(search_term).strip()):
            # Recherche effacée : retirer « Recherche avancée : '…' »
            self.parent_window.statusbar.clearMessage()
            return
        precisions = []
        if self._supersession_mode == 'superseded' and not self._supersession_bypass:
            precisions.append("chaîne complète")
        elif (self._supersession_mode == 'replacing' and self._supersession_expand
              and self._supersession_predecessors):
            precisions.append("anciennes réf. incluses")
        if self._equivalence_expand and self._equivalence_group:
            precisions.append("équivalents inclus")
        suffixe = f" ({', '.join(precisions)})" if precisions else ""
        total = f"{self.total_rows:,}".replace(",", "\u202f")  # espace fine, comme le compteur
        resultats = "résultat" if self.total_rows <= 1 else "résultats"
        self.parent_window.statusbar.showMessage(
            f"Recherche terminée : {total} {resultats}{suffixe}",
            Config.SEARCH_STATUS_MESSAGE_TIMEOUT
        )

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur démarrage load_data_async")
    def load_data_async(self, search_term: str = None, is_search: bool = False):
        """Version asynchrone de load_data() - Phase 2c

        ATTENTION: Même logique que load_data() mais avec requête DB en arrière-plan
        pour éviter le gel de l'UI. Résultats identiques garantis.
        """
        import time
        start_time = time.time()

        # Empêcher les requêtes multiples simultanées, mais NE PAS abandonner la
        # demande : on mémorise la dernière (coalescing) pour la rejouer dès que le
        # worker courant se termine. Sinon, une recherche tapée pendant qu'une
        # requête tourne encore était silencieusement perdue → le tableau gardait
        # les anciens résultats (notamment « aucun résultat » jamais affiché).
        if self.loading_in_progress:
            self._pending_async_request = (search_term, is_search)
            app_logger.debug("Requête async déjà en cours — demande mise en attente (coalescing)")
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
            self.parent_window.statusbar.showMessage("Chargement des données…")

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

        # Panneau pièces : vider si aucune ligne sélectionnée (même logique que load_data)
        if self.table.currentRow() < 0 and hasattr(self.parent_window, 'pieces_panel_service'):
            self.parent_window.pieces_panel_service.update_pieces_panel()

        # Nettoyer et finaliser
        self.loading_in_progress = False
        if hasattr(self.parent_window, 'statusbar'):
            self.parent_window.statusbar.showMessage(f"{len(records)} lignes chargées", Config.STATUS_MESSAGE_TIMEOUT)

        app_logger.debug(f"load_data_async terminé: {len(records)} résultats")

        # Rejouer la dernière demande mise en attente pendant ce chargement (coalescing)
        self._drain_pending_async_request()

    def _drain_pending_async_request(self):
        """Relance la dernière recherche async mise en attente pendant qu'une autre
        tournait. Garantit que la DERNIÈRE demande de l'utilisateur gagne toujours,
        sans relancer les requêtes intermédiaires (une seule en attente à la fois)."""
        pending = getattr(self, '_pending_async_request', None)
        if pending is not None:
            self._pending_async_request = None
            search_term, is_search = pending
            self.load_data_async(search_term, is_search)

    def _on_async_error(self, error_msg):
        """Callback en cas d'erreur async"""
        app_logger.error(f"Erreur requête async: {error_msg}")
        self.loading_in_progress = False
        self.table.setRowCount(0)
        if hasattr(self.parent_window, 'statusbar'):
            self.parent_window.statusbar.showMessage(f"Erreur DB : {error_msg}", Config.STATUS_MESSAGE_TIMEOUT)

        # Rejouer la dernière demande mise en attente même après une erreur, sinon
        # l'UI resterait bloquée sur l'ancien contenu jusqu'au prochain rafraîchissement.
        self._drain_pending_async_request()

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
            1: 155,  # Fabricant (124 coupait « Arthur-Martin-Electrolux »)
            2: 150,  # Référence Modèle
            3: 175,  # Référence Commerciale
            4: 120,  # Autre Référence
            5: 100,  # Catégorie (peut être cachée)
            6: 200,  # Notes (peut être cachée)
            7: 60,   # Nb Pièces (en-tête « Pièces », cf. AppareilsTableModel.headerData)
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

            # Passer par load_data (is_search=False) pour conserver toutes les injections :
            # bypass_supersession, expand_predecessors (sœurs), expand_equivalents.
            # current_sort_column / current_sort_order sont déjà mis à jour par _on_header_click.
            self.load_data(self.current_search_term, is_search=False)
            self._update_sort_indicators()
        finally:
            # Nettoyer le flag de tri en cours
            self._sorting_in_progress = False

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
        """Ajouter les contrôles de pagination.

        Trois zones dans une grille (compteur | navigation | lignes par page) :
        les deux colonnes extérieures ont le même poids, donc la navigation reste
        réellement centrée quelle que soit la longueur du compteur. Aucun widget
        n'est jamais masqué : sur une seule page, la navigation est grisée par
        NavigationService — la géométrie de la barre ne bouge pas.
        """
        from PyQt5.QtWidgets import QGridLayout
        import qtawesome as _qta_nav
        pagination_widget = QWidget()
        self.pagination_widget = pagination_widget
        pagination_layout = QGridLayout(pagination_widget)
        pagination_layout.setContentsMargins(4, 2, 4, 0)
        pagination_layout.setColumnStretch(0, 1)
        pagination_layout.setColumnStretch(2, 1)

        # Zone gauche : compteur de lignes
        self.size_label = QLabel(self._format_row_count(self.total_rows))
        pagination_layout.addWidget(self.size_label, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)

        # Zone centrale : navigation  ⏮ ◀ Page [n] / N ▶ ⏭
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)

        # Style unique pour les 4 boutons de navigation, avec règle :disabled
        # pour une désactivation cohérente (une seule page → tout grisé).
        _btn_style = StyleManager.SECONDARY_COMPACT_BUTTON   # rôle Compact

        def _nav_button(icon_name: str, tooltip: str) -> QPushButton:
            btn = QPushButton()
            btn.setIcon(_qta_nav.icon(icon_name, color='#555555', color_disabled='#c4c8cc'))
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_btn_style)
            nav_layout.addWidget(btn)
            return btn

        # Navigation gérée par NavigationService (clics + état activé/grisé)
        self.first_button = _nav_button('fa5s.angle-double-left', "Première page")
        self.prev_button = _nav_button('fa5s.angle-left', "Page précédente")

        # Saut de page direct : "Page [champ éditable] / N"
        self.page_text_label = QLabel("Page")
        nav_layout.addWidget(self.page_text_label)
        self.page_input = QLineEdit("1")
        self.page_input.setFixedWidth(48)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.setToolTip("Saisir un numéro de page puis Entrée")
        self.page_input.setStyleSheet(
            "QLineEdit { padding: 2px; font-size: 11px; border: 1px solid #bdbdbd;"
            " border-radius: 3px; } QLineEdit:focus { border: 1px solid #0d6efd; }"
            " QLineEdit:disabled { color: #adb5bd; border-color: #dee2e6; }"
        )
        nav_layout.addWidget(self.page_input)
        self.page_total_label = QLabel("/ 1")
        # Largeur réservée pour « / 99999 » : le total ne pousse plus les boutons
        self.page_total_label.setMinimumWidth(
            self.page_total_label.fontMetrics().horizontalAdvance("/ 99999") + 4
        )
        nav_layout.addWidget(self.page_total_label)
        # page_label conservé à None (remplacé par page_input + page_total_label)
        self.page_label = None

        self.next_button = _nav_button('fa5s.angle-right', "Page suivante")
        self.last_button = _nav_button('fa5s.angle-double-right', "Dernière page")

        pagination_layout.addWidget(nav_widget, 0, 1, Qt.AlignCenter)

        # Les boutons de saut vers la ligne incomplète précédente/suivante sont
        # dans la toolbar, autour de « Lignes à traiter » (cf. toolbar_service) ;
        # ils sont branchés ici par set_incomplete_nav_buttons().

        # Zone droite : sélecteur taille de page
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)
        size_label = QLabel("Lignes par page")
        size_layout.addWidget(size_label)
        
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["100", "250", "500", "1000", "2000", "Tout"])
        self.page_size_combo.setCurrentText(str(UIConfig.DEFAULT_PAGE_SIZE))
        self.page_size_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #bdbdbd;
                border-radius: 3px;
                padding: 2px 4px 2px 8px;
                background-color: white;
                color: #333333;
                min-width: 65px;
            }
            QComboBox:hover {
                border-color: #0d6efd;
            }
            QComboBox:focus {
                border-color: #0d6efd;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                width: 8px;
                height: 8px;
            }
        """)
        # Style du dropdown appliqué directement sur la view (plus fiable sur macOS)
        self.page_size_combo.view().setStyleSheet("""
            QAbstractItemView {
                background-color: white;
                border: 1px solid #bdbdbd;
                outline: none;
            }
            QAbstractItemView::item {
                background-color: white;
                color: #333333;
                padding: 4px 12px;
                min-height: 20px;
            }
            QAbstractItemView::item:hover {
                background-color: #eeeeee;
                color: #333333;
            }
            QAbstractItemView::item:selected {
                background-color: #e0e0e0;
                color: #333333;
            }
        """)
        # Changement de taille géré par NavigationService
        size_layout.addWidget(self.page_size_combo)
        pagination_layout.addWidget(size_widget, 0, 2, Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(pagination_widget)
    
    @staticmethod
    def _format_row_count(count: int) -> str:
        """« 690 418 lignes » : milliers séparés par une espace fine insécable."""
        return f"{count:,} {'ligne' if count <= 1 else 'lignes'}".replace(",", "\u202f")

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mise à jour pagination")
    def _update_pagination_controls(self):
        """Mettre à jour les contrôles de pagination"""
        # Champ de saut de page + total (remplace l'ancien page_label)
        if getattr(self, 'page_input', None) is not None:
            blocked = self.page_input.blockSignals(True)
            self.page_input.setText(str(self.current_page))
            self.page_input.blockSignals(blocked)
        if getattr(self, 'page_total_label', None) is not None:
            self.page_total_label.setText(f"/ {self.total_pages}")
        if self.size_label:
            self.size_label.setText(self._format_row_count(self.total_rows))

        # Une seule page : on grise au lieu de masquer (géométrie stable). Les
        # 4 boutons sont gérés par NavigationService ; le champ de page ici.
        single_page = self.total_pages <= 1
        for w in (getattr(self, 'page_input', None), getattr(self, 'page_text_label', None),
                  getattr(self, 'page_total_label', None)):
            if w is not None:
                w.setEnabled(not single_page)

        # Nouveau contexte affiché : réévaluer les flèches « ligne incomplète »
        # (sauf pendant leur propre balayage de pages, qui conclut lui-même).
        if not getattr(self, '_incomplete_scan_in_progress', False):
            self._update_empty_cell_buttons_state()

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
    
    @handle_database_operation_errors(return_value=[], log_prefix="Erreur liste filtre colonne")
    def _valeurs_filtre_colonne(self, column: int) -> List[str]:
        """Toutes les valeurs distinctes de la colonne Type (0) ou Marque (1).

        Volumétrie mesurée : ~40 types, ~500 marques ; la requête parcourt l'index
        couvrant de la colonne (6 ms pour les types, ~40 ms pour les marques).
        """
        db_field = "type" if column == 0 else "manufacturer"
        results = self.db_manager.execute_query(
            f"SELECT DISTINCT [{db_field}] FROM appareils "
            f"WHERE [{db_field}] IS NOT NULL AND [{db_field}] != '' "
            f"ORDER BY [{db_field}] COLLATE NOCASE"
        )
        return [row[0] for row in results if row[0]]
    
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
    
    @handle_table_operations_errors(log_prefix="Erreur récupération ID base de données")
    def get_db_id_from_row(self, row: int) -> int:
        """Récupérer l'ID de base de données d'une ligne"""
        item = self.table.item(row, 0)
        if item:
            return item.data(Qt.UserRole) or -1
        return -1
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur RAZ filtres colonne")
    def _clear_all_column_filters(self, checked=False):
        """Vider tous les filtres par colonne et recharger les données"""
        # Bloquer les signaux pour éviter N rechargements consécutifs
        for widget in self.filter_widgets.values():
            if widget is None:
                continue
            widget.blockSignals(True)
            try:
                if isinstance(widget, ComboFiltreColonne):
                    widget.vider_saisie()
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText("")
                else:
                    widget.clear()
            except RuntimeError:
                pass
            finally:
                widget.blockSignals(False)

        # Un seul rechargement après RAZ de tous les champs
        self.load_data(self.current_search_term, is_search=bool(self.current_search_term))

    
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

    def _check_supersession_banner(self, term: str):
        """
        Afficher le bandeau selon le rôle du terme dans la chaîne de supersession.

        Mode "superseded" : term est une ancienne réf. → chaîne forward affichée.
        Mode "replacing"  : term est une réf. courante qui remplace d'autres → prédécesseurs affichés.
        """
        if not hasattr(self, 'supersession_banner'):
            return
        if not term or '||' in term or '&&' in term:
            self._hide_supersession_banner()
            return
        try:
            # Cas A : term est une ancienne réf. (chaîne forward > 1 élément)
            chain = self.db_manager.get_supersession_chain(term)
            if len(chain) > 1:
                ref_current = chain[-1]
                all_preds = self.db_manager.get_all_predecessors(ref_current)
                siblings = [r for r in all_preds if r != term]
                siblings_are_new = siblings and set(siblings) != set(self._supersession_siblings)
                self._supersession_mode = 'superseded'
                self._supersession_term = term
                self._supersession_chain = chain
                self._supersession_predecessors = []
                self._supersession_siblings = siblings
                self._update_supersession_banner()
                self.supersession_banner.setVisible(True)
                equiv_is_new = self._check_equivalence_banner(term)
                # Les sœurs sont calculées APRÈS le premier chargement → relancer la requête
                # is_search=False pour ne pas rappeler _check_supersession_banner (évite boucle infinie)
                if siblings_are_new or equiv_is_new:
                    self.load_data(self.current_search_term, is_search=False)
                    # Rafraîchir la bannière après le fill_table (le layout connaît maintenant la vraie largeur)
                    self._update_supersession_banner()
                    self.supersession_banner.updateGeometry()
                return

            # Cas B : term est une réf. courante qui remplace d'autres
            predecessors = self.db_manager.get_all_predecessors(term)
            if predecessors:
                is_new_term = term != self._supersession_term
                self._supersession_mode = 'replacing'
                self._supersession_term = term
                self._supersession_chain = []
                self._supersession_predecessors = predecessors
                if is_new_term:
                    # Par défaut, une nouvelle recherche inclut les appareils des prédécesseurs
                    self._supersession_expand = True
                self._update_supersession_banner()
                self.supersession_banner.setVisible(True)
                equiv_is_new = self._check_equivalence_banner(term)
                if is_new_term or equiv_is_new:
                    # Le 1er chargement a eu lieu sans expansion (flag pas encore connu) → relancer
                    self.load_data(self.current_search_term, is_search=False)
                    self._update_supersession_banner()
                return

            self._hide_supersession_banner()
            if self._check_equivalence_banner(term):
                # 1er chargement sans expansion (flag pas encore connu) → relancer
                self.load_data(self.current_search_term, is_search=False)
                self._update_equivalence_banner()
        except Exception:
            self._hide_supersession_banner()
            self._hide_equivalence_banner()

    def _hide_supersession_banner(self):
        """Cacher le bandeau et réinitialiser tous les états de supersession."""
        self._supersession_bypass = False
        self._supersession_expand = False
        self._supersession_mode = ''
        self._supersession_term = None
        self._supersession_chain = []
        self._supersession_predecessors = []
        self._supersession_siblings = []
        if hasattr(self, 'supersession_banner'):
            self.supersession_banner.setVisible(False)

    # ── Suggestions Type/Marque par similarité ──────────────────────────────
    def set_similarity_suggestions(self, suggestions_by_db_id):
        """Installe les suggestions calculées (après import) dans le modèle et
        met à jour le compteur. {db_id: [candidat_dict, ...]}."""
        if self.model is not None and hasattr(self.model, 'set_pending_suggestions'):
            self.model.set_pending_suggestions(suggestions_by_db_id or {})
            self._update_similarity_indicator()

    def clear_similarity_suggestion(self, db_id):
        """Dissipe l'indicateur d'une ligne (acceptée / ignorée) et rafraîchit le compteur."""
        if self.model is not None and hasattr(self.model, 'clear_suggestion'):
            self.model.clear_suggestion(db_id)
            self._update_similarity_indicator()

    def _on_suggestion_icon_clicked(self, index, suggestions):
        """Relais du clic sur l'icône de suggestion (depuis SuggestionCellDelegate)
        vers la fenêtre principale : application directe si 1 candidat, chooser sinon."""
        if hasattr(self.parent_window, '_resolve_suggestion_inline'):
            self.parent_window._resolve_suggestion_inline(index, suggestions)

    def _on_verify_icon_clicked(self, index):
        """Relais du clic sur la coche d'une cellule auto-complétée : marque
        l'appareil comme vérifié (même chemin que le clic droit)."""
        db_id = self.model.get_db_id(index.row()) if self.model else None
        if db_id is not None and hasattr(self.parent_window, '_marquer_lignes_verifiees'):
            self.parent_window._marquer_lignes_verifiees([db_id], origine="clic sur la coche")

    def _update_similarity_indicator(self):
        """Relaie le nombre de suggestions en attente au bouton « Suggestions à
        valider (N) » de la barre d'état (absent tant qu'elle n'est pas créée)."""
        rafraichir = getattr(self.parent_window, '_rafraichir_bouton_suggestions', None)
        if rafraichir is not None:
            rafraichir()

    def _on_supersession_ref_clicked(self, ref: str):
        """Déclencher une nouvelle recherche en cliquant sur une référence dans la bannière."""
        if hasattr(self.parent_window, 'search_input'):
            self.parent_window.search_input.setText(ref)

    def _on_equivalence_ref_clicked(self, ref: str):
        """Déclencher une nouvelle recherche en cliquant sur une référence dans la bannière équivalence."""
        if hasattr(self.parent_window, 'search_input'):
            self.parent_window.search_input.setText(ref)

    @staticmethod
    def _make_linked_refs(refs: list, max_inline: int = 3, link_color: str = '#5D4037') -> tuple:
        """Tronque une liste de refs en enveloppant les refs visibles en liens HTML.

        Retourne (html_inline, tooltip_plain) :
        - html_inline  : refs inline avec <a href>, tronquées si > max_inline
        - tooltip_plain : liste complète en texte brut si tronquée, sinon ""
        """
        if not refs:
            return "", ""
        style = f'color:{link_color};text-decoration:underline;'
        full_plain = ", ".join(refs)
        shown = refs[:max_inline]
        linked = ", ".join(
            f'<a href="{_html.escape(r, quote=True)}" style="{style}">{_html.escape(r)}</a>'
            for r in shown
        )
        if len(refs) > max_inline:
            return f"{linked}  … +{len(refs) - max_inline}", full_plain
        return linked, ""

    def _update_supersession_banner(self):
        """Mettre à jour le texte et le bouton du bandeau selon le mode et l'état."""
        if not hasattr(self, 'supersession_banner_label'):
            return
        term = self._supersession_term or ''

        def _t(html: str) -> str:
            """Supprime les marges de bloc de QTextDocument pour éviter le décalage vertical."""
            return f"<p style='margin:0;padding:0;'>{html}</p>"

        def _link_chain(chain):
            """Chaîne de supersession avec chaque ref cliquable, séparée par →"""
            style = 'color:#5D4037;text-decoration:underline;'
            return " → ".join(
                f'<a href="{_html.escape(r, quote=True)}" style="{style}">{_html.escape(r)}</a>'
                for r in chain
            )

        if self._supersession_mode == 'superseded':
            chain = self._supersession_chain
            if self._supersession_bypass:
                self.supersession_banner_label.setText(_t(
                    f"▲ Résultats pour '{_html.escape(term)}' uniquement (ancienne réf.)"
                ))
                self.supersession_overflow_btn.setVisible(False)
                self.supersession_bypass_btn.setText("Voir toute la chaîne →")
            else:
                chain_html = _link_chain(chain)
                sibs = getattr(self, '_supersession_siblings', [])
                if sibs:
                    sibs_disp, sibs_tip = self._make_linked_refs(sibs)
                    prefix = f"▲ Ancienne réf. : {chain_html} (courante) — ainsi que : "
                    if sibs_tip:
                        base_disp, overflow = sibs_disp.rsplit('… +', 1)
                        self.supersession_banner_label.setText(_t(prefix + base_disp))
                        self.supersession_overflow_btn.setText(f"… +{overflow}")
                        self.supersession_overflow_btn.setToolTip(sibs_tip)
                        self.supersession_overflow_btn.setVisible(True)
                    else:
                        self.supersession_banner_label.setText(_t(prefix + sibs_disp))
                        self.supersession_overflow_btn.setVisible(False)
                else:
                    self.supersession_banner_label.setText(_t(
                        f"▲ Ancienne réf. : {chain_html} (courante)"
                    ))
                    self.supersession_overflow_btn.setVisible(False)
                self.supersession_banner_label.setToolTip("")
                self.supersession_bypass_btn.setText(f"Voir uniquement '{term}'")

        elif self._supersession_mode == 'replacing':
            preds = self._supersession_predecessors
            preds_disp, preds_tip = self._make_linked_refs(preds)
            if self._supersession_expand:
                prefix = f"▲ Résultats étendus — '{_html.escape(term)}' remplace : "
                self.supersession_bypass_btn.setText(f"Voir uniquement '{term}'")
            else:
                prefix = f"▲ '{_html.escape(term)}' remplace : "
                self.supersession_bypass_btn.setText("Voir aussi les appareils des réfs remplacées")
            if preds_tip:
                base_disp, overflow = preds_disp.rsplit('… +', 1)
                self.supersession_banner_label.setText(_t(prefix + base_disp))
                self.supersession_overflow_btn.setText(f"… +{overflow}")
                self.supersession_overflow_btn.setToolTip(preds_tip)
                self.supersession_overflow_btn.setVisible(True)
            else:
                self.supersession_banner_label.setText(_t(prefix + preds_disp))
                self.supersession_overflow_btn.setVisible(False)
            self.supersession_banner_label.setToolTip("")

    def _toggle_extend_search(self, checked: bool):
        """Basculer entre recherche exacte (défaut) et recherche étendue (LIKE substring)."""
        self._extend_search_active = checked
        self.load_data(self.current_search_term, is_search=True)

    # ── Navigation cellule vide (Type/Fabricant) ────────────────────────────

    def _current_incomplete_filter(self) -> bool:
        """Filtre « Lignes à traiter » actif ? Source : le service de tri/filtrage
        s'il existe, sinon l'attribut historique de la fenêtre."""
        # CORRECTION: Utiliser le service de tri/filtrage si disponible
        if (hasattr(self.parent_window, 'sorting_filtering_service') and
            self.parent_window.sorting_filtering_service):
            return self.parent_window.sorting_filtering_service.incomplete_filter_active
        return getattr(self.parent_window, 'show_incomplete_only', False)

    def _live_column_filters(self) -> dict:
        """Filtres de colonne actuellement saisis (même logique que load_data),
        utilisés pour que la vérification d'existence de cellule vide respecte
        exactement le même périmètre que ce qui est affiché à l'écran."""
        column_filters = {}
        for col_idx, filter_widget in self.filter_widgets.items():
            if filter_widget is not None:
                filter_text = (filter_widget.currentText() if isinstance(filter_widget, QComboBox)
                                else filter_widget.text()).strip()
                if filter_text:
                    column_filters[col_idx] = filter_text
        return column_filters

    def set_incomplete_nav_buttons(self, up_btn, down_btn):
        """Brancher les flèches « ligne incomplète précédente/suivante », créées
        dans la toolbar autour de « Lignes à traiter » (cf. toolbar_service)."""
        self.skip_empty_up_btn = up_btn
        self.skip_empty_down_btn = down_btn
        up_btn.clicked.connect(lambda: self._on_skip_empty_cell('up'))
        down_btn.clicked.connect(lambda: self._on_skip_empty_cell('down'))
        # État initial : posé au premier load_data (via _update_pagination_controls) —
        # la toolbar est construite avant le tableau, ses filtres n'existent pas encore.

    def on_incomplete_count_changed(self, _count: int = 0):
        """Le nombre de lignes incomplètes a changé (cellule vidée ou complétée,
        import…) : réévaluer les flèches tout de suite, sans attendre le prochain
        chargement de page. Sans cela, des flèches qui apparaissent (0 → 1)
        restaient grisées jusqu'au chargement suivant. L'épuisement mémorisé
        est oublié : une ligne apparue peut se trouver dans n'importe quelle
        direction."""
        self._empty_cells_search_exhausted = {'up': False, 'down': False}
        self._update_empty_cell_buttons_state()

    def _update_empty_cell_buttons_state(self):
        """Grise/dégrise les flèches selon l'existence d'au moins une ligne
        incomplète dans le périmètre courant (recherche/filtres actifs) et
        l'épuisement éventuel de chaque direction (mémorisé par le dernier
        balayage complet de _on_skip_empty_cell, remis à zéro à chaque nouveau
        contexte affiché — voir load_data()). Indépendant de la colonne sous le
        focus : réévalué à chaque affichage de page, pas à chaque clic de cellule."""
        if getattr(self, 'skip_empty_up_btn', None) is None:
            return

        effective_search_term = self.build_effective_search_term(self.current_search_term)
        has_incomplete = self.db_manager.count_data(
            effective_search_term, self._live_column_filters(), incomplete_filter=True
        ) > 0

        self.skip_empty_up_btn.setEnabled(has_incomplete and not self._empty_cells_search_exhausted['up'])
        self.skip_empty_down_btn.setEnabled(has_incomplete and not self._empty_cells_search_exhausted['down'])

    def _goto_page_preserving_context(self, page: int):
        """Change de page en gardant tri/recherche/filtres, via le chemin
        canonique NavigationService.go_to_page() quand disponible : ce service
        maintient son propre current_page interne, relu ensuite par
        _update_pagination_controls() pour l'affichage (champ de page, boutons
        «/») — muter self.current_page puis appeler load_data() directement
        désynchronise cet affichage du current_page réel."""
        if self.navigation_service:
            self.navigation_service.go_to_page(page)
        else:
            self.current_page = page
            self.load_data(self.current_search_term)

    def skip_to_incomplete_row(self, direction: str):
        """Point d'entrée des raccourcis ⌥⌘↑ / ⌥⌘↓ : même effet qu'un clic sur
        la flèche correspondante, et rien si elle est grisée (direction épuisée
        ou aucune ligne incomplète dans le périmètre)."""
        btn = getattr(self, 'skip_empty_up_btn' if direction == 'up' else 'skip_empty_down_btn', None)
        if btn is not None and btn.isEnabled() and btn.isVisible():
            self._on_skip_empty_cell(direction)

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur saut cellule vide")
    def _on_skip_empty_cell(self, direction: str):
        """Sauter vers la prochaine/précédente ligne incomplète (Type ou
        Fabricant vide), quelle que soit la colonne sous le focus, et placer le
        curseur sur la cellule à remplir. Le contexte courant (tri, recherche,
        filtres) est conservé : la ligne cible apparaît avec son environnement.

        1. Page affichée d'abord : cas le plus fréquent, aucune requête.
        2. Sinon une requête SQL donne la position de la cible dans l'ordre de
           l'écran → un seul chargement de page (find_incomplete_position).
        3. Repli sur le parcours page par page si la requête n'est pas possible
           (tri « Nb pièces ») ou échoue.
        """
        if not self.model:
            return

        start_index = self.table.currentIndex()
        row = start_index.row()
        if row < 0:
            # Aucune sélection : ▼ part du haut de la page, ▲ part du bas
            row = -1 if direction == 'down' else self.model.loaded_record_count()

        # 1. Page affichée
        found = self.model.find_incomplete_row(row, direction)
        if found is not None:
            self._focus_cell(*found)
            return

        if self.page_size != -1 and self.total_pages > 1:
            # 2. Position SQL au-delà de la page affichée
            try:
                position = self._find_incomplete_position_beyond_page(direction)
            except Exception as e:
                app_logger.warning(f"Saut ligne incomplète : requête de position impossible "
                                   f"({e}), repli sur le parcours des pages")
                self._scan_pages_for_incomplete(direction, start_index)
                return
            if position is not None:
                self._goto_page_preserving_context(position // self.page_size + 1)
                target_row = position % self.page_size
                # Recherche locale autour du rang visé (et non sélection aveugle) :
                # si une écriture a eu lieu entre-temps, on retombe sur la ligne
                # incomplète la plus proche dans la bonne direction.
                found = (self.model.find_incomplete_row(target_row - 1, 'down') if direction == 'down'
                         else self.model.find_incomplete_row(target_row + 1, 'up'))
                if found is not None:
                    self._focus_cell(*found)
                # Changement de page : load_data a remis à zéro l'épuisement
                # des deux directions → refléter ce nouvel état une seule fois.
                self._update_empty_cell_buttons_state()
                return

        # Rien dans cette direction, sans avoir quitté la page : la flèche se grise
        # silencieusement, sans interrompre l'utilisateur au milieu d'une série
        # de complétions.
        self._empty_cells_search_exhausted[direction] = True
        self._update_empty_cell_buttons_state()

    def _focus_cell(self, row: int, col: int):
        """Sélectionner une cellule de la page (révélée au
        besoin par le virtual scroll) et donner le focus au tableau."""
        self.model.reveal_row(row)
        target_index = self.model.index(row, col)
        self.table.setCurrentIndex(target_index)
        self.table.scrollTo(target_index)
        self.table.setFocus()

    def _find_incomplete_position_beyond_page(self, direction: str) -> Optional[int]:
        """Position globale de la prochaine ligne incomplète après la fin (▼) ou
        avant le début (▲) de la page affichée, avec exactement les paramètres
        de load_data (terme effectif, filtres, tri, filtre « Lignes à traiter »)."""
        page_start = (self.current_page - 1) * self.page_size
        from_position = (page_start + self.model.loaded_record_count() - 1
                         if direction == 'down' else page_start)
        sort_order_str = "ASC" if self.current_sort_order == Qt.AscendingOrder else "DESC"
        return self.db_manager.find_incomplete_position(
            self.build_effective_search_term(self.current_search_term),
            self._live_column_filters(),
            self.current_sort_column, sort_order_str,
            self._current_incomplete_filter(),
            from_position, direction,
        )

    def _scan_pages_for_incomplete(self, direction: str, start_index):
        """Repli : parcourir les pages une à une (tri « Nb pièces », ou requête
        de position en échec). La page affichée a déjà été examinée."""
        start_page = self.current_page
        start_cell = (start_index.row(), start_index.column()) if start_index.isValid() else None
        max_pages_to_scan = max(self.total_pages, 1)
        scanned_pages = 0

        self._incomplete_scan_in_progress = True
        try:
            while scanned_pages < max_pages_to_scan:
                # Page suivante/précédente, avec exactement les mêmes tri/recherche/filtres.
                if direction == 'down':
                    if self.page_size == -1 or self.current_page >= self.total_pages:
                        break
                    self._goto_page_preserving_context(self.current_page + 1)
                    row = -1  # recherche à partir de juste avant la 1ère ligne
                else:
                    if self.page_size == -1 or self.current_page <= 1:
                        break
                    self._goto_page_preserving_context(self.current_page - 1)
                    row = self.model.loaded_record_count()  # juste après la dernière ligne
                scanned_pages += 1

                found = self.model.find_incomplete_row(row, direction)
                if found is not None:
                    self._focus_cell(*found)
                    self._incomplete_scan_in_progress = False
                    # load_data a remis à zéro l'épuisement des deux directions
                    self._update_empty_cell_buttons_state()
                    return

            # Rien trouvé : revenir là où l'utilisateur était, au lieu de le
            # laisser sur la dernière (ou première) page traversée, sans sélection.
            if self.current_page != start_page:
                self._goto_page_preserving_context(start_page)
                if start_cell is not None:
                    self._focus_cell(*start_cell)
        finally:
            self._incomplete_scan_in_progress = False

        # Balayage complet sans résultat : mémoriser l'épuisement de cette
        # direction (après le retour, que load_data aurait sinon effacé).
        self._empty_cells_search_exhausted[direction] = True
        self._update_empty_cell_buttons_state()

    def _toggle_supersession_bypass(self):
        """Basculer l'état du bouton selon le mode actif."""
        if self._supersession_mode == 'superseded':
            self._supersession_bypass = not self._supersession_bypass
        elif self._supersession_mode == 'replacing':
            self._supersession_expand = not self._supersession_expand
        self._update_supersession_banner()
        self.load_data(self.current_search_term, is_search=True)

    # ── Bannière d'équivalence ───────────────────────────────────────────────

    def _check_equivalence_banner(self, term: str) -> bool:
        """
        Afficher le bandeau équivalence si le terme appartient à un groupe.
        Retourne True si l'expansion par défaut vient d'être (re)activée pour un
        nouveau groupe — signal pour l'appelant qu'un rechargement est nécessaire.
        """
        if not hasattr(self, 'equivalence_banner'):
            return False
        if not term or '||' in term or '&&' in term:
            self._hide_equivalence_banner()
            return False
        try:
            equivalents = self.db_manager.get_equivalents(term)
            # Affichage : sans les réfs déjà montrées par la chaîne de succession.
            # Groupe réduit à la seule famille du terme → rien à montrer : bandeau caché.
            display = (self.db_manager.get_equivalents_hors_chaine(term)
                       if equivalents else [])
            if display:
                group_is_new = set(equivalents) != set(self._equivalence_group)
                self._equivalence_term = term
                self._equivalence_group = equivalents
                self._equivalence_display = display
                if group_is_new:
                    # Par défaut, une nouvelle recherche inclut les appareils des équivalents
                    self._equivalence_expand = True
                self._update_equivalence_banner()
                self.equivalence_banner.setVisible(True)
                return group_is_new
            else:
                self._hide_equivalence_banner()
                return False
        except Exception:
            self._hide_equivalence_banner()
            return False

    def _hide_equivalence_banner(self):
        """Cacher le bandeau équivalence et réinitialiser l'état."""
        self._equivalence_expand = False
        self._equivalence_term = None
        self._equivalence_group = []
        self._equivalence_display = []
        if hasattr(self, 'equivalence_banner'):
            self.equivalence_banner.setVisible(False)

    def _update_equivalence_banner(self):
        """Mettre à jour le texte du bandeau équivalence."""
        if not hasattr(self, 'equivalence_banner_label'):
            return
        term = self._equivalence_term or ''
        equivs_disp, equivs_tip = self._make_linked_refs(self._equivalence_display, link_color='#6A1B9A')
        if self._equivalence_expand:
            prefix = f"≡ Résultats étendus — '{_html.escape(term)}' · équivalents inclus : "
            self.equivalence_expand_btn.setText(f"Voir uniquement '{term}'")
        else:
            prefix = f"≡ '{_html.escape(term)}' a des équivalents : "
            self.equivalence_expand_btn.setText("Voir aussi les appareils des équivalents")
        if equivs_tip:
            base_disp, overflow = equivs_disp.rsplit('… +', 1)
            self.equivalence_banner_label.setText(prefix + base_disp)
            self.equivalence_overflow_btn.setText(f"… +{overflow}")
            self.equivalence_overflow_btn.setToolTip(equivs_tip)
            self.equivalence_overflow_btn.setVisible(True)
        else:
            self.equivalence_banner_label.setText(prefix + equivs_disp)
            self.equivalence_overflow_btn.setVisible(False)
        self.equivalence_banner_label.setToolTip("")

    def _toggle_equivalence_expand(self):
        """Basculer l'inclusion des équivalents dans la recherche."""
        self._equivalence_expand = not self._equivalence_expand
        self._update_equivalence_banner()
        self.load_data(self.current_search_term, is_search=True)

    def _show_supersession_popup(self):
        """Popup de synthèse des relations pour le terme courant (bannière supersession)."""
        term = self._supersession_term or ''
        if not term:
            return
        chain = self._supersession_chain or []
        preds = self._supersession_predecessors or []
        equivs = self._equivalence_display if self._equivalence_term == term else []
        status_info = {
            'status':      'superseded' if self._supersession_mode == 'superseded' else 'replacing',
            'ref_new':     chain[-1] if chain and self._supersession_mode == 'superseded' else None,
            'refs_old':    ', '.join(preds) if preds else None,
            'is_obsolete': False,
            'equivalents': ', '.join(equivs) if equivs else None,
        }
        parent_widget = getattr(self, 'main_window', None)
        self._active_popup = PieceRelationsPopup(term, status_info, parent_widget)
        self._active_popup.show_at_cursor()

    def _show_equivalence_popup(self):
        """Popup de synthèse des relations pour le terme courant (bannière équivalence)."""
        term = self._equivalence_term or ''
        if not term:
            return
        equivs = self._equivalence_display or []
        preds  = self._supersession_predecessors if self._supersession_term == term else []
        status_info = {
            'status':      'replacing' if preds else 'current',
            'ref_new':     None,
            'refs_old':    ', '.join(preds) if preds else None,
            'is_obsolete': False,
            'equivalents': ', '.join(equivs) if equivs else None,
        }
        parent_widget = getattr(self, 'main_window', None)
        self._active_popup = PieceRelationsPopup(term, status_info, parent_widget)
        self._active_popup.show_at_cursor()

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
                    self.incomplete_filter_btn.setText(f"Filtre actif, plus que {pluralize(incomplete_count, 'ligne')}")
                    self.incomplete_filter_btn.setToolTip(f"Filtre actif - {pluralize(incomplete_count, 'ligne')} avec des champs vides")
                else:
                    self.incomplete_filter_btn.setText(f"{pluralize(incomplete_count, 'incomplète')}")
                    self.incomplete_filter_btn.setToolTip(f"Afficher uniquement les {pluralize(incomplete_count, 'ligne')} avec des champs vides")
            else:
                self.incomplete_filter_btn.hide()
    
    @handle_table_operations_errors(log_prefix="Erreur log largeur colonne")
    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        """Log des largeurs de colonnes quand elles sont modifiées"""
        # Récupérer le nom de la colonne
        column_name = Config.UI_HEADERS[logical_index] if logical_index < len(Config.UI_HEADERS) else f"Colonne {logical_index}"
    
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur nettoyage widgets")
    def stop_workers(self):
        """Arrêter proprement les QThread de fond (query + prefetch) avant la
        fermeture de la base. Indispensable au moment du quit : un worker encore
        en cours d'écriture sur la connexion partagée au moment où le process se
        termine est un risque de corruption de la base. Bloque jusqu'à la fin de
        chaque worker (les requêtes sont courtes). Idempotent."""
        if hasattr(self, 'prefetch_timer') and self.prefetch_timer is not None:
            try:
                self.prefetch_timer.stop()
            except Exception:
                pass
        for attr in ('query_worker', 'prefetch_worker'):
            worker = getattr(self, attr, None)
            if worker is not None:
                try:
                    if worker.isRunning():
                        worker.quit()
                        worker.wait()
                except Exception:
                    pass
                setattr(self, attr, None)

    def cleanup(self):
        """Nettoyage sécurisé des widgets Qt pour éviter les erreurs de destruction"""
        # Arrêter les workers de fond AVANT toute fermeture de connexion DB
        self.stop_workers()
        # Nettoyer les références aux widgets qui pourraient être détruits
        if hasattr(self, 'advanced_search_input'):
            self.advanced_search_input = None
        if hasattr(self, 'search_input'):
            self.search_input = None
        if hasattr(self, 'filter_widgets'):
            self.filter_widgets.clear()
