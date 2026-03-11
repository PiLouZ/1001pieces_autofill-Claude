"""
Service de gestion du comptage des pièces associées.
Centralise la logique de mise à jour des compteurs de pièces dans l'interface.
"""

from typing import Set, Optional, Dict

from ..data.database_manager import DatabaseManager
from ..core.logger import app_logger
from .base_service import BaseService


class PiecesCountService(BaseService):
    """Service dédié à la gestion du comptage et affichage des pièces associées.

    Travaille directement avec AppareillsTableModel — aucune dépendance à l'API
    QTableWidget. Une seule requête batch remplace les N+1 requêtes individuelles.
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager

    def update_pieces_count_for_rows(self, table, rows: Set[int]):
        """Mettre à jour la colonne Nb Pièces pour les lignes spécifiées (batch).

        1. Collecte les db_ids depuis le modèle.
        2. Une seule requête SQL pour tous les counts.
        3. Mise à jour directe du modèle via update_pieces_count().
        """
        if not rows or not table:
            return
        model = table.model()
        if not model:
            return

        # Collecter les db_ids valides pour les lignes demandées
        db_id_to_row: Dict[int, int] = {}
        for row in rows:
            db_id = model.get_db_id(row)
            if db_id is not None:
                db_id_to_row[db_id] = row

        if not db_id_to_row:
            return

        # Requête batch — une seule aller-retour DB pour toutes les lignes
        counts = self.db_manager.get_pieces_count_batch(list(db_id_to_row.keys()))

        # Mettre à jour le modèle directement (sans émettre cell_edited)
        updated = 0
        for db_id, row in db_id_to_row.items():
            count = counts.get(db_id, 0)
            model.update_pieces_count(row, count)
            updated += 1

        if updated > 0:
            app_logger.debug(f"{updated} compteurs Nb Pièces mis à jour")

    def refresh_entire_pieces_column(self, table):
        """Rafraîchir la colonne Nb Pièces pour toutes les lignes visibles."""
        if not table:
            return
        model = table.model()
        if not model or model.rowCount() == 0:
            return
        self.update_pieces_count_for_rows(table, set(range(model.rowCount())))

    def find_row_by_db_id(self, table, db_id: int) -> Optional[int]:
        """Trouver le numéro de ligne correspondant à un ID d'appareil."""
        if not table or db_id is None:
            return None
        model = table.model()
        if not model:
            return None
        return model.find_row_by_db_id(db_id)

    def get_pieces_count_summary(self, table) -> Dict[str, int]:
        """Obtenir un résumé du comptage des pièces dans le tableau."""
        if not table:
            return {"total_devices": 0, "devices_with_pieces": 0, "devices_without_pieces": 0}
        model = table.model()
        if not model:
            return {"total_devices": 0, "devices_with_pieces": 0, "devices_without_pieces": 0}

        total = model.rowCount()
        with_pieces = 0
        pieces_col = model.columnCount() - 1
        for row in range(total):
            val = model.data(model.index(row, pieces_col))
            if val and str(val).isdigit() and int(val) > 0:
                with_pieces += 1

        return {
            "total_devices": total,
            "devices_with_pieces": with_pieces,
            "devices_without_pieces": total - with_pieces,
        }
