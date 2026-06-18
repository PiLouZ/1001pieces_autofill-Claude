"""
Processeur de données pour le collage depuis le presse-papiers
Extrait de main_refactored.py pour améliorer la maintenabilité
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from src.core.config import Config
from src.core.logger import app_logger
from src.services.base_service import safe_operation


@dataclass
class PasteProcessingResult:
    """Résultat du traitement des données collées"""
    inserted_count: int = 0
    updated_count: int = 0
    ignored_count: int = 0
    associations_created: int = 0
    duplicates_skipped: int = 0
    manual_completion_count: int = 0
    no_piece_ref_count: int = 0
    descriptions_updated: int = 0
    duplicates_list: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.duplicates_list is None:
            self.duplicates_list = []


class PasteDataProcessor:
    """
    Processeur spécialisé pour le traitement des données d'import (collage + CSV/PDF)
    
    Responsabilités:
    - Parser et nettoyer les données du presse-papiers
    - Traiter les imports de fichiers CSV/PDF  
    - Mapper les colonnes selon les règles métier
    - Traiter les données par lots pour optimiser les performances
    - Gérer la logique de validation et de déduplication
    """
    
    def __init__(self, db_manager, validator, main_window=None):
        self.db_manager = db_manager
        self.validator = validator
        self.main_window = main_window  # Pour accès aux méthodes helper existantes
        
    def detect_separator(self, clipboard_text: str) -> str:
        """Détecter le séparateur utilisé dans les données"""
        return '\t' if '\t' in clipboard_text else ';'
    
    def detect_columns_count(self, clipboard_text: str) -> int:
        """Détecter le nombre de colonnes des données collées"""
        lines = clipboard_text.strip().split('\n')
        if not lines:
            return 0
            
        separator = self.detect_separator(clipboard_text)
        column_counts = []
        
        # Analyser les 5 premières lignes pour détecter la structure
        for line in lines[:5]:
            if line.strip():
                columns = len(line.split(separator))
                column_counts.append(columns)
        
        if not column_counts:
            return 0
            
        # Prendre le nombre de colonnes le plus fréquent
        return max(set(column_counts), key=column_counts.count)
    
    def parse_clipboard_data(self, clipboard_text: str) -> List[List[str]]:
        """Parser les données du presse-papiers en lignes et colonnes"""
        lines = clipboard_text.strip().split('\n')
        separator = self.detect_separator(clipboard_text)
        rows = [line.split(separator) for line in lines]
        
        # Nettoyer les données
        cleaned_rows = []
        for row in rows:
            clean_row = []
            for cell in row:
                if cell:
                    # Supprimer les caractères de contrôle dangereux
                    cleaned_cell = ''.join(
                        char for char in cell 
                        if char not in ['\0', '\r', '\n', '\t']
                    ).strip()
                    clean_row.append(cleaned_cell)
                else:
                    clean_row.append('')
            cleaned_rows.append(clean_row)
        
        return cleaned_rows
    
    def map_row_to_device_data(self, clean_row: List[str], third_column_choice: str = "ignore") -> Dict[str, Any]:
        """
        Mapper une ligne de données vers la structure appareil
        
        Args:
            clean_row: Ligne de données nettoyées
            third_column_choice: Choix pour la 3ème colonne ("other_ref", "notes", ou "ignore")
            
        Returns:
            Dict contenant les données de l'appareil mappées
        """
        num_cols = len(clean_row)
        appareil_data = {}
        
        if num_cols >= 4:
            # 4+ colonnes : mapper directement sur tous les champs DB
            for i, header in enumerate(Config.DB_HEADERS):
                if i < len(clean_row):
                    appareil_data[header] = clean_row[i]
                else:
                    appareil_data[header] = ''
                    
        elif num_cols == 1:
            # 1 colonne : mapper sur ref_modele uniquement
            appareil_data = {
                'type': '',
                'manufacturer': '',
                'ref_modele': clean_row[0],
                'commercial_ref': '',
                'other_ref': '',
                'category': '',
                'notes': ''
            }
            
        elif num_cols == 2 or num_cols == 3:
            # 2-3 colonnes : laisser Type et Fabricant vides pour auto-completion
            appareil_data = {
                'type': '',      # Sera auto-complété
                'manufacturer': '',  # Sera auto-complété
                'category': '',
                'notes': ''
            }
            
            # Mapper selon le nombre de colonnes
            if num_cols == 2:
                mapping_headers = ['ref_modele', 'commercial_ref']
            else:  # num_cols == 3
                if third_column_choice == "ignore":
                    mapping_headers = ['ref_modele', 'commercial_ref']
                else:
                    mapping_headers = ['ref_modele', 'commercial_ref', third_column_choice]
            
            for i, value in enumerate(clean_row):
                if i < len(mapping_headers):
                    appareil_data[mapping_headers[i]] = value
            
            # Compléter les autres champs manquants
            remaining_headers = ['other_ref', 'category', 'notes']
            for header in remaining_headers:
                if header not in appareil_data:
                    appareil_data[header] = ''
        else:
            # Nombre de colonnes non supporté
            return None
        
        return appareil_data
    
    def validate_device_data(self, device_data: Dict[str, Any], row_idx: int) -> bool:
        """
        Valider les données d'un appareil
        
        Args:
            device_data: Données de l'appareil à valider
            row_idx: Index de la ligne pour les logs
            
        Returns:
            True si valide, False sinon (mais continue l'import avec avertissement)
        """
        validation_result = self.validator.validate_record(device_data)
        if not validation_result.is_valid:
            app_logger.warning(
                f"Données ligne {row_idx + 1} avec avertissement: {validation_result.error_message}"
            )
            app_logger.warning(f"⚠️ Ligne {row_idx + 1}: VALIDATION: {validation_result.error_message} - Continuant l'import...")
            app_logger.warning(f"    Données concernées: {device_data}")
            return False  # Mais on continue l'import
        return True
    
    def _process_single_device(self, appareil_data: Dict[str, Any], row_idx: int,
                             ref_piece: str, libelle_piece: str,
                             piece_description_decisions: Dict,
                             result: PasteProcessingResult) -> Dict[str, Any]:
        """
        Traiter un seul appareil (recherche/création + associations)
        Cette méthode fait encore appel aux méthodes de MainWindow
        """
        # Chercher si l'appareil existe déjà
        existing_device = self.main_window._find_existing_device_by_refs(
            appareil_data.get('ref_modele', ''), 
            appareil_data.get('commercial_ref', ''),
            appareil_data.get('type', ''),
            appareil_data.get('manufacturer', '')
        )
        
        device_result = {'action': None, 'device_id': None}
        
        if existing_device:
            # Appareil existant - mettre à jour les champs manquants
            appareil_id = existing_device['id']
            
            # Préparer les mises à jour nécessaires
            updates = {}
            for field in ['type', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref', 'category', 'notes']:
                new_value = appareil_data.get(field, '').strip()
                if new_value and not existing_device.get(field):
                    updates[field] = new_value
            
            # Appliquer les mises à jour
            if updates:
                self.main_window._update_device_info(appareil_id, updates)
                device_result['action'] = 'updated'
            else:
                device_result['action'] = 'found'
                
            device_result['device_id'] = appareil_id
            
        else:
            # Nouvel appareil à créer - utiliser directement le DatabaseManager
            # Filtrer les valeurs vides pour une insertion propre
            filtered_data = {k: v for k, v in appareil_data.items() if v and str(v).strip()}

            if filtered_data:
                appareil_id = self.main_window._create_new_device(filtered_data)
                if appareil_id:
                    device_result['action'] = 'created'
                    device_result['device_id'] = appareil_id
                else:
                    app_logger.warning(f"❌ Ligne {row_idx + 1}: Échec création appareil")
                    device_result['action'] = 'failed'
                    return device_result
            else:
                app_logger.warning(f"❌ Ligne {row_idx + 1}: Données appareil vides après filtrage")
                device_result['action'] = 'failed'
                return device_result
        
        # Créer l'association pièce si nécessaire
        if ref_piece and device_result['device_id']:
            association_result = self.main_window.device_manager.create_piece_association(
                device_result['device_id'], ref_piece, libelle_piece,
                piece_description_decisions
            )
            device_result['association'] = association_result
        
        return device_result

    def _needs_manual_completion(self, device_data: Dict[str, str]) -> bool:
        """
        Vérifier si l'appareil nécessite une complétion manuelle
        
        Args:
            device_data: Données de l'appareil
            
        Returns:
            bool: True si complétion manuelle nécessaire
        """
        # Vérifier si les champs obligatoires sont vides
        return not (device_data.get('type', '').strip() and device_data.get('manufacturer', '').strip())

    def _update_result_stats(self, result: PasteProcessingResult, device_result: Dict[str, Any]):
        """Mettre à jour les statistiques selon le résultat du traitement"""
        action = device_result.get('action')
        
        if action == 'created':
            result.inserted_count += 1
        elif action == 'updated':
            result.updated_count += 1
        elif action == 'found':
            # Appareil existant sans mise à jour
            pass
        elif action == 'failed':
            result.ignored_count += 1
        
        # Statistiques associations
        association = device_result.get('association', {})
        if association.get('created'):
            result.associations_created += 1
        elif association.get('exists'):
            result.duplicates_skipped += 1
        
        if association.get('description_updated'):
            result.descriptions_updated += 1
    
    def _map_import_row_to_device_data(self, row: List[str], third_column_choice: str, import_type: str) -> Dict[str, Any]:
        """
        Mapper une ligne d'import vers la structure appareil
        Logique différente du collage : colonnes fixes selon import_type
        
        Args:
            row: Ligne de données du fichier
            third_column_choice: Choix pour la 3ème colonne
            import_type: "CSV" ou "PDF" 
            
        Returns:
            Dict contenant les données de l'appareil mappées
        """
        if not row:
            return None
            
        # Initialisation des variables par défaut
        type_val = ""
        manufacturer = ""
        ref_modele = ""
        commercial_ref = ""
        other_ref = ""
        notes = ""
        
        # Logique de mapping spécifique aux imports (différente du collage)
        if len(row) >= 1:
            ref_modele = str(row[0]).strip() if row[0] else ""
        if len(row) >= 2:
            commercial_ref = str(row[1]).strip() if row[1] else ""
        if len(row) >= 3 and third_column_choice != "ignore":
            if third_column_choice == "other_ref":
                other_ref = str(row[2]).strip() if row[2] else ""
            elif third_column_choice == "notes":
                notes = str(row[2]).strip() if row[2] else ""
            # Pour les imports > 3 colonnes, mapper les colonnes suivantes
        if len(row) >= 4:
            type_val = str(row[3]).strip() if row[3] else ""
        if len(row) >= 5:
            manufacturer = str(row[4]).strip() if row[4] else ""
        if len(row) >= 6 and not other_ref:  # Si pas déjà mappé via 3ème colonne
            other_ref = str(row[5]).strip() if row[5] else ""
        if len(row) >= 7 and not notes:  # Si pas déjà mappé via 3ème colonne
            notes = str(row[6]).strip() if row[6] else ""
        
        # Vérifier qu'on a au moins une référence
        if not ref_modele and not commercial_ref:
            return None
            
        return {
            'type': type_val,
            'manufacturer': manufacturer,
            'ref_modele': ref_modele,
            'commercial_ref': commercial_ref,
            'other_ref': other_ref,
            'category': '',
            'notes': notes
        }
    
    def _make_device_key(self, device_data: Dict[str, Any]) -> str:
        """Créer une clé unique pour détecter les doublons"""
        ref_modele = (device_data.get('ref_modele') or '').strip().lower()
        commercial_ref = (device_data.get('commercial_ref') or '').strip().lower()
        return f"{ref_modele}|{commercial_ref}"
    
    def _process_single_import_device(self, device_data: Dict[str, Any], row_idx: int,
                                    ref_piece: str, libelle_piece: str,
                                    piece_description_decisions: Dict,
                                    result: PasteProcessingResult) -> Dict[str, Any]:
        """
        Traiter un seul appareil d'import (recherche/création + associations)
        """
        # Chercher si l'appareil existe déjà
        existing_device = self.main_window._find_existing_device_by_refs(
            device_data.get('ref_modele', ''), 
            device_data.get('commercial_ref', ''),
            device_data.get('type', ''),
            device_data.get('manufacturer', '')
        )
        
        device_result = {'action': None, 'device_id': None, 'auto_completed': False}
        
        if existing_device:
            # Appareil existant - mettre à jour avec les nouvelles valeurs
            device_id = existing_device['id']
            print(f"🔄 Ligne {row_idx + 1}: Appareil existant trouvé (ID: {device_id})")
            
            # Pour les imports, mettre à jour si nouvelle valeur fournie
            updates = {}
            for field in ['type', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref', 'notes']:
                new_value = device_data.get(field, '').strip()
                if new_value:
                    updates[field] = new_value
            
            if updates:
                self.main_window._update_device_info(device_id, updates)
                device_result['action'] = 'updated'
            else:
                device_result['action'] = 'found'
                
            device_result['device_id'] = device_id
            
        else:
            # Nouvel appareil à créer
            if (device_data.get('ref_modele', '').strip() or 
                device_data.get('commercial_ref', '').strip()):
                
                
                # Essayer l'auto-complétion AVANT création
                auto_completion_success = False
                if (not device_data.get('type') or not device_data.get('manufacturer')):
                    auto_completion_success = self.main_window._try_auto_complete(device_data)
                    device_result['auto_completed'] = auto_completion_success
                
                # Filtrer les données vides
                filtered_data = {k: v for k, v in device_data.items() if v and str(v).strip()}
                
                # S'assurer qu'on a les références essentielles
                if 'ref_modele' not in filtered_data and device_data.get('ref_modele', '').strip():
                    filtered_data['ref_modele'] = device_data['ref_modele'].strip()
                if 'commercial_ref' not in filtered_data and device_data.get('commercial_ref', '').strip():
                    filtered_data['commercial_ref'] = device_data['commercial_ref'].strip()
                
                if filtered_data:
                    device_id = self.db_manager.insert_appareil(filtered_data)
                    if device_id:
                        device_result['action'] = 'created'
                        device_result['device_id'] = device_id
                        device_result['needs_completion'] = self.main_window._needs_manual_completion(filtered_data)
                    else:
                        app_logger.warning(f"❌ Ligne {row_idx + 1}: Échec création appareil")
                        device_result['action'] = 'failed'
                        return device_result
                else:
                    device_result['action'] = 'failed'
                    return device_result
            else:
                device_result['action'] = 'failed'
                return device_result
        
        # Créer l'association pièce si nécessaire
        if ref_piece and device_result['device_id']:
            association_result = self.main_window.device_manager.create_piece_association(
                device_result['device_id'], ref_piece, libelle_piece,
                piece_description_decisions
            )
            device_result['association'] = association_result
        
        return device_result
    
    def _update_import_result_stats(self, result: PasteProcessingResult, device_result: Dict[str, Any]):
        """Mettre à jour les statistiques selon le résultat du traitement d'import"""
        action = device_result.get('action')
        
        if action == 'created':
            result.inserted_count += 1
            if device_result.get('auto_completed'):
                result.auto_completed += 1
            if device_result.get('needs_completion'):
                result.manual_completion_count += 1
        elif action == 'updated':
            result.updated_count += 1
        elif action == 'found':
            result.matches_found += 1
        elif action == 'failed':
            result.ignored_count += 1
        
        # Statistiques associations
        association = device_result.get('association', {})
        if association.get('created'):
            result.associations_created += 1
        elif association.get('exists'):
            result.duplicates_skipped += 1
        
        if association.get('description_updated'):
            result.descriptions_updated += 1