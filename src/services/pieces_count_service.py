"""
Service de gestion du comptage des pièces associées
Centralise la logique de mise à jour des compteurs de pièces dans l'interface
"""

from typing import Set, Optional, Dict
from ..ui.qt_imports import QTableWidget, QTableWidgetItem, QApplication, Qt, QColor

from ..data.database_manager import DatabaseManager
from ..core.logger import app_logger

class PiecesCountService:
    """Service dédié à la gestion du comptage et affichage des pièces associées"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def update_pieces_count_for_rows(self, table: QTableWidget, rows: Set[int]):
        """Mettre à jour la colonne Nb Pièces pour les lignes spécifiées"""
        if not rows or not table:
            return
            
        updated_count = 0
        
        for row in rows:
            try:
                db_id = self._get_db_id_from_row(table, row)
                if db_id:
                    # Récupérer le nombre exact de pièces depuis la base
                    pieces_count = self.db_manager.get_pieces_count_for_appareil(db_id)
                    
                    # Mettre à jour la cellule
                    success = self._update_pieces_cell(table, row, pieces_count, db_id)
                    if success:
                        updated_count += 1
                        app_logger.debug(f"Nb Pièces mis à jour: ligne {row} → {pieces_count} pièces")
                    else:
                        app_logger.warning(f"Échec mise à jour Nb Pièces ligne {row}")
                        
            except Exception as e:
                app_logger.error(f"Erreur mise à jour Nb Pièces ligne {row}: {e}")
        
        if updated_count > 0:
            # Forcer le rafraîchissement global après toutes les mises à jour
            self._force_table_refresh(table)
            print(f"  ✅ {updated_count}/{len(rows)} cellules Nb Pièces mises à jour")
    
    def refresh_entire_pieces_column(self, table: QTableWidget):
        """Rafraîchir la colonne Nb Pièces pour toutes les lignes visibles"""
        if not table or table.rowCount() == 0:
            return
            
        # Collecter toutes les lignes à mettre à jour
        all_rows = set(range(table.rowCount()))
        self.update_pieces_count_for_rows(table, all_rows)
            
    def find_row_by_db_id(self, table: QTableWidget, db_id: int) -> Optional[int]:
        """Trouver le numéro de ligne correspondant à un ID d'appareil"""
        if not table or db_id is None:
            return None
            
        for row in range(table.rowCount()):
            # Vérifier le db_id stocké dans la première cellule
            first_item = table.item(row, 0)
            if first_item and first_item.data(Qt.ItemDataRole.UserRole) == db_id:
                return row
        return None
    
    def _update_pieces_cell(self, table: QTableWidget, row: int, pieces_count: int, db_id: int) -> bool:
        """Mettre à jour une cellule spécifique de la colonne Nb Pièces"""
        try:
            # SOLUTION: Bloquer temporairement tous les signaux pour éviter les conflits
            old_signals_blocked = table.blockSignals(True)
            # Méthode 1: Essayer de modifier l'item existant d'abord
            existing_item = table.item(row, 7)
            if existing_item:
                # Modifier l'item existant
                existing_item.setText(str(pieces_count))
                existing_item.setData(Qt.ItemDataRole.UserRole, db_id)
                
                # Appliquer le style
                if pieces_count > 0:
                    existing_item.setBackground(QColor(220, 248, 198))  # Vert clair
                    existing_item.setToolTip(f"{pieces_count} pièce(s) associée(s)")
                else:
                    existing_item.setBackground(QColor(248, 248, 248))  # Gris clair
                    existing_item.setToolTip("Aucune pièce associée")
            else:
                # Créer un nouvel item si aucun n'existe
                pieces_item = QTableWidgetItem(str(pieces_count))
                pieces_item.setFlags(pieces_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                pieces_item.setData(Qt.ItemDataRole.UserRole, db_id)
                
                # Style selon le nombre de pièces
                if pieces_count > 0:
                    pieces_item.setBackground(QColor(220, 248, 198))  # Vert clair
                    pieces_item.setToolTip(f"{pieces_count} pièce(s) associée(s)")
                else:
                    pieces_item.setBackground(QColor(248, 248, 248))  # Gris clair
                    pieces_item.setToolTip("Aucune pièce associée")
                
                table.setItem(row, 7, pieces_item)
            
            return True
            
        except Exception as e:
            app_logger.error(f"Erreur lors de la mise à jour de la cellule [{row}, 7]: {e}")
            return False
        finally:
            # Rétablir les signaux dans tous les cas
            table.blockSignals(old_signals_blocked)
    
    def _force_table_refresh(self, table: QTableWidget):
        """Forcer le rafraîchissement visuel du tableau"""
        try:
            # Méthode 1: Rafraîchissement spécifique de la colonne 7
            table.resizeColumnToContents(7)
            
            # Méthode 2: Rafraîchissement du viewport
            table.viewport().repaint()
            
            # Méthode 3: Traitement des événements en attente
            QApplication.processEvents()
            
            # Méthode 4: Invalidation de la région de la colonne
            column_rect = table.visualRect(table.model().index(0, 7))
            if not column_rect.isEmpty():
                table.viewport().update(column_rect)
                
        except Exception as e:
            app_logger.error(f"Erreur lors du rafraîchissement du tableau: {e}")
    
    def _get_db_id_from_row(self, table: QTableWidget, row: int) -> Optional[int]:
        """Récupérer l'ID de l'appareil depuis une ligne du tableau"""
        if not table or row < 0 or row >= table.rowCount():
            return None
        
        # L'ID est stocké dans le UserRole de la première cellule
        first_item = table.item(row, 0)
        if first_item:
            return first_item.data(Qt.ItemDataRole.UserRole)
        return None
    
    def get_pieces_count_summary(self, table: QTableWidget) -> Dict[str, int]:
        """Obtenir un résumé du comptage des pièces dans le tableau"""
        if not table:
            return {"total_devices": 0, "devices_with_pieces": 0, "devices_without_pieces": 0}
        
        total_devices = table.rowCount()
        devices_with_pieces = 0
        devices_without_pieces = 0
        
        for row in range(total_devices):
            pieces_item = table.item(row, 7)
            if pieces_item:
                pieces_count = int(pieces_item.text()) if pieces_item.text().isdigit() else 0
                if pieces_count > 0:
                    devices_with_pieces += 1
                else:
                    devices_without_pieces += 1
            else:
                devices_without_pieces += 1
        
        return {
            "total_devices": total_devices,
            "devices_with_pieces": devices_with_pieces,
            "devices_without_pieces": devices_without_pieces
        }
