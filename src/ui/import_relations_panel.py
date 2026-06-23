"""Panneau de déclaration des relations entre références importées (Lot 2).

Carte UNIFIÉE par référence (mono = lot à une carte) : on déclare des liens
(« Suit dans ce lot », « Équivalence », « Obsolète », liens vers la base), et le
panneau DÉRIVE et affiche les états (têtes/courantes multiples, couleur de chaîne,
fil d'Ariane, pastille de groupe) via `recompute_relations`.

Widget autonome, testable en offscreen, sans dépendance au dialogue d'import.
"""

from PyQt5.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QCheckBox, QPushButton, QScrollArea, QCompleter,
)
import qtawesome as qta

from ..services.import_relations import RefRelation, recompute_relations
from ..core.config import pluralize

# Palettes : chaînes en teintes FROIDES, équivalences en teintes CHAUDES
# (deux dimensions distinctes → ne pas confondre).
_CHAIN_COLORS = ["#1565C0", "#00838F", "#2E7D32", "#4527A0", "#00695C", "#283593"]
_EQUIV_COLORS = ["#EF6C00", "#AD1457", "#F9A825", "#5D4037", "#D84315"]

# Sentinelles pour le combo d'équivalence
_EQUIV_NONE = -1
_EQUIV_NEW = -2


def _chain_color(cid):
    return _CHAIN_COLORS[cid % len(_CHAIN_COLORS)]


def _equiv_color(gid):
    return _EQUIV_COLORS[(gid - 1) % len(_EQUIV_COLORS)]


def _group_label(gid):
    # 1 → « A », 2 → « B », … puis « G27 » au-delà de Z
    return chr(64 + gid) if 1 <= gid <= 26 else str(gid)


class RefCard(QFrame):
    """Carte d'une référence : contrôles de saisie des liens + affichage dérivé."""
    changed = pyqtSignal()

    def __init__(self, ref, filename="", is_solo=False, ref_model=None, parent=None):
        super().__init__(parent)
        self.ref = ref
        self.filename = filename
        self.is_solo = is_solo
        self._ref_model = ref_model      # QStringListModel partagé (autocomplétion base)
        self._suppress = False
        self.setObjectName("refCard")
        self._build()

    def _build(self):
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        # Ligne 1 : réf + fichier (multi) + badge Courante (dérivé)
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
        lay.addLayout(row1)

        # Ligne 2 : description
        row2 = QHBoxLayout()
        d_lbl = QLabel("Libellé :")
        d_lbl.setStyleSheet("font-size: 11px; color: #495057; border: none;")
        row2.addWidget(d_lbl)
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Description (optionnel)")
        row2.addWidget(self.desc_input, 1)
        lay.addLayout(row2)

        # Ligne 3 : Suit (combo) + Équivalence (combo + pastille) + Obsolète
        row3 = QHBoxLayout()
        if not self.is_solo:
            row3.addWidget(self._mk_lbl("Suit :"))
            self.suit_combo = QComboBox()
            self.suit_combo.setMinimumWidth(110)
            self.suit_combo.currentIndexChanged.connect(self._emit)
            row3.addWidget(self.suit_combo)
            row3.addWidget(self._mk_lbl("Éq. :"))
            self.equiv_combo = QComboBox()
            self.equiv_combo.setMinimumWidth(120)
            self.equiv_combo.currentIndexChanged.connect(self._on_equiv_changed)
            row3.addWidget(self.equiv_combo)
            self.equiv_pastille = QLabel("")
            self.equiv_pastille.setFixedWidth(14)
            self.equiv_pastille.setStyleSheet("border: none;")
            row3.addWidget(self.equiv_pastille)
        else:
            self.suit_combo = None
            self.equiv_combo = None
            self.equiv_pastille = None
        row3.addStretch(1)
        self.obsolete_check = QCheckBox("Obsolète")
        self.obsolete_check.setStyleSheet("font-size: 11px; color: #c0392b; border: none;")
        self.obsolete_check.stateChanged.connect(self._emit)
        row3.addWidget(self.obsolete_check)
        lay.addLayout(row3)

        # Ligne 4 : zone repliable « Lien avec la base »
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
        r_a = QHBoxLayout()
        r_a.addWidget(self._mk_lbl("Cette réf remplace :", 180))
        self.replaces_input = QLineEdit()
        self.replaces_input.setPlaceholderText("Ancienne réf en base")
        self.replaces_input.textChanged.connect(self._emit)
        r_a.addWidget(self.replaces_input, 1)
        bz.addLayout(r_a)
        r_b = QHBoxLayout()
        r_b.addWidget(self._mk_lbl("Est remplacée par :", 180))
        self.replaced_by_input = QLineEdit()
        self.replaced_by_input.setPlaceholderText("Réf en base qui la remplace")
        self.replaced_by_input.textChanged.connect(self._emit)
        r_b.addWidget(self.replaced_by_input, 1)
        bz.addLayout(r_b)
        self.phantom_warn = QLabel("")
        self.phantom_warn.setStyleSheet("color: #b06a00; font-size: 10px; border: none;")
        self.phantom_warn.setVisible(False)
        bz.addWidget(self.phantom_warn)
        self.base_zone.setVisible(False)
        lay.addWidget(self.base_zone)

        if self._ref_model is not None:
            for fld in (self.replaces_input, self.replaced_by_input):
                comp = QCompleter(self._ref_model, fld)
                comp.setCaseSensitivity(Qt.CaseInsensitive)
                comp.setFilterMode(Qt.MatchContains)
                fld.setCompleter(comp)

        # Ligne 5 : fil d'Ariane de chaîne (dérivé)
        self.breadcrumb = QLabel("")
        self.breadcrumb.setStyleSheet("color: #555; font-size: 10px; border: none;")
        self.breadcrumb.setVisible(False)
        lay.addWidget(self.breadcrumb)

    def _mk_lbl(self, text, width=None):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 11px; color: #495057; border: none;")
        if width:
            lbl.setFixedWidth(width)
        return lbl

    def _toggle_base(self):
        vis = not self.base_zone.isVisible()
        self.base_zone.setVisible(vis)
        arrow = "▾" if vis else "▸"
        self.base_toggle.setText(f"{arrow} Lien avec la base existante")

    def _emit(self, *args):
        if not self._suppress:
            self.changed.emit()

    def _on_equiv_changed(self, *args):
        if self._suppress:
            return
        # « + Nouveau groupe » : laisser le panneau allouer l'id puis recomposer
        self.changed.emit()

    # ── Saisie → relation ────────────────────────────────────────────────────
    def get_relation(self):
        suit = None
        if self.suit_combo is not None:
            data = self.suit_combo.currentData()
            suit = data if data else None
        equiv = None
        if self.equiv_combo is not None:
            gid = self.equiv_combo.currentData()
            if isinstance(gid, int) and gid > 0:
                equiv = gid
        return RefRelation(
            ref=self.ref,
            suit_ref=suit,
            equiv_group=equiv,
            is_obsolete=self.obsolete_check.isChecked(),
            base_replaces=(self.replaces_input.text().strip() or None),
            base_replaced_by=(self.replaced_by_input.text().strip() or None),
        )

    def equiv_choice(self):
        """Renvoie le choix d'équivalence courant : id (>0), _EQUIV_NEW ou _EQUIV_NONE."""
        if self.equiv_combo is None:
            return _EQUIV_NONE
        return self.equiv_combo.currentData()

    # ── États dérivés → affichage ────────────────────────────────────────────
    def set_suit_options(self, options, current):
        """options : liste de réfs éligibles comme prédécesseur. current : réf ou None."""
        if self.suit_combo is None:
            return
        self._suppress = True
        self.suit_combo.clear()
        self.suit_combo.addItem("—", None)
        for ref in options:
            self.suit_combo.addItem(ref, ref)
        idx = self.suit_combo.findData(current) if current else 0
        self.suit_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._suppress = False

    def set_equiv_options(self, group_ids, current):
        if self.equiv_combo is None:
            return
        self._suppress = True
        self.equiv_combo.clear()
        self.equiv_combo.addItem("—", _EQUIV_NONE)
        for gid in group_ids:
            self.equiv_combo.addItem(f"Groupe {_group_label(gid)}", gid)
        self.equiv_combo.addItem("+ Nouveau groupe", _EQUIV_NEW)
        idx = self.equiv_combo.findData(current) if (isinstance(current, int) and current > 0) else 0
        self.equiv_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._suppress = False

    def apply_derived(self, is_head, chain_id, breadcrumb, equiv_gid):
        # Liseré de chaîne + badge courante
        if chain_id is not None:
            color = _chain_color(chain_id)
            self.setStyleSheet(
                "#refCard { background: white; border: 1px solid #e9ecef;"
                f" border-left: 4px solid {color}; border-radius: 4px; }}")
        else:
            self.setStyleSheet(
                "#refCard { background: white; border: 1px solid #e9ecef; border-radius: 4px; }")
        if is_head:
            self.head_badge.setPixmap(qta.icon('fa5s.crown', color='#f39c12').pixmap(12, 12))
            self.head_badge.setToolTip("Courante (référence la plus récente de sa chaîne)")
        else:
            self.head_badge.clear()
            self.head_badge.setToolTip("")
        if breadcrumb:
            self.breadcrumb.setText("Chaîne : " + " → ".join(breadcrumb))
            self.breadcrumb.setVisible(True)
        else:
            self.breadcrumb.setVisible(False)
        # Pastille d'équivalence
        if self.equiv_pastille is not None:
            if equiv_gid:
                c = _equiv_color(equiv_gid)
                self.equiv_pastille.setText("●")
                self.equiv_pastille.setStyleSheet(f"color: {c}; border: none; font-size: 14px;")
            else:
                self.equiv_pastille.setText("")

    def set_phantom_warning(self, refs_missing):
        if refs_missing:
            self.phantom_warn.setText(
                "⚠ Réf absente de la base (créée en fantôme) : " + ", ".join(refs_missing))
            self.phantom_warn.setVisible(True)
            if not self.base_zone.isVisible():
                self.base_toggle.setText("▸ Lien avec la base existante  ⚠")
        else:
            self.phantom_warn.setVisible(False)


class RelationsPanel(QWidget):
    """Liste de RefCards + récap dérivé. Recalcule la dérivation à chaque édition."""

    def __init__(self, refs, is_solo=False, base_refs=None, parent=None):
        """refs : liste de (ref, filename). base_refs : réfs existantes en base."""
        super().__init__(parent)
        self._is_solo = is_solo
        self._base_set = set(base_refs or [])
        self._ref_model = QStringListModel(sorted(self._base_set), self)
        self._next_group = 1
        self._suppress = False
        self.cards = []
        self._build(refs)
        self.recompute()

    def _build(self, refs):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
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
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        self.recap = QLabel("")
        self.recap.setWordWrap(True)
        self.recap.setStyleSheet(
            "background: #f1f3f5; border: 1px solid #dee2e6; border-radius: 4px;"
            " padding: 6px; font-size: 11px; color: #333;")
        lay.addWidget(self.recap)

    def get_relations(self):
        return [c.get_relation() for c in self.cards]

    def recompute(self):
        if self._suppress:
            return
        self._suppress = True
        try:
            # Allouer un id pour les cartes ayant choisi « + Nouveau groupe »
            for card in self.cards:
                if card.equiv_choice() == _EQUIV_NEW:
                    card._pending_new_group = self._next_group
                    self._next_group += 1

            relations = []
            for card in self.cards:
                rel = card.get_relation()
                if getattr(card, '_pending_new_group', None) is not None:
                    rel.equiv_group = card._pending_new_group
                relations.append(rel)

            derived = recompute_relations(relations)
            rel_by_ref = {r.ref: r for r in relations}
            all_refs = [c.ref for c in self.cards]

            # Successeurs déjà attribués (un prédécesseur ne sert qu'une fois)
            used_pred = {r.suit_ref for r in relations if r.suit_ref}
            # Map ref → fil d'Ariane (chaîne ordonnée à laquelle elle appartient)
            crumb_by_ref = {}
            for chain in derived.chains:
                for ref in chain:
                    crumb_by_ref[ref] = chain if len(chain) > 1 else None

            existing_groups = sorted({r.equiv_group for r in relations if r.equiv_group})

            for card in self.cards:
                rel = rel_by_ref[card.ref]
                # Options « Suit » : exclure soi, ses descendants (anti-cycle),
                # et les prédécesseurs déjà pris par une autre carte.
                descendants = self._descendants(card.ref, relations)
                eligible = [r for r in all_refs
                            if r != card.ref and r not in descendants
                            and (r not in used_pred or r == rel.suit_ref)]
                card.set_suit_options(eligible, rel.suit_ref)
                card.set_equiv_options(existing_groups, rel.equiv_group)
                card.apply_derived(
                    is_head=(card.ref in derived.heads),
                    chain_id=derived.chain_id_by_ref.get(card.ref),
                    breadcrumb=crumb_by_ref.get(card.ref),
                    equiv_gid=rel.equiv_group,
                )
                # Avertissement fantôme sur les liens base
                missing = [v for v in (rel.base_replaces, rel.base_replaced_by)
                           if v and v not in self._base_set]
                card.set_phantom_warning(missing)
                card._pending_new_group = None
        finally:
            self._suppress = False

        self._update_recap(relations, derived)

    def _descendants(self, ref, relations):
        """Réfs atteignables en suivant les successeurs depuis `ref` (pour anti-cycle)."""
        succ = {}
        for r in relations:
            if r.suit_ref:
                succ[r.suit_ref] = r.ref
        out = set()
        cur = succ.get(ref)
        guard = 0
        while cur and cur not in out and guard <= len(relations):
            out.add(cur)
            cur = succ.get(cur)
            guard += 1
        return out

    def _update_recap(self, relations, derived):
        n = len(relations)
        n_chains = len(derived.chains)
        heads = sorted(derived.heads)
        groups = derived.equiv_groups
        n_base = sum(1 for r in relations if r.base_replaces or r.base_replaced_by)
        n_obs = sum(1 for r in relations if r.is_obsolete)
        phantoms = sorted({v for r in relations for v in (r.base_replaces, r.base_replaced_by)
                           if v and v not in self._base_set})
        parts = [pluralize(n, 'réf')]
        if n_chains:
            parts.append(pluralize(n_chains, 'chaîne'))
        if heads:
            parts.append(f"{pluralize(len(heads), 'courante')} ({', '.join(heads)})")
        for gid in sorted(groups):
            parts.append(f"Éq. {_group_label(gid)} : {', '.join(sorted(groups[gid]))}")
        if n_base:
            parts.append(pluralize(n_base, 'lien base', 'liens base'))
        if n_obs:
            parts.append(pluralize(n_obs, 'obsolète'))
        if phantoms:
            parts.append(f"{pluralize(len(phantoms), 'fantôme')} : {', '.join(phantoms)}")
        self.recap.setText(" · ".join(parts))
