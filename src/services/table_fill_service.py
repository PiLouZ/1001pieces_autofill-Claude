"""
Service pour la gestion du remplissage et de l'affichage des données dans les tables.
Phase 5 de la migration QTableView : tout le remplissage passe par AppareillsTableModel.
"""

from typing import List

from src.core.config import Config


class TableFillService:
    """Service pour gérer le remplissage des tables via AppareillsTableModel."""

    def __init__(self, main_window):
        self.main_window = main_window

    def fill_table_chunked(self, table, records: List, progress_dialog, search_term):
        """Remplissage optimisé — délègue au modèle (une seule ligne remplace N setItem)."""
        tc = self.main_window.table_controller
        if tc.model is not None:
            tc.model.set_search_term(search_term)
            tc.model.load_records(records)

    def fill_table_standard(self, table, records: List, progress_dialog, search_term):
        """Remplissage standard — même chemin que fill_table_chunked via le modèle."""
        tc = self.main_window.table_controller
        if tc.model is not None:
            tc.model.set_search_term(search_term)
            tc.model.load_records(records)

    def get_db_id_from_row(self, table, row: int) -> int:
        """Récupérer le db_id de la ligne depuis AppareillsTableModel."""
        model = table.model() if hasattr(table, 'model') and callable(table.model) else None
        if model and hasattr(model, 'get_db_id'):
            db_id = model.get_db_id(row)
            if db_id is not None:
                return int(db_id)
        raise ValueError(f"Aucun db_id trouvé pour la ligne {row}")
