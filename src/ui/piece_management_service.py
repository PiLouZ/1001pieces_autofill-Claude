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
from .qt_imports import Qt, QFrame
from .pieces_list_service import _link_if_truncated, PieceRelationsPopup, _format_piece_edit_history
from .piece_picker_dialog import PiecePickerDialog, RefTagList

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
                                 QPushButton, QGroupBox, QInputDialog, QMessageBox,
                                 QFrame, QScrollArea, QWidget, QApplication, QSize)
        import qtawesome as qta

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Éditer la pièce")
        dialog.setModal(True)

        # Hauteur max = écran disponible - marges de fenêtre
        screen_h = QApplication.primaryScreen().availableGeometry().height()
        dialog.resize(520, min(580, screen_h - 80))
        dialog.setMaximumHeight(screen_h - 60)

        # Layout racine : en-tête fixe + scroll + boutons fixes
        root_layout = QVBoxLayout(dialog)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ── Bandeau d'en-tête ─────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background: #f8f9fa; border-bottom: 1px solid #dee2e6;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon('fa5s.puzzle-piece', color='#495057').pixmap(16, 16))
        header_layout.addWidget(icon_lbl)

        ref_header_lbl = QLabel(ref_piece)
        ref_header_lbl.setStyleSheet(
            "font-family: monospace; font-weight: bold; font-size: 13px; color: #212529;"
        )
        header_layout.addWidget(ref_header_lbl)

        succ_status = QLabel()
        succ_status.setStyleSheet("font-size: 11px; padding: 1px 6px; border-radius: 3px;")
        header_layout.addWidget(succ_status)

        header_layout.addStretch()
        root_layout.addWidget(header)

        # ── Zone scrollable ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(4)

        scroll.setWidget(scroll_content)
        root_layout.addWidget(scroll, 1)

        # ── Séparateur avant les boutons ──────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")
        root_layout.addWidget(sep)

        # ── Champs Référence / Libellé ────────────────────────────────────
        def _field_row(label_text, value):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("font-size: 11px; color: #495057;")
            inp = QLineEdit(value)
            inp.setStyleSheet("font-size: 11px;")
            row.addWidget(lbl)
            row.addWidget(inp)
            return row, inp

        ref_row, ref_input = _field_row("Référence", ref_piece)
        layout.addLayout(ref_row)
        libelle_row, libelle_input = _field_row("Libellé", current_libelle)
        layout.addLayout(libelle_row)

        # ── Helper : header de section plat (style gestionnaire) ─────────
        def _section_sep(color='#dee2e6'):
            s = QFrame()
            s.setFrameShape(QFrame.HLine)
            s.setStyleSheet(f"color: {color};")
            return s

        def _section_header(label_text, color, btn_text, btn_color):
            row = QHBoxLayout()
            row.setContentsMargins(0, 4, 0, 0)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 11px;"
            )
            row.addWidget(lbl)
            row.addStretch()
            btn = QPushButton(btn_text)
            btn.setStyleSheet(
                f"QPushButton {{ color: {btn_color}; font-size: 11px; border: none; }}"
                f"QPushButton:hover {{ text-decoration: underline; }}"
            )
            btn.setFlat(True)
            row.addWidget(btn)
            return row, btn

        layout.addWidget(_section_sep())

        # ── Titre Succession + bouton obsolète sur la même ligne ──────────
        succ_hdr_row = QHBoxLayout()
        succ_hdr_row.setContentsMargins(0, 4, 0, 0)
        succ_hdr_lbl = QLabel("Succession")
        succ_hdr_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #495057;")
        succ_hdr_row.addWidget(succ_hdr_lbl)
        succ_hdr_row.addStretch()

        btn_obsolete = QPushButton("Marquer obsolète")
        btn_obsolete.setIcon(qta.icon('fa5s.ban', color='#c0392b'))
        btn_obsolete.setIconSize(QSize(11, 11))
        btn_obsolete.setStyleSheet(
            "QPushButton { color: #c0392b; font-size: 11px; border: none; padding: 2px 4px; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        btn_obsolete.setFlat(True)
        succ_hdr_row.addWidget(btn_obsolete)
        layout.addLayout(succ_hdr_row)

        # ── Conteneur Succession compact ──────────────────────────────────
        succ_container = QWidget()
        succ_inner = QVBoxLayout(succ_container)
        succ_inner.setContentsMargins(8, 2, 0, 2)
        succ_inner.setSpacing(2)

        sup_row, btn_superseded = _section_header(
            "↳ Remplacée par", "#e67e22", "+ Déclarer remplacée par…", "#e67e22"
        )
        sup_row.setContentsMargins(0, 0, 0, 0)
        succ_inner.addLayout(sup_row)

        superseded_by_tags = RefTagList()
        superseded_by_tags.set_compact(True)
        succ_inner.addWidget(superseded_by_tags)

        rep_row, btn_replaces = _section_header(
            "↑ Remplace", "#2980b9", "+ Ajouter une référence remplacée…", "#2980b9"
        )
        rep_row.setContentsMargins(0, 4, 0, 0)
        succ_inner.addLayout(rep_row)

        replaces_tags = RefTagList()
        replaces_tags.set_compact(True)
        succ_inner.addWidget(replaces_tags)

        layout.addWidget(succ_container)

        db = self.main_window.db_manager

        def _succ_history(msg):
            self.main_window.user_interaction_service.add_to_history(msg)

        def _refresh_succ():
            info = db.get_piece_status(ref_piece)
            status = info['status']
            is_obsolete = info['is_obsolete']
            ref_new = info.get('ref_new')
            btn_obsolete.setText("Retirer l'obsolescence" if is_obsolete else "Marquer obsolète")
            predecessors = db.get_all_predecessors(ref_piece)

            # Chip "Remplacée par" (0 ou 1)
            superseded_by_tags.set_refs([ref_new] if ref_new else [], '#e67e22')

            # Chips "Remplace" (N prédécesseurs)
            replaces_tags.set_refs(predecessors, '#2980b9')

            # Badge statut dans le bandeau d'en-tête
            if is_obsolete:
                succ_status.setText("Obsolète")
                succ_status.setStyleSheet(
                    "font-size: 11px; color: #c0392b; font-weight: bold;"
                    " background: #fdecea; border-radius: 3px; padding: 1px 6px;"
                )
            elif ref_new:
                succ_status.setText("Remplacée")
                succ_status.setStyleSheet(
                    "font-size: 11px; color: #e67e22; font-weight: bold;"
                    " background: #fef5e7; border-radius: 3px; padding: 1px 6px;"
                )
            elif predecessors:
                succ_status.setText("Remplaçante")
                succ_status.setStyleSheet(
                    "font-size: 11px; color: #2980b9; font-weight: bold;"
                    " background: #ebf5fb; border-radius: 3px; padding: 1px 6px;"
                )
            else:
                succ_status.setText("Courante")
                succ_status.setStyleSheet(
                    "font-size: 11px; color: #27ae60; font-weight: bold;"
                    " background: #eafaf1; border-radius: 3px; padding: 1px 6px;"
                )

        def _on_superseded():
            pick = PiecePickerDialog(db, dialog, exclude_ref=ref_piece,
                                     title=f"Référence qui remplace '{ref_piece}'")
            if pick.exec_() != QDialog.Accepted:
                return
            ref_new = pick.selected_ref()
            if not ref_new:
                return
            success, error = db.add_supersession(ref_piece, ref_new)
            if success:
                _succ_history(f"Succession :\n==> '{ref_piece}' → '{ref_new}'")
                _refresh_succ()
            else:
                QMessageBox.warning(dialog, "Erreur de succession", error)

        def _on_replaces():
            pick = PiecePickerDialog(db, dialog, exclude_ref=ref_piece,
                                     title=f"Référence remplacée par '{ref_piece}'")
            if pick.exec_() != QDialog.Accepted:
                return
            ref_old = pick.selected_ref()
            if not ref_old:
                return
            success, error = db.add_supersession(ref_old, ref_piece)
            if success:
                _succ_history(f"Succession :\n==> '{ref_old}' → '{ref_piece}'")
                _refresh_succ()
            else:
                QMessageBox.warning(dialog, "Erreur de succession", error)

        def _on_remove_superseded_by(_ref_new_chip: str):
            db.remove_supersession(ref_piece)
            _succ_history(f"Succession :\n==> '{ref_piece}' → (succession annulée)")
            _refresh_succ()

        def _on_remove_replaces(ref_old_chip: str):
            db.remove_supersession(ref_old_chip)
            _succ_history(f"Succession :\n==> '{ref_old_chip}' → (succession annulée)")
            _refresh_succ()

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

        btn_superseded.clicked.connect(_on_superseded)
        btn_replaces.clicked.connect(_on_replaces)
        superseded_by_tags.ref_removed.connect(_on_remove_superseded_by)
        replaces_tags.ref_removed.connect(_on_remove_replaces)
        btn_obsolete.clicked.connect(_on_obsolete)

        # Clic sur une référence → ouvrir (ou mettre au premier plan) le gestionnaire
        def _open_in_manager(ref: str):
            from .pieces_manager import PiecesManagerWindow
            mw = self.main_window
            if not hasattr(mw, 'pieces_manager') or not mw.pieces_manager:
                mw.pieces_manager = PiecesManagerWindow(mw, mw.db_manager)
            mw.pieces_manager.show()
            mw.pieces_manager.raise_()
            mw.pieces_manager.activateWindow()
            mw.pieces_manager._search_in_manager(ref)

        superseded_by_tags.ref_clicked.connect(_open_in_manager)
        replaces_tags.ref_clicked.connect(_open_in_manager)

        _refresh_succ()  # initialisation

        # ── Section Équivalences ────────────────────────────────────────────
        layout.addWidget(_section_sep())

        equiv_row, btn_link_equiv = _section_header(
            "≡ Équivalences", "#8e44ad", "+ Ajouter une équivalence…", "#8e44ad"
        )
        layout.addLayout(equiv_row)

        equiv_status = QLabel()
        equiv_status.setWordWrap(True)
        equiv_status.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(equiv_status)

        equiv_tags = RefTagList()
        equiv_tags.set_compact(True)
        layout.addWidget(equiv_tags)

        layout.addStretch()

        def _refresh_equiv():
            equivs = db.get_equivalents(ref_piece)
            if equivs:
                equiv_tags.set_refs(equivs, '#8e44ad')
                equiv_status.setText("")
            else:
                equiv_tags.set_refs([])
                equiv_status.setText("Aucune équivalence")
                equiv_status.setStyleSheet("color: #555555; font-size: 12px;")

        def _on_link_equiv():
            pick = PiecePickerDialog(db, dialog, exclude_ref=ref_piece,
                                     title=f"Référence équivalente à '{ref_piece}'")
            if pick.exec_() != QDialog.Accepted:
                return
            ref_b = pick.selected_ref()
            if not ref_b:
                return
            success = db.add_equivalence(ref_piece, ref_b)
            if success:
                _succ_history(f"Équivalence :\n==> '{ref_piece}' ≡ '{ref_b}'")
                _refresh_equiv()
            else:
                QMessageBox.warning(dialog, "Erreur", "Impossible de créer l'équivalence.")

        def _on_remove_equiv(equiv_ref: str):
            db.remove_equivalence(equiv_ref)
            _succ_history(f"Équivalence :\n==> '{equiv_ref}' → (retiré du groupe)")
            _refresh_equiv()

        btn_link_equiv.clicked.connect(_on_link_equiv)
        equiv_tags.ref_removed.connect(_on_remove_equiv)
        equiv_tags.ref_clicked.connect(_open_in_manager)
        _refresh_equiv()  # initialisation

        # ── Boutons Enregistrer / Annuler — hors scroll, toujours visibles ─
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(12, 8, 12, 12)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setIcon(qta.icon('fa5s.times', color='#495057'))
        cancel_btn.setIconSize(QSize(11, 11))
        cancel_btn.setStyleSheet(
            "QPushButton { padding: 3px 10px; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); }"
        )

        ok_btn = QPushButton("Enregistrer")
        ok_btn.setIcon(qta.icon('fa5s.check', color='white'))
        ok_btn.setIconSize(QSize(11, 11))
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background-color: #218838; }"
        )

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        root_layout.addWidget(btn_container)

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

                msg = _format_piece_edit_history(ref_piece, new_ref, current_libelle, new_libelle)
                if msg:
                    self.main_window.user_interaction_service.add_to_history(msg)

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