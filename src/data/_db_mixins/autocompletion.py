"""
Mixin Traçabilité des auto-complétions — v3.89.0.

Ne pas instancier directement : ce mixin est conçu pour être hérité par
DatabaseManager uniquement.

Un Type ou un Fabricant écrit par l'auto-complétion d'un import (et non lu dans le
fichier) laisse une ligne dans `appareils_autocompletes` : la valeur écrite,
l'appareil qui l'a fournie, la part d'appareils sources d'accord (« 1/2 ») et
l'horodatage de l'import. La fenêtre « Auto-complétés à vérifier » les relit.

La ligne disparaît d'elle-même, par déclencheur SQL, quand le champ change
(saisie, suggestion, Cmd+D, fusion…) ou quand l'appareil est supprimé : aucun
chemin d'écriture de l'application n'a besoin de s'en soucier. Une simple
réécriture de casse (« DELTA » → « Delta ») ne compte pas comme une vérification.

Refus (v3.94.0) : `refus_completions` mémorise ce que l'utilisateur a écarté pour
un appareil — une paire Type/Marque suggérée (champ 'paire', valeur « type|marque »)
ou un champ auto-complété qu'il a fait vider (champ 'type' ou 'manufacturer').
Les suggestions refusées ne sont plus proposées, et l'import ne réécrit plus une
auto-complétion refusée sur un appareil existant.

Dépendances attendues sur self (fournies par DatabaseManager.__init__) :
    self.cursor, self.conn, self._query_lock
"""

from . import with_query_lock
from ...core.logger import app_logger


class DatabaseAutocompletionMixin:
    """Trace des Type/Fabricant auto-complétés à l'import, en attente de vérification."""

    _CHAMPS_TRACES = ('type', 'manufacturer')

    def _setup_autocompletion_trace_table(self):
        """Créer la table de trace et ses déclencheurs (idempotent)."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS appareils_autocompletes (
                    appareil_id  INTEGER NOT NULL,
                    champ        TEXT    NOT NULL,
                    valeur       TEXT    NOT NULL,
                    source       TEXT,
                    accord       INTEGER,
                    total        INTEGER,
                    import_ts    TEXT    NOT NULL,
                    PRIMARY KEY (appareil_id, champ)
                )
            """)
            for champ in self._CHAMPS_TRACES:
                # lower() : un alignement de casse n'est pas une vérification
                self.cursor.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS trg_autocompletes_{champ}_modifie
                    AFTER UPDATE OF {champ} ON appareils
                    WHEN lower(COALESCE(NEW.{champ}, '')) <> lower(COALESCE(OLD.{champ}, ''))
                    BEGIN
                        DELETE FROM appareils_autocompletes
                        WHERE appareil_id = NEW.id AND champ = '{champ}';
                    END
                """)
            # Déclencheur plutôt que clé étrangère : vaut aussi si Config.FOREIGN_KEYS = False
            self.cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_autocompletes_appareil_supprime
                AFTER DELETE ON appareils
                BEGIN
                    DELETE FROM appareils_autocompletes WHERE appareil_id = OLD.id;
                END
            """)
        except Exception as e:
            app_logger.error(f"Erreur création table appareils_autocompletes: {e}")

    def _setup_refus_completions_table(self):
        """Créer la table des refus et son déclencheur de suppression (idempotent)."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS refus_completions (
                    appareil_id  INTEGER NOT NULL,
                    champ        TEXT    NOT NULL,
                    valeur       TEXT    NOT NULL,
                    refuse_le    TEXT    NOT NULL,
                    PRIMARY KEY (appareil_id, champ, valeur)
                )
            """)
            self.cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_refus_appareil_supprime
                AFTER DELETE ON appareils
                BEGIN
                    DELETE FROM refus_completions WHERE appareil_id = OLD.id;
                END
            """)
        except Exception as e:
            app_logger.error(f"Erreur création table refus_completions: {e}")

    @with_query_lock
    def enregistrer_refus(self, lignes) -> int:
        """Mémoriser des refus.

        Args:
            lignes: (appareil_id, champ, valeur). La valeur est rangée en minuscules :
                un refus ne dépend pas de la casse.
        Returns:
            Nombre de refus enregistrés (0 en cas d'échec, journalisé).
        """
        from datetime import datetime
        horodatage = datetime.now().isoformat(sep=' ', timespec='seconds')
        lignes = [(a, c, (v or '').strip().lower(), horodatage) for a, c, v in lignes
                  if (v or '').strip()]
        if not lignes:
            return 0
        try:
            self.cursor.executemany(
                "INSERT OR REPLACE INTO refus_completions "
                "(appareil_id, champ, valeur, refuse_le) VALUES (?, ?, ?, ?)", lignes)
            self.conn.commit()
            return len(lignes)
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Enregistrement des refus échoué : {e}")
            return 0

    @with_query_lock
    def lire_refus(self, appareil_ids):
        """Refus des appareils donnés.

        Returns:
            Ensemble de (appareil_id, champ, valeur en minuscules), ou None si la
            lecture a échoué (l'appelant ne filtre alors rien).
        """
        ids = list(dict.fromkeys(appareil_ids))
        refus = set()
        try:
            for debut in range(0, len(ids), 900):
                lot = ids[debut:debut + 900]
                self.cursor.execute(
                    "SELECT appareil_id, champ, valeur FROM refus_completions "
                    f"WHERE appareil_id IN ({','.join('?' * len(lot))})", lot)
                refus.update(tuple(r) for r in self.cursor.fetchall())
            return refus
        except Exception as e:
            app_logger.error(f"Lecture des refus échouée : {e}")
            return None

    @with_query_lock
    def enregistrer_autocompletions(self, lignes) -> int:
        """Tracer des champs auto-complétés.

        Args:
            lignes: (appareil_id, champ, valeur, source, accord, total, import_ts).
                À appeler APRÈS l'écriture du champ : le déclencheur effacerait sinon
                la trace qu'on vient de poser.
        Returns:
            Nombre de lignes enregistrées (0 en cas d'échec, journalisé).
        """
        lignes = list(lignes)
        if not lignes:
            return 0
        try:
            self.cursor.executemany(
                "INSERT OR REPLACE INTO appareils_autocompletes "
                "(appareil_id, champ, valeur, source, accord, total, import_ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", lignes)
            self.conn.commit()
            return len(lignes)
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Trace des auto-complétions échouée (non bloquant) : {e}")
            return 0

    @with_query_lock
    def compter_autocompletions_a_verifier(self) -> int:
        """Nombre d'appareils portant au moins un champ auto-complété non vérifié."""
        try:
            self.cursor.execute(
                "SELECT COUNT(DISTINCT appareil_id) FROM appareils_autocompletes")
            return self.cursor.fetchone()[0] or 0
        except Exception as e:
            app_logger.error(f"Comptage des auto-complétions échoué : {e}")
            return 0

    @with_query_lock
    def lire_autocompletions_a_verifier(self):
        """Traces jointes à l'état actuel de l'appareil.

        Returns:
            Liste de (appareil_id, ref_modele, commercial_ref, type, manufacturer,
            champ, valeur, source, accord, total, import_ts), ou None si la lecture
            a échoué.
        """
        try:
            self.cursor.execute("""
                SELECT t.appareil_id, a.ref_modele, a.commercial_ref, a.type,
                       a.manufacturer, t.champ, t.valeur, t.source, t.accord,
                       t.total, t.import_ts
                FROM appareils_autocompletes t
                JOIN appareils a ON a.id = t.appareil_id
                ORDER BY t.appareil_id, t.champ
            """)
            return [tuple(r) for r in self.cursor.fetchall()]
        except Exception as e:
            app_logger.error(f"Lecture des auto-complétions échouée : {e}")
            return None

    @with_query_lock
    def marquer_autocompletions_verifiees(self, appareil_ids) -> int:
        """Retirer les traces des appareils vérifiés. Returns: lignes retirées."""
        ids = list(dict.fromkeys(appareil_ids))
        if not ids:
            return 0
        retirees = 0
        try:
            for debut in range(0, len(ids), 900):
                lot = ids[debut:debut + 900]
                self.cursor.execute(
                    "DELETE FROM appareils_autocompletes WHERE appareil_id IN "
                    f"({','.join('?' * len(lot))})", lot)
                retirees += self.cursor.rowcount
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Marquage des auto-complétions vérifiées échoué : {e}")
            return 0
        return retirees
