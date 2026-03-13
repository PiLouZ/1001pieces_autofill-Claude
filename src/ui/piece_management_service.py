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

from src.core.config import Config
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
            self.main_window.pieces_panel_service.update_pieces_panel()
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

    @handle_ui_errors(log_prefix="Erreur édition pièce", show_message=True)
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

        # Récupérer les données actuelles de la pièce
        current_data = self.main_window.db_manager.get_piece_info(ref_piece, db_id)
        if not current_data:
            self.main_window.user_interaction_service.show_error("Pièce non trouvée")
            return

        current_ref, current_libelle = current_data

        # Dialog pour éditer la référence et le libellé
        from .qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QGroupBox, QInputDialog, QMessageBox)

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Éditer la pièce")
        dialog.setModal(True)
        dialog.resize(460, 400)

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

        # ── Section Succession ────────────────────────────────────────────
        succ_group = QGroupBox("Succession de référence")
        succ_layout = QVBoxLayout()
        succ_layout.setSpacing(4)

        succ_status = QLabel()
        succ_status.setWordWrap(True)
        succ_status.setStyleSheet("font-size: 12px;")
        succ_layout.addWidget(succ_status)

        succ_btn_layout = QHBoxLayout()
        btn_superseded = QPushButton("Remplacée par…")
        btn_obsolete   = QPushButton("Marquer obsolète")
        btn_obsolete.setStyleSheet("QPushButton { color: #E05252; }")
        btn_cancel_s   = QPushButton("Annuler succession")
        succ_btn_layout.addWidget(btn_superseded)
        succ_btn_layout.addWidget(btn_obsolete)
        succ_btn_layout.addWidget(btn_cancel_s)
        succ_btn_layout.addStretch()
        succ_layout.addLayout(succ_btn_layout)
        succ_group.setLayout(succ_layout)
        layout.addWidget(succ_group)

        db = self.main_window.db_manager

        def _refresh_succ():
            info = db.get_piece_status(ref_piece)
            status = info['status']
            is_obsolete = info['is_obsolete']
            ref_new = info.get('ref_new')
            btn_obsolete.setText("Retirer l'obsolescence" if is_obsolete else "Marquer obsolète")
            predecessors = db.get_all_predecessors(ref_piece)
            if status == 'superseded':
                text = f"↳ Remplacée par  {ref_new}"
                if is_obsolete:
                    text += "  (⚠ obsolète)"
                succ_status.setText(text)
                succ_status.setStyleSheet("color: #e67e22; font-size: 12px; font-weight: bold;")
                btn_cancel_s.setEnabled(True)
            elif status == 'obsolete':
                succ_status.setText("⚠ Obsolète — aucun remplacement")
                succ_status.setStyleSheet("color: #c0392b; font-size: 12px; font-weight: bold;")
                btn_cancel_s.setEnabled(False)
            elif predecessors:
                refs_old = ", ".join(predecessors)
                succ_status.setText(f"↑ Remplace  {refs_old}")
                succ_status.setStyleSheet("color: #2980b9; font-size: 12px; font-weight: bold;")
                btn_cancel_s.setEnabled(False)
            else:
                succ_status.setText("✓ Référence courante")
                succ_status.setStyleSheet("color: #34A853; font-size: 12px; font-weight: bold;")
                btn_cancel_s.setEnabled(False)

        def _succ_history(msg):
            self.main_window.user_interaction_service.add_to_history(msg)

        def _on_superseded():
            ref_new, ok = QInputDialog.getText(
                dialog, "Référence de remplacement",
                f"Référence qui remplace '{ref_piece}' :")
            if not ok or not ref_new.strip():
                return
            success, error = db.add_supersession(ref_piece, ref_new.strip())
            if success:
                _succ_history(f"Succession :\n==> '{ref_piece}' → '{ref_new.strip()}'")
                _refresh_succ()
            else:
                QMessageBox.warning(dialog, "Erreur de succession", error)

        def _on_obsolete():
            appareils = db.get_appareils_for_piece_ref(ref_piece)
            msg = f"Marquer '{ref_piece}' comme obsolète (aucun remplacement) ?"
            if appareils:
                lines = [f"  • {mfr or '?'} {ref_mod or '?'} ({type_ or '?'})" for type_, mfr, ref_mod in appareils[:10]]
                if len(appareils) > 10:
                    lines.append(f"  … et {len(appareils) - 10} autre(s)")
                msg += "\n\nAppareils concernés :\n" + "\n".join(lines)
            if QMessageBox.question(
                dialog, "Marquer comme obsolète", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
            is_obsolete = db.get_piece_status(ref_piece)['is_obsolete']
            if is_obsolete:
                ok = db.unmark_obsolete(ref_piece)
                msg = f"Succession :\n==> '{ref_piece}' → plus obsolète"
            else:
                ok = db.mark_obsolete(ref_piece)
                msg = f"Succession :\n==> '{ref_piece}' → obsolète"
            if ok:
                _succ_history(msg)
                _refresh_succ()
            else:
                QMessageBox.warning(dialog, "Erreur", "Impossible de modifier le statut d'obsolescence.")

        def _on_cancel_succ():
            if QMessageBox.question(
                dialog, "Annuler la succession",
                f"Supprimer le lien de succession pour '{ref_piece}' ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
            db.remove_supersession(ref_piece)
            _succ_history(f"Succession :\n==> '{ref_piece}' → (succession annulée)")
            _refresh_succ()

        btn_superseded.clicked.connect(_on_superseded)
        btn_obsolete.clicked.connect(_on_obsolete)
        btn_cancel_s.clicked.connect(_on_cancel_succ)
        _refresh_succ()  # initialisation

        # ── Section Équivalences ────────────────────────────────────────────
        equiv_group = QGroupBox("Équivalences")
        equiv_layout = QVBoxLayout()
        equiv_layout.setSpacing(4)

        equiv_status = QLabel()
        equiv_status.setWordWrap(True)
        equiv_status.setStyleSheet("font-size: 12px;")
        equiv_layout.addWidget(equiv_status)

        equiv_btn_layout = QHBoxLayout()
        btn_link_equiv   = QPushButton("Lier comme équivalent…")
        btn_unlink_equiv = QPushButton("Retirer du groupe")
        btn_unlink_equiv.setStyleSheet("QPushButton { color: #E05252; }")
        equiv_btn_layout.addWidget(btn_link_equiv)
        equiv_btn_layout.addWidget(btn_unlink_equiv)
        equiv_btn_layout.addStretch()
        equiv_layout.addLayout(equiv_btn_layout)
        equiv_group.setLayout(equiv_layout)
        layout.addWidget(equiv_group)

        def _refresh_equiv():
            equivs = db.get_equivalents(ref_piece)
            if equivs:
                equiv_status.setText(f"≡ Équivalente à  {', '.join(equivs)}")
                equiv_status.setStyleSheet("color: #8e44ad; font-size: 12px; font-weight: bold;")
                btn_unlink_equiv.setEnabled(True)
            else:
                equiv_status.setText("Aucune équivalence")
                equiv_status.setStyleSheet("color: #555555; font-size: 12px;")
                btn_unlink_equiv.setEnabled(False)

        def _on_link_equiv():
            ref_b, ok = QInputDialog.getText(
                dialog, "Référence équivalente",
                f"Référence équivalente à '{ref_piece}' :")
            if not ok or not ref_b.strip():
                return
            ref_b = ref_b.strip()
            success = db.add_equivalence(ref_piece, ref_b)
            if success:
                _succ_history(f"Équivalence :\n==> '{ref_piece}' ≡ '{ref_b}'")
                _refresh_equiv()
            else:
                QMessageBox.warning(dialog, "Erreur", "Impossible de créer l'équivalence.")

        def _on_unlink_equiv():
            if QMessageBox.question(
                dialog, "Retirer du groupe",
                f"Retirer '{ref_piece}' de son groupe d'équivalence ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
            db.remove_equivalence(ref_piece)
            _succ_history(f"Équivalence :\n==> '{ref_piece}' → (retiré du groupe)")
            _refresh_equiv()

        btn_link_equiv.clicked.connect(_on_link_equiv)
        btn_unlink_equiv.clicked.connect(_on_unlink_equiv)
        _refresh_equiv()  # initialisation

        # Boutons OK / Annuler
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

            # Utiliser la nouvelle méthode update_piece_complete pour une vraie mise à jour
            try:
                success = self.main_window.db_manager.update_piece_complete(
                    ref_piece, new_ref, new_libelle, db_id
                )
            except AttributeError:
                # Fallback vers l'ancienne logique si update_piece_complete n'existe pas
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
                self.main_window.pieces_panel_service.update_pieces_panel()
                self.main_window._refresh_pieces_count_column()

                # Construire un message d'historique détaillé
                changes = []
                if ref_piece != new_ref:
                    changes.append(f"référence: '{ref_piece}' → '{new_ref}'")
                if current_libelle != new_libelle:
                    old_display = f"'{current_libelle}'" if current_libelle else "vide"
                    new_display = f"'{new_libelle}'" if new_libelle else "vide"
                    changes.append(f"libellé: {old_display} → {new_display}")

                if changes:
                    summary = "Pièce modifiée:\n" + "\n".join(f"==> {c}" for c in changes)
                    self.main_window.user_interaction_service.add_to_history(summary)

                self.main_window.user_interaction_service.show_status_message(
                    f"Pièce modifiée avec succès", Config.STATUS_MESSAGE_TIMEOUT
                )
            else:
                self.main_window.user_interaction_service.show_error("Erreur lors de la modification de la pièce")

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

    def copy_piece(self, item: QListWidgetItem) -> None:
        """Copier la référence d'une pièce dans le presse-papier"""
        ref_piece = item.data(Qt.UserRole)
        if ref_piece:
            from .qt_imports import QApplication
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
                self.main_window.pieces_panel_service.update_pieces_panel()
                self.main_window._refresh_pieces_count_column()
                
                message = f"Pièce '{ref_piece}' supprimée de {success_count} appareil(s)"
                if error_count > 0:
                    message += f" ({error_count} erreur(s))"
                
                self.main_window.user_interaction_service.add_to_history(message)
                self.main_window.user_interaction_service.show_status_message(message, Config.STATUS_MESSAGE_TIMEOUT)
            else:
                self.main_window.user_interaction_service.show_error("Aucune suppression effectuée")

    @handle_ui_errors(log_prefix="Erreur ouverture gestionnaire pièces", show_message=True)
    def open_pieces_manager(self) -> None:
        """Ouvrir la fenêtre de gestion des pièces"""
        from .pieces_manager import PiecesManagerWindow
        if not hasattr(self.main_window, 'pieces_manager') or not self.main_window.pieces_manager:
            self.main_window.pieces_manager = PiecesManagerWindow(self.main_window, self.main_window.db_manager)

        self.main_window.pieces_manager.show()
        self.main_window.pieces_manager.raise_()
        self.main_window.pieces_manager.activateWindow()

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