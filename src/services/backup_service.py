"""
Service de sauvegarde automatique de la base de données
Copie de sécurité avant les opérations destructives (nettoyage doublons, import massif)

Utilise l'API backup native de SQLite (sqlite3.Connection.backup) :
- cohérente même avec le mode WAL actif (pas besoin d'arrêter l'application)
- travaille sur ses propres connexions (aucune interaction avec la connexion partagée)

Rotation automatique : seules les BACKUP_MAX_COPIES copies les plus récentes
sont conservées dans data/backups/ (base ~840 Mo, limite l'espace disque utilisé).
"""

import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base_service import BaseService
from ..core.constants import DatabaseConfig, Paths
from ..core.logger import app_logger


class BackupService(BaseService):
    """Sauvegarde de la base via l'API backup SQLite, avec rotation"""

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent_window, parent)

    def _get_db_path(self) -> Path:
        """Chemin de la base : via le db_manager si disponible, sinon via la config"""
        dm = getattr(self.parent_window, 'db_manager', None)
        db_file = getattr(dm, 'db_file', None) if dm else None
        return Path(db_file) if db_file else Paths.get_database_path()

    def _get_backups_dir(self) -> Path:
        backups_dir = self._get_db_path().parent / DatabaseConfig.BACKUP_DIR_NAME
        backups_dir.mkdir(parents=True, exist_ok=True)
        return backups_dir

    def create_backup(self, reason: str = "manuel",
                      max_age_hours: Optional[float] = None) -> Optional[Path]:
        """Créer une copie de sécurité de la base.

        Args:
            reason: étiquette incluse dans le nom du fichier (ex: 'nettoyage', 'import')
            max_age_hours: si fourni et qu'une copie plus récente que ce délai
                           existe déjà, la sauvegarde est sautée (évite de copier
                           ~840 Mo à chaque import quotidien)

        Returns:
            Chemin de la copie créée, ou None (sauvegarde sautée ou échouée).
            Un échec ne lève jamais : l'opération appelante doit pouvoir continuer
            comme avant l'introduction de ce service (zéro régression).
        """
        target = None
        try:
            db_path = self._get_db_path()
            if not db_path.exists():
                app_logger.warning(f"[Backup] Base introuvable : {db_path}")
                return None

            backups_dir = self._get_backups_dir()

            # Sauvegarde récente déjà présente ? (fenêtre glissante)
            if max_age_hours is not None:
                latest = self._latest_backup_mtime(backups_dir)
                if latest is not None and (time.time() - latest) < max_age_hours * 3600:
                    app_logger.info(
                        f"[Backup] Copie récente (< {max_age_hours}h) déjà présente — sauvegarde sautée"
                    )
                    return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = backups_dir / f"appareils_{timestamp}_{reason}.db"

            t0 = time.perf_counter()
            src = sqlite3.connect(str(db_path))
            try:
                dst = sqlite3.connect(str(target))
                try:
                    with dst:
                        src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()

            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            app_logger.info(f"[Backup] {target.name} créé en {elapsed_ms}ms ({reason})")

            self._rotate_backups(backups_dir)
            return target

        except (sqlite3.Error, OSError) as e:
            app_logger.error(f"[Backup] Échec de la sauvegarde ({reason}) : {e}")
            # Nettoyer une copie partielle éventuelle
            try:
                if target is not None and target.exists():
                    target.unlink()
            except OSError:
                pass
            return None

    def _latest_backup_mtime(self, backups_dir: Path) -> Optional[float]:
        """mtime (epoch) de la copie la plus récente, ou None si aucune"""
        backups = list(backups_dir.glob("appareils_*.db"))
        if not backups:
            return None
        return max(f.stat().st_mtime for f in backups)

    def _rotate_backups(self, backups_dir: Path) -> None:
        """Ne conserver que les BACKUP_MAX_COPIES copies les plus récentes"""
        backups = sorted(backups_dir.glob("appareils_*.db"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        for old in backups[DatabaseConfig.BACKUP_MAX_COPIES:]:
            try:
                old.unlink()
                app_logger.info(f"[Backup] Rotation : {old.name} supprimé")
            except OSError as e:
                app_logger.warning(f"[Backup] Rotation impossible pour {old.name} : {e}")
