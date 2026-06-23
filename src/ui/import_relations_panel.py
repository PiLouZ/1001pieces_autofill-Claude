"""Panneau de déclaration des relations entre références importées (Lot 2).

Agencement : QSplitter horizontal — cartes à gauche (succession + obsolète + liens
base), zone « Groupes d'équivalence » en drag-drop à droite, récap sticky en bas.

Succession SIMPLIFIÉE (l'utilisateur ne connaît pas l'ordre) : par réf, statut
« Courante » (plusieurs possibles) OU « Ancienne version de [réf récente] » (combo
ÉDITABLE : courantes du lot, réfs en base, ou saisie libre → fantôme). Chaque
ancienne pointe directement vers sa courante (étoile).

Équivalence : zone dédiée, on crée N groupes et on y glisse les pastilles de réf
(une réf ∈ au plus un groupe). Source unique de vérité : l'état des QListWidget.

Tout est dérivé via `recompute_relations`. Widget autonome (testable offscreen).
"""

from PyQt5.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QCheckBox, QPushButton, QScrollArea, QCompleter, QRadioButton, QSplitter,
    QListWidget, QListWidgetItem, QMenu, QAbstractItemView,
)
import qtawesome as qta

from ..services.import_relations import RefRelation, recompute_relations
from ..core.config import pluralize

_CHAIN_COLORS = ["#1565C0", "#00838F", "#2E7D32", "#4527A0", "#00695C", "#283593"]
_EQUIV_COLORS = ["#F9A825", "#EF6C00", "#C75B39", "#AD1457", "#D84315"]


def _chain_color(cid):
    return _CHAIN_COLORS[cid % len(_CHAIN_COLORS)]


def _equiv_color(gid):
    return _EQUIV_COLORS[(gid - 1) % len(_EQUIV_COLORS)]


def _group_label(gid):
    return chr(64 + gid) if 1 <= gid <= 26 else str(gid)


# ── Carte d'une référence ─────────────────────────────────────────────────────

class RefCard(QFrame):
    changed = pyqtSignal()

    def __init__(self, ref, filename="", is_solo=False, ref_model=None, parent=None):
        super().__init__(parent)
        self.ref = ref
        self.filename = filename
        self.is_solo = is_solo
        self._ref_model = ref_model
        self._suppress = False
        self.setObjectName("refCard")
        self._build()

    def _build(self):
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        row1 = QHBoxLayout()
        ref_lbl = QLabel(self.ref)
        ref_lbl.setStyleSheet("font-weight: bold; font-size: 12px; border: none;")
        row1.addWidget(ref_lbl)
        if not self.is_solo and self.filename:
            f_lbl = QLabel(self.filename)
            f_lbl.setStyleSheet("color: #666; font-size: 11px; border: none;")
            f_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row1.addWidget(f_lbl, 1)
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
        row2.addWidget(self._lbl("Libellé :"))
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Description (optionnel)")
        row2.addWidget(self.desc_input, 1)
        self.obsolete_check = QCheckBox("Obsolète")
        self.obsolete_check.setStyleSheet("font-size: 11px; color: #c0392b; border: none;")
        self.obsolete_check.stateChanged.connect(self._emit)
        row2.addWidget(self.obsolete_check)
        lay.addLayout(row2)

        # Statut succession (sauf solo : une seule réf, pas de lignée intra-lot)
        if not self.is_solo:
            row3 = QHBoxLayout()
            row3.addWidget(self._lbl("Statut :"))
            self.radio_current = QRadioButton("Courante")
            self.radio_current.setAutoExclusive(False)
            self.radio_current.toggled.connect(self._on_current_toggled)
            row3.addWidget(self.radio_current)
            self.radio_old = QRadioButton("Ancienne version de")
            self.radio_old.setAutoExclusive(False)
            self.radio_old.toggled.connect(self._on_old_toggled)
            row3.addWidget(self.radio_old)
            self.newer_combo = QComboBox()
            self.newer_combo.setEditable(True)        # choisir OU saisir une réf libre
            self.newer_combo.setInsertPolicy(QComboBox.NoInsert)
            self.newer_combo.setMinimumWidth(150)
            self.newer_combo.setEnabled(False)
            self.newer_combo.lineEdit().setPlaceholderText("réf récente (lot, base ou libre)")
            self.newer_combo.editTextChanged.connect(self._emit)
            row3.addWidget(self.newer_combo, 1)
            lay.addLayout(row3)
        else:
            self.radio_current = self.radio_old = self.newer_combo = None

        # Zone repliable « Lien avec la base »
        self.base_toggle = QPushButton("▸ Lien avec la base existante")
        self.base_toggle.setFlat(True)
        self.base_toggle.setCursor(Qt.PointingHandCursor)
        self.base_toggle.setStyleSheet(
            "QPushButton { color: #0066cc; font-size: 11px; text-align: left;"
            " border: none; background: transparent; padding: 2px; }"
            "QPushButton:hover { text-decoration: underline; }")
        self.base_toggle.clicked.connect(self._toggle_base)
        lay.addWidget(self.base_toggle)

        self.base_zone = QWidget()
        bz = QVBoxLayout(self.base_zone)
        bz.setContentsMargins(12, 2, 4, 4)
        bz.setSpacing(3)
        ra = QHBoxLayout()
        ra.addWidget(self._lbl("Cette réf remplace :", 170))
        self.replaces_input = QLineEdit()
        self.replaces_input.setPlaceholderText("Ancienne réf en base")
        self.replaces_input.textChanged.connect(self._emit)
        ra.addWidget(self.replaces_input, 1)
        bz.addLayout(ra)
        self.phantom_warn = QLabel("")
        self.phantom_warn.setStyleSheet("color: #b06a00; font-size: 10px; border: none;")
        self.phantom_warn.setVisible(False)
        bz.addWidget(self.phantom_warn)
        self.base_zone.setVisible(False)
        lay.addWidget(self.base_zone)

        if self._ref_model is not None:
            for fld in [self.replaces_input] + ([self.newer_combo.lineEdit()] if self.newer_combo else []):
                comp = QCompleter(self._ref_model, fld)
                comp.setCaseSensitivity(Qt.CaseInsensitive)
                comp.setFilterMode(Qt.MatchContains)
                fld.setCompleter(comp)

        self.breadcrumb = QLabel("")
        self.breadcrumb.setStyleSheet("color: #555; font-size: 10px; border: none;")
        self.breadcrumb.setVisible(False)
        lay.addWidget(self.breadcrumb)

    def _lbl(self, text, width=None):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 11px; color: #495057; border: none;")
        if width:
            lbl.setFixedWidth(width)
        return lbl

    def _on_current_toggled(self, checked):
        if self._suppress:
            return
        if checked and self.radio_old and self.radio_old.isChecked():
            self._suppress = True
            self.radio_old.setChecked(False)
            self._suppress = False
        self.newer_combo.setEnabled(self.radio_old.isChecked())
        self.changed.emit()

    def _on_old_toggled(self, checked):
        if self._suppress:
            return
        if checked and self.radio_current and self.radio_current.isChecked():
            self._suppress = True
            self.radio_current.setChecked(False)
            self._suppress = False
        self.newer_combo.setEnabled(self.radio_old.isChecked())
        self.changed.emit()

    def _toggle_base(self):
        vis = not self.base_zone.isVisible()
        self.base_zone.setVisible(vis)
        self.base_toggle.setText(("▾" if vis else "▸") + " Lien avec la base existante")

    def _emit(self, *a):
        if not self._suppress:
            self.changed.emit()

    def get_relation(self, equiv_group=None):
        is_current = bool(self.radio_current and self.radio_current.isChecked())
        newer = None
        if self.radio_old and self.radio_old.isChecked():
            newer = (self.newer_combo.currentText().strip() or None)
        return RefRelation(
            ref=self.ref, is_current=is_current, newer_ref=newer,
            equiv_group=equiv_group,
            is_obsolete=self.obsolete_check.isChecked(),
            base_replaces=(self.replaces_input.text().strip() or None),
        )

    def set_newer_options(self, courantes):
        """Repeuple la liste des courantes proposées (l'édition libre reste possible)."""
        if self.newer_combo is None:
            return
        self._suppress = True
        txt = self.newer_combo.currentText()
        self.newer_combo.clear()
        self.newer_combo.addItems([c for c in courantes if c != self.ref])
        self.newer_combo.setCurrentText(txt)
        self._suppress = False

    def apply_derived(self, is_head, chain_id, breadcrumb, equiv_gid, base_set, lot_refs):
        color = _chain_color(chain_id) if chain_id is not None else None
        border = f"border-left: 4px solid {color};" if color else ""
        self.setStyleSheet(
            f"#refCard {{ background: white; border: 1px solid #e9ecef; {border} border-radius: 4px; }}")
        if is_head:
            self.head_badge.setPixmap(qta.icon('fa5s.crown', color='#1565C0').pixmap(12, 12))
            self.head_badge.setToolTip("Courante")
        else:
            self.head_badge.clear()
        if equiv_gid:
            self.equiv_badge.setText(f"● Éq. {_group_label(equiv_gid)}")
            self.equiv_badge.setStyleSheet(f"color: {_equiv_color(equiv_gid)}; border: none; font-size: 11px;")
        else:
            self.equiv_badge.setText("")
        if breadcrumb:
            self.breadcrumb.setText("Chaîne : " + " → ".join(breadcrumb))
            self.breadcrumb.setVisible(True)
        else:
            self.breadcrumb.setVisible(False)
        # Avertissement fantôme : réf citée (remplace / ancienne version de) absente
        # de la base ET hors du lot (une réf du lot est valide, pas un fantôme).
        missing = []
        rel = self.get_relation()
        for v in (rel.base_replaces, rel.newer_ref):
            if v and v not in base_set and v not in lot_refs:
                missing.append(v)
        if missing:
            self.phantom_warn.setText("⚠ Réf absente de la base (fantôme) : " + ", ".join(missing))
            self.phantom_warn.setVisible(True)
        else:
            self.phantom_warn.setVisible(False)


# ── Zone des groupes d'équivalence (drag-drop) ───────────────────────────────

class _RefList(QListWidget):
    """Liste de pastilles de réf acceptant le drag-drop entre conteneurs."""
    dropped = pyqtSignal()

    def __init__(self, group_id=None, parent=None):
        super().__init__(parent)
        self.group_id = group_id      # None = réservoir « Non groupées »
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.Adjust)
        self.setMaximumHeight(72)
        self.setStyleSheet("QListWidget { border: 1px dashed #ccc; border-radius: 4px; }")

    def dropEvent(self, event):
        super().dropEvent(event)
        self.dropped.emit()

    def refs(self):
        return [self.item(i).text() for i in range(self.count())]


class EquivGroupsZone(QWidget):
    changed = pyqtSignal()

    def __init__(self, refs, parent=None):
        super().__init__(parent)
        self._all_refs = list(refs)
        self._next_gid = 1
        self._group_lists = {}     # gid → _RefList
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        title = QLabel("Groupes d'équivalence")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        lay.addWidget(title)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrer une réf…")
        self._filter.addAction(qta.icon('fa5s.search', color='#888'), QLineEdit.LeadingPosition)
        self._filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self._filter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_lay = QVBoxLayout(content)
        self._content_lay.setContentsMargins(2, 2, 2, 2)
        self._content_lay.setSpacing(6)
        self._content_lay.setAlignment(Qt.AlignTop)

        # Réservoir « Non groupées »
        self._content_lay.addWidget(self._mk_header("Non groupées", None))
        self.reservoir = _RefList(group_id=None)
        for r in self._all_refs:
            self.reservoir.addItem(QListWidgetItem(r))
        self.reservoir.dropped.connect(self._on_change)
        self._content_lay.addWidget(self.reservoir)

        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        add_btn = QPushButton("+ Nouveau groupe")
        add_btn.clicked.connect(self.add_group)
        lay.addWidget(add_btn)

    def _mk_header(self, text, gid):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 2, 0, 0)
        lbl = QLabel(text)
        col = "#495057" if gid is None else _equiv_color(gid)
        lbl.setStyleSheet(f"font-weight: bold; font-size: 11px; color: {col};")
        h.addWidget(lbl)
        h.addStretch(1)
        if gid is not None:
            empty = QPushButton("vider")
            empty.setFlat(True)
            empty.setStyleSheet("color: #0066cc; font-size: 10px; border: none;")
            empty.clicked.connect(lambda: self._empty_group(gid))
            h.addWidget(empty)
            rem = QPushButton("supprimer")
            rem.setFlat(True)
            rem.setStyleSheet("color: #c0392b; font-size: 10px; border: none;")
            rem.clicked.connect(lambda: self.remove_group(gid))
            h.addWidget(rem)
        return w

    def add_group(self):
        gid = self._next_gid
        self._next_gid += 1
        self._content_lay.addWidget(self._mk_header(f"Groupe {_group_label(gid)}", gid))
        lst = _RefList(group_id=gid)
        lst.dropped.connect(self._on_change)
        self._group_lists[gid] = lst
        self._content_lay.addWidget(lst)
        self._on_change()
        return gid

    def _empty_group(self, gid):
        lst = self._group_lists.get(gid)
        if lst:
            for r in lst.refs():
                self.reservoir.addItem(QListWidgetItem(r))
            lst.clear()
            self._on_change()

    def remove_group(self, gid):
        self._empty_group(gid)
        lst = self._group_lists.pop(gid, None)
        if lst:
            # retirer le header (widget juste avant la liste) + la liste
            idx = self._content_lay.indexOf(lst)
            lst.setParent(None)
            if idx >= 1:
                hdr = self._content_lay.itemAt(idx - 1).widget()
                if hdr:
                    hdr.setParent(None)
        self._on_change()

    def _apply_filter(self, text):
        text = (text or "").strip().lower()
        for lst in [self.reservoir] + list(self._group_lists.values()):
            for i in range(lst.count()):
                it = lst.item(i)
                it.setHidden(bool(text) and text not in it.text().lower())

    def _on_change(self, *a):
        self.changed.emit()

    def assignments(self):
        """{ref → group_id} (source de vérité = état des listes)."""
        out = {}
        for gid, lst in self._group_lists.items():
            for r in lst.refs():
                out[r] = gid
        return out


# ── Panneau global ───────────────────────────────────────────────────────────

class RelationsPanel(QWidget):
    def __init__(self, refs, is_solo=False, base_refs=None, parent=None):
        super().__init__(parent)
        self._is_solo = is_solo
        self._base_set = set(base_refs or [])
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

        # Gauche : cartes
        left = QScrollArea()
        left.setWidgetResizable(True)
        content = QWidget()
        self._cards_layout = QVBoxLayout(content)
        self._cards_layout.setContentsMargins(6, 6, 6, 6)
        self._cards_layout.setSpacing(6)
        self._cards_layout.setAlignment(Qt.AlignTop)
        for ref, filename in refs:
            card = RefCard(ref, filename, is_solo=self._is_solo, ref_model=self._ref_model)
            card.changed.connect(self.recompute)
            self.cards.append(card)
            self._cards_layout.addWidget(card)
        left.setWidget(content)
        splitter.addWidget(left)

        # Droite : groupes d'équivalence (sauf solo)
        if not self._is_solo:
            self.groups_zone = EquivGroupsZone([r for r, _ in refs])
            self.groups_zone.changed.connect(self.recompute)
            splitter.addWidget(self.groups_zone)
            splitter.setSizes([620, 380])
        else:
            self.groups_zone = None
        lay.addWidget(splitter, 1)

        self.recap = QLabel("")
        self.recap.setWordWrap(True)
        self.recap.setStyleSheet(
            "background: #f1f3f5; border: 1px solid #dee2e6; border-radius: 4px;"
            " padding: 6px; font-size: 11px; color: #333;")
        lay.addWidget(self.recap)

    def get_relations(self):
        assign = self.groups_zone.assignments() if self.groups_zone else {}
        return [c.get_relation(equiv_group=assign.get(c.ref)) for c in self.cards]

    def recompute(self):
        if self._suppress:
            return
        self._suppress = True
        try:
            relations = self.get_relations()
            derived = recompute_relations(relations)
            rel_by_ref = {r.ref: r for r in relations}
            courantes = sorted(derived.heads)
            crumb = {}
            for chain in derived.chains:
                for ref in chain:
                    crumb[ref] = chain if len(chain) > 1 else None
            lot_refs = {c.ref for c in self.cards}
            for card in self.cards:
                rel = rel_by_ref[card.ref]
                card.set_newer_options(courantes)
                card.apply_derived(
                        is_head=(card.ref in derived.heads),
                        chain_id=derived.chain_id_by_ref.get(card.ref),
                        breadcrumb=crumb.get(card.ref),
                        equiv_gid=rel.equiv_group,
                        base_set=self._base_set,
                        lot_refs=lot_refs,
                    )
        finally:
            self._suppress = False
        self._update_recap(relations, derived)

    def _update_recap(self, relations, derived):
        heads = sorted(derived.heads)
        groups = derived.equiv_groups
        n_base = sum(1 for r in relations if r.base_replaces or r.base_replaced_by)
        n_obs = sum(1 for r in relations if r.is_obsolete)
        ungrouped = sum(1 for r in relations if r.equiv_group is None)
        phantoms = sorted({v for r in relations for v in (r.base_replaces, r.newer_ref)
                           if v and v not in self._base_set
                           and v not in {c.ref for c in self.cards}})
        parts = [pluralize(len(relations), 'réf')]
        if heads:
            parts.append(f"{pluralize(len(heads), 'courante')} ({', '.join(heads)})")
        for gid in sorted(groups):
            parts.append(f"Éq. {_group_label(gid)} : {', '.join(sorted(groups[gid]))}")
        if n_base:
            parts.append(pluralize(n_base, 'lien base', 'liens base'))
        if n_obs:
            parts.append(pluralize(n_obs, 'obsolète'))
        if self.groups_zone and ungrouped:
            parts.append(f"{ungrouped} non groupée(s)")
        if phantoms:
            parts.append(f"{pluralize(len(phantoms), 'fantôme')} : {', '.join(phantoms)}")
        self.recap.setText(" · ".join(parts))
