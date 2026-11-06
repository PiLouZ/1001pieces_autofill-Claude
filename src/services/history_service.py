"""
Service de persistance de l'historique des modifications.

Reçoit les entrées structurées produites par user_interaction_service
et les écrit dans la table modifications_history (SQLite).

Fournit aussi l'API de lecture pour HistoryViewDialog.
"""

import json
import re
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

            # Pour un edit mono-champ, agg_key = (field, new_value) — strings
            # Pour un edit multi-champs, agg_key = tuple de tuples → ignorer
            agg_key = entry.get('agg_key')
            # Édition issue d'une suggestion : clé enveloppée (clé, ('__source__',))
            # par user_interaction_service, pour ne pas la regrouper avec une manuelle.
            if (agg_key and isinstance(agg_key, tuple) and len(agg_key) == 2
                    and agg_key[1] == ("__source__",)):
                agg_key = agg_key[0]
            if (agg_key and isinstance(agg_key, tuple) and len(agg_key) == 2
                    and isinstance(agg_key[0], str)):
                field_name, new_value = agg_key

            # Extraire old_value depuis la première ligne de details (multi-champs)
            if details_raw and isinstance(details_raw, list):
                first_detail = details_raw[0] if isinstance(details_raw[0], str) else ''
                # Format : "==> Champ : 'old' → 'new'"
                m = re.search(r"'(.*)'\s*→\s*'(.*)'", first_detail)
                if m:
                    old_value = m.group(1)
                    if new_value is None:
                        new_value = m.group(2)

            # Fallback : extraire old_value depuis le titre (mono-champ absorbe tout dans title)
            # Format titre : "[Field]  'old' → 'new'"
            if old_value is None and title:
                m = re.search(r"'(.*)'\s*→\s*'(.*)'", title)
                if m:
                    old_value = m.group(1)  # peut être '' si le champ était vide
                    if new_value is None:
                        new_value = m.group(2)

            self.db_manager.ajouter_historique_modification(
                timestamp_str, action_type, title, details_json,
                device_ref, field_name, old_value, new_value
            )

        except Exception as e:
            app_logger.warning(f"HistoryService.persist : échec silencieux — {e}")

    # ── Lecture ───────────────────────────────────────────────────────────────

    def get_recent_rows(self, limit: int = 2000) -> List[tuple]:
        """Dernières lignes persistées, de la plus récente à la plus ancienne.

        Sert à recharger le panneau Historique au lancement. La limite est large :
        les modifications regroupées (badge ×N) consomment plusieurs lignes pour
        une seule entrée affichée.

        Returns:
            Liste de tuples (timestamp, action_type, title, details,
                             device_ref, field_name, new_value)
        """
        if not self.db_manager:
            return []
        return self.db_manager.historique_recent(limit) or []

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

        return self.db_manager.historique_entrees(
            limit, offset, action_type, date_from, date_to, search) or []

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

        rows = self.db_manager.historique_total(action_type, date_from, date_to, search)
        return rows[0][0] if rows else 0

    def clear_history(self) -> bool:
        """Supprimer toutes les entrées d'historique persistant."""
        if not self.db_manager:
            return False
        try:
            # Commité (execute_write) : par execute_query, sans commit, la
            # suppression revenait au lancement suivant si rien d'autre n'écrivait.
            return self.db_manager.vider_historique() >= 0
        except Exception as e:
            app_logger.error(f"HistoryService.clear_history : {e}")
            return False
