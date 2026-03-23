"""
Import Service - Phase 4 Architecture Refactoring
Sépare la logique d'import de l'interface utilisateur
"""

from typing import Dict, Any, Optional, List
import os
from ..core.import_manager import ImportManager, ImportConfiguration
from ..data.database_manager import DatabaseManager
from .event_bus import event_bus
from .base_service import BaseService
from ..utils.error_handler import handle_import_errors, handle_file_errors, handle_validation_errors

class ImportService(BaseService):
    """Service dédié aux opérations d'import"""
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.import_manager = ImportManager(db_manager)
    
    def import_files(self, files: List[str],
                    config_options: Dict[str, Any]) -> Dict[str, Any]:
        """Importer des fichiers avec configuration"""

        event_bus.emit('import.started', {
            'file_count': len(files),
            'options': config_options
        })

        return self._safe_import_files_core(files, config_options)

    @handle_import_errors()
    def _safe_import_files_core(self, files: List[str], config_options: Dict[str, Any]) -> Dict[str, Any]:
        """Noyau sécurisé pour l'import de fichiers"""
        # Créer la configuration d'import
        config = self._build_import_config(files, config_options)

        # Exécuter l'import
        results = self.import_manager._execute_import(config)

        # Enrichir les résultats
        results.update({
            'success': True,
            'config_used': config_options
        })

        event_bus.emit('import.completed', results)
        return results
    
    def _build_import_config(self, files: List[str], 
                           options: Dict[str, Any]) -> ImportConfiguration:
        """Construire la configuration d'import"""
        
        config = ImportConfiguration()
        
        # Configuration globale
        config.use_common_reference = options.get('use_common_reference', False)
        config.common_reference = options.get('common_reference', '')
        config.common_label = options.get('common_label', '')
        
        # Traitement des fichiers
        for file_path in files:
            # Déterminer le type de fichier
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext == '.pdf':
                file_type = self.import_manager.FileType.PDF
            elif file_ext == '.csv':
                file_type = self.import_manager.FileType.CSV
            else:
                continue  # Ignorer les types non supportés
            
            # Créer l'objet ImportFile
            import_file = self.import_manager.ImportFile(
                path=file_path,
                filename=os.path.basename(file_path),
                type=file_type,
                suggested_reference=self._suggest_reference(file_path)
            )
            
            config.files.append(import_file)
            
            # Configuration spécifique au fichier
            if options.get('auto_file_references', True):
                config.individual_references[file_path] = import_file.suggested_reference
                config.individual_labels[file_path] = options.get('file_label', '')
        
        # Configuration des colonnes
        config.third_column_choice = options.get('third_column_choice', 'ignore')
        
        return config
    
    def _suggest_reference(self, file_path: str) -> str:
        """Suggérer une référence basée sur le nom du fichier"""
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]
        
        # Nettoyer le nom pour en faire une référence valide
        reference = name_without_ext.replace(' ', '_').replace('-', '_')
        
        # Garder seulement les caractères alphanumériques et underscores
        reference = ''.join(c for c in reference if c.isalnum() or c == '_')
        
        return reference
    
    @handle_file_errors()
    def preview_file(self, file_path: str, max_rows: int = 5) -> Dict[str, Any]:
        """Prévisualiser le contenu d'un fichier avant import"""
        # Déterminer le type
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == '.pdf':
            data = self.import_manager.load_pdf_data(file_path, max_rows=max_rows)
            file_type = 'PDF'
        elif file_ext == '.csv':
            data = self.import_manager.load_csv_data(file_path, max_rows=max_rows)
            file_type = 'CSV'
        else:
            return {
                'success': False,
                'error': f'Type de fichier non supporté: {file_ext}'
            }

        return {
            'success': True,
            'file_type': file_type,
            'sample_data': data,
            'suggested_reference': self._suggest_reference(file_path),
            'columns_detected': len(data[0]) if data else 0
        }
    
    def validate_files(self, files: List[str]) -> Dict[str, Any]:
        """Valider une liste de fichiers avant import"""
        validation_results = {
            'valid_files': [],
            'invalid_files': [],
            'total_size': 0,
            'estimated_records': 0
        }
        
        for file_path in files:
            result = self._safe_validate_single_file(file_path, validation_results)
            if result:
                validation_results['valid_files'].append(result)

    @handle_validation_errors()
    def _safe_validate_single_file(self, file_path: str, validation_results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Valider un fichier de manière sécurisée"""
        # Vérifier existence
        if not os.path.exists(file_path):
            validation_results['invalid_files'].append({
                'file': file_path,
                'error': 'Fichier introuvable'
            })
            return None

        # Vérifier taille
        file_size = os.path.getsize(file_path)
        validation_results['total_size'] += file_size

        # Vérifier type
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in ['.pdf', '.csv']:
            validation_results['invalid_files'].append({
                'file': file_path,
                'error': f'Type de fichier non supporté: {file_ext}'
            })
            return None

        # Estimer le nombre d'enregistrements
        preview = self.preview_file(file_path, max_rows=10)
        estimated_records = 0
        if preview and preview.get('success'):
            estimated_records = len(preview['sample_data']) * 10  # Estimation grossière
            validation_results['estimated_records'] += estimated_records

        return {
            'file': file_path,
            'type': file_ext[1:].upper(),
            'size': file_size,
            'estimated_records': estimated_records
        }