"""
Référence associée Whirlpool / Indesit / Beko, pour tous les imports (CDC import
fiches site, § 10.17, PR 4)

- forme d'une référence : Whirlpool (48 + 10 chiffres), Indesit (C00 + 6), Beko
  (10 chiffres en 17, 18, 28) ; les autres n'ont pas de champ ;
- mémoire : la référence associée devient une équivalente de ligne 0 avec sa marque
  d'origine ; « aucune » est retenue ; le renommage de la pièce suit ;
- fenêtre d'import : fichier seul (collage), cartes de plusieurs fichiers, fiche du
  site (préremplie avec la 2ᵉ réf. de son code produit) ; la réponse mémorisée revient.
Aucun accès réseau, aucun réglage du poste écrit.
"""

import os
from pathlib import Path

import pytest

from src.core.import_manager import (FileType, ImportConfiguration, ImportFile, ImportManager,
                                     ImportType)
from src.ui.fenetre_import import ImportDialog
from src.utils.rapprochement_fiche.associee import autres_origines, origine_associable

from tests.unit.test_fiche_import_ecran import URL_7285, _dialogue_import, _fenetre, _service
from tests.unit.test_reprise_site import FIXTURES, Construite, _db_extrait


@pytest.fixture
def rendus(tmp_path):
    d = Path(os.environ.get('AUTOFILL_RENDUS') or tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_formes_des_trois_groupes():
    assert origine_associable('481073071153') == 'Whirlpool'
    assert origine_associable('C00319033') == 'Indesit'
    assert origine_associable('1734560100') == 'Beko'
    assert origine_associable('11051894') == ''             # BSH : pas de champ
    assert origine_associable('') == ''
    assert autres_origines('Whirlpool') == 'Indesit ou Beko'


def test_memoire_equivalente_ligne_0_aucune_et_renommage(tmp_path):
    b = Construite(tmp_path)
    db = b.db
    assert db.reference_associee('481010595117') == (False, None)
    n = db.definir_references_associees([('481010595117', 'C00111222'), ('481010595118', None)],
                                        '2026-11-13T12:00:00', {'C00111222': 'Indesit'})
    assert n == 2
    assert db.reference_associee('481010595117') == (True, 'C00111222')
    assert db.reference_associee('481010595118') == (True, None)
    ligne, origine = db.conn.execute(
        "SELECT ligne_fiche, origine FROM piece_equivalence_groups WHERE ref_piece = 'C00111222'"
    ).fetchone()
    assert (ligne, origine) == (0, 'Indesit')
    # Sans réponse mémorisée : l'équivalente de ligne 0 est proposée, mais pas connue
    db.conn.execute("DELETE FROM references_associees WHERE ref_piece = '481010595117'")
    db.conn.commit()
    assert db.reference_associee('481010595117') == (False, 'C00111222')
    # Le renommage de la pièce emporte sa réponse
    db.definir_references_associees([('481010595118', None)], '2026-11-13T12:01:00')
    assert db.rename_piece_catalog('481010595118', '481010595119', '')
    assert db.reference_associee('481010595119') == (True, None)
    assert db.reference_associee('481010595118') == (False, None)


def _collage(ref_dialogue, qapp, db, lignes):
    fenetre = _fenetre(qapp, db)
    fichier = ImportFile(path='Collage', type=FileType.CLIPBOARD, suggested_reference='',
                         data=lignes)
    config = ImportConfiguration(files=[fichier], import_type=ImportType.SINGLE_FILE)
    dialogue = ImportDialog(None, config, import_manager=fenetre.import_manager)
    dialogue._load_data_deferred()
    from PyQt5.QtWidgets import QLineEdit
    saisie = dialogue.findChild(QLineEdit, 'ref_input_Collage')
    saisie.setText(ref_dialogue)
    return dialogue


def test_fichier_seul_reponse_memorisee_puis_reproposee(qapp, tmp_path, rendus):
    b = Construite(tmp_path)
    dialogue = _collage('481010595117', qapp, b.db, [['WAE24/01', 'Maxx']])
    champ = dialogue.champ_associee
    assert not champ.isHidden() and "Indesit ou Beko" in champ.libelle.toolTip()
    champ.champ.set_refs(['C00999888'])
    dialogue.resize(1000, 600)
    dialogue.grab().save(str(rendus / 'reference_associee_collage.png'))
    dialogue._validate_and_accept()
    config = dialogue.get_configuration()
    assert config.references_associees == {'481010595117': 'C00999888'}
    res = ImportManager(b.db)._run_import_files(config)
    assert res['references_associees'] == {'481010595117': 'C00999888'}
    groupe = {r[0] for r in b.db.conn.execute("SELECT ref_piece FROM piece_equivalence_groups")}
    assert {'481010595117', 'C00999888'} <= groupe
    # Réimport de la même pièce : la réponse revient
    dialogue = _collage('481010595117', qapp, b.db, [['WAE24/01', 'Maxx']])
    assert dialogue.champ_associee.champ.refs() == ['C00999888']
    # Autre pièce, champ laissé vide : rien n'est retenu ; une pièce BSH n'a pas de champ
    dialogue = _collage('C00123456', qapp, b.db, [['WAE24/01', 'Maxx']])
    assert "Whirlpool ou Beko" in dialogue.champ_associee.libelle.toolTip()
    dialogue._validate_and_accept()
    assert dialogue.get_configuration().references_associees is None
    ImportManager(b.db)._run_import_files(dialogue.get_configuration())
    assert b.db.reference_associee('C00123456') == (False, None)
    dialogue = _collage('11051894', qapp, b.db, [['WAE24/01', 'Maxx']])
    assert dialogue.champ_associee.isHidden()
    dialogue._validate_and_accept()
    assert dialogue.get_configuration().references_associees is None


def test_cartes_de_plusieurs_fichiers(qapp, tmp_path):
    b = Construite(tmp_path)
    fenetre = _fenetre(qapp, b.db)
    fichiers = [ImportFile(path=str(tmp_path / f'{ref}.csv'), type=FileType.CSV,
                           suggested_reference=ref, data=[['WAE24/01', 'Maxx']])
                for ref in ('481010595117', '11051894')]
    config = ImportConfiguration(files=fichiers, import_type=ImportType.MULTI_FILE)
    dialogue = ImportDialog(None, config, import_manager=fenetre.import_manager)
    dialogue._load_data_deferred()
    dialogue.auto_file_references_checkbox.setChecked(True)   # réf. = nom du fichier
    champs = {f.suggested_reference: c for f, c in dialogue._champs_associes}
    assert not champs['481010595117'].isHidden() and champs['11051894'].isHidden()
    champs['481010595117'].champ.set_refs(['C00555666'])
    dialogue._validate_and_accept()
    assert dialogue.get_configuration().references_associees == {'481010595117': 'C00555666'}


def test_fiche_du_site_proposee_par_son_code_produit(qapp, qtbot, tmp_path):
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    service = _service(db, fenetre)
    from src.ui.fiche_site_import import SaisieFicheSite
    saisie = SaisieFicheSite(fenetre, service=service)
    saisie.analyser_page((FIXTURES / 'produit_7285.html').read_text(encoding='utf-8'), URL_7285)
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    champ = dialogue.champ_associee
    assert not champ.isHidden() and champ.champ.refs() == ['C00319033']
    dialogue._validate_and_accept()
    qtbot.waitUntil(lambda: len(fenetre.imports) == 1, timeout=30000)
    assert db.reference_associee('481073071153') == (True, 'C00319033')


def test_reference_associee_a_la_suite_dans_le_code_produit(tmp_path):
    """Pièce importée par PDF (sans produit du site) : sa référence associée va à la
    suite dans le code produit de la Fiche complète, pas dans les équivalentes ;
    dans les deux sens."""
    from tests.unit.test_fiche_export_site import _fiche_service
    b = Construite(tmp_path)
    b.db.definir_references_associees([('C00138863', '482000029398')], '2026-11-13T15:00:00',
                                      {'482000029398': 'Whirlpool'})
    svc = _fiche_service(b.db)
    refs = svc.references_fiche('C00138863')
    assert refs['code_produit'] == ['C00138863', '482000029398']
    assert all('482000029398' not in l for l in refs['lignes_equivalentes'])
    assert svc.references_fiche('482000029398')['code_produit'] == ['482000029398', 'C00138863']


def test_champ_juste_apres_la_reference(qapp, tmp_path, rendus):
    """Fichier seul : « Réf. associée » suit la référence, sans vide entre les deux."""
    b = Construite(tmp_path)
    fenetre = _fenetre(qapp, b.db)
    fichier = ImportFile(path=str(tmp_path / 'C00138863.pdf'), type=FileType.CSV,
                         suggested_reference='C00138863', data=[['WAE24/01', 'Maxx']])
    dialogue = ImportDialog(None, ImportConfiguration(files=[fichier],
                                                      import_type=ImportType.SINGLE_FILE),
                            import_manager=fenetre.import_manager)
    dialogue._load_data_deferred()
    dialogue.resize(1000, 600)
    dialogue.show()
    qapp.processEvents()
    dialogue.grab().save(str(rendus / 'reference_associee_fichier.png'))
    ref = dialogue.findChild(__import__('PyQt5.QtWidgets', fromlist=['QLabel']).QLabel,
                             f"ref_display_{fichier.path}")
    champ = dialogue.champ_associee
    ecart = champ.geometry().left() - ref.geometry().right()
    assert 0 <= ecart < 30, ecart
    dialogue.close()
