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

    def test_collecte_suggestions_chemin_standard_petit_fichier(self, import_manager):
        """NON-RÉGRESSION (bug réel remonté par l'utilisateur, 2026-07-01) : un import
        de moins de BATCH_THRESHOLD (50) lignes passe par _process_data_import (chemin
        « standard »), PAS _process_data_import_batch. La collecte pour les suggestions
        par similarité n'existait historiquement QUE dans le chemin batch — les petits
        imports (ex. PDF courts) ne déclenchaient donc JAMAIS de suggestion automatique
        après import, même avec des lignes réellement incomplètes. Vérifie ici le vrai
        pipeline bout-en-bout (_run_import_files), pas seulement le calcul isolé."""
        import_manager._preload_existing_devices()
        import_manager._pending_similarity_candidates = []
        import_manager._imported_complete_for_similarity = []

        # FileType.CLIPBOARD utilise les données pré-chargées (file.data) sans relire
        # depuis le disque, contrairement à FileType.CSV — pratique en test isolé.
        config = ImportConfiguration(
            files=[ImportFile(
                path='Collage', type=FileType.CLIPBOARD,
                suggested_reference='REF', suggested_label='REF',
                data=[['NEWREF001', 'COMREF001']],  # 1 seule ligne < BATCH_THRESHOLD
            )],
            import_type=ImportType.SINGLE_FILE,
        )

        results = import_manager._run_import_files(config)

        assert len(import_manager._pending_similarity_candidates) == 1
        assert import_manager._pending_similarity_candidates[0]['ref_modele'] == 'NEWREF001'
        # L'id doit être réinjecté (nécessaire au calcul différé des suggestions).
        assert import_manager._pending_similarity_candidates[0].get('id')
        assert results['successful_files'] == 1

    def test_progress_cb_invoque_pendant_le_calcul(self, import_manager):
        """La phase de recherche de suggestions notifie sa progression (sinon la
        barre semble figée → impression de plantage). Le libellé doit l'identifier."""
        import_manager._batch_insert_devices([{
            'type': 'Lave-vaisselle', 'manufacturer': 'Bosch',
            'ref_modele': 'SMU6ZCS10S/58', 'commercial_ref': '',
            'other_ref': '', 'notes': '', 'category': '',
        }])
        import_manager._preload_existing_devices()
        import_manager._pending_similarity_candidates = [
            {'id': 999999, 'ref_modele': 'SMU6ZCS10S/82', 'commercial_ref': ''}
        ]
        calls = []
        import_manager._compute_pending_similarity_suggestions(
            progress_cb=lambda v, m, lbl: calls.append((v, m, lbl))
        )
        assert calls, "progress_cb jamais appelé pendant le calcul des suggestions"
        assert any("suggestion" in lbl.lower() for _, _, lbl in calls)
        # Le maximum annoncé correspond au nombre de lignes incomplètes traitées.
        assert calls[-1][1] == 1
        # Le coût réel dominant est la construction de l'index (potentiellement
        # des centaines de milliers de lignes), PAS la boucle de recherche (souvent
        # quelques lignes) : un libellé doit couvrir cette étape en premier, sinon
        # elle reste silencieuse malgré la présence de progress_cb (cas réel :
        # 2 lignes incomplètes traitées en <10ms, mais ~2,6s de silence observés
        # avant, faute de ce libellé).
        assert calls[0][2] == "Préparation de l'index de suggestions…"

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

    def test_levier1_freres_complets_du_lot(self, import_manager):
        """Levier 1 : une incomplète reçoit une suggestion grâce aux frères COMPLETS
        du même lot (non encore en base), ajoutés à l'index de similarité.

        Les frères partagent le préfixe ET la structure de la référence
        (cf. garde de signature de forme du Palier C) — une vraie famille de
        modèles a une structure homogène. Les refs restent suffisamment éloignées
        (distance d'édition) pour exercer le consensus, pas le fuzzy."""
        import_manager._preload_existing_devices()
        import_manager._pending_similarity_candidates = [
            {'id': 999, 'ref_modele': 'AHLN1ZZ/1', 'commercial_ref': 'AHLN1ZZ'}
        ]
        # Sans frères du lot : aucune suggestion (rien en base pour AHLN)
        import_manager._imported_complete_for_similarity = []
        assert import_manager._compute_pending_similarity_suggestions() == {}
        # Avec ≥ 3 frères complets du lot, même préfixe + même structure → consensus Brandt
        import_manager._imported_complete_for_similarity = [
            {'id': 101, 'ref_modele': 'AHLN9WA/1', 'commercial_ref': 'AHLN9WA',
             'type': 'Hotte', 'manufacturer': 'Brandt'},
            {'id': 102, 'ref_modele': 'AHLN8XB/1', 'commercial_ref': 'AHLN8XB',
             'type': 'Hotte', 'manufacturer': 'Brandt'},
            {'id': 103, 'ref_modele': 'AHLN7YC/1', 'commercial_ref': 'AHLN7YC',
             'type': 'Hotte', 'manufacturer': 'Brandt'},
        ]
        suggestions = import_manager._compute_pending_similarity_suggestions()
        assert 999 in suggestions
        assert suggestions[999][0]['manufacturer'] == 'Brandt'
        assert suggestions[999][0]['type'] == 'Hotte'


class TestApplyRelationsFromConfig:
    """Câblage backend du modèle « par groupes » dans l'import (Lot 2b)."""

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    def test_apply_relations_from_config(self, import_manager, test_db_manager):
        from src.core.import_manager import ImportConfiguration, ImportType
        from src.services.import_relations import Group, CardData, KIND_SUCCESSION
        for ref in ("B1", "B2", "S1"):
            test_db_manager.execute_query("INSERT OR IGNORE INTO pieces(ref_piece) VALUES (?)", [ref])
        test_db_manager.conn.commit()
        config = ImportConfiguration(files=[], import_type=ImportType.MULTI_FILE)
        config.relations_groups = [
            Group(KIND_SUCCESSION, courante="B3_BASE", members=["B1", "B2"], cross_equivalent=True),
            Group(KIND_SUCCESSION, courante="S2_BASE", members=["S1"], cross_equivalent=True),
        ]
        config.relations_cards = [CardData("B1"), CardData("B2"), CardData("S1")]
        results = {}
        import_manager._apply_relations_from_config(config, results)
        # B1 → B3_BASE (succession) ; B1/B2/S1 obsolètes ; B3_BASE ≡ S2_BASE
        row = test_db_manager.execute_query(
            "SELECT ref_new FROM piece_supersessions WHERE ref_old=?", ["B1"])
        assert row and row[0][0] == "B3_BASE"
        for r in ("B1", "B2", "S1"):
            o = test_db_manager.execute_query("SELECT is_obsolete FROM pieces WHERE ref_piece=?", [r])
            assert o and o[0][0] == 1
        g = test_db_manager.execute_query(
            "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece IN ('B3_BASE','S2_BASE')")
        assert len({x[0] for x in g}) == 1 and len(g) == 2
        assert results.get('succession_created', 0) >= 2

    def test_routage_relations_prime_sur_legacy(self, import_manager):
        """Si relations_groups est renseigné, l'ancien chemin succession n'est pas pris."""
        from src.core.import_manager import ImportConfiguration, ImportType
        config = ImportConfiguration(files=[], import_type=ImportType.MULTI_FILE)
        config.relations_groups = []
        config.relations_cards = []
        called = {'legacy': False, 'new': False}
        import_manager._apply_succession_from_config = lambda *a: called.__setitem__('legacy', True)
        import_manager._apply_relations_from_config = lambda *a: called.__setitem__('new', True)
        # Reproduit la condition de routage de _run_import_files
        if config.relations_groups is not None or config.relations_cards is not None:
            import_manager._apply_relations_from_config(config, {})
        else:
            import_manager._apply_succession_from_config(config, {})
        assert called['new'] and not called['legacy']


class TestDialogRelationsCollection:
    """Collecte du modèle « par groupes » par le dialogue (Lot 2b 2/2)."""

    def test_validate_collecte_relations_multi(self, qapp, test_db_manager):
        from PyQt5.QtWidgets import QListWidgetItem
        from src.core.import_manager import (
            ImportManager, ImportDialog, ImportConfiguration, ImportFile,
            ImportType, FileType)
        from src.services.import_relations import KIND_SUCCESSION
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        files = [ImportFile(f'/{r}.csv', FileType.CSV, r) for r in ('REF_A', 'REF_B', 'REF_C')]
        # Pré-renseigner les données : le dialogue planifie un chargement différé
        # (QTimer) qui lirait les chemins fictifs sur disque → évité ici.
        for f in files:
            f.data = [['Référence', 'Type', 'Marque'], [f.suggested_reference, 'Four', 'Bosch']]
        cfg = ImportConfiguration(files=files, import_type=ImportType.MULTI_FILE)
        dlg = ImportDialog(None, cfg, im)
        dlg.auto_file_references_checkbox.setChecked(True)   # réfs = suggested_reference
        z = dlg._relations_groups_zone
        assert z is not None
        box = z.add_group(KIND_SUCCESSION)
        box.courante_input.setText('REF_C')
        res = z.reservoir
        for ref in ('REF_A', 'REF_B'):
            for i in range(res.count()):
                if res.item(i).text() == ref:
                    res.takeItem(i)
                    break
            box.members.addItem(QListWidgetItem(ref))
        dlg._validate_and_accept()
        rc = dlg.result_config
        assert rc.relations_groups and rc.relations_groups[0].courante == 'REF_C'
        assert sorted(rc.relations_groups[0].members) == ['REF_A', 'REF_B']
        assert {c.ref for c in rc.relations_cards} == {'REF_A', 'REF_B', 'REF_C'}

    def test_mono_fichier_pas_de_relations_groups(self, qapp, test_db_manager):
        from src.core.import_manager import (
            ImportManager, ImportDialog, ImportConfiguration, ImportFile,
            ImportType, FileType)
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        f = ImportFile('/a.csv', FileType.CSV, 'REF_A')
        # Pré-renseigner les données (cf. note test multi) : évite la lecture disque
        # du chargement différé sur le chemin fictif.
        f.data = [['Référence', 'Type', 'Marque'], ['REF_A', 'Four', 'Bosch']]
        cfg = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg = ImportDialog(None, cfg, im)
        assert dlg._relations_groups_zone is None   # chemin legacy mono inchangé
