"""Fenêtre « Auto-complétés à vérifier » (v3.89.0).

Liste les appareils dont un Type ou un Fabricant a été écrit par l'auto-complétion
d'un import, du moins sûr au plus sûr : valeur, appareil source, accord des
sources (« 1/2 »), date de l'import. Construite sur le modèle de « Valider les
suggestions » (suggestion_validation_dialog.py) pour garder le même geste :
cocher = vérifié, double-clic sur Type/Marque = corriger via la fenêtre Cmd+D.

La validation remet au callback `on_validate(verifies, corrections)` :
    verifies    : ids des appareils cochés (leurs traces seront retirées) ;
    corrections : [(id, {champ: valeur})] des seuls champs modifiés.

Non bloquant : ouvert via show() + callback (jamais exec_(), cf. conventions projet).
"""

from datetime import datetime

from .style_manager import StyleManager
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QFrame, QHeaderView, QMenu, QShortcut,
    QApplication, QAbstractItemView,
)
import qtawesome as qta

from src.core.config import pluralize
from .tri_colonnes import ItemTriable, ROLE_TRI, activer_tri, TriSuspendu
from .espace_coche import activer_espace_coche

# ── Colonnes ────────────────────────────────────────────────────────────────
COL_CHECK = 0
COL_REF = 1
COL_TYPE = 2
COL_MFR = 3
COL_CONFIANCE = 4
COL_SOURCE = 5
COL_IMPORT = 6

_HEADERS = ["", "Référence", "Type", "Marque", "Confiance", "Source", "Import"]
_CHAMP_PAR_COLONNE = {COL_TYPE: 'type', COL_MFR: 'manufacturer'}

_ROLE_ID = Qt.UserRole
_ROLE_REF = Qt.UserRole + 1
_ROLE_ORIGINAL = Qt.UserRole + 2   # {champ: valeur actuelle en base}


def regrouper_traces(lignes):
    """Lignes de `lire_autocompletions_a_verifier` → une entrée par appareil.

    Returns:
        [{'id', 'ref_modele', 'commercial_ref', 'type', 'manufacturer',
          'champs': {champ: {'valeur', 'source', 'accord', 'total'}},
          'import_ts'}], triées du moins sûr au plus sûr (cf. cle_de_tri).
    """
    par_id = {}
    for (appareil_id, ref_modele, commercial_ref, type_actuel, fabricant_actuel,
         champ, valeur, source, accord, total, import_ts) in lignes or []:
        entree = par_id.setdefault(appareil_id, {
            'id': appareil_id, 'ref_modele': ref_modele or '',
            'commercial_ref': commercial_ref or '', 'type': type_actuel or '',
            'manufacturer': fabricant_actuel or '', 'champs': {}, 'import_ts': import_ts,
        })
        entree['champs'][champ] = {'valeur': valeur, 'source': source or '',
                                   'accord': accord, 'total': total}
        entree['import_ts'] = max(entree['import_ts'] or '', import_ts or '')
    return sorted(par_id.values(), key=cle_de_tri)


def confiance(entree):
    """(accord, total) du champ le moins sûr de l'appareil ; (None, None) si une
    source ne dit rien de sa représentativité (cache du chemin batch)."""
    pire = None
    for p in entree['champs'].values():
        if p['accord'] is None or not p['total']:
            return (None, None)
        if pire is None or (p['accord'] / p['total'], p['total']) < (pire[0] / pire[1], pire[1]):
            pire = (p['accord'], p['total'])
    return pire or (None, None)


def cle_de_tri(entree):
    """Inconnue d'abord, puis par accord croissant, puis par nombre de sources
    croissant (« 1/1 » est moins sûr que « 12/12 »), puis import le plus récent."""
    accord, total = confiance(entree)
    import_ts = entree.get('import_ts') or ''
    recence = tuple(-ord(c) for c in import_ts)
    if accord is None:
        return (0, 0, 0, recence)
    return (1, accord / total, total, recence)


def couleur_confiance(accord, total):
    """Vert : unanimité sur au moins 2 sources. Ambre : une seule source, ou
    majorité nette. Rouge : sources partagées ou confiance inconnue."""
    if accord is None:
        return QColor("#c0392b")
    if accord == total and total >= 2:
        return QColor("#2e7d32")
    if accord == total or accord / total >= 0.75:
        return QColor("#b06a00")
    return QColor("#c0392b")


def libelle_confiance(accord, total):
    if accord is None:
        return "?"
    return f"{accord}/{total}"


def date_lisible(import_ts):
    try:
        return datetime.fromisoformat(import_ts).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return import_ts or ''


class AutocompletionReviewDialog(QDialog):
    def __init__(self, parent, entrees, on_validate, value_picker=None):
        """value_picker(db_field, current_value, candidates) -> str|dict|None :
        fenêtre Cmd+D. Optionnel (correction désactivée si absent, pour les tests)."""
        super().__init__(parent)
        self._entrees = entrees or []
        self._on_validate = on_validate
        self._value_picker = value_picker
        self._suppress = False
        self._items = []

        self.setWindowTitle("Auto-complétés à vérifier")
        self.resize(1060, 600)
        self.setMinimumSize(720, 400)

        self._build_ui()
        self._populate()
        self._update_count()

    # ── Construction UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)

        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background: #FFF8E1; border: 1px solid #f39c12; border-radius: 3px; }"
        )
        b_lay = QVBoxLayout(banner)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.magic', color='#f39c12').pixmap(18, 18))
        title_row.addWidget(icon)
        self._title_label = QLabel()
        self._title_label.setStyleSheet("border: none; font-weight: bold;")
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        b_lay.addLayout(title_row)
        help_label = QLabel(
            "Valeurs en italique : écrites par l'auto-complétion d'un import. Tout est coché "
            "(présumé juste) : décochez ce qui reste à revoir (Espace sur la ligne courante), "
            "double-cliquez une valeur Type ou Marque pour la corriger. "
            "Confiance : appareils sources d'accord / appareils sources trouvés."
        )
        help_label.setStyleSheet("border: none; color: #666; font-size: 11px;")
        help_label.setWordWrap(True)
        b_lay.addWidget(help_label)
        root.addWidget(banner)

        tools = QHBoxLayout()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrer par référence, type, marque ou source…")
        self._filter.addAction(qta.icon('fa5s.search', color='#888'), QLineEdit.LeadingPosition)
        self._filter.textChanged.connect(self._on_filter)
        tools.addWidget(self._filter, 1)
        self._count_label = QLabel()
        self._count_label.setStyleSheet("color: #444;")
        tools.addWidget(self._count_label)
        root.addLayout(tools)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_HEADERS))
        self._tree.setHeaderLabels(_HEADERS)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        copy_sc = QShortcut(QKeySequence.Copy, self._tree)
        copy_sc.setContext(Qt.WidgetShortcut)
        copy_sc.activated.connect(self._copy_selected_refs)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_REF, QHeaderView.Stretch)
        self._tree.setColumnWidth(COL_CHECK, 34)
        self._tree.setColumnWidth(COL_TYPE, 140)
        self._tree.setColumnWidth(COL_MFR, 120)
        self._tree.setColumnWidth(COL_CONFIANCE, 88)
        self._tree.setColumnWidth(COL_SOURCE, 120)
        # Calée sur la date affichée : à 118 px, l'heure était tronquée
        self._tree.setColumnWidth(
            COL_IMPORT, self._tree.fontMetrics().horizontalAdvance("00/00/0000 00:00") + 24)
        activer_tri(self._tree)
        activer_espace_coche(self._tree)
        root.addWidget(self._tree, 1)

        actions = QHBoxLayout()
        uncheck_btn = QPushButton("Tout décocher")
        uncheck_btn.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        uncheck_btn.setAutoDefault(False)
        uncheck_btn.clicked.connect(lambda: self._set_all_checked(False))
        actions.addWidget(uncheck_btn)
        check_btn = QPushButton("Tout cocher")
        check_btn.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        check_btn.setAutoDefault(False)
        check_btn.clicked.connect(lambda: self._set_all_checked(True))
        actions.addWidget(check_btn)
        actions.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.reject)
        actions.addWidget(close_btn)
        self._validate_btn = QPushButton()
        self._validate_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self._validate_btn.setDefault(True)
        self._validate_btn.clicked.connect(self._on_validate_clicked)
        actions.addWidget(self._validate_btn)
        root.addLayout(actions)

    # ── Remplissage ──────────────────────────────────────────────────────────
    def _populate(self):
        with TriSuspendu(self._tree):
            self._remplir()

    def _remplir(self):
        self._suppress = True
        italique = QFont()
        italique.setItalic(True)
        for entree in self._entrees:
            item = ItemTriable(self._tree)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # Cochée par défaut : une auto-complétion est présumée juste, on ne
            # décoche que celles à revoir (demande utilisateur, v3.89.1)
            item.setCheckState(COL_CHECK, Qt.Checked)
            refs = " - ".join(r for r in (entree['ref_modele'], entree['commercial_ref']) if r)
            item.setText(COL_REF, refs or f"#{entree['id']}")
            item.setData(COL_CHECK, _ROLE_ID, entree['id'])
            item.setData(COL_CHECK, _ROLE_REF, entree['ref_modele'] or entree['commercial_ref'])
            item.setData(COL_CHECK, _ROLE_ORIGINAL,
                         {'type': entree['type'], 'manufacturer': entree['manufacturer']})
            for col, champ in _CHAMP_PAR_COLONNE.items():
                item.setText(col, entree[champ])
                prov = entree['champs'].get(champ)
                if prov:
                    item.setFont(col, italique)
                    item.setToolTip(col, (
                        f"Auto-complété d'après {prov['source'] or '?'} "
                        f"({libelle_confiance(prov['accord'], prov['total'])})"))
                else:
                    item.setForeground(col, QBrush(QColor("#9e9e9e")))
            accord, total = confiance(entree)
            item.setText(COL_CONFIANCE, libelle_confiance(accord, total))
            # Même ordre que l'ouverture : inconnue, puis accord et nb de sources croissants
            item.setData(COL_CONFIANCE, ROLE_TRI, cle_de_tri(entree)[:3])
            item.setForeground(COL_CONFIANCE, QBrush(couleur_confiance(accord, total)))
            item.setTextAlignment(COL_CONFIANCE, Qt.AlignCenter)
            if accord is None:
                item.setToolTip(COL_CONFIANCE, "Une seule source connue, représentativité inconnue")
            sources = sorted({p['source'] for p in entree['champs'].values() if p['source']})
            item.setText(COL_SOURCE, ", ".join(sources))
            item.setText(COL_IMPORT, date_lisible(entree.get('import_ts')))
            item.setData(COL_IMPORT, ROLE_TRI, entree.get('import_ts') or '')
            self._items.append(item)
        self._suppress = False

    # ── Interactions ─────────────────────────────────────────────────────────
    def _on_item_double_clicked(self, item, column):
        """Correction d'une valeur via la fenêtre Cmd+D ; la ligne est cochée."""
        champ = _CHAMP_PAR_COLONNE.get(column)
        if self._value_picker is None or champ is None:
            return
        result = self._value_picker(champ, item.text(column), [])
        if result is None:
            return
        if isinstance(result, dict):
            result = result.get(champ) or ''
        result = (result or '').strip()
        if not result:
            return
        self._suppress = True
        item.setText(column, result)
        original = (item.data(COL_CHECK, _ROLE_ORIGINAL) or {}).get(champ, '')
        item.setBackground(column, QBrush(QColor("#E3F2FD") if result != original else Qt.transparent))
        item.setCheckState(COL_CHECK, Qt.Checked)
        self._suppress = False
        self._update_count()

    def _on_item_changed(self, item, column):
        if not self._suppress and column == COL_CHECK:
            self._update_count()

    def _on_context_menu(self, pos):
        refs = self._selected_refs()
        if not refs:
            return
        menu = QMenu(self)
        action = menu.addAction(f"Copier {pluralize(len(refs), 'référence')}")
        action.triggered.connect(self._copy_selected_refs)
        menu.exec_(self._tree.viewport().mapToGlobal(pos))

    def _selected_refs(self):
        return [r for r in (it.data(COL_CHECK, _ROLE_REF) for it in self._tree.selectedItems()) if r]

    def _copy_selected_refs(self):
        refs = self._selected_refs()
        if refs:
            QApplication.clipboard().setText("\n".join(refs))

    def _on_filter(self, text):
        text = (text or '').strip().lower()
        for item in self._items:
            hay = " ".join(item.text(c) for c in (COL_REF, COL_TYPE, COL_MFR, COL_SOURCE)).lower()
            item.setHidden(bool(text) and text not in hay)

    def _set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self._suppress = True
        for item in self._items:
            if not item.isHidden():
                item.setCheckState(COL_CHECK, state)
        self._suppress = False
        self._update_count()

    def _checked_items(self):
        return [it for it in self._items if it.checkState(COL_CHECK) == Qt.Checked]

    def _update_count(self):
        total = len(self._items)
        sel = len(self._checked_items())
        self._title_label.setText(f"{pluralize(total, 'appareil')} auto-complété"
                                  f"{'s' if total > 1 else ''} à vérifier")
        self._count_label.setText(f"{pluralize(sel, 'coché')} sur {total}")
        self._validate_btn.setText(f"Marquer comme vérifiés ({sel})")
        self._validate_btn.setEnabled(sel > 0)

    # ── Validation ───────────────────────────────────────────────────────────
    def collecter_decisions(self):
        """(verifies, corrections) des lignes cochées — cf. docstring du module."""
        verifies, corrections = [], []
        for item in self._checked_items():
            appareil_id = item.data(COL_CHECK, _ROLE_ID)
            original = item.data(COL_CHECK, _ROLE_ORIGINAL) or {}
            verifies.append(appareil_id)
            champs = {champ: item.text(col).strip()
                      for col, champ in _CHAMP_PAR_COLONNE.items()
                      if item.text(col).strip() and item.text(col).strip() != original.get(champ, '')}
            if champs:
                corrections.append((appareil_id, champs))
        return verifies, corrections

    def _on_validate_clicked(self):
        verifies, corrections = self.collecter_decisions()
        if verifies and callable(self._on_validate):
            self._on_validate(verifies, corrections)
        self.accept()
