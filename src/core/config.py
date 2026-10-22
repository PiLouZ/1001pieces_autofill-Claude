"""
Configuration centralisée pour l'application de gestion d'appareils
"""

import os

def pluralize(count, singular, plural=None):
    """
    Fonction globale pour gérer les pluriels correctement
    
    Args:
        count: Nombre d'éléments
        singular: Forme singulière
        plural: Forme plurielle (optionnel, ajoute 's' par défaut)
    
    Returns:
        str: Texte avec la forme correcte
        
    Exemples:
        pluralize(1, "appareil") -> "1 appareil"
        pluralize(3, "appareil") -> "3 appareils"
        pluralize(1, "cheval", "chevaux") -> "1 cheval"
        pluralize(2, "cheval", "chevaux") -> "2 chevaux"
    """
    if plural is None:
        plural = singular + "s"
    return f"{count} {singular if count <= 1 else plural}"

class Config:
    """Configuration et constantes de l'application"""
    
    # Version de l'application
    VERSION = "3.96.0"
    
    # Base de données
    DB_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'appareils.db')
    
    # Interface utilisateur
    WINDOW_TITLE = "Gestionnaire de pièces & d'appareils - 1001pieces.com"
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    
    # Timers et intervalles
    STATUS_MESSAGE_TIMEOUT = 2000  # ms
    LONG_STATUS_MESSAGE_TIMEOUT = 3000  # ms
    SEARCH_STATUS_MESSAGE_TIMEOUT = 6000  # ms — total d'une recherche (barre d'état)
    
    # Performance et pagination
    DEFAULT_PAGE_SIZE = 500   # Lignes par page
    MAX_DISPLAY_ROWS = 2000   # Maximum sans pagination
    # Optimisations Phase 2 - Interface
    CHUNK_SIZE = 500          # Taille des chunks pour setItem optimisé
    PAGINATION_THRESHOLD = 5000  # Activer pagination automatiquement
    RESPONSIVE_UPDATE_INTERVAL = 250  # ms entre les mises à jour UI
    
    # Optimisations Phase 2.4 - Import Batch Performance
    BATCH_INSERT_SIZE = 1000   # Taille optimale pour batch insert (SQLite optimum)
    BATCH_CACHE_PRELOAD = True # Pré-charger le cache d'auto-complétion
    IMPORT_PROGRESS_FREQUENCY = 100  # Fréquence des mises à jour de progress (toutes les 100 lignes)
    
    # Optimisations Phase 3 - Recherche
    SEARCH_CACHE_SIZE = 1000  # Nombre de recherches à garder en cache
    FULLTEXT_CACHE_ENABLED = True  # Activer le cache full-text
    SMART_CACHE_ENABLED = True   # Cache LRU pour load_data — invalidé après chaque écriture
    EXACT_SEARCH_THRESHOLD = 10  # Longueur min pour recherche exacte optimisée
    SEARCH_LIMIT = 5000       # Limite pour les recherches
    
    # Historique
    UNDO_HISTORY_SIZE = 100
    
    # Validation
    MAX_FIELD_LENGTH = 50
    NOTES_PREVIEW_LENGTH = 50

    # Interface
    DRAG_HANDLE_SIZE = 10

    # Feature Flag — Virtual scrolling (canFetchMore / fetchMore)
    # True  = affichage progressif : FETCH_INITIAL lignes initiales puis +FETCH_CHUNK au scroll
    # False = comportement classique : toutes les lignes d'un coup (fallback si régression)
    USE_VIRTUAL_SCROLL = True
    FETCH_INITIAL = 200   # Lignes affichées au chargement initial
    FETCH_CHUNK   = 200   # Lignes ajoutées à chaque fetchMore()

    # Feature Flag — FTS5 Full-Text Search
    # True  = recherche via index FTS5 trigram (activé depuis v3.18.0)
    # False = fallback LIKE %terme% (si l'index est absent ou corrompu)
    # Note  : désactivé automatiquement si SEARCH_PIECES_ONLY=True (pièces non indexées)
    USE_FTS5 = True

    # Clés étrangères SQLite (v3.85.0)
    # True  = `PRAGMA foreign_keys=ON` à l'ouverture : la base refuse une association
    #         vers une pièce ou un appareil absent, et applique les ON DELETE déclarés.
    # False = contraintes purement déclaratives (comportement d'avant la v3.85.0).
    # Réglage par connexion, jamais écrit dans le fichier : repasser à False suffit
    # pour revenir en arrière, sans migration.
    FOREIGN_KEYS = True

    # Feature Flags - Phase 2 Async Operations
    USE_ASYNC_LOAD_DATA = True  # Phase 2d: Migration pilote load_data_async() - TEST A/B ACTIVÉ

    # Feature Flags - Phase 5 Search Optimization
    SEARCH_PIECES_ONLY = True  # Phase 5: Recherche principale → pièces uniquement (désactivé = comportement actuel)

    # Feature Flags - Suggestions Type/Marque par similarité de référence
    # Complète (ne remplace JAMAIS) l'auto-complétion exacte de l'import.
    # Aucune application automatique : suggestions soumises à validation utilisateur.
    ENABLE_SIMILARITY_SUGGESTIONS = True
    # Suggestion « type de la pièce importée » (v3.87.0) : propose le Type que portent
    # déjà les appareils de la pièce. Mesuré le 2026-10-15 sur les saisies réelles :
    # juste à 94 % quand ce type couvre ≥ 95 % d'au moins 5 appareils ; 68 % entre
    # 80 et 95 % — d'où les seuils. Jamais appliquée sans validation.
    ENABLE_TYPE_PIECE_SUGGESTION = True
    TYPE_PIECE_PART_MIN = 0.95
    TYPE_PIECE_APPAREILS_MIN = 5
    SIMILARITY_FUZZY_THRESHOLD = 0.80        # Seuil Palier B (difflib SequenceMatcher) — abaissé à 0.80 pour capturer les variantes simples
    SIMILARITY_ALLOW_NUMERIC_FUZZY = False   # Palier B exclu par défaut sur préfixe numérique (risque rebadging)
    SIMILARITY_PREFIX_CONSENSUS = True       # Palier C : consensus de préfixe (familles mono-marque)
    SIMILARITY_ENFORCE_SHAPE = True          # Garde de structure : consensus restreint au même système de nommage (anti « HMG 280 X » -> Bosch)
    SIMILARITY_GROUPE_CODE = True            # Écarte une marque jamais vue sur la famille du code numérique de l'appareil (groupe industriel, v3.93.0)

    # Rotation des fichiers de log (v3.66.0)
    # Sans rotation, detailed.log grossissait indéfiniment : 2,3 Go / ~19 M lignes
    # constatés le 2026-09-01, dont 89,6 % de DEBUG. Le volume est proportionnel à
    # la volumétrie métier (un message par appareil traité), pas au temps.
    # Plafond total garanti : 100 + 15 + 15 = 130 Mo.
    LOG_ROTATION_ENABLED = True
    LOG_MAX_BYTES_DETAILED = 20 * 1024 * 1024   # 20 Mo par fichier
    LOG_BACKUP_COUNT_DETAILED = 5               # + 5 archives → 120 Mo max
    LOG_MAX_BYTES_SECONDARY = 5 * 1024 * 1024   # errors.log et data_operations.log
    LOG_BACKUP_COUNT_SECONDARY = 3              # → 20 Mo max chacun

    # Logs par-appareil agrégés plutôt qu'unitaires (v3.66.0).
    # True = comportement historique (une ligne DEBUG par appareil), utile pour
    # déboguer un import précis mais très volumineux.
    LOG_VERBOSE_PER_DEVICE = False

    # ==========================================================================
    # COULEURS - Centralisation PRIORITÉ 3
    # Toutes les couleurs de l'application pour éviter hardcoding dispersé
    # ==========================================================================
    
    # Couleurs existantes (conservées pour compatibilité)
    MODIFIED_CELL_COLOR = (255, 255, 200)  # Jaune clair  
    SEARCH_HIGHLIGHT_COLOR = (255, 255, 0, 100)  # Jaune transparent
    DRAG_HANDLE_COLOR = (100, 100, 255)  # Bleu
    
    # Couleurs principales (Bootstrap-like palette)
    class Colors:
        # Couleurs de base
        PRIMARY = "#0d6efd"        # Bleu principal
        PRIMARY_HOVER = "#0b5ed7"  # Bleu principal au survol
        PRIMARY_ACTIVE = "#0a58ca"  # Bleu principal actif
        
        SUCCESS = "#198754"        # Vert succès
        SUCCESS_HOVER = "#157347"  # Vert succès au survol
        SUCCESS_LIGHT = "#198754"  # Ancien alias (#28a745), aligné sur SUCCESS en v3.78.0
        SUCCESS_BG = "#d1e7dd"     # Fond vert succès
        SUCCESS_TEXT = "#0a3622"   # Texte vert succès
        
        WARNING = "#fd7e14"        # Orange avertissement
        WARNING_HOVER = "#e8680d"  # Orange avertissement au survol
        WARNING_BG = "#fff3cd"     # Fond orange avertissement
        WARNING_TEXT = "#664d03"   # Texte orange avertissement
        
        DANGER = "#dc3545"         # Rouge erreur/danger
        DANGER_HOVER = "#c82333"   # Rouge erreur au survol
        DANGER_ACTIVE = "#bd2130"  # Rouge erreur actif
        DANGER_BG = "#f8d7da"      # Fond rouge erreur
        DANGER_TEXT = "#721c24"    # Texte rouge erreur
        
        INFO = "#1976d2"           # Bleu information
        INFO_LIGHT = "#2c5282"     # Bleu information clair
        
        # Couleurs neutres  
        LIGHT = "#f8f9fa"          # Gris très clair
        LIGHT_HOVER = "#e9ecef"    # Gris très clair au survol
        GRAY = "#6c757d"           # Gris moyen
        GRAY_DARK = "#495057"      # Gris foncé
        GRAY_BORDER = "#dee2e6"    # Gris bordure
        GRAY_BORDER_HOVER = "#adb5bd"  # Gris bordure au survol
        
        WHITE = "#ffffff"          # Blanc
        BLACK = "#212529"          # Noir (texte)
        TEXT_MUTED = "#666"        # Texte atténué
        TEXT_SECONDARY = "#555"    # Texte secondaire
        
        # Couleurs spécifiques pour les statuts de données
        MISSING_LABEL = (255, 235, 200)   # Orangé clair pour libellé manquant
        # Fond de la colonne « Nb » du gestionnaire de pièces. Teintes adoucies
        # (v3.78.0) : l'ancien vert (200, 255, 200) saturait toute la colonne,
        # la quasi-totalité des pièces étant multi-appareils.
        ORPHAN_ROW = (248, 215, 218)      # Rouge pâle : pièce orpheline
        SINGLE_PIECE = (255, 243, 205)    # Jaune pâle : un seul appareil
        MULTI_PIECES = (225, 241, 230)    # Vert pâle : plusieurs appareils
        ERROR_LOG = (255, 200, 200)       # Rouge clair pour erreurs dans logs
        
        # Couleurs d'interface
        SELECTION = "#e7f1ff"      # Fond sélection
        SELECTION_BORDER = "#80bdff"  # Bordure sélection
        GRIDLINE = "#e9ecef"       # Lignes de grille
        ALTERNATE_ROW = "#f8f9fa"  # Lignes alternées
        SCROLLBAR = "#ced4da"      # Barres de défilement
        
    
    # Messages
    MESSAGES = {
        'no_selection': "Veuillez sélectionner un appareil",
        'no_search_term': "Veuillez entrer un terme de recherche",
        'no_piece_ref': "Veuillez entrer une référence de pièce",
        'save_success': "Sauvegardé",
        'save_pending': "Modifications non sauvegardées",
        'connected': "Connecté",
        'auto_save_done': "Sauvegarde effectuée",
        'new_row_added': "Nouvelle ligne ajoutée",
        'data_copied': "Données copiées dans le presse-papiers",
        'categories_updated': "Catégories mises à jour",
        'notes_updated': "Notes mises à jour",
        'piece_added': "Pièce ajoutée",
        'piece_updated': "Pièce mise à jour",
        'validation_success': "✓ Aucun problème détecté dans la base de données",
        'cleanup_success': "Lignes vides et doublons supprimés.\nPièces réassignées aux appareils conservés.",
        'completion_success': "ligne(s) ont été complétée(s).",
        'import_success': "ligne(s) importée(s)",
        'export_success': "Export créé",
        'rows_deleted': "ligne(s) supprimée(s)",
        'rows_imported': "ligne(s) ajoutée(s)"
    }
    
    # Validation
    VALIDATION_ERRORS = {
        'type_too_long': "Le type ne peut pas dépasser {max_length} caractères",
        'manufacturer_too_long': "Le fabricant ne peut pas dépasser {max_length} caractères",
        'duplicate_reference': "Cette référence existe déjà: {ref}",
        'db_error': "Erreur de base de données: {error}",
        'validation_error': "Erreur de validation: {error}",
        'import_error': "Erreur lors de l'import: {error}",
        'export_error': "Erreur lors de l'export: {error}"
    }
    
    # Requêtes SQL fréquentes (Prepared Statements optimisés)
    QUERIES = {
        'select_all': "SELECT id, {headers} FROM appareils",
        'search_condition': "({search_fields}) OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece LIKE ?)",
        'duplicate_check': "SELECT COUNT(*) FROM appareils WHERE ref_modele = ? OR commercial_ref = ? OR other_ref = ?",
        'orphaned_pieces': "SELECT COUNT(*) FROM pieces WHERE id NOT IN (SELECT DISTINCT piece_id FROM piece_associations)",
        'duplicate_refs': """SELECT ref_modele, COUNT(*) as count FROM appareils 
                           WHERE ref_modele IS NOT NULL AND ref_modele != '' 
                           GROUP BY ref_modele HAVING COUNT(*) > 1""",
        'empty_critical': """SELECT COUNT(*) FROM appareils 
                           WHERE (type IS NULL OR type = '') 
                           AND (manufacturer IS NULL OR manufacturer = '')""",
        # Nouvelles requêtes optimisées pour les imports
        'find_device_by_refs': """SELECT id FROM appareils 
                                WHERE (ref_modele = ? AND commercial_ref = ?) 
                                   OR (ref_modele = ? AND commercial_ref IS NULL AND ? IS NULL)
                                   OR (ref_modele IS NULL AND commercial_ref = ? AND ? IS NULL)""",
        'insert_device_batch': """INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref, other_ref, notes, category)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
        'update_device_other_ref': "UPDATE appareils SET other_ref = ? WHERE id = ?",
        'update_device_notes': "UPDATE appareils SET notes = ? WHERE id = ?",
        # Complétion d'un appareil existant à l'import : la garde WHERE interdit
        # d'écraser une valeur déjà saisie, quel que soit l'état du cache.
        'complete_device_type': """UPDATE appareils SET type = ?
                                 WHERE id = ? AND (type IS NULL OR TRIM(type) = '')""",
        'complete_device_manufacturer': """UPDATE appareils SET manufacturer = ?
                                 WHERE id = ? AND (manufacturer IS NULL OR TRIM(manufacturer) = '')""",
        'autocomplete_search': """SELECT id, ref_modele, commercial_ref, type, manufacturer 
                               FROM appareils 
                               WHERE (ref_modele LIKE ? OR commercial_ref LIKE ?) 
                               AND (type IS NOT NULL AND type != '') 
                               AND (manufacturer IS NOT NULL AND manufacturer != '')
                               LIMIT 10""",
        # Index sur id déjà présent pour optimisation
        'preload_all_devices': """SELECT id, ref_modele, commercial_ref, type, manufacturer, other_ref, notes 
                               FROM appareils 
                               WHERE (ref_modele IS NOT NULL AND ref_modele != '') 
                                  OR (commercial_ref IS NOT NULL AND commercial_ref != '')
                               ORDER BY id""",
        # Requêtes optimisées Phase 3 - Recherche
        'exact_search_optimized': """SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes,
                                    (SELECT COUNT(*) FROM piece_associations pa WHERE pa.appareil_id = a.id) as pieces_count
                                    FROM appareils a
                                    WHERE (type = ? OR manufacturer = ? OR ref_modele = ? OR commercial_ref = ? OR other_ref = ? OR category = ?)
                                       OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa
                                                  JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece = ?)""",
        'prefix_search_optimized': """SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes,
                                     (SELECT COUNT(*) FROM piece_associations pa WHERE pa.appareil_id = a.id) as pieces_count
                                     FROM appareils a
                                     WHERE (type LIKE ? OR manufacturer LIKE ? OR ref_modele LIKE ? OR commercial_ref LIKE ? OR other_ref LIKE ? OR category LIKE ?)
                                        OR a.id IN (SELECT pa.appareil_id FROM piece_associations pa
                                                   JOIN pieces p ON pa.piece_id = p.id WHERE p.ref_piece LIKE ?)""",
        'search_pieces_only': """SELECT DISTINCT pa.appareil_id FROM piece_associations pa 
                               JOIN pieces p ON pa.piece_id = p.id 
                               WHERE p.ref_piece LIKE ?""",
        
        # ==========================================================================
        # REQUÊTES CONSOLIDÉES - PRIORITÉ 3 PHASE 2
        # Centralisation des requêtes SELECT DISTINCT fréquemment dupliquées
        # ==========================================================================
        
        # Requêtes DISTINCT pour champs d'appareils
        'distinct_types': """SELECT DISTINCT type FROM appareils 
                           WHERE type IS NOT NULL AND type != '' 
                           ORDER BY type LIMIT 1000""",
        'distinct_manufacturers': """SELECT DISTINCT manufacturer FROM appareils 
                                   WHERE manufacturer IS NOT NULL AND manufacturer != '' 
                                   ORDER BY manufacturer LIMIT 1000""",
        'distinct_ref_modele': """SELECT DISTINCT ref_modele FROM appareils 
                                WHERE ref_modele IS NOT NULL AND ref_modele != '' 
                                ORDER BY ref_modele LIMIT 1000""",
        'distinct_commercial_ref': """SELECT DISTINCT commercial_ref FROM appareils 
                                    WHERE commercial_ref IS NOT NULL AND commercial_ref != '' 
                                    ORDER BY commercial_ref LIMIT 1000""",
        'distinct_ref_pieces': """SELECT DISTINCT ref_piece FROM pieces 
                                WHERE ref_piece IS NOT NULL AND ref_piece != '' 
                                ORDER BY ref_piece LIMIT 1000""",
        
        # Requêtes pour auto-complétion avec filtre dynamique  
        'autocomplete_field': """SELECT DISTINCT {field} FROM appareils 
                               WHERE {field} IS NOT NULL AND {field} != '' 
                               ORDER BY {field} LIMIT 1000""",
        
        # Requêtes auto-complétion avec filtre LIKE 
        'autocomplete_types_like': """SELECT DISTINCT type FROM appareils 
                                    WHERE type LIKE ? AND type != '' 
                                    ORDER BY type LIMIT 20""",
        'autocomplete_manufacturers_like': """SELECT DISTINCT manufacturer FROM appareils 
                                            WHERE manufacturer LIKE ? AND manufacturer != '' 
                                            ORDER BY manufacturer LIMIT 20""",
        
        # Requêtes pour SEO/analytics avec jointures fréquentes
        # Nombre de modèles distincts par (type, fabricant) pour un ensemble de références :
        # un modèle associé à plusieurs références de la liste n'est compté qu'une fois.
        'device_counts_for_pieces': """SELECT TRIM(a.type), TRIM(a.manufacturer), COUNT(DISTINCT a.id)
                              FROM appareils a 
                              JOIN piece_associations pa ON a.id = pa.appareil_id 
                              JOIN pieces p ON pa.piece_id = p.id 
                              WHERE p.ref_piece IN ({placeholders}) 
                                AND a.type IS NOT NULL AND a.type != '' 
                                AND a.manufacturer IS NOT NULL AND a.manufacturer != ''
                              GROUP BY TRIM(a.type), TRIM(a.manufacturer)""",
        
        # Requêtes de comptage communes
        'count_pieces_for_device': """SELECT COUNT(*) FROM piece_associations pa 
                                    WHERE pa.appareil_id = ?""",
        'count_devices_for_piece': """SELECT COUNT(DISTINCT pa.appareil_id) 
                                    FROM piece_associations pa 
                                    JOIN pieces p ON pa.piece_id = p.id 
                                    WHERE p.ref_piece = ?""",
        
        # Requêtes de validation/nettoyage communes
        'find_duplicates_by_refs': """SELECT ref_modele, commercial_ref, COUNT(*) as count 
                                    FROM appareils 
                                    WHERE (ref_modele IS NOT NULL AND ref_modele != '') 
                                       OR (commercial_ref IS NOT NULL AND commercial_ref != '')
                                    GROUP BY ref_modele, commercial_ref 
                                    HAVING COUNT(*) > 1""",
        'delete_piece_by_ref': """DELETE FROM pieces WHERE ref_piece = ?"""
    }
    
    # Structure de la base de données (SANS pieces_count pour simplifier)
    DB_HEADERS = ["type", "manufacturer", "ref_modele", "commercial_ref", "other_ref", "category", "notes"]
    UI_HEADERS = [
        "Type", "Fabricant", "Référence modèle",
        "Référence commerciale", "Autre référence", "Catégorie", "Notes", "Nb pièces"
    ]
    
    # Configuration des colonnes (index, nom, visible par défaut)
    COLUMN_CONFIG = [
        {"index": 0, "name": "Type", "db_field": "type", "visible": True, "mandatory": True},
        {"index": 1, "name": "Fabricant", "db_field": "manufacturer", "visible": True, "mandatory": True},
        {"index": 2, "name": "Référence modèle", "db_field": "ref_modele", "visible": True, "mandatory": True},
        {"index": 3, "name": "Référence commerciale", "db_field": "commercial_ref", "visible": True, "mandatory": True},
        {"index": 4, "name": "Autre référence", "db_field": "other_ref", "visible": True, "mandatory": True},
        {"index": 5, "name": "Catégorie", "db_field": "category", "visible": False, "mandatory": False},
        {"index": 6, "name": "Notes", "db_field": "notes", "visible": False, "mandatory": False}
    ]
    
    # Raccourcis clavier
    SHORTCUTS = {
        'new_row': 'Cmd+N',
        'save': 'Cmd+S',
        'undo': 'Cmd+Z',
        'redo': 'Cmd+Y',
        'find': 'Cmd+F',
        'copy': 'Cmd+C',
        'paste': 'Cmd+V',
        'refresh': 'F5',
        'next_empty_down': 'Cmd+Down',
        'next_empty_up': 'Cmd+Up',
        'column_values': 'Cmd+D'
    }
    
    @classmethod
    def get_message(cls, key, **kwargs):
        """Récupérer un message avec formatage"""
        message = cls.MESSAGES.get(key, key)
        return message.format(**kwargs) if kwargs else message
    
    @classmethod
    def get_validation_error(cls, key, **kwargs):
        """Récupérer une erreur de validation avec formatage"""
        error = cls.VALIDATION_ERRORS.get(key, key)
        return error.format(**kwargs) if kwargs else error
    
    @classmethod
    def get_query(cls, key, **kwargs):
        """Récupérer une requête SQL avec formatage"""
        query = cls.QUERIES.get(key, key)
        return query.format(**kwargs) if kwargs else query