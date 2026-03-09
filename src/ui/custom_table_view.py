"""
CustomTableView — QTableView de remplacement pour CustomTableWidget.

Réplique le comportement clavier de CustomTableWidget(QTableWidget) mais
utilise l'API QTableView standard (modèle/vue découplés).

Phase 2 de la migration QTableWidget → QTableView.
Production : non activé tant que Config.USE_TABLE_VIEW = False.
"""

from PyQt5.QtWidgets import QTableView, QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeyEvent


class CustomTableView(QTableView):
    """QTableView avec gestion clavier identique à CustomTableWidget.

    Helpers de rétro-compatibilité inclus (currentRow, currentColumn, rowCount)
    pour éviter de tout casser lors du swap en Phase 3. Ces helpers seront
    supprimés progressivement en Phase 4 lors de la migration des services.
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
            # Remonte la chaîne parent pour trouver _show_column_values_list
            # (défini dans main_refactored.py)
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
