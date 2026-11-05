"""
Service d'analyse des doublons
Centralise toute la logique d'analyse et de détection des doublons
"""

from typing import Dict, List, Any, Optional, Tuple, Set
from ..utils.qt_imports import QObject, pyqtSignal, QThread, QTimer

from ..core.logger import app_logger
from ..data.database_manager import DatabaseManager
from .base_service import BaseService, safe_operation
from ..utils.text_utils import clean_display_text

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
            
            # Les valeurs émises sont les PLAFONDS de fin de phase : l'UI fait glisser
            # la barre vers ce plafond pendant que la phase s'exécute (animation fluide).

            # Phase 1: Analyse des appareils en doublon (phase principale)
            self.progress_updated.emit(55, "Recherche des appareils en doublon…")
            if not self.should_stop:
                results['duplicate_devices'] = self._find_duplicate_devices()

            # Phase 2: Analyse des pièces dupliquées
            self.progress_updated.emit(80, "Recherche des pièces dupliquées…")
            if not self.should_stop:
                results['duplicate_pieces'] = self._find_duplicate_pieces()

            # Phase 3: Incohérences potentielles - DÉSACTIVÉE (produit cartésien trop lent)
            results['potential_inconsistencies'] = []

            # Phase 4: Calcul des statistiques
            self.progress_updated.emit(92, "Calcul des statistiques…")
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
        """Trouver les appareils en doublon basés sur ref_modele.

        Performance : on récupère les détails (+ comptage de pièces) de TOUS les
        appareils des groupes en quelques requêtes batch, au lieu d'une requête par
        appareil. L'ancienne version (N+1) ré-agrégeait toute la table
        `piece_associations` (3,5 M lignes) à chaque appareil → ~12 min pour 1443
        appareils ; la version batch tient en ~0,5 s.
        """
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
        if not results:
            return []

        # Conserver l'ordre des groupes et collecter tous les ids
        group_order = []  # [(ref_modele, count, [ids])]
        all_ids = []
        for ref_modele, count, ids_str in results:
            ids = [int(id_str) for id_str in ids_str.split(',')]
            group_order.append((ref_modele, count, ids))
            all_ids.extend(ids)

        if not all_ids:
            return []

        # Détails + comptage de pièces de tous les appareils, par lots (limite de
        # variables liées de SQLite : on reste prudemment sous 999 par requête)
        by_id: Dict[int, Dict[str, Any]] = {}
        CHUNK = 900
        for start in range(0, len(all_ids), CHUNK):
            chunk_ids = all_ids[start:start + CHUNK]
            placeholders = ",".join("?" * len(chunk_ids))
            # La sous-requête de comptage est filtrée sur les ids du lot (WHERE
            # appareil_id IN …) : elle n'agrège que les lignes utiles via l'index
            # sur piece_associations.appareil_id, au lieu de balayer les 3,5 M lignes.
            detail_query = f"""
            SELECT a.id, a.ref_modele, a.type, a.manufacturer,
                   a.commercial_ref, a.other_ref, a.category, a.notes,
                   COALESCE(pc.cnt, 0) as pieces_count
            FROM appareils a
            LEFT JOIN (
                SELECT pa.appareil_id, COUNT(*) as cnt
                FROM piece_associations pa
                INNER JOIN pieces p ON pa.piece_id = p.id
                WHERE pa.appareil_id IN ({placeholders})
                GROUP BY pa.appareil_id
            ) pc ON pc.appareil_id = a.id
            WHERE a.id IN ({placeholders})
            """
            rows = self.db_manager.execute_query(detail_query, tuple(chunk_ids) + tuple(chunk_ids))
            for r in (rows or []):
                by_id[r[0]] = {
                    'id': r[0],
                    'ref_modele': clean_display_text(r[1] or ''),
                    'type_appareil': clean_display_text(r[2] or ''),
                    'manufacturer': clean_display_text(r[3] or ''),
                    'commercial_ref': clean_display_text(r[4] or ''),
                    'other_ref': clean_display_text(r[5] or ''),
                    'category': clean_display_text(r[6] or ''),
                    'notes': clean_display_text(r[7] or ''),
                    'pieces_count': r[8] or 0
                }

        # Reconstituer les groupes dans l'ordre initial
        duplicates = []
        for ref_modele, count, ids in group_order:
            devices = [by_id[i] for i in ids if i in by_id]
            duplicates.append({
                'ref_modele': ref_modele,
                'count': count,
                'devices': devices
            })

        return duplicates
            
    def _find_duplicate_pieces(self) -> List[Dict[str, Any]]:
        """Trouver les pièces dupliquées basées sur ref_piece"""
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

class DuplicatesAnalysisService(BaseService):
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
            if not self.analysis_worker.wait(3000):  # Attendre 3 secondes max
                # Le thread est toujours actif (requête SQL longue en cours) :
                # déconnecter ses signaux pour éviter un crash si le thread
                # émet vers des objets déjà détruits (fenêtre fermée entre temps),
                # et le laisser se terminer seul en arrière-plan
                app_logger.warning("DuplicatesAnalysisWorker toujours actif après 3s, déconnexion des signaux")
                try:
                    self.analysis_worker.progress_updated.disconnect()
                except TypeError:
                    pass
                try:
                    self.analysis_worker.analysis_completed.disconnect()
                except TypeError:
                    pass
                try:
                    self.analysis_worker.analysis_error.disconnect()
                except TypeError:
                    pass
            
    def _on_analysis_completed(self, results: Dict[str, Any]):
        """Gérer la fin d'analyse"""
        self.current_results = results
        self.analysis_completed.emit(results)
        app_logger.info(f"Analyse doublons terminée: {results['statistics']}")
        
    @safe_operation(operation_name="apply_cleanup_decisions", default_return={'errors': ['Erreur application nettoyage']})
    def apply_cleanup_decisions(self, cleanup_options: Dict[str, Any]) -> Dict[str, Any]:
        """Appliquer les décisions de nettoyage"""
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

        # Traiter les suppressions de pièces
        if 'piece_deletions' in cleanup_options:
            for ref_piece in cleanup_options['piece_deletions']:
                deleted_count = self._delete_duplicate_pieces(ref_piece)
                results['pieces_deleted'] += deleted_count

        return results
            
    @safe_operation(operation_name="_merge_devices", default_return=False)
    def _merge_devices(self, master_id: int, duplicate_ids: List[int]) -> bool:
        """Fusionner des appareils doublons vers un appareil maître"""
        # Les trois étapes passaient par execute_custom_query, qui ne commit pas :
        # la fusion était visible dans l'interface mais perdue au lancement suivant
        # si rien d'autre n'écrivait entre-temps. Un lot atomique règle aussi le
        # second défaut : supprimer l'appareil sans avoir transféré ses pièces
        # laisserait des associations orphelines (les FOREIGN KEY ne protègent
        # que si Config.FOREIGN_KEYS est actif, et ne transfèrent rien).
        operations = []
        for duplicate_id in duplicate_ids:
            # Stratégie: Supprimer d'abord les doublons de pièces puis transférer les uniques

            # 1. Supprimer les associations de pièces qui existent déjà pour le maître
            #    (éviter les violations de contrainte UNIQUE)
            operations.append(("""
            DELETE FROM piece_associations
            WHERE appareil_id = ?
            AND piece_id IN (
                SELECT piece_id FROM piece_associations
                WHERE appareil_id = ?
            )
            """, (duplicate_id, master_id)))

            # 2. Transférer les pièces restantes du duplicata vers le maître
            operations.append((
                "UPDATE piece_associations SET appareil_id = ? WHERE appareil_id = ?",
                (master_id, duplicate_id)
            ))

            # 3. Supprimer l'appareil dupliqué
            operations.append(("DELETE FROM appareils WHERE id = ?", (duplicate_id,)))

        if not self.db_manager.execute_write_batch(operations):
            app_logger.error(f"Fusion de l'appareil {master_id} avec {duplicate_ids} annulée")
            return False

        app_logger.info(f"Appareil {master_id} fusionné avec {duplicate_ids}")
        return True
            
    @safe_operation(operation_name="_delete_duplicate_pieces", default_return=0)
    def _delete_duplicate_pieces(self, ref_piece: str) -> int:
        """Supprimer les pièces dupliquées (garder la plus récente)"""
        # Garder la pièce avec l'ID le plus élevé (plus récente)
        query = """
        DELETE FROM pieces
        WHERE ref_piece = ?
        AND id NOT IN (
            SELECT MAX(id) FROM pieces WHERE ref_piece = ?
        )
        """

        # execute_write commit ET renvoie le nombre réel de lignes : la suppression
        # est durable, et le compte n'est plus simulé à 1 quoi qu'il arrive.
        supprimees = self.db_manager.execute_write(query, (ref_piece, ref_piece))
        if supprimees < 0:
            app_logger.error(f"Suppression pièces dupliquées {ref_piece} : échec")
            return 0
        app_logger.info(f"Suppression pièces dupliquées {ref_piece}: {supprimees} supprimées")
        return supprimees