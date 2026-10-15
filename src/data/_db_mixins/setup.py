"""
Mixin Setup & Migrations — extrait de DatabaseManager.

Ne pas instancier directement : ce mixin est conçu pour être hérité par
DatabaseManager uniquement.

Dépendances attendues sur self (fournies par DatabaseManager.__init__) :
    self.cursor  — curseur SQLite actif
    self.conn    — connexion SQLite active
    self.remove_duplicate_pieces()  — méthode CRUD (DatabaseManager)
"""

import sqlite3
import re

from ...core.config import Config
from ...core.logger import app_logger
from ...utils.error_handler import (
    handle_database_errors,
    handle_sqlite_column_errors,
)
from . import DatabaseError


class DatabaseSetupMixin:
    """Méthodes de configuration initiale et migrations pour DatabaseManager."""

    # ── Setup & Migrations ───────────────────────────────────────────────────

    @handle_database_errors(title="Erreur configuration base de données")
    def _setup_database(self):
        """Configuration et création des tables"""
        # Table appareils
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS appareils (
                id INTEGER PRIMARY KEY,
                type TEXT,
                manufacturer TEXT,
                ref_modele TEXT,
                commercial_ref TEXT,
                other_ref TEXT,
                category TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Ajouter les colonnes manquantes
        self._add_missing_columns()

        # Table pièces (structure finale — la migration la recrée si l'ancienne structure est détectée)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pieces (
                id INTEGER PRIMARY KEY,
                ref_piece TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table associations pièce-appareil (nouvelle structure)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS piece_associations (
                id INTEGER PRIMARY KEY,
                piece_id INTEGER NOT NULL,
                appareil_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(piece_id) REFERENCES pieces(id) ON DELETE CASCADE,
                FOREIGN KEY(appareil_id) REFERENCES appareils(id) ON DELETE CASCADE,
                UNIQUE(piece_id, appareil_id)
            )
        """)

        # Garder l'ancienne table pour migration
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pieces_old (
                id INTEGER PRIMARY KEY,
                ref_piece TEXT NOT NULL,
                appareil_id INTEGER,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(appareil_id) REFERENCES appareils(id) ON DELETE CASCADE,
                UNIQUE(appareil_id, ref_piece)
            )
        """)

        # Table catégories
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table des décisions sur les doublons de références
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS reference_decisions (
                ref_modele TEXT PRIMARY KEY,
                decision TEXT CHECK(decision IN ('DISTINCT', 'MERGE')) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """)

        # Ajouter les colonnes manquantes pour la table pieces
        self._add_missing_pieces_columns()

        # Ajouter la contrainte unique pour prévenir les doublons
        self._add_unique_constraint_pieces()

        # Index pour les performances
        self._create_indexes()

        # Migration des données vers la nouvelle structure
        self._migrate_pieces_to_new_structure()

        # Table d'historique des modifications (persistance inter-sessions)
        self._setup_modifications_history_table()

        # Infrastructure FTS5 : créée seulement si l'index est utilisable,
        # retirée sinon (population via rebuild_fts5())
        self._synchroniser_infrastructure_fts5()

        # Table de supersession des références pièces
        self._setup_supersession_table()

        # Table d'équivalence des références pièces
        self._setup_equivalence_table()

        self.conn.commit()

    @handle_database_errors(title="Erreur ajout colonnes")
    def _add_missing_columns(self):
        """Ajouter les colonnes manquantes à la table appareils"""
        self.cursor.execute("PRAGMA table_info(appareils)")
        existing_columns = {row[1] for row in self.cursor.fetchall()}

        for header in Config.DB_HEADERS + ['created_at', 'updated_at']:
            if header not in existing_columns:
                self._add_column_to_appareils(header)

    @handle_database_errors(title="Erreur ajout colonnes pièces")
    def _add_missing_pieces_columns(self):
        """Ajouter les colonnes manquantes à la table pieces"""
        # Vérifier si la table pieces existe
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pieces'")
        if not self.cursor.fetchone():
            return

        self.cursor.execute("PRAGMA table_info(pieces)")
        existing_columns = {row[1] for row in self.cursor.fetchall()}

        # Si la table n'a pas de colonne 'appareil_id', elle a déjà la nouvelle structure
        if 'appareil_id' not in existing_columns:
            return

        # Ajouter la colonne description si elle n'existe pas
        if 'description' not in existing_columns:
            self._add_column_to_pieces('description')

        # Ajouter la colonne created_at si elle n'existe pas
        if 'created_at' not in existing_columns:
            self._add_column_to_pieces('created_at')

        # Forcer un commit immédiat
        self.conn.commit()

    @handle_sqlite_column_errors(log_message="Erreur ajout colonne pieces")
    def _add_column_to_pieces(self, column_name: str) -> bool:
        """Ajouter une colonne à la table pieces avec gestion d'erreur factorisée.
        column_name doit être un identifiant SQL valide (lettres, chiffres, _)."""
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_ ]*$', column_name):
            raise ValueError(f"Nom de colonne invalide : '{column_name}'")
        self.cursor.execute(f"ALTER TABLE pieces ADD COLUMN {column_name} TEXT")
        app_logger.info(f"Colonne '{column_name}' ajoutée à la table pieces")
        return True

    @handle_sqlite_column_errors(log_message="Erreur ajout colonne appareils")
    def _add_column_to_appareils(self, column_name: str) -> bool:
        """Ajouter une colonne à la table appareils avec gestion d'erreur factorisée.
        column_name doit être un identifiant SQL valide (lettres, chiffres, _, espaces)."""
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_ ]*$', column_name):
            raise ValueError(f"Nom de colonne invalide : '{column_name}'")
        self.cursor.execute(f"ALTER TABLE appareils ADD COLUMN [{column_name}] TEXT")
        app_logger.info(f"Colonne '{column_name}' ajoutée à la table appareils")
        return True

    def _add_unique_constraint_pieces(self):
        """Ajouter la contrainte unique pour prévenir les doublons de pièces"""
        try:
            # Vérifier si la table pieces a déjà la nouvelle structure
            self.cursor.execute("PRAGMA table_info(pieces)")
            pieces_columns = [row[1] for row in self.cursor.fetchall()]

            if 'appareil_id' not in pieces_columns:
                # Nouvelle structure déjà en place, skip
                return

            # Ancienne structure - vérifier si la contrainte unique existe déjà
            self.cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='pieces'")
            table_sql = self.cursor.fetchone()

            if table_sql and 'UNIQUE(appareil_id, ref_piece)' not in table_sql[0]:
                # Nettoyer les doublons existants avant d'ajouter la contrainte
                self.remove_duplicate_pieces()

                # Recréer la table avec la contrainte unique
                self.cursor.execute("BEGIN TRANSACTION")

                # Créer une table temporaire avec la contrainte
                self.cursor.execute("""
                    CREATE TABLE pieces_temp (
                        id INTEGER PRIMARY KEY,
                        ref_piece TEXT NOT NULL,
                        appareil_id INTEGER,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(appareil_id) REFERENCES appareils(id) ON DELETE CASCADE,
                        UNIQUE(appareil_id, ref_piece)
                    )
                """)

                # Copier les données (sans doublons)
                self.cursor.execute("""
                    INSERT INTO pieces_temp (id, ref_piece, appareil_id, description, created_at)
                    SELECT id, ref_piece, appareil_id, description, created_at
                    FROM pieces
                    WHERE id IN (
                        SELECT MIN(id)
                        FROM pieces
                        GROUP BY appareil_id, ref_piece
                    )
                """)

                # Supprimer l'ancienne table et renommer la nouvelle
                self.cursor.execute("DROP TABLE pieces")
                self.cursor.execute("ALTER TABLE pieces_temp RENAME TO pieces")

                self.cursor.execute("COMMIT")
                app_logger.info("Contrainte unique ajoutée à la table pieces")

        except sqlite3.Error as e:
            self.cursor.execute("ROLLBACK")
            app_logger.error("Erreur", e)

    def _create_indexes(self):
        """Créer les index pour optimiser les performances"""
        indexes = [
            # Index simples appareils
            "CREATE INDEX IF NOT EXISTS idx_appareils_type ON appareils(type)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_manufacturer ON appareils(manufacturer)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_ref_modele ON appareils(ref_modele)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_commercial_ref ON appareils(commercial_ref)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_other_ref ON appareils(other_ref)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_category ON appareils(category)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_id_desc ON appareils(id DESC)",
            # Index composites appareils (exports et filtres multi-colonnes)
            "CREATE INDEX IF NOT EXISTS idx_appareils_search_composite ON appareils (ref_modele, commercial_ref, other_ref)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_type_manufacturer ON appareils (type, manufacturer)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_search_performance ON appareils(type, manufacturer, ref_modele)",
            # Index pièces
            "CREATE INDEX IF NOT EXISTS idx_pieces_ref ON pieces(ref_piece)",
            "CREATE INDEX IF NOT EXISTS idx_pieces_ref_description ON pieces (ref_piece, description)",
            # Index piece_associations — idx_piece_assoc_reverse est critique pour les sous-requêtes de recherche
            "CREATE INDEX IF NOT EXISTS idx_piece_associations_piece ON piece_associations(piece_id)",
            "CREATE INDEX IF NOT EXISTS idx_piece_associations_appareil ON piece_associations(appareil_id)",
            "CREATE INDEX IF NOT EXISTS idx_piece_assoc_composite ON piece_associations (appareil_id, piece_id)",
            "CREATE INDEX IF NOT EXISTS idx_piece_assoc_reverse ON piece_associations (piece_id, appareil_id)",
            "CREATE INDEX IF NOT EXISTS idx_piece_assoc_performance ON piece_associations(appareil_id, piece_id)",
        ]

        for index_query in indexes:
            try:
                self.cursor.execute(index_query)
            except sqlite3.OperationalError as e:
                # Ignorer les erreurs de table non-existante (base en mémoire ou migration)
                if "no such table" in str(e):
                    continue
                else:
                    raise DatabaseError(f"Erreur lors de la création des index: {e}")
            except sqlite3.Error as e:
                raise DatabaseError(f"Erreur lors de la création des index: {e}")

    def _migrate_pieces_to_new_structure(self):
        """Migrer les données de l'ancienne structure vers la nouvelle structure normalisée"""
        try:
            # Vérifier si la migration a déjà été effectuée
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pieces'")
            pieces_exists = self.cursor.fetchone()

            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='piece_associations'")
            assoc_exists = self.cursor.fetchone()

            if not pieces_exists or not assoc_exists:
                app_logger.debug("Tables de migration manquantes, skip")
                return

            # Vérifier la structure de la table pieces actuelle
            self.cursor.execute("PRAGMA table_info(pieces)")
            pieces_columns = [row[1] for row in self.cursor.fetchall()]

            # Si la table pieces n'a pas de colonne 'appareil_id', la migration a déjà été effectuée
            if 'appareil_id' not in pieces_columns:
                return

            # Vérifier si les nouvelles tables sont vides
            self.cursor.execute("SELECT COUNT(*) FROM pieces")
            old_pieces_count = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM piece_associations")
            assoc_count = self.cursor.fetchone()[0]

            if old_pieces_count == 0:
                app_logger.debug("Pas de données à migrer")
                return

            if assoc_count > 0:
                return

            app_logger.info(" Début de la migration des pièces vers la nouvelle structure...")

            # Étape 1: Sauvegarder les anciennes données
            app_logger.info(" Sauvegarde des anciennes données...")

            # Adapter la requête selon les colonnes disponibles
            if 'description' in pieces_columns:
                if 'created_at' in pieces_columns:
                    # Table complète avec description et created_at
                    self.cursor.execute("INSERT INTO pieces_old (id, ref_piece, appareil_id, description, created_at) SELECT id, ref_piece, appareil_id, description, created_at FROM pieces")
                else:
                    # Table avec description mais sans created_at
                    self.cursor.execute("INSERT INTO pieces_old (id, ref_piece, appareil_id, description) SELECT id, ref_piece, appareil_id, description FROM pieces")
            else:
                # Table simple sans description
                self.cursor.execute("INSERT INTO pieces_old (id, ref_piece, appareil_id) SELECT id, ref_piece, appareil_id FROM pieces")

            # Étape 2: Créer les nouvelles pièces uniques
            app_logger.info(" Création des pièces uniques...")
            pieces_data = {}

            # Récupérer toutes les pièces avec leurs données
            if 'description' in pieces_columns and 'created_at' in pieces_columns:
                self.cursor.execute("SELECT ref_piece, description, created_at FROM pieces")
                for ref_piece, description, created_at in self.cursor.fetchall():
                    if ref_piece not in pieces_data:
                        pieces_data[ref_piece] = {'description': description, 'created_at': created_at}
                    elif description and not pieces_data[ref_piece]['description']:
                        pieces_data[ref_piece]['description'] = description
            elif 'description' in pieces_columns:
                self.cursor.execute("SELECT ref_piece, description FROM pieces")
                for ref_piece, description in self.cursor.fetchall():
                    if ref_piece not in pieces_data:
                        pieces_data[ref_piece] = {'description': description, 'created_at': None}
                    elif description and not pieces_data[ref_piece]['description']:
                        pieces_data[ref_piece]['description'] = description
            else:
                self.cursor.execute(Config.get_query('distinct_ref_pieces'))
                for (ref_piece,) in self.cursor.fetchall():
                    pieces_data[ref_piece] = {'description': None, 'created_at': None}

            # Étape 3: Recréer la table pieces avec la nouvelle structure
            print(" Recréation de la table pieces...")
            self.cursor.execute("DROP TABLE pieces")
            self.cursor.execute("""
                CREATE TABLE pieces (
                    id INTEGER PRIMARY KEY,
                    ref_piece TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Insérer les pièces uniques dans la nouvelle table
            for ref_piece, data in pieces_data.items():
                if data['created_at']:
                    self.cursor.execute("INSERT INTO pieces (ref_piece, description, created_at) VALUES (?, ?, ?)",
                                       (ref_piece, data['description'], data['created_at']))
                else:
                    self.cursor.execute("INSERT INTO pieces (ref_piece, description) VALUES (?, ?)",
                                       (ref_piece, data['description']))

            app_logger.info(f" {len(pieces_data)} pièces uniques créées")

            # Étape 4: Créer les associations dans piece_associations
            app_logger.info(" Création des associations...")
            self.cursor.execute("""
                INSERT INTO piece_associations (piece_id, appareil_id, created_at)
                SELECT
                    p_new.id as piece_id,
                    p_old.appareil_id,
                    COALESCE(p_old.created_at, CURRENT_TIMESTAMP) as created_at
                FROM pieces_old p_old
                JOIN pieces p_new ON p_old.ref_piece = p_new.ref_piece
                WHERE p_old.appareil_id IS NOT NULL
            """)

            associations_migrated = self.cursor.rowcount
            app_logger.info(f" {associations_migrated} associations migrées")

            app_logger.info("[OK] Migration terminée avec succès")

        except sqlite3.Error as e:
            # En cas d'erreur, essayer de restaurer
            try:
                self.cursor.execute("DROP TABLE IF EXISTS piece_associations")
                self.cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise DatabaseError(f"Erreur lors de la migration des pièces: {e}")

    def _setup_modifications_history_table(self):
        """Créer la table d'historique persistant des modifications utilisateur."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS modifications_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                action_type TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                details     TEXT,
                device_ref  TEXT,
                field_name  TEXT,
                old_value   TEXT,
                new_value   TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Index pour les requêtes de consultation (filtre par type, tri par date)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mh_timestamp
            ON modifications_history(timestamp DESC)
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mh_action_type
            ON modifications_history(action_type)
        """)

    # ── Fin Setup & Migrations ───────────────────────────────────────────────
