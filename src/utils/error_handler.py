"""
Gestion centralisée des erreurs par décorateurs.

Deux socles, et des décorateurs nommés par famille d'erreurs qui ne font que
les paramétrer (comportement figé par tests/unit/test_error_handler_comportement.py) :

- `handle_errors` : journalise via le logger « ErrorHandler » et, si demandé,
  affiche une fenêtre d'erreur détaillée ; les décorateurs « à message »
  (`handle_seo_data_errors`, `handle_save_service_errors`…) en sont des
  préréglages fabriqués par `_prereglage`.
- `_journaliser` : journalise via app_logger puis renvoie une valeur de repli,
  avec un éventuel complément (fenêtre d'erreur, signal, ligne de debug) ; les
  décorateurs « journalisants » (`handle_db_query_errors`,
  `handle_ui_operation_errors`…) en sont des variantes.

Usage :
    @handle_errors(title="Erreur de sauvegarde", return_on_error=False)
    @handle_export_errors(title="Erreur export CSV")
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde")
"""

import functools
import traceback
import logging
from typing import Callable, Any, Type, Tuple
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
                        from .qt_imports import QWidget
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

# ─── Préréglages de handle_errors ─────────────────────────────────────────────

def _prereglage(nom: str, doc: str, titre: str, message: str = None,
                afficher: bool = True, repli: Any = None):
    """Fabriquer un décorateur `nom(return_value=repli, title=titre)` qui applique
    handle_errors avec un message et un affichage fixés."""
    def fabrique(return_value=repli, title: str = titre):
        return handle_errors(title=title, message=message, show_message=afficher,
                             return_on_error=return_value)
    fabrique.__name__ = fabrique.__qualname__ = nom
    fabrique.__doc__ = doc
    return fabrique


def _prereglage_titre(nom: str, doc: str, titre: str, message: str = None,
                      repli: Any = None):
    """Variante à un seul paramètre, `nom(title=titre)` : valeur de repli fixe."""
    def fabrique(title: str = titre):
        return handle_errors(title=title, message=message, return_on_error=repli)
    fabrique.__name__ = fabrique.__qualname__ = nom
    fabrique.__doc__ = doc
    return fabrique


handle_database_errors = _prereglage_titre(
    'handle_database_errors', "Erreurs de base de données (fenêtre d'erreur, renvoie False).",
    "Erreur de base de données", repli=False)

handle_export_errors = _prereglage_titre(
    'handle_export_errors', "Erreurs d'export (fenêtre d'erreur, renvoie False).",
    "Erreur d'export", "Erreur lors de l'export des données.", repli=False)

handle_seo_generation_errors = _prereglage_titre(
    'handle_seo_generation_errors', "Erreurs de génération SEO (title / description).",
    "Erreur génération SEO",
    "Erreur lors de la génération du contenu SEO. Vérifiez les données de recherche.")

# Décorateurs « à message » : log via handle_errors, fenêtre d'erreur si afficher=True.

handle_seo_data_errors = _prereglage(
    'handle_seo_data_errors', 'Extraction des données SEO (log seulement).',
    'Erreur données SEO',
    "Erreur lors de l'extraction des données pour le SEO.",
    afficher=False)

handle_seo_dialog_errors = _prereglage(
    'handle_seo_dialog_errors', 'Dialogues SEO.',
    'Erreur dialogue SEO',
    "Erreur lors de l'affichage du dialogue de sélection.",
    afficher=True)

handle_save_service_errors = _prereglage(
    'handle_save_service_errors', 'Sauvegarde événementielle (log seulement, pas de fenêtre pour les sauvegardes).',
    'Erreur service sauvegarde',
    "Erreur lors de la sauvegarde. L'opération sera réessayée automatiquement.",
    afficher=False)

handle_logger_errors = _prereglage(
    'handle_logger_errors', 'Opérations du logger (log seulement, évite la récursion).',
    'Erreur logger',
    'Erreur lors de la lecture des logs.',
    afficher=False)

handle_event_bus_errors = _prereglage(
    'handle_event_bus_errors', "Bus d'événements (log seulement).",
    "Erreur bus d'événements",
    "Erreur lors de l'émission d'événement. Les autres listeners continueront.",
    afficher=False)

handle_cache_callback_errors = _prereglage(
    'handle_cache_callback_errors', "Callbacks d'invalidation de cache (log seulement).",
    'Erreur callback cache',
    "Erreur lors de l'exécution d'un callback d'invalidation de cache.",
    afficher=False)

handle_search_errors = _prereglage(
    'handle_search_errors', "Recherche (log seulement : l'interface est notifiée par signaux).",
    'Erreur recherche',
    "Erreur lors de l'exécution de la recherche.",
    afficher=False)

handle_event_handler_errors = _prereglage(
    'handle_event_handler_errors', "Gestionnaires d'événements (log seulement).",
    "Erreur gestionnaire d'événement",
    "Erreur lors de l'exécution d'un gestionnaire d'événement.",
    afficher=False)

handle_count_operation_errors = _prereglage(
    'handle_count_operation_errors', 'Comptages en base (log seulement, renvoie 0 par défaut).',
    'Erreur comptage',
    'Erreur lors du comptage en base de données.',
    afficher=False, repli=0)

handle_ui_update_errors = _prereglage(
    'handle_ui_update_errors', "Mises à jour d'interface (log seulement).",
    'Erreur mise à jour UI',
    "Erreur lors de la mise à jour de l'interface utilisateur.",
    afficher=False)

handle_navigation_errors = _prereglage(
    'handle_navigation_errors', 'Navigation et pagination (log seulement).',
    'Erreur navigation',
    'Erreur lors de la navigation ou pagination.',
    afficher=False)

handle_log_viewer_errors = _prereglage(
    'handle_log_viewer_errors', 'Visionneur de logs : lecture, analyse, affichage (log seulement).',
    'Erreur visionneur de logs',
    'Erreur lors du traitement des logs.',
    afficher=False)

handle_cleanup_preview_errors = _prereglage(
    'handle_cleanup_preview_errors', "Aperçu et application du nettoyage des doublons (fenêtre d'erreur).",
    'Erreur nettoyage doublons',
    'Erreur lors du nettoyage des doublons.',
    afficher=True)

handle_pieces_panel_errors = _prereglage(
    'handle_pieces_panel_errors', 'Panneau des pièces (log seulement).',
    'Erreur panneau des pièces',
    'Erreur lors de la mise à jour du panneau des pièces.',
    afficher=False)

handle_drag_operation_errors = _prereglage(
    'handle_drag_operation_errors', 'Glisser-déposer (log seulement).',
    'Erreur glisser-déposer',
    'Erreur lors des opérations de glisser-déposer.',
    afficher=False)

handle_data_management_errors = _prereglage(
    'handle_data_management_errors', 'Gestion des données (log seulement).',
    'Erreur gestion données',
    'Erreur lors de la gestion des données.',
    afficher=False)

handle_pdf_extraction_errors = _prereglage(
    'handle_pdf_extraction_errors', 'Extraction PDF (log seulement).',
    'Erreur extraction PDF',
    "Erreur lors de l'extraction des données PDF.",
    afficher=False)

_autocompletion = _prereglage(
    'handle_autocompletion_errors', "", "Erreur auto-complétion",
    "Erreur lors de la récupération des données d'auto-complétion.", False)


def handle_autocompletion_errors(return_value=None, title: str = "Erreur auto-complétion"):
    """Auto-complétion (log seulement) ; repli par défaut : liste vide."""
    return _autocompletion(return_value if return_value is not None else [], title)


# ─── Décorateurs journalisants (app_logger + valeur de repli) ────────────────

def _journaliser(log_prefix: str, return_value: Any = None,
                 complement: Callable = None):
    """Décorateur : journalise « {log_prefix}: {erreur} » via app_logger et
    renvoie `return_value`. `complement(args, func, e)`, s'il est fourni, est
    appelé ensuite (fenêtre d'erreur, signal, ligne de debug…)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from ..core.logger import app_logger
                app_logger.error(f"{log_prefix}: {e}")
                if complement is not None:
                    complement(args, func, e)
                return return_value
        return wrapper
    return decorator


def _fenetre_erreur(prefixe: str):
    """Complément : fenêtre d'erreur « {prefixe}{erreur} », parentée au widget
    décoré s'il en est un. Ne propage jamais (évite les erreurs en cascade)."""
    def complement(args, func, e):
        if not args:
            return
        try:
            from .qt_imports import QWidget
            from ..ui.message_helper import MessageHelper
            parent = args[0] if isinstance(args[0], QWidget) else None
            MessageHelper.show_error(parent, f"{prefixe}{e}")
        except Exception:
            pass
    return complement


def handle_db_query_errors(return_value=None, log_prefix="Erreur DB query"):
    """Requêtes DB renvoyant une valeur par défaut.
    Usage: @handle_db_query_errors(return_value=[], log_prefix="Erreur load_data")"""
    return _journaliser(log_prefix, return_value)


def handle_sqlite_column_errors(log_message="Erreur ajout colonne"):
    """Opérations SQLite de schéma (ALTER TABLE…) : renvoie False."""
    return _journaliser(log_message, False)


def handle_ui_column_errors(return_value="Colonne inconnue"):
    """Erreurs de colonnes UI.
    Usage: @handle_ui_column_errors(return_value="Colonne par défaut")"""
    return _journaliser("Erreur colonne UI", return_value)


def handle_ui_errors(log_prefix="Erreur UI", show_message=True, return_value=None):
    """Erreurs d'interface : log, puis fenêtre « Erreur: … » si demandé.
    Usage: @handle_ui_errors(log_prefix="Erreur mise à jour pagination", show_message=False)"""
    return _journaliser(log_prefix, return_value,
                        _fenetre_erreur("Erreur: ") if show_message else None)


def handle_table_operations_errors(log_prefix="Erreur opération table", show_message=False):
    """Opérations sur les tables : log, puis fenêtre « Erreur table: … » si demandé.
    Usage: @handle_table_operations_errors(log_prefix="Erreur mise à jour colonnes")"""
    return _journaliser(log_prefix, None,
                        _fenetre_erreur("Erreur table: ") if show_message else None)


def _emettre_error_occurred(args, func, e):
    """Complément : émettre le signal error_occurred de l'objet décoré, s'il en a un."""
    if args and hasattr(args[0], 'error_occurred'):
        signal = getattr(args[0], 'error_occurred')
        if hasattr(signal, 'emit'):
            signal.emit(str(e))


def handle_async_worker_errors(log_prefix="Erreur worker asynchrone", emit_signal=True):
    """Workers asynchrones : log, puis signal error_occurred si présent.
    Usage: @handle_async_worker_errors(log_prefix="Erreur DatabaseQueryWorker")"""
    return _journaliser(log_prefix, None, _emettre_error_occurred if emit_signal else None)


def _debug_classe(contexte: str):
    """Complément : ligne de debug « Erreur{contexte} dans Classe.méthode: … »."""
    def complement(args, func, e):
        if args and hasattr(args[0], '__class__'):
            from ..core.logger import app_logger
            app_logger.debug(
                f"Erreur{contexte} dans {args[0].__class__.__name__}.{func.__name__}: {e}")
    return complement


def handle_database_operation_errors(return_value=None, log_prefix="Erreur base de données"):
    """Opérations de base de données (CRUD, transactions).

    Usage:
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur sauvegarde")
    @handle_database_operation_errors(return_value={}, log_prefix="Erreur récupération")
    """
    return _journaliser(log_prefix, return_value, _debug_classe(""))


def handle_ui_operation_errors(return_value=None, log_prefix="Erreur opération UI"):
    """Opérations d'interface utilisateur (PyQt5, interactions).

    Usage:
    @handle_ui_operation_errors(return_value=False, log_prefix="Erreur UI")
    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur widget")
    """
    return _journaliser(log_prefix, return_value, _debug_classe(" UI"))
