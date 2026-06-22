"""
Service de gestion de l'état de l'interface utilisateur
Extrait de main_refactored.py - Phase 3.4

Responsabilités:
- Gestion des indicateurs visuels (sort, progress, boutons)
- Configuration des paramètres d'interface
- Mise à jour des états d'affichage
- Gestion des overlays et des effets visuels
- Opérations de rafraîchissement global
"""

from typing import Optional, Any
from ..ui.qt_imports import (pyqtSignal, QTimer, Qt, QApplication, QProgressBar,
                            QLabel, QTableWidget, QFont, QPixmap, QPainter, QIcon, QPalette)

from ..core.config import Config, pluralize
from ..core.logger import app_logger
from .base_service import BaseService, DebounceTimer, service_operation
from ..utils.error_handler import handle_ui_operation_errors

class UIStateManagementService(BaseService):
    """Service unifié pour la gestion de l'état de l'interface utilisateur"""

    # Signaux pour communiquer les changements d'état
    state_updated = pyqtSignal(str, Any)  # state_name, value
    visual_indicator_changed = pyqtSignal(str, bool)  # indicator_type, enabled
    progress_updated = pyqtSignal(int)  # progress_value
    ui_refreshed = pyqtSignal()

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent_window=parent_window, parent=parent)

        # Services requis pour l'injection automatique
        self._required_services = []

        # État des indicateurs visuels
        self.sort_indicators_enabled = True
        self.progress_visible = False
        self.current_progress_value = 0

        # Références aux widgets (seront initialisées lors de l'injection)
        self.table_widget = None
        self.progress_bar = None
        self.status_bar = None

        # Timer pour les mises à jour différées avec DebounceTimer
        self.refresh_timer = DebounceTimer(
            callback=self._delayed_refresh,
            delay_ms=100,
            parent=self
        )

        self.log_operation("__init__", "UIStateManagementService initialisé", "info")

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur initialize_services")
    def initialize_services(self):
        """Initialiser les références vers les widgets principaux"""
        if not self.parent_window:
            self.log_operation("initialize_services", "parent_window non défini", "warning")
            return

        # Récupérer les références des widgets depuis le parent
        self.table_widget = getattr(self.parent_window, 'table', None)
        self.progress_bar = getattr(self.parent_window, 'progress_bar', None)
        self.status_bar = getattr(self.parent_window, 'statusbar', None)

        self.log_operation("initialize_services", "UIStateManagementService: Services initialisés", "info")

    # === GESTION DES INDICATEURS VISUELS ===

    @service_operation("mise_a_jour_indicateurs_tri")
    def update_sort_indicators(self, enabled: bool = True):
        """Mettre à jour l'affichage des indicateurs de tri"""
        self.sort_indicators_enabled = enabled

        if self.table_widget and hasattr(self.table_widget, 'horizontalHeader'):
            header = self.table_widget.horizontalHeader()
            if header:
                # Appliquer la visibilité des indicateurs
                header.setSectionsClickable(enabled)
                if enabled:
                    header.setSortIndicatorShown(True)
                else:
                    header.setSortIndicatorShown(False)

        self.visual_indicator_changed.emit("sort_indicators", enabled)
        self.log_operation("update_sort_indicators", f"Indicateurs de tri: {'activés' if enabled else 'désactivés'}", "debug")

    @service_operation("mise_a_jour_visibilite_progress")
    def update_progress_visibility(self, visible: bool):
        """Mettre à jour la visibilité de la barre de progression"""
        self.progress_visible = visible

        if self.progress_bar:
            self.progress_bar.setVisible(visible)
            if not visible:
                self.progress_bar.setValue(0)
                self.current_progress_value = 0

        self.visual_indicator_changed.emit("progress_bar", visible)
        self.log_operation("update_progress_visibility", f"Barre de progression: {'visible' if visible else 'cachée'}", "debug")

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur update_progress_value")
    def update_progress_value(self, value: int):
        """Mettre à jour la valeur de la barre de progression"""
        self.current_progress_value = max(0, min(100, value))

        if self.progress_bar and self.progress_visible:
            self.progress_bar.setValue(self.current_progress_value)

        self.progress_updated.emit(self.current_progress_value)

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur set_button_states")
    def set_button_states(self, button_configs: dict):
        """Configurer l'état de plusieurs boutons

        Args:
            button_configs: Dict avec nom_bouton -> {"enabled": bool, "visible": bool, "text": str}
        """
        for button_name, config in button_configs.items():
            button = getattr(self.parent_window, button_name, None)
            if button:
                if "enabled" in config:
                    button.setEnabled(config["enabled"])
                if "visible" in config:
                    button.setVisible(config["visible"])
                if "text" in config:
                    button.setText(config["text"])

    # === CONFIGURATION DES PARAMÈTRES D'INTERFACE ===

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur configure_table_appearance")
    def configure_table_appearance(self, font_size: int = None, alternate_colors: bool = None):
        """Configurer l'apparence du tableau"""
        if not self.table_widget:
            return

        if font_size is not None:
            font = self.table_widget.font()
            font.setPointSize(font_size)
            self.table_widget.setFont(font)

        if alternate_colors is not None:
            self.table_widget.setAlternatingRowColors(alternate_colors)

        self.state_updated.emit("table_appearance", {
            "font_size": font_size,
            "alternate_colors": alternate_colors
        })

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur set_window_title_suffix")
    def set_window_title_suffix(self, suffix: str = ""):
        """Ajouter un suffixe au titre de la fenêtre"""
        if self.parent_window:
            base_title = "1001 Pièces Auto-Fill"
            if suffix:
                title = f"{base_title} - {suffix}"
            else:
                title = base_title
            self.parent_window.setWindowTitle(title)

    # === GESTION DES SÉLECTIONS ET DES HANDLES ===

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur update_selection_state")
    def update_selection_state(self, has_selection: bool, selection_count: int = 0):
        """Mettre à jour l'état basé sur la sélection actuelle"""
        # Configurer les boutons dépendant de la sélection
        selection_buttons = {
            "delete_button": {"enabled": has_selection},
            "copy_button": {"enabled": has_selection},
        }

        self.set_button_states(selection_buttons)

        # Mettre à jour la barre de statut si applicable
        if self.status_bar and has_selection:
            status_text = pluralize(selection_count, 'élément sélectionné', 'éléments sélectionnés')
            self.status_bar.showMessage(status_text, Config.STATUS_MESSAGE_TIMEOUT)

        self.state_updated.emit("selection", {
            "has_selection": has_selection,
            "count": selection_count
        })

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur toggle_drag_handles_visibility")
    def toggle_drag_handles_visibility(self, visible: bool):
        """Basculer la visibilité des poignées de redimensionnement"""
        if self.table_widget and hasattr(self.table_widget, 'horizontalHeader'):
            header = self.table_widget.horizontalHeader()
            if header:
                # Permettre ou interdire le redimensionnement
                if visible:
                    header.setSectionsMovable(True)
                    header.setStretchLastSection(False)
                else:
                    header.setSectionsMovable(False)
                    header.setStretchLastSection(True)

        self.visual_indicator_changed.emit("drag_handles", visible)

    # === OVERLAYS ET EFFETS VISUELS ===

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur show_loading_overlay")
    def show_loading_overlay(self, message: str = "Chargement en cours..."):
        """Afficher un overlay de chargement"""
        if self.status_bar:
            self.status_bar.showMessage(f"⏳ {message}")

        # Désactiver les interactions pendant le chargement
        if self.parent_window:
            self.parent_window.setEnabled(False)

        QApplication.processEvents()

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur hide_loading_overlay")
    def hide_loading_overlay(self):
        """Masquer l'overlay de chargement"""
        if self.parent_window:
            self.parent_window.setEnabled(True)

        if self.status_bar:
            self.status_bar.clearMessage()

        QApplication.processEvents()

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur apply_visual_effect")
    def apply_visual_effect(self, effect_type: str, target_widget: str = "table"):
        """Appliquer un effet visuel temporaire"""
        widget = getattr(self.parent_window, target_widget, None)
        if not widget:
            return

        if effect_type == "highlight":
            # Effet de surbrillance temporaire
            original_style = widget.styleSheet()
            widget.setStyleSheet(f"{original_style}; border: 2px solid #007ACC;")

            # Restaurer après 1 seconde
            QTimer.singleShot(1000, lambda: widget.setStyleSheet(original_style))

        elif effect_type == "flash":
            # Effet de clignotement
            self._flash_widget(widget)

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur _flash_widget")
    def _flash_widget(self, widget):
        """Effet de clignotement pour un widget"""
        original_style = widget.styleSheet()
        flash_style = f"{original_style}; background-color: rgba(0, 122, 204, 0.3);"

        widget.setStyleSheet(flash_style)
        QTimer.singleShot(150, lambda: widget.setStyleSheet(original_style))

    # === RAFRAÎCHISSEMENT GLOBAL ===

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur schedule_refresh")
    def schedule_refresh(self, delay_ms: int = 100):
        """Programmer un rafraîchissement différé de l'interface"""
        self.refresh_timer.stop()
        self.refresh_timer.start(delay_ms)

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur _delayed_refresh")
    def _delayed_refresh(self):
        """Effectuer le rafraîchissement différé"""
        self.force_refresh_all_ui()

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur force_refresh_all_ui")
    def force_refresh_all_ui(self):
        """Forcer le rafraîchissement complet de l'interface"""
        # Rafraîchir le tableau
        if self.table_widget:
            self.table_widget.viewport().update()

        # Rafraîchir les indicateurs
        self.update_sort_indicators(self.sort_indicators_enabled)
        self.update_progress_visibility(self.progress_visible)

        # Forcer le traitement des événements
        QApplication.processEvents()

        self.ui_refreshed.emit()
        app_logger.debug(" Rafraîchissement complet de l'interface")

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur reset_ui_state")
    def reset_ui_state(self):
        """Remettre l'interface dans son état par défaut"""
        # Remettre les indicateurs par défaut
        self.update_sort_indicators(True)
        self.update_progress_visibility(False)
        self.hide_loading_overlay()

        # Remettre le titre par défaut
        self.set_window_title_suffix("")

        # Remettre les boutons par défaut
        default_buttons = {
            "save_button": {"enabled": True, "visible": True},
            "refresh_button": {"enabled": True, "visible": True}
        }
        self.set_button_states(default_buttons)

        self.state_updated.emit("ui_reset", True)
        app_logger.info(" Interface remise à l'état par défaut")

    # === UTILITAIRES ET GESTION D'ÉTAT ===

    def get_current_state(self) -> dict:
        """Obtenir l'état actuel de l'interface"""
        return {
            "sort_indicators_enabled": self.sort_indicators_enabled,
            "progress_visible": self.progress_visible,
            "current_progress_value": self.current_progress_value,
            "widgets_initialized": all([
                self.table_widget is not None,
                self.progress_bar is not None,
                self.status_bar is not None
            ])
        }

    @handle_ui_operation_errors(return_value=None, log_prefix="[ERR] Erreur apply_state")
    def apply_state(self, state_dict: dict):
        """Appliquer un état d'interface"""
        if "sort_indicators_enabled" in state_dict:
            self.update_sort_indicators(state_dict["sort_indicators_enabled"])

        if "progress_visible" in state_dict:
            self.update_progress_visibility(state_dict["progress_visible"])

        if "current_progress_value" in state_dict:
            self.update_progress_value(state_dict["current_progress_value"])

        app_logger.debug(" État d'interface appliqué")