"""
Service de navigation vers la prochaine/précédente cellule vide (Type ou Fabricant)

Une ligne dont Type OU Fabricant est vide compte, y compris si une suggestion
Type/Marque par similarité est en attente : ces suggestions ne sont jamais
calculées que pour des lignes déjà incomplètes (cf. reference_similarity_service),
la condition SQL sur type/manufacturer les couvre donc automatiquement.

Ordre de parcours : id croissant (direction='down') / décroissant ('up'), pour
rester déterministe quel que soit le tri ou le filtre visuel actif du tableau —
comportement volontairement indépendant de la vue courante, à l'image du bouton
« lignes à compléter » qui compte sur l'ensemble de la base.
"""

from typing import Optional, Tuple

from .base_service import BaseService
from ..data.database_manager import DatabaseManager

_NAVIGABLE_COLUMNS = ('type', 'manufacturer')


class EmptyCellNavigationService(BaseService):
    """Recherche indexée (SQL) de la prochaine ligne incomplète sur une colonne donnée."""

    def __init__(self, db_manager: DatabaseManager, parent_window=None, parent=None):
        super().__init__(parent_window, parent)
        self.db_manager = db_manager

    def find_next_empty(self, column_name: str, current_db_id: int,
                         direction: str = 'down') -> Optional[Tuple[int, str]]:
        """Retourne (db_id, ref_modele) de la prochaine ligne où column_name est
        vide, en parcourant les id depuis current_db_id. None si aucune trouvée
        ou si column_name/direction invalides."""
        if column_name not in _NAVIGABLE_COLUMNS or direction not in ('down', 'up'):
            return None

        op = '>' if direction == 'down' else '<'
        order = 'ASC' if direction == 'down' else 'DESC'
        query = f"""
            SELECT id, ref_modele FROM appareils
            WHERE ([{column_name}] IS NULL OR [{column_name}] = '')
              AND id {op} ?
            ORDER BY id {order}
            LIMIT 1
        """
        results = self.db_manager.execute_query(query, [current_db_id])
        if not results:
            return None
        return results[0][0], results[0][1]
