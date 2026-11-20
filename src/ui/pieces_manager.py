"""
Gestionnaire des pièces - Fenêtre de gestion des références de pièces
"""

from ..utils.qt_imports import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QLabel,
    QPushButton,
    QLineEdit,
    QHeaderView,
    QMessageBox,
    QSplitter,
    QApplication,
    QWidget,
    QMenu,
    QCheckBox,
    Qt,
    QTimer,
    pyqtSignal,
    QColor,
    QButtonGroup,
    QFont,
    QFrame,
    QScrollArea,
    QSize,
    QPoint,
    QCursor,
    QEvent,
    QStackedWidget,
    QProgressBar,
    QItemSelectionModel,
    QCompleter,
    QStringListModel,
)
from typing import List, Tuple
import html as _html
import qtawesome as qta


def _format_refs_recap(refs: list, max_shown: int = 8) -> str:
    """Formater une liste de refs pour un récapitulatif de confirmation."""
    if len(refs) <= max_shown:
        return ", ".join(refs)
    return ", ".join(refs[:max_shown]) + f", … et {pluralize(len(refs) - max_shown, 'autre')}"


# Catégories de références liées (get_references_liees) : (clé, singulier, pluriel)
_CATEGORIES_LIEES = (
    ('nouvelles', "nouvelle référence", "nouvelles références"),
    ('anciennes', "ancienne référence", "anciennes références"),
    ('autres', "autre version de la lignée", "autres versions de la lignée"),
    ('equivalentes', "équivalente", "équivalentes"),
)


def refs_liees_a_plat(liees: dict) -> list:
    """Toutes les références liées, dans l'ordre des catégories."""
    return [ref for cle, _s, _p in _CATEGORIES_LIEES for ref in (liees or {}).get(cle, [])]


def resume_references_liees(liees: dict) -> List[str]:
    """Une ligne par catégorie non vide : « ancienne référence : 11025804 »."""
    lignes = []
    for cle, singulier, pluriel in _CATEGORIES_LIEES:
        refs = (liees or {}).get(cle, [])
        if refs:
            libelle = singulier if len(refs) == 1 else pluriel
            lignes.append(f"{libelle} : {_format_refs_recap(refs)}")
    return lignes


def libelles_remplaces(libelles: dict, refs: list, nouveau: str) -> List[Tuple[str, str]]:
    """(ref, libellé actuel) des références dont un libellé NON VIDE et différent
    serait écrasé par `nouveau`. Remplir un libellé vide n'est pas remplacer."""
    nouveau = (nouveau or '').strip()
    return [(ref, libelles[ref]) for ref in refs
            if libelles.get(ref) and libelles[ref] != nouveau]


def libelles_candidats(libelles) -> list:
    """Libellés distincts et non vides d'un groupe, dans l'ordre de rencontre.

    Le vide n'est pas un candidat : harmoniser sert à propager un bon libellé
    aux membres qui n'en ont pas, pas à vider le groupe. Quand un seul membre
    est nommé, son libellé devient le seul choix — l'effet recherché.
    """
    candidats = []
    for libelle in libelles:
        libelle = (libelle or "").strip()
        if libelle and libelle not in candidats:
            candidats.append(libelle)
    return candidats


def libelles_incoherents(libelles) -> bool:
    """Le groupe demande-t-il une harmonisation de ses libellés ?

    Vrai si ses membres portent des libellés différents, **ou** si aucun n'en
    porte : un groupe entièrement anonyme ne produisait qu'un seul libellé
    distinct ({""}) et passait donc pour cohérent, ce qui faisait du cas le plus
    grave le seul à n'être jamais signalé.
    """
    descs = {(libelle or "").strip() for libelle in libelles}
    return len(descs) > 1 or descs == {""}

from ..core.config import Config, pluralize
from ..utils.error_handler import handle_ui_errors
from ..core.logger import app_logger
from .pieces_list_service import PieceRelationsPopup, _format_piece_edit_history
from .style_manager import StyleManager, inline_icon_html
from .piece_picker_dialog import PiecePickerDialog, RefTagList
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QShortcut
from .saisie_relation import SaisieRelation
from .ligne_reference_associee import (AUCUNE, INCONNUE, JUMELLE, PROPOSEE, VIDE,
                                       LigneReferenceAssociee)
from ..utils.rapprochement_fiche.associee import (ORIGINES_ASSOCIEES, autres_origines,
                                                  origine_associable, origine_declaree,
                                                  origine_du_format)
from ..utils.ouverture_modale import ouvrir_modal
from ..utils.boites import demander_oui_non, choisir_fichier_a_enregistrer, saisir_texte, choisir_element

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
        
        self._data_loaded = False
        self._init_ui()
        # Afficher la fenêtre d'abord, charger les données après le premier rendu
        # (sauf si open_on_piece a déjà déclenché un chargement synchrone entre-temps)
        QTimer.singleShot(50, self._initial_load)

    def _initial_load(self):
        """Chargement initial différé — ignoré si les données sont déjà chargées."""
        if not self._data_loaded:
            self._load_pieces_data()

    def showEvent(self, event):
        """La fenêtre est mise en cache par piece_management_service et réutilisée :
        recharger les données à chaque ré-affichage, sinon elles restent figées
        au premier chargement (listes et statuts périmés)."""
        super().showEvent(event)
        if self._data_loaded:
            self._load_pieces_data()

    def _init_ui(self):
        """Initialiser l'interface utilisateur"""
        layout = QVBoxLayout()

        # Titre et statistiques
        header_layout = QHBoxLayout()
        title_label = QLabel("Gestionnaire des pièces")
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
        # ⌘F : curseur dans la recherche du gestionnaire
        QShortcut(QKeySequence.Find, self,
                  activated=lambda: (self.search_input.setFocus(), self.search_input.selectAll()))
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
                ('all',       'Toutes',       'fa5s.list',            '#495057'),
                ('orphan',    'Orphelines',   'fa5s.unlink',          '#c0392b'),
                ('phantom',   'Fantômes',     'fa5s.ghost',           '#7f8c8d'),
                # Distinct de « Fantômes » : une réf jamais importée peut très bien
                # porter un libellé (hérité d'une voisine), et une pièce bien réelle
                # peut n'en avoir aucun si le fichier source n'en fournissait pas.
                ('unlabeled', 'Sans libellé', 'fa5s.question-circle', '#d35400'),
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
                ('twin_missing', 'Jumelle à renseigner', 'fa5s.clone',              '#8e44ad'),
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
            cluster_title.setStyleSheet(StyleManager.TEXTE_ESTOMPE)
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
                if key == 'twin_missing':
                    btn.setToolTip("Pièces Whirlpool, Indesit ou Beko (hors fantômes) dont la "
                                   "réf. associée n'est pas renseignée : ni jumelle, ni « Aucune ». "
                                   "Une réf. seulement proposée par la fiche du site en fait partie.")

            cluster_col.addLayout(cluster_row)
            filter_layout.addLayout(cluster_col)

        self._filter_group.buttonClicked.connect(self._on_filter_changed)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Tableau des pièces
        self.pieces_table = PiecesTableWidget()
        self.pieces_table.setColumnCount(6)
        self.pieces_table.setHorizontalHeaderLabels([
            "Référence pièce", "Libellé", "Nb", "Statut", "Types d'appareils", ""
        ])

        # Configuration du tableau — Libellé en Interactive (redimensionnable par l'utilisateur),
        # Types d'Appareils en Stretch pour absorber l'espace résiduel.
        header = self.pieces_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Référence
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Libellé (redimensionnable)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)        # Nb
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Statut
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)      # Types d'Appareils
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)        # Actions
        self.pieces_table.setColumnWidth(0, 130)   # Référence Pièce
        self.pieces_table.setColumnWidth(1, 220)   # Libellé
        self.pieces_table.setColumnWidth(2, 55)    # Nb
        self.pieces_table.setColumnWidth(3, 130)   # Statut (78 tronquait « → … », « Remp… »)
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
        self._loading_label = QLabel("Chargement des pièces…")
        self._loading_label.setStyleSheet(StyleManager.TITRE_SECTION)
        spinner_row.addWidget(self._loading_label)
        loading_layout.addLayout(spinner_row)

        # Barre de progression fine indéterminée
        loading_bar = QProgressBar()
        loading_bar.setRange(0, 0)
        loading_bar.setTextVisible(False)
        loading_bar.setFixedHeight(6)
        loading_bar.setMaximumWidth(400)
        loading_bar.setStyleSheet(StyleManager.BARRE_PROGRESSION_DISCRETE)
        loading_layout.addWidget(loading_bar, 0, Qt.AlignHCenter)

        self._table_stack.addWidget(loading_page)    # index 0 : chargement
        self._table_stack.addWidget(self.pieces_table)  # index 1 : tableau
        self._table_stack.setCurrentIndex(0)

        main_splitter.addWidget(self._table_stack)

        # ── Droite : panneau de détail ────────────────────────────────────────
        side_panel = QWidget()
        side_panel.setMinimumWidth(200)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(0, 4, 4, 4)  # gauche : l'espace est la poignée (8 px)
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
        self.succession_status_label.setStyleSheet(StyleManager.TEXTE_GRIS_PETIT)
        self.succession_status_label.setWordWrap(True)
        side_layout.addWidget(self.succession_status_label)

        # ── 2 zones : Équivalences (prioritaire) / Succession + actions ────────
        sections_splitter = QSplitter(Qt.Vertical)
        sections_splitter.setChildrenCollapsible(False)

        # Section "≡ Équivalences" — zone prioritaire en haut
        equiv_section = QFrame()
        equiv_section.setObjectName("equivSection")
        equiv_section.setStyleSheet(StyleManager.side_card("equivSection"))
        self.equiv_section = equiv_section
        eq_sec_layout = QVBoxLayout(equiv_section)
        eq_sec_layout.setContentsMargins(6, 4, 6, 4)
        eq_sec_layout.setSpacing(3)

        equiv_hdr = QHBoxLayout()
        lbl_eq = QLabel("≡ Équivalences")
        lbl_eq.setStyleSheet("color: #8e44ad; font-weight: bold; font-size: 11px;")
        equiv_hdr.addWidget(lbl_eq)
        equiv_hdr.addStretch()
        self.btn_link_equiv = QPushButton()
        self.btn_link_equiv.setIcon(qta.icon('fa5s.plus', color='#8e44ad'))
        self.btn_link_equiv.setIconSize(QSize(11, 11))
        self.btn_link_equiv.setFixedSize(20, 20)
        self.btn_link_equiv.setToolTip("Ajouter une équivalence")
        self.btn_link_equiv.setStyleSheet(
            "QPushButton { border: none; border-radius: 3px; background: transparent; }"
            "QPushButton:hover { background: rgba(142,68,173,0.12); }"
        )
        self.btn_link_equiv.setFlat(True)
        self.btn_link_equiv.setEnabled(False)
        self.btn_link_equiv.clicked.connect(self._on_link_equiv)
        equiv_hdr.addWidget(self.btn_link_equiv)
        eq_sec_layout.addLayout(equiv_hdr)

        # Réf. associée (jumelle Whirlpool / Indesit / Beko) : une équivalente
        # particulière, en tête de la carte ; masquée pour les autres pièces
        self.ligne_associee = LigneReferenceAssociee()
        self.ligne_associee.ajouter.connect(self._on_ajouter_associee)
        self.ligne_associee.retirer.connect(self._on_retirer_associee)
        self.ligne_associee.inverser.connect(self._on_inverser_associee)
        self.ligne_associee.confirmer.connect(self._on_confirmer_associee)
        self.ligne_associee.refuser.connect(self._on_refuser_associee)
        self.ligne_associee.marquer_aucune.connect(self._on_marquer_aucune_associee)
        self.ligne_associee.oublier_aucune.connect(self._on_oublier_aucune_associee)
        self.ligne_associee.declarer_groupe.connect(self._on_declarer_groupe)
        self.ligne_associee.oublier_groupe.connect(self._on_oublier_groupe)
        self.ligne_associee.ref_clicked.connect(self._search_in_manager)
        self.ligne_associee.ref_right_clicked.connect(self._on_chip_right_click)
        eq_sec_layout.addWidget(self.ligne_associee)

        # Saisie directe (sans fenêtre) : Espace / Entrée / collage écrit aussitôt
        self._saisies_relation = {}
        self.saisie_equiv = self._creer_saisie(self.EQUIVALENTES, "Réf. équivalente…")
        eq_sec_layout.addWidget(self.saisie_equiv)

        self.equiv_status_label = QLabel("")
        self.equiv_status_label.setStyleSheet(StyleManager.TEXTE_GRIS_PETIT)
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
        # Simple conteneur : ce sont ses deux cartes (Remplace / Remplacée par) qui
        # portent le fond ; plus de cadre englobant.
        succession_combined.setFrameShape(QFrame.NoFrame)
        succ_combined_layout = QVBoxLayout(succession_combined)
        succ_combined_layout.setContentsMargins(0, 0, 0, 0)  # cartes alignées sur celle des équivalences
        succ_combined_layout.setSpacing(4)

        succession_row = QHBoxLayout()
        succession_row.setSpacing(8)  # même écart que les poignées entre cartes

        # Colonne "↑ Remplace"
        replaces_section = QFrame()
        replaces_section.setObjectName("replacesSection")
        replaces_section.setStyleSheet(StyleManager.side_card("replacesSection"))
        self.replaces_section = replaces_section
        rep_sec_layout = QVBoxLayout(replaces_section)
        rep_sec_layout.setContentsMargins(6, 4, 6, 4)
        rep_sec_layout.setSpacing(3)

        replaces_hdr = QHBoxLayout()
        lbl_rep = QLabel("↑ Remplace")
        lbl_rep.setStyleSheet("color: #2980b9; font-weight: bold; font-size: 11px;")
        replaces_hdr.addWidget(lbl_rep)
        replaces_hdr.addStretch()
        self.btn_mark_replaces = QPushButton()
        self.btn_mark_replaces.setIcon(qta.icon('fa5s.plus', color='#2980b9'))
        self.btn_mark_replaces.setIconSize(QSize(11, 11))
        self.btn_mark_replaces.setFixedSize(20, 20)
        self.btn_mark_replaces.setToolTip("Ajouter une référence remplacée")
        self.btn_mark_replaces.setStyleSheet(
            "QPushButton { border: none; border-radius: 3px; background: transparent; }"
            "QPushButton:hover { background: rgba(41,128,185,0.12); }"
        )
        self.btn_mark_replaces.setFlat(True)
        self.btn_mark_replaces.clicked.connect(self._on_mark_replaces)
        replaces_hdr.addWidget(self.btn_mark_replaces)
        rep_sec_layout.addLayout(replaces_hdr)
        self.saisie_remplace = self._creer_saisie(self.REMPLACE, "Ancienne réf. remplacée…")
        rep_sec_layout.addWidget(self.saisie_remplace)

        self.replaces_tag_list = RefTagList()
        self.replaces_tag_list.enable_full_height_mode()
        self.replaces_tag_list.ref_removed.connect(self._on_remove_replaces)
        rep_sec_layout.addWidget(self.replaces_tag_list, 1)
        succession_row.addWidget(replaces_section)

        # Colonne "↳ Remplacée par"
        superseded_section = QFrame()
        superseded_section.setObjectName("superseded_section")
        superseded_section.setStyleSheet(StyleManager.side_card("superseded_section"))
        self.superseded_section = superseded_section
        sup_sec_layout = QVBoxLayout(superseded_section)
        sup_sec_layout.setContentsMargins(6, 4, 6, 4)
        sup_sec_layout.setSpacing(3)

        superseded_hdr = QHBoxLayout()
        lbl_sup = QLabel("↳ Remplacée par")
        lbl_sup.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 11px;")
        superseded_hdr.addWidget(lbl_sup)
        superseded_hdr.addStretch()
        self.btn_mark_superseded = QPushButton()
        self.btn_mark_superseded.setIcon(qta.icon('fa5s.plus', color='#e67e22'))
        self.btn_mark_superseded.setIconSize(QSize(11, 11))
        self.btn_mark_superseded.setFixedSize(20, 20)
        self.btn_mark_superseded.setToolTip("Déclarer remplacée par une autre référence")
        self.btn_mark_superseded.setStyleSheet(
            "QPushButton { border: none; border-radius: 3px; background: transparent; }"
            "QPushButton:hover { background: rgba(230,126,34,0.12); }"
        )
        self.btn_mark_superseded.setFlat(True)
        self.btn_mark_superseded.clicked.connect(self._on_mark_superseded)
        superseded_hdr.addWidget(self.btn_mark_superseded)
        sup_sec_layout.addLayout(superseded_hdr)
        self.saisie_remplacee_par = self._creer_saisie(self.REMPLACEE_PAR, "Réf. qui la remplace…")
        sup_sec_layout.addWidget(self.saisie_remplacee_par)

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
        self.btn_cancel_succession.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self.btn_cancel_succession.clicked.connect(self._on_cancel_succession)
        self.btn_cancel_succession.setVisible(False)

        self.btn_unlink_equiv = QPushButton("Retirer du groupe")
        self.btn_unlink_equiv.setIcon(qta.icon('fa5s.unlink', color='#E05252'))
        self.btn_unlink_equiv.setIconSize(QSize(11, 11))
        self.btn_unlink_equiv.setToolTip("Retirer la pièce sélectionnée de son groupe d'équivalence")
        self.btn_unlink_equiv.setEnabled(False)
        self.btn_unlink_equiv.setStyleSheet(StyleManager.DANGER_COMPACT_BUTTON)
        self.btn_unlink_equiv.setVisible(False)
        self.btn_unlink_equiv.clicked.connect(self._on_unlink_equiv)

        self.btn_mark_equivalent_group = QPushButton("Fusionner en un groupe d'équivalents")
        self.btn_mark_equivalent_group.setIcon(qta.icon('fa5s.link', color='#8e44ad'))
        self.btn_mark_equivalent_group.setIconSize(QSize(11, 11))
        self.btn_mark_equivalent_group.setToolTip(
            "Fusionner toutes les pièces sélectionnées dans un seul groupe d'équivalence")
        self.btn_mark_equivalent_group.setStyleSheet(f"{StyleManager.SECONDARY_COMPACT_BUTTON} QPushButton {{ color: #8e44ad; }}")
        self.btn_mark_equivalent_group.setVisible(False)
        self.btn_mark_equivalent_group.clicked.connect(self._on_mark_equivalent_group)

        self.btn_lier_associees = QPushButton("Lier comme réf. associées")
        self.btn_lier_associees.setIcon(qta.icon('fa5s.exchange-alt', color='#8e44ad'))
        self.btn_lier_associees.setIconSize(QSize(11, 11))
        self.btn_lier_associees.setToolTip(
            "La pièce affichée devient la principale, l'autre son associée (et son équivalente)")
        self.btn_lier_associees.setStyleSheet(f"{StyleManager.SECONDARY_COMPACT_BUTTON} QPushButton {{ color: #8e44ad; }}")
        self.btn_lier_associees.setVisible(False)
        self.btn_lier_associees.clicked.connect(self._on_lier_associees)

        self.btn_harmonize_labels = QPushButton("Harmoniser les libellés…")
        self.btn_harmonize_labels.setIcon(qta.icon('fa5s.palette', color='#d35400'))
        self.btn_harmonize_labels.setIconSize(QSize(11, 11))
        self.btn_harmonize_labels.setToolTip(
            "Les pièces équivalentes n'ont pas le même libellé — choisir celui à appliquer à tout le groupe")
        self.btn_harmonize_labels.setStyleSheet(f"{StyleManager.SECONDARY_COMPACT_BUTTON} QPushButton {{ color: #d35400; }}")
        self.btn_harmonize_labels.setVisible(False)
        self.btn_harmonize_labels.clicked.connect(self._on_harmonize_labels)

        # ── Actions de groupe (multi-sélection) ────────────────────────────
        self.btn_batch_edit_libelle = QPushButton("Modifier le libellé…")
        self.btn_batch_edit_libelle.setIcon(qta.icon('fa5s.edit', color='#1565C0'))
        self.btn_batch_edit_libelle.setIconSize(QSize(11, 11))
        self.btn_batch_edit_libelle.setToolTip(
            "Appliquer le même libellé à toutes les pièces sélectionnées")
        self.btn_batch_edit_libelle.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self.btn_batch_edit_libelle.setVisible(False)
        self.btn_batch_edit_libelle.clicked.connect(self._on_batch_edit_libelle)

        self.btn_export_selection = QPushButton("Exporter la sélection")
        self.btn_export_selection.setIcon(qta.icon('fa5s.file-export', color='#555555'))
        self.btn_export_selection.setIconSize(QSize(11, 11))
        self.btn_export_selection.setToolTip(
            "Exporter uniquement les pièces sélectionnées au format CSV")
        self.btn_export_selection.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self.btn_export_selection.setVisible(False)
        self.btn_export_selection.clicked.connect(self._export_selected_pieces)

        # Sous-sections : (titre, [boutons]) — le titre est masqué si aucun
        # bouton de la sous-section n'est visible (voir _sync_action_sections)
        self._action_sections = []
        for section_title, buttons in [
            ("SUCCESSION",   [self.btn_cancel_succession]),
            ("ÉQUIVALENCES", [self.btn_unlink_equiv, self.btn_lier_associees,
                              self.btn_harmonize_labels]),
        ]:
            title_lbl = QLabel(section_title)
            title_lbl.setStyleSheet("color: #adb5bd; font-size: 11px; font-weight: bold;")
            succ_combined_layout.addWidget(title_lbl)
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            for btn in buttons:
                btn_row.addWidget(btn)
            btn_row.addStretch()
            succ_combined_layout.addLayout(btn_row)
            self._action_sections.append((title_lbl, buttons))
        # État initial : aucune sélection → titres masqués (ils restaient affichés,
        # orphelins, jusqu'au premier changement de sélection)
        self._sync_action_sections()

        sections_splitter.addWidget(succession_combined)
        sections_splitter.setStretchFactor(0, 3)
        sections_splitter.setStretchFactor(1, 2)

        side_layout.addWidget(sections_splitter, 1)

        # Glisser une réf. d'une carte vers une autre l'y ajoute (copie : le lien
        # d'origine reste) ; dépôt sur toute la carte
        self._cartes_depot = {equiv_section: self.EQUIVALENTES,
                              replaces_section: self.REMPLACE,
                              superseded_section: self.REMPLACEE_PAR}
        for carte in self._cartes_depot:
            carte.setAcceptDrops(True)
            carte.installEventFilter(self)
        for liste in (self.equiv_tag_list, self.replaces_tag_list, self.superseded_by_tag_list):
            liste.rendre_glissable()

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
        self._btn_selection_popup.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }"
        )
        self._btn_selection_popup.setVisible(False)
        self._btn_selection_popup.clicked.connect(self._show_selection_popup)
        _ab_layout.addWidget(self._btn_selection_popup)
        _ab_layout.setAlignment(self._btn_selection_popup, Qt.AlignVCenter)

        _ab_sep = QFrame()
        _ab_sep.setFrameShape(QFrame.VLine)
        _ab_sep.setFrameShadow(QFrame.Sunken)
        _ab_layout.addWidget(_ab_sep)

        _ab_layout.addWidget(self.btn_mark_equivalent_group)
        _ab_layout.addWidget(self.btn_batch_edit_libelle)
        _ab_layout.addWidget(self.btn_export_selection)
        _ab_layout.addStretch()

        _btn_deselect_bar = QPushButton("Désélectionner tout")
        _btn_deselect_bar.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        _btn_deselect_bar.clicked.connect(self._clear_sticky_selection)
        _ab_layout.addWidget(_btn_deselect_bar)

        layout.addWidget(self._action_bar)

        # Boutons d'action (footer)
        # Style par défaut (rôle Secondaire) : plus de style local
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        # "Chercher dans l'app" déplacé dans le menu contextuel (clic droit sur une ligne)

        export_btn = QPushButton("Exporter la liste")
        export_btn.setIcon(qta.icon('fa5s.file-export', color='#555555'))
        export_btn.setIconSize(QSize(12, 12))
        export_btn.clicked.connect(self._export_pieces)
        buttons_layout.addWidget(export_btn)

        close_btn = QPushButton("Fermer")
        close_btn.setIcon(qta.icon('fa5s.times', color='#495057'))
        close_btn.setIconSize(QSize(12, 12))
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
        Affiche le spinner, remplit la liste, puis déclenche le chargement complet."""
        # Spinner visible pour tout chargement/rechargement (pas seulement le premier)
        is_reload = bool(getattr(self, 'all_pieces_data', None))
        if hasattr(self, '_loading_label'):
            self._loading_label.setText("Actualisation…" if is_reload else "Chargement des pièces…")
        if hasattr(self, '_table_stack'):
            self._table_stack.setCurrentIndex(0)
        self._loading_phase = 1  # empêche _update_table_display de switcher vers le tableau
        QApplication.setOverrideCursor(Qt.WaitCursor)

        results = self.db_manager.lister_pieces_apercu() or []
        self.all_pieces_data = results
        self.all_statuses = {}
        self._data_loaded = True
        self.stats_label.setText(f"{pluralize(len(results), 'référence')} — chargement des données…")
        self._update_table_display()
        # Phase 2 : données complètes après le premier rendu
        QTimer.singleShot(0, self._load_pieces_data_full)

    @handle_ui_errors(log_prefix="Erreur chargement complet pièces", show_message=True)
    def _load_pieces_data_full(self, checked=False):
        """Phase 2 : chargement complet avec comptages, types et statuts de succession."""
        results = self.db_manager.lister_pieces_completes() or []

        total_pieces = len(results)
        orphan_pieces = len([r for r in results if r[2] == 0])
        phantom_pieces = len([r for r in results if r[4] == 1])
        unlabeled_pieces = len([r for r in results if not (r[1] or '').strip()])
        total_associations = sum(r[2] for r in results)

        from src.core.config import pluralize
        phantom_str = f"  •  {pluralize(phantom_pieces, 'fantôme')}" if phantom_pieces else ""
        # Compté à part du fantôme : les deux ensembles se recoupent sans se
        # confondre (relevé du 2026-09-22 : 98 fantômes nommées, 76 pièces
        # bien réelles sans libellé).
        unlabeled_str = (f"  •  {pluralize(unlabeled_pieces, 'sans libellé', 'sans libellé')}"
                         if unlabeled_pieces else "")
        def _milliers(nombre: int) -> str:
            # 4771467 → « 4 771 467 » (espace fine insécable, usage français)
            return f"{nombre:,}".replace(",", "\u202f")

        self.stats_label.setText(
            f"{_milliers(total_pieces)} référence{'s' if total_pieces > 1 else ''}  •  "
            f"{pluralize(orphan_pieces, 'orpheline')}"
            f"{phantom_str}{unlabeled_str}  •  "
            f"{_milliers(total_associations)} association{'s' if total_associations > 1 else ''}"
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
                status['labels_differ'] = libelles_incoherents(
                    self._desc_by_ref.get(r, "") for r in group_refs
                )
            else:
                status['labels_differ'] = False

        # Jumelle à renseigner : Whirlpool / Indesit / Beko, hors fantômes, sans
        # réponse (ni paire, ni « aucune ») — une requête, 10 ms pour 6 300 réfs
        try:
            renseignees = self.db_manager.refs_avec_reponse_associee()
        except Exception as exc:
            app_logger.warning(f"Réfs associées non lues pour le filtre : {exc}")
            renseignees = None
        if renseignees is not None:
            for r in results:
                ref = r[0]
                if (ref and ref not in renseignees and not (len(r) > 4 and r[4] == 1)
                        and origine_associable(ref)):
                    self.all_statuses.setdefault(ref, {})['jumelle_a_renseigner'] = True

        # Phase 2 terminée : autoriser le switch vers le tableau
        self._loading_phase = 0
        QApplication.restoreOverrideCursor()
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
        """Gérer le survol entre le tableau et le widget d'actions flottant, et le
        dépôt d'une réf. glissée sur une carte de relations."""
        # Une exception ici fait avorter PyQt (plantage sans trace) : les cartes
        # reçoivent des événements (style global, polish) dès l'installation du
        # filtre, avant que le reste de la fenêtre existe — elles ne vont donc
        # jamais plus loin que leur propre traitement.
        if obj in getattr(self, '_cartes_depot', {}):
            try:
                traite = self._depot_carte(obj, event)
            except Exception as exc:
                app_logger.error(f"Glisser-déposer sur une carte : {exc}")
                traite = None
            return traite if traite is not None else super().eventFilter(obj, event)
        flottant = getattr(self, '_floating_actions', None)
        if flottant is None:
            return super().eventFilter(obj, event)
        if obj is self.pieces_table.viewport() and event.type() == QEvent.Leave:
            # Cacher le widget flottant seulement si le curseur ne se trouve pas dessus
            cursor_pos = self.pieces_table.viewport().mapFromGlobal(QCursor.pos())
            if not self._floating_actions.geometry().contains(cursor_pos):
                self._floating_actions.setVisible(False)
        elif obj is self._floating_actions and event.type() == QEvent.Leave:
            self._floating_actions.setVisible(False)
        return super().eventFilter(obj, event)

    # ── Glisser une réf. vers une carte ─────────────────────────────────────

    def _refs_glissees(self, carte, event) -> list:
        """Réfs d'un glisser acceptable sur `carte` ([] sinon) : du texte, pas
        venu de cette même carte, et une carte dont la saisie est active."""
        md = event.mimeData()
        if md is None or not md.hasText():
            return []
        source = event.source()
        if source is not None and carte.isAncestorOf(source):
            return []
        saisie = self._saisies_relation.get(self._cartes_depot[carte])
        if saisie is None or not saisie.champ.isEnabled():
            return []
        from ..utils.text_utils import decouper_refs
        return decouper_refs(md.text())

    def _surligner_carte(self, carte, actif: bool):
        nom = carte.objectName()
        carte.setStyleSheet(StyleManager.side_card_depot(nom) if actif
                            else StyleManager.side_card(nom))

    def _depot_carte(self, carte, event):
        """Glisser-déposer sur une carte ; None = événement non traité ici."""
        genre = event.type()
        if genre in (QEvent.DragEnter, QEvent.DragMove):
            if self._refs_glissees(carte, event):
                event.setDropAction(Qt.CopyAction)
                event.accept()
                self._surligner_carte(carte, True)
            else:
                event.ignore()
            return True
        if genre == QEvent.DragLeave:
            self._surligner_carte(carte, False)
            return True
        if genre == QEvent.Drop:
            self._surligner_carte(carte, False)
            refs = self._refs_glissees(carte, event)
            if not refs:
                event.ignore()
                return True
            event.setDropAction(Qt.CopyAction)     # copie : la carte d'origine garde la réf.
            event.accept()
            relation = self._cartes_depot[carte]
            # Après la fin du glisser (la boucle du QDrag tient encore la puce)
            QTimer.singleShot(0, lambda: self._sur_saisie_relation(relation, refs))
            return True
        return None

    def keyPressEvent(self, event):
        """Raccourcis clavier sur le tableau de pièces."""
        key = event.key()
        if key == Qt.Key_F2:
            self._edit_selected_piece()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            row = self.pieces_table.currentRow()
            if row >= 0:
                self._delete_at_row_or_selection(row)
            elif self._sticky_selected_refs:
                # Sélection entièrement hors de la vue filtrée : supprimer la sticky
                self._delete_selected_pieces()
        else:
            super().keyPressEvent(event)

    def _update_table_display(self):
        """Mettre à jour l'affichage du tableau avec filtrage.
        Les signaux sont bloqués pendant la reconstruction pour éviter que
        setRowCount() ne déclenche itemSelectionChanged → sections cachées."""
        # Basculer vers le tableau uniquement quand la phase 2 est terminée
        if (hasattr(self, '_table_stack')
                and self._table_stack.currentIndex() == 0
                and not getattr(self, '_loading_phase', 0)):
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

        _phantom_font = QFont()
        _phantom_font.setItalic(True)
        _phantom_color = QColor(170, 170, 170)

        for row_idx, row_data in enumerate(filtered_data):
            self._remplir_ligne_piece(row_idx, row_data, statuses, _phantom_font, _phantom_color)

        self.pieces_table.blockSignals(False)
        self._restaurer_selection_pieces()

    def _remplir_ligne_piece(self, row_idx, row_data, statuses, _phantom_font, _phantom_color):
        """Les 5 colonnes d'une ligne du tableau des pièces (signaux déjà bloqués)."""
        from src.core.config import pluralize
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
        if not (description or "").strip():
            # Une cellule vide ne se voit pas : sans fond, la référence anonyme
            # se confond avec les autres et personne ne la corrige jamais.
            desc_item.setBackground(QColor(*Config.Colors.MISSING_LABEL))
            desc_item.setToolTip("Aucun libellé — à compléter")
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
        _icon, _status_text, _status_tip = self._statut_piece(
            is_phantom, is_obsolete, status, status_info)
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

    @staticmethod
    def _statut_piece(is_phantom, is_obsolete, status, status_info):
        """(icône, texte court, infobulle) de la colonne Statut, par ordre de
        priorité : fantôme, obsolète, remplacée, remplace, équivalente, courante."""
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
            # L'icône est déjà une flèche : pas de « → » en plus dans le texte
            _status_text = ref_new if ref_new else "Remplacée"
            _status_tip = f"Remplacée par {ref_new}" if ref_new else "Remplacée"
        elif status == 'replacing':
            _raw = status_info.get('refs_old') or []
            # refs_old peut être une chaîne CSV (ex. "REF1, REF2") ou une liste
            if isinstance(_raw, str):
                refs_old = [r.strip() for r in _raw.split(',') if r.strip()]
            else:
                refs_old = list(_raw)
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
        return _icon, _status_text, _status_tip

    def _restaurer_selection_pieces(self):
        """Après reconstruction du tableau : resélectionner les pièces mémorisées
        (sticky) encore visibles et remettre les panneaux en cohérence."""
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
            
    # Filtres de statut (boutons-filtres) : prédicat (ligne, statuts) -> bool.
    # Ligne = (ref_piece, description, nb_appareils, types, is_phantom) ;
    # statuts = {ref: {'status', 'is_obsolete', 'equivalents', 'labels_differ'}}.
    # Un filtre absent de la table ('all') ne filtre rien.
    _FILTRES_STATUT = {
        'orphan':       lambda r, st: r[2] == 0,
        'phantom':      lambda r, st: len(r) > 4 and r[4] == 1,
        'unlabeled':    lambda r, st: not (r[1] or '').strip(),
        'superseded':   lambda r, st: st.get(r[0] or '', {}).get('status') == 'superseded',
        'obsolete':     lambda r, st: st.get(r[0] or '', {}).get('is_obsolete'),
        'replacing':    lambda r, st: st.get(r[0] or '', {}).get('status') == 'replacing',
        'equivalent':   lambda r, st: st.get(r[0] or '', {}).get('equivalents'),
        'current':      lambda r, st: (st.get(r[0] or '', {}).get('status') == 'current'
                                       and not st.get(r[0] or '', {}).get('is_obsolete')
                                       and not (len(r) > 4 and r[4] == 1)),
        'inconsistent': lambda r, st: st.get(r[0] or '', {}).get('labels_differ'),
        'twin_missing': lambda r, st: st.get(r[0] or '', {}).get('jumelle_a_renseigner'),
    }

    @staticmethod
    def _filtrer_par_texte(lignes, search_text: str):
        """Filtre texte (référence + libellé, insensible à la casse) ; « ; »
        sépare plusieurs termes, dont un seul suffit."""
        if not search_text:
            return lignes
        if ';' in search_text:
            parts = [p.strip() for p in search_text.split(';') if p.strip()]
            return [r for r in lignes
                    if any(p in (r[0] or "").lower() or p in (r[1] or "").lower()
                           for p in parts)]
        return [r for r in lignes
                if search_text in (r[0] or "").lower()
                or search_text in (r[1] or "").lower()]

    def _get_filtered_data(self):
        """Obtenir les données filtrées selon les critères"""
        if not hasattr(self, 'all_pieces_data'):
            return []

        # Filtre texte (référence + libellé) — supporte ; pour multi-refs
        filtered = PiecesManagerWindow._filtrer_par_texte(self.all_pieces_data,
                                                          self.search_input.text().lower().strip())

        # Filtre actif
        predicat = PiecesManagerWindow._FILTRES_STATUT.get(getattr(self, '_active_filter', 'all'))
        if predicat is not None:
            statuses = getattr(self, 'all_statuses', {})
            filtered = [r for r in filtered if predicat(r, statuses)]

        return filtered
        
    def _filter_pieces(self):
        """Filtrer les pièces selon les critères"""
        self._update_table_display()

    def _on_filter_changed(self, btn):
        """Changer le filtre actif via les boutons rapides."""
        self._active_filter = btn.property('filter_key')
        self._update_table_display()

    def _on_double_click_piece(self, item):
        """Double-clic sur une ligne → édition immédiate.
        Le champ correspondant à la colonne double-cliquée est présélectionné
        dans le dialogue (colonne 1 = libellé, sinon référence)."""
        focus_field = 'desc' if item.column() == 1 else 'ref'
        self._edit_selected_piece(focus_field=focus_field)

    def open_on_piece(self, ref: str):
        """Ouvrir le gestionnaire et se positionner sur la pièce donnée.
        Point d'entrée public utilisé par piece_management_service."""
        was_visible = self.isVisible()
        self.show()   # showEvent recharge les données si la fenêtre était cachée
        self.raise_()
        self.activateWindow()
        # Fenêtre déjà visible (pas de showEvent) ou chargement initial encore
        # différé (QTimer 50ms pas écoulé) : recharger avant de chercher la ref,
        # sinon la recherche s'exécute sur une table périmée ou vide.
        if was_visible or not self._data_loaded:
            self._load_pieces_data()
        self._search_in_manager(ref)

    def editer_libelle(self, ref: str):
        """Ouvrir le gestionnaire sur la pièce, puis « Modifier la pièce » avec le
        curseur dans le champ Libellé. Point d'entrée public (lien de l'historique
        et raccourci ⌘⇧L) : l'enregistrement passe par le chemin habituel
        (_do_edit_piece — historique, propagation aux équivalents, garde
        contre l'effacement)."""
        self.open_on_piece(ref)
        rows = self.db_manager.lire_libelle_piece(ref)
        libelle_actuel = (rows[0][0] or "") if rows else ""
        self._do_edit_piece(ref, libelle_actuel, focus_field='desc')

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
                # selectRow est un no-op SILENCIEUX si la ligne était déjà
                # sélectionnée (sélection résiduelle déplacée par Qt pendant le
                # refill sous blockSignals) : itemSelectionChanged ne part pas
                # et les panneaux restent sur l'ancienne pièce. Synchroniser
                # explicitement (idempotent si le signal a bien été émis).
                self._on_piece_selected()
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
        dlg.resize(420, 140)

        form_layout = QVBoxLayout(dlg)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(16, 14, 16, 12)

        champs, ref_input, lib_input = _formulaire_piece()
        form_layout.addLayout(champs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setAutoDefault(False)
        btn_ok = QPushButton("Créer")
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
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
        """Supprimer la pièce à la ligne, ou toute la sélection sticky si la ligne
        en fait partie (sélection multi). La sélection sticky est la source de
        vérité unique, comme pour les actions batch (cohérence du périmètre)."""
        item = self.pieces_table.item(row, 0)
        ref = (item.data(Qt.UserRole) or item.text()) if item else None
        if ref and ref in self._sticky_selected_refs and len(self._sticky_selected_refs) > 1:
            self._delete_selected_pieces()
        else:
            self._delete_piece_at_row(row)

    def _on_obsolete_at_row(self, row: int):
        """Marquer/retirer l'obsolescence pour la pièce à la ligne donnée."""
        item = self.pieces_table.item(row, 0)
        if not item:
            return
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

        Convention native (macOS/Windows) :
        - clic SIMPLE (sans modificateur) → REMPLACE : la sélection repart de
          zéro, on ne garde que les lignes visibles sélectionnées. Les refs
          composées lors de recherches précédentes sont abandonnées (évite la
          sélection « surprise » dont l'origine est introuvable).
        - Ctrl/Cmd/Maj tenu → COMPOSE : on cumule, y compris à travers plusieurs
          recherches successives (les refs hors-écran sont préservées).

        Cette méthode n'est appelée que sur une sélection pilotée par
        l'utilisateur : les reconstructions programmatiques du tableau bloquent
        les signaux (cf. _update_table_display), donc keyboardModifiers() reflète
        bien le geste en cours."""
        visible_refs = set()
        for row in range(self.pieces_table.rowCount()):
            item = self.pieces_table.item(row, 0)
            if item:
                visible_refs.add(item.data(Qt.UserRole) or item.text())
        visible_selected = set(self._get_visible_selected_refs())

        mods = QApplication.keyboardModifiers()
        additive = bool(mods & (Qt.ControlModifier | Qt.MetaModifier | Qt.ShiftModifier))
        if additive:
            # Composer : retirer les refs visibles désélectionnées, ajouter les nouvelles
            self._sticky_selected_refs -= (visible_refs - visible_selected)
            self._sticky_selected_refs |= visible_selected
        else:
            # Remplacer : on repart de la seule sélection visible
            self._sticky_selected_refs = set(visible_selected)
        self._update_sticky_selection_indicator()

    def _update_sticky_selection_indicator(self):
        """Afficher/masquer la barre d'actions contextuelle selon la sélection."""
        n = len(self._sticky_selected_refs)
        if n > 0:
            from src.core.config import pluralize
            refs_sorted = sorted(self._sticky_selected_refs)
            # Refs sélectionnées absentes de la vue filtrée actuelle : on le signale
            # pour rendre la composition multi-recherche découvrable.
            visible_refs = set()
            for row in range(self.pieces_table.rowCount()):
                item = self.pieces_table.item(row, 0)
                if item:
                    visible_refs.add(item.data(Qt.UserRole) or item.text())
            offscreen = len(self._sticky_selected_refs - visible_refs)
            label = pluralize(n, 'pièce sélectionnée', 'pièces sélectionnées')
            if offscreen:
                label += f"  ·  {offscreen} hors écran"
            self._action_bar_label.setText(label)
            self._action_bar_label.setToolTip(
                "<html>" + "<br>".join(_html.escape(r) for r in refs_sorted) + "</html>"
            )
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

        # Récupérer les libellés en une seule requête batch
        desc_rows = self.db_manager.lire_libelles_pieces(refs)
        desc_map = {r[0]: (r[1] or "") for r in desc_rows}

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
            rl.setSpacing(6)
            lbl_ref = QLabel(ref)
            lbl_ref.setStyleSheet("font-size: 11px; color: #212529; font-weight: 500;")
            lbl_ref.setMinimumWidth(80)
            rl.addWidget(lbl_ref)
            desc = desc_map.get(ref, "")
            if desc:
                MAX_DESC = 38
                desc_display = desc[:MAX_DESC] + "…" if len(desc) > MAX_DESC else desc
                lbl_desc = QLabel(desc_display)
                lbl_desc.setStyleSheet("font-size: 11px; color: #868e96; font-style: italic;")
                lbl_desc.setToolTip("<html>" + _html.escape(desc) + "</html>")
                rl.addWidget(lbl_desc, 1)
            else:
                rl.addStretch()
            btn_x = QPushButton()
            btn_x.setIcon(qta.icon('fa5s.times', color='#868e96'))
            btn_x.setIconSize(QSize(9, 9))
            btn_x.setFixedSize(18, 18)
            btn_x.setStyleSheet(
                "QPushButton { border: none; padding: 0; background: transparent; }"
                "QPushButton:hover { background: #f8d7da; border-radius: 3px; }"
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
        # Resynchroniser la pièce courante + panneau latéral : ce mutateur
        # contourne _on_piece_selected (blockSignals), il faut donc recalculer
        # l'état affiché à la main, sinon l'en-tête/les sections gardent la
        # pièce retirée (incohérence d'affichage après désélection).
        self._resync_after_selection_mutation()
        if self._sticky_selected_refs:
            self._show_selection_popup()

    def _resync_after_selection_mutation(self):
        """Recalculer la pièce courante et rafraîchir le panneau latéral après
        une mutation DIRECTE de _sticky_selected_refs (popover ×) qui ne passe
        pas par _on_piece_selected. Garde l'affichage cohérent avec la sélection."""
        if self._current_ref_piece in self._sticky_selected_refs:
            target = self._current_ref_piece
        elif self._sticky_selected_refs:
            # La pièce courante a été retirée : reprendre la dernière restante
            target = sorted(self._sticky_selected_refs)[-1]
        else:
            target = None
        self._current_ref_piece = target
        if target:
            self._update_panel_header(target)
        else:
            self.panel_header_label.setText("—")
        self._refresh_succession_panel(target)
        self._refresh_equivalence_panel(target)

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
        # isHidden() et non isVisible() : isVisible() vaut False tant que la
        # fenêtre n'est pas affichée, même pour un bouton destiné à apparaître.
        for title_lbl, buttons in getattr(self, '_action_sections', []):
            title_lbl.setVisible(any(not b.isHidden() for b in buttons))

    def _refresh_succession_panel_impl(self, ref_piece):
        """Mettre à jour le panneau Succession pour la pièce courante (dernière sélectionnée)."""
        selected = self._get_selected_refs()
        n = len(selected)
        has_selection = n > 0

        # ── Aucune sélection ──────────────────────────────────────────────
        # Option B : les sections restent TOUJOURS visibles (vidées) pour un
        # layout stable — comme le fait déjà ≡ Équivalences. Plus aucun bloc
        # ne « disparaît » quand rien n'est sélectionné.
        # Messages d'état vide : seulement en sélection unique (sinon trompeurs)
        _single = has_selection and ref_piece is not None and n == 1
        self.superseded_by_tag_list.set_empty_text("Non remplacée" if _single else "")
        self.replaces_tag_list.set_empty_text("Ne remplace aucune référence" if _single else "")

        if not has_selection or ref_piece is None:
            self.succession_status_label.setText("Sélectionnez une pièce pour voir son statut.")
            self.succession_status_label.setStyleSheet(StyleManager.TEXTE_GRIS_MOYEN)
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
            self.succession_status_label.setStyleSheet(StyleManager.TEXTE_GRIS_MOYEN)
            # Sections visibles mais vidées : les chips n'ont pas de sens en
            # multi-sélection, les actions passent par les boutons batch.
            self.superseded_by_tag_list.set_refs([], '#e67e22')
            self.replaces_tag_list.set_refs([], '#2980b9')
            self.superseded_section.setVisible(True)
            self.replaces_section.setVisible(True)
            self.btn_mark_superseded.setEnabled(True)
            # Une réf. n'a qu'une remplaçante : « Remplace » vise une seule pièce
            self.btn_mark_replaces.setEnabled(False)
            self.btn_mark_replaces.setToolTip(
                "Une réf. n'a qu'une remplaçante : sélectionnez une seule pièce")
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
            self.succession_status_label.setText(
                f"{inline_icon_html('fa5s.exclamation-triangle', '#c0392b', 12)}&nbsp;Obsolète")
            self.succession_status_label.setStyleSheet(
                "color: #c0392b; font-size: 12px; font-weight: bold;")
        elif not ref_new and not predecessors:
            self.succession_status_label.setText(
                f"{inline_icon_html('fa5s.check-circle', '#2e7d32', 12)}&nbsp;Référence courante")
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
        self.btn_mark_replaces.setToolTip("Ajouter des références remplacées")
        self.btn_cancel_succession.setVisible(False)  # chips suffisent en mono-sélection

        # Libellés divergents au sein du groupe d'équivalence (C)
        labels_differ = self.all_statuses.get(ref_piece, {}).get('labels_differ', False)
        self.btn_harmonize_labels.setVisible(bool(equivalents) and labels_differ)
        self.btn_harmonize_labels.setEnabled(bool(equivalents) and labels_differ)

    # ── Écriture des relations (saisie directe et fenêtre de sélection) ─────

    REMPLACE, REMPLACEE_PAR, EQUIVALENTES = 'remplace', 'remplacee_par', 'equivalentes'

    def _refs_inconnues(self, refs) -> List[str]:
        """Réfs absentes des pièces : l'écriture les créera en fantôme."""
        return [r for r in refs if not self.db_manager.lire_piece_exacte(r)]

    def _ecrire_relation(self, genre: str, refs: list):
        """Écrit une relation pour la sélection et retourne (lignes d'historique,
        erreurs, réfs créées en fantôme). Mêmes écritures qu'avant la saisie
        directe : add_supersession / add_equivalence puis propagate_description.

        - REMPLACE : chaque réf. est remplacée par LA pièce sélectionnée (une
          seule : une réf. n'a qu'une remplaçante ; à plusieurs pièces, l'ancien
          code la faisait remplacer par la dernière, sans message) ;
        - REMPLACEE_PAR : chaque pièce sélectionnée est remplacée par la réf.
          (une seule) ;
        - EQUIVALENTES : la pièce affichée devient équivalente à chaque réf."""
        pieces = self._get_selected_refs()
        refs = [r for r in dict.fromkeys(refs) if r]
        lignes, erreurs = [], []
        if not refs or (not pieces and genre != self.EQUIVALENTES):
            return lignes, erreurs, []
        fantomes = self._refs_inconnues(refs)
        if genre == self.REMPLACE:
            if len(pieces) != 1:
                return lignes, ["Une réf. n'a qu'une remplaçante : sélectionnez une seule pièce."], []
            couples = [(ref_old, pieces[0]) for ref_old in refs]
        elif genre == self.REMPLACEE_PAR:
            if len(refs) != 1:
                return lignes, ["Une pièce n'a qu'une remplaçante : saisissez une seule réf."], []
            couples = [(ref_old, refs[0]) for ref_old in pieces]
        else:
            courante = self._current_ref_piece
            if not courante:
                return lignes, erreurs, []
            for ref_b in refs:
                # add_equivalence renvoie (ok, message) : ne propager qu'après succès
                ok, message = self.db_manager.add_equivalence(courante, ref_b)
                if ok:
                    lignes.append(f"==> '{courante}' ≡ '{ref_b}'")
                    self.db_manager.propagate_description(courante, ref_b)
                else:
                    erreurs.append(f"{ref_b} : {message}")
            return lignes, erreurs, [f for f in fantomes if any(f"'{f}'" in l for l in lignes)]
        for ref_old, ref_new in couples:
            ok, message = self.db_manager.add_supersession(ref_old, ref_new)
            if ok:
                lignes.append(f"==> '{ref_old}' → '{ref_new}'")
                # Une réf. inconnue est créée en fantôme, donc anonyme : elle hérite
                # du libellé, comme à l'import (sans écraser deux libellés existants)
                self.db_manager.propagate_description(ref_old, ref_new)
            else:
                erreurs.append(f"{ref_old} → {ref_new} : {message}")
        return lignes, erreurs, [f for f in fantomes if any(f"'{f}'" in l for l in lignes)]

    def _apres_relation(self, genre: str, lignes: list, fantomes: list):
        """Historique, rafraîchissement et rechargement — une fois par lot de réfs."""
        if not lignes:
            return
        titre = "Équivalence :\n" if genre == self.EQUIVALENTES else "Succession :\n"
        self._notify_history(titre + "\n".join(lignes))
        if fantomes:
            self._recharger_completion()
        self._refresh_succession_panel(self._current_ref_piece)
        self._refresh_equivalence_panel(self._current_ref_piece)
        # add_supersession / add_equivalence peuvent créer des fantômes et changer
        # les statuts : le cache all_statuses est périmé
        self._load_pieces_data()

    def _remplacantes_existantes(self, ref_new: str) -> List[Tuple[str, str]]:
        """(pièce, remplaçante actuelle) des pièces sélectionnées déjà remplacées
        par une autre réf. que `ref_new`."""
        existantes = []
        for piece in self._get_selected_refs():
            actuelle = self.db_manager.get_piece_status(piece).get('ref_new')
            if actuelle and actuelle != ref_new:
                existantes.append((piece, actuelle))
        return existantes

    def _appliquer_relation(self, genre: str, refs: list, sur_fin=None):
        """Écrit puis rend compte : `sur_fin(lignes, erreurs, fantomes)` (saisie
        directe : ligne d'état), sinon boîte d'erreurs (fenêtre de sélection).
        « Remplacée par » sur une pièce qui a déjà une remplaçante : confirmation."""
        def _ecrire():
            lignes, erreurs, fantomes = self._ecrire_relation(genre, refs)
            self._apres_relation(genre, lignes, fantomes)
            if sur_fin is not None:
                sur_fin(lignes, erreurs, fantomes)
            elif erreurs:
                titre = "Erreurs d'équivalence" if genre == self.EQUIVALENTES else "Erreurs de succession"
                QMessageBox.warning(self, titre, "\n".join(erreurs))

        if genre == self.REMPLACEE_PAR and len(refs) == 1:
            existantes = self._remplacantes_existantes(refs[0])
            if existantes:
                detail = "\n".join(f"{p} : {a} → {refs[0]}" for p, a in existantes[:8])
                demander_oui_non(self, "Changer de remplaçante",
                                 f"Une pièce n'a qu'une remplaçante. Remplacer :\n{detail}\n ?",
                                 _ecrire, defaut=None)
                return
        _ecrire()

    # ── Saisie directe dans les cartes ──────────────────────────────────────

    # Raccourcis : ⌘1 / ⌘2 / ⌘3 = saisie de la carte (ordre du panneau)
    _RACCOURCIS_SAISIE = {'equivalentes': 'Ctrl+1', 'remplace': 'Ctrl+2', 'remplacee_par': 'Ctrl+3'}

    def _creer_saisie(self, genre: str, aide: str) -> SaisieRelation:
        touche = self._RACCOURCIS_SAISIE[genre]
        saisie = SaisieRelation(aide, raccourci=QKeySequence(touche).toString(
            QKeySequence.NativeText))
        QShortcut(QKeySequence(touche), self, activated=saisie.prendre_le_curseur)
        saisie.activer(False, "Sélectionnez une pièce")
        saisie.refs_saisies.connect(lambda refs, g=genre: self._sur_saisie_relation(g, refs))
        # Une complétion par champ, toutes sur le même modèle gardé sur la fenêtre
        # (piège GC du QCompleter : un modèle sans référence Python disparaît)
        completer = QCompleter(self._modele_completion(), saisie)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        saisie.setCompleter(completer)
        self._saisies_relation[genre] = saisie
        return saisie

    def _modele_completion(self) -> QStringListModel:
        """Modèle partagé des réfs de pièces (toutes : pas de limite à 5 000)."""
        if getattr(self, '_completion_refs', None) is None:
            self._completion_refs = QStringListModel(self)
            self._recharger_completion()
        return self._completion_refs

    def _recharger_completion(self):
        try:
            refs = self.db_manager.lister_toutes_refs_pieces()
        except Exception as exc:
            app_logger.warning(f"Complétion des réfs de pièces non chargée : {exc}")
            refs = []
        self._modele_completion().setStringList(refs)

    def _sur_saisie_relation(self, genre: str, refs: list):
        saisie = self._saisies_relation[genre]
        self._appliquer_relation(
            genre, refs, sur_fin=lambda lignes, erreurs, fantomes:
            saisie.afficher_bilan(lignes, erreurs, fantomes))

    def _maj_saisies_relation(self, n: int):
        """Activer / décrire les saisies selon la sélection (0, 1 ou N pièces)."""
        if not hasattr(self, '_saisies_relation'):
            return
        # Le bilan d'une saisie survit au rechargement qui la suit (même
        # sélection) ; il s'efface quand on change de pièce
        selection = (tuple(self._get_selected_refs()) if n else (), self._current_ref_piece)
        if selection != getattr(self, '_selection_saisies', None):
            self._selection_saisies = selection
            for saisie in self._saisies_relation.values():
                saisie.effacer_etat()
        if n == 0:
            for saisie in self._saisies_relation.values():
                saisie.activer(False, "Sélectionnez une pièce")
            return
        courante = self._current_ref_piece or ''
        self.saisie_equiv.activer(bool(courante))
        self.saisie_equiv.definir_aide(
            "Réf. équivalente…" if n == 1 else f"Réf. équivalente à {courante}…")
        if n == 1:
            self.saisie_remplace.activer(True)
            self.saisie_remplace.definir_aide("Ancienne réf. remplacée…")
            self.saisie_remplacee_par.activer(True)
            self.saisie_remplacee_par.definir_aide("Réf. qui la remplace…")
        else:
            self.saisie_remplace.activer(
                False, "Une réf. n'a qu'une remplaçante : sélectionnez une seule pièce")
            self.saisie_remplace.definir_aide(
                "Une seule pièce", "Une réf. n'a qu'une remplaçante : sélectionnez une seule pièce")
            self.saisie_remplacee_par.activer(True)
            self.saisie_remplacee_par.definir_aide(f"Réf. qui remplace les {n} pièces…")

    def _ouvrir_selecteur_relation(self, genre: str):
        """Bouton + d'une carte : fenêtre de sélection avec panier."""
        refs = self._get_selected_refs()
        if not refs and genre != self.EQUIVALENTES:
            return
        cible = f"{refs[0]}" if len(refs) == 1 else f"{len(refs)} pièces"
        if genre == self.REMPLACE:
            if len(refs) != 1:
                return
            titre, maxi = f"Ajouter des réf. remplacées par {cible}", None
        elif genre == self.REMPLACEE_PAR:
            titre, maxi = f"Choisir la réf. qui remplace {cible}", 1
        else:
            cible = self._current_ref_piece
            if not cible:
                return
            titre, maxi = f"Ajouter des réf. équivalentes à {cible}", None
        saisie = self._saisies_relation.get(genre) if hasattr(self, '_saisies_relation') else None
        exclure = cible if genre == self.EQUIVALENTES else (refs[0] if len(refs) == 1 else None)
        dlg = PiecePickerDialog(
            self.db_manager, self,
            exclude_ref=exclure,
            title=titre, multi_select=maxi is None, max_refs=maxi,
            recherche_initiale=saisie.texte_en_cours() if saisie is not None else '')

        def _sur_accepte():
            choisies = dlg.selected_refs()
            if choisies:
                if saisie is not None:
                    saisie.vider()
                self._appliquer_relation(genre, choisies)

        ouvrir_modal(dlg, sur_accepte=_sur_accepte)  # jamais exec_ (gel macOS)

    def _on_mark_superseded(self):
        """Déclarer que les pièces sélectionnées sont remplacées par une autre."""
        self._ouvrir_selecteur_relation(self.REMPLACEE_PAR)

    def _on_mark_replaces(self):
        """Déclarer que d'autres réfs sont remplacées par la pièce sélectionnée."""
        self._ouvrir_selecteur_relation(self.REMPLACE)

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
                    appareils_lines.append(f"  … et {pluralize(len(appareils) - 10, 'autre')}")

        label = f"'{refs[0]}'" if len(refs) == 1 else f"{len(refs)} pièces sélectionnées"
        msg = f"Marquer {label} comme obsolète(s) (aucun remplacement) ?"
        if appareils_lines:
            msg += "\n\nAppareils concernés :" + "\n".join(appareils_lines)

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite():
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
                self._load_pieces_data()
            if errors:
                QMessageBox.warning(self, "Erreur", "\n".join(errors))

        demander_oui_non(self, 'Marquer comme obsolète', msg, _suite, defaut=None)

    def _on_cancel_succession(self):
        """Annuler la relation de succession pour les pièces sélectionnées."""
        refs = self._get_selected_refs()
        if not refs:
            return

        label = f"'{refs[0]}'" if len(refs) == 1 else f"{len(refs)} pièces"
        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite():
            details_lines = []
            for ref in refs:
                self.db_manager.remove_supersession(ref)
                details_lines.append(f"==> '{ref}' → (succession annulée)")

            if details_lines:
                self._notify_history("Succession :\n" + "\n".join(details_lines))
                self._refresh_succession_panel(self._current_ref_piece)
                self._load_pieces_data()

        demander_oui_non(self, 'Annuler la succession', f'Supprimer le lien de succession pour {label} ?', _suite, defaut=None)

    _format_refs_recap = staticmethod(_format_refs_recap)

    def _on_batch_edit_libelle(self):
        """Appliquer le même libellé à toutes les pièces sélectionnées (action D/A)."""
        refs = self._get_selected_refs()
        if len(refs) < 2:
            return

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite(new_desc):
            # Un champ laissé vide n'est pas un renommage mais un effacement de masse :
            # le dire, plutôt que d'annoncer « va devenir «  » ».
            if not new_desc.strip():
                message = (f"Le libellé de {pluralize(len(refs), 'pièce')} va être "
                           f"effacé :\n{self._format_refs_recap(refs)}")
            else:
                message = (f"Le libellé de {len(refs)} pièces va devenir « {new_desc} » :\n"
                           f"{self._format_refs_recap(refs)}")

            # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
            def _appliquer():
                updated = self.db_manager.set_description_for_refs(refs, new_desc)
                if updated:
                    self._notify_history(
                        f"Libellé :\n==> {pluralize(updated, 'pièce')} → « {new_desc} » ({self._format_refs_recap(refs)})"
                    )
                    self._load_pieces_data()

            demander_oui_non(self, 'Modifier le libellé', message, _appliquer, defaut=None)

        saisir_texte(self, 'Modifier le libellé', f'Nouveau libellé pour les {len(refs)} pièces sélectionnées :', "", _suite)

    def _on_mark_equivalent_group(self):
        """Fusionner toutes les pièces sélectionnées dans un seul groupe d'équivalence (action D)."""
        refs = self._get_selected_refs()
        if len(refs) < 2:
            return

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite():
            errors = []
            for ref_b in refs[1:]:
                success, error_msg = self.db_manager.add_equivalence(refs[0], ref_b)
                if success:
                    self.db_manager.propagate_description(refs[0], ref_b)
                else:
                    errors.append(f"{ref_b} : {error_msg}")

            self._notify_history(
                f"Équivalence :\n==> {len(refs)} pièces fusionnées en un groupe ({self._format_refs_recap(refs)})"
            )
            self._load_pieces_data()
            if errors:
                QMessageBox.warning(self, "Erreur", "\n".join(errors))

        demander_oui_non(self, 'Marquer comme équivalentes', f"Fusionner ces {len(refs)} pièces dans un seul groupe d'équivalence ?\n{self._format_refs_recap(refs)}", _suite, defaut=None)

    def _on_harmonize_labels(self):
        """Harmoniser les libellés divergents d'un groupe d'équivalence (action C)."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return

        equivalents = self.db_manager.get_equivalents(ref_piece)
        if not equivalents:
            return

        group_refs = [ref_piece] + equivalents

        descs = libelles_candidats(self._desc_by_ref.get(r, "") for r in group_refs)

        if not descs:
            # Groupe entièrement anonyme : le bouton est visible (c'est bien une
            # incohérence à traiter) mais il n'y a rien à propager — le dire,
            # plutôt que de ne rien faire sans explication.
            QMessageBox.information(
                self, "Harmoniser les libellés",
                f"Aucune pièce du groupe ne porte de libellé "
                f"({self._format_refs_recap(group_refs)}).\n"
                "Saisissez-en un sur l'une d'elles, il pourra ensuite être propagé."
            )
            return

        choices = []
        for d in descs:
            count = sum(1 for r in group_refs
                        if (self._desc_by_ref.get(r, "") or "").strip() == d)
            choices.append(f"{d}  —  {pluralize(count, 'pièce')}")

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite(choice):
            chosen_desc = descs[choices.index(choice)]

            updated = self.db_manager.set_description_for_refs(group_refs, chosen_desc)
            if updated:
                self._notify_history(
                    f"Libellé :\n==> {pluralize(updated, 'pièce harmonisée', 'pièces harmonisées')} → « {chosen_desc} » "
                    f"({self._format_refs_recap(group_refs)})"
                )
                self._load_pieces_data()

        choisir_element(self, 'Harmoniser les libellés', f'Libellés actuels du groupe ({self._format_refs_recap(group_refs)}) :\nChoisir le libellé à appliquer à toutes les pièces du groupe :', choices, _suite, courant=0, modifiable=False)

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
        self.equiv_tag_list.set_empty_text(
            "Aucune équivalence" if has_selection and ref_piece is not None and n == 1 else "")

        # ── Aucune sélection ──────────────────────────────────────────────
        self.btn_lier_associees.setVisible(n == 2 and self._paire_associable(selected))
        self._maj_saisies_relation(n if ref_piece is not None else 0)
        if not has_selection or ref_piece is None:
            self.equiv_status_label.setText("Sélectionnez une pièce pour voir ses équivalences.")
            self.equiv_status_label.setStyleSheet(StyleManager.TEXTE_GRIS_MOYEN)
            self.equiv_status_label.setVisible(True)
            self.equiv_tag_list.set_refs([])
            self.btn_unlink_equiv.setVisible(False)
            self.ligne_associee.masquer()
            return

        # ── Multi-sélection ────────────────────────────────────────────────
        if n > 1:
            self.equiv_status_label.setVisible(False)
            self.equiv_tag_list.set_refs([])
            self.btn_unlink_equiv.setVisible(True)
            self.btn_unlink_equiv.setEnabled(True)
            self.ligne_associee.masquer()
            return

        # ── Sélection unique : chips ──────────────────────────────────────
        jumelle = self._afficher_reference_associee(ref_piece)
        # La jumelle (ou la réf. proposée) est en tête : pas deux fois
        equivs = [e for e in self.db_manager.get_equivalents(ref_piece) if e != jumelle]
        if jumelle:
            self.equiv_tag_list.set_empty_text("Aucune autre équivalence")
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

    # ── Réf. associée (jumelle Whirlpool / Indesit / Beko) ──────────────────

    @staticmethod
    def _paire_associable(refs) -> bool:
        """Deux réf. de groupes différents parmi Whirlpool / Indesit / Beko."""
        origines = [origine_associable(r) for r in refs]
        return len(origines) == 2 and all(origines) and origines[0] != origines[1]

    def _etat_reference_associee(self, ref_piece: str):
        """(état, référence, rôle de la pièce) de la ligne « Réf. associée »."""
        db = self.db_manager
        origine = origine_associable(ref_piece)
        connue, associee = db.reference_associee(ref_piece)
        if connue and associee:
            return JUMELLE, associee, "principale"
        principale = db.reference_principale_de(ref_piece)
        if principale:
            return JUMELLE, principale, "associée"
        if connue:
            return AUCUNE, '', ''
        # Proposée (ligne 0 du groupe) : d'un autre groupe, et pas déjà la jumelle
        # d'une autre pièce du groupe
        if (associee and origine_associable(associee) not in ('', origine)
                and not db.references_associees_de(associee)):
            return PROPOSEE, associee, ''
        return VIDE, '', ''

    def _afficher_reference_associee(self, ref_piece: str) -> str:
        """Met la ligne à jour ; retourne la référence affichée (ou '')."""
        origine = origine_associable(ref_piece)
        etat, reference, role = self._etat_reference_associee(ref_piece)
        if not origine and etat != JUMELLE:
            # Forme non reconnue (§ 10.17 bis) : son groupe peut être déclaré (une
            # jumelle déjà posée, elle, reste affichée)
            self.ligne_associee.afficher(INCONNUE, '', '')
            return ''
        libelle = ''
        if reference:
            lignes = self.db_manager.lire_libelle_piece(reference)
            libelle = (lignes[0][0] or '') if lignes else ''
        declare = bool(origine_declaree(ref_piece)) and not origine_du_format(ref_piece)
        self.ligne_associee.afficher(etat, origine, autres_origines(origine), reference,
                                     libelle, role, piece=ref_piece, declare=declare)
        return reference

    def _on_declarer_groupe(self):
        """Forme non reconnue : la pièce est déclarée Whirlpool, Indesit ou Beko."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return

        def _sur_groupe(groupe: str):
            if groupe in ORIGINES_ASSOCIEES and self.db_manager.declarer_origines(
                    {ref_piece: groupe}, self._maintenant()):
                self._apres_associee(f"==> '{ref_piece}' déclarée {groupe}")

        choisir_element(self, "Groupe de la référence",
                        f"{ref_piece} n'a pas une forme connue. Elle est :",
                        list(ORIGINES_ASSOCIEES), _sur_groupe, modifiable=False)

    def _on_oublier_groupe(self):
        ref_piece = self._current_ref_piece
        if ref_piece and self.db_manager.oublier_origine_declaree(ref_piece):
            self._apres_associee(f"==> '{ref_piece}' → (groupe déclaré oublié)")

    @staticmethod
    def _maintenant() -> str:
        from datetime import datetime
        return datetime.now().isoformat(timespec='seconds')

    def _apres_associee(self, message: str):
        """Historique puis rafraîchissement, comme les autres actions du panneau."""
        self._notify_history("Réf. associée :\n" + message)
        self._refresh_equivalence_panel(self._current_ref_piece)
        self._load_pieces_data()

    def _lier_associee(self, principale: str, associee: str):
        ok, motif = self.db_manager.lier_reference_associee(principale, associee,
                                                            self._maintenant())
        if not ok:
            QMessageBox.warning(self, "Réf. associée", motif)
            return
        self._apres_associee(f"==> '{principale}' ⇄ '{associee}'")

    def _on_ajouter_associee(self):
        ref_piece = self._current_ref_piece
        origine = origine_associable(ref_piece or '')
        if not origine:
            return
        autres = [g for g in ORIGINES_ASSOCIEES if g != origine]
        # Les deux autres groupes ; les réf. de forme non reconnue, seulement
        # quand on les cherche (leur groupe est demandé ensuite, § 10.17 bis).
        # Un refus (déjà liée…) s'affiche sous le choix, la fenêtre reste ouverte
        dlg = PiecePickerDialog(
            self.db_manager, self, exclude_ref=ref_piece, max_refs=1,
            title=f"Réf. associée de {ref_piece} ({autres_origines(origine)})",
            filtre=lambda ref: origine_associable(ref) not in ('', origine),
            a_chercher=lambda ref: not origine_associable(ref),
            valider=lambda refs: self.db_manager.motif_refus_associee(
                ref_piece, refs[0], origine_associee=(
                    '' if origine_associable(refs[0]) else autres[0])))

        def _sur_accepte():
            choisie = (dlg.selected_ref() or '').strip()
            if not choisie:
                return
            if origine_associable(choisie):
                self._lier_associee(ref_piece, choisie)
                return

            def _sur_groupe(groupe: str):
                if groupe in autres and self.db_manager.declarer_origines(
                        {choisie: groupe}, self._maintenant()):
                    self._lier_associee(ref_piece, choisie)

            # Après la fermeture du choix de pièce (jamais deux fenêtres enchaînées
            # dans le même tour de boucle : gel macOS)
            QTimer.singleShot(0, lambda: choisir_element(
                self, "Groupe de la réf. associée",
                f"{choisie} n'a pas une forme connue. Elle est :", autres, _sur_groupe,
                modifiable=False))

        ouvrir_modal(dlg, sur_accepte=_sur_accepte)  # jamais exec_ (gel macOS)

    def _on_retirer_associee(self):
        ref_piece = self._current_ref_piece
        jumelle = self.ligne_associee.reference
        if not ref_piece or not jumelle:
            return

        def _suite():
            if self.db_manager.retirer_reference_associee(ref_piece):
                self._apres_associee(f"==> '{ref_piece}' ⇄ '{jumelle}' → (retirée)")

        demander_oui_non(self, "Retirer la réf. associée",
                         f"{jumelle} ne sera plus la réf. associée de {ref_piece}.\n"
                         f"Les deux pièces restent équivalentes.", _suite, defaut=None)

    def _on_inverser_associee(self):
        ref_piece = self._current_ref_piece
        if ref_piece and self.db_manager.inverser_reference_associee(ref_piece,
                                                                     self._maintenant()):
            principale = self.db_manager.reference_principale_de(ref_piece)
            nouvelle = principale if principale else ref_piece
            self._apres_associee(f"==> '{nouvelle}' devient la référence principale")

    def _on_confirmer_associee(self):
        ref_piece, proposee = self._current_ref_piece, self.ligne_associee.reference
        if ref_piece and proposee:
            self._lier_associee(ref_piece, proposee)

    def _on_refuser_associee(self):
        ref_piece, proposee = self._current_ref_piece, self.ligne_associee.reference
        if not ref_piece or not proposee:
            return

        def _suite():
            self.db_manager.refuser_reference_proposee(proposee)
            self._apres_associee(f"==> '{proposee}' n'est pas la réf. associée de "
                                 f"'{ref_piece}' (reste équivalente)")

        demander_oui_non(self, "Réf. associée proposée",
                         f"{proposee} n'est pas la réf. associée de {ref_piece} ?\n"
                         f"Elle reste équivalente, mais ne sera plus proposée.",
                         _suite, defaut=None)

    def _on_marquer_aucune_associee(self):
        ref_piece = self._current_ref_piece
        if ref_piece:
            self.db_manager.definir_references_associees([(ref_piece, None)], self._maintenant())
            self._apres_associee(f"==> '{ref_piece}' → aucune")

    def _on_oublier_aucune_associee(self):
        ref_piece = self._current_ref_piece
        if ref_piece:
            self.db_manager.oublier_reponse_aucune(ref_piece)
            self._apres_associee(f"==> '{ref_piece}' → (réponse « aucune » oubliée)")

    def _on_lier_associees(self):
        """Deux pièces sélectionnées : la pièce affichée devient la principale."""
        refs = self._get_selected_refs()
        if len(refs) != 2:
            return
        principale = self._current_ref_piece if self._current_ref_piece in refs else refs[0]
        associee = refs[1] if principale == refs[0] else refs[0]
        self._lier_associee(principale, associee)

    def _on_link_equiv(self):
        """Lier la pièce affichée à des réfs équivalentes (fenêtre de sélection)."""
        self._ouvrir_selecteur_relation(self.EQUIVALENTES)

    def _on_unlink_equiv(self):
        """Retirer les pièces sélectionnées de leur groupe d'équivalence (le bouton
        n'apparaît qu'en multi-sélection ; il ne retirait que la pièce affichée)."""
        selection = self._get_selected_refs() or (
            [self._current_ref_piece] if self._current_ref_piece else [])
        refs = [r for r in selection if self.db_manager.get_equivalents(r)]
        if not refs:
            QMessageBox.information(self, 'Retirer du groupe',
                                    "Aucune des pièces sélectionnées n'a d'équivalence.")
            return
        hors = len(selection) - len(refs)
        message = (f"Retirer '{refs[0]}' de son groupe d'équivalence ?" if len(refs) == 1
                   else f"Retirer ces {len(refs)} pièces de leur groupe d'équivalence ?\n"
                        f"{self._format_refs_recap(refs)}")
        if hors:
            message += (f"\n\n({pluralize(hors, 'pièce sélectionnée', 'pièces sélectionnées')} sans équivalence "
                        f"{'ne change' if hors == 1 else 'ne changent'} pas.)")

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite():
            for ref in refs:
                self.db_manager.remove_equivalence(ref)
            self._notify_history("Équivalence :\n" + "\n".join(
                f"==> '{ref}' → (retiré du groupe)" for ref in refs))
            self._refresh_equivalence_panel(self._current_ref_piece)
            self._load_pieces_data()

        demander_oui_non(self, 'Retirer du groupe', message, _suite, defaut=None)

    def _on_remove_superseded_by(self, ref_new: str):
        """Supprimer le lien 'Remplacée par ref_new' pour la pièce courante (chip ×)."""
        ref_piece = self._current_ref_piece
        if not ref_piece:
            return
        self.db_manager.remove_supersession(ref_piece)
        self._notify_history(f"Succession :\n==> '{ref_piece}' → (succession annulée)")
        self._refresh_succession_panel(ref_piece)
        self._load_pieces_data()

    def _on_remove_replaces(self, ref_old: str):
        """Supprimer le lien 'ref_old est remplacée par pièce courante' (chip ×)."""
        if not ref_old:
            return
        self.db_manager.remove_supersession(ref_old)
        self._notify_history(f"Succession :\n==> '{ref_old}' → (succession annulée)")
        self._refresh_succession_panel(self._current_ref_piece)
        self._load_pieces_data()

    def _on_remove_equiv(self, equiv_ref: str):
        """Retirer un membre spécifique du groupe d'équivalence (chip ×)."""
        if not equiv_ref:
            return
        self.db_manager.remove_equivalence(equiv_ref)
        self._notify_history(f"Équivalence :\n==> '{equiv_ref}' → (retiré du groupe)")
        self._refresh_equivalence_panel(self._current_ref_piece)
        self._load_pieces_data()

    def _notify_history(self, message: str):
        """Envoyer un message à l'historique principal si disponible."""
        try:
            parent = self.parent()
            if parent and hasattr(parent, 'user_interaction_service'):
                parent.user_interaction_service.add_to_history(message)
        except Exception as exc:
            app_logger.debug(f"Message non envoyé à l'historique principal : {exc}")

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

    def _chemin_export_par_defaut(self, nom_fichier: str) -> str:
        """Chemin proposé par défaut dans le dialogue de sauvegarde.

        Ouvre le sélecteur dans le dossier d'export configuré (Bureau par
        défaut) plutôt que dans le dernier dossier utilisé par le système.
        """
        import os
        from ..services.export_config_service import resolve_output_dir
        service = getattr(self.parent(), 'export_config_service', None)
        return os.path.join(resolve_output_dir(service), nom_fichier)

    @handle_ui_errors(log_prefix="Erreur export pièces", show_message=True)
    def _export_pieces(self, checked=False):
        """Exporter la liste des pièces"""

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        @handle_ui_errors(log_prefix='Erreur export pièces', show_message=True)
        def _suite(_fenetre, filename):
            self._write_pieces_csv(filename, self._get_filtered_data())
            QMessageBox.information(self, "Export réussi", f"Liste exportée vers:\n{filename}")

        choisir_fichier_a_enregistrer(self, 'Exporter les pièces', self._chemin_export_par_defaut('pieces_everyParts.csv'), 'Fichiers CSV (*.csv)', (lambda *a: _suite(self, *a)))

    @handle_ui_errors(log_prefix="Erreur export sélection pièces", show_message=True)
    def _export_selected_pieces(self, checked=False):
        """Exporter uniquement les pièces sélectionnées"""

        selected_refs = set(self._get_selected_refs())
        if not selected_refs:
            return

        rows = [row for row in self._get_filtered_data() if row[0] in selected_refs]

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        @handle_ui_errors(log_prefix='Erreur export sélection pièces', show_message=True)
        def _suite(_fenetre, filename):
            self._write_pieces_csv(filename, rows)
            QMessageBox.information(self, "Export réussi", f"Sélection exportée vers:\n{filename}")

        choisir_fichier_a_enregistrer(self, 'Exporter la sélection', self._chemin_export_par_defaut('pieces_selection.csv'), 'Fichiers CSV (*.csv)', (lambda *a: _suite(self, *a)))
    
    def _do_delete_piece(self, ref_piece: str):
        """Suppression effective d'une pièce : associations puis pièce (sans commit — l'appelant commite)."""
        self.db_manager.delete_piece_catalog(ref_piece, commit=False)

    @handle_ui_errors(log_prefix="Erreur suppression pièces", show_message=True)
    def _delete_selected_pieces(self, checked=False):
        """Supprimer les références de pièces sélectionnées (sélection sticky).

        La source de vérité est _sticky_selected_refs, pas la sélection visible :
        la suppression porte donc aussi sur les pièces hors de la vue filtrée, qui
        sont alors listées explicitement dans la confirmation."""
        selected_refs = self._get_selected_refs()  # sticky, trié

        if not selected_refs:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner au moins une référence de pièce à supprimer.")
            return

        # Nb d'associations résolu depuis all_pieces_data (couvre visible ET hors-écran)
        nb_by_ref = {r[0]: r[2] for r in getattr(self, 'all_pieces_data', [])}
        visible_refs = set()
        for row in range(self.pieces_table.rowCount()):
            item = self.pieces_table.item(row, 0)
            if item:
                visible_refs.add(item.data(Qt.UserRole) or item.text())

        pieces_to_delete = [(ref, int(nb_by_ref.get(ref, 0))) for ref in selected_refs]
        total_associations = sum(nb for _, nb in pieces_to_delete)
        offscreen_refs = [ref for ref in selected_refs if ref not in visible_refs]

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

        # Lister explicitement les pièces hors de la vue actuelle (sinon suppression « invisible »)
        if offscreen_refs:
            message += (f"Dont {pluralize(len(offscreen_refs), 'pièce')} hors de la vue actuelle :\n"
                        f"{_format_refs_recap(offscreen_refs)}\n\n")

        message += "Cette action est irréversible. Continuer ?"

        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        @handle_ui_errors(log_prefix='Erreur suppression pièces', show_message=True)
        def _suite(_fenetre):
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

            # La sélection sticky portait exactement sur les pièces supprimées :
            # la purger pour éviter des refs fantômes comptées « hors écran » après reload.
            self._sticky_selected_refs.clear()
            self._current_ref_piece = None

            # Recharger les données (sans fermer la fenêtre)
            self._load_pieces_data()

        demander_oui_non(self, 'Confirmation de suppression', message, (lambda *a: _suite(self, *a)), defaut=QMessageBox.StandardButton.No)

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
    
    def _do_edit_piece(self, current_ref: str, current_desc: str, focus_field: str = 'ref'):
        """Logique commune d'édition d'une pièce : dialogue, validation, mise à jour DB, historique."""
        liees = self.db_manager.get_references_liees(current_ref)
        refs_liees = refs_liees_a_plat(liees)
        libelles = self.db_manager.get_descriptions(refs_liees)
        dialog = PieceEditDialog(self, current_ref, current_desc, liees, libelles,
                                 focus_field=focus_field)

        def _on_accepted():
            new_ref, new_desc, propagate = dialog.get_values()

            if not new_ref:
                QMessageBox.warning(self, "Erreur", "La référence ne peut pas être vide.")
                return

            if any(char in new_ref for char in ['||', '&&']):
                QMessageBox.warning(self, "Erreur",
                                    "La référence ne peut pas contenir les caractères '||' ou '&&'.")
                return

            def _enregistrer():
                # Suite de la validation, directe ou après « Oui » (boîte non bloquante)
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

                if propagate and refs_liees:
                    updated = self.db_manager.set_description_for_refs(refs_liees, new_desc)
                    if updated and hasattr(self.parent(), 'user_interaction_service'):
                        details = "\n".join(f"   {l}" for l in resume_references_liees(liees))
                        self.parent().user_interaction_service.add_to_history(
                            f"Libellé :\n==> {pluralize(updated, 'référence liée', 'références liées')} "
                            f"→ « {new_desc} »\n{details}"
                        )
                        self._load_pieces_data()

            # La référence était validée non vide, le libellé ne l'était pas :
            # valider le dialogue avec le champ effacé suffisait à perdre le
            # libellé, et à le perdre pour toute la lignée si « propager » est coché.
            if not new_desc.strip() and (current_desc or '').strip():
                cibles = 1 + (len(refs_liees) if (propagate and refs_liees) else 0)
                demander_oui_non(
                    self, "Effacer le libellé",
                    f"Le libellé « {current_desc} » va être effacé "
                    f"de {pluralize(cibles, 'pièce')}.\nContinuer ?",
                    _enregistrer, defaut=None,
                )
                return

            _enregistrer()

        dialog.accepted.connect(_on_accepted)
        dialog.show()

    @handle_ui_errors(log_prefix="Erreur modification pièce", show_message=True)
    def _edit_selected_piece(self, checked=False, focus_field: str = 'ref'):
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
        self._do_edit_piece(current_ref, current_desc, focus_field=focus_field)

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
        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        @handle_ui_errors(log_prefix='Erreur suppression pièce (row)', show_message=True)
        def _suite(_fenetre):
            nb_item = self.pieces_table.item(row, 2)
            nb_appareils = int(nb_item.text()) if nb_item and nb_item.text().isdigit() else 0

            self._do_delete_piece(ref_piece)
            self.db_manager.conn.commit()
            # Retirer la pièce supprimée de la sélection sticky (cohérence du compteur)
            self._sticky_selected_refs.discard(ref_piece)
            if self._current_ref_piece == ref_piece:
                self._current_ref_piece = None
            self._load_pieces_data()
            self._add_to_main_history(ref_piece, nb_appareils)

        demander_oui_non(self, 'Confirmer la suppression', f"Êtes-vous sûr de vouloir supprimer la pièce '{ref_piece}' ?\n\nCette action supprimera également toutes ses associations avec les appareils.", (lambda *a: _suite(self, *a)), defaut=QMessageBox.No)

# Chargement complet du gestionnaire de pièces (comptages, types, fantômes).
# REQUETE_PIECES_COMPLETE : déplacée dans src/data/_db_mixins/pieces.py


def _formulaire_piece(ref: str = "", libelle: str = ""):
    """Champs Référence / Libellé communs aux fenêtres « Nouvelle pièce » et
    « Modifier la pièce » : même grille, libellés alignés à droite.

    Avant, les deux fenêtres jumelles différaient (« Référence * » sans
    deux-points d'un côté, champs non alignés de l'autre).
    Retourne (layout, champ_ref, champ_libelle).
    """
    from PyQt5.QtWidgets import QFormLayout
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(8)
    champ_ref = QLineEdit(ref)
    champ_ref.setPlaceholderText("Obligatoire — ex. : 12345678")
    champ_libelle = QLineEdit(libelle)
    champ_libelle.setPlaceholderText("Optionnel")
    form.addRow("Référence :", champ_ref)
    form.addRow("Libellé :", champ_libelle)
    return form, champ_ref, champ_libelle


class PieceEditDialog(QDialog):
    """Dialogue d'édition d'une pièce"""
    
    def __init__(self, parent, current_ref, current_desc, liees=None, libelles=None,
                 focus_field='ref'):
        super().__init__(parent)
        self.setWindowTitle("Modifier la pièce")
        self.setModal(True)
        self.resize(420, 140)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 14, 16, 12)

        # Champs communs avec « Nouvelle pièce » (_formulaire_piece)
        champs, self.ref_input, self.desc_input = _formulaire_piece(current_ref, current_desc)
        layout.addLayout(champs)

        # Propagation du libellé à toutes les références liées : lignée de
        # succession (nouvelles, anciennes, autres versions) et équivalentes.
        # Jusqu'en 3.85.0, seules les équivalentes : la case restait invisible
        # pour 626 familles de succession sur 722.
        self.liees = liees or {}
        self.refs_liees = refs_liees_a_plat(self.liees)
        self.libelles = libelles or {}
        self.propagate_checkbox = QCheckBox()
        self.detail_label = QLabel()
        self.remplaces_label = QLabel()
        if self.refs_liees:
            n = len(self.refs_liees)
            self.propagate_checkbox.setText(
                "Appliquer aussi ce libellé à la référence liée" if n == 1
                else f"Appliquer aussi ce libellé aux {n} références liées"
            )
            self.detail_label.setText("\n".join(resume_references_liees(self.liees)))
            self.detail_label.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
            self.detail_label.setWordWrap(True)
            self.remplaces_label.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
            self.remplaces_label.setWordWrap(True)
            bloc = QVBoxLayout()
            bloc.setSpacing(2)
            bloc.addWidget(self.propagate_checkbox)
            for label in (self.detail_label, self.remplaces_label):
                label.setContentsMargins(22, 0, 0, 0)   # aligné sous le texte de la case
                bloc.addWidget(label)
            layout.addLayout(bloc)
            self.desc_input.textChanged.connect(self._maj_libelles_remplaces)
            self._maj_libelles_remplaces()
        else:
            self.propagate_checkbox.setVisible(False)
            self.detail_label.setVisible(False)
            self.remplaces_label.setVisible(False)

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
        save_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        buttons_layout.addWidget(save_btn)
        
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
        
        # Présélectionner le champ correspondant à la colonne double-cliquée
        target = self.desc_input if focus_field == 'desc' else self.ref_input
        target.selectAll()
        target.setFocus()
        
    def _maj_libelles_remplaces(self, *_):
        """Lister, à la frappe, les libellés différents que la propagation écraserait."""
        remplaces = libelles_remplaces(self.libelles, self.refs_liees, self.desc_input.text())
        if not remplaces:
            self.remplaces_label.setVisible(False)
            return
        apercu = ", ".join(f"{ref} « {lib} »" for ref, lib in remplaces[:3])
        if len(remplaces) > 3:
            apercu += f", … et {pluralize(len(remplaces) - 3, 'autre')}"
        self.remplaces_label.setText(
            f"dont {pluralize(len(remplaces), 'libellé différent remplacé', 'libellés différents remplacés')} : "
            f"{apercu}")
        self.remplaces_label.setVisible(True)

    def get_values(self):
        """Retourner les valeurs saisies"""
        return (self.ref_input.text().strip(), self.desc_input.text().strip(),
                self.propagate_checkbox.isChecked())