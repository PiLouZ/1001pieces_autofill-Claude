"""
Service de gestion des pièces - Phase 2.14
Extrait de main_refactored.py pour centraliser la logique de gestion des pièces détachées

Responsabilités:
- Ajout, modification et suppression de pièces
- Gestion des associations pièces-appareils
- Validation et confirmation des opérations sur les pièces
- Interface avec le gestionnaire de pièces externe
- Mise à jour des descriptions et références de pièces
"""

from typing import Optional, List, Dict, Any, Set
from .qt_imports import QListWidgetItem, QMessageBox
from .qt_imports import Qt

from src.core.config import Config, pluralize
from src.core.logger import app_logger
from src.utils.error_handler import handle_ui_errors

class PieceManagementService:
    """
    Service spécialisé pour la gestion des pièces détachées
    
    Responsabilités:
    - Gestion du cycle de vie des pièces (CRUD)
    - Validation des références et descriptions
    - Gestion des associations pièces-appareils
    - Interface avec le gestionnaire de pièces externe
    - Confirmation des opérations critiques
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        # Cache pour éviter de redemander les confirmations de mise à jour
        self._piece_description_decisions = {}
    
    def add_piece(self) -> bool:
        """Ajouter une pièce aux appareils sélectionnés.

        Returns:
            True si la pièce a été ajoutée à au moins un appareil.
        """
        # Récupérer la référence et le libellé
        ref_piece = self.main_window.piece_input.text().strip()
        libelle_piece = self.main_window.piece_libelle_input.text().strip()
        
        # Récupérer toutes les lignes sélectionnées
        selected_rows = set()
        selected_ranges = self.main_window.table.selectedRanges()
        
        if selected_ranges:
            # Utiliser les plages sélectionnées
            for range_sel in selected_ranges:
                for row in range(range_sel.topRow(), range_sel.bottomRow() + 1):
                    selected_rows.add(row)
        else:
            # Fallback sur la ligne courante si aucune sélection
            current_row = self.main_window.table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)
        
        if not selected_rows:
            self.main_window.user_interaction_service.show_info(Config.get_message('no_selection'))
            return False
        
        if not ref_piece:
            self.main_window.user_interaction_service.show_info(Config.get_message('no_piece_ref'))
            return False
        
        # Validation des caractères spéciaux
        if any(char in ref_piece for char in ['||', '&&']):
            self.main_window.user_interaction_service.show_error(
                "La référence de pièce ne peut pas contenir les caractères '||' ou '&&'"
            )
            return False
        
        success_count = 0
        error_count = 0
        errors_detail = []
        
        # Traitement de chaque ligne sélectionnée
        for row in selected_rows:
            try:
                # Obtenir l'ID de l'appareil depuis la ligne
                db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, row)
                if not db_id:
                    app_logger.warning(f"ID non trouvé pour la ligne {row}")
                    error_count += 1
                    errors_detail.append(f"Ligne {row + 1}: ID non trouvé")
                    continue
                
                # Ajouter la pièce à l'appareil
                result = self.main_window.db_manager.add_piece(ref_piece, db_id, libelle_piece)
                
                if result:
                    success_count += 1
                else:
                    error_count += 1
                    errors_detail.append(f"Ligne {row + 1}: Échec ajout pièce")
                    
            except Exception as e:
                app_logger.error(f"Erreur lors de l'ajout de pièce ligne {row}: {e}")
                error_count += 1
                errors_detail.append(f"Ligne {row + 1}: {str(e)}")
        
        # Rafraîchissement et messages
        if success_count > 0:
            self.main_window.pieces_panel_service.update_pieces_panel()
            self.main_window._refresh_pieces_count_column()
            
            # Message de succès
            if error_count == 0:
                history_message = f"Pièce '{ref_piece}' ajoutée avec succès à {pluralize(success_count, 'appareil')}"
            else:
                history_message = f"Pièce '{ref_piece}' ajoutée à {pluralize(success_count, 'appareil')}"
                if error_count > 0:
                    history_message += f" ({pluralize(error_count, 'erreur')})"
                    
            self.main_window.user_interaction_service.add_to_history(history_message)
            self.main_window.user_interaction_service.show_status_message(history_message, Config.STATUS_MESSAGE_TIMEOUT)
            
            # Vider les champs après ajout réussi
            self.main_window.piece_input.clear()
            self.main_window.piece_libelle_input.clear()
        else:
            self.main_window.user_interaction_service.add_to_history(f"Erreur: Aucune pièce n'a pu être ajoutée pour '{ref_piece}'")
        
        # Affichage détaillé des erreurs si nécessaire
        if error_count > 0 and len(errors_detail) <= 5:
            error_msg = f"Erreurs détaillées:\n" + "\n".join(errors_detail)
            self.main_window.user_interaction_service.show_error(error_msg)
        elif error_count > 5:
            self.main_window.user_interaction_service.show_error(f"{error_count} erreurs détectées (trop nombreuses pour être affichées)")

        return success_count > 0

    @handle_ui_errors(log_prefix="Erreur ouverture pièce", show_message=True)
    def edit_piece(self, item: QListWidgetItem) -> None:
        """Ouvrir le gestionnaire de pièces positionné sur la pièce sélectionnée."""
        if not item:
            return
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        mw = self.main_window
        from .pieces_manager import PiecesManagerWindow
        if not hasattr(mw, 'pieces_manager') or not mw.pieces_manager:
            mw.pieces_manager = PiecesManagerWindow(mw, mw.db_manager)
        mw.pieces_manager.open_on_piece(ref_piece)

    @handle_ui_errors(log_prefix="Erreur suppression pièce", show_message=True)
    def delete_piece(self, item: QListWidgetItem) -> None:
        """Supprimer une pièce avec confirmation"""
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return

        # Demander confirmation avec raccourcis clavier
        confirmed = self.main_window.user_interaction_service.show_confirmation(
            "Confirmer la suppression",
            f"Êtes-vous sûr de vouloir supprimer la pièce '{ref_piece}' ?",
            default_yes=False
        )

        if confirmed:
            # Obtenir l'ID de l'appareil sélectionné
            current_row = self.main_window.table.currentRow()
            if current_row < 0:
                self.main_window.user_interaction_service.show_error("Aucun appareil sélectionné")
                return

            db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, current_row)
            if not db_id:
                self.main_window.user_interaction_service.show_error("Impossible de récupérer l'ID de l'appareil")
                return

            # Supprimer la pièce
            success = self.main_window.db_manager.delete_piece(ref_piece, db_id)

            if success:
                self.main_window.pieces_panel_service.update_pieces_panel()
                self.main_window._refresh_pieces_count_column()
                self.main_window.user_interaction_service.add_to_history(f"Pièce '{ref_piece}' supprimée")
                self.main_window.user_interaction_service.show_status_message(
                    f"Pièce supprimée avec succès", Config.STATUS_MESSAGE_TIMEOUT
                )
            else:
                self.main_window.user_interaction_service.show_error("Erreur lors de la suppression")

    def delete_piece_from_selected(self, item: QListWidgetItem) -> None:
        """Supprimer une pièce des appareils sélectionnés"""
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        
        # Récupérer toutes les lignes sélectionnées
        selected_rows = set()
        selected_ranges = self.main_window.table.selectedRanges()
        
        if selected_ranges:
            for range_sel in selected_ranges:
                for row in range(range_sel.topRow(), range_sel.bottomRow() + 1):
                    selected_rows.add(row)
        else:
            current_row = self.main_window.table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)
        
        if not selected_rows:
            self.main_window.user_interaction_service.show_info("Aucune sélection")
            return
        
        # Demander confirmation
        confirmed = self.main_window.user_interaction_service.show_confirmation(
            "Confirmer la suppression multiple",
            f"Supprimer la pièce '{ref_piece}' de "
            f"{pluralize(len(selected_rows), 'appareil sélectionné', 'appareils sélectionnés')} ?",
            default_yes=False
        )
        
        if confirmed:
            success_count = 0
            error_count = 0
            
            for row in selected_rows:
                try:
                    db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, row)
                    if db_id:
                        success = self.main_window.db_manager.delete_piece(ref_piece, db_id)
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    app_logger.error(f"Erreur suppression pièce ligne {row}: {e}")
                    error_count += 1
            
            # Rafraîchissement et messages
            if success_count > 0:
                self.main_window.pieces_panel_service.update_pieces_panel()
                self.main_window._refresh_pieces_count_column()
                
                message = f"Pièce '{ref_piece}' supprimée de {pluralize(success_count, 'appareil')}"
                if error_count > 0:
                    message += f" ({pluralize(error_count, 'erreur')})"
                
                self.main_window.user_interaction_service.add_to_history(message)
                self.main_window.user_interaction_service.show_status_message(message, Config.STATUS_MESSAGE_TIMEOUT)
            else:
                self.main_window.user_interaction_service.show_error("Aucune suppression effectuée")

    @handle_ui_errors(log_prefix="Erreur ouverture gestionnaire pièces", show_message=True)
    def _gestionnaire(self):
        """Fenêtre du gestionnaire de pièces, créée au premier besoin."""
        from .pieces_manager import PiecesManagerWindow
        if not hasattr(self.main_window, 'pieces_manager') or not self.main_window.pieces_manager:
            self.main_window.pieces_manager = PiecesManagerWindow(self.main_window, self.main_window.db_manager)
        return self.main_window.pieces_manager

    @handle_ui_errors(log_prefix="Erreur ouverture édition du libellé", show_message=True)
    def completer_libelle(self, ref: str) -> None:
        """Ouvrir « Modifier la pièce » sur le libellé de `ref` (lien de l'historique)."""
        self._gestionnaire().editer_libelle(ref)

    @handle_ui_errors(log_prefix="Erreur raccourci libellé", show_message=True)
    def completer_libelle_recherche(self) -> None:
        """
        Raccourci ⌘⇧L : modifier le libellé de la pièce tapée dans la recherche.
        Même résolution que les boutons Méta (référence exacte, puis sans tenir
        compte de la casse ; jamais de fragment).
        """
        terme = self.main_window.search_input.text().strip()
        piece = self.main_window.seo_service.trouver_piece(terme) if terme else None
        if not piece:
            message = (f"Libellé : aucune pièce ne correspond exactement à « {terme} »" if terme
                       else "Libellé : tapez d'abord une référence de pièce dans la recherche")
            self.main_window.statusbar.showMessage(message, 5000)
            return
        self.completer_libelle(piece[0])

    def open_pieces_manager(self) -> None:
        """Ouvrir la fenêtre de gestion des pièces"""
        self._gestionnaire()

        self.main_window.pieces_manager.show()
        self.main_window.pieces_manager.raise_()
        self.main_window.pieces_manager.activateWindow()