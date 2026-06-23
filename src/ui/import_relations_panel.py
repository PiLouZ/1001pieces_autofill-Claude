"""Panneau « par groupes » de déclaration des relations entre réfs importées (Lot 2).

Agencement QSplitter : cartes à gauche (libellé, Obsolète, « remplace [base] »),
zone groupes à droite, récap sticky en bas.

Zone groupes (drag-drop) : un réservoir « Non groupées » + deux sections de boîtes :
- **Lignées de succession** : Courante éditable (lot/base/à créer) + membres (anciennes
  versions) + checkbox « Équivalente ».
- **Groupes d'équivalence** : Courante repère optionnelle + membres (tous valides) +
  checkbox « Équivalente ».
La checkbox relie les courantes des groupes cochés. États dérivés via `derive`.

Widget autonome (testable offscreen).
"""

from PyQt5.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QCheckBox, QPushButton, QScrollArea, QCompleter, QSplitter,
    QListWidget, QListWidgetItem, QAbstractItemView,
)
import qtawesome as qta

from ..services.import_relations import (
    Group, CardData, derive, KIND_SUCCESSION, KIND_EQUIVALENCE,
)
from ..core.config import pluralize

# Couleurs alignées sur les bannières du tableau principal (table_controller.py) :
# succession = famille BLEUE (#E3F2FD/#64B5F6/#0D47A1), équivalence = famille VIOLETTE
# (#F3E5F5/#CE93D8/#6A1B9A). Nuances par index pour distinguer plusieurs groupes.
_SUCC_COLORS = ["#0D47A1", "#1565C0", "#1976D2", "#1E88E5", "#42A5F5", "#5C6BC0"]
_EQUIV_COLORS = ["#6A1B9A", "#8E24AA", "#9C27B0", "#AB47BC", "#7B1FA2", "#BA68C8"]
# Fonds/bordures pâles officiels, partagés par les boîtes et les cartes courantes.
_SUCC_BG, _SUCC_BORDER = "#E3F2FD", "#64B5F6"
_EQUIV_BG, _EQUIV_BORDER = "#F3E5F5", "#CE93D8"


def _succ_color(i):
    return _SUCC_COLORS[i % len(_SUCC_COLORS)]


def _equiv_color(i):
    return _EQUIV_COLORS[i % len(_EQUIV_COLORS)]


def _lbl(text, size=11, color="#495057", width=None, bold=False):
    w = QLabel(text)
    w.setStyleSheet(f"font-size: {size}px; color: {color}; border: none;"
                    + (" font-weight: bold;" if bold else ""))
    if width:
        w.setFixedWidth(width)
    return w


# ── Carte d'une référence ─────────────────────────────────────────────────────

class RefCard(QFrame):
    changed = pyqtSignal()

    def __init__(self, ref, filename="", is_solo=False, ref_model=None, parent=None):
        super().__init__(parent)
        self.ref = ref
        self.filename = filename
        self.is_solo = is_solo
        self._ref_model = ref_model
        self.setObjectName("refCard")
        self._build()

    def _build(self):
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        row1 = QHBoxLayout()
        row1.addWidget(_lbl(self.ref, size=12, color="#212121", bold=True))
        if not self.is_solo and self.filename:
            f = _lbl(self.filename, color="#666")
            f.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row1.addWidget(f, 1)
        else:
            row1.addStretch(1)
        self.head_badge = QLabel("")
        self.head_badge.setStyleSheet("border: none;")
        row1.addWidget(self.head_badge)
        self.equiv_badge = QLabel("")
        self.equiv_badge.setStyleSheet("border: none;")
        row1.addWidget(self.equiv_badge)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(_lbl("Libellé :"))
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Description (optionnel)")
        row2.addWidget(self.desc_input, 1)
        self.obsolete_check = QCheckBox("Obsolète")
        self.obsolete_check.setStyleSheet("font-size: 11px; color: #c0392b; border: none;")
        self.obsolete_check.stateChanged.connect(lambda *_: self.changed.emit())
        row2.addWidget(self.obsolete_check)
        lay.addLayout(row2)

        self.base_toggle = QPushButton("▸ Cette réf remplace une réf en base")
        self.base_toggle.setFlat(True)
        self.base_toggle.setCursor(Qt.PointingHandCursor)
        self.base_toggle.setStyleSheet(
            "QPushButton { color: #0066cc; font-size: 11px; text-align: left;"
            " border: none; background: transparent; padding: 2px; }"
            "QPushButton:hover { text-decoration: underline; }")
        self.base_toggle.clicked.connect(self._toggle_base)
        lay.addWidget(self.base_toggle)

        self.base_zone = QWidget()
        bz = QHBoxLayout(self.base_zone)
        bz.setContentsMargins(12, 0, 4, 2)
        bz.addWidget(_lbl("Remplace (réf base) :", width=150))
        self.replaces_input = QLineEdit()
        self.replaces_input.setPlaceholderText("Ancienne réf en base")
        self.replaces_input.textChanged.connect(lambda *_: self.changed.emit())
        bz.addWidget(self.replaces_input, 1)
        self.base_zone.setVisible(False)
        lay.addWidget(self.base_zone)

        self.obs_hint = QLabel("")
        self.obs_hint.setStyleSheet("color: #9e9e9e; font-size: 10px; border: none;")
        self.obs_hint.setVisible(False)
        lay.addWidget(self.obs_hint)

        if self._ref_model is not None:
            comp = QCompleter(self._ref_model, self.replaces_input)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
            self.replaces_input.setCompleter(comp)

    def _toggle_base(self):
        vis = not self.base_zone.isVisible()
        self.base_zone.setVisible(vis)
        self.base_toggle.setText(("▾" if vis else "▸") + " Cette réf remplace une réf en base")

    def get_card(self):
        return CardData(ref=self.ref,
                        is_obsolete=self.obsolete_check.isChecked(),
                        base_replaces=(self.replaces_input.text().strip() or None))

    def apply_derived(self, is_courante, succ_gi, equiv_gi, obsolete_via_group):
        color = _succ_color(succ_gi) if succ_gi is not None else None
        border = f"border-left: 4px solid {color};" if color else ""
        self.setStyleSheet(
            f"#refCard {{ background: white; border: 1px solid #e9ecef; {border} border-radius: 4px; }}")
        if is_courante:
            self.head_badge.setPixmap(qta.icon('fa5s.crown', color='#1565C0').pixmap(12, 12))
            self.head_badge.setToolTip("Courante d'une lignée")
        else:
            self.head_badge.clear()
        if equiv_gi is not None:
            self.equiv_badge.setText("●")
            self.equiv_badge.setStyleSheet(f"color: {_equiv_color(equiv_gi)}; border: none; font-size: 14px;")
            self.equiv_badge.setToolTip("Membre d'un groupe d'équivalence")
        else:
            self.equiv_badge.setText("")
        if obsolete_via_group and not self.obsolete_check.isChecked():
            self.obs_hint.setText("→ deviendra obsolète (ancienne version)")
            self.obs_hint.setVisible(True)
        else:
            self.obs_hint.setVisible(False)


# ── Listes de pastilles drag-drop ─────────────────────────────────────────────

class _RefList(QListWidget):
    dropped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.Adjust)
        self.setMaximumHeight(64)
        self.setStyleSheet("QListWidget { border: 1px dashed #ccc; border-radius: 4px; }")

    def dropEvent(self, event):
        super().dropEvent(event)
        self.dropped.emit()

    def refs(self):
        return [self.item(i).text() for i in range(self.count())]


# ── Boîte d'un groupe ─────────────────────────────────────────────────────────

class GroupBox(QFrame):
    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)
    empty_requested = pyqtSignal(object)

    def __init__(self, kind, index, ref_model=None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.index = index
        self._ref_model = ref_model
        self.setObjectName("groupBox")
        self._build()

    def _build(self):
        self.setFrameShape(QFrame.StyledPanel)
        is_succ = self.kind == KIND_SUCCESSION
        col = _succ_color(self.index) if is_succ else _equiv_color(self.index)
        bg = _SUCC_BG if is_succ else _EQUIV_BG
        border = _SUCC_BORDER if is_succ else _EQUIV_BORDER
        self.setStyleSheet(
            f"#groupBox {{ background: {bg}; border: 1px solid {border};"
            f" border-left: 4px solid {col}; border-radius: 4px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(3)

        head = QHBoxLayout()
        name = "Lignée" if self.kind == KIND_SUCCESSION else "Éq."
        head.addWidget(_lbl(f"{name} {self.index + 1}", color=col, bold=True))
        head.addStretch(1)
        self.cross_check = QCheckBox("Équivalente")
        self.cross_check.setToolTip("Sa courante est équivalente à celle des autres groupes cochés")
        self.cross_check.setStyleSheet("font-size: 10px; border: none;")
        self.cross_check.stateChanged.connect(lambda *_: self.changed.emit())
        head.addWidget(self.cross_check)
        empty = QPushButton("vider")
        empty.setFlat(True)
        empty.setStyleSheet("color: #0066cc; font-size: 10px; border: none;")
        empty.clicked.connect(lambda: self.empty_requested.emit(self))
        head.addWidget(empty)
        rem = QPushButton("suppr")
        rem.setFlat(True)
        rem.setStyleSheet("color: #c0392b; font-size: 10px; border: none;")
        rem.clicked.connect(lambda: self.remove_requested.emit(self))
        head.addWidget(rem)
        lay.addLayout(head)

        crow = QHBoxLayout()
        clbl = "Courante :" if self.kind == KIND_SUCCESSION else "Courante (repère) :"
        crow.addWidget(_lbl(clbl, width=130))
        self.courante_combo = QComboBox()
        self.courante_combo.setEditable(True)
        self.courante_combo.setInsertPolicy(QComboBox.NoInsert)
        self.courante_combo.lineEdit().setPlaceholderText("réf récente (lot, base ou à créer)")
        self.courante_combo.editTextChanged.connect(lambda *_: self.changed.emit())
        crow.addWidget(self.courante_combo, 1)
        lay.addLayout(crow)

        self.members = _RefList()
        self.members.dropped.connect(self.changed)
        lay.addWidget(self.members)

        if self._ref_model is not None:
            comp = QCompleter(self._ref_model, self.courante_combo.lineEdit())
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
            self.courante_combo.lineEdit().setCompleter(comp)

    def set_courante_options(self, refs):
        cur = self.courante_combo.currentText()
        self.courante_combo.blockSignals(True)
        self.courante_combo.clear()
        self.courante_combo.addItems(refs)
        self.courante_combo.setCurrentText(cur)
        self.courante_combo.blockSignals(False)

    def to_group(self):
        return Group(kind=self.kind,
                     courante=(self.courante_combo.currentText().strip() or None),
                     members=self.members.refs(),
                     cross_equivalent=self.cross_check.isChecked())


# ── Zone des groupes ──────────────────────────────────────────────────────────

class GroupsZone(QWidget):
    changed = pyqtSignal()

    def __init__(self, refs, ref_model=None, parent=None):
        super().__init__(parent)
        self._all_refs = list(refs)
        self._ref_model = ref_model
        self._succ_boxes = []
        self._equiv_boxes = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrer une réf…")
        self._filter.addAction(qta.icon('fa5s.search', color='#888'), QLineEdit.LeadingPosition)
        self._filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self._filter)

        # Réservoir « Non groupées » en ligne, pleine largeur, en haut
        lay.addWidget(_lbl("Non groupées", bold=True))
        self.reservoir = _RefList()
        for r in self._all_refs:
            self.reservoir.addItem(QListWidgetItem(r))
        self.reservoir.dropped.connect(self.changed)
        lay.addWidget(self.reservoir)

        # Deux colonnes côte à côte : succession (gauche) | équivalence (droite),
        # chacune avec son propre ascenseur vertical.
        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(6)

        self._succ_lay, succ_col = self._build_group_column(
            "Lignées de succession", "#1565C0",
            "+ Nouvelle lignée", lambda: self.add_group(KIND_SUCCESSION))
        cols.addWidget(succ_col, 1)

        self._equiv_lay, equiv_col = self._build_group_column(
            "Groupes d'équivalence", "#6A1B9A",
            "+ Nouveau groupe d'équivalence", lambda: self.add_group(KIND_EQUIVALENCE))
        cols.addWidget(equiv_col, 1)

        lay.addLayout(cols, 1)

    def _build_group_column(self, title, color, btn_text, on_add):
        """Construit une colonne (titre + zone scrollable de boîtes + bouton d'ajout).
        Retourne (layout_d_ancrage_des_boîtes, widget_colonne)."""
        col = QWidget()
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        cl.addWidget(_lbl(title, bold=True, color=color))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        anchor = QWidget()
        anchor_lay = QVBoxLayout(anchor)
        anchor_lay.setContentsMargins(2, 2, 2, 2)
        anchor_lay.setSpacing(4)
        anchor_lay.setAlignment(Qt.AlignTop)
        scroll.setWidget(anchor)
        cl.addWidget(scroll, 1)

        btn = QPushButton(btn_text)
        btn.clicked.connect(on_add)
        cl.addWidget(btn)
        return anchor_lay, col

    def add_group(self, kind):
        boxes = self._succ_boxes if kind == KIND_SUCCESSION else self._equiv_boxes
        layout = self._succ_lay if kind == KIND_SUCCESSION else self._equiv_lay
        box = GroupBox(kind, len(boxes), ref_model=self._ref_model)
        box.changed.connect(self.changed)
        box.remove_requested.connect(self._remove_box)
        box.empty_requested.connect(self._empty_box)
        box.members.dropped.connect(self.changed)
        boxes.append(box)
        layout.addWidget(box)
        self.changed.emit()
        return box

    def _empty_box(self, box):
        for r in box.members.refs():
            self.reservoir.addItem(QListWidgetItem(r))
        box.members.clear()
        self.changed.emit()

    def _remove_box(self, box):
        for r in box.members.refs():
            self.reservoir.addItem(QListWidgetItem(r))
        boxes = self._succ_boxes if box.kind == KIND_SUCCESSION else self._equiv_boxes
        if box in boxes:
            boxes.remove(box)
        box.setParent(None)
        # ré-indexer
        for i, b in enumerate(boxes):
            b.index = i
        self.changed.emit()

    def _apply_filter(self, text):
        text = (text or "").strip().lower()
        lists = [self.reservoir] + [b.members for b in self._succ_boxes + self._equiv_boxes]
        for lst in lists:
            for i in range(lst.count()):
                it = lst.item(i)
                it.setHidden(bool(text) and text not in it.text().lower())

    def groups(self):
        return [b.to_group() for b in self._succ_boxes + self._equiv_boxes]

    def all_boxes(self):
        return self._succ_boxes + self._equiv_boxes


# ── Panneau global ────────────────────────────────────────────────────────────

class RelationsPanel(QWidget):
    def __init__(self, refs, is_solo=False, base_refs=None, parent=None):
        super().__init__(parent)
        self._is_solo = is_solo
        self._base_set = set(base_refs or [])
        self._lot_refs = {r for r, _ in refs}
        self._ref_model = QStringListModel(sorted(self._base_set), self)
        self._suppress = False
        self.cards = []
        self._build(refs)
        self.recompute()

    def _build(self, refs):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        splitter = QSplitter(Qt.Horizontal)

        left = QScrollArea()
        left.setWidgetResizable(True)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(6, 6, 6, 6)
        cl.setSpacing(6)
        cl.setAlignment(Qt.AlignTop)
        for ref, filename in refs:
            card = RefCard(ref, filename, is_solo=self._is_solo, ref_model=self._ref_model)
            card.changed.connect(self.recompute)
            self.cards.append(card)
            cl.addWidget(card)
        left.setWidget(content)
        splitter.addWidget(left)

        if not self._is_solo:
            self.groups_zone = GroupsZone([r for r, _ in refs], ref_model=self._ref_model)
            self.groups_zone.changed.connect(self.recompute)
            splitter.addWidget(self.groups_zone)
            splitter.setSizes([560, 440])
        else:
            self.groups_zone = None
        lay.addWidget(splitter, 1)

        self.recap = QLabel("")
        self.recap.setWordWrap(True)
        self.recap.setStyleSheet(
            "background: #f1f3f5; border: 1px solid #dee2e6; border-radius: 4px;"
            " padding: 6px; font-size: 11px; color: #333;")
        lay.addWidget(self.recap)

    def get_groups(self):
        return self.groups_zone.groups() if self.groups_zone else []

    def get_cards(self):
        return [c.get_card() for c in self.cards]

    def recompute(self):
        if self._suppress:
            return
        self._suppress = True
        try:
            groups = self.get_groups()
            cards = self.get_cards()
            d = derive(groups, cards, self._lot_refs, self._base_set)
            # Courantes proposées pour les combos (lot)
            lot_sorted = sorted(self._lot_refs)
            for box in (self.groups_zone.all_boxes() if self.groups_zone else []):
                box.set_courante_options(lot_sorted)
            for card in self.cards:
                card.apply_derived(
                    is_courante=(card.ref in d.courantes),
                    succ_gi=d.succ_group_of.get(card.ref),
                    equiv_gi=d.equiv_group_of.get(card.ref),
                    obsolete_via_group=(card.ref in d.obsoletes),
                )
        finally:
            self._suppress = False
        self._update_recap(groups, cards, d)

    def _update_recap(self, groups, cards, d):
        n = len(self.cards)
        n_succ = sum(1 for g in groups if g.kind == KIND_SUCCESSION)
        n_equiv = sum(1 for g in groups if g.kind == KIND_EQUIVALENCE)
        courantes = sorted({g.courante for g in groups
                            if g.kind == KIND_SUCCESSION and g.courante})
        n_obs = len(d.obsoletes)
        ungrouped = sum(1 for c in self.cards
                        if c.ref not in d.succ_group_of and c.ref not in d.equiv_group_of)
        parts = [pluralize(n, 'réf')]
        if n_succ:
            parts.append(f"{pluralize(n_succ, 'lignée')}" + (f" (courantes : {', '.join(courantes)})" if courantes else ""))
        if n_equiv:
            parts.append(pluralize(n_equiv, "groupe d'équiv.", "groupes d'équiv."))
        if d.cross_courantes:
            parts.append(f"équiv. croisée : {', '.join(d.cross_courantes)}")
        if n_obs:
            parts.append(pluralize(n_obs, 'obsolète'))
        if self.groups_zone and ungrouped:
            parts.append(f"{ungrouped} non groupée(s)")
        if d.phantoms:
            parts.append(f"{pluralize(len(d.phantoms), 'fantôme')} : {', '.join(sorted(d.phantoms))}")
        self.recap.setText(" · ".join(parts))
