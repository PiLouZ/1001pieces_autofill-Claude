"""
Service centralisé pour les opérations de base de données CRUD
Extrait de main_refactored.py pour centraliser la logique métier critique
"""

from typing import Optional, Dict, List, Any, Tuple, Callable
from ..ui.qt_imports import QMessageBox
from ..ui.qt_imports import pyqtSignal, Qt

from ..core.config import Config, pluralize
from ..core.logger import app_logger
from .base_service import BaseService, service_operation
from ..utils.error_handler import handle_database_operation_errors

class DatabaseOperationsService(BaseService):
    """Service centralisé pour les opérations CRUD de base de données"""

    # Signaux pour notifier les changements
    device_added = pyqtSignal(int)  # device_id
    device_deleted = pyqtSignal(list)  # device_ids
    data_saved = pyqtSignal(int)  # nb_cells_saved
    validation_failed = pyqtSignal(str)  # error_message

    def __init__(self, parent_window, parent=None):
        super().__init__(parent_window=parent_window, parent=parent)

        # Services requis pour l'injection automatique (seulement les essentiels disponibles)
        self._required_services = [
            'db_manager',
            'cache_service',
            'auto_save_manager'
        ]

        # État interne
        self.modified_cells = set()
        self.save_in_progress = False

    def initialize_services(self):
        """Initialiser les références aux services depuis la fenêtre parent"""
        # Utiliser l'injection automatique de BaseService
        self.inject_required_services()

        # Référence aux modified_cells de la fenêtre parent
        if hasattr(self.parent_window, 'modified_cells'):
            self.modified_cells = self.parent_window.modified_cells

        self.log_operation("initialize_services", "DatabaseOperationsService services initialisés", "debug")

    # ================================
    # OPÉRATIONS CREATE
    # ================================

    @service_operation("ajout_appareil")
    def add_new_device(self, device_data: Optional[Dict[str, str]] = None) -> Optional[int]:
        """Ajouter un nouvel appareil à la base de données"""
        if not self.db_manager:
            self.handle_error(Exception("DatabaseManager non disponible"), "add_new_device")
            return None

        # Données par défaut pour un nouvel appareil
        if device_data is None:
            device_data = {
                'type': '',
                'marque': '',
                'modele': '',
                'reference': '',
                'designation': '',
                'prix': '0.00',
                'stock': '0',
                'notes': ''
            }

        # Validation des données (sauf pour les nouvelles lignes vides)
        is_new_empty_row = all(not str(value).strip() for value in device_data.values() if value != '0.00' and value != '0')
        if not is_new_empty_row:
            is_valid, errors = self.validate_device_data(device_data)
            if not is_valid:
                error_msg = "Erreurs de validation:\n" + "\n".join(errors)
                if self.user_interaction_service:
                    self.user_interaction_service.show_error(error_msg)
                self.validation_failed.emit(error_msg)
                return None

        # Ajouter en base
        device_id = self.db_manager.add_device(device_data)

        if device_id:
            self.log_operation("add_new_device", f"Nouvel appareil ajouté avec ID: {device_id}", "info")

            # Recharger la table
            if hasattr(self.parent_window, 'table_controller') and self.parent_window.table_controller:
                self.parent_window.table_controller.load_data()

            # Mettre à jour le bouton lignes incomplètes après ajout
            # Forcer l'invalidation du cache du service incomplete_button
            if hasattr(self.parent_window, 'incomplete_button_service'):
                self.parent_window.incomplete_button_service._cache_valid = False

            # Invalider le cache des doublons après ajout
            if hasattr(self.parent_window, 'duplicate_indicator_service'):
                self.parent_window.duplicate_indicator_service.invalidate_cache("nouvel appareil ajouté")

            # Utiliser un appel différé pour éviter les problèmes de synchronisation
            from ..ui.qt_imports import QTimer
            def update_incomplete_button():
                if hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                    self.parent_window._update_incomplete_button_visibility()

            QTimer.singleShot(100, update_incomplete_button)  # 100ms de délai

            # Invalider le cache
            cache_service = getattr(self, 'cache_service', None)
            if cache_service:
                cache_service.invalidate_all("nouvel appareil ajouté")

            # Ajouter à l'historique
            if self.user_interaction_service:
                self.user_interaction_service.add_to_history(
                    f"Nouvel appareil ajouté: {device_data.get('marque', '')} {device_data.get('modele', '')}"
                )

                # Émettre le signal
                self.device_added.emit(device_id)

                return device_id
        else:
            error_msg = "Erreur lors de l'ajout en base de données"
            self.handle_error(Exception(error_msg), "add_new_device")
            return None

    # ================================
    # OPÉRATIONS UPDATE
    # ================================

    def save_cells_batch(self, updates_by_db_id: Optional[Dict[int, Dict[str, str]]] = None) -> bool:
        """Sauvegarder un lot de cellules modifiées"""
        return self._safe_save_cells_batch(updates_by_db_id)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde batch")
    def _safe_save_cells_batch(self, updates_by_db_id: Optional[Dict[int, Dict[str, str]]] = None) -> bool:
        """Version sécurisée de save_cells_batch"""
        if self.save_in_progress:
            app_logger.warning("Sauvegarde déjà en cours")
            return False

        if not self.db_manager:
            app_logger.error("DatabaseManager non disponible")
            return False

        # Utiliser les cellules modifiées si pas de données spécifiques
        if updates_by_db_id is None:
            if not self.modified_cells:
                return True

            updates_by_db_id = self._prepare_updates_from_modified_cells()

        if not updates_by_db_id:
            return True

        self.save_in_progress = True

        # Effectuer la sauvegarde avec gestion automatique du cleanup
        result = self._safe_perform_batch_save(updates_by_db_id)

        # Cleanup toujours exécuté
        self._cleanup_after_batch_save()

        return result

    def _cleanup_after_batch_save(self):
        """Nettoyer après sauvegarde batch (toujours exécuté)"""
        # Reprendre l'invalidation du cache
        cache_service = getattr(self, 'cache_service', None)
        if cache_service:
            cache_service.resume_invalidation(force_invalidate=True)
        self.save_in_progress = False

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur exécution sauvegarde batch")
    def _safe_perform_batch_save(self, updates_by_db_id):
        """Exécuter la sauvegarde batch sans try/catch"""
        # Suspendre l'invalidation du cache pendant la sauvegarde
        cache_service = getattr(self, 'cache_service', None)
        if cache_service:
            cache_service.suspend_invalidation("sauvegarde batch")

        # Effectuer les mises à jour en base
        success = self.db_manager.update_multiple_cells_batch(updates_by_db_id)

        if success:
            cells_saved = sum(len(updates) for updates in updates_by_db_id.values())
            app_logger.info(f"Sauvegarde batch réussie: {cells_saved} cellules")

            # Nettoyer les cellules modifiées du parent window ET du service
            # BUGFIX: Utiliser getattr pour éviter l'erreur de variable non définie
            parent_modified_cells = getattr(self.parent_window, 'modified_cells', set())
            parent_modified_cells.clear()
            self.modified_cells.clear()

            # Mettre à jour les indicateurs UI
            self._update_save_indicators(True)

            # Émettre le signal
            self.data_saved.emit(cells_saved)

            # Mettre à jour le bouton lignes incomplètes après sauvegarde batch
            from ..ui.qt_imports import QTimer
            def update_incomplete_button_after_batch():
                if hasattr(self.parent_window, 'incomplete_button_service'):
                    self.parent_window.incomplete_button_service.invalidate_cache("sauvegarde batch")
                if hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                    self.parent_window._update_incomplete_button_visibility()

            QTimer.singleShot(100, update_incomplete_button_after_batch)

            return True
        else:
            app_logger.error("Échec de la sauvegarde batch")
            if self.user_interaction_service:
                self.user_interaction_service.show_error("Erreur lors de la sauvegarde")
            return False

    def save_drag_changes(self, drag_handle) -> bool:
        """Sauvegarder les modifications issues d'un drag & drop"""
        return self._safe_save_drag_changes(drag_handle)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde drag & drop")
    def _safe_save_drag_changes(self, drag_handle) -> bool:
        """Version sécurisée de save_drag_changes"""
        if not drag_handle or not hasattr(drag_handle, 'get_rows_to_save'):
            app_logger.warning("Drag handle invalide")
            return False

        # Récupérer les lignes à sauvegarder
        rows_to_save = drag_handle.get_rows_to_save()
        if not rows_to_save:
            return True

        # Préparer les mises à jour
        updates_by_db_id = {}
        for row_data in rows_to_save:
            db_id = row_data.get('id')
            if db_id:
                updates_by_db_id[db_id] = {
                    col: value for col, value in row_data.items()
                    if col != 'id' and value is not None
                }

        # Utiliser la sauvegarde batch
        success = self.save_cells_batch(updates_by_db_id)

        if success:
            app_logger.info(f"Modifications drag & drop sauvegardées: {len(rows_to_save)} lignes")

            # Ajouter à l'historique
            if self.user_interaction_service:
                self.user_interaction_service.add_to_history(
                    f"Modification par glisser-déposer: {len(rows_to_save)} appareils"
                )

        return success

    def manual_save(self) -> bool:
        """Effectuer une sauvegarde manuelle"""
        return self._safe_manual_save()

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde manuelle")
    def _safe_manual_save(self) -> bool:
        """Version sécurisée de manual_save"""
        # Accéder directement aux modified_cells du parent
        parent_modified_cells = getattr(self.parent_window, 'modified_cells', set())

        # Vérifier s'il y a des modifications à sauvegarder
        if not parent_modified_cells:
            return True

        # Convertir modified_cells en format attendu (utiliser parent_modified_cells)
        updates_by_db_id = self._convert_modified_cells_to_updates(parent_modified_cells)

        # Déléguer au AutoSaveManager si disponible
        auto_save_manager = getattr(self, 'auto_save_manager', None)
        if auto_save_manager and hasattr(auto_save_manager, 'save_now'):
            return auto_save_manager.save_now()
        else:
            # Fallback vers sauvegarde batch
            return self.save_cells_batch(updates_by_db_id)

    @service_operation("sauvegarde_automatique")
    def auto_save(self) -> bool:
        """Effectuer une sauvegarde automatique"""
        return self._safe_auto_save()

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde automatique")
    def _safe_auto_save(self) -> bool:
        """Version sécurisée de auto_save"""
        # Accéder directement aux modified_cells du parent
        parent_modified_cells = getattr(self.parent_window, 'modified_cells', set())

        # Vérifier s'il y a des modifications à sauvegarder
        if not parent_modified_cells:
            return True

        # Convertir modified_cells en format attendu
        updates_by_db_id = self._convert_modified_cells_to_updates(parent_modified_cells)

        # Utiliser save_cells_batch pour l'auto-save
        return self.save_cells_batch(updates_by_db_id)

    def _convert_modified_cells_to_updates(self, modified_cells_to_use=None) -> Dict[int, Dict[str, str]]:
        """Convertir modified_cells du parent en format attendu par save_cells_batch"""
        return self._safe_convert_modified_cells_to_updates(modified_cells_to_use)

    @handle_database_operation_errors(return_value={}, log_prefix="Erreur conversion modified_cells")
    def _safe_convert_modified_cells_to_updates(self, modified_cells_to_use=None) -> Dict[int, Dict[str, str]]:
        """Version sécurisée de _convert_modified_cells_to_updates"""
        if not self.parent_window or not hasattr(self.parent_window, 'table'):
            app_logger.warning("Impossible de convertir modified_cells: parent_window ou table non disponible")
            return {}

        # Utiliser les cellules fournies ou celles du service
        cells_to_convert = modified_cells_to_use if modified_cells_to_use is not None else self.modified_cells

        table = self.parent_window.table
        updates_by_db_id = {}

        for row, col in cells_to_convert:
            # Traiter chaque cellule séparément avec gestion d'erreur locale
            cell_updates = self._safe_process_cell_update(table, row, col)
            if cell_updates:
                db_id, field_name, cell_value = cell_updates
                if db_id not in updates_by_db_id:
                    updates_by_db_id[db_id] = {}
                updates_by_db_id[db_id][field_name] = cell_value

        return updates_by_db_id

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur traitement cellule")
    def _safe_process_cell_update(self, table, row, col):
        """Traiter une cellule individuelle pour conversion"""
        # Vérifier le nom de la colonne pour détecter si c'est l'ID
        column_header = table.horizontalHeaderItem(col)
        if not column_header:
            return None
        column_name = column_header.text()

        # Ignorer seulement si c'est réellement une colonne ID
        if col == 0 and column_name.lower() in ['id', 'db_id', 'database_id']:
            return None

        # Obtenir l'item de la cellule
        item = table.item(row, col)
        if not item:
            return None

        # Chercher l'ID database (peut être dans une colonne cachée ou via d'autres moyens)
        db_id = None

        # Méthode 1 (rapide, O(1)) : récupérer le db_id directement depuis le
        # modèle, qui le stocke déjà par ligne (évite de balayer toutes les
        # colonnes via table.item(), coûteux car CustomTableView.item()
        # reconstruit un QTableWidgetItem à chaque appel)
        model = table.model() if hasattr(table, 'model') and callable(table.model) else None
        if model and hasattr(model, 'get_db_id'):
            model_db_id = model.get_db_id(row)
            if model_db_id is not None:
                db_id = self._safe_convert_to_int(model_db_id)

        # Méthode 1bis (repli) : Chercher UserRole dans TOUTES les colonnes de la ligne
        if db_id is None:
            for check_col in range(table.columnCount()):
                table_item = table.item(row, check_col)
                if table_item:
                    user_role_data = table_item.data(Qt.UserRole)
                    if user_role_data:
                        # Conversion sécurisée avec décorateur
                        db_id = self._safe_convert_to_int(user_role_data)
                        if db_id is not None:
                            break

        # Méthode 2: Essayer la première colonne si elle contient un nombre
        if db_id is None:
            first_col_item = table.item(row, 0)
            if first_col_item and first_col_item.text().strip().isdigit():
                db_id = int(first_col_item.text())

        # Méthode 3: Chercher dans toutes les colonnes une qui s'appelle ID
        if db_id is None:
            for check_col in range(table.columnCount()):
                header = table.horizontalHeaderItem(check_col)
                if header and header.text().lower() in ['id', 'db_id', 'database_id']:
                    id_item = table.item(row, check_col)
                    if id_item and id_item.text().strip().isdigit():
                        db_id = int(id_item.text())
                        break

        if db_id is None:
            return None  # Ignorer les cellules sans ID database valide

        # Valeur de la cellule
        cell_value = item.text()

        # Mapper nom de colonne UI vers nom de champ BDD
        from ..core.config import Config
        db_field_name = None
        for col_config in Config.COLUMN_CONFIG:
            if col_config["name"] == column_name:
                db_field_name = col_config["db_field"]
                break

        # Utiliser le nom BDD ou l'original si pas de mapping
        field_name = db_field_name if db_field_name else column_name

        return db_id, field_name, cell_value

    # ================================
    # OPÉRATIONS DELETE
    # ================================

    def delete_selected_devices(self, device_ids: Optional[List[int]] = None) -> int:
        """Supprimer les appareils sélectionnés"""
        return self._safe_delete_selected_devices(device_ids)

    @handle_database_operation_errors(return_value=0, log_prefix="Erreur suppression appareils")
    def _safe_delete_selected_devices(self, device_ids: Optional[List[int]] = None) -> int:
        """Version sécurisée de delete_selected_devices"""
        if not self.db_manager:
            app_logger.error("DatabaseManager non disponible")
            return 0

        # Récupérer les IDs sélectionnés si pas fournis
        if device_ids is None:
            device_ids = self._get_selected_device_ids()

        if not device_ids:
            return 0

        # Demander confirmation
        if not self._confirm_deletion(len(device_ids)):
            return 0

        # Récupérer les infos avant suppression (pour historique)
        devices_info = []
        for device_id in device_ids:
            info = self.db_manager.get_device_info(device_id)
            if info:
                devices_info.append(f"{info.get('manufacturer', '')} {info.get('type', '')}")
                app_logger.debug(f"Préparation suppression appareil ID {device_id}: {info.get('manufacturer', '')} {info.get('type', '')}")
            else:
                app_logger.warning(f"Appareil ID {device_id} introuvable lors de la récupération d'infos")

        # Effectuer la suppression
        deleted_count = 0
        app_logger.info(f"Tentative suppression de {len(device_ids)} appareil(s): {device_ids}")
        for device_id in device_ids:
            if self.db_manager.delete_appareil(device_id):
                deleted_count += 1
                app_logger.info(f"Suppression réussie appareil ID: {device_id}")
            else:
                app_logger.warning(f"Échec suppression appareil ID: {device_id}")

        if deleted_count > 0:
            app_logger.info(f"Suppression réussie: {deleted_count} appareils")

            # Recharger la table
            if hasattr(self.parent_window, 'table_controller') and self.parent_window.table_controller:
                self.parent_window.table_controller.load_data()

            # Mettre à jour le bouton lignes incomplètes après suppression
            # Forcer l'invalidation du cache du service incomplete_button
            if hasattr(self.parent_window, 'incomplete_button_service'):
                self.parent_window.incomplete_button_service._cache_valid = False

            # Utiliser un appel différé pour éviter les problèmes de synchronisation
            from ..ui.qt_imports import QTimer
            def update_incomplete_button():
                if hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                    self.parent_window._update_incomplete_button_visibility()

            QTimer.singleShot(100, update_incomplete_button)  # 100ms de délai

            # Invalider le cache
            cache_service = getattr(self, 'cache_service', None)
            if cache_service:
                cache_service.invalidate_all("appareils supprimés")

            # Ajouter à l'historique
            if self.user_interaction_service and devices_info:
                history_msg = f"Suppression de {pluralize(deleted_count, 'appareil')}: " + ", ".join(devices_info[:3])
                if len(devices_info) > 3:
                    history_msg += f" et {pluralize(len(devices_info) - 3, 'autre')}"
                self.user_interaction_service.add_to_history(history_msg)

            # Afficher le résultat
            if self.user_interaction_service:
                self.user_interaction_service.show_success(
                    f"{pluralize(deleted_count, 'appareil supprimé', 'appareils supprimés')} avec succès"
                )

            # Feature Flag: Phase 4 - Sauvegarde événementielle après suppression (délégation service)
            if Config.ENABLE_EVENT_DRIVEN_SAVE:
                if hasattr(self.parent_window, 'event_driven_save_service') and self.parent_window.event_driven_save_service:
                    self.parent_window.event_driven_save_service.handle_deletion_completed(deleted_count)
                else:
                    # Fallback si service pas encore initialisé
                    app_logger.warning("EventDrivenSaveService non disponible, fallback méthode locale")
                    self._trigger_event_driven_save_after_deletion(deleted_count)

            # Émettre le signal
            self.device_deleted.emit(device_ids[:deleted_count])

        else:
            error_msg = "Aucun appareil n'a pu être supprimé"
            app_logger.error(error_msg)
            if self.user_interaction_service:
                self.user_interaction_service.show_error(error_msg)

        return deleted_count

    # ================================
    # VALIDATION
    # ================================

    def validate_device_data(self, device_data: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Valider les données d'un appareil"""
        return self._safe_validate_device_data(device_data)

    @handle_database_operation_errors(return_value=(False, ["Erreur de validation"]), log_prefix="Erreur validation appareil")
    def _safe_validate_device_data(self, device_data: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Version sécurisée de validate_device_data"""
        errors = []

        # Validation de la référence (obligatoire)
        reference = device_data.get('reference', '').strip()
        if not reference:
            errors.append("La référence est obligatoire")
        elif len(reference) > 50:
            errors.append("La référence ne peut pas dépasser 50 caractères")

        # Validation de la marque
        marque = device_data.get('marque', '').strip()
        if marque and len(marque) > 100:
            errors.append("La marque ne peut pas dépasser 100 caractères")

        # Validation du modèle
        modele = device_data.get('modele', '').strip()
        if modele and len(modele) > 100:
            errors.append("Le modèle ne peut pas dépasser 100 caractères")

        # Validation du prix
        prix_validation = self._safe_validate_price(device_data.get('prix', '0'))
        if prix_validation:
            errors.append(prix_validation)

        # Validation du stock
        stock_validation = self._safe_validate_stock(device_data.get('stock', '0'))
        if stock_validation:
            errors.append(stock_validation)

        # Validation des notes
        notes = device_data.get('notes', '').strip()
        if notes and len(notes) > 1000:
            errors.append("Les notes ne peuvent pas dépasser 1000 caractères")

        # Vérification de l'unicité de la référence
        if reference and self.db_manager:
            existing_device = self.db_manager.get_device_by_reference(reference)
            if existing_device:
                errors.append(f"La référence '{reference}' existe déjà")

        return len(errors) == 0, errors

    @handle_database_operation_errors(return_value="Le prix doit être un nombre valide", log_prefix="Erreur validation prix")
    def _safe_validate_price(self, prix_str: str) -> Optional[str]:
        """Valider le prix avec gestion d'erreur"""
        prix_str = prix_str.strip()
        if prix_str:
            prix = float(prix_str)
            if prix < 0:
                return "Le prix ne peut pas être négatif"
            elif prix > 999999.99:
                return "Le prix ne peut pas dépasser 999 999,99"
        return None

    @handle_database_operation_errors(return_value="Le stock doit être un nombre entier valide", log_prefix="Erreur validation stock")
    def _safe_validate_stock(self, stock_str: str) -> Optional[str]:
        """Valider le stock avec gestion d'erreur"""
        stock_str = stock_str.strip()
        if stock_str:
            stock = int(stock_str)
            if stock < 0:
                return "Le stock ne peut pas être négatif"
            elif stock > 99999:
                return "Le stock ne peut pas dépasser 99 999"
        return None

    def detect_data_inconsistencies(self) -> List[str]:
        """Détecter les incohérences dans les données"""
        return self._safe_detect_data_inconsistencies()

    @handle_database_operation_errors(return_value=["Erreur de détection"], log_prefix="Erreur détection incohérences")
    def _safe_detect_data_inconsistencies(self) -> List[str]:
        """Version sécurisée de detect_data_inconsistencies"""
        inconsistencies = []

        if not self.db_manager:
            return inconsistencies

        # Vérifier les références dupliquées
        duplicates = self.db_manager.find_duplicate_references()
        if duplicates:
            inconsistencies.append(f"Références dupliquées détectées: {len(duplicates)}")

        # Vérifier les prix incohérents
        invalid_prices = self.db_manager.find_invalid_prices()
        if invalid_prices:
            inconsistencies.append(f"Prix invalides détectés: {len(invalid_prices)}")

        # Vérifier les stocks négatifs
        negative_stocks = self.db_manager.find_negative_stocks()
        if negative_stocks:
            inconsistencies.append(f"Stocks négatifs détectés: {len(negative_stocks)}")

        if inconsistencies:
            app_logger.warning(f"Incohérences détectées: {inconsistencies}")

        return inconsistencies

    # ================================
    # MÉTHODES PRIVÉES/UTILITAIRES
    # ================================

    def _prepare_updates_from_modified_cells(self) -> Dict[int, Dict[str, str]]:
        """Préparer les mises à jour depuis les cellules modifiées"""
        return self._safe_prepare_updates_from_modified_cells()

    @handle_database_operation_errors(return_value={}, log_prefix="Erreur préparation mises à jour")
    def _safe_prepare_updates_from_modified_cells(self) -> Dict[int, Dict[str, str]]:
        """Version sécurisée de _prepare_updates_from_modified_cells"""
        updates_by_db_id = {}

        if not hasattr(self.parent_window, 'table') or not self.parent_window.table:
            return updates_by_db_id

        table = self.parent_window.table

        for row, col in self.modified_cells:
            # Traiter chaque cellule avec gestion d'erreur locale
            cell_update = self._safe_prepare_single_cell_update(table, row, col)
            if cell_update:
                db_id, column_name, cell_value = cell_update
                if db_id not in updates_by_db_id:
                    updates_by_db_id[db_id] = {}
                updates_by_db_id[db_id][column_name] = cell_value

        return updates_by_db_id

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur préparation cellule")
    def _safe_prepare_single_cell_update(self, table, row, col):
        """Préparer la mise à jour d'une cellule individuelle"""
        # Récupérer l'ID de la base de données
        db_id_item = table.item(row, 0)  # Colonne ID supposée être la première
        if not db_id_item:
            return None

        db_id = int(db_id_item.text())

        # Récupérer la valeur de la cellule
        cell_item = table.item(row, col)
        if not cell_item:
            return None

        cell_value = cell_item.text()

        # Récupérer le nom de la colonne
        header_item = table.horizontalHeaderItem(col)
        if not header_item:
            return None

        column_name = header_item.text().lower()

        return db_id, column_name, cell_value

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur conversion int")
    def _safe_convert_to_int(self, value):
        """Convertir une valeur en int de manière sécurisée"""
        return int(value)

    def _get_selected_device_ids(self) -> List[int]:
        """Récupérer les IDs des appareils sélectionnés"""
        return self._safe_get_selected_device_ids()

    @handle_database_operation_errors(return_value=[], log_prefix="Erreur récupération IDs sélectionnés")
    def _safe_get_selected_device_ids(self) -> List[int]:
        """Version sécurisée de _get_selected_device_ids"""
        device_ids = []

        if not hasattr(self.parent_window, 'table') or not self.parent_window.table:
            return device_ids

        table = self.parent_window.table
        selected_rows = set()

        # Récupérer les lignes sélectionnées
        for item in table.selectedItems():
            selected_rows.add(item.row())

        app_logger.debug(f"Lignes sélectionnées détectées: {selected_rows}")

        # Récupérer les vrais IDs d'appareils via table_fill_service
        for row in selected_rows:
            device_id = self._safe_get_device_id_from_row(table, row)
            if device_id:
                device_ids.append(device_id)
                app_logger.debug(f"ID appareil trouvé pour ligne {row}: {device_id}")
            else:
                app_logger.warning(f"Aucun ID trouvé pour la ligne sélectionnée {row}")

        app_logger.info(f"IDs finaux récupérés: {device_ids}")
        return device_ids

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur récupération ID ligne")
    def _safe_get_device_id_from_row(self, table, row):
        """Récupérer l'ID d'un appareil depuis une ligne de table"""
        # Utiliser la méthode existante qui connaît la structure de données
        return self.parent_window.table_fill_service.get_db_id_from_row(table, row)

    def _confirm_deletion(self, count: int) -> bool:
        """Demander confirmation pour la suppression"""
        return self._safe_confirm_deletion(count)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur dialogue confirmation")
    def _safe_confirm_deletion(self, count: int) -> bool:
        """Version sécurisée de _confirm_deletion"""
        if count == 1:
            message = "Êtes-vous sûr de vouloir supprimer cet appareil ?"
            title = "Confirmer la suppression"
        else:
            message = f"Êtes-vous sûr de vouloir supprimer ces {count} appareils ?"
            title = "Confirmer la suppression multiple"

        reply = QMessageBox.question(
            self.parent_window,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        return reply == QMessageBox.Yes

    def _update_save_indicators(self, saved: bool):
        """Mettre à jour les indicateurs de sauvegarde"""
        self._safe_update_save_indicators(saved)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur mise à jour indicateurs")
    def _safe_update_save_indicators(self, saved: bool):
        """Version sécurisée de _update_save_indicators"""
        if hasattr(self.parent_window, 'save_indicator') and self.parent_window.save_indicator:
            if saved:
                self.parent_window.save_indicator.setStyleSheet("color: green;")
                self.parent_window.save_indicator.setText("Sauvegardé")
            else:
                self.parent_window.save_indicator.setStyleSheet("color: orange;")
                self.parent_window.save_indicator.setText("● Non sauvegardé")

        if hasattr(self.parent_window, 'statusbar') and self.parent_window.statusbar:
            if saved:
                self.parent_window.statusbar.showMessage("Données sauvegardées", 2000)
            else:
                self.parent_window.statusbar.showMessage("Modifications en cours", 2000)

    # ================================
    # TRANSACTIONS
    # ================================

    def execute_with_transaction(self, operations: List[Callable]) -> bool:
        """Exécuter plusieurs opérations dans une transaction"""
        return self._safe_execute_with_transaction(operations)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur gestion transaction")
    def _safe_execute_with_transaction(self, operations: List[Callable]) -> bool:
        """Version sécurisée de execute_with_transaction"""
        if not self.db_manager or not hasattr(self.db_manager, 'begin_transaction'):
            app_logger.warning("Transactions non supportées, exécution séquentielle")
            # Fallback: exécution séquentielle sans transaction
            for operation in operations:
                if not operation():
                    return False
            return True

        # Début de transaction
        self.db_manager.begin_transaction()

        # Exécuter les opérations avec gestion d'erreur séparée
        return self._safe_execute_transaction_operations(operations)

    @handle_database_operation_errors(return_value=False, log_prefix="Erreur exécution transaction")
    def _safe_execute_transaction_operations(self, operations: List[Callable]) -> bool:
        """Exécuter les opérations de transaction avec rollback automatique"""
        # Exécuter toutes les opérations (le décorateur gère les exceptions)
        for operation in operations:
            if not operation():
                self.db_manager.rollback_transaction()
                return False

        # Confirmer la transaction
        self.db_manager.commit_transaction()
        return True

    def _trigger_event_driven_save_after_deletion(self, deleted_count: int):
        """Déclencher sauvegarde événementielle après suppression"""
        self._safe_trigger_event_driven_save_after_deletion(deleted_count)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur sauvegarde événementielle après suppression")
    def _safe_trigger_event_driven_save_after_deletion(self, deleted_count: int):
        """Version sécurisée de _trigger_event_driven_save_after_deletion"""
        app_logger.debug(f"Sauvegarde événementielle après suppression de {deleted_count} appareil(s)")
        # Après une suppression, les données sont déjà commitées en base
        # On peut forcer un auto_save pour s'assurer que les transactions en attente sont terminées
        success = self.auto_save()

        if success:
            app_logger.debug(f"Sauvegarde événementielle réussie après suppression")
        else:
            app_logger.warning(f"Échec sauvegarde événementielle après suppression")