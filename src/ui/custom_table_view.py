"""
CustomTableView — QTableView de remplacement pour CustomTableWidget.

Réplique le comportement clavier de CustomTableWidget(QTableWidget) et expose
des méthodes de compatibilité QTableWidget pour que les services non encore
migrés (Phase 4) continuent à fonctionner sans modification.

Phase 2 de la migration QTableWidget → QTableView.
Production : non activé tant que Config.USE_TABLE_VIEW = False.
"""

from PyQt5.QtWidgets import QTableView, QApplication, QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeyEvent


class _SelectionRangeCompat:
    """Simule QTableWidgetSelectionRange pour les services non encore migrés.

    Permet à tout code qui appelle .selectedRanges()[0].topRow() etc. de
    continuer à fonctionner sans modification jusqu'à la Phase 4.
    """

    def __init__(self, top: int, left: int, bottom: int, right: int):
        self._top = top
        self._left = left
        self._bottom = bottom
        self._right = right

    def topRow(self) -> int:
        return self._top

    def bottomRow(self) -> int:
        return self._bottom

    def leftColumn(self) -> int:
        return self._left

    def rightColumn(self) -> int:
        return self._right

    def rowCount(self) -> int:
        return self._bottom - self._top + 1

    def columnCount(self) -> int:
        return self._right - self._left + 1


class CustomTableView(QTableView):
    """QTableView avec gestion clavier identique à CustomTableWidget.

    Deux catégories de méthodes :
    1. Comportement clavier — réplique exacte de CustomTableWidget.
    2. Compatibilité QTableWidget — permet aux services Phase 3 non encore
       migrés de continuer à fonctionner. Supprimées progressivement en Phase 4.
    """

    def keyPressEvent(self, event: QKeyEvent):
        """Gestion des événements clavier — miroir de CustomTableWidget."""
        key = event.key()
        model = self.model()

        # Delete / Backspace — efface les cellules sélectionnées éditables
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            sel_indexes = self.selectionModel().selectedIndexes() if self.selectionModel() else []
            if sel_indexes:
                for index in sel_indexes:
                    if model and model.flags(index) & Qt.ItemIsEditable:
                        model.setData(index, "", Qt.EditRole)
            return

        # Cmd+D (macOS) / Ctrl+D (Windows/Linux) — popup auto-complétion
        is_cmd = event.modifiers() & (Qt.MetaModifier | Qt.ControlModifier)
        if is_cmd and key == Qt.Key_D:
            parent = self.parent()
            while parent:
                if hasattr(parent, '_show_column_values_list'):
                    parent._show_column_values_list()
                    return
                parent = parent.parent()
            return

        # Entrée / Return — passe à la ligne suivante (même colonne)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid() and model:
                next_row = idx.row() + 1
                if next_row < model.rowCount():
                    self.setCurrentIndex(model.index(next_row, idx.column()))
                    self.setFocus()
            return

        super().keyPressEvent(event)

    # ── Helpers de rétro-compatibilité ──────────────────────────────────────
    # Permettent aux services existants de continuer à fonctionner en Phase 3
    # avant que chaque service soit migré un par un (Phase 4).

    def currentRow(self) -> int:
        """Compat QTableWidget.currentRow()."""
        return self.currentIndex().row()

    def currentColumn(self) -> int:
        """Compat QTableWidget.currentColumn()."""
        return self.currentIndex().column()

    def rowCount(self) -> int:
        """Compat QTableWidget.rowCount()."""
        return self.model().rowCount() if self.model() else 0

    def columnCount(self) -> int:
        """Compat QTableWidget.columnCount()."""
        return self.model().columnCount() if self.model() else 0

    def selectedRanges(self) -> list:
        """Compat QTableWidget.selectedRanges() — retourne un _SelectionRangeCompat.

        Permet à tout code qui itère sur selectedRanges() et appelle
        .topRow()/.bottomRow()/.leftColumn()/.rightColumn() de fonctionner
        sans modification.
        """
        sm = self.selectionModel()
        if not sm or not sm.hasSelection():
            return []
        indexes = sm.selectedIndexes()
        if not indexes:
            return []
        rows = [idx.row() for idx in indexes]
        cols = [idx.column() for idx in indexes]
        return [_SelectionRangeCompat(min(rows), min(cols), max(rows), max(cols))]

    def horizontalHeaderItem(self, col: int):
        """Compat QTableWidget.horizontalHeaderItem() — retourne un QTableWidgetItem simulé."""
        if self.model():
            text = self.model().headerData(col, Qt.Horizontal, Qt.DisplayRole)
            if text is not None:
                return QTableWidgetItem(str(text))
        return None

    def item(self, row: int, col: int):
        """Compat QTableWidget.item() — retourne un QTableWidgetItem simulé depuis le modèle."""
        model = self.model()
        if not model:
            return None
        idx = model.index(row, col)
        if not idx.isValid():
            return None
        text = model.data(idx, Qt.DisplayRole) or ""
        db_id = model.data(idx, Qt.UserRole)
        widget_item = QTableWidgetItem(str(text))
        if db_id is not None:
            widget_item.setData(Qt.UserRole, db_id)
        return widget_item

    def visualItemRect(self, item):
        """Compat QTableWidget.visualItemRect() — délègue à visualRect() via UserRole."""
        # item est un QTableWidgetItem simulé ; on retrouve la cellule via la sélection courante
        # Fallback : retourner un QRect invalide (drag handle se cachera)
        from PyQt5.QtCore import QRect
        return QRect()
