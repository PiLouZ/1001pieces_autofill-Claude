"""
Service d'analyse des doublons
Centralise toute la logique d'analyse et de détection des doublons
"""

import re
from typing import Dict, List, Any, Optional, Tuple, Set
from ..ui.qt_imports import QObject, pyqtSignal, QThread, QTimer

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
        # Ne pas utiliser le db_manager du thread principal
        # On créera une nouvelle connexion dans le thread
        self.db_path = db_manager.db_path if hasattr(db_manager, 'db_path') else 'data/appareils.db'
        self.db_manager = None  # Sera initialisé dans run()
        self.should_stop = False
        
    def stop(self):
        """Arrêter l'analyse"""
        self.should_stop = True
        
    def run(self):
        """Exécuter l'analyse des doublons"""
        try:
            # Créer une nouvelle connexion DB pour ce thread
            self.db_manager = DatabaseManager()

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
        finally:
            # Fermer la connexion DB du thread
            if self.db_manager:
                try:
                    self.db_manager.close()
                except:
                    pass
            
    def _find_duplicate_devices(self) -> List[Dict[str, Any]]:
        """Trouver les appareils en doublon basés sur ref_modele"""
        try:
            query = """
            SELECT ref_modele, COUNT(*) as count, GROUP_CONCAT(id) as ids
            FROM appareils
            WHERE ref_modele IS NOT NULL AND ref_modele != ''
            AND ref_modele NOT IN (
                SELECT ref_modele FROM reference_decisions
                WHERE decision = 'DISTINCT'
            )
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
                    SELECT a.id, a.ref_modele, a.type, a.manufacturer,
                           a.commercial_ref, a.other_ref, a.category, a.notes,
                           COALESCE(p.pieces_count, 0) as pieces_count
                    FROM appareils a
                    LEFT JOIN (
                        SELECT pa.appareil_id, COUNT(*) as pieces_count
                        FROM piece_associations pa
                        INNER JOIN pieces p ON pa.piece_id = p.id
                        GROUP BY pa.appareil_id
                    ) p ON a.id = p.appareil_id
                    WHERE a.id = ?
                    """
                    device_details = self.db_manager.execute_query(device_query, (device_id,))
                    if device_details:
                        device = {
                            'id': device_details[0][0],
                            'ref_modele': clean_display_text(device_details[0][1] or ''),
                            'type_appareil': clean_display_text(device_details[0][2] or ''),
                            'manufacturer': clean_display_text(device_details[0][3] or ''),
                            'commercial_ref': clean_display_text(device_details[0][4] or ''),
                            'other_ref': clean_display_text(device_details[0][5] or ''),
                            'category': clean_display_text(device_details[0][6] or ''),
                            'notes': clean_display_text(device_details[0][7] or ''),
                            'pieces_count': device_details[0][8] or 0
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
            SELECT DISTINCT a1.id, a1.ref_modele, a1.type, a1.manufacturer,
                   a2.id, a2.ref_modele, a2.type, a2.manufacturer
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
                OR (a1.type = a2.type 
                    AND a1.manufacturer = a2.manufacturer
                    AND a1.type IS NOT NULL
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
                # Stratégie: Supprimer d'abord les doublons de pièces puis transférer les uniques

                # 1. Supprimer les associations de pièces qui existent déjà pour le maître
                #    (éviter les violations de contrainte UNIQUE)
                cleanup_query = """
                DELETE FROM piece_associations
                WHERE appareil_id = ?
                AND piece_id IN (
                    SELECT piece_id FROM piece_associations
                    WHERE appareil_id = ?
                )
                """
                self.db_manager.execute_custom_query(cleanup_query, (duplicate_id, master_id))

                # 2. Transférer les pièces restantes du duplicata vers le maître
                update_query = """
                UPDATE piece_associations SET appareil_id = ? WHERE appareil_id = ?
                """
                self.db_manager.execute_custom_query(update_query, (master_id, duplicate_id))

                # 3. Supprimer l'appareil dupliqué
                delete_query = "DELETE FROM appareils WHERE id = ?"
                self.db_manager.execute_custom_query(delete_query, (duplicate_id,))

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
            
            result = self.db_manager.execute_custom_query(query, (ref_piece, ref_piece))
            # execute_custom_query ne retourne pas le nombre de lignes, on simule
            result = 1 if result is not None else 0
            app_logger.info(f"Suppression pièces dupliquées {ref_piece}: {result} supprimées")
            return result
            
        except Exception as e:
            app_logger.error(f"Erreur suppression pièces dupliquées: {e}")
            return 0