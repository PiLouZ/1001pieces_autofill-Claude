"""
Service de persistance de l'historique des modifications.

Reçoit les entrées structurées produites par user_interaction_service
et les écrit dans la table modifications_history (SQLite).

Fournit aussi l'API de lecture pour HistoryViewDialog.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base_service import BaseService
from ..core.logger import app_logger

# Types d'action non pertinents à conserver (bruit opérationnel)
_SKIP_ACTION_TYPES = {'system'}


class HistoryService(BaseService):
    """Persistance et consultation de l'historique des modifications."""

    def __init__(self, parent_window, parent=None):
        super().__init__(parent_window, parent)
        self.db_manager = getattr(parent_window, 'db_manager', None)

    # ── Écriture ─────────────────────────────────────────────────────────────

    def persist(self, entry: Dict[str, Any]) -> None:
        """Persister une entrée d'historique en base.

        Args:
            entry: dict produit par _parse_entry() dans user_interaction_service.
                   Champs attendus : timestamp, action_type, title, details,
                   devices, agg_key (optionnel).
        """
        if not self.db_manager:
            return

        action_type = entry.get('action_type', 'system')
        if action_type in _SKIP_ACTION_TYPES:
            return

        try:
            ts = entry['timestamp']
            timestamp_str = ts.strftime('%Y-%m-%d %H:%M:%S') if isinstance(ts, datetime) else str(ts)

            title = entry.get('title', '')
            details_raw = entry.get('details', [])
            details_json = json.dumps(details_raw, ensure_ascii=False) if details_raw else None

            # Extraire device_ref, field_name, old_value, new_value si disponibles
            device_ref = None
            field_name = None
            old_value = None
            new_value = None

            devices = entry.get('devices', [])
            if devices:
                device_ref = devices[0] if isinstance(devices[0], str) else None

            # Pour un edit mono-champ, agg_key = (field, new_value)
            agg_key = entry.get('agg_key')
            if agg_key and isinstance(agg_key, tuple) and len(agg_key) == 2:
                field_name, new_value = agg_key

            # Extraire old_value depuis la première ligne de details
            if details_raw and isinstance(details_raw, list) and details_raw:
                first_detail = details_raw[0] if isinstance(details_raw[0], str) else ''
                # Format : "==> Champ : 'old' → 'new'"
                import re
                m = re.search(r"'(.*)'\s*→\s*'(.*)'", first_detail)
                if m:
                    old_value = m.group(1)
                    if new_value is None:
                        new_value = m.group(2)

            self.db_manager.execute_insert(
                """
                INSERT INTO modifications_history
                    (timestamp, action_type, title, details,
                     device_ref, field_name, old_value, new_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [timestamp_str, action_type, title, details_json,
                 device_ref, field_name, old_value, new_value]
            )

        except Exception as e:
            app_logger.warning(f"HistoryService.persist : échec silencieux — {e}")

    # ── Lecture ───────────────────────────────────────────────────────────────

    def get_entries(
        self,
        limit: int = 200,
        offset: int = 0,
        action_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[tuple]:
        """Récupérer des entrées d'historique avec filtres optionnels.

        Returns:
            Liste de tuples (id, timestamp, action_type, title, details,
                             device_ref, field_name, old_value, new_value)
        """
        if not self.db_manager:
            return []

        conditions = []
        params: List[Any] = []

        if action_type and action_type != 'all':
            conditions.append("action_type = ?")
            params.append(action_type)

        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)

        if date_to:
            # Inclure toute la journée de fin
            conditions.append("timestamp <= ?")
            params.append(date_to + ' 23:59:59')

        if search and search.strip():
            s = f"%{search.strip()}%"
            conditions.append(
                "(title LIKE ? OR device_ref LIKE ? OR field_name LIKE ? "
                "OR old_value LIKE ? OR new_value LIKE ?)"
            )
            params.extend([s, s, s, s, s])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])

        return self.db_manager.execute_query(
            f"""
            SELECT id, timestamp, action_type, title, details,
                   device_ref, field_name, old_value, new_value
            FROM modifications_history
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            params
        ) or []

    def get_total_count(
        self,
        action_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Nombre total d'entrées pour la pagination."""
        if not self.db_manager:
            return 0

        conditions = []
        params: List[Any] = []

        if action_type and action_type != 'all':
            conditions.append("action_type = ?")
            params.append(action_type)
        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to + ' 23:59:59')
        if search and search.strip():
            s = f"%{search.strip()}%"
            conditions.append(
                "(title LIKE ? OR device_ref LIKE ? OR field_name LIKE ? "
                "OR old_value LIKE ? OR new_value LIKE ?)"
            )
            params.extend([s, s, s, s, s])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self.db_manager.execute_query(
            f"SELECT COUNT(*) FROM modifications_history {where}", params
        )
        return rows[0][0] if rows else 0

    def clear_history(self) -> bool:
        """Supprimer toutes les entrées d'historique persistant."""
        if not self.db_manager:
            return False
        try:
            self.db_manager.execute_query("DELETE FROM modifications_history")
            return True
        except Exception as e:
            app_logger.error(f"HistoryService.clear_history : {e}")
            return False
