"""
Système de logging avancé pour l'application 1001pieces
Permet un suivi précis des opérations et des erreurs
"""

import logging
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from ..utils.error_handler import handle_logger_errors

# Répertoire de logs absolu : <racine_projet>/data/logs/
#
# La variable d'environnement AUTOFILL_LOG_DIR le redirige ailleurs. Elle existe
# pour que la suite de tests n'écrive pas dans les logs de production : sur six
# mois, ~80 % des 6 909 lignes d'errors.log provenaient des tests (mocks,
# « colonne_invalide », « Erreur de test »…), noyant les rares vraies erreurs.
# Absente — le cas normal — le comportement est inchangé.
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_LOG_DIR = (os.environ.get('AUTOFILL_LOG_DIR')
                    or str(_PROJECT_ROOT / "data" / "logs"))

class AppLogger:
    """Gestionnaire de logs avancé pour l'application"""
    
    def __init__(self, log_dir: str = _DEFAULT_LOG_DIR):
        """
        Initialise le système de logging
        
        Args:
            log_dir: Répertoire où stocker les logs
        """
        self.log_dir = log_dir
        self.ensure_log_dir()
        
        # Configuration du logger principal
        self.logger = logging.getLogger("1001pieces")
        self.logger.setLevel(logging.DEBUG)
        
        # Éviter les doublons de handlers
        if not self.logger.handlers:
            self.setup_handlers()
    
    def ensure_log_dir(self):
        """Crée le répertoire de logs s'il n'existe pas"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def _file_handler(self, filename: str, max_bytes: int, backup_count: int):
        """Handler fichier avec rotation par taille.

        Auparavant un logging.FileHandler simple, sans aucun plafond : detailed.log
        atteignait 2,3 Go (~19 M lignes) le 2026-09-01. La rotation borne le disque
        de façon définitive ; Config.LOG_ROTATION_ENABLED permet de revenir au
        comportement historique si besoin.
        """
        from .config import Config
        chemin = os.path.join(self.log_dir, filename)
        if getattr(Config, 'LOG_ROTATION_ENABLED', True):
            from logging.handlers import RotatingFileHandler
            return RotatingFileHandler(
                chemin, maxBytes=max_bytes, backupCount=backup_count,
                encoding='utf-8'
            )
        return logging.FileHandler(chemin, encoding='utf-8')

    def setup_handlers(self):
        """Configure les handlers de logging"""
        from .config import Config

        # Handler pour fichier détaillé
        detailed_handler = self._file_handler(
            "detailed.log",
            getattr(Config, 'LOG_MAX_BYTES_DETAILED', 20 * 1024 * 1024),
            getattr(Config, 'LOG_BACKUP_COUNT_DETAILED', 5),
        )
        detailed_handler.setLevel(logging.DEBUG)
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-12s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
        )
        detailed_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(detailed_handler)
        
        # Handler pour erreurs uniquement
        error_handler = self._file_handler(
            "errors.log",
            getattr(Config, 'LOG_MAX_BYTES_SECONDARY', 5 * 1024 * 1024),
            getattr(Config, 'LOG_BACKUP_COUNT_SECONDARY', 3),
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        self.logger.addHandler(error_handler)
        
        # Handler pour opérations sur les données
        data_handler = self._file_handler(
            "data_operations.log",
            getattr(Config, 'LOG_MAX_BYTES_SECONDARY', 5 * 1024 * 1024),
            getattr(Config, 'LOG_BACKUP_COUNT_SECONDARY', 3),
        )
        data_handler.setLevel(logging.INFO)
        data_formatter = logging.Formatter(
            '%(asctime)s | %(message)s'
        )
        data_handler.setFormatter(data_formatter)
        data_handler.addFilter(lambda record: record.levelname in ['DATA_OP', 'AUTO_COMPLETE'])
        self.logger.addHandler(data_handler)
        
        # Handler console pour développement
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def log_data_operation(self, operation: str, data: Dict[str, Any], 
                          table_id: Optional[int] = None, 
                          success: bool = True, 
                          error_msg: Optional[str] = None):
        """
        Log une opération sur les données
        
        Args:
            operation: Type d'opération (CREATE, UPDATE, DELETE, etc.)
            data: Données concernées
            table_id: ID de la ligne concernée
            success: Succès de l'opération
            error_msg: Message d'erreur si échec
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "table_id": table_id,
            "data": data,
            "success": success,
            "error": error_msg
        }
        
        level = logging.INFO if success else logging.ERROR
        message = f"DATA_OP | {operation} | ID:{table_id} | {json.dumps(log_entry, ensure_ascii=False)}"
        
        # Créer un record personnalisé
        record = logging.LogRecord(
            name=self.logger.name,
            level=level,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        record.levelname = "DATA_OP"
        self.logger.handle(record)
    
    
    def debug(self, msg: str, **kwargs):
        """Log niveau DEBUG"""
        self.logger.debug(msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        """Log niveau INFO"""
        self.logger.info(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Log niveau WARNING"""
        self.logger.warning(msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        """Log niveau ERROR"""
        self.logger.error(msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        """Log niveau CRITICAL"""
        self.logger.critical(msg, **kwargs)
    
    @handle_logger_errors(return_value="Erreur lors de la lecture des logs")
    def get_recent_logs(self, log_type: str = "detailed", lines: int = 100) -> str:
        """
        Récupère les logs récents

        Args:
            log_type: Type de log (detailed, errors, data_operations)
            lines: Nombre de lignes à récupérer

        Returns:
            Contenu des logs récents
        """
        log_file = os.path.join(self.log_dir, f"{log_type}.log")

        if not os.path.exists(log_file):
            return "Aucun log trouvé"

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return ''.join(recent_lines)

# Instance globale du logger
app_logger = AppLogger()