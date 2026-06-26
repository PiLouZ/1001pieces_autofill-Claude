"""
Tests de non-régression — Rendu des exports HTML et CSV
Couvre : {modele_complet}, {separateur}, tiret résiduel, limite de caractères
"""

import copy
import pytest
from unittest.mock import patch

from src.services.export_config_service import ExportConfigService, DEFAULT_CONFIG
from src.services.html_export_service import HtmlExportService


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def config_service(qapp, tmp_path):
    """
    ExportConfigService avec fichier de config temporaire isolé.
    On instancie normalement (QObject.__init__ appelé via qapp),
    puis on redirige le chemin de config vers tmp_path.
    """
    config_path = str(tmp_path / "export_config.json")
    with patch.object(ExportConfigService, '_resolve_config_path', return_value=config_path):
        svc = ExportConfigService()
    # Repartir explicitement sur les défauts (zéro interférence inter-tests)
    svc._config = copy.deepcopy(DEFAULT_CONFIG)
    return svc


@pytest.fixture(autouse=True)
def inject_config(config_service):
    """Injecter le service de config dans HtmlExportService pour chaque test"""
    HtmlExportService.set_config_service(config_service)
    yield
    HtmlExportService.set_config_service(None)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_col(config_service: ExportConfigService, row: list, header: str) -> str:
    """Récupérer la valeur d'une colonne CSV par son en-tête"""
    for i, col in enumerate(config_service.get_csv_columns()):
        if col['header'] == header:
            return row[i]
    raise KeyError(f"Colonne '{header}' introuvable dans la config CSV")


def _add_col(config_service: ExportConfigService, header: str, source: str):
    """Ajouter une colonne temporaire à la config CSV"""
    cfg = config_service.get_config()
    cfg['csv']['columns'].append({'header': header, 'source': source})
    config_service.save_config(cfg)


def _set_details(config_service: ExportConfigService, **kwargs):
    """Écrire des clés du profil HTML Détails PAR DÉFAUT (source de vérité depuis
    la migration profils v3.40.0). La section legacy 'html.details' est un miroir
    reconstruit depuis ce profil à la sauvegarde : y écrire directement serait
    écrasé. `generate_html_details` lit `get_html_details_config()` → ce profil."""
    cfg = config_service.get_config()
    name = cfg['html'].get('details_default_profile')
    for p in cfg['html']['details_profiles']:
        if p.get('name') == name:
            p.update(kwargs)
            break
    config_service.save_config(cfg)


# ─── Tests {modele_complet} — rendu CSV ──────────────────────────────────────

class TestCsvModeleComplet:
    """Colonne modele_name utilisant {modele_complet}"""

    def test_deux_refs_fusionnees(self, config_service):
        """Les deux refs → fusionnées avec tiret"""
        record = ('Type', 'Marque', 'REF-MOD', 'REF-COM', 'OTHER', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        assert _get_col(config_service, row, 'modele_name') == 'REF-MOD - REF-COM'

    def test_ref_modele_seule_sans_tiret_residuel(self, config_service):
        """Seulement ref_modele → pas de tiret résiduel en fin de valeur"""
        record = ('Type', 'Marque', 'REF-MOD', '', 'OTHER', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        val = _get_col(config_service, row, 'modele_name')
        assert val == 'REF-MOD'
        assert not val.endswith(' -') and not val.startswith('- ')

    def test_ref_commerciale_seule_sans_tiret_residuel(self, config_service):
        """Seulement ref_commerciale → pas de tiret résiduel en début de valeur"""
        record = ('Type', 'Marque', '', 'REF-COM', 'OTHER', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        val = _get_col(config_service, row, 'modele_name')
        assert val == 'REF-COM'
        assert not val.endswith(' -') and not val.startswith('- ')

    def test_les_deux_vides(self, config_service):
        """Aucune ref → chaîne vide"""
        record = ('Type', 'Marque', '', '', 'OTHER', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        assert _get_col(config_service, row, 'modele_name') == ''


# ─── Tests {separateur} — rendu CSV ──────────────────────────────────────────

class TestCsvSeparateur:
    """{separateur} = ' - ' si les deux refs présentes, '' sinon"""

    def test_separateur_present_quand_deux_refs(self, config_service):
        # Note : en CSV le contexte utilise {commercial_ref}, pas {ref_commerciale} (convention HTML)
        _add_col(config_service, 'sep_test', '{ref_modele}{separateur}{commercial_ref}')
        record = ('Type', 'Marque', 'MOD', 'COM', '', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        assert _get_col(config_service, row, 'sep_test') == 'MOD - COM'

    def test_separateur_absent_quand_ref_modele_manquante(self, config_service):
        _add_col(config_service, 'sep_test', '{ref_modele}{separateur}{commercial_ref}')
        record = ('Type', 'Marque', '', 'COM', '', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        val = _get_col(config_service, row, 'sep_test')
        assert val == 'COM'
        assert ' - ' not in val

    def test_separateur_absent_quand_ref_commerciale_manquante(self, config_service):
        _add_col(config_service, 'sep_test', '{ref_modele}{separateur}{commercial_ref}')
        record = ('Type', 'Marque', 'MOD', '', '', 'PIECE')
        row = config_service.render_csv_row(record, 'test')
        val = _get_col(config_service, row, 'sep_test')
        assert val == 'MOD'
        assert ' - ' not in val


# ─── Tests {modele_complet} et {separateur} — rendu HTML ─────────────────────

class TestHtmlRendering:
    """Rendu HTML via HtmlExportService"""

    _deux_refs  = [('Appl', 'Bosch', 'MOD-1', 'COM-1')]
    _mod_seul   = [('Appl', 'Bosch', 'MOD-1', '')]
    _com_seul   = [('Appl', 'Bosch', '', 'COM-1')]
    _deux_vides = [('Appl', 'Bosch', '', '')]

    def test_template_defaut_deux_refs(self):
        """Template défaut {modele_complet} : deux refs → fusionnées"""
        html = HtmlExportService.generate_html_details(self._deux_refs)
        assert 'MOD-1 - COM-1' in html

    def test_template_defaut_ref_modele_seule(self):
        """Template défaut : ref_modele seule → pas de tiret résiduel"""
        html = HtmlExportService.generate_html_details(self._mod_seul)
        assert 'MOD-1' in html
        assert ' - ' not in html

    def test_template_defaut_ref_commerciale_seule(self):
        """Template défaut : ref_commerciale seule → pas de tiret résiduel"""
        html = HtmlExportService.generate_html_details(self._com_seul)
        assert 'COM-1' in html
        assert ' - ' not in html

    def test_template_defaut_deux_refs_vides(self):
        """Template défaut : aucune ref → aucune ligne modèle rendue"""
        html = HtmlExportService.generate_html_details(self._deux_vides)
        assert '<div></div>' not in html

    def test_template_personnalise_separateur(self, config_service):
        """Template {separateur} : tiret uniquement quand les deux refs présentes"""
        _set_details(config_service,
                     model_line_template='<div><b>{ref_modele}</b>{separateur}{ref_commerciale}</div>')

        html_deux = HtmlExportService.generate_html_details(self._deux_refs)
        assert '<b>MOD-1</b> - COM-1' in html_deux

        html_mod = HtmlExportService.generate_html_details(self._mod_seul)
        assert '<b>MOD-1</b>' in html_mod
        assert ' - ' not in html_mod

    def test_template_personnalise_modele_complet(self, config_service):
        """Template {modele_complet} : rendu correct selon la présence des refs"""
        _set_details(config_service, model_line_template='<li>{modele_complet}</li>')

        html = HtmlExportService.generate_html_details(self._deux_refs)
        assert '<li>MOD-1 - COM-1</li>' in html

        html_mod = HtmlExportService.generate_html_details(self._mod_seul)
        assert '<li>MOD-1</li>' in html_mod
        assert ' - ' not in html_mod


# ─── Tests limite de caractères HTML ─────────────────────────────────────────

class TestHtmlCharLimit:
    """Stratégies de réduction quand la limite est dépassée"""

    @staticmethod
    def _make_data(n: int):
        return [
            ('Appl', f'Marque{i % 5}', f'REF-MODELE-LONG-{i:04d}', f'COM-REF-LONG-{i:04d}')
            for i in range(n)
        ]

    def test_contenu_valide_dans_limite(self):
        """Avec peu de données, retourne le HTML avec les refs attendues"""
        data = self._make_data(5)
        html = HtmlExportService.generate_html_details(data)
        assert 'REF-MODELE-LONG-0000' in html

    def test_fallback_quand_limite_depassee(self, config_service):
        """Quand full dépasse la limite, repasse en mode ref unique"""
        _set_details(config_service, char_limit=200)

        data = self._make_data(50)
        html = HtmlExportService.generate_html_details(data)
        # Les deux refs fusionnées ne doivent plus apparaître ensemble
        assert 'REF-MODELE-LONG-0000 - COM-REF-LONG-0000' not in html

    def test_message_trop_volumineux_en_dernier_recours(self, config_service):
        """Quand même le fallback dépasse, affiche le message d'erreur dédié"""
        _set_details(config_service, char_limit=1)

        html = HtmlExportService.generate_html_details(self._make_data(100))
        assert 'trop volumineuses' in html


# ─── Tests _render_source — comportement du nettoyage de tiret ───────────────

class TestRenderSourceBehavior:
    """
    Documente le comportement de _render_source face aux tirets résiduels.

    IMPORTANT : _render_source nettoie uniquement les cas ' - ' (les deux champs vides).
    Les cas 'REF - ' (un seul champ vide) ne sont PAS nettoyés par _render_source.
    C'est pourquoi {modele_complet} existe : il produit toujours un résultat propre.
    """

    def test_source_literale_sans_variables(self, config_service):
        """Source sans variable → rendue telle quelle"""
        _add_col(config_service, 'lit', 'valeur_fixe')
        record = ('T', 'M', 'R', 'C', 'O', 'P')
        row = config_service.render_csv_row(record, 'x')
        assert _get_col(config_service, row, 'lit') == 'valeur_fixe'

    def test_render_source_nettoie_les_deux_vides(self, config_service):
        """_render_source : quand les deux champs sont vides, le ' - ' est nettoyé"""
        _add_col(config_service, 'old_style', '{ref_modele} - {commercial_ref}')
        record = ('T', 'M', '', '', 'O', 'P')
        row = config_service.render_csv_row(record, 'x')
        val = _get_col(config_service, row, 'old_style')
        assert val == ''  # nettoyé par _render_source

    def test_modele_complet_propre_la_ou_old_style_ne_lest_pas(self, config_service):
        """
        {modele_complet} produit 'REF' (propre) là où {ref_modele} - {commercial_ref}
        produirait 'REF -' (tiret résiduel non nettoyé par _render_source).
        C'est la raison d'être de {modele_complet}.
        """
        _add_col(config_service, 'new_style', '{modele_complet}')
        _add_col(config_service, 'old_style', '{ref_modele} - {commercial_ref}')

        record = ('T', 'M', 'REF', '', 'O', 'P')
        row = config_service.render_csv_row(record, 'x')

        new_val = _get_col(config_service, row, 'new_style')
        old_val = _get_col(config_service, row, 'old_style')

        # {modele_complet} → propre
        assert new_val == 'REF'
        assert not new_val.endswith(' -')

        # ancien template → tiret résiduel (comportement documenté, non régressé)
        assert old_val == 'REF -'
