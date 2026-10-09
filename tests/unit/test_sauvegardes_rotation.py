"""
Sauvegardes : rotation (nombre de copies, fichiers -wal/-shm) et restauration
de la copie la plus ancienne.

Avant 3.78.5 :
- la rotation supprimait `appareils_*.db` mais laissait ses `-wal`/`-shm` orphelins ;
- restaurer la copie la plus ancienne échouait : la copie « avant_restauration »
  déclenchait la rotation, qui supprimait justement la copie à restaurer, après
  la fermeture de la connexion à la base.
"""

import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.core.constants import DatabaseConfig
from src.services.backup_service import BackupService
from src.services.restore_service import RestoreService


def _creer_base(chemin: Path, valeur: str) -> None:
    conn = sqlite3.connect(str(chemin))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", (valeur,))
    conn.commit()
    conn.close()


def _lire_base(chemin: Path) -> str:
    conn = sqlite3.connect(str(chemin))
    try:
        return conn.execute("SELECT v FROM t").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Base de travail + dossier de sauvegardes contenant BACKUP_MAX_COPIES copies datées."""
    base = tmp_path / "appareils.db"
    _creer_base(base, "courante")
    dossier = tmp_path / DatabaseConfig.BACKUP_DIR_NAME
    dossier.mkdir()

    copies = []
    maintenant = time.time()
    for i in range(DatabaseConfig.BACKUP_MAX_COPIES):
        copie = dossier / f"appareils_2026010{i + 1}_120000_import.db"
        _creer_base(copie, f"copie{i}")
        age = (DatabaseConfig.BACKUP_MAX_COPIES - i) * 3600  # copie0 = la plus ancienne
        os.utime(copie, (maintenant - age, maintenant - age))
        copies.append(copie)

    service = BackupService(parent_window=Mock())
    monkeypatch.setattr(service, "_get_db_path", lambda: base)
    return base, dossier, copies, service


def test_nombre_de_copies_conservees_est_deux():
    assert DatabaseConfig.BACKUP_MAX_COPIES == 2


def test_rotation_conserve_les_plus_recentes(env):
    base, dossier, copies, service = env
    nouvelle = service.create_backup("test")

    restantes = sorted(dossier.glob("appareils_*.db"))
    assert len(restantes) == DatabaseConfig.BACKUP_MAX_COPIES
    assert nouvelle in restantes
    assert not copies[0].exists()  # la plus ancienne est partie


def test_rotation_supprime_aussi_wal_et_shm(env):
    base, dossier, copies, service = env
    plus_ancienne = copies[0]
    for suffixe in ("-wal", "-shm"):
        Path(str(plus_ancienne) + suffixe).write_bytes(b"x")
    # Les fichiers annexes d'une copie conservée ne doivent pas être touchés
    conservee_wal = Path(str(copies[-1]) + "-wal")
    conservee_wal.write_bytes(b"x")

    service.create_backup("test")

    assert not plus_ancienne.exists()
    assert not Path(str(plus_ancienne) + "-wal").exists()
    assert not Path(str(plus_ancienne) + "-shm").exists()
    assert conservee_wal.exists()


def test_restaurer_la_copie_la_plus_ancienne(env):
    base, dossier, copies, service = env
    parent = Mock()
    parent.backup_service = service
    restore = RestoreService(parent_window=parent)

    erreur = restore.restore_and_quit(copies[0])

    assert erreur is None
    assert _lire_base(base) == "copie0"
    parent.close.assert_called_once()
    # La copie de sécurité « avant_restauration » contient l'état d'avant
    avant = list(dossier.glob("appareils_*_avant_restauration.db"))
    assert len(avant) == 1
    assert _lire_base(avant[0]) == "courante"
