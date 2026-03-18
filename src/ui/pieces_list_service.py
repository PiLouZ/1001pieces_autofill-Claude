"""
Service de gestion de la liste des pièces avec boutons d'action au survol
Responsabilités:
- Widget PieceItemWidget : affichage 2 lignes + boutons hover (✎ 🔍 ×)
- PiecesListWidget : QListWidget utilisant setItemWidget
- PiecesListService : factory + menu contextuel minimal
- PieceRelationsPopup : popup de synthèse de toutes les relations d'une pièce
"""

from typing import Optional
from .qt_imports import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                          QListWidget, QListWidgetItem, QLabel, QMenu,
                          QFont, QSize, Qt, QDialog, QScrollArea, QFrame,
                          QCursor, QTimer, QApplication)
from src.core.logger import app_logger


def _truncate_refs_str(refs_str: str, max_inline: int = 2) -> tuple:
    """
    Parse une string de refs séparées par virgules et tronque si nécessaire.
    Retourne (display_str, full_tooltip).
    - display_str : "REF1, REF2 … +N" si > max_inline, sinon la string complète.
    - full_tooltip : string complète si tronquée, sinon "".
    """
    if not refs_str:
        return "", ""
    parts = [r.strip() for r in refs_str.split(',') if r.strip()]
    full = ", ".join(parts)
    if len(parts) <= max_inline:
        return full, ""
    shown = ", ".join(parts[:max_inline])
    return f"{shown}  … +{len(parts) - max_inline}", full


def _link_if_truncated(disp: str, tip: str, color: str) -> str:
    """
    Si tip est non-vide (liste tronquée), remplace le '… +N' de disp par un lien HTML.
    Sinon retourne disp tel quel (compatible RichText).
    """
    if not tip or '… +' not in disp:
        return disp
    base, n = disp.rsplit('… +', 1)
    return (f"{base}<a href='#' style='color:{color};text-decoration:none;"
            f"border-bottom:1px dashed {color};'>… +{n}</a>")


def _parse_refs(refs_str: str) -> list:
    """Parse une string de refs séparées par virgules en liste propre."""
    if not refs_str:
        return []
    return [r.strip() for r in refs_str.split(',') if r.strip()]


# ── Popup de synthèse des relations ────────────────────────────────────────────

class PieceRelationsPopup(QDialog):
    """
    Popup léger affichant la synthèse complète des relations d'une pièce :
    obsolescence, supersession (↳/↑) et équivalences (≡).

    Se ferme au clic extérieur grâce au flag Qt.Popup.
    Scrollable si le contenu dépasse MAX_HEIGHT.
    """

    MAX_HEIGHT = 300
    WIDTH      = 280

    def __init__(self, ref_piece: str, status_info: dict, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        status      = status_info.get('status', 'current')
        is_obsolete = status_info.get('is_obsolete', False)
        ref_new     = status_info.get('ref_new')
        refs_old    = _parse_refs(status_info.get('refs_old') or '')
        equivalents = _parse_refs(status_info.get('equivalents') or '')

        # ── Mise en page racine ────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.setStyleSheet("""
            QDialog {
                background: white;
                border: 1px solid #ced4da;
                border-radius: 8px;
            }
        """)

        # ── En-tête ────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            "background: #f8f9fa;"
            "border-bottom: 1px solid #e9ecef;"
            "border-top-left-radius: 8px;"
            "border-top-right-radius: 8px;"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel(f"<b>{ref_piece}</b>  <span style='color:#6c757d;font-weight:normal;'>"
                       f"— Relations</span>")
        title.setStyleSheet("font-size: 12px; color: #2c3e50; background: transparent;")
        h_layout.addWidget(title, 1)
        root.addWidget(header)

        # ── Zone scrollable ────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(self.MAX_HEIGHT)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: white;")

        content = QWidget()
        content.setStyleSheet("background: white;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(12, 10, 12, 12)
        c_layout.setSpacing(10)

        has_content = False

        # Obsolète
        if is_obsolete:
            lbl = QLabel("⚠  Obsolète")
            lbl.setStyleSheet(
                "color: #c0392b; font-weight: bold; font-size: 11px;"
                "background: #fdf2f2; border: 1px solid #f5c6cb;"
                "border-radius: 4px; padding: 4px 8px;"
            )
            c_layout.addWidget(lbl)
            has_content = True

        # Remplacée par
        if status == 'superseded' and ref_new:
            c_layout.addWidget(self._section(
                "↳  Remplacée par", [ref_new], "#e67e22", "#fef9f0", "#fde8c8"))
            has_content = True

        # Remplace
        if refs_old:
            c_layout.addWidget(self._section(
                f"↑  Remplace  ({len(refs_old)})", refs_old, "#2980b9", "#f0f7ff", "#c5dff8"))
            has_content = True

        # Équivalences
        if equivalents:
            c_layout.addWidget(self._section(
                f"≡  Équivalences  ({len(equivalents)})", equivalents, "#8e44ad", "#faf0ff", "#e8c8f8"))
            has_content = True

        if not has_content:
            lbl = QLabel("Aucune relation enregistrée.")
            lbl.setStyleSheet("color: #6c757d; font-size: 11px; font-style: italic;")
            c_layout.addWidget(lbl)

        c_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        self.setFixedWidth(self.WIDTH)

    @staticmethod
    def _section(title: str, refs: list, color: str,
                 bg: str, border_color: str) -> QWidget:
        """Crée un bloc section (titre + liste de refs) avec fond coloré."""
        w = QWidget()
        w.setStyleSheet(
            f"background: {bg}; border: 1px solid {border_color}; border-radius: 6px;"
        )
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(3)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px;"
            f"background: transparent; border: none;"
        )
        layout.addWidget(title_lbl)

        for ref in refs:
            ref_lbl = QLabel(f"  {ref}")
            ref_lbl.setStyleSheet(
                "color: #2c3e50; font-size: 11px; font-family: monospace;"
                "background: transparent; border: none;"
            )
            layout.addWidget(ref_lbl)

        return w

    def show_at_cursor(self):
        """
        Positionner le popup près du curseur et l'afficher.
        Le QTimer.singleShot(0) diffère l'affichage d'un tick pour que le clic
        qui a déclenché l'appel soit entièrement consommé avant l'ouverture —
        évite la fermeture immédiate du Qt.Popup sur les parents de haut niveau.
        """
        pos = QCursor.pos()
        self.move(pos.x() + 4, pos.y() + 4)
        QTimer.singleShot(0, self.show)


# ── Helpers label ───────────────────────────────────────────────────────────────

def _make_relation_label(prefix: str, refs_str: str, color: str,
                          click_callback, search_callback=None,
                          max_inline: int = 2) -> QLabel:
    """
    Crée un QLabel pour une ligne de relation (↳/↑/≡).
    - Si search_callback est fourni, chaque ref individuelle est un lien cliquable.
    - Le '… +N' (liste tronquée) ouvre toujours le popup via click_callback.
    """
    parts = _parse_refs(refs_str)
    if not parts:
        return None

    style = (f"color: {color}; font-style: italic; font-size: 10px;"
             " background: transparent; border: none;")

    def _ref_link(ref: str, hovered: str = '') -> str:
        deco = 'underline' if ref == hovered else 'none'
        return (f"<a href='ref://{ref}' style='color:{color};font-style:italic;"
                f"font-size:10px;text-decoration:{deco};'>{ref}</a>")

    def _build_html(shown: list, n_more: int, hovered_href: str = '') -> str:
        hovered_ref = hovered_href[6:] if hovered_href.startswith('ref://') else ''
        parts_html  = ', '.join(_ref_link(r, hovered_ref) for r in shown)
        text = f"{prefix}  {parts_html}"
        if n_more:
            text += (f"  <a href='#popup' style='color:{color}; font-style:italic; font-size:9px;"
                     f"text-decoration:none; border-bottom:1px dashed {color};'>"
                     f"… +{n_more}</a>")
        return text

    def _on_link(href: str):
        if href.startswith('ref://') and search_callback:
            search_callback(href[6:])
        elif href == '#popup':
            click_callback()

    shown_refs = parts[:max_inline]
    n_more_    = len(parts) - max_inline if len(parts) > max_inline else 0

    def _make_interactive_label(html: str, shown: list, n_more: int) -> QLabel:
        """Créer un QLabel interactif avec hover-underline et menu clic-droit 'Copier'."""
        lbl = QLabel(html)
        lbl.setTextFormat(Qt.RichText)
        lbl.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        lbl.setStyleSheet(style)

        _last_hovered = ['']

        def _on_hover(href: str):
            _last_hovered[0] = href
            lbl.setText(_build_html(shown, n_more, href))

        def _show_ctx_menu(pos):
            menu = QMenu(lbl)
            hovered_ref = (_last_hovered[0][6:]
                           if _last_hovered[0].startswith('ref://') else None)
            targets = [hovered_ref] if hovered_ref else shown
            for r in targets:
                action = menu.addAction(f"Copier  {r}")
                action.triggered.connect(
                    lambda checked, _r=r: QApplication.clipboard().setText(_r))
            menu.exec_(lbl.mapToGlobal(pos))

        lbl.setContextMenuPolicy(Qt.CustomContextMenu)
        lbl.customContextMenuRequested.connect(_show_ctx_menu)
        lbl.linkHovered.connect(_on_hover)
        lbl.linkActivated.connect(_on_link)
        return lbl

    if len(parts) <= max_inline:
        if search_callback:
            return _make_interactive_label(_build_html(shown_refs, 0), shown_refs, 0)
        else:
            lbl = QLabel(f"{prefix}  {', '.join(parts)}")
            lbl.setStyleSheet(style)
            return lbl

    return _make_interactive_label(_build_html(shown_refs, n_more_), shown_refs, n_more_)


# ── Widget item pièce ───────────────────────────────────────────────────────────

class PieceItemWidget(QWidget):
    """
    Widget autonome pour un item de pièce — lignes additives + boutons hover.

    Ligne 1 : référence (bold) + désignation (gris)
    Ligne 2 : ⚠ Obsolète                              [si is_obsolete]
    Ligne 3 : ↳ Remplacée par / ↑ Remplace…  [+N]    [si supersession]
    Ligne 4 : ≡ Équiv. …                      [+N]    [si équivalences]
    Boutons  : ✎ éditer | 🔍 rechercher | × supprimer  (visibles au survol)

    Le lien '… +N' ouvre PieceRelationsPopup avec la synthèse complète.
    """

    def __init__(self, ref_piece: str, description: str, status_info: dict,
                 list_item: QListWidgetItem, parent=None):
        super().__init__(parent)
        self.list_item    = list_item
        self.ref_piece    = ref_piece
        self._status_info = status_info
        self.setMouseTracking(True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 3, 4, 3)
        outer.setSpacing(4)

        # ── Bloc texte ─────────────────────────────────────────────────────
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        status      = status_info.get('status', 'current')
        is_obsolete = status_info.get('is_obsolete', False)
        ref_new     = status_info.get('ref_new')
        refs_old    = status_info.get('refs_old')     # str séparée par virgules
        equivalents = status_info.get('equivalents')  # str séparée par virgules

        # Ligne 1 : référence (bold) + désignation inline (gris)
        desc_html = (f' <span style="color:#9e9e9e;font-size:10px;">{description}</span>'
                     if description else '')
        line1 = QLabel(f'<b>{ref_piece}</b>{desc_html}')
        line1.setTextFormat(Qt.RichText)
        text_layout.addWidget(line1)

        extra_lines = 0

        # Ligne 2 : obsolète (indépendant des autres statuts)
        if is_obsolete:
            lbl = QLabel("⚠ Obsolète")
            lbl.setStyleSheet("color: #c0392b; font-style: italic; font-size: 10px;")
            text_layout.addWidget(lbl)
            extra_lines += 1

        # Ligne 3 : direction de supersession
        if status == 'superseded' and ref_new:
            _color_sup = '#e67e22'
            _base_html = (lambda deco='none': (
                f"↳ Remplacée par  <a href='ref://{ref_new}' style='color:{_color_sup};"
                f"font-style:italic;font-size:10px;text-decoration:{deco};'>{ref_new}</a>"))
            lbl = QLabel(_base_html())
            lbl.setTextFormat(Qt.RichText)
            lbl.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
            lbl.setStyleSheet(f"color: {_color_sup}; font-style: italic; font-size: 10px;"
                              " background: transparent; border: none;")
            lbl.linkHovered.connect(
                lambda href, l=lbl, b=_base_html:
                l.setText(b('underline') if href else b('none')))
            lbl.linkActivated.connect(
                lambda href, r=ref_new: self._search_ref_in_main(r)
                if href.startswith('ref://') else None)

            def _sup_ctx_menu(pos, lbl=lbl, r=ref_new):
                menu = QMenu(lbl)
                action = menu.addAction(f"Copier  {r}")
                action.triggered.connect(lambda: QApplication.clipboard().setText(r))
                menu.exec_(lbl.mapToGlobal(pos))
            lbl.setContextMenuPolicy(Qt.CustomContextMenu)
            lbl.customContextMenuRequested.connect(_sup_ctx_menu)

            text_layout.addWidget(lbl)
            extra_lines += 1

        if refs_old:  # peut coexister avec is_obsolete
            lbl = _make_relation_label(
                "↑ Remplace", refs_old, "#2980b9",
                self._show_relations_popup, self._search_ref_in_main)
            text_layout.addWidget(lbl)
            extra_lines += 1

        # Ligne 4 : équivalences (toujours affichée si présente)
        if equivalents:
            lbl = _make_relation_label(
                "≡ Équiv.", equivalents, "#8e44ad",
                self._show_relations_popup, self._search_ref_in_main)
            text_layout.addWidget(lbl)
            extra_lines += 1

        self._has_line2   = extra_lines > 0  # rétrocompat
        self._extra_lines = extra_lines
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

    def _show_relations_popup(self):
        """Afficher le popup de synthèse des relations de cette pièce."""
        popup = PieceRelationsPopup(self.ref_piece, self._status_info, self)
        popup.show_at_cursor()

    def _search_ref_in_main(self, ref: str):
        """Injecter une ref dans la recherche principale (sans copie automatique).
        Utilise QTimer.singleShot pour éviter un use-after-free si ce widget est
        détruit lors du rafraîchissement déclenché par le setText."""
        from .qt_imports import QTimer
        mw = self._main_window()
        if mw and hasattr(mw, 'search_input'):
            QTimer.singleShot(0, lambda: mw.search_input.setText(ref))

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
        height = 40 + widget._extra_lines * 12
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
