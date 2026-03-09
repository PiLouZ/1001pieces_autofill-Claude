"""
Service de gestion des données - Phase 2.5c
Extrait de main_refactored.py pour améliorer la maintenabilité

Responsabilités:
- Auto-complétion des champs vides (Type, Fabricant)
- Nettoyage des données et gestion des doublons
- Logique de validation et de cohérence des données
"""

from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from .qt_imports import QDialog
from src.core.config import Config
from src.core.logger import app_logger
from src.utils.error_handler import handle_data_management_errors

@dataclass
class FieldCompletionResult:
    """Résultat de l'auto-complétion des champs"""
    completed_count: int = 0
    total_rows_processed: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class DataManagementService:
    """
    Service spécialisé pour la gestion et maintenance des données
    
    Responsabilités:
    - Auto-complétion intelligente des champs manquants
    - Nettoyage et déduplication des données
    - Validation et cohérence des informations
    - Maintenance de la qualité des données
    """
    
    def __init__(self, db_manager, main_window=None):
        self.db_manager = db_manager
        self.main_window = main_window  # Pour accès aux méthodes UI existantes
        
    def auto_complete_empty_fields(self, table_data: List[Dict[str, Any]]) -> FieldCompletionResult:
        """
        Auto-compléter les champs vides Type et Fabricant
        
        Args:
            table_data: Liste des données du tableau [{'id': db_id, 'data': {field: value}}]
            
        Returns:
            FieldCompletionResult avec les statistiques de complétion
        """
        result = FieldCompletionResult()
        result.total_rows_processed = len(table_data)
        
        if not table_data:
            result.errors.append("Aucune donnée à traiter")
            return result
        
        app_logger.info(f"Auto-complétion: Traitement de {len(table_data)} lignes")
        
        for row_data in table_data:
            success = self._safe_process_device_row(row_data, result)
            if success:
                result.completed_count += 1

        app_logger.info(f"Auto-complétion terminée: {result.completed_count}/{result.total_rows_processed} lignes complétées")
        return result

    @handle_data_management_errors(return_value=False)
    def _safe_process_device_row(self, row_data: Dict[str, Any], result: FieldCompletionResult) -> bool:
        """Traiter une ligne d'appareil de manière sécurisée"""
        db_id = row_data.get('id')
        device_data = row_data.get('data', {})

        if not db_id:
            result.errors.append("ID manquant pour une ligne")
            return False

        # Vérifier si Type ou Fabricant manquants
        current_type = device_data.get('type', '').strip()
        current_manufacturer = device_data.get('manufacturer', '').strip()

        if not current_type or not current_manufacturer:
            # Tentative d'auto-complétion
            completed = self._try_auto_complete_device(db_id, device_data)
            return completed is not None

        return False
    
    def _try_auto_complete_device(self, db_id: int, device_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Tenter l'auto-complétion d'un appareil spécifique
        
        Args:
            db_id: ID de l'appareil en base
            device_data: Données actuelles de l'appareil
            
        Returns:
            Dict avec les champs complétés ou None si aucune complétion
        """
        ref_modele = device_data.get('ref_modele', '').strip()
        commercial_ref = device_data.get('commercial_ref', '').strip()
        current_type = device_data.get('type', '').strip()
        current_manufacturer = device_data.get('manufacturer', '').strip()
        
        # Aucune référence pour faire l'auto-complétion
        if not ref_modele and not commercial_ref:
            return None
        
        # Déjà complet
        if current_type and current_manufacturer:
            return None
        
        # Chercher des appareils similaires avec Type ET Fabricant renseignés
        similar_devices = self._find_similar_complete_devices(ref_modele, commercial_ref)
        
        if not similar_devices:
            return None
        
        # Prendre les valeurs les plus fréquentes
        best_match = self._select_best_completion_match(similar_devices)
        
        updates = {}
        completed_fields = []
        
        # Compléter Type si manquant
        if not current_type and best_match.get('type'):
            updates['type'] = best_match['type']
            completed_fields.append('Type')
        
        # Compléter Fabricant si manquant
        if not current_manufacturer and best_match.get('manufacturer'):
            updates['manufacturer'] = best_match['manufacturer']
            completed_fields.append('Fabricant')
        
        # Appliquer les mises à jour
        if updates and self.main_window:
            success = self.main_window._update_device_info(db_id, updates)
            if success:
                return {'fields': completed_fields, 'values': updates}
        
        return None
    
    def _find_similar_complete_devices(self, ref_modele: str, commercial_ref: str) -> List[Dict[str, Any]]:
        """
        Trouver des appareils similaires avec Type ET Fabricant complets
        """
        similar_devices = []
        
        return self._safe_search_similar_devices(ref_modele, commercial_ref, similar_devices)

    @handle_data_management_errors(return_value=[])
    def _safe_search_similar_devices(self, ref_modele: str, commercial_ref: str, similar_devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rechercher des appareils similaires de manière sécurisée"""
        # Stratégie 1: Recherche par préfixes de référence
        search_patterns = []

        if ref_modele:
            # Extraire différents patterns de la référence
            patterns = self._extract_reference_patterns(ref_modele)
            search_patterns.extend(patterns)

        if commercial_ref:
            patterns = self._extract_reference_patterns(commercial_ref)
            search_patterns.extend(patterns)

        # Chercher pour chaque pattern
        for pattern in search_patterns:
            if len(pattern) >= 3:  # Pattern minimum
                query = """
                    SELECT type, manufacturer, ref_modele, commercial_ref, COUNT(*) as frequency
                    FROM appareils
                    WHERE (type IS NOT NULL AND type != '')
                      AND (manufacturer IS NOT NULL AND manufacturer != '')
                      AND (ref_modele LIKE ? OR commercial_ref LIKE ?)
                    GROUP BY type, manufacturer
                    ORDER BY frequency DESC
                    LIMIT 10
                """
                pattern_like = f"{pattern}%"
                rows = self.db_manager.execute_query(query, (pattern_like, pattern_like))

                for row in rows:
                    similar_devices.append({
                        'type': row[0],
                        'manufacturer': row[1],
                        'frequency': row[4]
                    })
        
        return similar_devices
    
    def _extract_reference_patterns(self, reference: str) -> List[str]:
        """
        Extraire des patterns utiles d'une référence pour la recherche
        """
        if not reference:
            return []
        
        patterns = []
        ref_clean = reference.strip().upper()
        
        # Pattern: premiers caractères (marque/série)
        if len(ref_clean) >= 3:
            patterns.append(ref_clean[:3])
        if len(ref_clean) >= 4:
            patterns.append(ref_clean[:4])
        if len(ref_clean) >= 5:
            patterns.append(ref_clean[:5])
        
        # Pattern: avant les chiffres (pour extraire marque)
        import re
        match = re.match(r'^([A-Z]+)', ref_clean)
        if match and len(match.group(1)) >= 2:
            patterns.append(match.group(1))
        
        # Pattern: avant tirets ou espaces
        parts = re.split(r'[-\s]+', ref_clean)
        if parts and len(parts[0]) >= 2:
            patterns.append(parts[0])
        
        return list(set(patterns))  # Dédupliquer
    
    def _select_best_completion_match(self, similar_devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sélectionner le meilleur match pour l'auto-complétion
        """
        if not similar_devices:
            return {}
        
        # Regrouper par type + fabricant et compter les occurrences
        combinations = {}
        for device in similar_devices:
            key = (device.get('type', ''), device.get('manufacturer', ''))
            if key not in combinations:
                combinations[key] = {'count': 0, 'type': device['type'], 'manufacturer': device['manufacturer']}
            combinations[key]['count'] += device.get('frequency', 1)
        
        # Prendre la combinaison la plus fréquente
        best_combination = max(combinations.values(), key=lambda x: x['count'])
        
        return {
            'type': best_combination['type'],
            'manufacturer': best_combination['manufacturer']
        }
    
    @handle_data_management_errors()
    def prepare_data_cleaning(self) -> Optional[Dict[str, Any]]:
        """
        Préparer le nettoyage des données avec analyse préalable

        Returns:
            Dict avec le résultat de la fenêtre ou None si annulé
        """
        # Importer et utiliser CleanupPreviewDialog
        from .cleanup_preview_refactored import CleanupPreviewDialog

        if not self.main_window:
            app_logger.error("MainWindow nécessaire pour CleanupPreviewDialog")
            return None

        # Ouvrir la fenêtre de prévisualisation
        preview_dialog = CleanupPreviewDialog(self.main_window)

        result = preview_dialog.exec_()
        user_choice = preview_dialog.get_user_choice()

        # Si l'utilisateur a annulé ou fermé la fenêtre
        if result != QDialog.Accepted and user_choice != 'applied':
            return None

        # Retourner un dict indiquant que la fenêtre a été utilisée avec succès
        return {'dialog_completed': True, 'user_choice': user_choice}
    
    def execute_data_cleaning(self, cleanup_options: Dict[str, Any]) -> Dict[str, int]:
        """
        Exécuter le nettoyage des données selon les options choisies
        
        Args:
            cleanup_options: Options de nettoyage de CleanupPreviewDialog
            
        Returns:
            Dict avec les statistiques du nettoyage effectué
        """
        if not self.main_window:
            return {'error': 'MainWindow requis pour le nettoyage'}
        
        return self._safe_execute_cleanup(cleanup_options)

    @handle_data_management_errors(return_value={'error': 'Erreur lors du nettoyage'})
    def _safe_execute_cleanup(self, cleanup_options: Dict[str, Any]) -> Dict[str, int]:
        """Exécuter le nettoyage de manière sécurisée"""
        # Exécuter le nettoyage des données selon les options
        stats = {'devices_deleted': 0, 'pieces_deleted': 0, 'pieces_merged': 0}

        # Nettoyer les appareils dupliqués si demandé
        if cleanup_options.get('clean_devices', False):
            devices_deleted = self.db_manager.remove_duplicate_devices()
            stats['devices_deleted'] = devices_deleted

        # Nettoyer les pièces dupliquées si demandé
        if cleanup_options.get('clean_pieces', False):
            pieces_deleted = self.db_manager.remove_duplicate_pieces()
            stats['pieces_deleted'] = pieces_deleted
            stats['pieces_merged'] = pieces_deleted  # Les pièces supprimées sont effectivement "fusionnées"

        return stats