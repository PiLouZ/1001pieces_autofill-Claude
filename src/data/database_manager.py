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
from ..core.constants import DatabaseConfig
from ..core.logger import app_logger
from ..utils.error_handler import (
    handle_db_query_errors,
    handle_sqlite_column_errors, handle_database_errors,
    handle_database_operation_errors
)
from ._db_mixins import DatabaseError, with_query_lock as _with_query_lock
from ._db_mixins.fts5 import DatabaseFts5Mixin
from ._db_mixins.supersession import DatabaseSupersessionMixin
from ._db_mixins.setup import DatabaseSetupMixin
from ._db_mixins.autocompletion import DatabaseAutocompletionMixin

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config


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
        return hashlib.sha256(str(key_data).encode()).hexdigest()
    
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
    
    def clear(self):
        """Vider le cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    

class DatabaseManager(DatabaseFts5Mixin, DatabaseSupersessionMixin, DatabaseSetupMixin,
                      DatabaseAutocompletionMixin):
    """Gestionnaire centralisé pour toutes les opérations de base de données"""

    def __init__(self, db_file: str = None):
        import threading
        self.db_file = db_file or Config.DB_FILE
        self.conn = None
        self.cursor = None
        # Verrou RÉENTRANT pour sérialiser les accès au curseur partagé entre threads
        # (prefetch_worker, _ImportWorker et thread principal partagent self.cursor).
        # RLock et non Lock : certaines méthodes verrouillées s'appellent entre elles
        # (ex: load_data → execute_query) — un Lock simple provoquerait un deadlock.
        self._query_lock = threading.RLock()
        # Phase 3: Initialiser le cache de recherche optimisé
        self.search_cache = SearchCache(Config.SEARCH_CACHE_SIZE) if Config.FULLTEXT_CACHE_ENABLED else None
        # Cache du COUNT total (sans filtre) — invalide uniquement sur insert/delete
        self._total_count_cache: Optional[int] = None
        # Phase 2.3: Initialiser le service d'invalidation de cache (import local pour éviter cycle)
        from ..services.search_cache_service import SearchCacheInvalidationService
        self.cache_invalidation = SearchCacheInvalidationService(self)
        self._connect()
        self._setup_database()
        self._activer_cles_etrangeres()

    def _activer_cles_etrangeres(self):
        """Activer les clés étrangères, APRÈS les migrations de `_setup_database`.

        L'ordre compte : trois migrations de l'ancien schéma (setup.py) font
        `DROP TABLE pieces` / `piece_associations`. Clés actives, un DROP TABLE
        vide d'abord la table et déclenche les `ON DELETE CASCADE` — toutes les
        associations partiraient avec. Elles ne tournent plus sur le schéma
        actuel, mais activer après elles écarte le risque.

        Sans effet dans une transaction ouverte : on valide d'abord ce que les
        migrations auraient laissé en cours."""
        if not Config.FOREIGN_KEYS:
            return
        if self.conn.in_transaction:
            self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        actives = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        if not actives:
            app_logger.warning("Clés étrangères demandées mais non activées par SQLite")

    @handle_database_errors(title="Erreur de connexion")
    def _connect(self):
        """Établir la connexion à la base de données"""
        # check_same_thread=False : autorise l'usage depuis plusieurs threads.
        # La sécurité est assurée par _query_lock dans load_data() (accès sérialisé).
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()

        # Réglages de performance par connexion (sans effet sur le format du fichier) :
        # - synchronous=NORMAL : réglage recommandé avec WAL (déjà actif sur cette base),
        #   réduit les fsync ; la cohérence reste garantie par le journal WAL
        # - cache_size négatif = taille en Kio (64 Mo de cache de pages)
        # - temp_store=MEMORY : tris/index temporaires en RAM plutôt que sur disque
        # - mmap_size : lecture du fichier (~840 Mo) via mémoire mappée (256 Mo)
        self.cursor.execute("PRAGMA synchronous=NORMAL")
        self.cursor.execute(f"PRAGMA cache_size={DatabaseConfig.SQLITE_CACHE_SIZE_KIB}")
        self.cursor.execute("PRAGMA temp_store=MEMORY")
        self.cursor.execute(f"PRAGMA mmap_size={DatabaseConfig.SQLITE_MMAP_SIZE_BYTES}")

    def get_connection(self):
        """Retourner la connexion pour les opérations batch"""
        return self.conn

    def _piece_association_subquery(self, op: str = "LIKE", alias: str = "a") -> str:
        """Condition SQL paramétrée : l'appareil possède une pièce associée
        dont ref_piece correspond (op = "=" ou "LIKE").

        Factorise la sous-requête piece_associations dupliquée à de
        nombreux endroits dans les conditions de recherche.
        """
        return (
            f"{alias}.id IN (SELECT pa.appareil_id FROM piece_associations pa "
            f"WHERE pa.piece_id IN (SELECT id FROM pieces WHERE ref_piece {op} ?))"
        )

    def _get_incomplete_condition(self, alias: str = "a") -> str:
        """Condition SQL : l'appareil a un type et/ou un fabricant manquant ou vide.

        Factorise le pattern dupliqué dans load_data, count_data et
        get_export_data (filtre "lignes incomplètes").
        """
        return (
            f"({alias}.[type] IS NULL OR {alias}.[type] = '' "
            f"OR {alias}.[manufacturer] IS NULL OR {alias}.[manufacturer] = '')"
        )

    def _build_search_condition_optimized(self, search_term):
        """Construire la condition SQL de recherche.

        Aiguillage sur deux axes : le type d'entrée (chaîne, ou dict simple /
        and / or) et le mode `Config.SEARCH_PIECES_ONLY`. Chaque type délègue à
        une méthode dédiée, qui gère elle-même ses deux modes.

        Si Config.USE_FTS5=True et SEARCH_PIECES_ONLY=False, délègue à
        build_fts5_condition(). Fallback automatique sur LIKE si le type de
        recherche n'est pas supporté par FTS5 (regex, groupes imbriqués).

        Le SQL produit est figé par tests/unit/test_search_condition_characterization.py
        (176 points de mesure) : toute modification y devient visible.
        """
        # Branche FTS5 — activée uniquement si USE_FTS5=True ET SEARCH_PIECES_ONLY=False.
        # L'index FTS5 couvre les colonnes d'appareils uniquement ; quand on recherche
        # dans pieces.ref_piece, FTS5 n'est pas applicable → fallback LIKE pièces.
        if self.fts5_utilisable():
            fts_condition = self.build_fts5_condition(search_term)
            if fts_condition is not None:
                return fts_condition
            # Fallback silencieux sur LIKE pour les types non supportés

        if isinstance(search_term, str):
            return self._condition_depuis_chaine(search_term)

        if not search_term:
            return None

        constructeurs = {
            'simple': self._condition_simple,
            'and':    self._condition_et,
            'or':     self._condition_ou,
        }
        constructeur = constructeurs.get(search_term.get('type', 'simple'))
        return constructeur(search_term) if constructeur else None

    # ─── Briques de construction des conditions ──────────────────────────────

    def _condition_terme_toutes_colonnes(self, terme):
        """Le terme recherché dans TOUTES les colonnes d'appareil, ou dans la
        référence d'une pièce associée.

        Brique de base du mode LIKE : ce bloc était écrit à l'identique en cinq
        endroits de la construction des conditions.

        Returns:
            (condition SQL, liste de paramètres)
        """
        conditions = [f"a.[{h}] LIKE ?" for h in Config.DB_HEADERS]
        conditions.append(self._piece_association_subquery("LIKE"))
        return (
            f"({' OR '.join(conditions)})",
            [f"%{terme}%"] * (len(Config.DB_HEADERS) + 1),
        )

    @staticmethod
    def _operateur_correspondance(extend_search):
        """Opérateur SQL selon le mode : correspondance exacte, ou partielle."""
        return "LIKE" if extend_search else "="

    @staticmethod
    def _parametre_correspondance(terme, extend_search):
        """Paramètre associé à l'opérateur de correspondance."""
        return f"%{terme}%" if extend_search else terme

    # ─── Un constructeur par type de recherche ───────────────────────────────

    def _condition_depuis_chaine(self, search_term):
        """Recherche simple passée en chaîne (ancienne API)."""
        if not search_term.strip():
            return None

        term = search_term.strip()

        # Phase 5: Recherche uniquement dans les pièces associées (avec supersession)
        if Config.SEARCH_PIECES_ONLY:
            return self._build_pieces_only_condition(term)  # string path — pas de bypass possible

        # Recherche LIKE classique (plus lente).
        # Note : les paramètres sont construits depuis search_term NON trimmé,
        # contrairement à la branche pieces_only ci-dessus qui utilise term.
        # Incohérence d'origine, conservée telle quelle et figée par les tests
        # de caractérisation (cas « chaine_avec_espaces »).
        condition, _ = self._condition_terme_toutes_colonnes(term)
        return {
            'query_type': 'like',
            'condition': condition,
            'params': [f"%{search_term}%"] * (len(Config.DB_HEADERS) + 1),
        }

    def _condition_simple(self, search_term):
        """Recherche avancée à terme unique."""
        terms = search_term.get('terms', [])
        if not terms:
            return None

        term = terms[0]

        # Phase 5: Recherche uniquement dans les pièces associées (avec supersession)
        if Config.SEARCH_PIECES_ONLY:
            extra_refs = list(search_term.get('expand_predecessors', []))
            for r in search_term.get('expand_equivalents', []):
                if r not in extra_refs:
                    extra_refs.append(r)
            return self._build_pieces_only_condition(
                term,
                bypass=search_term.get('bypass_supersession', False),
                extra_refs=extra_refs,
                extend_search=search_term.get('extend_search', False),
            )

        condition, params = self._condition_terme_toutes_colonnes(term)
        return {'condition': condition, 'params': params}

    def _condition_et(self, search_term):
        """Recherche AND (&&) : tous les termes doivent être trouvés."""
        terms = search_term.get('terms', [])
        if not terms:
            return None

        # Phase 5: Recherche uniquement dans les pièces associées
        if Config.SEARCH_PIECES_ONLY:
            extend_search = search_term.get('extend_search', False)
            op = self._operateur_correspondance(extend_search)
            return {
                'query_type': 'pieces_only',
                'condition': f"({' AND '.join(self._piece_association_subquery(op) for _ in terms)})",
                'params': [self._parametre_correspondance(t, extend_search) for t in terms],
            }

        conditions, params = [], []
        for term in terms:
            # Chaque terme doit être trouvé dans au moins une colonne
            condition_terme, params_terme = self._condition_terme_toutes_colonnes(term)
            conditions.append(condition_terme)
            params.extend(params_terme)

        if not conditions:
            return None
        return {'condition': f"({' AND '.join(conditions)})", 'params': params}

    def _condition_ou(self, search_term):
        """Recherche OR : groupes combinés, chaque groupe étant simple ou AND."""
        groups = search_term.get('groups', [])
        if not groups:
            return None

        # Phase 5: Recherche uniquement dans les pièces associées
        if Config.SEARCH_PIECES_ONLY:
            return self._condition_ou_pieces_only(
                groups, search_term.get('extend_search', False))

        conditions, params = [], []
        for group in groups:
            terms = group.get('terms', [])
            if not terms:
                continue

            if group['type'] == 'and':
                # Groupe AND : tous les termes doivent être présents
                sous_conditions = []
                for term in terms:
                    condition_terme, params_terme = self._condition_terme_toutes_colonnes(term)
                    sous_conditions.append(condition_terme)
                    params.extend(params_terme)
                if sous_conditions:
                    conditions.append(f"({' AND '.join(sous_conditions)})")

            elif group['type'] == 'simple':
                # Groupe simple : premier terme recherché dans toutes les colonnes
                condition_terme, params_terme = self._condition_terme_toutes_colonnes(terms[0])
                conditions.append(condition_terme)
                params.extend(params_terme)

        if not conditions:
            return None
        return {'condition': f"({' OR '.join(conditions)})", 'params': params}

    def _condition_ou_pieces_only(self, groups, extend_search):
        """Variante pieces_only de la recherche OR."""
        op = self._operateur_correspondance(extend_search)
        conditions, params = [], []

        for group in groups:
            terms = group.get('terms', [])
            if not terms:
                continue

            if group['type'] == 'and':
                conditions.append(
                    f"({' AND '.join(self._piece_association_subquery(op) for _ in terms)})")
                params.extend(self._parametre_correspondance(t, extend_search) for t in terms)
            else:  # simple
                conditions.append(self._piece_association_subquery(op))
                params.append(self._parametre_correspondance(terms[0], extend_search))

        if not conditions:
            return None
        return {
            'query_type': 'pieces_only',
            'condition': f"({' OR '.join(conditions)})",
            'params': params,
        }

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
    
    # ── Setup & Migrations → voir src/data/_db_mixins/setup.py ─────────────

    # ── Supersession & Équivalences → voir src/data/_db_mixins/supersession.py ─

    # ── FTS5 Full-Text Search → voir src/data/_db_mixins/fts5.py ────────────
    
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
        return hashlib.sha256(str(key).encode()).hexdigest()

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
            conditions, params = self._build_load_conditions(search_term, column_filters, incomplete_filter)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += self._build_load_order_by(sort_column, sort_order)
            
            # Ajouter LIMIT et OFFSET pour la pagination
            if limit:
                query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
            
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Erreur lors du chargement des données: {e}")
    
    def _build_load_conditions(self, search_term: Optional[str],
                               column_filters: Optional[Dict[int, str]],
                               incomplete_filter: bool) -> Tuple[List[str], List]:
        """Conditions WHERE (et leurs paramètres) du périmètre affiché à l'écran :
        recherche, filtres de colonne, filtre « lignes incomplètes ».

        Partagées par _load_data_original (les pages) et find_incomplete_position
        (le saut ▲/▼) : une seule source, donc la position calculée en SQL
        désigne forcément une ligne de la page qui sera affichée.
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
                        condition = f"(a.ref_modele = ? OR a.commercial_ref = ? OR a.other_ref = ?) OR {self._piece_association_subquery('=')}"
                    else:  # prefix
                        condition = f"(a.ref_modele LIKE ? OR a.commercial_ref LIKE ? OR a.other_ref LIKE ?) OR {self._piece_association_subquery('LIKE')}"

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
            conditions.append(self._get_incomplete_condition())

        return conditions, params

    @staticmethod
    def _build_load_order_by(sort_column: Optional[int], sort_order: Optional[str]) -> str:
        """Clause ORDER BY des pages affichées.

        Tri par colonne : départagé par a.id dans le même sens. Les ex-æquo
        (des milliers d'appareils partagent un même Type) ont ainsi un ordre
        stable, identique entre les pages (LIMIT/OFFSET) et le calcul de
        position de find_incomplete_position. Sur les colonnes indexées c'est
        déjà l'ordre de lecture de l'index (valeur puis rowid) : même résultat,
        même plan. Seul le tri sans index (Notes) y gagne un ordre déterministe.
        """
        order = "ASC" if sort_order == "ASC" else "DESC"
        if sort_column is not None and 0 <= sort_column < len(Config.DB_HEADERS):
            return f" ORDER BY a.[{Config.DB_HEADERS[sort_column]}] {order}, a.id {order}"
        if sort_column is not None and sort_column == len(Config.DB_HEADERS):
            # Tri par nombre de pièces (dernière colonne)
            return f" ORDER BY pieces_count {order}"
        return " ORDER BY a.id DESC"  # Tri par défaut

    def find_incomplete_position(self, search_term: Optional[str],
                                 column_filters: Optional[Dict[int, str]],
                                 sort_column: Optional[int], sort_order: Optional[str],
                                 incomplete_filter: bool,
                                 from_position: int, direction: str) -> Optional[int]:
        """Position (0-based, dans l'ordre exact de l'écran) de la prochaine ligne
        incomplète — Type ou Fabricant vide — strictement après (direction
        'down') ou avant ('up') from_position. None si aucune.

        ROW_NUMBER() numérote le périmètre affiché avec le même WHERE et le même
        ORDER BY que les pages : la ligne cible est à la page
        position // taille_page, rang position % taille_page. Une requête au lieu
        d'un chargement de chaque page traversée (~0,8 s contre ~10 s sur
        700 000 appareils sans filtre).

        Le tri « Nb pièces » est refusé (ValueError) : son ORDER BY porte sur une
        sous-requête corrélée, la calculer pour toute la base coûterait plus cher
        que le parcours de pages que l'appelant garde en repli.

        Pas de décorateur « retourner None si erreur » : None signifie « aucune
        ligne », ce qui grisera la flèche. Une erreur doit au contraire remonter
        pour que l'appelant retombe sur le parcours de pages.
        """
        if sort_column is not None and sort_column == len(Config.DB_HEADERS):
            raise ValueError("tri « Nb pièces » non pris en charge")
        conditions, params = self._build_load_conditions(search_term, column_filters, incomplete_filter)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        order_by = self._build_load_order_by(sort_column, sort_order)[len(" ORDER BY "):]
        if direction == 'down':
            comparison, pick = "pos > ?", "ORDER BY pos ASC"
        else:
            comparison, pick = "pos < ?", "ORDER BY pos DESC"
        query = f"""
            SELECT pos FROM (
                SELECT ROW_NUMBER() OVER (ORDER BY {order_by}) - 1 AS pos,
                       {self._get_incomplete_condition()} AS incomplete
                FROM appareils a{where}
            )
            WHERE incomplete AND {comparison}
            {pick} LIMIT 1
        """
        with self._query_lock:
            row = self.cursor.execute(query, params + [from_position]).fetchone()
        return row[0] if row else None

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
                        condition = f"(ref_modele = ? OR commercial_ref = ? OR other_ref = ?) OR {self._piece_association_subquery('=')}"
                    else:  # prefix
                        condition = f"(ref_modele LIKE ? OR commercial_ref LIKE ? OR other_ref LIKE ?) OR {self._piece_association_subquery('LIKE')}"

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
            incomplete_condition = self._get_incomplete_condition()
            conditions.append(incomplete_condition)

        # Ajouter les conditions
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Note: Le tri n'affecte pas le comptage, donc on ignore sort_column et sort_order
        self.cursor.execute(query, params)
        return self.cursor.fetchone()[0]
    
    @_with_query_lock
    @handle_db_query_errors(return_value=0, log_prefix="Erreur comptage appareils incomplets")
    def count_incomplete_devices(self) -> int:
        """Compter le nombre d'appareils où colonne A et/ou B est vide"""
        query = f"""
        SELECT COUNT(*) FROM appareils a
        WHERE {self._get_incomplete_condition()}
        """
        self.cursor.execute(query)
        return self.cursor.fetchone()[0]
    
    def update_cell(self, db_id: int, column: str, value: str) -> bool:
        """Mettre à jour une cellule spécifique"""
        result = self._safe_update_cell(db_id, column, value)
        if not result:
            raise DatabaseError(f"Erreur lors de la mise à jour de la cellule {column}")
        return result

    @_with_query_lock
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

    @_with_query_lock
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

    @_with_query_lock
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

    @_with_query_lock
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
            app_logger.info(f"[OK] {deleted_count} appareil(s) supprimé(s) avec {associations_deleted} association(s) de pièce(s)")
        elif deleted_count > 0:
            app_logger.info(f"[OK] {deleted_count} appareil(s) supprimé(s) (aucune association de pièce)")

        # Phase 2.3: Invalider le cache après suppression d'appareils
        if deleted_count > 0 and hasattr(self, 'cache_invalidation'):
            self.cache_invalidation.invalidate_after_device_modification("suppression", deleted_count)

        return deleted_count
    
    def delete_appareil(self, appareil_id: int) -> bool:
        """Supprimer un appareil par ID et toutes ses associations de pièces"""
        return self._safe_delete_appareil(appareil_id)

    @_with_query_lock
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

    def get_pieces_for_appareil(self, appareil_id: int) -> List[Tuple]:
        """Récupérer les pièces associées à un appareil (nouvelle structure)"""
        return self._safe_get_pieces_for_appareil(appareil_id)

    @_with_query_lock
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
    
    @_with_query_lock
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

    @_with_query_lock
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

    @_with_query_lock
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

            # Promouvoir la ref fantôme en pièce réelle si nécessaire
            self.cursor.execute(
                "UPDATE pieces SET is_phantom = 0 WHERE id = ? AND is_phantom = 1",
                (piece_id,)
            )

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

    @_with_query_lock
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur ajout/mise à jour pièce")
    def _safe_add_or_update_piece_with_description(self, ref_piece: str, appareil_id: int, description: str = None, confirm_callback=None) -> tuple:
        """Helper sécurisé pour ajouter ou mettre à jour une pièce avec description"""
        # Nettoyer la description d'entrée
        clean_description = None
        if description:
            cleaned = str(description).strip()
            if cleaned:
                clean_description = cleaned

        # Appelé une fois par association pièce↔appareil : sur un import de plusieurs
        # milliers de lignes, ce seul message pesait des dizaines de milliers de
        # lignes de log. Le total est journalisé par l'appelant (v3.66.0).
        if Config.LOG_VERBOSE_PER_DEVICE:
            app_logger.debug(f"   Traitement {ref_piece} avec description: '{clean_description}'")
        description_updated = False

        # Étape 1: Vérifier si la pièce existe déjà
        piece_query = "SELECT id, description FROM pieces WHERE ref_piece = ?"
        piece_result = self.execute_query(piece_query, [ref_piece])

        if piece_result:
            # Pièce existante
            piece_id = piece_result[0][0]
            current_desc = piece_result[0][1]

            # Promouvoir la ref fantôme en pièce réelle si nécessaire
            self.cursor.execute(
                "UPDATE pieces SET is_phantom = 0 WHERE id = ? AND is_phantom = 1",
                (piece_id,)
            )

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
    



    def rename_piece_catalog(self, old_ref_piece: str, new_ref_piece: str, description: str) -> bool:
        """Renommer une pièce du catalogue (référence + description).

        Retourne False si new_ref_piece existe déjà (et diffère de old_ref_piece) :
        l'appelant doit alors avertir l'utilisateur sans rien modifier.
        """
        return self._safe_rename_piece_catalog(old_ref_piece, new_ref_piece, description)

    @_with_query_lock
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur renommage pièce catalogue")
    def _safe_rename_piece_catalog(self, old_ref_piece: str, new_ref_piece: str, description: str) -> bool:
        """Helper sécurisé pour renommer une pièce du catalogue.

        Le renommage doit propager aux tables qui désignent la pièce par sa
        RÉFÉRENCE TEXTE — `piece_supersessions` et `piece_equivalence_groups` —
        sans quoi elles pointent vers une référence qui n'existe plus.
        `piece_associations` n'est pas concernée : elle pointe par `piece_id`.

        Les FOREIGN KEY vers `pieces(ref_piece)` ne couvrent que `ON DELETE` (pas
        de `ON UPDATE CASCADE`). Clés actives (`Config.FOREIGN_KEYS`), mettre à
        jour la pièce avant ses relations violerait la contrainte le temps d'une
        instruction : la vérification est donc différée jusqu'au COMMIT, où tout
        est de nouveau cohérent.

        Cas réel du 2026-09-10 : une succession importée avec une coquille
        (`2080942408 → 96001828`) puis corrigée par renommage de la pièce en
        `960018281` laissait la succession pointer vers `96001828`, disparue.
        L'export de `2080942408` suivait la chaîne dans le vide et échouait.
        """
        if new_ref_piece != old_ref_piece:
            existing = self.execute_query("SELECT id FROM pieces WHERE ref_piece = ?", [new_ref_piece])
            if existing:
                return False

        try:
            # Remis à OFF automatiquement au COMMIT ou au ROLLBACK : ne vaut que
            # pour ce renommage.
            self.cursor.execute("PRAGMA defer_foreign_keys=ON")
            self.cursor.execute(
                "UPDATE pieces SET ref_piece = ?, description = ? WHERE ref_piece = ?",
                (new_ref_piece, description, old_ref_piece)
            )

            if new_ref_piece != old_ref_piece:
                self.cursor.execute(
                    "UPDATE piece_supersessions SET ref_old = ? WHERE ref_old = ?",
                    (new_ref_piece, old_ref_piece))
                self.cursor.execute(
                    "UPDATE piece_supersessions SET ref_new = ? WHERE ref_new = ?",
                    (new_ref_piece, old_ref_piece))
                self.cursor.execute(
                    "UPDATE piece_equivalence_groups SET ref_piece = ? WHERE ref_piece = ?",
                    (new_ref_piece, old_ref_piece))
                # Une succession devenue réflexive (X → X) n'a aucun sens : elle
                # apparaît si l'on renomme une pièce vers sa propre remplaçante.
                self.cursor.execute(
                    "DELETE FROM piece_supersessions WHERE ref_old = ref_new")

            self.conn.commit()
            return True

        except sqlite3.IntegrityError:
            # `ref_old` est clé primaire de piece_supersessions, et
            # (group_id, ref_piece) celle de piece_equivalence_groups : la
            # référence cible peut déjà porter une relation orpheline. Tout
            # annuler plutôt que renommer la pièce en abandonnant ses relations.
            # (Une clé étrangère encore violée au COMMIT différé arrive ici aussi.)
            self.conn.rollback()
            app_logger.warning(
                f"Renommage '{old_ref_piece}' → '{new_ref_piece}' annulé : la "
                f"référence cible porte déjà une succession ou une équivalence")
            return False

    def create_piece_standalone(self, ref_piece: str, description: str = None) -> bool:
        """Créer une pièce orpheline dans le catalogue (sans association d'appareils).
        Retourne False si la référence existe déjà."""
        return self._safe_create_piece_standalone(ref_piece, description)

    @_with_query_lock
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur création pièce catalogue")
    def _safe_create_piece_standalone(self, ref_piece: str, description: str = None) -> bool:
        """Helper sécurisé pour créer une pièce orpheline dans le catalogue."""
        existing = self.execute_query("SELECT id FROM pieces WHERE ref_piece = ?", [ref_piece])
        if existing:
            return False
        clean_desc = description.strip() if description and description.strip() else None
        self.cursor.execute(
            "INSERT INTO pieces (ref_piece, description) VALUES (?, ?)",
            (ref_piece, clean_desc)
        )
        self.conn.commit()
        return True

    def delete_piece_catalog(self, ref_piece: str, commit: bool = True) -> None:
        """Supprimer une pièce du catalogue (toutes ses associations puis la pièce elle-même)."""
        return self._safe_delete_piece_catalog(ref_piece, commit)

    @_with_query_lock
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur suppression pièce catalogue")
    def _safe_delete_piece_catalog(self, ref_piece: str, commit: bool = True) -> None:
        """Helper sécurisé pour supprimer une pièce du catalogue (sans commit si appelée en boucle).

        Trou jumeau de celui du renommage : le schéma déclare bien
        `ON DELETE CASCADE` sur `piece_supersessions.ref_old` et
        `piece_equivalence_groups.ref_piece`, et `ON DELETE SET NULL` sur
        `piece_supersessions.ref_new` — mais `PRAGMA foreign_keys` n'a été activé
        qu'en v3.85.0, et reste désactivable (`Config.FOREIGN_KEYS`). Les ordres
        explicites ci-dessous ne dépendent donc pas des clauses : sans eux,
        clés désactivées, les relations pointeraient dans le vide.

        Ces ordres suppriment la ligne des deux côtés (`ref_old` comme `ref_new`).
        C'est le seul comportement valable sur les DEUX schémas rencontrés : le code
        crée `ref_new TEXT NOT NULL` (supersession.py) tandis que les bases anciennes
        le portent nullable — `CREATE TABLE IF NOT EXISTS` ne les fera jamais
        converger. Passer `ref_new` à NULL lèverait donc une contrainte sur toute
        base neuve. L'information « cette pièce est obsolète » n'est pas perdue pour
        autant : elle vit dans `pieces.is_obsolete`, indépendamment de cette table.
        """
        self.cursor.execute(
            "DELETE FROM piece_associations WHERE piece_id IN (SELECT id FROM pieces WHERE ref_piece = ?)",
            [ref_piece]
        )
        self.cursor.execute(
            "DELETE FROM piece_supersessions WHERE ref_old = ? OR ref_new = ?",
            [ref_piece, ref_piece])
        self.cursor.execute("DELETE FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_piece])
        self.cursor.execute("DELETE FROM pieces WHERE ref_piece = ?", [ref_piece])
        if commit:
            self.conn.commit()

    
    def delete_piece(self, ref_piece: str, appareil_id: int) -> bool:
        """Supprimer une pièce spécifique d'un appareil (nouvelle structure)"""
        return self._safe_delete_piece(ref_piece, appareil_id)

    @_with_query_lock
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


    
    def get_duplicate_ref_modeles(self) -> List[Tuple[str, int]]:
        """Récupérer les ref_modele en doublon avec leur nombre d'occurrences (recherche exacte uniquement)"""
        return self._safe_get_duplicate_ref_modeles()

    @_with_query_lock
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

    

    
    @_with_query_lock
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
    
    @_with_query_lock
    @handle_database_errors(title="Erreur récupération catégories")
    def get_categories(self) -> List[str]:
        """Récupérer toutes les catégories"""
        self.cursor.execute("SELECT name FROM categories ORDER BY name")
        return [row[0] for row in self.cursor.fetchall()]

    @_with_query_lock
    @handle_database_errors(title="Erreur récupération valeurs colonne")
    def get_column_values(self, db_field: str) -> List[str]:
        """Récupérer les valeurs distinctes d'un champ de la table appareils.

        db_field doit être un champ validé via _get_db_field_name() —
        jamais une entrée utilisateur directe (prévient les injections SQL).
        """
        query = Config.get_query('autocomplete_field', field=db_field)
        self.cursor.execute(query)
        return [row[0] for row in self.cursor.fetchall() if row[0]]
    
    @_with_query_lock
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
    
    
    @_with_query_lock
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
            search_condition = self._build_search_condition_optimized(parsed_search)
            if search_condition:
                # Phase 3: Gérer les requêtes optimisées (éviter erreur "near SELECT")
                if search_condition.get('query_type') in ['exact', 'prefix']:
                    # Pour les requêtes optimisées, extraire juste la condition WHERE
                    if search_condition['query_type'] == 'exact':
                        condition = f"(a.ref_modele = ? OR a.commercial_ref = ? OR a.other_ref = ?) OR {self._piece_association_subquery('=')}"
                    else:  # prefix
                        condition = f"(a.ref_modele LIKE ? OR a.commercial_ref LIKE ? OR a.other_ref LIKE ?) OR {self._piece_association_subquery('LIKE')}"

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
            incomplete_condition = self._get_incomplete_condition()
            conditions.append(incomplete_condition)

        # Ajouter les conditions WHERE si nécessaire
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    @_with_query_lock
    @handle_database_errors(title="Erreur requête personnalisée")
    def execute_custom_query(self, query: str, params: Optional[List] = None) -> List[Tuple]:
        """Exécuter une requête SQL personnalisée — **lecture uniquement**.

        Cette méthode n'appelle pas `commit()` : une écriture passée par ici
        reste dans la transaction implicite ouverte par sqlite3 et se perd si
        l'application se ferme avant qu'autre chose ne commit. Le piège est
        sournois parce que l'écriture est bien visible depuis cette connexion.
        Pour écrire, utiliser `execute_write` ou `execute_write_batch`.
        """
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

        # Curseur partagé : sérialiser avec les autres threads (P5 thread-safety)
        with self._query_lock:
            try:
                self.cursor.execute(query, params)
                self.conn.commit()
                return self.cursor.lastrowid
            except Exception as e:
                self.conn.rollback()
                raise
    
    def execute_write(self, query: str, params: Optional[List] = None) -> int:
        """Exécuter une écriture SQL (INSERT/UPDATE/DELETE) **et la rendre durable**.

        À utiliser partout où `execute_custom_query` servait à écrire : cette
        dernière n'appelle jamais `commit()`. La connexion étant ouverte sans
        `isolation_level`, le module sqlite3 ouvre une transaction implicite dès
        le premier DML — l'écriture est visible depuis la même connexion, donc
        depuis l'interface, mais perdue si l'application se ferme avant qu'une
        autre opération ne commit. Le symptôme est intermittent : n'importe
        quelle écriture ultérieure valide la transaction au passage, si bien que
        l'opération paraît fonctionner la plupart du temps.

        Returns: nombre de lignes affectées, ou -1 si l'écriture a échoué.
        """
        return self._safe_execute_write(query, params)

    @handle_database_operation_errors(return_value=-1, log_prefix="Erreur exécution écriture")
    def _safe_execute_write(self, query: str, params: Optional[List] = None) -> int:
        """Helper sécurisé pour exécuter une écriture SQL durable"""
        if params is None:
            params = []

        # Curseur partagé : sérialiser avec les autres threads (P5 thread-safety)
        with self._query_lock:
            try:
                self.cursor.execute(query, params)
                affectees = self.cursor.rowcount
                self.conn.commit()
                return affectees
            except Exception:
                self.conn.rollback()
                raise

    def execute_write_batch(self, operations: List[Tuple]) -> bool:
        """Exécuter plusieurs écritures en **une seule transaction**.

        Pour les opérations dont les étapes n'ont pas de sens isolément — une
        fusion d'appareils transfère les associations *puis* supprime le
        doublon : commiter chaque étape séparément laisserait, en cas d'échec au
        milieu, un appareil supprimé dont les pièces n'ont pas été transférées.

        Args:
            operations: liste de (requête, paramètres). Les paramètres peuvent
                        être None pour une requête sans argument.

        Returns: True si toutes les écritures ont été commitées.
        """
        return self._safe_execute_write_batch(operations)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur exécution lot d'écritures")
    def _safe_execute_write_batch(self, operations: List[Tuple]) -> bool:
        """Helper sécurisé pour exécuter un lot d'écritures atomique"""
        if not operations:
            return True

        with self._query_lock:
            try:
                for query, params in operations:
                    self.cursor.execute(query, list(params) if params else [])
                self.conn.commit()
                return True
            except Exception:
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

        # Curseur partagé : sérialiser avec les autres threads (P5 thread-safety)
        with self._query_lock:
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
    
    @_with_query_lock
    def lire_appareils_pour_import(self) -> List[Tuple]:
        """Lit tous les appareils référencés, pour le cache de dédoublonnage de l'import.

        À la différence d'execute_query, une erreur SQLite N'EST PAS avalée : elle
        remonte en DatabaseError. Un [] silencieux ferait croire à l'import que la
        base est vide, et chaque ligne importée deviendrait un nouvel appareil
        (la table appareils n'a aucune contrainte d'unicité pour l'en empêcher).
        """
        try:
            self.cursor.execute(Config.QUERIES['preload_all_devices'])
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            raise DatabaseError(f"Lecture des appareils existants impossible : {e}") from e

    # Lots sous la limite historique de 999 paramètres par requête SQLite.
    _TAILLE_LOT_IDS = 900

    @_with_query_lock
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur lecture appareils par id")
    def lire_appareils_par_id(self, db_ids) -> Optional[Dict[int, Tuple]]:
        """Lit Type, Fabricant et références d'appareils désignés par id.

        Returns:
            {id: (type, manufacturer, ref_modele, commercial_ref)} — un id absent
            du résultat n'existe plus en base. None si la lecture a échoué
            (à la différence d'execute_query, qui renverrait [] dans les deux cas).
        """
        ids = list(dict.fromkeys(db_ids))
        out = {}
        for debut in range(0, len(ids), self._TAILLE_LOT_IDS):
            lot = ids[debut:debut + self._TAILLE_LOT_IDS]
            marqueurs = ",".join("?" * len(lot))
            self.cursor.execute(
                "SELECT id, type, manufacturer, ref_modele, commercial_ref "
                f"FROM appareils WHERE id IN ({marqueurs})", lot)
            for row in self.cursor.fetchall():
                out[row[0]] = tuple(row[1:])
        return out

    def compter_types_par_piece(self, refs_pieces) -> Dict[str, Dict[str, int]]:
        """Nombre d'appareils typés par type, pour chaque référence de pièce.

        Returns:
            {ref_piece: {type: nombre d'appareils}} — les pièces sans appareil
            typé sont absentes. {} si la lecture échoue (execute_query l'avale).
        """
        refs = sorted(set(refs_pieces))
        out: Dict[str, Dict[str, int]] = {}
        for debut in range(0, len(refs), 500):
            lot = refs[debut:debut + 500]
            marqueurs = ','.join('?' * len(lot))
            rows = self.execute_query(
                f"""SELECT p.ref_piece, TRIM(a.type), COUNT(*)
                    FROM pieces p
                    JOIN piece_associations pa ON pa.piece_id = p.id
                    JOIN appareils a ON a.id = pa.appareil_id
                    WHERE p.ref_piece IN ({marqueurs})
                      AND COALESCE(TRIM(a.type), '') <> ''
                    GROUP BY p.ref_piece, TRIM(a.type)""", lot) or []
            for ref, type_app, n in rows:
                out.setdefault(ref, {})[type_app] = n
        return out

    # Une pièce portée par plus d'appareils que cela (joint, courroie…) va sur tous
    # les types : elle ne vote pas. Mesure 2026-10-22 : lecture ×10 plus rapide
    # (90ᵉ centile 522 → 18 ms, pire cas 868 → 93 ms).
    _PIECE_GENERIQUE_MIN = 2000

    def voter_par_pieces(self, appareil_id: int) -> Optional[Dict[str, Any]]:
        """Type et Marque des appareils qui partagent les pièces d'un appareil.

        Returns:
            {'nb_pieces': pièces de l'appareil, 'paires': [(type, marque, nb
            d'appareils)] par effectif décroissant}, ou None si la lecture échoue.
        """
        try:
            nb = self.execute_query(
                "SELECT COUNT(*) FROM piece_associations WHERE appareil_id = ?",
                [appareil_id]) or [(0,)]
            rows = self.execute_query(
                """WITH mes AS (SELECT piece_id FROM piece_associations WHERE appareil_id = ?),
                        votantes AS (SELECT m.piece_id FROM mes m
                                     WHERE (SELECT COUNT(*) FROM piece_associations x
                                            WHERE x.piece_id = m.piece_id) <= ?)
                   SELECT COALESCE(TRIM(a.type), ''), COALESCE(TRIM(a.manufacturer), ''),
                          COUNT(DISTINCT a.id)
                   FROM votantes v
                   JOIN piece_associations p2 ON p2.piece_id = v.piece_id
                                             AND p2.appareil_id <> ?
                   JOIN appareils a ON a.id = p2.appareil_id
                   GROUP BY 1, 2 ORDER BY 3 DESC""",
                [appareil_id, self._PIECE_GENERIQUE_MIN, appareil_id]) or []
            return {'nb_pieces': nb[0][0], 'paires': [tuple(r) for r in rows]}
        except Exception as e:
            app_logger.error(f"Vote des pièces de l'appareil {appareil_id} échoué : {e}")
            return None

    def lire_refs_pieces_par_appareil(self, db_ids) -> Dict[int, List[str]]:
        """Références des pièces associées à chaque appareil.

        Returns:
            {appareil_id: [ref_piece, …]} — les appareils sans pièce sont absents.
        """
        ids = list(dict.fromkeys(db_ids))
        out: Dict[int, List[str]] = {}
        for debut in range(0, len(ids), self._TAILLE_LOT_IDS):
            lot = ids[debut:debut + self._TAILLE_LOT_IDS]
            marqueurs = ",".join("?" * len(lot))
            rows = self.execute_query(
                "SELECT pa.appareil_id, p.ref_piece FROM piece_associations pa "
                "JOIN pieces p ON p.id = pa.piece_id "
                f"WHERE pa.appareil_id IN ({marqueurs}) ORDER BY p.ref_piece", lot) or []
            for appareil_id, ref in rows:
                out.setdefault(appareil_id, []).append(ref)
        return out

    # Méthodes pour gérer les décisions sur les doublons de références
    def save_reference_decision(self, ref_modele: str, decision: str, notes: str = None) -> bool:
        """Sauvegarder une décision sur un doublon de référence"""
        result = self._safe_save_reference_decision(ref_modele, decision, notes)
        if not result:
            raise DatabaseError(f"Erreur lors de la sauvegarde de la décision pour {ref_modele}")
        return result

    @_with_query_lock
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



    
    @_with_query_lock
    def close(self):
        """Fermer proprement la connexion à la base de données.

        Idempotent. Ordre important pour la robustesse à la fermeture (notamment
        Cmd+Q) :
          1. wal_checkpoint(TRUNCATE) : replie le journal WAL dans le fichier
             principal et le tronque. Garantit qu'aucune écriture ne reste
             seulement dans le -wal au moment où le process se termine — un -wal
             non replié + arrêt brutal est un facteur connu de corruption.
          2. PRAGMA optimize : ANALYZE incrémental (plans de requêtes corrects sur
             3,5M d'associations).
        Aucune de ces étapes ne doit empêcher la fermeture (try/except chacune)."""
        if self.conn:
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            try:
                self.conn.execute("PRAGMA optimize")
            except sqlite3.Error:
                pass
            try:
                self.conn.close()
            finally:
                self.conn = None
                self.cursor = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()