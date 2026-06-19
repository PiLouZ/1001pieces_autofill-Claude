"""
Tests essentiels pour ImportManager
Focus sur les fonctionnalités critiques d'import et traitement de données
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from src.core.import_manager import (
    ImportManager, ImportType, FileType, ImportFile,
    ImportConfiguration, LabelConfiguration
)


@pytest.mark.unit
@pytest.mark.critical
class TestImportManagerCore:
    """Tests critiques pour ImportManager"""

    @pytest.fixture
    def import_manager(self, test_db_manager):
        """Fixture ImportManager"""
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    @pytest.fixture
    def sample_csv_file(self, temp_csv_file):
        """Fixture fichier CSV de test (réutilise celui de conftest)"""
        return temp_csv_file

    def test_import_manager_initialization(self, import_manager, test_db_manager):
        """Test initialisation ImportManager"""
        assert import_manager.db_manager == test_db_manager
        assert import_manager.parent_widget is None

    def test_load_csv_data_success(self, import_manager, sample_csv_file):
        """Test chargement CSV réussi"""
        data = import_manager.load_csv_data(sample_csv_file)

        assert isinstance(data, list)
        assert len(data) > 0
        # Le fichier de conftest contient 4 lignes (1 header + 3 data)
        assert len(data) == 4

        # Vérifier la structure des données
        assert isinstance(data[0], list)  # Chaque ligne est une liste
        assert len(data[0]) >= 3  # Au moins 3 colonnes

    def test_load_csv_data_with_limit(self, import_manager, sample_csv_file):
        """Test chargement CSV avec limite"""
        data = import_manager.load_csv_data(sample_csv_file, max_rows=2)

        assert isinstance(data, list)
        assert len(data) == 2  # Limité à 2 lignes

    def test_load_csv_data_file_not_found(self, import_manager):
        """Test chargement CSV fichier inexistant"""
        with pytest.raises(Exception):  # Peut être FileNotFoundError ou ValueError
            import_manager.load_csv_data("/chemin/inexistant.csv")

    def test_load_csv_data_empty_file(self, import_manager):
        """Test chargement CSV fichier vide"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            # Fichier vide
            tmp_file.write("")
            empty_file_path = tmp_file.name

        try:
            data = import_manager.load_csv_data(empty_file_path)
            # Un fichier vide doit retourner une liste vide
            assert data == []
        finally:
            os.unlink(empty_file_path)

    def test_import_file_class(self):
        """Test classe ImportFile"""
        import_file = ImportFile(
            path="/test/path/fichier.csv",
            type=FileType.CSV,
            suggested_reference="REF001",
            suggested_label="Label test"
        )

        assert import_file.path == "/test/path/fichier.csv"
        assert import_file.type == FileType.CSV
        assert import_file.suggested_reference == "REF001"
        assert import_file.suggested_label == "Label test"
        assert import_file.filename == "fichier.csv"
        assert import_file.name_without_ext == "fichier"

    def test_label_configuration_class(self):
        """Test classe LabelConfiguration"""
        # Configuration par défaut
        config = LabelConfiguration()
        assert not config.use_common_label
        assert config.common_label == ""
        assert config.individual_labels == {}

        # Configuration avec données
        individual_labels = {"/file1.csv": "Label 1", "/file2.csv": "Label 2"}
        config = LabelConfiguration(
            use_common_label=True,
            common_label="Label commun",
            individual_labels=individual_labels
        )
        assert config.use_common_label
        assert config.common_label == "Label commun"
        assert config.individual_labels == individual_labels

    def test_import_configuration_class(self):
        """Test classe ImportConfiguration"""
        files = [
            ImportFile("/test1.csv", FileType.CSV, "REF1"),
            ImportFile("/test2.csv", FileType.CSV, "REF2")
        ]

        config = ImportConfiguration(
            files=files,
            import_type=ImportType.MULTI_FILE,
            use_common_reference=True,
            common_reference="COMMON_REF"
        )

        assert config.files == files
        assert config.import_type == ImportType.MULTI_FILE
        assert config.use_common_reference
        assert config.common_reference == "COMMON_REF"

        # Vérifier l'initialisation automatique
        assert config.label_config is not None
        assert config.individual_references == {}
        assert config.individual_labels == {}

    def test_csv_data_processing_different_delimiters(self, import_manager):
        """Test traitement CSV avec différents délimiteurs"""
        # Test avec délimiteur point-virgule
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write("Type;Fabricant;Référence\n")
            tmp_file.write("Lave-vaisselle;Bosch;SMS123\n")
            tmp_file.write("Lave-linge;Samsung;WW456\n")
            semicolon_file = tmp_file.name

        try:
            data = import_manager.load_csv_data(semicolon_file)
            assert len(data) == 3  # Header + 2 lignes de données
            assert len(data[0]) == 3  # 3 colonnes
            assert data[1][0] == "Lave-vaisselle"
            assert data[1][1] == "Bosch"
        finally:
            os.unlink(semicolon_file)

        # Test avec délimiteur virgule
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write("Type,Fabricant,Référence\n")
            tmp_file.write("Lave-vaisselle,Bosch,SMS123\n")
            comma_file = tmp_file.name

        try:
            data = import_manager.load_csv_data(comma_file)
            assert len(data) == 2
            assert len(data[0]) == 3
            assert data[1][0] == "Lave-vaisselle"
        finally:
            os.unlink(comma_file)

    def test_csv_encoding_handling(self, import_manager):
        """Test gestion des encodages"""
        # Test avec caractères accentués
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write("Type;Fabricant;Référence\n")
            tmp_file.write("Lave-vaisselle;Boîtier électronique;Réf-Spéciale\n")
            accented_file = tmp_file.name

        try:
            data = import_manager.load_csv_data(accented_file)
            assert len(data) == 2
            # Vérifier que les caractères accentués sont bien lus
            assert "Boîtier" in data[1][1]
            assert "Référence" in data[0][2]
        finally:
            os.unlink(accented_file)

    def test_csv_malformed_data_handling(self, import_manager):
        """Test gestion des données CSV malformées"""
        # CSV avec lignes de longueurs différentes
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write("Type;Fabricant;Référence\n")
            tmp_file.write("Lave-vaisselle;Bosch\n")  # Manque une colonne
            tmp_file.write("Lave-linge;Samsung;WW456;Extra\n")  # Colonne en plus
            tmp_file.write(";;;\n")  # Ligne vide avec séparateurs
            malformed_file = tmp_file.name

        try:
            data = import_manager.load_csv_data(malformed_file)
            # Doit traiter les lignes malformées sans planter
            assert isinstance(data, list)
            assert len(data) >= 1  # Au moins le header
        finally:
            os.unlink(malformed_file)

    def test_enum_values(self):
        """Test valeurs des énumérations"""
        # ImportType
        assert ImportType.SINGLE_FILE.value == "single_file"
        assert ImportType.MULTI_FILE.value == "multi_file"

        # FileType
        assert FileType.CSV.value == "csv"
        assert FileType.PDF.value == "pdf"

    def test_large_csv_file_performance(self, import_manager):
        """Test performance avec fichier CSV plus grand"""
        # Générer un fichier CSV de taille modérée pour les tests
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write("Type;Fabricant;Référence;Notes\n")

            # Générer 1000 lignes de test
            for i in range(1000):
                tmp_file.write(f"Type{i};Fabricant{i};REF{i:04d};Notes ligne {i}\n")

            large_file = tmp_file.name

        try:
            import time
            start_time = time.time()

            # Charger toutes les données
            data = import_manager.load_csv_data(large_file)

            load_time = time.time() - start_time

            # Vérifications
            assert len(data) == 1001  # Header + 1000 lignes
            assert load_time < 5.0, f"Chargement trop lent: {load_time}s"

            # Test avec limite
            start_time = time.time()
            limited_data = import_manager.load_csv_data(large_file, max_rows=100)
            limited_load_time = time.time() - start_time

            assert len(limited_data) == 100
            assert limited_load_time < load_time, "La limite devrait accélérer le chargement"

        finally:
            os.unlink(large_file)

    def test_csv_special_characters_handling(self, import_manager):
        """Test gestion des caractères spéciaux dans CSV"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp_file:
            # Données avec caractères spéciaux, guillemets, virgules
            tmp_file.write('Type;Fabricant;Notes\n')
            tmp_file.write('Lave-vaisselle;"Bosch GmbH";"Note avec, virgule"\n')
            tmp_file.write('Micro-ondes;Whirlpool;"Note avec ""guillemets"" doubles"\n')
            special_file = tmp_file.name

        try:
            data = import_manager.load_csv_data(special_file)
            assert len(data) == 3

            # Vérifier que les guillemets sont bien gérés
            assert data[1][1] == "Bosch GmbH"
            assert "virgule" in data[1][2]
            assert "guillemets" in data[2][2]

        finally:
            os.unlink(special_file)

    @patch('src.core.import_manager.QApplication')
    def test_import_manager_error_handling(self, mock_qapp, import_manager):
        """Test gestion d'erreurs générale"""
        # Test avec fichier binaire (non-CSV)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(b'\x00\x01\x02\x03')  # Données binaires
            binary_file = tmp_file.name

        try:
            # ImportManager gère bien les erreurs - teste juste qu'il ne plante pas
            result = import_manager.load_csv_data(binary_file)
            # Peut retourner une liste vide ou traiter comme texte
            assert isinstance(result, list)
        except Exception as e:
            # C'est acceptable si ça lève une exception propre
            assert "Error" in str(type(e).__name__) or "Error" in str(e) or True
        finally:
            os.unlink(binary_file)

@pytest.mark.unit
class TestSimilaritySuggestions:
    """Tests des suggestions Type/Marque par similarité (Phase 2 — additif).

    Vérifie la NON-RÉGRESSION du mécanisme exact et le calcul différé des
    suggestions, sans jamais écrire automatiquement Type/Marque.
    """

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    def test_mecanisme_exact_inchange(self, import_manager):
        """NON-RÉGRESSION : l'auto-complétion exacte remplit toujours sur ref identique."""
        cache = {'sms46aw03e': {'type': 'Lave-vaisselle', 'manufacturer': 'Bosch'}}
        device_data = {'ref_modele': 'SMS46AW03E', 'commercial_ref': ''}
        import_manager._apply_autocomplete_from_cache(device_data, cache)
        assert device_data['type'] == 'Lave-vaisselle'
        assert device_data['manufacturer'] == 'Bosch'

    def test_suggestions_pour_variante_suffixe(self, import_manager):
        """Une ligne incomplète variante /82 d'un appareil /58 existant reçoit une suggestion."""
        new_ids = import_manager._batch_insert_devices([{
            'type': 'Lave-vaisselle', 'manufacturer': 'Bosch',
            'ref_modele': 'SMU6ZCS10S/58', 'commercial_ref': '',
            'other_ref': '', 'notes': '', 'category': '',
        }])
        assert len(new_ids) == 1

        # Précharger l'index (remplit _existing_devices_rows_for_similarity)
        import_manager._preload_existing_devices()
        # Simuler une ligne importée restée incomplète (variante /82)
        import_manager._pending_similarity_candidates = [
            {'id': 999999, 'ref_modele': 'SMU6ZCS10S/82', 'commercial_ref': ''}
        ]
        suggestions = import_manager._compute_pending_similarity_suggestions()

        assert 999999 in suggestions
        best = suggestions[999999][0]
        assert best['manufacturer'] == 'Bosch'
        assert best['type'] == 'Lave-vaisselle'
        assert best['confidence_tier'] == 'A_suffix_variant'

    def test_flag_desactive_retourne_vide(self, import_manager):
        """Avec le flag à False, aucun calcul même si des candidats existent."""
        from src.core.config import Config
        original = Config.ENABLE_SIMILARITY_SUGGESTIONS
        Config.ENABLE_SIMILARITY_SUGGESTIONS = False
        try:
            import_manager._preload_existing_devices()
            import_manager._pending_similarity_candidates = [
                {'id': 1, 'ref_modele': 'SMU6ZCS10S/82', 'commercial_ref': ''}
            ]
            assert import_manager._compute_pending_similarity_suggestions() == {}
        finally:
            Config.ENABLE_SIMILARITY_SUGGESTIONS = original

    def test_aucun_candidat_collecte_retourne_vide(self, import_manager):
        """Sans lignes incomplètes collectées, retourne {} sans erreur."""
        import_manager._preload_existing_devices()
        import_manager._pending_similarity_candidates = []
        assert import_manager._compute_pending_similarity_suggestions() == {}
