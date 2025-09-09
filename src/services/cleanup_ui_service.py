"""
Service d'interface utilisateur pour le nettoyage des doublons
Centralise la logique d'affichage et d'interaction pour la prévisualisation de nettoyage
"""

from typing import Dict, List, Any, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QGroupBox, QTabWidget,
    QProgressBar, QCheckBox, QTreeWidget, QTreeWidgetItem, QApplication
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtGui import QFont

from ..core.logger import app_logger
from .duplicates_analysis_service import clean_display_text


class CleanupStatsWidget(QWidget):
    """Widget pour afficher les statistiques de nettoyage"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialiser l'interface du widget statistiques"""
        layout = QHBoxLayout(self)
        
        # Statistiques principales
        self.devices_stats = QLabel("📱 0 groupes d'appareils (0 appareils concernés)")
        self.pieces_stats = QLabel("🔧 0 pièces dupliquées")
        self.inconsistencies_stats = QLabel("📋 0 incohérences potentielles")
        self.savings_stats = QLabel("💾 Économie potentielle: 0 appareils, 0 pièces")
        
        # Style
        for label in [self.devices_stats, self.pieces_stats, self.inconsistencies_stats, self.savings_stats]:
            label.setStyleSheet("padding: 8px; background: #f8f9fa; border-radius: 4px; margin: 2px;")
            
        layout.addWidget(self.devices_stats)
        layout.addWidget(self.pieces_stats)
        layout.addWidget(self.inconsistencies_stats)
        layout.addWidget(self.savings_stats)
        
    def update_stats(self, statistics: Dict[str, Any]):
        """Mettre à jour les statistiques affichées"""
        try:
            self.devices_stats.setText(
                f"📱 {statistics.get('total_duplicate_devices', 0)} groupes "
                f"({statistics.get('total_affected_devices', 0)} appareils concernés)"
            )
            
            self.pieces_stats.setText(
                f"🔧 {statistics.get('total_duplicate_pieces', 0)} pièces dupliquées "
                f"({statistics.get('total_affected_pieces', 0)} occurrences)"
            )
            
            self.inconsistencies_stats.setText(
                f"📋 {statistics.get('total_potential_inconsistencies', 0)} incohérences potentielles"
            )
            
            self.savings_stats.setText(
                f"💾 Économie potentielle: {statistics.get('potential_savings_devices', 0)} appareils, "
                f"{statistics.get('potential_savings_pieces', 0)} pièces"
            )
            
        except Exception as e:
            app_logger.error(f"Erreur mise à jour stats: {e}")


class DuplicateDevicesWidget(QWidget):
    """Widget pour gérer les appareils en doublon"""
    
    devices_selection_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.duplicate_groups = []
        self.init_ui()
        
    def init_ui(self):
        """Initialiser l'interface pour les appareils en doublon"""
        layout = QVBoxLayout(self)
        
        # En-tête avec actions
        header_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("Tout sélectionner")
        self.select_none_btn = QPushButton("Tout désélectionner")
        self.auto_select_oldest_btn = QPushButton("Sélectionner automatiquement (+ anciens)")
        self.auto_select_complete_btn = QPushButton("Sélectionner automatiquement (+ complets)")
        
        header_layout.addWidget(self.select_all_btn)
        header_layout.addWidget(self.select_none_btn)
        header_layout.addWidget(self.auto_select_oldest_btn)
        header_layout.addWidget(self.auto_select_complete_btn)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Arbre des appareils
        self.devices_tree = QTreeWidget()
        self.devices_tree.setHeaderLabels([
            "Sélection", "ID", "Référence Modèle", "Type", "Fabricant", 
            "Référence Commerciale", "Désignation", "Nb Pièces"
        ])
        self.devices_tree.setRootIsDecorated(True)
        
        layout.addWidget(self.devices_tree)
        
        # Connecter les signaux
        self.devices_tree.itemChanged.connect(self._on_item_changed)
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn.clicked.connect(self._select_none)
        self.auto_select_oldest_btn.clicked.connect(self._auto_select_oldest)
        self.auto_select_complete_btn.clicked.connect(self._auto_select_complete)
        
    def populate_devices(self, duplicate_devices: List[Dict[str, Any]]):
        """Remplir la liste des appareils en doublon"""
        self.duplicate_groups = duplicate_devices
        self.devices_tree.clear()
        
        for group in duplicate_devices:
            ref_modele = group['ref_modele']
            count = group['count']
            devices = group['devices']
            
            # Créer le nœud parent pour le groupe
            group_item = QTreeWidgetItem([
                "", "", f"{ref_modele} ({count} appareils)", "", "", "", "", ""
            ])
            group_item.setExpanded(True)
            
            # Style pour le groupe
            font = QFont()
            font.setBold(True)
            group_item.setFont(2, font)
            
            self.devices_tree.addTopLevelItem(group_item)
            
            # Ajouter les appareils individuels
            for device in devices:
                device_item = QTreeWidgetItem([
                    "", str(device['id']), device['ref_modele'], 
                    device['type_appareil'], device['manufacturer'],
                    device['commercial_ref'], device['designation'],
                    str(device['pieces_count'])
                ])
                
                # Checkbox pour sélection
                device_item.setFlags(device_item.flags() | Qt.ItemIsUserCheckable)
                device_item.setCheckState(0, Qt.Unchecked)
                device_item.setData(0, Qt.UserRole, device['id'])
                
                group_item.addChild(device_item)
                
        # Ajuster les colonnes
        for i in range(self.devices_tree.columnCount()):
            self.devices_tree.resizeColumnToContents(i)
            
    def _on_item_changed(self, item, column):
        """Gérer les changements de sélection"""
        if column == 0:  # Colonne checkbox
            self.devices_selection_changed.emit()
            
    def _select_all(self):
        """Sélectionner tous les appareils"""
        self._set_all_checkboxes(Qt.Checked)
        
    def _select_none(self):
        """Désélectionner tous les appareils"""
        self._set_all_checkboxes(Qt.Unchecked)
        
    def _set_all_checkboxes(self, state):
        """Définir l'état de toutes les checkboxes"""
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                device_item.setCheckState(0, state)
                
    def _auto_select_oldest(self):
        """Sélectionner automatiquement les plus anciens appareils (ID plus petits)"""
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            
            # Trouver l'appareil avec l'ID le plus petit (plus ancien)
            oldest_item = None
            oldest_id = float('inf')
            
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                device_id = device_item.data(0, Qt.UserRole)
                if device_id < oldest_id:
                    oldest_id = device_id
                    oldest_item = device_item
                    
            # Sélectionner tous sauf le plus ancien
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                if device_item == oldest_item:
                    device_item.setCheckState(0, Qt.Unchecked)  # Garder le plus ancien
                else:
                    device_item.setCheckState(0, Qt.Checked)    # Supprimer les autres
                    
    def _auto_select_complete(self):
        """Sélectionner automatiquement en gardant les appareils les plus complets"""
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            
            # Trouver l'appareil le plus complet
            best_item = None
            best_score = -1
            
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                
                # Calculer un score de complétude
                score = 0
                if device_item.text(3):  # type_appareil
                    score += 1
                if device_item.text(4):  # manufacturer
                    score += 1
                if device_item.text(5):  # commercial_ref
                    score += 1
                if device_item.text(6):  # designation
                    score += 1
                pieces_count = int(device_item.text(7) or 0)
                score += min(pieces_count / 10, 1)  # Bonus pour le nombre de pièces
                
                if score > best_score:
                    best_score = score
                    best_item = device_item
                    
            # Sélectionner tous sauf le meilleur
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                if device_item == best_item:
                    device_item.setCheckState(0, Qt.Unchecked)  # Garder le meilleur
                else:
                    device_item.setCheckState(0, Qt.Checked)    # Supprimer les autres
                    
    def get_selected_devices(self) -> List[int]:
        """Obtenir les IDs des appareils sélectionnés pour suppression"""
        selected = []
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                if device_item.checkState(0) == Qt.Checked:
                    device_id = device_item.data(0, Qt.UserRole)
                    selected.append(device_id)
        return selected
        
    def get_merge_groups(self) -> List[Dict[str, Any]]:
        """Obtenir les groupes de fusion d'appareils"""
        merge_groups = []
        root = self.devices_tree.invisibleRootItem()
        
        for i in range(root.childCount()):
            group_item = root.child(i)
            group_devices = []
            selected_devices = []
            
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                device_id = device_item.data(0, Qt.UserRole)
                group_devices.append(device_id)
                
                if device_item.checkState(0) == Qt.Checked:
                    selected_devices.append(device_id)
                    
            # S'il y a des appareils sélectionnés, créer un groupe de fusion
            if selected_devices:
                # Le maître est celui qui n'est pas sélectionné (ou le premier non sélectionné)
                master_candidates = [d for d in group_devices if d not in selected_devices]
                if master_candidates:
                    master_id = master_candidates[0]
                    merge_groups.append({
                        'master_id': master_id,
                        'duplicate_ids': selected_devices
                    })
                    
        return merge_groups


class DuplicatePiecesWidget(QWidget):
    """Widget pour gérer les pièces dupliquées"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.duplicate_pieces = []
        self.init_ui()
        
    def init_ui(self):
        """Initialiser l'interface pour les pièces dupliquées"""
        layout = QVBoxLayout(self)
        
        # Actions
        actions_layout = QHBoxLayout()
        self.select_all_pieces_btn = QPushButton("Tout sélectionner")
        self.select_none_pieces_btn = QPushButton("Tout désélectionner")
        
        actions_layout.addWidget(self.select_all_pieces_btn)
        actions_layout.addWidget(self.select_none_pieces_btn)
        actions_layout.addStretch()
        
        layout.addLayout(actions_layout)
        
        # Table des pièces
        self.pieces_table = QTableWidget()
        self.pieces_table.setColumnCount(3)
        self.pieces_table.setHorizontalHeaderLabels(["Supprimer", "Référence Pièce", "Nombre de doublons"])
        self.pieces_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(self.pieces_table)
        
        # Connecter les signaux
        self.select_all_pieces_btn.clicked.connect(self._select_all_pieces)
        self.select_none_pieces_btn.clicked.connect(self._select_none_pieces)
        
    def populate_pieces(self, duplicate_pieces: List[Dict[str, Any]]):
        """Remplir la table des pièces dupliquées"""
        self.duplicate_pieces = duplicate_pieces
        self.pieces_table.setRowCount(len(duplicate_pieces))
        
        for row, piece_data in enumerate(duplicate_pieces):
            ref_piece = piece_data['ref_piece']
            count = piece_data['count']
            
            # Checkbox
            checkbox = QCheckBox()
            self.pieces_table.setCellWidget(row, 0, checkbox)
            
            # Référence pièce
            ref_item = QTableWidgetItem(ref_piece)
            ref_item.setFlags(ref_item.flags() & ~Qt.ItemIsEditable)
            self.pieces_table.setItem(row, 1, ref_item)
            
            # Nombre de doublons
            count_item = QTableWidgetItem(str(count))
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.pieces_table.setItem(row, 2, count_item)
            
        self.pieces_table.resizeColumnsToContents()
        
    def _select_all_pieces(self):
        """Sélectionner toutes les pièces"""
        for row in range(self.pieces_table.rowCount()):
            checkbox = self.pieces_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(True)
                
    def _select_none_pieces(self):
        """Désélectionner toutes les pièces"""
        for row in range(self.pieces_table.rowCount()):
            checkbox = self.pieces_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(False)
                
    def get_selected_pieces(self) -> List[str]:
        """Obtenir les références des pièces sélectionnées"""
        selected = []
        for row in range(self.pieces_table.rowCount()):
            checkbox = self.pieces_table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                ref_item = self.pieces_table.item(row, 1)
                if ref_item:
                    selected.append(ref_item.text())
        return selected


class CleanupUIService(QObject):
    """Service d'interface utilisateur pour le nettoyage des doublons"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def create_stats_widget(self) -> CleanupStatsWidget:
        """Créer le widget des statistiques"""
        return CleanupStatsWidget()
        
    def create_devices_widget(self) -> DuplicateDevicesWidget:
        """Créer le widget des appareils en doublon"""
        return DuplicateDevicesWidget()
        
    def create_pieces_widget(self) -> DuplicatePiecesWidget:
        """Créer le widget des pièces dupliquées"""
        return DuplicatePiecesWidget()
        
    def create_progress_widget(self) -> Dict[str, QWidget]:
        """Créer les widgets de progression"""
        widgets = {}
        
        # Label de titre
        widgets['title'] = QLabel("🔍 Analyse des doublons en cours...")
        widgets['title'].setStyleSheet("font-size: 18px; font-weight: bold; color: #007bff; padding: 10px;")
        
        # Barre de progression
        widgets['progress_bar'] = QProgressBar()
        widgets['progress_bar'].setRange(0, 100)
        widgets['progress_bar'].setValue(0)
        
        # Label de statut
        widgets['status'] = QLabel("Initialisation de l'analyse...")
        widgets['status'].setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        
        return widgets
        
    def update_progress(self, widgets: Dict[str, QWidget], progress: int, message: str):
        """Mettre à jour l'affichage de progression"""
        if 'progress_bar' in widgets:
            widgets['progress_bar'].setValue(progress)
        if 'status' in widgets:
            widgets['status'].setText(message)
        if 'title' in widgets and progress == 100:
            widgets['title'].setText("✅ Analyse terminée - Résultats disponibles")
            
    def show_analysis_error(self, widgets: Dict[str, QWidget], error_message: str):
        """Afficher une erreur d'analyse"""
        if 'title' in widgets:
            widgets['title'].setText("❌ Erreur lors de l'analyse")
            widgets['title'].setStyleSheet("font-size: 18px; font-weight: bold; color: #dc3545; padding: 10px;")
        if 'status' in widgets:
            widgets['status'].setText(f"Erreur: {error_message}")
            widgets['status'].setStyleSheet("color: #dc3545; font-style: italic; padding: 5px;")
        if 'progress_bar' in widgets:
            widgets['progress_bar'].setVisible(False)