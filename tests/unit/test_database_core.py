"""
Tests essentiels pour DatabaseManager - Version simplifiée pour validation rapide
Focus sur les opérations CRUD critiques et la sécurité
"""

import pytest
import sqlite3
import tempfile
from typing import List, Dict, Any

from src.data.database_manager import DatabaseManager, DatabaseError
from src.core.config import Config


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.critical
class TestDatabaseManagerCore:
    """Tests critiques simplifiés pour DatabaseManager - ZÉRO RÉGRESSION"""

    def test_database_initialization(self, test_db_manager):
        """Test initialisation et connectivité DB"""
        assert test_db_manager.conn is not None
        assert test_db_manager.cursor is not None

        # Test insert basique
        test_data = {'type': 'Test', 'manufacturer': 'Test Co'}
        device_id = test_db_manager.insert_appareil(test_data)
        assert device_id is not None
        assert isinstance(device_id, int)
        assert device_id > 0

    def test_crud_operations(self, test_db_manager, sample_device_data):
        """Test CRUD complet"""
        # CREATE
        device_id = test_db_manager.insert_appareil(sample_device_data)
        assert device_id is not None

        # READ - vérifier que l'appareil existe
        query = "SELECT * FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert len(results) == 1

        # UPDATE
        success = test_db_manager.update_cell(device_id, 'notes', 'Test modifié')
        assert success

        # Vérifier la mise à jour
        query = "SELECT notes FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert results[0][0] == 'Test modifié'

        # DELETE
        success = test_db_manager.delete_appareil(device_id)
        assert success

        # Vérifier la suppression
        query = "SELECT COUNT(*) FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert results[0][0] == 0

    def test_search_functionality(self, test_db_manager, multiple_devices_data, test_helpers):
        """Test fonctionnalité de recherche"""
        # Ajouter des données de test
        device_ids = []
        for device_data in multiple_devices_data:
            device_id = test_db_manager.insert_appareil(device_data)
            device_ids.append(device_id)

        # Test recherche simple avec load_data
        results = test_db_manager.load_data(search_term='Bosch')
        assert len(results) >= 1

        # Vérifier qu'on trouve le bon résultat
        found_bosch = False
        for result in results:
            if 'Bosch' in str(result):
                found_bosch = True
                break
        assert found_bosch

        # Test recherche vide
        results = test_db_manager.load_data(search_term='MARQUE_INEXISTANTE_XYZ')
        assert len(results) == 0

    def test_batch_operations(self, test_db_manager, multiple_devices_data):
        """Test opérations par lots"""
        # Insérer plusieurs appareils
        device_ids = []
        for device_data in multiple_devices_data:
            device_id = test_db_manager.insert_appareil(device_data)
            device_ids.append(device_id)

        # Test mise à jour par lots
        batch_updates = {}
        for i, device_id in enumerate(device_ids):
            batch_updates[device_id] = {
                'notes': f'Batch update {i}',
                'category': f'Catégorie {i}'
            }

        success = test_db_manager.update_multiple_cells_batch(batch_updates)
        assert success

        # Vérifier les mises à jour
        for device_id, updates in batch_updates.items():
            query = "SELECT notes, category FROM appareils WHERE id = ?"
            results = test_db_manager.execute_query(query, [device_id])
            assert results[0][0] == updates['notes']
            assert results[0][1] == updates['category']

        # Test suppression par lots
        deleted_count = test_db_manager.delete_appareils(device_ids)
        assert deleted_count == len(device_ids)

    def test_data_count(self, test_db_manager, multiple_devices_data):
        """Test comptage de données"""
        # Compter avant ajout
        initial_count = test_db_manager.count_data()

        # Ajouter des données
        for device_data in multiple_devices_data:
            test_db_manager.insert_appareil(device_data)

        # Compter après ajout
        new_count = test_db_manager.count_data()
        assert new_count == initial_count + len(multiple_devices_data)

        # Test comptage avec recherche
        search_count = test_db_manager.count_data(search_term='Bosch')
        assert search_count >= 1

    def test_sql_injection_resistance(self, test_db_manager):
        """Test résistance aux injections SQL - SÉCURITÉ CRITIQUE"""
        malicious_inputs = [
            "'; DROP TABLE appareils; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM appareils --",
            "<script>alert('xss')</script>",
        ]

        for malicious_input in malicious_inputs:
            # Tester recherche
            results = test_db_manager.load_data(search_term=malicious_input)
            assert isinstance(results, list)

            # Tester ajout avec données malveillantes
            malicious_device = {
                'type': malicious_input,
                'manufacturer': malicious_input,
                'ref_modele': malicious_input,
                'notes': malicious_input
            }

            try:
                device_id = test_db_manager.insert_appareil(malicious_device)
                if device_id:
                    # Vérifier que les données sont correctement échappées
                    query = "SELECT type, manufacturer FROM appareils WHERE id = ?"
                    results = test_db_manager.execute_query(query, [device_id])
                    assert len(results) == 1
                    # Les données doivent être là telles quelles, pas exécutées
                    assert results[0][0] == malicious_input
                    assert results[0][1] == malicious_input
            except Exception as e:
                # C'est acceptable si l'insertion échoue proprement
                assert "DatabaseError" in str(type(e)) or "sqlite3" in str(type(e))

    def test_pieces_operations(self, test_db_manager, sample_device_data):
        """Test opérations sur les pièces"""
        # Créer un appareil
        device_id = test_db_manager.insert_appareil(sample_device_data)

        # Ajouter une pièce
        assoc_id = test_db_manager.add_piece('TEST-PIECE-001', device_id, 'Description test')
        assert assoc_id is not None

        # Compter les pièces
        count = test_db_manager.get_pieces_count_for_appareil(device_id)
        assert count == 1

        # Récupérer les pièces
        pieces = test_db_manager.get_pieces_for_appareil(device_id)
        assert len(pieces) == 1
        assert pieces[0][0] == 'TEST-PIECE-001'
        assert pieces[0][1] == 'Description test'

        # Supprimer la pièce
        success = test_db_manager.delete_piece('TEST-PIECE-001', device_id)
        assert success

        # Vérifier suppression
        count = test_db_manager.get_pieces_count_for_appareil(device_id)
        assert count == 0

    def test_concurrent_access_simulation(self, test_db_manager, sample_device_data):
        """Test simulation accès concurrent"""
        device_id = test_db_manager.insert_appareil(sample_device_data)

        # Lecture simultanée (simulation)
        for i in range(10):
            query = "SELECT * FROM appareils WHERE id = ?"
            results = test_db_manager.execute_query(query, [device_id])
            assert len(results) == 1

        # Mise à jour simultanée (simulation)
        for i in range(5):
            success = test_db_manager.update_cell(device_id, 'notes', f'Note {i}')
            assert success

    def test_database_integrity(self, test_db_manager, sample_device_data):
        """Test intégrité de la base après erreurs"""
        # Ajouter un appareil valide
        device_id = test_db_manager.insert_appareil(sample_device_data)
        assert device_id is not None

        # Tenter une opération qui doit échouer (lève DatabaseError sur colonne invalide)
        with pytest.raises(DatabaseError):
            test_db_manager.update_cell(device_id, 'colonne_invalide', 'valeur')

        # Vérifier que l'appareil est toujours cohérent
        query = "SELECT type FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert len(results) == 1
        assert results[0][0] == sample_device_data['type']


def test_database_connection_management():
    """Test gestion des connexions de base de données"""
    with tempfile.NamedTemporaryFile(suffix='.db') as tmp_file:
        original_db_path = Config.DB_FILE
        Config.DB_FILE = tmp_file.name

        # Test création et fermeture
        db_manager = DatabaseManager()
        assert db_manager.conn is not None

        # Test fermeture
        db_manager.close()

        # Restaurer
        Config.DB_FILE = original_db_path


@pytest.mark.slow
def test_performance_basic(test_db_manager):
    """Test performance basique avec dataset réduit"""
    import time

    # Générer un dataset plus petit pour les tests rapides
    dataset_size = 100
    large_dataset = []
    for i in range(dataset_size):
        device = {
            'type': f'Type {i}',
            'manufacturer': f'Manufacturer {i % 5}',  # Répétition pour test recherche
            'ref_modele': f'REF{i:04d}',
            'notes': f'Notes pour appareil {i}'
        }
        large_dataset.append(device)

    # Test ajout en masse
    start_time = time.time()
    device_ids = []
    for device_data in large_dataset:
        device_id = test_db_manager.insert_appareil(device_data)
        device_ids.append(device_id)

    add_time = time.time() - start_time
    assert add_time < 10.0, f"Ajout de {dataset_size} appareils trop lent: {add_time}s"

    # Test recherche
    start_time = time.time()
    results = test_db_manager.load_data(search_term='Manufacturer 2')
    search_time = time.time() - start_time
    assert search_time < 2.0, f"Recherche trop lente: {search_time}s"
    assert len(results) == 20, f"Doit trouver 20 appareils Manufacturer 2, trouvé: {len(results)}"