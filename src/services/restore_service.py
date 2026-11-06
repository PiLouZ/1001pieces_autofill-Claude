"""
Service de restauration de la base de données depuis une copie de sauvegarde
(data/backups/, alimenté par BackupService).

La restauration ferme la connexion SQLite active, écrase data/appareils.db par
la copie choisie (après nettoyage des fichiers WAL/SHM périmés) puis quitte
l'application : rouvrir une connexion à chaud sur un fichier remplacé sous les
caches/services en cours laisserait l'état applicatif incohérent (zéro régression).
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .base_service import BaseService
from ..core.logger import app_logger


class RestoreService(BaseService):
    """Restauration de la base depuis une copie de data/backups/"""

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent_window, parent)

    def list_backups(self) -> List[Tuple[Path, datetime, int]]:
        """Lister les sauvegardes disponibles, plus récente en premier.

        Returns:
            Liste de (chemin, date de création, taille en octets)
        """
        backups_dir = self.parent_window.backup_service._get_backups_dir()
        backups = sorted(backups_dir.glob("appareils_*.db"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        return [(f, datetime.fromtimestamp(f.stat().st_mtime), f.stat().st_size)
                for f in backups]

    def restore_and_quit(self, backup_path: Path) -> Optional[str]:
        """Restaurer la base depuis `backup_path` puis fermer l'application.

        Returns:
            None en cas de succès (l'application se ferme), ou un message
            d'erreur en cas d'échec (l'application reste ouverte).
        """
        try:
            db_path = self.parent_window.backup_service._get_db_path()

            # Sauvegarde de sécurité de l'état actuel avant écrasement
            # (la copie à restaurer est protégée de la rotation : elle peut être la plus ancienne)
            self.parent_window.backup_service.create_backup("avant_restauration",
                                                            proteger=backup_path)

            # Fermer la connexion active avant de remplacer le fichier
            self.parent_window.db_manager.close()

            # Les fichiers WAL/SHM de l'ancienne base ne doivent pas être
            # réappliqués sur la base restaurée au prochain démarrage
            for suffix in ("-wal", "-shm"):
                stale = Path(str(db_path) + suffix)
                if stale.exists():
                    stale.unlink()

            shutil.copy2(backup_path, db_path)
            app_logger.info(f"[Restore] Base restaurée depuis {backup_path.name}")

            self.parent_window.close()
            return None

        except OSError as e:
            app_logger.error(f"[Restore] Échec de la restauration : {e}")
            return str(e)
