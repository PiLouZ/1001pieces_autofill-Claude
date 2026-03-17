"""
Service de configuration de la barre d'outils - Phase 2.5d
Extrait de main_refactored.py pour améliorer la maintenabilité

Responsabilités:
- Configuration et création de la barre d'outils moderne
- Gestion des actions et raccourcis
- Séparation UI/logique pour une architecture plus propre
"""

from .qt_imports import QToolBar, QAction, QPushButton, QMenu
from .qt_imports import QSize, Qt
from .qt_imports import QKeySequence

class ToolbarService:
    """
    Service spécialisé pour la configuration de la barre d'outils
    
    Responsabilités:
    - Création et configuration de la toolbar moderne
    - Définition des actions et raccourcis
    - Gestion des groupes d'outils logiques
    - Interface claire entre UI et logique métier
    """
    
    def __init__(self, main_window):
        self.main_window = main_window

        # Références des boutons pour les services externes
        self.action_button = None
        self.clean_duplicates_action = None
        
    def setup_toolbar(self):
        """Configurer la barre d'outils"""
        toolbar = QToolBar()
        toolbar.setObjectName("modernToolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toolbar.setMovable(False)
        self.main_window.addToolBar(toolbar)

        # Groupe Édition
        self.main_window.undo_action = QAction("Annuler", self.main_window)
        self.main_window.undo_action.setShortcut(QKeySequence.Undo)
        self.main_window.undo_action.setToolTip("Annuler la dernière action (Cmd+Z)")
        self.main_window.undo_action.triggered.connect(self.main_window._undo)
        toolbar.addAction(self.main_window.undo_action)

        self.main_window.redo_action = QAction("Rétablir", self.main_window)
        self.main_window.redo_action.setShortcut(QKeySequence.Redo)
        self.main_window.redo_action.setToolTip("Rétablir l'action annulée (Cmd+Y)")
        self.main_window.redo_action.triggered.connect(self.main_window._redo)
        toolbar.addAction(self.main_window.redo_action)

        self._add_toolbar_separator(toolbar)

        # Groupe Données
        save_action = QAction("Sauvegarder", self.main_window)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setToolTip("Sauvegarder toutes les modifications (Cmd+S)")
        save_action.triggered.connect(getattr(self.main_window, '_manual_save', lambda: None))
        toolbar.addAction(save_action)

        import_action = QAction("Importer", self.main_window)
        import_action.setToolTip("Importer un fichier PDF ou CSV")
        import_action.triggered.connect(self.main_window._import_file)
        toolbar.addAction(import_action)

        self._add_toolbar_separator(toolbar)

        # Accès direct Pièces
        pieces_action = QAction("Pièces", self.main_window)
        pieces_action.setToolTip("Gérer les pièces détachées")
        pieces_action.triggered.connect(getattr(self.main_window, '_open_pieces_manager', lambda: None))
        toolbar.addAction(pieces_action)

        self._add_toolbar_separator(toolbar)

        # Menus déroulants
        self._setup_display_menu(toolbar)
        self._setup_tools_menu(toolbar)

        self._add_toolbar_separator(toolbar)

        # Aide et diagnostic
        logs_action = QAction("Journal", self.main_window)
        logs_action.setToolTip("Ouvrir le visualiseur de logs")
        logs_action.triggered.connect(getattr(self.main_window, '_open_log_viewer', lambda: None))
        toolbar.addAction(logs_action)

        guide_action = QAction("Guide", self.main_window)
        guide_action.setToolTip("Guide d'utilisation et raccourcis clavier")
        guide_action.triggered.connect(getattr(self.main_window, '_show_local_guide', lambda: None))
        toolbar.addAction(guide_action)

        self._add_toolbar_separator(toolbar)

        # Rafraîchir (discret, en fin)
        refresh_action = QAction("↺", self.main_window)
        refresh_action.setShortcut("F5")
        refresh_action.setToolTip("Rafraîchir l'application (F5)")
        refresh_action.triggered.connect(getattr(self.main_window, '_refresh_application', lambda: None))
        toolbar.addAction(refresh_action)

        return toolbar
    
    def _setup_display_menu(self, toolbar):
        """Menu Affichage — tout ce qui concerne la présentation des données"""
        display_btn = QPushButton("Affichage")
        display_btn.setObjectName("menuButton")
        display_menu = QMenu()

        columns_action = QAction("Colonnes", self.main_window)
        columns_action.setToolTip("Configurer l'affichage des colonnes")
        columns_action.triggered.connect(getattr(self.main_window, '_configure_columns', lambda: None))
        display_menu.addAction(columns_action)

        categories_action = QAction("Catégories", self.main_window)
        categories_action.triggered.connect(self.main_window._manage_categories)
        display_menu.addAction(categories_action)

        display_btn.setMenu(display_menu)
        toolbar.addWidget(display_btn)

    def _setup_tools_menu(self, toolbar):
        """Menu Outils — actions de maintenance et configuration"""
        tools_btn = QPushButton("Outils")
        tools_btn.setObjectName("menuButton")
        tools_menu = QMenu()

        autocomplete_action = QAction("Autocomplétion", self.main_window)
        autocomplete_action.triggered.connect(self.main_window._fill_empty_fields)
        tools_menu.addAction(autocomplete_action)

        clean_action = QAction("Nettoyer les doublons", self.main_window)
        clean_action.triggered.connect(self.main_window._clean_data)
        tools_menu.addAction(clean_action)

        paste_config_action = QAction("Configuration Collage", self.main_window)
        paste_config_action.setToolTip("Configurer le nettoyage automatique des extensions collées")
        paste_config_action.triggered.connect(self._configure_paste_cleanup)
        tools_menu.addAction(paste_config_action)

        tools_menu.addSeparator()

        fts5_action = QAction("Index de recherche FTS5", self.main_window)
        fts5_action.setToolTip("Gérer l'index de recherche plein texte (FTS5)")
        fts5_action.triggered.connect(getattr(self.main_window, '_open_fts5_manager', lambda: None))
        tools_menu.addAction(fts5_action)

        tools_menu.addSeparator()

        export_action = QAction("Exporter l'application…", self.main_window)
        export_action.setToolTip("Créer un dossier portable pour installation sur une autre machine")
        export_action.triggered.connect(getattr(self.main_window, '_export_application', lambda: None))
        tools_menu.addAction(export_action)

        tools_btn.setMenu(tools_menu)
        toolbar.addWidget(tools_btn)

        # Stocker les références pour les services externes (compatibilité)
        self.action_button = tools_btn
        self.clean_duplicates_action = clean_action
    
    def _add_toolbar_separator(self, toolbar):
        """Ajouter un séparateur dans la toolbar"""
        toolbar.addSeparator()
    
    def _configure_paste_cleanup(self):
        """Configurer le service de nettoyage du collage"""
        from .qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox, QPushButton
        
        class PasteConfigDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Configuration du Collage Automatique")
                self.setModal(True)
                self.setup_ui()
                
            def setup_ui(self):
                layout = QVBoxLayout()
                
                # Titre explicatif
                title = QLabel("📋 Configuration du nettoyage automatique du collage")
                title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
                layout.addWidget(title)
                
                explanation = QLabel(
                    "Configure comment les extensions de fichiers (.pdf, .csv, etc.)\n"
                    "sont traitées lors du collage dans le champ de recherche."
                )
                explanation.setStyleSheet("margin-bottom: 15px;")
                layout.addWidget(explanation)
                
                # Option confirmation
                self.confirmation_checkbox = QCheckBox("Demander confirmation avant transformation")
                self.confirmation_checkbox.setChecked(self.parent().paste_cleanup_service._ask_confirmation)
                layout.addWidget(self.confirmation_checkbox)
                
                # Option mémorisation
                self.remember_checkbox = QCheckBox("Mémoriser le choix pour les mêmes extensions")
                self.remember_checkbox.setChecked(self.parent().paste_cleanup_service._remember_choice)
                layout.addWidget(self.remember_checkbox)
                
                # Remplacement par défaut
                default_layout = QHBoxLayout()
                default_layout.addWidget(QLabel("Remplacement par défaut:"))
                
                self.replacement_combo = QComboBox()
                self.replacement_combo.addItems([
                    "|| (OU logique)",
                    "&& (ET logique)", 
                    "Espace simple",
                    "Supprimer complètement"
                ])
                
                # Sélectionner l'option actuelle
                current_replacement = self.parent().paste_cleanup_service._default_replacement
                if current_replacement == '||':
                    self.replacement_combo.setCurrentIndex(0)
                elif current_replacement == '&&':
                    self.replacement_combo.setCurrentIndex(1)
                elif current_replacement == ' ':
                    self.replacement_combo.setCurrentIndex(2)
                else:
                    self.replacement_combo.setCurrentIndex(3)
                
                default_layout.addWidget(self.replacement_combo)
                layout.addLayout(default_layout)
                
                # Exemple
                example_label = QLabel(
                    "\nExemple: \"46X0008.pdf 45X2378.csv\" → \"46X0008 || 45X2378\""
                )
                example_label.setStyleSheet("color: #666; font-style: italic; margin-top: 10px;")
                layout.addWidget(example_label)
                
                # Boutons
                buttons_layout = QHBoxLayout()
                
                clear_memory_btn = QPushButton("🗑️ Effacer mémoire")
                clear_memory_btn.setToolTip("Effacer tous les choix mémorisés")
                clear_memory_btn.clicked.connect(self.clear_memory)
                buttons_layout.addWidget(clear_memory_btn)
                
                buttons_layout.addStretch()
                
                ok_btn = QPushButton("OK")
                ok_btn.clicked.connect(self.accept)
                buttons_layout.addWidget(ok_btn)
                
                cancel_btn = QPushButton("Annuler")
                cancel_btn.clicked.connect(self.reject)
                buttons_layout.addWidget(cancel_btn)
                
                layout.addLayout(buttons_layout)
                self.setLayout(layout)
                
            def clear_memory(self):
                self.parent().paste_cleanup_service.clear_memory()
                from .qt_imports import QMessageBox
                QMessageBox.information(self, "Mémoire effacée", "Tous les choix mémorisés ont été supprimés.")
                
            def get_config(self):
                replacement_map = {
                    0: '||',
                    1: '&&', 
                    2: ' ',
                    3: ''
                }
                
                return {
                    'ask_confirmation': self.confirmation_checkbox.isChecked(),
                    'remember_choice': self.remember_checkbox.isChecked(),
                    'default_replacement': replacement_map[self.replacement_combo.currentIndex()]
                }
        
        # Afficher le dialogue
        dialog = PasteConfigDialog(self.main_window)
        if dialog.exec_() == QDialog.Accepted:
            config = dialog.get_config()
            
            # Appliquer la configuration
            self.main_window.paste_cleanup_service.configure_defaults(
                config['default_replacement'],
                config['ask_confirmation'],
                config['remember_choice']
            )