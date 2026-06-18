"""
AppareillsTableModel — QAbstractTableModel pour la migration QTableWidget → QTableView.

Structure d'un record : (db_id, type, manufacturer, ref_modele,
                          commercial_ref, other_ref, category, notes, pieces_count)

Usage :
    model = AppareillsTableModel()
    model.load_records(records)
    view.setModel(model)
"""

from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate

from src.core.config import Config


class AppareillsTableModel(QAbstractTableModel):
    """Modèle de données tabulaires pour les appareils.

    Remplace QTableWidget côté données. La vue (QTableView ou QTableWidget)
    est décorrelée du stockage.

    Signaux :
        cell_edited(row, col, old_value, new_value) — émis par setData(),
        remplace le signal itemChanged de QTableWidget.

    Virtual scrolling (USE_VIRTUAL_SCROLL) :
        _display_count : nombre de lignes actuellement exposées à la vue.
        rowCount() retourne _display_count (pas len(_records)).
        canFetchMore() / fetchMore() révèlent FETCH_CHUNK lignes supplémentaires
        quand l'utilisateur approche du bas de liste — sans requête DB.
    """

    # Signal custom — remplace itemChanged de QTableWidget
    cell_edited = pyqtSignal(int, int, str, str)  # row, col, old_value, new_value

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._records = []            # List[Tuple]: (db_id, col1..colN, pieces_count)
        self._display_count = 0       # Lignes actuellement visibles (virtual scroll)
        self._headers = Config.UI_HEADERS
        self._main_window = main_window
        self._search_term = None

    # ── API Qt obligatoire ───────────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self._display_count

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        if parent.isValid():
            return False
        if not Config.USE_VIRTUAL_SCROLL:
            return False
        return self._display_count < len(self._records)

    def fetchMore(self, parent=QModelIndex()):
        """Révèle FETCH_CHUNK lignes supplémentaires depuis _records (déjà en mémoire)."""
        if parent.isValid():
            return
        remaining = len(self._records) - self._display_count
        to_fetch = min(Config.FETCH_CHUNK, remaining)
        if to_fetch <= 0:
            return
        self.beginInsertRows(QModelIndex(), self._display_count, self._display_count + to_fetch - 1)
        self._display_count += to_fetch
        self.endInsertRows()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= self._display_count:
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
        if row >= self._display_count:
            return False
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
        if not index.isValid() or index.row() >= self._display_count:
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

        Avec USE_VIRTUAL_SCROLL, expose seulement FETCH_INITIAL lignes
        initialement ; fetchMore() révèle la suite au fur et à mesure.
        Sans virtual scroll, toutes les lignes sont exposées immédiatement.
        """
        self.beginResetModel()
        self._records = list(records)
        if Config.USE_VIRTUAL_SCROLL:
            self._display_count = min(Config.FETCH_INITIAL, len(self._records))
        else:
            self._display_count = len(self._records)
        self.endResetModel()

    def get_db_id(self, row: int):
        """Retourne le db_id de la ligne, ou None si hors limites.

        Remplace item(row, col).data(Qt.UserRole) dans les 20+ endroits du code.
        """
        return self._records[row][0] if 0 <= row < len(self._records) else None

    def update_record_db_id(self, row: int, db_id: int):
        """Met à jour le db_id (record[0]) d'une ligne existante.

        Utilisé après auto-création d'une ligne en DB pour propager l'ID
        généré vers le modèle. Émet dataChanged sur toute la ligne pour
        rafraîchir le UserRole dans la vue.
        """
        if not (0 <= row < len(self._records)):
            return
        record = list(self._records[row])
        record[0] = db_id
        self._records[row] = tuple(record)
        # Notifier la vue que le UserRole a changé sur toute la ligne
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, len(self._headers) - 1),
            [Qt.UserRole]
        )

    def update_pieces_count(self, row: int, count: int):
        """Met à jour pieces_count (record[-1]) sans émettre cell_edited.

        Utilisé exclusivement par PiecesCountService après association/suppression
        de pièce. N'est pas une édition utilisateur → pas de sauvegarde déclenchée.
        Si la ligne n'est pas encore visible (virtual scroll), met à jour _records
        silencieusement — elle affichera la bonne valeur quand elle deviendra visible.
        """
        if not (0 <= row < len(self._records)):
            return
        record = list(self._records[row])
        record[-1] = count
        self._records[row] = tuple(record)
        # Émettre dataChanged uniquement si la ligne est visible
        if row < self._display_count:
            idx = self.index(row, len(self._headers) - 1)
            self.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.BackgroundRole, Qt.ToolTipRole])

    def find_row_by_db_id(self, db_id: int):
        """Retourne l'index de ligne pour un db_id donné, ou None si absent."""
        for i, rec in enumerate(self._records):
            if rec[0] == db_id:
                return i
        return None

    def set_search_term(self, term):
        """Met à jour le terme de recherche pour le highlight (Phase 3+).

        Appelé depuis load_data() après chargement. Déclenche un refresh
        des BackgroundRole sur toutes les cellules.
        """
        self._search_term = term
        if self._display_count > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._display_count - 1, len(self._headers) - 1),
                [Qt.BackgroundRole]
            )


class PiecesCountDelegate(QStyledItemDelegate):
    """Peint un badge pill coloré dans la colonne Nb Pièces.

    - count > 0 → vert #27ae60
    - count == 0 → orange #e67e22
    Gère la sélection : fond highlight Qt quand la cellule est sélectionnée.
    """

    _COLOR_HAS_PIECES = QColor("#27ae60")
    _COLOR_NO_PIECES  = QColor("#e67e22")
    _COLOR_BG         = QColor(248, 248, 248)

    def paint(self, painter, option, index):
        painter.save()

        # Fond : couleur sélection ou gris très clair (même que BackgroundRole)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, self._COLOR_BG)

        # Valeur
        try:
            count = int(index.data(Qt.DisplayRole) or 0)
        except (ValueError, TypeError):
            count = 0

        badge_color = self._COLOR_HAS_PIECES if count > 0 else self._COLOR_NO_PIECES

        # Geometry du badge pill (centré dans la cellule)
        badge_w, badge_h = 34, 18
        cx = option.rect.center().x()
        cy = option.rect.center().y()
        badge_rect = QRectF(cx - badge_w / 2, cy - badge_h / 2, badge_w, badge_h)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(badge_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge_rect, 9, 9)

        # Texte blanc centré
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(badge_rect.toRect(), Qt.AlignCenter, str(count))

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(50, 26)
