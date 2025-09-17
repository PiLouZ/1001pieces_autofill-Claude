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
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtWidgets import QApplication, QProgressBar, QLabel, QTableWidget
from PyQt5.QtGui import QFont, QPixmap, QPainter, QIcon, QPalette

from ..core.config import Config
from ..core.logger import app_logger


class UIStateManagementService(QObject):
    """Service unifié pour la gestion de l'état de l'interface utilisateur"""

    # Signaux pour communiquer les changements d'état
    state_updated = pyqtSignal(str, Any)  # state_name, value
    visual_indicator_changed = pyqtSignal(str, bool)  # indicator_type, enabled
    progress_updated = pyqtSignal(int)  # progress_value
    ui_refreshed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent

        # État des indicateurs visuels
        self.sort_indicators_enabled = True
        self.progress_visible = False
        self.current_progress_value = 0

        # Références aux widgets (seront initialisées lors de l'injection)
        self.table_widget = None
        self.progress_bar = None
        self.status_bar = None

        # Timer pour les mises à jour différées
        self.refresh_timer = QTimer()
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self._delayed_refresh)

        app_logger.info("✅ UIStateManagementService initialisé")

    def initialize_services(self):
        """Initialiser les références vers les widgets principaux"""
        if not self.parent_widget:
            app_logger.warning("⚠️ UIStateManagementService: parent_widget non défini")
            return

        try:
            # Récupérer les références des widgets depuis le parent
            self.table_widget = getattr(self.parent_widget, 'table', None)
            self.progress_bar = getattr(self.parent_widget, 'progress_bar', None)
            self.status_bar = getattr(self.parent_widget, 'statusbar', None)

            app_logger.info("🔧 UIStateManagementService: Services initialisés")

        except Exception as e:
            app_logger.error(f"❌ Erreur lors de l'initialisation UIStateManagementService: {e}")

    # === GESTION DES INDICATEURS VISUELS ===

    def update_sort_indicators(self, enabled: bool = True):
        """Mettre à jour l'affichage des indicateurs de tri"""
        try:
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
            app_logger.debug(f"🎯 Indicateurs de tri: {'activés' if enabled else 'désactivés'}")

        except Exception as e:
            app_logger.error(f"❌ Erreur update_sort_indicators: {e}")

    def update_progress_visibility(self, visible: bool):
        """Mettre à jour la visibilité de la barre de progression"""
        try:
            self.progress_visible = visible

            if self.progress_bar:
                self.progress_bar.setVisible(visible)
                if not visible:
                    self.progress_bar.setValue(0)
                    self.current_progress_value = 0

            self.visual_indicator_changed.emit("progress_bar", visible)
            app_logger.debug(f"📊 Barre de progression: {'visible' if visible else 'cachée'}")

        except Exception as e:
            app_logger.error(f"❌ Erreur update_progress_visibility: {e}")

    def update_progress_value(self, value: int):
        """Mettre à jour la valeur de la barre de progression"""
        try:
            self.current_progress_value = max(0, min(100, value))

            if self.progress_bar and self.progress_visible:
                self.progress_bar.setValue(self.current_progress_value)

            self.progress_updated.emit(self.current_progress_value)

        except Exception as e:
            app_logger.error(f"❌ Erreur update_progress_value: {e}")

    def set_button_states(self, button_configs: dict):
        """Configurer l'état de plusieurs boutons

        Args:
            button_configs: Dict avec nom_bouton -> {"enabled": bool, "visible": bool, "text": str}
        """
        try:
            for button_name, config in button_configs.items():
                button = getattr(self.parent_widget, button_name, None)
                if button:
                    if "enabled" in config:
                        button.setEnabled(config["enabled"])
                    if "visible" in config:
                        button.setVisible(config["visible"])
                    if "text" in config:
                        button.setText(config["text"])

            app_logger.debug(f"🔘 États des boutons mis à jour: {list(button_configs.keys())}")

        except Exception as e:
            app_logger.error(f"❌ Erreur set_button_states: {e}")

    # === CONFIGURATION DES PARAMÈTRES D'INTERFACE ===

    def configure_table_appearance(self, font_size: int = None, alternate_colors: bool = None):
        """Configurer l'apparence du tableau"""
        try:
            if not self.table_widget:
                return

            if font_size is not None:
                font = self.table_widget.font()
                font.setPointSize(font_size)
                self.table_widget.setFont(font)
                app_logger.debug(f"🔤 Taille de police du tableau: {font_size}")

            if alternate_colors is not None:
                self.table_widget.setAlternatingRowColors(alternate_colors)
                app_logger.debug(f"🎨 Couleurs alternées: {'activées' if alternate_colors else 'désactivées'}")

            self.state_updated.emit("table_appearance", {
                "font_size": font_size,
                "alternate_colors": alternate_colors
            })

        except Exception as e:
            app_logger.error(f"❌ Erreur configure_table_appearance: {e}")

    def set_window_title_suffix(self, suffix: str = ""):
        """Ajouter un suffixe au titre de la fenêtre"""
        try:
            if self.parent_widget:
                base_title = "1001 Pièces Auto-Fill"
                if suffix:
                    title = f"{base_title} - {suffix}"
                else:
                    title = base_title
                self.parent_widget.setWindowTitle(title)

                app_logger.debug(f"📝 Titre de fenêtre: {title}")

        except Exception as e:
            app_logger.error(f"❌ Erreur set_window_title_suffix: {e}")

    # === GESTION DES SÉLECTIONS ET DES HANDLES ===

    def update_selection_state(self, has_selection: bool, selection_count: int = 0):
        """Mettre à jour l'état basé sur la sélection actuelle"""
        try:
            # Configurer les boutons dépendant de la sélection
            selection_buttons = {
                "delete_button": {"enabled": has_selection},
                "copy_button": {"enabled": has_selection},
            }

            self.set_button_states(selection_buttons)

            # Mettre à jour la barre de statut si applicable
            if self.status_bar and has_selection:
                status_text = f"{selection_count} élément(s) sélectionné(s)"
                self.status_bar.showMessage(status_text, Config.STATUS_MESSAGE_TIMEOUT)

            self.state_updated.emit("selection", {
                "has_selection": has_selection,
                "count": selection_count
            })

            app_logger.debug(f"✅ État de sélection: {selection_count} élément(s)")

        except Exception as e:
            app_logger.error(f"❌ Erreur update_selection_state: {e}")

    def toggle_drag_handles_visibility(self, visible: bool):
        """Basculer la visibilité des poignées de redimensionnement"""
        try:
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
            app_logger.debug(f"🖱️ Poignées de redimensionnement: {'visibles' if visible else 'cachées'}")

        except Exception as e:
            app_logger.error(f"❌ Erreur toggle_drag_handles_visibility: {e}")

    # === OVERLAYS ET EFFETS VISUELS ===

    def show_loading_overlay(self, message: str = "Chargement en cours..."):
        """Afficher un overlay de chargement"""
        try:
            if self.status_bar:
                self.status_bar.showMessage(f"⏳ {message}")

            # Désactiver les interactions pendant le chargement
            if self.parent_widget:
                self.parent_widget.setEnabled(False)

            QApplication.processEvents()
            app_logger.debug(f"🔄 Overlay de chargement: {message}")

        except Exception as e:
            app_logger.error(f"❌ Erreur show_loading_overlay: {e}")

    def hide_loading_overlay(self):
        """Masquer l'overlay de chargement"""
        try:
            if self.parent_widget:
                self.parent_widget.setEnabled(True)

            if self.status_bar:
                self.status_bar.clearMessage()

            QApplication.processEvents()
            app_logger.debug("✅ Overlay de chargement masqué")

        except Exception as e:
            app_logger.error(f"❌ Erreur hide_loading_overlay: {e}")

    def apply_visual_effect(self, effect_type: str, target_widget: str = "table"):
        """Appliquer un effet visuel temporaire"""
        try:
            widget = getattr(self.parent_widget, target_widget, None)
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

            app_logger.debug(f"✨ Effet visuel '{effect_type}' appliqué à {target_widget}")

        except Exception as e:
            app_logger.error(f"❌ Erreur apply_visual_effect: {e}")

    def _flash_widget(self, widget):
        """Effet de clignotement pour un widget"""
        try:
            original_style = widget.styleSheet()
            flash_style = f"{original_style}; background-color: rgba(0, 122, 204, 0.3);"

            widget.setStyleSheet(flash_style)
            QTimer.singleShot(150, lambda: widget.setStyleSheet(original_style))

        except Exception as e:
            app_logger.error(f"❌ Erreur _flash_widget: {e}")

    # === RAFRAÎCHISSEMENT GLOBAL ===

    def schedule_refresh(self, delay_ms: int = 100):
        """Programmer un rafraîchissement différé de l'interface"""
        try:
            self.refresh_timer.stop()
            self.refresh_timer.start(delay_ms)
            app_logger.debug(f"⏱️ Rafraîchissement programmé dans {delay_ms}ms")

        except Exception as e:
            app_logger.error(f"❌ Erreur schedule_refresh: {e}")

    def _delayed_refresh(self):
        """Effectuer le rafraîchissement différé"""
        try:
            self.force_refresh_all_ui()

        except Exception as e:
            app_logger.error(f"❌ Erreur _delayed_refresh: {e}")

    def force_refresh_all_ui(self):
        """Forcer le rafraîchissement complet de l'interface"""
        try:
            # Rafraîchir le tableau
            if self.table_widget:
                self.table_widget.viewport().update()

            # Rafraîchir les indicateurs
            self.update_sort_indicators(self.sort_indicators_enabled)
            self.update_progress_visibility(self.progress_visible)

            # Forcer le traitement des événements
            QApplication.processEvents()

            self.ui_refreshed.emit()
            app_logger.debug("🔄 Rafraîchissement complet de l'interface")

        except Exception as e:
            app_logger.error(f"❌ Erreur force_refresh_all_ui: {e}")

    def reset_ui_state(self):
        """Remettre l'interface dans son état par défaut"""
        try:
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
            app_logger.info("🔄 Interface remise à l'état par défaut")

        except Exception as e:
            app_logger.error(f"❌ Erreur reset_ui_state: {e}")

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

    def apply_state(self, state_dict: dict):
        """Appliquer un état d'interface"""
        try:
            if "sort_indicators_enabled" in state_dict:
                self.update_sort_indicators(state_dict["sort_indicators_enabled"])

            if "progress_visible" in state_dict:
                self.update_progress_visibility(state_dict["progress_visible"])

            if "current_progress_value" in state_dict:
                self.update_progress_value(state_dict["current_progress_value"])

            app_logger.debug("📊 État d'interface appliqué")

        except Exception as e:
            app_logger.error(f"❌ Erreur apply_state: {e}")