"""
Tests du volume des logs (v3.66.0)

Contexte : detailed.log atteignait 2,3 Go / ~19 M lignes le 2026-09-01, dont 89,6 %
de DEBUG. Deux causes cumulées :
  1. logging.FileHandler sans aucune rotation → croissance infinie ;
  2. des messages émis une fois par appareil traité, dans une application conçue
     pour gérer des centaines de milliers d'appareils.
"""

import glob
import logging
import os
import shutil
import tempfile

import pytest

from src.core.config import Config
from src.core.logger import AppLogger
from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType, FileType)


@pytest.fixture
def log_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


class _CaptureHandler(logging.Handler):
    """Collecte les messages émis. Remplace caplog, indisponible ici : la suite
    tourne avec « -p no:logging », qui désactive le plugin fournissant caplog."""

    def __init__(self, niveau=logging.INFO):
        super().__init__(level=niveau)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _capture(niveau=logging.INFO):
    """Contexte : attache un handler de capture au logger applicatif."""
    from src.core.logger import app_logger

    class _Ctx:
        def __enter__(self):
            self.handler = _CaptureHandler(niveau)
            self.logger = app_logger.logger
            self.niveau_initial = self.logger.level
            self.logger.setLevel(min(niveau, self.niveau_initial))
            self.logger.addHandler(self.handler)
            return self.handler

        def __exit__(self, *exc):
            self.logger.removeHandler(self.handler)
            self.logger.setLevel(self.niveau_initial)
            return False

    return _Ctx()


def _logger_isole(log_dir):
    """AppLogger branché sur un dossier neuf.

    Le logger « 1001pieces » est un singleton déjà équipé au moment de l'import du
    module : sans vider ses handlers, setup_handlers() est sauté et les écritures
    partent dans les logs réels du projet.
    """
    lg = AppLogger(log_dir=log_dir)
    lg.logger.handlers.clear()
    lg.log_dir = log_dir
    lg.setup_handlers()
    return lg


class TestRotationDesLogs:
    """Sans rotation, aucun plafond : le fichier grossit indéfiniment."""

    def test_handlers_fichier_sont_rotatifs(self, log_dir):
        from logging.handlers import RotatingFileHandler
        lg = _logger_isole(log_dir)
        handlers_fichier = [h for h in lg.logger.handlers
                            if isinstance(h, logging.FileHandler)]
        assert len(handlers_fichier) == 3          # detailed, errors, data_operations
        assert all(isinstance(h, RotatingFileHandler) for h in handlers_fichier)

    def test_plafond_de_taille_respecte(self, log_dir, monkeypatch):
        """Le volume total sur disque ne dépasse jamais (maxBytes × (backupCount+1))."""
        monkeypatch.setattr(Config, 'LOG_MAX_BYTES_DETAILED', 50 * 1024)
        monkeypatch.setattr(Config, 'LOG_BACKUP_COUNT_DETAILED', 3)
        lg = _logger_isole(log_dir)

        for i in range(4000):
            lg.logger.debug(f"ligne de test {i} avec un peu de contenu pour peser")
        for h in lg.logger.handlers:
            h.flush()

        fichiers = glob.glob(os.path.join(log_dir, 'detailed.log*'))
        total = sum(os.path.getsize(f) for f in fichiers)
        assert len(fichiers) > 1, "aucune rotation n'a eu lieu"
        assert total <= 50 * 1024 * 4

    def test_desactivation_possible(self, log_dir, monkeypatch):
        """NON-RÉGRESSION : Config.LOG_ROTATION_ENABLED=False rend le comportement
        historique (FileHandler simple)."""
        from logging.handlers import RotatingFileHandler
        monkeypatch.setattr(Config, 'LOG_ROTATION_ENABLED', False)
        lg = _logger_isole(log_dir)
        handlers_fichier = [h for h in lg.logger.handlers
                            if isinstance(h, logging.FileHandler)]
        assert handlers_fichier and not any(
            isinstance(h, RotatingFileHandler) for h in handlers_fichier)


class TestVolumeParAppareil:
    """Les messages par-appareil sont agrégés en une ligne de synthèse."""

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    @staticmethod
    def _config(nb, mapping=None, prefixe='WW'):
        """`prefixe` permet à deux passages successifs d'importer des appareils
        INÉDITS. Sans lui, le 2ᵉ passage est un ré-import : il retrouve les
        appareils du 1ᵉʳ au lieu d'en créer (v3.66.1), et les deux passages ne
        sont plus comparables — voir test_import_fonctionnellement_inchange."""
        data = [['', '', f'{prefixe}{i:05d}EE'] for i in range(nb)]
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference='PIECE900', suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': 'PIECE900'}
        config.column_mapping = mapping or {3: ['type', 'manufacturer', 'ref_modele']}
        return config

    def test_reduction_du_nombre_de_lignes(self, import_manager, log_dir, monkeypatch):
        """Un import identique doit produire nettement moins de lignes de log
        en mode agrégé qu'en mode historique."""
        def volume(verbose, prefixe):
            monkeypatch.setattr(Config, 'LOG_VERBOSE_PER_DEVICE', verbose)
            sous_dossier = tempfile.mkdtemp(dir=log_dir)
            lg = _logger_isole(sous_dossier)
            # Préfixe distinct par passage : les deux partagent la même base, et un
            # ré-import ne produit pas le même volume de log qu'un import initial.
            import_manager._run_import_files(self._config(60, prefixe=prefixe))
            for h in lg.logger.handlers:
                h.flush()
            total = 0
            for f in glob.glob(os.path.join(sous_dossier, 'detailed.log*')):
                with open(f, encoding='utf-8', errors='replace') as fh:
                    total += sum(1 for _ in fh)
            return total

        lignes_verbose = volume(True, 'VB')
        lignes_agrege = volume(False, 'AG')
        assert lignes_agrege < lignes_verbose / 2, (
            f"réduction insuffisante : {lignes_verbose} → {lignes_agrege}")

    def test_synthese_journalisee(self, import_manager):
        """La ligne de synthèse remplace les messages unitaires : elle doit exister
        et porter le rapport lignes/clés distinctes."""
        with _capture(logging.INFO) as cap:
            import_manager._run_import_files(self._config(10))
        syntheses = [m for m in cap.messages if '[Import] Synthèse' in m]
        assert len(syntheses) == 1
        assert '10 lignes traitées' in syntheses[0]
        assert '10 clés' in syntheses[0]

    def test_alerte_si_une_seule_cle_distincte(self, import_manager):
        """Détecteur de régression : un mapping qui écrase l'identité des appareils
        (le bug du 2026-09-01) doit déclencher un WARNING explicite — le symptôme
        n'était auparavant visible qu'en lisant des centaines de lignes DEBUG."""
        # Reproduit la forme exacte du bug : le mapping envoie Type et Marque dans
        # ref_modele / commercial_ref, si bien que les 60 lignes partagent l'identité
        # « lave-linge|samsung » et que 59 d'entre elles finissent en doublons.
        data = [['Lave-linge', 'Samsung', f'WW{i:05d}EE'] for i in range(60)]
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference='PIECE900', suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': 'PIECE900'}
        config.column_mapping = {3: ['ref_modele', 'commercial_ref', 'ignore']}

        with _capture(logging.WARNING) as cap:
            import_manager._run_import_files(config)
        alertes = [m for m in cap.messages if 'clé(s) distincte(s)' in m]
        assert alertes, "aucune alerte alors que toutes les lignes ont la même clé"
        assert 'vérifiez le mapping' in alertes[0]

    def test_import_fonctionnellement_inchange(self, import_manager, monkeypatch):
        """NON-RÉGRESSION : le niveau de verbosité des logs ne doit RIEN changer au
        résultat de l'import. Les deux passages sont comparés terme à terme.

        Les deux passages doivent porter sur des appareils DIFFÉRENTS (préfixes
        distincts) : ils partagent la même base, donc réutiliser le même jeu ferait
        du 2ᵉ passage un ré-import, qui retrouve légitimement les 60 appareils au
        lieu d'en créer 60. Comparer un import initial à un ré-import ne mesure
        plus la verbosité. Le test ne passait avant la v3.66.1 que parce que le
        ré-import était buggé et recréait les appareils à l'identique."""
        monkeypatch.setattr(Config, 'LOG_VERBOSE_PER_DEVICE', False)
        agrege = import_manager._run_import_files(self._config(60, prefixe='AG'))
        monkeypatch.setattr(Config, 'LOG_VERBOSE_PER_DEVICE', True)
        verbose = import_manager._run_import_files(self._config(60, prefixe='VB'))

        compteurs = ('total_imported', 'new_entries', 'matches_found',
                     'duplicates_in_file', 'associations_created')
        assert {k: agrege[k] for k in compteurs} == {k: verbose[k] for k in compteurs}
        assert agrege['total_imported'] == 60
