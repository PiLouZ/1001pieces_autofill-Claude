"""
Import, chemin standard : la mise à jour d'un appareil existant (autre réf.,
notes depuis la 3ᵉ colonne) est COMMITÉE.

`_update_existing_device` passait par execute_query, qui ne commit pas : la
mise à jour était visible depuis l'application mais perdue si elle était la
dernière écriture avant la fermeture. Relecture sur une connexion NEUVE, seule
façon de distinguer « écrit » de « commité » (cf. test_ecritures_durables).
"""

import os
import sqlite3
import tempfile
from collections import Counter

import pytest

from src.core.config import Config
from src.core.import_manager import ImportManager
from src.data.database_manager import DatabaseManager


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        conn.execute("INSERT INTO appareils (id, type, manufacturer, ref_modele, commercial_ref, "
                     "other_ref, notes, category) VALUES (1, 'Four', 'Bosch', 'R1', 'C1', '', '', '')")
        conn.commit()
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        for suffixe in ('', '-wal', '-shm'):
            if os.path.exists(chemin + suffixe):
                os.remove(chemin + suffixe)


def test_mise_a_jour_d_un_appareil_existant_survit_a_une_connexion_neuve(db):
    importeur = ImportManager.__new__(ImportManager)
    importeur.db_manager = db
    importeur._log_counters = Counter()
    importeur._update_existing_device(1, {'other_ref': 'AUTRE9', 'notes': 'note importée'})
    neuve = sqlite3.connect(Config.DB_FILE)
    try:
        assert neuve.execute("SELECT other_ref, notes FROM appareils WHERE id = 1").fetchone() \
            == ('AUTRE9', 'note importée')
    finally:
        neuve.close()


def test_rien_a_mettre_a_jour_n_ecrit_rien(db):
    importeur = ImportManager.__new__(ImportManager)
    importeur.db_manager = db
    importeur._update_existing_device(1, {'other_ref': '  ', 'notes': ''})
    assert db.execute_query("SELECT other_ref, notes FROM appareils WHERE id = 1") == [('', '')]
