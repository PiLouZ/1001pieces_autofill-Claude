"""
Comportement figé des décorateurs de src/utils/error_handler.py

Chaque décorateur, sous chacune des formes d'appel utilisées dans le code, est
appliqué à une fonction qui lève une exception. On relève ce qu'il fait :
valeur renvoyée, lignes de log (app_logger et logger « ErrorHandler »), fenêtre
d'erreur (MessageHelper), signal error_occurred. Le tableau ATTENDU a été
relevé sur l'implémentation d'avant la factorisation (v3.100.0) : il garantit
que la fabrique commune reproduit exactement chaque décorateur.
"""

import pytest
from unittest.mock import patch, MagicMock

import src.utils.error_handler as eh


class _Objet:
    """Instance non-QWidget, avec un signal error_occurred factice."""
    def __init__(self):
        self.error_occurred = MagicMock()


CAS = [
    ('handle_errors', {}),
    ('handle_errors', {'title': 'T', 'message': 'M', 'show_message': False, 'return_on_error': 7}),
    ('handle_database_errors', {}),
    ('handle_database_errors', {'title': 'T'}),
    ('handle_db_query_errors', {}),
    ('handle_db_query_errors', {'return_value': [], 'log_prefix': 'P'}),
    ('handle_sqlite_column_errors', {}),
    ('handle_sqlite_column_errors', {'log_message': 'P'}),
    ('handle_ui_errors', {}),
    ('handle_ui_errors', {'log_prefix': 'P', 'show_message': False}),
    ('handle_ui_errors', {'log_prefix': 'P', 'show_message': True, 'return_value': 3}),
    ('handle_ui_column_errors', {}),
    ('handle_ui_column_errors', {'return_value': 'X'}),
    ('handle_table_operations_errors', {}),
    ('handle_table_operations_errors', {'log_prefix': 'P', 'show_message': True}),
    ('handle_async_worker_errors', {}),
    ('handle_async_worker_errors', {'log_prefix': 'P', 'emit_signal': False}),
    ('handle_export_errors', {}),
    ('handle_export_errors', {'title': 'T'}),
    ('handle_seo_generation_errors', {}),
    ('handle_database_operation_errors', {}),
    ('handle_database_operation_errors', {'return_value': False, 'log_prefix': 'P'}),
    ('handle_ui_operation_errors', {}),
    ('handle_ui_operation_errors', {'return_value': 0, 'log_prefix': 'P'}),
] + [
    (nom, kw) for nom in (
        'handle_seo_data_errors', 'handle_seo_dialog_errors', 'handle_save_service_errors',
        'handle_logger_errors', 'handle_event_bus_errors', 'handle_cache_callback_errors',
        'handle_autocompletion_errors', 'handle_search_errors', 'handle_event_handler_errors',
        'handle_count_operation_errors', 'handle_ui_update_errors', 'handle_navigation_errors',
        'handle_log_viewer_errors', 'handle_cleanup_preview_errors', 'handle_pieces_panel_errors',
        'handle_drag_operation_errors', 'handle_data_management_errors',
        'handle_pdf_extraction_errors')
    for kw in ({}, {'return_value': 5, 'title': 'T'})
]


def observer(nom, kwargs):
    """Appliquer le décorateur à une fonction qui lève, relever ses effets."""
    decorateur = getattr(eh, nom)(**kwargs)

    @decorateur
    def methode(self):
        raise ValueError("boum")

    obj = _Objet()
    app_logger = MagicMock()
    with patch('src.core.logger.app_logger', app_logger), \
            patch.object(eh, 'error_logger') as error_logger, \
            patch('src.ui.message_helper.MessageHelper.show_error') as show_error, \
            patch('src.ui.message_helper.MessageHelper.show_detailed_error') as show_detailed:
        retour = methode(obj)

    def appels(m):
        return [tuple(a for a in c.args if not isinstance(a, _Objet)) for c in m.call_args_list]

    return {
        'retour': retour,
        'app_error': appels(app_logger.error),
        'app_debug': appels(app_logger.debug),
        'eh_error': appels(error_logger.error),
        'popup': [c.args[1:] for c in show_error.call_args_list],
        'popup_detail': [(c.args[1], c.args[3]) for c in show_detailed.call_args_list],
        'signal': [c.args for c in obj.error_occurred.emit.call_args_list],
    }


@pytest.mark.parametrize('nom,kwargs', CAS, ids=[f"{n}-{i}" for i, (n, _) in enumerate(CAS)])
def test_comportement_inchange(nom, kwargs):
    assert observer(nom, kwargs) == ATTENDU[(nom, repr(sorted(kwargs.items())))]


def test_succes_et_metadonnees_preservees():
    for nom, kwargs in CAS:
        @getattr(eh, nom)(**kwargs)
        def ma_fonction(x):
            """doc"""
            return x * 2
        assert ma_fonction(21) == 42
        assert ma_fonction.__name__ == 'ma_fonction' and ma_fonction.__doc__ == 'doc'


def test_forme_positionnelle_utilisee_dans_le_code():
    # main_refactored : @handle_database_errors("Erreur d'initialisation des composants")
    @eh.handle_database_errors("Titre positionnel")
    def f(self):
        raise ValueError("boum")
    with patch('src.ui.message_helper.MessageHelper.show_detailed_error') as detail, \
            patch.object(eh, 'error_logger'):
        assert f(_Objet()) is False
    assert detail.call_args.args[3] == "Titre positionnel"


# ATTENDU — généré sur l'implémentation d'origine
ATTENDU = {('handle_async_worker_errors', "[('emit_signal', False), ('log_prefix', 'P')]"): {'app_debug': [],
                                                                                   'app_error': [('P: '
                                                                                                  'boum',)],
                                                                                   'eh_error': [],
                                                                                   'popup': [],
                                                                                   'popup_detail': [],
                                                                                   'retour': None,
                                                                                   'signal': []},
 ('handle_async_worker_errors', '[]'): {'app_debug': [],
                                        'app_error': [('Erreur worker asynchrone: boum',)],
                                        'eh_error': [],
                                        'popup': [],
                                        'popup_detail': [],
                                        'retour': None,
                                        'signal': [('boum',)]},
 ('handle_autocompletion_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                             'app_error': [],
                                                                             'eh_error': [('Erreur '
                                                                                           'dans '
                                                                                           'methode: '
                                                                                           'Erreur '
                                                                                           'lors '
                                                                                           'de la '
                                                                                           'récupération '
                                                                                           'des '
                                                                                           'données '
                                                                                           "d'auto-complétion.",)],
                                                                             'popup': [],
                                                                             'popup_detail': [],
                                                                             'retour': 5,
                                                                             'signal': []},
 ('handle_autocompletion_errors', '[]'): {'app_debug': [],
                                          'app_error': [],
                                          'eh_error': [('Erreur dans methode: Erreur lors de la '
                                                        'récupération des données '
                                                        "d'auto-complétion.",)],
                                          'popup': [],
                                          'popup_detail': [],
                                          'retour': [],
                                          'signal': []},
 ('handle_cache_callback_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                             'app_error': [],
                                                                             'eh_error': [('Erreur '
                                                                                           'dans '
                                                                                           'methode: '
                                                                                           'Erreur '
                                                                                           'lors '
                                                                                           'de '
                                                                                           "l'exécution "
                                                                                           "d'un "
                                                                                           'callback '
                                                                                           "d'invalidation "
                                                                                           'de '
                                                                                           'cache.',)],
                                                                             'popup': [],
                                                                             'popup_detail': [],
                                                                             'retour': 5,
                                                                             'signal': []},
 ('handle_cache_callback_errors', '[]'): {'app_debug': [],
                                          'app_error': [],
                                          'eh_error': [('Erreur dans methode: Erreur lors de '
                                                        "l'exécution d'un callback d'invalidation "
                                                        'de cache.',)],
                                          'popup': [],
                                          'popup_detail': [],
                                          'retour': None,
                                          'signal': []},
 ('handle_cleanup_preview_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                              'app_error': [],
                                                                              'eh_error': [('Erreur '
                                                                                            'dans '
                                                                                            'methode: '
                                                                                            'Erreur '
                                                                                            'lors '
                                                                                            'du '
                                                                                            'nettoyage '
                                                                                            'des '
                                                                                            'doublons.',)],
                                                                              'popup': [],
                                                                              'popup_detail': [('Erreur '
                                                                                                'lors '
                                                                                                'du '
                                                                                                'nettoyage '
                                                                                                'des '
                                                                                                'doublons.',
                                                                                                'T')],
                                                                              'retour': 5,
                                                                              'signal': []},
 ('handle_cleanup_preview_errors', '[]'): {'app_debug': [],
                                           'app_error': [],
                                           'eh_error': [('Erreur dans methode: Erreur lors du '
                                                         'nettoyage des doublons.',)],
                                           'popup': [],
                                           'popup_detail': [('Erreur lors du nettoyage des '
                                                             'doublons.',
                                                             'Erreur nettoyage doublons')],
                                           'retour': None,
                                           'signal': []},
 ('handle_count_operation_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                              'app_error': [],
                                                                              'eh_error': [('Erreur '
                                                                                            'dans '
                                                                                            'methode: '
                                                                                            'Erreur '
                                                                                            'lors '
                                                                                            'du '
                                                                                            'comptage '
                                                                                            'en '
                                                                                            'base '
                                                                                            'de '
                                                                                            'données.',)],
                                                                              'popup': [],
                                                                              'popup_detail': [],
                                                                              'retour': 5,
                                                                              'signal': []},
 ('handle_count_operation_errors', '[]'): {'app_debug': [],
                                           'app_error': [],
                                           'eh_error': [('Erreur dans methode: Erreur lors du '
                                                         'comptage en base de données.',)],
                                           'popup': [],
                                           'popup_detail': [],
                                           'retour': 0,
                                           'signal': []},
 ('handle_data_management_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                              'app_error': [],
                                                                              'eh_error': [('Erreur '
                                                                                            'dans '
                                                                                            'methode: '
                                                                                            'Erreur '
                                                                                            'lors '
                                                                                            'de la '
                                                                                            'gestion '
                                                                                            'des '
                                                                                            'données.',)],
                                                                              'popup': [],
                                                                              'popup_detail': [],
                                                                              'retour': 5,
                                                                              'signal': []},
 ('handle_data_management_errors', '[]'): {'app_debug': [],
                                           'app_error': [],
                                           'eh_error': [('Erreur dans methode: Erreur lors de la '
                                                         'gestion des données.',)],
                                           'popup': [],
                                           'popup_detail': [],
                                           'retour': None,
                                           'signal': []},
 ('handle_database_errors', "[('title', 'T')]"): {'app_debug': [],
                                                  'app_error': [],
                                                  'eh_error': [('Erreur dans methode: boum',)],
                                                  'popup': [],
                                                  'popup_detail': [('boum', 'T')],
                                                  'retour': False,
                                                  'signal': []},
 ('handle_database_errors', '[]'): {'app_debug': [],
                                    'app_error': [],
                                    'eh_error': [('Erreur dans methode: boum',)],
                                    'popup': [],
                                    'popup_detail': [('boum', 'Erreur de base de données')],
                                    'retour': False,
                                    'signal': []},
 ('handle_database_operation_errors', "[('log_prefix', 'P'), ('return_value', False)]"): {'app_debug': [('Erreur '
                                                                                                         'dans '
                                                                                                         '_Objet.methode: '
                                                                                                         'boum',)],
                                                                                          'app_error': [('P: '
                                                                                                         'boum',)],
                                                                                          'eh_error': [],
                                                                                          'popup': [],
                                                                                          'popup_detail': [],
                                                                                          'retour': False,
                                                                                          'signal': []},
 ('handle_database_operation_errors', '[]'): {'app_debug': [('Erreur dans _Objet.methode: boum',)],
                                              'app_error': [('Erreur base de données: boum',)],
                                              'eh_error': [],
                                              'popup': [],
                                              'popup_detail': [],
                                              'retour': None,
                                              'signal': []},
 ('handle_db_query_errors', "[('log_prefix', 'P'), ('return_value', [])]"): {'app_debug': [],
                                                                             'app_error': [('P: '
                                                                                            'boum',)],
                                                                             'eh_error': [],
                                                                             'popup': [],
                                                                             'popup_detail': [],
                                                                             'retour': [],
                                                                             'signal': []},
 ('handle_db_query_errors', '[]'): {'app_debug': [],
                                    'app_error': [('Erreur DB query: boum',)],
                                    'eh_error': [],
                                    'popup': [],
                                    'popup_detail': [],
                                    'retour': None,
                                    'signal': []},
 ('handle_drag_operation_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                             'app_error': [],
                                                                             'eh_error': [('Erreur '
                                                                                           'dans '
                                                                                           'methode: '
                                                                                           'Erreur '
                                                                                           'lors '
                                                                                           'des '
                                                                                           'opérations '
                                                                                           'de '
                                                                                           'glisser-déposer.',)],
                                                                             'popup': [],
                                                                             'popup_detail': [],
                                                                             'retour': 5,
                                                                             'signal': []},
 ('handle_drag_operation_errors', '[]'): {'app_debug': [],
                                          'app_error': [],
                                          'eh_error': [('Erreur dans methode: Erreur lors des '
                                                        'opérations de glisser-déposer.',)],
                                          'popup': [],
                                          'popup_detail': [],
                                          'retour': None,
                                          'signal': []},
 ('handle_errors', "[('message', 'M'), ('return_on_error', 7), ('show_message', False), ('title', 'T')]"): {'app_debug': [],
                                                                                                            'app_error': [],
                                                                                                            'eh_error': [('Erreur '
                                                                                                                          'dans '
                                                                                                                          'methode: '
                                                                                                                          'M',)],
                                                                                                            'popup': [],
                                                                                                            'popup_detail': [],
                                                                                                            'retour': 7,
                                                                                                            'signal': []},
 ('handle_errors', '[]'): {'app_debug': [],
                           'app_error': [],
                           'eh_error': [('Erreur dans methode: boum',)],
                           'popup': [],
                           'popup_detail': [('boum', 'Erreur')],
                           'retour': None,
                           'signal': []},
 ('handle_event_bus_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                        'app_error': [],
                                                                        'eh_error': [('Erreur dans '
                                                                                      'methode: '
                                                                                      'Erreur lors '
                                                                                      'de '
                                                                                      "l'émission "
                                                                                      "d'événement. "
                                                                                      'Les autres '
                                                                                      'listeners '
                                                                                      'continueront.',)],
                                                                        'popup': [],
                                                                        'popup_detail': [],
                                                                        'retour': 5,
                                                                        'signal': []},
 ('handle_event_bus_errors', '[]'): {'app_debug': [],
                                     'app_error': [],
                                     'eh_error': [("Erreur dans methode: Erreur lors de l'émission "
                                                   "d'événement. Les autres listeners "
                                                   'continueront.',)],
                                     'popup': [],
                                     'popup_detail': [],
                                     'retour': None,
                                     'signal': []},
 ('handle_event_handler_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                            'app_error': [],
                                                                            'eh_error': [('Erreur '
                                                                                          'dans '
                                                                                          'methode: '
                                                                                          'Erreur '
                                                                                          'lors de '
                                                                                          "l'exécution "
                                                                                          "d'un "
                                                                                          'gestionnaire '
                                                                                          "d'événement.",)],
                                                                            'popup': [],
                                                                            'popup_detail': [],
                                                                            'retour': 5,
                                                                            'signal': []},
 ('handle_event_handler_errors', '[]'): {'app_debug': [],
                                         'app_error': [],
                                         'eh_error': [('Erreur dans methode: Erreur lors de '
                                                       "l'exécution d'un gestionnaire "
                                                       "d'événement.",)],
                                         'popup': [],
                                         'popup_detail': [],
                                         'retour': None,
                                         'signal': []},
 ('handle_export_errors', "[('title', 'T')]"): {'app_debug': [],
                                                'app_error': [],
                                                'eh_error': [('Erreur dans methode: Erreur lors de '
                                                              "l'export des données.",)],
                                                'popup': [],
                                                'popup_detail': [("Erreur lors de l'export des "
                                                                  'données.',
                                                                  'T')],
                                                'retour': False,
                                                'signal': []},
 ('handle_export_errors', '[]'): {'app_debug': [],
                                  'app_error': [],
                                  'eh_error': [("Erreur dans methode: Erreur lors de l'export des "
                                                'données.',)],
                                  'popup': [],
                                  'popup_detail': [("Erreur lors de l'export des données.",
                                                    "Erreur d'export")],
                                  'retour': False,
                                  'signal': []},
 ('handle_log_viewer_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                         'app_error': [],
                                                                         'eh_error': [('Erreur '
                                                                                       'dans '
                                                                                       'methode: '
                                                                                       'Erreur '
                                                                                       'lors du '
                                                                                       'traitement '
                                                                                       'des '
                                                                                       'logs.',)],
                                                                         'popup': [],
                                                                         'popup_detail': [],
                                                                         'retour': 5,
                                                                         'signal': []},
 ('handle_log_viewer_errors', '[]'): {'app_debug': [],
                                      'app_error': [],
                                      'eh_error': [('Erreur dans methode: Erreur lors du '
                                                    'traitement des logs.',)],
                                      'popup': [],
                                      'popup_detail': [],
                                      'retour': None,
                                      'signal': []},
 ('handle_logger_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                     'app_error': [],
                                                                     'eh_error': [('Erreur dans '
                                                                                   'methode: '
                                                                                   'Erreur lors de '
                                                                                   'la lecture des '
                                                                                   'logs.',)],
                                                                     'popup': [],
                                                                     'popup_detail': [],
                                                                     'retour': 5,
                                                                     'signal': []},
 ('handle_logger_errors', '[]'): {'app_debug': [],
                                  'app_error': [],
                                  'eh_error': [('Erreur dans methode: Erreur lors de la lecture '
                                                'des logs.',)],
                                  'popup': [],
                                  'popup_detail': [],
                                  'retour': None,
                                  'signal': []},
 ('handle_navigation_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                         'app_error': [],
                                                                         'eh_error': [('Erreur '
                                                                                       'dans '
                                                                                       'methode: '
                                                                                       'Erreur '
                                                                                       'lors de la '
                                                                                       'navigation '
                                                                                       'ou '
                                                                                       'pagination.',)],
                                                                         'popup': [],
                                                                         'popup_detail': [],
                                                                         'retour': 5,
                                                                         'signal': []},
 ('handle_navigation_errors', '[]'): {'app_debug': [],
                                      'app_error': [],
                                      'eh_error': [('Erreur dans methode: Erreur lors de la '
                                                    'navigation ou pagination.',)],
                                      'popup': [],
                                      'popup_detail': [],
                                      'retour': None,
                                      'signal': []},
 ('handle_pdf_extraction_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                             'app_error': [],
                                                                             'eh_error': [('Erreur '
                                                                                           'dans '
                                                                                           'methode: '
                                                                                           'Erreur '
                                                                                           'lors '
                                                                                           'de '
                                                                                           "l'extraction "
                                                                                           'des '
                                                                                           'données '
                                                                                           'PDF.',)],
                                                                             'popup': [],
                                                                             'popup_detail': [],
                                                                             'retour': 5,
                                                                             'signal': []},
 ('handle_pdf_extraction_errors', '[]'): {'app_debug': [],
                                          'app_error': [],
                                          'eh_error': [('Erreur dans methode: Erreur lors de '
                                                        "l'extraction des données PDF.",)],
                                          'popup': [],
                                          'popup_detail': [],
                                          'retour': None,
                                          'signal': []},
 ('handle_pieces_panel_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                           'app_error': [],
                                                                           'eh_error': [('Erreur '
                                                                                         'dans '
                                                                                         'methode: '
                                                                                         'Erreur '
                                                                                         'lors de '
                                                                                         'la mise '
                                                                                         'à jour '
                                                                                         'du '
                                                                                         'panneau '
                                                                                         'des '
                                                                                         'pièces.',)],
                                                                           'popup': [],
                                                                           'popup_detail': [],
                                                                           'retour': 5,
                                                                           'signal': []},
 ('handle_pieces_panel_errors', '[]'): {'app_debug': [],
                                        'app_error': [],
                                        'eh_error': [('Erreur dans methode: Erreur lors de la mise '
                                                      'à jour du panneau des pièces.',)],
                                        'popup': [],
                                        'popup_detail': [],
                                        'retour': None,
                                        'signal': []},
 ('handle_save_service_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                           'app_error': [],
                                                                           'eh_error': [('Erreur '
                                                                                         'dans '
                                                                                         'methode: '
                                                                                         'Erreur '
                                                                                         'lors de '
                                                                                         'la '
                                                                                         'sauvegarde. '
                                                                                         "L'opération "
                                                                                         'sera '
                                                                                         'réessayée '
                                                                                         'automatiquement.',)],
                                                                           'popup': [],
                                                                           'popup_detail': [],
                                                                           'retour': 5,
                                                                           'signal': []},
 ('handle_save_service_errors', '[]'): {'app_debug': [],
                                        'app_error': [],
                                        'eh_error': [('Erreur dans methode: Erreur lors de la '
                                                      "sauvegarde. L'opération sera réessayée "
                                                      'automatiquement.',)],
                                        'popup': [],
                                        'popup_detail': [],
                                        'retour': None,
                                        'signal': []},
 ('handle_search_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                     'app_error': [],
                                                                     'eh_error': [('Erreur dans '
                                                                                   'methode: '
                                                                                   'Erreur lors de '
                                                                                   "l'exécution de "
                                                                                   'la '
                                                                                   'recherche.',)],
                                                                     'popup': [],
                                                                     'popup_detail': [],
                                                                     'retour': 5,
                                                                     'signal': []},
 ('handle_search_errors', '[]'): {'app_debug': [],
                                  'app_error': [],
                                  'eh_error': [("Erreur dans methode: Erreur lors de l'exécution "
                                                'de la recherche.',)],
                                  'popup': [],
                                  'popup_detail': [],
                                  'retour': None,
                                  'signal': []},
 ('handle_seo_data_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                       'app_error': [],
                                                                       'eh_error': [('Erreur dans '
                                                                                     'methode: '
                                                                                     'Erreur lors '
                                                                                     'de '
                                                                                     "l'extraction "
                                                                                     'des données '
                                                                                     'pour le '
                                                                                     'SEO.',)],
                                                                       'popup': [],
                                                                       'popup_detail': [],
                                                                       'retour': 5,
                                                                       'signal': []},
 ('handle_seo_data_errors', '[]'): {'app_debug': [],
                                    'app_error': [],
                                    'eh_error': [('Erreur dans methode: Erreur lors de '
                                                  "l'extraction des données pour le SEO.",)],
                                    'popup': [],
                                    'popup_detail': [],
                                    'retour': None,
                                    'signal': []},
 ('handle_seo_dialog_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                         'app_error': [],
                                                                         'eh_error': [('Erreur '
                                                                                       'dans '
                                                                                       'methode: '
                                                                                       'Erreur '
                                                                                       'lors de '
                                                                                       "l'affichage "
                                                                                       'du '
                                                                                       'dialogue '
                                                                                       'de '
                                                                                       'sélection.',)],
                                                                         'popup': [],
                                                                         'popup_detail': [('Erreur '
                                                                                           'lors '
                                                                                           'de '
                                                                                           "l'affichage "
                                                                                           'du '
                                                                                           'dialogue '
                                                                                           'de '
                                                                                           'sélection.',
                                                                                           'T')],
                                                                         'retour': 5,
                                                                         'signal': []},
 ('handle_seo_dialog_errors', '[]'): {'app_debug': [],
                                      'app_error': [],
                                      'eh_error': [('Erreur dans methode: Erreur lors de '
                                                    "l'affichage du dialogue de sélection.",)],
                                      'popup': [],
                                      'popup_detail': [("Erreur lors de l'affichage du dialogue de "
                                                        'sélection.',
                                                        'Erreur dialogue SEO')],
                                      'retour': None,
                                      'signal': []},
 ('handle_seo_generation_errors', '[]'): {'app_debug': [],
                                          'app_error': [],
                                          'eh_error': [('Erreur dans methode: Erreur lors de la '
                                                        'génération du contenu SEO. Vérifiez les '
                                                        'données de recherche.',)],
                                          'popup': [],
                                          'popup_detail': [('Erreur lors de la génération du '
                                                            'contenu SEO. Vérifiez les données de '
                                                            'recherche.',
                                                            'Erreur génération SEO')],
                                          'retour': None,
                                          'signal': []},
 ('handle_sqlite_column_errors', "[('log_message', 'P')]"): {'app_debug': [],
                                                             'app_error': [('P: boum',)],
                                                             'eh_error': [],
                                                             'popup': [],
                                                             'popup_detail': [],
                                                             'retour': False,
                                                             'signal': []},
 ('handle_sqlite_column_errors', '[]'): {'app_debug': [],
                                         'app_error': [('Erreur ajout colonne: boum',)],
                                         'eh_error': [],
                                         'popup': [],
                                         'popup_detail': [],
                                         'retour': False,
                                         'signal': []},
 ('handle_table_operations_errors', "[('log_prefix', 'P'), ('show_message', True)]"): {'app_debug': [],
                                                                                       'app_error': [('P: '
                                                                                                      'boum',)],
                                                                                       'eh_error': [],
                                                                                       'popup': [('Erreur '
                                                                                                  'table: '
                                                                                                  'boum',)],
                                                                                       'popup_detail': [],
                                                                                       'retour': None,
                                                                                       'signal': []},
 ('handle_table_operations_errors', '[]'): {'app_debug': [],
                                            'app_error': [('Erreur opération table: boum',)],
                                            'eh_error': [],
                                            'popup': [],
                                            'popup_detail': [],
                                            'retour': None,
                                            'signal': []},
 ('handle_ui_column_errors', "[('return_value', 'X')]"): {'app_debug': [],
                                                          'app_error': [('Erreur colonne UI: '
                                                                         'boum',)],
                                                          'eh_error': [],
                                                          'popup': [],
                                                          'popup_detail': [],
                                                          'retour': 'X',
                                                          'signal': []},
 ('handle_ui_column_errors', '[]'): {'app_debug': [],
                                     'app_error': [('Erreur colonne UI: boum',)],
                                     'eh_error': [],
                                     'popup': [],
                                     'popup_detail': [],
                                     'retour': 'Colonne inconnue',
                                     'signal': []},
 ('handle_ui_errors', "[('log_prefix', 'P'), ('return_value', 3), ('show_message', True)]"): {'app_debug': [],
                                                                                              'app_error': [('P: '
                                                                                                             'boum',)],
                                                                                              'eh_error': [],
                                                                                              'popup': [('Erreur: '
                                                                                                         'boum',)],
                                                                                              'popup_detail': [],
                                                                                              'retour': 3,
                                                                                              'signal': []},
 ('handle_ui_errors', "[('log_prefix', 'P'), ('show_message', False)]"): {'app_debug': [],
                                                                          'app_error': [('P: '
                                                                                         'boum',)],
                                                                          'eh_error': [],
                                                                          'popup': [],
                                                                          'popup_detail': [],
                                                                          'retour': None,
                                                                          'signal': []},
 ('handle_ui_errors', '[]'): {'app_debug': [],
                              'app_error': [('Erreur UI: boum',)],
                              'eh_error': [],
                              'popup': [('Erreur: boum',)],
                              'popup_detail': [],
                              'retour': None,
                              'signal': []},
 ('handle_ui_operation_errors', "[('log_prefix', 'P'), ('return_value', 0)]"): {'app_debug': [('Erreur '
                                                                                               'UI '
                                                                                               'dans '
                                                                                               '_Objet.methode: '
                                                                                               'boum',)],
                                                                                'app_error': [('P: '
                                                                                               'boum',)],
                                                                                'eh_error': [],
                                                                                'popup': [],
                                                                                'popup_detail': [],
                                                                                'retour': 0,
                                                                                'signal': []},
 ('handle_ui_operation_errors', '[]'): {'app_debug': [('Erreur UI dans _Objet.methode: boum',)],
                                        'app_error': [('Erreur opération UI: boum',)],
                                        'eh_error': [],
                                        'popup': [],
                                        'popup_detail': [],
                                        'retour': None,
                                        'signal': []},
 ('handle_ui_update_errors', "[('return_value', 5), ('title', 'T')]"): {'app_debug': [],
                                                                        'app_error': [],
                                                                        'eh_error': [('Erreur dans '
                                                                                      'methode: '
                                                                                      'Erreur lors '
                                                                                      'de la mise '
                                                                                      'à jour de '
                                                                                      "l'interface "
                                                                                      'utilisateur.',)],
                                                                        'popup': [],
                                                                        'popup_detail': [],
                                                                        'retour': 5,
                                                                        'signal': []},
 ('handle_ui_update_errors', '[]'): {'app_debug': [],
                                     'app_error': [],
                                     'eh_error': [('Erreur dans methode: Erreur lors de la mise à '
                                                   "jour de l'interface utilisateur.",)],
                                     'popup': [],
                                     'popup_detail': [],
                                     'retour': None,
                                     'signal': []}}
