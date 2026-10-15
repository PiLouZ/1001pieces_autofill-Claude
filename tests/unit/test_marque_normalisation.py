"""
Normalisation de la casse des marques à l'import (v3.82.0)

Cas réels du collage du 2026-10-15 : « DELTA », « HEXATHERM », « EQUATION »
existaient déjà en base sous la forme « Delta », « Hexatherm », « Equation ».
"""

import os
import tempfile

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType,
    LabelConfiguration, FileType,
)
from src.services.marque_normalisation_service import (
    MarqueNormalisationService, cle_marque, mettre_en_forme,
)


class _DbFactice:
    def __init__(self, marques):
        self.marques = marques

    def execute_query(self, _requete):
        return self.marques


def _service(marques):
    service = MarqueNormalisationService(_DbFactice(marques))
    service.charger()
    return service


# ─── Fonctions pures ─────────────────────────────────────────────────────────

class TestReglesPures:

    def test_cle_ignore_casse_accents_espaces_tirets(self):
        assert cle_marque("Hotpoint-Ariston") == cle_marque("HOTPOINT ARISTON")
        assert cle_marque("Scholtès") == cle_marque("SCHOLTES")
        assert cle_marque("Jünker") == cle_marque("junker")

    @pytest.mark.parametrize("brute, attendue", [
        ("HEXATHERM", "Hexatherm"),
        ("ARTHUR-MARTIN", "Arthur-Martin"),
        ("DE DIETRICH", "De Dietrich"),
        ("ROSIÈRES", "Rosières"),
        ("CDA", "CDA"),          # sigle court
        ("DELT", "DELT"),        # 4 caractères : encore un sigle
        ("KitchenAid", "KitchenAid"),  # casse mixte : jamais touchée
        ("atlantic", "atlantic"),      # minuscules : pas la règle 2
        ("12345", "12345"),            # pas de lettre
    ])
    def test_mise_en_forme_marque_nouvelle(self, brute, attendue):
        assert mettre_en_forme(brute) == attendue


# ─── Service ────────────────────────────────────────────────────────────────

class TestService:

    def test_regle_1_base_fait_foi(self):
        service = _service([("Delta", 37), ("AEG", 20145), ("Scholtès", 3022),
                            ("Hotpoint-Ariston", 13601)])
        assert service.normaliser("DELTA") == "Delta"
        assert service.normaliser("aeg") == "AEG"
        assert service.normaliser("SCHOLTES") == "Scholtès"
        assert service.normaliser("HOTPOINT ARISTON") == "Hotpoint-Ariston"
        assert service.normaliser("Delta") == "Delta"

    def test_regle_1_passe_avant_la_longueur(self):
        """Une marque de plus de 4 lettres écrite en capitales EN BASE reste ainsi."""
        service = _service([("MIELE-PRO", 2)])
        assert service.normaliser("miele-pro") == "MIELE-PRO"

    def test_variante_la_plus_frequente_l_emporte(self):
        service = _service([("MIDEA", 11), ("Midea", 3)])
        assert service.normaliser("midea") == "MIDEA"

    def test_marque_nouvelle_devient_reference_du_lot(self):
        service = _service([])
        assert service.normaliser("NEWCOMARK") == "Newcomark"
        assert service.normaliser("newcomark") == "Newcomark"

    def test_alignements_traces(self):
        service = _service([("Delta", 37)])
        for _ in range(3):
            service.normaliser("DELTA")
        service.normaliser("Delta")
        service.normaliser("HEXATHERM")
        assert service.alignements() == [("DELTA", "Delta", 3), ("HEXATHERM", "Hexatherm", 1)]
        assert service.resume(service.alignements()) == \
            "DELTA → Delta (3), HEXATHERM → Hexatherm (1)"

    def test_recharger_remet_les_traces_a_zero(self):
        service = _service([("Delta", 37)])
        service.normaliser("DELTA")
        service.charger()
        assert service.alignements() == []

    def test_base_indisponible_regle_2_seule(self):
        service = MarqueNormalisationService(_DbFactice(None))
        assert service.normaliser("HEXATHERM") == "Hexatherm"
        assert service.normaliser("CDA") == "CDA"

    def test_vide_inchange(self):
        service = _service([])
        assert service.normaliser("") == ""
        assert service.normaliser(None) is None or service.normaliser(None) == ""


# ─── Intégration : les deux chemins d'import ─────────────────────────────────

LIGNES = [
    ["Chauffage", "DELTA", "558812", "DELTA RAYONN. BLANC INT. 1250 W"],
    ["Chauffage", "HEXATHERM", "558121", "RAY.ELECTR.HEXATHERM 750 W."],
    ["Chauffage", "Atlantic", "510212", "SOLIUS 2 HORIZONTAL BLANC 1250W"],
    ["Chauffage", "NOUVEAUMARQ", "999001", "RADIATEUR X"],
    ["Chauffage", "CDA", "999002", "RADIATEUR Y"],
]


@pytest.fixture
def manager():
    chemin_db = tempfile.mktemp(suffix='.db')
    db_origine, recherche_origine = Config.DB_FILE, Config.SEARCH_PIECES_ONLY
    Config.DB_FILE = chemin_db
    Config.SEARCH_PIECES_ONLY = False
    try:
        db = DatabaseManager()
        db.execute_query(
            "INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref) VALUES "
            "('Chauffage', 'Delta', 'X1', 'X1'), ('Chauffage', 'Hexatherm', 'X2', 'X2'), "
            "('Chauffage', 'Atlantic', 'X3', 'X3')"
        )
        if hasattr(db, 'connection') and db.connection:
            db.connection.commit()
        im = ImportManager(db_manager=db, parent_widget=None)
        im._pending_similarity_candidates = []
        im._imported_complete_for_similarity = []
        yield im, db
    finally:
        Config.DB_FILE, Config.SEARCH_PIECES_ONLY = db_origine, recherche_origine
        for suffixe in ('', '-wal', '-shm'):
            if os.path.exists(chemin_db + suffixe):
                os.remove(chemin_db + suffixe)


def _config():
    fichier = ImportFile(path='/tmp/inexistant.csv', type=FileType.CSV,
                         suggested_reference='REF_TEST')
    config = ImportConfiguration(
        files=[fichier], import_type=ImportType.SINGLE_FILE,
        common_reference="REF_TEST", use_common_reference=True,
        label_config=LabelConfiguration(), individual_references={},
        individual_labels={}, csv_import_mode=2, has_headers=False,
    )
    return config, fichier


@pytest.mark.parametrize("chemin", ["standard", "batch"])
def test_import_aligne_les_marques(manager, chemin):
    im, db = manager
    im._marques.charger()
    config, fichier = _config()
    if chemin == 'standard':
        im._process_data_import(LIGNES, [("REF_TEST", "libelle")], config, fichier, set())
    else:
        im._process_data_import_batch(LIGNES, [("REF_TEST", "libelle")], config, fichier, set())

    marques = {ref: m for ref, m in db.execute_query(
        "SELECT ref_modele, manufacturer FROM appareils")}
    assert marques['558812'] == 'Delta'
    assert marques['558121'] == 'Hexatherm'
    assert marques['510212'] == 'Atlantic'
    assert marques['999001'] == 'Nouveaumarq'
    assert marques['999002'] == 'CDA'
    assert im._marques.alignements() == [
        ("DELTA", "Delta", 1), ("HEXATHERM", "Hexatherm", 1), ("NOUVEAUMARQ", "Nouveaumarq", 1)]
