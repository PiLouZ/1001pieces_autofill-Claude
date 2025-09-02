"""
Service de configuration de la barre d'outils - Phase 2.5d
Extrait de main_refactored.py pour améliorer la maintenabilité

Responsabilités:
- Configuration et création de la barre d'outils moderne
- Gestion des actions et raccourcis
- Séparation UI/logique pour une architecture plus propre
"""

from PyQt5.QtWidgets import QToolBar, QAction, QPushButton, QMenu
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QKeySequence


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
        
        self._add_toolbar_separator(toolbar)
        
        # Bouton configuration des colonnes
        columns_action = QAction("☰ Colonnes", self.main_window)
        columns_action.setToolTip("Configurer l'affichage des colonnes")
        columns_action.triggered.connect(getattr(self.main_window, '_configure_columns', lambda: None))
        toolbar.addAction(columns_action)
        
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
        
        validate_action = QAction("🔍 Incohérences", self.main_window)
        validate_action.triggered.connect(self.main_window._validate_and_detect_inconsistencies)
        gestion_menu.addAction(validate_action)
        
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