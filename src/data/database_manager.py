"""
Gestionnaire de base de données pour l'application de gestion d'appareils
"""

import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

try:
    from PyQt5.QtCore import QThread, pyqtSignal
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


class DatabaseWorker(QThread):
    """Worker thread pour les opérations de base de données asynchrones"""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, db_file: str, query: str, params: Optional[List] = None):
        super().__init__()
        self.db_file = db_file
        self.query = query
        self.params = params or []
    
    def run(self):
        """Exécuter la requête de base de données"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(self.query, self.params)
            records = cursor.fetchall()
            conn.close()
            self.data_loaded.emit(records)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DatabaseManager:
    """Gestionnaire centralisé pour toutes les opérations de base de données"""
    
    def __init__(self, db_file: str = None):
        self.db_file = db_file or Config.DB_FILE
        self.conn = None
        self.cursor = None
        self._connect()
        self._setup_database()
    
    def _connect(self):
        """Établir la connexion à la base de données"""
        try:
            self.conn = sqlite3.connect(self.db_file)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            raise DatabaseError(f"Impossible de se connecter à la base de données: {e}")
    
    def _build_search_condition(self, search_term):
        """Construire une condition de recherche basée sur le terme de recherche (simple ou avancé)"""
        import re
        
        # Si c'est une chaîne simple (ancienne API), traiter comme recherche simple
        if isinstance(search_term, str):
            if not search_term.strip():
                return None
            search_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
            search_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece LIKE ?)")
            return {
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
            search_conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
            search_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece LIKE ?)")
            return {
                'condition': f"({' OR '.join(search_conditions)})",
                'params': [f"%{term}%"] * (len(Config.DB_HEADERS) + 1)
            }
        
        elif search_type == 'or':
            # Recherche avec groupes OR
            groups = search_term.get('groups', [])
            if not groups:
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
                        term_conditions.append("a.id IN (SELECT pa.appareil_id FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece LIKE ?)")
                        
                        and_conditions.append(f"({' OR '.join(term_conditions)})")
                        all_params.extend([f"%{term}%"] * (len(Config.DB_HEADERS) + 1))
                    
                    if and_conditions:
                        group_conditions.append(f"({' AND '.join(and_conditions)})")
            
            if group_conditions:
                return {
                    'condition': f"({' OR '.join(group_conditions)})",
                    'params': all_params
                }
        
        return None
    
    def _setup_database(self):
        """Configuration et création des tables"""
        try:
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
            
            # Ajouter les colonnes manquantes pour la table pieces
            self._add_missing_pieces_columns()
            
            # Ajouter la contrainte unique pour prévenir les doublons
            self._add_unique_constraint_pieces()
            
            # Index pour les performances
            self._create_indexes()
            
            # Migration des données vers la nouvelle structure
            self._migrate_pieces_to_new_structure()
            
            self.conn.commit()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la configuration de la base: {e}")
    
    def _add_missing_columns(self):
        """Ajouter les colonnes manquantes à la table appareils"""
        try:
            self.cursor.execute("PRAGMA table_info(appareils)")
            existing_columns = {row[1] for row in self.cursor.fetchall()}
            
            for header in Config.DB_HEADERS + ['created_at', 'updated_at']:
                if header not in existing_columns:
                    try:
                        self.cursor.execute(f"ALTER TABLE appareils ADD COLUMN [{header}] TEXT")
                    except sqlite3.OperationalError:
                        pass  # Colonne déjà existante
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'ajout des colonnes: {e}")
    
    def _add_missing_pieces_columns(self):
        """Ajouter les colonnes manquantes à la table pieces"""
        try:
            # Vérifier si la table pieces existe
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pieces'")
            if not self.cursor.fetchone():
                print("Table pieces n'existe pas, skip ajout colonnes")
                return
                
            self.cursor.execute("PRAGMA table_info(pieces)")
            existing_columns = {row[1] for row in self.cursor.fetchall()}
            
            # Si la table n'a pas de colonne 'appareil_id', elle a déjà la nouvelle structure
            if 'appareil_id' not in existing_columns:
                print("Table pieces déjà avec nouvelle structure, skip ajout colonnes")
                return
            
            # Ajouter la colonne description si elle n'existe pas
            if 'description' not in existing_columns:
                try:
                    self.cursor.execute("ALTER TABLE pieces ADD COLUMN description TEXT")
                    print("Colonne 'description' ajoutée à la table pieces")
                except sqlite3.OperationalError as e:
                    print(f"Erreur lors de l'ajout de la colonne description: {e}")
                    
            # Ajouter la colonne created_at si elle n'existe pas
            if 'created_at' not in existing_columns:
                try:
                    self.cursor.execute("ALTER TABLE pieces ADD COLUMN created_at TEXT")
                    print("Colonne 'created_at' ajoutée à la table pieces")
                except sqlite3.OperationalError as e:
                    print(f"Erreur lors de l'ajout de la colonne created_at: {e}")
            
            # Forcer un commit immédiat
            self.conn.commit()
                    
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'ajout des colonnes pieces: {e}")
    
    def _add_unique_constraint_pieces(self):
        """Ajouter la contrainte unique pour prévenir les doublons de pièces"""
        try:
            # Vérifier si la table pieces a déjà la nouvelle structure
            self.cursor.execute("PRAGMA table_info(pieces)")
            pieces_columns = [row[1] for row in self.cursor.fetchall()]
            
            if 'appareil_id' not in pieces_columns:
                # Nouvelle structure déjà en place, skip
                print("Table pieces déjà avec nouvelle structure, skip contrainte unique")
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
                print("Contrainte unique ajoutée à la table pieces")
                
        except sqlite3.Error as e:
            self.cursor.execute("ROLLBACK")
            print(f"Erreur lors de l'ajout de la contrainte unique: {e}")
    
    def _create_indexes(self):
        """Créer les index pour optimiser les performances"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_appareils_type ON appareils(type)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_manufacturer ON appareils(manufacturer)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_ref_modele ON appareils(ref_modele)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_commercial_ref ON appareils(commercial_ref)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_other_ref ON appareils(other_ref)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_category ON appareils(category)",
            "CREATE INDEX IF NOT EXISTS idx_appareils_id_desc ON appareils(id DESC)",  # Pour ORDER BY id DESC
            "CREATE INDEX IF NOT EXISTS idx_pieces_ref ON pieces(ref_piece)",
            "CREATE INDEX IF NOT EXISTS idx_piece_associations_piece ON piece_associations(piece_id)",
            "CREATE INDEX IF NOT EXISTS idx_piece_associations_appareil ON piece_associations(appareil_id)"
        ]
        
        for index_query in indexes:
            try:
                self.cursor.execute(index_query)
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
                print("Tables de migration manquantes, skip")
                return
            
            # Vérifier la structure de la table pieces actuelle
            self.cursor.execute("PRAGMA table_info(pieces)")
            pieces_columns = [row[1] for row in self.cursor.fetchall()]
            print(f"Colonnes de pieces: {pieces_columns}")
            
            # Si la table pieces n'a pas de colonne 'appareil_id', la migration a déjà été effectuée
            if 'appareil_id' not in pieces_columns:
                print("Migration déjà effectuée (pas de colonne appareil_id), skip")
                return
                
            # Vérifier si les nouvelles tables sont vides
            self.cursor.execute("SELECT COUNT(*) FROM pieces")
            old_pieces_count = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM piece_associations")
            assoc_count = self.cursor.fetchone()[0]
            
            if old_pieces_count == 0:
                print("Pas de données à migrer")
                return
                
            if assoc_count > 0:
                print("Migration déjà effectuée (associations existantes), skip")
                return
            
            print("🔄 Début de la migration des pièces vers la nouvelle structure...")
            
            # Étape 1: Sauvegarder les anciennes données
            print("📋 Sauvegarde des anciennes données...")
            
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
            print("📦 Création des pièces uniques...")
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
                self.cursor.execute("SELECT DISTINCT ref_piece FROM pieces")
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
            
            print(f"📦 {len(pieces_data)} pièces uniques créées")
            
            # Étape 4: Créer les associations dans piece_associations
            print("🔗 Création des associations...")
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
            print(f"🔗 {associations_migrated} associations migrées")
            
            print("✅ Migration terminée avec succès")
            
        except sqlite3.Error as e:
            print(f"❌ Erreur lors de la migration: {e}")
            # En cas d'erreur, essayer de restaurer
            try:
                self.cursor.execute("DROP TABLE IF EXISTS piece_associations")
                self.cursor.execute("ROLLBACK")
            except:
                pass
            raise DatabaseError(f"Erreur lors de la migration des pièces: {e}")
    
    def load_data(self, search_term: Optional[str] = None, 
                  column_filters: Optional[Dict[int, str]] = None, 
                  limit: Optional[int] = None,
                  offset: Optional[int] = None,
                  sort_column: Optional[int] = None,
                  sort_order: Optional[str] = None,
                  incomplete_filter: bool = False) -> List[Tuple]:
        """Charger les données avec filtres optionnels"""
        try:
            # Construction de la requête avec comptage des pièces
            headers_str = ', '.join(f'a.[{h}]' for h in Config.DB_HEADERS)
            query = f"""
                SELECT a.id, {headers_str}, 
                       COALESCE(p.pieces_count, 0) as pieces_count
                FROM appareils a
                LEFT JOIN (
                    SELECT appareil_id, COUNT(*) as pieces_count
                    FROM piece_associations
                    GROUP BY appareil_id
                ) p ON a.id = p.appareil_id
            """
            params = []
            conditions = []
            
            # Recherche globale pour load_data (avec support recherche avancée)
            if search_term:
                search_condition = self._build_search_condition(search_term)
                if search_condition:
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
    
    def count_data(self, search_term: Optional[str] = None, 
                   column_filters: Optional[Dict[int, str]] = None,
                   sort_column: Optional[int] = None,
                   sort_order: Optional[str] = None,
                   incomplete_filter: bool = False) -> int:
        """Compter le nombre total de lignes correspondant aux critères"""
        try:
            query = "SELECT COUNT(*) FROM appareils a"
            params = []
            conditions = []
            
            # Recherche globale pour count_data (avec support recherche avancée)
            if search_term:
                search_condition = self._build_search_condition(search_term)
                if search_condition:
                    # Si c'est une recherche regex, on ne peut pas compter précisément avec SQLite
                    # On retourne une estimation pour éviter l'erreur
                    if 'regex_filter' in search_condition:
                        # Pour les regex, retourner un count approximatif (total)
                        # Le vrai filtrage se fera côté Python
                        return self.cursor.execute("SELECT COUNT(*) FROM appareils").fetchone()[0]
                    else:
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
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors du comptage: {e}")
    
    def update_cell(self, db_id: int, column: str, value: str) -> bool:
        """Mettre à jour une cellule spécifique"""
        try:
            query = f"""
                UPDATE appareils 
                SET [{column}] = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """
            self.cursor.execute(query, (value, db_id))
            self.conn.commit()
            return True
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la mise à jour: {e}")
    
    def insert_appareil(self, data: Dict[str, Any]) -> int:
        """Insérer un nouvel appareil"""
        try:
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
            return self.cursor.lastrowid
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'insertion: {e}")
    
    def delete_appareils(self, ids: List[int]) -> int:
        """Supprimer des appareils par ID"""
        try:
            if not ids:
                return 0
            
            placeholders = ','.join('?' for _ in ids)
            query = f"DELETE FROM appareils WHERE id IN ({placeholders})"
            
            self.cursor.execute(query, ids)
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            
            return deleted_count
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la suppression: {e}")
    
    def delete_appareil(self, appareil_id: int) -> bool:
        """Supprimer un appareil par ID"""
        try:
            query = "DELETE FROM appareils WHERE id = ?"
            
            self.cursor.execute(query, [appareil_id])
            success = self.cursor.rowcount > 0
            self.conn.commit()
            
            return success
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la suppression: {e}")
    
    def check_duplicate_reference(self, ref: str, exclude_id: Optional[int] = None) -> bool:
        """Vérifier si une référence existe déjà"""
        try:
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
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la vérification des doublons: {e}")
    
    def clean_data(self) -> Dict[str, int]:
        """Nettoyer les données (supprimer vides et doublons)"""
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
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(f"Erreur lors du nettoyage: {e}")
    
    def get_pieces_for_appareil(self, appareil_id: int) -> List[Tuple]:
        """Récupérer les pièces associées à un appareil (nouvelle structure)"""
        try:
            query = """
                SELECT p.ref_piece, p.description 
                FROM pieces p
                JOIN piece_associations pa ON p.id = pa.piece_id
                WHERE pa.appareil_id = ?
                ORDER BY p.ref_piece
            """
            
            self.cursor.execute(query, (appareil_id,))
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des pièces: {e}")
    
    def get_pieces_count_for_appareil(self, appareil_id: int) -> int:
        """Récupérer le nombre de pièces associées à un appareil (nouvelle structure)"""
        try:
            query = """
                SELECT COUNT(*) 
                FROM piece_associations 
                WHERE appareil_id = ?
            """
            self.cursor.execute(query, (appareil_id,))
            result = self.cursor.fetchone()
            return result[0] if result else 0
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors du comptage des pièces: {e}")
    
    def add_piece(self, ref_piece: str, appareil_id: int, description: Optional[str] = None, confirm_callback=None) -> int:
        """Ajouter une pièce à un appareil (nouvelle structure)"""
        try:
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
                print(f"  📦 Pièce existante trouvée (ID: {piece_id})")
                
                # Gérer les conflits de description
                if clean_description and current_desc and clean_description != current_desc:
                    if confirm_callback:
                        print(f"  ⚠️ Conflit description: '{current_desc}' vs '{clean_description}'")
                        final_description = confirm_callback(ref_piece, current_desc, clean_description)
                        if final_description != current_desc:
                            self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (final_description, piece_id))
                            self.conn.commit()
                            print(f"  📝 Description mise à jour: '{final_description}'")
                    else:
                        print(f"  ⚠️ Conflit description ignoré: garde '{current_desc}'")
                elif clean_description and not current_desc:
                    # Ajouter description à une pièce sans description
                    self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (clean_description, piece_id))
                    self.conn.commit()
                    print(f"  📝 Description ajoutée: '{clean_description}'")
                    
            else:
                # Créer la nouvelle pièce
                print(f"  ✨ Nouvelle pièce: {ref_piece}")
                self.cursor.execute("INSERT INTO pieces (ref_piece, description) VALUES (?, ?)", (ref_piece, clean_description))
                piece_id = self.cursor.lastrowid
                self.conn.commit()
                print(f"  📦 Pièce créée (ID: {piece_id})")
            
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
            return assoc_id
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'ajout de la pièce: {e}")
    
    def add_or_update_piece_with_description(self, ref_piece: str, appareil_id: int, description: str = None, confirm_callback=None) -> tuple:
        """
        Ajouter une pièce ou mettre à jour sa description si elle existe déjà.
        NOUVELLE STRUCTURE: Une pièce = une référence + une description, associations séparées.
        Retourne: (assoc_id, description_updated)
        """
        try:
            # Nettoyer la description d'entrée
            clean_description = None
            if description:
                cleaned = str(description).strip()
                if cleaned:
                    clean_description = cleaned
            
            print(f"  🔍 Traitement {ref_piece} avec description: '{clean_description}'")
            description_updated = False
            
            # Étape 1: Vérifier si la pièce existe déjà
            piece_query = "SELECT id, description FROM pieces WHERE ref_piece = ?"
            piece_result = self.execute_query(piece_query, [ref_piece])
            
            if piece_result:
                # Pièce existante
                piece_id = piece_result[0][0]
                current_desc = piece_result[0][1]
                print(f"  📦 Pièce existante trouvée (ID: {piece_id})")
                
                # Gérer les conflits de description
                if clean_description and current_desc and clean_description != current_desc:
                    if confirm_callback:
                        final_description = confirm_callback(ref_piece, current_desc, clean_description)
                        if final_description != current_desc:
                            self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (final_description, piece_id))
                            self.conn.commit()
                            print(f"  📝 Description mise à jour: '{final_description}'")
                            description_updated = True
                    else:
                        print(f"  ⚠️ Conflit description ignoré: garde '{current_desc}'")
                elif clean_description and not current_desc:
                    # Ajouter description à une pièce sans description
                    self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?", (clean_description, piece_id))
                    self.conn.commit()
                    print(f"  📝 Description ajoutée: '{clean_description}'")
                    description_updated = True
                    
            else:
                # Nouvelle pièce
                print(f"  ✨ Nouvelle pièce: {ref_piece}")
                self.cursor.execute("INSERT INTO pieces (ref_piece, description) VALUES (?, ?)", (ref_piece, clean_description))
                piece_id = self.cursor.lastrowid
                self.conn.commit()
                print(f"  📦 Pièce créée (ID: {piece_id})")
            
            # Étape 2: Vérifier si l'association existe déjà
            assoc_query = "SELECT id FROM piece_associations WHERE piece_id = ? AND appareil_id = ?"
            assoc_result = self.execute_query(assoc_query, [piece_id, appareil_id])
            
            if assoc_result:
                # Association existante
                assoc_id = assoc_result[0][0]
                print(f"  🔗 Association existante (ID: {assoc_id})")
                return (assoc_id, description_updated)
            else:
                # Nouvelle association
                self.cursor.execute("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)", (piece_id, appareil_id))
                assoc_id = self.cursor.lastrowid
                self.conn.commit()
                print(f"  🔗 Association créée (ID: {assoc_id})")
                return (assoc_id, description_updated)
                
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'ajout/mise à jour de la pièce: {e}")
    
    def update_piece(self, ref_piece: str, description: str) -> bool:
        """Mettre à jour la description d'une pièce (nouvelle structure)"""
        try:
            query = "UPDATE pieces SET description = ? WHERE ref_piece = ?"
            self.cursor.execute(query, (description, ref_piece))
            self.conn.commit()
            return self.cursor.rowcount > 0
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la mise à jour de la pièce: {e}")
    
    def get_piece_info(self, ref_piece: str, appareil_id: int) -> Optional[Tuple[str, str]]:
        """Récupérer les informations d'une pièce spécifique (nouvelle structure)"""
        try:
            query = """
                SELECT p.ref_piece, p.description 
                FROM pieces p
                JOIN piece_associations pa ON p.id = pa.piece_id
                WHERE p.ref_piece = ? AND pa.appareil_id = ?
            """
            self.cursor.execute(query, (ref_piece, appareil_id))
            result = self.cursor.fetchone()
            return result if result else None
                
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des informations de la pièce: {e}")
    
    def delete_piece(self, ref_piece: str, appareil_id: int) -> bool:
        """Supprimer une pièce spécifique d'un appareil (nouvelle structure)"""
        try:
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
            return True
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la suppression de la pièce: {e}")
    
    def delete_pieces_by_appareil(self, appareil_id: int) -> int:
        """Supprimer toutes les pièces d'un appareil (nouvelle structure)"""
        try:
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
            return deleted_count
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la suppression des pièces: {e}")
    
    def delete_piece_from_multiple_appareils(self, ref_piece: str, appareil_ids: List[int]) -> int:
        """Supprimer une pièce de plusieurs appareils"""
        try:
            deleted_count = 0
            for appareil_id in appareil_ids:
                if self.delete_piece(ref_piece, appareil_id):
                    deleted_count += 1
            return deleted_count
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la suppression multiple de la pièce: {e}")
    
    def get_duplicate_ref_modeles(self) -> List[Tuple[str, int]]:
        """Récupérer les ref_modele en doublon avec leur nombre d'occurrences (recherche exacte uniquement)"""
        try:
            # Récupérer uniquement les doublons exacts
            query = Config.get_query('duplicate_refs')
            exact_duplicates = self.execute_custom_query(query)
            
            # Retourner sous forme de liste triée
            return sorted(exact_duplicates, key=lambda x: x[1], reverse=True)
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des doublons ref_modele: {e}")
    
    
    
    
    def get_devices_by_ref_modele(self, ref_modele: str) -> List[Tuple]:
        """Récupérer tous les appareils ayant exactement la même ref_modele"""
        try:
            # Récupérer uniquement les appareils avec la référence exacte
            query = """
                SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes
                FROM appareils 
                WHERE ref_modele = ?
                ORDER BY id
            """
            return self.execute_custom_query(query, [ref_modele])
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des appareils: {e}")
    

    def get_duplicate_references(self) -> List[Tuple[str, str, str, str, str, int]]:
        """Récupérer les références d'appareils en doublon (colonnes A,B,C,D,E identiques)"""
        try:
            query = """
                SELECT type, manufacturer, ref_modele, commercial_ref, other_ref, COUNT(*) as count 
                FROM appareils 
                GROUP BY type, manufacturer, ref_modele, commercial_ref, other_ref 
                HAVING COUNT(*) > 1
                ORDER BY count DESC, type, manufacturer, ref_modele, commercial_ref, other_ref
            """
            return self.execute_custom_query(query)
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des doublons: {e}")
    
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
    
    def get_duplicate_pieces_count(self) -> int:
        """Compter les références de pièces dupliquées (nouvelle structure)"""
        try:
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
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors du comptage des pièces dupliquées: {e}")
    
    def analyze_piece_duplicates(self) -> List[Tuple]:
        """Analyser les doublons de pièces en détail (nouvelle structure)"""
        try:
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
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'analyse des doublons: {e}")
    
    def get_categories(self) -> List[str]:
        """Récupérer toutes les catégories"""
        try:
            self.cursor.execute("SELECT name FROM categories ORDER BY name")
            return [row[0] for row in self.cursor.fetchall()]
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des catégories: {e}")
    
    def update_categories(self, categories: List[str]) -> bool:
        """Mettre à jour la liste des catégories"""
        try:
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
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la mise à jour des catégories: {e}")
    
    def validate_database(self) -> Dict[str, Any]:
        """Valider la cohérence de la base de données"""
        try:
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
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la validation: {e}")
    
    def get_export_data(self, search_term: str) -> List[Tuple]:
        """Récupérer les données pour l'export"""
        try:
            query = f"""
                SELECT a.{', '.join(f'[{h}]' for h in Config.DB_HEADERS[:5])}, p.ref_piece
                FROM appareils a
                LEFT JOIN piece_associations pa ON a.id = pa.appareil_id
                LEFT JOIN pieces p ON pa.piece_id = p.id
                WHERE {' OR '.join(f'[{h}] LIKE ?' for h in Config.DB_HEADERS)}
                OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece LIKE ?)
            """
            params = [f"%{search_term}%"] * (len(Config.DB_HEADERS) + 1)
            
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de la récupération des données d'export: {e}")
    
    def execute_custom_query(self, query: str, params: Optional[List] = None) -> List[Tuple]:
        """Exécuter une requête SQL personnalisée"""
        try:
            if params is None:
                params = []
            
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'exécution de la requête personnalisée: {e}")
    
    def execute_insert(self, query: str, params: Optional[List] = None) -> Optional[int]:
        """Exécuter une requête INSERT et retourner l'ID de la ligne insérée"""
        try:
            if params is None:
                params = []
            
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor.lastrowid
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(f"Erreur lors de l'exécution de la requête INSERT: {e}")
    
    def execute_query(self, query: str, params: Optional[List] = None) -> List[Tuple]:
        """Exécuter une requête SQL de lecture (SELECT)"""
        try:
            if params is None:
                params = []
            
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors de l'exécution de la requête SELECT: {e}")
    
    def close(self):
        """Fermer la connexion à la base de données"""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()