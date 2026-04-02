"""
Dialogue de consultation de l'historique persistant des modifications.
"""

import json
from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    Qt, QHeaderView, QSizePolicy, QMessageBox, QColor,
    QScrollArea, QFrame, QWidget, QApplication, QCursor, QTimer,
)
from PyQt5.QtWidgets import QDateEdit
from PyQt5.QtCore import QDate
import qtawesome as qta

_PAGE_SIZE = 100

_ACTION_LABELS = {
    'all':    'Tous',
    'edit':   'Modification',
    'import': 'Import',
    'export': 'Export',
    'delete': 'Suppression',
    'piece':  'Pièce',
    'undo':   'Annulation',
}

_ACTION_COLORS = {
    'edit':   '#4A9EFF',
    'import': '#34D058',
    'export': '#9B59B6',
    'delete': '#E05252',
    'piece':  '#1ABC9C',
    'undo':   '#F39C12',
}

# Types d'action pour lesquels un popup de détails est pertinent
_DETAIL_ACTION_TYPES = {'import', 'export', 'delete', 'piece', 'undo'}


# ── Popup de détails ──────────────────────────────────────────────────────────

class HistoryDetailPopup(QDialog):
    """
    Popup contextuel affichant le détail complet d'une entrée d'historique.
    Même pattern que PieceRelationsPopup : Qt.Popup + repositionnement bords d'écran.
    """

    MAX_HEIGHT = 320
    WIDTH      = 300

    def __init__(self, title: str, details: list, action_type: str, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        color = _ACTION_COLORS.get(action_type, '#888')

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

        label = _ACTION_LABELS.get(action_type, action_type.upper())
        badge = QLabel(label)
        badge.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px;"
            "background: transparent; border: none;"
        )
        h_layout.addWidget(badge)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "color: #2c3e50; font-size: 11px; background: transparent; border: none;"
        )
        title_lbl.setWordWrap(True)
        h_layout.addWidget(title_lbl, 1)
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
        c_layout.setSpacing(6)

        # Rendu des lignes groupées en sections
        current_section = None
        section_items = []

        def _flush_section():
            nonlocal current_section, section_items
            if current_section is not None and section_items:
                c_layout.addWidget(
                    self._section(current_section, section_items, color)
                )
            current_section = None
            section_items = []

        for line in details:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('==>'):
                item_text = stripped[3:].strip()
                if current_section is None:
                    # Items sans section parente → section implicite
                    current_section = ''
                section_items.append(item_text)
            else:
                _flush_section()
                current_section = stripped.rstrip(':')
                section_items = []

        _flush_section()

        if not details:
            lbl = QLabel("Aucun détail disponible.")
            lbl.setStyleSheet("color: #6c757d; font-size: 11px; font-style: italic;")
            c_layout.addWidget(lbl)

        c_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        self.setFixedWidth(self.WIDTH)

    @staticmethod
    def _section(title: str, items: list, color: str) -> QWidget:
        """Bloc section : titre optionnel + liste d'items."""
        bg = '#f8f9fa'
        border = '#dee2e6'

        w = QWidget()
        w.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; border-radius: 6px;"
        )
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(2)

        if title:
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 11px;"
                "background: transparent; border: none;"
            )
            layout.addWidget(title_lbl)

        for item in items:
            item_lbl = QLabel(f"  {item}")
            item_lbl.setStyleSheet(
                "color: #2c3e50; font-size: 11px;"
                "background: transparent; border: none;"
            )
            layout.addWidget(item_lbl)

        return w

    def show_at_cursor(self):
        """Positionner le popup près du curseur, replié si nécessaire."""
        cursor_pos = QCursor.pos()

        def _do_show():
            self.adjustSize()
            pw = self.width()  or self.WIDTH
            ph = self.height() or self.MAX_HEIGHT

            screen = QApplication.screenAt(cursor_pos)
            if screen is None:
                screen = QApplication.primaryScreen()
            avail = screen.availableGeometry()

            x = cursor_pos.x() + 4
            y = cursor_pos.y() + 4

            if x + pw > avail.right():
                x = cursor_pos.x() - pw - 4
            if y + ph > avail.bottom():
                y = cursor_pos.y() - ph - 4

            x = max(avail.left(), x)
            y = max(avail.top(), y)

            self.move(x, y)
            self.show()

        QTimer.singleShot(0, _do_show)


# ── Dialogue principal ────────────────────────────────────────────────────────

class HistoryViewDialog(QDialog):
    """Vue consultable de l'historique persistant des modifications."""

    def __init__(self, history_service, parent=None):
        super().__init__(parent)
        self.history_service = history_service
        self._current_page = 0
        self._total_count = 0
        self._active_popup = None

        self.setWindowTitle("Historique des modifications")
        self.setMinimumSize(900, 600)
        self.setModal(False)

        self._build_ui()
        self._load()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # ── Barre de filtres ──────────────────────────────────────────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        # Filtre type
        self._type_combo = QComboBox()
        for key, label in _ACTION_LABELS.items():
            self._type_combo.addItem(label, key)
        self._type_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(QLabel("Type :"))
        filter_bar.addWidget(self._type_combo)

        # Filtre dates
        filter_bar.addWidget(QLabel("Du :"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addMonths(-1))
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.dateChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._date_from)

        filter_bar.addWidget(QLabel("Au :"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.dateChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._date_to)

        # Recherche libre
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Rechercher dans l'historique…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._search_input, 1)

        layout.addLayout(filter_bar)

        # ── Tableau ───────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ['Date', 'Type', 'Description', 'Appareil', 'Champ', 'Ancienne valeur', 'Nouvelle valeur']
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)
        self._table.setWordWrap(False)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Date
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        hh.setSectionResizeMode(2, QHeaderView.Stretch)            # Description
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Appareil
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Champ
        hh.setSectionResizeMode(5, QHeaderView.Stretch)            # Ancienne
        hh.setSectionResizeMode(6, QHeaderView.Stretch)            # Nouvelle

        self._table.cellClicked.connect(self._on_cell_clicked)

        layout.addWidget(self._table)

        # ── Barre de statut + pagination ──────────────────────────────────────
        bottom_bar = QHBoxLayout()

        self._count_label = QLabel("0 entrée(s)")
        self._count_label.setStyleSheet("color: #666;")
        bottom_bar.addWidget(self._count_label)
        bottom_bar.addStretch()

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(qta.icon('fa5s.chevron-left', color='#555'))
        self._prev_btn.setFixedWidth(30)
        self._prev_btn.setToolTip("Page précédente")
        self._prev_btn.clicked.connect(self._prev_page)
        bottom_bar.addWidget(self._prev_btn)

        self._page_label = QLabel("Page 1")
        self._page_label.setAlignment(Qt.AlignCenter)
        self._page_label.setMinimumWidth(80)
        bottom_bar.addWidget(self._page_label)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(qta.icon('fa5s.chevron-right', color='#555'))
        self._next_btn.setFixedWidth(30)
        self._next_btn.setToolTip("Page suivante")
        self._next_btn.clicked.connect(self._next_page)
        bottom_bar.addWidget(self._next_btn)

        bottom_bar.addStretch()

        clear_btn = QPushButton("Effacer l'historique")
        clear_btn.setIcon(qta.icon('fa5s.trash-alt', color='#c0392b'))
        clear_btn.setStyleSheet("color: #c0392b;")
        clear_btn.clicked.connect(self._confirm_clear)
        bottom_bar.addWidget(clear_btn)

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.close)
        bottom_bar.addWidget(close_btn)

        layout.addLayout(bottom_bar)

    # ── Chargement ────────────────────────────────────────────────────────────

    def _filters(self) -> dict:
        action_type = self._type_combo.currentData()
        return {
            'action_type': action_type if action_type != 'all' else None,
            'date_from':   self._date_from.date().toString('yyyy-MM-dd'),
            'date_to':     self._date_to.date().toString('yyyy-MM-dd'),
            'search':      self._search_input.text().strip() or None,
        }

    def _load(self):
        f = self._filters()
        self._total_count = self.history_service.get_total_count(**f)
        total_pages = max(1, (self._total_count + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._current_page = min(self._current_page, total_pages - 1)

        rows = self.history_service.get_entries(
            limit=_PAGE_SIZE,
            offset=self._current_page * _PAGE_SIZE,
            **f,
        )
        self._populate_table(rows)

        self._count_label.setText(f"{self._total_count:,} entrée(s)".replace(',', ' '))
        self._page_label.setText(f"Page {self._current_page + 1} / {total_pages}")
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < total_pages - 1)

    def _populate_table(self, rows):
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            _id, timestamp, action_type, title, details_json, device_ref, field_name, old_val, new_val = row

            # Date — affichage court
            ts_display = str(timestamp)[:16] if timestamp else ''
            self._set_item(r, 0, ts_display)

            # Badge type
            label = _ACTION_LABELS.get(action_type, action_type.upper())
            color = _ACTION_COLORS.get(action_type, '#888')
            type_item = QTableWidgetItem(label)
            type_item.setForeground(QColor(color))
            type_item.setToolTip(action_type)
            self._table.setItem(r, 1, type_item)

            # Description : titre, enrichi du nombre de champs pour les éditions multi-champs
            description = title or ''
            if action_type == 'edit' and details_json:
                try:
                    details = json.loads(details_json)
                    if isinstance(details, list) and len(details) > 1:
                        description = f"{title} — {len(details)} champs"
                except Exception:
                    pass

            desc_item = QTableWidgetItem(description)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)

            # Stocker details_json et action_type pour le popup
            has_details = bool(
                details_json and action_type in _DETAIL_ACTION_TYPES
            )
            if has_details:
                desc_item.setData(Qt.UserRole, (action_type, title, details_json))
                desc_item.setToolTip("Cliquez pour voir les détails")

            self._table.setItem(r, 2, desc_item)

            self._set_item(r, 3, device_ref or '')
            self._set_item(r, 4, field_name or '')
            self._set_item(r, 5, old_val or '')
            self._set_item(r, 6, new_val or '')

    def _set_item(self, row: int, col: int, text: str):
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, col, item)

    # ── Interactions ──────────────────────────────────────────────────────────

    def _on_cell_clicked(self, row: int, col: int):
        """Affiche le popup de détails lors d'un clic sur la colonne Description."""
        if col != 2:
            return
        item = self._table.item(row, col)
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return

        action_type, title, details_json = data
        try:
            details = json.loads(details_json) if details_json else []
        except Exception:
            details = []

        if self._active_popup is not None:
            try:
                self._active_popup.close()
            except RuntimeError:
                pass  # objet C++ déjà supprimé par WA_DeleteOnClose
            self._active_popup = None

        self._active_popup = HistoryDetailPopup(title, details, action_type, parent=self)
        self._active_popup.destroyed.connect(lambda: setattr(self, '_active_popup', None))
        self._active_popup.show_at_cursor()

    def _on_filter_changed(self):
        self._current_page = 0
        self._load()

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._load()

    def _next_page(self):
        total_pages = max(1, (self._total_count + _PAGE_SIZE - 1) // _PAGE_SIZE)
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._load()

    def _confirm_clear(self):
        reply = QMessageBox.question(
            self,
            "Effacer l'historique",
            "Supprimer définitivement tout l'historique des modifications ?\n"
            "Cette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.history_service.clear_history()
            self._current_page = 0
            self._load()
