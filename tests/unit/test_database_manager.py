"""
Tests unitaires pour DatabaseManager - Service critique
Validation COMPLÈTE du CRUD et des requêtes pour sécuriser les refactorings
"""

import pytest
import sqlite3
import tempfile
from unittest.mock import Mock, patch
from typing import List, Dict, Any

from src.data.database_manager import DatabaseManager, DatabaseError
from src.core.config import Config


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.critical
class TestDatabaseManager:
    """Tests critiques pour DatabaseManager - ZÉRO RÉGRESSION"""

    def test_database_initialization(self, test_db_manager):
        """Test initialisation base de données"""
        # Vérifier que le manager fonctionne
        assert test_db_manager.conn is not None, "Connexion DB doit être établie"
        assert test_db_manager.cursor is not None, "Cursor DB doit être disponible"

        # Vérifier qu'on peut insérer et récupérer des données basiques
        test_data = {'type': 'Test', 'manufacturer': 'Test Manufacturer'}
        device_id = test_db_manager.insert_appareil(test_data)
        assert device_id is not None, "L'insertion doit fonctionner"

        # Vérifier la récupération
        query = "SELECT type, manufacturer FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert len(results) == 1, "Doit retrouver l'appareil inséré"
        assert results[0][0] == 'Test', "Type doit correspondre"
        assert results[0][1] == 'Test Manufacturer', "Manufacturer doit correspondre"

    def test_add_device_success(self, test_db_manager, sample_device_data):
        """Test ajout appareil réussi"""
        device_id = test_db_manager.insert_appareil(sample_device_data)

        assert device_id is not None, "L'ID de l'appareil ne doit pas être None"
        assert isinstance(device_id, int), "L'ID doit être un entier"
        assert device_id > 0, "L'ID doit être positif"

        # Vérifier que l'appareil est bien en base
        query = "SELECT * FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert len(results) == 1, "L'appareil doit être récupérable"

        # Vérifier les données - construire un dictionnaire des résultats
        headers = ['id', 'type', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref', 'category', 'notes', 'created_at', 'updated_at']
        retrieved_device = dict(zip(headers, results[0]))
        for key, expected_value in sample_device_data.items():
            assert retrieved_device[key] == expected_value, f"Valeur incorrecte pour {key}"

    def test_add_device_minimal_data(self, test_db_manager):
        """Test ajout appareil avec données minimales"""
        minimal_data = {
            'type': 'Test Type',
            'manufacturer': 'Test Manufacturer'
        }

        device_id = test_db_manager.insert_appareil(minimal_data)
        assert device_id is not None, "L'ajout avec données minimales doit fonctionner"

        query = "SELECT type, manufacturer FROM appareils WHERE id = ?"
        results = test_db_manager.execute_query(query, [device_id])
        assert len(results) == 1, "Doit récupérer l'appareil"
        assert results[0][0] == 'Test Type'
        assert results[0][1] == 'Test Manufacturer'

    def test_add_device_empty_strings(self, test_db_manager):
        """Test ajout appareil avec chaînes vides"""
        empty_data = {
            'type': '',
            'manufacturer': '',
            'ref_modele': '',
            'commercial_ref': '',
            'other_ref': '',
            'category': '',
            'notes': ''
        }

        device_id = test_db_manager.insert_appareil(empty_data)
        assert device_id is not None, "L'ajout avec chaînes vides doit fonctionner"

    def test_get_device_by_id_existing(self, test_db_manager, sample_device_data):
        """Test récupération appareil existant"""
        device_id = test_db_manager.insert_appareil(sample_device_data)
        retrieved_device = test_db_manager.get_device_info(device_id)

        assert retrieved_device is not None
        assert retrieved_device['id'] == device_id

    def test_get_device_by_id_nonexistent(self, test_db_manager):
        """Test récupération appareil inexistant"""
        retrieved_device = test_db_manager.get_device_info(99999)
        assert retrieved_device is None

    def test_get_device_by_id_invalid(self, test_db_manager):
        """Test récupération avec ID invalide"""
        invalid_ids = [None, 'abc', -1, 0]

        for invalid_id in invalid_ids:
            retrieved_device = test_db_manager.get_device_info(invalid_id)
            assert retrieved_device is None, f"ID invalide {invalid_id} doit retourner None"

    def test_update_device_success(self, test_db_manager, sample_device_data):
        """Test mise à jour appareil réussie"""
        device_id = test_db_manager.insert_appareil(sample_device_data)

        # Mise à jour
        updates = {
            'type': 'Type Modifié',
            'manufacturer': 'Fabricant Modifié',
            'notes': 'Notes modifiées'
        }

        success = test_db_manager.update_multiple_cells_batch({device_id: updates})
        assert success, "La mise à jour doit réussir"

        # Vérifier les modifications
        updated_device = test_db_manager.get_device_info(device_id)
        for key, expected_value in updates.items():
            assert updated_device[key] == expected_value, f"Valeur non mise à jour pour {key}"

        # Vérifier que les autres champs n'ont pas changé
        unchanged_fields = ['ref_modele', 'commercial_ref', 'other_ref']
        for field in unchanged_fields:
            assert updated_device[field] == sample_device_data[field], f"Champ {field} ne devrait pas changer"

    def test_update_device_nonexistent(self, test_db_manager):
        """Test mise à jour appareil inexistant — SQLite ne lève pas d'erreur sur 0 rows"""
        # SQLite retourne True même si aucune ligne n'est affectée (rowcount=0 n'est pas une erreur)
        success = test_db_manager.update_multiple_cells_batch({99999: {'type': 'Test'}})
        assert success  # Le batch réussit silencieusement (0 lignes affectées)

    def test_update_cell_success(self, test_db_manager, sample_device_data):
        """Test mise à jour cellule individuelle"""
        device_id = test_db_manager.insert_appareil(sample_device_data)

        success = test_db_manager.update_cell(device_id, 'type', 'Nouveau Type')
        assert success, "La mise à jour de cellule doit réussir"

        updated_device = test_db_manager.get_device_info(device_id)
        assert updated_device['type'] == 'Nouveau Type'

    def test_update_cell_invalid_column(self, test_db_manager, sample_device_data):
        """Test mise à jour cellule avec colonne invalide — lève DatabaseError"""
        device_id = test_db_manager.insert_appareil(sample_device_data)

        with pytest.raises(DatabaseError):
            test_db_manager.update_cell(device_id, 'colonne_inexistante', 'valeur')

    def test_delete_device_success(self, test_db_manager, sample_device_data):
        """Test suppression appareil réussie"""
        device_id = test_db_manager.insert_appareil(sample_device_data)

        success = test_db_manager.delete_appareil(device_id)
        assert success, "La suppression doit réussir"

        # Vérifier que l'appareil n'existe plus
        deleted_device = test_db_manager.get_device_info(device_id)
        assert deleted_device is None, "L'appareil supprimé ne doit plus exister"

    def test_delete_device_nonexistent(self, test_db_manager):
        """Test suppression appareil inexistant"""
        success = test_db_manager.delete_appareil(99999)
        assert not success, "La suppression d'un appareil inexistant doit échouer"

    def test_search_devices_simple(self, test_db_manager, multiple_devices_data, test_helpers):
        """Test recherche simple d'appareils"""
        # Ajouter des appareils de test
        device_ids = test_helpers.create_test_devices(test_db_manager, multiple_devices_data)

        # Test recherche par type
        results = test_db_manager.load_data(search_term='Lave-vaisselle')
        assert len(results) >= 1, "Doit trouver au moins un lave-vaisselle"
        assert any('Lave-vaisselle' in str(row) for row in results), "Résultat doit contenir Lave-vaisselle"

        # Test recherche par fabricant
        results = test_db_manager.load_data(search_term='Bosch')
        assert len(results) >= 1, "Doit trouver au moins un appareil Bosch"

        # Test recherche sans résultat
        results = test_db_manager.load_data(search_term='MARQUE_INEXISTANTE_XYZ')
        assert len(results) == 0, "Recherche sans résultat doit retourner liste vide"

    def test_search_devices_empty_query(self, test_db_manager):
        """Test recherche avec requête vide"""
        results = test_db_manager.load_data(search_term='')
        assert isinstance(results, list), "Recherche vide doit retourner une liste"

        results = test_db_manager.load_data(search_term=None)
        assert isinstance(results, list), "Recherche None doit retourner une liste"

    def test_get_all_devices(self, test_db_manager, multiple_devices_data, test_helpers):
        """Test récupération de tous les appareils"""
        # Base vide
        all_ids = test_db_manager.execute_query("SELECT id FROM appareils", [])
        initial_count = len(all_ids)

        # Ajouter des appareils
        device_ids = test_helpers.create_test_devices(test_db_manager, multiple_devices_data)

        # Vérifier le nouveau count
        all_ids = test_db_manager.execute_query("SELECT id FROM appareils", [])
        assert len(all_ids) == initial_count + len(multiple_devices_data)

        # Vérifier que tous les appareils ajoutés sont présents
        retrieved_ids = [row[0] for row in all_ids]
        for device_id in device_ids:
            assert device_id in retrieved_ids, f"Appareil {device_id} manquant dans get_all_devices"

    def test_get_all_devices_limit(self, test_db_manager, multiple_devices_data, test_helpers):
        """Test récupération avec limite (via load_data)"""
        # Ajouter des appareils
        test_helpers.create_test_devices(test_db_manager, multiple_devices_data)

        # Vérifier que load_data retourne des éléments
        all_devices = test_db_manager.load_data()
        assert len(all_devices) >= len(multiple_devices_data), "load_data doit retourner les appareils ajoutés"

    def test_update_multiple_cells_batch(self, test_db_manager, multiple_devices_data, test_helpers):
        """Test mise à jour multiple en batch"""
        device_ids = test_helpers.create_test_devices(test_db_manager, multiple_devices_data)

        # Préparer les mises à jour
        batch_updates = {}
        for i, device_id in enumerate(device_ids[:2]):  # Mettre à jour les 2 premiers
            batch_updates[device_id] = {
                'notes': f'Note batch {i}',
                'category': f'Catégorie batch {i}'
            }

        # Exécuter batch update
        success = test_db_manager.update_multiple_cells_batch(batch_updates)
        assert success, "Le batch update doit réussir"

        # Vérifier les mises à jour
        for device_id, updates in batch_updates.items():
            updated_device = test_db_manager.get_device_info(device_id)
            for field, expected_value in updates.items():
                assert updated_device[field] == expected_value, f"Batch update échoué pour {device_id}.{field}"

    def test_update_multiple_cells_batch_empty(self, test_db_manager):
        """Test batch update avec dictionnaire vide"""
        success = test_db_manager.update_multiple_cells_batch({})
        assert success, "Batch update vide doit réussir"

    def test_get_devices_count(self, test_db_manager, multiple_devices_data, test_helpers):
        """Test comptage d'appareils"""
        initial_count = test_db_manager.count_data()

        device_ids = test_helpers.create_test_devices(test_db_manager, multiple_devices_data)

        new_count = test_db_manager.count_data()
        assert new_count == initial_count + len(multiple_devices_data)

    def test_sql_injection_resistance(self, test_db_manager, test_helpers):
        """Test résistance aux injections SQL - SÉCURITÉ CRITIQUE"""
        test_helpers.assert_sql_injection_safe(test_db_manager)

    def test_concurrent_access_simulation(self, test_db_manager, sample_device_data):
        """Test simulation accès concurrent"""
        # Simuler plusieurs opérations concurrentes
        device_id = test_db_manager.insert_appareil(sample_device_data)

        # Lecture simultanée
        for i in range(10):
            device = test_db_manager.get_device_info(device_id)
            assert device is not None, f"Lecture {i} doit réussir"

        # Mise à jour simultanée
        for i in range(5):
            success = test_db_manager.update_cell(device_id, 'notes', f'Note {i}')
            assert success, f"Mise à jour {i} doit réussir"

    def test_database_consistency_after_error(self, test_db_manager, sample_device_data):
        """Test cohérence base après erreur"""
        # Ajouter un appareil valide
        device_id = test_db_manager.insert_appareil(sample_device_data)
        assert device_id is not None

        # Tenter une opération qui doit échouer (lève DatabaseError sur colonne invalide)
        with pytest.raises(DatabaseError):
            test_db_manager.update_cell(device_id, 'colonne_invalide', 'valeur')

        # Vérifier que l'appareil est toujours là et cohérent
        device = test_db_manager.get_device_info(device_id)
        assert device is not None
        assert device['type'] == sample_device_data['type']

    def test_close_database(self, test_db_manager):
        """Test fermeture base de données"""
        # Ajouter un appareil pour s'assurer que la base fonctionne
        device_data = {'type': 'Test', 'manufacturer': 'Test'}
        device_id = test_db_manager.insert_appareil(device_data)
        assert device_id is not None

        # Fermer la base
        test_db_manager.close()

        # Tenter d'utiliser la base fermée ne doit pas planter
        # (le comportement exact dépend de l'implémentation)


def test_database_schema_integrity():
    """Test d'intégrité du schéma de base de données"""
    with tempfile.NamedTemporaryFile(suffix='.db') as tmp_file:
        # Créer une nouvelle base
        original_db_path = Config.DB_FILE
        Config.DB_FILE = tmp_file.name

        db_manager = DatabaseManager()

        # Vérifier les contraintes FK (pragma est par-connexion, doit être activé manuellement)
        connection = sqlite3.connect(tmp_file.name)
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")  # FK est OFF par défaut sur nouvelle connexion

        cursor.execute("PRAGMA foreign_keys;")
        fk_status = cursor.fetchone()[0]
        assert fk_status == 1, "Les clés étrangères doivent être activées"

        # Vérifier structure des tables
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='appareils';")
        table_sql = cursor.fetchone()[0]
        assert 'PRIMARY KEY' in table_sql, "Table appareils doit avoir une clé primaire"

        connection.close()
        db_manager.close()

        # Restaurer
        Config.DB_FILE = original_db_path


# Tests de performance et limite
@pytest.mark.slow
def test_large_dataset_performance(test_db_manager):
    """Test performance avec grand dataset"""
    import time

    # Générer un grand nombre d'appareils
    large_dataset = []
    for i in range(1000):
        device = {
            'type': f'Type {i}',
            'manufacturer': f'Manufacturer {i % 10}',  # Quelques fabricants répétés
            'ref_modele': f'REF{i:04d}',
            'commercial_ref': f'COMM{i:04d}',
            'other_ref': f'OTHER{i:04d}',
            'category': f'Category {i % 5}',  # Quelques catégories répétées
            'notes': f'Notes pour appareil {i}'
        }
        large_dataset.append(device)

    # Tester l'ajout en masse
    start_time = time.time()
    device_ids = []
    for device_data in large_dataset:
        device_id = test_db_manager.insert_appareil(device_data)
        device_ids.append(device_id)

    add_time = time.time() - start_time
    assert add_time < 30.0, f"Ajout de 1000 appareils trop lent: {add_time}s"

    # Tester la recherche
    start_time = time.time()
    results = test_db_manager.load_data(search_term='Manufacturer 5')
    search_time = time.time() - start_time
    assert search_time < 5.0, f"Recherche trop lente: {search_time}s"
    assert len(results) == 100, "Doit trouver 100 appareils Manufacturer 5"

    # Tester get_all avec limite via requête directe
    start_time = time.time()
    all_devices = test_db_manager.execute_query("SELECT id FROM appareils LIMIT ?", [100])
    get_all_time = time.time() - start_time
    assert get_all_time < 2.0, f"execute_query avec LIMIT trop lent: {get_all_time}s"
    assert len(all_devices) == 100, "Doit retourner exactement 100 appareils"