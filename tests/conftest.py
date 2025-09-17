"""
Configuration globale des tests - 1001pieces_autofill
Fixtures communes pour tous les tests
"""

import sys
import os
import tempfile
import sqlite3
from pathlib import Path
from typing import Generator
import pytest
from unittest.mock import Mock, MagicMock

# Ajouter le chemin source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.core.logger import app_logger


@pytest.fixture(scope="session")
def qapp():
    """Fixture QApplication pour les tests PyQt5"""
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Pas de app.quit() pour éviter les erreurs de fermeture


@pytest.fixture
def temp_db_path():
    """Fixture pour une base de données temporaire"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
        db_path = tmp_file.name

    yield db_path

    # Nettoyage
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def test_db_manager(temp_db_path):
    """Fixture DatabaseManager avec base temporaire"""
    # Sauvegarder l'ancien chemin
    original_db_path = Config.DB_FILE

    # Configurer chemin temporaire
    Config.DB_FILE = temp_db_path

    # Créer le manager (l'initialisation se fait automatiquement)
    db_manager = DatabaseManager()

    yield db_manager

    # Restaurer et nettoyer
    Config.DB_FILE = original_db_path
    db_manager.close()


@pytest.fixture
def sample_device_data():
    """Fixture données d'appareil pour tests"""
    return {
        'type': 'Lave-vaisselle',
        'manufacturer': 'Bosch',
        'ref_modele': 'SMS46AW03E',
        'commercial_ref': 'Serie 4',
        'other_ref': 'TEST-001',
        'category': 'Electroménager',
        'notes': 'Appareil de test'
    }


@pytest.fixture
def multiple_devices_data():
    """Fixture plusieurs appareils pour tests batch"""
    return [
        {
            'type': 'Lave-vaisselle',
            'manufacturer': 'Bosch',
            'ref_modele': 'SMS46AW03E',
            'commercial_ref': 'Serie 4',
            'other_ref': 'TEST-001',
            'category': 'Electroménager',
            'notes': 'Test 1'
        },
        {
            'type': 'Lave-linge',
            'manufacturer': 'Samsung',
            'ref_modele': 'WW90T4540AE',
            'commercial_ref': 'EcoBubble',
            'other_ref': 'TEST-002',
            'category': 'Electroménager',
            'notes': 'Test 2'
        },
        {
            'type': 'Micro-ondes',
            'manufacturer': 'Whirlpool',
            'ref_modele': 'MWP254W',
            'commercial_ref': 'MAX 25',
            'other_ref': 'TEST-003',
            'category': 'Electroménager',
            'notes': 'Test 3'
        }
    ]


@pytest.fixture
def mock_main_window():
    """Fixture MainWindow mockée pour tests services"""
    mock_window = MagicMock()
    mock_window.statusbar = MagicMock()
    mock_window.table = MagicMock()
    mock_window.save_indicator = MagicMock()
    return mock_window


@pytest.fixture
def mock_user_interaction_service():
    """Fixture service d'interaction utilisateur mocké"""
    mock_service = MagicMock()
    mock_service.show_error = MagicMock()
    mock_service.show_warning = MagicMock()
    mock_service.show_info = MagicMock()
    mock_service.add_to_history = MagicMock()
    return mock_service


@pytest.fixture
def sample_csv_content():
    """Fixture contenu CSV pour tests d'import"""
    return """Type,Fabricant,Référence Modèle,Référence Commerciale,Autre Référence,Catégorie,Notes
Lave-vaisselle,Bosch,SMS46AW03E,Serie 4,TEST-001,Electroménager,Test import CSV 1
Lave-linge,Samsung,WW90T4540AE,EcoBubble,TEST-002,Electroménager,Test import CSV 2
Micro-ondes,Whirlpool,MWP254W,MAX 25,TEST-003,Electroménager,Test import CSV 3"""


@pytest.fixture
def temp_csv_file(sample_csv_content):
    """Fixture fichier CSV temporaire"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
        tmp_file.write(sample_csv_content)
        csv_path = tmp_file.name

    yield csv_path

    # Nettoyage
    if os.path.exists(csv_path):
        os.unlink(csv_path)


@pytest.fixture(autouse=True)
def setup_logging():
    """Configuration du logging pour les tests"""
    # Réduire le niveau de logging pendant les tests (si méthode disponible)
    if hasattr(app_logger, 'setLevel'):
        app_logger.setLevel("ERROR")
    yield
    # Restaurer niveau normal (si méthode disponible)
    if hasattr(app_logger, 'setLevel'):
        app_logger.setLevel("INFO")


# Helpers pour tests
class TestHelpers:
    """Classe utilitaire pour fonctions communes de tests"""

    @staticmethod
    def assert_device_equals(actual_device: dict, expected_device: dict, ignore_fields=None):
        """Comparer deux dictionnaires d'appareil en ignorant certains champs"""
        if ignore_fields is None:
            ignore_fields = ['id', 'created_at', 'updated_at']

        for key, expected_value in expected_device.items():
            if key not in ignore_fields:
                assert key in actual_device, f"Champ manquant: {key}"
                assert actual_device[key] == expected_value, f"Valeur différente pour {key}: {actual_device[key]} != {expected_value}"

    @staticmethod
    def create_test_devices(db_manager: DatabaseManager, devices_data: list) -> list:
        """Créer des appareils de test en base et retourner leurs IDs"""
        device_ids = []
        for device_data in devices_data:
            device_id = db_manager.add_device(device_data)
            device_ids.append(device_id)
        return device_ids

    @staticmethod
    def assert_sql_injection_safe(db_manager: DatabaseManager):
        """Vérifier que les requêtes résistent aux injections SQL"""
        malicious_inputs = [
            "'; DROP TABLE appareils; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM appareils --",
            "<script>alert('xss')</script>",
            "../../etc/passwd"
        ]

        for malicious_input in malicious_inputs:
            # Tester recherche
            results = db_manager.search_devices(malicious_input)
            assert isinstance(results, list), "La recherche doit retourner une liste même avec input malveillant"

            # Tester ajout d'appareil avec données malveillantes
            malicious_device = {
                'type': malicious_input,
                'manufacturer': malicious_input,
                'ref_modele': malicious_input,
                'commercial_ref': malicious_input,
                'other_ref': malicious_input,
                'category': malicious_input,
                'notes': malicious_input
            }

            device_id = db_manager.add_device(malicious_device)
            assert device_id is not None, "L'ajout doit fonctionner même avec données malveillantes"

            # Vérifier que les données sont correctement échappées
            retrieved_device = db_manager.get_device_by_id(device_id)
            assert retrieved_device is not None, "L'appareil doit être récupérable"


# Fixture helper accessible globalement
@pytest.fixture
def test_helpers():
    """Fixture pour accéder aux helpers de test"""
    return TestHelpers()