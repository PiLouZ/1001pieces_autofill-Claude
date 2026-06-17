"""
Gestionnaire des pièces - Fenêtre de gestion des références de pièces
"""

from .qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                           QTableWidgetItem, QTableWidgetSelectionRange, QLabel,
                           QPushButton, QLineEdit,
                           QHeaderView, QMessageBox, QSplitter, QTextEdit,
                           QApplication, QWidget, QMenu, QInputDialog, QCheckBox,
                           Qt, QTimer, pyqtSignal, QColor,
                           QButtonGroup, QFont,
                           QFrame, QScrollArea, QSize, QPoint, QCursor, QPalette,
                           QEvent, QStackedWidget, QProgressBar, QItemSelectionModel)
from typing import List, Tuple, Dict
import qtawesome as qta


def _format_refs_recap(refs: list, max_shown: int = 8) -> str:
    """Formater une liste de refs pour un récapitulatif de confirmation."""
    if len(refs) <= max_shown:
        return ", ".join(refs)
    return ", ".join(refs[:max_shown]) + f", … et {len(refs) - max_shown} autre(s)"

from ..core.config import Config
from ..utils.error_handler import handle_ui_errors
from ..core.logger import app_logger
from .pieces_list_service import PieceRelationsPopup, _format_piece_edit_history
from .style_manager import StyleManager
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
            StyleManager.ICON_BUTTON +
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
            StyleManager.ICON_BUTTON +
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
            StyleManager.ICON_BUTTON +
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

        # Nombre de références actuellement affichées (après recherche/filtre)
        self.filtered_count_label = QLabel("")
        self.filtered_count_label.setStyleSheet(f"color: {Config.Colors.TEXT_MUTED}; margin: 10px;")
        header_layout.addWidget(self.filtered_count_label)

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
        refresh_btn.setStyleSheet(StyleManager.REFRESH_BUTTON)
        refresh_btn.clicked.connect(self._load_pieces_data)
        search_layout.addWidget(refresh_btn)

        new_piece_btn = QPushButton("+ Nouvelle pièce")
        new_piece_btn.setIcon(qta.icon('fa5s.plus-circle', color='#1565C0'))
        new_piece_btn.setIconSize(QSize(12, 12))
        new_piece_btn.setToolTip("Créer une nouvelle référence de pièce dans le catalogue")
        new_piece_btn.setStyleSheet(
            "QPushButton { padding: 3px 9px; font-size: 11px; color: #1565C0; border-radius: 3px; }"
            "QPushButton:hover { background: rgba(21,101,192,0.10); }"
        )
        new_piece_btn.clicked.connect(self._show_new_piece_dialog)
        search_layout.addWidget(new_piece_btn)

        layout.addLayout(search_layout)


        # ── Barre de filtres rapides, regroupée en 3 clusters thématiques ───
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filtrer :"))

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._active_filter = 'all'

        # Clusters : (libellé du cluster, [(clé, label, icône, couleur), ...])
        _filter_clusters = [
            ('général', [
                ('all',     'Toutes',     'fa5s.list',   '#495057'),
                ('orphan',  'Orphelines', 'fa5s.unlink', '#c0392b'),
                ('phantom', 'Fantômes',   'fa5s.ghost',  '#7f8c8d'),
            ]),
            ('succession', [
                ('obsolete',   'Obsolètes',    'fa5s.exclamation-triangle', '#e67e22'),
                ('superseded', 'Remplacées',   'fa5s.long-arrow-alt-right', '#e67e22'),
                ('replacing',  'Remplaçantes', 'fa5s.level-up-alt',         '#2980b9'),
                ('current',    'Courantes',    'fa5s.check-circle',         '#27ae60'),
            ]),
            ('équivalences', [
                ('equivalent',   'Équivalentes',         'fa5s.exchange-alt',       '#8e44ad'),
                ('inconsistent', 'Libellés incohérents', 'fa5s.exclamation-circle', '#d35400'),
            ]),
        ]

        def _make_icon_toggle(b, iname, icolor):
            def _on_toggled(checked):
                b.setIcon(qta.icon(iname, color='white' if checked else icolor))
            return _on_toggled

        self._filter_btns = {}
        btn_index = 0
        for cluster_idx, (cluster_label, defs) in enumerate(_filter_clusters):
            if cluster_idx > 0:
                separator = QFrame()
                separator.setFrameShape(QFrame.VLine)
                separator.setFrameShadow(QFrame.Sunken)
                filter_layout.addWidget(separator)

            cluster_col = QVBoxLayout()
            cluster_col.setSpacing(1)

            cluster_title = QLabel(cluster_label)
            cluster_title.setStyleSheet("color: #adb5bd; font-size: 9px;")
            cluster_col.addWidget(cluster_title)

            cluster_row = QHBoxLayout()
            cluster_row.setSpacing(4)
            for key, label, icon_name, icon_color in defs:
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
                self._filter_group.addButton(btn, btn_index)
                btn_index += 1
                cluster_row.addWidget(btn)
                self._filter_btns[key] = btn

            cluster_col.addLayout(cluster_row)
            filter_layout.addLayout(cluster_col)

        self._filter_group.buttonClicked.connect(self._on_filter_changed)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Tableau des pièces
        self.pieces_table = PiecesTableWidget()
        self.pieces_table.setColumnCount(6)
        self.pieces_table.setHorizontalHeaderLabels([
            "Référence Pièce", "Libellé", "Nb", "Statut", "Types d'Appareils", ""
        ])

        # Configuration du tableau — Libellé en Interactive (redimensionnable par l'utilisateur),
        # Types d'Appareils en Stretch pour absorber l'espace résiduel.
        header = self.pieces_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Référence
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Libellé (redimensionnable)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)        # Nb
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)        # Statut
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)      # Types d'Appareils
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)        # Actions
        self.pieces_table.setColumnWidth(0, 130)   # Référence Pièce
        self.pieces_table.setColumnWidth(1, 220)   # Libellé
        self.pieces_table.setColumnWidth(2, 55)    # Nb
        self.pieces_table.setColumnWidth(3, 78)    # Statut
        self.pieces_table.setColumnWidth(5, 72)    # Actions (3 boutons × 22px)

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
        self.pieces_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pieces_table.customContextMenuRequested.connect(self._show_table_context_menu)

        # ── Layout principal : splitter table | panneau latéral ────────────────
        # details_text supprimé (widget orphelin — non affiché dans l'UI, requête SQL inutile à chaque sélection)

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
        spinner_btn.setStyleSheet(StyleManager.FLAT_TRANSPARENT)
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
        side_panel.setMinimumWidth(200)
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

        # ── 2 zones : Équivalences (prioritaire) / Succession + actions ────────
        sections_splitter = QSplitter(Qt.Vertical)
        sections_splitter.setChildrenCollapsible(False)

        # Section "≡ Équivalences" — zone prioritaire en haut
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

        # ── Zone "Succession" (Remplace / Remplacée par en 2 colonnes + actions) ──
        succession_combined = QFrame()
        succession_combined.setFrameShape(QFrame.StyledPanel)
        succ_combined_layout = QVBoxLayout(succession_combined)
        succ_combined_layout.setContentsMargins(6, 4, 6, 4)
        succ_combined_layout.setSpacing(4)

        succession_row = QHBoxLayout()
        succession_row.setSpacing(6)

        # Colonne "↑ Remplace"
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
        succession_row.addWidget(replaces_section)

        # Colonne "↳ Remplacée par"
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
        succession_row.addWidget(superseded_section)

        succ_combined_layout.addLayout(succession_row)

        # succ_single_widget : wrapper fantôme gardé pour la compatibilité
        self.succ_single_widget = QWidget()
        self.succ_single_widget.setVisible(False)  # never shown, kept for compat

        # ── Approche A : actions regroupées en sous-sections avec mini-titres ──
        self.btn_cancel_succession = QPushButton("Supprimer les liens de succession")
        self.btn_cancel_succession.setIcon(qta.icon('fa5s.ban', color='#e67e22'))
        self.btn_cancel_succession.setIconSize(QSize(11, 11))
        self.btn_cancel_succession.setToolTip("Supprimer tous les liens de succession pour les pièces sélectionnées")
        self.btn_cancel_succession.setEnabled(False)
        self.btn_cancel_succession.setStyleSheet("font-size: 11px;")
        self.btn_cancel_succession.clicked.connect(self._on_cancel_succession)
        self.btn_cancel_succession.setVisible(False)

        self.btn_unlink_equiv = QPushButton("Retirer du groupe")
        self.btn_unlink_equiv.setIcon(qta.icon('fa5s.unlink', color='#E05252'))
        self.btn_unlink_equiv.setIconSize(QSize(11, 11))
        self.btn_unlink_equiv.setToolTip("Retirer la pièce sélectionnée de son groupe d'équivalence")
        self.btn_unlink_equiv.setEnabled(False)
        self.btn_unlink_equiv.setStyleSheet("QPushButton { color: #E05252; font-size: 11px; }")
        self.btn_unlink_equiv.setVisible(False)
        self.btn_unlink_equiv.clicked.connect(self._on_unlink_equiv)

        self.btn_mark_equivalent_group = QPushButton("Fusionner en un groupe d'équivalents")
        self.btn_mark_equivalent_group.setIcon(qta.icon('fa5s.link', color='#8e44ad'))
        self.btn_mark_equivalent_group.setIconSize(QSize(11, 11))
        self.btn_mark_equivalent_group.setToolTip(
            "Fusionner toutes les pièces sélectionnées dans un seul groupe d'équivalence")
        self.btn_mark_equivalent_group.setStyleSheet("color: #8e44ad; font-size: 11px;")
        self.btn_mark_equivalent_group.setVisible(False)
        self.btn_mark_equivalent_group.clicked.connect(self._on_mark_equivalent_group)

        self.btn_harmonize_labels = QPushButton("Harmoniser les libellés…")
        self.btn_harmonize_labels.setIcon(qta.icon('fa5s.palette', color='#d35400'))
        self.btn_harmonize_labels.setIconSize(QSize(11, 11))
        self.btn_harmonize_labels.setToolTip(
            "Les pièces équivalentes n'ont pas le même libellé — choisir celui à appliquer à tout le groupe")
        self.btn_harmonize_labels.setStyleSheet("color: #d35400; font-size: 11px;")
        self.btn_harmonize_labels.setVisible(False)
        self.btn_harmonize_labels.clicked.connect(self._on_harmonize_labels)

        # ── Actions de groupe (multi-sélection) ────────────────────────────
        self.btn_batch_edit_libelle = QPushButton("Modifier le libellé…")
        self.btn_batch_edit_libelle.setIcon(qta.icon('fa5s.edit', color='#1565C0'))
        self.btn_batch_edit_libelle.setIconSize(QSize(11, 11))
        self.btn_batch_edit_libelle.setToolTip(
            "Appliquer le même libellé à toutes les pièces sélectionnées")
        self.btn_batch_edit_libelle.setStyleSheet("font-size: 11px;")
        self.btn_batch_edit_libelle.setVisible(False)
        self.btn_batch_edit_libelle.clicked.connect(self._on_batch_edit_libelle)

        self.btn_export_selection = QPushButton("Exporter la sélection")
        self.btn_export_selection.setIcon(qta.icon('fa5s.file-export', color='#555555'))
        self.btn_export_selection.setIconSize(QSize(11, 11))
        self.btn_export_selection.setToolTip(
            "Exporter uniquement les pièces sélectionnées au format CSV")
        self.btn_export_selection.setStyleSheet("font-size: 11px;")
        self.btn_export_selection.setVisible(False)
        self.btn_export_selection.clicked.connect(self._export_selected_pieces)

        # Sous-sections : (titre, [boutons]) — le titre est masqué si aucun
        # bouton de la sous-section n'est visible (voir _sync_action_sections)
        self._action_sections = []
        for section_title, buttons in [
            ("SUCCESSION",   [self.btn_cancel_succession]),
            ("ÉQUIVALENCES", [self.btn_unlink_equiv, self.btn_harmonize_labels]),
        ]:
            title_lbl = QLabel(section_title)
            title_lbl.setStyleSheet("color: #adb5bd; font-size: 9px; font-weight: bold;")
            succ_combined_layout.addWidget(title_lbl)
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            for btn in buttons:
                btn_row.addWidget(btn)
            btn_row.addStretch()
            succ_combined_layout.addLayout(btn_row)
            self._action_sections.append((title_lbl, buttons))

        sections_splitter.addWidget(succession_combined)
        sections_splitter.setStretchFactor(0, 3)
        sections_splitter.setStretchFactor(1, 2)

        side_layout.addWidget(sections_splitter, 1)

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

        # Sélection persistante (sticky) : refs sélectionnées par l'utilisateur,
        # conservées même quand une recherche/filtre les masque temporairement —
        # permet de composer une sélection multi-pièces sur plusieurs recherches.
        self._sticky_selected_refs = set()

        main_splitter.addWidget(side_panel)
        # Taille initiale : 70% tableau / 30% panneau latéral
        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setSizes([700, 300])  # Force la répartition initiale 70/30

        layout.addWidget(main_splitter, 1)

        # ── Barre d'actions contextuelle (masquée sauf si ≥1 pièce sélectionnée) ──
        self._action_bar = QFrame()
        self._action_bar.setStyleSheet(
            "QFrame { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }"
        )
        self._action_bar.setVisible(False)
        _ab_layout = QHBoxLayout(self._action_bar)
        _ab_layout.setContentsMargins(8, 4, 8, 4)
        _ab_layout.setSpacing(8)

        self._action_bar_label = QLabel("")
        self._action_bar_label.setStyleSheet("color: #495057; font-size: 11px; font-weight: bold;")
        _ab_layout.addWidget(self._action_bar_label)

        self._btn_selection_popup = QPushButton()
        self._btn_selection_popup.setIcon(qta.icon('fa5s.chevron-down', color='#495057'))
        self._btn_selection_popup.setIconSize(QSize(9, 9))
        self._btn_selection_popup.setFixedSize(20, 20)
        self._btn_selection_popup.setToolTip("Voir et gérer la sélection")
        self._btn_selection_popup.setFlat(True)
        self._btn_selection_popup.setVisible(False)
        self._btn_selection_popup.clicked.connect(self._show_selection_popup)
        _ab_layout.addWidget(self._btn_selection_popup)

        _ab_sep = QFrame()
        _ab_sep.setFrameShape(QFrame.VLine)
        _ab_sep.setFrameShadow(QFrame.Sunken)
        _ab_layout.addWidget(_ab_sep)

        _ab_layout.addWidget(self.btn_mark_equivalent_group)
        _ab_layout.addWidget(self.btn_batch_edit_libelle)
        _ab_layout.addWidget(self.btn_export_selection)
        _ab_layout.addStretch()

        _btn_deselect_bar = QPushButton("Désélectionner tout")
        _btn_deselect_bar.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        _btn_deselect_bar.clicked.connect(self._clear_sticky_selection)
        _ab_layout.addWidget(_btn_deselect_bar)

        layout.addWidget(self._action_bar)

        # Boutons d'action (footer)
        _btn_style = (
            "QPushButton { padding: 3px 10px; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); }"
        )
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        # "Chercher dans l'app" déplacé dans le menu contextuel (clic droit sur une ligne)

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

        # Détection des libellés divergents au sein d'un groupe d'équivalence (C+I)
        self._desc_by_ref = {r[0]: (r[1] or "") for r in results}
        for ref, status in self.all_statuses.items():
            equiv_str = status.get('equivalents')
            if equiv_str:
                group_refs = [ref] + [e.strip() for e in equiv_str.split(',') if e.strip()]
                descs = {self._desc_by_ref.get(r, "") for r in group_refs}
                status['labels_differ'] = len(descs) > 1
            else:
                status['labels_differ'] = False

        self._update_table_display()

    # ── Widget d'actions flottant ─────────────────────────────────────────────

    def _on_cell_entered(self, row: int, _col: int):
        """Positionner le widget d'actions flottant sur la ligne survolée."""
        idx = self.pieces_table.model().index(row, 5)
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

    def keyPressEvent(self, event):
        """Raccourcis clavier sur le tableau de pièces."""
        key = event.key()
        if key == Qt.Key_F2:
            self._edit_selected_piece()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            row = self.pieces_table.currentRow()
            if row >= 0:
                self._delete_at_row_or_selection(row)
        else:
            super().keyPressEvent(event)

    def _update_table_display(self):
        """Mettre à jour l'affichage du tableau avec filtrage.
        Les signaux sont bloqués pendant la reconstruction pour éviter que
        setRowCount() ne déclenche itemSelectionChanged → sections cachées."""
        # Remplacer l'écran de chargement par le tableau au premier appel
        if hasattr(self, '_table_stack') and self._table_stack.currentIndex() == 0:
            self._table_stack.setCurrentIndex(1)

        filtered_data = self._get_filtered_data()

        from src.core.config import pluralize
        total = len(getattr(self, 'all_pieces_data', []))
        if len(filtered_data) != total:
            self.filtered_count_label.setText(f"— {pluralize(len(filtered_data), 'affichée')}")
        else:
            self.filtered_count_label.setText("")

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

            # ── Colonne 3 : statut (icône + texte court) ─────────────────
            if is_phantom:
                _icon = qta.icon('fa5s.ghost', color='#999999')
                _status_text = "Fantôme"
                _status_tip = "Référence fantôme — créée pour la succession"
            elif is_obsolete:
                ref_new = status_info.get('ref_new', '')
                _icon = qta.icon('fa5s.ban', color='#c62828')
                _status_text = "Obsolète"
                _status_tip = f"Obsolète → {ref_new}" if ref_new else "Marquée obsolète"
            elif status == 'superseded':
                ref_new = status_info.get('ref_new', '')
                _icon = qta.icon('fa5s.long-arrow-alt-right', color='#e67e22')
                _status_text = f"→ {ref_new}" if ref_new else "Remplacée"
                _status_tip = f"Remplacée par {ref_new}" if ref_new else "Remplacée"
            elif status == 'replacing':
                refs_old = status_info.get('refs_old') or []
                _icon = qta.icon('fa5s.level-up-alt', color='#1565C0')
                _n = len(refs_old)
                _status_text = f"Remplace ({_n})" if _n > 1 else "Remplace"
                _status_tip = "Remplace : " + ", ".join(refs_old) if refs_old else "Remplace d'anciennes réfs"
            elif status_info.get('equivalents'):
                _icon = qta.icon('fa5s.exchange-alt', color='#8e44ad')
                _status_text = "Équivalent"
                _status_tip = "Fait partie d'un groupe d'équivalents"
            else:
                _icon = qta.icon('fa5s.check-circle', color='#2e7d32')
                _status_text = "OK"
                _status_tip = "Référence courante, active"
            status_item = QTableWidgetItem(_status_text)
            status_item.setIcon(_icon)
            status_item.setToolTip(_status_tip)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            self.pieces_table.setItem(row_idx, 3, status_item)

            # ── Colonne 4 : types d'appareils — espace après les virgules ──
            types_display = (types_appareils or "—").replace(",", ", ")
            if len(types_display) > 55:
                types_display = types_display[:52] + "…"
            types_item = QTableWidgetItem(types_display)
            types_item.setToolTip((types_appareils or "Aucun type").replace(",", ", "))
            self.pieces_table.setItem(row_idx, 4, types_item)

            # Colonne 5 : actions gérées par le widget flottant (_floating_actions)

        self.pieces_table.blockSignals(False)

        # Restaurer la sélection persistante (sticky) et les panneaux.
        # selectionModel().select(..., Select | Rows) est utilisé (pas selectRow,
        # qui ne cumule PAS les lignes — chaque appel remplace la sélection
        # précédente) ni setCurrentCell (qui en ExtendedSelection ne sélectionne
        # pas réellement la ligne → selectedIndexes() resterait vide).
        ref = getattr(self, '_current_ref_piece', None)
        restored = []  # [(row, item_ref), ...] — toutes les refs sticky encore visibles
        # blockSignals pendant la boucle : sinon chaque select() émet
        # itemSelectionChanged → _sync_sticky_selection() re-synchronise sur une
        # sélection PARTIELLEMENT restaurée et retire les refs pas encore
        # re-sélectionnées de _sticky_selected_refs (perte de sélection).
        self.pieces_table.blockSignals(True)
        selection_model = self.pieces_table.selectionModel()
        for row in range(self.pieces_table.rowCount()):
            item = self.pieces_table.item(row, 0)
            if item:
                item_ref = item.data(Qt.UserRole) or item.text()
                if item_ref in self._sticky_selected_refs:
                    selection_model.select(
                        self.pieces_table.model().index(row, 0),
                        QItemSelectionModel.Select | QItemSelectionModel.Rows
                    )
                    restored.append((row, item_ref))
        self.pieces_table.blockSignals(False)

        target_row, target_ref = None, None
        for row, item_ref in restored:
            if item_ref == ref:
                target_row, target_ref = row, item_ref
                break
        if target_ref is None and restored:
            target_row, target_ref = restored[-1]

        self._update_sticky_selection_indicator()

        if target_ref:
            self._current_ref_piece = target_ref
            if target_ref != ref:
                self._update_panel_header(target_ref)
            self._refresh_succession_panel(target_ref)
            self._refresh_equivalence_panel(target_ref)
        elif ref:
            # La pièce courante n'est plus dans la liste filtrée (recherche /
            # filtre / suppression) : on remet le panneau dans un état « rien
            # de sélectionné » COHÉRENT — sinon l'en-tête garderait l'ancienne
            # pièce alors que le reste du panneau s'est vidé (bug des blocs
            # qui « disparaissent »).
            self._current_ref_piece = None
            self.panel_header_label.setText("—")
            self._refresh_succession_panel(None)
            self._refresh_equivalence_panel(None)
            
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
        elif active == 'inconsistent':
            filtered = [r for r in filtered
                        if statuses.get(r[0] or '', {}).get('labels_differ')]

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

    def open_on_piece(self, ref: str):
        """Ouvrir le gestionnaire et se positionner sur la pièce donnée.
        Point d'entrée public utilisé par piece_management_service."""
        self.show()
        self.raise_()
        self.activateWindow()
        self._search_in_manager(ref)

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

    def _show_table_context_menu(self, pos):
        """Menu contextuel clic droit sur une ligne du tableau de pièces."""
        row = self.pieces_table.rowAt(pos.y())
        if row < 0:
            return
        item = self.pieces_table.item(row, 0)
        if not item:
            return
        ref = item.data(Qt.UserRole) or item.text()
        menu = QMenu(self)
        edit_action = menu.addAction("Modifier cette pièce")
        edit_action.triggered.connect(lambda: self._edit_piece_at_row(row))
        menu.addSeparator()
        search_action = menu.addAction("Chercher dans l'app")
        search_action.triggered.connect(lambda: self._inject_ref_in_search(ref))
        copy_action = menu.addAction("Copier la référence")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(ref))
        menu.exec_(QCursor.pos())

    def _show_new_piece_dialog(self):
        """Ouvrir le dialogue de création d'une nouvelle référence de pièce."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Nouvelle pièce")
        dlg.setModal(True)
        dlg.resize(360, 130)

        form_layout = QVBoxLayout(dlg)
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(12, 12, 12, 10)

        ref_row = QHBoxLayout()
        lbl_ref = QLabel("Référence *")
        lbl_ref.setFixedWidth(70)
        ref_row.addWidget(lbl_ref)
        ref_input = QLineEdit()
        ref_input.setPlaceholderText("Ex. : 12345678")
        ref_row.addWidget(ref_input)
        form_layout.addLayout(ref_row)

        lib_row = QHBoxLayout()
        lbl_lib = QLabel("Libellé")
        lbl_lib.setFixedWidth(70)
        lib_row.addWidget(lbl_lib)
        lib_input = QLineEdit()
        lib_input.setPlaceholderText("Description (optionnelle)")
        lib_row.addWidget(lib_input)
        form_layout.addLayout(lib_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler")
        btn_ok = QPushButton("Créer")
        btn_ok.setDefault(True)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        form_layout.addLayout(btn_row)

        def _on_create():
            ref = ref_input.text().strip()
            libelle = lib_input.text().strip() or None
            if not ref:
                ref_input.setFocus()
                return
            if any(c in ref for c in ['||', '&&']):
                QMessageBox.warning(dlg, "Référence invalide",
                                    "La référence ne peut pas contenir '||' ou '&&'.")
                return
            success = self.db_manager.create_piece_standalone(ref, libelle)
            dlg.close()
            if success:
                app_logger.info(f"Nouvelle pièce créée : {ref}")
                self._load_pieces_data()
                QTimer.singleShot(300, lambda: self.open_on_piece(ref))
            else:
                # Ref existante : ouvrir directement dessus
                QMessageBox.information(
                    self, "Référence existante",
                    f"La référence « {ref} » existe déjà dans le catalogue."
                )
                self.open_on_piece(ref)

        btn_ok.clicked.connect(_on_create)
        btn_cancel.clicked.connect(dlg.close)
        ref_input.returnPressed.connect(_on_create)
        dlg.show()
        ref_input.setFocus()

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
        self._sync_sticky_selection()
        current_row = self.pieces_table.currentRow()
        if current_row < 0:
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
        
    # ── Succession ──────────────────────────────────────────────────────────

    def _get_visible_selected_refs(self) -> list:
        """Retourner les refs des lignes sélectionnées dans le tableau affiché."""
        rows = sorted({idx.row() for idx in self.pieces_table.selectedIndexes()})
        refs = []
        for row in rows:
            item = self.pieces_table.item(row, 0)
            if item:
                refs.append(item.data(Qt.UserRole) or item.text())
        return refs

    def _get_selected_refs(self) -> list:
        """Retourner la liste des refs sélectionnées (persiste entre les recherches)."""
        return sorted(self._sticky_selected_refs)

    def _sync_sticky_selection(self):
        """Synchroniser la sélection persistante avec la sélection visible.
        Les refs visibles ajoutées/retirées de la sélection mettent à jour
        _sticky_selected_refs ; les refs masquées par la recherche/filtre en
        cours restent inchangées — ce qui permet de composer une sélection
        multi-pièces à travers plusieurs recherches successives."""
        visible_refs = set()
        for row in range(self.pieces_table.rowCount()):
            item = self.pieces_table.item(row, 0)
            if item:
                visible_refs.add(item.data(Qt.UserRole) or item.text())
        visible_selected = set(self._get_visible_selected_refs())
        self._sticky_selected_refs -= (visible_refs - visible_selected)
        self._sticky_selected_refs |= visible_selected
        self._update_sticky_selection_indicator()

    def _update_sticky_selection_indicator(self):
        """Afficher/masquer la barre d'actions contextuelle selon la sélection."""
        n = len(self._sticky_selected_refs)
        if n > 0:
            from src.core.config import pluralize
            refs_sorted = sorted(self._sticky_selected_refs)
            self._action_bar_label.setText(pluralize(n, 'pièce') + " sélectionnée(s)")
            self._action_bar_label.setToolTip("\n".join(refs_sorted))
            self._btn_selection_popup.setVisible(True)
            self._action_bar.setVisible(True)
            # Boutons batch : visibles seulement en multi-sélection (n > 1)
            show_batch = n > 1
            self.btn_mark_equivalent_group.setVisible(show_batch)
            self.btn_batch_edit_libelle.setVisible(show_batch)
            self.btn_export_selection.setVisible(show_batch)
            if show_batch:
                self.btn_export_selection.setText(f"Exporter la sélection ({n})")
        else:
            self._action_bar.setVisible(False)
            self._btn_selection_popup.setVisible(False)
            self._action_bar_label.setToolTip("")

    def _show_selection_popup(self):
        """Afficher un popover listant les pièces sélectionnées avec désélection individuelle (×)."""
        refs = sorted(self._sticky_selected_refs)
        if not refs:
            return

        popup = QFrame(None)
        popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        popup.setObjectName("selectionPopup")
        popup.setStyleSheet(
            "QFrame#selectionPopup { background: #ffffff; border: 1px solid #ced4da;"
            " border-radius: 4px; }"
        )

        outer = QVBoxLayout(popup)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QLabel(f"  Pièces sélectionnées — {len(refs)}")
        header.setStyleSheet(
            "background: #e9ecef; color: #495057; font-size: 11px; font-weight: bold;"
            " padding: 5px 8px;"
        )
        outer.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        outer.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(220)
        scroll.setMinimumWidth(270)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: #ffffff;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 2, 0, 2)
        cl.setSpacing(0)

        for ref in refs:
            row_w = QWidget()
            row_w.setStyleSheet("QWidget:hover { background: #f1f3f5; }")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(8, 3, 6, 3)
            rl.setSpacing(4)
            lbl = QLabel(ref)
            lbl.setStyleSheet("font-size: 11px; color: #212529;")
            rl.addWidget(lbl)
            rl.addStretch()
            btn_x = QPushButton("×")
            btn_x.setFixedSize(18, 18)
            btn_x.setStyleSheet(
                "QPushButton { color: #868e96; border: none; font-size: 14px; padding: 0;"
                " background: transparent; }"
                "QPushButton:hover { color: #dc3545; background: #f8d7da; border-radius: 3px; }"
            )
            btn_x.setToolTip(f"Retirer {ref} de la sélection")
            btn_x.clicked.connect(lambda checked, r=ref, p=popup: self._remove_ref_from_sticky(r, p))
            rl.addWidget(btn_x)
            cl.addWidget(row_w)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        popup.adjustSize()

        btn = self._btn_selection_popup
        pos = btn.mapToGlobal(QPoint(0, btn.height() + 2))
        screen_rect = self.screen().availableGeometry()
        if pos.x() + popup.sizeHint().width() > screen_rect.right():
            pos.setX(screen_rect.right() - popup.sizeHint().width() - 4)
        popup.move(pos)
        popup.show()

    def _remove_ref_from_sticky(self, ref: str, popup):
        """Retirer une pièce de la sélection persistante depuis le popover."""
        self._sticky_selected_refs.discard(ref)
        # Désélectionner la ligne dans le tableau si visible, sans déclencher selectionChanged
        self.pieces_table.blockSignals(True)
        try:
            for row in range(self.pieces_table.rowCount()):
                item = self.pieces_table.item(row, 0)
                if item and (item.data(Qt.UserRole) or item.text()) == ref:
                    self.pieces_table.setRangeSelected(
                        QTableWidgetSelectionRange(row, 0, row, self.pieces_table.columnCount() - 1),
                        False
                    )
                    break
        finally:
            self.pieces_table.blockSignals(False)
        popup.close()
        self._update_sticky_selection_indicator()
        if self._sticky_selected_refs:
            self._show_selection_popup()

    def _clear_sticky_selection(self, checked=False):
        """Vider la sélection persistante et la sélection visible du tableau."""
        self._sticky_selected_refs.clear()
        self.pieces_table.clearSelection()
        self._current_ref_piece = None
        self.panel_header_label.setText("—")
        self._update_sticky_selection_indicator()
        self._refresh_succession_panel(None)
        self._refresh_equivalence_panel(None)

    def _refresh_succession_panel(self, ref_piece):
        """Mettre à jour le panneau Succession, puis synchroniser les mini-titres des
        sous-sections d'actions (Approche A) en fonction des boutons visibles."""
        self._refresh_succession_panel_impl(ref_piece)
        self._sync_action_sections()

    def _sync_action_sections(self):
        """Masquer le mini-titre d'une sous-section d'actions si aucun de ses
        boutons n'est visible (Approche A)."""
        for title_lbl, buttons in getattr(self, '_action_sections', []):
            title_lbl.setVisible(any(b.isVisible() for b in buttons))

    def _refresh_succession_panel_impl(self, ref_piece):
        """Mettre à jour le panneau Succession pour la pièce courante (dernière sélectionnée)."""
        selected = self._get_selected_refs()
        n = len(selected)
        has_selection = n > 0

        # ── Aucune sélection ──────────────────────────────────────────────
        # Option B : les sections restent TOUJOURS visibles (vidées) pour un
        # layout stable — comme le fait déjà ≡ Équivalences. Plus aucun bloc
        # ne « disparaît » quand rien n'est sélectionné.
        if not has_selection or ref_piece is None:
            self.succession_status_label.setText("Sélectionnez une pièce pour voir son statut.")
            self.succession_status_label.setStyleSheet("color: #555555; font-size: 12px;")
            self.superseded_by_tag_list.set_refs([], '#e67e22')
            self.replaces_tag_list.set_refs([], '#2980b9')
            self.superseded_section.setVisible(True)
            self.replaces_section.setVisible(True)
            self.btn_mark_superseded.setEnabled(False)
            self.btn_mark_replaces.setEnabled(False)
            self.btn_cancel_succession.setVisible(False)
            self.btn_cancel_succession.setEnabled(False)
            self.btn_harmonize_labels.setVisible(False)
            return

        # ── Multi-sélection : boutons batch, pas de chips ─────────────────
        if n > 1:
            self.succession_status_label.setText(
                f"{n} pièces sélectionnées — les actions s'appliquent à toutes.")
            self.succession_status_label.setStyleSheet("color: #555555; font-size: 12px;")
            # Sections visibles mais vidées : les chips n'ont pas de sens en
            # multi-sélection, les actions passent par les boutons batch.
            self.superseded_by_tag_list.set_refs([], '#e67e22')
            self.replaces_tag_list.set_refs([], '#2980b9')
            self.superseded_section.setVisible(True)
            self.replaces_section.setVisible(True)
            self.btn_mark_superseded.setEnabled(True)
            self.btn_mark_replaces.setEnabled(True)
            self.btn_cancel_succession.setVisible(True)
            self.btn_cancel_succession.setEnabled(True)
            self.btn_harmonize_labels.setVisible(False)
            return

        # ── Sélection unique : chips ──────────────────────────────────────
        status_info = self.db_manager.get_piece_status(ref_piece)
        status      = status_info['status']
        is_obsolete = status_info['is_obsolete']
        ref_new     = status_info.get('ref_new')
        predecessors = self.db_manager.get_all_predecessors(ref_piece)
        equivalents  = self.db_manager.get_equivalents(ref_piece)


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
        self.btn_mark_superseded.setEnabled(True)
        self.btn_mark_replaces.setEnabled(True)
        self.btn_cancel_succession.setVisible(False)  # chips suffisent en mono-sélection

        # Libellés divergents au sein du groupe d'équivalence (C)
        labels_differ = self.all_statuses.get(ref_piece, {}).get('labels_differ', False)
        self.btn_harmonize_labels.setVisible(bool(equivalents) and labels_differ)
        self.btn_harmonize_labels.setEnabled(bool(equivalents) and labels_differ)

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

    _format_refs_recap = staticmethod(_format_refs_recap)

    def _on_batch_edit_libelle(self):
        """Appliquer le même libellé à toutes les pièces sélectionnées (action D/A)."""
        refs = self._get_selected_refs()
        if len(refs) < 2:
            return

        new_desc, ok = QInputDialog.getText(
            self, "Modifier le libellé",
            f"Nouveau libellé pour les {len(refs)} pièces sélectionnées :"
        )
        if not ok:
            return

        confirm = QMessageBox.question(
            self, "Modifier le libellé",
            f"Le libellé de {len(refs)} pièces va devenir « {new_desc} » :\n"
            f"{self._format_refs_recap(refs)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        updated = self.db_manager.set_description_for_refs(refs, new_desc)
        if updated:
            self._notify_history(
                f"Libellé :\n==> {updated} pièce(s) → « {new_desc} » ({self._format_refs_recap(refs)})"
            )
            self._load_pieces_data()

    def _on_mark_equivalent_group(self):
        """Fusionner toutes les pièces sélectionnées dans un seul groupe d'équivalence (action D)."""
        refs = self._get_selected_refs()
        if len(refs) < 2:
            return

        confirm = QMessageBox.question(
            self, "Marquer comme équivalentes",
            f"Fusionner ces {len(refs)} pièces dans un seul groupe d'équivalence ?\n"
            f"{self._format_refs_recap(refs)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        errors = []
        for ref_b in refs[1:]:
            success, error_msg = self.db_manager.add_equivalence(refs[0], ref_b)
            if not success:
                errors.append(f"{ref_b} : {error_msg}")

        self._notify_history(
            f"Équivalence :\n==> {len(refs)} pièces fusionnées en un groupe ({self._format_refs_recap(refs)})"
        )
        self._update_table_display()
        if errors:
            QMessageBox.warning(self, "Erreur", "\n".join(errors))

    def _on_harmonize_labels(self):
        """Harmoniser les libellés divergents d'un groupe d'équivalence (action C)."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return

        equivalents = self.db_manager.get_equivalents(ref_piece)
        if not equivalents:
            return

        group_refs = [ref_piece] + equivalents

        descs = []
        for r in group_refs:
            d = self._desc_by_ref.get(r, "")
            if d not in descs:
                descs.append(d)

        if len(descs) < 2:
            return

        choices = []
        for d in descs:
            count = sum(1 for r in group_refs if self._desc_by_ref.get(r, "") == d)
            label_display = d if d else "(vide)"
            choices.append(f"{label_display}  —  {count} pièce(s)")

        choice, ok = QInputDialog.getItem(
            self, "Harmoniser les libellés",
            f"Libellés actuels du groupe ({self._format_refs_recap(group_refs)}) :\n"
            f"Choisir le libellé à appliquer à toutes les pièces du groupe :",
            choices, 0, False
        )
        if not ok:
            return

        chosen_desc = descs[choices.index(choice)]

        updated = self.db_manager.set_description_for_refs(group_refs, chosen_desc)
        if updated:
            self._notify_history(
                f"Libellé :\n==> {updated} pièce(s) harmonisées → « {chosen_desc} » "
                f"({self._format_refs_recap(group_refs)})"
            )
            self._load_pieces_data()

    # ── Équivalences ────────────────────────────────────────────────────────

    def _refresh_equivalence_panel(self, ref_piece):
        """Mettre à jour le panneau Équivalences, puis synchroniser les mini-titres
        des sous-sections d'actions (Approche A)."""
        self._refresh_equivalence_panel_impl(ref_piece)
        self._sync_action_sections()

    def _refresh_equivalence_panel_impl(self, ref_piece):
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

    @staticmethod
    def _write_pieces_csv(filename, rows):
        """Écrire une liste de lignes (ref, description, nb_appareils, types_appareils) en CSV."""
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow(['Référence Pièce', 'Libellé', 'Nb Appareils', "Types d'Appareils"])
            for row in rows:
                ref_piece, description, nb_appareils, types_appareils = row[0], row[1], row[2], row[3]
                writer.writerow([ref_piece, description, nb_appareils, types_appareils or ""])

    @handle_ui_errors(log_prefix="Erreur export pièces", show_message=True)
    def _export_pieces(self, checked=False):
        """Exporter la liste des pièces"""
        from .qt_imports import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self, "Exporter les pièces", "pieces_everyParts.csv",
            "Fichiers CSV (*.csv)"
        )

        if filename:
            self._write_pieces_csv(filename, self._get_filtered_data())
            QMessageBox.information(self, "Export réussi", f"Liste exportée vers:\n{filename}")

    @handle_ui_errors(log_prefix="Erreur export sélection pièces", show_message=True)
    def _export_selected_pieces(self, checked=False):
        """Exporter uniquement les pièces sélectionnées"""
        from .qt_imports import QFileDialog

        selected_refs = set(self._get_selected_refs())
        if not selected_refs:
            return

        rows = [row for row in self._get_filtered_data() if row[0] in selected_refs]

        filename, _ = QFileDialog.getSaveFileName(
            self, "Exporter la sélection", "pieces_selection.csv",
            "Fichiers CSV (*.csv)"
        )

        if filename:
            self._write_pieces_csv(filename, rows)
            QMessageBox.information(self, "Export réussi", f"Sélection exportée vers:\n{filename}")
    
    def _do_delete_piece(self, ref_piece: str):
        """Suppression effective d'une pièce : associations puis pièce (sans commit — l'appelant commite)."""
        self.db_manager.delete_piece_catalog(ref_piece, commit=False)

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
        equivalents = self.db_manager.get_equivalents(current_ref)
        dialog = PieceEditDialog(self, current_ref, current_desc, equivalents)

        def _on_accepted():
            new_ref, new_desc, propagate = dialog.get_values()

            if not new_ref:
                QMessageBox.warning(self, "Erreur", "La référence ne peut pas être vide.")
                return

            if any(char in new_ref for char in ['||', '&&']):
                QMessageBox.warning(self, "Erreur",
                                    "La référence ne peut pas contenir les caractères '||' ou '&&'.")
                return

            if not self.db_manager.rename_piece_catalog(current_ref, new_ref, new_desc):
                QMessageBox.warning(
                    self, "Référence existante",
                    f"La référence '{new_ref}' existe déjà. Veuillez choisir une référence différente."
                )
                return

            self._load_pieces_data()

            if hasattr(self.parent(), 'user_interaction_service'):
                msg = _format_piece_edit_history(current_ref, new_ref, current_desc, new_desc)
                if msg:
                    self.parent().user_interaction_service.add_to_history(msg)

            if propagate and equivalents:
                updated = self.db_manager.set_description_for_refs(equivalents, new_desc)
                if updated and hasattr(self.parent(), 'user_interaction_service'):
                    self.parent().user_interaction_service.add_to_history(
                        f"Libellé :\n==> {updated} pièce(s) équivalente(s) → « {new_desc} » "
                        f"({_format_refs_recap(equivalents)})"
                    )
                    self._load_pieces_data()

        dialog.accepted.connect(_on_accepted)
        dialog.show()

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
    
    def __init__(self, parent, current_ref, current_desc, equivalents=None):
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

        # Propagation au groupe d'équivalence (B)
        self.equivalents = equivalents or []
        self.propagate_checkbox = QCheckBox()
        if self.equivalents:
            self.propagate_checkbox.setText(
                f"Appliquer aussi ce libellé aux {len(self.equivalents)} pièces équivalentes "
                f"({_format_refs_recap(self.equivalents)})"
            )
            layout.addWidget(self.propagate_checkbox)
        else:
            self.propagate_checkbox.setVisible(False)

        # Boutons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Sauvegarder")
        save_btn.setDefault(True)
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
        return (self.ref_input.text().strip(), self.desc_input.text().strip(),
                self.propagate_checkbox.isChecked())