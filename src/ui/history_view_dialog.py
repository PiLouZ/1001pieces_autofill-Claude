"""
Dialogue de consultation de l'historique persistant des modifications.
"""

import json
from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    Qt, QHeaderView, QSizePolicy, QMessageBox, QColor,
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


class HistoryViewDialog(QDialog):
    """Vue consultable de l'historique persistant des modifications."""

    def __init__(self, history_service, parent=None):
        super().__init__(parent)
        self.history_service = history_service
        self._current_page = 0
        self._total_count = 0

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
            type_item.setForeground(Qt.white)
            type_item.setBackground(Qt.transparent)
            type_item.setToolTip(action_type)
            type_item.setForeground(QColor(color))
            self._table.setItem(r, 1, type_item)

            # Description : toujours le titre, enrichi du nombre de champs pour les edits multi
            description = title or ''
            if details_json:
                try:
                    details = json.loads(details_json)
                    if isinstance(details, list) and len(details) > 1:
                        description = f"{title} — {len(details)} champs"
                except Exception:
                    pass
            self._set_item(r, 2, description)

            self._set_item(r, 3, device_ref or '')
            self._set_item(r, 4, field_name or '')
            self._set_item(r, 5, old_val or '')
            self._set_item(r, 6, new_val or '')

    def _set_item(self, row: int, col: int, text: str):
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, col, item)

    # ── Interactions ──────────────────────────────────────────────────────────

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
