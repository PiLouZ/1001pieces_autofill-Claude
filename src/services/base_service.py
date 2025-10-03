"""
Classe de base pour tous les services - Factorisation des patterns communs
Optimisation architecturale - Version 3.2.0+

Responsabilités:
- Patterns d'initialisation standardisés
- Gestion d'erreurs unifiée
- Signaux métier communs
- Logging standardisé
- Injection de dépendances
"""

from typing import List, Callable, Any, Optional
from ..ui.qt_imports import QObject, pyqtSignal, QTimer, QApplication

from ..core.logger import app_logger

class BaseService(QObject):
    """Classe de base abstraite pour tous les services avec patterns communs"""

    # Signaux standardisés pour tous les services
    operation_started = pyqtSignal(str)  # operation_name
    operation_completed = pyqtSignal(str, bool)  # operation_name, success
    operation_progress = pyqtSignal(str, int)  # operation_name, percentage
    error_occurred = pyqtSignal(str, str)  # context, error_message
    data_changed = pyqtSignal(str, object)  # operation_type, data
    validation_failed = pyqtSignal(str, list)  # operation, error_list

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self._required_services = []  # À définir dans les classes filles
        self._service_name = self.__class__.__name__

        # Services injectés automatiquement
        self.dialog_service = None
        self.user_interaction_service = None

        app_logger.info(f"✅ {self._service_name} initialisé")

    def initialize_services(self):
        """
        Pattern d'initialisation standardisé pour tous les services
        Les services enfants définissent _required_services pour l'injection automatique
        """
        if not self.parent_window:
            app_logger.warning(f"⚠️ {self._service_name}: parent_window non défini")
            return

        try:
            # Injection automatique des services requis
            for service_name in self._required_services:
                service = getattr(self.parent_window, service_name, None)
                setattr(self, service_name, service)
                if service is None:
                    app_logger.warning(f"⚠️ Service '{service_name}' non trouvé pour {self._service_name}")

            # Services communs toujours injectés
            self.dialog_service = getattr(self.parent_window, 'dialog_service', None)
            self.user_interaction_service = getattr(self.parent_window, 'user_interaction_service', None)

            # Appeler la méthode d'initialisation spécifique si elle existe
            if hasattr(self, '_initialize_specific_services'):
                self._initialize_specific_services()

            app_logger.info(f"🔧 {self._service_name}: Services initialisés")

        except Exception as e:
            app_logger.error(f"❌ Erreur initialisation services {self._service_name}: {e}")

    def inject_required_services(self):
        """
        Injection automatique des services requis
        Méthode séparée pour permettre l'appel depuis initialize_services() des enfants
        """
        if not self.parent_window:
            app_logger.warning(f"⚠️ {self._service_name}: parent_window non défini pour injection")
            return

        try:
            # Injection automatique des services requis
            for service_name in self._required_services:
                service = getattr(self.parent_window, service_name, None)
                setattr(self, service_name, service)
                if service is None:
                    app_logger.warning(f"⚠️ Service '{service_name}' non trouvé pour {self._service_name}")

            # Services communs toujours injectés
            self.dialog_service = getattr(self.parent_window, 'dialog_service', None)
            self.user_interaction_service = getattr(self.parent_window, 'user_interaction_service', None)

            app_logger.debug(f"🔧 {self._service_name}: Services injectés automatiquement")

        except Exception as e:
            app_logger.error(f"❌ Erreur injection services {self._service_name}: {e}")

    def handle_error(self, error: Exception, context: str, show_dialog: bool = True) -> None:
        """
        Gestion d'erreurs standardisée pour tous les services

        Args:
            error: Exception capturée
            context: Contexte de l'erreur (ex: "sauvegarde", "chargement")
            show_dialog: Afficher une boîte de dialogue à l'utilisateur
        """
        try:
            error_msg = f"❌ Erreur {context} dans {self._service_name}: {error}"
            app_logger.error(error_msg)

            # Émettre le signal d'erreur
            self.error_occurred.emit(context, str(error))

            # Afficher le dialogue si demandé et disponible
            if show_dialog:
                if self.user_interaction_service:
                    self.user_interaction_service.show_error(f"Erreur {context}", str(error))
                elif self.dialog_service:
                    self.dialog_service.show_error(f"Erreur {context}", str(error))

        except Exception as meta_error:
            # Erreur dans la gestion d'erreur - log seulement
            app_logger.critical(f"💥 Erreur critique dans handle_error de {self._service_name}: {meta_error}")

    def handle_error_with_return(self, error: Exception, context: str, return_value=None, show_dialog: bool = False):
        """
        Gestion d'erreurs avec retour de valeur (pattern fréquent)

        Args:
            error: Exception capturée
            context: Contexte de l'erreur
            return_value: Valeur à retourner (par défaut None)
            show_dialog: Afficher une boîte de dialogue

        Returns:
            return_value (généralement None)
        """
        self.handle_error(error, context, show_dialog)
        return return_value

    def handle_error_with_result(self, error: Exception, context: str, success: bool = False, count: int = 0, extra_fields: dict = None):
        """
        Gestion d'erreurs avec retour d'objet résultat (pattern export/import)

        Args:
            error: Exception capturée
            context: Contexte de l'erreur
            success: État de succès (False par défaut)
            count: Nombre d'éléments traités
            extra_fields: Champs additionnels pour le résultat

        Returns:
            Dict: Objet résultat standardisé
        """
        self.handle_error(error, context)
        result = {
            'success': success,
            'error': str(error),
            'count': count
        }
        if extra_fields:
            result.update(extra_fields)
        return result

    def log_operation(self, operation: str, message: str, level: str = "debug") -> None:
        """
        Logging standardisé avec préfixe de service

        Args:
            operation: Nom de l'opération
            message: Message à logger
            level: Niveau de log (debug, info, warning, error)
        """
        try:
            formatted_msg = f"{self._service_name}.{operation}: {message}"

            if level == "debug":
                app_logger.debug(formatted_msg)
            elif level == "info":
                app_logger.info(formatted_msg)
            elif level == "warning":
                app_logger.warning(formatted_msg)
            elif level == "error":
                app_logger.error(formatted_msg)

        except Exception as e:
            app_logger.error(f"❌ Erreur de logging dans {self._service_name}: {e}")

    def emit_operation_started(self, operation: str) -> None:
        """Émettre le signal de début d'opération"""
        self.operation_started.emit(operation)
        self.log_operation(operation, "démarrée", "debug")

    def emit_operation_completed(self, operation: str, success: bool) -> None:
        """Émettre le signal de fin d'opération"""
        self.operation_completed.emit(operation, success)
        status = "réussie" if success else "échouée"
        level = "debug" if success else "warning"
        self.log_operation(operation, f"terminée ({status})", level)

    def emit_progress(self, operation: str, percentage: int) -> None:
        """Émettre le signal de progression"""
        self.operation_progress.emit(operation, max(0, min(100, percentage)))

    def emit_data_changed(self, operation_type: str, data: Any) -> None:
        """Émettre le signal de changement de données"""
        self.data_changed.emit(operation_type, data)

    def emit_validation_failed(self, operation: str, errors: List[str]) -> None:
        """Émettre le signal d'échec de validation"""
        self.validation_failed.emit(operation, errors)
        self.log_operation(operation, f"validation échouée: {errors}", "warning")

    def get_service_state(self) -> dict:
        """Retourner l'état actuel du service pour debugging"""
        return {
            "service_name": self._service_name,
            "parent_window_available": self.parent_window is not None,
            "required_services": self._required_services,
            "services_initialized": all(
                getattr(self, service, None) is not None
                for service in self._required_services
            ),
            "dialog_service_available": self.dialog_service is not None,
            "user_interaction_service_available": self.user_interaction_service is not None
        }

class DebounceTimer(QTimer):
    """
    Timer réutilisable avec pattern debounce pour optimiser les performances
    Évite les appels répétitifs lors d'événements rapides (typing, filtering, etc.)
    """

    def __init__(self, callback: Callable, delay_ms: int = 300, parent=None):
        super().__init__(parent)
        self.setSingleShot(True)
        self.timeout.connect(callback)
        self.delay_ms = delay_ms
        self.callback = callback

        app_logger.debug(f"🕐 DebounceTimer créé avec délai {delay_ms}ms")

    def trigger(self) -> None:
        """Déclencher le timer avec debounce"""
        self.stop()  # Arrêter le timer précédent s'il existe
        self.start(self.delay_ms)

    def set_delay(self, delay_ms: int) -> None:
        """Modifier le délai de debounce"""
        self.delay_ms = delay_ms

    def force_execute(self) -> None:
        """Forcer l'exécution immédiate sans attendre le délai"""
        self.stop()
        if self.callback:
            self.callback()

def service_operation(operation_name: str, emit_signals: bool = True):
    """
    Décorateur pour standardiser les opérations de service avec gestion d'erreurs

    Args:
        operation_name: Nom de l'opération pour le logging et les signaux
        emit_signals: Émettre les signaux de début/fin d'opération

    Usage:
        @service_operation("sauvegarder_donnees")
        def save_data(self, data):
            # logique métier
            return result
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(self, *args, **kwargs):
            if not isinstance(self, BaseService):
                raise TypeError("Le décorateur @service_operation ne peut être utilisé que sur des BaseService")

            try:
                if emit_signals:
                    self.emit_operation_started(operation_name)

                result = func(self, *args, **kwargs)

                if emit_signals:
                    self.emit_operation_completed(operation_name, True)

                return result

            except Exception as e:
                self.handle_error(e, operation_name)

                if emit_signals:
                    self.emit_operation_completed(operation_name, False)

                return None

        return wrapper
    return decorator

def safe_operation(operation_name: str, default_return: Any = None):
    """
    Décorateur léger pour helpers internes avec gestion d'erreurs silencieuse

    Args:
        operation_name: Nom de l'opération pour le logging
        default_return: Valeur à retourner en cas d'erreur (None par défaut)

    Usage:
        @safe_operation("parse_data", default_return=[])
        def _safe_parse_data(self, data):
            # logique métier
            return result
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                # Log uniquement, pas d'interaction utilisateur
                error_msg = f"Erreur {operation_name}: {e}"
                app_logger.error(f"{self._service_name}.{error_msg}")
                return default_return

        return wrapper
    return decorator

class ServiceFactory:
    """
    Factory pour la création et l'injection de dépendances entre services
    Centralise la configuration des services
    """

    @staticmethod
    def create_service(service_class: type, parent_window, **kwargs) -> BaseService:
        """
        Créer un service avec injection automatique des dépendances

        Args:
            service_class: Classe du service à créer
            parent_window: Fenêtre parent pour l'injection
            **kwargs: Arguments supplémentaires pour le constructeur

        Returns:
            Instance du service configurée
        """
        try:
            # Créer l'instance
            service = service_class(parent_window=parent_window, **kwargs)

            # Initialiser les services automatiquement
            service.initialize_services()

            app_logger.info(f"🏭 ServiceFactory: {service_class.__name__} créé et configuré")

            return service

        except Exception as e:
            app_logger.error(f"❌ Erreur création service {service_class.__name__}: {e}")
            raise

    @staticmethod
    def inject_dependencies(service: BaseService, parent_window) -> None:
        """
        Injecter les dépendances dans un service existant

        Args:
            service: Service à configurer
            parent_window: Fenêtre parent pour l'injection
        """
        try:
            service.parent_window = parent_window
            service.initialize_services()

            app_logger.debug(f"🔧 ServiceFactory: Dépendances injectées dans {service._service_name}")

        except Exception as e:
            app_logger.error(f"❌ Erreur injection dépendances {service._service_name}: {e}")
            raise