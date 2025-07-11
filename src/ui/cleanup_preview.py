"""
Fenêtre de prévisualisation du nettoyage des doublons
"""

import re
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter, QTextEdit,
    QGroupBox, QTabWidget, QWidget, QProgressBar, QCheckBox, QTreeWidget,
    QTreeWidgetItem, QApplication
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


def clean_display_text(text):
    """Nettoie le texte pour l'affichage en supprimant les caractères illisibles"""
    if not text:
        return ""
    text = str(text)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    try:
        text = text.encode('utf-8', errors='replace').decode('utf-8')
    except:
        text = "???"
    text = re.sub(r'\s+', ' ', text)
    return text.strip()




class CleanupPreviewDialog(QDialog):
    """Fenêtre de prévisualisation du nettoyage des doublons"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("🧹 Prévisualisation du Nettoyage des Doublons")
        self.resize(1400, 900)
        self.setModal(True)
        
        # Données d'analyse
        self.analysis_data = None
        self.user_choice = None
        
        self._init_ui()
        
        # Démarrer l'analyse avec un délai pour permettre l'affichage de la fenêtre
        QTimer.singleShot(100, self._start_analysis)
    
    def _init_ui(self):
        """Initialiser l'interface"""
        layout = QVBoxLayout(self)
        
        # En-tête avec titre et progression
        header_layout = QVBoxLayout()
        
        title_label = QLabel("🔍 Analyse des doublons en cours...")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #007bff; padding: 10px;")
        header_layout.addWidget(title_label)
        self.title_label = title_label
        
        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(True)
        header_layout.addWidget(self.progress_bar)
        
        layout.addLayout(header_layout)
        
        # Zone principale (masquée pendant l'analyse)
        self.main_widget = QWidget()
        self.main_widget.setVisible(False)
        main_layout = QVBoxLayout(self.main_widget)
        
        # Statistiques en haut
        self.stats_widget = self._create_stats_widget()
        main_layout.addWidget(self.stats_widget)
        
        # Onglets pour les différents types de nettoyage
        self.tab_widget = QTabWidget()
        
        # Onglet Appareils en doublon
        self.devices_tab = self._create_devices_tab()
        self.tab_widget.addTab(self.devices_tab, "📱 Appareils en doublon")
        
        # Onglet Pièces dupliquées
        self.pieces_tab = self._create_pieces_tab()
        self.tab_widget.addTab(self.pieces_tab, "🔧 Pièces dupliquées")
        
        # Onglet Doublons de références
        self.inconsistencies_tab = self._create_inconsistencies_tab()
        self.tab_widget.addTab(self.inconsistencies_tab, "📋 Doublons références")
        
        main_layout.addWidget(self.tab_widget)
        
        layout.addWidget(self.main_widget)
        
        # Boutons d'action
        self.buttons_layout = QHBoxLayout()
        
        # Options de nettoyage
        self.clean_devices_cb = QCheckBox("Nettoyer les appareils en doublon")
        self.clean_devices_cb.setChecked(True)
        self.buttons_layout.addWidget(self.clean_devices_cb)
        
        self.clean_pieces_cb = QCheckBox("Nettoyer les pièces dupliquées")
        self.clean_pieces_cb.setChecked(True)
        self.buttons_layout.addWidget(self.clean_pieces_cb)
        
        self.clean_inconsistencies_cb = QCheckBox("Fusionner les doublons de références")
        self.clean_inconsistencies_cb.setChecked(False)  # Se cochera automatiquement lors d'une sélection
        self.buttons_layout.addWidget(self.clean_inconsistencies_cb)
        
        self.buttons_layout.addStretch()
        
        # Boutons principaux
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.reject)
        self.buttons_layout.addWidget(self.cancel_btn)
        
        self.proceed_btn = QPushButton("🧹 Procéder au nettoyage")
        self.proceed_btn.clicked.connect(self.accept)
        self.proceed_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 8px;")
        self.proceed_btn.setEnabled(False)
        self.buttons_layout.addWidget(self.proceed_btn)
        
        layout.addLayout(self.buttons_layout)
    
    def _create_stats_widget(self):
        """Créer le widget des statistiques"""
        group_box = QGroupBox("📊 Résumé du nettoyage")
        layout = QHBoxLayout(group_box)
        
        self.devices_stat = QLabel("0 appareils à supprimer")
        self.devices_stat.setStyleSheet("font-size: 14px; font-weight: bold; color: #dc3545;")
        layout.addWidget(self.devices_stat)
        
        self.pieces_stat = QLabel("0 pièces à transférer")
        self.pieces_stat.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffc107;")
        layout.addWidget(self.pieces_stat)
        
        self.groups_stat = QLabel("0 groupes de doublons")
        self.groups_stat.setStyleSheet("font-size: 14px; font-weight: bold; color: #007bff;")
        layout.addWidget(self.groups_stat)
        
        self.inconsistencies_stat = QLabel("0 doublons de références")
        self.inconsistencies_stat.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff8c00;")
        layout.addWidget(self.inconsistencies_stat)
        
        return group_box
    
    def _create_devices_tab(self):
        """Créer l'onglet des appareils en doublon"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Description
        desc_label = QLabel("Groupes d'appareils identiques. Le plus ancien sera conservé, les autres supprimés.")
        desc_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        layout.addWidget(desc_label)
        
        # Tableau des groupes d'appareils
        self.devices_table = QTableWidget()
        self.devices_table.setColumnCount(7)
        self.devices_table.setHorizontalHeaderLabels([
            "Type", "Fabricant", "Ref Modèle", "Ref Comm.", "ID Conservé", "IDs Supprimés", "Pièces à transférer"
        ])
        
        # Configuration
        header = self.devices_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        
        self.devices_table.setAlternatingRowColors(True)
        self.devices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        layout.addWidget(self.devices_table)
        
        return widget
    
    def _create_pieces_tab(self):
        """Créer l'onglet des pièces dupliquées"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Description
        desc_label = QLabel("Pièces référencées plusieurs fois pour le même appareil. Les doublons seront supprimés.")
        desc_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        layout.addWidget(desc_label)
        
        # Tableau des pièces dupliquées
        self.pieces_table = QTableWidget()
        self.pieces_table.setColumnCount(6)
        self.pieces_table.setHorizontalHeaderLabels([
            "ID Appareil", "Type", "Fabricant", "Ref Modèle", "Référence Pièce", "Doublons à supprimer"
        ])
        
        # Configuration
        header = self.pieces_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        self.pieces_table.setAlternatingRowColors(True)
        self.pieces_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        layout.addWidget(self.pieces_table)
        
        return widget
    
    def _create_inconsistencies_tab(self):
        """Créer l'onglet des doublons de références"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Description
        desc_label = QLabel("Références modèles identiques (colonne C). L'appareil le plus ancien fait office de référence principale. Cochez l'appareil à utiliser comme base de fusion et modifiez les données si nécessaire.")
        desc_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        layout.addWidget(desc_label)
        
        # Arbre hiérarchique des doublons de références
        self.inconsistencies_tree = QTreeWidget()
        self.inconsistencies_tree.setHeaderLabels([
            "📋 Fusion", "ID", "Type", "Fabricant", "Ref Modèle", "Ref Comm.", "Autre Ref", "Catégorie", "Notes"
        ])
        
        # Configuration de l'arbre
        header = self.inconsistencies_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Checkbox
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # Type
        header.setSectionResizeMode(3, QHeaderView.Stretch)           # Fabricant
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # Ref Modèle
        header.setSectionResizeMode(5, QHeaderView.Stretch)           # Ref Comm
        header.setSectionResizeMode(6, QHeaderView.Stretch)           # Autre Ref
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Catégorie
        header.setSectionResizeMode(8, QHeaderView.Stretch)           # Notes
        
        # Permettre l'édition des cellules
        self.inconsistencies_tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.inconsistencies_tree.setAlternatingRowColors(True)
        self.inconsistencies_tree.setRootIsDecorated(True)
        self.inconsistencies_tree.setItemsExpandable(True)
        
        # Configurer le clic droit pour copier directement les valeurs
        self.inconsistencies_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.inconsistencies_tree.customContextMenuRequested.connect(self._copy_cell_on_right_click)
        
        layout.addWidget(self.inconsistencies_tree)
        
        # Boutons d'action pour les doublons
        inconsistencies_actions = QHBoxLayout()
        
        self.expand_all_btn = QPushButton("📂 Tout développer")
        self.expand_all_btn.clicked.connect(self.inconsistencies_tree.expandAll)
        inconsistencies_actions.addWidget(self.expand_all_btn)
        
        self.collapse_all_btn = QPushButton("📁 Tout réduire")
        self.collapse_all_btn.clicked.connect(self.inconsistencies_tree.collapseAll)
        inconsistencies_actions.addWidget(self.collapse_all_btn)
        
        self.auto_select_oldest_btn = QPushButton("⏰ Auto: sélectionner les plus anciens")
        self.auto_select_oldest_btn.clicked.connect(self._auto_select_oldest_masters)
        inconsistencies_actions.addWidget(self.auto_select_oldest_btn)
        
        self.auto_select_complete_btn = QPushButton("✅ Auto: sélectionner les plus complets")
        self.auto_select_complete_btn.clicked.connect(self._auto_select_complete_masters)
        inconsistencies_actions.addWidget(self.auto_select_complete_btn)
        
        inconsistencies_actions.addStretch()
        layout.addLayout(inconsistencies_actions)
        
        # Connecter les événements
        self.inconsistencies_tree.itemChanged.connect(self._on_tree_item_changed)
        
        return widget
    
    def _start_analysis(self):
        """Démarrer l'analyse des doublons dans le thread principal"""
        try:
            self.progress_bar.setValue(10)
            
            # Analyser les doublons directement (thread principal)
            analysis_result = {
                'device_groups': [],
                'piece_duplicates': [],
                'inconsistencies': [],
                'statistics': {
                    'total_devices_to_delete': 0,
                    'total_pieces_to_transfer': 0,
                    'total_duplicate_pieces': 0,
                    'groups_count': 0,
                    'inconsistencies_count': 0
                }
            }
            
            # 1. Analyser les doublons d'appareils
            duplicates_query = """
                SELECT type, manufacturer, ref_modele, commercial_ref, other_ref, 
                       GROUP_CONCAT(id || '|' || COALESCE(notes, '')) as devices_info, 
                       MIN(id) as keep_id, COUNT(*) as count
                FROM appareils 
                GROUP BY type, manufacturer, ref_modele, commercial_ref, other_ref 
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """
            
            device_duplicates = self.parent_window.db_manager.execute_custom_query(duplicates_query)
            self.progress_bar.setValue(40)
            
            groups_count = 0
            total_devices_to_delete = 0
            
            for row in device_duplicates:
                type_val, manufacturer, ref_modele, commercial_ref, other_ref, devices_info, keep_id, count = row
                
                # Parser les informations des appareils
                devices_list = []
                if devices_info:
                    for device_str in devices_info.split(','):
                        if '|' in device_str:
                            device_id, notes = device_str.split('|', 1)
                            devices_list.append({
                                'id': int(device_id),
                                'notes': notes or '',
                                'will_keep': int(device_id) == keep_id
                            })
                
                # Compter les pièces à transférer pour ce groupe
                pieces_to_transfer = 0
                for device in devices_list:
                    if not device['will_keep']:
                        pieces_query = "SELECT COUNT(*) FROM pieces WHERE appareil_id = ?"
                        result = self.parent_window.db_manager.execute_custom_query(pieces_query, [device['id']])
                        if result:
                            pieces_to_transfer += result[0][0]
                
                group_info = {
                    'type': clean_display_text(type_val),
                    'manufacturer': clean_display_text(manufacturer),
                    'ref_modele': clean_display_text(ref_modele),
                    'commercial_ref': clean_display_text(commercial_ref),
                    'other_ref': clean_display_text(other_ref),
                    'devices': devices_list,
                    'keep_id': keep_id,
                    'pieces_to_transfer': pieces_to_transfer
                }
                
                analysis_result['device_groups'].append(group_info)
                groups_count += 1
                total_devices_to_delete += count - 1  # Tous sauf celui qu'on garde
                analysis_result['statistics']['total_pieces_to_transfer'] += pieces_to_transfer
            
            self.progress_bar.setValue(50)
            
            # 2. Analyser les doublons de ref_modele (même logique que la validation)
            inconsistencies_query = """
                SELECT ref_modele, COUNT(*) as count,
                       GROUP_CONCAT(id || '|' || COALESCE(type, '') || '|' || COALESCE(manufacturer, '') || '|' || COALESCE(commercial_ref, '') || '|' || COALESCE(other_ref, '')) as devices_info
                FROM appareils 
                WHERE ref_modele IS NOT NULL AND ref_modele != ''
                GROUP BY ref_modele 
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """
            
            inconsistencies = self.parent_window.db_manager.execute_custom_query(inconsistencies_query)
            inconsistencies_count = 0
            
            for row in inconsistencies:
                ref_modele, count, devices_info = row
                
                # Parser les informations des appareils
                devices_list = []
                if devices_info:
                    for device_str in devices_info.split(','):
                        parts = device_str.split('|')
                        if len(parts) >= 5:
                            device_id, type_val, manufacturer, commercial_ref, other_ref = parts[:5]
                            devices_list.append({
                                'id': int(device_id),
                                'type': clean_display_text(type_val),
                                'manufacturer': clean_display_text(manufacturer),
                                'commercial_ref': clean_display_text(commercial_ref),
                                'other_ref': clean_display_text(other_ref),
                                'is_master': False  # À définir par l'utilisateur
                            })
                
                if len(devices_list) > 1:  # Seulement s'il y a vraiment des doublons
                    inconsistency_info = {
                        'ref_modele': clean_display_text(ref_modele),
                        'variants_count': count,  # Nombre total d'appareils (pas variantes)
                        'devices': devices_list,
                        'master_id': None  # À définir par l'utilisateur
                    }
                    
                    analysis_result['inconsistencies'].append(inconsistency_info)
                    inconsistencies_count += 1
            
            self.progress_bar.setValue(70)
            
            # 3. Analyser les doublons de pièces
            piece_duplicates_query = """
                SELECT appareil_id, ref_piece, COUNT(*) as count, GROUP_CONCAT(id) as piece_ids
                FROM pieces 
                GROUP BY appareil_id, ref_piece 
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """
            
            piece_duplicates = self.parent_window.db_manager.execute_custom_query(piece_duplicates_query)
            total_duplicate_pieces = 0
            
            for row in piece_duplicates:
                appareil_id, ref_piece, count, piece_ids = row
                
                # Récupérer les infos de l'appareil
                device_query = "SELECT type, manufacturer, ref_modele FROM appareils WHERE id = ?"
                device_info = self.parent_window.db_manager.execute_custom_query(device_query, [appareil_id])
                
                device_type = device_manufacturer = device_ref = ""
                if device_info:
                    device_type, device_manufacturer, device_ref = device_info[0]
                
                piece_info = {
                    'appareil_id': appareil_id,
                    'device_type': clean_display_text(device_type),
                    'device_manufacturer': clean_display_text(device_manufacturer),
                    'device_ref': clean_display_text(device_ref),
                    'ref_piece': clean_display_text(ref_piece),
                    'count': count,
                    'pieces_to_delete': count - 1
                }
                
                analysis_result['piece_duplicates'].append(piece_info)
                total_duplicate_pieces += count - 1  # Tous sauf un
            
            self.progress_bar.setValue(90)
            
            # 4. Finaliser les statistiques
            analysis_result['statistics'].update({
                'total_devices_to_delete': total_devices_to_delete,
                'total_duplicate_pieces': total_duplicate_pieces,
                'groups_count': groups_count,
                'inconsistencies_count': inconsistencies_count
            })
            
            self.progress_bar.setValue(100)
            self._on_analysis_completed(analysis_result)
            
        except Exception as e:
            self._on_analysis_error(f"Erreur lors de l'analyse: {e}")
    
    def _on_analysis_completed(self, analysis_data):
        """Traiter les résultats de l'analyse"""
        self.analysis_data = analysis_data
        
        # Masquer la progression et afficher les résultats
        self.progress_bar.setVisible(False)
        self.title_label.setText("🔍 Aperçu des opérations de nettoyage")
        self.main_widget.setVisible(True)
        
        # Mettre à jour les statistiques
        stats = analysis_data['statistics']
        self.devices_stat.setText(f"{stats['total_devices_to_delete']} appareils à supprimer")
        self.pieces_stat.setText(f"{stats['total_pieces_to_transfer']} pièces à transférer")
        self.groups_stat.setText(f"{stats['groups_count']} groupes de doublons")
        self.inconsistencies_stat.setText(f"{stats['inconsistencies_count']} doublons de références")
        
        # Remplir les tableaux
        self._populate_devices_table()
        self._populate_pieces_table()
        self._populate_inconsistencies_table()
        
        # Activer le bouton de validation
        self.proceed_btn.setEnabled(True)
        
        # Mettre à jour le message selon les résultats
        if stats['total_devices_to_delete'] == 0 and stats['total_duplicate_pieces'] == 0 and stats['inconsistencies_count'] == 0:
            self.title_label.setText("✅ Aucun doublon trouvé !")
            self.proceed_btn.setText("Fermer")
            self.proceed_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 8px;")
    
    def _populate_devices_table(self):
        """Remplir le tableau des appareils en doublon"""
        device_groups = self.analysis_data['device_groups']
        self.devices_table.setRowCount(len(device_groups))
        
        for row, group in enumerate(device_groups):
            self.devices_table.setItem(row, 0, QTableWidgetItem(group['type']))
            self.devices_table.setItem(row, 1, QTableWidgetItem(group['manufacturer']))
            self.devices_table.setItem(row, 2, QTableWidgetItem(group['ref_modele']))
            self.devices_table.setItem(row, 3, QTableWidgetItem(group['commercial_ref']))
            
            # ID conservé
            keep_item = QTableWidgetItem(str(group['keep_id']))
            keep_item.setBackground(Qt.green)
            keep_item.setForeground(Qt.white)
            self.devices_table.setItem(row, 4, keep_item)
            
            # IDs supprimés
            delete_ids = [str(device['id']) for device in group['devices'] if not device['will_keep']]
            delete_item = QTableWidgetItem(", ".join(delete_ids))
            delete_item.setBackground(Qt.red)
            delete_item.setForeground(Qt.white)
            self.devices_table.setItem(row, 5, delete_item)
            
            # Pièces à transférer
            pieces_item = QTableWidgetItem(str(group['pieces_to_transfer']))
            pieces_item.setTextAlignment(Qt.AlignCenter)
            if group['pieces_to_transfer'] > 0:
                pieces_item.setBackground(Qt.yellow)
            self.devices_table.setItem(row, 6, pieces_item)
    
    def _populate_pieces_table(self):
        """Remplir le tableau des pièces dupliquées"""
        piece_duplicates = self.analysis_data['piece_duplicates']
        self.pieces_table.setRowCount(len(piece_duplicates))
        
        for row, piece in enumerate(piece_duplicates):
            self.pieces_table.setItem(row, 0, QTableWidgetItem(str(piece['appareil_id'])))
            self.pieces_table.setItem(row, 1, QTableWidgetItem(piece['device_type']))
            self.pieces_table.setItem(row, 2, QTableWidgetItem(piece['device_manufacturer']))
            self.pieces_table.setItem(row, 3, QTableWidgetItem(piece['device_ref']))
            self.pieces_table.setItem(row, 4, QTableWidgetItem(piece['ref_piece']))
            
            # Nombre de doublons à supprimer
            delete_item = QTableWidgetItem(str(piece['pieces_to_delete']))
            delete_item.setTextAlignment(Qt.AlignCenter)
            delete_item.setBackground(Qt.red)
            delete_item.setForeground(Qt.white)
            self.pieces_table.setItem(row, 5, delete_item)
    
    def _populate_inconsistencies_table(self):
        """Remplir l'arbre hiérarchique des doublons de références"""
        inconsistencies = self.analysis_data['inconsistencies']
        self.inconsistencies_tree.clear()
        
        for inconsistency in inconsistencies:
            ref_modele = inconsistency['ref_modele']
            devices = inconsistency['devices']
            
            # Trier les appareils par ID (plus ancien en premier)
            devices_sorted = sorted(devices, key=lambda d: d['id'])
            
            # Créer l'élément parent (référence principale - plus ancien)
            oldest_device = devices_sorted[0]
            parent_item = QTreeWidgetItem([
                "",  # Checkbox sera ajoutée programmatiquement
                str(oldest_device['id']),
                oldest_device['type'],
                oldest_device['manufacturer'],
                ref_modele,
                oldest_device['commercial_ref'],
                oldest_device['other_ref'],
                "", # Catégorie - à récupérer de la base
                ""  # Notes - à récupérer de la base
            ])
            
            # Marquer comme référence principale
            parent_item.setBackground(0, Qt.lightGray)
            parent_item.setBackground(1, Qt.lightGray)
            parent_item.setText(0, "🏆 Référence")
            parent_item.setFont(0, QFont("", -1, QFont.Bold))
            parent_item.setFont(1, QFont("", -1, QFont.Bold))
            
            # Rendre les cellules éditables (sauf ID et checkbox)
            for col in range(2, 9):
                parent_item.setFlags(parent_item.flags() | Qt.ItemIsEditable)
            
            # Stocker les données de l'appareil
            parent_item.setData(0, Qt.UserRole, {
                'device_data': oldest_device,
                'is_master': False,  # Aucune sélection par défaut
                'ref_modele': ref_modele,
                'group_size': len(devices)
            })
            
            # Ajouter une checkbox pour sélectionner comme base de fusion
            parent_item.setCheckState(0, Qt.Unchecked)  # Aucune sélection par défaut
            
            self.inconsistencies_tree.addTopLevelItem(parent_item)
            
            # Ajouter les autres appareils comme enfants
            for device in devices_sorted[1:]:
                child_item = QTreeWidgetItem([
                    "",  # Checkbox
                    str(device['id']),
                    device['type'],
                    device['manufacturer'],
                    ref_modele,
                    device['commercial_ref'],
                    device['other_ref'],
                    "", # Catégorie
                    ""  # Notes
                ])
                
                # Marquer comme doublon
                child_item.setBackground(0, Qt.yellow)
                child_item.setText(0, "📋 Doublon")
                
                # Rendre les cellules éditables (sauf ID et checkbox)
                for col in range(2, 9):
                    child_item.setFlags(child_item.flags() | Qt.ItemIsEditable)
                
                # Stocker les données
                child_item.setData(0, Qt.UserRole, {
                    'device_data': device,
                    'is_master': False,
                    'ref_modele': ref_modele,
                    'parent_id': oldest_device['id']
                })
                
                # Ajouter une checkbox
                child_item.setCheckState(0, Qt.Unchecked)
                
                parent_item.addChild(child_item)
            
            # Développer le groupe par défaut
            parent_item.setExpanded(True)
        
        # Récupérer les données complètes (catégorie, notes) pour tous les appareils
        self._load_complete_device_data()
    
    def _load_complete_device_data(self):
        """Charger les données complètes (catégorie, notes) pour tous les appareils"""
        try:
            # Parcourir tous les éléments de l'arbre
            for i in range(self.inconsistencies_tree.topLevelItemCount()):
                parent_item = self.inconsistencies_tree.topLevelItem(i)
                
                # Charger les données du parent
                self._load_item_complete_data(parent_item)
                
                # Charger les données des enfants
                for j in range(parent_item.childCount()):
                    child_item = parent_item.child(j)
                    self._load_item_complete_data(child_item)
                    
        except Exception as e:
            print(f"Erreur lors du chargement des données complètes: {e}")
    
    def _load_item_complete_data(self, item):
        """Charger les données complètes pour un élément"""
        try:
            user_data = item.data(0, Qt.UserRole)
            if user_data and 'device_data' in user_data:
                device_id = user_data['device_data']['id']
                
                # Requête pour récupérer toutes les données
                query = "SELECT category, notes FROM appareils WHERE id = ?"
                result = self.parent_window.db_manager.execute_custom_query(query, [device_id])
                
                if result:
                    category, notes = result[0]
                    item.setText(7, clean_display_text(category) if category else "")
                    item.setText(8, clean_display_text(notes) if notes else "")
                    
        except Exception as e:
            print(f"Erreur lors du chargement des données pour l'appareil: {e}")
    
    def _on_tree_item_changed(self, item, column):
        """Gérer les changements dans l'arbre (checkbox et édition)"""
        try:
            if column == 0:  # Checkbox changée
                self._handle_checkbox_change(item)
            else:  # Contenu de cellule modifié
                self._handle_cell_edit(item, column)
                
        except Exception as e:
            print(f"Erreur lors du traitement du changement: {e}")
    
    def _handle_checkbox_change(self, item):
        """Gérer le changement de checkbox"""
        user_data = item.data(0, Qt.UserRole)
        if not user_data:
            return
        
        is_checked = item.checkState(0) == Qt.Checked
        user_data['is_master'] = is_checked
        
        
        # Si c'est un enfant qui est coché, décocher les autres enfants du même groupe
        parent = item.parent()
        if parent:
            # Décocher les autres enfants
            for i in range(parent.childCount()):
                sibling = parent.child(i)
                if sibling != item and sibling.checkState(0) == Qt.Checked:
                    sibling.setCheckState(0, Qt.Unchecked)
                    sibling_data = sibling.data(0, Qt.UserRole)
                    if sibling_data:
                        sibling_data['is_master'] = False
            
            # Décocher le parent si un enfant est sélectionné
            if is_checked:
                parent.setCheckState(0, Qt.Unchecked)
                parent_data = parent.data(0, Qt.UserRole)
                if parent_data:
                    parent_data['is_master'] = False
        else:
            # Si c'est un parent qui est coché, décocher tous ses enfants
            if is_checked:
                for i in range(item.childCount()):
                    child = item.child(i)
                    child.setCheckState(0, Qt.Unchecked)
                    child_data = child.data(0, Qt.UserRole)
                    if child_data:
                        child_data['is_master'] = False
        
        # Cocher automatiquement la checkbox de fusion si une sélection est faite
        self._update_fusion_checkbox()
    
    def _update_fusion_checkbox(self):
        """Mettre à jour la checkbox de fusion selon les sélections"""
        has_selection = False
        selected_count = 0
        
        # Vérifier s'il y a au moins une sélection dans l'arbre
        for i in range(self.inconsistencies_tree.topLevelItemCount()):
            parent_item = self.inconsistencies_tree.topLevelItem(i)
            
            # Vérifier le parent (utiliser l'état réel de la checkbox)
            if parent_item.checkState(0) == Qt.Checked:
                has_selection = True
                selected_count += 1
            
            # Vérifier les enfants (utiliser l'état réel des checkboxes)
            for j in range(parent_item.childCount()):
                child_item = parent_item.child(j)
                if child_item.checkState(0) == Qt.Checked:
                    has_selection = True
                    selected_count += 1
        
        # Cocher ou décocher la checkbox selon les sélections
        self.clean_inconsistencies_cb.setChecked(has_selection)
    
    def _handle_cell_edit(self, item, column):
        """Gérer l'édition d'une cellule"""
        user_data = item.data(0, Qt.UserRole)
        if not user_data or 'device_data' not in user_data:
            return
        
        # Marquer que les données ont été modifiées
        user_data['modified'] = True
        
        # Mettre à jour les données du device selon la colonne
        device_data = user_data['device_data']
        new_value = item.text(column)
        
        column_mapping = {
            2: 'type',
            3: 'manufacturer', 
            4: 'ref_modele',
            5: 'commercial_ref',
            6: 'other_ref',
            7: 'category',
            8: 'notes'
        }
        
        if column in column_mapping:
            device_data[column_mapping[column]] = new_value
            print(f"Mise à jour: {column_mapping[column]} = '{new_value}' pour l'appareil ID {device_data['id']}")
    
    def _update_inconsistencies_buttons(self):
        """Cette méthode n'est plus nécessaire avec la nouvelle interface"""
        pass
    
    
    def _auto_select_oldest_masters(self):
        """Sélectionner automatiquement les appareils les plus anciens comme maîtres"""
        for i in range(self.inconsistencies_tree.topLevelItemCount()):
            parent_item = self.inconsistencies_tree.topLevelItem(i)
            
            # Le parent est déjà le plus ancien par défaut, donc le cocher
            parent_item.setCheckState(0, Qt.Checked)
            parent_data = parent_item.data(0, Qt.UserRole)
            if parent_data:
                parent_data['is_master'] = True
            
            # Décocher tous les enfants
            for j in range(parent_item.childCount()):
                child = parent_item.child(j)
                child.setCheckState(0, Qt.Unchecked)
                child_data = child.data(0, Qt.UserRole)
                if child_data:
                    child_data['is_master'] = False
        
        # Mettre à jour la checkbox de fusion
        self._update_fusion_checkbox()
    
    def _auto_select_complete_masters(self):
        """Sélectionner automatiquement les appareils les plus complets comme maîtres"""
        for i in range(self.inconsistencies_tree.topLevelItemCount()):
            parent_item = self.inconsistencies_tree.topLevelItem(i)
            
            # Évaluer tous les appareils du groupe (parent + enfants)
            all_items = [parent_item]
            for j in range(parent_item.childCount()):
                all_items.append(parent_item.child(j))
            
            best_item = None
            best_score = -1
            best_id = float('inf')
            
            for item in all_items:
                user_data = item.data(0, Qt.UserRole)
                if not user_data or 'device_data' not in user_data:
                    continue
                
                device_data = user_data['device_data']
                
                # Calculer le score de complétude
                score = 0
                if device_data.get('type', '').strip():
                    score += 1
                if device_data.get('manufacturer', '').strip():
                    score += 1
                if device_data.get('commercial_ref', '').strip():
                    score += 1
                if device_data.get('other_ref', '').strip():
                    score += 1
                
                # En cas d'égalité, préférer l'ID le plus bas (plus ancien)
                device_id = device_data['id']
                if score > best_score or (score == best_score and device_id < best_id):
                    best_score = score
                    best_id = device_id
                    best_item = item
            
            if best_item:
                # Décocher tous les éléments du groupe
                for item in all_items:
                    item.setCheckState(0, Qt.Unchecked)
                    item_data = item.data(0, Qt.UserRole)
                    if item_data:
                        item_data['is_master'] = False
                
                # Cocher le meilleur élément
                best_item.setCheckState(0, Qt.Checked)
                best_data = best_item.data(0, Qt.UserRole)
                if best_data:
                    best_data['is_master'] = True
        
        # Mettre à jour la checkbox de fusion
        self._update_fusion_checkbox()
    
    def _on_analysis_error(self, error_message):
        """Gérer les erreurs d'analyse"""
        self.progress_bar.setVisible(False)
        self.title_label.setText("❌ Erreur lors de l'analyse")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #dc3545; padding: 10px;")
        
        error_label = QLabel(f"Erreur: {error_message}")
        error_label.setStyleSheet("color: #dc3545; padding: 20px;")
        self.layout().addWidget(error_label)
        
        self.proceed_btn.setText("Fermer")
        self.proceed_btn.setEnabled(True)
    
    def _copy_cell_on_right_click(self, position):
        """Copier directement la valeur de la cellule sous le clic droit"""
        # Vérifier qu'on a cliqué sur un élément valide
        item = self.inconsistencies_tree.itemAt(position)
        if not item:
            return
        
        # Obtenir la colonne cliquée
        column = self.inconsistencies_tree.columnAt(position.x())
        if column < 1:  # Ignorer la colonne 0 (checkbox)
            return
        
        # Obtenir la valeur de la cellule
        cell_value = item.text(column)
        if not cell_value or cell_value.strip() == "":
            return
        
        # Copier directement dans le presse-papiers
        self._copy_to_clipboard(cell_value)
    
    def _copy_to_clipboard(self, text):
        """Copier le texte dans le presse-papiers"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        # Feedback visuel (optionnel)
        if hasattr(self, 'parent_window') and hasattr(self.parent_window, 'statusbar'):
            self.parent_window.statusbar.showMessage(f"📋 Copié: '{text}'", 2000)
    
    def get_cleanup_options(self):
        """Retourner les options de nettoyage sélectionnées"""
        # Collecter les données de fusion des doublons de références
        inconsistencies_fusion_data = []
        
        if hasattr(self, 'inconsistencies_tree'):
            for i in range(self.inconsistencies_tree.topLevelItemCount()):
                parent_item = self.inconsistencies_tree.topLevelItem(i)
                
                # Collecter toutes les données du groupe
                parent_user_data = parent_item.data(0, Qt.UserRole)
                ref_modele = parent_user_data.get('ref_modele', '') if parent_user_data else ''
                
                group_data = {
                    'ref_modele': ref_modele,
                    'devices': [],
                    'master_device': None
                }
                
                # Analyser le parent
                parent_data = parent_item.data(0, Qt.UserRole)
                if parent_data:
                    # Utiliser l'état réel de la checkbox plutôt que les données stockées
                    is_master = parent_item.checkState(0) == Qt.Checked
                    device_id = parent_data['device_data']['id']
                    
                    device_info = {
                        'id': device_id,
                        'is_master': is_master,
                        'modified': parent_data.get('modified', False),
                        'current_data': {
                            'type': parent_item.text(2),
                            'manufacturer': parent_item.text(3),
                            'ref_modele': parent_item.text(4),
                            'commercial_ref': parent_item.text(5),
                            'other_ref': parent_item.text(6),
                            'category': parent_item.text(7),
                            'notes': parent_item.text(8)
                        }
                    }
                    group_data['devices'].append(device_info)
                    if device_info['is_master']:
                        group_data['master_device'] = device_info
                
                # Analyser les enfants
                for j in range(parent_item.childCount()):
                    child_item = parent_item.child(j)
                    child_data = child_item.data(0, Qt.UserRole)
                    if child_data:
                        # Utiliser l'état réel de la checkbox plutôt que les données stockées
                        is_master = child_item.checkState(0) == Qt.Checked
                        device_id = child_data['device_data']['id']
                        
                        device_info = {
                            'id': device_id,
                            'is_master': is_master,
                            'modified': child_data.get('modified', False),
                            'current_data': {
                                'type': child_item.text(2),
                                'manufacturer': child_item.text(3),
                                'ref_modele': child_item.text(4),
                                'commercial_ref': child_item.text(5),
                                'other_ref': child_item.text(6),
                                'category': child_item.text(7),
                                'notes': child_item.text(8)
                            }
                        }
                        group_data['devices'].append(device_info)
                        if device_info['is_master']:
                            group_data['master_device'] = device_info
                
                # Seulement ajouter le groupe s'il y a un master sélectionné
                if group_data['master_device']:
                    inconsistencies_fusion_data.append(group_data)
        
        return {
            'clean_devices': self.clean_devices_cb.isChecked(),
            'clean_pieces': self.clean_pieces_cb.isChecked(),
            'clean_inconsistencies': self.clean_inconsistencies_cb.isChecked(),
            'analysis_data': self.analysis_data,
            'inconsistencies_fusion_data': inconsistencies_fusion_data
        }
    
    def get_selected_inconsistencies_master_ids(self):
        """Retourner les IDs des appareils sélectionnés comme maîtres pour chaque groupe de doublons"""
        master_selections = {}
        
        for i in range(self.inconsistencies_tree.topLevelItemCount()):
            parent_item = self.inconsistencies_tree.topLevelItem(i)
            parent_data = parent_item.data(0, Qt.UserRole)
            
            if not parent_data:
                continue
                
            ref_modele = parent_data.get('ref_modele', '')
            master_id = None
            
            # Vérifier si le parent est sélectionné
            if parent_data.get('is_master', False):
                master_id = parent_data['device_data']['id']
            else:
                # Chercher parmi les enfants
                for j in range(parent_item.childCount()):
                    child_item = parent_item.child(j)
                    child_data = child_item.data(0, Qt.UserRole)
                    
                    if child_data and child_data.get('is_master', False):
                        master_id = child_data['device_data']['id']
                        break
            
            # Seulement ajouter si un maître est effectivement sélectionné
            if master_id is not None:
                master_selections[ref_modele] = master_id
        
        return master_selections