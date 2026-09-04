"""
Tests — La suite de tests n'écrit pas dans les logs de production

Sur six mois, **~80 % des 6 909 lignes de `data/logs/errors.log` provenaient de
la suite de tests** : « no such column: colonne_invalide », « could not convert
string to float: 'invalid_price' », « Échec import: Erreur de test », et des
milliers d'erreurs `NoneType` issues des mocks.

Les rares vraies erreurs de production — 209 le jour de la corruption de base du
2026-06-24, deux échecs SELECT — y étaient noyées. Le fichier était inexploitable
pour ce à quoi il sert : repérer un problème réel.

`tests/conftest.py` redirige donc le logger vers un répertoire temporaire, via
`AUTOFILL_LOG_DIR`. Ces tests garantissent que la redirection tient : c'est le
genre de protection qui se perd silencieusement au premier refactoring du
conftest, et dont on ne s'aperçoit que des mois plus tard.
"""

import os
from pathlib import Path

from src.core.logger import app_logger


def _repertoire_production():
    """<racine_projet>/data/logs — celui que les tests ne doivent pas toucher."""
    racine = Path(__file__).resolve().parent.parent.parent
    return (racine / 'data' / 'logs').resolve()


class TestRedirection:

    def test_la_variable_d_environnement_est_posee(self):
        assert os.environ.get('AUTOFILL_LOG_DIR'), \
            "AUTOFILL_LOG_DIR devrait être posée par conftest avant tout import du logger"

    def test_le_logger_ecrit_hors_de_la_production(self):
        actuel = Path(app_logger.log_dir).resolve()
        assert actuel != _repertoire_production(), (
            f"la suite écrit dans les logs de production ({actuel}) — "
            "la redirection de conftest.py a été perdue"
        )

    def test_le_repertoire_de_test_est_temporaire(self):
        import tempfile
        actuel = Path(app_logger.log_dir).resolve()
        assert str(actuel).startswith(str(Path(tempfile.gettempdir()).resolve())), \
            f"le répertoire de logs des tests devrait être temporaire, pas {actuel}"


class TestEcritureEffective:
    """La redirection ne doit pas avoir cassé la journalisation elle-même.

    Ces tests portent sur la **destination** des handlers, pas sur la croissance
    des fichiers : d'autres tests de la suite modifient les niveaux de log
    (cf. test_logger_volume.py), et une assertion sur la taille échouerait selon
    l'ordre d'exécution — ce qui mesurerait l'ordre des tests, pas l'isolation.
    """

    def test_les_fichiers_de_log_existent_dans_le_repertoire_de_test(self):
        repertoire = Path(app_logger.log_dir)
        assert (repertoire / 'errors.log').exists()
        assert (repertoire / 'detailed.log').exists()

    def test_tous_les_handlers_fichier_pointent_hors_production(self):
        import logging
        production = _repertoire_production()
        destinations = [
            Path(h.baseFilename).resolve()
            for h in app_logger.logger.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert destinations, "aucun handler fichier — la journalisation est cassée"
        for chemin in destinations:
            assert chemin.parent != production, f"{chemin} écrit en production"

    def test_la_production_reste_intacte(self):
        """Écrire une erreur ne doit rien ajouter aux logs de production."""
        production = _repertoire_production() / 'errors.log'
        avant = production.stat().st_size if production.exists() else None

        app_logger.error("second marqueur — la production ne doit pas bouger")
        for handler in app_logger.logger.handlers:
            handler.flush()

        if avant is not None:
            assert production.stat().st_size == avant, \
                "la suite a écrit dans les logs de production"


class TestComportementDeProduction:
    """Sans la variable, le chemin par défaut doit rester celui de production."""

    def test_le_defaut_reste_data_logs(self, monkeypatch):
        monkeypatch.delenv('AUTOFILL_LOG_DIR', raising=False)
        import importlib
        import src.core.logger as module_logger
        recharge = importlib.reload(module_logger)
        try:
            assert Path(recharge._DEFAULT_LOG_DIR).resolve() == _repertoire_production()
        finally:
            monkeypatch.setenv('AUTOFILL_LOG_DIR', app_logger.log_dir)
            importlib.reload(module_logger)
