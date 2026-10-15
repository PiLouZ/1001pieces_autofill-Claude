"""
Service de sauvegarde automatique de la base de données
Copie de sécurité avant les opérations destructives (nettoyage doublons, import massif)

Utilise l'API backup native de SQLite (sqlite3.Connection.backup) :
- cohérente même avec le mode WAL actif (pas besoin d'arrêter l'application)
- travaille sur ses propres connexions (aucune interaction avec la connexion partagée)

Rotation automatique dans data/backups/ (base ~840 Mo, limite l'espace disque),
en deux réserves indépendantes (v3.84.0) :
- automatiques (import, nettoyage, avant restauration) : BACKUP_MAX_COPIES copies ;
- ponctuelles (tout autre motif : fusion de marques, script…) :
  BACKUP_MAX_COPIES_PONCTUELLES copies.
Avant, une seule réserve : deux copies ponctuelles le même jour avaient évincé
les deux copies d'import (2026-10-15).
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
                      max_age_hours: Optional[float] = None,
                      proteger: Optional[Path] = None) -> Optional[Path]:
        """Créer une copie de sécurité de la base.

        Args:
            reason: étiquette incluse dans le nom du fichier (ex: 'nettoyage', 'import')
            max_age_hours: si fourni et qu'une copie plus récente que ce délai
                           existe déjà, la sauvegarde est sautée (évite de copier
                           ~840 Mo à chaque import quotidien)
            proteger: copie à ne jamais supprimer lors de la rotation (ex. la copie
                      en cours de restauration, qui peut être la plus ancienne)

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

            # Sauvegarde récente déjà présente ? (fenêtre glissante, dans la même
            # réserve : une copie ponctuelle ne dispense pas de la copie d'import)
            if max_age_hours is not None:
                latest = self._latest_backup_mtime(backups_dir, self._reserve(reason))
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

            self._rotate_backups(backups_dir, proteger)
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

    @staticmethod
    def _motif(copie: Path) -> str:
        """Motif tiré du nom : appareils_20261015_085138_fusion_midea.db → 'fusion_midea'."""
        parties = copie.stem.split('_', 3)
        return parties[3] if len(parties) == 4 else ''

    @staticmethod
    def _reserve(motif: str) -> str:
        return 'automatique' if motif in DatabaseConfig.BACKUP_MOTIFS_AUTOMATIQUES else 'ponctuelle'

    def _copies(self, backups_dir: Path, reserve: str) -> list:
        return [f for f in backups_dir.glob("appareils_*.db")
                if self._reserve(self._motif(f)) == reserve]

    def _latest_backup_mtime(self, backups_dir: Path, reserve: str = 'automatique') -> Optional[float]:
        """mtime (epoch) de la copie la plus récente de la réserve, ou None si aucune"""
        backups = self._copies(backups_dir, reserve)
        if not backups:
            return None
        return max(f.stat().st_mtime for f in backups)

    def _rotate_backups(self, backups_dir: Path, proteger: Optional[Path] = None) -> None:
        """Ne conserver que les copies les plus récentes de chaque réserve :
        BACKUP_MAX_COPIES automatiques, BACKUP_MAX_COPIES_PONCTUELLES ponctuelles.

        La copie `proteger` n'est jamais supprimée ni comptée. Les fichiers
        annexes -wal/-shm d'une copie supprimée partent avec elle.
        """
        proteger = proteger.resolve() if proteger is not None else None
        limites = {'automatique': DatabaseConfig.BACKUP_MAX_COPIES,
                   'ponctuelle': DatabaseConfig.BACKUP_MAX_COPIES_PONCTUELLES}
        a_supprimer = []
        for reserve, limite in limites.items():
            backups = sorted((f for f in self._copies(backups_dir, reserve)
                              if f.resolve() != proteger),
                             key=lambda f: f.stat().st_mtime, reverse=True)
            a_supprimer.extend(backups[limite:])
        for old in a_supprimer:
            try:
                old.unlink()
                app_logger.info(f"[Backup] Rotation : {old.name} supprimé")
            except OSError as e:
                app_logger.warning(f"[Backup] Rotation impossible pour {old.name} : {e}")
                continue
            for suffixe in ("-wal", "-shm"):
                annexe = Path(str(old) + suffixe)
                try:
                    annexe.unlink(missing_ok=True)
                except OSError as e:
                    app_logger.warning(f"[Backup] Rotation impossible pour {annexe.name} : {e}")
