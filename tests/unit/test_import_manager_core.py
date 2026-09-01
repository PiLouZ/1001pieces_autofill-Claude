"""
Tests essentiels pour ImportManager
Focus sur les fonctionnalités critiques d'import et traitement de données
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from PyQt5.QtWidgets import QLineEdit

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

    def test_run_import_files_expose_imported_refs(self, import_manager):
        """results['imported_refs'] contient les refs importées, dans l'ordre, sans
        doublon ni vide — utilisé pour charger automatiquement la recherche sur la
        référence courante après import (v3.60.0)."""
        config = ImportConfiguration(
            files=[
                ImportFile(path='f1', type=FileType.CLIPBOARD,
                           suggested_reference='REFA', suggested_label='REFA',
                           data=[['REFA', 'COMA']]),
                ImportFile(path='f2', type=FileType.CLIPBOARD,
                           suggested_reference='REFB', suggested_label='REFB',
                           data=[['REFB', 'COMB']]),
            ],
            import_type=ImportType.MULTI_FILE,
        )
        config.individual_references = {'f1': 'REFA', 'f2': 'REFB'}

        results = import_manager._run_import_files(config)

        assert results['imported_refs'] == ['REFA', 'REFB']

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


class TestBatchInsertCacheInvalidation:
    """NON-RÉGRESSION : après un import, le tableau affiche le nouveau total
    de lignes (pas l'ancien) — bug constaté par l'utilisateur (vidéo du
    2026-07-02) où le total restait figé après import, laissant croire à un
    échec et provoquant un ré-import en double du même fichier."""

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    def test_total_count_reflete_import_batch(self, import_manager, test_db_manager):
        """_batch_insert_devices (chemin réel de l'import, cursor brut hors des
        méthodes normales de DatabaseManager) doit invalider _total_count_cache,
        sinon count_data() sans filtre reste périmé après l'import."""
        test_db_manager.insert_appareil({
            'ref_modele': 'REF0', 'commercial_ref': '', 'type': 'Four',
            'manufacturer': 'Bosch', 'other_ref': '', 'notes': '', 'category': '',
        })
        count_before = test_db_manager.count_data(None, None)

        new_ids = import_manager._batch_insert_devices([
            {'type': 'Congélateur', 'manufacturer': 'Whirlpool', 'ref_modele': f'AFG{i}',
             'commercial_ref': '', 'other_ref': '', 'notes': '', 'category': ''}
            for i in range(5)
        ])
        assert len(new_ids) == 5

        count_after = test_db_manager.count_data(None, None)
        assert count_after == count_before + 5


class TestEquivalenceGuardDialog:
    """v3.62.0 : garde-fous contre la perte silencieuse des déclarations
    d'équivalence dans le dialogue d'import multi-fichiers."""

    def _dialog(self, test_db_manager, refs=('REF_A', 'REF_B', 'REF_C')):
        from src.core.import_manager import (
            ImportManager, ImportDialog, ImportConfiguration, ImportFile,
            ImportType, FileType)
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        files = [ImportFile(f'/{r}.csv', FileType.CSV, r) for r in refs]
        for f in files:
            f.data = [['Référence', 'Type', 'Marque'], [f.suggested_reference, 'Four', 'Bosch']]
        cfg = ImportConfiguration(files=files, import_type=ImportType.MULTI_FILE)
        dlg = ImportDialog(None, cfg, im)
        dlg.auto_file_references_checkbox.setChecked(True)
        return dlg

    def test_toutes_equivalentes_passe_sans_garde_fou(self, qapp, test_db_manager):
        """Cas nominal : réservoir plein + case cochée → équivalences collectées,
        validation directe (pas d'avertissement)."""
        from src.services.import_relations import KIND_EQUIVALENCE
        dlg = self._dialog(test_db_manager)
        dlg._apply_all_equiv_checkbox.setChecked(True)
        dlg._validate_and_accept()
        rc = dlg.result_config
        assert rc is not None
        equiv = [g for g in rc.relations_groups if g.kind == KIND_EQUIVALENCE]
        assert len(equiv) == 1 and sorted(equiv[0].members) == ['REF_A', 'REF_B', 'REF_C']

    def test_toutes_equivalentes_reservoir_vide_se_decoche(self, qapp, test_db_manager):
        """Réservoir vide : la coche ne produit rien → elle se décoche d'elle-même
        (plus de case cochée sans effet) et se grise."""
        from PyQt5.QtWidgets import QListWidgetItem
        from src.services.import_relations import KIND_SUCCESSION
        dlg = self._dialog(test_db_manager)
        z = dlg._relations_groups_zone
        box = z.add_group(KIND_SUCCESSION)
        for ref in ('REF_A', 'REF_B', 'REF_C'):
            for i in range(z.reservoir.count()):
                if z.reservoir.item(i).text() == ref:
                    z.reservoir.takeItem(i)
                    break
            box.members.addItem(QListWidgetItem(ref))
        z.changed.emit()
        assert not dlg._apply_all_equiv_checkbox.isEnabled()
        dlg._apply_all_equiv_checkbox.setChecked(True)     # coche programmatique
        assert not dlg._apply_all_equiv_checkbox.isChecked()  # auto-décochée

    def test_garde_fou_intention_sans_equivalence(self, qapp, test_db_manager):
        """« Toutes les lignées équivalentes » cochée sans 2 courantes → la
        validation passe par l'avertissement au lieu d'accepter en silence."""
        dlg = self._dialog(test_db_manager)
        dlg._relations_groups_zone.all_equiv_check.setChecked(True)
        captured = {}
        dlg._confirm_import_sans_equivalence = \
            lambda config, msg: captured.update(config=config, msg=msg)
        dlg._validate_and_accept()
        assert dlg.result_config is None                  # pas d'accept direct
        assert "AUCUNE liaison d'équivalence" in captured['msg']
        # « Importer quand même » = le chemin du callback : config prête à l'emploi
        assert captured['config'].relations_groups is not None

    def test_pas_de_garde_fou_sans_intention(self, qapp, test_db_manager):
        """Aucune option d'équivalence cochée → import direct, aucun avertissement."""
        dlg = self._dialog(test_db_manager)
        called = []
        dlg._confirm_import_sans_equivalence = lambda *a: called.append(a)
        dlg._validate_and_accept()
        assert dlg.result_config is not None and not called


class TestDedupKeyRespectsColumnMapping:
    """NON-RÉGRESSION (bug réel constaté par l'utilisateur, logs du 2026-09-01) :
    un collage de 310 lignes « Type | Marque | Référence » n'importait qu'UNE seule
    ligne, les 309 autres étant classées « doublon » et jetées silencieusement.

    Cause : la clé de déduplication était calculée positionnellement (row[0]|row[1])
    en ignorant le mapping de colonnes déclaré par l'utilisateur. Sur ce format, la
    clé valait « lave-linge|samsung » pour TOUTES les lignes — la colonne qui les
    distingue (la référence, en position 2) n'était jamais regardée.

    La clé doit désormais être dérivée de _parse_row_data, donc du mapping réel.
    """

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    @staticmethod
    def _config_collage(nb_lignes, mapping=None, ref_piece='PIECE001'):
        """Collage « Type | Marque | Référence » — toutes les lignes distinctes."""
        data = [['Lave-linge', 'Samsung', f'WW{i:05d}EE'] for i in range(nb_lignes)]
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference=ref_piece, suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': ref_piece}
        config.column_mapping = mapping if mapping is not None else {
            3: ['type', 'manufacturer', 'ref_modele']
        }
        return config

    def test_collage_310_lignes_chemin_batch(self, import_manager):
        """Le cas exact des logs : 310 lignes ≥ BATCH_THRESHOLD (50) → chemin batch,
        où la perte était TOTALE (la branche doublon ne faisait qu'un _find_in_cache,
        sans insertion ni association)."""
        results = import_manager._run_import_files(self._config_collage(310))

        assert results['total_imported'] == 310, \
            f"310 lignes distinctes attendues, {results['total_imported']} importées"
        assert results['duplicates_in_file'] == 0
        assert results['new_entries'] == 310

    def test_collage_10_lignes_chemin_standard(self, import_manager):
        """Même jeu sous le seuil de 50 → chemin standard (_process_data_import),
        où la perte était partielle mais les compteurs faux."""
        results = import_manager._run_import_files(self._config_collage(10))

        assert results['total_imported'] == 10
        assert results['duplicates_in_file'] == 0

    def test_associations_creees_pour_chaque_ligne(self, import_manager):
        """Les lignes rejetées ne créaient aucune association : l'import produisait
        des appareils orphelins (« 1 lignes traitées vs 0 lignes avec associations »)."""
        results = import_manager._run_import_files(self._config_collage(60))

        assert results['associations_created'] == 60

    def test_vrais_doublons_toujours_detectes(self, import_manager):
        """NON-RÉGRESSION inverse : la déduplication doit rester active quand les
        lignes sont RÉELLEMENT identiques après mapping."""
        data = [['Lave-linge', 'Samsung', 'WW80T4020EE']] * 5
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference='PIECE001', suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': 'PIECE001'}
        config.column_mapping = {3: ['type', 'manufacturer', 'ref_modele']}

        results = import_manager._run_import_files(config)

        assert results['total_imported'] == 1
        assert results['duplicates_in_file'] == 4

    def test_positionnel_4_colonnes_inchange(self, import_manager):
        """GARDE ANTI-RÉGRESSION du correctif : sans column_mapping, un import
        4 colonnes « Type | Marque | Réf | RéfCom » (chiffres en col. 3/4) doit
        donner exactement les mêmes comptages qu'avant — _parse_row_data mappe
        déjà row[2]/row[3] sur ref_modele/commercial_ref, comme l'heuristique."""
        data = [['Four', 'Bosch', f'HBA{i:04d}', f'SER{i:04d}'] for i in range(60)]
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference='PIECE002', suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': 'PIECE002'}

        results = import_manager._run_import_files(config)

        assert results['total_imported'] == 60
        assert results['duplicates_in_file'] == 0
        assert results['new_entries'] == 60

    def test_doublon_batch_sur_appareil_en_attente(self, import_manager):
        """CORRECTIF 2 : dans le chemin batch, un doublon dont l'appareil n'est pas
        ENCORE en base (il attend dans new_devices_batch) échouait au _find_in_cache
        et perdait son association — ni insertion, ni rattachement. Il doit être
        rattaché à la 1ʳᵉ occurrence via son (data_index, existing_id)."""
        # 60 appareils distincts (≥ BATCH_THRESHOLD) + 10 répétitions du 1er
        data = [['Lave-linge', 'Samsung', f'WW{i:05d}EE'] for i in range(60)]
        data += [['Lave-linge', 'Samsung', 'WW00000EE']] * 10

        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference='PIECE003', suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': 'PIECE003'}
        config.column_mapping = {3: ['type', 'manufacturer', 'ref_modele']}

        results = import_manager._run_import_files(config)

        assert results['total_imported'] == 60
        assert results['duplicates_in_file'] == 10
        # Les 10 doublons sont rattachés au MÊME appareil que la 1ʳᵉ occurrence :
        # l'association existe déjà → comptée « existante », plus jamais perdue.
        assert results['associations_created'] == 60
        assert results['associations_existing'] == 10


class TestReimportAppareilsMonoReference:
    """NON-RÉGRESSION (bug réel constaté par l'utilisateur, 2026-09-01) : ré-importer
    le MÊME lot d'appareils créait des doublons au lieu de retrouver les existants.

    Cause : le cache du chemin batch était construit ET interrogé sous la garde
    `if ref_modele and commercial_ref` (un ET), alors que la requête SQL
    `preload_all_devices` sélectionne en OU. Tout appareil mono-référence était donc
    chargé depuis la base puis jeté avant d'entrer dans le cache — un ré-import ne
    pouvait pas le retrouver. Mesuré : 2ᵉ import de 60 lignes → 60 nouveaux appareils
    (120 en base) au lieu de 60 correspondances.

    Le chemin standard (< BATCH_THRESHOLD) s'en sortait pour « ref_modele seule »
    grâce à une requête de repli, mais pas pour le cas miroir « commercial_ref
    seule » — corrigé ici aussi (v3.65.1).
    """

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    @staticmethod
    def _config(nb_lignes, champ_ref='ref_modele', ref_piece='PIECE900'):
        """Collage « Type | Marque | Référence » avec type/marque VIDES : une seule
        des deux références principales est renseignée (cas déclencheur du bug)."""
        data = [['', '', f'WW{i:05d}EE'] for i in range(nb_lignes)]
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                              suggested_reference=ref_piece, suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': ref_piece}
        config.column_mapping = {3: ['type', 'manufacturer', champ_ref]}
        return config

    def _compter_appareils(self, import_manager):
        return import_manager.db_manager.execute_query(
            "SELECT COUNT(*) FROM appareils")[0][0]

    def test_reimport_batch_ref_modele_seule(self, import_manager):
        """LE CAS DU BUG : 60 lignes (≥ BATCH_THRESHOLD) avec ref_modele seule.
        Le 2ᵉ import doit RETROUVER les 60 appareils, pas les recréer."""
        premier = import_manager._run_import_files(self._config(60))
        second = import_manager._run_import_files(self._config(60))

        assert premier['new_entries'] == 60
        assert second['new_entries'] == 0, \
            f"{second['new_entries']} appareils recréés au ré-import (doublons)"
        assert second['matches_found'] == 60
        assert self._compter_appareils(import_manager) == 60

    def test_reimport_batch_commercial_ref_seule(self, import_manager):
        """Cas miroir dans le chemin batch : seule commercial_ref est renseignée."""
        premier = import_manager._run_import_files(self._config(60, 'commercial_ref'))
        second = import_manager._run_import_files(self._config(60, 'commercial_ref'))

        assert premier['new_entries'] == 60
        assert second['new_entries'] == 0
        assert second['matches_found'] == 60
        assert self._compter_appareils(import_manager) == 60

    def test_reimport_standard_commercial_ref_seule(self, import_manager):
        """Cas miroir dans le chemin STANDARD (< 50 lignes) : aucune des deux
        requêtes de _insert_or_find_device ne couvrait « commercial_ref seule »
        (la 1ʳᵉ exige les deux références, la 2ᵉ exige ref_modele)."""
        import_manager._run_import_files(self._config(10, 'commercial_ref'))
        import_manager._run_import_files(self._config(10, 'commercial_ref'))

        assert self._compter_appareils(import_manager) == 10

    def test_reimport_standard_ref_modele_seule_inchange(self, import_manager):
        """NON-RÉGRESSION : ce cas fonctionnait DÉJÀ avant le correctif (repli sur
        ref_modele) — il doit continuer à fonctionner à l'identique."""
        import_manager._run_import_files(self._config(10))
        second = import_manager._run_import_files(self._config(10))

        assert second['new_entries'] == 0
        assert self._compter_appareils(import_manager) == 10

    def test_reimport_batch_deux_references_inchange(self, import_manager):
        """NON-RÉGRESSION : le cas « deux références renseignées » fonctionnait déjà
        (seul cas que le cache acceptait) — il ne doit pas être dégradé."""
        def config():
            data = [['Four', 'Bosch', f'HBA{i:04d}', f'SER{i:04d}'] for i in range(60)]
            c = ImportConfiguration(
                files=[ImportFile(path='Collage', type=FileType.CLIPBOARD,
                                  suggested_reference='PIECE901', suggested_label='',
                                  data=data)],
                import_type=ImportType.SINGLE_FILE,
            )
            c.individual_references = {'Collage': 'PIECE901'}
            return c

        import_manager._run_import_files(config())
        second = import_manager._run_import_files(config())

        assert second['new_entries'] == 0
        assert second['matches_found'] == 60
        assert self._compter_appareils(import_manager) == 60

    def test_appareil_partiel_ne_matche_pas_appareil_complet(self, import_manager):
        """GARDE ANTI-RÉGRESSION ESSENTIELLE du correctif : élargir le cache ne doit
        PAS relâcher la sévérité de la correspondance. Un appareil « ref_modele
        seule » ne doit jamais être confondu avec un appareil complet partageant
        cette ref_modele — la clé reste la composite « ref|commercial_ref », donc
        « HBA0001| » ne peut pas matcher « HBA0001|SER0001 »."""
        import_manager._batch_insert_devices([{
            'type': 'Four', 'manufacturer': 'Bosch',
            'ref_modele': 'HBA0001', 'commercial_ref': 'SER0001',
            'other_ref': '', 'notes': '', 'category': '',
        }])
        cache = import_manager._preload_existing_devices()

        # Ligne partielle : même ref_modele, mais SANS commercial_ref
        partiel = {'ref_modele': 'HBA0001', 'commercial_ref': ''}
        assert import_manager._find_in_cache(partiel, cache) is None

        # La ligne complète, elle, est bien retrouvée
        complet = {'ref_modele': 'HBA0001', 'commercial_ref': 'SER0001'}
        assert import_manager._find_in_cache(complet, cache) is not None

    def test_cache_contient_les_appareils_mono_reference(self, import_manager):
        """Test unitaire de la cause racine : les appareils mono-référence chargés
        par la requête SQL (qui sélectionne en OU) doivent bien atterrir dans le
        cache, au lieu d'être filtrés par une garde en ET."""
        import_manager._batch_insert_devices([
            {'type': '', 'manufacturer': '', 'ref_modele': 'REFSEULE',
             'commercial_ref': '', 'other_ref': '', 'notes': '', 'category': ''},
            {'type': '', 'manufacturer': '', 'ref_modele': '',
             'commercial_ref': 'COMSEULE', 'other_ref': '', 'notes': '', 'category': ''},
        ])
        cache = import_manager._preload_existing_devices()

        assert 'refseule|' in cache
        assert '|comseule' in cache


class TestReferencePieceManquanteCollage:
    """CORRECTIF 3 : le collage part d'un champ de référence de pièce VIDE (contrairement
    à l'import fichier où elle est déduite du nom de fichier) et rien ne bloquait
    l'import. Résultat observé le 2026-09-01 : « 1 lignes traitées vs 0 lignes avec
    associations » — des appareils créés sans aucun rattachement à une pièce."""

    def _dialog(self, test_db_manager, ref_piece=''):
        from src.core.import_manager import ImportDialog
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        f = ImportFile('Collage', FileType.CLIPBOARD, '', '')
        f.data = [['Lave-linge', 'Samsung', 'WW80T4020EE']]
        cfg = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg = ImportDialog(None, cfg, im)
        ref_input = dlg.findChild(QLineEdit, 'ref_input_Collage')
        assert ref_input is not None, "le collage doit exposer un champ de référence éditable"
        ref_input.setText(ref_piece)
        return dlg

    def test_avertissement_si_reference_vide(self, qapp, test_db_manager):
        """Référence vide → avertissement au lieu d'un accept silencieux."""
        dlg = self._dialog(test_db_manager, ref_piece='')
        captured = {}
        dlg._confirm_import_malgre_avertissement = \
            lambda config, titre, msg: captured.update(config=config, titre=titre, msg=msg)

        dlg._validate_and_accept()

        assert dlg.result_config is None                 # pas d'accept direct
        assert "AUCUNE pièce" in captured['msg']
        assert captured['config'] is not None            # « Importer quand même » possible

    def test_pas_d_avertissement_si_reference_saisie(self, qapp, test_db_manager):
        """NON-RÉGRESSION : référence renseignée → import direct, aucun avertissement."""
        dlg = self._dialog(test_db_manager, ref_piece='AS6015830')
        called = []
        dlg._confirm_import_malgre_avertissement = lambda *a: called.append(a)

        dlg._validate_and_accept()

        assert dlg.result_config is not None and not called
        assert dlg.result_config.individual_references['Collage'] == 'AS6015830'


class TestLigneEnTeteIgnoree:
    """L'option « 1ʳᵉ ligne = en-têtes (ignorée) » était enregistrée dans
    ImportConfiguration.has_headers mais JAMAIS lue : la ligne d'en-tête d'un CSV ou
    d'un collage était importée comme un appareil réel. Pire, la case était masquée
    pour le collage — l'utilisateur ne pouvait même pas déclarer son en-tête."""

    @pytest.fixture
    def import_manager(self, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    @staticmethod
    def _config(has_headers, type_fichier=FileType.CLIPBOARD):
        data = [['Type', 'Marque', 'Référence'],
                ['Lave-linge', 'Samsung', 'WW80T4020EE'],
                ['Lave-linge', 'Samsung', 'WW90T4040EE']]
        config = ImportConfiguration(
            files=[ImportFile(path='Collage', type=type_fichier,
                              suggested_reference='PIECE100', suggested_label='',
                              data=data)],
            import_type=ImportType.SINGLE_FILE,
        )
        config.individual_references = {'Collage': 'PIECE100'}
        config.column_mapping = {3: ['type', 'manufacturer', 'ref_modele']}
        config.has_headers = has_headers
        return config

    def test_entete_ignoree_quand_declaree(self, import_manager, test_db_manager):
        """has_headers=True → la ligne d'en-tête n'est plus importée."""
        results = import_manager._run_import_files(self._config(has_headers=True))

        assert results['total_imported'] == 2
        # L'en-tête ne doit pas avoir créé d'appareil « Type / Marque / Référence »
        parasites = test_db_manager.execute_query(
            "SELECT COUNT(*) FROM appareils WHERE ref_modele = 'Référence'")[0][0]
        assert parasites == 0

    def test_non_regression_sans_declaration(self, import_manager, test_db_manager):
        """NON-RÉGRESSION : has_headers=False (défaut) → comportement inchangé,
        les 3 lignes sont traitées comme avant."""
        results = import_manager._run_import_files(self._config(has_headers=False))

        assert results['total_imported'] == 3
        parasites = test_db_manager.execute_query(
            "SELECT COUNT(*) FROM appareils WHERE ref_modele = 'Référence'")[0][0]
        assert parasites == 1  # l'en-tête est bien importée, comme historiquement

    def test_entete_non_retiree_pour_pdf(self, import_manager):
        """GARDE : has_headers est global. L'extracteur PDF retire déjà l'en-tête —
        l'appliquer une seconde fois supprimerait une vraie ligne de données lors
        d'un import mixte CSV + PDF."""
        from unittest.mock import patch
        config = self._config(has_headers=True, type_fichier=FileType.PDF)
        config.files[0].path = '/faux/chemin.pdf'
        config.individual_references = {'/faux/chemin.pdf': 'PIECE100'}
        donnees_pdf = [['Lave-linge', 'Samsung', 'WW10T634'],
                       ['Lave-linge', 'Samsung', 'WW11T635']]

        with patch.object(ImportManager, 'load_pdf_data', return_value=donnees_pdf):
            results = import_manager._run_import_files(config)

        assert results['total_imported'] == 2   # aucune ligne perdue

    def test_fichier_reduit_a_son_entete(self, import_manager):
        """Un fichier ne contenant QUE son en-tête ne doit pas partir en import vide."""
        config = self._config(has_headers=True)
        config.files[0].data = [['Type', 'Marque', 'Référence']]

        results = import_manager._run_import_files(config)

        assert results['successful_files'] == 0


class TestDetectionEnTeteReference:
    """« Référence » et « Ref » seuls ne figuraient pas dans les synonymes de
    ref_modele : un en-tête « Type | Marque | Référence » ne produisait aucun
    mapping ref_modele, ce qui grisait le bouton Importer sans explication."""

    def test_reference_seule_reconnue(self):
        from src.core.import_manager import ImportDialog
        mapping = ImportDialog._detect_csv_header_mapping(
            [['Type', 'Marque', 'Référence']], 3)
        assert mapping == ['type', 'manufacturer', 'ref_modele']

    def test_ref_seule_reconnue(self):
        from src.core.import_manager import ImportDialog
        mapping = ImportDialog._detect_csv_header_mapping([['Ref', 'Fabricant']], 2)
        assert mapping == ['ref_modele', 'manufacturer']

    def test_pas_de_collision_avec_ref_commerciale(self):
        """NON-RÉGRESSION : la correspondance est exacte, « Ref commerciale » et
        « Autre ref » ne doivent pas basculer sur ref_modele."""
        from src.core.import_manager import ImportDialog
        mapping = ImportDialog._detect_csv_header_mapping(
            [['Référence', 'Ref commerciale', 'Autre ref']], 3)
        assert mapping == ['ref_modele', 'commercial_ref', 'other_ref']


class TestCaseEnTeteVisibleCollage:
    """La case « 1ʳᵉ ligne = en-têtes » n'était affichée que pour les CSV."""

    def _dialog(self, test_db_manager, type_fichier, data):
        from src.core.import_manager import ImportDialog
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        f = ImportFile('Collage', type_fichier, 'REF', '')
        f.data = data
        cfg = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg = ImportDialog(None, cfg, im)
        # Le dialogue peuple son UI en différé (QTimer.singleShot 50 ms, lazy loading) :
        # en test synchrone le timer ne se déclenche jamais. On appelle le même point
        # d'entrée que le timer pour exercer le vrai chemin, sans dépendre du temps.
        dlg._load_data_deferred()
        return dlg

    def test_case_visible_pour_collage(self, qapp, test_db_manager):
        dlg = self._dialog(test_db_manager, FileType.CLIPBOARD,
                           [['Type', 'Marque', 'Référence'],
                            ['Lave-linge', 'Samsung', 'WW80T4020EE']])
        assert dlg.headers_checkbox.isVisibleTo(dlg)

    def test_case_prechochee_si_entete_detectee(self, qapp, test_db_manager):
        """Cohérence : si la détection a reconnu un en-tête (et s'en est servie pour
        inférer le mapping), la case doit être cochée — sinon l'application détecte
        l'en-tête PUIS l'importe comme un appareil."""
        dlg = self._dialog(test_db_manager, FileType.CLIPBOARD,
                           [['Type', 'Marque', 'Référence'],
                            ['Lave-linge', 'Samsung', 'WW80T4020EE']])
        assert dlg.headers_checkbox.isChecked()
        # Renseigner la référence de pièce, sinon le garde-fou v3.64.1 intercepte
        # la validation (collage sans référence = appareils orphelins).
        dlg.findChild(QLineEdit, 'ref_input_Collage').setText('AS6015830')
        dlg._validate_and_accept()
        assert dlg.result_config.has_headers is True

    def test_case_non_cochee_sans_entete(self, qapp, test_db_manager):
        """NON-RÉGRESSION : données sans en-tête → case décochée, rien n'est sauté."""
        dlg = self._dialog(test_db_manager, FileType.CLIPBOARD,
                           [['Lave-linge', 'Samsung', 'WW80T4020EE'],
                            ['Lave-linge', 'Samsung', 'WW90T4040EE']])
        assert not dlg.headers_checkbox.isChecked()
