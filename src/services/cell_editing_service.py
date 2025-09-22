"""
Service d'édition des cellules
Centralise toute la logique d'édition, validation et sauvegarde des cellules de table
"""

from typing import Optional, Tuple, Dict, Any, List
from PyQt5.QtWidgets import QTableWidgetItem, QTableWidget
from PyQt5.QtCore import QObject, pyqtSignal

from ..core.logger import app_logger
from ..data.database_manager import DatabaseManager
from ..data.data_validator import DataValidator
from ..utils.error_handler import handle_errors

class CellEditingService(QObject):
    """Service centralisé pour l'édition des cellules"""
    
    # Signaux pour notifier les changements
    cell_updated = pyqtSignal(QTableWidgetItem, str, str)  # item, old_value, new_value
    cell_validation_failed = pyqtSignal(QTableWidgetItem, str)  # item, error_message
    batch_edit_completed = pyqtSignal(int)  # nombre de cellules modifiées
    
    def __init__(self, table_widget: QTableWidget, db_manager: DatabaseManager, 
                 data_validator: DataValidator, parent=None):
        super().__init__(parent)
        self.table = table_widget
        self.db_manager = db_manager
        self.data_validator = data_validator
        self.parent_window = parent
        
        # Cache pour optimiser les accès
        self._column_mapping_cache = {}
        self._validation_cache = {}
        
        # État des modifications
        self.pending_changes = {}  # {(row, col): (old_value, new_value)}
        self.is_batch_editing = False
        
    def get_cell_db_info(self, item: QTableWidgetItem) -> Tuple[Optional[int], Optional[str]]:
        """Récupérer les informations DB d'une cellule (db_id, column_name)"""
        try:
            from PyQt5.QtCore import Qt
            row, col = item.row(), item.column()

            # L'ID est stocké dans UserRole de chaque cellule
            db_id = item.data(Qt.ItemDataRole.UserRole)
            if db_id is None:
                return None, None

            try:
                db_id = int(db_id)
            except (ValueError, TypeError) as e:
                return None, None

            # Récupérer le nom de la colonne
            column_name = self._get_db_column_name(col)
            if not column_name:
                return None, None

            return db_id, column_name

        except Exception as e:
            app_logger.error(f"Erreur récupération info cellule: {e}")
            return None, None
            
    def _get_db_column_name(self, ui_column: int) -> Optional[str]:
        """Mapper une colonne UI vers le nom de colonne DB"""
        # Cache pour éviter les calculs répétés
        if ui_column in self._column_mapping_cache:
            return self._column_mapping_cache[ui_column]

        # Mapping correct des colonnes UI vers DB selon Config.DB_HEADERS
        from ..core.config import Config
        column_mapping = {}

        # Mapper les colonnes UI vers les colonnes DB correspondantes
        for ui_idx, db_field in enumerate(Config.DB_HEADERS):
            column_mapping[ui_idx] = db_field

        # La dernière colonne "Nb Pièces" est en lecture seule, pas de mapping DB

        column_name = column_mapping.get(ui_column)
        if column_name:
            self._column_mapping_cache[ui_column] = column_name

        return column_name

    def _try_auto_create_row(self, item: QTableWidgetItem, row: int, col: int) -> bool:
        """Essayer de créer automatiquement une ligne en base pour une cellule orpheline"""
        try:
            # Vérifier qu'on n'est pas en train de créer des lignes en boucle
            if hasattr(self, '_creating_rows') and self._creating_rows:
                return False

            # Ne créer automatiquement que pour des colonnes importantes
            # (éviter création pour colonnes calculées ou temporaires)
            important_columns = [1, 2, 3, 4, 5, 6]  # ref_piece, designation, ref_modele, type, manufacturer, commercial_ref
            if col not in important_columns:
                return False

            # Marquer qu'on est en création pour éviter la récursion
            self._creating_rows = True

            try:
                from ..core.config import Config

                # Créer un dictionnaire vide pour les données de base
                empty_data = {header: '' for header in Config.DB_HEADERS}

                # Ajouter la valeur actuelle de la cellule si elle n'est pas vide
                column_name = self._get_db_column_name(col)
                if column_name and item.text().strip():
                    empty_data[column_name] = item.text().strip()

                # Créer la ligne en base
                db_id = self.db_manager.insert_appareil(empty_data)

                if db_id:
                    # Mettre à jour l'item de la colonne 0 avec le nouvel ID
                    id_item = self.table.item(row, 0)
                    if not id_item:
                        # Créer l'item ID s'il n'existe pas
                        from PyQt5.QtWidgets import QTableWidgetItem
                        id_item = QTableWidgetItem(str(db_id))
                        self.table.setItem(row, 0, id_item)
                    else:
                        id_item.setText(str(db_id))

                    app_logger.info(f"Auto-création ligne réussie - ID: {db_id} pour cellule ({row}, {col})")
                    return True
                else:
                    app_logger.warning(f"Échec insert_appareil pour auto-création ligne ({row}, {col})")
                    return False

            finally:
                self._creating_rows = False

        except Exception as e:
            app_logger.error(f"Erreur auto-création ligne ({row}, {col}): {e}")
            if hasattr(self, '_creating_rows'):
                self._creating_rows = False
            return False

    @handle_errors("Erreur lors de la mise à jour de la cellule")
    def update_cell_in_db(self, item: QTableWidgetItem, skip_history: bool = False) -> bool:
        """Mettre à jour une cellule dans la base de données"""
        try:
            row, col = item.row(), item.column()
            new_value = item.text().strip()
            
            # Récupérer les informations de la cellule
            db_id, column_name = self.get_cell_db_info(item)
            if not db_id or not column_name:
                return False
                
            # Récupérer l'ancienne valeur
            old_value = getattr(item, '_original_value', '')
            
            # Éviter les mises à jour inutiles
            if old_value == new_value:
                return True
                
            # Validation de la nouvelle valeur
            if not self._validate_cell_value(column_name, new_value, db_id):
                return False
                
            # Mise à jour en base
            success = self.db_manager.update_cell(
                db_id,
                column_name,
                new_value
            )
            
            if success:
                # Gérer les actions post mise à jour
                self._handle_successful_cell_update(item, old_value, new_value, skip_history)
                return True
            else:
                app_logger.error(f"Échec mise à jour cellule: {column_name} = '{new_value}' (ID: {db_id})")
                return False
                
        except Exception as e:
            app_logger.error(f"Erreur mise à jour cellule: {e}")
            return False
            
    def _validate_cell_value(self, column_name: str, value: str, db_id: int) -> bool:
        """Valider la valeur d'une cellule"""
        try:
            # Utiliser le cache de validation si disponible
            cache_key = f"{column_name}:{value}"
            if cache_key in self._validation_cache:
                return self._validation_cache[cache_key]
                
            # Validation selon le type de colonne
            is_valid = True
            error_message = ""
            
            if column_name == 'pieces_count':
                # Validation pour le nombre de pièces (colonne read-only, ne devrait pas arriver)
                if value and not value.isdigit():
                    is_valid = False
                    error_message = "Le nombre de pièces doit être un nombre entier"
            elif column_name in ['ref_modele', 'commercial_ref', 'other_ref']:
                # Validation pour les références
                if len(value) > 100:  # Limite de longueur
                    is_valid = False
                    error_message = "La référence ne peut pas dépasser 100 caractères"
            elif column_name in ['type', 'manufacturer', 'category']:
                # Validation pour les champs catégoriques
                if len(value) > 50:
                    is_valid = False
                    error_message = "Ce champ ne peut pas dépasser 50 caractères"
            elif column_name == 'notes':
                # Validation pour les notes (peut être plus long)
                if len(value) > 500:
                    is_valid = False
                    error_message = "Les notes ne peuvent pas dépasser 500 caractères"
                    
            # Mettre en cache le résultat
            self._validation_cache[cache_key] = is_valid
            
            if not is_valid and error_message:
                self.cell_validation_failed.emit(
                    self.table.currentItem(), 
                    error_message
                )
                
            return is_valid
            
        except Exception as e:
            app_logger.error(f"Erreur validation cellule: {e}")
            return False
            
    def _handle_successful_cell_update(self, item: QTableWidgetItem, old_value: str, 
                                     new_value: str, skip_history: bool):
        """Gérer les actions post mise à jour réussie"""
        try:
            row, col = item.row(), item.column()
            
            # Marquer l'item comme modifié (style visuel)
            item.setData(32, True)  # Role personnalisé pour marquer les modifications
            
            # Sauvegarder la nouvelle valeur comme valeur originale
            item._original_value = new_value
            
            # Émettre le signal de mise à jour
            self.cell_updated.emit(item, old_value, new_value)
            
            # Ajouter à l'historique si requis
            if not skip_history and hasattr(self.parent_window, 'undo_manager_service'):
                self.parent_window.undo_manager_service.add_action({
                    'type': 'cell_edit',
                    'row': row,
                    'col': col,
                    'old_value': old_value,
                    'new_value': new_value,
                    'timestamp': app_logger.get_timestamp()
                })
                
            # Mettre à jour les statistiques si nécessaire
            self._update_statistics_after_edit(item)

        except Exception as e:
            app_logger.error(f"Erreur gestion post mise à jour: {e}")
            
    def _update_statistics_after_edit(self, item: QTableWidgetItem):
        """Mettre à jour les statistiques après édition"""
        try:
            # Mettre à jour les boutons et compteurs si nécessaire
            if hasattr(self.parent_window, '_update_incomplete_button_visibility'):
                self.parent_window._update_incomplete_button_visibility()
                
            # Rafraîchir la colonne de comptage si modifiée
            column_name = self._get_db_column_name(item.column())
            if column_name == 'pieces_count' and hasattr(self.parent_window, '_refresh_pieces_count_column'):
                self.parent_window._refresh_pieces_count_column()

        except Exception as e:
            app_logger.error(f"Erreur mise à jour statistiques: {e}")

    def start_batch_edit(self):
        """Démarrer une édition en lot"""
        self.is_batch_editing = True
        self.pending_changes.clear()
        
    def add_to_batch(self, item: QTableWidgetItem, new_value: str):
        """Ajouter une modification au lot"""
        if not self.is_batch_editing:
            return False
            
        row, col = item.row(), item.column()
        old_value = getattr(item, '_original_value', item.text())
        self.pending_changes[(row, col)] = (old_value, new_value)
        return True
        
    def commit_batch_edit(self) -> int:
        """Valider toutes les modifications du lot"""
        if not self.is_batch_editing:
            return 0
            
        success_count = 0
        
        try:
            for (row, col), (old_value, new_value) in self.pending_changes.items():
                item = self.table.item(row, col)
                if item:
                    item.setText(new_value)
                    if self.update_cell_in_db(item, skip_history=True):
                        success_count += 1
                        
            # Nettoyer l'état du lot
            self.is_batch_editing = False
            self.pending_changes.clear()
            
            # Émettre le signal de fin de lot
            self.batch_edit_completed.emit(success_count)
            
            app_logger.info(f"Édition en lot terminée: {success_count} cellules modifiées")
            return success_count
            
        except Exception as e:
            app_logger.error(f"Erreur lors de l'édition en lot: {e}")
            self.is_batch_editing = False
            self.pending_changes.clear()
            return success_count
            
    def cancel_batch_edit(self):
        """Annuler l'édition en lot"""
        self.is_batch_editing = False
        self.pending_changes.clear()
        
    def navigate_to_empty_cell(self, direction: str = 'down') -> bool:
        """Navigation intelligente vers une cellule vide"""
        try:
            current_row = self.table.currentRow()
            current_col = self.table.currentColumn()
            
            if current_row < 0 or current_col < 0:
                return False
                
            # Déterminer la direction de recherche
            if direction == 'down':
                start_row, end_row, step = current_row + 1, self.table.rowCount(), 1
            elif direction == 'up':
                start_row, end_row, step = current_row - 1, -1, -1
            else:
                return False
                
            # Chercher la prochaine cellule vide ou pleine selon le contexte
            current_item = self.table.item(current_row, current_col)
            current_is_empty = not current_item or not current_item.text().strip()
            
            for row in range(start_row, end_row, step):
                item = self.table.item(row, current_col)
                is_empty = not item or not item.text().strip()
                
                # Si on est sur une case vide, aller à la première case pleine
                # Si on est sur une case pleine, aller à la première case vide
                if current_is_empty and not is_empty:
                    self.table.setCurrentCell(row, current_col)
                    return True
                elif not current_is_empty and is_empty:
                    self.table.setCurrentCell(row, current_col)
                    return True
                    
            return False
            
        except Exception as e:
            app_logger.error(f"Erreur navigation cellule vide: {e}")
            return False
            
    def clear_validation_cache(self):
        """Vider le cache de validation"""
        self._validation_cache.clear()
        
    def get_edit_statistics(self) -> Dict[str, Any]:
        """Obtenir les statistiques d'édition"""
        return {
            'pending_changes': len(self.pending_changes),
            'is_batch_editing': self.is_batch_editing,
            'cache_size': len(self._validation_cache),
            'column_mappings': len(self._column_mapping_cache)
        }