"""
Tests de concurrence — non-régression du correctif anti-corruption (fix/db-concurrency-corruption).

Contexte : la connexion sqlite3 / le curseur de DatabaseManager sont UNIQUES et partagés
entre le thread principal et les workers de fond (DatabaseQueryWorker, _ImportWorker).
sqlite3 libère le GIL pendant execute/commit → deux threads dans le moteur sur la même
connexion = « database disk image is malformed ». Le correctif sérialise TOUS les accès
(lectures ET écritures) via le RLock partagé `_query_lock`.

Ces tests verrouillent ce comportement :
1. les méthodes d'écriture acquièrent bien `_query_lock` (sérialisation déterministe) ;
2. un accès concurrent intensif lecture/écriture préserve l'intégrité de la base.
"""

import threading
import time

import pytest

from src.data.database_manager import DatabaseManager


@pytest.mark.unit
@pytest.mark.database
class TestDbConcurrencySerialization:
    """Le verrou _query_lock sérialise réellement les accès à la connexion partagée."""

    def test_write_blocks_while_lock_held(self, test_db_manager):
        """Une écriture lancée depuis un autre thread DOIT attendre la libération du verrou.

        On tient `_query_lock` dans le thread principal puis on lance une insertion
        dans un thread de fond : tant que le verrou est tenu, l'insertion ne progresse pas.
        """
        done = threading.Event()

        def worker():
            test_db_manager.insert_appareil({'type': 'T', 'manufacturer': 'M'})
            done.set()

        with test_db_manager._query_lock:
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            # Le worker doit rester bloqué sur le verrou tant qu'on le détient.
            assert not done.wait(timeout=0.5), \
                "L'écriture a progressé alors que _query_lock était tenu (non sérialisée)"

        # Verrou libéré : l'écriture doit aboutir rapidement.
        assert done.wait(timeout=5.0), "L'écriture n'a jamais abouti après libération du verrou"
        t.join(timeout=5.0)

    def test_reentrant_no_deadlock(self, test_db_manager):
        """Une méthode décorée qui en appelle une autre (toutes deux verrouillées) ne deadlocke pas.

        `_safe_delete_appareil` acquiert le verrou puis appelle `execute_query` (verrouillé) :
        le RLock réentrant doit l'autoriser dans le même thread.
        """
        device_id = test_db_manager.insert_appareil({'type': 'T', 'manufacturer': 'M'})
        # delete_appareil → _safe_delete_appareil (verrou) → execute_query (verrou) : réentrance.
        result = test_db_manager.delete_appareil(device_id)
        assert result is True


@pytest.mark.unit
@pytest.mark.database
class TestDbConcurrencyIntegrity:
    """Accès concurrent intensif : aucune exception, intégrité préservée."""

    def test_concurrent_read_write_keeps_integrity(self, test_db_manager):
        db = test_db_manager

        # Pré-amorcer quelques lignes pour que lectures et updates aient de la matière.
        seed_ids = [db.insert_appareil({'type': f'T{i}', 'manufacturer': f'M{i}'})
                    for i in range(20)]

        errors = []
        stop = threading.Event()

        def writer(worker_id):
            try:
                for i in range(40):
                    if stop.is_set():
                        return
                    new_id = db.insert_appareil({
                        'type': f'W{worker_id}', 'manufacturer': f'F{i}',
                        'ref_modele': f'R{worker_id}-{i}',
                    })
                    db.update_multiple_cells_batch({new_id: {'notes': f'n{i}'}})
                    if seed_ids:
                        db.update_cell(seed_ids[i % len(seed_ids)], 'notes', f'u{worker_id}{i}')
            except Exception as e:  # noqa: BLE001 — on veut remonter toute exception thread
                errors.append(('writer', worker_id, repr(e)))
                stop.set()

        def reader(worker_id):
            try:
                for _ in range(60):
                    if stop.is_set():
                        return
                    db.load_data(limit=50, offset=0)
                    db.count_data()
            except Exception as e:  # noqa: BLE001
                errors.append(('reader', worker_id, repr(e)))
                stop.set()

        threads = (
            [threading.Thread(target=writer, args=(w,)) for w in range(3)] +
            [threading.Thread(target=reader, args=(w,)) for w in range(3)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        assert not errors, f"Exceptions levées sous concurrence : {errors}"

        # La base doit rester intègre malgré le martelage concurrent.
        check = db.execute_query("PRAGMA integrity_check")
        assert check and check[0][0] == 'ok', f"integrity_check != ok : {check}"
