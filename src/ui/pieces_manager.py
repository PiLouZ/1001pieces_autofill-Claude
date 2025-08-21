"""
Gestionnaire des pièces - Fenêtre de gestion des références de pièces
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                           QTableWidgetItem, QLabel, QPushButton, QLineEdit,
                           QHeaderView, QMessageBox, QSplitter, QTextEdit,
                           QCheckBox, QApplication)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
import sqlite3
from typing import List, Tuple, Dict


class PiecesManagerWindow(QDialog):
    """Fenêtre de gestion des pièces"""
    
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("🔧 Gestionnaire des Pièces - 1001pieces.com")
        self.setModal(False)
        self.resize(1000, 700)
        
        self._init_ui()
        self._load_pieces_data()
        
    def _init_ui(self):
        """Initialiser l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Titre et statistiques
        header_layout = QHBoxLayout()
        title_label = QLabel("🔧 Gestionnaire des Pièces")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        header_layout.addWidget(title_label)
        
        self.stats_label = QLabel("Chargement...")
        self.stats_label.setStyleSheet("color: #666; margin: 10px;")
        header_layout.addWidget(self.stats_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Barre de recherche et filtres
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Recherche:"))
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher une référence ou un libellé de pièce...")
        self.search_input.textChanged.connect(self._filter_pieces)
        search_layout.addWidget(self.search_input)
        
        self.orphan_checkbox = QCheckBox("Afficher seulement les pièces orphelines")
        self.orphan_checkbox.stateChanged.connect(self._filter_pieces)
        search_layout.addWidget(self.orphan_checkbox)
        
        refresh_btn = QPushButton("🔄 Actualiser")
        refresh_btn.clicked.connect(self._load_pieces_data)
        search_layout.addWidget(refresh_btn)
        
        layout.addLayout(search_layout)
        
        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Tableau des pièces
        self.pieces_table = QTableWidget()
        self.pieces_table.setColumnCount(4)
        self.pieces_table.setHorizontalHeaderLabels([
            "Référence Pièce", "Libellé", "Nb Appareils", "Type d'Appareils"
        ])
        
        # Configuration du tableau
        header = self.pieces_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Référence
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Libellé
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Nb
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Types
        
        self.pieces_table.setAlternatingRowColors(True)
        self.pieces_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pieces_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)  # Sélection multiple
        self.pieces_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # Empêche l'édition
        self.pieces_table.itemSelectionChanged.connect(self._on_piece_selected)
        
        splitter.addWidget(self.pieces_table)
        
        # Zone de détails
        details_widget = QTextEdit()
        details_widget.setMaximumHeight(200)
        details_widget.setPlaceholderText("Sélectionnez une pièce pour voir les détails des appareils associés...")
        self.details_text = details_widget
        splitter.addWidget(details_widget)
        
        layout.addWidget(splitter)
        
        # Boutons d'action
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        export_btn = QPushButton("📊 Exporter la liste")
        export_btn.clicked.connect(self._export_pieces)
        buttons_layout.addWidget(export_btn)
        
        edit_btn = QPushButton("✏️ Modifier pièce")
        edit_btn.setToolTip("Modifier la référence et le libellé de la pièce sélectionnée")
        edit_btn.clicked.connect(self._edit_selected_piece)
        edit_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; }")
        buttons_layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("🗑️ Supprimer pièce(s)")
        delete_btn.setToolTip("Supprimer les références de pièces sélectionnées (Ctrl+Clic pour sélection multiple)")
        delete_btn.clicked.connect(self._delete_selected_pieces)
        delete_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; }")
        buttons_layout.addWidget(delete_btn)
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
    def _load_pieces_data(self):
        """Charger les données des pièces"""
        try:
            # Requête pour obtenir les statistiques des pièces (nouvelle structure)
            query = """
            SELECT 
                p.ref_piece,
                p.description,
                COUNT(DISTINCT pa.appareil_id) as nb_appareils,
                GROUP_CONCAT(DISTINCT a.type) as types_appareils
            FROM pieces p
            LEFT JOIN piece_associations pa ON p.id = pa.piece_id
            LEFT JOIN appareils a ON pa.appareil_id = a.id
            GROUP BY p.id, p.ref_piece, p.description
            ORDER BY nb_appareils DESC, p.ref_piece ASC
            """
            
            results = self.db_manager.execute_query(query)
            
            # Calculer les statistiques
            total_pieces = len(results)
            orphan_pieces = len([r for r in results if r[2] == 0])  # nb_appareils est maintenant à l'index 2
            total_associations = sum(r[2] for r in results)  # nb_appareils est maintenant à l'index 2
            
            from src.core.config import pluralize
            self.stats_label.setText(
                f"📊 {pluralize(total_pieces, 'référence')} • "
                f"⚠️ {pluralize(orphan_pieces, 'orpheline')} • "
                f"🔗 {pluralize(total_associations, 'association')}"
            )
            
            # Stocker les données pour le filtrage
            self.all_pieces_data = results
            self._update_table_display()
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors du chargement: {e}")
            
    def _update_table_display(self):
        """Mettre à jour l'affichage du tableau avec filtrage"""
        filtered_data = self._get_filtered_data()
        
        self.pieces_table.setRowCount(len(filtered_data))
        
        for row_idx, (ref_piece, description, nb_appareils, types_appareils) in enumerate(filtered_data):
            # Référence de pièce
            ref_item = QTableWidgetItem(ref_piece or "")
            self.pieces_table.setItem(row_idx, 0, ref_item)
            
            # Libellé de la pièce
            desc_item = QTableWidgetItem(description or "")
            desc_item.setToolTip(description or "Pas de libellé")
            self.pieces_table.setItem(row_idx, 1, desc_item)
            
            # Nombre d'appareils
            nb_item = QTableWidgetItem(str(nb_appareils))
            nb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Colorer selon le statut
            from src.core.config import pluralize
            if nb_appareils == 0:
                nb_item.setBackground(QColor(255, 200, 200))  # Rouge clair pour orphelines
                nb_item.setToolTip("⚠️ Pièce orpheline - aucun appareil associé")
            elif nb_appareils == 1:
                nb_item.setBackground(QColor(255, 255, 200))  # Jaune pour 1 seul
                nb_item.setToolTip("⚡ Pièce associée à un seul appareil")
            else:
                nb_item.setBackground(QColor(200, 255, 200))  # Vert pour multiples
                nb_item.setToolTip(f"✅ Pièce associée à {pluralize(nb_appareils, 'appareil')}")
                
            self.pieces_table.setItem(row_idx, 2, nb_item)
            
            # Types d'appareils (limité à 50 caractères pour l'affichage)
            types_display = types_appareils or "N/A"
            if len(types_display) > 50:
                types_display = types_display[:47] + "..."
            types_item = QTableWidgetItem(types_display)
            types_item.setToolTip(types_appareils or "Aucun type")
            self.pieces_table.setItem(row_idx, 3, types_item)
            
    def _get_filtered_data(self):
        """Obtenir les données filtrées selon les critères"""
        if not hasattr(self, 'all_pieces_data'):
            return []
            
        filtered = self.all_pieces_data
        
        # Filtre par recherche (référence ET libellé)
        search_text = self.search_input.text().lower().strip()
        if search_text:
            filtered = [
                row for row in filtered 
                if search_text in (row[0] or "").lower() or search_text in (row[1] or "").lower()
            ]
        
        # Filtre orphelines (nb_appareils est maintenant à l'index 2)
        if self.orphan_checkbox.isChecked():
            filtered = [row for row in filtered if row[2] == 0]
            
        return filtered
        
    def _filter_pieces(self):
        """Filtrer les pièces selon les critères"""
        self._update_table_display()
        
    def _on_piece_selected(self):
        """Quand une pièce est sélectionnée"""
        current_row = self.pieces_table.currentRow()
        if current_row < 0:
            self.details_text.clear()
            return
            
        # Obtenir la référence de la pièce sélectionnée
        ref_item = self.pieces_table.item(current_row, 0)
        if not ref_item:
            return
            
        ref_piece = ref_item.text()
        self._load_piece_details(ref_piece)
        
    def _load_piece_details(self, ref_piece):
        """Charger les détails d'une pièce"""
        try:
            query = """
            SELECT 
                a.id,
                a.type,
                a.manufacturer,
                a.ref_modele,
                a.commercial_ref,
                a.other_ref
            FROM pieces p
            JOIN piece_associations pa ON p.id = pa.piece_id
            JOIN appareils a ON pa.appareil_id = a.id
            WHERE p.ref_piece = ?
            ORDER BY a.type, a.manufacturer, a.ref_modele
            """
            
            results = self.db_manager.execute_query(query, [ref_piece])
            
            if not results:
                self.details_text.setText(f"⚠️ Aucun appareil associé à la pièce '{ref_piece}'")
                return
                
            from src.core.config import pluralize
            details = f"🔧 Détails de la pièce '{ref_piece}' ({pluralize(len(results), 'appareil')}):\n\n"
            
            for appareil in results:
                details += f"• ID {appareil[0]}: {appareil[1] or 'N/A'} | "
                details += f"{appareil[2] or 'N/A'} | "
                details += f"Modèle: {appareil[3] or 'N/A'} | "
                details += f"Commercial: {appareil[4] or 'N/A'}"
                if appareil[5]:
                    details += f" | Autre: {appareil[5]}"
                details += "\n"
                
            self.details_text.setText(details)
            
        except Exception as e:
            self.details_text.setText(f"❌ Erreur lors du chargement des détails: {e}")
            
    def _export_pieces(self):
        """Exporter la liste des pièces"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            
            filename, _ = QFileDialog.getSaveFileName(
                self, "Exporter les pièces", "pieces_export.csv",
                "Fichiers CSV (*.csv)"
            )
            
            if filename:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file, delimiter=';')
                    writer.writerow(['Référence Pièce', 'Nb Appareils', 'Types d\'Appareils'])
                    
                    filtered_data = self._get_filtered_data()
                    for ref_piece, nb_appareils, types_appareils in filtered_data:
                        writer.writerow([ref_piece, nb_appareils, types_appareils or ""])
                
                QMessageBox.information(self, "Export réussi", f"Liste exportée vers:\n{filename}")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export: {e}")
    
    def _delete_selected_pieces(self):
        """Supprimer les références de pièces sélectionnées"""
        selected_rows = list(set([item.row() for item in self.pieces_table.selectedItems()]))
        
        if not selected_rows:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner au moins une référence de pièce à supprimer.")
            return
        
        # Collecter les informations des pièces sélectionnées
        pieces_to_delete = []
        total_associations = 0
        
        for row in selected_rows:
            ref_item = self.pieces_table.item(row, 0)
            nb_item = self.pieces_table.item(row, 2)  # Colonne 2 pour le nombre d'appareils
            if ref_item and nb_item:
                ref_piece = ref_item.text()
                nb_appareils = int(nb_item.text())
                pieces_to_delete.append((ref_piece, nb_appareils))
                total_associations += nb_appareils
        
        if not pieces_to_delete:
            return
            
        # Confirmation
        from src.core.config import pluralize
        if len(pieces_to_delete) == 1:
            ref_piece, nb_appareils = pieces_to_delete[0]
            message = f"Supprimer la référence de pièce '{ref_piece}' ?\n\n"
            if nb_appareils > 0:
                message += f"⚠️ Cette pièce est associée à {pluralize(nb_appareils, 'appareil')}.\n"
                message += "Toutes les associations seront supprimées.\n\n"
        else:
            message = f"Supprimer {pluralize(len(pieces_to_delete), 'référence')} de pièces ?\n\n"
            if total_associations > 0:
                message += f"⚠️ Ces pièces sont associées à {pluralize(total_associations, 'appareil')} au total.\n"
                message += "Toutes les associations seront supprimées.\n\n"
                
        message += "Cette action est irréversible. Continuer ?"
        
        reply = QMessageBox.question(
            self, "Confirmation de suppression",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        try:
            deleted_count = 0
            deleted_associations = 0
            
            # Supprimer chaque pièce
            for ref_piece, nb_appareils in pieces_to_delete:
                query = "DELETE FROM pieces WHERE ref_piece = ?"
                result = self.db_manager.execute_query(query, [ref_piece])
                deleted_count += 1
                deleted_associations += nb_appareils
                
                # Ajouter à l'historique de la fenêtre principale
                self._add_to_main_history(ref_piece, nb_appareils)
            
            # Valider la transaction
            self.db_manager.conn.commit()
            
            # Message de succès
            if len(pieces_to_delete) == 1:
                QMessageBox.information(
                    self, "Suppression réussie",
                    f"La référence '{pieces_to_delete[0][0]}' et ses {pluralize(pieces_to_delete[0][1], 'association')} ont été supprimées."
                )
            else:
                QMessageBox.information(
                    self, "Suppression réussie",
                    f"{pluralize(deleted_count, 'référence')} supprimées avec {pluralize(deleted_associations, 'association')} au total."
                )
            
            # Recharger les données (sans fermer la fenêtre)
            self._load_pieces_data()
            
            # Informer la fenêtre principale si elle existe (sans forcer le refresh qui pourrait fermer cette fenêtre)
            # Note: Le refresh est fait automatiquement par l'historique
            # if hasattr(self.parent(), '_force_refresh_display'):
            #     self.parent()._force_refresh_display()
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur de suppression", f"Erreur lors de la suppression: {e}")
            
    def _add_to_main_history(self, ref_piece, nb_associations):
        """Ajouter une entrée dans l'historique de la fenêtre principale"""
        try:
            if hasattr(self.parent(), '_add_to_history'):
                # Ajouter directement à l'historique visible de la fenêtre principale
                from src.core.config import pluralize
                summary = f"🗑️ Suppression de la pièce '{ref_piece}' ({pluralize(nb_associations, 'association')})"
                self.parent()._add_to_history(summary)
        except Exception as e:
            print(f"Erreur lors de l'ajout à l'historique: {e}")
    
    def _edit_selected_piece(self):
        """Modifier la pièce sélectionnée"""
        current_row = self.pieces_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner une pièce à modifier.")
            return
            
        # Obtenir les données actuelles de la pièce
        ref_item = self.pieces_table.item(current_row, 0)
        desc_item = self.pieces_table.item(current_row, 1)
        
        if not ref_item:
            return
            
        current_ref = ref_item.text()
        current_desc = desc_item.text() if desc_item else ""
        
        # Créer une boîte de dialogue d'édition
        dialog = PieceEditDialog(self, current_ref, current_desc)
        if dialog.exec_() == QDialog.Accepted:
            new_ref, new_desc = dialog.get_values()
            
            # Mettre à jour dans la base de données
            try:
                # Vérifier si la nouvelle référence existe déjà (si elle a changé)
                if new_ref != current_ref:
                    existing_query = "SELECT id FROM pieces WHERE ref_piece = ?"
                    existing_result = self.db_manager.execute_query(existing_query, [new_ref])
                    if existing_result:
                        QMessageBox.warning(self, "Référence existante", 
                                          f"La référence '{new_ref}' existe déjà. Veuillez choisir une référence différente.")
                        return
                
                # Mettre à jour la pièce
                update_query = "UPDATE pieces SET ref_piece = ?, description = ? WHERE ref_piece = ?"
                self.db_manager.cursor.execute(update_query, (new_ref, new_desc, current_ref))
                self.db_manager.conn.commit()
                
                # Recharger les données
                self._load_pieces_data()
                
                # Ajouter à l'historique de la fenêtre principale
                if hasattr(self.parent(), '_add_to_history'):
                    changes = []
                    if new_ref != current_ref:
                        changes.append(f"référence: '{current_ref}' → '{new_ref}'")
                    if new_desc != current_desc:
                        changes.append(f"libellé: '{current_desc or '(vide)'}' → '{new_desc or '(vide)'}'")
                    
                    if changes:
                        summary = f"✏️ Modification de la pièce: {', '.join(changes)}"
                        self.parent()._add_to_history(summary)
                
                QMessageBox.information(self, "Succès", "La pièce a été modifiée avec succès.")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la modification: {e}")


class PieceEditDialog(QDialog):
    """Dialogue d'édition d'une pièce"""
    
    def __init__(self, parent, current_ref, current_desc):
        super().__init__(parent)
        self.setWindowTitle("Modifier la pièce")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout()
        
        # Champ référence
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence:"))
        self.ref_input = QLineEdit(current_ref)
        self.ref_input.setPlaceholderText("Référence de la pièce")
        ref_layout.addWidget(self.ref_input)
        layout.addLayout(ref_layout)
        
        # Champ libellé
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Libellé:"))
        self.desc_input = QLineEdit(current_desc)
        self.desc_input.setPlaceholderText("Libellé de la pièce (optionnel)")
        desc_layout.addWidget(self.desc_input)
        layout.addLayout(desc_layout)
        
        # Boutons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Sauvegarder")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; }")
        buttons_layout.addWidget(save_btn)
        
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
        
        # Focus sur le champ référence
        self.ref_input.selectAll()
        self.ref_input.setFocus()
        
    def get_values(self):
        """Retourner les valeurs saisies"""
        return self.ref_input.text().strip(), self.desc_input.text().strip()