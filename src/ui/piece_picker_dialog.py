"""
PiecePickerDialog : dialog de sélection de pièce avec recherche en temps réel.
RefTagList        : widget de liste de références supprimables (chips).
"""

from typing import Optional, List
from .qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                          QLabel, QPushButton, QLineEdit, QTableWidget,
                          QTableWidgetItem, QHeaderView, Qt, QFrame, QScrollArea,
                          QSize, pyqtSignal, QColor, QFont)
from src.core.config import Config
from src.core.logger import app_logger


# ── RefTagList ───────────────────────────────────────────────────────────────

class RefTagList(QWidget):
    """
    Widget affichant des références comme des lignes (chips) individuellement supprimables.

    Chaque ligne : [ref monospace] [description grisée]  [✕]

    Auto-scrollable : hauteur limitée à MAX_HEIGHT, ascenseur vertical si dépassement.
    Signal ref_removed(str) émis quand l'utilisateur clique ✕.
    """

    ref_removed = pyqtSignal(str)
    MAX_HEIGHT = 124  # ~4 chips visibles avant scroll

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Zone scrollable
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(3)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._refs = []
        self.setVisible(False)

    # ── API publique ─────────────────────────────────────────────────────────

    def set_refs(self, refs: list, color: str = '#2c3e50',
                 descriptions: Optional[dict] = None):
        """
        Mettre à jour la liste des chips.

        :param refs: liste de références à afficher
        :param color: couleur du texte de la référence
        :param descriptions: dict {ref: description} optionnel pour affichage inline
        """
        # Nettoyer les widgets précédents
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._refs = list(refs)

        for ref in refs:
            desc = (descriptions or {}).get(ref, '')
            row_widget = self._make_row(ref, desc, color)
            self._layout.addWidget(row_widget)

        # Hauteur adaptive : limitée à MAX_HEIGHT, ascenseur si plus
        n = len(refs)
        if n == 0:
            self.setVisible(False)
        else:
            natural_h = n * 31 + 4  # 28px chip + 3px spacing + marges
            self._scroll.setFixedHeight(min(natural_h, self.MAX_HEIGHT))
            self.setVisible(True)

    def get_refs(self) -> list:
        return list(self._refs)

    def is_empty(self) -> bool:
        return len(self._refs) == 0

    # ── Interne ──────────────────────────────────────────────────────────────

    def _make_row(self, ref: str, desc: str, color: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            "QWidget { background: #f8f9fa; border: 1px solid #dee2e6;"
            "border-radius: 4px; } "
            "QWidget:hover { background: #e9ecef; border-color: #adb5bd; }"
        )
        row.setFixedHeight(28)

        h = QHBoxLayout(row)
        h.setContentsMargins(8, 3, 6, 3)
        h.setSpacing(6)

        # Référence en monospace bold coloré
        ref_lbl = QLabel(ref)
        ref_lbl.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
        )
        h.addWidget(ref_lbl)

        # Description en gris (si disponible)
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                "color: #6c757d; font-size: 10px; background: transparent; border: none;"
            )
            desc_lbl.setMaximumWidth(200)
            h.addWidget(desc_lbl, 1)
        else:
            h.addStretch(1)

        # ✕ cliquable (QLabel pour éviter la hauteur minimale imposée par macOS)
        remove_lbl = QLabel("<b>✕</b>")
        remove_lbl.setStyleSheet(
            "color: #dc3545; font-size: 13px; background: transparent; border: none;"
            "padding: 0 2px;"
        )
        remove_lbl.setToolTip(f"Retirer {ref}")
        remove_lbl.setCursor(Qt.PointingHandCursor)
        remove_lbl.mousePressEvent = (lambda event, r=ref: self.ref_removed.emit(r))
        h.addWidget(remove_lbl)

        return row


# ── PiecePickerDialog ────────────────────────────────────────────────────────

class PiecePickerDialog(QDialog):
    """
    Dialog de sélection d'une pièce avec recherche en temps réel.

    Affiche un tableau (ref | description | statut) filtrables.
    Mode 'single' : retourne une référence via selected_ref().

    Usage :
        dlg = PiecePickerDialog(db_manager, parent=self, exclude_ref='AS001')
        if dlg.exec_() == QDialog.Accepted:
            ref = dlg.selected_ref()
    """

    def __init__(self, db_manager, parent=None, exclude_ref: Optional[str] = None,
                 title: str = "Sélectionner une pièce"):
        super().__init__(parent)
        self.db_manager = db_manager
        self.exclude_ref = exclude_ref
        self._selected_ref: Optional[str] = None
        self._all_rows: list = []  # cache des données

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 420)
        self._init_ui()
        self._load_pieces()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Champ de recherche / saisie libre
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Référence :"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Rechercher ou saisir une nouvelle référence…")
        self._search_input.textChanged.connect(self._filter)
        self._search_input.returnPressed.connect(self._on_search_confirmed)
        search_row.addWidget(self._search_input)
        layout.addLayout(search_row)

        # Tableau
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Référence", "Libellé", "Statut"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.itemDoubleClicked.connect(self._on_double_click)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(0, 130)   # Référence
        self._table.setColumnWidth(1, 270)   # Libellé
        self._table.setColumnWidth(2, 90)    # Statut
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Hint fantôme (visible quand le texte saisi ne correspond à aucune ligne sélectionnée)
        self._phantom_hint = QLabel("")
        self._phantom_hint.setStyleSheet(
            "color: #6c757d; font-size: 11px; font-style: italic;"
        )
        self._phantom_hint.setVisible(False)
        layout.addWidget(self._phantom_hint)

        # Boutons OK / Annuler
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("Sélectionner")
        self._ok_btn.setEnabled(False)
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    # ── Chargement ───────────────────────────────────────────────────────────

    def _load_pieces(self):
        """Charger toutes les pièces depuis la base."""
        try:
            query = """
                SELECT p.ref_piece, p.description,
                       COALESCE(p.is_obsolete, 0), COALESCE(p.is_phantom, 0)
                FROM pieces p
                ORDER BY p.ref_piece ASC
            """
            rows = self.db_manager.execute_query(query)
            self._all_rows = [r for r in (rows or [])
                              if r[0] and r[0] != self.exclude_ref]
            self._populate(self._all_rows)
        except Exception as e:
            app_logger.error(f"PiecePickerDialog: erreur chargement pièces: {e}")

    def _populate(self, rows: list):
        """Remplir le tableau avec les lignes fournies."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))

        _italic = QFont()
        _italic.setItalic(True)
        _phantom_color = QColor(150, 150, 150)

        for i, (ref, desc, is_obsolete, is_phantom) in enumerate(rows):
            # Col 0 : référence
            ref_item = QTableWidgetItem(ref or "")
            ref_item.setData(Qt.UserRole, ref)
            if is_phantom:
                ref_item.setForeground(_phantom_color)
                ref_item.setFont(_italic)
            self._table.setItem(i, 0, ref_item)

            # Col 1 : libellé
            desc_item = QTableWidgetItem(desc or "")
            if is_phantom:
                desc_item.setForeground(_phantom_color)
                desc_item.setFont(_italic)
            self._table.setItem(i, 1, desc_item)

            # Col 2 : statut
            if is_phantom:
                status_text = "👻 Fantôme"
                status_color = QColor(150, 150, 150)
            elif is_obsolete:
                status_text = "⚠ Obsolète"
                status_color = QColor(192, 57, 43)
            else:
                status_text = "✓"
                status_color = QColor(52, 168, 83)

            st_item = QTableWidgetItem(status_text)
            st_item.setForeground(status_color)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 2, st_item)

        self._table.setSortingEnabled(True)

    # ── Filtrage ─────────────────────────────────────────────────────────────

    def _filter(self, text: str):
        """Filtrer la liste et mettre à jour le hint fantôme."""
        t = text.lower().strip()
        if not t:
            self._populate(self._all_rows)
        else:
            filtered = [
                r for r in self._all_rows
                if t in (r[0] or '').lower() or t in (r[1] or '').lower()
            ]
            self._populate(filtered)

        # Désélectionner si le texte a changé
        self._table.clearSelection()
        self._selected_ref = None
        self._update_ok_btn()

    # ── Sélection tableau ────────────────────────────────────────────────────

    def _on_selection_changed(self):
        selected = self._table.selectedItems()
        if selected:
            row = self._table.currentRow()
            ref_item = self._table.item(row, 0)
            self._selected_ref = ref_item.data(Qt.UserRole) if ref_item else None
        else:
            self._selected_ref = None
        self._update_ok_btn()

    def _on_double_click(self, item):
        row = self._table.currentRow()
        ref_item = self._table.item(row, 0)
        if ref_item:
            self._selected_ref = ref_item.data(Qt.UserRole)
            self.accept()

    def _on_search_confirmed(self):
        """Entrée clavier dans le champ de recherche : valider si quelque chose est disponible."""
        if self._ok_btn.isEnabled():
            self.accept()

    # ── Hint + bouton OK ─────────────────────────────────────────────────────

    def _update_ok_btn(self):
        text = self._search_input.text().strip()
        has_selection = bool(self._selected_ref)
        has_text = bool(text)

        self._ok_btn.setEnabled(has_selection or has_text)

        # Hint fantôme : visible quand texte saisi mais aucune ligne sélectionnée
        if has_text and not has_selection:
            self._phantom_hint.setText(f"↵  Utiliser « {text} » comme nouvelle référence fantôme")
            self._phantom_hint.setVisible(True)
        else:
            self._phantom_hint.setVisible(False)

    # ── API publique ─────────────────────────────────────────────────────────

    def selected_ref(self) -> Optional[str]:
        """
        Retourne la référence à utiliser :
        - ligne sélectionnée dans le tableau si présente
        - sinon le texte brut du champ de recherche (nouvelle référence fantôme)
        """
        return self._selected_ref or self._search_input.text().strip() or None
