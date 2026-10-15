"""
Normalisation de la casse des marques et des types (v3.82.0, types et saisie
manuelle v3.83.0)

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
from src.services.casse_normalisation_service import (
    CasseNormalisationService, cle_marque, mettre_en_forme, mettre_en_forme_type,
)


class _DbFactice:
    def __init__(self, marques):
        self.marques = marques

    def execute_query(self, _requete):
        return self.marques


def _service(marques):
    service = CasseNormalisationService(_DbFactice(marques))
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
        service = CasseNormalisationService(_DbFactice(None))
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
    ["CHAUFFAGE", "Atlantic", "999003", "RADIATEUR Z"],
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
    im._types.charger()
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
    assert {r: t for r, t in db.execute_query(
        "SELECT ref_modele, type FROM appareils")}['999003'] == 'Chauffage'
    assert im._types.alignements() == [("CHAUFFAGE", "Chauffage", 1)]


# ─── Historique : une marque par ligne ───────────────────────────────────────

def test_lignes_virgule_sauf_la_derniere():
    alignements = [("DELTA", "Delta", 7), ("EQUATION", "Equation", 2), ("HEXATHERM", "Hexatherm", 1)]
    assert CasseNormalisationService.lignes(alignements) == [
        "DELTA → Delta (7),", "EQUATION → Equation (2),", "HEXATHERM → Hexatherm (1)"]
    assert CasseNormalisationService.lignes([("DELTA", "Delta", 1)]) == ["DELTA → Delta (1)"]


def test_bloc_historique_avant_l_alerte_de_mapping():
    """Les lignes de marques précèdent le « [!] » : placées après, elles seraient
    surlignées en jaune comme faisant partie de l'alerte."""
    import types
    from src.ui.main_refactored import MainWindow
    historique = []
    fenetre = types.SimpleNamespace(
        user_interaction_service=types.SimpleNamespace(
            add_to_history=lambda s, duration_ms=None: historique.append(s)),
        _lignes_alignements=MainWindow._lignes_alignements)
    MainWindow._safe_show_import_results_new(fenetre, {
        'total_files': 1, 'file_details': [{'filename': 'Collage', 'type': 'CSV', 'lines_processed': 2}],
        'marques_alignees': [("DELTA", "Delta", 1), ("HEXATHERM", "Hexatherm", 1)],
        'alerte_mapping': "alerte",
    })
    lignes = historique[0].splitlines()
    i = lignes.index("     ==> Marques alignées sur la base :")
    assert lignes[i + 1:i + 4] == ["     - DELTA → Delta (1),", "     - HEXATHERM → Hexatherm (1)",
                                   "     [!] alerte"]


# ─── Types (v3.83.0) ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("brute, attendue", [
    ("CHAUFFE-EAU", "Chauffe-eau"),
    ("LAVE LINGE", "Lave linge"),
    ("RÉFRIGÉRATEUR", "Réfrigérateur"),
    ("Lave-linge", "Lave-linge"),
    ("VMC", "VMC"),
])
def test_mise_en_forme_type_nouveau(brute, attendue):
    assert mettre_en_forme_type(brute) == attendue


def test_type_aligne_sur_la_base():
    service = CasseNormalisationService(_DbFactice([("Chauffage", 1799), ("Lave-linge", 9)]), 'type')
    assert service.normaliser("CHAUFFAGE") == "Chauffage"
    assert service.normaliser("lave linge") == "Lave-linge"
    assert service.normaliser("CHAUFFE-EAU") == "Chauffe-eau"


def test_colonne_inconnue_refusee():
    with pytest.raises(ValueError):
        CasseNormalisationService(_DbFactice([]), 'notes')


class _DbEvolutive:
    """Base dont le contenu change après le chargement (import, restauration)."""
    def __init__(self):
        self.valeurs = [("Delta", 37)]

    def execute_query(self, requete):
        if requete.startswith("SELECT DISTINCT"):
            return [(v,) for v, _ in self.valeurs]
        return list(self.valeurs)


def test_valeur_apparue_apres_chargement_est_retrouvee():
    """Liste chargée au lancement, puis « KitchenAid » arrive en base : la saisie
    « KITCHENAID » doit la retrouver, pas créer « Kitchenaid »."""
    db = _DbEvolutive()
    service = CasseNormalisationService(db, 'manufacturer')
    service.charger()
    db.valeurs.append(("KitchenAid", 3))
    assert service.normaliser("KITCHENAID") == "KitchenAid"


def test_historique_marques_puis_types():
    import types
    from src.ui.main_refactored import MainWindow
    texte = MainWindow._lignes_alignements({
        'marques_alignees': [("DELTA", "Delta", 7)],
        'types_alignes': [("CHAUFFAGE", "Chauffage", 25)],
    }, retrait="     ")
    assert texte.splitlines() == [
        "     ==> Marques alignées sur la base :", "     - DELTA → Delta (7)",
        "     ==> Types alignés sur la base :", "     - CHAUFFAGE → Chauffage (25)"]
    assert MainWindow._lignes_alignements({}, retrait="") == ""


# ─── Saisie manuelle dans le tableau (v3.83.0) ───────────────────────────────

class _ModeleFactice:
    def __init__(self):
        self.ecrit = {}

    def signalsBlocked(self):
        return False

    def get_db_id(self, row):
        return 100 + row


def _fenetre(marques):
    import types
    from src.ui.main_refactored import MainWindow
    modele = _ModeleFactice()
    appels = []
    fenetre = types.SimpleNamespace(
        table_controller=types.SimpleNamespace(model=modele),
        validator=types.SimpleNamespace(
            validate_field=lambda champ, valeur: types.SimpleNamespace(is_valid=True)),
        normalisation_casse={
            'manufacturer': CasseNormalisationService(_DbFactice(marques), 'manufacturer'),
            'type': CasseNormalisationService(_DbFactice([("Chauffage", 1)]), 'type'),
        },
        _get_db_field_name=lambda col: {0: 'type', 1: 'manufacturer', 2: 'ref_modele'}.get(col),
        _set_cell_value_in_table=lambda r, c, v: modele.ecrit.__setitem__((r, c), v),
        _apply_cell_edit_logic=lambda *a: appels.append(a),
    )
    return MainWindow._on_cell_changed_model, fenetre, modele, appels


def test_saisie_marque_alignee_et_affichee():
    handler, fenetre, modele, appels = _fenetre([("Delta", 37)])
    handler(fenetre, 3, 1, "", "DELTA")
    assert modele.ecrit == {(3, 1): "Delta"}          # cellule réécrite
    assert appels == [(3, 1, "", "Delta", 103)]        # sauvegarde/undo/historique


def test_saisie_type_aligne():
    handler, fenetre, modele, appels = _fenetre([])
    handler(fenetre, 0, 0, "", "CHAUFFAGE")
    assert appels == [(0, 0, "", "Chauffage", 100)]


def test_saisie_identique_apres_alignement_ne_sauvegarde_rien():
    """« DELTA » retapé sur une cellule « Delta » : rien ne change."""
    handler, fenetre, modele, appels = _fenetre([("Delta", 37)])
    handler(fenetre, 0, 1, "Delta", "DELTA")
    assert modele.ecrit == {(0, 1): "Delta"}
    assert appels == []


def test_autres_colonnes_et_effacement_intacts():
    handler, fenetre, modele, appels = _fenetre([("Delta", 37)])
    handler(fenetre, 0, 2, "", "ABCDEFG")             # référence modèle
    handler(fenetre, 1, 1, "Delta", "")               # effacement de la marque
    assert modele.ecrit == {}
    assert appels == [(0, 2, "", "ABCDEFG", 100), (1, 1, "Delta", "", 101)]


# ─── Aperçu d'import : corrections annoncées avant d'écrire (v3.83.0) ────────

def test_apercu_liste_marques_puis_types():
    from src.core.import_manager import ImportPreviewDialog
    assert ImportPreviewDialog._lignes_alignements({
        'marques_alignees': [("DELTA", "Delta", 7), ("HEXATHERM", "Hexatherm", 1)],
        'types_alignes': [("CHAUFFAGE", "Chauffage", 25)],
    }) == ["Marques :", "    DELTA → Delta (7),", "    HEXATHERM → Hexatherm (1)",
           "Types :", "    CHAUFFAGE → Chauffage (25)"]


def test_apercu_liste_longue_tronquee():
    from src.core.import_manager import ImportPreviewDialog
    lignes = ImportPreviewDialog._lignes_alignements(
        {'marques_alignees': [(f"MARQUE{i}", f"Marque{i}", 1) for i in range(11)]})
    assert len(lignes) == 1 + ImportPreviewDialog.MAX_ALIGNEMENTS_AFFICHES + 1
    assert lignes[-2].endswith(',') and lignes[-1] == "    … et 3 autres"


def test_apercu_sans_correction_sans_encadre(qapp):
    from src.core.import_manager import ImportPreviewDialog
    dialogue = ImportPreviewDialog({'new_entries': 1}, None)
    assert dialogue._encadre_alignements({'new_entries': 1}) is None
    assert dialogue._encadre_alignements({'types_alignes': [("CHAUFFAGE", "Chauffage", 1)]}) is not None


def test_analyse_a_blanc_remonte_les_alignements(manager):
    """L'aperçu repose sur le dry run : il doit porter les corrections sans rien écrire."""
    im, db = manager
    fichier = ImportFile(path='Collage', type=FileType.CLIPBOARD, suggested_reference='REF_TEST',
                         suggested_label='', data=LIGNES)
    config = ImportConfiguration(
        files=[fichier], import_type=ImportType.SINGLE_FILE, common_reference="REF_TEST",
        use_common_reference=True, label_config=LabelConfiguration(), individual_references={},
        individual_labels={}, has_headers=False,
        column_mapping={4: ['type', 'manufacturer', 'ref_modele', 'commercial_ref']})
    resultats = im._run_import_files(config, dry_run=True)
    assert ("DELTA", "Delta", 1) in resultats['marques_alignees']
    assert resultats['types_alignes'] == [("CHAUFFAGE", "Chauffage", 1)]
    assert db.execute_query("SELECT COUNT(*) FROM appareils")[0][0] == 3   # rien d'écrit
