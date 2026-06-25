"""
Exceptions et utilitaires partagés entre les mixins DatabaseManager.
"""

import functools


class DatabaseError(Exception):
    """Exception personnalisée pour les erreurs de base de données."""
    pass


def with_query_lock(method):
    """Sérialise l'accès à la connexion sqlite3 partagée entre threads.

    La connexion `self.conn` / le curseur `self.cursor` sont uniques et partagés
    entre le thread principal et les workers de fond (DatabaseQueryWorker, _ImportWorker).
    sqlite3 LIBÈRE le GIL pendant execute/commit (code C) : deux threads peuvent donc
    être simultanément dans le moteur sur la MÊME connexion → « database disk image is
    malformed ». Ce décorateur garantit qu'une seule opération touche la connexion à la
    fois. `self._query_lock` est un RLock réentrant : les méthodes décorées qui s'appellent
    entre elles ne se bloquent pas mutuellement.

    Défini ici (module neutre) pour être partagé par database_manager.py ET les mixins
    sans créer de cycle d'import.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._query_lock:
            return method(self, *args, **kwargs)
    return wrapper
