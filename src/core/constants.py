"""
📋 Gestionnaire de constantes centralisé
Élimine les 50+ valeurs hardcodées dispersées dans le projet
"""

from pathlib import Path
from enum import Enum

class ExportFormat(Enum):
    """Formats d'export supportés - VERSION UNIFIÉE
    
    Source unique depuis la consolidation des définitions incohérentes
    qui coexistaient dans data_exporter.py et services/export_service.py
    (ces deux modules ont été supprimés en v3.69.0).
    """
    CSV = "CSV"
    JSON = "JSON" 
    HTML_BRANDS = "HTML_BRANDS"
    HTML_DETAILS = "HTML_DETAILS"
    XML = "XML"
    EXCEL = "EXCEL"
    
    # Méthodes utilitaires pour la compatibilité
    
    @property
    def lowercase(self) -> str:
        """Retourner la valeur en minuscules (compatibilité data_exporter)"""
        return self.value.lower()

class DatabaseConfig:
    """Configuration de base de données"""
    DB_NAME = "appareils.db"
    BACKUP_SUFFIX = "_backup"
    BACKUP_DIR_NAME = "backups"          # data/backups/
    BACKUP_MAX_COPIES = 2                # rotation (~900 Mo par copie)
    # Copies faites par l'application elle-même, avant une opération à risque.
    # Tout autre motif (fusion de marques, script ponctuel…) a sa propre réserve,
    # pour ne jamais évincer ces copies-là (v3.84.0).
    BACKUP_MOTIFS_AUTOMATIQUES = ("import", "nettoyage", "avant_restauration")
    # 2 et non 1 (v3.86.1) : avec une seule place, chaque opération ponctuelle
    # effaçait la précédente — le 2026-10-15, la copie du nettoyage des orphelins
    # a évincé celle d'avant la fusion des marques, prise le matin même.
    BACKUP_MAX_COPIES_PONCTUELLES = 2
    BACKUP_MIN_INTERVAL_IMPORT_H = 24    # avant import : au plus 1 copie / 24h

    # Réglages de performance SQLite (PRAGMA appliqués à chaque connexion)
    SQLITE_CACHE_SIZE_KIB = -65536       # cache_size négatif = Kio → 64 Mo de cache de pages
    SQLITE_MMAP_SIZE_BYTES = 268435456   # mmap_size → 256 Mo de fichier en mémoire mappée
    
    # Tables principales
    TABLE_APPAREILS = "appareils"
    TABLE_PIECES = "pieces"
    TABLE_COMPATIBILITY = "compatibility"
    
    # Colonnes communes
    COLUMN_ID = "id"
    COLUMN_REFERENCE = "reference"
    COLUMN_DESIGNATION = "designation"
    COLUMN_MARQUE = "marque"
    COLUMN_MODELE = "modele"
    COLUMN_PRICE = "prix"
    COLUMN_STOCK = "stock"
    COLUMN_CATEGORY = "categorie"
    COLUMN_NOTES = "notes"
    COLUMN_CREATED = "date_creation"
    COLUMN_UPDATED = "date_modification"

class UIConfig:
    """Configuration de l'interface utilisateur"""
    WINDOW_MIN_WIDTH = 1200
    WINDOW_MIN_HEIGHT = 800
    WINDOW_DEFAULT_WIDTH = 1400
    WINDOW_DEFAULT_HEIGHT = 900
    
    # Tailles de colonnes par défaut
    COLUMN_WIDTH_ID = 80
    COLUMN_WIDTH_REFERENCE = 120
    COLUMN_WIDTH_DESIGNATION = 200
    COLUMN_WIDTH_MARQUE = 100
    COLUMN_WIDTH_MODELE = 120
    COLUMN_WIDTH_PRICE = 80
    COLUMN_WIDTH_STOCK = 60
    
    # Couleurs de l'interface
    COLOR_SUCCESS = "#198754"
    COLOR_WARNING = "#ffc107" 
    COLOR_ERROR = "#dc3545"
    COLOR_INFO = "#17a2b8"
    
    # Hauteur des lignes du tableau principal (px) — réglable dans Affichage.
    # Clé QSettings : ui/row_height. « aeree » = ancienne hauteur fixe (30 px).
    ROW_HEIGHTS = {
        "compacte": ("Compacte", 22),
        "normale": ("Normale", 26),
        "aeree": ("Aérée", 30),
    }
    DEFAULT_ROW_HEIGHT = "normale"

    # Pagination
    DEFAULT_PAGE_SIZE = 500
    COLOR_PRIMARY = "#0d6efd"
    COLOR_SECONDARY = "#6c757d"
    
    # Styles CSS fréquents
    STYLE_SUCCESS_BUTTON = f"background-color: {COLOR_SUCCESS}; color: white; padding: 5px 10px; border-radius: 3px;"
    STYLE_ERROR_BUTTON = f"background-color: {COLOR_ERROR}; color: white; padding: 5px 10px; border-radius: 3px;"
    STYLE_WARNING_BUTTON = f"background-color: {COLOR_WARNING}; color: black; padding: 5px 10px; border-radius: 3px;"

    # Liens d'action de l'historique des opérations (MainWindow._handle_history_link)
    LIEN_HISTORIQUE_LIBELLE = "libelle:"   # + référence encodée → « Modifier la pièce » sur le libellé
    LIEN_HISTORIQUE_AUTOCOMPLETES = "autocompletes:"  # → fenêtre « Auto-complétés à vérifier »


class Messages:
    """Messages utilisateur standardisés"""
    
    # Titres de dialogues
    TITLE_INFO = "Information"
    TITLE_SUCCESS = "Succès"  
    TITLE_WARNING = "Attention"
    TITLE_ERROR = "Erreur"
    TITLE_QUESTION = "Question"
    
    # Messages de succès
    SAVE_SUCCESS = "Les données ont été sauvegardées avec succès."
    EXPORT_SUCCESS = "L'export a été généré avec succès."
    IMPORT_SUCCESS = "L'import a été effectué avec succès."
    DELETE_SUCCESS = "L'élément a été supprimé avec succès."
    UPDATE_SUCCESS = "La mise à jour a été effectuée avec succès."
    
    # Messages d'erreur génériques
    SAVE_ERROR = "Erreur lors de la sauvegarde des données."
    EXPORT_ERROR = "Erreur lors de l'export des données."
    IMPORT_ERROR = "Erreur lors de l'import des données."
    DELETE_ERROR = "Erreur lors de la suppression."
    UPDATE_ERROR = "Erreur lors de la mise à jour."
    DATABASE_ERROR = "Erreur de base de données."
    FILE_NOT_FOUND = "Fichier non trouvé."
    PERMISSION_ERROR = "Permissions insuffisantes."
    NETWORK_ERROR = "Erreur de connexion réseau."
    
    # Messages de validation
    FIELD_REQUIRED = "Ce champ est obligatoire."
    FIELD_INVALID_FORMAT = "Format de champ invalide."
    DUPLICATE_REFERENCE = "Cette référence existe déjà."
    INVALID_PRICE = "Le prix doit être un nombre positif."
    INVALID_STOCK = "Le stock doit être un nombre entier positif."
    
    # Messages de confirmation
    CONFIRM_DELETE = "Êtes-vous sûr de vouloir supprimer cet élément ?"
    CONFIRM_DELETE_MULTIPLE = "Êtes-vous sûr de vouloir supprimer ces éléments ?"
    CONFIRM_OVERWRITE = "Le fichier existe déjà. Voulez-vous le remplacer ?"
    CONFIRM_EXIT = "Voulez-vous vraiment quitter l'application ?"
    CONFIRM_CLEAR_DATA = "Êtes-vous sûr de vouloir effacer toutes les données ?"
    
    # Messages d'information
    NO_DATA_SELECTED = "Aucune donnée sélectionnée."
    NO_DATA_AVAILABLE = "Aucune donnée disponible."
    OPERATION_CANCELLED = "Opération annulée par l'utilisateur."
    PROCESSING = "Traitement en cours..."
    LOADING = "Chargement..."
    SEARCHING = "Recherche en cours..."

class Paths:
    """Chemins et répertoires de l'application"""
    
    @staticmethod
    def get_app_root() -> Path:
        """Obtenir le répertoire racine de l'application"""
        return Path(__file__).parent.parent.parent
    
    @staticmethod 
    def get_data_dir() -> Path:
        """Obtenir le répertoire de données"""
        return Paths.get_app_root() / "data"
    
    @staticmethod
    def get_database_path() -> Path:
        """Obtenir le chemin de la base de données"""
        return Paths.get_data_dir() / DatabaseConfig.DB_NAME


class TypesAppareils:
    """Libellés de types d'appareils fixés par décision client.

    Le libellé doit être identique, au caractère près, au type créé sur le site
    (sinon l'export crée une catégorie orpheline)."""

    # Règles de nomenclature, lot 2 (décision D6 du 2026-11-23)
    FOUR_COMBINE_MICRO_ONDES = "Four combiné micro-ondes"

    # Règles de nomenclature (décision D9) : types accessoires, exclus des règles
    # — aucune règle ne les propose ni ne les retire.
    ACCESSOIRES = frozenset({
        "Accessoires", "Porte", "Tiroir à couverts", "Filtre à eau", "Kit d'évacuation",
        "Panier à couverts", "Filtre", "Rails téléscopique", "Kit de recyclage",
    })

    # Règles de nomenclature (CDC § 7) : familles de types « voisins », que les
    # pièces partagées ne départagent pas ; une proposition entre deux types
    # d'une même famille reste « simple » (revue ligne à ligne).
    FAMILLES_VOISINES = (
        frozenset({"Réfrigérateur", "Congélateur", "Cave à vin"}),
        frozenset({"Four", "Four vapeur", FOUR_COMBINE_MICRO_ONDES, "Cuisinière", "Micro-ondes"}),
        frozenset({"Lave-linge", "Sèche-linge", "Lavante-séchante"}),
    )
