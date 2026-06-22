"""Fenêtre de validation polyvalente des suggestions Type/Marque par similarité.

Synthétise TOUTES les suggestions en attente (y compris celles à plusieurs candidats
concurrents) dans un arbre regroupable : une case à cocher par appareil, valeurs Type/
Marque éditables via la MÊME fenêtre que Cmd+D du tableau principal (valeurs existantes
+ suggestions), score de ressemblance et niveau de fiabilité lisible. La validation
applique les seules lignes cochées via le callback `on_validate` fourni par la fenêtre
principale (chemin batché + historisé existant).

Non bloquant : ouvert via show() + callback (jamais exec_(), cf. conventions projet).
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFrame, QHeaderView,
)
import qtawesome as qta

from src.core.config import pluralize

# ── Colonnes ────────────────────────────────────────────────────────────────
COL_CHECK = 0      # case à cocher (étroite ; le libellé de groupe va sur COL_REF)
COL_REF = 1        # référence de l'appareil (+ libellé de groupe sur les parents)
COL_NEW_TYPE = 2   # Type retenu (double-clic → fenêtre Cmd+D)
COL_NEW_MFR = 3    # Marque retenue (double-clic → fenêtre Cmd+D)
COL_SCORE = 4      # ressemblance (%)
COL_TIER = 5       # fiabilité (badge lisible)

_HEADERS = ["", "Référence", "Type", "Marque", "Score", "Fiabilité"]

# Rôles personnalisés stockés sur la colonne 0 des feuilles
_ROLE_DBID = Qt.UserRole
_ROLE_CANDS = Qt.UserRole + 1
_ROLE_EDITED = Qt.UserRole + 2
_ROLE_IS_LEAF = Qt.UserRole + 3

# Palier technique → libellé humain + ordre de tri + couleur de badge
_TIER_LABEL = {
    'A_suffix_variant': "Quasi-certain",
    'B_fuzzy_alpha': "Probable",
    'B_fuzzy_numeric': "Probable",
    'C_prefix_consensus': "À vérifier",
}
_TIER_ORDER = {'A_suffix_variant': 0, 'B_fuzzy_alpha': 1, 'B_fuzzy_numeric': 1,
               'C_prefix_consensus': 2}
_TIER_BADGE = {
    "Quasi-certain": ("#E8F5E9", "#2e7d32"),
    "Probable": ("#FFF8E1", "#b06a00"),
    "À vérifier": ("#ECEFF1", "#546E7A"),
}


def tier_label(tier):
    return _TIER_LABEL.get(tier, "Probable")


def score_color(score):
    if score >= 0.90:
        return QColor("#2e7d32")
    if score >= 0.75:
        return QColor("#f39c12")
    return QColor("#b06a00")


def is_safe_default(entry):
    """Pré-cochage : candidat unique ET (palier A OU score ≥ 0,90). Reproduit
    fonctionnellement l'ancien « sans concurrence »."""
    cands = entry.get('candidates') or []
    if len(cands) != 1:
        return False
    c = cands[0]
    return c.get('confidence_tier') == 'A_suffix_variant' or float(c.get('score', 0)) >= 0.90


class SuggestionValidationDialog(QDialog):
    def __init__(self, parent, snapshot, on_validate, value_picker=None):
        """value_picker(db_field, current_value, candidates) -> str|dict|None :
        ouvre la fenêtre Cmd+D pour éditer une valeur. Optionnel (édition désactivée
        si absent — utile pour les tests sans service)."""
        super().__init__(parent)
        self._snapshot = snapshot or []
        self._on_validate = on_validate
        self._value_picker = value_picker
        self._suppress = False     # garde anti-récursion sur itemChanged
        self._leaves = []          # toutes les feuilles (appareils)

        self.setWindowTitle("Valider les suggestions Type / Marque")
        self.resize(820, 600)
        self.setMinimumSize(680, 400)

        self._build_ui()
        self._populate('none')
        self._update_count()

    # ── Construction UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)

        # Zone A — bannière ambre
        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background: #FFF8E1; border: 1px solid #f39c12; border-radius: 3px; }"
        )
        b_lay = QVBoxLayout(banner)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.lightbulb', color='#f39c12').pixmap(18, 18))
        title_row.addWidget(icon)
        self._title_label = QLabel()
        self._title_label.setStyleSheet("border: none; font-weight: bold;")
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        b_lay.addLayout(title_row)
        help_label = QLabel(
            "Cochez les suggestions à appliquer. Double-cliquez une valeur Type ou Marque "
            "pour la choisir parmi les suggestions et les valeurs existantes."
        )
        help_label.setStyleSheet("border: none; color: #666; font-size: 11px;")
        help_label.setWordWrap(True)
        b_lay.addWidget(help_label)
        root.addWidget(banner)

        # Zone B — barre d'outils
        tools = QHBoxLayout()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrer par référence, type ou marque…")
        self._filter.addAction(qta.icon('fa5s.search', color='#888'), QLineEdit.LeadingPosition)
        self._filter.textChanged.connect(self._on_filter)
        tools.addWidget(self._filter, 1)
        tools.addWidget(QLabel("Regrouper par"))
        self._group_combo = QComboBox()
        self._group_combo.addItem("Aucun", 'none')
        self._group_combo.addItem("Fiabilité", 'tier')
        self._group_combo.addItem("Marque", 'manufacturer')
        self._group_combo.currentIndexChanged.connect(self._on_group_changed)
        tools.addWidget(self._group_combo)
        self._count_label = QLabel()
        self._count_label.setStyleSheet("color: #444;")
        tools.addWidget(self._count_label)
        root.addLayout(tools)

        # Zone C — arbre
        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_HEADERS))
        self._tree.setHeaderLabels(_HEADERS)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setIndentation(14)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        header = self._tree.header()
        header.setStretchLastSection(False)
        # Référence (colonne la plus importante, longueur variable) absorbe l'espace ;
        # Score et Fiabilité au plus juste pour leur contenu.
        header.setSectionResizeMode(COL_REF, QHeaderView.Stretch)
        # Case à peine plus large que la coche elle-même
        self._tree.setColumnWidth(COL_CHECK, 34)
        self._tree.setColumnWidth(COL_NEW_TYPE, 160)
        self._tree.setColumnWidth(COL_NEW_MFR, 160)
        self._tree.setColumnWidth(COL_SCORE, 78)
        self._tree.setColumnWidth(COL_TIER, 104)
        root.addWidget(self._tree, 1)

        # Zone D — barre d'actions bas (couleurs : vert valider, rouge annuler)
        actions = QHBoxLayout()
        uncheck_btn = QPushButton("Tout décocher")
        uncheck_btn.clicked.connect(lambda: self._set_all_checked(False))
        actions.addWidget(uncheck_btn)
        check_btn = QPushButton("Tout cocher")
        check_btn.clicked.connect(lambda: self._set_all_checked(True))
        actions.addWidget(check_btn)
        actions.addStretch()
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setProperty("class", "danger")   # rouge — ligne directrice projet
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(cancel_btn)
        self._validate_btn = QPushButton()
        self._validate_btn.setProperty("class", "success")  # vert
        self._validate_btn.setDefault(True)
        self._validate_btn.clicked.connect(self._on_validate_clicked)
        actions.addWidget(self._validate_btn)
        root.addLayout(actions)

    # ── Remplissage ──────────────────────────────────────────────────────────
    def _populate(self, group_by):
        self._suppress = True
        self._tree.clear()
        self._leaves = []

        if group_by == 'none':
            for entry in self._sorted_entries(self._snapshot):
                self._add_leaf(self._tree.invisibleRootItem(), entry)
        else:
            groups = {}
            for entry in self._snapshot:
                key = self._group_key(entry, group_by)
                groups.setdefault(key, []).append(entry)
            for key in self._sorted_group_keys(groups.keys(), group_by):
                entries = groups[key]
                # Libellé de groupe sur COL_REF pour garder COL_CHECK étroite
                parent = QTreeWidgetItem(self._tree)
                parent.setText(COL_REF, f"{key} ({len(entries)})")
                parent.setData(COL_CHECK, _ROLE_IS_LEAF, False)
                f = parent.font(COL_REF)
                f.setBold(True)
                parent.setFont(COL_REF, f)
                parent.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsAutoTristate)
                parent.setCheckState(COL_CHECK, Qt.Unchecked)
                for entry in self._sorted_entries(entries):
                    self._add_leaf(parent, entry)
                parent.setExpanded(True)
        self._suppress = False
        self._refresh_parent_states()

    def _sorted_entries(self, entries):
        def keyf(e):
            cands = e.get('candidates') or []
            best = cands[0] if cands else {}
            tier_o = _TIER_ORDER.get(best.get('confidence_tier'), 1)
            return (tier_o, -float(best.get('score', 0)))
        return sorted(entries, key=keyf)

    def _group_key(self, entry, group_by):
        cands = entry.get('candidates') or []
        best = cands[0] if cands else {}
        if group_by == 'tier':
            return tier_label(best.get('confidence_tier'))
        return best.get('manufacturer') or "(marque inconnue)"

    def _sorted_group_keys(self, keys, group_by):
        if group_by == 'tier':
            order = {"Quasi-certain": 0, "Probable": 1, "À vérifier": 2}
            return sorted(keys, key=lambda k: order.get(k, 1))
        return sorted(keys)

    def _add_leaf(self, parent, entry):
        cands = entry.get('candidates') or []
        ref = entry.get('ref_modele') or ''
        comm = entry.get('commercial_ref') or ''
        ref_text = ref if not comm else f"{ref}  ·  {comm}"

        leaf = QTreeWidgetItem(parent)
        leaf.setData(COL_CHECK, _ROLE_IS_LEAF, True)
        leaf.setData(COL_CHECK, _ROLE_DBID, entry.get('db_id'))
        leaf.setData(COL_CHECK, _ROLE_CANDS, cands)
        leaf.setData(COL_CHECK, _ROLE_EDITED, False)
        # Pas d'édition inline : l'édition passe par la fenêtre Cmd+D (double-clic)
        leaf.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        leaf.setText(COL_REF, ref_text)
        leaf.setToolTip(COL_REF, ref_text)

        # Valeurs retenues + score/fiabilité depuis le 1er candidat
        if cands:
            self._apply_candidate_to_leaf(leaf, cands[0])

        leaf.setCheckState(COL_CHECK, Qt.Checked if is_safe_default(entry) else Qt.Unchecked)
        self._leaves.append(leaf)

    def _apply_candidate_to_leaf(self, leaf, cand):
        """Reporte un candidat dans les colonnes retenues + score + fiabilité."""
        leaf.setText(COL_NEW_TYPE, cand.get('type', '') or '')
        leaf.setText(COL_NEW_MFR, cand.get('manufacturer', '') or '')
        leaf.setData(COL_CHECK, _ROLE_EDITED, False)
        leaf.setForeground(COL_NEW_TYPE, QBrush(QColor("#212121")))
        leaf.setForeground(COL_NEW_MFR, QBrush(QColor("#212121")))
        leaf.setBackground(COL_NEW_TYPE, QBrush())
        leaf.setBackground(COL_NEW_MFR, QBrush())
        score = float(cand.get('score', 0))
        leaf.setText(COL_SCORE, f"{int(score * 100)} %")
        leaf.setForeground(COL_SCORE, QBrush(score_color(score)))
        label = tier_label(cand.get('confidence_tier'))
        leaf.setText(COL_TIER, label)
        bg, fg = _TIER_BADGE.get(label, ("#ECEFF1", "#546E7A"))
        leaf.setBackground(COL_TIER, QBrush(QColor(bg)))
        leaf.setForeground(COL_TIER, QBrush(QColor(fg)))

    # ── Événements ───────────────────────────────────────────────────────────
    def _on_group_changed(self):
        self._populate(self._group_combo.currentData())
        self._on_filter(self._filter.text())
        self._update_count()

    def _on_item_double_clicked(self, item, column):
        """Édition d'une valeur Type/Marque via la fenêtre Cmd+D (valeurs existantes
        + suggestions). Choisir un candidat (dict) remplit Type ET Marque ; saisir/
        choisir une valeur libre (str) ne touche que la colonne éditée."""
        if self._value_picker is None:
            return
        if not item.data(COL_CHECK, _ROLE_IS_LEAF):
            return
        if column not in (COL_NEW_TYPE, COL_NEW_MFR):
            return
        db_field = 'type' if column == COL_NEW_TYPE else 'manufacturer'
        current = item.text(column)
        cands = item.data(COL_CHECK, _ROLE_CANDS) or []
        result = self._value_picker(db_field, current, cands)
        if result is None:
            return
        self._suppress = True
        if isinstance(result, dict):
            # Candidat choisi → paire Type+Marque + score/fiabilité du candidat
            self._apply_candidate_to_leaf(item, result)
        else:
            # Valeur libre → seule la colonne éditée ; score neutralisé
            item.setText(column, result)
            self._mark_edited(item)
        item.setCheckState(COL_CHECK, Qt.Checked)
        self._suppress = False
        self._refresh_parent_states()
        self._update_count()

    def _mark_edited(self, leaf):
        leaf.setData(COL_CHECK, _ROLE_EDITED, True)
        leaf.setText(COL_SCORE, "— (modifié)")
        leaf.setForeground(COL_SCORE, QBrush(QColor("#9e9e9e")))
        leaf.setBackground(COL_NEW_TYPE, QBrush(QColor("#E3F2FD")))
        leaf.setBackground(COL_NEW_MFR, QBrush(QColor("#E3F2FD")))

    def _on_item_changed(self, item, column):
        if self._suppress:
            return
        is_leaf = bool(item.data(COL_CHECK, _ROLE_IS_LEAF))

        # Propagation case parent → enfants
        if not is_leaf and column == COL_CHECK:
            state = item.checkState(COL_CHECK)
            if state != Qt.PartiallyChecked:
                self._suppress = True
                for i in range(item.childCount()):
                    item.child(i).setCheckState(COL_CHECK, state)
                self._suppress = False
            self._update_count()
            return

        if is_leaf and column == COL_CHECK:
            self._refresh_parent_states()
            self._update_count()

    def _refresh_parent_states(self):
        """Recalcule l'état tri-state de chaque nœud-groupe d'après ses enfants."""
        self._suppress = True
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            if parent.data(COL_CHECK, _ROLE_IS_LEAF):
                continue
            n = parent.childCount()
            checked = sum(1 for j in range(n)
                          if parent.child(j).checkState(COL_CHECK) == Qt.Checked)
            if checked == 0:
                parent.setCheckState(COL_CHECK, Qt.Unchecked)
            elif checked == n:
                parent.setCheckState(COL_CHECK, Qt.Checked)
            else:
                parent.setCheckState(COL_CHECK, Qt.PartiallyChecked)
        self._suppress = False

    def _on_filter(self, text):
        text = (text or '').strip().lower()
        for leaf in self._leaves:
            hay = " ".join([
                leaf.text(COL_REF), leaf.text(COL_NEW_TYPE), leaf.text(COL_NEW_MFR),
            ]).lower()
            leaf.setHidden(bool(text) and text not in hay)
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            if parent.data(COL_CHECK, _ROLE_IS_LEAF):
                continue
            any_visible = any(not parent.child(j).isHidden()
                              for j in range(parent.childCount()))
            parent.setHidden(not any_visible)

    def _set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self._suppress = True
        for leaf in self._leaves:
            if not leaf.isHidden():
                leaf.setCheckState(COL_CHECK, state)
        self._suppress = False
        self._refresh_parent_states()
        self._update_count()

    def _checked_leaves(self):
        return [lf for lf in self._leaves if lf.checkState(COL_CHECK) == Qt.Checked]

    def _update_count(self):
        total = len(self._leaves)
        sel = len(self._checked_leaves())
        self._title_label.setText(f"{pluralize(total, 'suggestion')} à valider")
        self._count_label.setText(f"{pluralize(sel, 'sélectionnée')} sur {total}")
        self._validate_btn.setText(f"Valider la sélection ({sel})")
        self._validate_btn.setEnabled(sel > 0)

    # ── Validation ───────────────────────────────────────────────────────────
    def _collect_decisions(self):
        decisions = []
        for leaf in self._checked_leaves():
            db_id = leaf.data(COL_CHECK, _ROLE_DBID)
            if db_id is None:
                continue
            type_v = (leaf.text(COL_NEW_TYPE) or '').strip()
            mfr_v = (leaf.text(COL_NEW_MFR) or '').strip()
            if not type_v and not mfr_v:
                continue  # rien à écrire
            cands = leaf.data(COL_CHECK, _ROLE_CANDS) or []
            ref = score = None
            edited = bool(leaf.data(COL_CHECK, _ROLE_EDITED))
            for c in cands:
                if c.get('type', '') == type_v and c.get('manufacturer', '') == mfr_v:
                    ref, score = c.get('ref', ''), c.get('score', 0)
                    break
            if ref is None and cands:
                ref, score = cands[0].get('ref', ''), cands[0].get('score', 0)
            cand = {'type': type_v, 'manufacturer': mfr_v, 'ref': ref or '',
                    'score': score or 0}
            if edited:
                cand['ref'] = (cand['ref'] + " · ajusté").strip(' ·')
            decisions.append((db_id, cand))
        return decisions

    def _on_validate_clicked(self):
        decisions = self._collect_decisions()
        if not decisions:
            self.reject()
            return
        if callable(self._on_validate):
            self._on_validate(decisions)
        self.accept()
