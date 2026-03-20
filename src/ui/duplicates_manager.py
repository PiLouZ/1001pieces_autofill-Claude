"""
Gestionnaire des références en doublon avec interface de fusion et correction
"""

import qtawesome as qta
from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter, QTextEdit,
    QGroupBox, QComboBox, QLineEdit, QCheckBox, QMessageBox, QProgressBar
)
from .qt_imports import Qt, QTimer
from .qt_imports import QFont, QSize
from src.core.logger import app_logger
from src.utils.error_handler import handle_ui_errors, handle_database_operation_errors
from src.utils.text_utils import clean_display_text

class DuplicatesManager(QDialog):
    """Gestionnaire des références en doublon avec interface de fusion"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Gestionnaire des Références en Doublon")
        self.resize(1200, 800)
        self.setModal(False)
        
        # Données
        self.duplicates_data = []
        self.selected_group = None
        self.selected_items = []
        
        self._init_ui()
        self._load_duplicates()
    
    def _init_ui(self):
        """Initialiser l'interface"""
        layout = QVBoxLayout(self)
        
        # En-tête avec statistiques
        header_layout = QHBoxLayout()
        self.stats_label = QLabel("Chargement des doublons…")
        self.stats_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 11px; padding: 4px;")
        header_layout.addWidget(self.stats_label)
        
        header_layout.addStretch()
        
        # Boutons d'action rapide
        refresh_btn = QPushButton()
        refresh_btn.setIcon(qta.icon('fa5s.sync-alt', color='#555555'))
        refresh_btn.setIconSize(QSize(13, 13))
        refresh_btn.setFixedSize(26, 26)
        refresh_btn.setFlat(True)
        refresh_btn.setStyleSheet("QPushButton { border: none; background: transparent; } QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }")
        refresh_btn.setToolTip("Actualiser")
        refresh_btn.clicked.connect(self._load_duplicates)
        header_layout.addWidget(refresh_btn)

        auto_merge_btn = QPushButton("Fusion auto")
        auto_merge_btn.setIcon(qta.icon('fa5s.magic', color='white'))
        auto_merge_btn.setIconSize(QSize(11, 11))
        auto_merge_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 3px 10px; font-size: 11px; border-radius: 3px; }")
        auto_merge_btn.setToolTip("Fusionner automatiquement tous les appareils strictement identiques")
        auto_merge_btn.clicked.connect(self._auto_merge_identical)
        header_layout.addWidget(auto_merge_btn)
        
        layout.addLayout(header_layout)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Panneau gauche : Liste des groupes de doublons
        left_panel = self._create_duplicates_list()
        main_splitter.addWidget(left_panel)
        
        # Panneau droit : Détails et actions pour le groupe sélectionné
        right_panel = self._create_details_panel()
        main_splitter.addWidget(right_panel)
        
        # Répartition 60/40
        main_splitter.setSizes([720, 480])
        layout.addWidget(main_splitter)
        
        # Boutons de fermeture
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Fermer")
        close_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def _create_duplicates_list(self):
        """Créer le panneau de liste des doublons"""
        group_box = QGroupBox("Groupes de Références en Doublon")
        layout = QVBoxLayout(group_box)
        
        # Filtre de recherche
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Recherche :"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filtrer par référence (ex: 3000240000)...")
        self.search_input.textChanged.connect(self._filter_duplicates)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Tableau des groupes de doublons
        self.duplicates_table = QTableWidget()
        self.duplicates_table.setColumnCount(2)
        self.duplicates_table.setHorizontalHeaderLabels([
            "Référence Modèle (Colonne C)", "Occurrences"
        ])
        
        # Configuration du tableau
        header = self.duplicates_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        
        self.duplicates_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.duplicates_table.setAlternatingRowColors(True)
        self.duplicates_table.itemSelectionChanged.connect(self._on_group_selected)
        
        layout.addWidget(self.duplicates_table)
        
        return group_box
    
    def _create_details_panel(self):
        """Créer le panneau de détails et actions"""
        group_box = QGroupBox("Détails et Actions")
        layout = QVBoxLayout(group_box)
        
        # Info sur le groupe sélectionné
        self.group_info_label = QLabel("Sélectionnez un groupe dans la liste pour voir les détails")
        self.group_info_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 10px;")
        layout.addWidget(self.group_info_label)
        
        # Tableau des appareils dans le groupe
        self.devices_table = QTableWidget()
        self.devices_table.setColumnCount(8)
        self.devices_table.setHorizontalHeaderLabels([
            "ID", "Type", "Fabricant", "Ref Modèle", "Ref Comm.", "Autre Ref", "Catégorie", "Notes"
        ])
        
        # Configuration
        devices_header = self.devices_table.horizontalHeader()
        devices_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        devices_header.setSectionResizeMode(1, QHeaderView.Stretch)
        devices_header.setSectionResizeMode(2, QHeaderView.Stretch)
        devices_header.setSectionResizeMode(3, QHeaderView.Stretch)
        devices_header.setSectionResizeMode(4, QHeaderView.Stretch)
        devices_header.setSectionResizeMode(5, QHeaderView.Stretch)
        devices_header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        devices_header.setSectionResizeMode(7, QHeaderView.Stretch)
        
        self.devices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.devices_table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.devices_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.devices_table)
        
        # Actions sur le groupe sélectionné
        actions_layout = QHBoxLayout()
        
        self.merge_selected_btn = QPushButton("Fusionner")
        self.merge_selected_btn.setIcon(qta.icon('fa5s.compress-arrows-alt', color='white'))
        self.merge_selected_btn.setIconSize(QSize(11, 11))
        self.merge_selected_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; padding: 3px 10px; font-size: 11px; border-radius: 3px; } QPushButton:disabled { background-color: #adb5bd; }")
        self.merge_selected_btn.clicked.connect(self._merge_selected_devices)
        self.merge_selected_btn.setEnabled(False)
        actions_layout.addWidget(self.merge_selected_btn)

        self.view_in_main_btn = QPushButton("Voir dans tableau")
        self.view_in_main_btn.setIcon(qta.icon('fa5s.eye', color='#495057'))
        self.view_in_main_btn.setIconSize(QSize(11, 11))
        self.view_in_main_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        self.view_in_main_btn.clicked.connect(self._view_selected_in_main)
        self.view_in_main_btn.setEnabled(False)
        actions_layout.addWidget(self.view_in_main_btn)

        self.delete_selected_btn = QPushButton("Supprimer")
        self.delete_selected_btn.setIcon(qta.icon('fa5s.trash-alt', color='white'))
        self.delete_selected_btn.setIconSize(QSize(11, 11))
        self.delete_selected_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; padding: 3px 10px; font-size: 11px; border-radius: 3px; } QPushButton:disabled { background-color: #adb5bd; }")
        self.delete_selected_btn.clicked.connect(self._delete_selected_devices)
        self.delete_selected_btn.setEnabled(False)
        actions_layout.addWidget(self.delete_selected_btn)
        
        layout.addLayout(actions_layout)
        
        # Zone d'information
        self.info_text = QTextEdit()
        self.info_text.setMaximumHeight(120)
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.info_text)
        
        # Activer/désactiver boutons selon sélection
        self.devices_table.itemSelectionChanged.connect(self._update_action_buttons)
        
        return group_box
    
    @handle_ui_errors(log_prefix="Erreur chargement doublons", show_message=True)
    def _load_duplicates(self):
        """Charger les données des doublons"""
        # Récupérer les doublons par ref_modele depuis la base (même logique que validation)
        duplicates = self.parent_window.db_manager.get_duplicate_ref_modeles()
        self.duplicates_data = duplicates

        # Mettre à jour l'affichage
        self._update_duplicates_table()
        self._update_stats()
    
    def _update_duplicates_table(self):
        """Mettre à jour le tableau des doublons"""
        # Filtrer selon la recherche
        search_text = self.search_input.text().lower()
        filtered_data = []
        
        for item in self.duplicates_data:
            ref_modele, count = item
            search_content = f"{ref_modele}".lower()
            
            if not search_text or search_text in search_content:
                filtered_data.append(item)
        
        # Remplir le tableau
        self.duplicates_table.setRowCount(len(filtered_data))
        
        for row, (ref_modele, count) in enumerate(filtered_data):
            self.duplicates_table.setItem(row, 0, QTableWidgetItem(clean_display_text(ref_modele)))
            
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            
            # Colorer selon le nombre d'occurrences
            if count > 5:
                count_item.setBackground(Qt.red)
                count_item.setForeground(Qt.white)
            elif count > 2:
                count_item.setBackground(Qt.yellow)
            
            self.duplicates_table.setItem(row, 1, count_item)
            
            # Stocker les données complètes dans la première cellule
            self.duplicates_table.item(row, 0).setData(Qt.UserRole, item)
    
    def _update_stats(self):
        """Mettre à jour les statistiques"""
        total_groups = len(self.duplicates_data)
        total_duplicates = sum(count for _, count in self.duplicates_data)
        
        # Afficher le nombre de groupes filtrés vs total
        filtered_groups = self.duplicates_table.rowCount()
        if filtered_groups == total_groups:
            self.stats_label.setText(
                f"{total_groups} références en doublon  •  {total_duplicates} appareils dupliqués"
            )
        else:
            self.stats_label.setText(
                f"{filtered_groups}/{total_groups} références affichées"
            )
    
    def _filter_duplicates(self):
        """Filtrer la liste des doublons"""
        self._update_duplicates_table()
    
    def _on_group_selected(self):
        """Gérer la sélection d'un groupe de doublons"""
        selected_rows = self.duplicates_table.selectionModel().selectedRows()
        
        if not selected_rows:
            self.group_info_label.setText("Sélectionnez un groupe dans la liste pour voir les détails")
            self.devices_table.setRowCount(0)
            return
        
        # Récupérer les données du groupe sélectionné
        row = selected_rows[0].row()
        item_data = self.duplicates_table.item(row, 0).data(Qt.UserRole)
        ref_modele, count = item_data
        
        self.selected_group = item_data
        
        # Mettre à jour l'info
        clean_ref = clean_display_text(ref_modele)
        
        self.group_info_label.setText(
            f"Référence: {clean_ref} ({count} occurrences)"
        )
        
        # Charger les appareils de ce groupe
        self._load_group_devices()
    
    @handle_ui_errors(log_prefix="Erreur chargement appareils", show_message=True)
    def _load_group_devices(self):
        """Charger les appareils du groupe sélectionné"""
        if not self.selected_group:
            return

        ref_modele, count = self.selected_group

        # Utiliser la nouvelle méthode pour récupérer tous les appareils avec cette ref_modele
        devices = self.parent_window.db_manager.get_devices_by_ref_modele(ref_modele)

        # Remplir le tableau des appareils
        self.devices_table.setRowCount(len(devices))

        for row, device in enumerate(devices):
            device_id, dev_type, dev_manufacturer, dev_ref_modele, dev_commercial_ref, dev_other_ref, dev_category, dev_notes = device

            self.devices_table.setItem(row, 0, QTableWidgetItem(str(device_id)))
            self.devices_table.setItem(row, 1, QTableWidgetItem(clean_display_text(dev_type)))
            self.devices_table.setItem(row, 2, QTableWidgetItem(clean_display_text(dev_manufacturer)))
            self.devices_table.setItem(row, 3, QTableWidgetItem(clean_display_text(dev_ref_modele)))
            self.devices_table.setItem(row, 4, QTableWidgetItem(clean_display_text(dev_commercial_ref)))
            self.devices_table.setItem(row, 5, QTableWidgetItem(clean_display_text(dev_other_ref)))
            self.devices_table.setItem(row, 6, QTableWidgetItem(clean_display_text(dev_category)))
            self.devices_table.setItem(row, 7, QTableWidgetItem(clean_display_text(dev_notes)))

            # Stocker l'ID pour les actions
            self.devices_table.item(row, 0).setData(Qt.UserRole, device_id)

        # Afficher les infos dans la zone de texte
        self._update_group_info()
    
    def _update_group_info(self):
        """Mettre à jour les informations du groupe"""
        if not self.selected_group:
            return
        
        info_lines = []
        info_lines.append("INFORMATIONS SUR LE GROUPE DE DOUBLONS")
        info_lines.append("=" * 50)

        device_count = self.devices_table.rowCount()
        info_lines.append(f"Nombre d'appareils: {device_count}")

        if device_count > 1:
            info_lines.append("")
            info_lines.append("ACTIONS POSSIBLES:")
            info_lines.append("• Sélectionnez plusieurs appareils et cliquez 'Fusionner' pour les combiner")
            info_lines.append("• Utilisez 'Voir dans tableau principal' pour localiser dans l'interface")
            info_lines.append("• 'Supprimer sélectionnés' pour éliminer les doublons indésirables")
        
        self.info_text.setPlainText("\n".join(info_lines))
    
    def _update_action_buttons(self):
        """Activer/désactiver les boutons selon la sélection"""
        selected_count = len(self.devices_table.selectionModel().selectedRows())
        
        self.merge_selected_btn.setEnabled(selected_count >= 2)
        self.view_in_main_btn.setEnabled(selected_count >= 1)
        self.delete_selected_btn.setEnabled(selected_count >= 1)
    
    def _merge_selected_devices(self):
        """Fusionner les appareils sélectionnés"""
        selected_rows = self.devices_table.selectionModel().selectedRows()
        
        if len(selected_rows) < 2:
            QMessageBox.warning(self, "Attention", "Sélectionnez au moins 2 appareils à fusionner.")
            return
        
        # Récupérer les IDs des appareils à fusionner
        device_ids = []
        for row in selected_rows:
            device_id = self.devices_table.item(row.row(), 0).data(Qt.UserRole)
            device_ids.append(device_id)
        
        # Confirmation
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Fusionner {len(device_ids)} appareils ?\n\n"
            "Le premier appareil sélectionné sera conservé, les autres seront supprimés.\n"
            "Les pièces associées seront transférées vers l'appareil conservé.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._merge_selected(device_ids)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur fusion appareils")
    def _merge_selected(self, device_ids):
        """Effectue la fusion des appareils sélectionnés"""
        # Garder le premier ID, supprimer les autres
        keep_id = device_ids[0]
        delete_ids = device_ids[1:]

        # Transférer les pièces vers l'appareil conservé
        for delete_id in delete_ids:
            self.parent_window.db_manager.transfer_pieces(delete_id, keep_id)
            self.parent_window.db_manager.delete_appareil(delete_id)

        QMessageBox.information(
            self, "Succès",
            f"Fusion réussie ! {len(delete_ids)} appareils supprimés, "
            f"données consolidées vers l'appareil ID {keep_id}."
        )

        # Actualiser les données
        self._load_duplicates()
        if hasattr(self.parent_window, 'load_data'):
            self.parent_window.load_data()

    def _view_selected_in_main(self):
        """Voir les appareils sélectionnés dans le tableau principal"""
        selected_rows = self.devices_table.selectionModel().selectedRows()

        if not selected_rows:
            return

        # Récupérer l'ID du premier appareil sélectionné
        device_id = self.devices_table.item(selected_rows[0].row(), 0).data(Qt.UserRole)
        self._find_in_main(device_id)

    @handle_ui_errors(log_prefix="Erreur recherche appareil", show_message=True)
    def _find_in_main(self, device_id):
        """Recherche un appareil dans le tableau principal"""
        # Récupérer les données de l'appareil
        query = "SELECT ref_modele FROM appareils WHERE id = ?"
        result = self.parent_window.db_manager.execute_custom_query(query, [device_id])

        if result:
            ref_modele = result[0][0]
            # Rechercher dans la fenêtre principale
            self.parent_window.search_input.setText(clean_display_text(ref_modele))
            self.parent_window.load_data(ref_modele)

            # Message de confirmation
            self.parent_window.statusbar.showMessage(
                f"Recherche de l'appareil ID {device_id} dans le tableau principal", 3000
            )
    
    def _delete_selected_devices(self):
        """Supprimer les appareils sélectionnés"""
        selected_rows = self.devices_table.selectionModel().selectedRows()
        
        if not selected_rows:
            return
        
        # Confirmation
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Supprimer définitivement {len(selected_rows)} appareil(s) ?\n\n"
            "Cette action est irréversible !",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._delete_selected(selected_rows)

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur suppression appareils")
    def _delete_selected(self, selected_rows):
        """Effectue la suppression des appareils sélectionnés"""
        for row in selected_rows:
            device_id = self.devices_table.item(row.row(), 0).data(Qt.UserRole)
            self.parent_window.db_manager.delete_appareil(device_id)

        QMessageBox.information(
            self, "Succès",
            f"{len(selected_rows)} appareil(s) supprimé(s) avec succès."
        )

        # Actualiser
        self._load_duplicates()
        if hasattr(self.parent_window, 'load_data'):
            self.parent_window.load_data()

    def _auto_merge_identical(self):
        """Fusion automatique des doublons strictement identiques"""
        reply = QMessageBox.question(
            self, "Fusion automatique",
            "Fusionner automatiquement tous les appareils strictement identiques ?\n\n"
            "Cette opération gardera le plus ancien de chaque groupe et supprimera les autres.\n"
            "Les pièces associées seront transférées.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._auto_merge_all()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur fusion automatique")
    def _auto_merge_all(self):
        """Effectue la fusion automatique de tous les doublons identiques"""
        # Utiliser la méthode existante du database_manager
        deleted_count = self.parent_window.db_manager.remove_duplicate_devices()

        QMessageBox.information(
            self, "Fusion automatique terminée",
            f"{deleted_count} appareils dupliqués ont été supprimés.\n"
            "Les données ont été consolidées vers les appareils les plus anciens."
        )

        # Actualiser
        self._load_duplicates()
        if hasattr(self.parent_window, 'load_data'):
            self.parent_window.load_data()

    def _show_error(self, message):
        """Afficher un message d'erreur"""
        QMessageBox.critical(self, "Erreur", message)