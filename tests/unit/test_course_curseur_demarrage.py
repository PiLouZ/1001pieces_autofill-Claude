"""
Course au démarrage entre l'import et les comptages différés (v3.88.2).

Constat (2026-10-15, simulation offscreen sur une copie de la base) : un import lancé
juste après l'ouverture de la fenêtre a préchargé 0 appareil, ou ~32 000 sur 708 166,
et une fois le processus a planté. Le fil d'import tenait `_query_lock`, mais le fil
principal comptait les doublons (`execute_custom_query`) et les lignes incomplètes
(`count_incomplete_devices`) SANS le verrou, sur le même curseur partagé.

Piège : la troncature est SILENCIEUSE côté import (aucune exception) — l'autre fil
réinitialise le curseur et `fetchall()` rend ce qui avait déjà été lu. Seule la
sérialisation corrige ; le filet « échouer bruyamment » couvre les vraies erreurs SQLite.
"""

import sqlite3
import threading
from unittest.mock import MagicMock

import pytest

from src.data._db_mixins import DatabaseError
from src.core.import_manager import ImportManager


# Méthodes qui touchaient self.cursor sans verrou (appelées depuis le fil principal).
METHODES_VERROUILLEES = {
    'count_incomplete_devices': lambda db: db.count_incomplete_devices(),
    'execute_custom_query': lambda db: db.execute_custom_query("SELECT 1"),
    'get_column_values': lambda db: db.get_column_values('type'),
    'get_export_data': lambda db: db.get_export_data(""),
    'remove_duplicate_pieces': lambda db: db.remove_duplicate_pieces(),
    'lire_appareils_pour_import': lambda db: db.lire_appareils_pour_import(),
}


@pytest.mark.unit
@pytest.mark.database
class TestMethodesSousVerrou:

    @pytest.mark.parametrize('nom', sorted(METHODES_VERROUILLEES))
    def test_attend_la_liberation_du_verrou(self, test_db_manager, nom):
        """Lancée depuis un autre fil pendant que le verrou est tenu, la méthode attend."""
        fini = threading.Event()

        def fil():
            METHODES_VERROUILLEES[nom](test_db_manager)
            fini.set()

        with test_db_manager._query_lock:
            t = threading.Thread(target=fil, daemon=True)
            t.start()
            assert not fini.wait(timeout=0.5), f"{nom} a touché le curseur sans _query_lock"
        assert fini.wait(timeout=5.0), f"{nom} n'a jamais abouti après libération du verrou"
        t.join(timeout=5.0)

    def test_close_attend_la_liberation_du_verrou(self, test_db_manager):
        """close() ne ferme pas la connexion sous les pieds d'un fil qui l'utilise."""
        fini = threading.Event()

        def fil():
            test_db_manager.close()
            fini.set()

        with test_db_manager._query_lock:
            t = threading.Thread(target=fil, daemon=True)
            t.start()
            assert not fini.wait(timeout=0.5), "close() n'a pas attendu le verrou"
            assert test_db_manager.conn is not None
        assert fini.wait(timeout=5.0)
        t.join(timeout=5.0)
        assert test_db_manager.conn is None


@pytest.mark.unit
@pytest.mark.database
class TestPrechargementPendantLesComptages:

    def test_prechargement_complet_malgre_les_comptages(self, test_db_manager):
        """Scénario du démarrage : préchargement en fil de fond, comptages dans le fil
        principal. Chaque préchargement doit rendre toutes les clés, jamais un cache
        vide ou tronqué."""
        db = test_db_manager
        db.conn.executemany(
            "INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref) "
            "VALUES (?, ?, ?, ?)",
            [('', '', f'REF{i:06d}', f'COM{i:06d}') for i in range(20000)])
        db.conn.commit()
        manager = ImportManager(db_manager=db, parent_widget=None)

        tailles, erreurs = [], []
        stop = threading.Event()

        def importeur():
            try:
                for _ in range(8):
                    tailles.append(len(manager._preload_existing_devices()))
            except Exception as e:  # noqa: BLE001 — toute exception du fil doit remonter
                erreurs.append(repr(e))
            finally:
                stop.set()

        t = threading.Thread(target=importeur)
        t.start()
        while not stop.is_set():
            db.count_incomplete_devices()
            db.execute_custom_query(
                "SELECT ref_modele, COUNT(*) FROM appareils GROUP BY ref_modele HAVING COUNT(*) > 1")
        t.join(timeout=60.0)

        assert not erreurs, erreurs
        assert tailles == [20000] * 8, f"préchargements incomplets : {tailles}"


@pytest.mark.unit
@pytest.mark.database
class TestPrechargementEchoueBruyamment:

    def test_erreur_sqlite_remonte_au_lieu_de_liste_vide(self, test_db_manager):
        """Une erreur SQLite remonte en DatabaseError (execute_query aurait rendu [])."""
        vrai_curseur = test_db_manager.cursor
        faux = MagicMock()
        faux.execute.side_effect = sqlite3.OperationalError("Recursive use of cursors not allowed.")
        test_db_manager.cursor = faux
        try:
            with pytest.raises(DatabaseError, match="Recursive use of cursors"):
                test_db_manager.lire_appareils_pour_import()
            manager = ImportManager(db_manager=test_db_manager, parent_widget=None)
            with pytest.raises(DatabaseError):
                manager._preload_existing_devices()
        finally:
            test_db_manager.cursor = vrai_curseur

    def test_lecture_identique_a_execute_query(self, test_db_manager):
        """Sans erreur, la nouvelle lecture rend exactement les lignes d'avant."""
        from src.core.config import Config
        test_db_manager.insert_appareil({'type': 'T', 'manufacturer': 'M', 'ref_modele': 'A1'})
        test_db_manager.insert_appareil({'type': 'T', 'manufacturer': 'M', 'commercial_ref': 'C2'})
        test_db_manager.insert_appareil({'type': 'T', 'manufacturer': 'M'})
        attendu = test_db_manager.execute_query(Config.QUERIES['preload_all_devices'])
        assert test_db_manager.lire_appareils_pour_import() == attendu
        assert len(attendu) == 2
