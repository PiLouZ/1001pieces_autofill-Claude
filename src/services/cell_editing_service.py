"""
Service d'édition des cellules — ce qu'il en reste : la navigation vers la
prochaine cellule vide (Cmd+↓ / Cmd+↑).

L'ancienne édition directe des cellules (QTableWidget : écriture en base,
validation, lots, création de ligne) a été retirée : l'édition passe par le
modèle du tableau et EventDrivenSaveService.
"""

from ..ui.qt_imports import QTableWidget, QObject

from ..data.database_manager import DatabaseManager
from ..data.data_validator import DataValidator
from ..utils.error_handler import handle_errors

class CellEditingService(QObject):
    """Navigation vers les cellules vides du tableau"""

    def __init__(self, table_widget: QTableWidget, db_manager: DatabaseManager,
                 data_validator: DataValidator, parent=None):
        super().__init__(parent)
        self.table = table_widget
        self.db_manager = db_manager
        self.data_validator = data_validator
        self.parent_window = parent

    @handle_errors(title="Erreur navigation cellule vide", return_on_error=False)
    def navigate_to_empty_cell(self, direction: str = 'down') -> bool:
        """Navigation intelligente vers une cellule vide"""
        current_row = self.table.currentRow()
        current_col = self.table.currentColumn()

        if current_row < 0 or current_col < 0:
            return False

        # Déterminer la direction de recherche
        if direction == 'down':
            start_row, end_row, step = current_row + 1, self.table.rowCount(), 1
        elif direction == 'up':
            start_row, end_row, step = current_row - 1, -1, -1
        else:
            return False

        # Chercher la prochaine cellule vide ou pleine selon le contexte
        current_item = self.table.item(current_row, current_col)
        current_is_empty = not current_item or not current_item.text().strip()

        for row in range(start_row, end_row, step):
            item = self.table.item(row, current_col)
            is_empty = not item or not item.text().strip()

            # Si on est sur une case vide, aller à la première case pleine
            # Si on est sur une case pleine, aller à la première case vide
            if current_is_empty and not is_empty:
                self.table.setCurrentCell(row, current_col)
                return True
            elif not current_is_empty and is_empty:
                self.table.setCurrentCell(row, current_col)
                return True

        return False
            