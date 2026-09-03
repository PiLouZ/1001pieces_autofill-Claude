"""
Tests de non-régression — Dossier de destination des exports
Couvre : défaut Bureau, dossier personnalisé, replis (inexistant / lecture seule),
persistance de la clé à travers une sauvegarde, et le résolveur partagé.
"""

import copy
import os
import stat
import pytest
from unittest.mock import patch

from src.services.export_config_service import (
    ExportConfigService, DEFAULT_CONFIG, resolve_output_dir
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def config_service(qapp, tmp_path):
    """ExportConfigService avec fichier de config temporaire isolé."""
    config_path = str(tmp_path / "export_config.json")
    with patch.object(ExportConfigService, '_resolve_config_path', return_value=config_path):
        svc = ExportConfigService()
    svc._config = copy.deepcopy(DEFAULT_CONFIG)
    return svc


@pytest.fixture
def bureau():
    return os.path.join(os.path.expanduser("~"), "Desktop")


# ─── Valeur par défaut : le Bureau ───────────────────────────────────────────

class TestDefautBureau:

    def test_config_par_defaut_contient_output_dir_vide(self):
        """Stocké vide = config portable entre machines."""
        assert DEFAULT_CONFIG['output_dir'] == ''

    def test_output_dir_vide_resout_vers_le_bureau(self, config_service, bureau):
        assert config_service.get_output_dir() == bureau

    def test_get_default_output_dir_est_le_bureau(self, bureau):
        assert ExportConfigService.get_default_output_dir() == bureau

    def test_valeur_absente_de_la_config_resout_vers_le_bureau(self, config_service, bureau):
        """Config legacy antérieure à la fonctionnalité : aucun plantage."""
        del config_service._config['output_dir']
        assert config_service.get_output_dir() == bureau


# ─── Dossier personnalisé ────────────────────────────────────────────────────

class TestDossierPersonnalise:

    def test_dossier_existant_est_respecte(self, config_service, tmp_path):
        cible = tmp_path / "exports"
        cible.mkdir()
        config_service._config['output_dir'] = str(cible)
        assert config_service.get_output_dir() == str(cible)

    def test_chemin_tilde_est_developpe(self, config_service):
        config_service._config['output_dir'] = "~"
        assert config_service.get_output_dir() == os.path.expanduser("~")

    def test_chemin_relatif_est_rendu_absolu(self, config_service, tmp_path, monkeypatch):
        cible = tmp_path / "relatif"
        cible.mkdir()
        monkeypatch.chdir(tmp_path)
        config_service._config['output_dir'] = "relatif"
        assert config_service.get_output_dir() == str(cible)


# ─── Replis : un export ne doit jamais échouer sur un réglage obsolète ───────

class TestReplis:

    def test_dossier_inexistant_repli_sur_le_bureau(self, config_service, tmp_path, bureau):
        config_service._config['output_dir'] = str(tmp_path / "disque_externe_debranche")
        assert config_service.get_output_dir() == bureau

    def test_dossier_lecture_seule_repli_sur_le_bureau(self, config_service, tmp_path, bureau):
        cible = tmp_path / "lecture_seule"
        cible.mkdir()
        cible.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            config_service._config['output_dir'] = str(cible)
            assert config_service.get_output_dir() == bureau
        finally:
            cible.chmod(stat.S_IRWXU)  # laisser tmp_path nettoyable

    def test_valeur_blanche_repli_sur_le_bureau(self, config_service, bureau):
        config_service._config['output_dir'] = "   "
        assert config_service.get_output_dir() == bureau


# ─── Persistance à travers une sauvegarde ────────────────────────────────────

class TestPersistance:

    def test_output_dir_survit_a_une_sauvegarde(self, config_service, tmp_path):
        """Piège : _merge_with_defaults ne traitait que 'csv' et 'html' —
        une clé racine non gérée serait silencieusement remise à vide."""
        cible = tmp_path / "mes_exports"
        cible.mkdir()

        config = config_service.get_config()
        config['output_dir'] = str(cible)
        assert config_service.save_config(config) is True

        assert config_service.get_config()['output_dir'] == str(cible)
        assert config_service.get_output_dir() == str(cible)

    def test_config_legacy_sans_la_cle_est_migree_sans_perte(self, config_service, tmp_path):
        """Une config existante conserve ses personnalisations CSV et gagne le défaut."""
        legacy = {
            "csv": {"separator": "|", "encoding": "latin-1", "columns": [
                {"header": "ref", "source": "{ref_piece}"}
            ]},
            "html": {"brands": {"separator": ", "}}
        }
        merged = config_service._merge_with_defaults(legacy)
        assert merged['output_dir'] == ''
        assert merged['csv']['separator'] == '|'
        assert merged['csv']['encoding'] == 'latin-1'

    def test_valeur_non_texte_ignoree(self, config_service):
        """Config corrompue à la main : on ne propage pas un type invalide."""
        merged = config_service._merge_with_defaults({"output_dir": 42})
        assert merged['output_dir'] == ''

    def test_reset_remet_le_bureau(self, config_service, tmp_path, bureau):
        cible = tmp_path / "autre"
        cible.mkdir()
        config_service._config['output_dir'] = str(cible)
        config_service.reset_to_defaults()
        assert config_service.get_output_dir() == bureau


# ─── Résolveur partagé ───────────────────────────────────────────────────────

class TestResolveOutputDir:

    def test_sans_service_repli_sur_le_bureau(self, bureau):
        """Widgets construits sans parent exploitable : comportement historique."""
        assert resolve_output_dir(None) == bureau

    def test_avec_service_delegue_au_service(self, config_service, tmp_path):
        cible = tmp_path / "delegue"
        cible.mkdir()
        config_service._config['output_dir'] = str(cible)
        assert resolve_output_dir(config_service) == str(cible)

    def test_service_defaillant_repli_sur_le_bureau(self, bureau):
        class ServiceCasse:
            def get_output_dir(self):
                raise RuntimeError("config illisible")

        assert resolve_output_dir(ServiceCasse()) == bureau


# ─── Bout en bout : le chemin d'export réellement emprunté ───────────────────

class TestExportCsvEcritDansLeDossierConfigure:
    """L'export CSV de la barre d'outils passe par ExportManagerService.
    Ces tests vérifient le branchement, pas seulement le service de config."""

    @staticmethod
    def _manager(config_service):
        from src.services.export_manager import ExportManagerService

        class FausseFenetre:
            pass

        fenetre = FausseFenetre()
        fenetre.export_config_service = config_service
        return ExportManagerService(fenetre)

    @staticmethod
    def _donnees():
        return [('Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20', '', 'AS6015830')]

    def test_ecrit_dans_le_dossier_configure(self, config_service, tmp_path):
        cible = tmp_path / "exports"
        cible.mkdir()
        config_service._config['output_dir'] = str(cible)

        assert self._manager(config_service)._execute_csv_export(
            self._donnees(), "REF123"
        ) is True
        assert (cible / "REF123_everyParts.csv").exists()

    def test_repli_bureau_si_dossier_absent(self, config_service, tmp_path):
        """Réglage devenu obsolète : l'export ne doit pas échouer.

        Le Bureau est simulé : un test ne doit jamais écrire dans le vrai
        dossier de l'utilisateur.
        """
        faux_bureau = tmp_path / "faux_bureau"
        faux_bureau.mkdir()
        config_service._config['output_dir'] = str(tmp_path / "inexistant")

        with patch.object(ExportConfigService, 'get_default_output_dir',
                          return_value=str(faux_bureau)):
            assert self._manager(config_service)._execute_csv_export(
                self._donnees(), "REF_REPLI_TEST"
            ) is True

        assert (faux_bureau / "REF_REPLI_TEST_everyParts.csv").exists()

    def test_contenu_inchange_par_rapport_au_comportement_historique(
        self, config_service, tmp_path
    ):
        """ZERO REGRESSION : seul le dossier change, pas une virgule du CSV."""
        cible = tmp_path / "exports"
        cible.mkdir()
        config_service._config['output_dir'] = str(cible)

        self._manager(config_service)._execute_csv_export(self._donnees(), "REF123")

        contenu = (cible / "REF123_everyParts.csv").read_text(encoding='utf-8')
        lignes = contenu.splitlines()
        assert lignes[0] == (
            "product;type;manufacturer;modele_name;"
            "reference_modele;commercial_reference"
        )
        assert lignes[1] == "REF123;Aspirateur;Samsung;SC4520 - PowerBrush 20;SC4520;PowerBrush 20"
