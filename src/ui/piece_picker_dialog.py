"""
PiecePickerDialog : dialog de sélection de pièce avec recherche en temps réel.
RefTagList        : widget de liste de références supprimables (chips).
"""

import qtawesome as qta
from typing import Optional, List
from ..utils.qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                          QLabel, QPushButton, QLineEdit, QTableWidget,
                          QTableWidgetItem, QHeaderView, Qt, QFrame, QScrollArea,
                          QSize, pyqtSignal, QColor, QFont)
from src.core.logger import app_logger
from .style_manager import StyleManager


# ── RefTagList ───────────────────────────────────────────────────────────────

class RefTagList(QWidget):
    """
    Widget affichant des références comme des lignes (chips) individuellement supprimables.

    Chaque ligne : [ref monospace] [description grisée]  [✕]

    Auto-scrollable : hauteur limitée à MAX_HEIGHT, ascenseur vertical si dépassement.
    Signal ref_removed(str) émis quand l'utilisateur clique ✕.
    """

    ref_removed       = pyqtSignal(str)
    ref_clicked       = pyqtSignal(str)   # émis au clic gauche sur le texte de la référence
    ref_right_clicked = pyqtSignal(str)   # émis au clic droit sur le texte de la référence
    MAX_HEIGHT = 124  # ~4 chips visibles avant scroll

    def __init__(self, parent=None):
        super().__init__(parent)
        self._compact = False

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # ── Chemin normal : QScrollArea (gestionnaire, panneau pièces) ────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(3)

        self._scroll.setWidget(self._content)
        self._outer.addWidget(self._scroll)

        # ── Chemin compact : QWidget plat sans QScrollArea ────────────────
        self._flat = QWidget()
        self._flat.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._flat_layout = QVBoxLayout(self._flat)
        self._flat_layout.setContentsMargins(16, 0, 0, 0)
        self._flat_layout.setSpacing(0)
        self._flat.setVisible(False)
        self._outer.addWidget(self._flat)

        self._refs = []
        self._full_height_mode = False
        # Message affiché quand la liste est vide (mode pleine hauteur seulement)
        self._empty_text = ""
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
        self._refs = list(refs)
        n = len(refs)

        if self._compact:
            # ── Chemin plat : pas de QScrollArea ─────────────────────────────
            while self._flat_layout.count():
                item = self._flat_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for ref in refs:
                desc = (descriptions or {}).get(ref, '')
                row_widget = self._make_row(ref, desc, color)
                self._flat_layout.addWidget(row_widget)

            if not self._full_height_mode:
                self._flat.setVisible(n > 0)
                self.setVisible(n > 0)
        else:
            # ── Chemin normal : QScrollArea ───────────────────────────────────
            while self._layout.count():
                item = self._layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for ref in refs:
                desc = (descriptions or {}).get(ref, '')
                row_widget = self._make_row(ref, desc, color)
                self._layout.addWidget(row_widget)

            if n == 0 and self._full_height_mode and self._empty_text:
                empty = QLabel(self._empty_text)
                empty.setAlignment(Qt.AlignCenter)
                empty.setWordWrap(True)
                empty.setStyleSheet("color: #adb5bd; font-size: 11px; padding-top: 12px;")
                self._layout.addWidget(empty)

            self._layout.addStretch()

            if not self._full_height_mode:
                if n == 0:
                    self.setVisible(False)
                else:
                    self._scroll.setFixedHeight(min(n * 31 + 4, self.MAX_HEIGHT))
                    self.setVisible(True)
        # else full_height_mode : toujours visible, hauteur gérée par le layout parent

    def is_empty(self) -> bool:
        return len(self._refs) == 0

    def enable_full_height_mode(self):
        """Mode hauteur libre : le widget remplit l'espace disponible (panneau latéral)."""
        from ..utils.qt_imports import QSizePolicy
        self._full_height_mode = True
        self.setVisible(True)
        self._scroll.setMaximumHeight(16777215)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Fond du cadre parent plutôt que le gris par défaut de la zone défilante
        # (grands blocs gris vides dans le panneau du gestionnaire de pièces)
        self._scroll.setStyleSheet(StyleManager.ZONE_DEFILEMENT_TRANSPARENTE)
        self._scroll.viewport().setAutoFillBackground(False)

    def set_empty_text(self, text: str):
        """Message centré et estompé affiché quand la liste est vide (mode pleine
        hauteur). Pris en compte au prochain set_refs()."""
        self._empty_text = text

    # ── Interne ──────────────────────────────────────────────────────────────

    def _make_row(self, ref: str, desc: str, color: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            "QWidget { background: transparent; border: none;"
            "border-bottom: 1px solid #eeeeee; } "
            "QWidget:hover { background: #f5f5f5; }"
        )
        row.setFixedHeight(28)

        h = QHBoxLayout(row)
        h.setContentsMargins(8, 3, 6, 3)
        h.setSpacing(6)

        # Référence en monospace bold coloré — cliquable (copie + recherche)
        ref_lbl = QLabel(ref)
        ref_lbl.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
        )
        ref_lbl.setCursor(Qt.PointingHandCursor)
        ref_lbl.setToolTip(f"Cliquer pour rechercher '{ref}'")
        ref_lbl.enterEvent  = lambda event, lbl=ref_lbl, c=color: lbl.setStyleSheet(
            f"color: {c}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
            "text-decoration: underline;"
        )
        ref_lbl.leaveEvent  = lambda event, lbl=ref_lbl, c=color: lbl.setStyleSheet(
            f"color: {c}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
        )
        def _ref_mouse_press(event, r=ref):
            if event.button() == Qt.LeftButton:
                self.ref_clicked.emit(r)
            elif event.button() == Qt.RightButton:
                self.ref_right_clicked.emit(r)
        ref_lbl.mousePressEvent = _ref_mouse_press
        h.addWidget(ref_lbl)

        # Description en gris (si disponible)
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                "color: #6c757d; font-size: 11px; background: transparent; border: none;"
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
        ouvrir_modal(dlg, sur_accepte=lambda: traiter(dlg.selected_ref()))
        # (ouverture_modale.ouvrir_modal : show() + callbacks, jamais exec_)
    """

    def __init__(self, db_manager, parent=None, exclude_ref: Optional[str] = None,
                 title: str = "Sélectionner une pièce",
                 multi_select: bool = False):
        super().__init__(parent)
        self.db_manager = db_manager
        self.exclude_ref = exclude_ref
        self._multi_select = multi_select
        self._selected_ref: Optional[str] = None
        self._selected_refs: List[str] = []
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
        sel_mode = (QTableWidget.SelectionMode.ExtendedSelection
                    if self._multi_select
                    else QTableWidget.SelectionMode.SingleSelection)
        self._table.setSelectionMode(sel_mode)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.itemDoubleClicked.connect(self._on_double_click)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Tri croissant par défaut : sans cela, Qt part de son indicateur par
        # défaut (décroissant) et la liste s'ouvrait de Z à A.
        hdr.setSortIndicator(0, Qt.AscendingOrder)
        self._table.setColumnWidth(0, 130)   # Référence
        self._table.setColumnWidth(1, 270)   # Libellé
        self._table.setColumnWidth(2, 90)    # Statut
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Hint fantôme (visible quand le texte saisi ne correspond à aucune ligne sélectionnée)
        self._phantom_hint = QLabel("")
        self._phantom_hint.setStyleSheet(
            StyleManager.TEXTE_SECONDAIRE_ITALIQUE
        )
        self._phantom_hint.setVisible(False)
        layout.addWidget(self._phantom_hint)

        # Boutons OK / Annuler
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("Sélectionner (plusieurs avec Ctrl/⇧)" if self._multi_select else "Sélectionner")
        self._ok_btn.setIcon(qta.icon('fa5s.check', color='white'))
        self._ok_btn.setIconSize(QSize(11, 11))
        self._ok_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
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
            rows = self.db_manager.lister_pieces_selecteur()
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

            # Col 2 : statut — mêmes icônes et libellés que la colonne Statut du
            # gestionnaire de pièces (et non plus des glyphes ✓ / ⚠)
            if is_phantom:
                status_text, icone, couleur = "Fantôme", 'fa5s.ghost', '#999999'
            elif is_obsolete:
                status_text, icone, couleur = "Obsolète", 'fa5s.ban', '#c62828'
            else:
                status_text, icone, couleur = "OK", 'fa5s.check-circle', '#2e7d32'

            st_item = QTableWidgetItem(status_text)
            st_item.setIcon(qta.icon(icone, color=couleur))
            if is_phantom:
                st_item.setForeground(_phantom_color)
            self._table.setItem(i, 2, st_item)

        self._table.setSortingEnabled(True)

    # ── Filtrage ─────────────────────────────────────────────────────────────

    def _filter(self, text: str):
        """Filtrer la liste et mettre à jour le hint fantôme.

        En mode multi_select, la saisie « REF1; REF2 » filtre les lignes
        correspondantes et les sélectionne automatiquement toutes.
        """
        t = text.lower().strip()

        # Mode multi-ref : termes séparés par « ; »
        if self._multi_select and ';' in t:
            parts = [p.strip() for p in t.split(';') if p.strip()]
            filtered = [
                r for r in self._all_rows
                if any(p in (r[0] or '').lower() or p in (r[1] or '').lower()
                       for p in parts)
            ]
            self._populate(filtered)
            if filtered:
                self._table.selectAll()   # → déclenche _on_selection_changed
            else:
                self._table.clearSelection()
                self._selected_ref = None
            self._update_ok_btn()
            return

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
        selected_rows = sorted(set(item.row() for item in self._table.selectedItems()))
        self._selected_refs = []
        for row in selected_rows:
            ref_item = self._table.item(row, 0)
            if ref_item:
                ref = ref_item.data(Qt.UserRole)
                if ref:
                    self._selected_refs.append(ref)
        self._selected_ref = self._selected_refs[0] if self._selected_refs else None
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

        # En mode multi-select : afficher le nombre de sélections dans le bouton
        if self._multi_select and len(self._selected_refs) > 1:
            self._ok_btn.setText(f"Sélectionner ({len(self._selected_refs)})")
        elif self._multi_select:
            self._ok_btn.setText("Sélectionner (plusieurs avec Ctrl/⇧)")

        # Hint fantôme : visible quand texte saisi mais aucune ligne sélectionnée
        if has_text and not has_selection:
            self._phantom_hint.setText(f"↵  Utiliser « {text} » comme nouvelle référence fantôme")
            self._phantom_hint.setVisible(True)
        else:
            self._phantom_hint.setVisible(False)

    # ── API publique ─────────────────────────────────────────────────────────

    def selected_ref(self) -> Optional[str]:
        """Retourne la première référence sélectionnée (ou le texte brut saisi)."""
        return self._selected_ref or self._search_input.text().strip() or None

    def selected_refs(self) -> List[str]:
        """Retourne toutes les références sélectionnées (mode multi_select)."""
        if self._selected_refs:
            return list(self._selected_refs)
        text = self._search_input.text().strip()
        return [text] if text else []
