"""
Service centralisé pour les opérations de base de données CRUD
Extrait de main_refactored.py pour centraliser la logique métier critique
"""

from typing import Optional, Dict, List, Any, Tuple, Callable
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import pyqtSignal, Qt

from ..core.config import Config
from ..core.logger import app_logger
from .base_service import BaseService, service_operation

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
            'db_manager'  # Seul service réellement essentiel et toujours disponible
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

        # Validation des données
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
            if self.table_controller:
                self.table_controller.load_data()

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
        try:
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

            try:
                # Suspendre l'invalidation du cache pendant la sauvegarde
                cache_service = getattr(self, 'cache_service', None)
                if cache_service:
                    cache_service.suspend_invalidation("sauvegarde batch")

                # Effectuer les mises à jour en base
                success = self.db_manager.update_multiple_cells_batch(updates_by_db_id)

                if success:
                    cells_saved = sum(len(updates) for updates in updates_by_db_id.values())
                    app_logger.info(f"Sauvegarde batch réussie: {cells_saved} cellules")

                    # Nettoyer les cellules modifiées
                    self.modified_cells.clear()

                    # Mettre à jour les indicateurs UI
                    self._update_save_indicators(True)

                    # Émettre le signal
                    self.data_saved.emit(cells_saved)

                    return True
                else:
                    app_logger.error("Échec de la sauvegarde batch")
                    if self.user_interaction_service:
                        self.user_interaction_service.show_error("Erreur lors de la sauvegarde")
                    return False

            finally:
                # Reprendre l'invalidation du cache
                cache_service = getattr(self, 'cache_service', None)
                if cache_service:
                    cache_service.resume_invalidation(force_invalidate=True)

        except Exception as e:
            app_logger.error(f"Erreur lors de la sauvegarde batch: {e}")
            if self.user_interaction_service:
                self.user_interaction_service.show_error(f"Erreur sauvegarde: {e}")
            return False
        finally:
            self.save_in_progress = False

    def save_drag_changes(self, drag_handle) -> bool:
        """Sauvegarder les modifications issues d'un drag & drop"""
        try:
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

        except Exception as e:
            app_logger.error(f"Erreur sauvegarde drag & drop: {e}")
            if self.user_interaction_service:
                self.user_interaction_service.show_error(f"Erreur drag & drop: {e}")
            return False

    def manual_save(self) -> bool:
        """Effectuer une sauvegarde manuelle"""
        try:
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

        except Exception as e:
            import traceback
            traceback.print_exc()
            app_logger.error(f"Erreur sauvegarde manuelle: {e}")
            return False

    @service_operation("sauvegarde_automatique")
    def auto_save(self) -> bool:
        """Effectuer une sauvegarde automatique"""
        try:
            # Accéder directement aux modified_cells du parent
            parent_modified_cells = getattr(self.parent_window, 'modified_cells', set())

            # Vérifier s'il y a des modifications à sauvegarder
            if not parent_modified_cells:
                return True

            # Convertir modified_cells en format attendu
            updates_by_db_id = self._convert_modified_cells_to_updates(parent_modified_cells)

            # Utiliser save_cells_batch pour l'auto-save
            return self.save_cells_batch(updates_by_db_id)

        except Exception as e:
            app_logger.error(f"Erreur sauvegarde automatique: {e}")
            return False

    def _convert_modified_cells_to_updates(self, modified_cells_to_use=None) -> Dict[int, Dict[str, str]]:
        """Convertir modified_cells du parent en format attendu par save_cells_batch"""
        try:
            if not self.parent_window or not hasattr(self.parent_window, 'table'):
                app_logger.warning("Impossible de convertir modified_cells: parent_window ou table non disponible")
                return {}

            # Utiliser les cellules fournies ou celles du service
            cells_to_convert = modified_cells_to_use if modified_cells_to_use is not None else self.modified_cells

            table = self.parent_window.table
            updates_by_db_id = {}

            for row, col in cells_to_convert:
                try:
                    # Vérifier le nom de la colonne pour détecter si c'est l'ID
                    column_header = table.horizontalHeaderItem(col)
                    if not column_header:
                        continue
                    column_name = column_header.text()

                    # Ignorer seulement si c'est réellement une colonne ID
                    if col == 0 and column_name.lower() in ['id', 'db_id', 'database_id']:
                        continue

                    # Obtenir l'item de la cellule
                    item = table.item(row, col)
                    if not item:
                        continue

                    # Chercher l'ID database (peut être dans une colonne cachée ou via d'autres moyens)
                    db_id = None

                    # Méthode 1: Chercher UserRole dans TOUTES les colonnes de la ligne
                    for check_col in range(table.columnCount()):
                        table_item = table.item(row, check_col)
                        if table_item:
                            user_role_data = table_item.data(Qt.UserRole)
                            if user_role_data:
                                try:
                                    db_id = int(user_role_data)
                                    break
                                except (ValueError, TypeError):
                                    continue

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
                        continue  # Ignorer les cellules sans ID database valide

                    # (column_name déjà défini plus haut)

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

                    # Ajouter aux updates
                    if db_id not in updates_by_db_id:
                        updates_by_db_id[db_id] = {}

                    updates_by_db_id[db_id][field_name] = cell_value

                except (ValueError, AttributeError) as e:
                    app_logger.warning(f"Erreur conversion cellule ({row},{col}): {e}")
                    continue

            return updates_by_db_id

        except Exception as e:
            app_logger.error(f"Erreur _convert_modified_cells_to_updates: {e}")
            return {}

    # ================================
    # OPÉRATIONS DELETE
    # ================================

    def delete_selected_devices(self, device_ids: Optional[List[int]] = None) -> int:
        """Supprimer les appareils sélectionnés"""
        try:
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
                if self.table_controller:
                    self.table_controller.load_data()

                # Invalider le cache
                cache_service = getattr(self, 'cache_service', None)
                if cache_service:
                    cache_service.invalidate_all("appareils supprimés")

                # Ajouter à l'historique
                if self.user_interaction_service and devices_info:
                    history_msg = f"Suppression de {deleted_count} appareil(s): " + ", ".join(devices_info[:3])
                    if len(devices_info) > 3:
                        history_msg += f" et {len(devices_info) - 3} autre(s)"
                    self.user_interaction_service.add_to_history(history_msg)

                # Afficher le résultat
                if self.user_interaction_service:
                    self.user_interaction_service.show_success(
                        f"{deleted_count} appareil(s) supprimé(s) avec succès"
                    )

                # Émettre le signal
                self.device_deleted.emit(device_ids[:deleted_count])

            else:
                error_msg = "Aucun appareil n'a pu être supprimé"
                app_logger.error(error_msg)
                if self.user_interaction_service:
                    self.user_interaction_service.show_error(error_msg)

            return deleted_count

        except Exception as e:
            app_logger.error(f"Erreur lors de la suppression: {e}")
            if self.user_interaction_service:
                self.user_interaction_service.show_error(f"Erreur suppression: {e}")
            return 0

    # ================================
    # VALIDATION
    # ================================

    def validate_device_data(self, device_data: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Valider les données d'un appareil"""
        errors = []

        try:
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
            try:
                prix_str = device_data.get('prix', '0').strip()
                if prix_str:
                    prix = float(prix_str)
                    if prix < 0:
                        errors.append("Le prix ne peut pas être négatif")
                    elif prix > 999999.99:
                        errors.append("Le prix ne peut pas dépasser 999 999,99")
            except ValueError:
                errors.append("Le prix doit être un nombre valide")

            # Validation du stock
            try:
                stock_str = device_data.get('stock', '0').strip()
                if stock_str:
                    stock = int(stock_str)
                    if stock < 0:
                        errors.append("Le stock ne peut pas être négatif")
                    elif stock > 99999:
                        errors.append("Le stock ne peut pas dépasser 99 999")
            except ValueError:
                errors.append("Le stock doit être un nombre entier valide")

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

        except Exception as e:
            app_logger.error(f"Erreur lors de la validation: {e}")
            errors.append(f"Erreur de validation: {e}")
            return False, errors

    def detect_data_inconsistencies(self) -> List[str]:
        """Détecter les incohérences dans les données"""
        inconsistencies = []

        try:
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

        except Exception as e:
            app_logger.error(f"Erreur détection incohérences: {e}")
            inconsistencies.append(f"Erreur de détection: {e}")

        return inconsistencies

    # ================================
    # MÉTHODES PRIVÉES/UTILITAIRES
    # ================================

    def _prepare_updates_from_modified_cells(self) -> Dict[int, Dict[str, str]]:
        """Préparer les mises à jour depuis les cellules modifiées"""
        updates_by_db_id = {}

        try:
            if not hasattr(self.parent_window, 'table') or not self.parent_window.table:
                return updates_by_db_id

            table = self.parent_window.table

            for row, col in self.modified_cells:
                # Récupérer l'ID de la base de données
                db_id_item = table.item(row, 0)  # Colonne ID supposée être la première
                if not db_id_item:
                    continue

                try:
                    db_id = int(db_id_item.text())
                except ValueError:
                    continue

                # Récupérer la valeur de la cellule
                cell_item = table.item(row, col)
                if not cell_item:
                    continue

                cell_value = cell_item.text()

                # Récupérer le nom de la colonne
                header_item = table.horizontalHeaderItem(col)
                if not header_item:
                    continue

                column_name = header_item.text().lower()

                # Ajouter à la mise à jour
                if db_id not in updates_by_db_id:
                    updates_by_db_id[db_id] = {}

                updates_by_db_id[db_id][column_name] = cell_value

        except Exception as e:
            app_logger.error(f"Erreur préparation mises à jour: {e}")

        return updates_by_db_id

    def _get_selected_device_ids(self) -> List[int]:
        """Récupérer les IDs des appareils sélectionnés"""
        device_ids = []

        try:
            if not hasattr(self.parent_window, 'table') or not self.parent_window.table:
                return device_ids

            table = self.parent_window.table
            selected_rows = set()

            # Récupérer les lignes sélectionnées
            for item in table.selectedItems():
                selected_rows.add(item.row())

            # Récupérer les IDs
            for row in selected_rows:
                id_item = table.item(row, 0)  # Colonne ID supposée être la première
                if id_item:
                    try:
                        device_id = int(id_item.text())
                        device_ids.append(device_id)
                    except ValueError:
                        continue

        except Exception as e:
            app_logger.error(f"Erreur récupération IDs sélectionnés: {e}")

        return device_ids

    def _confirm_deletion(self, count: int) -> bool:
        """Demander confirmation pour la suppression"""
        try:
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

        except Exception as e:
            app_logger.error(f"Erreur dialogue confirmation: {e}")
            return False

    def _update_save_indicators(self, saved: bool):
        """Mettre à jour les indicateurs de sauvegarde"""
        try:
            if hasattr(self.parent_window, 'save_indicator') and self.parent_window.save_indicator:
                if saved:
                    self.parent_window.save_indicator.setStyleSheet("color: green;")
                    self.parent_window.save_indicator.setText("✓ Sauvegardé")
                else:
                    self.parent_window.save_indicator.setStyleSheet("color: orange;")
                    self.parent_window.save_indicator.setText("● Non sauvegardé")

            if hasattr(self.parent_window, 'statusbar') and self.parent_window.statusbar:
                if saved:
                    self.parent_window.statusbar.showMessage("Données sauvegardées", 2000)
                else:
                    self.parent_window.statusbar.showMessage("Modifications en cours", 2000)

        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateurs: {e}")

    # ================================
    # TRANSACTIONS
    # ================================

    def execute_with_transaction(self, operations: List[Callable]) -> bool:
        """Exécuter plusieurs opérations dans une transaction"""
        try:
            if not self.db_manager or not hasattr(self.db_manager, 'begin_transaction'):
                app_logger.warning("Transactions non supportées, exécution séquentielle")
                # Fallback: exécution séquentielle sans transaction
                for operation in operations:
                    if not operation():
                        return False
                return True

            # Début de transaction
            self.db_manager.begin_transaction()

            try:
                # Exécuter toutes les opérations
                for operation in operations:
                    if not operation():
                        self.db_manager.rollback_transaction()
                        return False

                # Confirmer la transaction
                self.db_manager.commit_transaction()
                return True

            except Exception as e:
                self.db_manager.rollback_transaction()
                app_logger.error(f"Erreur dans transaction, rollback effectué: {e}")
                return False

        except Exception as e:
            app_logger.error(f"Erreur gestion transaction: {e}")
            return False