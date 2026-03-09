"""
AppareillsTableModel — QAbstractTableModel pour la migration QTableWidget → QTableView.

Structure d'un record : (db_id, type, manufacturer, ref_modele,
                          commercial_ref, other_ref, category, notes, pieces_count)

Usage :
    model = AppareillsTableModel()
    model.load_records(records)
    view.setModel(model)
"""

from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt5.QtGui import QBrush, QColor

from src.core.config import Config


class AppareillsTableModel(QAbstractTableModel):
    """Modèle de données tabulaires pour les appareils.

    Remplace QTableWidget côté données. La vue (QTableView ou QTableWidget)
    est décorrelée du stockage.

    Signaux :
        cell_edited(row, col, old_value, new_value) — émis par setData(),
        remplace le signal itemChanged de QTableWidget.
    """

    # Signal custom — remplace itemChanged de QTableWidget
    cell_edited = pyqtSignal(int, int, str, str)  # row, col, old_value, new_value

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._records = []            # List[Tuple]: (db_id, col1..colN, pieces_count)
        self._headers = Config.UI_HEADERS
        self._main_window = main_window
        self._search_term = None

    # ── API Qt obligatoire ───────────────────────────────────────────────────

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
                # record[0] = db_id, donc les données commencent à record[1]
                return str(record[col + 1] or "")
            else:
                # Dernière colonne : Nb Pièces (record[-1] = pieces_count)
                return str(record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0)

        elif role == Qt.UserRole:
            # db_id — remplace item.data(Qt.UserRole) dans l'ensemble du code
            return record[0]

        elif role == Qt.BackgroundRole:
            if col == len(Config.DB_HEADERS):   # Nb Pièces
                pieces = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
                color = QColor(220, 248, 198) if pieces > 0 else QColor(248, 248, 248)
                return QBrush(color)
            # Highlight de recherche : délégué au service (Phase 3+)
            return None

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
        if index.column() == len(Config.DB_HEADERS):    # Nb Pièces — lecture seule
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._headers[section] if section < len(self._headers) else None
            else:
                return str(section + 1)   # 1-indexé comme l'ancien setVerticalHeaderItem
        return None

    # ── API custom ───────────────────────────────────────────────────────────

    def load_records(self, records: list):
        """Charge un lot d'enregistrements et réinitialise le modèle.

        Remplace setRowCount(n) + boucle setItem(). Une seule ligne d'appel.
        Émet modelReset pour forcer le rafraîchissement de la vue.
        """
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()

    def get_db_id(self, row: int):
        """Retourne le db_id de la ligne, ou None si hors limites.

        Remplace item(row, col).data(Qt.UserRole) dans les 20+ endroits du code.
        """
        return self._records[row][0] if 0 <= row < len(self._records) else None

    def get_record(self, row: int):
        """Retourne le tuple complet de la ligne, ou None si hors limites."""
        return self._records[row] if 0 <= row < len(self._records) else None

    def set_search_term(self, term):
        """Met à jour le terme de recherche pour le highlight (Phase 3+).

        Appelé depuis load_data() après chargement. Déclenche un refresh
        des BackgroundRole sur toutes les cellules.
        """
        self._search_term = term
        if self._records:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._records) - 1, len(self._headers) - 1),
                [Qt.BackgroundRole]
            )
