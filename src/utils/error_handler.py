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
                if args and hasattr(args[0], parent_attr):
                    parent = getattr(args[0], parent_attr)
                elif args and hasattr(args[0], 'parent'):
                    parent = getattr(args[0], 'parent', None)
                elif args:
                    # Si c'est une méthode d'instance, utiliser self comme parent
                    parent = args[0] if hasattr(args[0], 'show') else None
                
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


def handle_network_errors(title: str = "Erreur réseau"):
    """
    Décorateur spécialisé pour les erreurs réseau
    """
    return handle_errors(
        title=title,
        message="Problème de connexion réseau. Vérifiez votre connexion.",
        exceptions=(ConnectionError, TimeoutError),
        return_on_error=None
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
            return f"✅ Toutes les opérations réussies ({self.successes}/{self.total_operations})"
        
        summary = f"📊 Résumé: {self.successes} succès, {len(self.errors)} échecs sur {self.total_operations} opérations\n\n"
        
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