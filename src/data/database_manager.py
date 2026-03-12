"""
Gestionnaire de base de données pour l'application de gestion d'appareils
"""

import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from collections import OrderedDict
import hashlib
import time

from ..core.config import Config
from ..core.logger import app_logger
from ..utils.error_handler import (
    handle_db_query_errors, handle_db_signal_errors,
    handle_sqlite_column_errors, handle_database_errors,
    handle_database_operation_errors
)

try:
    from ..ui.qt_imports import QThread, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    # Classes de substitution pour les tests sans PyQt5
    class QThread:
        def __init__(self):
            pass
    class pyqtSignal:
        def __init__(self, *args):
            pass

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config

class DatabaseError(Exception):
    """Exception personnalisée pour les erreurs de base de données"""
    pass

class SearchCache:
    """Cache optimisé pour les recherches - Phase 3"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.hits = 0
        self.misses = 0
    
    def _make_key(self, search_term: str, column_filters: Dict, sort_info: Tuple) -> str:
        """Créer une clé unique pour la recherche"""
        key_data = {
            'search': search_term,
            'filters': column_filters,
            'sort': sort_info
        }
        return hashlib.md5(str(key_data).encode()).hexdigest()
    
    def get(self, search_term: str, column_filters: Dict = None, sort_info: Tuple = None) -> Optional[List]:
        """Récupérer du cache"""
        key = self._make_key(search_term, column_filters or {}, sort_info or ())
        
        if key in self.cache:
            # Déplacer vers la fin (plus récent)
            result = self.cache.pop(key)
            self.cache[key] = result
            self.hits += 1
            return result
        
        self.misses += 1
        return None
    
    def put(self, search_term: str, results: List, column_filters: Dict = None, sort_info: Tuple = None):
        """Mettre en cache"""
        key = self._make_key(search_term, column_filters or {}, sort_info or ())
        
        # Limiter la taille du cache
        if len(self.cache) >= self.max_size:
            # Supprimer le plus ancien
            self.cache.popitem(last=False)
        
        self.cache[key] = results
    
    def clear(self):
        """Vider le cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def get_stats(self) -> Dict[str, int]:
        """Statistiques du cache"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(hit_rate, 1),
            'size': len(self.cache)
        }

class DatabaseWorker(QThread):
    """Worker thread pour les opérations de base de données asynchrones"""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, db_file: str, query: str, params: Optional[List] = None):
        super().__init__()
        self.db_file = db_file
        self.query = query
        self.params = params or []
    
    @handle_db_signal_errors(error_signal_name="error_occurred")
    def run(self):
        """Exécuter la requête de base de données"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(self.query, self.params)
            records = cursor.fetchall()
            self.data_loaded.emit(records)
        finally:
            # SÉCURITÉ: Garantir fermeture connexion même si exception
            if conn:
                try:
                    conn.close()
                except:
                    # Bare except légitime: cleanup ne doit pas masquer erreur principale
                    pass

class DatabaseManager:
    """Gestionnaire centralisé pour toutes les opérations de base de données"""

    def __init__(self, db_file: str = None):
        import threading
        self.db_file = db_file or Config.DB_FILE
        self.conn = None
        self.cursor = None
        # Verrou pour serialiser les requêtes load_data() entre threads
        # (prefetch_worker + thread principal partagent la même connexion SQLite)
        self._query_lock = threading.Lock()
        # Phase 3: Initialiser le cache de recherche optimisé
        self.search_cache = SearchCache(Config.SEARCH_CACHE_SIZE) if Config.FULLTEXT_CACHE_ENABLED else None
        # Cache du COUNT total (sans filtre) — invalide uniquement sur insert/delete
        self._total_count_cache: Optional[int] = None
        # Phase 2.3: Initialiser le service d'invalidation de cache (import local pour éviter cycle)
        from ..services.search_cache_service import SearchCacheInvalidationService
        self.cache_invalidation = SearchCacheInvalidationService(self)
        self._connect()
        self._setup_database()
    
    @handle_database_errors(title="Erreur de connexion")
    def _connect(self):
        """Établir la connexion à la base de données"""
        # check_same_thread=False : autorise l'usage depuis plusieurs threads.
        # La sécurité est assurée par _query_lock dans load_data() (accès sérialisé).
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
    
    def get_connection(self):
        """Retourner la connexion pour les opérations batch"""
        return self.conn
    
    def _build_search_condition(self, search_term):
        """Construire une condition de recherche basée sur le terme de recherche (simple ou avancé)"""
        import re
        
        # Phase 3: Utiliser la nouvelle logique optimisée
        return self._build_search_condition_optimized(search_term)
    
    def _build_search_condition_optimized(self, search_term):
        """Phase 3: Condition de recherche optimisée selon le type de requête.

        Si Config.USE_FTS5=True et que l'index est peuplé, délègue à
        build_fts5_condition(). Fallback automatique sur LIKE si le type de
        recherche n'est pas supporté par FTS5 (regex, groupes imbriqués).
        """
        # Branche FTS5 — activée uniquement si USE_FTS5=True ET SEARCH_PIECES_ONLY=False.
        # L'index FTS5 couvre les colonnes d'appareils uniquement ; quand on recherche
        # dans pieces.ref_piece, FTS5 n'est pas applicable → fallback LIKE pièces.
        if Config.USE_FTS5 and not Config.SEARCH_PIECES_ONLY:
            fts_condition = self.build_fts5_condition(search_term)
            if fts_condition is not None:
                return fts_condition
            # Fallback silencieux sur LIKE pour les types non supportés

        # Si c'est une chaîne simple (ancienne API), traiter comme recherche simple
        if isinstance(search_term, str):
            if not search_term.strip():
                return None

            term = search_term.strip()

            # Phase 5: Recherche uniquement dans les pièces associées
            if Config.SEARCH_PIECES_ONLY:
                return {
                    'query_type': 'pieces_only',
                    'condition': "a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))",
                    'params': [f"%{term}%"]
                }

            # DÉSACTIVÉ TEMPORAIREMENT: Recherches optimisées à cause de problèmes de paramètres
            # Utiliser toujours la recherche LIKE classique pour garantir la stabilité

            # Recherche LIKE classique (plus lente)
            search_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
            search_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))")
            return {
                'query_type': 'like',
                'condition': f"({' OR '.join(search_conditions)})",
                'params': [f"%{search_term}%"] * (len(Config.DB_HEADERS) + 1)
            }
        
        # Si c'est None, pas de recherche
        if not search_term:
            return None
        
        # Recherche avancée
        search_type = search_term.get('type', 'simple')
        
        if search_type == 'simple':
            # Recherche simple avec un seul terme
            terms = search_term.get('terms', [])
            if not terms:
                return None

            term = terms[0]

            # Phase 5: Recherche uniquement dans les pièces associées
            if Config.SEARCH_PIECES_ONLY:
                return {
                    'query_type': 'pieces_only',
                    'condition': "a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))",
                    'params': [f"%{term}%"]
                }

            search_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
            search_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))")
            return {
                'condition': f"({' OR '.join(search_conditions)})",
                'params': [f"%{term}%"] * (len(Config.DB_HEADERS) + 1)
            }
        
        elif search_type == 'and':
            # Recherche avec opérateur AND (&&) - tous les termes doivent être trouvés
            terms = search_term.get('terms', [])
            if not terms:
                return None

            # Phase 5: Recherche uniquement dans les pièces associées
            if Config.SEARCH_PIECES_ONLY:
                pieces_conditions = [
                    "a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))"
                    for _ in terms
                ]
                return {
                    'query_type': 'pieces_only',
                    'condition': f"({' AND '.join(pieces_conditions)})",
                    'params': [f"%{t}%" for t in terms]
                }

            and_conditions = []
            all_params = []

            for term in terms:
                # Chaque terme doit être trouvé dans au moins une colonne
                term_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
                term_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))")

                and_conditions.append(f"({' OR '.join(term_conditions)})")
                all_params.extend([f"%{term}%"] * (len(Config.DB_HEADERS) + 1))

            if and_conditions:
                return {
                    'condition': f"({' AND '.join(and_conditions)})",
                    'params': all_params
                }

        elif search_type == 'or':
            # Recherche avec groupes OR
            groups = search_term.get('groups', [])
            if not groups:
                return None

            # Phase 5: Recherche uniquement dans les pièces associées
            if Config.SEARCH_PIECES_ONLY:
                group_conditions = []
                all_params = []
                for group in groups:
                    g_terms = group.get('terms', [])
                    if not g_terms:
                        continue
                    if group['type'] == 'and':
                        and_conds = [
                            "a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))"
                            for _ in g_terms
                        ]
                        group_conditions.append(f"({' AND '.join(and_conds)})")
                        all_params.extend([f"%{t}%" for t in g_terms])
                    else:  # simple
                        group_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))")
                        all_params.append(f"%{g_terms[0]}%")
                if group_conditions:
                    return {
                        'query_type': 'pieces_only',
                        'condition': f"({' OR '.join(group_conditions)})",
                        'params': all_params
                    }
                return None

            group_conditions = []
            all_params = []

            for group in groups:
                if group['type'] == 'and':
                    # Groupe AND : tous les termes doivent être présents
                    terms = group.get('terms', [])
                    if not terms:
                        continue

                    and_conditions = []
                    for term in terms:
                        # Chaque terme doit être trouvé dans au moins une colonne
                        term_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
                        term_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))")

                        and_conditions.append(f"({' OR '.join(term_conditions)})")
                        all_params.extend([f"%{term}%"] * (len(Config.DB_HEADERS) + 1))

                    if and_conditions:
                        group_conditions.append(f"({' AND '.join(and_conditions)})")

                elif group['type'] == 'simple':
                    # Groupe simple : terme unique à rechercher dans toutes les colonnes
                    terms = group.get('terms', [])
                    if not terms:
                        continue

                    term = terms[0]  # Premier terme du groupe simple
                    # Chercher le terme dans toutes les colonnes
                    term_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
                    term_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))")

                    group_conditions.append(f"({' OR '.join(term_conditions)})")
                    all_params.extend([f"%{term}%"] * (len(Config.DB_HEADERS) + 1))

            if group_conditions:
                return {
                    'condition': f"({' OR '.join(group_conditions)})",
                    'params': all_params
                }

        return None
    
    def _parse_search_term_for_export(self, search_term):
        """Parser un terme de recherche pour l'export - reproduit la logique de _parse_advanced_search"""
        # Si c'est déjà un objet parsé, le retourner tel quel
        if isinstance(search_term, dict):
            return search_term
        
        # Si c'est une chaîne vide, la retourner telle quelle
        if not search_term or not search_term.strip():
            return search_term
        
        # Si pas d'opérateurs, retourner tel quel pour traitement simple
        if '||' not in search_term and '&&' not in search_term:
            return search_term
        
        # Parser les opérateurs logiques
        # Diviser d'abord par || (OU)
        or_groups = search_term.split('||')
        
        parsed_groups = []
        for group in or_groups:
            group = group.strip()
            if not group:
                continue
                
            # Diviser chaque groupe par && (ET)
            and_terms = [term.strip() for term in group.split('&&') if term.strip()]
            if and_terms:
                parsed_groups.append({
                    'type': 'and',
                    'terms': and_terms
                })
        
        if not parsed_groups:
            # Pas d'opérateurs trouvés, recherche simple
            return {
                'type': 'simple',
                'terms': [search_term.strip()]
            }
        
        return {
            'type': 'or',
            'groups': parsed_groups
        }
    
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

        # Table pièces (sera créée/recréée par la migration)

        # Table associations pièce-appareil (nouvelle structure)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS piece_associations (
                id INTEGER PRIMARY KEY,
                piece_id INTEGER NOT NULL,
                appareil_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(piece_id) REFERENCES pieces_new(id) ON DELETE CASCADE,
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

        # Infrastructure FTS5 (table + triggers) — population via rebuild_fts5()
        self._setup_fts5()

        # Table de supersession des références pièces
        self._setup_supersession_table()

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
            # print("Table pieces n'existe pas, skip ajout colonnes")
            return

        self.cursor.execute("PRAGMA table_info(pieces)")
        existing_columns = {row[1] for row in self.cursor.fetchall()}

        # Si la table n'a pas de colonne 'appareil_id', elle a déjà la nouvelle structure
        if 'appareil_id' not in existing_columns:
            # print("Table pieces déjà avec nouvelle structure, skip ajout colonnes")
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
        """Ajouter une colonne à la table pieces avec gestion d'erreur factorисée"""
        self.cursor.execute(f"ALTER TABLE pieces ADD COLUMN {column_name} TEXT")
        app_logger.info(f"Colonne '{column_name}' ajoutée à la table pieces")
        return True

    @handle_sqlite_column_errors(log_message="Erreur ajout colonne appareils")
    def _add_column_to_appareils(self, column_name: str) -> bool:
        """Ajouter une colonne à la table appareils avec gestion d'erreur factorисée"""
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
                # print("Table pieces déjà avec nouvelle structure, skip contrainte unique")
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
    
    # ── Supersession des références pièces ──────────────────────────────────

    def _setup_supersession_table(self):
        """Créer la table piece_supersessions si elle n'existe pas."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS piece_supersessions (
                    ref_old  TEXT NOT NULL,
                    ref_new  TEXT,
                    PRIMARY KEY (ref_old),
                    FOREIGN KEY (ref_old) REFERENCES pieces(ref_piece) ON DELETE CASCADE,
                    FOREIGN KEY (ref_new) REFERENCES pieces(ref_piece) ON DELETE SET NULL
                )
            """)
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_supersessions_old ON piece_supersessions(ref_old)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_supersessions_new ON piece_supersessions(ref_new)"
            )
        except Exception as e:
            app_logger.error(f"Erreur création table piece_supersessions: {e}")

    def get_piece_status(self, ref_piece: str) -> dict:
        """
        Retourner le statut de succession d'une référence pièce.

        Returns:
            dict avec les clés :
              - 'status' : 'current' | 'superseded' | 'obsolete'
              - 'ref_new' : ref de remplacement (str ou None)
        """
        try:
            row = self.execute_query(
                "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?",
                [ref_piece]
            )
            if not row:
                return {'status': 'current', 'ref_new': None}
            ref_new = row[0][0]
            if ref_new is None:
                return {'status': 'obsolete', 'ref_new': None}
            return {'status': 'superseded', 'ref_new': ref_new}
        except Exception as e:
            app_logger.error(f"Erreur get_piece_status({ref_piece}): {e}")
            return {'status': 'current', 'ref_new': None}

    def get_pieces_statuses_batch(self, refs: list) -> dict:
        """
        Retourner les statuts de succession pour une liste de références en une seule requête.

        Returns:
            dict {ref_piece: {'status': 'current'|'superseded'|'obsolete', 'ref_new': str|None}}
            Les refs absentes de piece_supersessions ont le statut 'current'.
        """
        if not refs:
            return {}
        try:
            placeholders = ",".join("?" * len(refs))
            rows = self.execute_query(
                f"SELECT ref_old, ref_new FROM piece_supersessions WHERE ref_old IN ({placeholders})",
                refs
            )
            result = {ref: {'status': 'current', 'ref_new': None} for ref in refs}
            for ref_old, ref_new in rows:
                if ref_new is None:
                    result[ref_old] = {'status': 'obsolete', 'ref_new': None}
                else:
                    result[ref_old] = {'status': 'superseded', 'ref_new': ref_new}
            return result
        except Exception as e:
            app_logger.error(f"Erreur get_pieces_statuses_batch: {e}")
            return {ref: {'status': 'current', 'ref_new': None} for ref in refs}

    def resolve_current_ref(self, ref_piece: str, max_depth: int = 20) -> str:
        """
        Remonter la chaîne de succession jusqu'à la référence courante.
        Protégé contre les cycles via max_depth.

        Returns:
            La ref courante (dernière de la chaîne), ou ref_piece si déjà courante.
        """
        try:
            query = """
                WITH RECURSIVE chain(ref, depth) AS (
                    SELECT ?, 0
                    UNION ALL
                    SELECT ps.ref_new, chain.depth + 1
                    FROM chain
                    JOIN piece_supersessions ps ON ps.ref_old = chain.ref
                    WHERE ps.ref_new IS NOT NULL AND chain.depth < ?
                )
                SELECT ref FROM chain ORDER BY depth DESC LIMIT 1
            """
            rows = self.execute_query(query, [ref_piece, max_depth])
            return rows[0][0] if rows else ref_piece
        except Exception as e:
            app_logger.error(f"Erreur resolve_current_ref({ref_piece}): {e}")
            return ref_piece

    def get_supersession_chain(self, ref_piece: str, max_depth: int = 20) -> list:
        """
        Retourner la chaîne complète depuis la ref donnée jusqu'à la ref courante.

        Returns:
            Liste ordonnée [ref_piece, ..., ref_courante].
            Contient uniquement ref_piece si elle est déjà courante.
        """
        try:
            query = """
                WITH RECURSIVE chain(ref, depth) AS (
                    SELECT ?, 0
                    UNION ALL
                    SELECT ps.ref_new, chain.depth + 1
                    FROM chain
                    JOIN piece_supersessions ps ON ps.ref_old = chain.ref
                    WHERE ps.ref_new IS NOT NULL AND chain.depth < ?
                )
                SELECT ref FROM chain ORDER BY depth ASC
            """
            rows = self.execute_query(query, [ref_piece, max_depth])
            return [r[0] for r in rows] if rows else [ref_piece]
        except Exception as e:
            app_logger.error(f"Erreur get_supersession_chain({ref_piece}): {e}")
            return [ref_piece]

    def _has_supersession_cycle(self, ref_old: str, ref_new: str) -> bool:
        """Vérifier si ajouter ref_old → ref_new créerait un cycle."""
        try:
            current = ref_new
            visited = {ref_old}
            for _ in range(30):
                if current in visited:
                    return True
                visited.add(current)
                rows = self.execute_query(
                    "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?",
                    [current]
                )
                if not rows or rows[0][0] is None:
                    return False
                current = rows[0][0]
            return True  # chaîne trop longue, considérée comme cycle
        except Exception as e:
            app_logger.error(f"Erreur détection cycle supersession: {e}")
            return False

    def add_supersession(self, ref_old: str, ref_new) -> tuple:
        """
        Ajouter ou mettre à jour une entrée de supersession.

        Args:
            ref_old : référence remplacée (ou obsolète)
            ref_new : nouvelle référence, ou None pour marquer obsolète

        Returns:
            (success: bool, error_message: str)
        """
        try:
            if ref_old == ref_new:
                return False, "Une référence ne peut pas se remplacer elle-même."
            if ref_new is not None and self._has_supersession_cycle(ref_old, ref_new):
                return False, f"Cette opération créerait un cycle de succession ({ref_old} → ... → {ref_old})."
            with self._query_lock:
                self.cursor.execute(
                    "INSERT OR REPLACE INTO piece_supersessions(ref_old, ref_new) VALUES (?, ?)",
                    [ref_old, ref_new]
                )
                self.conn.commit()
            return True, ""
        except Exception as e:
            app_logger.error(f"Erreur add_supersession({ref_old} → {ref_new}): {e}")
            return False, str(e)

    def remove_supersession(self, ref_old: str) -> bool:
        """Supprimer la relation de supersession pour ref_old."""
        try:
            with self._query_lock:
                self.cursor.execute(
                    "DELETE FROM piece_supersessions WHERE ref_old = ?",
                    [ref_old]
                )
                self.conn.commit()
            return True
        except Exception as e:
            app_logger.error(f"Erreur remove_supersession({ref_old}): {e}")
            return False

    # ── FTS5 Full-Text Search ────────────────────────────────────────────────

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
        import time
        t0 = time.time()

        # Vider l'index existant via la commande spéciale FTS5
        # Note : DELETE FROM ne fonctionne pas sur une external content table —
        # FTS5 doit lire les anciennes valeurs depuis la source pour mettre à jour
        # l'index, ce qui échoue si l'index est vide ou partiel.
        self.cursor.execute("INSERT INTO appareils_fts(appareils_fts) VALUES('delete-all')")

        col_names  = ', '.join(f'[{h}]' for h in Config.DB_HEADERS)
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
            
            app_logger.info("🔄 Début de la migration des pièces vers la nouvelle structure...")
            
            # Étape 1: Sauvegarder les anciennes données
            app_logger.info("📋 Sauvegarde des anciennes données...")
            
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
            app_logger.info("📦 Création des pièces uniques...")
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
            print("🔄 Recréation de la table pieces...")
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
            
            app_logger.info(f"📦 {len(pieces_data)} pièces uniques créées")
            
            # Étape 4: Créer les associations dans piece_associations
            app_logger.info("🔗 Création des associations...")
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
            app_logger.info(f"🔗 {associations_migrated} associations migrées")
            
            app_logger.info("✅ Migration terminée avec succès")
            
        except sqlite3.Error as e:
                        # En cas d'erreur, essayer de restaurer
            try:
                self.cursor.execute("DROP TABLE IF EXISTS piece_associations")
                self.cursor.execute("ROLLBACK")
            except:
                pass
            raise DatabaseError(f"Erreur lors de la migration des pièces: {e}")
    
    @handle_db_query_errors(return_value=[], log_prefix="Erreur load_data")
    def load_data(self, search_term: Optional[str] = None,
                  column_filters: Optional[Dict[int, str]] = None,
                  limit: Optional[int] = None,
                  offset: Optional[int] = None,
                  sort_column: Optional[int] = None,
                  sort_order: Optional[str] = None,
                  incomplete_filter: bool = False) -> List[Tuple]:
        """Charger les données avec cache LRU optionnel (SMART_CACHE_ENABLED).

        Le cache est actif uniquement pour les requêtes sans filtres complexes
        (column_filters, incomplete_filter). Il est invalidé après chaque écriture
        via invalidate_search_cache().
        """
        with self._query_lock:
            use_cache = (
                Config.SMART_CACHE_ENABLED
                and self.search_cache is not None
                and self._should_use_cache(search_term, column_filters, incomplete_filter, limit)
            )

            if use_cache:
                cache_key = self._make_load_cache_key(
                    search_term, column_filters, limit, offset,
                    sort_column, sort_order, incomplete_filter
                )
                if cache_key in self.search_cache.cache:
                    self.search_cache.cache.move_to_end(cache_key)
                    self.search_cache.hits += 1
                    return list(self.search_cache.cache[cache_key])

            result = self._load_data_original(
                search_term, column_filters, limit, offset,
                sort_column, sort_order, incomplete_filter
            )

            if use_cache:
                if len(self.search_cache.cache) >= self.search_cache.max_size:
                    self.search_cache.cache.popitem(last=False)
                self.search_cache.cache[cache_key] = result
                self.search_cache.misses += 1

            return result

    def _make_load_cache_key(self, search_term, column_filters, limit, offset,
                             sort_column, sort_order, incomplete_filter) -> str:
        """Clé de cache unique pour load_data — hash MD5 de tous les paramètres."""
        import hashlib
        key = (
            str(search_term),
            str(sorted(column_filters.items()) if column_filters else []),
            limit, offset, sort_column, sort_order, incomplete_filter
        )
        return hashlib.md5(str(key).encode()).hexdigest()

    def invalidate_search_cache(self, invalidate_total_count: bool = False):
        """Vider le cache de recherche après toute modification de données.

        À appeler systématiquement après chaque écriture (update, insert, delete)
        pour garantir que load_data ne retourne jamais de données périmées.

        invalidate_total_count=True : réinitialise aussi _total_count_cache.
        À passer uniquement lors d'un insert ou d'un delete (pas d'un update).
        """
        if self.search_cache:
            self.search_cache.clear()
        if invalidate_total_count:
            self._total_count_cache = None

    def _should_use_cache(self, search_term: Optional[str], column_filters: Optional[Dict],
                         incomplete_filter: bool, limit: Optional[int]) -> bool:
        """Phase 3: Logique intelligente d'utilisation du cache

        Cache activé si :
        - Cache search disponible
        - Recherche simple (pas de filters complexes)
        - Résultats attendus <= 5000 (éviter surcharge mémoire)
        - Pas de filter incomplet (trop spécialisé)
        """
        if not self.search_cache:
            return False

        # Pas de cache pour filters complexes
        if column_filters or incomplete_filter:
            return False

        # Cache pour recherches avec terme (peu importe la limite)
        if search_term and limit and limit <= 5000:
            return True

        # Cache pour recherches simples sans terme si petite pagination
        if not search_term and limit and limit <= 5000:
            return True

        # Pas de cache pour gros volumes ou sans limite
        return False

    def _load_data_original(self, search_term: Optional[str] = None, 
                          column_filters: Optional[Dict[int, str]] = None, 
                          limit: Optional[int] = None,
                          offset: Optional[int] = None,
                          sort_column: Optional[int] = None,
                          sort_order: Optional[str] = None,
                          incomplete_filter: bool = False) -> List[Tuple]:
        """Méthode originale de chargement des données (fallback)"""
        try:
            # Construction de la requête avec comptage des pièces.
            # Sous-requête corrélée au lieu du LEFT JOIN matérialisé :
            # l'ancienne version faisait GROUP BY sur 1,86M lignes de piece_associations
            # même pour 3 résultats. La corrélée n'exécute le COUNT que pour les
            # lignes effectivement retournées, via l'index idx_piece_associations_appareil.
            headers_str = ', '.join(f'a.[{h}]' for h in Config.DB_HEADERS)
            query = f"""
                SELECT a.id, {headers_str},
                       (SELECT COUNT(*) FROM piece_associations pa
                        INNER JOIN pieces p ON pa.piece_id = p.id
                        WHERE pa.appareil_id = a.id) as pieces_count
                FROM appareils a
            """
            params = []
            conditions = []
            
            # Recherche globale pour load_data (avec support recherche avancée)
            if search_term:
                search_condition = self._build_search_condition_optimized(search_term)
                if search_condition:
                    # Phase 3: Gérer les requêtes optimisées (éviter erreur "near SELECT")
                    if search_condition.get('query_type') in ['exact', 'prefix']:
                        # Pour les requêtes optimisées, extraire juste la condition WHERE
                        if search_condition['query_type'] == 'exact':
                            condition = "(a.ref_modele = ? OR a.commercial_ref = ? OR a.other_ref = ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece = ?))"
                        else:  # prefix
                            condition = "(a.ref_modele LIKE ? OR a.commercial_ref LIKE ? OR a.other_ref LIKE ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))"
                        
                        conditions.append(condition)
                        params.extend(search_condition['params'])
                    else:
                        # Condition WHERE classique
                        conditions.append(search_condition['condition'])
                        params.extend(search_condition['params'])
            
            # Filtres par colonne pour load_data
            if column_filters:
                for col_idx, filter_text in column_filters.items():
                    if col_idx < len(Config.DB_HEADERS) and filter_text.strip():
                        conditions.append(f"a.[{Config.DB_HEADERS[col_idx]}] LIKE ?")
                        params.append(f"%{filter_text}%")
            
            # Filtre pour les lignes incomplètes (champs type OU manufacturer vides) pour load_data
            if incomplete_filter:
                incomplete_condition = "(a.[type] IS NULL OR a.[type] = '' OR a.[manufacturer] IS NULL OR a.[manufacturer] = '')"
                conditions.append(incomplete_condition)
            
            # Ajouter les conditions
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            # Gérer le tri
            if sort_column is not None and 0 <= sort_column < len(Config.DB_HEADERS):
                sort_field = Config.DB_HEADERS[sort_column]
                order = "ASC" if sort_order == "ASC" else "DESC"
                query += f" ORDER BY a.[{sort_field}] {order}"
            elif sort_column is not None and sort_column == len(Config.DB_HEADERS):
                # Tri par nombre de pièces (dernière colonne)
                order = "ASC" if sort_order == "ASC" else "DESC"
                query += f" ORDER BY pieces_count {order}"
            else:
                query += " ORDER BY a.id DESC"  # Tri par défaut
            
            # Ajouter LIMIT et OFFSET pour la pagination
            if limit:
                query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
            
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors du chargement des données: {e}")
    
    @handle_database_errors(title="Erreur comptage données")
    def count_data(self, search_term: Optional[str] = None,
                   column_filters: Optional[Dict[int, str]] = None,
                   sort_column: Optional[int] = None,
                   sort_order: Optional[str] = None,
                   incomplete_filter: bool = False) -> int:
        """Compter le nombre total de lignes correspondant aux critères"""
        with self._query_lock:
            return self._count_data_core(search_term, column_filters, incomplete_filter)

    def _count_data_core(self, search_term: Optional[str] = None,
                         column_filters: Optional[Dict[int, str]] = None,
                         incomplete_filter: bool = False) -> int:
        """Logique interne du comptage — appelée sous _query_lock.

        Cas sans filtre : retourne _total_count_cache (calculé une seule fois,
        invalidé sur insert/delete). Évite un scan complet de 598k lignes à
        chaque effacement du champ de recherche (~70ms → 0ms).
        """
        # Court-circuit : sans filtre, le total ne change qu'à l'insert/delete
        if not search_term and not column_filters and not incomplete_filter:
            if self._total_count_cache is not None:
                return self._total_count_cache
            result = self.cursor.execute("SELECT COUNT(*) FROM appareils").fetchone()[0]
            self._total_count_cache = result
            return result

        # COUNT simple sur appareils — le LEFT JOIN sur piece_associations
        # était inutile ici (pieces_count n'est pas utilisé dans un COUNT(*))
        # et forçait la matérialisation de 1,86M lignes pour rien.
        query = "SELECT COUNT(*) FROM appareils a"
        params = []
        conditions = []

        # Recherche globale pour count_data (avec support recherche avancée)
        if search_term:
            search_condition = self._build_search_condition_optimized(search_term)
            if search_condition:
                # Si c'est une recherche regex, on ne peut pas compter précisément avec SQLite
                if 'regex_filter' in search_condition:
                    # Pour les regex, retourner un count approximatif (total)
                    return self.cursor.execute("SELECT COUNT(*) FROM appareils").fetchone()[0]

                # Phase 3: Gérer les requêtes optimisées (SELECT complets)
                elif search_condition.get('query_type') in ['exact', 'prefix']:
                    # Pour les requêtes optimisées, extraire juste la condition WHERE
                    if search_condition['query_type'] == 'exact':
                        condition = "(ref_modele = ? OR commercial_ref = ? OR other_ref = ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece = ?))"
                    else:  # prefix
                        condition = "(ref_modele LIKE ? OR commercial_ref LIKE ? OR other_ref LIKE ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))"

                    conditions.append(condition)
                    params.extend(search_condition['params'])
                else:
                    # Condition WHERE classique
                    conditions.append(search_condition['condition'])
                    params.extend(search_condition['params'])

        # Filtres par colonne pour count_data
        if column_filters:
            for col_idx, filter_text in column_filters.items():
                if col_idx < len(Config.DB_HEADERS) and filter_text.strip():
                    conditions.append(f"a.[{Config.DB_HEADERS[col_idx]}] LIKE ?")
                    params.append(f"%{filter_text}%")

        # Filtre pour les lignes incomplètes pour count_data
        if incomplete_filter:
            incomplete_condition = "(a.[type] IS NULL OR a.[type] = '' OR a.[manufacturer] IS NULL OR a.[manufacturer] = '')"
            conditions.append(incomplete_condition)

        # Ajouter les conditions
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Note: Le tri n'affecte pas le comptage, donc on ignore sort_column et sort_order
        self.cursor.execute(query, params)
        return self.cursor.fetchone()[0]
    
    @handle_db_query_errors(return_value=0, log_prefix="Erreur comptage appareils incomplets")
    def count_incomplete_devices(self) -> int:
        """Compter le nombre d'appareils où colonne A et/ou B est vide"""
        query = """
        SELECT COUNT(*) FROM appareils a
        WHERE (a.type IS NULL OR a.type = '') OR (a.manufacturer IS NULL OR a.manufacturer = '')
        """
        self.cursor.execute(query)
        return self.cursor.fetchone()[0]
    
    def update_cell(self, db_id: int, column: str, value: str) -> bool:
        """Mettre à jour une cellule spécifique"""
        result = self._safe_update_cell(db_id, column, value)
        if not result:
            raise DatabaseError(f"Erreur lors de la mise à jour de la cellule {column}")
        return result

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur mise à jour cellule")
    def _safe_update_cell(self, db_id: int, column: str, value: str) -> bool:
        """Helper sécurisé pour mettre à jour une cellule spécifique"""
        query = f"""
            UPDATE appareils
            SET [{column}] = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        self.cursor.execute(query, (value, db_id))
        self.conn.commit()
        self.invalidate_search_cache()

        # Phase 2.3: Invalider le cache après mise à jour d'appareil
        if hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_device_modification("modification", 1)

        return True
    
    def update_multiple_cells_batch(self, updates_by_db_id: Dict[int, Dict[str, str]]) -> bool:
        """Mettre à jour plusieurs cellules en une seule transaction optimisée"""
        result = self._safe_update_multiple_cells_batch(updates_by_db_id)
        if not result:
            raise DatabaseError("Erreur lors de la mise à jour par lots")
        return result

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur mise à jour par lots")
    def _safe_update_multiple_cells_batch(self, updates_by_db_id: Dict[int, Dict[str, str]]) -> bool:
        """Helper sécurisé pour mettre à jour plusieurs cellules en une seule transaction"""
        # Vérifier s'il y a déjà une transaction active pour éviter les transactions imbriquées
        in_transaction = self.conn.in_transaction if hasattr(self.conn, 'in_transaction') else False

        try:
            # Commencer une transaction uniquement si pas déjà en cours
            if not in_transaction:
                self.cursor.execute("BEGIN TRANSACTION")

            for db_id, column_updates in updates_by_db_id.items():
                if column_updates:  # Vérifier qu'il y a des mises à jour
                    # Construire la requête UPDATE avec toutes les colonnes pour cette ligne
                    set_clauses = []
                    values = []

                    for column, value in column_updates.items():
                        set_clauses.append(f"[{column}] = ?")
                        values.append(value)

                    # Ajouter la mise à jour du timestamp
                    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                    values.append(db_id)  # Pour la clause WHERE

                    query = f"UPDATE appareils SET {', '.join(set_clauses)} WHERE id = ?"
                    self.cursor.execute(query, values)

            # Valider la transaction seulement si on l'a commencée
            if not in_transaction:
                self.conn.commit()
            self.invalidate_search_cache()

            # Phase 2.3: Invalider le cache après mise à jour multiple
            if hasattr(self, 'cache_invalidation'):
                self.cache_invalidation.invalidate_after_device_modification("modification", len(updates_by_db_id))

            return True

        except Exception as e:
            # Annuler la transaction en cas d'erreur (seulement si on l'a commencée)
            if not in_transaction:
                self.conn.rollback()
            raise
    
    def insert_appareil(self, data: Dict[str, Any]) -> int:
        """Insérer un nouvel appareil"""
        result = self._safe_insert_appareil(data)
        if result == 0:
            raise DatabaseError("Erreur lors de l'insertion de l'appareil")
        return result

    @handle_database_operation_errors(return_value=0, log_prefix="Erreur insertion appareil")
    def _safe_insert_appareil(self, data: Dict[str, Any]) -> int:
        """Helper sécurisé pour insérer un nouvel appareil"""
        # Préparer les données
        columns = []
        values = []
        placeholders = []

        for header in Config.DB_HEADERS:
            if header in data:
                columns.append(f'[{header}]')
                values.append(data[header])
                placeholders.append('?')

        if not columns:
            raise DatabaseError("Aucune donnée fournie pour l'insertion")

        query = f"""
            INSERT INTO appareils ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
        """

        self.cursor.execute(query, values)
        self.conn.commit()
        self.invalidate_search_cache(invalidate_total_count=True)

        # Phase 2.3: Invalider le cache après ajout d'appareil
        if hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_device_modification("ajout", 1)

        return self.cursor.lastrowid

    def add_device(self, device_data: Dict[str, Any]) -> int:
        """Alias pour insert_appareil - pour compatibilité avec DatabaseOperationsService"""
        return self.insert_appareil(device_data)

    def delete_appareils(self, ids: List[int]) -> int:
        """Supprimer des appareils par ID et toutes leurs associations de pièces"""
        result = self._safe_delete_appareils(ids)
        if result == -1:
            raise DatabaseError("Erreur lors de la suppression des appareils")
        return result

    @handle_database_operation_errors(return_value=-1, log_prefix="Erreur suppression appareils")
    def _safe_delete_appareils(self, ids: List[int]) -> int:
        """Helper sécurisé pour supprimer des appareils par ID"""
        if not ids:
            return 0

        placeholders = ','.join('?' for _ in ids)

        # D'abord supprimer toutes les associations de pièces pour ces appareils
        assoc_query = f"DELETE FROM piece_associations WHERE appareil_id IN ({placeholders})"
        self.cursor.execute(assoc_query, ids)
        associations_deleted = self.cursor.rowcount

        # Puis supprimer les appareils eux-mêmes
        device_query = f"DELETE FROM appareils WHERE id IN ({placeholders})"
        self.cursor.execute(device_query, ids)
        deleted_count = self.cursor.rowcount

        self.conn.commit()
        self.invalidate_search_cache(invalidate_total_count=True)

        if deleted_count > 0 and associations_deleted > 0:
            app_logger.info(f"✅ {deleted_count} appareil(s) supprimé(s) avec {associations_deleted} association(s) de pièce(s)")
        elif deleted_count > 0:
            app_logger.info(f"✅ {deleted_count} appareil(s) supprimé(s) (aucune association de pièce)")

        # Phase 2.3: Invalider le cache après suppression d'appareils
        if deleted_count > 0 and hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_device_modification("suppression", deleted_count)

        return deleted_count
    
    def delete_appareil(self, appareil_id: int) -> bool:
        """Supprimer un appareil par ID et toutes ses associations de pièces"""
        return self._safe_delete_appareil(appareil_id)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur suppression appareil")
    def _safe_delete_appareil(self, appareil_id: int) -> bool:
        """Helper sécurisé pour supprimer un appareil par ID"""
        # Vérifier d'abord si l'appareil existe
        check_query = "SELECT id FROM appareils WHERE id = ?"
        result = self.execute_query(check_query, [appareil_id])
        if not result:
            app_logger.warning(f"Tentative suppression appareil inexistant ID: {appareil_id}")
            return False

        # D'abord supprimer toutes les associations de pièces pour cet appareil
        assoc_query = "DELETE FROM piece_associations WHERE appareil_id = ?"
        self.cursor.execute(assoc_query, [appareil_id])
        associations_deleted = self.cursor.rowcount

        # Puis supprimer l'appareil lui-même
        device_query = "DELETE FROM appareils WHERE id = ?"
        self.cursor.execute(device_query, [appareil_id])
        device_deleted = self.cursor.rowcount > 0

        self.conn.commit()
        self.invalidate_search_cache(invalidate_total_count=True)

        # Log pour debug
        if device_deleted and associations_deleted > 0:
            app_logger.info(f"Appareil {appareil_id} supprimé avec {associations_deleted} association(s)")
        elif device_deleted:
            app_logger.info(f"Appareil {appareil_id} supprimé (aucune association)")
        else:
            app_logger.error(f"Échec suppression appareil {appareil_id} - rowcount: {self.cursor.rowcount}")

        success = device_deleted

        # Phase 2.3: Invalider le cache après suppression d'appareil
        if success and hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_device_modification("suppression", 1)

        return success
    
    def check_duplicate_reference(self, ref: str, exclude_id: Optional[int] = None) -> bool:
        """Vérifier si une référence existe déjà"""
        return self._safe_check_duplicate_reference(ref, exclude_id)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur vérification doublons")
    def _safe_check_duplicate_reference(self, ref: str, exclude_id: Optional[int] = None) -> bool:
        """Helper sécurisé pour vérifier si une référence existe déjà"""
        query = """
            SELECT COUNT(*) FROM appareils
            WHERE (ref_modele = ? OR commercial_ref = ? OR other_ref = ?)
        """
        params = [ref, ref, ref]

        if exclude_id:
            query += " AND id != ?"
            params.append(exclude_id)

        self.cursor.execute(query, params)
        count = self.cursor.fetchone()[0]
        return count > 0
    
    def clean_data(self) -> Dict[str, int]:
        """Nettoyer les données (supprimer vides et doublons)"""
        result = self._safe_clean_data()
        if not result:
            raise DatabaseError("Erreur lors du nettoyage des données")
        return result

    @handle_database_operation_errors(return_value={}, log_prefix="Erreur nettoyage données")
    def _safe_clean_data(self) -> Dict[str, int]:
        """Helper sécurisé pour nettoyer les données"""
        try:
            # Supprimer les lignes vides (vérifier les 4 champs principaux)
            condition_vide = " AND ".join(f"([{h}] IS NULL OR [{h}] = '')" for h in Config.DB_HEADERS[:4])
            self.cursor.execute(f"DELETE FROM appareils WHERE {condition_vide}")
            deleted_empty = self.cursor.rowcount

            # Identifier les doublons - colonnes A, B, C, D, E identiques
            # Considérer comme doublons: même type, manufacturer, ref_modele, commercial_ref, other_ref
            duplicates_query = """
                SELECT GROUP_CONCAT(id) as ids, MIN(id) as keep_id
                FROM appareils
                GROUP BY COALESCE([type],''), COALESCE([manufacturer],''),
                         COALESCE([ref_modele],''), COALESCE([commercial_ref],''),
                         COALESCE([other_ref],'')
                HAVING COUNT(*) > 1
            """

            self.cursor.execute(duplicates_query)
            duplicate_groups = self.cursor.fetchall()

            deleted_duplicates = 0
            merged_data = 0

            # Traiter chaque groupe de doublons
            for ids_str, keep_id in duplicate_groups:
                all_ids = [int(x) for x in ids_str.split(',')]
                ids_to_delete = [x for x in all_ids if x != keep_id]

                if ids_to_delete:
                    # ÉTAPE 1: Fusionner les notes des doublons
                    notes_query = "SELECT [notes] FROM appareils WHERE id IN ({})".format(
                        ','.join('?' for _ in all_ids)
                    )
                    self.cursor.execute(notes_query, all_ids)
                    all_notes = [row[0] for row in self.cursor.fetchall() if row[0] and row[0].strip()]

                    if all_notes:
                        # Combiner les notes uniques
                        unique_notes = []
                        for note in all_notes:
                            if note.strip() and note.strip() not in unique_notes:
                                unique_notes.append(note.strip())

                        if unique_notes:
                            combined_notes = " | ".join(unique_notes)
                            self.cursor.execute(
                                "UPDATE appareils SET [notes] = ? WHERE id = ?",
                                (combined_notes, keep_id)
                            )
                            merged_data += 1

                    # ÉTAPE 2: Réassigner toutes les pièces vers l'appareil conservé
                    placeholders = ','.join('?' for _ in ids_to_delete)
                    self.cursor.execute(f"""
                        UPDATE pieces
                        SET appareil_id = ?
                        WHERE appareil_id IN ({placeholders})
                    """, [keep_id] + ids_to_delete)

                    # ÉTAPE 3: Supprimer les doublons
                    self.cursor.execute(f"""
                        DELETE FROM appareils
                        WHERE id IN ({placeholders})
                    """, ids_to_delete)

                    deleted_duplicates += len(ids_to_delete)

            self.conn.commit()

            return {
                'deleted_empty': deleted_empty,
                'deleted_duplicates': deleted_duplicates,
                'merged_notes': merged_data
            }

        except Exception as e:
            self.conn.rollback()
            raise
    
    def get_pieces_for_appareil(self, appareil_id: int) -> List[Tuple]:
        """Récupérer les pièces associées à un appareil (nouvelle structure)"""
        return self._safe_get_pieces_for_appareil(appareil_id)

    @handle_database_operation_errors(return_value=[], log_prefix="Erreur récupération pièces")
    def _safe_get_pieces_for_appareil(self, appareil_id: int) -> List[Tuple]:
        """Helper sécurisé pour récupérer les pièces associées à un appareil"""
        query = """
            SELECT p.ref_piece, p.description
            FROM pieces p
            JOIN piece_associations pa ON p.id = pa.piece_id
            WHERE pa.appareil_id = ?
            ORDER BY p.ref_piece
        """

        self.cursor.execute(query, (appareil_id,))
        return self.cursor.fetchall()
    
    @handle_db_query_errors(return_value=0, log_prefix="Erreur comptage pièces appareil")
    def get_pieces_count_for_appareil(self, appareil_id: int) -> int:
        """Récupérer le nombre de pièces associées à un appareil (seulement celles qui existent)"""
        query = """
            SELECT COUNT(*)
            FROM piece_associations pa
            INNER JOIN pieces p ON pa.piece_id = p.id
            WHERE pa.appareil_id = ?
        """
        self.cursor.execute(query, (appareil_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    @handle_db_query_errors(return_value={}, log_prefix="Erreur comptage pièces batch")
    def get_pieces_count_batch(self, appareil_ids: List[int]) -> Dict[int, int]:
        """Récupérer le nombre de pièces pour une liste d'appareils en une seule requête.

        Retourne {appareil_id: count}. Les appareils sans pièces n'apparaissent pas
        dans le dict (count implicitement 0).
        """
        if not appareil_ids:
            return {}
        placeholders = ','.join('?' * len(appareil_ids))
        query = f"""
            SELECT pa.appareil_id, COUNT(*) as cnt
            FROM piece_associations pa
            INNER JOIN pieces p ON pa.piece_id = p.id
            WHERE pa.appareil_id IN ({placeholders})
            GROUP BY pa.appareil_id
        """
        self.cursor.execute(query, appareil_ids)
        return {row[0]: row[1] for row in self.cursor.fetchall()}
    
    def add_piece(self, ref_piece: str, appareil_id: int, description: Optional[str] = None, confirm_callback=None) -> int:
        """Ajouter une pièce à un appareil (nouvelle structure)"""
        result = self._safe_add_piece(ref_piece, appareil_id, description, confirm_callback)
        if result == 0:
            raise DatabaseError(f"Erreur lors de l'ajout de la pièce {ref_piece}")
        return result

    @handle_database_operation_errors(return_value=0, log_prefix="Erreur ajout pièce")
    def _safe_add_piece(self, ref_piece: str, appareil_id: int, description: Optional[str] = None, confirm_callback=None) -> int:
        """Helper sécurisé pour ajouter une pièce à un appareil"""
        # Nettoyer la description d'entrée
        clean_description = None
        if description:
            cleaned = str(description).strip()
            if cleaned:
                clean_description = cleaned
        # Étape 1: Vérifier si la pièce existe déjà
        piece_query = "SELECT id, description FROM pieces WHERE ref_piece = ?"
        self.cursor.execute(piece_query, (ref_piece,))
        piece_result = self.cursor.fetchone()

        if piece_result:
            piece_id, current_desc = piece_result

            # Gérer les conflits de description
            if clean_description and current_desc and clean_description != current_desc:
                if confirm_callback:
                    final_description = confirm_callback(ref_piece, current_desc, clean_description)
                    if final_description != current_desc:
                        self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (final_description, piece_id))
                        self.conn.commit()
            elif clean_description and not current_desc:
                # Ajouter description à une pièce sans description
                self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (clean_description, piece_id))
                self.conn.commit()

        else:
            # Créer la nouvelle pièce
            self.cursor.execute("INSERT INTO pieces (ref_piece, description) VALUES (?, ?)", (ref_piece, clean_description))
            piece_id = self.cursor.lastrowid
            self.conn.commit()

        # Étape 2: Vérifier si l'association existe déjà
        assoc_query = "SELECT id FROM piece_associations WHERE piece_id = ? AND appareil_id = ?"
        self.cursor.execute(assoc_query, (piece_id, appareil_id))
        existing_assoc = self.cursor.fetchone()

        if existing_assoc:
            return existing_assoc[0]  # Retourner l'ID de l'association existante

        # Étape 3: Créer l'association
        self.cursor.execute("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)", (piece_id, appareil_id))
        assoc_id = self.cursor.lastrowid

        self.conn.commit()

        # Phase 2.3: Invalider le cache après ajout de pièce
        if hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_piece_modification("ajout", ref_piece, 1)

        return assoc_id
    
    def add_or_update_piece_with_description(self, ref_piece: str, appareil_id: int, description: str = None, confirm_callback=None) -> tuple:
        """
        Ajouter une pièce ou mettre à jour sa description si elle existe déjà.
        NOUVELLE STRUCTURE: Une pièce = une référence + une description, associations séparées.
        Retourne: (assoc_id, description_updated, association_created)
        """
        result = self._safe_add_or_update_piece_with_description(ref_piece, appareil_id, description, confirm_callback)
        if not result:
            raise DatabaseError(f"Erreur lors de l'ajout/mise à jour de la pièce {ref_piece}")
        return result

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur ajout/mise à jour pièce")
    def _safe_add_or_update_piece_with_description(self, ref_piece: str, appareil_id: int, description: str = None, confirm_callback=None) -> tuple:
        """Helper sécurisé pour ajouter ou mettre à jour une pièce avec description"""
        # Nettoyer la description d'entrée
        clean_description = None
        if description:
            cleaned = str(description).strip()
            if cleaned:
                clean_description = cleaned

        app_logger.debug(f"  🔍 Traitement {ref_piece} avec description: '{clean_description}'")
        description_updated = False

        # Étape 1: Vérifier si la pièce existe déjà
        piece_query = "SELECT id, description FROM pieces WHERE ref_piece = ?"
        piece_result = self.execute_query(piece_query, [ref_piece])

        if piece_result:
            # Pièce existante
            piece_id = piece_result[0][0]
            current_desc = piece_result[0][1]

            # Gérer les conflits de description
            if clean_description and current_desc and clean_description != current_desc:
                if confirm_callback:
                    final_description = confirm_callback(ref_piece, current_desc, clean_description)
                    if final_description != current_desc:
                        self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (final_description, piece_id))
                        self.conn.commit()
                        description_updated = True
            elif clean_description and not current_desc:
                # Ajouter description à une pièce sans description
                self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (clean_description, piece_id))
                self.conn.commit()
                description_updated = True

        else:
            # Nouvelle pièce
            self.cursor.execute("INSERT INTO pieces (ref_piece, description) VALUES (?, ?)", (ref_piece, clean_description))
            piece_id = self.cursor.lastrowid
            self.conn.commit()

        # Étape 2: Vérifier si l'association existe déjà
        assoc_query = "SELECT id FROM piece_associations WHERE piece_id = ? AND appareil_id = ?"
        assoc_result = self.execute_query(assoc_query, [piece_id, appareil_id])

        if assoc_result:
            # Association existante
            assoc_id = assoc_result[0][0]

            # Invalider le cache si description modifiée
            if description_updated and hasattr(self, 'cache_invalidation'):
                self.cache_invalidation.invalidate_after_piece_modification("modification", ref_piece, 1)

            return (assoc_id, description_updated, False)  # False = pas nouvelle association
        else:
            # Nouvelle association
            self.cursor.execute("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)", (piece_id, appareil_id))
            assoc_id = self.cursor.lastrowid
            self.conn.commit()

            # Phase 2.3: Invalider le cache après création d'association
            if hasattr(self, 'cache_invalidation'):
                self.cache_invalidation.invalidate_after_piece_modification("ajout", ref_piece, 1)

            return (assoc_id, description_updated, True)  # True = nouvelle association
    
    def update_piece(self, ref_piece: str, description: str) -> bool:
        """Mettre à jour la description d'une pièce (nouvelle structure)"""
        return self._safe_update_piece(ref_piece, description)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur mise à jour pièce")
    def _safe_update_piece(self, ref_piece: str, description: str) -> bool:
        """Helper sécurisé pour mettre à jour la description d'une pièce"""
        query = "UPDATE pieces SET description = ? WHERE ref_piece = ?"
        self.cursor.execute(query, (description, ref_piece))
        updated = self.cursor.rowcount > 0
        self.conn.commit()

        # Phase 2.3: Invalider le cache après mise à jour de pièce
        if updated and hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_piece_modification("modification", ref_piece, 1)

        return updated
    
    def update_piece_complete(self, old_ref_piece: str, new_ref_piece: str, description: str, appareil_id: int) -> bool:
        """Mettre à jour complètement une pièce (référence ET description)"""
        result = self._safe_update_piece_complete(old_ref_piece, new_ref_piece, description, appareil_id)
        if result is None:
            raise DatabaseError(f"Erreur lors de la mise à jour complète de la pièce {old_ref_piece}")
        return result

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur mise à jour complète pièce")
    def _safe_update_piece_complete(self, old_ref_piece: str, new_ref_piece: str, description: str, appareil_id: int) -> bool:
        """Helper sécurisé pour mettre à jour complètement une pièce"""
        try:
            # Si la référence ne change pas, utiliser update_piece simple
            if old_ref_piece == new_ref_piece:
                return self.update_piece(new_ref_piece, description)

            # Si la référence change, vérifier que la nouvelle référence n'existe pas déjà
            check_query = "SELECT COUNT(*) FROM pieces WHERE ref_piece = ?"
            self.cursor.execute(check_query, (new_ref_piece,))
            if self.cursor.fetchone()[0] > 0:
                # La nouvelle référence existe déjà - on va faire une association
                # Supprimer l'ancienne association et créer la nouvelle
                piece_query = "SELECT id FROM pieces WHERE ref_piece = ?"
                self.cursor.execute(piece_query, (old_ref_piece,))
                old_piece_result = self.cursor.fetchone()

                self.cursor.execute(piece_query, (new_ref_piece,))
                new_piece_result = self.cursor.fetchone()

                if old_piece_result and new_piece_result:
                    old_piece_id, new_piece_id = old_piece_result[0], new_piece_result[0]

                    # Supprimer l'ancienne association
                    delete_assoc = "DELETE FROM piece_associations WHERE piece_id = ? AND appareil_id = ?"
                    self.cursor.execute(delete_assoc, (old_piece_id, appareil_id))

                    # Ajouter la nouvelle association si elle n'existe pas
                    check_assoc = "SELECT COUNT(*) FROM piece_associations WHERE piece_id = ? AND appareil_id = ?"
                    self.cursor.execute(check_assoc, (new_piece_id, appareil_id))
                    if self.cursor.fetchone()[0] == 0:
                        insert_assoc = "INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)"
                        self.cursor.execute(insert_assoc, (new_piece_id, appareil_id))

                    # Mettre à jour la description si fournie
                    if description:
                        self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (description, new_piece_id))

                    self.conn.commit()

                    # Invalider le cache
                    if hasattr(self, 'cache_invalidation'):
                        self.cache_invalidation.invalidate_after_piece_modification("modification", new_ref_piece, 1)

                    return True
            else:
                # La nouvelle référence n'existe pas - mise à jour directe
                update_query = "UPDATE pieces SET ref_piece = ?, description = ? WHERE ref_piece = ?"
                self.cursor.execute(update_query, (new_ref_piece, description, old_ref_piece))
                updated = self.cursor.rowcount > 0
                self.conn.commit()

                # Invalider le cache
                if updated and hasattr(self, 'cache_invalidation'):
                    self.cache_invalidation.invalidate_after_piece_modification("modification", new_ref_piece, 1)

                return updated

        except Exception as e:
            self.conn.rollback()
            raise
    
    def get_piece_info(self, ref_piece: str, appareil_id: int) -> Optional[Tuple[str, str]]:
        """Récupérer les informations d'une pièce spécifique (nouvelle structure)"""
        return self._safe_get_piece_info(ref_piece, appareil_id)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur récupération info pièce")
    def _safe_get_piece_info(self, ref_piece: str, appareil_id: int) -> Optional[Tuple[str, str]]:
        """Helper sécurisé pour récupérer les informations d'une pièce spécifique"""
        query = """
            SELECT p.ref_piece, p.description
            FROM pieces p
            JOIN piece_associations pa ON p.id = pa.piece_id
            WHERE p.ref_piece = ? AND pa.appareil_id = ?
        """
        self.cursor.execute(query, (ref_piece, appareil_id))
        result = self.cursor.fetchone()
        return result if result else None
    
    def delete_piece(self, ref_piece: str, appareil_id: int) -> bool:
        """Supprimer une pièce spécifique d'un appareil (nouvelle structure)"""
        return self._safe_delete_piece(ref_piece, appareil_id)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur suppression pièce")
    def _safe_delete_piece(self, ref_piece: str, appareil_id: int) -> bool:
        """Helper sécurisé pour supprimer une pièce spécifique d'un appareil"""
        # Étape 1: Trouver la pièce et l'association
        query = """
            SELECT p.id, pa.id
            FROM pieces p
            JOIN piece_associations pa ON p.id = pa.piece_id
            WHERE p.ref_piece = ? AND pa.appareil_id = ?
        """
        self.cursor.execute(query, (ref_piece, appareil_id))
        result = self.cursor.fetchone()

        if not result:
            return False

        piece_id, assoc_id = result

        # Étape 2: Supprimer l'association
        self.cursor.execute("DELETE FROM piece_associations WHERE id = ?", (assoc_id,))

        # Étape 3: Vérifier si la pièce a d'autres associations
        self.cursor.execute("SELECT COUNT(*) FROM piece_associations WHERE piece_id = ?", (piece_id,))
        remaining_assocs = self.cursor.fetchone()[0]

        # Si plus d'associations, supprimer la pièce aussi
        if remaining_assocs == 0:
            self.cursor.execute("DELETE FROM pieces WHERE id = ?", (piece_id,))

        self.conn.commit()

        # Phase 2.3: Invalider le cache après suppression de pièce
        if hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_piece_modification("suppression", ref_piece, 1)

        return True
    
    def delete_pieces_by_appareil(self, appareil_id: int) -> int:
        """Supprimer toutes les pièces d'un appareil (nouvelle structure)"""
        result = self._safe_delete_pieces_by_appareil(appareil_id)
        if result == -1:
            raise DatabaseError(f"Erreur lors de la suppression des pièces de l'appareil {appareil_id}")
        return result

    @handle_database_operation_errors(return_value=-1, log_prefix="Erreur suppression pièces appareil")
    def _safe_delete_pieces_by_appareil(self, appareil_id: int) -> int:
        """Helper sécurisé pour supprimer toutes les pièces d'un appareil"""
        # Étape 1: Récupérer toutes les pièces associées à cet appareil
        query = """
            SELECT p.id, p.ref_piece
            FROM pieces p
            JOIN piece_associations pa ON p.id = pa.piece_id
            WHERE pa.appareil_id = ?
        """
        self.cursor.execute(query, (appareil_id,))
        piece_info = self.cursor.fetchall()

        if not piece_info:
            return 0

        # Étape 2: Supprimer toutes les associations pour cet appareil
        self.cursor.execute("DELETE FROM piece_associations WHERE appareil_id = ?", (appareil_id,))
        deleted_count = self.cursor.rowcount

        # Étape 3: Supprimer les pièces qui n'ont plus d'associations
        for piece_id, ref_piece in piece_info:
            self.cursor.execute("SELECT COUNT(*) FROM piece_associations WHERE piece_id = ?", (piece_id,))
            remaining_assocs = self.cursor.fetchone()[0]

            if remaining_assocs == 0:
                self.cursor.execute("DELETE FROM pieces WHERE id = ?", (piece_id,))

        self.conn.commit()

        # Phase 2.3: Invalider le cache après suppression de pièces d'appareil
        if deleted_count > 0 and hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_device_modification("suppression de pièces", 1)

        return deleted_count
    
    def delete_piece_from_multiple_appareils(self, ref_piece: str, appareil_ids: List[int]) -> int:
        """Supprimer une pièce de plusieurs appareils"""
        result = self._safe_delete_piece_from_multiple_appareils(ref_piece, appareil_ids)
        if result == -1:
            raise DatabaseError(f"Erreur lors de la suppression multiple de la pièce {ref_piece}")
        return result

    @handle_database_operation_errors(return_value=-1, log_prefix="Erreur suppression multiple pièce")
    def _safe_delete_piece_from_multiple_appareils(self, ref_piece: str, appareil_ids: List[int]) -> int:
        """Helper sécurisé pour supprimer une pièce de plusieurs appareils"""
        deleted_count = 0
        for appareil_id in appareil_ids:
            if self.delete_piece(ref_piece, appareil_id):
                deleted_count += 1

        # Phase 2.3: Invalider le cache après suppression multiple
        if deleted_count > 0 and hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_piece_modification("suppression", ref_piece, deleted_count)

        return deleted_count
    
    def get_duplicate_ref_modeles(self) -> List[Tuple[str, int]]:
        """Récupérer les ref_modele en doublon avec leur nombre d'occurrences (recherche exacte uniquement)"""
        return self._safe_get_duplicate_ref_modeles()

    @handle_database_operation_errors(return_value=[], log_prefix="Erreur récupération doublons ref_modele")
    def _safe_get_duplicate_ref_modeles(self) -> List[Tuple[str, int]]:
        """Helper sécurisé pour récupérer les ref_modele en doublon"""
        # Récupérer uniquement les doublons exacts
        query = Config.get_query('duplicate_refs')
        exact_duplicates = self.execute_custom_query(query)

        # Retourner sous forme de liste triée
        return sorted(exact_duplicates, key=lambda x: x[1], reverse=True)

    @handle_db_query_errors(return_value=None, log_prefix="Erreur récupération infos appareil")
    def get_device_info(self, device_id: int) -> Optional[Dict[str, Any]]:
        """Récupérer les informations d'un appareil par son ID"""
        query = """
            SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes
            FROM appareils
            WHERE id = ?
        """
        result = self.execute_query(query, [device_id])

        if result:
            row = result[0]
            return {
                'id': row[0],
                'type': row[1],
                'manufacturer': row[2],
                'ref_modele': row[3],
                'commercial_ref': row[4],
                'other_ref': row[5],
                'category': row[6],
                'notes': row[7]
            }
        return None

    @handle_db_query_errors(return_value=[], log_prefix="Erreur récupération appareils par ref_modele")
    def get_devices_by_ref_modele(self, ref_modele: str) -> List[Tuple]:
        """Récupérer tous les appareils ayant exactement la même ref_modele"""
        # Récupérer uniquement les appareils avec la référence exacte
        query = """
            SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes
            FROM appareils
            WHERE ref_modele = ?
            ORDER BY id
        """
        return self.execute_custom_query(query, [ref_modele])

    @handle_database_errors(title="Erreur récupération doublons")
    def get_duplicate_references(self) -> List[Tuple[str, str, str, str, str, int]]:
        """Récupérer les références d'appareils en doublon (colonnes A,B,C,D,E identiques)"""
        query = """
            SELECT type, manufacturer, ref_modele, commercial_ref, other_ref, COUNT(*) as count
            FROM appareils
            GROUP BY type, manufacturer, ref_modele, commercial_ref, other_ref
            HAVING COUNT(*) > 1
            ORDER BY count DESC, type, manufacturer, ref_modele, commercial_ref, other_ref
        """
        return self.execute_custom_query(query)
    
    def transfer_pieces(self, from_device_id: int, to_device_id: int):
        """Transférer les pièces d'un appareil vers un autre (nouvelle structure)"""
        try:
            # Étape 1: Récupérer toutes les pièces de l'appareil source
            source_query = """
                SELECT p.id, p.ref_piece
                FROM pieces p
                JOIN piece_associations pa ON p.id = pa.piece_id
                WHERE pa.appareil_id = ?
            """
            self.cursor.execute(source_query, (from_device_id,))
            source_pieces = self.cursor.fetchall()
            
            # Étape 2: Récupérer les pièces déjà associées à l'appareil de destination
            dest_query = """
                SELECT p.ref_piece
                FROM pieces p
                JOIN piece_associations pa ON p.id = pa.piece_id
                WHERE pa.appareil_id = ?
            """
            self.cursor.execute(dest_query, (to_device_id,))
            dest_pieces = {row[0] for row in self.cursor.fetchall()}
            
            # Étape 3: Transférer les pièces non-doublons
            transferred = 0
            for piece_id, ref_piece in source_pieces:
                if ref_piece not in dest_pieces:
                    # Transférer l'association
                    self.cursor.execute("UPDATE piece_associations SET appareil_id = ? WHERE piece_id = ? AND appareil_id = ?", 
                                      (to_device_id, piece_id, from_device_id))
                    transferred += 1
            
            # Étape 4: Supprimer les associations restantes de l'appareil source
            self.cursor.execute("DELETE FROM piece_associations WHERE appareil_id = ?", (from_device_id,))
            
            self.conn.commit()
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(f"Erreur lors du transfert des pièces: {e}")

    def remove_duplicate_devices(self) -> int:
        """Supprimer les appareils en doublon en gardant le plus ancien"""
        try:
            # Récupérer les doublons (colonnes A,B,C,D,E identiques)
            duplicates_query = """
                SELECT type, manufacturer, ref_modele, commercial_ref, other_ref, GROUP_CONCAT(id) as ids, MIN(id) as keep_id
                FROM appareils 
                GROUP BY type, manufacturer, ref_modele, commercial_ref, other_ref 
                HAVING COUNT(*) > 1
            """
            duplicates = self.execute_custom_query(duplicates_query)
            
            deleted_count = 0
            for type_val, manufacturer, ref_modele, commercial_ref, other_ref, ids_str, keep_id in duplicates:
                all_ids = [int(x) for x in ids_str.split(',')]
                ids_to_delete = [x for x in all_ids if x != keep_id]
                
                for delete_id in ids_to_delete:
                    # Transférer les pièces vers l'appareil à conserver (nouvelle structure)
                    self.transfer_pieces(delete_id, keep_id)
                    
                    # Supprimer l'appareil doublon
                    self.cursor.execute("DELETE FROM appareils WHERE id = ?", (delete_id,))
                    deleted_count += 1
            
            self.conn.commit()
            return deleted_count
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(f"Erreur lors de la suppression des doublons: {e}")
    
    def remove_duplicate_pieces(self) -> int:
        """Supprimer les références de pièces dupliquées (nouvelle structure)"""
        try:
            # Avec la nouvelle structure, il ne devrait pas y avoir de doublons
            # car piece_associations a une contrainte UNIQUE(piece_id, appareil_id)
            # et pieces a une contrainte UNIQUE(ref_piece)
            
            # Mais on peut vérifier s'il y a des doublons d'associations
            duplicate_assoc_query = """
                DELETE FROM piece_associations 
                WHERE id NOT IN (
                    SELECT MIN(id) 
                    FROM piece_associations 
                    GROUP BY piece_id, appareil_id
                )
            """
            self.cursor.execute(duplicate_assoc_query)
            deleted_count = self.cursor.rowcount
            
            # Supprimer les pièces orphelines (sans associations)
            orphan_query = """
                DELETE FROM pieces 
                WHERE id NOT IN (
                    SELECT DISTINCT piece_id 
                    FROM piece_associations
                )
            """
            self.cursor.execute(orphan_query)
            orphan_count = self.cursor.rowcount
            
            self.conn.commit()
            return deleted_count + orphan_count
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(f"Erreur lors de la suppression des pièces dupliquées: {e}")
    
    @handle_db_query_errors(return_value=0, log_prefix="Erreur comptage pièces dupliquées")
    def get_duplicate_pieces_count(self) -> int:
        """Compter les références de pièces dupliquées (nouvelle structure)"""
        # Compter les doublons d'associations
        query = """
            SELECT COUNT(*)
            FROM piece_associations
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM piece_associations
                GROUP BY piece_id, appareil_id
            )
        """
        self.cursor.execute(query)
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    @handle_database_errors(title="Erreur analyse doublons pièces")
    def analyze_piece_duplicates(self) -> List[Tuple]:
        """Analyser les doublons de pièces en détail (nouvelle structure)"""
        # Analyser les doublons d'associations
        query = """
            SELECT
                p.ref_piece,
                pa.appareil_id,
                COUNT(*) as count
            FROM piece_associations pa
            JOIN pieces p ON pa.piece_id = p.id
            WHERE p.ref_piece IS NOT NULL AND p.ref_piece != ''
            GROUP BY pa.piece_id, pa.appareil_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC, p.ref_piece, pa.appareil_id
        """
        self.cursor.execute(query)
        return self.cursor.fetchall()
    
    @handle_database_errors(title="Erreur récupération catégories")
    def get_categories(self) -> List[str]:
        """Récupérer toutes les catégories"""
        self.cursor.execute("SELECT name FROM categories ORDER BY name")
        return [row[0] for row in self.cursor.fetchall()]

    @handle_database_errors(title="Erreur récupération valeurs colonne")
    def get_column_values(self, db_field: str) -> List[str]:
        """Récupérer les valeurs distinctes d'un champ de la table appareils.

        db_field doit être un champ validé via _get_db_field_name() —
        jamais une entrée utilisateur directe (prévient les injections SQL).
        """
        query = Config.get_query('autocomplete_field', field=db_field)
        self.cursor.execute(query)
        return [row[0] for row in self.cursor.fetchall() if row[0]]
    
    @handle_database_errors(title="Erreur mise à jour catégories")
    def update_categories(self, categories: List[str]) -> bool:
        """Mettre à jour la liste des catégories"""
        # Supprimer toutes les catégories existantes
        self.cursor.execute("DELETE FROM categories")

        # Ajouter les nouvelles catégories
        for category in categories:
            self.cursor.execute(
                "INSERT INTO categories (name) VALUES (?)",
                (category,)
            )

        self.conn.commit()
        return True
    
    @handle_database_errors(title="Erreur validation base de données")
    def validate_database(self) -> Dict[str, Any]:
        """Valider la cohérence de la base de données"""
        issues = {}

        # Pièces orphelines
        self.cursor.execute(Config.get_query('orphaned_pieces'))
        issues['orphaned_pieces'] = self.cursor.fetchone()[0]

        # Doublons de références
        self.cursor.execute(Config.get_query('duplicate_refs'))
        issues['duplicate_refs'] = len(self.cursor.fetchall())

        # Champs vides critiques
        self.cursor.execute(Config.get_query('empty_critical'))
        issues['empty_critical'] = self.cursor.fetchone()[0]

        return issues
    
    @handle_database_errors(title="Erreur récupération données export")
    def get_export_data(self, search_term: str,
                       column_filters: Optional[Dict[int, str]] = None,
                       incomplete_filter: bool = False) -> List[Tuple]:
        """Récupérer les données pour l'export - utilise exactement la même logique que load_data()"""
        # Construction de la requête similaire à load_data mais adaptée pour l'export
        headers_str = ', '.join(f'a.[{h}]' for h in Config.DB_HEADERS[:5])
        query = f"""
            SELECT DISTINCT {headers_str}, ? as ref_piece
            FROM appareils a
            LEFT JOIN piece_associations pa ON a.id = pa.appareil_id
            LEFT JOIN pieces p ON pa.piece_id = p.id
        """

        # Paramètre fixe pour la référence de pièce dans le résultat
        # Si c'est un objet dict, utiliser un terme par défaut pour le paramètre
        if isinstance(search_term, dict):
            display_term = "recherche_multiple"
        else:
            display_term = search_term
        params = [display_term]
        conditions = []

        # Recherche globale utilisant la même logique que load_data
        if search_term:
            # Parser le terme de recherche s'il contient des opérateurs || ou &&
            parsed_search = self._parse_search_term_for_export(search_term)
            search_condition = self._build_search_condition(parsed_search)
            if search_condition:
                # Phase 3: Gérer les requêtes optimisées (éviter erreur "near SELECT")
                if search_condition.get('query_type') in ['exact', 'prefix']:
                    # Pour les requêtes optimisées, extraire juste la condition WHERE
                    if search_condition['query_type'] == 'exact':
                        condition = "(a.ref_modele = ? OR a.commercial_ref = ? OR a.other_ref = ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece = ?))"
                    else:  # prefix
                        condition = "(a.ref_modele LIKE ? OR a.commercial_ref LIKE ? OR a.other_ref LIKE ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))"

                    conditions.append(condition)
                    params.extend(search_condition['params'])
                else:
                    # Condition WHERE classique
                    conditions.append(search_condition['condition'])
                    params.extend(search_condition['params'])

        # Filtres par colonne (comme dans load_data)
        if column_filters:
            for col_idx, filter_text in column_filters.items():
                if col_idx < len(Config.DB_HEADERS) and filter_text.strip():
                    conditions.append(f"a.[{Config.DB_HEADERS[col_idx]}] LIKE ?")
                    params.append(f"%{filter_text}%")

        # Filtre pour les lignes incomplètes (comme dans load_data)
        if incomplete_filter:
            incomplete_condition = "(a.[type] IS NULL OR a.[type] = '' OR a.[manufacturer] IS NULL OR a.[manufacturer] = '')"
            conditions.append(incomplete_condition)

        # Ajouter les conditions WHERE si nécessaire
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    @handle_database_errors(title="Erreur requête personnalisée")
    def execute_custom_query(self, query: str, params: Optional[List] = None) -> List[Tuple]:
        """Exécuter une requête SQL personnalisée"""
        if params is None:
            params = []

        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    def execute_insert(self, query: str, params: Optional[List] = None) -> Optional[int]:
        """Exécuter une requête INSERT et retourner l'ID de la ligne insérée"""
        result = self._safe_execute_insert(query, params)
        if result is None:
            raise DatabaseError("Erreur lors de l'exécution de la requête INSERT")
        return result

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur exécution INSERT")
    def _safe_execute_insert(self, query: str, params: Optional[List] = None) -> Optional[int]:
        """Helper sécurisé pour exécuter une requête INSERT"""
        if params is None:
            params = []

        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            self.conn.rollback()
            raise
    
    def execute_query(self, query: str, params: Optional[List] = None) -> List[Tuple]:
        """Exécuter une requête SQL de lecture (SELECT)"""
        return self._safe_execute_query(query, params)

    @handle_database_operation_errors(return_value=[], log_prefix="Erreur exécution SELECT")
    def _safe_execute_query(self, query: str, params: Optional[List] = None) -> List[Tuple]:
        """Helper sécurisé pour exécuter une requête SQL de lecture"""
        if params is None:
            params = []

        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    # Méthodes pour gérer les décisions sur les doublons de références
    def save_reference_decision(self, ref_modele: str, decision: str, notes: str = None) -> bool:
        """Sauvegarder une décision sur un doublon de référence"""
        result = self._safe_save_reference_decision(ref_modele, decision, notes)
        if not result:
            raise DatabaseError(f"Erreur lors de la sauvegarde de la décision pour {ref_modele}")
        return result

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde décision référence")
    def _safe_save_reference_decision(self, ref_modele: str, decision: str, notes: str = None) -> bool:
        """Helper sécurisé pour sauvegarder une décision sur un doublon de référence"""
        if decision not in ('DISTINCT', 'MERGE'):
            raise ValueError(f"Décision invalide: {decision}")

        query = """
            INSERT OR REPLACE INTO reference_decisions
            (ref_modele, decision, notes, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """

        try:
            self.cursor.execute(query, (ref_modele, decision, notes))
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            raise
    
    def get_reference_decision(self, ref_modele: str) -> Optional[Dict[str, Any]]:
        """Récupérer la décision pour une référence"""
        return self._safe_get_reference_decision(ref_modele)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur récupération décision référence")
    def _safe_get_reference_decision(self, ref_modele: str) -> Optional[Dict[str, Any]]:
        """Helper sécurisé pour récupérer la décision pour une référence"""
        query = """
            SELECT decision, notes, created_at
            FROM reference_decisions
            WHERE ref_modele = ?
        """

        self.cursor.execute(query, (ref_modele,))
        result = self.cursor.fetchone()

        if result:
            return {
                'ref_modele': ref_modele,
                'decision': result[0],
                'notes': result[1],
                'created_at': result[2]
            }
        return None
    
    def get_references_by_decision(self, decision: str = None) -> List[Dict[str, Any]]:
        """Récupérer toutes les références filtrées par décision (optionnel)"""
        return self._safe_get_references_by_decision(decision)

    @handle_database_operation_errors(return_value=[], log_prefix="Erreur récupération références par décision")
    def _safe_get_references_by_decision(self, decision: str = None) -> List[Dict[str, Any]]:
        """Helper sécurisé pour récupérer toutes les références par décision"""
        if decision and decision not in ('DISTINCT', 'MERGE'):
            raise ValueError(f"Décision invalide: {decision}")

        if decision:
            query = """
                SELECT ref_modele, decision, notes, created_at
                FROM reference_decisions
                WHERE decision = ?
                ORDER BY created_at DESC
            """
            self.cursor.execute(query, (decision,))
        else:
            query = """
                SELECT ref_modele, decision, notes, created_at
                FROM reference_decisions
                ORDER BY created_at DESC
            """
            self.cursor.execute(query)

        results = []
        for row in self.cursor.fetchall():
            results.append({
                'ref_modele': row[0],
                'decision': row[1],
                'notes': row[2],
                'created_at': row[3]
            })

        return results
    
    def delete_reference_decision(self, ref_modele: str) -> bool:
        """Supprimer une décision (réinitialiser à l'état nouveau)"""
        return self._safe_delete_reference_decision(ref_modele)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur suppression décision référence")
    def _safe_delete_reference_decision(self, ref_modele: str) -> bool:
        """Helper sécurisé pour supprimer une décision de référence"""
        query = "DELETE FROM reference_decisions WHERE ref_modele = ?"

        try:
            self.cursor.execute(query, (ref_modele,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            raise
    
    def _load_data_optimized(self, search_term: Optional[str] = None,
                          column_filters: Optional[Dict[int, str]] = None,
                          limit: Optional[int] = None,
                          offset: Optional[int] = None,
                          sort_column: Optional[int] = None,
                          sort_order: Optional[str] = None,
                          incomplete_filter: bool = False) -> List[Tuple]:
        """Version optimisée de load_data - sépare requête principale du calcul pieces_count"""
        try:
            # ÉTAPE 1: Requête principale RAPIDE (sans LEFT JOIN coûteux)
            headers_str = ', '.join(f'a.[{h}]' for h in Config.DB_HEADERS)
            query = f"SELECT a.id, {headers_str} FROM appareils a"
            params = []
            conditions = []

            # Mêmes conditions de recherche que l'original
            if search_term:
                search_condition = self._build_search_condition_optimized(search_term)
                if search_condition:
                    if search_condition.get('query_type') in ['exact', 'prefix']:
                        if search_condition['query_type'] == 'exact':
                            condition = "(a.ref_modele = ? OR a.commercial_ref = ? OR a.other_ref = ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece = ?))"
                        else:  # prefix
                            condition = "(a.ref_modele LIKE ? OR a.commercial_ref LIKE ? OR a.other_ref LIKE ?) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece LIKE ?))"
                        conditions.append(condition)
                        params.extend(search_condition['params'])
                    else:
                        conditions.append(search_condition['condition'])
                        params.extend(search_condition['params'])

            # Filtres par colonne
            if column_filters:
                for col_idx, filter_text in column_filters.items():
                    if col_idx < len(Config.DB_HEADERS) and filter_text.strip():
                        conditions.append(f"a.[{Config.DB_HEADERS[col_idx]}] LIKE ?")
                        params.append(f"%{filter_text}%")

            # Filtre lignes incomplètes
            if incomplete_filter:
                incomplete_condition = "(a.type IS NULL OR a.type = '' OR a.manufacturer IS NULL OR a.manufacturer = '')"
                conditions.append(incomplete_condition)

            # Assemblage WHERE
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            # Tri (même logique que l'original)
            if sort_column is not None and 0 <= sort_column < len(Config.DB_HEADERS):
                sort_col = Config.DB_HEADERS[sort_column]
                order = "DESC" if sort_order == "desc" else "ASC"
                query += f" ORDER BY a.[{sort_col}] {order}"
            else:
                query += " ORDER BY a.id DESC"

            # Pagination
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
                if offset is not None:
                    query += " OFFSET ?"
                    params.append(offset)

            # ÉTAPE 2: Exécuter requête principale
            main_results = self.execute_query(query, params)
            if not main_results:
                return []

            # ÉTAPE 3: Calculer pieces_count seulement pour les résultats retournés
            appareil_ids = [str(row[0]) for row in main_results]
            pieces_counts = {}

            if appareil_ids:
                count_query = f"""
                    SELECT pa.appareil_id, COUNT(*) as pieces_count
                    FROM piece_associations pa
                    INNER JOIN pieces p ON pa.piece_id = p.id
                    WHERE pa.appareil_id IN ({','.join(['?'] * len(appareil_ids))})
                    GROUP BY pa.appareil_id
                """
                count_results = self.execute_query(count_query, appareil_ids)
                pieces_counts = {row[0]: row[1] for row in count_results}

            # ÉTAPE 4: Assembler résultats finaux avec pieces_count
            final_results = []
            for row in main_results:
                appareil_id = row[0]
                pieces_count = pieces_counts.get(appareil_id, 0)
                final_row = row + (pieces_count,)
                final_results.append(final_row)

            return final_results

        except Exception as e:
            app_logger.error(f"Erreur _load_data_optimized: {e}")
            raise

    def close(self):
        """Fermer la connexion à la base de données"""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()