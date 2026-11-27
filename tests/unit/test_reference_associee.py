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
    # Forme non reconnue : seulement « Associer… » (groupe à déclarer, § 10.17 bis)
    champ = dialogue.champ_associee
    assert champ.champ.isHidden() and not champ.lien_associer.isHidden()
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
    assert not champs['481010595117'].isHidden() and champs['11051894'].champ.isHidden()
    assert champs['481010595117'].lien_associer.isHidden()
    assert not champs['11051894'].lien_associer.isHidden()
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
    suite dans le code produit de la Fiche complète, pas dans les équivalentes ; la
    principale toujours en premier, quelle que soit la référence recherchée."""
    from tests.unit.test_fiche_export_site import _fiche_service
    b = Construite(tmp_path)
    b.db.definir_references_associees([('C00138863', '482000029398')], '2026-11-13T15:00:00',
                                      {'482000029398': 'Whirlpool'})
    svc = _fiche_service(b.db)
    refs = svc.references_fiche('C00138863')
    assert refs['code_produit'] == ['C00138863', '482000029398']
    assert all('482000029398' not in l for l in refs['lignes_equivalentes'])
    assert svc.references_fiche('482000029398')['code_produit'] == ['C00138863', '482000029398']


def test_jumelle_d_une_ancienne_reference_a_la_suite_dans_remplace(tmp_path):
    """Import PDF de C00647231 : sa jumelle va dans le code produit, celle de son
    ancienne référence 481010771228 juste derrière elle dans « Remplace » (et pas
    en équivalente, ni en « ligne 0 » du code produit)."""
    from tests.unit.test_fiche_export_site import _fiche_service
    b = Construite(tmp_path)
    b.db.add_supersession('481010771228', 'C00647231')
    b.db.definir_references_associees(
        [('C00647231', '488000647231'), ('481010771228', 'C00446909')], '2026-11-16T15:12:04',
        {'488000647231': 'Whirlpool', 'C00446909': 'Indesit'})
    ligne = b.db.conn.execute("SELECT ligne_fiche FROM piece_equivalence_groups "
                              "WHERE ref_piece = 'C00446909'").fetchone()[0]
    assert ligne is None
    assert b.db.reference_associee('C00647231') == (True, '488000647231')
    refs = _fiche_service(b.db).references_fiche('C00647231')
    assert refs['code_produit'] == ['C00647231', '488000647231']
    assert refs['remplace'] == ['481010771228', 'C00446909']
    assert refs['lignes_equivalentes'] == [] and refs['equivalentes'] == []


def test_jumelles_des_equivalentes_suivent_leur_principale(tmp_path):
    """Cas Beko : appareils sur les réf. de fichier (4298…), jumelles C00… . Chaque
    paire se suit, principale d'abord, dans l'ordre des lignées (successeur avant
    ancienne), sur une seule ligne d'équivalentes."""
    from tests.unit.test_fiche_export_site import _fiche_service
    b = Construite(tmp_path)
    db = b.db
    db.add_supersession('C00880446', 'C00916410')
    db.add_supersession('C00869001', 'C00870867')
    le = '2026-11-27T08:31:51'
    db.definir_references_associees(
        [('C00868066', '4298130200'), ('C00916410', '4298130100'), ('C00880446', '4298130172'),
         ('C00870867', '4858140300'), ('C00869001', '4858140372')], le)
    for autre in ('C00916410', 'C00880446', 'C00870867', 'C00869001'):   # un seul groupe
        db.add_equivalence('C00868066', autre)
    for ref in ('4298130100', '4298130172'):          # les appareils sont sur les réf. de fichier
        db.conn.execute("INSERT OR IGNORE INTO pieces (ref_piece, description) VALUES (?, 'x')", (ref,))
    for i, ref in enumerate(('4298130100', '4298130172', '4298130172'), start=1):
        db.conn.execute("INSERT OR IGNORE INTO appareils (id) VALUES (?)", (i,))
        pid = db.conn.execute("SELECT id FROM pieces WHERE ref_piece = ?", (ref,)).fetchone()[0]
        db.conn.execute("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)", (pid, i))
    db.conn.commit()
    svc = _fiche_service(db)
    attendu = [['C00916410', '4298130100', 'C00880446', '4298130172',
                'C00870867', '4858140300', 'C00869001', '4858140372']]
    for cherchee in ('C00868066', '4298130200'):
        refs = svc.references_fiche(cherchee)
        assert refs['code_produit'] == ['C00868066', '4298130200']
        assert refs['lignes_equivalentes'] == attendu


def test_reference_associee_herite_du_libelle(tmp_path):
    """La jumelle créée par l'import (sans libellé) reçoit celui de la pièce ; un
    libellé déjà présent n'est jamais écrasé, dans un sens comme dans l'autre."""
    b = Construite(tmp_path)
    db = b.db
    db.conn.execute("INSERT INTO pieces (ref_piece, description) VALUES ('4298130200', 'Balconnet')")
    db.conn.execute("INSERT INTO pieces (ref_piece, description) VALUES ('C00900001', 'Autre nom')")
    db.conn.commit()
    db.definir_references_associees(
        [('4298130200', 'C00868066'), ('C00900001', '4858140372'), ('C00700002', 'C00900001')],
        '2026-11-27T08:31:51')
    desc = dict(db.conn.execute("SELECT ref_piece, description FROM pieces").fetchall())
    assert desc['C00868066'] == 'Balconnet'               # jumelle sans libellé : hérite
    assert desc['4858140372'] == 'Autre nom'
    assert desc['C00700002'] == 'Autre nom'               # sens inverse : la pièce hérite
    assert desc['4298130200'] == 'Balconnet' and desc['C00900001'] == 'Autre nom'


def test_jumelles_a_la_suite_sur_la_meme_ligne():
    from src.ui.fiche_produit_service import FicheProduitService
    suite = FicheProduitService.jumelles_a_la_suite
    # Jumelle d'une ancienne réf. : de l'équivalente vers « Remplace »
    assert suite([['A1'], ['I1', 'X']], [('A1', 'I1')]) == [['A1', 'I1'], ['X']]
    # La première des deux garde sa place, sa jumelle juste derrière
    assert suite([['X', 'I1', 'Y'], ['A1']], [('A1', 'I1')]) == [['X', 'I1', 'A1', 'Y'], []]
    # Deux lignes d'équivalentes : sur la première
    assert suite([[], ['P', 'Q'], ['R', 'S']], [('S', 'P')]) == [[], ['P', 'S', 'Q'], ['R']]
    # Même ligne, écartées : rapprochées
    assert suite([['A1', 'X', 'I1']], [('A1', 'I1')]) == [['A1', 'I1', 'X']]
    # Déjà à la suite (dans un sens ou l'autre, ordre du site), ou une réf. absente : inchangé
    assert suite([['A1', 'I1', 'X']], [('A1', 'I1')]) == [['A1', 'I1', 'X']]
    assert suite([['I1', 'A1', 'X']], [('A1', 'I1')]) == [['I1', 'A1', 'X']]
    assert suite([['A1', 'X']], [('A1', 'I9')]) == [['A1', 'X']]
    # Une réf. déjà rangée avec une jumelle n'en change pas
    assert suite([['A1', 'I1', 'B1']], [('A1', 'I1'), ('B1', 'I1')]) == [['A1', 'I1', 'B1']]


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


# =============================================================================
# « ⇄ » : la référence associée devient la principale
# =============================================================================

def test_inverser_dans_un_collage(qapp, tmp_path):
    b = Construite(tmp_path)
    dialogue = _collage('C00138863', qapp, b.db, [['WAE24/01', 'Maxx']])
    champ = dialogue.champ_associee
    assert champ.bouton_inverser.isHidden()               # rien à inverser sans associée
    champ.champ.set_refs(['482000029398'])
    assert not champ.bouton_inverser.isHidden()
    champ.inverser()
    from PyQt5.QtWidgets import QLineEdit
    assert dialogue.findChild(QLineEdit, 'ref_input_Collage').text() == '482000029398'
    assert champ.champ.refs() == ['C00138863']
    dialogue._validate_and_accept()
    config = dialogue.get_configuration()
    assert config.individual_references['Collage'] == '482000029398'
    assert config.references_associees == {'482000029398': 'C00138863'}


def test_inverser_un_fichier_appareils_restent_sur_le_fichier(qapp, tmp_path, rendus):
    """« ⇄ » sur un fichier : l'associée devient la PRINCIPALE de la paire, mais les
    appareils restent sur la réf. du nom de fichier (cas Beko 4298130200 / C00868066)."""
    from tests.unit.test_fiche_export_site import _fiche_service
    b = Construite(tmp_path)
    fenetre = _fenetre(qapp, b.db)
    chemin = tmp_path / 'C00138863.csv'
    chemin.write_text('WAE24/01;Maxx\n', encoding='utf-8')
    fichier = ImportFile(path=str(chemin), type=FileType.CSV, suggested_reference='C00138863',
                         data=[['WAE24/01', 'Maxx']])
    dialogue = ImportDialog(None, ImportConfiguration(files=[fichier],
                                                      import_type=ImportType.SINGLE_FILE),
                            import_manager=fenetre.import_manager)
    dialogue._load_data_deferred()
    dialogue.champ_associee.champ.set_refs(['482000029398'])
    dialogue.champ_associee.inverser()
    from PyQt5.QtWidgets import QLabel
    etiquette = dialogue.findChild(QLabel, f"ref_display_{fichier.path}")
    assert etiquette.text() == "→ Réf. : C00138863" and '482000029398' in etiquette.toolTip()
    assert dialogue.champ_associee.libelle.text() == "Réf. principale :"
    dialogue.resize(1000, 600)
    dialogue.show()
    qapp.processEvents()
    dialogue.grab().save(str(rendus / 'reference_associee_inversee.png'))
    dialogue._validate_and_accept()
    config = dialogue.get_configuration()
    assert config.individual_references[fichier.path] == 'C00138863'
    assert config.references_associees == {'482000029398': 'C00138863'}
    ImportManager(b.db)._run_import_files(config)
    lies = dict(b.db.conn.execute(
        "SELECT p.ref_piece, COUNT(pa.id) FROM pieces p LEFT JOIN piece_associations pa "
        "ON pa.piece_id = p.id GROUP BY p.ref_piece").fetchall())
    assert lies.get('C00138863') == 1 and not lies.get('482000029398')
    assert b.db.reference_associee('482000029398') == (True, 'C00138863')
    assert b.db.reference_principale_de('C00138863') == '482000029398'
    svc = _fiche_service(b.db)
    for cherchee in ('482000029398', 'C00138863'):
        assert svc.references_fiche(cherchee)['code_produit'] == ['482000029398', 'C00138863']
    # Inverser deux fois revient au point de départ
    d2 = ImportDialog(None, ImportConfiguration(files=[fichier], import_type=ImportType.SINGLE_FILE),
                      import_manager=fenetre.import_manager)
    d2._load_data_deferred()
    d2.champ_associee.champ.set_refs(['482000029398'])
    d2.champ_associee.inverser()
    d2.champ_associee.inverser()
    d2._validate_and_accept()
    config2 = d2.get_configuration()
    assert config2.individual_references[fichier.path] == 'C00138863'
    assert config2.references_associees == {'C00138863': '482000029398'}
    assert d2.champ_associee.libelle.text() == "Réf. associée :"
    dialogue.close()


def test_inverser_une_fiche_du_site(qapp, qtbot, tmp_path):
    """Fiche 7285 : la 2ᵉ réf. du code produit devient la pièce (appareils, produit du site)."""
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    service = _service(db, fenetre)
    from src.ui.fiche_site_import import SaisieFicheSite
    saisie = SaisieFicheSite(fenetre, service=service)
    saisie.analyser_page((FIXTURES / 'produit_7285.html').read_text(encoding='utf-8'), URL_7285)
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    assert dialogue.champ_associee.champ.refs() == ['C00319033']
    dialogue.champ_associee.inverser()
    dialogue._validate_and_accept()
    qtbot.waitUntil(lambda: len(fenetre.imports) == 1, timeout=30000)
    assert db.reference_associee('C00319033') == (True, '481073071153')
    produit = db.conn.execute("SELECT ref_piece FROM produits_site").fetchone()
    assert produit == ('C00319033',)
    liens = db.conn.execute(
        "SELECT COUNT(*) FROM piece_associations pa JOIN pieces p ON p.id = pa.piece_id "
        "WHERE p.ref_piece = 'C00319033'").fetchone()[0]
    assert liens > 0
    egale = db.conn.execute(
        "SELECT COUNT(*) FROM piece_equivalence_groups a JOIN piece_equivalence_groups b "
        "ON a.group_id = b.group_id WHERE a.ref_piece = 'C00319033' AND b.ref_piece = '481073071153'"
    ).fetchone()[0]
    assert egale == 1
