"""
Service de gestion des raccourcis clavier
Extrait de main_refactored.py - Phase 3.5

Responsabilités:
- Gestion centralisée des raccourcis clavier
- Détection des modificateurs de plateforme (Cmd/Ctrl)
- Dispatch vers les actions appropriées
- Support multi-plateforme (macOS/Windows/Linux)
"""

import sys
from typing import Optional, Callable, Dict
from ..ui.qt_imports import pyqtSignal, Qt, QKeySequence, QKeyEvent, QWidget

from ..core.config import Config
from ..core.logger import app_logger
from .base_service import BaseService, service_operation, safe_operation

class KeyboardShortcutService(BaseService):
    """Service unifié pour la gestion des raccourcis clavier"""

    # Signaux pour notifier les actions de raccourcis
    shortcut_triggered = pyqtSignal(str, object)  # shortcut_name, event
    modifier_detected = pyqtSignal(bool)  # has_cmd_modifier

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent_window=parent_window, parent=parent)

        # Services requis pour l'injection automatique
        self._required_services = []

        # Mapping des raccourcis vers les actions
        self.shortcut_actions = {}
        self.focus_dependent_shortcuts = set()

        # Configuration des raccourcis par défaut
        self._setup_default_shortcuts()

        self.log_operation("__init__", "KeyboardShortcutService initialisé", "info")

    def initialize_services(self):
        """Initialiser les références vers les services principaux"""
        if not self.parent_window:
            self.log_operation("initialize_services", "parent_window non défini", "warning")
            return

        # Les actions seront déléguées au parent window
        self.log_operation("initialize_services", "KeyboardShortcutService: Services initialisés", "info")

    @safe_operation("_setup_default_shortcuts")
    def _setup_default_shortcuts(self):
        """Configurer les raccourcis par défaut"""
        # Raccourcis avec modificateur Cmd/Ctrl
        self.shortcut_actions = {
            Qt.Key.Key_N: ("new_row", "Ajouter nouvelle ligne"),
            Qt.Key.Key_Z: ("undo", "Annuler"),
            Qt.Key.Key_Y: ("redo", "Refaire"),
            Qt.Key.Key_D: ("show_column_values", "Afficher valeurs colonne"),
            Qt.Key.Key_Up: ("smart_navigate_up", "Cellule vide précédente ou tout en haut"),
            Qt.Key.Key_Down: ("smart_navigate_down", "Cellule vide suivante ou tout en bas")
        }

        # Raccourcis standard Qt (utiliser strings au lieu d'enums)
        self.standard_shortcuts = {
            "Save": ("save", "Sauvegarder"),
            "Find": ("find", "Rechercher"),
            "Paste": ("paste", "Coller"),
            "Copy": ("copy", "Copier"),
            "Undo": ("undo", "Annuler"),
            "Redo": ("redo", "Refaire")
        }

        # Raccourcis sans modificateur
        self.function_key_shortcuts = {
            Qt.Key.Key_F5: ("refresh", "Actualiser"),
            Qt.Key.Key_F12: ("log_viewer", "Ouvrir visualiseur de logs"),
            Qt.Key.Key_Escape: ("clear_search", "Effacer recherche")
        }

        # Raccourcis dépendants du focus
        self.focus_dependent_shortcuts.add(Qt.Key.Key_D)

        self.log_operation("_setup_default_shortcuts", "Raccourcis par défaut configurés", "debug")

    @service_operation("gestion_raccourci_clavier")
    def handle_key_press_event(self, event: QKeyEvent) -> bool:
        """
        Gestion centralisée des raccourcis clavier

        Args:
            event: Événement clavier Qt

        Returns:
            bool: True si l'événement a été traité, False sinon
        """
        # Détecter les modificateurs de plateforme
        has_cmd_modifier = self._detect_cmd_modifier(event)
        self.modifier_detected.emit(has_cmd_modifier)

        # Traitement des raccourcis avec modificateur
        if has_cmd_modifier:
            return self._handle_modifier_shortcuts(event)

        # Traitement des raccourcis sans modificateur
        else:
            return self._handle_function_key_shortcuts(event)

    @safe_operation("_detect_cmd_modifier", default_return=False)
    def _detect_cmd_modifier(self, event: QKeyEvent) -> bool:
        """Détecter les modificateurs Cmd/Ctrl selon la plateforme"""
        if sys.platform == 'darwin':
            # Sur macOS, tester les deux possibilités (Qt mappe parfois Cmd vers Ctrl)
            return bool(event.modifiers() & (Qt.MetaModifier | Qt.ControlModifier))
        else:
            # Sur Windows/Linux, utiliser ControlModifier
            return bool(event.modifiers() & Qt.ControlModifier)

    @safe_operation("_handle_modifier_shortcuts", default_return=False)
    def _handle_modifier_shortcuts(self, event: QKeyEvent) -> bool:
        """Traiter les raccourcis avec modificateur Cmd/Ctrl"""
        # Vérifier les raccourcis standard Qt d'abord
        for standard_key_name, (action_name, description) in self.standard_shortcuts.items():
            standard_key = getattr(QKeySequence.StandardKey, standard_key_name, None)
            if standard_key and event.matches(standard_key):
                return self._execute_shortcut_action(action_name, event, description)

        # Vérifier les raccourcis personnalisés
        key = event.key()
        if key in self.shortcut_actions:
            action_name, description = self.shortcut_actions[key]

            # Vérifier les contraintes de focus pour certains raccourcis
            if key in self.focus_dependent_shortcuts:
                if not self._check_focus_constraint(key):
                    return False

            return self._execute_shortcut_action(action_name, event, description)

        return False

    @safe_operation("_handle_function_key_shortcuts", default_return=False)
    def _handle_function_key_shortcuts(self, event: QKeyEvent) -> bool:
        """Traiter les raccourcis sans modificateur (touches fonction)"""
        key = event.key()

        if key in self.function_key_shortcuts:
            action_name, description = self.function_key_shortcuts[key]
            return self._execute_shortcut_action(action_name, event, description)

        return False

    @safe_operation("_check_focus_constraint", default_return=True)
    def _check_focus_constraint(self, key: int) -> bool:
        """Vérifier les contraintes de focus pour certains raccourcis"""
        if key == Qt.Key.Key_D:
            # CMD+D ne fonctionne que depuis le tableau, pas depuis la barre de recherche
            if self.parent_window:
                current_focus = self.parent_window.focusWidget()
                search_input = getattr(self.parent_window, 'search_input', None)
                return current_focus != search_input

        return True

    @safe_operation("_execute_shortcut_action", default_return=False)
    def _execute_shortcut_action(self, action_name: str, event: QKeyEvent, description: str) -> bool:
        """Exécuter l'action correspondant au raccourci"""
        if not self.parent_window:
            app_logger.warning(f"⚠️ Impossible d'exécuter '{action_name}': parent_window non défini")
            return False

        # Mapper les actions vers les méthodes du parent
        action_methods = {
            "new_row": "_add_new_row",
            "save": "_manual_save",
            "find": self._handle_find_shortcut,
            "paste": "_handle_paste",
            "copy": "_handle_copy",
            "undo": "_undo",
            "redo": "_redo",
            "show_column_values": "_show_column_values_list",
            "smart_navigate_up": lambda: self._handle_navigation_shortcut('up'),
            "smart_navigate_down": lambda: self._handle_navigation_shortcut('down'),
            "navigate_top": lambda: self._handle_extreme_navigation('top'),
            "navigate_bottom": lambda: self._handle_extreme_navigation('bottom'),
            "refresh": self._handle_refresh_shortcut,
            "log_viewer": "_open_log_viewer",
            "clear_search": self._handle_clear_search_shortcut
        }

        action_method = action_methods.get(action_name)
        if action_method:
            if callable(action_method):
                # Action lambda directe
                action_method()
            elif isinstance(action_method, str):
                # Méthode du parent window
                method = getattr(self.parent_window, action_method, None)
                if method and callable(method):
                    method()
                else:
                    app_logger.warning(f"⚠️ Méthode '{action_method}' non trouvée")
                    return False

            # Émettre le signal de raccourci traité
            self.shortcut_triggered.emit(action_name, event)
            app_logger.debug(f"⌨️ Raccourci exécuté: {description}")
            return True
        else:
            app_logger.warning(f"⚠️ Action '{action_name}' non configurée")
            return False

    @safe_operation("_handle_find_shortcut")
    def _handle_find_shortcut(self):
        """Traiter le raccourci de recherche (Focus + sélection)"""
        if self.parent_window:
            search_input = getattr(self.parent_window, 'search_input', None)
            if search_input:
                search_input.setFocus()
                search_input.selectAll()

    @safe_operation("_handle_extreme_navigation")
    def _handle_extreme_navigation(self, direction: str):
        """Traiter les raccourcis de navigation vers le haut/bas absolu"""
        if self.parent_window and hasattr(self.parent_window, 'table'):
            table = self.parent_window.table
            current_col = table.currentColumn()

            if current_col < 0:
                current_col = 0  # Prendre la première colonne par défaut

            if direction == 'top':
                # Aller à la première ligne
                table.setCurrentCell(0, current_col)
                app_logger.debug("🔝 Navigation: Première ligne atteinte")
            elif direction == 'bottom':
                # Aller à la dernière ligne
                last_row = table.rowCount() - 1
                if last_row >= 0:
                    table.setCurrentCell(last_row, current_col)
                    app_logger.debug("🔻 Navigation: Dernière ligne atteinte")

    @safe_operation("_handle_navigation_shortcut")
    def _handle_navigation_shortcut(self, direction: str):
        """Navigation intelligente hybride : cellule vide OU extrême selon contexte"""
        if self.parent_window:
            # D'abord essayer la navigation vers cellule vide
            method = getattr(self.parent_window, '_navigate_to_empty_cell', None)
            if method and callable(method):
                # Essayer de naviguer vers une cellule vide
                found_empty = method(direction=direction)

                # Si aucune cellule vide trouvée, faire navigation extrême
                if not found_empty:
                    extreme_direction = 'top' if direction == 'up' else 'bottom'
                    self._handle_extreme_navigation(extreme_direction)
                    app_logger.debug(f"🔄 Navigation hybride: aucune cellule vide → navigation extrême {extreme_direction}")
                else:
                    app_logger.debug(f"✅ Navigation hybride: cellule vide trouvée en direction {direction}")

    @safe_operation("_handle_refresh_shortcut")
    def _handle_refresh_shortcut(self):
        """Traiter le raccourci F5 (Actualiser) - Phase 2d: Migration async pilote"""
        if self.parent_window:
            # Utiliser la recherche parsée actuelle
            advanced_search_service = getattr(self.parent_window, 'advanced_search_service', None)
            table_controller = getattr(self.parent_window, 'table_controller', None)

            if advanced_search_service and table_controller:
                search_term = advanced_search_service.get_current_search_term_with_fallback(self.parent_window)

                # Phase 2d: Migration pilote avec flag A/B testing
                from ..core.config import Config
                if Config.USE_ASYNC_LOAD_DATA:
                    # NOUVEAU: Version async (Phase 2d test pilote)
                    app_logger.debug("🚀 F5 refresh: utilisation load_data_async()")
                    table_controller.load_data_async(search_term)
                else:
                    # ORIGINAL: Version sync (stable, fallback)
                    app_logger.debug("🔄 F5 refresh: utilisation load_data() sync")
                    table_controller.load_data(search_term)

    @safe_operation("_handle_clear_search_shortcut")
    def _handle_clear_search_shortcut(self):
        """Traiter le raccourci Escape (Effacer recherche)"""
        if self.parent_window:
            advanced_search_service = getattr(self.parent_window, 'advanced_search_service', None)
            if advanced_search_service:
                advanced_search_service.clear_search_ui(self.parent_window)

    # === CONFIGURATION DYNAMIQUE ===

    @safe_operation("register_shortcut")
    def register_shortcut(self, key: int, action_name: str, description: str, with_modifier: bool = True):
        """Enregistrer un nouveau raccourci dynamiquement"""
        if with_modifier:
            self.shortcut_actions[key] = (action_name, description)
        else:
            self.function_key_shortcuts[key] = (action_name, description)

        app_logger.debug(f"🔧 Raccourci enregistré: {description} ({action_name})")

    @safe_operation("unregister_shortcut")
    def unregister_shortcut(self, key: int, with_modifier: bool = True):
        """Supprimer un raccourci"""
        if with_modifier and key in self.shortcut_actions:
            del self.shortcut_actions[key]
        elif not with_modifier and key in self.function_key_shortcuts:
            del self.function_key_shortcuts[key]

        app_logger.debug(f"🗑️ Raccourci supprimé: clé {key}")

    def get_registered_shortcuts(self) -> Dict[str, Dict]:
        """Obtenir la liste des raccourcis enregistrés"""
        return {
            "modifier_shortcuts": dict(self.shortcut_actions),
            "standard_shortcuts": dict(self.standard_shortcuts),
            "function_key_shortcuts": dict(self.function_key_shortcuts)
        }

    def enable_focus_constraint(self, key: int):
        """Activer une contrainte de focus pour un raccourci"""
        self.focus_dependent_shortcuts.add(key)

    def disable_focus_constraint(self, key: int):
        """Désactiver une contrainte de focus pour un raccourci"""
        self.focus_dependent_shortcuts.discard(key)