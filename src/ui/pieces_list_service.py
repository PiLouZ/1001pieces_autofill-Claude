"""
Service de gestion de la liste des pièces avec boutons d'action au survol
Responsabilités:
- Widget PieceItemWidget : affichage 2 lignes + boutons hover (✎ 🔍 ×)
- PiecesListWidget : QListWidget utilisant setItemWidget
- PiecesListService : factory + menu contextuel minimal
"""

from typing import Optional
from .qt_imports import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                          QListWidget, QListWidgetItem, QLabel, QMenu,
                          QFont, QSize, Qt)
from src.core.logger import app_logger


class PieceItemWidget(QWidget):
    """
    Widget autonome pour un item de pièce — 2 lignes + boutons hover.

    Ligne 1 : référence (bold)
    Ligne 2 : statut de succession (coloré) ou description (gris)
    Boutons  : ✎ éditer | 🔍 rechercher | × supprimer  (visibles au survol)
    """

    def __init__(self, ref_piece: str, description: str, status_info: dict,
                 list_item: QListWidgetItem, parent=None):
        super().__init__(parent)
        self.list_item = list_item
        self.ref_piece = ref_piece
        self.setMouseTracking(True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 3, 4, 3)
        outer.setSpacing(4)

        # ── Bloc texte ─────────────────────────────────────────────────────
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        status   = status_info.get('status', 'current')
        ref_new  = status_info.get('ref_new')
        refs_old = status_info.get('refs_old')

        # Ligne 1 : référence (bold) + désignation inline (gris)
        desc_html = (f' <span style="color:#9e9e9e;font-size:10px;">{description}</span>'
                     if description else '')
        line1 = QLabel(f'<b>{ref_piece}</b>{desc_html}')
        line1.setTextFormat(Qt.RichText)
        text_layout.addWidget(line1)

        # Ligne 2 : statut de succession uniquement (absent si pièce courante)
        if status == 'superseded':
            line2_text  = f"↳ Remplacée par  {ref_new}"
            line2_style = "color: #e67e22; font-style: italic; font-size: 10px;"
        elif status == 'obsolete':
            line2_text  = "⚠ Obsolète — aucun remplacement"
            line2_style = "color: #c0392b; font-style: italic; font-size: 10px;"
        elif status == 'replacing':
            line2_text  = f"↑ Remplace  {refs_old}"
            line2_style = "color: #2980b9; font-style: italic; font-size: 10px;"
        elif status_info.get('equivalents'):
            line2_text  = f"≡ Équiv.  {status_info['equivalents']}"
            line2_style = "color: #8e44ad; font-style: italic; font-size: 10px;"
        else:
            line2_text  = ""
            line2_style = ""

        self._has_line2 = bool(line2_text)
        if line2_text:
            line2 = QLabel(line2_text)
            line2.setStyleSheet(line2_style)
            text_layout.addWidget(line2)

        outer.addWidget(text_widget, 1)

        # ── Boutons hover ─────────────────────────────────────────────────
        self._search_btn = self._make_btn("🔍", "#28a745", "#1e7e34", "Rechercher les appareils compatibles")
        self._edit_btn   = self._make_btn("✎",  "#007bff", "#0056b3", "Modifier cette pièce")
        self._delete_btn = self._make_btn("×",  "#dc3545", "#c82333", "Supprimer cette pièce")

        for btn in (self._search_btn, self._edit_btn, self._delete_btn):
            btn.setVisible(False)
            outer.addWidget(btn)

        self._search_btn.clicked.connect(self._search_piece)
        self._edit_btn.clicked.connect(self._edit_piece)
        self._delete_btn.clicked.connect(self._delete_piece)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_btn(text: str, bg: str, bg_hover: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(22, 22)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 1px;
            }}
            QPushButton:hover {{ background-color: {bg_hover}; }}
        """)
        return btn

    def _main_window(self):
        """Remonter jusqu'à la MainWindow."""
        w = self.parent()
        while w and not hasattr(w, '_edit_piece'):
            w = w.parent()
        return w

    # ── Hover ──────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        for btn in (self._search_btn, self._edit_btn, self._delete_btn):
            btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        for btn in (self._search_btn, self._edit_btn, self._delete_btn):
            btn.setVisible(False)
        super().leaveEvent(event)

    # ── Actions ────────────────────────────────────────────────────────────

    def _search_piece(self):
        """Lancer une recherche des appareils compatibles dans le champ principal."""
        mw = self._main_window()
        if mw and hasattr(mw, 'search_input'):
            mw.search_input.setText(self.ref_piece)
            mw.search_input.setFocus()

    def _edit_piece(self):
        mw = self._main_window()
        if mw:
            mw._edit_piece(self.list_item)

    def _delete_piece(self):
        mw = self._main_window()
        if mw and hasattr(mw, '_delete_piece_from_selected'):
            mw._delete_piece_from_selected(self.list_item)


class PiecesListWidget(QListWidget):
    """QListWidget utilisant setItemWidget pour les items 2 lignes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        # Hauteur de ligne uniforme pour les items avec widget
        self.setUniformItemSizes(False)

    def clear(self):
        """Override : nettoyer les item widgets avant de vider la liste."""
        for i in range(self.count()):
            w = self.itemWidget(self.item(i))
            if w:
                w.deleteLater()
        super().clear()

    def add_piece_item(self, ref_piece: str, description: str,
                       status_info: dict) -> QListWidgetItem:
        """Ajouter un item pièce avec son widget."""
        item = QListWidgetItem()
        item.setData(Qt.UserRole, ref_piece)
        self.addItem(item)
        widget = PieceItemWidget(ref_piece, description, status_info, item, self)
        height = 52 if widget._has_line2 else 40
        item.setSizeHint(QSize(0, height))
        self.setItemWidget(item, widget)
        return item


class PiecesListService:
    """
    Service pour la gestion de la liste des pièces.
    Factory + menu contextuel minimal (multi-sélection uniquement).
    """

    def __init__(self, main_window):
        self.main_window = main_window

    def create_pieces_list_widget(self) -> PiecesListWidget:
        pieces_list = PiecesListWidget()
        pieces_list.itemDoubleClicked.connect(self._on_double_click)
        pieces_list.setContextMenuPolicy(Qt.CustomContextMenu)
        pieces_list.customContextMenuRequested.connect(self._show_pieces_context_menu)
        app_logger.debug("PiecesListWidget créé")
        return pieces_list

    def _on_double_click(self, item: QListWidgetItem):
        """Double-clic → éditer la pièce."""
        self.main_window._edit_piece(item)

    def _show_pieces_context_menu(self, position):
        """Menu contextuel : uniquement pour la suppression multi-appareils."""
        item = self.main_window.pieces_list.itemAt(position)
        if not item:
            return

        selected_ranges = self.main_window.table.selectedRanges()
        total_selected = sum(
            r.bottomRow() - r.topRow() + 1 for r in selected_ranges
        ) if selected_ranges else 0

        if total_selected <= 1:
            return  # Rien de spécial à proposer pour sélection simple

        menu = QMenu(self.main_window)
        delete_all = menu.addAction("🗑️ Supprimer de tous les appareils sélectionnés")
        delete_all.triggered.connect(
            lambda: self.main_window._delete_piece_from_selected(item)
        )
        menu.exec_(self.main_window.pieces_list.mapToGlobal(position))
