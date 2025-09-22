"""
Service de détection de doublons lors des imports - Phase 2.3+
Gère intelligemment les doublons cross-fichiers vs intra-fichiers
"""

from typing import Dict, Set, Tuple, List
from ..core.logger import app_logger

class ImportDuplicatesService:
    """Service de détection intelligente des doublons lors des imports multi-fichiers"""
    
    def __init__(self):
        # Tracking des associations par fichier
        self.associations_by_file: Dict[str, Set[Tuple[str, int]]] = {}  # {file_path: {(piece_ref, device_id)}}
        
        # Tracking global des associations déjà créées dans cette session d'import
        self.global_associations: Set[Tuple[str, int]] = set()  # {(piece_ref, device_id)}
        
        # Compteurs de doublons détectés
        self.duplicates_stats = {
            'cross_file_associations_created': 0,  # Associations créées malgré device dupliqué
            'intra_file_duplicates_skipped': 0,    # Doublons dans même fichier ignorés
            'total_processed': 0
        }
    
    def reset_session(self):
        """Réinitialiser pour nouvelle session d'import"""
        self.associations_by_file.clear()
        self.global_associations.clear()
        self.duplicates_stats = {
            'cross_file_associations_created': 0,
            'intra_file_duplicates_skipped': 0,
            'total_processed': 0
        }
        app_logger.info("Session de détection de doublons réinitialisée")
    
    def should_create_association(self, piece_ref: str, device_id: int, file_path: str) -> bool:
        """
        Détermine si une association pièce-device doit être créée
        
        Règles:
        1. Même pièce + même device dans même fichier = SKIP (doublon intra-fichier)
        2. Même pièce + même device dans fichier différent = CREATE (association cross-fichier)
        3. Nouvelle association = CREATE
        """
        self.duplicates_stats['total_processed'] += 1
        
        # Clé de l'association
        association_key = (piece_ref, device_id)
        
        # Initialiser tracking pour ce fichier si nécessaire
        if file_path not in self.associations_by_file:
            self.associations_by_file[file_path] = set()
        
        current_file_associations = self.associations_by_file[file_path]
        
        # CAS 1: Déjà vu dans le même fichier → SKIP (doublon intra-fichier)
        if association_key in current_file_associations:
            self.duplicates_stats['intra_file_duplicates_skipped'] += 1
            app_logger.debug(f"Doublon intra-fichier ignoré: {piece_ref} → device {device_id} dans {file_path}")
            return False
        
        # CAS 2: Déjà vu globalement mais pas dans ce fichier → CREATE (cross-fichier)
        if association_key in self.global_associations:
            self.duplicates_stats['cross_file_associations_created'] += 1
            app_logger.info(f"Association cross-fichier créée: {piece_ref} → device {device_id} (fichier: {file_path})")
            
            # Enregistrer dans le fichier courant
            current_file_associations.add(association_key)
            return True
        
        # CAS 3: Nouvelle association → CREATE
        current_file_associations.add(association_key)
        self.global_associations.add(association_key)
        return True
    
    def get_file_statistics(self, file_path: str) -> Dict[str, int]:
        """Obtenir statistiques pour un fichier spécifique"""
        if file_path not in self.associations_by_file:
            return {'associations_count': 0}
        
        return {
            'associations_count': len(self.associations_by_file[file_path]),
            'unique_devices': len({device_id for _, device_id in self.associations_by_file[file_path]}),
            'unique_pieces': len({piece_ref for piece_ref, _ in self.associations_by_file[file_path]})
        }
    
    def get_session_statistics(self) -> Dict[str, int]:
        """Obtenir statistiques complètes de la session"""
        stats = self.duplicates_stats.copy()
        stats.update({
            'total_files_processed': len(self.associations_by_file),
            'unique_global_associations': len(self.global_associations),
            'total_devices': len({device_id for _, device_id in self.global_associations}),
            'total_pieces': len({piece_ref for piece_ref, _ in self.global_associations})
        })
        return stats
    
    def log_session_summary(self):
        """Logger un résumé de la session d'import"""
        stats = self.get_session_statistics()
        
        app_logger.info("=== RÉSUMÉ DÉTECTION DOUBLONS IMPORT ===")
        app_logger.info(f"📁 Fichiers traités: {stats['total_files_processed']}")
        app_logger.info(f"🔗 Associations créées: {stats['unique_global_associations']}")
        app_logger.info(f"✅ Associations cross-fichiers: {stats['cross_file_associations_created']}")
        app_logger.info(f"⏭️ Doublons intra-fichier ignorés: {stats['intra_file_duplicates_skipped']}")
        app_logger.info(f"📊 Total traité: {stats['total_processed']}")
        
        if stats['cross_file_associations_created'] > 0:
            app_logger.info(f"🎯 Succès: {stats['cross_file_associations_created']} associations multi-fichiers créées")
    
    def get_cross_file_duplicates_report(self) -> List[Dict]:
        """Générer rapport des doublons cross-fichiers pour l'utilisateur"""
        cross_file_devices = {}  # device_id: [list of files]
        
        for file_path, associations in self.associations_by_file.items():
            for piece_ref, device_id in associations:
                if device_id not in cross_file_devices:
                    cross_file_devices[device_id] = []
                cross_file_devices[device_id].append(file_path)
        
        # Filtrer seulement les devices qui apparaissent dans plusieurs fichiers
        duplicates_report = []
        for device_id, files in cross_file_devices.items():
            if len(files) > 1:
                duplicates_report.append({
                    'device_id': device_id,
                    'files': files,
                    'occurrences_count': len(files)
                })
        
        return duplicates_report