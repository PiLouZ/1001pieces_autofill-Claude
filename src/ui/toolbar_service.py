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
        """Configurer la barre d'outils moderne (reproduction exacte de l'original)"""
        toolbar = QToolBar()
        toolbar.setObjectName("modernToolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setMovable(False)  # Fixer la barre pour un look plus moderne
        toolbar.setIconSize(QSize(20, 20))  # Icônes de taille uniforme
        self.main_window.addToolBar(toolbar)
        
        # Groupe Actualisation
        refresh_action = QAction("↻", self.main_window)
        refresh_action.setShortcut("F5")
        refresh_action.setToolTip("Rafraîchir l'application (F5)")
        refresh_action.triggered.connect(getattr(self.main_window, '_refresh_application', lambda: None))
        toolbar.addAction(refresh_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Édition
        self.main_window.undo_action = QAction("←", self.main_window)
        self.main_window.undo_action.setShortcut(QKeySequence.Undo)
        self.main_window.undo_action.setToolTip("Annuler la dernière action (Cmd+Z)")
        self.main_window.undo_action.triggered.connect(self.main_window._undo)
        toolbar.addAction(self.main_window.undo_action)
        
        self.main_window.redo_action = QAction("→", self.main_window)
        self.main_window.redo_action.setShortcut(QKeySequence.Redo)
        self.main_window.redo_action.setToolTip("Rétablir l'action annulée (Cmd+Y)")
        self.main_window.redo_action.triggered.connect(self.main_window._redo)
        toolbar.addAction(self.main_window.redo_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Presse-papiers
        copy_action = QAction("📋", self.main_window)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setToolTip("Copier la sélection (Cmd+C)")
        copy_action.triggered.connect(getattr(self.main_window, '_handle_copy', lambda: None))
        toolbar.addAction(copy_action)
        
        paste_action = QAction("📥", self.main_window)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.setToolTip("Coller depuis le presse-papiers (Cmd+V)")
        paste_action.triggered.connect(self.main_window._handle_paste)
        toolbar.addAction(paste_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Sauvegarde
        save_action = QAction("💾", self.main_window)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setToolTip("Sauvegarder toutes les modifications (Cmd+S)")
        save_action.triggered.connect(getattr(self.main_window, '_manual_save', lambda: None))
        toolbar.addAction(save_action)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Menus déroulants
        self._setup_management_menu(toolbar)
        self._setup_action_menu(toolbar)
        
        self._add_toolbar_separator(toolbar)
        
        # Groupe Outils
        self._setup_tools_actions(toolbar)
        
        # Bouton Colonnes déplacé vers le menu Gestion
        
        return toolbar
    
    def _setup_management_menu(self, toolbar):
        """Menu Gestion dans la toolbar"""
        gestion_btn = QPushButton("Gestion")
        gestion_btn.setObjectName("menuButton")
        gestion_menu = QMenu()
        
        categories_action = QAction("🏷️ Catégories", self.main_window)
        categories_action.triggered.connect(self.main_window._manage_categories)
        gestion_menu.addAction(categories_action)
        
        pieces_action = QAction("🔧 Pièces", self.main_window)
        pieces_action.triggered.connect(getattr(self.main_window, '_open_pieces_manager', lambda: None))
        gestion_menu.addAction(pieces_action)
        
        gestion_menu.addSeparator()
        
        # Configuration du collage automatique
        paste_config_action = QAction("📋 Configuration Collage", self.main_window)
        paste_config_action.setToolTip("Configurer le nettoyage automatique des extensions collées")
        paste_config_action.triggered.connect(self._configure_paste_cleanup)
        gestion_menu.addAction(paste_config_action)
        
        # Configuration des colonnes (déplacé depuis la toolbar)
        columns_action = QAction("☰ Colonnes", self.main_window)
        columns_action.setToolTip("Configurer l'affichage des colonnes")
        columns_action.triggered.connect(getattr(self.main_window, '_configure_columns', lambda: None))
        gestion_menu.addAction(columns_action)
        
        gestion_btn.setMenu(gestion_menu)
        toolbar.addWidget(gestion_btn)
    
    def _setup_action_menu(self, toolbar):
        """Menu Action dans la toolbar"""
        action_btn = QPushButton("Action")
        action_btn.setObjectName("menuButton")
        action_menu = QMenu()

        import_action = QAction("📈 Import", self.main_window)
        import_action.triggered.connect(self.main_window._import_file)
        action_menu.addAction(import_action)

        action_menu.addSeparator()

        autocomplete_action = QAction("🗯️ Autocomplétion", self.main_window)
        autocomplete_action.triggered.connect(self.main_window._fill_empty_fields)
        action_menu.addAction(autocomplete_action)

        clean_action = QAction("🧹 Nettoyer les doublons", self.main_window)
        clean_action.triggered.connect(self.main_window._clean_data)
        action_menu.addAction(clean_action)

        action_btn.setMenu(action_menu)
        toolbar.addWidget(action_btn)

        # Stocker les références pour les services externes
        self.action_button = action_btn
        self.clean_duplicates_action = clean_action
    
    def _setup_tools_actions(self, toolbar):
        """Groupe Outils"""
        logs_action = QAction("📊 Journal", self.main_window)
        logs_action.setToolTip("Ouvrir le visualiseur de logs")
        logs_action.triggered.connect(getattr(self.main_window, '_open_log_viewer', lambda: None))
        toolbar.addAction(logs_action)
        
        guide_action = QAction("📖 Guide", self.main_window)
        guide_action.setToolTip("Ouvrir le guide d'utilisation")
        guide_action.triggered.connect(getattr(self.main_window, '_open_user_guide', lambda: None))
        toolbar.addAction(guide_action)
    
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