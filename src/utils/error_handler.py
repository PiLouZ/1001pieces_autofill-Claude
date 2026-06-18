"""
🛡️ ErrorHandler - Décorateur centralisé pour la gestion d'erreurs
Élimine la duplication des 295 blocs try/catch dans le projet
"""

import functools
import traceback
import logging
from typing import Callable, Optional, Union, Any, Type, Tuple
from ..ui.message_helper import MessageHelper
from ..core.constants import Messages

# Configuration du logger pour les erreurs
error_logger = logging.getLogger('ErrorHandler')

class ErrorHandlerConfig:
    """Configuration pour le gestionnaire d'erreurs"""
    SHOW_TRACEBACK_IN_DETAILS = True
    LOG_ALL_ERRORS = True
    DEFAULT_ERROR_TITLE = Messages.TITLE_ERROR
    DEFAULT_SUCCESS_TITLE = Messages.TITLE_SUCCESS

def handle_errors(
    title: str = ErrorHandlerConfig.DEFAULT_ERROR_TITLE,
    message: str = None,
    show_message: bool = True,
    log_error: bool = True,
    return_on_error: Any = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    parent_attr: str = "main_window"
):
    """
    Décorateur pour la gestion centralisée des erreurs
    
    Args:
        title: Titre du message d'erreur
        message: Message d'erreur personnalisé (None = utiliser str(exception))
        show_message: Afficher un message à l'utilisateur
        log_error: Enregistrer l'erreur dans les logs
        return_on_error: Valeur à retourner en cas d'erreur
        exceptions: Types d'exceptions à capturer
        parent_attr: Nom de l'attribut parent pour les messages (self.main_window, self.parent, etc.)
    
    Usage:
        @handle_errors()
        def ma_methode(self):
            # Code pouvant lever des exceptions
            pass
            
        @handle_errors(title="Erreur de sauvegarde", return_on_error=False)
        def save_data(self):
            # Code de sauvegarde
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                # Récupérer le parent pour afficher les messages
                parent = None
                if args:
                    # Si c'est une méthode d'instance d'un QWidget, utiliser self comme parent
                    try:
                        from ..ui.qt_imports import QWidget
                        if isinstance(args[0], QWidget):
                            parent = args[0]
                        else:
                            # Sinon, chercher l'attribut parent_attr
                            if hasattr(args[0], parent_attr):
                                potential_parent = getattr(args[0], parent_attr)
                                # Vérifier que c'est un widget et pas une fonction
                                if callable(potential_parent):
                                    parent = None  # Éviter les fonctions
                                elif isinstance(potential_parent, QWidget):
                                    parent = potential_parent
                                else:
                                    parent = None
                            elif hasattr(args[0], 'parent'):
                                potential_parent = getattr(args[0], 'parent', None)
                                if isinstance(potential_parent, QWidget):
                                    parent = potential_parent
                                else:
                                    parent = None
                            else:
                                parent = None
                    except ImportError:
                        parent = None
                
                # Message d'erreur
                error_msg = message or str(e)
                
                # Log de l'erreur
                if log_error:
                    error_logger.error(
                        f"Erreur dans {func.__name__}: {error_msg}",
                        exc_info=True
                    )
                
                # Affichage du message utilisateur
                if show_message:
                    if ErrorHandlerConfig.SHOW_TRACEBACK_IN_DETAILS:
                        details = traceback.format_exc()
                        MessageHelper.show_detailed_error(parent, error_msg, details, title)
                    else:
                        MessageHelper.show_error(parent, error_msg, title)
                
                return return_on_error
        
        return wrapper
    return decorator

def handle_database_errors(title: str = "Erreur de base de données"):
    """
    Décorateur spécialisé pour les erreurs de base de données
    """
    return handle_errors(
        title=title,
        exceptions=(Exception,),  # Capture toutes les erreurs DB
        return_on_error=False
    )

def handle_db_query_errors(return_value=None, log_prefix="Erreur DB query"):
    """
    Décorateur spécialisé pour les requêtes DB retournant une valeur par défaut
    Usage: @handle_db_query_errors(return_value=[], log_prefix="Erreur load_data")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")
                return return_value
        return wrapper
    return decorator

def handle_db_signal_errors(error_signal_name="error_occurred"):
    """
    Décorateur spécialisé pour les méthodes émettant des signaux en cas d'erreur
    Usage: @handle_db_signal_errors(error_signal_name="error_occurred")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"Erreur {func.__name__}: {e}")

                # Émettre le signal d'erreur si l'objet l'a
                if args and hasattr(args[0], error_signal_name):
                    error_signal = getattr(args[0], error_signal_name)
                    if hasattr(error_signal, 'emit'):
                        error_signal.emit(str(e))
                return None
        return wrapper
    return decorator

def handle_sqlite_column_errors(log_message="Erreur ajout colonne"):
    """
    Décorateur spécialisé pour les opérations SQLite (ALTER TABLE, etc.)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:  # Inclut sqlite3.OperationalError
                from ..core.logger import app_logger
                app_logger.error(f"{log_message}: {e}")
                return False
        return wrapper
    return decorator

def handle_ui_errors(log_prefix="Erreur UI", show_message=True, return_value=None):
    """
    Décorateur spécialisé pour les erreurs d'interface utilisateur
    Usage: @handle_ui_errors(log_prefix="Erreur mise à jour pagination", show_message=False)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")

                # Afficher message utilisateur si demandé
                if show_message and args:
                    try:
                        from ..ui.qt_imports import QWidget
                        from ..ui.message_helper import MessageHelper

                        # Trouver le widget parent pour afficher l'erreur
                        parent = None
                        if isinstance(args[0], QWidget):
                            parent = args[0]

                        MessageHelper.show_error(parent, f"Erreur: {e}")
                    except Exception:
                        pass  # Éviter erreur en cascade

                return return_value
        return wrapper
    return decorator

def handle_ui_column_errors(return_value="Colonne inconnue"):
    """
    Décorateur spécialisé pour les erreurs de colonnes UI
    Usage: @handle_ui_column_errors(return_value="Colonne par défaut")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"Erreur colonne UI: {e}")
                return return_value
        return wrapper
    return decorator

def handle_table_operations_errors(log_prefix="Erreur opération table", show_message=False):
    """
    Décorateur spécialisé pour les erreurs d'opérations sur les tables
    Usage: @handle_table_operations_errors(log_prefix="Erreur mise à jour colonnes")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")

                # Optionnel: afficher message si demandé
                if show_message and args:
                    try:
                        from ..ui.qt_imports import QWidget
                        from ..ui.message_helper import MessageHelper

                        parent = None
                        if isinstance(args[0], QWidget):
                            parent = args[0]

                        MessageHelper.show_error(parent, f"Erreur table: {e}")
                    except Exception:
                        pass

                return None
        return wrapper
    return decorator

def handle_async_worker_errors(log_prefix="Erreur worker asynchrone", emit_signal=True):
    """
    Décorateur spécialisé pour les erreurs de workers asynchrones
    Usage: @handle_async_worker_errors(log_prefix="Erreur DatabaseQueryWorker")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")

                # Émettre signal d'erreur si l'objet l'a
                if emit_signal and args and hasattr(args[0], 'error_occurred'):
                    error_signal = getattr(args[0], 'error_occurred')
                    if hasattr(error_signal, 'emit'):
                        error_signal.emit(str(e))

                return None
        return wrapper
    return decorator

def handle_file_errors(title: str = "Erreur de fichier"):
    """
    Décorateur spécialisé pour les erreurs de fichiers
    """
    return handle_errors(
        title=title,
        exceptions=(IOError, OSError, FileNotFoundError, PermissionError),
        return_on_error=None
    )

def handle_import_errors(title: str = "Erreur d'import"):
    """
    Décorateur spécialisé pour les erreurs d'import
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'import des données. Vérifiez le format du fichier.",
        return_on_error=None
    )

def handle_export_errors(title: str = "Erreur d'export"):
    """
    Décorateur spécialisé pour les erreurs d'export  
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'export des données.",
        return_on_error=False
    )

def handle_validation_errors(title: str = "Erreur de validation"):
    """
    Décorateur spécialisé pour les erreurs de validation
    """
    return handle_errors(
        title=title,
        exceptions=(ValueError, TypeError),
        return_on_error=None
    )

def handle_seo_generation_errors(title: str = "Erreur génération SEO"):
    """
    Décorateur spécialisé pour les erreurs de génération SEO (title/description)
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la génération du contenu SEO. Vérifiez les données de recherche.",
        show_message=True,
        return_on_error=None
    )

def handle_seo_data_errors(return_value=None, title: str = "Erreur données SEO"):
    """
    Décorateur spécialisé pour les erreurs d'extraction de données SEO
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'extraction des données pour le SEO.",
        show_message=False,  # Pas de popup, juste logs
        return_on_error=return_value
    )

def handle_seo_dialog_errors(return_value=None, title: str = "Erreur dialogue SEO"):
    """
    Décorateur spécialisé pour les erreurs des dialogues SEO
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'affichage du dialogue de sélection.",
        show_message=True,
        return_on_error=return_value
    )


def handle_save_service_errors(return_value=None, title: str = "Erreur service sauvegarde"):
    """
    Décorateur spécialisé pour les services de sauvegarde événementielle
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la sauvegarde. L'opération sera réessayée automatiquement.",
        show_message=False,  # Logging seulement, pas de popup pour les saves
        return_on_error=return_value
    )

def handle_logger_errors(return_value=None, title: str = "Erreur logger"):
    """
    Décorateur spécialisé pour les opérations de logger
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la lecture des logs.",
        show_message=False,  # Logging seulement pour éviter récursion
        return_on_error=return_value
    )

def handle_auto_save_errors(return_value=None, title: str = "Erreur sauvegarde automatique"):
    """
    Décorateur spécialisé pour les opérations d'auto-sauvegarde
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la sauvegarde automatique. Les modifications seront sauvegardées au prochain cycle.",
        show_message=True,  # Afficher à l'utilisateur pour les erreurs d'auto-save
        return_on_error=return_value
    )

def handle_event_bus_errors(return_value=None, title: str = "Erreur bus d'événements"):
    """
    Décorateur spécialisé pour les opérations du bus d'événements
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'émission d'événement. Les autres listeners continueront.",
        show_message=False,  # Logging seulement pour éviter spam
        return_on_error=return_value
    )

def handle_cache_callback_errors(return_value=None, title: str = "Erreur callback cache"):
    """
    Décorateur spécialisé pour les callbacks d'invalidation de cache
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'exécution d'un callback d'invalidation de cache.",
        show_message=False,  # Logging seulement pour éviter spam
        return_on_error=return_value
    )

def handle_autocompletion_errors(return_value=None, title: str = "Erreur auto-complétion"):
    """
    Décorateur spécialisé pour les opérations d'auto-complétion
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la récupération des données d'auto-complétion.",
        show_message=False,  # Logging seulement pour ne pas gêner l'utilisateur
        return_on_error=return_value if return_value is not None else []
    )

def handle_search_errors(return_value=None, title: str = "Erreur recherche"):
    """
    Décorateur spécialisé pour les opérations de recherche
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'exécution de la recherche.",
        show_message=False,  # Utilise les signaux pour notifier l'UI
        return_on_error=return_value
    )

def handle_highlight_errors(return_value=False, title: str = "Erreur mise en évidence"):
    """
    Décorateur spécialisé pour les opérations de mise en évidence de recherche
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la mise en évidence de recherche.",
        show_message=False,  # Logging seulement pour ne pas gêner l'utilisateur
        return_on_error=return_value
    )

def handle_event_handler_errors(return_value=None, title: str = "Erreur gestionnaire d'événement"):
    """
    Décorateur spécialisé pour les gestionnaires d'événements
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'exécution d'un gestionnaire d'événement.",
        show_message=False,  # Logging seulement pour éviter spam
        return_on_error=return_value
    )

def handle_count_operation_errors(return_value=0, title: str = "Erreur comptage"):
    """
    Décorateur spécialisé pour les opérations de comptage de base de données
    """
    return handle_errors(
        title=title,
        message="Erreur lors du comptage en base de données.",
        show_message=False,  # Logging seulement pour les opérations de comptage
        return_on_error=return_value
    )

def handle_ui_update_errors(return_value=None, title: str = "Erreur mise à jour UI"):
    """
    Décorateur spécialisé pour les mises à jour d'interface utilisateur
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la mise à jour de l'interface utilisateur.",
        show_message=False,  # Logging seulement pour ne pas gêner l'utilisateur
        return_on_error=return_value
    )

def handle_navigation_errors(return_value=None, title: str = "Erreur navigation"):
    """
    Décorateur spécialisé pour les opérations de navigation et pagination
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la navigation ou pagination.",
        show_message=False,  # Logging seulement pour les erreurs de navigation
        return_on_error=return_value
    )

class SafeOperation:
    """
    Context manager pour les opérations sécurisées
    Alternative au décorateur pour les blocs de code
    
    Usage:
        with SafeOperation(self, "Erreur de traitement") as safe:
            # Code pouvant lever des exceptions
            result = operation_dangereuse()
            safe.set_result(result)
        
        if safe.success:
            print(f"Succès: {safe.result}")
        else:
            print(f"Échec: {safe.error}")
    """
    
    def __init__(self, parent=None, error_title: str = ErrorHandlerConfig.DEFAULT_ERROR_TITLE, 
                 show_message: bool = True, log_error: bool = True):
        self.parent = parent
        self.error_title = error_title
        self.show_message = show_message
        self.log_error = log_error
        
        self.success = False
        self.error = None
        self.result = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Une exception s'est produite
            self.success = False
            self.error = str(exc_val)
            
            # Log de l'erreur
            if self.log_error:
                error_logger.error(f"Erreur dans SafeOperation: {self.error}", exc_info=True)
            
            # Message utilisateur
            if self.show_message:
                if ErrorHandlerConfig.SHOW_TRACEBACK_IN_DETAILS:
                    details = ''.join(traceback.format_exception(exc_type, exc_val, exc_tb))
                    MessageHelper.show_detailed_error(self.parent, self.error, details, self.error_title)
                else:
                    MessageHelper.show_error(self.parent, self.error, self.error_title)
            
            # Supprimer l'exception pour éviter qu'elle se propage
            return True
        else:
            # Aucune exception
            self.success = True
    
    def set_result(self, result: Any):
        """Définir le résultat de l'opération"""
        self.result = result

class ErrorReporter:
    """
    Collecteur d'erreurs pour les opérations en lot
    Utile pour traiter plusieurs éléments et rapporter tous les échecs
    """
    
    def __init__(self, parent=None):
        self.parent = parent
        self.errors = []
        self.successes = 0
        self.total_operations = 0
    
    def run_operation(self, operation: Callable, operation_name: str = "", *args, **kwargs) -> Any:
        """
        Exécuter une opération et enregistrer le résultat
        
        Args:
            operation: Fonction à exécuter
            operation_name: Nom descriptif de l'opération
            *args, **kwargs: Arguments pour l'opération
            
        Returns:
            Résultat de l'opération ou None en cas d'échec
        """
        self.total_operations += 1
        
        try:
            result = operation(*args, **kwargs)
            self.successes += 1
            return result
        except Exception as e:
            error_info = {
                'operation': operation_name or operation.__name__,
                'error': str(e),
                'args': args,
                'kwargs': kwargs
            }
            self.errors.append(error_info)
            
            # Log de l'erreur
            error_logger.error(
                f"Erreur dans {error_info['operation']}: {error_info['error']}",
                exc_info=True
            )
            
            return None
    
    def get_summary(self) -> str:
        """Obtenir un résumé des opérations"""
        if not self.errors:
            return f"Toutes les opérations réussies ({self.successes}/{self.total_operations})"

        summary = f"Résumé: {self.successes} succès, {len(self.errors)} échecs sur {self.total_operations} opérations\n\n"
        
        for i, error in enumerate(self.errors, 1):
            summary += f"{i}. {error['operation']}: {error['error']}\n"
        
        return summary
    
    def show_summary(self, title: str = "Résumé des opérations"):
        """Afficher le résumé à l'utilisateur"""
        summary = self.get_summary()
        
        if self.errors:
            MessageHelper.show_warning(self.parent, summary, title)
        else:
            MessageHelper.show_success(self.parent, summary, title)

# Fonctions utilitaires pour les cas d'usage courants
def safe_execute(operation: Callable, parent=None, error_title: str = "Erreur", 
                default_return: Any = None, *args, **kwargs) -> Any:
    """
    Exécuter une opération de manière sécurisée
    
    Usage:
        result = safe_execute(fonction_dangereuse, self, "Erreur custom", default_value, arg1, arg2)
    """
    try:
        return operation(*args, **kwargs)
    except Exception as e:
        error_logger.error(f"Erreur dans safe_execute: {str(e)}", exc_info=True)
        MessageHelper.show_error(parent, str(e), error_title)
        return default_return

def safe_call_method(obj, method_name: str, *args, **kwargs) -> Any:
    """
    Appeler une méthode de manière sécurisée
    
    Usage:
        result = safe_call_method(mon_objet, "ma_methode", arg1, arg2)
    """
    try:
        method = getattr(obj, method_name)
        return method(*args, **kwargs)
    except AttributeError:
        error_logger.error(f"Méthode {method_name} non trouvée sur {type(obj)}")
        return None
    except Exception as e:
        error_logger.error(f"Erreur lors de l'appel de {method_name}: {str(e)}", exc_info=True)
        return None

def handle_paste_results_errors(return_value=None, title: str = "Erreur résultats collage"):
    """
    Décorateur pour gérer les erreurs lors de l'affichage/logging des résultats de collage
    """
    return handle_errors(
        title=title,
        message="Erreur lors du traitement des résultats de collage.",
        show_message=False,
        return_on_error=return_value
    )

def handle_log_viewer_errors(return_value=None, title: str = "Erreur visionneur de logs"):
    """
    Décorateur pour gérer les erreurs dans le visionneur de logs (lecture, parsing, affichage)
    """
    return handle_errors(
        title=title,
        message="Erreur lors du traitement des logs.",
        show_message=False,
        return_on_error=return_value
    )

def handle_cleanup_preview_errors(return_value=None, title: str = "Erreur nettoyage doublons"):
    """
    Décorateur pour gérer les erreurs dans la prévisualisation et application du nettoyage des doublons
    """
    return handle_errors(
        title=title,
        message="Erreur lors du nettoyage des doublons.",
        show_message=True,  # Afficher car l'utilisateur doit être informé
        return_on_error=return_value
    )

def handle_pieces_panel_errors(return_value=None, title: str = "Erreur panneau des pièces"):
    """
    Décorateur pour gérer les erreurs dans la gestion du panneau des pièces
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la mise à jour du panneau des pièces.",
        show_message=False,
        return_on_error=return_value
    )

def handle_drag_operation_errors(return_value=None, title: str = "Erreur glisser-déposer"):
    """
    Décorateur spécialisé pour les erreurs de glisser-déposer
    """
    return handle_errors(
        title=title,
        message="Erreur lors des opérations de glisser-déposer.",
        show_message=False,
        return_on_error=return_value
    )

def handle_data_management_errors(return_value=None, title: str = "Erreur gestion données"):
    """
    Décorateur spécialisé pour les erreurs de gestion des données
    """
    return handle_errors(
        title=title,
        message="Erreur lors de la gestion des données.",
        show_message=False,
        return_on_error=return_value
    )

def handle_pdf_extraction_errors(return_value=None, title: str = "Erreur extraction PDF"):
    """
    Décorateur spécialisé pour les erreurs d'extraction PDF
    """
    return handle_errors(
        title=title,
        message="Erreur lors de l'extraction des données PDF.",
        show_message=False,
        return_on_error=return_value
    )

# Exemples d'utilisation dans les commentaires
"""
EXEMPLES D'UTILISATION:

1. Décorateur simple:
    @handle_errors()
    def ma_fonction(self):
        # Code pouvant lever des exceptions
        pass

2. Décorateur avec configuration:
    @handle_errors(title="Erreur de sauvegarde", return_on_error=False)
    def save_data(self):
        # Code de sauvegarde
        pass

3. Context manager:
    with SafeOperation(self, "Erreur de traitement") as safe:
        result = operation_complexe()
        safe.set_result(result)
    
    if safe.success:
        print(safe.result)

4. Traitement en lot:
    reporter = ErrorReporter(self)
    
    for item in items:
        reporter.run_operation(process_item, f"Traitement {item}", item)
    
    reporter.show_summary("Traitement terminé")

5. Exécution sécurisée:
    result = safe_execute(fonction_dangereuse, self, "Erreur", valeur_par_defaut, arg1, arg2)
"""

def handle_database_operation_errors(return_value=None, log_prefix="Erreur base de données"):
    """
    Décorateur spécialisé pour les erreurs d'opérations de base de données
    Adapté aux opérations CRUD et transactions.

    Usage:
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde")
    @handle_database_operation_errors(return_value={}, log_prefix="Erreur récupération")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")

                # Pour les services de base de données, log des détails supplémentaires
                if args and hasattr(args[0], '__class__'):
                    class_name = args[0].__class__.__name__
                    app_logger.debug(f"Erreur dans {class_name}.{func.__name__}: {e}")

                return return_value
        return wrapper
    return decorator

def handle_ui_operation_errors(return_value=None, log_prefix="Erreur opération UI"):
    """
    Décorateur spécialisé pour les erreurs d'opérations d'interface utilisateur
    Adapté aux opérations PyQt5 et interactions UI.

    Usage:
    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur UI")
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur widget")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")

                # Pour les opérations UI, log des détails supplémentaires
                if args and hasattr(args[0], '__class__'):
                    class_name = args[0].__class__.__name__
                    app_logger.debug(f"Erreur UI dans {class_name}.{func.__name__}: {e}")

                return return_value
        return wrapper
    return decorator