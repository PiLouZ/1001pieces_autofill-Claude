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
        self.setWindowTitle("🔧 Gestionnaire des Pièces")
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
        self.search_input.setPlaceholderText("Rechercher une référence de pièce...")
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
            "Référence Pièce", "Nb Appareils", "Type d'Appareils", "Actions"
        ])
        
        # Configuration du tableau
        header = self.pieces_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Référence
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Nb
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Types
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Actions
        
        self.pieces_table.setAlternatingRowColors(True)
        self.pieces_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
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
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
    def _load_pieces_data(self):
        """Charger les données des pièces"""
        try:
            # Requête pour obtenir les statistiques des pièces
            query = """
            SELECT 
                p.ref_piece,
                COUNT(DISTINCT p.appareil_id) as nb_appareils,
                GROUP_CONCAT(DISTINCT a.type) as types_appareils
            FROM pieces p
            LEFT JOIN appareils a ON p.appareil_id = a.id
            GROUP BY p.ref_piece
            ORDER BY nb_appareils DESC, p.ref_piece ASC
            """
            
            results = self.db_manager.execute_query(query)
            
            # Calculer les statistiques
            total_pieces = len(results)
            orphan_pieces = len([r for r in results if r[1] == 0])
            total_associations = sum(r[1] for r in results)
            
            self.stats_label.setText(
                f"📊 {total_pieces} références • "
                f"⚠️ {orphan_pieces} orphelines • "
                f"🔗 {total_associations} associations"
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
        
        for row_idx, (ref_piece, nb_appareils, types_appareils) in enumerate(filtered_data):
            # Référence de pièce
            ref_item = QTableWidgetItem(ref_piece or "")
            self.pieces_table.setItem(row_idx, 0, ref_item)
            
            # Nombre d'appareils
            nb_item = QTableWidgetItem(str(nb_appareils))
            nb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Colorer selon le statut
            if nb_appareils == 0:
                nb_item.setBackground(QColor(255, 200, 200))  # Rouge clair pour orphelines
                nb_item.setToolTip("⚠️ Pièce orpheline - aucun appareil associé")
            elif nb_appareils == 1:
                nb_item.setBackground(QColor(255, 255, 200))  # Jaune pour 1 seul
                nb_item.setToolTip("⚡ Pièce associée à un seul appareil")
            else:
                nb_item.setBackground(QColor(200, 255, 200))  # Vert pour multiples
                nb_item.setToolTip(f"✅ Pièce associée à {nb_appareils} appareils")
                
            self.pieces_table.setItem(row_idx, 1, nb_item)
            
            # Types d'appareils (limité à 50 caractères pour l'affichage)
            types_display = types_appareils or "N/A"
            if len(types_display) > 50:
                types_display = types_display[:47] + "..."
            types_item = QTableWidgetItem(types_display)
            types_item.setToolTip(types_appareils or "Aucun type")
            self.pieces_table.setItem(row_idx, 2, types_item)
            
            # Actions
            action_text = "🗑️ Supprimer" if nb_appareils == 0 else "👁️ Voir"
            action_item = QTableWidgetItem(action_text)
            action_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pieces_table.setItem(row_idx, 3, action_item)
            
    def _get_filtered_data(self):
        """Obtenir les données filtrées selon les critères"""
        if not hasattr(self, 'all_pieces_data'):
            return []
            
        filtered = self.all_pieces_data
        
        # Filtre par recherche
        search_text = self.search_input.text().lower().strip()
        if search_text:
            filtered = [
                row for row in filtered 
                if search_text in (row[0] or "").lower()
            ]
        
        # Filtre orphelines
        if self.orphan_checkbox.isChecked():
            filtered = [row for row in filtered if row[1] == 0]
            
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
            JOIN appareils a ON p.appareil_id = a.id
            WHERE p.ref_piece = ?
            ORDER BY a.type, a.manufacturer, a.ref_modele
            """
            
            results = self.db_manager.execute_query(query, [ref_piece])
            
            if not results:
                self.details_text.setText(f"⚠️ Aucun appareil associé à la pièce '{ref_piece}'")
                return
                
            details = f"🔧 Détails de la pièce '{ref_piece}' ({len(results)} appareil(s)):\n\n"
            
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