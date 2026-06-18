"""
Service de groupement d'historique pour les modifications d'appareils
Groupe les modifications multiples d'un même appareil en une seule entrée
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime
from ..ui.qt_imports import QTimer, QObject, pyqtSignal
from ..core.logger import app_logger

class GroupedHistoryService(QObject):
    """Service de groupement des modifications d'historique"""

    # Signal émis quand des modifications sont flushées vers l'historique
    modifications_flushed = pyqtSignal(str)  # message formaté

    def __init__(self, user_interaction_service):
        super().__init__()
        self.user_interaction_service = user_interaction_service
        # Garder une référence vers la fenêtre principale pour accéder aux données
        self.main_window = user_interaction_service.main_window

        # Buffer des modifications en attente : {db_id: {'timestamp': datetime, 'modifications': [(field, old, new)]}}
        self.pending_modifications: Dict[int, Dict] = {}

        # Fenêtre de groupement : 2 secondes
        self.grouping_window_ms = 2000

        # Timer pour flusher les modifications
        self.flush_timer = QTimer()
        self.flush_timer.setSingleShot(True)
        self.flush_timer.timeout.connect(self.flush_all_pending_modifications)

        # Statistiques pour debugging
        self.stats = {
            'single_modifications': 0,
            'grouped_modifications': 0,
            'total_devices_modified': 0
        }

    def add_modification(self, db_id: int, field_name: str, old_value: str, new_value: str):
        """
        Ajouter une modification au buffer de groupement

        Args:
            db_id: ID de l'appareil dans la base de données
            field_name: Nom du champ modifié (ex: "Type", "Fabricant")
            old_value: Ancienne valeur
            new_value: Nouvelle valeur
        """
        try:
            current_time = datetime.now()

            # Si c'est la première modification de cet appareil
            if db_id not in self.pending_modifications:
                self.pending_modifications[db_id] = {
                    'timestamp': current_time,
                    'modifications': []
                }

            # Ajouter la modification
            self.pending_modifications[db_id]['modifications'].append((field_name, old_value, new_value))

            # Redémarrer le timer (fenêtre de groupement)
            self.flush_timer.start(self.grouping_window_ms)

        except Exception as e:
            app_logger.error(f"Erreur ajout modification groupée: {e}")
            # Fallback : ajouter directement à l'historique normal
            self._fallback_to_normal_history(field_name, old_value, new_value)

    def flush_all_pending_modifications(self):
        """Flusher toutes les modifications en attente vers l'historique"""
        if not self.pending_modifications:
            return

        # Construire un index db_id -> ligne une seule fois : évite un balayage
        # complet de la table (O(lignes x colonnes)) pour chaque appareil flushé,
        # ce qui devenait O(n²) lors d'une édition en masse (ex: 6615 cellules)
        self._row_index_cache = self._build_row_index()

        try:
            # Traiter chaque appareil
            for db_id, data in self.pending_modifications.items():
                self._flush_device_modifications(db_id, data)
        finally:
            self._row_index_cache = None

        # Vider le buffer
        self.pending_modifications.clear()

    def _build_row_index(self) -> Dict[int, int]:
        """Construire un index {db_id: row} à partir du modèle affiché"""
        index: Dict[int, int] = {}
        if hasattr(self.main_window, 'table') and self.main_window.table:
            table = self.main_window.table
            model = table.model() if hasattr(table, 'model') and callable(table.model) else None
            if model and hasattr(model, 'get_db_id'):
                for row in range(table.rowCount()):
                    db_id = model.get_db_id(row)
                    if db_id is not None:
                        index[int(db_id)] = row
        return index

    def _flush_device_modifications(self, db_id: int, data: Dict):
        """Flusher les modifications d'un appareil spécifique"""
        try:
            modifications = data['modifications']
            timestamp = data['timestamp']

            if len(modifications) == 1:
                # Modification unique : utiliser le format harmonisé avec appareil
                field_name, old_value, new_value = modifications[0]
                appareil_ref = self._get_appareil_reference(db_id)
                message = f"Modification de l'appareil {appareil_ref}\n     ==> {field_name} : '{old_value}' → '{new_value}'"
                self.user_interaction_service.add_to_history(message)
                self.stats['single_modifications'] += 1

            else:
                # Modifications multiples : utiliser le format groupé
                message = self._format_grouped_modifications(db_id, modifications, timestamp)
                self.user_interaction_service.add_to_history(message)
                self.stats['grouped_modifications'] += 1

            self.stats['total_devices_modified'] += 1

        except Exception as e:
            app_logger.error(f"Erreur flush appareil {db_id}: {e}")
            # Fallback : ajouter chaque modification séparément
            for field_name, old_value, new_value in data['modifications']:
                self._fallback_to_normal_history(field_name, old_value, new_value)

    def _format_grouped_modifications(self, db_id: int, modifications: List[Tuple[str, str, str]], timestamp: datetime) -> str:
        """
        Formater les modifications groupées selon le format cible

        Format cible:
        [HH:MM:SS] Modification de l'appareil {référence}
             ==> {Champ} : '{Ancien}' → '{Nouveau}'
             ==> {Champ} : '{Ancien}' → '{Nouveau}'
        """
        # Obtenir une référence lisible pour l'appareil
        appareil_ref = self._get_appareil_reference(db_id)

        # IMPORTANT: Ne pas inclure le timestamp ici car add_to_history() l'ajoute automatiquement
        lines = [f"Modification de l'appareil {appareil_ref}"]

        for field_name, old_value, new_value in modifications:
            lines.append(f"     ==> {field_name} : '{old_value}' → '{new_value}'")

        return '\\n'.join(lines)

    def _get_appareil_reference(self, db_id: int) -> str:
        """Obtenir une référence lisible pour l'appareil"""
        try:
            # Chercher dans la table affichée pour trouver la ligne correspondante
            if hasattr(self.main_window, 'table') and self.main_window.table:
                table = self.main_window.table

                # Utiliser l'index pré-calculé (flush en masse) si disponible,
                # sinon balayer la table (cas d'un flush isolé, ex: force_flush_device)
                row_index_cache = getattr(self, '_row_index_cache', None)
                if row_index_cache is not None:
                    rows_to_check = [row_index_cache[db_id]] if db_id in row_index_cache else []
                else:
                    rows_to_check = range(table.rowCount())

                for row in rows_to_check:
                    # Vérifier si cette ligne correspond au db_id en cherchant dans toutes les colonnes
                    found_row = row_index_cache is not None
                    if not found_row:
                        for col in range(table.columnCount()):
                            item = table.item(row, col)
                            if item and item.data(256) == db_id:  # Qt.UserRole = 256
                                found_row = True
                                break

                    if found_row:
                        # Récupérer Référence Modèle et Référence Commerciale
                        ref_modele_item = table.item(row, 2)
                        commercial_ref_item = table.item(row, 3)

                        ref_modele = ref_modele_item.text().strip() if ref_modele_item else ""
                        commercial_ref = commercial_ref_item.text().strip() if commercial_ref_item else ""

                        # Combiner les références avec " - "
                        if ref_modele and commercial_ref:
                            return f"{ref_modele} - {commercial_ref}"
                        elif ref_modele:
                            return ref_modele
                        elif commercial_ref:
                            return commercial_ref

                        # Fallback: Autre Référence (colonne 4)
                        other_ref_item = table.item(row, 4)
                        if other_ref_item and other_ref_item.text().strip():
                            return other_ref_item.text().strip()

                        # Fallback final: Type + Fabricant
                        type_item = table.item(row, 0)
                        fabricant_item = table.item(row, 1)
                        type_text = type_item.text().strip() if type_item else ""
                        fabricant_text = fabricant_item.text().strip() if fabricant_item else ""

                        if type_text and fabricant_text:
                            return f"{type_text} {fabricant_text}"
                        elif type_text:
                            return type_text
                        elif fabricant_text:
                            return fabricant_text

            # Fallback : utiliser l'ID
            return str(db_id)

        except Exception as e:
            app_logger.error(f"Erreur récupération référence appareil {db_id}: {e}")
            return str(db_id)

    def _fallback_to_normal_history(self, field_name: str, old_value: str, new_value: str):
        """Fallback vers l'historique normal en cas d'erreur"""
        message = f"Modification {field_name}: '{old_value}' → '{new_value}'"
        self.user_interaction_service.add_to_history(message)

    def force_flush_device(self, db_id: int):
        """
        Forcer le flush immédiat des modifications d'un appareil spécifique
        Utile quand on commence à modifier un autre appareil
        """
        if db_id in self.pending_modifications:
            data = self.pending_modifications.pop(db_id)
            self._flush_device_modifications(db_id, data)

    def get_stats(self) -> Dict:
        """Obtenir les statistiques d'utilisation"""
        return self.stats.copy()

    def cleanup(self):
        """Nettoyer les ressources"""
        # Flusher les modifications en attente avant nettoyage
        self.flush_all_pending_modifications()

        # Arrêter le timer
        if self.flush_timer.isActive():
            self.flush_timer.stop()