# Migration QTableWidget → QTableView + QAbstractTableModel

**Branche** : `feature/qtableview-migration`
**Version de départ** : 3.15.8 (main)
**Objectif** : Remplacer `QTableWidget` par `QTableView + QAbstractTableModel` pour séparer données et rendu, réduire la mémoire et accélérer l'affichage.
**Principe absolu** : ZERO REGRESSION — feature flag `USE_TABLE_VIEW` réversible à tout moment.

---

## État d'avancement

| Phase | Statut | Version | Notes |
|-------|--------|---------|-------|
| 0 — Préparation (feature flag + tests) | ⬜ À faire | — | |
| 1 — `AppareillsTableModel` isolé | ✅ Fait | `src/data/appareils_table_model.py` | 13/13 tests verts |
| 2 — `CustomTableView` isolé | ⬜ À faire | — | |
| 3 — Swap dans `table_controller` | ⬜ À faire | — | |
| 4a — `cell_editing_service` | ⬜ À faire | — | |
| 4b — Signaux `main_refactored` | ⬜ À faire | — | |
| 4c — Données `main_refactored` | ⬜ À faire | — | |
| 4d — `drag_handle_service` | ⬜ À faire | — | |
| 5 — Nettoyage final | ⬜ À faire | — | |

Légende : ⬜ À faire · 🔄 En cours · ✅ Terminé · ⚠️ Bloqué

---

## Principes directeurs

1. **Feature flag `USE_TABLE_VIEW = False`** dans `config.py` — bascule instantanément réversible
2. **Strangler Fig** — les deux implémentations coexistent, on migre service par service
3. **Tests avant code** — chaque phase commence par les tests qui valident ce qui précède
4. **Jamais de big bang** — une seule sous-phase par session de travail

---

## Architecture cible

```
src/
  data/
    appareils_table_model.py   ← NOUVEAU (Phase 1)
  ui/
    custom_table_view.py       ← NOUVEAU (Phase 2)
  services/
    cell_editing_service.py    ← MODIFIÉ (Phase 4a)
    drag_handle_service.py     ← MODIFIÉ (Phase 4d) — le plus délicat
    table_fill_service.py      ← MODIFIÉ (Phase 3) puis SUPPRIMÉ (Phase 5)
  ui/
    main_refactored.py         ← MODIFIÉ (Phase 4b + 4c)
    table_controller.py        ← MODIFIÉ (Phase 3)
  core/
    config.py                  ← USE_TABLE_VIEW = False ajouté (Phase 0)
tests/
  test_table_model.py          ← NOUVEAU (Phase 0)
```

---

## Table de correspondance API — Référence permanente

| Pattern actuel (QTableWidget) | Équivalent QTableView | Difficulté |
|-------------------------------|----------------------|------------|
| `table.item(r,c).text()` | `model.data(model.index(r,c))` | Faible |
| `table.item(r,c).data(UserRole)` | `model.get_db_id(r)` | Faible |
| `table.setItem(r,c, QTableWidgetItem(v))` | `model.setData(model.index(r,c), v)` | Faible |
| `table.currentRow()` | `view.currentIndex().row()` | Faible |
| `table.currentColumn()` | `view.currentIndex().column()` | Faible |
| `table.currentItem()` | `view.currentIndex()` → QModelIndex | Faible |
| `table.setCurrentCell(r,c)` | `view.setCurrentIndex(model.index(r,c))` | Faible |
| `table.rowCount()` | `model.rowCount()` | Faible |
| `table.setRowCount(n)` + boucle setItem | `model.load_records(records)` — **1 ligne** | Faible |
| `table.blockSignals(True/False)` | `model.beginResetModel()/endResetModel()` | Moyen |
| `table.itemChanged` signal | `model.cell_edited(row,col,old,new)` signal custom | Moyen |
| `table.currentItemChanged` signal | `selectionModel().currentChanged` | Moyen |
| `table.selectedItems()` | `[model.data(idx) for idx in selectionModel().selectedIndexes()]` | Moyen |
| `table.selectedRanges()` | `view.selectionModel().selection()` → QItemSelection | **Élevé** |
| `table.setRangeSelected(range, True)` | `selectionModel().select(QItemSelection(...), ClearAndSelect)` | **Élevé** |
| `item.setBackground(color)` | `model.data(index, BackgroundRole)` retourne QBrush | Moyen |
| `item.setFlags(...)` | `model.flags(index)` méthode | Faible |
| `table.setColumnHidden(c,b)` | `view.setColumnHidden(c,b)` — **identique** | Zéro |
| `table.horizontalHeader()` | `view.horizontalHeader()` — **identique** | Zéro |
| `table.viewport()` | `view.viewport()` — **identique** | Zéro |
| `QTableWidgetSelectionRange(t,l,b,r)` | `QItemSelection(model.index(t,l), model.index(b,r))` | Moyen |
| `range.topRow() / bottomRow()` | `item_range.top() / bottom()` | Faible |

---

## Phase 0 — Préparation

**Statut** : ⬜ À faire · **Durée estimée** : 30 min · **Risque** : Zéro

### Tâches

- [ ] Ajouter dans `src/core/config.py` :
  ```python
  USE_TABLE_VIEW = False  # Migration QTableView — Phase 5 — NE PAS ACTIVER EN PROD
  ```
- [ ] Créer `tests/test_table_model.py` avec les cas de test suivants (à écrire *avant* la Phase 1) :
  - `test_load_records_emits_model_reset`
  - `test_data_display_role_returns_string`
  - `test_data_user_role_returns_db_id`
  - `test_setdata_updates_record_and_emits_cell_edited`
  - `test_setdata_emits_dataChanged`
  - `test_pieces_column_not_editable`
  - `test_pieces_background_green_when_nonzero`
  - `test_rowcount_after_load`
  - `test_get_db_id_returns_correct_value`

### Validation
```bash
python3 -m pytest tests/test_table_model.py  # Tous les tests doivent ÉCHOUER (modèle pas encore écrit)
```

---

## Phase 1 — `AppareillsTableModel`

**Statut** : ✅ Fait · **Durée estimée** : 1h · **Risque** : Zéro (fichier additionnel)

### Fichier à créer : `src/data/appareils_table_model.py`

```python
class AppareillsTableModel(QAbstractTableModel):
    # Signal custom — remplace itemChanged de QTableWidget
    cell_edited = pyqtSignal(int, int, str, str)  # row, col, old_value, new_value

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._records = []           # List[Tuple]: (db_id, col1..colN, pieces_count)
        self._headers = Config.UI_HEADERS
        self._main_window = main_window
        self._search_term = None

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._records)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._records):
            return None
        row, col = index.row(), index.column()
        record = self._records[row]

        if role in (Qt.DisplayRole, Qt.EditRole):
            if col < len(Config.DB_HEADERS):
                return str(record[col + 1] or "")   # record[0] = db_id
            else:                                    # Nb Pièces (dernière colonne)
                return str(record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0)

        elif role == Qt.UserRole:                    # db_id — remplace item.data(UserRole)
            return record[0]

        elif role == Qt.BackgroundRole:
            if col == len(Config.DB_HEADERS):        # Nb Pièces
                pieces = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
                return QBrush(QColor(220, 248, 198) if pieces > 0 else QColor(248, 248, 248))
            if self._search_term and self._main_window:
                # Déléguer au AdvancedSearchService (même logique qu'avant)
                # TODO: implémenter apply_search_highlight via BackgroundRole

        elif role == Qt.ToolTipRole:
            if col == len(Config.DB_HEADERS):
                pieces = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
                return f"{pieces} pièce(s) associée(s)" if pieces > 0 else "Aucune pièce associée"

        return None

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False
        row, col = index.row(), index.column()
        old_value = self.data(index, Qt.DisplayRole) or ""
        new_value = str(value)
        record = list(self._records[row])
        if col < len(Config.DB_HEADERS):
            record[col + 1] = new_value
        self._records[row] = tuple(record)
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        self.cell_edited.emit(row, col, old_value, new_value)
        return True

    def flags(self, index) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() == len(Config.DB_HEADERS):   # Nb Pièces — lecture seule
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._headers[section] if section < len(self._headers) else None
            else:
                return str(section + 1)   # 1-indexed comme l'ancien setVerticalHeaderItem
        return None

    # === API custom ===

    def load_records(self, records: list):
        """Remplace setRowCount(n) + boucle setItem(). Une seule ligne."""
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()

    def get_db_id(self, row: int):
        """Remplace item(row, col).data(Qt.UserRole). Utilisé dans 20+ endroits."""
        return self._records[row][0] if 0 <= row < len(self._records) else None

    def get_record(self, row: int):
        return self._records[row] if 0 <= row < len(self._records) else None

    def set_search_term(self, term):
        """Mise à jour terme de recherche pour le highlight — appelé depuis load_data."""
        self._search_term = term
        if self._records:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._records) - 1, len(self._headers) - 1),
                [Qt.BackgroundRole]
            )
```

### Validation
```bash
python3 -m pytest tests/test_table_model.py  # Tous les tests doivent PASSER
python3 -c "from src.data.appareils_table_model import AppareillsTableModel; print('OK')"
```

---

## Phase 2 — `CustomTableView`

**Statut** : ⬜ À faire · **Durée estimée** : 30 min · **Risque** : Zéro (fichier additionnel)

### Fichier à créer : `src/ui/custom_table_view.py`

```python
class CustomTableView(QTableView):
    """Remplacement de CustomTableWidget(QTableWidget)"""

    def keyPressEvent(self, event):
        key = event.key()

        # Delete / Backspace — efface les cellules sélectionnées
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            for index in self.selectionModel().selectedIndexes():
                if self.model().flags(index) & Qt.ItemIsEditable:
                    self.model().setData(index, "")
            return

        # Cmd+D — autocomplete popup
        is_cmd = event.modifiers() & (Qt.MetaModifier | Qt.ControlModifier)
        if is_cmd and key == Qt.Key_D:
            parent = self.parent()
            while parent:
                if hasattr(parent, '_show_column_values_list'):
                    parent._show_column_values_list()
                    return
                parent = parent.parent()
            return

        # Entrée — navigation ligne suivante
        if key in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid():
                next_row = idx.row() + 1
                if next_row < self.model().rowCount():
                    self.setCurrentIndex(self.model().index(next_row, idx.column()))
            return

        super().keyPressEvent(event)

    # Helpers de rétro-compatibilité (évitent de tout casser en Phase 3)
    def currentRow(self) -> int:
        return self.currentIndex().row()

    def currentColumn(self) -> int:
        return self.currentIndex().column()

    def rowCount(self) -> int:
        return self.model().rowCount() if self.model() else 0
```

### Validation
```bash
python3 -c "from src.ui.custom_table_view import CustomTableView; print('OK')"
```

---

## Phase 3 — Swap dans `table_controller` (derrière le feature flag)

**Statut** : ⬜ À faire · **Durée estimée** : 1-2h · **Risque** : Moyen (encapsulé, réversible)

### `src/ui/table_controller.py` — `create_table_widget()`

```python
if Config.USE_TABLE_VIEW:
    from ..data.appareils_table_model import AppareillsTableModel
    from .custom_table_view import CustomTableView
    self.model = AppareillsTableModel(self.parent_window)
    self.table = CustomTableView()
    self.table.setModel(self.model)
    # Même configuration header/colonnes/drag/sort qu'avant
else:
    self.table = self.table_widget_service.create_custom_table()
    # Code existant intact
```

### `src/services/table_fill_service.py`

```python
if Config.USE_TABLE_VIEW:
    # Une seule ligne remplace 50+ lignes de setItem
    tc = self.main_window.table_controller
    tc.model.set_search_term(search_term)
    tc.model.load_records(records)
else:
    # Code existant setUpdatesEnabled + boucle intact
    ...
```

### Critères de validation (avec `USE_TABLE_VIEW = True`)
- [ ] Données affichées correctement toutes pages
- [ ] Pagination fonctionnelle (Précédent / Suivant)
- [ ] F5 actualise
- [ ] Tri par colonne fonctionnel
- [ ] Aucun crash au démarrage
- [ ] Repasser `USE_TABLE_VIEW = False` avant de committer

---

## Phase 4a — `cell_editing_service.py` (11 accès)

**Statut** : ⬜ À faire · **Durée estimée** : 30 min · **Risque** : Faible

### Accès à migrer (sous `if Config.USE_TABLE_VIEW`)

| Ligne | Avant | Après |
|-------|-------|-------|
| 115 | `table.item(row, 0)` | `model.get_db_id(row)` |
| 214 | `table.currentItem()` | `view.currentIndex()` |
| 300,302,339,343 | `table.item(row, col).text()` | `model.data(model.index(row, col))` |
| 324 | `table.currentRow()` | `view.currentRow()` (helper compat) |
| 325 | `table.currentColumn()` | `view.currentColumn()` (helper compat) |
| 332 | `table.rowCount()` | `model.rowCount()` |
| 349 | `table.setCurrentCell(r,c)` | `view.setCurrentIndex(model.index(r,c))` |

---

## Phase 4b — Signaux `main_refactored.py`

**Statut** : ⬜ À faire · **Durée estimée** : 45 min · **Risque** : Moyen

### Connexions à adapter (lignes ~445-446)

```python
if Config.USE_TABLE_VIEW:
    tc.model.cell_edited.connect(self._on_cell_changed)
    tc.table.selectionModel().currentChanged.connect(self._on_current_item_changed_new)
else:
    self.table.itemChanged.connect(self._on_cell_changed)
    self.table.currentItemChanged.connect(self._on_current_item_changed)
```

### `_on_cell_changed` — adapter la signature

```python
# AVANT: reçoit un QTableWidgetItem
def _on_cell_changed(self, item: QTableWidgetItem):
    row, col = item.row(), item.column()
    new_value = item.text()

# APRÈS: reçoit (row, col, old_value, new_value) depuis cell_edited
def _on_cell_changed(self, row: int, col: int, old_value: str, new_value: str):
    ...
```

### `blockSignals` dans undo / redo / autocomplete (lignes 1478, 1497, 1526)

```python
if Config.USE_TABLE_VIEW:
    self.table_controller.model.blockSignals(True)
else:
    self.table.blockSignals(True)
```

---

## Phase 4c — Données `main_refactored.py` (~20 occurrences)

**Statut** : ⬜ À faire · **Durée estimée** : 1h · **Risque** : Moyen

### Patterns systématiques

```python
# item(r,c).text()
model.data(model.index(r, c))

# item(r,c).data(Qt.UserRole) — db_id
model.get_db_id(r)

# selectedItems() (ligne 2529)
[model.data(idx) for idx in table.selectionModel().selectedIndexes()]

# selectedRanges() vérification vide (ligne 1082, 2730)
table.selectionModel().selection().isEmpty()

# Boucle copie sur ranges (lignes 2714-2717)
for item_range in table.selectionModel().selection():
    for r in range(item_range.top(), item_range.bottom() + 1):
        for c in range(item_range.left(), item_range.right() + 1):
            val = model.data(model.index(r, c))
```

---

## Phase 4d — `drag_handle_service.py` (29 accès — LE PLUS DÉLICAT)

**Statut** : ⬜ À faire · **Durée estimée** : 1-2h · **Risque** : Élevé

> ⚠️ **À faire en dernier et à la main, sans agent.** Le drag ne doit pas bloquer les signaux — c'est intentionnel pour que `cell_edited` déclenche la sauvegarde automatique.

### `selectedRanges()` → `selectionModel().selection()`

```python
# AVANT (lignes 58, 69, 246, 264)
ranges = self.table.selectedRanges()
for r in ranges:
    top, bottom = r.topRow(), r.bottomRow()
    left, right = r.leftColumn(), r.rightColumn()

# APRÈS
from PyQt5.QtCore import QItemSelection, QItemSelectionModel
selection = self.table.selectionModel().selection()
for item_range in selection:
    top, bottom = item_range.top(), item_range.bottom()
    left, right = item_range.left(), item_range.right()
```

### `setRangeSelected()` → `selectionModel().select()`

```python
# AVANT (lignes 161, 217, 318)
self.table.setRangeSelected(QTableWidgetSelectionRange(top, left, bottom, right), True)

# APRÈS
model = self.table.model()
sel = QItemSelection(model.index(top, left), model.index(bottom, right))
self.table.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect)
```

### `setItem()` → `model.setData()`

```python
# AVANT (lignes 143, 199, 304)
new_item = QTableWidgetItem(source_value)
self.table.setItem(dest_row, dest_col, new_item)

# APRÈS
self.table.model().setData(self.table.model().index(dest_row, dest_col), source_value)
# → émet automatiquement cell_edited → sauvegarde auto (comportement préservé)
```

---

## Phase 5 — Nettoyage final

**Statut** : ⬜ À faire · **Durée estimée** : 30 min · **Risque** : Faible

- [ ] `USE_TABLE_VIEW = True` en permanence
- [ ] Supprimer les branches `else` (ancien code QTableWidget)
- [ ] Supprimer `CustomTableWidget` de `table_widget_service.py`
- [ ] Simplifier `table_fill_service.py` (supprimer les boucles setItem devenues inutiles)
- [ ] Retirer le feature flag `USE_TABLE_VIEW` de `config.py`
- [ ] PR vers `main` avec description des changements

---

## Agents configurés

| Phase | Agent | Mode | Raison |
|-------|-------|------|--------|
| 1 | `general-purpose` | `isolation: worktree` | Modèle pur, testable en isolation complète |
| 4c | `general-purpose` | `isolation: worktree` | Remplacement en masse ~20 patterns `item(r,c)` |
| 5 | `general-purpose` | Normal | Suppression code mort — tâche mécanique |
| 4d | **Direct (pas d'agent)** | — | Trop critique — vérification manuelle ligne par ligne |

---

## Récapitulatif par session

| Phase | Contenu | Durée | Risque | Flag requis |
|-------|---------|-------|--------|-------------|
| 0 | Feature flag + tests | 30 min | Zéro | Non |
| 1 | `AppareillsTableModel` | 1h | Zéro | Non |
| 2 | `CustomTableView` | 30 min | Zéro | Non |
| 3 | Swap `table_controller` | 1-2h | Moyen | `= True` pour tester |
| 4a | `cell_editing_service` | 30 min | Faible | Oui |
| 4b | Signaux `main_refactored` | 45 min | Moyen | Oui |
| 4c | Données `main_refactored` | 1h | Moyen | Oui |
| 4d | `drag_handle_service` | 1-2h | Élevé | Oui |
| 5 | Nettoyage final | 30 min | Faible | — |
| **Total** | | **~7-10h** | | |

---

*Dernière mise à jour : 2026-03-09 — Phase 0 non commencée*
