"""
Gestionnaire des pièces - Fenêtre de gestion des références de pièces
"""

from .qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                           QTableWidgetItem, QLabel, QPushButton, QLineEdit,
                           QHeaderView, QMessageBox, QSplitter, QTextEdit,
                           QApplication, QWidget, QMenu,
                           Qt, QTimer, pyqtSignal, QColor,
                           QButtonGroup, QInputDialog, QComboBox, QFont,
                           QFrame, QSize, QCursor, QPalette, QSizePolicy,
                           QEvent, QPoint, QStackedWidget, QProgressBar)
from typing import List, Tuple, Dict
import qtawesome as qta

from ..core.config import Config
from ..utils.error_handler import handle_ui_errors
from ..core.logger import app_logger
from .pieces_list_service import PieceRelationsPopup, _parse_refs, _link_if_truncated, _format_piece_edit_history
from .piece_picker_dialog import PiecePickerDialog, RefTagList

class ActionButtonWidget(QWidget):
    """Widget contenant les boutons d'action (icônes sans fond) pour chaque ligne du tableau"""

    editRequested    = pyqtSignal(int)
    deleteRequested  = pyqtSignal(int)
    obsoleteRequested = pyqtSignal(int)

    def __init__(self, row_index: int, parent=None):
        super().__init__(parent)
        self.row_index = row_index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        # Bouton éditer — icône bleue, fond transparent
        edit_btn = QPushButton()
        edit_btn.setIcon(qta.icon('fa5s.edit', color='#1565C0'))
        edit_btn.setIconSize(QSize(13, 13))
        edit_btn.setFixedSize(22, 22)
        edit_btn.setFlat(True)
        edit_btn.setToolTip("Modifier cette pièce")
        edit_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; margin: 0; outline: none; }"
            "QPushButton:hover { border: none; background: rgba(21,101,192,0.12); border-radius: 3px; outline: none; padding: 0; }"
            "QPushButton:pressed { border: none; background: rgba(21,101,192,0.20); border-radius: 3px; }"
        )
        edit_btn.clicked.connect(lambda: self.editRequested.emit(self.row_index))
        layout.addWidget(edit_btn)

        # Bouton obsolète — icône orange, fond transparent
        obsolete_btn = QPushButton()
        obsolete_btn.setIcon(qta.icon('fa5s.ban', color='#e67e22'))
        obsolete_btn.setIconSize(QSize(13, 13))
        obsolete_btn.setFixedSize(22, 22)
        obsolete_btn.setFlat(True)
        obsolete_btn.setToolTip("Marquer obsolète / retirer l'obsolescence")
        obsolete_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; margin: 0; outline: none; }"
            "QPushButton:hover { border: none; background: rgba(230,126,34,0.12); border-radius: 3px; outline: none; padding: 0; }"
            "QPushButton:pressed { border: none; background: rgba(230,126,34,0.20); border-radius: 3px; }"
        )
        obsolete_btn.clicked.connect(lambda: self.obsoleteRequested.emit(self.row_index))
        layout.addWidget(obsolete_btn)

        # Bouton supprimer — icône rouge, fond transparent
        delete_btn = QPushButton()
        delete_btn.setIcon(qta.icon('fa5s.trash-alt', color='#c62828'))
        delete_btn.setIconSize(QSize(13, 13))
        delete_btn.setFixedSize(22, 22)
        delete_btn.setFlat(True)
        delete_btn.setToolTip("Supprimer cette pièce")
        delete_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; margin: 0; outline: none; }"
            "QPushButton:hover { border: none; background: rgba(198,40,40,0.12); border-radius: 3px; outline: none; padding: 0; }"
            "QPushButton:pressed { border: none; background: rgba(198,40,40,0.20); border-radius: 3px; }"
        )
        delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self.row_index))
        layout.addWidget(delete_btn)

class PiecesTableWidget(QTableWidget):
    """Table widget personnalisé avec curseur contextuel sur la colonne Statut"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.action_widgets = {}
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        
    def enterEvent(self, event):
        """Souris entre dans le widget"""
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Souris quitte le widget"""
        super().leaveEvent(event)
        # Masquer tous les boutons d'action
        for widget in self.action_widgets.values():
            widget.hide()
    
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
    
    def _show_action_buttons_for_row(self, row: int):
        """Afficher les boutons d'action pour une ligne - DÉSACTIVÉ"""
        # BOUTONS DE SURVOL SUPPRIMÉS - Méthode désactivée
        return
    
    def _on_edit_requested(self, row: int):
        """Signal émis quand édition demandée"""
        if hasattr(self.parent(), '_edit_piece_at_row'):
            self.parent()._edit_piece_at_row(row)
    
    def _on_delete_requested(self, row: int):
        """Signal émis quand suppression demandée"""
        if hasattr(self.parent(), '_delete_piece_at_row'):
            self.parent()._delete_piece_at_row(row)
    
    def setRowCount(self, rows: int):
        """Override pour nettoyer les widgets d'action"""
        super().setRowCount(rows)
        # Nettoyer les widgets obsolètes
        for row in list(self.action_widgets.keys()):
            if row >= rows:
                self.action_widgets[row].deleteLater()
                del self.action_widgets[row]

class PiecesManagerWindow(QDialog):
    """Fenêtre de gestion des pièces"""
    
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("Gestionnaire des pièces - 1001pieces.com")
        self.setModal(False)
        # Taille adaptée à l'écran disponible
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1300, screen.width() - 80), min(800, screen.height() - 80))
        
        self._init_ui()
        # Afficher la fenêtre d'abord, charger les données après le premier rendu
        QTimer.singleShot(50, self._load_pieces_data)
        
    def _init_ui(self):
        """Initialiser l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Titre et statistiques
        header_layout = QHBoxLayout()
        title_label = QLabel("Gestionnaire des Pièces")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        header_layout.addWidget(title_label)
        
        self.stats_label = QLabel("Chargement...")
        self.stats_label.setStyleSheet(f"color: {Config.Colors.TEXT_MUTED}; margin: 10px;")
        header_layout.addWidget(self.stats_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Barre de recherche
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Recherche :"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Référence ou libellé… (utiliser ; pour plusieurs refs)")
        self.search_input.setClearButtonEnabled(True)  # Bouton × natif intégré au champ
        self.search_input.textChanged.connect(self._filter_pieces)
        search_layout.addWidget(self.search_input)

        refresh_btn = QPushButton()
        refresh_btn.setIcon(qta.icon('fa5s.sync-alt', color='#555555'))
        refresh_btn.setIconSize(QSize(13, 13))
        refresh_btn.setFixedSize(26, 26)
        refresh_btn.setFlat(True)
        refresh_btn.setToolTip("Actualiser (F5)")
        refresh_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }"
        )
        refresh_btn.clicked.connect(self._load_pieces_data)
        search_layout.addWidget(refresh_btn)

        layout.addLayout(search_layout)

        # Barre de filtres rapides
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filtrer :"))

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._active_filter = 'all'

        _filter_defs = [
            ('all',        'Toutes',        'fa5s.list',                    '#495057'),
            ('orphan',     'Orphelines',    'fa5s.unlink',                  '#c0392b'),
            ('phantom',    'Fantômes',      'fa5s.ghost',                   '#7f8c8d'),
            ('superseded', 'Remplacées',    'fa5s.long-arrow-alt-right',    '#e67e22'),
            ('obsolete',   'Obsolètes',     'fa5s.exclamation-triangle',    '#e67e22'),
            ('replacing',  'Remplaçantes',  'fa5s.level-up-alt',            '#2980b9'),
            ('equivalent', 'Équivalentes',  'fa5s.exchange-alt',            '#8e44ad'),
            ('current',    'Courantes',     'fa5s.check-circle',            '#27ae60'),
        ]
        def _make_icon_toggle(b, iname, icolor):
            def _on_toggled(checked):
                b.setIcon(qta.icon(iname, color='white' if checked else icolor))
            return _on_toggled

        self._filter_btns = {}
        for i, (key, label, icon_name, icon_color) in enumerate(_filter_defs):
            btn = QPushButton(label)
            is_checked = (key == 'all')
            btn.setIcon(qta.icon(icon_name, color='white' if is_checked else icon_color))
            btn.setIconSize(QSize(11, 11))
            btn.setCheckable(True)
            btn.setChecked(is_checked)
            btn.setProperty('filter_key', key)
            btn.setStyleSheet("""
                QPushButton { padding: 2px 6px; font-size: 11px; }
                QPushButton:checked { background-color: #495057; color: white; border-radius: 3px; }
            """)
            btn.toggled.connect(_make_icon_toggle(btn, icon_name, icon_color))
            self._filter_group.addButton(btn, i)
            filter_layout.addWidget(btn)
            self._filter_btns[key] = btn

        self._filter_group.buttonClicked.connect(self._on_filter_changed)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Tableau des pièces
        self.pieces_table = PiecesTableWidget()
        self.pieces_table.setColumnCount(5)
        self.pieces_table.setHorizontalHeaderLabels([
            "Référence Pièce", "Libellé", "Nb", "Types d'Appareils", ""
        ])

        # Configuration du tableau — Libellé en stretch pour remplir la largeur disponible
        header = self.pieces_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Référence
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)      # Libellé (le plus large)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)        # Nb
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Types d'Appareils
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)        # Actions
        self.pieces_table.setColumnWidth(0, 140)   # Référence Pièce
        self.pieces_table.setColumnWidth(2, 65)    # Nb (6 chiffres minimum)
        self.pieces_table.setColumnWidth(3, 200)   # Types d'Appareils
        self.pieces_table.setColumnWidth(4, 84)    # Actions (3 boutons inline)

        self.pieces_table.setAlternatingRowColors(True)
        self.pieces_table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #e0e0e0;
                color: #212121;
            }
            QTableWidget::item:selected:focus {
                background-color: #d5d5d5;
                color: #212121;
            }
        """)
        self.pieces_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pieces_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.pieces_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pieces_table.itemSelectionChanged.connect(self._on_piece_selected)
        self.pieces_table.currentItemChanged.connect(lambda *_: self._on_piece_selected())
        self.pieces_table.itemDoubleClicked.connect(self._on_double_click_piece)

        # ── Layout principal : splitter table | panneau latéral ────────────────
        self.details_text = QTextEdit()  # conservé pour compatibilité interne

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # ── Gauche : tableau (avec écran de chargement initial) ──────────────
        self._table_stack = QStackedWidget()

        # Page 0 : spinner de chargement
        loading_page = QWidget()
        loading_layout = QVBoxLayout(loading_page)
        loading_layout.setAlignment(Qt.AlignCenter)
        loading_layout.setSpacing(16)

        # Spinner + titre en ligne horizontale
        spinner_row = QHBoxLayout()
        spinner_row.setAlignment(Qt.AlignCenter)
        spinner_row.setSpacing(10)
        spinner_btn = QPushButton()
        spinner_btn.setFlat(True)
        spinner_btn.setEnabled(False)
        spinner_btn.setFixedSize(28, 28)
        spinner_btn.setIconSize(QSize(22, 22))
        spinner_btn.setIcon(qta.icon('fa5s.circle-notch', color='#495057',
                                     animation=qta.Spin(spinner_btn)))
        spinner_btn.setStyleSheet("border: none; background: transparent;")
        spinner_row.addWidget(spinner_btn)
        title_lbl = QLabel("Chargement des pièces…")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #212529;")
        spinner_row.addWidget(title_lbl)
        loading_layout.addLayout(spinner_row)

        # Barre de progression fine indéterminée
        loading_bar = QProgressBar()
        loading_bar.setRange(0, 0)
        loading_bar.setTextVisible(False)
        loading_bar.setFixedHeight(6)
        loading_bar.setMaximumWidth(400)
        loading_bar.setStyleSheet("""
            QProgressBar { border: none; border-radius: 3px; background: #e9ecef; }
            QProgressBar::chunk { border-radius: 3px; background: #495057; }
        """)
        loading_layout.addWidget(loading_bar, 0, Qt.AlignHCenter)

        self._table_stack.addWidget(loading_page)    # index 0 : chargement
        self._table_stack.addWidget(self.pieces_table)  # index 1 : tableau
        self._table_stack.setCurrentIndex(0)

        main_splitter.addWidget(self._table_stack)

        # ── Droite : panneau de détail ────────────────────────────────────────
        side_panel = QWidget()
        side_panel.setMinimumWidth(280)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(6, 4, 4, 4)
        side_layout.setSpacing(6)

        # En-tête : référence sélectionnée
        self.panel_header_label = QLabel("—")
        self.panel_header_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2c3e50;"
            " padding: 4px 6px; background: #f8f9fa;"
            " border: 1px solid #dee2e6; border-radius: 4px;"
        )
        self.panel_header_label.setWordWrap(True)
        side_layout.addWidget(self.panel_header_label)

        # Label statut (héritage : met à jour le statut succession)
        self.succession_status_label = QLabel("Sélectionnez une pièce pour voir son statut.")
        self.succession_status_label.setStyleSheet("color: #555555; font-size: 11px;")
        self.succession_status_label.setWordWrap(True)
        side_layout.addWidget(self.succession_status_label)

        # ── 3 sections égales ─────────────────────────────────────────────────
        sections_splitter = QSplitter(Qt.Vertical)
        sections_splitter.setChildrenCollapsible(False)

        # Section "↳ Remplacée par"
        superseded_section = QFrame()
        superseded_section.setFrameShape(QFrame.StyledPanel)
        superseded_section.setObjectName("superseded_section")
        self.superseded_section = superseded_section
        sup_sec_layout = QVBoxLayout(superseded_section)
        sup_sec_layout.setContentsMargins(6, 4, 6, 4)
        sup_sec_layout.setSpacing(3)

        superseded_hdr = QHBoxLayout()
        lbl_sup = QLabel("↳ Remplacée par")
        lbl_sup.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 11px;")
        superseded_hdr.addWidget(lbl_sup)
        superseded_hdr.addStretch()
        self.btn_mark_superseded = QPushButton("+ Déclarer remplacée par…")
        self.btn_mark_superseded.setStyleSheet(
            "QPushButton { color: #e67e22; font-size: 11px; border: none; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        self.btn_mark_superseded.setFlat(True)
        self.btn_mark_superseded.clicked.connect(self._on_mark_superseded)
        superseded_hdr.addWidget(self.btn_mark_superseded)
        sup_sec_layout.addLayout(superseded_hdr)

        self.superseded_by_tag_list = RefTagList()
        self.superseded_by_tag_list.enable_full_height_mode()
        self.superseded_by_tag_list.ref_removed.connect(self._on_remove_superseded_by)
        sup_sec_layout.addWidget(self.superseded_by_tag_list, 1)
        sections_splitter.addWidget(superseded_section)

        # Section "↑ Remplace"
        replaces_section = QFrame()
        replaces_section.setFrameShape(QFrame.StyledPanel)
        self.replaces_section = replaces_section
        rep_sec_layout = QVBoxLayout(replaces_section)
        rep_sec_layout.setContentsMargins(6, 4, 6, 4)
        rep_sec_layout.setSpacing(3)

        replaces_hdr = QHBoxLayout()
        lbl_rep = QLabel("↑ Remplace")
        lbl_rep.setStyleSheet("color: #2980b9; font-weight: bold; font-size: 11px;")
        replaces_hdr.addWidget(lbl_rep)
        replaces_hdr.addStretch()
        self.btn_mark_replaces = QPushButton("+ Ajouter une référence remplacée…")
        self.btn_mark_replaces.setStyleSheet(
            "QPushButton { color: #2980b9; font-size: 11px; border: none; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        self.btn_mark_replaces.setFlat(True)
        self.btn_mark_replaces.clicked.connect(self._on_mark_replaces)
        replaces_hdr.addWidget(self.btn_mark_replaces)
        rep_sec_layout.addLayout(replaces_hdr)

        self.replaces_tag_list = RefTagList()
        self.replaces_tag_list.enable_full_height_mode()
        self.replaces_tag_list.ref_removed.connect(self._on_remove_replaces)
        rep_sec_layout.addWidget(self.replaces_tag_list, 1)
        sections_splitter.addWidget(replaces_section)

        # Section "≡ Équivalences"
        equiv_section = QFrame()
        equiv_section.setFrameShape(QFrame.StyledPanel)
        self.equiv_section = equiv_section
        eq_sec_layout = QVBoxLayout(equiv_section)
        eq_sec_layout.setContentsMargins(6, 4, 6, 4)
        eq_sec_layout.setSpacing(3)

        equiv_hdr = QHBoxLayout()
        lbl_eq = QLabel("≡ Équivalences")
        lbl_eq.setStyleSheet("color: #8e44ad; font-weight: bold; font-size: 11px;")
        equiv_hdr.addWidget(lbl_eq)
        equiv_hdr.addStretch()
        self.btn_link_equiv = QPushButton("+ Ajouter une équivalence…")
        self.btn_link_equiv.setStyleSheet(
            "QPushButton { color: #8e44ad; font-size: 11px; border: none; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        self.btn_link_equiv.setFlat(True)
        self.btn_link_equiv.setEnabled(False)
        self.btn_link_equiv.clicked.connect(self._on_link_equiv)
        equiv_hdr.addWidget(self.btn_link_equiv)
        eq_sec_layout.addLayout(equiv_hdr)

        self.equiv_status_label = QLabel("")
        self.equiv_status_label.setStyleSheet("color: #555555; font-size: 11px;")
        self.equiv_status_label.setWordWrap(True)
        self.equiv_status_label.setVisible(False)  # caché jusqu'au premier rafraîchissement
        eq_sec_layout.addWidget(self.equiv_status_label)

        self.equiv_tag_list = RefTagList()
        self.equiv_tag_list.enable_full_height_mode()
        self.equiv_tag_list.ref_removed.connect(self._on_remove_equiv)
        eq_sec_layout.addWidget(self.equiv_tag_list, 1)
        sections_splitter.addWidget(equiv_section)

        # succ_single_widget : wrapper fantôme gardé pour la compatibilité
        self.succ_single_widget = QWidget()
        self.succ_single_widget.setVisible(False)  # never shown, kept for compat

        side_layout.addWidget(sections_splitter, 1)

        # btn_mark_obsolete : conservé comme widget orphelin pour la compatibilité
        # avec _refresh_succession_panel (setEnabled / setText) — non affiché dans l'UI
        # (redondant avec le bouton inline dans chaque ligne du tableau)
        self.btn_mark_obsolete = QPushButton("Marquer obsolète")
        self.btn_mark_obsolete.setEnabled(False)
        self.btn_mark_obsolete.clicked.connect(self._on_mark_obsolete)

        # ── Ligne d'actions communes ──────────────────────────────────────────
        succ_action_row = QHBoxLayout()
        self.btn_cancel_succession = QPushButton("Annuler la succession")
        self.btn_cancel_succession.setToolTip("Supprimer tous les liens de succession pour les pièces sélectionnées")
        self.btn_cancel_succession.setEnabled(False)
        self.btn_cancel_succession.setStyleSheet("font-size: 11px;")
        self.btn_cancel_succession.clicked.connect(self._on_cancel_succession)
        self.btn_cancel_succession.setVisible(False)
        succ_action_row.addWidget(self.btn_cancel_succession)

        self.btn_unlink_equiv = QPushButton("Retirer du groupe")
        self.btn_unlink_equiv.setToolTip("Retirer la pièce sélectionnée de son groupe d'équivalence")
        self.btn_unlink_equiv.setEnabled(False)
        self.btn_unlink_equiv.setStyleSheet("QPushButton { color: #E05252; font-size: 11px; }")
        self.btn_unlink_equiv.setVisible(False)
        self.btn_unlink_equiv.clicked.connect(self._on_unlink_equiv)
        succ_action_row.addWidget(self.btn_unlink_equiv)

        succ_action_row.addStretch()
        side_layout.addLayout(succ_action_row)

        # Clic gauche sur une référence dans les fieldsets → recherche dans le gestionnaire
        self.superseded_by_tag_list.ref_clicked.connect(self._search_in_manager)
        self.replaces_tag_list.ref_clicked.connect(self._search_in_manager)
        self.equiv_tag_list.ref_clicked.connect(self._search_in_manager)
        # Clic droit → menu contextuel (copier / rechercher dans l'app principale)
        self.superseded_by_tag_list.ref_right_clicked.connect(self._on_chip_right_click)
        self.replaces_tag_list.ref_right_clicked.connect(self._on_chip_right_click)
        self.equiv_tag_list.ref_right_clicked.connect(self._on_chip_right_click)

        # Référence courante sélectionnée (pour les callbacks)
        self._current_ref_piece = None

        main_splitter.addWidget(side_panel)
        # Taille initiale : 70% tableau / 30% panneau latéral
        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)

        layout.addWidget(main_splitter, 1)

        # Boutons d'action
        _btn_style = (
            "QPushButton { padding: 3px 10px; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); }"
        )
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        search_app_btn = QPushButton("Chercher dans l'app")
        search_app_btn.setIcon(qta.icon('fa5s.search', color='#555555'))
        search_app_btn.setIconSize(QSize(12, 12))
        search_app_btn.setToolTip("Injecter la référence sélectionnée dans la recherche principale")
        search_app_btn.setStyleSheet(_btn_style)
        search_app_btn.clicked.connect(self._search_in_main_app)
        buttons_layout.addWidget(search_app_btn)

        export_btn = QPushButton("Exporter la liste")
        export_btn.setIcon(qta.icon('fa5s.file-export', color='#555555'))
        export_btn.setIconSize(QSize(12, 12))
        export_btn.setStyleSheet(_btn_style)
        export_btn.clicked.connect(self._export_pieces)
        buttons_layout.addWidget(export_btn)

        close_btn = QPushButton("Fermer")
        close_btn.setIcon(qta.icon('fa5s.times', color='#495057'))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setStyleSheet(_btn_style)
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # ── Widget d'actions flottant (un seul, positionné sur la ligne survolée) ──
        self._floating_actions = ActionButtonWidget(-1)
        self._floating_actions.setParent(self.pieces_table.viewport())
        self._floating_actions.setVisible(False)
        self._floating_actions.editRequested.connect(self._edit_piece_at_row)
        self._floating_actions.deleteRequested.connect(self._delete_at_row_or_selection)
        self._floating_actions.obsoleteRequested.connect(self._on_obsolete_at_row)

        self.pieces_table.setMouseTracking(True)
        self.pieces_table.viewport().setMouseTracking(True)
        self.pieces_table.cellEntered.connect(self._on_cell_entered)
        self.pieces_table.verticalScrollBar().valueChanged.connect(
            lambda: self._floating_actions.setVisible(False))
        self.pieces_table.viewport().installEventFilter(self)
        self._floating_actions.installEventFilter(self)
        
    @handle_ui_errors(log_prefix="Erreur chargement pièces", show_message=True)
    def _load_pieces_data(self, checked=False):
        """Phase 1 : chargement rapide (ref + libellé uniquement, sans jointures).
        Affiche la liste immédiatement, puis déclenche le chargement complet."""
        query_fast = """
        SELECT p.ref_piece, p.description, 0, NULL, COALESCE(p.is_phantom, 0)
        FROM pieces p
        ORDER BY p.ref_piece ASC
        """
        results = self.db_manager.execute_query(query_fast) or []
        self.all_pieces_data = results
        self.all_statuses = {}
        self.stats_label.setText(f"{len(results)} référence(s) — chargement des données…")
        self._update_table_display()
        # Phase 2 : données complètes après le premier rendu
        QTimer.singleShot(0, self._load_pieces_data_full)

    @handle_ui_errors(log_prefix="Erreur chargement complet pièces", show_message=True)
    def _load_pieces_data_full(self, checked=False):
        """Phase 2 : chargement complet avec comptages, types et statuts de succession."""
        query = """
        SELECT
            p.ref_piece,
            p.description,
            COUNT(DISTINCT pa.appareil_id) as nb_appareils,
            GROUP_CONCAT(DISTINCT a.type) as types_appareils,
            COALESCE(p.is_phantom, 0) as is_phantom
        FROM pieces p
        LEFT JOIN piece_associations pa ON p.id = pa.piece_id
        LEFT JOIN appareils a ON pa.appareil_id = a.id
        GROUP BY p.id, p.ref_piece, p.description, p.is_phantom
        ORDER BY nb_appareils DESC, p.ref_piece ASC
        """
        results = self.db_manager.execute_query(query) or []

        total_pieces = len(results)
        orphan_pieces = len([r for r in results if r[2] == 0])
        phantom_pieces = len([r for r in results if r[4] == 1])
        total_associations = sum(r[2] for r in results)

        from src.core.config import pluralize
        phantom_str = f"  •  {pluralize(phantom_pieces, 'fantôme')}" if phantom_pieces else ""
        self.stats_label.setText(
            f"{pluralize(total_pieces, 'référence')}  •  "
            f"{pluralize(orphan_pieces, 'orpheline')}"
            f"{phantom_str}  •  "
            f"{pluralize(total_associations, 'association')}"
        )

        self.all_pieces_data = results
        all_refs = [r[0] for r in results if r[0]]
        self.all_statuses = self.db_manager.get_pieces_statuses_batch(all_refs)
        self._update_table_display()

    # ── Widget d'actions flottant ─────────────────────────────────────────────

    def _on_cell_entered(self, row: int, col: int):
        """Positionner le widget d'actions flottant sur la ligne survolée."""
        idx = self.pieces_table.model().index(row, 4)
        rect = self.pieces_table.visualRect(idx)
        self._floating_actions.row_index = row
        self._floating_actions.move(rect.topLeft())
        self._floating_actions.setFixedSize(rect.width(), rect.height())
        self._floating_actions.setVisible(True)
        self._floating_actions.raise_()

    def eventFilter(self, obj, event):
        """Gérer le survol entre le tableau et le widget d'actions flottant."""
        if obj is self.pieces_table.viewport() and event.type() == QEvent.Leave:
            # Cacher le widget flottant seulement si le curseur ne se trouve pas dessus
            cursor_pos = self.pieces_table.viewport().mapFromGlobal(QCursor.pos())
            if not self._floating_actions.geometry().contains(cursor_pos):
                self._floating_actions.setVisible(False)
        elif obj is self._floating_actions and event.type() == QEvent.Leave:
            self._floating_actions.setVisible(False)
        return super().eventFilter(obj, event)

    def _update_table_display(self):
        """Mettre à jour l'affichage du tableau avec filtrage.
        Les signaux sont bloqués pendant la reconstruction pour éviter que
        setRowCount() ne déclenche itemSelectionChanged → sections cachées."""
        # Remplacer l'écran de chargement par le tableau au premier appel
        if hasattr(self, '_table_stack') and self._table_stack.currentIndex() == 0:
            self._table_stack.setCurrentIndex(1)

        filtered_data = self._get_filtered_data()
        if hasattr(self, '_floating_actions'):
            self._floating_actions.setVisible(False)
        self.pieces_table.blockSignals(True)
        self.pieces_table.setRowCount(len(filtered_data))
        statuses = getattr(self, 'all_statuses', {})

        from src.core.config import pluralize
        _phantom_font = QFont()
        _phantom_font.setItalic(True)
        _phantom_color = QColor(170, 170, 170)

        for row_idx, row_data in enumerate(filtered_data):
            ref_piece    = row_data[0]
            description  = row_data[1]
            nb_appareils = row_data[2]
            types_appareils = row_data[3]
            is_phantom   = row_data[4] if len(row_data) > 4 else 0

            status_info = statuses.get(ref_piece or '', {'status': 'current', 'ref_new': None, 'refs_old': None})
            status = status_info.get('status', 'current')
            is_obsolete = status_info.get('is_obsolete', False)

            # ── Colonne 0 : référence (plain, fantôme en gris italique) ────
            ref_item = QTableWidgetItem(ref_piece or "")
            ref_item.setData(Qt.UserRole, ref_piece or "")
            if is_phantom:
                ref_item.setForeground(_phantom_color)
                ref_item.setFont(_phantom_font)
                ref_item.setToolTip("Référence fantôme — créée automatiquement pour la succession")
            self.pieces_table.setItem(row_idx, 0, ref_item)

            # ── Colonne 1 : libellé ───────────────────────────────────────
            desc_item = QTableWidgetItem(description or "")
            desc_item.setToolTip(description or "Pas de libellé")
            if is_phantom:
                desc_item.setForeground(_phantom_color)
                desc_item.setFont(_phantom_font)
            self.pieces_table.setItem(row_idx, 1, desc_item)

            # ── Colonne 2 : nb appareils (fond coloré) ────────────────────
            nb_item = QTableWidgetItem(str(nb_appareils))
            nb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if nb_appareils == 0:
                nb_item.setBackground(QColor(*Config.Colors.ORPHAN_ROW))
                nb_item.setToolTip("Pièce orpheline — aucun appareil associé")
            elif nb_appareils == 1:
                nb_item.setBackground(QColor(*Config.Colors.SINGLE_PIECE))
                nb_item.setToolTip("Pièce associée à un seul appareil")
            else:
                nb_item.setBackground(QColor(*Config.Colors.MULTI_PIECES))
                nb_item.setToolTip(f"Pièce associée à {pluralize(nb_appareils, 'appareil')}")
            self.pieces_table.setItem(row_idx, 2, nb_item)

            # ── Colonne 3 : types d'appareils — espace après les virgules ──
            types_display = (types_appareils or "—").replace(",", ", ")
            if len(types_display) > 55:
                types_display = types_display[:52] + "…"
            types_item = QTableWidgetItem(types_display)
            types_item.setToolTip((types_appareils or "Aucun type").replace(",", ", "))
            self.pieces_table.setItem(row_idx, 3, types_item)

            # Colonne 4 : actions gérées par le widget flottant (_floating_actions)

        self.pieces_table.blockSignals(False)

        # Restaurer la sélection et les panneaux si la pièce courante est toujours visible
        # selectRow() est utilisé (pas setCurrentCell) car en ExtendedSelection,
        # setCurrentCell ne sélectionne pas réellement la ligne → selectedIndexes() resterait
        # vide → has_selection = False → sections du panneau cachées à tort.
        ref = getattr(self, '_current_ref_piece', None)
        if ref:
            for row in range(self.pieces_table.rowCount()):
                item = self.pieces_table.item(row, 0)
                if item and (item.data(Qt.UserRole) or item.text()) == ref:
                    self.pieces_table.selectRow(row)
                    break
            self._refresh_succession_panel(ref)
            self._refresh_equivalence_panel(ref)
            
    def _get_filtered_data(self):
        """Obtenir les données filtrées selon les critères"""
        if not hasattr(self, 'all_pieces_data'):
            return []

        filtered = self.all_pieces_data

        # Filtre texte (référence + libellé) — supporte && pour multi-refs
        search_text = self.search_input.text().lower().strip()
        if search_text:
            if ';' in search_text:
                parts = [p.strip() for p in search_text.split(';') if p.strip()]
                filtered = [r for r in filtered
                            if any(p in (r[0] or "").lower() or p in (r[1] or "").lower()
                                   for p in parts)]
            else:
                filtered = [r for r in filtered
                            if search_text in (r[0] or "").lower()
                            or search_text in (r[1] or "").lower()]

        # Filtre actif
        active = getattr(self, '_active_filter', 'all')
        statuses = getattr(self, 'all_statuses', {})

        if active == 'orphan':
            filtered = [r for r in filtered if r[2] == 0]
        elif active == 'phantom':
            filtered = [r for r in filtered if (len(r) > 4 and r[4] == 1)]
        elif active == 'superseded':
            filtered = [r for r in filtered
                        if statuses.get(r[0] or '', {}).get('status') == 'superseded']
        elif active == 'obsolete':
            filtered = [r for r in filtered
                        if statuses.get(r[0] or '', {}).get('is_obsolete')]
        elif active == 'replacing':
            filtered = [r for r in filtered
                        if statuses.get(r[0] or '', {}).get('status') == 'replacing']
        elif active == 'equivalent':
            filtered = [r for r in filtered
                        if statuses.get(r[0] or '', {}).get('equivalents')]
        elif active == 'current':
            filtered = [r for r in filtered
                        if (statuses.get(r[0] or '', {}).get('status') == 'current'
                            and not statuses.get(r[0] or '', {}).get('is_obsolete')
                            and not (len(r) > 4 and r[4] == 1))]

        return filtered
        
    def _filter_pieces(self):
        """Filtrer les pièces selon les critères"""
        self._update_table_display()

    def _on_filter_changed(self, btn):
        """Changer le filtre actif via les boutons rapides."""
        self._active_filter = btn.property('filter_key')
        self._update_table_display()

    def _on_double_click_piece(self, item):
        """Double-clic sur une ligne → édition immédiate."""
        self._edit_selected_piece()

    def _search_in_main_app(self):
        """Injecter la référence sélectionnée dans le champ de recherche principal."""
        current_row = self.pieces_table.currentRow()
        if current_row < 0:
            return
        ref_item = self.pieces_table.item(current_row, 0)
        if not ref_item:
            return
        ref = ref_item.data(Qt.UserRole) or ref_item.text()
        self._inject_ref_in_search(ref)

    def _make_status_cell_widget(self, row_idx: int, prefix: str, refs: list,
                                  color: str, ref_piece: str, status_info: dict) -> QLabel:
        """Créer un QLabel avec refs cliquables pour la colonne Statut.
        Soulignement dynamique via linkHovered (le survol souligne uniquement la ref survolée).
        Clic = copie dans le presse-papier + injection dans la recherche principale."""
        MAX_INLINE = 2

        # Couleur de fond alternée (correspondant aux lignes du tableau)
        palette = self.pieces_table.palette()
        bg = (palette.color(QPalette.AlternateBase).name()
              if row_idx % 2 == 1
              else palette.color(QPalette.Base).name())

        lbl = QLabel()
        lbl.setStyleSheet(f"background: {bg}; padding: 2px 6px; border: none;")
        lbl.setTextFormat(Qt.RichText)
        lbl.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        refs_shown = refs[:MAX_INLINE]
        n_more     = len(refs) - MAX_INLINE if len(refs) > MAX_INLINE else 0

        def _build_html(hovered_href: str = ''):
            parts = []
            for r in refs_shown:
                deco = 'underline' if f'ref://{r}' == hovered_href else 'none'
                parts.append(
                    f"<a href='ref://{r}' style='color:{color};font-weight:bold;"
                    f"font-size:11px;text-decoration:{deco};'>{r}</a>")
            refs_html = ' '.join(parts)
            popup_html = ''
            if n_more:
                popup_html = (f" <a href='#popup' style='color:{color};font-size:10px;"
                              f"text-decoration:none;border-bottom:1px dashed {color};'>"
                              f"… +{n_more}</a>")
            return (f"<span style='color:{color};font-size:11px;'>{prefix}</span>"
                    f" {refs_html}{popup_html}")

        _last_hovered = ['']  # conteneur mutable pour la closure

        lbl.setText(_build_html())

        def _on_hover(href: str):
            _last_hovered[0] = href
            lbl.setText(_build_html(href))

        def _on_link(href: str, _rp=ref_piece, _si=status_info):
            if href.startswith('ref://'):
                self._search_in_manager(href[6:])
            elif href == '#popup':
                popup = PieceRelationsPopup(_rp, _si, self)
                popup.show_at_cursor()

        def _show_context_menu(pos):
            """Clic droit : copier la référence ou rechercher dans l'app."""
            menu = QMenu(lbl)
            hovered_ref = (_last_hovered[0][6:]
                           if _last_hovered[0].startswith('ref://') else None)
            targets = [hovered_ref] if hovered_ref else refs_shown
            for r in targets:
                copy_action = menu.addAction(f"Copier  {r}")
                copy_action.triggered.connect(
                    lambda checked, _r=r: QApplication.clipboard().setText(_r))
                search_action = menu.addAction(f"Rechercher dans l'app  {r}")
                search_action.triggered.connect(
                    lambda checked, _r=r: self._inject_ref_in_search(_r))
            menu.exec_(lbl.mapToGlobal(pos))

        lbl.setContextMenuPolicy(Qt.CustomContextMenu)
        lbl.customContextMenuRequested.connect(_show_context_menu)
        lbl.linkHovered.connect(_on_hover)
        lbl.linkActivated.connect(_on_link)
        return lbl

    def _search_in_manager(self, ref: str):
        """Injecter une référence dans le champ de recherche du gestionnaire.
        Réinitialise les filtres rapides pour s'assurer que la pièce est visible,
        puis sélectionne automatiquement la ligne correspondante."""
        # Réinitialiser le filtre actif → "Toutes" pour garantir la visibilité de la pièce
        self._active_filter = 'all'
        if hasattr(self, '_filter_btns'):
            self._filter_btns['all'].setChecked(True)
        self.search_input.setText(ref)
        self.search_input.setFocus()
        # La table est déjà repeuplée (textChanged synchrone) — chercher la ligne exacte
        # selectRow() pour garantir que selectedIndexes() soit non-vide (voir _refresh_succession_panel)
        for row in range(self.pieces_table.rowCount()):
            item = self.pieces_table.item(row, 0)
            if item and (item.data(Qt.UserRole) or item.text()) == ref:
                self.pieces_table.selectRow(row)
                self.pieces_table.scrollToItem(item)
                break

    def _inject_ref_in_search(self, ref: str):
        """Injecter la référence dans la recherche principale (fenêtre principale de l'app)."""
        parent = self.parent()
        if parent and hasattr(parent, 'search_input'):
            parent.search_input.setText(ref)
            parent.search_input.setFocus()
            parent.activateWindow()

    def _on_chip_right_click(self, ref: str):
        """Clic droit sur un chip de fieldset : copier ou rechercher dans l'app."""
        menu = QMenu(self)
        copy_action = menu.addAction(f"Copier  {ref}")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(ref))
        search_action = menu.addAction(f"Rechercher dans l'app  {ref}")
        search_action.triggered.connect(lambda: self._inject_ref_in_search(ref))
        menu.exec_(QCursor.pos())


    def _delete_at_row_or_selection(self, row: int):
        """Supprimer la pièce à la ligne, ou toute la sélection si la ligne en fait partie."""
        selected_rows = list(set([item.row() for item in self.pieces_table.selectedItems()]))
        if len(selected_rows) > 1 and row in selected_rows:
            self._delete_selected_pieces()
        else:
            self._delete_piece_at_row(row)

    def _on_obsolete_at_row(self, row: int):
        """Marquer/retirer l'obsolescence pour la pièce à la ligne donnée."""
        item = self.pieces_table.item(row, 0)
        if not item:
            return
        ref = item.data(Qt.UserRole) or item.text()
        self.pieces_table.setCurrentCell(row, 0)
        self._on_mark_obsolete()

    def _on_piece_selected(self):
        """Quand une pièce est sélectionnée"""
        current_row = self.pieces_table.currentRow()
        if current_row < 0:
            self.details_text.clear()
            self._current_ref_piece = None
            self.panel_header_label.setText("—")
            self._refresh_succession_panel(None)
            self._refresh_equivalence_panel(None)
            return

        ref_item = self.pieces_table.item(current_row, 0)
        if not ref_item:
            return

        ref_piece = ref_item.data(Qt.UserRole) or ref_item.text()
        self._current_ref_piece = ref_piece
        self._update_panel_header(ref_piece)
        self._load_piece_details(ref_piece)
        self._refresh_succession_panel(ref_piece)
        self._refresh_equivalence_panel(ref_piece)

    def _update_panel_header(self, ref_piece: str):
        """Mettre à jour l'en-tête du panneau latéral avec la pièce sélectionnée."""
        if not ref_piece:
            self.panel_header_label.setText("—")
            return
        desc = ""
        for row in getattr(self, 'all_pieces_data', []):
            if row[0] == ref_piece:
                desc = row[1] or ""
                break
        if desc:
            self.panel_header_label.setText(f"{ref_piece}  ·  {desc}")
        else:
            self.panel_header_label.setText(ref_piece)
        
    @handle_ui_errors(log_prefix="Erreur chargement détails pièce", show_message=False)
    def _load_piece_details(self, ref_piece):
        """Charger les détails d'une pièce"""
        query = """
        SELECT
            a.id,
            a.type,
            a.manufacturer,
            a.ref_modele,
            a.commercial_ref,
            a.other_ref
        FROM pieces p
        JOIN piece_associations pa ON p.id = pa.piece_id
        JOIN appareils a ON pa.appareil_id = a.id
        WHERE p.ref_piece = ?
        ORDER BY a.type, a.manufacturer, a.ref_modele
        """

        results = self.db_manager.execute_query(query, [ref_piece])

        if not results:
            self.details_text.setText(f"ATTENTION: Aucun appareil associé à la pièce '{ref_piece}'")
            return

        from src.core.config import pluralize
        details = f"Détails de la pièce '{ref_piece}' ({pluralize(len(results), 'appareil')}):\n\n"

        for appareil in results:
            details += f"• ID {appareil[0]}: {appareil[1] or 'N/A'} | "
            details += f"{appareil[2] or 'N/A'} | "
            details += f"Modèle: {appareil[3] or 'N/A'} | "
            details += f"Commercial: {appareil[4] or 'N/A'}"
            if appareil[5]:
                details += f" | Autre: {appareil[5]}"
            details += "\n"

        self.details_text.setText(details)
            
    # ── Succession ──────────────────────────────────────────────────────────

    def _get_selected_refs(self) -> list:
        """Retourner la liste des refs de toutes les lignes sélectionnées."""
        rows = sorted({idx.row() for idx in self.pieces_table.selectedIndexes()})
        refs = []
        for row in rows:
            item = self.pieces_table.item(row, 0)
            if item:
                refs.append(item.data(Qt.UserRole) or item.text())
        return refs

    def _refresh_succession_panel(self, ref_piece):
        """Mettre à jour le panneau Succession pour la pièce courante (dernière sélectionnée)."""
        selected = self._get_selected_refs()
        n = len(selected)
        has_selection = n > 0

        self.btn_mark_obsolete.setEnabled(has_selection)

        # ── Aucune sélection ──────────────────────────────────────────────
        if not has_selection or ref_piece is None:
            self.succession_status_label.setText("Sélectionnez une pièce pour voir son statut.")
            self.succession_status_label.setStyleSheet("color: #555555; font-size: 12px;")
            self.superseded_section.setVisible(False)
            self.replaces_section.setVisible(False)
            self.btn_cancel_succession.setVisible(False)
            self.btn_cancel_succession.setEnabled(False)
            return

        # ── Multi-sélection : boutons batch, pas de chips ─────────────────
        if n > 1:
            self.succession_status_label.setText(
                f"{n} pièces sélectionnées — les actions s'appliquent à toutes.")
            self.succession_status_label.setStyleSheet("color: #555555; font-size: 12px;")
            self.superseded_section.setVisible(False)
            self.replaces_section.setVisible(False)
            self.btn_mark_superseded.setEnabled(True)
            self.btn_mark_replaces.setEnabled(True)
            self.btn_cancel_succession.setVisible(True)
            self.btn_cancel_succession.setEnabled(True)
            return

        # ── Sélection unique : chips ──────────────────────────────────────
        status_info = self.db_manager.get_piece_status(ref_piece)
        status      = status_info['status']
        is_obsolete = status_info['is_obsolete']
        ref_new     = status_info.get('ref_new')
        predecessors = self.db_manager.get_all_predecessors(ref_piece)
        equivalents  = self.db_manager.get_equivalents(ref_piece)

        self.btn_mark_obsolete.setText("Retirer l'obsolescence" if is_obsolete else "Marquer obsolète")

        # Chip "Remplacée par" (0 ou 1)
        if ref_new:
            self.superseded_by_tag_list.set_refs([ref_new], '#e67e22')
        else:
            self.superseded_by_tag_list.set_refs([], '#e67e22')

        # Chips "Remplace"
        if predecessors:
            self.replaces_tag_list.set_refs(predecessors, '#2980b9')
        else:
            self.replaces_tag_list.set_refs([], '#2980b9')

        # Message d'état (obsolète ou rien)
        if is_obsolete:
            self.succession_status_label.setText("⚠ Obsolète")
            self.succession_status_label.setStyleSheet(
                "color: #c0392b; font-size: 12px; font-weight: bold;")
        elif not ref_new and not predecessors:
            self.succession_status_label.setText("✓ Référence courante")
            self.succession_status_label.setStyleSheet(
                "color: #34A853; font-size: 12px; font-weight: bold;")
        else:
            self.succession_status_label.setText("")

        # Stocker pour la popup relations
        self._relations_popup_data = {
            'status': status, 'ref_new': ref_new, 'is_obsolete': is_obsolete,
            'refs_old': ", ".join(predecessors) if predecessors else None,
            'equivalents': ", ".join(equivalents) if equivalents else None,
        }

        self.superseded_section.setVisible(True)
        self.replaces_section.setVisible(True)
        self.btn_cancel_succession.setVisible(False)  # chips suffisent en mono-sélection

    def _on_mark_superseded(self):
        """Déclarer que les pièces sélectionnées sont remplacées par une autre."""
        refs = self._get_selected_refs()
        if not refs:
            return

        label = f"'{refs[0]}'" if len(refs) == 1 else f"{len(refs)} pièces sélectionnées"
        exclude = refs[0] if len(refs) == 1 else None
        dlg = PiecePickerDialog(
            self.db_manager, self,
            exclude_ref=exclude,
            title=f"Référence qui remplace {label}"
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        ref_new = dlg.selected_ref()
        if not ref_new:
            return

        errors = []
        details_lines = []
        for ref_old in refs:
            success, error = self.db_manager.add_supersession(ref_old, ref_new)
            if success:
                details_lines.append(f"==> '{ref_old}' → '{ref_new}'")
            else:
                errors.append(f"{ref_old} : {error}")

        if details_lines:
            self._notify_history("Succession :\n" + "\n".join(details_lines))
            self._refresh_succession_panel(self._current_ref_piece)
            self._update_table_display()
        if errors:
            QMessageBox.warning(self, "Erreurs de succession", "\n".join(errors))

    def _on_mark_replaces(self):
        """Déclarer qu'une autre référence est remplacée par la pièce courante (ou les pièces sélectionnées)."""
        refs = self._get_selected_refs()
        if not refs:
            return

        label = f"'{refs[0]}'" if len(refs) == 1 else f"{len(refs)} pièces sélectionnées"
        dlg = PiecePickerDialog(
            self.db_manager, self,
            exclude_ref=refs[0] if len(refs) == 1 else None,
            title=f"Référence(s) remplacée(s) par {label}",
            multi_select=True
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        refs_old = dlg.selected_refs()
        if not refs_old:
            return

        errors = []
        details_lines = []
        for ref_old in refs_old:
            for ref_new in refs:
                success, error = self.db_manager.add_supersession(ref_old, ref_new)
                if success:
                    details_lines.append(f"==> '{ref_old}' → '{ref_new}'")
                else:
                    errors.append(f"{ref_old} → {ref_new} : {error}")

        if details_lines:
            self._notify_history("Succession :\n" + "\n".join(details_lines))
            self._refresh_succession_panel(self._current_ref_piece)
            self._update_table_display()
        if errors:
            QMessageBox.warning(self, "Erreurs de succession", "\n".join(errors))

    def _show_relations_popup(self):
        """Afficher la popup de synthèse des relations pour la pièce courante."""
        ref = self._current_ref_piece
        if not ref:
            return
        data = getattr(self, '_relations_popup_data', {})
        self._active_popup = PieceRelationsPopup(ref, data, self)
        self._active_popup.show_at_cursor()

    def _on_mark_obsolete(self):
        """Marquer les pièces sélectionnées comme obsolètes."""
        refs = self._get_selected_refs()
        if not refs:
            return

        # Construire la liste des appareils concernés
        appareils_lines = []
        for ref in refs:
            appareils = self.db_manager.get_appareils_for_piece_ref(ref)
            if appareils:
                if len(refs) > 1:
                    appareils_lines.append(f"\n{ref} :")
                for type_, mfr, ref_mod in appareils[:10]:
                    appareils_lines.append(f"  • {mfr or '?'} {ref_mod or '?'} ({type_ or '?'})")
                if len(appareils) > 10:
                    appareils_lines.append(f"  … et {len(appareils) - 10} autre(s)")

        label = f"'{refs[0]}'" if len(refs) == 1 else f"{len(refs)} pièces sélectionnées"
        msg = f"Marquer {label} comme obsolète(s) (aucun remplacement) ?"
        if appareils_lines:
            msg += "\n\nAppareils concernés :" + "\n".join(appareils_lines)

        confirm = QMessageBox.question(
            self,
            "Marquer comme obsolète",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Détecter si toutes les refs sélectionnées sont déjà obsolètes (toggle)
        all_obsolete = all(
            self.db_manager.get_piece_status(ref)['is_obsolete'] for ref in refs
        )
        details_lines = []
        errors = []
        for ref in refs:
            if all_obsolete:
                ok = self.db_manager.unmark_obsolete(ref)
                label = f"==> '{ref}' → plus obsolète"
            else:
                ok = self.db_manager.mark_obsolete(ref)
                label = f"==> '{ref}' → obsolète"
            if ok:
                details_lines.append(label)
            else:
                errors.append(f"{ref} : échec")

        if details_lines:
            self._notify_history("Succession :\n" + "\n".join(details_lines))
            self._refresh_succession_panel(self._current_ref_piece)
            self._update_table_display()
        if errors:
            QMessageBox.warning(self, "Erreur", "\n".join(errors))

    def _on_cancel_succession(self):
        """Annuler la relation de succession pour les pièces sélectionnées."""
        refs = self._get_selected_refs()
        if not refs:
            return

        label = f"'{refs[0]}'" if len(refs) == 1 else f"{len(refs)} pièces"
        confirm = QMessageBox.question(
            self,
            "Annuler la succession",
            f"Supprimer le lien de succession pour {label} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        details_lines = []
        for ref in refs:
            self.db_manager.remove_supersession(ref)
            details_lines.append(f"==> '{ref}' → (succession annulée)")

        if details_lines:
            self._notify_history("Succession :\n" + "\n".join(details_lines))
            self._refresh_succession_panel(self._current_ref_piece)
            self._update_table_display()

    # ── Équivalences ────────────────────────────────────────────────────────

    def _refresh_equivalence_panel(self, ref_piece):
        """Mettre à jour le panneau Équivalences pour la pièce courante."""
        selected = self._get_selected_refs()
        n = len(selected)
        has_selection = n > 0

        self.btn_link_equiv.setEnabled(has_selection)

        # ── Aucune sélection ──────────────────────────────────────────────
        if not has_selection or ref_piece is None:
            self.equiv_status_label.setText("Sélectionnez une pièce pour voir ses équivalences.")
            self.equiv_status_label.setStyleSheet("color: #555555; font-size: 12px;")
            self.equiv_status_label.setVisible(True)
            self.equiv_tag_list.set_refs([])
            self.btn_unlink_equiv.setVisible(False)
            return

        # ── Multi-sélection ────────────────────────────────────────────────
        if n > 1:
            self.equiv_status_label.setText(f"{n} pièces sélectionnées.")
            self.equiv_status_label.setStyleSheet("color: #555555; font-size: 12px;")
            self.equiv_status_label.setVisible(True)
            self.equiv_tag_list.set_refs([])
            self.btn_unlink_equiv.setVisible(True)
            self.btn_unlink_equiv.setEnabled(True)
            return

        # ── Sélection unique : chips ──────────────────────────────────────
        equivs = self.db_manager.get_equivalents(ref_piece)
        if equivs:
            self.equiv_tag_list.set_refs(equivs, '#8e44ad')
            self.equiv_status_label.setText("")
            self.equiv_status_label.setVisible(False)
            # Stocker pour la popup relations
            if hasattr(self, '_relations_popup_data'):
                self._relations_popup_data['equivalents'] = ", ".join(equivs)
            self.btn_unlink_equiv.setVisible(False)
        else:
            self.equiv_tag_list.set_refs([])
            self.equiv_status_label.setText("")
            self.equiv_status_label.setVisible(False)
            self.btn_unlink_equiv.setVisible(False)

    def _on_link_equiv(self):
        """Lier la pièce courante à une référence équivalente (via PiecePickerDialog)."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return
        dlg = PiecePickerDialog(
            self.db_manager, self,
            exclude_ref=ref_piece,
            title=f"Référence(s) équivalente(s) à '{ref_piece}'",
            multi_select=True
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        refs_b = dlg.selected_refs()
        if not refs_b:
            return
        errors = []
        details_lines = []
        for ref_b in refs_b:
            success = self.db_manager.add_equivalence(ref_piece, ref_b)
            if success:
                details_lines.append(f"==> '{ref_piece}' ≡ '{ref_b}'")
            else:
                errors.append(f"Impossible de créer l'équivalence pour : {ref_b}")
        if details_lines:
            self._notify_history("Équivalence :\n" + "\n".join(details_lines))
            self._refresh_equivalence_panel(ref_piece)
            self._update_table_display()
        if errors:
            QMessageBox.warning(self, "Erreur", "\n".join(errors))

    def _on_unlink_equiv(self):
        """Retirer la pièce courante de son groupe d'équivalence (multi-sélection)."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return
        confirm = QMessageBox.question(
            self, "Retirer du groupe",
            f"Retirer '{ref_piece}' de son groupe d'équivalence ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.db_manager.remove_equivalence(ref_piece)
        self._notify_history(f"Équivalence :\n==> '{ref_piece}' → (retiré du groupe)")
        self._refresh_equivalence_panel(ref_piece)
        self._update_table_display()

    def _on_remove_superseded_by(self, ref_new: str):
        """Supprimer le lien 'Remplacée par ref_new' pour la pièce courante (chip ×)."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return
        self.db_manager.remove_supersession(ref_piece)
        self._notify_history(f"Succession :\n==> '{ref_piece}' → (succession annulée)")
        self._refresh_succession_panel(ref_piece)
        self._update_table_display()

    def _on_remove_replaces(self, ref_old: str):
        """Supprimer le lien 'ref_old est remplacée par pièce courante' (chip ×)."""
        if not ref_old:
            return
        self.db_manager.remove_supersession(ref_old)
        self._notify_history(f"Succession :\n==> '{ref_old}' → (succession annulée)")
        self._refresh_succession_panel(self._current_ref_piece)
        self._update_table_display()

    def _on_remove_equiv(self, equiv_ref: str):
        """Retirer un membre spécifique du groupe d'équivalence (chip ×)."""
        if not equiv_ref:
            return
        self.db_manager.remove_equivalence(equiv_ref)
        self._notify_history(f"Équivalence :\n==> '{equiv_ref}' → (retiré du groupe)")
        self._refresh_equivalence_panel(self._current_ref_piece)
        self._update_table_display()

    def _notify_history(self, message: str):
        """Envoyer un message à l'historique principal si disponible."""
        try:
            parent = self.parent()
            if parent and hasattr(parent, 'user_interaction_service'):
                parent.user_interaction_service.add_to_history(message)
        except Exception:
            pass

    @handle_ui_errors(log_prefix="Erreur export pièces", show_message=True)
    def _export_pieces(self, checked=False):
        """Exporter la liste des pièces"""
        from .qt_imports import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self, "Exporter les pièces", "pieces_everyParts.csv",
            "Fichiers CSV (*.csv)"
        )

        if filename:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(['Référence Pièce', 'Libellé', 'Nb Appareils', "Types d'Appareils"])

                filtered_data = self._get_filtered_data()
                for row in filtered_data:
                    ref_piece, description, nb_appareils, types_appareils = row[0], row[1], row[2], row[3]
                    writer.writerow([ref_piece, description, nb_appareils, types_appareils or ""])

            QMessageBox.information(self, "Export réussi", f"Liste exportée vers:\n{filename}")
    
    def _do_delete_piece(self, ref_piece: str):
        """Suppression effective d'une pièce : associations puis pièce (sans commit — l'appelant commite)."""
        self.db_manager.cursor.execute(
            "DELETE FROM piece_associations WHERE piece_id IN (SELECT id FROM pieces WHERE ref_piece = ?)",
            [ref_piece]
        )
        self.db_manager.cursor.execute(
            "DELETE FROM pieces WHERE ref_piece = ?",
            [ref_piece]
        )

    @handle_ui_errors(log_prefix="Erreur suppression pièces", show_message=True)
    def _delete_selected_pieces(self, checked=False):
        """Supprimer les références de pièces sélectionnées"""
        selected_rows = list(set([item.row() for item in self.pieces_table.selectedItems()]))

        if not selected_rows:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner au moins une référence de pièce à supprimer.")
            return

        # Collecter les informations des pièces sélectionnées
        pieces_to_delete = []
        total_associations = 0

        for row in selected_rows:
            ref_item = self.pieces_table.item(row, 0)
            nb_item = self.pieces_table.item(row, 2)  # Colonne 2 pour le nombre d'appareils
            if ref_item and nb_item:
                ref_piece = ref_item.data(Qt.UserRole) or ref_item.text()
                nb_appareils = int(nb_item.text())
                pieces_to_delete.append((ref_piece, nb_appareils))
                total_associations += nb_appareils

        if not pieces_to_delete:
            return

        # Confirmation
        from src.core.config import pluralize
        if len(pieces_to_delete) == 1:
            ref_piece, nb_appareils = pieces_to_delete[0]
            message = f"Supprimer la référence de pièce '{ref_piece}' ?\n\n"
            if nb_appareils > 0:
                message += f"ATTENTION: Cette pièce est associée à {pluralize(nb_appareils, 'appareil')}.\n"
                message += "Toutes les associations seront supprimées.\n\n"
        else:
            message = f"Supprimer {pluralize(len(pieces_to_delete), 'référence')} de pièces ?\n\n"
            if total_associations > 0:
                message += f"ATTENTION: Ces pièces sont associées à {pluralize(total_associations, 'appareil')} au total.\n"
                message += "Toutes les associations seront supprimées.\n\n"

        message += "Cette action est irréversible. Continuer ?"

        reply = QMessageBox.question(
            self, "Confirmation de suppression",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_count = 0
        deleted_associations = 0

        # Supprimer chaque pièce
        for ref_piece, nb_appareils in pieces_to_delete:
            self._do_delete_piece(ref_piece)
            deleted_count += 1
            deleted_associations += nb_appareils

            # Ajouter à l'historique de la fenêtre principale
            self._add_to_main_history(ref_piece, nb_appareils)

        # Valider la transaction
        self.db_manager.conn.commit()

        # Message de succès
        if len(pieces_to_delete) == 1:
            QMessageBox.information(
                self, "Suppression réussie",
                f"La référence '{pieces_to_delete[0][0]}' et ses {pluralize(pieces_to_delete[0][1], 'association')} ont été supprimées."
            )
        else:
            QMessageBox.information(
                self, "Suppression réussie",
                f"{pluralize(deleted_count, 'référence')} supprimées avec {pluralize(deleted_associations, 'association')} au total."
            )

        # Recharger les données (sans fermer la fenêtre)
        self._load_pieces_data()

        # Informer la fenêtre principale si elle existe (sans forcer le refresh qui pourrait fermer cette fenêtre)
        # Note: Le refresh est fait automatiquement par l'historique
        # if hasattr(self.parent(), '_force_refresh_display'):
        #     self.parent()._force_refresh_display()
            
    @handle_ui_errors(log_prefix="Erreur ajout historique", show_message=False)
    def _add_to_main_history(self, ref_piece, nb_associations):
        """Ajouter une entrée dans l'historique de la fenêtre principale"""
        if hasattr(self.parent(), 'user_interaction_service'):
            # Ajouter directement à l'historique visible de la fenêtre principale
            from src.core.config import pluralize
            summary = f"Suppression de la pièce '{ref_piece}' ({pluralize(nb_associations, 'association')})"
            self.parent().user_interaction_service.add_to_history(summary)
    
    def _do_edit_piece(self, current_ref: str, current_desc: str):
        """Logique commune d'édition d'une pièce : dialogue, validation, mise à jour DB, historique."""
        dialog = PieceEditDialog(self, current_ref, current_desc)
        if dialog.exec_() != QDialog.Accepted:
            return

        new_ref, new_desc = dialog.get_values()

        if not new_ref:
            QMessageBox.warning(self, "Erreur", "La référence ne peut pas être vide.")
            return

        if any(char in new_ref for char in ['||', '&&']):
            QMessageBox.warning(self, "Erreur",
                                "La référence ne peut pas contenir les caractères '||' ou '&&'.")
            return

        # Vérifier si la nouvelle référence existe déjà (si elle a changé)
        if new_ref != current_ref:
            existing = self.db_manager.execute_query(
                "SELECT id FROM pieces WHERE ref_piece = ?", [new_ref]
            )
            if existing:
                QMessageBox.warning(
                    self, "Référence existante",
                    f"La référence '{new_ref}' existe déjà. Veuillez choisir une référence différente."
                )
                return

        self.db_manager.cursor.execute(
            "UPDATE pieces SET ref_piece = ?, description = ? WHERE ref_piece = ?",
            (new_ref, new_desc, current_ref)
        )
        self.db_manager.conn.commit()
        self._load_pieces_data()

        if hasattr(self.parent(), 'user_interaction_service'):
            msg = _format_piece_edit_history(current_ref, new_ref, current_desc, new_desc)
            if msg:
                self.parent().user_interaction_service.add_to_history(msg)

    @handle_ui_errors(log_prefix="Erreur modification pièce", show_message=True)
    def _edit_selected_piece(self, checked=False):
        """Modifier la pièce sélectionnée"""
        current_row = self.pieces_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner une pièce à modifier.")
            return

        ref_item = self.pieces_table.item(current_row, 0)
        if not ref_item:
            return

        current_ref = ref_item.data(Qt.UserRole) or ref_item.text()
        desc_item = self.pieces_table.item(current_row, 1)
        current_desc = desc_item.text() if desc_item else ""
        self._do_edit_piece(current_ref, current_desc)

    @handle_ui_errors(log_prefix="Erreur modification pièce (row)", show_message=True)
    def _edit_piece_at_row(self, row: int):
        """Éditer la pièce à la ligne spécifiée (appelée depuis boutons au survol)"""
        if row < 0 or row >= self.pieces_table.rowCount():
            return

        ref_item = self.pieces_table.item(row, 0)
        if not ref_item:
            return

        current_ref = ref_item.data(Qt.UserRole) or ref_item.text()
        desc_item = self.pieces_table.item(row, 1)
        current_desc = desc_item.text() if desc_item else ""
        self._do_edit_piece(current_ref, current_desc)

    @handle_ui_errors(log_prefix="Erreur suppression pièce (row)", show_message=True)
    def _delete_piece_at_row(self, row: int):
        """Supprimer la pièce à la ligne spécifiée (appelée depuis boutons au survol)"""
        if row < 0 or row >= self.pieces_table.rowCount():
            return

        # Obtenir la référence de la pièce
        ref_item = self.pieces_table.item(row, 0)
        if not ref_item:
            return

        ref_piece = ref_item.data(Qt.UserRole) or ref_item.text()

        # Confirmation
        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Êtes-vous sûr de vouloir supprimer la pièce '{ref_piece}' ?\n\n"
            f"Cette action supprimera également toutes ses associations avec les appareils.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            nb_item = self.pieces_table.item(row, 2)
            nb_appareils = int(nb_item.text()) if nb_item and nb_item.text().isdigit() else 0

            self._do_delete_piece(ref_piece)
            self.db_manager.conn.commit()
            self._load_pieces_data()
            self._add_to_main_history(ref_piece, nb_appareils)

class PieceEditDialog(QDialog):
    """Dialogue d'édition d'une pièce"""
    
    def __init__(self, parent, current_ref, current_desc):
        super().__init__(parent)
        self.setWindowTitle("Modifier la pièce")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout()
        
        # Champ référence
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence:"))
        self.ref_input = QLineEdit(current_ref)
        self.ref_input.setPlaceholderText("Référence de la pièce")
        ref_layout.addWidget(self.ref_input)
        layout.addLayout(ref_layout)
        
        # Champ libellé
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Libellé:"))
        self.desc_input = QLineEdit(current_desc)
        self.desc_input.setPlaceholderText("Libellé de la pièce (optionnel)")
        desc_layout.addWidget(self.desc_input)
        layout.addLayout(desc_layout)
        
        # Boutons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Sauvegarder")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet(f"QPushButton {{ background-color: {Config.Colors.SUCCESS_LIGHT}; color: white; }}")
        buttons_layout.addWidget(save_btn)
        
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
        
        # Focus sur le champ référence
        self.ref_input.selectAll()
        self.ref_input.setFocus()
        
    def get_values(self):
        """Retourner les valeurs saisies"""
        return self.ref_input.text().strip(), self.desc_input.text().strip()


class PieceSuccessionDialog(QDialog):
    """
    Dialogue de gestion de la succession pour une référence pièce.
    Utilisable depuis le gestionnaire de pièces ou la liste des pièces associées.
    """

    def __init__(self, parent, db_manager, ref_piece: str, history_callback=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.ref_piece = ref_piece
        self.history_callback = history_callback  # callable(message) ou None

        self.setWindowTitle(f"Succession — {ref_piece}")
        self.setModal(True)
        self.resize(480, 200)
        self._init_ui()
        self._refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Statut + chaîne
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.status_label)

        # Boutons d'action
        btn_layout = QHBoxLayout()

        self.btn_superseded = QPushButton("Remplacée par…")
        self.btn_superseded.clicked.connect(self._on_mark_superseded)
        btn_layout.addWidget(self.btn_superseded)

        self.btn_obsolete = QPushButton("Marquer obsolète")
        self.btn_obsolete.setStyleSheet("QPushButton { color: #E05252; }")
        self.btn_obsolete.clicked.connect(self._on_mark_obsolete)
        btn_layout.addWidget(self.btn_obsolete)

        self.btn_cancel_succ = QPushButton("Annuler la succession")
        self.btn_cancel_succ.clicked.connect(self._on_cancel_succession)
        btn_layout.addWidget(self.btn_cancel_succ)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Fermer
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

    def _refresh(self):
        """Mettre à jour l'affichage du statut."""
        status_info = self.db_manager.get_piece_status(self.ref_piece)
        status = status_info['status']
        is_obsolete = status_info['is_obsolete']
        ref_new = status_info.get('ref_new')

        self.btn_obsolete.setText("Retirer l'obsolescence" if is_obsolete else "Marquer obsolète")
        predecessors = self.db_manager.get_all_predecessors(self.ref_piece)

        if status == 'superseded':
            text = f"↳ Remplacée par  {ref_new}"
            if is_obsolete:
                text += "  (⚠ obsolète)"
            self.status_label.setText(text)
            self.status_label.setStyleSheet("color: #e67e22; font-size: 12px; font-weight: bold;")
            self.btn_cancel_succ.setEnabled(True)
        elif status == 'obsolete':
            self.status_label.setText("⚠ Obsolète — aucun remplacement")
            self.status_label.setStyleSheet("color: #c0392b; font-size: 12px; font-weight: bold;")
            self.btn_cancel_succ.setEnabled(False)
        elif predecessors:
            refs_old = ", ".join(predecessors)
            self.status_label.setText(f"↑ Remplace  {refs_old}")
            self.status_label.setStyleSheet("color: #2980b9; font-size: 12px; font-weight: bold;")
            self.btn_cancel_succ.setEnabled(False)
        else:
            self.status_label.setText("✓ Référence courante")
            self.status_label.setStyleSheet("color: #34A853; font-size: 12px; font-weight: bold;")
            self.btn_cancel_succ.setEnabled(False)

    def _on_mark_superseded(self):
        dlg = PiecePickerDialog(
            self.db_manager, self,
            exclude_ref=self.ref_piece,
            title=f"Référence qui remplace '{self.ref_piece}'"
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        ref_new = dlg.selected_ref()
        if not ref_new:
            return
        success, error = self.db_manager.add_supersession(self.ref_piece, ref_new)
        if success:
            self._send_history(f"Succession :\n==> '{self.ref_piece}' → '{ref_new}'")
            self._refresh()
        else:
            QMessageBox.warning(self, "Erreur de succession", error)

    def _on_mark_obsolete(self):
        appareils = self.db_manager.get_appareils_for_piece_ref(self.ref_piece)
        msg = f"Marquer '{self.ref_piece}' comme obsolète (aucun remplacement) ?"
        if appareils:
            lines = [f"  • {mfr or '?'} {ref_mod or '?'} ({type_ or '?'})" for type_, mfr, ref_mod in appareils[:10]]
            if len(appareils) > 10:
                lines.append(f"  … et {len(appareils) - 10} autre(s)")
            msg += "\n\nAppareils concernés :\n" + "\n".join(lines)
        confirm = QMessageBox.question(
            self, "Marquer comme obsolète", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        is_obsolete = self.db_manager.get_piece_status(self.ref_piece)['is_obsolete']
        if is_obsolete:
            ok = self.db_manager.unmark_obsolete(self.ref_piece)
            msg_history = f"Succession :\n==> '{self.ref_piece}' → plus obsolète"
        else:
            ok = self.db_manager.mark_obsolete(self.ref_piece)
            msg_history = f"Succession :\n==> '{self.ref_piece}' → obsolète"
        if ok:
            self._send_history(msg_history)
            self._refresh()
        else:
            QMessageBox.warning(self, "Erreur", "Impossible de modifier le statut d'obsolescence.")

    def _on_cancel_succession(self):
        confirm = QMessageBox.question(
            self, "Annuler la succession",
            f"Supprimer le lien de succession pour '{self.ref_piece}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.db_manager.remove_supersession(self.ref_piece)
        self._send_history(f"Succession :\n==> '{self.ref_piece}' → (succession annulée)")
        self._refresh()

    def _send_history(self, message: str):
        if self.history_callback:
            try:
                self.history_callback(message)
            except Exception:
                pass
