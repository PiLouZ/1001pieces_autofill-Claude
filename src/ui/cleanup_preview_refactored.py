"""
Fenêtre de prévisualisation du nettoyage des doublons - Version refactorisée
Utilise les services DuplicatesAnalysisService et CleanupUIService
"""

from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QButtonGroup, QFrame, QWidget, QMessageBox, QProgressBar, QSizePolicy, QSize
)
from .qt_imports import Qt, QTimer
import qtawesome as qta

from ..core.logger import app_logger
from .style_manager import StyleManager
from ..data.database_manager import DatabaseManager
from ..data.data_validator import DataValidator
from ..services.duplicates_analysis_service import DuplicatesAnalysisService
from ..services.cleanup_ui_service import CleanupUIService
from .message_helper import show_success, show_error, MessageHelper
from ..utils.error_handler import handle_cleanup_preview_errors

class CleanupPreviewDialog(QDialog):
    """Fenêtre de prévisualisation du nettoyage des doublons - Version refactorisée"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Nettoyage des doublons")
        self.resize(1400, 900)
        self.setModal(True)
        
        # Services
        self.db_manager = parent.db_manager if parent else DatabaseManager()
        self.analysis_service = DuplicatesAnalysisService(self.db_manager, self)
        self.ui_service = CleanupUIService(self)
        
        # État
        self.analysis_results = None
        self.user_choice = None
        # Nombre de groupes marqués "distincts" pendant cette session (action immédiate)
        self._distinct_marked_session = 0

        # Animation fluide de la barre de chargement : la valeur affichée glisse vers
        # un "plafond" (dernier jalon reçu) avec une inertie, au lieu de sauter par
        # paliers — évite l'effet "charge un peu puis se fige".
        self._loading_ceiling = 0.0
        self._loading_display = 0.0
        self._loading_timer = None

        # Widgets
        self._loading_widget = None
        self._loading_step_label = None
        self._loading_bar = None
        self.stats_widget = None
        self.devices_widget = None
        self.pieces_widget = None
        self.distinct_widget = None
        self.history_widget = None
        self.main_widget = None
        
        self._init_ui()
        self._connect_signals()
        self.analysis_service.start_analysis()
        
    def _init_ui(self):
        """Initialiser l'interface utilisateur"""
        layout = QVBoxLayout(self)

        # Widget de chargement inline (visible pendant l'analyse)
        self._loading_widget = QWidget()
        self._loading_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        loading_layout = QVBoxLayout(self._loading_widget)
        loading_layout.setAlignment(Qt.AlignCenter)
        loading_layout.setSpacing(16)

        # Spinner + titre
        spinner_row = QHBoxLayout()
        spinner_row.setAlignment(Qt.AlignCenter)
        spinner_row.setSpacing(10)
        spinner_btn = QPushButton()
        spinner_btn.setFlat(True)
        spinner_btn.setEnabled(False)
        spinner_btn.setFixedSize(28, 28)
        spinner_btn.setIconSize(QSize(22, 22))
        spinner_btn.setIcon(qta.icon('fa5s.circle-notch', color='#495057',
                                     animation=qta.Spin(spinner_btn)))
        spinner_btn.setStyleSheet(StyleManager.FLAT_TRANSPARENT)
        spinner_row.addWidget(spinner_btn)
        title_lbl = QLabel("Analyse des doublons en cours…")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #212529;")
        spinner_row.addWidget(title_lbl)
        loading_layout.addLayout(spinner_row)

        # Étape courante
        self._loading_step_label = QLabel("Initialisation…")
        self._loading_step_label.setAlignment(Qt.AlignCenter)
        self._loading_step_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        loading_layout.addWidget(self._loading_step_label)

        # Barre de progression fine
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 100)
        self._loading_bar.setValue(0)
        self._loading_bar.setTextVisible(False)
        self._loading_bar.setFixedHeight(6)
        self._loading_bar.setMaximumWidth(400)
        self._loading_bar.setStyleSheet("""
            QProgressBar { border: none; border-radius: 3px; background: #e9ecef; }
            QProgressBar::chunk { border-radius: 3px; background: #495057; }
        """)
        loading_layout.addWidget(self._loading_bar, 0, Qt.AlignHCenter)
        layout.addWidget(self._loading_widget)

        # Timer d'animation de la barre (glissement fluide vers le plafond courant)
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(40)
        self._loading_timer.timeout.connect(self._tick_loading_bar)
        self._loading_timer.start()

        # Widget principal (masqué pendant l'analyse)
        self.main_widget = QWidget()
        self.main_widget.setVisible(False)
        self._init_main_widget()
        layout.addWidget(self.main_widget)

        # Boutons de contrôle
        self._init_control_buttons()
        layout.addLayout(self.control_layout)
        
    def _init_main_widget(self):
        """Initialiser le widget principal avec les résultats"""
        main_layout = QVBoxLayout(self.main_widget)

        # Statistiques
        self.stats_widget = self.ui_service.create_stats_widget()
        main_layout.addWidget(self.stats_widget)

        # Définition des sections de navigation
        _nav_defs = [
            ('fa5s.mobile-alt', '#2980b9', 'Appareils en doublon'),
            ('fa5s.cog',        '#e67e22', 'Pièces dupliquées'),
            ('fa5s.tag',        '#8e44ad', 'Références distinctes'),
            ('fa5s.history',    '#6c757d', 'Historique'),
        ]

        # Créer les widgets de contenu dans l'ordre
        self.devices_widget = self.ui_service.create_devices_widget()
        self.devices_widget.history_callback = self.add_to_history

        self.pieces_widget = self.ui_service.create_pieces_widget()

        self.distinct_widget = self.ui_service.create_distinct_references_widget()
        self.distinct_widget.set_db_manager(self.db_manager)

        self.history_widget = self.ui_service.create_history_widget()
        self.history_widget.export_config_service = getattr(
            self.parent_window, 'export_config_service', None
        )
        self.history_widget.set_db_manager(self.db_manager)

        _pages = [
            self.devices_widget,
            self.pieces_widget,
            self.distinct_widget,
            self.history_widget,
        ]

        # Stack de contenu
        self._nav_stack = QStackedWidget()
        for widget in _pages:
            self._nav_stack.addWidget(widget)

        # Barre de navigation (boutons checkables exclusifs)
        nav_bar = QHBoxLayout()
        nav_bar.setSpacing(2)
        nav_bar.setContentsMargins(0, 4, 0, 4)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        def _make_nav_toggle(b, iname, icolor):
            def _on_toggled(checked):
                b.setIcon(qta.icon(iname, color='white' if checked else icolor))
            return _on_toggled

        for i, (icon_name, icon_color, label) in enumerate(_nav_defs):
            btn = QPushButton(label)
            is_first = (i == 0)
            btn.setIcon(qta.icon(icon_name, color='white' if is_first else icon_color))
            btn.setIconSize(QSize(12, 12))
            btn.setCheckable(True)
            btn.setChecked(is_first)
            btn.setStyleSheet("""
                QPushButton { padding: 4px 12px; font-size: 11px; border-radius: 4px; }
                QPushButton:checked { background-color: #495057; color: white; }
            """)
            btn.toggled.connect(_make_nav_toggle(btn, icon_name, icon_color))
            btn.toggled.connect(
                lambda checked, idx=i: self._nav_stack.setCurrentIndex(idx) if checked else None
            )
            self._nav_group.addButton(btn, i)
            nav_bar.addWidget(btn)

        nav_bar.addStretch()
        main_layout.addLayout(nav_bar)

        # Séparateur fin
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #dee2e6;")
        main_layout.addWidget(separator)

        main_layout.addWidget(self._nav_stack)
        
    def _init_control_buttons(self):
        """Initialiser les boutons de contrôle"""
        self.control_layout = QHBoxLayout()
        
        # Boutons d'action
        self.preview_btn = QPushButton("Prévisualiser")
        self.preview_btn.setIcon(qta.icon('fa5s.eye', color='white'))
        self.preview_btn.setIconSize(QSize(12, 12))
        self.preview_btn.setStyleSheet(
            "QPushButton { background-color: #007bff; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
        )

        self.apply_btn = QPushButton("Appliquer le nettoyage")
        self.apply_btn.setIcon(qta.icon('fa5s.check', color='white'))
        self.apply_btn.setIconSize(QSize(12, 12))
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
        )

        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setIcon(qta.icon('fa5s.times', color='white'))
        self.cancel_btn.setIconSize(QSize(12, 12))
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #6c757d; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
        )

        # Bouton de relance de l'analyse (vérification manuelle à la demande) —
        # utilitaire distinct du flux Prévisualiser → Appliquer, donc placé à gauche.
        self.reanalyze_btn = QPushButton("Re-analyser")
        self.reanalyze_btn.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        self.reanalyze_btn.setIconSize(QSize(12, 12))
        self.reanalyze_btn.setToolTip("Relancer la détection des doublons")
        self.reanalyze_btn.setStyleSheet(
            "QPushButton { background-color: #17a2b8; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:disabled { background-color: #b8dce3; color: #f0f0f0; }"
        )

        # Initialement désactivés (jusqu'à la fin de la première analyse)
        self.preview_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.reanalyze_btn.setEnabled(False)

        self.control_layout.addWidget(self.cancel_btn)
        self.control_layout.addWidget(self.reanalyze_btn)
        self.control_layout.addStretch()
        self.control_layout.addWidget(self.preview_btn)
        self.control_layout.addWidget(self.apply_btn)
        
    def _connect_signals(self):
        """Connecter les signaux"""
        # Signaux du service d'analyse
        self.analysis_service.analysis_progress.connect(self._on_analysis_progress)
        self.analysis_service.analysis_completed.connect(self._on_analysis_completed)
        self.analysis_service.analysis_error.connect(self._on_analysis_error)
        
        # Signaux des widgets
        if self.devices_widget:
            self.devices_widget.devices_selection_changed.connect(self._update_buttons_state)
            self.devices_widget.groups_marked_distinct.connect(self._on_groups_marked_distinct)

        if self.pieces_widget:
            self.pieces_widget.pieces_selection_changed.connect(self._update_buttons_state)
            
        # Signaux des boutons
        self.preview_btn.clicked.connect(self._preview_changes)
        self.apply_btn.clicked.connect(self._apply_cleanup)
        self.cancel_btn.clicked.connect(self.reject)
        self.reanalyze_btn.clicked.connect(self._restart_analysis)
        
    def _restart_analysis(self, checked=False):
        """Relancer une analyse complète des doublons sans rouvrir la fenêtre.

        Reconstitue l'état « chargement » (les callbacks d'analyse pilotent deux
        modes mutuellement exclusifs : `_loading_widget` vs `main_widget`) puis
        rappelle le service. Le service se garde déjà d'un double lancement, mais
        on désactive aussi les boutons côté UI pendant le scan.
        """
        # Ne pas relancer si une analyse est déjà en cours
        worker = getattr(self.analysis_service, 'analysis_worker', None)
        if worker is not None and worker.isRunning():
            return

        # Réinitialiser l'animation de la barre de chargement
        self._loading_ceiling = 0.0
        self._loading_display = 0.0
        if self._loading_bar:
            self._loading_bar.setValue(0)
        if self._loading_step_label:
            self._loading_step_label.setText("Initialisation…")

        # Les marquages « distincts » de la session précédente sont déjà persistés
        # en base et exclus par la requête d'analyse : la nouvelle analyse les
        # reflète. On repart donc d'un compteur d'aperçu vierge.
        self._distinct_marked_session = 0

        # Repasser en mode chargement
        if self.main_widget:
            self.main_widget.setVisible(False)
        if self._loading_widget:
            self._loading_widget.setVisible(True)
        if self._loading_timer:
            self._loading_timer.start()

        # Désactiver les actions pendant le scan
        self.preview_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.reanalyze_btn.setEnabled(False)

        app_logger.info("Relance manuelle de l'analyse des doublons")
        self.analysis_service.start_analysis()

    def _on_analysis_progress(self, progress: int, message: str):
        """Gérer la progression de l'analyse.

        On ne fixe pas directement la valeur de la barre : on relève le "plafond"
        vers lequel l'animation va glisser (cf. `_tick_loading_bar`).
        """
        self._loading_ceiling = float(progress)
        if self._loading_step_label:
            self._loading_step_label.setText(message)

    def _tick_loading_bar(self):
        """Faire glisser la barre vers le plafond courant avec une inertie.

        Le rapprochement décélère près du plafond (rendu "réaliste"), avec un pas
        minimal pour que le mouvement reste perceptible même quand le worker est
        silencieux entre deux jalons.
        """
        if not self._loading_bar:
            return
        if self._loading_display < self._loading_ceiling:
            step = max(0.4, (self._loading_ceiling - self._loading_display) * 0.07)
            self._loading_display = min(self._loading_display + step, self._loading_ceiling)
            self._loading_bar.setValue(int(self._loading_display))
        
    @handle_cleanup_preview_errors()
    def _on_analysis_completed(self, results: dict):
        """Gérer la fin de l'analyse"""
        self.analysis_results = results

        # Finaliser l'animation : barre à 100 % puis arrêt du timer
        if self._loading_timer:
            self._loading_timer.stop()
        if self._loading_bar:
            self._loading_bar.setValue(100)

        # Masquer le chargement, afficher les résultats
        if self._loading_widget:
            self._loading_widget.setVisible(False)

        # Afficher les résultats
        self.main_widget.setVisible(True)

        # Mettre à jour les statistiques
        if self.stats_widget and 'statistics' in results:
            self.stats_widget.update_stats(results['statistics'])

        # Peupler les onglets
        if self.devices_widget and 'duplicate_devices' in results:
            self.devices_widget.populate_devices(results['duplicate_devices'])

        if self.pieces_widget and 'duplicate_pieces' in results:
            self.pieces_widget.populate_pieces(results['duplicate_pieces'])

        # Rafraîchir l'onglet « Références distinctes » pour rester cohérent avec
        # ce nouveau scan (utile notamment après une relance manuelle).
        if self.distinct_widget:
            self.distinct_widget.load_distinct_references()

        # Activer les boutons (réactive aussi « Re-analyser » après un scan)
        self.preview_btn.setEnabled(True)
        self.reanalyze_btn.setEnabled(True)
        self._update_buttons_state()

        app_logger.info("Interface de nettoyage mise à jour avec les résultats d'analyse")
            
    def _on_analysis_error(self, error_message: str):
        """Gérer les erreurs d'analyse"""
        if self._loading_timer:
            self._loading_timer.stop()
        if self._loading_widget:
            self._loading_widget.setVisible(False)
        # Réactiver « Re-analyser » pour permettre de retenter après un échec
        self.reanalyze_btn.setEnabled(True)
        show_error(self, "Erreur d'analyse", f"Erreur lors de l'analyse des doublons:\n{error_message}")
        
    def _on_groups_marked_distinct(self, marked: list):
        """Réagir au marquage 'distinct' d'un ou plusieurs groupes (effet immédiat).

        Décrémente les statistiques affichées et rafraîchit l'onglet des références
        distinctes, sans relancer toute l'analyse.
        """
        if not marked:
            return

        # Compteur de session (action immédiate, déjà enregistrée en base)
        self._distinct_marked_session += len(marked)

        # Décrément des stats live (les groupes marqués distincts ne sont plus des doublons)
        stats = (self.analysis_results or {}).get('statistics')
        if stats is not None and self.stats_widget:
            removed_groups = len(marked)
            removed_affected = sum(m.get('affected', 0) for m in marked)
            removed_savings = sum(m.get('savings', 0) for m in marked)

            stats['total_duplicate_devices'] = max(
                stats.get('total_duplicate_devices', 0) - removed_groups, 0
            )
            stats['total_affected_devices'] = max(
                stats.get('total_affected_devices', 0) - removed_affected, 0
            )
            stats['potential_savings_devices'] = max(
                stats.get('potential_savings_devices', 0) - removed_savings, 0
            )
            self.stats_widget.update_stats(stats)

        # Rafraîchir l'onglet "Références distinctes" pour refléter les nouveaux marquages
        if self.distinct_widget:
            self.distinct_widget.load_distinct_references()

        # Mettre à jour l'état des boutons (la sélection peut avoir changé)
        self._update_buttons_state()

    def _update_buttons_state(self):
        """Mettre à jour l'état des boutons selon les sélections"""
        has_actionable = False

        # Appareils : seuls comptent les groupes VALIDES (exactement 1 maître coché).
        # Cocher 0 ou ≥2 appareils dans un groupe le rend ignoré silencieusement —
        # on n'active donc pas "Appliquer" sur cette base trompeuse.
        if self.devices_widget:
            merge_groups = self.devices_widget.get_merge_groups()
            has_actionable = has_actionable or len(merge_groups) > 0

        # Pièces : au moins une référence sélectionnée
        if self.pieces_widget:
            selected_pieces = self.pieces_widget.get_selected_pieces()
            has_actionable = has_actionable or len(selected_pieces) > 0

        self.apply_btn.setEnabled(has_actionable)
        
    @handle_cleanup_preview_errors()
    def _preview_changes(self, checked=False):
        """Prévisualiser les changements qui seront appliqués"""
        preview_text = ""

        # Section "immédiat" : marquages distincts déjà enregistrés cette session
        if self._distinct_marked_session > 0:
            preview_text += "DÉJÀ APPLIQUÉ pendant cette session (immédiat) :\n"
            _n = self._distinct_marked_session
            _g = 'groupe marqué' if _n <= 1 else 'groupes marqués'
            preview_text += (
                f"  • {_n} {_g} comme distinct{'s' if _n > 1 else ''} "
                f"— enregistré{'s' if _n > 1 else ''} en base\n\n"
            )

        preview_text += "SERA APPLIQUÉ au clic sur « Appliquer le nettoyage » (différé) :\n\n"

        # Appareils à fusionner
        if self.devices_widget:
            merge_groups = self.devices_widget.get_merge_groups()
            if merge_groups:
                preview_text += f"APPAREILS À FUSIONNER ({len(merge_groups)} groupes) :\n"
                for group in merge_groups:
                    master_id = group['master_id']
                    duplicate_ids = group['duplicate_ids']
                    preview_text += f"  • Fusionner appareils {duplicate_ids} vers appareil {master_id}\n"
                preview_text += "\n"

        # Pièces à supprimer
        if self.pieces_widget:
            selected_pieces = self.pieces_widget.get_selected_pieces()
            if selected_pieces:
                preview_text += f"PIÈCES DUPLIQUÉES À NETTOYER ({len(selected_pieces)} références) :\n"
                for ref_piece in selected_pieces[:10]:  # Montrer les 10 premières
                    preview_text += f"  • {ref_piece}\n"
                if len(selected_pieces) > 10:
                    preview_text += f"  • ... et {len(selected_pieces) - 10} autres\n"
                preview_text += "\n"

        preview_text += "ATTENTION: Ces opérations sont irréversibles!\n"
        preview_text += "Assurez-vous d'avoir une sauvegarde de votre base de données."

        # Afficher dans une boîte de dialogue
        from .qt_imports import QTextEdit
        dialog = QDialog(self)
        dialog.setWindowTitle("Aperçu des changements")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setPlainText(preview_text)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        # Bouton fermer
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        # show() + WA_DeleteOnClose au lieu de exec_() (évite une boucle d'événements
        # imbriquée pendant que l'analyse tourne en arrière-plan)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setModal(True)
        dialog.show()
            
    @handle_cleanup_preview_errors()
    def _apply_cleanup(self, checked=False):
        """Appliquer le nettoyage sélectionné"""
        # Confirmation
        if not MessageHelper.ask_question(
            self,
            "Êtes-vous sûr de vouloir appliquer ces changements?\n\n"
            "Cette opération est irréversible.\n"
            "Une copie de sécurité de la base sera créée automatiquement.",
            "Confirmation du nettoyage"
        ):
            return

        # Copie de sécurité systématique avant cette opération destructive.
        # En cas d'échec de la copie, l'opération continue (comportement historique).
        backup_service = getattr(self.parent_window, 'backup_service', None)
        if backup_service:
            backup_service.create_backup(reason="nettoyage")

        # Préparer les options de nettoyage
        cleanup_options = {}

        # Options pour les appareils
        if self.devices_widget:
            merge_groups = self.devices_widget.get_merge_groups()
            if merge_groups:
                cleanup_options['device_merges'] = merge_groups

        # Options pour les pièces
        if self.pieces_widget:
            selected_pieces = self.pieces_widget.get_selected_pieces()
            if selected_pieces:
                cleanup_options['piece_deletions'] = selected_pieces

        # Appliquer le nettoyage
        if cleanup_options:
            results = self.analysis_service.apply_cleanup_decisions(cleanup_options)

            # Afficher les résultats
            if results.get('errors'):
                error_text = "\n".join(results['errors'])
                show_error(self, "Erreurs lors du nettoyage", f"Certaines opérations ont échoué:\n{error_text}")
            else:
                success_message = f"Nettoyage terminé avec succès!\n\n"
                success_message += f"• {results.get('devices_merged', 0)} appareils fusionnés\n"
                success_message += f"• {results.get('devices_deleted', 0)} doublons d'appareils supprimés\n"
                success_message += f"• {results.get('pieces_deleted', 0)} pièces dupliquées supprimées"

                MessageHelper.show_success(self, success_message, "Nettoyage terminé")

                # Enregistrer dans l'historique
                if self.history_widget:
                    details = f"{results.get('devices_merged', 0)} appareils fusionnés, {results.get('devices_deleted', 0)} doublons supprimés, {results.get('pieces_deleted', 0)} pièces nettoyées"
                    self.history_widget.add_action("Nettoyage automatique", details, "Succès")

                # Fermer la boîte de dialogue
                self.user_choice = 'applied'
                self.accept()
        else:
            show_error(self, "Aucune sélection", "Aucun élément sélectionné pour le nettoyage.")
            
    def get_user_choice(self):
        """Obtenir le choix de l'utilisateur"""
        return self.user_choice

    def add_to_history(self, action_type: str, details: str, result: str):
        """Ajouter une action à l'historique"""
        if self.history_widget:
            self.history_widget.add_action(action_type, details, result)
        
    def closeEvent(self, event):
        """Gérer la fermeture de la fenêtre"""
        # Arrêter l'animation de la barre
        if self._loading_timer:
            self._loading_timer.stop()
        # Arrêter l'analyse si en cours
        if self.analysis_service:
            self.analysis_service.stop_analysis()
        event.accept()
        
    def reject(self):
        """Gérer l'annulation"""
        self.user_choice = 'cancelled'
        super().reject()