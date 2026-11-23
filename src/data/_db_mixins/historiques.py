"""
Historiques et décisions du nettoyage, mixés dans DatabaseManager.

Requêtes autrefois écrites dans HistoryService (table modifications_history)
et dans la fenêtre de nettoyage (cleanup_history, reference_decisions),
rassemblées dans la couche données (audit 2026-11-05 ; les deux INSERT
d'historique ont suivi le 2026-11-06, toujours via execute_insert).

Lectures et DDL : même méthode d'exécution que l'appel d'origine. Écritures :
execute_write, qui COMMIT — y compris pour vider l'historique des
modifications, qui passait par execute_query (sans commit) et revenait au
lancement suivant si rien d'autre n'écrivait entre-temps.
"""

from typing import Any, List, Optional, Tuple


class DatabaseHistoriquesMixin:
    """Historique des modifications, historique et décisions du nettoyage."""

    # ── Historique des modifications ─────────────────────────────────────────

    def historique_recent(self, limit: int) -> List[Tuple]:
        """Dernières lignes, de la plus récente à la plus ancienne : (timestamp,
        action_type, title, details, device_ref, field_name, new_value)."""
        return self.execute_query(
            """
            SELECT timestamp, action_type, title, details,
                   device_ref, field_name, new_value
            FROM modifications_history
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            [limit]
        )

    @staticmethod
    def _filtre_historique(action_type: Optional[str], date_from: Optional[str],
                           date_to: Optional[str], search: Optional[str]) -> Tuple[str, List[Any]]:
        """(clause WHERE, paramètres) des filtres de la fenêtre Historique —
        commune à la page affichée et au total (jadis recopiée dans les deux)."""
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
        return where, params

    def historique_entrees(self, limit: int, offset: int, action_type: Optional[str] = None,
                           date_from: Optional[str] = None, date_to: Optional[str] = None,
                           search: Optional[str] = None) -> List[Tuple]:
        """Page d'entrées filtrées : (id, timestamp, action_type, title, details,
        device_ref, field_name, old_value, new_value)."""
        where, params = self._filtre_historique(action_type, date_from, date_to, search)
        params.extend([limit, offset])
        return self.execute_query(
            f"""
            SELECT id, timestamp, action_type, title, details,
                   device_ref, field_name, old_value, new_value
            FROM modifications_history
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            params
        )

    def historique_total(self, action_type: Optional[str] = None, date_from: Optional[str] = None,
                         date_to: Optional[str] = None, search: Optional[str] = None) -> List[Tuple]:
        """[(nombre d'entrées correspondant aux filtres,)]."""
        where, params = self._filtre_historique(action_type, date_from, date_to, search)
        return self.execute_query(
            f"SELECT COUNT(*) FROM modifications_history {where}", params
        )

    def ajouter_historique_modification(self, timestamp: str, action_type: str, title: str,
                                        details: Optional[str], device_ref: Optional[str],
                                        field_name: Optional[str], old_value: Optional[str],
                                        new_value: Optional[str]) -> Optional[int]:
        """Écrire une entrée de l'historique des modifications (commité) ;
        id de la ligne. Lève DatabaseError en cas d'échec (execute_insert)."""
        return self.execute_insert(
            """
            INSERT INTO modifications_history
                (timestamp, action_type, title, details,
                 device_ref, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [timestamp, action_type, title, details,
             device_ref, field_name, old_value, new_value]
        )

    def ajouter_historique_modifications(self, lignes: List[Tuple]) -> bool:
        """Écrire plusieurs entrées de l'historique en une seule transaction
        (correction de type en lot : des milliers d'appareils). Chaque ligne :
        (timestamp, action_type, title, details, device_ref, field_name,
        old_value, new_value). True si tout est commité."""
        if not lignes:
            return True
        requete = """
            INSERT INTO modifications_history
                (timestamp, action_type, title, details,
                 device_ref, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        return self.execute_write_batch([(requete, list(l)) for l in lignes])

    def vider_historique(self) -> int:
        """Supprimer tout l'historique des modifications (commité) ; nombre de
        lignes supprimées, ou -1 en cas d'échec."""
        return self.execute_write("DELETE FROM modifications_history")

    # ── Nettoyage : références marquées distinctes ───────────────────────────

    def references_distinctes(self) -> List[Tuple]:
        """Références marquées DISTINCT avec leur nombre d'appareils :
        (ref_modele, nb_appareils, created_at, ref_key), les plus récentes en tête."""
        return self.execute_query("""
            SELECT rd.ref_modele,
                   COUNT(a.id) as nb_appareils,
                   rd.created_at,
                   rd.ref_modele as ref_key
            FROM reference_decisions rd
            LEFT JOIN appareils a ON a.ref_modele = rd.ref_modele
            WHERE rd.decision = 'DISTINCT'
            GROUP BY rd.ref_modele, rd.created_at
            ORDER BY rd.created_at DESC
        """)

    def retirer_references_distinctes(self, refs: List[str]) -> int:
        """Retirer des références de la liste des distinctes (commité) ; nombre
        de lignes supprimées, ou -1 en cas d'échec."""
        placeholders = ','.join(['?'] * len(refs))
        return self.execute_write(
            f"DELETE FROM reference_decisions WHERE ref_modele IN ({placeholders})", refs)

    # ── Nettoyage : historique des actions ───────────────────────────────────

    def creer_table_historique_nettoyage(self) -> None:
        """Créer la table cleanup_history si elle n'existe pas."""
        self.execute_custom_query("""
            CREATE TABLE IF NOT EXISTS cleanup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                details TEXT,
                result TEXT,
                user TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def ajouter_action_nettoyage(self, timestamp: str, action_type: str, details: str,
                                 result: str, user: str) -> Optional[int]:
        """Écrire une action du nettoyage (commité) ; id de la ligne. Lève
        DatabaseError en cas d'échec (execute_insert)."""
        return self.execute_insert("""
            INSERT INTO cleanup_history (timestamp, action_type, details, result, user)
            VALUES (?, ?, ?, ?, ?)
        """, (timestamp, action_type, details, result, user))

    def historique_nettoyage(self) -> List[Tuple]:
        """100 dernières actions du nettoyage : (timestamp, action_type, details,
        result, user)."""
        return self.execute_query("""
            SELECT timestamp, action_type, details, result, user
            FROM cleanup_history
            ORDER BY timestamp DESC
            LIMIT 100
        """)

    def vider_historique_nettoyage(self) -> int:
        """Vider l'historique du nettoyage (commité) ; nombre de lignes supprimées,
        ou -1 en cas d'échec."""
        return self.execute_write("DELETE FROM cleanup_history")
