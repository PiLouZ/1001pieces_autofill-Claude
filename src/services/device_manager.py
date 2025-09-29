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
from .base_service import BaseService

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
        try:
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
            
        except Exception as e:
            app_logger.error(f"Erreur recherche dispositif par références: {e}")
            return None
    
    def create_new_device(self, device_data: Dict[str, str]) -> Optional[int]:
        """
        Créer un nouveau dispositif dans la base de données
        
        Args:
            device_data: Données du dispositif à créer
            
        Returns:
            int: ID du nouvel appareil ou None si échec
        """
        try:
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
                
        except Exception as e:
            app_logger.error(f"Erreur lors de la création du nouvel appareil: {e}")
            return None
    
    def update_device_info(self, device_id: int, updates: Dict[str, str]) -> bool:
        """
        Mettre à jour les informations d'un appareil existant
        
        Args:
            device_id: ID de l'appareil à mettre à jour
            updates: Dictionnaire des champs à mettre à jour
            
        Returns:
            bool: True si succès, False sinon
        """
        try:
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
                
        except Exception as e:
            app_logger.error(f"Erreur lors de la mise à jour de l'appareil {device_id}: {e}")
            return False
    
    def try_auto_complete(self, device_data: Dict[str, str]) -> bool:
        """
        Tentative d'auto-complétion des données de l'appareil
        
        Args:
            device_data: Données de l'appareil à compléter
            
        Returns:
            bool: True si auto-complétion réussie
        """
        try:
            # Tentative d'auto-complétion basée sur ref_modele
            ref_modele = device_data.get('ref_modele', '').strip()
            if not ref_modele:
                return False
            
            # Rechercher des appareils similaires pour auto-complétion
            query = """
                SELECT type, manufacturer, COUNT(*) as count
                FROM appareils 
                WHERE ref_modele = ? AND type IS NOT NULL AND manufacturer IS NOT NULL
                GROUP BY type, manufacturer
                ORDER BY count DESC
                LIMIT 1
            """
            
            result = self.db_manager.execute_query(query, [ref_modele])
            
            if result and len(result) > 0:
                row = result[0]
                suggested_type = row[0]
                suggested_manufacturer = row[1]
                
                # Auto-compléter si les champs sont manquants
                updated = False
                if not device_data.get('type', '').strip() and suggested_type:
                    device_data['type'] = suggested_type
                    updated = True
                
                if not device_data.get('fabricant', '').strip() and suggested_manufacturer:
                    device_data['fabricant'] = suggested_manufacturer
                    updated = True
                
                return updated
            
            return False
            
        except Exception as e:
            app_logger.error(f"Erreur auto-complétion: {e}")
            return False
    
    def needs_manual_completion(self, device_data: Dict[str, str]) -> bool:
        """
        Vérifier si l'appareil nécessite une complétion manuelle
        
        Args:
            device_data: Données de l'appareil à vérifier
            
        Returns:
            bool: True si complétion manuelle nécessaire
        """
        try:
            # Champs essentiels qui doivent être remplis
            essential_fields = ['type', 'fabricant']
            
            for field in essential_fields:
                value = device_data.get(field, '').strip()
                if not value:
                    return True
            
            return False
            
        except Exception as e:
            app_logger.error(f"Erreur vérification complétion manuelle: {e}")
            return True  # En cas d'erreur, considérer qu'une complétion est nécessaire
    
    def get_device_by_id(self, device_id: int) -> Optional[Dict]:
        """
        Récupérer un dispositif par son ID
        
        Args:
            device_id: ID du dispositif
            
        Returns:
            Dict: Informations du dispositif ou None
        """
        try:
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
            
        except Exception as e:
            app_logger.error(f"Erreur récupération dispositif {device_id}: {e}")
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