"""
Service de gestion des données - Phase 2.5c
Extrait de main_refactored.py pour améliorer la maintenabilité

Responsabilités:
- Auto-complétion des champs vides (Type, Fabricant)
- Nettoyage des données et gestion des doublons
- Logique de validation et de cohérence des données
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass
from ..utils.qt_imports import QDialog
from src.core.logger import app_logger
from src.utils.error_handler import handle_data_management_errors
from src.services.proposition_type_fabricant import proposer_type_fabricant
from src.utils.ouverture_modale import ouvrir_modal

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
    
    LIBELLES_CHAMPS = {'type': 'Type', 'manufacturer': 'Fabricant'}

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
        
        # Refus lus une fois pour le lot (et non ligne à ligne) ; None si la
        # lecture échoue : rien n'est alors filtré, comme à l'import.
        lire_refus = getattr(self.db_manager, 'lire_refus', None)
        refus = lire_refus([r.get('id') for r in table_data if r.get('id')]) if lire_refus else None
        if not isinstance(refus, set):
            refus = None

        for row_data in table_data:
            success = self._safe_process_device_row(row_data, result, refus)
            if success:
                result.completed_count += 1

        app_logger.info(f"Auto-complétion terminée: {result.completed_count}/{result.total_rows_processed} lignes complétées")
        return result

    @handle_data_management_errors(return_value=False)
    def _safe_process_device_row(self, row_data: Dict[str, Any], result: FieldCompletionResult,
                                 refus: Optional[Set[Tuple[int, str, str]]] = None) -> bool:
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
            completed = self._try_auto_complete_device(db_id, device_data, refus)
            return completed is not None

        return False
    
    @handle_data_management_errors(return_value=None)
    def _try_auto_complete_device(self, db_id: int, device_data: Dict[str, Any],
                                  refus: Optional[Set[Tuple[int, str, str]]] = None
                                  ) -> Optional[Dict[str, Any]]:
        """
        Tenter l'auto-complétion d'un appareil spécifique.

        Même règle que l'import (`proposer_type_fabricant`) : correspondance exacte
        sur les références non vides, auto-complétés non vérifiés exclus des
        sources, combinaison la plus fréquente. Une valeur que l'utilisateur a
        refusée pour cet appareil (fenêtre « Auto-complétés à vérifier ») n'est pas
        reproposée. Chaque champ écrit est tracé, donc revu comme ceux de l'import.

        Args:
            db_id: ID de l'appareil en base
            device_data: Données actuelles de l'appareil
            refus: (appareil_id, champ, valeur en minuscules) refusés, lus une
                fois pour tout le lot (None : rien à filtrer)

        Returns:
            Dict avec les champs complétés ou None si aucune complétion
        """
        propositions = proposer_type_fabricant(self.db_manager, device_data)
        if refus:
            propositions = {champ: p for champ, p in propositions.items()
                            if (db_id, champ, p.valeur.strip().lower()) not in refus}
        if not propositions:
            return None

        # Chemin batché canonique, qui COMMIT (execute_custom_query ne le fait pas :
        # l'UPDATE serait perdu à la fermeture).
        updates = {champ: p.valeur for champ, p in propositions.items()}
        if not self.db_manager.update_multiple_cells_batch({db_id: updates}):
            return None

        # Tracée APRÈS l'écriture (le déclencheur effacerait sinon la trace) et
        # aussitôt : la ligne suivante ne doit pas prendre celle-ci pour source.
        enregistrer = getattr(self.db_manager, 'enregistrer_autocompletions', None)
        if enregistrer is not None:
            horodatage = datetime.now().isoformat(sep=' ', timespec='seconds')
            enregistrer([(db_id, champ, p.valeur, p.source, p.accord, p.total, horodatage)
                         for champ, p in propositions.items()])

        return {'fields': [self.LIBELLES_CHAMPS[champ] for champ in propositions],
                'values': updates}
    
    @handle_data_management_errors()
    def prepare_data_cleaning(self, sur_resultat=None) -> None:
        """
        Ouvrir le nettoyage des données avec analyse préalable (fenêtre modale non
        bloquante, jamais exec_).

        Args:
            sur_resultat: appelé à la fermeture avec {'dialog_completed': True,
                'user_choice': ...} si la fenêtre a été utilisée ; rien si annulée.
        """
        # Importer et utiliser CleanupPreviewDialog
        from .cleanup_preview_refactored import CleanupPreviewDialog

        if not self.main_window:
            app_logger.error("MainWindow nécessaire pour CleanupPreviewDialog")
            return None

        # Ouvrir la fenêtre de prévisualisation
        preview_dialog = CleanupPreviewDialog(self.main_window)

        @handle_data_management_errors()
        def _sur_fin(_fenetre, result):
            user_choice = preview_dialog.get_user_choice()

            # Le marquage "distinct" d'un groupe écrit directement en base, indépendamment
            # du résultat (Appliquer/Annuler) : invalider le cache des doublons systématiquement
            # pour que le bouton "Outils" reflète l'état réel.
            if hasattr(self.main_window, 'duplicate_indicator_service'):
                self.main_window.duplicate_indicator_service.invalidate_cache("nettoyage doublons")

            # Si l'utilisateur a annulé ou fermé la fenêtre
            if result != QDialog.Accepted and user_choice != 'applied':
                return

            # La fenêtre a été utilisée avec succès
            if sur_resultat is not None:
                sur_resultat({'dialog_completed': True, 'user_choice': user_choice})

        ouvrir_modal(preview_dialog, sur_fin=(lambda *a: _sur_fin(self, *a)))
