"""
Mixin FTS5 Full-Text Search — extrait de DatabaseManager.

Ne pas instancier directement : ce mixin est conçu pour être hérité par
DatabaseManager uniquement.

Dépendances attendues sur self (fournies par DatabaseManager.__init__) :
    self.cursor  — curseur SQLite actif
    self.conn    — connexion SQLite active
"""

import sqlite3
import time

from ...core.config import Config
from ...core.logger import app_logger
from . import with_query_lock


class DatabaseFts5Mixin:
    """Méthodes FTS5 Full-Text Search pour DatabaseManager."""

    # ── FTS5 Full-Text Search ────────────────────────────────────────────────

    @staticmethod
    def fts5_utilisable() -> bool:
        """L'index FTS5 peut-il servir à une recherche ?

        Non si `SEARCH_PIECES_ONLY` : l'index couvre les colonnes d'appareils,
        or la recherche porte alors sur `pieces.ref_piece`. Source unique de
        cette règle — la condition de recherche s'en sert aussi.
        """
        return Config.USE_FTS5 and not Config.SEARCH_PIECES_ONLY

    def _synchroniser_infrastructure_fts5(self):
        """Aligner l'infrastructure FTS5 sur ce que la configuration permet.

        Appelé à l'ouverture de la base. Tant que l'index est inutilisable, le
        maintenir coûte cher pour rien : ~20 % du poids de la base, et des
        écritures ~6,7× plus lentes à cause des trois triggers, qui se
        déclenchent à chaque import. On le supprime donc plutôt que de le tenir
        à jour — « Construire l'index » du menu le recrée intégralement le jour
        où `SEARCH_PIECES_ONLY` repasse à False.
        """
        if self.fts5_utilisable():
            self._setup_fts5()
        else:
            self._supprimer_infrastructure_fts5()

    def _supprimer_infrastructure_fts5(self):
        """Retirer les triggers et la table d'index FTS5 s'ils existent."""
        try:
            existe = self.cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='appareils_fts'"
            ).fetchone()
            for trigger in ('appareils_fts_ai', 'appareils_fts_ad', 'appareils_fts_au'):
                self.cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            self.cursor.execute("DROP TABLE IF EXISTS appareils_fts")
            self.conn.commit()
            if existe:
                app_logger.info(
                    "FTS5 : index et triggers retirés (inutilisables tant que "
                    "SEARCH_PIECES_ONLY=True). L'espace disque se libère au prochain VACUUM."
                )
        except Exception as e:
            app_logger.warning(f"FTS5 : suppression de l'infrastructure impossible ({e})")

    def _setup_fts5(self):
        """Créer la table FTS5 et les triggers de synchronisation.

        Utilise le tokenizer `trigram` (SQLite ≥ 3.34) pour permettre la
        recherche par sous-chaîne, exactement comme LIKE '%terme%' mais indexée.

        La table est créée comme external content table (content='appareils') :
        FTS5 ne stocke que l'index, pas les données (gain mémoire).

        Phase A : crée la table et les triggers.
        Phase B : peuplera l'index existant via rebuild_fts5().
        """
        cols = ' '.join(f'[{h}],' for h in Config.DB_HEADERS).rstrip(',')

        # Table virtuelle FTS5
        self.cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS appareils_fts USING fts5(
                {cols},
                content='appareils',
                content_rowid='id',
                tokenize='trigram'
            )
        """)

        # Triggers pour maintenir l'index à jour automatiquement
        self._setup_fts5_triggers()

    def _setup_fts5_triggers(self):
        """Créer les triggers INSERT / UPDATE / DELETE sur appareils → appareils_fts."""
        col_names  = ', '.join(f'[{h}]' for h in Config.DB_HEADERS)
        new_values = ', '.join(f'new.[{h}]' for h in Config.DB_HEADERS)
        old_values = ', '.join(f'old.[{h}]' for h in Config.DB_HEADERS)

        try:
            # Trigger INSERT
            self.cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS appareils_fts_ai
                AFTER INSERT ON appareils BEGIN
                    INSERT INTO appareils_fts(rowid, {col_names})
                    VALUES (new.id, {new_values});
                END
            """)

            # Trigger DELETE
            self.cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS appareils_fts_ad
                AFTER DELETE ON appareils BEGIN
                    INSERT INTO appareils_fts(appareils_fts, rowid, {col_names})
                    VALUES ('delete', old.id, {old_values});
                END
            """)

            # Trigger UPDATE (delete old entry + insert new)
            self.cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS appareils_fts_au
                AFTER UPDATE ON appareils BEGIN
                    INSERT INTO appareils_fts(appareils_fts, rowid, {col_names})
                    VALUES ('delete', old.id, {old_values});
                    INSERT INTO appareils_fts(rowid, {col_names})
                    VALUES (new.id, {new_values});
                END
            """)
        except sqlite3.Error as e:
            app_logger.error(f"Erreur création triggers FTS5 — l'index ne sera pas maintenu automatiquement : {e}")
            raise

    @with_query_lock
    def rebuild_fts5(self, progress_callback=None) -> int:
        """Peupler (ou repeupler) l'index FTS5 depuis la table appareils.

        À appeler une seule fois après la création initiale, ou après une
        migration de données. Sur 523k enregistrements avec trigram, compter
        ~30-90 secondes selon le matériel.

        Args:
            progress_callback: callable(int) optionnel, reçoit le nombre de
                               lignes traitées toutes les 10k insertions.

        Returns:
            Nombre d'enregistrements indexés.
        """
        t0 = time.time()

        # L'infrastructure a pu être retirée (index inutilisable) : la recréer
        # avant de peupler, pour que « Construire l'index » reparte de zéro.
        self._setup_fts5()

        # Vider l'index existant via la commande spéciale FTS5
        # Note : DELETE FROM ne fonctionne pas sur une external content table —
        # FTS5 doit lire les anciennes valeurs depuis la source pour mettre à jour
        # l'index, ce qui échoue si l'index est vide ou partiel.
        self.cursor.execute("INSERT INTO appareils_fts(appareils_fts) VALUES('delete-all')")

        col_names   = ', '.join(f'[{h}]' for h in Config.DB_HEADERS)
        select_cols = ', '.join(f'[{h}]' for h in Config.DB_HEADERS)

        # Lire les données par blocs pour ne pas saturer la mémoire
        batch_size = 5000
        offset = 0
        total = 0

        while True:
            self.cursor.execute(
                f"SELECT id, {select_cols} FROM appareils LIMIT ? OFFSET ?",
                (batch_size, offset)
            )
            rows = self.cursor.fetchall()
            if not rows:
                break

            self.cursor.executemany(
                f"INSERT INTO appareils_fts(rowid, {col_names}) VALUES ({', '.join(['?'] * (len(Config.DB_HEADERS) + 1))})",
                rows
            )
            total += len(rows)
            offset += batch_size

            if progress_callback:
                progress_callback(total)

        self.conn.commit()
        elapsed = time.time() - t0
        app_logger.info(f"FTS5 rebuild : {total} enregistrements indexés en {elapsed:.1f}s")
        return total

    @with_query_lock
    def get_fts5_row_count(self) -> int:
        """Retourne le nombre de documents réellement indexés dans FTS5 (0 si non peuplé).

        Note : COUNT(*) sur un content table FTS5 lit la table source (appareils),
        pas l'index. La shadow table appareils_fts_docsize contient une entrée
        par document effectivement indexé — c'est le bon indicateur.
        """
        try:
            row = self.cursor.execute(
                "SELECT COUNT(*) FROM appareils_fts_docsize"
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def is_fts5_populated(self) -> bool:
        """Retourne True si l'index FTS5 contient des données."""
        return self.get_fts5_row_count() > 0

    @staticmethod
    def _escape_fts5(term: str) -> str:
        """Échappe un terme pour la syntaxe MATCH de FTS5.

        Entoure le terme de guillemets doubles (phrase FTS5) et échappe les
        guillemets internes. Avec le tokenizer trigram, cela force la recherche
        de la sous-chaîne exacte, équivalent à LIKE '%terme%'.
        """
        return '"' + term.replace('"', '""') + '"'

    def build_fts5_condition(self, search_term) -> dict:
        """Construit la condition SQL FTS5 équivalente à _build_search_condition_optimized.

        Supporte les mêmes types de recherche : simple, and (&&), or (||).
        Les recherches regex sont renvoyées sur le chemin LIKE classique.

        Returns:
            dict avec 'query_type'='fts5', 'condition', 'params'
            ou None si le terme est vide ou de type non supporté.
        """
        if not search_term:
            return None

        # Le tokenizer trigram requiert au moins 3 caractères par terme.
        # Si un terme est trop court, FTS5 ne trouvera rien → fallback LIKE.
        def _too_short(t: str) -> bool:
            return len(t.strip()) < 3

        fts_base = "a.id IN (SELECT rowid FROM appareils_fts WHERE appareils_fts MATCH ?)"

        if isinstance(search_term, str):
            term = search_term.strip()
            if not term:
                return None
            if _too_short(term):
                return None  # Fallback LIKE pour les termes courts (< 3 chars)
            return {
                'query_type': 'fts5',
                'condition': fts_base,
                'params': [self._escape_fts5(term)]
            }

        search_type = search_term.get('type', 'simple')

        if search_type == 'simple':
            terms = search_term.get('terms', [])
            if not terms:
                return None
            if _too_short(terms[0]):
                return None
            return {
                'query_type': 'fts5',
                'condition': fts_base,
                'params': [self._escape_fts5(terms[0])]
            }

        elif search_type == 'and':
            terms = search_term.get('terms', [])
            if not terms:
                return None
            if any(_too_short(t) for t in terms):
                return None  # Fallback si l'un des termes est trop court
            # FTS5 : espace entre phrases = ET implicite
            match_expr = ' '.join(self._escape_fts5(t) for t in terms)
            return {
                'query_type': 'fts5',
                'condition': fts_base,
                'params': [match_expr]
            }

        elif search_type == 'or':
            terms = search_term.get('terms', [])
            if not terms:
                return None
            if any(_too_short(t) for t in terms):
                return None  # Fallback si l'un des termes est trop court
            # FTS5 : OR explicite
            match_expr = ' OR '.join(self._escape_fts5(t) for t in terms)
            return {
                'query_type': 'fts5',
                'condition': fts_base,
                'params': [match_expr]
            }

        # Types non supportés (regex, groupes imbriqués) → fallback LIKE
        return None

    # ── Fin FTS5 ─────────────────────────────────────────────────────────────
