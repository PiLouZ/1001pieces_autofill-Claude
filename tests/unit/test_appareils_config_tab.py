"""Onglet « Appareils » de la configuration des exports : édition des appellations."""

import pytest

from src.utils.qt_imports import QSettings, Qt
from src.utils.appellations_appareils import CONFIG_PAR_DEFAUT


@pytest.fixture
def dialogue(qapp, tmp_path, monkeypatch):
    from src.services import export_config_service as module
    from src.ui.export_config_dialog import ExportConfigDialog
    monkeypatch.setattr(module.ExportConfigService, '_resolve_config_path',
                        staticmethod(lambda: str(tmp_path / 'export_config.json')))
    ini = str(tmp_path / 'reglages.ini')
    monkeypatch.setattr(ExportConfigDialog, '_reglages',
                        staticmethod(lambda: QSettings(ini, QSettings.IniFormat)))
    d = ExportConfigDialog(module.ExportConfigService())
    yield d
    d.deleteLater()


def _ligne_type(onglet, type_):
    return next(i for i, a in enumerate(onglet._appareils) if a['type'] == type_)


def test_aller_retour_inchange(dialogue):
    assert dialogue._collect_config()['synonymes_appareils'] == CONFIG_PAR_DEFAUT


def test_selection_affiche_les_appellations(dialogue):
    onglet = dialogue.appareils_tab
    onglet.types_table.selectRow(_ligne_type(onglet, 'chauffage'))
    assert onglet.variantes_table.rowCount() == 4
    assert onglet.variantes_table.item(1, 0).text() == 'radiateur'
    assert onglet.variantes_table.item(1, 3).checkState() == Qt.Unchecked


def test_activer_un_sous_type_puis_enregistrer(dialogue):
    onglet = dialogue.appareils_tab
    onglet.types_table.selectRow(_ligne_type(onglet, 'chauffage'))
    onglet.variantes_table.item(1, 3).setCheckState(Qt.Checked)
    config = dialogue._collect_config()
    assert dialogue.export_config_service.save_config(config)
    chauffage = next(a for a in dialogue.export_config_service.get_config()
                     ['synonymes_appareils']['appareils'] if a['type'] == 'chauffage')
    assert chauffage['variantes'][1]['actif'] is True
    appellations = dialogue.export_config_service.get_appellations()
    termes = {appellations.choisir('chauffage', f'R{i}', 'meta_description').terme for i in range(300)}
    assert 'radiateur' in termes


def test_ajouter_et_supprimer(dialogue):
    onglet = dialogue.appareils_tab
    onglet.types_table.selectRow(_ligne_type(onglet, 'four'))
    onglet._ajouter_variante()
    onglet.variantes_table.item(0, 0).setText('four encastrable')
    onglet.variantes_table.cellWidget(0, 2).setCurrentIndex(1)   # sous-type
    four = onglet.collect()['appareils'][_ligne_type(onglet, 'four')]
    assert four['variantes'] == [{'terme': 'four encastrable', 'genre': 'm',
                                  'nature': 'sous_type', 'actif': True}]
    onglet.variantes_table.selectRow(0)
    onglet._supprimer_variante()
    assert onglet.collect()['appareils'][_ligne_type(onglet, 'four')]['variantes'] == []

    nb = len(onglet._appareils)
    onglet._ajouter_type()
    onglet.types_table.item(nb, 0).setText('Tireuse à bière')
    onglet.types_table.cellWidget(nb, 1).setCurrentIndex(1)       # féminin
    assert onglet.collect()['appareils'][-1] == {'type': 'tireuse à bière', 'genre': 'f',
                                                 'variantes': []}
    onglet._supprimer_type()
    assert len(onglet._appareils) == nb


def test_case_varier_du_gabarit_titre(dialogue):
    titre = dialogue.titre_tab
    assert not titre.varier_check.isChecked()
    assert all('machine à laver' not in t for t, _ in titre.apercu())
    dialogue.appareils_tab.part_spin.setValue(0)
    titre.varier_check.setChecked(True)
    assert any('machine à laver' in t for t, _ in titre.apercu())
    config = dialogue._collect_config()
    assert config['titre']['profiles'][0]['varier_appareil'] is True
    assert dialogue.export_config_service.save_config(config)
    assert dialogue.export_config_service.get_titre_profile(None)['varier_appareil'] is True


def test_apercu_parts(dialogue):
    onglet = dialogue.appareils_tab
    onglet.part_spin.setValue(100)
    parts = dict(onglet.apercu_type('lave-linge'))
    assert [(c.terme, p) for c, p in parts['Méta description']] == [('lave-linge', 100)]
    onglet.part_spin.setValue(50)
    termes = {c.terme for c, _ in dict(onglet.apercu_type('lave-linge'))['Méta description']}
    assert termes == {'lave-linge', 'machine à laver'}


def test_migration_four_combine_survit_a_l_enregistrement(qapp, tmp_path, monkeypatch):
    """Config d'avant le lot 2 : la migration désactive « four micro-ondes » ;
    l'utilisateur le réactive et enregistre : son choix tient au rechargement
    (la migration notée dans la config ne rejoue pas)."""
    import json
    from src.services import export_config_service as module
    from src.ui.export_config_dialog import ExportConfigDialog
    chemin = tmp_path / 'export_config.json'
    chemin.write_text(json.dumps({'synonymes_appareils': {'appareils': [
        {'type': 'four', 'genre': 'm', 'variantes': []},
        {'type': 'micro-ondes', 'genre': 'm', 'variantes': [
            {'terme': 'four micro-ondes', 'genre': 'm', 'nature': 'synonyme', 'actif': True}]},
    ]}}), encoding='utf-8')
    monkeypatch.setattr(module.ExportConfigService, '_resolve_config_path',
                        staticmethod(lambda: str(chemin)))
    ini = str(tmp_path / 'reglages.ini')
    monkeypatch.setattr(ExportConfigDialog, '_reglages',
                        staticmethod(lambda: QSettings(ini, QSettings.IniFormat)))
    d = ExportConfigDialog(module.ExportConfigService())
    try:
        onglet = d.appareils_tab
        assert [a['type'] for a in onglet._appareils] == ['four', 'micro-ondes',
                                                          'four combiné micro-ondes']
        onglet.types_table.selectRow(_ligne_type(onglet, 'micro-ondes'))
        assert onglet.variantes_table.item(0, 3).checkState() == Qt.Unchecked
        onglet.variantes_table.item(0, 3).setCheckState(Qt.Checked)
        assert d.export_config_service.save_config(d._collect_config())
        relu = module.ExportConfigService().get_config()['synonymes_appareils']
        micro = next(a for a in relu['appareils'] if a['type'] == 'micro-ondes')
        assert micro['variantes'][0]['actif'] is True
    finally:
        d.deleteLater()
