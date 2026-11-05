"""
Requêtes rapatriées dans la couche données (DatabaseHistoriquesMixin) :
les écritures sont COMMITÉES.

« Vider l'historique » passait par execute_query, qui ne commit pas : la
suppression était visible depuis la connexion de l'application, mais l'historique
revenait au lancement suivant si rien d'autre n'écrivait entre-temps. Comme
dans test_ecritures_durables, on relit sur une connexion NEUVE, seule façon de
distinguer « écrit » de « commité ».
"""

import os
import sqlite3
import tempfile

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.services.history_service import HistoryService


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        for suffixe in ('', '-wal', '-shm'):
            if os.path.exists(chemin + suffixe):
                os.remove(chemin + suffixe)


def _compter_sur_connexion_neuve(table):
    neuve = sqlite3.connect(Config.DB_FILE)
    try:
        return neuve.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        neuve.close()


def test_vider_l_historique_survit_a_une_connexion_neuve(db):
    conn = db.get_connection()
    conn.executemany(
        "INSERT INTO modifications_history (timestamp, action_type, title) VALUES (?, ?, ?)",
        [('2026-11-05 10:00:00', 'edit', 'a'), ('2026-11-05 10:01:00', 'edit', 'b')])
    conn.commit()
    service = HistoryService.__new__(HistoryService)
    service.db_manager = db
    assert service.clear_history() is True
    assert _compter_sur_connexion_neuve('modifications_history') == 0


def test_nettoyage_suppressions_commitees(db):
    db.creer_table_historique_nettoyage()
    conn = db.get_connection()
    conn.execute("INSERT INTO cleanup_history (timestamp, action_type) VALUES ('t', 'x')")
    conn.execute("INSERT INTO reference_decisions (ref_modele, decision) VALUES ('R1', 'DISTINCT')")
    conn.execute("INSERT INTO reference_decisions (ref_modele, decision) VALUES ('R2', 'DISTINCT')")
    conn.commit()
    assert db.retirer_references_distinctes(['R1']) == 1
    assert db.vider_historique_nettoyage() == 1
    neuve = sqlite3.connect(Config.DB_FILE)
    try:
        assert [r[0] for r in neuve.execute("SELECT ref_modele FROM reference_decisions")] == ['R2']
        assert neuve.execute("SELECT COUNT(*) FROM cleanup_history").fetchone()[0] == 0
    finally:
        neuve.close()


def test_filtre_commun_a_la_page_et_au_total(db):
    conn = db.get_connection()
    conn.executemany(
        "INSERT INTO modifications_history (timestamp, action_type, title, device_ref) VALUES (?, ?, ?, ?)",
        [('2026-10-01 09:00:00', 'edit', 'Bosch', 'A1'), ('2026-10-15 09:00:00', 'import', 'pdf', 'A2'),
         ('2026-10-31 18:00:00', 'edit', 'Siemens', 'A3')])
    conn.commit()
    for filtres in ({}, {'action_type': 'edit'}, {'search': 'bosch'},
                    {'date_from': '2026-10-10', 'date_to': '2026-10-31'}):
        page = db.historique_entrees(100, 0, **filtres)
        total = db.historique_total(**filtres)[0][0]
        assert total == len(page), filtres
    assert db.historique_total(date_to='2026-10-31')[0][0] == 3   # journée de fin incluse
