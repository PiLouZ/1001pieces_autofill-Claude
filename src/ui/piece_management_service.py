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
from PyQt5.QtWidgets import QListWidgetItem, QMessageBox
from PyQt5.QtCore import Qt

from src.core.config import Config
from src.core.logger import app_logger


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
    
    def add_piece(self) -> None:
        """Ajouter une pièce aux appareils sélectionnés"""
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
            return
        
        if not ref_piece:
            self.main_window.user_interaction_service.show_info(Config.get_message('no_piece_ref'))
            return
        
        # Validation des caractères spéciaux
        if any(char in ref_piece for char in ['||', '&&']):
            self.main_window.user_interaction_service.show_error(
                "La référence de pièce ne peut pas contenir les caractères '||' ou '&&'"
            )
            return
        
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
            self.main_window._update_pieces_panel()
            self.main_window._refresh_pieces_count_column()
            
            # Message de succès
            if error_count == 0:
                history_message = f"Pièce '{ref_piece}' ajoutée avec succès à {success_count} appareil(s)"
            else:
                history_message = f"Pièce '{ref_piece}' ajoutée à {success_count} appareil(s)"
                if error_count > 0:
                    history_message += f" ({error_count} erreur(s))"
                    
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

    def edit_piece(self, item: QListWidgetItem) -> None:
        """Éditer une pièce (référence et libellé)"""
        if not item:
            return
            
        ref_piece = item.data(Qt.UserRole)
        if not ref_piece:
            return
        
        # Obtenir l'ID de l'appareil sélectionné
        current_row = self.main_window.table.currentRow()
        if current_row < 0:
            self.main_window.user_interaction_service.show_error("Aucun appareil sélectionné")
            return
        
        db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, current_row)
        if not db_id:
            self.main_window.user_interaction_service.show_error("Impossible de récupérer l'ID de l'appareil")
            return
        
        try:
            # Récupérer les données actuelles de la pièce
            current_data = self.main_window.db_manager.get_piece_info(ref_piece, db_id)
            if not current_data:
                self.main_window.user_interaction_service.show_error("Pièce non trouvée")
                return
            
            current_ref, current_libelle = current_data
            
            # Dialog pour éditer la référence et le libellé
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
            
            dialog = QDialog(self.main_window)
            dialog.setWindowTitle("Éditer la pièce")
            dialog.setModal(True)
            dialog.resize(400, 150)
            
            layout = QVBoxLayout(dialog)
            
            # Référence
            ref_layout = QHBoxLayout()
            ref_layout.addWidget(QLabel("Référence:"))
            ref_input = QLineEdit(ref_piece)
            ref_layout.addWidget(ref_input)
            layout.addLayout(ref_layout)
            
            # Libellé
            libelle_layout = QHBoxLayout()
            libelle_layout.addWidget(QLabel("Libellé:"))
            libelle_input = QLineEdit(current_libelle)
            libelle_layout.addWidget(libelle_input)
            layout.addLayout(libelle_layout)
            
            # Boutons
            btn_layout = QHBoxLayout()
            ok_btn = QPushButton("OK")
            cancel_btn = QPushButton("Annuler")
            btn_layout.addWidget(ok_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)
            
            # Connexions
            ok_btn.clicked.connect(dialog.accept)
            cancel_btn.clicked.connect(dialog.reject)
            
            if dialog.exec_() == QDialog.Accepted:
                new_ref = ref_input.text().strip()
                new_libelle = libelle_input.text().strip()
                
                if not new_ref:
                    self.main_window.user_interaction_service.show_error("La référence ne peut pas être vide")
                    return
                
                # Validation des caractères spéciaux
                if any(char in new_ref for char in ['||', '&&']):
                    self.main_window.user_interaction_service.show_error(
                        "La référence de pièce ne peut pas contenir les caractères '||' ou '&&'"
                    )
                    return
                
                # Mettre à jour la pièce - utiliser update_piece si elle existe ou une logique alternative
                # D'abord supprimer l'ancienne et ajouter la nouvelle si la référence a changé
                if new_ref != ref_piece:
                    # Si la référence change, supprimer l'ancienne et créer une nouvelle
                    delete_success = self.main_window.db_manager.delete_piece(ref_piece, db_id)
                    if delete_success:
                        add_result = self.main_window.db_manager.add_piece(new_ref, db_id, new_libelle)
                        success = bool(add_result)
                    else:
                        success = False
                else:
                    # Si seul le libellé change, utiliser update_piece si disponible
                    try:
                        success = self.main_window.db_manager.update_piece(new_ref, new_libelle)
                    except AttributeError:
                        # Si update_piece n'existe pas, recréer la pièce
                        delete_success = self.main_window.db_manager.delete_piece(ref_piece, db_id)
                        if delete_success:
                            add_result = self.main_window.db_manager.add_piece(new_ref, db_id, new_libelle)
                            success = bool(add_result)
                        else:
                            success = False
                
                if success:
                    self.main_window._update_pieces_panel()
                    self.main_window._refresh_pieces_count_column()
                    self.main_window.user_interaction_service.add_to_history(f"Pièce modifiée: '{ref_piece}' → '{new_ref}'")
                    self.main_window.user_interaction_service.show_status_message(
                        f"Pièce modifiée avec succès", Config.STATUS_MESSAGE_TIMEOUT
                    )
                else:
                    self.main_window.user_interaction_service.show_error("Erreur lors de la modification de la pièce")
                    
        except Exception as e:
            app_logger.error(f"Erreur lors de l'édition de pièce: {e}")
            self.main_window.user_interaction_service.show_error(f"Erreur: {e}")

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
            try:
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
                    self.main_window._update_pieces_panel()
                    self.main_window._refresh_pieces_count_column()
                    self.main_window.user_interaction_service.add_to_history(f"Pièce '{ref_piece}' supprimée")
                    self.main_window.user_interaction_service.show_status_message(
                        f"Pièce supprimée avec succès", Config.STATUS_MESSAGE_TIMEOUT
                    )
                else:
                    self.main_window.user_interaction_service.show_error("Erreur lors de la suppression")
                    
            except Exception as e:
                app_logger.error(f"Erreur lors de la suppression de pièce: {e}")
                self.main_window.user_interaction_service.show_error(f"Erreur: {e}")

    def copy_piece(self, item: QListWidgetItem) -> None:
        """Copier la référence d'une pièce dans le presse-papier"""
        ref_piece = item.data(Qt.UserRole)
        if ref_piece:
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(ref_piece)
            self.main_window.user_interaction_service.show_status_message(
                f"Référence '{ref_piece}' copiée", 2000
            )

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
            f"Supprimer la pièce '{ref_piece}' de {len(selected_rows)} appareil(s) sélectionné(s) ?",
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
                self.main_window._update_pieces_panel()
                self.main_window._refresh_pieces_count_column()
                
                message = f"Pièce '{ref_piece}' supprimée de {success_count} appareil(s)"
                if error_count > 0:
                    message += f" ({error_count} erreur(s))"
                
                self.main_window.user_interaction_service.add_to_history(message)
                self.main_window.user_interaction_service.show_status_message(message, Config.STATUS_MESSAGE_TIMEOUT)
            else:
                self.main_window.user_interaction_service.show_error("Aucune suppression effectuée")

    def open_pieces_manager(self) -> None:
        """Ouvrir la fenêtre de gestion des pièces"""
        try:
            from .pieces_manager import PiecesManagerWindow
            if not hasattr(self.main_window, 'pieces_manager') or not self.main_window.pieces_manager:
                self.main_window.pieces_manager = PiecesManagerWindow(self.main_window, self.main_window.db_manager)
            
            self.main_window.pieces_manager.show()
            self.main_window.pieces_manager.raise_()
            self.main_window.pieces_manager.activateWindow()
            
        except Exception as e:
            self.main_window.user_interaction_service.show_error(f"Erreur lors de l'ouverture du gestionnaire de pièces: {e}")

    def confirm_piece_description_update(self, ref_piece: str, existing_desc: str, new_desc: str) -> str:
        """
        Demander à l'utilisateur de confirmer la mise à jour d'une description de pièce.
        Retourne la description finale à utiliser.
        Utilise un cache pour éviter de redemander pour la même référence.
        """
        # Créer une clé de cache unique
        cache_key = f"{ref_piece}:{existing_desc}:{new_desc}"
        
        # Vérifier le cache
        if cache_key in self._piece_description_decisions:
            return self._piece_description_decisions[cache_key]
        
        # Si les descriptions sont identiques, pas besoin de demander
        if existing_desc == new_desc:
            return existing_desc
        
        # Préparer le message de confirmation
        message = f"Référence: {ref_piece}\n\n"
        message += f"Description actuelle: '{existing_desc}'\n"
        message += f"Nouvelle description: '{new_desc}'\n\n"
        message += "Que souhaitez-vous faire ?"
        
        # Afficher la boîte de dialogue personnalisée
        result = self.main_window.user_interaction_service.show_save_confirmation(
            "Mise à jour de description",
            message
        )
        
        if result == "yes":  # Remplacer par la nouvelle
            self._piece_description_decisions[cache_key] = new_desc
            return new_desc
        elif result == "no":  # Conserver l'existante
            self._piece_description_decisions[cache_key] = existing_desc
            return existing_desc
        else:  # Conserver l'existante
            self._piece_description_decisions[cache_key] = existing_desc
            return existing_desc