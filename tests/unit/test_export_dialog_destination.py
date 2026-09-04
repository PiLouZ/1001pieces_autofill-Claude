"""
Tests — La fenêtre d'export annonce où ira le fichier

Depuis la v3.68.0, le nom du fichier CSV est piloté par un pattern configurable :
la référence saisie ne détermine plus seulement la première colonne, mais aussi
le nom du fichier. Rien ne le montrait à l'utilisateur.

La fenêtre affiche désormais le dossier de destination et le nom réel du fichier,
recalculé à chaque frappe. L'invariant essentiel — et c'est l'objet du test le
plus important ici — est que cet aperçu ne peut pas diverger du fichier
réellement écrit : les deux passent par `format_csv_filename`.
"""

import copy
import csv
import os
import pytest
from unittest.mock import patch

from src.core.constants import ExportFormat
from src.services.export_config_service import ExportConfigService, DEFAULT_CONFIG
from src.services.export_manager import ExportManagerService


@pytest.fixture
def config_service(qapp, tmp_path):
    chemin = str(tmp_path / "export_config.json")
    with patch.object(ExportConfigService, '_resolve_config_path', return_value=chemin):
        svc = ExportConfigService()
    svc._config = copy.deepcopy(DEFAULT_CONFIG)
    return svc


@pytest.fixture
def manager(config_service, tmp_path):
    cible = tmp_path / "exports"
    cible.mkdir()
    config_service._config['output_dir'] = str(cible)

    class FausseFenetre:
        pass

    fenetre = FausseFenetre()
    fenetre.export_config_service = config_service
    return ExportManagerService(fenetre)


class TestPresenceDuBloc:
    """Le bloc destination n'a de sens que pour les exports qui écrivent un fichier."""

    def test_present_pour_le_csv(self, manager):
        destination = manager._destination_export(ExportFormat.CSV)
        assert destination is not None
        assert set(destination) == {'dossier', 'nom_fichier', 'changer'}

    @pytest.mark.parametrize("format_html", [
        ExportFormat.HTML_BRANDS, ExportFormat.HTML_DETAILS
    ])
    def test_absent_pour_le_html(self, manager, format_html):
        """Les exports HTML vont dans le presse-papier : pas de destination."""
        assert manager._destination_export(format_html) is None

    def test_absent_sans_format(self, manager):
        assert manager._destination_export(None) is None


class TestContenuAffiche:

    def test_le_dossier_est_celui_configure(self, manager, config_service):
        destination = manager._destination_export(ExportFormat.CSV)
        assert destination['dossier'] == config_service.get_output_dir()

    def test_le_nom_suit_le_pattern_configure(self, manager, config_service):
        config_service._config['csv']['filename_pattern'] = 'catalogue_{export_ref}.csv'
        destination = manager._destination_export(ExportFormat.CSV)
        assert destination['nom_fichier']('REF123') == 'catalogue_REF123.csv'

    def test_le_nom_suit_la_reference_saisie(self, manager):
        nom = manager._destination_export(ExportFormat.CSV)['nom_fichier']
        assert nom('AAA') == 'AAA_everyParts.csv'
        assert nom('BBB') == 'BBB_everyParts.csv'

    def test_pattern_invalide_ne_casse_pas_l_apercu(self, manager, config_service):
        """Le pattern vient d'un champ libre : l'aperçu doit rester affichable."""
        config_service._config['csv']['filename_pattern'] = '{inconnue}.csv'
        nom = manager._destination_export(ExportFormat.CSV)['nom_fichier']
        assert nom('REF123') == 'REF123_everyParts.csv'


class TestApercuFidele:
    """L'invariant : ce qui est annoncé est ce qui est écrit."""

    @pytest.mark.parametrize("pattern", [
        '{export_ref}_everyParts.csv',
        'catalogue_{export_ref}.csv',
        'export.csv',
        '{inconnue}.csv',
    ])
    def test_l_apercu_correspond_au_fichier_ecrit(self, manager, config_service, pattern):
        config_service._config['csv']['filename_pattern'] = pattern
        annonce = manager._destination_export(ExportFormat.CSV)['nom_fichier']('REF123')

        manager._execute_csv_export(
            [('Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20', '', '')], 'REF123'
        )

        dossier = config_service.get_output_dir()
        ecrits = os.listdir(dossier)
        assert annonce in ecrits, (
            f"annoncé {annonce!r}, écrit {ecrits!r} — l'aperçu a divergé du fichier réel"
        )


class TestChangerDossier:

    def test_le_choix_est_memorise_dans_la_configuration(self, manager, config_service, tmp_path):
        nouveau = tmp_path / "ailleurs"
        nouveau.mkdir()
        changer = manager._destination_export(ExportFormat.CSV)['changer']

        with patch('src.ui.qt_imports.QFileDialog.getExistingDirectory',
                   return_value=str(nouveau)):
            retour = changer()

        assert retour == str(nouveau)
        assert config_service.get_output_dir() == str(nouveau)

    def test_annuler_ne_change_rien(self, manager, config_service):
        avant = config_service.get_output_dir()
        changer = manager._destination_export(ExportFormat.CSV)['changer']

        with patch('src.ui.qt_imports.QFileDialog.getExistingDirectory', return_value=''):
            assert changer() is None

        assert config_service.get_output_dir() == avant


class TestLibellesDeFormat:
    """ExportFormat.value est un identifiant technique, pas un texte d'interface."""

    def test_html_details_est_lisible(self):
        assert ExportManagerService._libelle_format(ExportFormat.HTML_DETAILS) == "HTML — Détails"

    def test_csv_reste_csv(self):
        assert ExportManagerService._libelle_format(ExportFormat.CSV) == "CSV"

    def test_format_inconnu_retombe_sur_sa_valeur(self):
        assert ExportManagerService._libelle_format(ExportFormat.JSON) == "JSON"
