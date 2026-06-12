"""
Device Manager Service - Phase 2.16
Centralise toute la logique de gestion des dispositifs/appareils

Responsabilités:
- Création de nouveaux dispositifs
- Mise à jour de dispositifs existants
- Recherche de dispositifs par références
- Auto-complétion des données manquantes
- Validation des données de dispositifs
"""

from typing import Optional, Dict, List, Any
from ..core.logger import app_logger
from ..utils.error_handler import handle_database_operation_errors
from .base_service import BaseService, safe_operation

class DeviceManager(BaseService):
    """
    Service de gestion des dispositifs/appareils
    
    Responsabilités:
    - CRUD operations sur les dispositifs
    - Auto-complétion et validation des données
    - Recherche et correspondance de dispositifs existants
    - Intégration avec DatabaseManager
    """
    
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
    
    @safe_operation(operation_name="find_existing_device_by_refs", default_return=None)
    def find_existing_device_by_refs(self, ref_modele: str, commercial_ref: str,
                                   device_type: str = "", manufacturer: str = "") -> Optional[Dict]:
        """
        Rechercher un dispositif existant par ses références

        Args:
            ref_modele: Référence du modèle
            commercial_ref: Référence commerciale
            device_type: Type de dispositif (optionnel)
            manufacturer: Fabricant (optionnel)

        Returns:
            Dict: Informations du dispositif trouvé ou None
        """
        # Recherche par références exactes d'abord
        query = """
            SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref
            FROM appareils
            WHERE ref_modele = ? AND commercial_ref = ?
        """
        params = [ref_modele, commercial_ref]

        # Ajouter des filtres additionnels si fournis
        if device_type.strip():
            query += " AND type = ?"
            params.append(device_type.strip())

        if manufacturer.strip():
            query += " AND manufacturer = ?"
            params.append(manufacturer.strip())

        query += " LIMIT 1"

        result = self.db_manager.execute_query(query, params)

        if result and len(result) > 0:
            row = result[0]
            device_info = {
                'id': row[0],
                'type': row[1] or '',
                'fabricant': row[2] or '',  # Garder fabricant pour l'interface
                'manufacturer': row[2] or '',  # Ajouter aussi manufacturer
                'ref_modele': row[3] or '',
                'commercial_ref': row[4] or '',
                'other_ref': row[5] or ''
            }
            return device_info

        return None
    
    @safe_operation(operation_name="create_new_device", default_return=None)
    def create_new_device(self, device_data: Dict[str, str]) -> Optional[int]:
        """
        Créer un nouveau dispositif dans la base de données

        Args:
            device_data: Données du dispositif à créer

        Returns:
            int: ID du nouvel appareil ou None si échec
        """
        # Préparer les champs pour l'insertion
        fields = []
        values = []
        placeholders = []

        # Mapping des champs du dictionnaire vers les colonnes de la DB
        field_mapping = {
            'type': 'type',
            'fabricant': 'manufacturer',  # fabricant -> manufacturer dans la DB
            'manufacturer': 'manufacturer',  # Support direct aussi
            'ref_modele': 'ref_modele',
            'commercial_ref': 'commercial_ref',
            'other_ref': 'other_ref'
        }

        for key, db_field in field_mapping.items():
            if key in device_data and device_data[key] and device_data[key].strip():
                fields.append(db_field)
                values.append(device_data[key].strip())
                placeholders.append('?')

        if not fields:
            app_logger.warning("Aucune donnée valide pour créer un nouvel appareil")
            return None

        # Construire et exécuter la requête d'insertion
        query = f"INSERT INTO appareils ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"

        new_id = self.db_manager.execute_insert(query, values)
        if new_id:
            app_logger.info(f"Nouvel appareil créé avec ID: {new_id}")
            return new_id
        else:
            app_logger.error("Échec de la création du nouvel appareil")
            return None
    
    @safe_operation(operation_name="update_device_info", default_return=False)
    def update_device_info(self, device_id: int, updates: Dict[str, str]) -> bool:
        """
        Mettre à jour les informations d'un appareil existant

        Args:
            device_id: ID de l'appareil à mettre à jour
            updates: Dictionnaire des champs à mettre à jour

        Returns:
            bool: True si succès, False sinon
        """
        if not updates:
            return True  # Rien à faire

        # Préparer les champs pour la mise à jour
        set_clauses = []
        values = []

        # Mapping des champs du dictionnaire vers les colonnes de la DB
        field_mapping = {
            'type': 'type',
            'fabricant': 'manufacturer',  # fabricant -> manufacturer dans la DB
            'manufacturer': 'manufacturer',  # Support direct aussi
            'ref_modele': 'ref_modele',
            'commercial_ref': 'commercial_ref',
            'other_ref': 'other_ref'
        }

        for key, value in updates.items():
            if key in field_mapping and value is not None:
                db_field = field_mapping[key]
                set_clauses.append(f"{db_field} = ?")
                values.append(value.strip() if isinstance(value, str) else value)

        if not set_clauses:
            app_logger.warning("Aucune mise à jour valide à appliquer")
            return True

        # Ajouter l'ID pour la clause WHERE
        values.append(device_id)

        # Construire et exécuter la requête de mise à jour
        query = f"UPDATE appareils SET {', '.join(set_clauses)} WHERE id = ?"

        result = self.db_manager.execute_custom_query(query, values)
        if result is not None:
            app_logger.info(f"Appareil {device_id} mis à jour avec succès")
            return True
        else:
            app_logger.error(f"Échec de la mise à jour de l'appareil {device_id}")
            return False

    @handle_database_operation_errors(return_value={'created': False, 'exists': False, 'description_updated': False}, log_prefix="Erreur création association pièce")
    def create_piece_association(self, device_id: int, ref_piece: str,
                                 libelle_piece: str = "", _decisions_cache: Dict = None) -> Dict:
        """
        Créer une association entre un appareil et une pièce (variante import).

        Retourne {created, exists, description_updated} : les statistiques
        d'import dépendent de cette distinction created/exists. Ne pas confondre
        avec DatabaseManager.add_piece() dont le contrat de retour diffère
        (cf. follow-up de déduplication noté dans l'audit structure).
        """
        # Vérifier si l'association existe déjà
        check_query = """
            SELECT COUNT(*) FROM piece_associations pa
            JOIN pieces p ON pa.piece_id = p.id
            WHERE pa.appareil_id = ? AND p.ref_piece = ?
        """
        result = self.db_manager.execute_query(check_query, [device_id, ref_piece])
        if result and result[0][0] > 0:
            return {'created': False, 'exists': True, 'description_updated': False}

        # Vérifier si la pièce existe ou la créer
        piece_query = "SELECT id FROM pieces WHERE ref_piece = ?"
        piece_result = self.db_manager.execute_query(piece_query, [ref_piece])

        if piece_result:
            piece_id = piece_result[0][0]
        else:
            insert_piece_query = "INSERT INTO pieces (ref_piece, description) VALUES (?, ?)"
            piece_result = self.db_manager.execute_query(insert_piece_query, [ref_piece, libelle_piece or ''])
            if not piece_result:
                return {'created': False, 'exists': False, 'description_updated': False}
            piece_id = self.db_manager.cursor.lastrowid

        # Créer l'association
        association_query = "INSERT INTO piece_associations (appareil_id, piece_id) VALUES (?, ?)"
        assoc_result = self.db_manager.execute_query(association_query, [device_id, piece_id])

        if assoc_result:
            return {'created': True, 'exists': False, 'description_updated': False}
        else:
            return {'created': False, 'exists': False, 'description_updated': False}

    @safe_operation(operation_name="try_auto_complete", default_return=False)
    def try_auto_complete(self, device_data: Dict[str, str]) -> bool:
        """
        Tentative d'auto-complétion des données de l'appareil (Type et Fabricant).
        Correspondance exacte uniquement sur les références non vides.
        Sélectionne la combinaison type+fabricant la plus fréquente en base.

        Args:
            device_data: Données de l'appareil à compléter (modifié en place)

        Returns:
            bool: True si au moins un champ a été complété
        """
        type_empty = not device_data.get('type', '').strip()
        manufacturer_empty = not device_data.get('manufacturer', '').strip()

        if not type_empty and not manufacturer_empty:
            return False

        # Construire la condition uniquement sur les références non vides
        ref_modele = device_data.get('ref_modele', '').strip()
        commercial_ref = device_data.get('commercial_ref', '').strip()

        if not ref_modele and not commercial_ref:
            return False

        conditions = []
        params = []
        if ref_modele:
            conditions.append('ref_modele = ?')
            params.append(ref_modele)
        if commercial_ref:
            conditions.append('commercial_ref = ?')
            params.append(commercial_ref)

        where_clause = ' OR '.join(conditions)
        query = f"""
            SELECT type, manufacturer, COUNT(*) as freq
            FROM appareils
            WHERE ({where_clause})
              AND type IS NOT NULL AND type != ''
              AND manufacturer IS NOT NULL AND manufacturer != ''
            GROUP BY type, manufacturer
            ORDER BY freq DESC
            LIMIT 1
        """

        result = self.db_manager.execute_query(query, params)

        if result:
            found_type, found_manufacturer = result[0][0], result[0][1]
            updated = False
            if type_empty and found_type:
                device_data['type'] = found_type
                updated = True
            if manufacturer_empty and found_manufacturer:
                device_data['manufacturer'] = found_manufacturer
                updated = True
            return updated

        return False
    
    @safe_operation(operation_name="needs_manual_completion", default_return=True)
    def needs_manual_completion(self, device_data: Dict[str, str]) -> bool:
        """
        Vérifier si l'appareil nécessite une complétion manuelle

        Args:
            device_data: Données de l'appareil à vérifier

        Returns:
            bool: True si complétion manuelle nécessaire
        """
        # Champs essentiels qui doivent être remplis
        essential_fields = ['type', 'manufacturer']

        for field in essential_fields:
            value = device_data.get(field, '').strip()
            if not value:
                return True

        return False
    
    @safe_operation(operation_name="get_device_by_id", default_return=None)
    def get_device_by_id(self, device_id: int) -> Optional[Dict]:
        """
        Récupérer un dispositif par son ID

        Args:
            device_id: ID du dispositif

        Returns:
            Dict: Informations du dispositif ou None
        """
        query = """
            SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref
            FROM appareils
            WHERE id = ?
            LIMIT 1
        """

        result = self.db_manager.execute_query(query, [device_id])

        if result and len(result) > 0:
            row = result[0]
            return {
                'id': row[0],
                'type': row[1] or '',
                'fabricant': row[2] or '',  # Garder fabricant pour l'interface
                'manufacturer': row[2] or '',  # Ajouter aussi manufacturer
                'ref_modele': row[3] or '',
                'commercial_ref': row[4] or '',
                'other_ref': row[5] or ''
            }

        return None
    
    def validate_device_data(self, device_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Valider les données d'un dispositif
        
        Args:
            device_data: Données à valider
            
        Returns:
            Dict: Résultat de validation avec 'valid' (bool) et 'errors' (list)
        """
        errors = []
        
        try:
            # Vérifications de base
            required_fields = ['ref_modele', 'commercial_ref']
            for field in required_fields:
                if not device_data.get(field, '').strip():
                    errors.append(f"Champ requis manquant: {field}")
            
            # Validation des longueurs
            max_lengths = {
                'type': 100,
                'fabricant': 100,
                'ref_modele': 200,
                'commercial_ref': 200,
                'other_ref': 200
            }
            
            for field, max_len in max_lengths.items():
                value = device_data.get(field, '')
                if len(value) > max_len:
                    errors.append(f"Champ {field} trop long (max {max_len} caractères)")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors
            }
            
        except Exception as e:
            app_logger.error(f"Erreur validation données dispositif: {e}")
            return {
                'valid': False,
                'errors': [f"Erreur de validation: {e}"]
            }