"""
Service de configuration de la barre d'outils - Phase 2.5d
Extrait de main_refactored.py pour améliorer la maintenabilité

Responsabilités:
- Configuration et création de la barre d'outils moderne
- Gestion des actions et raccourcis
- Séparation UI/logique pour une architecture plus propre
"""

import qtawesome as qta
from ..utils.qt_imports import QToolBar, QAction, QPushButton, QMenu, QWidget, QSizePolicy
from ..utils.qt_imports import QSize, Qt
from ..utils.qt_imports import QKeySequence
from .style_manager import StyleManager

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
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(14, 14))
        toolbar.setMovable(False)
        self.main_window.addToolBar(toolbar)

        # Groupe Édition
        self.main_window.undo_action = QAction(qta.icon('fa5s.undo', color='#555555'), "Annuler", self.main_window)
        self.main_window.undo_action.setShortcut(QKeySequence.Undo)
        self.main_window.undo_action.setToolTip("Annuler la dernière action (Cmd+Z)")
        self.main_window.undo_action.triggered.connect(self.main_window._undo)
        toolbar.addAction(self.main_window.undo_action)

        self.main_window.redo_action = QAction(qta.icon('fa5s.redo', color='#555555'), "Rétablir", self.main_window)
        self.main_window.redo_action.setShortcut(QKeySequence.Redo)
        self.main_window.redo_action.setToolTip("Rétablir l'action annulée (Cmd+Y)")
        self.main_window.redo_action.triggered.connect(self.main_window._redo)
        toolbar.addAction(self.main_window.redo_action)

        self._add_toolbar_separator(toolbar)

        # Groupe Données
        save_action = QAction(qta.icon('fa5s.save', color='#555555'), "Sauvegarder", self.main_window)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setToolTip("Sauvegarder toutes les modifications (Cmd+S)")
        save_action.triggered.connect(getattr(self.main_window, '_manual_save', lambda: None))
        toolbar.addAction(save_action)

        import_action = QAction(qta.icon('fa5s.file-import', color='#555555'), "Importer", self.main_window)
        import_action.setToolTip("Importer un fichier PDF ou CSV")
        import_action.triggered.connect(self.main_window._import_file)
        toolbar.addAction(import_action)

        self._add_toolbar_separator(toolbar)

        # Accès direct Pièces
        pieces_action = QAction(qta.icon('fa5s.puzzle-piece', color='#555555'), "Pièces", self.main_window)
        pieces_action.setToolTip("Gérer les pièces détachées")
        pieces_action.triggered.connect(getattr(self.main_window, '_open_pieces_manager', lambda: None))
        toolbar.addAction(pieces_action)

        self._add_toolbar_separator(toolbar)

        # Menus déroulants : Affichage / Données / Configuration
        self._setup_display_menu(toolbar)
        self._setup_data_menu(toolbar)
        self._setup_config_menu(toolbar)

        self._add_toolbar_separator(toolbar)

        # Aide et diagnostic
        logs_action = QAction(qta.icon('fa5s.scroll', color='#555555'), "Journal", self.main_window)
        logs_action.setToolTip("Ouvrir le visualiseur de logs")
        logs_action.triggered.connect(getattr(self.main_window, '_open_log_viewer', lambda: None))
        toolbar.addAction(logs_action)

        guide_action = QAction(qta.icon('fa5s.book', color='#555555'), "Guide", self.main_window)
        guide_action.setToolTip("Guide d'utilisation et raccourcis clavier")
        guide_action.triggered.connect(getattr(self.main_window, '_show_local_guide', lambda: None))
        toolbar.addAction(guide_action)

        self._add_toolbar_separator(toolbar)

        # Rafraîchir (discret)
        refresh_action = QAction(qta.icon('fa5s.sync-alt', color='#555555'), "", self.main_window)
        refresh_action.setShortcut("F5")
        refresh_action.setToolTip("Rafraîchir l'application (F5)")
        refresh_action.triggered.connect(getattr(self.main_window, '_refresh_application', lambda: None))
        toolbar.addAction(refresh_action)

        # Espace extensible → pousse le cluster "santé des données" à droite
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Le groupe « ▲ Lignes à traiter ▼ » est dans la barre d'état, sous le
        # tableau (IncompleteNavWidget, cf. main_refactored._setup_statusbar).

        # Bouton dédié "Nettoyer les doublons" (sorti du menu). Sa couleur passe au
        # rouge via DuplicateIndicatorService quand des doublons sont en attente.
        self.clean_duplicates_btn = QPushButton("Nettoyer les doublons")
        self.clean_duplicates_btn.setObjectName("cleanDuplicatesButton")
        self.clean_duplicates_btn.setIcon(qta.icon('fa5s.clone', color='#555555'))
        self.clean_duplicates_btn.setToolTip("Nettoyer les doublons")
        # Style (padding compact) géré par DuplicateIndicatorService (_normal_style /
        # _warning_style) : un setStyleSheet ici serait écrasé.
        self.clean_duplicates_btn.clicked.connect(self.main_window._clean_data)
        # Action conservée pour compatibilité avec DuplicateIndicatorService
        self.clean_duplicates_action = QAction("Nettoyer les doublons", self.main_window)
        self.clean_duplicates_action.triggered.connect(self.main_window._clean_data)
        toolbar.addWidget(self.clean_duplicates_btn)

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

        display_menu.addSeparator()

        # Position de la barre de recherche pièce (haut/bas du tableau) — mémorisée
        search_top_action = QAction("Recherche pièce en haut du tableau", self.main_window)
        search_top_action.setCheckable(True)
        search_top_action.setToolTip("Placer la barre de recherche pièce au-dessus du tableau (sinon sous le tableau)")
        _pos = "bottom"
        if hasattr(self.main_window, 'settings'):
            _pos = self.main_window.settings.value("ui/search_position", "bottom")
        search_top_action.setChecked(_pos == "top")
        search_top_action.toggled.connect(
            getattr(self.main_window, '_on_search_position_toggled', lambda checked: None)
        )
        display_menu.addAction(search_top_action)

        # Hauteur des lignes du tableau — choix exclusif, mémorisé
        from ..utils.qt_imports import QActionGroup
        from ..core.constants import UIConfig
        row_height_menu = display_menu.addMenu("Hauteur des lignes")
        _key = UIConfig.DEFAULT_ROW_HEIGHT
        if hasattr(self.main_window, 'settings'):
            _key = self.main_window.settings.value("ui/row_height", UIConfig.DEFAULT_ROW_HEIGHT)
        row_height_group = QActionGroup(self.main_window)
        row_height_group.setExclusive(True)
        for key, (label, height) in UIConfig.ROW_HEIGHTS.items():
            action = QAction(f"{label} ({height} px)", self.main_window)
            action.setCheckable(True)
            action.setChecked(key == _key)
            action.triggered.connect(
                lambda checked, k=key: getattr(self.main_window, '_on_row_height_chosen', lambda k: None)(k)
            )
            row_height_group.addAction(action)
            row_height_menu.addAction(action)

        display_btn.setMenu(display_menu)
        toolbar.addWidget(display_btn)

    def _setup_data_menu(self, toolbar):
        """Menu Données — opérations sur les données les plus fréquentes"""
        data_btn = QPushButton("Données")
        data_btn.setObjectName("menuButton")
        data_menu = QMenu()

        autocomplete_action = QAction("Autocomplétion", self.main_window)
        autocomplete_action.setToolTip("Compléter automatiquement Type et Fabricant manquants")
        autocomplete_action.triggered.connect(self.main_window._fill_empty_fields)
        data_menu.addAction(autocomplete_action)

        suggest_action = QAction("Suggérer Type/Marque par similarité", self.main_window)
        suggest_action.setToolTip("Proposer Type/Marque pour les lignes incomplètes d'après des références proches déjà renseignées")
        suggest_action.triggered.connect(
            getattr(self.main_window, '_scan_all_for_suggestions', lambda: None)
        )
        data_menu.addAction(suggest_action)

        fiche_site_action = QAction("Lire une fiche du site…", self.main_window)
        fiche_site_action.setToolTip("Reprendre une fiche produit du site : aperçu, validation, enregistrement")
        fiche_site_action.triggered.connect(getattr(self.main_window, '_open_fiche_site_dialog', lambda: None))
        data_menu.addAction(fiche_site_action)

        reprise_site_action = QAction("Reprise des fiches du site…", self.main_window)
        reprise_site_action.setToolTip("Importer en masse les fiches du site, par lots, depuis les exports PrestaShop")
        reprise_site_action.triggered.connect(getattr(self.main_window, '_open_reprise_site_dialog', lambda: None))
        data_menu.addAction(reprise_site_action)

        history_action = QAction("Historique des modifications…", self.main_window)
        history_action.setToolTip("Consulter l'historique persistant des modifications")
        history_action.triggered.connect(getattr(self.main_window, '_open_history_view', lambda: None))
        data_menu.addAction(history_action)

        data_btn.setMenu(data_menu)
        toolbar.addWidget(data_btn)

    def _setup_config_menu(self, toolbar):
        """Menu Configuration — réglages, maintenance et export applicatif"""
        config_btn = QPushButton("Configuration")
        config_btn.setObjectName("menuButton")
        config_menu = QMenu()

        paste_config_action = QAction("Configuration du collage", self.main_window)
        paste_config_action.setToolTip("Configurer le nettoyage automatique des extensions collées")
        paste_config_action.triggered.connect(self._configure_paste_cleanup)
        config_menu.addAction(paste_config_action)

        export_config_action = QAction("Configuration des exports…", self.main_window)
        export_config_action.setToolTip("Personnaliser les colonnes CSV et les templates HTML d'export")
        export_config_action.triggered.connect(
            getattr(self.main_window, '_open_export_config', lambda: None)
        )
        config_menu.addAction(export_config_action)

        config_menu.addSeparator()

        fts5_action = QAction("Index de recherche FTS5", self.main_window)
        fts5_action.setToolTip("Gérer l'index de recherche plein texte (FTS5)")
        fts5_action.triggered.connect(getattr(self.main_window, '_open_fts5_manager', lambda: None))
        config_menu.addAction(fts5_action)

        supersession_csv_action = QAction("Exporter les chaînes de supersession (CSV)", self.main_window)
        supersession_csv_action.setToolTip("Rapport CSV de toutes les relations de remplacement de pièces")
        supersession_csv_action.triggered.connect(
            getattr(self.main_window, '_export_supersession_chains', lambda: None)
        )
        config_menu.addAction(supersession_csv_action)

        restore_action = QAction("Restaurer une sauvegarde…", self.main_window)
        restore_action.setToolTip("Restaurer la base depuis une copie de data/backups/")
        restore_action.triggered.connect(
            getattr(self.main_window, '_open_restore_backup_dialog', lambda: None)
        )
        config_menu.addAction(restore_action)

        config_menu.addSeparator()

        export_action = QAction("Exporter l'application…", self.main_window)
        export_action.setToolTip("Créer un dossier portable pour installation sur une autre machine")
        export_action.triggered.connect(getattr(self.main_window, '_export_application', lambda: None))
        config_menu.addAction(export_action)

        config_btn.setMenu(config_menu)
        toolbar.addWidget(config_btn)
    
    def _add_toolbar_separator(self, toolbar):
        """Ajouter un séparateur dans la toolbar"""
        toolbar.addSeparator()
    
    def _configure_paste_cleanup(self):
        """Configurer le service de nettoyage du collage"""
        from ..utils.qt_imports import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox, QPushButton, QSize
        
        class PasteConfigDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Configuration du collage automatique")
                self.setModal(True)
                self.setup_ui()
                
            def setup_ui(self):
                layout = QVBoxLayout()
                
                # Titre explicatif
                title = QLabel("Configuration du nettoyage automatique du collage")
                title.setStyleSheet("font-weight: bold; font-size: 11px; margin-bottom: 10px;")
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
                default_layout.addWidget(QLabel("Remplacement par défaut :"))
                
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
                    "\nExemple : \"46X0008.pdf 45X2378.csv\" → \"46X0008 || 45X2378\""
                )
                example_label.setStyleSheet("color: #666; font-style: italic; margin-top: 10px;")
                layout.addWidget(example_label)
                
                # Boutons
                buttons_layout = QHBoxLayout()
                
                import qtawesome as qta
                clear_memory_btn = QPushButton("Effacer mémoire")
                clear_memory_btn.setIcon(qta.icon('fa5s.trash-alt', color='#dc3545'))
                clear_memory_btn.setIconSize(QSize(11, 11))
                clear_memory_btn.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
                clear_memory_btn.setToolTip("Effacer tous les choix mémorisés")
                clear_memory_btn.clicked.connect(self.clear_memory)
                buttons_layout.addWidget(clear_memory_btn)

                buttons_layout.addStretch()

                # Ordre de l'appli : Annuler à gauche, action principale à droite
                cancel_btn = QPushButton("Annuler")
                cancel_btn.setAutoDefault(False)
                cancel_btn.clicked.connect(self.reject)
                buttons_layout.addWidget(cancel_btn)

                ok_btn = QPushButton("Enregistrer")
                ok_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
                ok_btn.setDefault(True)
                ok_btn.clicked.connect(self.accept)
                buttons_layout.addWidget(ok_btn)
                
                layout.addLayout(buttons_layout)
                self.setLayout(layout)
                
            def clear_memory(self):
                self.parent().paste_cleanup_service.clear_memory()
                from ..utils.qt_imports import QMessageBox
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

        def _appliquer():
            config = dialog.get_config()
            self.main_window.paste_cleanup_service.configure_defaults(
                config['default_replacement'],
                config['ask_confirmation'],
                config['remember_choice']
            )

        # Modal sans boucle imbriquée (jamais exec_)
        from ..utils.ouverture_modale import ouvrir_modal
        ouvrir_modal(dialog, sur_accepte=_appliquer)