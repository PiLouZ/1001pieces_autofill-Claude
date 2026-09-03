"""
Tests — L'export CSV réel respecte la fenêtre « Configuration des exports »

Jusqu'à la v3.68.0, ExportManagerService._execute_csv_export réécrivait en dur
les en-têtes, le séparateur et le nom de fichier : l'onglet CSV de la fenêtre de
configuration était sans effet sur l'export réel. Ces tests verrouillent le
branchement, sur le chemin réellement emprunté par le bouton CSV.
"""

import copy
import csv
import os
import pytest
from unittest.mock import patch

from src.services.export_config_service import (
    ExportConfigService, DEFAULT_CONFIG, format_csv_filename, get_csv_settings
)
from src.services.export_manager import ExportManagerService


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def config_service(qapp, tmp_path):
    config_path = str(tmp_path / "export_config.json")
    with patch.object(ExportConfigService, '_resolve_config_path', return_value=config_path):
        svc = ExportConfigService()
    svc._config = copy.deepcopy(DEFAULT_CONFIG)
    return svc


@pytest.fixture
def dossier(tmp_path, config_service):
    """Dossier d'export isolé — aucun test n'écrit sur le vrai Bureau."""
    cible = tmp_path / "exports"
    cible.mkdir()
    config_service._config['output_dir'] = str(cible)
    return cible


@pytest.fixture
def manager(config_service):
    class FausseFenetre:
        pass

    fenetre = FausseFenetre()
    fenetre.export_config_service = config_service
    return ExportManagerService(fenetre)


DONNEES = [('Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20', 'AUTRE', 'PIECE')]


def _lire(chemin, separator=';', encoding='utf-8'):
    with open(chemin, newline='', encoding=encoding) as f:
        return list(csv.reader(f, delimiter=separator))


# ─── La configuration pilote enfin l'export ──────────────────────────────────

class TestConfigurationRespectee:

    def test_colonnes_personnalisees(self, manager, config_service, dossier):
        config_service._config['csv']['columns'] = [
            {"header": "piece",  "source": "{export_ref}"},
            {"header": "marque", "source": "{manufacturer}"},
        ]
        manager._execute_csv_export(DONNEES, "REF123")

        lignes = _lire(dossier / "REF123_everyParts.csv")
        assert lignes[0] == ["piece", "marque"]
        assert lignes[1] == ["REF123", "Samsung"]

    def test_separateur_personnalise(self, manager, config_service, dossier):
        config_service._config['csv']['separator'] = ','
        manager._execute_csv_export(DONNEES, "REF123")

        brut = (dossier / "REF123_everyParts.csv").read_text(encoding='utf-8')
        assert brut.splitlines()[0].startswith("product,type,manufacturer")
        assert ';' not in brut.splitlines()[0]

    def test_encodage_personnalise(self, manager, config_service, dossier):
        config_service._config['csv']['encoding'] = 'latin-1'
        donnees = [('Réfrigérateur', 'Électrolux', 'REF', 'COM', '', '')]
        manager._execute_csv_export(donnees, "REF123")

        chemin = dossier / "REF123_everyParts.csv"
        assert 'Réfrigérateur' in chemin.read_text(encoding='latin-1')
        with pytest.raises(UnicodeDecodeError):
            chemin.read_text(encoding='utf-8')

    def test_pattern_nom_de_fichier_personnalise(self, manager, config_service, dossier):
        config_service._config['csv']['filename_pattern'] = 'pieces_{export_ref}.csv'
        manager._execute_csv_export(DONNEES, "REF123")

        assert (dossier / "pieces_REF123.csv").exists()
        assert not (dossier / "REF123_everyParts.csv").exists()

    def test_pattern_avec_timestamp(self, manager, config_service, dossier):
        config_service._config['csv']['filename_pattern'] = '{export_ref}_{timestamp}.csv'
        manager._execute_csv_export(DONNEES, "REF123")

        fichiers = list(dossier.glob("REF123_*.csv"))
        assert len(fichiers) == 1
        horodatage = fichiers[0].stem.split('_', 1)[1]
        assert len(horodatage) == 15 and horodatage[8] == '_'  # AAAAMMJJ_HHMMSS

    def test_toutes_les_variables_sont_substituables(self, manager, config_service, dossier):
        config_service._config['csv']['columns'] = [
            {"header": h, "source": "{" + h + "}"}
            for h in ('export_ref', 'type_app', 'manufacturer', 'ref_modele',
                      'commercial_ref', 'other_ref', 'modele_complet')
        ]
        manager._execute_csv_export(DONNEES, "REF123")

        lignes = _lire(dossier / "REF123_everyParts.csv")
        assert lignes[1] == ["REF123", "Aspirateur", "Samsung", "SC4520",
                             "PowerBrush 20", "AUTRE", "SC4520 - PowerBrush 20"]


# ─── {export_ref} = référence confirmée dans le dialogue ─────────────────────

class TestReferenceConfirmee:
    """Décision produit : {export_ref} vaut la référence validée par
    l'utilisateur dans le dialogue d'export, jamais le terme de recherche."""

    def test_export_ref_est_la_reference_confirmee(self, manager, dossier):
        manager._execute_csv_export(DONNEES, "REF_CONFIRMEE")

        lignes = _lire(dossier / "REF_CONFIRMEE_everyParts.csv")
        assert lignes[1][0] == "REF_CONFIRMEE"

    def test_export_ref_ignore_la_reference_de_piece_du_record(self, manager, dossier):
        """Le 6ᵉ champ du record ne doit pas se substituer à la référence confirmée."""
        donnees = [('Aspirateur', 'Samsung', 'SC4520', 'PB20', '', 'AUTRE_CHOSE')]
        manager._execute_csv_export(donnees, "REF_CONFIRMEE")

        lignes = _lire(dossier / "REF_CONFIRMEE_everyParts.csv")
        assert lignes[1][0] == "REF_CONFIRMEE"


# ─── Correction : la chaîne "None" dans modele_name ──────────────────────────

class TestValeursNulles:
    """159 appareils de la base réelle ont commercial_ref à NULL. L'ancien
    assemblage produisait littéralement « SC4520 - None » dans le CSV."""

    def test_commercial_ref_nulle_ne_produit_plus_none(self, manager, dossier):
        manager._execute_csv_export(
            [('Aspirateur', 'Samsung', 'SC4520', None, None, None)], "REF123"
        )

        lignes = _lire(dossier / "REF123_everyParts.csv")
        assert lignes[1][3] == "SC4520"        # modele_name
        assert "None" not in ";".join(lignes[1])

    def test_ref_modele_nulle_ne_produit_plus_none(self, manager, dossier):
        manager._execute_csv_export(
            [('Aspirateur', 'Samsung', None, 'PowerBrush 20', None, None)], "REF123"
        )

        lignes = _lire(dossier / "REF123_everyParts.csv")
        assert lignes[1][3] == "PowerBrush 20"
        assert "None" not in ";".join(lignes[1])

    def test_deux_references_nulles(self, manager, dossier):
        manager._execute_csv_export(
            [('Aspirateur', 'Samsung', None, None, None, None)], "REF123"
        )

        lignes = _lire(dossier / "REF123_everyParts.csv")
        assert lignes[1][3] == ""
        assert "None" not in ";".join(lignes[1])


# ─── Robustesse : un réglage saisi librement ne casse pas l'export ───────────

class TestPatternRobuste:

    def test_variable_inconnue_repli_sur_le_pattern_par_defaut(self, manager,
                                                               config_service, dossier):
        config_service._config['csv']['filename_pattern'] = '{inconnue}_truc.csv'
        assert manager._execute_csv_export(DONNEES, "REF123") is True
        assert (dossier / "REF123_everyParts.csv").exists()

    def test_accolade_mal_fermee_repli_sur_le_pattern_par_defaut(self, manager,
                                                                 config_service, dossier):
        config_service._config['csv']['filename_pattern'] = '{export_ref.csv'
        assert manager._execute_csv_export(DONNEES, "REF123") is True
        assert (dossier / "REF123_everyParts.csv").exists()

    def test_separateur_de_chemin_reste_dans_le_dossier_dexport(self, manager,
                                                                config_service, dossier):
        """Le pattern ne doit pas permettre d'écrire hors du dossier choisi."""
        config_service._config['csv']['filename_pattern'] = '../../{export_ref}.csv'
        assert manager._execute_csv_export(DONNEES, "REF123") is True

        assert (dossier / "REF123.csv").exists()
        assert not (dossier.parent.parent / "REF123.csv").exists()

    def test_format_csv_filename_isolement(self):
        assert format_csv_filename('{export_ref}.csv', 'A') == 'A.csv'
        assert format_csv_filename('{inconnue}.csv', 'A') == 'A_everyParts.csv'
        assert format_csv_filename('/etc/{export_ref}.csv', 'A') == 'A.csv'


# ─── Repli sans service : comportement historique préservé ───────────────────

class TestSansService:

    def test_get_csv_settings_sans_service_rend_les_defauts(self):
        reglages = get_csv_settings(None)
        assert reglages['separator'] == ';'
        assert reglages['encoding'] == 'utf-8'
        assert reglages['headers'] == [
            'product', 'type', 'manufacturer',
            'modele_name', 'reference_modele', 'commercial_reference'
        ]

    def test_export_sans_service_ecrit_le_format_historique(self, qapp, tmp_path):
        class FausseFenetre:
            pass

        manager = ExportManagerService(FausseFenetre())
        faux_bureau = tmp_path / "faux_bureau"
        faux_bureau.mkdir()

        with patch.object(ExportConfigService, 'get_default_output_dir',
                          return_value=str(faux_bureau)):
            assert manager._execute_csv_export(DONNEES, "REF123") is True

        lignes = _lire(faux_bureau / "REF123_everyParts.csv")
        assert lignes[0] == ['product', 'type', 'manufacturer',
                             'modele_name', 'reference_modele', 'commercial_reference']
        assert lignes[1] == ['REF123', 'Aspirateur', 'Samsung',
                             'SC4520 - PowerBrush 20', 'SC4520', 'PowerBrush 20']
