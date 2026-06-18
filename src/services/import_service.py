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
from ..utils.error_handler import handle_import_errors

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
    
