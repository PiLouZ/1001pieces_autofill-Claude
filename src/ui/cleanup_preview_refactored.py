"""
Fenêtre de prévisualisation du nettoyage des doublons - Version refactorisée
Utilise les services DuplicatesAnalysisService et CleanupUIService
"""

from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTabWidget, QWidget, QMessageBox
)
from .qt_imports import Qt

from ..core.logger import app_logger
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
        self.setWindowTitle("🧹 Prévisualisation du Nettoyage des Doublons")
        self.resize(1400, 900)
        self.setModal(True)
        
        # Services
        self.db_manager = parent.db_manager if parent else DatabaseManager()
        self.analysis_service = DuplicatesAnalysisService(self.db_manager, self)
        self.ui_service = CleanupUIService(self)
        
        # État
        self.analysis_results = None
        self.user_choice = None

        # Widgets
        self.progress_widgets = {}
        self.stats_widget = None
        self.devices_widget = None
        self.pieces_widget = None
        self.distinct_widget = None
        self.history_widget = None
        self.main_widget = None
        
        self._init_ui()
        self._connect_signals()
        
        # Démarrer l'analyse
        self.analysis_service.start_analysis()
        
    def _init_ui(self):
        """Initialiser l'interface utilisateur"""
        layout = QVBoxLayout(self)
        
        # Widgets de progression
        self.progress_widgets = self.ui_service.create_progress_widget()
        
        # En-tête avec progression
        header_layout = QVBoxLayout()
        header_layout.addWidget(self.progress_widgets['title'])
        header_layout.addWidget(self.progress_widgets['progress_bar'])
        header_layout.addWidget(self.progress_widgets['status'])
        layout.addLayout(header_layout)
        
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
        
        # Onglets
        self.tab_widget = QTabWidget()
        
        # Onglet Appareils en doublon
        self.devices_widget = self.ui_service.create_devices_widget()
        self.devices_widget.history_callback = self.add_to_history  # Passer la callback pour l'historique
        self.tab_widget.addTab(self.devices_widget, "📱 Appareils en doublon")
        
        # Onglet Pièces dupliquées
        self.pieces_widget = self.ui_service.create_pieces_widget()
        self.tab_widget.addTab(self.pieces_widget, "🔧 Pièces dupliquées")

        # Onglet Références distinctes
        self.distinct_widget = self.ui_service.create_distinct_references_widget()
        self.distinct_widget.set_db_manager(self.db_manager)
        self.tab_widget.addTab(self.distinct_widget, "🏷️ Références distinctes")

        # Onglet Historique des actions
        self.history_widget = self.ui_service.create_history_widget()
        self.history_widget.set_db_manager(self.db_manager)
        self.tab_widget.addTab(self.history_widget, "📋 Historique")

        main_layout.addWidget(self.tab_widget)
        
    def _init_control_buttons(self):
        """Initialiser les boutons de contrôle"""
        self.control_layout = QHBoxLayout()
        
        # Boutons d'action
        self.preview_btn = QPushButton("📋 Prévisualiser les changements")
        self.apply_btn = QPushButton("✅ Appliquer le nettoyage")
        self.cancel_btn = QPushButton("❌ Annuler")
        
        # Style
        self.preview_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; padding: 8px 16px; border-radius: 4px; }")
        self.apply_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; padding: 8px 16px; border-radius: 4px; }")
        self.cancel_btn.setStyleSheet("QPushButton { background-color: #6c757d; color: white; padding: 8px 16px; border-radius: 4px; }")
        
        # Initialement désactivés
        self.preview_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        
        self.control_layout.addWidget(self.cancel_btn)
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
            
        # Signaux des boutons
        self.preview_btn.clicked.connect(self._preview_changes)
        self.apply_btn.clicked.connect(self._apply_cleanup)
        self.cancel_btn.clicked.connect(self.reject)
        
    def _on_analysis_progress(self, progress: int, message: str):
        """Gérer la progression de l'analyse"""
        self.ui_service.update_progress(self.progress_widgets, progress, message)
        
    @handle_cleanup_preview_errors()
    def _on_analysis_completed(self, results: dict):
        """Gérer la fin de l'analyse"""
        self.analysis_results = results

        # Masquer la progression
        for widget in self.progress_widgets.values():
            widget.setVisible(False)

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

        # Activer les boutons
        self.preview_btn.setEnabled(True)
        self._update_buttons_state()

        app_logger.info("Interface de nettoyage mise à jour avec les résultats d'analyse")
            
    def _on_analysis_error(self, error_message: str):
        """Gérer les erreurs d'analyse"""
        self.ui_service.show_analysis_error(self.progress_widgets, error_message)
        show_error(self, "Erreur d'analyse", f"Erreur lors de l'analyse des doublons:\n{error_message}")
        
    def _update_buttons_state(self):
        """Mettre à jour l'état des boutons selon les sélections"""
        has_selection = False
        
        # Vérifier les sélections d'appareils
        if self.devices_widget:
            selected_devices = self.devices_widget.get_selected_devices()
            has_selection = has_selection or len(selected_devices) > 0
            
        # Vérifier les sélections de pièces
        if self.pieces_widget:
            selected_pieces = self.pieces_widget.get_selected_pieces()
            has_selection = has_selection or len(selected_pieces) > 0
            
        self.apply_btn.setEnabled(has_selection)
        
    @handle_cleanup_preview_errors()
    def _preview_changes(self, checked=False):
        """Prévisualiser les changements qui seront appliqués"""
        preview_text = "Aperçu des changements qui seront appliqués:\n\n"

        # Appareils à fusionner
        if self.devices_widget:
            merge_groups = self.devices_widget.get_merge_groups()
            if merge_groups:
                preview_text += f"📱 APPAREILS À FUSIONNER ({len(merge_groups)} groupes):\n"
                for group in merge_groups:
                    master_id = group['master_id']
                    duplicate_ids = group['duplicate_ids']
                    preview_text += f"  • Fusionner appareils {duplicate_ids} vers appareil {master_id}\n"
                preview_text += "\n"

        # Pièces à supprimer
        if self.pieces_widget:
            selected_pieces = self.pieces_widget.get_selected_pieces()
            if selected_pieces:
                preview_text += f"🔧 PIÈCES DUPLIQUÉES À NETTOYER ({len(selected_pieces)} références):\n"
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

        dialog.exec_()
            
    @handle_cleanup_preview_errors()
    def _apply_cleanup(self, checked=False):
        """Appliquer le nettoyage sélectionné"""
        # Confirmation
        if not MessageHelper.ask_question(
            self,
            "Êtes-vous sûr de vouloir appliquer ces changements?\n\n"
            "Cette opération est irréversible.\n"
            "Assurez-vous d'avoir une sauvegarde de votre base de données.",
            "Confirmation du nettoyage"
        ):
            return

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
        # Arrêter l'analyse si en cours
        if self.analysis_service:
            self.analysis_service.stop_analysis()
        event.accept()
        
    def reject(self):
        """Gérer l'annulation"""
        self.user_choice = 'cancelled'
        super().reject()