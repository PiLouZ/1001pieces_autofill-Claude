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
    VERSION = "2.8.2"
    
    # Base de données
    DB_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'appareils.db')
    
    # Interface utilisateur
    WINDOW_TITLE = "Gestionnaire de pièces & d'appareils - 1001pieces.com"
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    
    # Timers et intervalles
    AUTO_SAVE_INTERVAL = 5000  # ms
    STATUS_MESSAGE_TIMEOUT = 2000  # ms
    LONG_STATUS_MESSAGE_TIMEOUT = 3000  # ms
    
    # Performance et pagination
    DEFAULT_PAGE_SIZE = 1000  # Lignes par page
    MAX_DISPLAY_ROWS = 2000   # Maximum sans pagination
    SEARCH_LIMIT = 5000       # Limite pour les recherches
    
    # Historique
    UNDO_HISTORY_SIZE = 100
    
    # Validation
    MAX_FIELD_LENGTH = 50
    NOTES_PREVIEW_LENGTH = 50
    
    # Interface
    DRAG_HANDLE_SIZE = 10
    
    # Couleurs
    MODIFIED_CELL_COLOR = (255, 255, 200)  # Jaune clair
    SEARCH_HIGHLIGHT_COLOR = (255, 255, 0, 100)  # Jaune transparent
    DRAG_HANDLE_COLOR = (100, 100, 255)  # Bleu
    
    # Messages
    MESSAGES = {
        'no_selection': "Veuillez sélectionner un appareil",
        'no_search_term': "Veuillez entrer un terme de recherche",
        'no_piece_ref': "Veuillez entrer une référence de pièce",
        'save_success': "💾 Sauvegardé",
        'save_pending': "💾 Modifications non sauvegardées",
        'connected': "🔗 Connecté",
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
    
    # Requêtes SQL fréquentes
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
                           AND (manufacturer IS NULL OR manufacturer = '')"""
    }
    
    # Structure de la base de données (SANS pieces_count pour simplifier)
    DB_HEADERS = ["type", "manufacturer", "ref_modele", "commercial_ref", "other_ref", "category", "notes"]
    UI_HEADERS = [
        "Type", "Fabricant", "Référence Modèle",
        "Référence Commerciale", "Autre Référence", "Catégorie", "Notes", "Nb Pièces"
    ]
    
    # Configuration des colonnes (index, nom, visible par défaut)
    COLUMN_CONFIG = [
        {"index": 0, "name": "Type", "db_field": "type", "visible": True, "mandatory": True},
        {"index": 1, "name": "Fabricant", "db_field": "manufacturer", "visible": True, "mandatory": True},
        {"index": 2, "name": "Référence Modèle", "db_field": "ref_modele", "visible": True, "mandatory": True},
        {"index": 3, "name": "Référence Commerciale", "db_field": "commercial_ref", "visible": True, "mandatory": True},
        {"index": 4, "name": "Autre Référence", "db_field": "other_ref", "visible": True, "mandatory": True},
        {"index": 5, "name": "Catégorie", "db_field": "category", "visible": False, "mandatory": False},
        {"index": 6, "name": "Notes", "db_field": "notes", "visible": False, "mandatory": False},
        {"index": 7, "name": "Nb Pièces", "db_field": None, "visible": True, "mandatory": False}
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