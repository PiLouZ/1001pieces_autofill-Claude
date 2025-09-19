"""
Service d'analyse des doublons
Centralise toute la logique d'analyse et de détection des doublons
"""

import re
from typing import Dict, List, Any, Optional, Tuple, Set
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer

from ..core.logger import app_logger
from ..data.database_manager import DatabaseManager


def clean_display_text(text: str) -> str:
    """Nettoie le texte pour l'affichage en supprimant les caractères illisibles"""
    if not text:
        return ""
    text = str(text)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    try:
        text = text.encode('utf-8', errors='replace').decode('utf-8')
    except:
        text = "???"
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


class DuplicatesAnalysisWorker(QThread):
    """Worker thread pour l'analyse des doublons"""
    
    progress_updated = pyqtSignal(int, str)  # pourcentage, message
    analysis_completed = pyqtSignal(dict)    # résultats
    analysis_error = pyqtSignal(str)         # message d'erreur
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.should_stop = False
        
    def stop(self):
        """Arrêter l'analyse"""
        self.should_stop = True
        
    def run(self):
        """Exécuter l'analyse des doublons"""
        try:
            results = {
                'duplicate_devices': [],
                'duplicate_pieces': [],
                'potential_inconsistencies': [],
                'statistics': {}
            }
            
            # Phase 1: Analyse des appareils en doublon
            self.progress_updated.emit(10, "Recherche des appareils en doublon...")
            if not self.should_stop:
                results['duplicate_devices'] = self._find_duplicate_devices()
                
            # Phase 2: Analyse des pièces dupliquées
            self.progress_updated.emit(40, "Recherche des pièces dupliquées...")
            if not self.should_stop:
                results['duplicate_pieces'] = self._find_duplicate_pieces()
                
            # Phase 3: Analyse des incohérences potentielles
            self.progress_updated.emit(70, "Analyse des incohérences potentielles...")
            if not self.should_stop:
                results['potential_inconsistencies'] = self._find_potential_inconsistencies()
                
            # Phase 4: Calcul des statistiques
            self.progress_updated.emit(90, "Calcul des statistiques...")
            if not self.should_stop:
                results['statistics'] = self._calculate_statistics(results)
                
            self.progress_updated.emit(100, "Analyse terminée")
            
            if not self.should_stop:
                self.analysis_completed.emit(results)
                
        except Exception as e:
            app_logger.error(f"Erreur lors de l'analyse des doublons: {e}")
            self.analysis_error.emit(f"Erreur lors de l'analyse: {str(e)}")
            
    def _find_duplicate_devices(self) -> List[Dict[str, Any]]:
        """Trouver les appareils en doublon basés sur ref_modele"""
        try:
            query = """
            SELECT ref_modele, COUNT(*) as count, GROUP_CONCAT(id) as ids
            FROM appareils 
            WHERE ref_modele IS NOT NULL AND ref_modele != '' 
            GROUP BY ref_modele 
            HAVING count > 1
            ORDER BY count DESC
            """
            
            results = self.db_manager.execute_query(query)
            duplicates = []
            
            for row in results:
                ref_modele, count, ids_str = row
                ids = [int(id_str) for id_str in ids_str.split(',')]
                
                # Récupérer les détails de chaque appareil
                devices = []
                for device_id in ids:
                    device_query = """
                    SELECT id, ref_modele, type_appareil, manufacturer, 
                           commercial_ref, designation, pieces_count
                    FROM appareils WHERE id = ?
                    """
                    device_details = self.db_manager.execute_query(device_query, (device_id,))
                    if device_details:
                        device = {
                            'id': device_details[0][0],
                            'ref_modele': clean_display_text(device_details[0][1]),
                            'type_appareil': clean_display_text(device_details[0][2] or ''),
                            'manufacturer': clean_display_text(device_details[0][3] or ''),
                            'commercial_ref': clean_display_text(device_details[0][4] or ''),
                            'designation': clean_display_text(device_details[0][5] or ''),
                            'pieces_count': device_details[0][6] or 0
                        }
                        devices.append(device)
                        
                duplicates.append({
                    'ref_modele': ref_modele,
                    'count': count,
                    'devices': devices
                })
                
            return duplicates
            
        except Exception as e:
            app_logger.error(f"Erreur recherche appareils doublons: {e}")
            return []
            
    def _find_duplicate_pieces(self) -> List[Dict[str, Any]]:
        """Trouver les pièces dupliquées basées sur ref_piece"""
        try:
            query = """
            SELECT ref_piece, COUNT(*) as count
            FROM pieces 
            WHERE ref_piece IS NOT NULL AND ref_piece != ''
            GROUP BY ref_piece 
            HAVING count > 1
            ORDER BY count DESC
            LIMIT 100
            """
            
            results = self.db_manager.execute_query(query)
            duplicates = []
            
            for row in results:
                ref_piece, count = row
                duplicates.append({
                    'ref_piece': clean_display_text(ref_piece),
                    'count': count
                })
                
            return duplicates
            
        except Exception as e:
            app_logger.error(f"Erreur recherche pièces dupliquées: {e}")
            return []
            
    def _find_potential_inconsistencies(self) -> List[Dict[str, Any]]:
        """Trouver les incohérences potentielles"""
        try:
            # Rechercher les appareils avec des références modèle similaires mais pas identiques
            query = """
            SELECT DISTINCT a1.id, a1.ref_modele, a1.type_appareil, a1.manufacturer,
                   a2.id, a2.ref_modele, a2.type_appareil, a2.manufacturer
            FROM appareils a1, appareils a2
            WHERE a1.id < a2.id
            AND a1.ref_modele IS NOT NULL AND a2.ref_modele IS NOT NULL
            AND a1.ref_modele != a2.ref_modele
            AND (
                -- Références très similaires (distance de Levenshtein approximative)
                LENGTH(a1.ref_modele) > 3 AND LENGTH(a2.ref_modele) > 3
                AND (
                    a1.ref_modele LIKE '%' || SUBSTR(a2.ref_modele, 1, LENGTH(a2.ref_modele)-1) || '%'
                    OR a2.ref_modele LIKE '%' || SUBSTR(a1.ref_modele, 1, LENGTH(a1.ref_modele)-1) || '%'
                    OR ABS(LENGTH(a1.ref_modele) - LENGTH(a2.ref_modele)) <= 2
                )
                -- Même type et fabricant mais références différentes
                OR (a1.type_appareil = a2.type_appareil 
                    AND a1.manufacturer = a2.manufacturer
                    AND a1.type_appareil IS NOT NULL
                    AND a1.manufacturer IS NOT NULL)
            )
            ORDER BY a1.ref_modele, a2.ref_modele
            LIMIT 200
            """
            
            results = self.db_manager.execute_query(query)
            inconsistencies = []
            
            processed_pairs = set()
            
            for row in results:
                id1, ref1, type1, manuf1, id2, ref2, type2, manuf2 = row
                
                # Éviter les doublons en utilisant un tuple ordonné
                pair_key = tuple(sorted([id1, id2]))
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)
                
                inconsistency = {
                    'devices': [
                        {
                            'id': id1,
                            'ref_modele': clean_display_text(ref1),
                            'type_appareil': clean_display_text(type1 or ''),
                            'manufacturer': clean_display_text(manuf1 or '')
                        },
                        {
                            'id': id2,
                            'ref_modele': clean_display_text(ref2),
                            'type_appareil': clean_display_text(type2 or ''),
                            'manufacturer': clean_display_text(manuf2 or '')
                        }
                    ],
                    'similarity_score': self._calculate_similarity(ref1, ref2),
                    'decision': None  # 'merge', 'keep_separate', ou None
                }
                inconsistencies.append(inconsistency)
                
            return inconsistencies
            
        except Exception as e:
            app_logger.error(f"Erreur recherche incohérences: {e}")
            return []
            
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculer un score de similitude simple entre deux textes"""
        if not text1 or not text2:
            return 0.0
            
        text1, text2 = text1.lower(), text2.lower()
        
        # Similitude basée sur les caractères communs
        set1, set2 = set(text1), set(text2)
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        if union == 0:
            return 0.0
            
        return intersection / union
        
    def _calculate_statistics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculer les statistiques d'analyse"""
        stats = {
            'total_duplicate_devices': len(results['duplicate_devices']),
            'total_affected_devices': sum(group['count'] for group in results['duplicate_devices']),
            'total_duplicate_pieces': len(results['duplicate_pieces']),
            'total_affected_pieces': sum(group['count'] for group in results['duplicate_pieces']),
            'total_potential_inconsistencies': len(results['potential_inconsistencies']),
            'potential_savings_devices': 0,
            'potential_savings_pieces': 0
        }
        
        # Calcul des économies potentielles (appareils en trop qui pourraient être supprimés)
        for group in results['duplicate_devices']:
            stats['potential_savings_devices'] += group['count'] - 1  # Garder un exemplaire
            
        for group in results['duplicate_pieces']:
            stats['potential_savings_pieces'] += group['count'] - 1
            
        return stats


class DuplicatesAnalysisService(QObject):
    """Service d'analyse des doublons"""
    
    analysis_started = pyqtSignal()
    analysis_progress = pyqtSignal(int, str)  # pourcentage, message
    analysis_completed = pyqtSignal(dict)     # résultats
    analysis_error = pyqtSignal(str)          # message d'erreur
    
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.analysis_worker = None
        self.current_results = None
        
    def start_analysis(self):
        """Démarrer l'analyse des doublons"""
        if self.analysis_worker and self.analysis_worker.isRunning():
            app_logger.warning("Analyse déjà en cours")
            return
            
        self.analysis_worker = DuplicatesAnalysisWorker(self.db_manager)
        
        # Connecter les signaux
        self.analysis_worker.progress_updated.connect(self.analysis_progress.emit)
        self.analysis_worker.analysis_completed.connect(self._on_analysis_completed)
        self.analysis_worker.analysis_error.connect(self.analysis_error.emit)
        
        self.analysis_started.emit()
        self.analysis_worker.start()
        
    def stop_analysis(self):
        """Arrêter l'analyse en cours"""
        if self.analysis_worker and self.analysis_worker.isRunning():
            self.analysis_worker.stop()
            self.analysis_worker.wait(3000)  # Attendre 3 secondes max
            
    def _on_analysis_completed(self, results: Dict[str, Any]):
        """Gérer la fin d'analyse"""
        self.current_results = results
        self.analysis_completed.emit(results)
        app_logger.info(f"Analyse doublons terminée: {results['statistics']}")
        
    def get_current_results(self) -> Optional[Dict[str, Any]]:
        """Obtenir les résultats de la dernière analyse"""
        return self.current_results
        
    def apply_cleanup_decisions(self, cleanup_options: Dict[str, Any]) -> Dict[str, Any]:
        """Appliquer les décisions de nettoyage"""
        try:
            results = {
                'devices_merged': 0,
                'devices_deleted': 0,
                'pieces_deleted': 0,
                'inconsistencies_resolved': 0,
                'errors': []
            }
            
            # Traiter les fusions d'appareils
            if 'device_merges' in cleanup_options:
                for merge_info in cleanup_options['device_merges']:
                    try:
                        master_id = merge_info['master_id']
                        duplicate_ids = merge_info['duplicate_ids']

                        app_logger.info(f"Tentative de fusion: maître={master_id}, doublons={duplicate_ids}")

                        # Vérifier que les IDs sont valides
                        if not master_id or not duplicate_ids:
                            results['errors'].append(f"IDs invalides pour fusion: maître={master_id}, doublons={duplicate_ids}")
                            continue

                        # Fusionner les appareils
                        if self._merge_devices(master_id, duplicate_ids):
                            results['devices_merged'] += 1
                            results['devices_deleted'] += len(duplicate_ids)
                            app_logger.info(f"Fusion réussie: {len(duplicate_ids)} appareil(s) fusionné(s) vers {master_id}")
                        else:
                            results['errors'].append(f"Échec fusion appareil {master_id}")

                    except Exception as e:
                        app_logger.error(f"Exception lors de la fusion: {e}")
                        results['errors'].append(f"Erreur fusion: {e}")
                        
            # Traiter les suppressions de pièces
            if 'piece_deletions' in cleanup_options:
                for ref_piece in cleanup_options['piece_deletions']:
                    try:
                        deleted_count = self._delete_duplicate_pieces(ref_piece)
                        results['pieces_deleted'] += deleted_count
                    except Exception as e:
                        results['errors'].append(f"Erreur suppression pièce {ref_piece}: {e}")
                        
            return results
            
        except Exception as e:
            app_logger.error(f"Erreur application nettoyage: {e}")
            return {'errors': [str(e)]}
            
    def _merge_devices(self, master_id: int, duplicate_ids: List[int]) -> bool:
        """Fusionner des appareils doublons vers un appareil maître"""
        try:
            # Pour chaque appareil dupliqué, transférer ses pièces vers le maître
            for duplicate_id in duplicate_ids:
                # Mettre à jour les associations de pièces (table piece_associations)
                update_query = """
                UPDATE piece_associations SET appareil_id = ? WHERE appareil_id = ?
                """
                self.db_manager.execute_update(update_query, (master_id, duplicate_id))

                # Supprimer l'appareil dupliqué
                delete_query = "DELETE FROM appareils WHERE id = ?"
                self.db_manager.execute_update(delete_query, (duplicate_id,))

            app_logger.info(f"Appareil {master_id} fusionné avec {duplicate_ids}")
            return True

        except Exception as e:
            app_logger.error(f"Erreur fusion appareils: {e}")
            return False
            
    def _delete_duplicate_pieces(self, ref_piece: str) -> int:
        """Supprimer les pièces dupliquées (garder la plus récente)"""
        try:
            # Garder la pièce avec l'ID le plus élevé (plus récente)
            query = """
            DELETE FROM pieces 
            WHERE ref_piece = ? 
            AND id NOT IN (
                SELECT MAX(id) FROM pieces WHERE ref_piece = ?
            )
            """
            
            result = self.db_manager.execute_update(query, (ref_piece, ref_piece))
            app_logger.info(f"Suppression pièces dupliquées {ref_piece}: {result} supprimées")
            return result
            
        except Exception as e:
            app_logger.error(f"Erreur suppression pièces dupliquées: {e}")
            return 0