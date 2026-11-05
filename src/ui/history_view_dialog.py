"""
Dialogue de consultation de l'historique persistant des modifications.
"""

import json
import re
from datetime import datetime
from ..utils.qt_imports import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    Qt,
    QHeaderView,
    QMessageBox,
    QColor,
    QScrollArea,
    QFrame,
    QWidget
)
from PyQt5.QtWidgets import QDateEdit
from PyQt5.QtCore import QDate
import qtawesome as qta
from .popup_positioning import PopupAuCurseurMixin
from .style_manager import StyleManager
from ..core.config import Config
from ..utils.boites import demander_oui_non

_PAGE_SIZE = 100

_ACTION_LABELS = {
    'all':    'Tous',
    'edit':   'Modification',
    'import': 'Import',
    'export': 'Export',
    'delete': 'Suppression',
    'error':  'Erreur',
    'piece':  'Pièce',
    'undo':   'Annulation',
}

# Mêmes teintes que l'historique de la fenêtre principale
# (_ACTION_STYLES dans user_interaction_service.py).
_ACTION_COLORS = {
    'edit':   '#2F6CD0',
    'import': '#1E7F36',
    'export': '#8E44AD',
    'delete': '#A33A3A',
    'error':  '#D61F1F',
    'piece':  '#0E7A64',
    'undo':   '#B05E00',
}

# Au-delà de cette longueur, une cellule risque d'être coupée : texte complet en infobulle
_TOOLTIP_MIN_LEN = 20


def _format_timestamp(timestamp) -> str:
    """'2026-10-09 10:09:31' → '09/10/2026 10:09' (format des filtres de date).

    Valeur inattendue : renvoyée tronquée telle quelle, comme avant.
    """
    if not timestamp:
        return ''
    text = str(timestamp)
    try:
        return datetime.strptime(text[:16], "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text[:16]


# Types d'action pour lesquels un popup de détails est pertinent
_DETAIL_ACTION_TYPES = {'import', 'export', 'delete', 'error', 'piece', 'undo'}

# Ligne de fichier d'un import multi-fichiers : « Fichier PDF 805101.pdf : 357 lignes extraites »
# (un import d'un seul fichier écrit « Fichier PDF : 357 lignes extraites », sans nom)
_RE_LIGNE_FICHIER = re.compile(r'^Fichier \S+ (.+) : (\d+) lignes? extraites?$')


def _regrouper_fichiers(details: list) -> tuple:
    """Réunir les lignes de fichiers consécutives d'un import multi-fichiers.

    Le popup forme une section par ligne de titre et y range les lignes « ==> »
    qui suivent ; une section sans ligne « ==> » n'est pas affichée. Or les lignes
    de fichiers se suivent : seule la dernière restait, avec le total de l'import
    comme si elle l'avait produit seule. Une suite d'au moins 2 lignes de fichiers
    devient donc une section « N fichiers » listant chaque fichier ; le total
    (« ==> Lignes traitées ») qui suit s'y range à la fin.

    Returns:
        (détails transformés, titres des sections de fichiers créées)
    """
    resultat, titres = [], set()
    i = 0
    while i < len(details):
        j = i
        while j < len(details) and isinstance(details[j], str) \
                and _RE_LIGNE_FICHIER.match(details[j].strip()):
            j += 1
        if j - i >= 2:
            titre = f"{j - i} fichiers"
            titres.add(titre)
            resultat.append(titre)
            for ligne in details[i:j]:
                nom, n = _RE_LIGNE_FICHIER.match(ligne.strip()).groups()
                pluriel = '' if n == '1' else 's'
                resultat.append(f"==> {nom} : {n} ligne{pluriel} extraite{pluriel}")
            i = j
        else:
            resultat.append(details[i])
            i += 1
    return resultat, titres


# ── Popup de détails ──────────────────────────────────────────────────────────

class HistoryDetailPopup(PopupAuCurseurMixin, QDialog):
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

        self.setStyleSheet(StyleManager.POPUP_CADRE)

        # ── En-tête ────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            StyleManager.POPUP_ENTETE
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
        scroll.setStyleSheet(StyleManager.FOND_BLANC)

        content = QWidget()
        content.setStyleSheet(StyleManager.FOND_BLANC)
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(12, 10, 12, 12)
        c_layout.setSpacing(6)

        # Rendu des lignes groupées en sections
        current_section = None
        section_items = []

        def _flush_section():
            nonlocal current_section, section_items
            # Une alerte « [!] » s'affiche même sans ligne « ==> » sous elle
            # (alerte de mapping) : sans cette exception, elle disparaissait.
            alerte = bool(current_section and current_section.startswith('[!]'))
            if current_section is not None and (section_items or alerte):
                c_layout.addWidget(
                    self._section(current_section, section_items, color, alerte,
                                  retour_ligne=current_section in titres_fichiers)
                )
            current_section = None
            section_items = []

        details, titres_fichiers = _regrouper_fichiers(details)
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
            elif stripped.startswith('- '):
                # Sous-élément du « ==> » précédent (marques alignées) : reste
                # dans la section, en retrait, au lieu d'ouvrir une section
                if current_section is None:
                    current_section = ''
                section_items.append(f"      {stripped}")
            else:
                _flush_section()
                current_section = stripped.rstrip(':')
                section_items = []

        _flush_section()

        if not details:
            lbl = QLabel("Aucun détail disponible.")
            lbl.setStyleSheet(StyleManager.TEXTE_SECONDAIRE_ITALIQUE)
            c_layout.addWidget(lbl)

        c_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        self.setFixedWidth(self.WIDTH)

    @staticmethod
    def _section(title: str, items: list, color: str, alerte: bool = False,
                 retour_ligne: bool = False) -> QWidget:
        """Bloc section : titre optionnel + liste d'items.

        Alerte « [!] » : jaune avertissement, comme dans le panneau Historique
        (pas de rouge, réservé aux erreurs), et retour à la ligne pour que la
        fourchette ou le conseil ne soient pas coupés au bord du popup.
        """
        bg = Config.Colors.WARNING_BG if alerte else '#f8f9fa'
        border = Config.Colors.WARNING if alerte else '#dee2e6'
        if alerte:
            color = Config.Colors.WARNING_TEXT
        texte = Config.Colors.WARNING_TEXT if alerte else '#2c3e50'
        # Retour à la ligne : alertes, et noms de fichiers longs d'un multi-import
        retour_ligne = retour_ligne or alerte

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
            title_lbl.setWordWrap(retour_ligne)
            layout.addWidget(title_lbl)

        for item in items:
            item_lbl = QLabel(f"  {item}")
            item_lbl.setStyleSheet(
                f"color: {texte}; font-size: 11px;"
                "background: transparent; border: none;"
            )
            item_lbl.setWordWrap(retour_ligne)
            layout.addWidget(item_lbl)

        return w



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
        # Ouverture plus large que le minimum : la description est la colonne lue
        self.resize(1200, 650)
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

        # Filtres de même hauteur (liste, dates, recherche)
        filter_widget = QWidget()
        filter_widget.setLayout(filter_bar)
        filter_widget.setStyleSheet(StyleManager.COMPACT_FILTER_BAR)
        layout.addWidget(filter_widget)

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

        # Largeurs : « Appareil » ne se cale plus sur son contenu (des libellés
        # d'appareil longs écrasaient Description / Ancienne / Nouvelle jusqu'à
        # « crip », « ne », « lle »). Largeurs fixes mais ajustables ; Description
        # prend la place restante ; texte complet en infobulle (cf. _set_item).
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Date
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        hh.setSectionResizeMode(2, QHeaderView.Stretch)            # Description
        hh.setSectionResizeMode(3, QHeaderView.Interactive)        # Appareil
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Champ
        hh.setSectionResizeMode(5, QHeaderView.Interactive)        # Ancienne
        hh.setSectionResizeMode(6, QHeaderView.Interactive)        # Nouvelle
        self._table.setColumnWidth(3, 220)
        self._table.setColumnWidth(5, 150)
        self._table.setColumnWidth(6, 150)

        self._table.cellClicked.connect(self._on_cell_clicked)

        layout.addWidget(self._table)

        # ── Barre de statut + pagination ──────────────────────────────────────
        bottom_bar = QHBoxLayout()

        self._count_label = QLabel("0 entrée")
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
        clear_btn.setStyleSheet(StyleManager.DANGER_COMPACT_BUTTON)
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

        _formatted = f"{self._total_count:,}".replace(',', ' ')
        self._count_label.setText(f"{_formatted} {'entrée' if self._total_count <= 1 else 'entrées'}")
        self._page_label.setText(f"Page {self._current_page + 1} / {total_pages}")
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < total_pages - 1)

    def _populate_table(self, rows):
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            _id, timestamp, action_type, title, details_json, device_ref, field_name, old_val, new_val = row

            # Date — affichage court, au format des filtres (jj/mm/aaaa hh:mm)
            ts_display = _format_timestamp(timestamp)
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
                desc_item.setToolTip(f"{description}\nCliquez pour voir les détails")
            elif len(description) > _TOOLTIP_MIN_LEN:
                desc_item.setToolTip(description)

            self._table.setItem(r, 2, desc_item)

            self._set_item(r, 3, device_ref or '')
            self._set_item(r, 4, field_name or '')
            self._set_item(r, 5, old_val or '')
            self._set_item(r, 6, new_val or '')

    def _set_item(self, row: int, col: int, text: str):
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        # Texte potentiellement coupé par la largeur de colonne → complet en infobulle
        if len(str(text)) > _TOOLTIP_MIN_LEN:
            item.setToolTip(str(text))
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
        # Rappel à la validation (boîte modale non bloquante, jamais de boucle imbriquée)
        def _suite():
            self.history_service.clear_history()
            self._current_page = 0
            self._load()

        demander_oui_non(self, "Effacer l'historique", "Supprimer définitivement tout l'historique des modifications ?\nCette action est irréversible.", _suite, defaut=QMessageBox.No)
