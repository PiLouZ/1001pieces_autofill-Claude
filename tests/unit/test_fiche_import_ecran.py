"""
« Lire une fiche du site » passe par la fenêtre d'import (CDC import fiches site,
§ 10.12 à 10.14, PR 2)

- la fiche 7285 s'ouvre dans `ImportDialog` : aperçu des lignes, référence,
  libellé, Succession préremplie ; une équivalente retirée est écartée ; l'import
  réel se fait comme pour un PDF (historique, suggestions) ; relue, elle n'ajoute rien ;
- la fiche 7196 (crochet portillon, lignes « 12NC nom description » collées) est en
  vrac : bandeau, aucun appareil créé, fiche notée « à refaire depuis les PDF » ;
  un import (collage) de sa référence la retire de la liste ;
- un lien de 1001pieces.com collé est reconnu.
Rendus hors écran dans AUTOFILL_RENDUS (sinon dans le dossier du test). Aucun accès
réseau, aucun réglage du poste écrit.
"""

import os
from pathlib import Path

import pytest

from src.core.import_manager import (FileType, ImportConfiguration, ImportFile, ImportManager,
                                     ImportType)
from src.services.enregistrement_fiche_service import EnregistrementFicheService
from src.ui.fenetre_import import ImportDialog
from src.ui.fiche_site_import import SaisieFicheSite, est_lien_fiche_site

from tests.unit.test_reprise_site import CONFIG, FIXTURES, MODELES, _db_extrait, _instantane

URL_7285 = 'https://www.1001pieces.com/7285-fiche.html'


@pytest.fixture
def rendus(tmp_path):
    d = Path(os.environ.get('AUTOFILL_RENDUS') or tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fenetre(qapp, db):
    """Fenêtre principale réduite à ce que l'import d'une fiche utilise."""
    from PyQt5.QtWidgets import QWidget

    class Principale(QWidget):
        def __init__(self):
            super().__init__()
            self.db_manager = db
            self.import_manager = ImportManager(db, parent_widget=self)
            self.imports, self.pieces = [], []

        def _on_import_complete(self, results):
            self.imports.append(results)

        def _apres_fiche_site(self, ref, _results):
            self.pieces.append(ref)

    return Principale()


def _service(db, fenetre):
    s = EnregistrementFicheService(db, parent_window=fenetre, configuration=CONFIG)
    s._modeles = lambda: MODELES
    return s


def _dialogue_import(qapp):
    qapp.processEvents()
    ouverts = [w for w in qapp.topLevelWidgets() if isinstance(w, ImportDialog) and w.isVisible()]
    assert len(ouverts) == 1
    return ouverts[0]


def _importer(qtbot, dialogue, fenetre, attendus):
    dialogue._validate_and_accept()
    qtbot.waitUntil(lambda: len(fenetre.imports) == attendus, timeout=30000)
    return fenetre.imports[-1]


def test_zone_unique_lien_ou_description(qapp, monkeypatch, tmp_path):
    """Un lien seul est téléchargé ; un texte (même contenant un lien) est une description."""
    from src.ui.fiche_site_import import est_un_lien
    assert est_un_lien(' https://www.1001pieces.com/7196-crochet.html \n')
    assert not est_un_lien('<div>Code produit : 480131100599</div> https://x.fr/a')
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    saisie = SaisieFicheSite(fenetre, service=_service(db, fenetre))
    appels = []
    monkeypatch.setattr(saisie, 'lire_lien', lambda url='': appels.append(('lien', url)))
    monkeypatch.setattr(saisie, '_analyser', lambda lire, url='': appels.append(('texte', url)))
    saisie.champ.setPlainText('https://www.1001pieces.com/7196-crochet.html')
    saisie.lire()
    saisie.champ.setPlainText('Code produit : 480131100599\nAppareils : …')
    saisie.lire()
    assert appels == [('lien', 'https://www.1001pieces.com/7196-crochet.html'), ('texte', '')]


def test_lien_du_site_reconnu():
    assert est_lien_fiche_site('  https://www.1001pieces.com/porte/7196-crochet.html\n')
    assert est_lien_fiche_site('http://1001pieces.com/7285-fiche.html')
    assert not est_lien_fiche_site('https://www.exemple.com/7285.html')
    assert not est_lien_fiche_site('WAE24/01\tMaxx')
    assert not est_lien_fiche_site('https://www.1001pieces.com/a.html autre')


def test_fiche_7285_par_la_fenetre_d_import(qapp, qtbot, tmp_path, rendus):
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    service = _service(db, fenetre)
    page = (FIXTURES / 'produit_7285.html').read_text(encoding='utf-8')
    saisie = SaisieFicheSite(fenetre, service=service)
    saisie.analyser_page(page, URL_7285)
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    assert dialogue.windowTitle() == "Importer une fiche du site"
    assert "Fiche du site n° 7285" in dialogue.format_info_label.text()
    assert "1838 appareils connus à relier" in dialogue.format_desc_label.text()
    assert not dialogue.mapping_container.isVisible()
    # Succession préremplie depuis la fiche
    remplace = dialogue.succ_replaces_input.refs()
    assert 'C00535957' in remplace and '488000535957' in remplace
    equivalentes = dialogue.equiv_input.refs()
    assert 'C00319033' in equivalentes and '00145522' in equivalentes
    dialogue.resize(1100, 820)
    dialogue.grab().save(str(rendus / 'fiche_7285_fenetre_import.png'))
    # On retire une équivalente : confirmation demandée, puis elle est écartée,
    # et n'est plus proposée
    dialogue.equiv_input.remove_ref('00145522')
    dialogue._validate_and_accept()
    boite = dialogue._boite_ecartees
    assert boite is not None and '481073071153 : 00145522' in boite.text()
    boite.buttons()[0].click()          # « Écarter et importer »
    qtbot.waitUntil(lambda: len(fenetre.imports) == 1, timeout=30000)
    resultats = fenetre.imports[-1]
    assert resultats["total_files"] == 1 and resultats["associations_created"] > 0
    assert 'similarity_suggestions' in resultats
    assert fenetre.pieces == ['481073071153']
    ecartee = db.conn.execute("SELECT nature FROM decisions_references WHERE ref_piece = "
                              "'481073071153' AND reference = '00145522'").fetchone()
    assert ecartee == ('ecartee',)
    groupe = {r[0] for r in db.conn.execute("SELECT ref_piece FROM piece_equivalence_groups")}
    assert '00145522' not in groupe and 'C00319033' in groupe
    apres = _instantane(db)
    # Relue par la même fenêtre : rien n'est ajouté
    saisie = SaisieFicheSite(fenetre, service=service)
    saisie.analyser_page(page, URL_7285)
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    assert '00145522' not in dialogue.equiv_input.refs()
    resultats = _importer(qtbot, dialogue, fenetre, 2)
    assert resultats['new_entries'] == 0 and resultats['associations_created'] == 0
    assert _instantane(db) == apres


def test_fiche_en_vrac_a_refaire_puis_refaite_par_un_import(qapp, qtbot, tmp_path, rendus):
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    service = _service(db, fenetre)
    description = (FIXTURES / 'description_7196.html').read_text(encoding='utf-8')
    saisie = SaisieFicheSite(fenetre, service=service)
    saisie.champ.setPlainText(description)
    saisie.lire()                       # un texte, pas un lien : lu comme description
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    assert dialogue.bandeau_fiche.isVisible() or not dialogue.isVisible()
    assert "à refaire depuis les PDF" in dialogue.bandeau_fiche.text()
    assert "480131100599" in dialogue.bandeau_fiche.text()
    dialogue.resize(1100, 760)
    dialogue.grab().save(str(rendus / 'fiche_7196_en_vrac.png'))
    avant = _instantane(db)
    resultats = _importer(qtbot, dialogue, fenetre, 1)
    assert resultats['new_entries'] == 0                   # aucune création bancale
    assert _instantane(db)['appareils'] == avant['appareils']
    assert [r for r, _ in resultats['fiches_a_refaire']] == ['480131100599']
    liste = db.fiches_a_refaire()
    assert [f['ref_piece'] for f in liste] == ['480131100599'] and liste[0]['en_vrac'] == 1
    # La fiche est refaite par un import (ici un collage) de sa référence
    fichier = ImportFile(path='Collage', type=FileType.CLIPBOARD, suggested_reference='',
                         data=[['ARC5453', ''], ['ARG8612/A+', '']])
    config = ImportConfiguration(files=[fichier], import_type=ImportType.SINGLE_FILE,
                                 individual_references={'Collage': '480131100599'})
    res = ImportManager(db)._run_import_files(config)
    assert res['fiches_refaites'] == ['480131100599']
    assert db.fiches_a_refaire() == []


def test_lien_colle_dans_le_tableau_ouvre_la_fiche(qapp):
    """Cmd+V d'un lien de 1001pieces.com : import de cette fiche, pas un collage."""
    from PyQt5.QtWidgets import QApplication
    from src.ui.main_refactored import MainWindow

    class Fausse:
        _piece_description_decisions = {}

        def __init__(self):
            self.ouvertes = []

        def _open_fiche_site_dialog(self, url=''):
            self.ouvertes.append(url)

    f = Fausse()
    QApplication.clipboard().setText(' https://www.1001pieces.com/7196-crochet.html\n')
    MainWindow._safe_handle_paste(f)
    assert f.ouvertes == ['https://www.1001pieces.com/7196-crochet.html']


def test_equivalente_deplacee_dans_remplace_pas_ecartee(qapp, qtbot, tmp_path):
    """Fiche mal structurée (cas 00648024) : une ancienne référence citée en
    équivalente est déplacée dans « Remplace » à l'import. Le remplacement est
    écrit, l'équivalence non, et la référence n'est pas écartée."""
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    page = (FIXTURES / 'produit_7285.html').read_text(encoding='utf-8')
    saisie = SaisieFicheSite(fenetre, service=_service(db, fenetre))
    saisie.analyser_page(page, URL_7285)
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    dialogue.equiv_input.remove_ref('00145522')
    dialogue.succ_replaces_input.set_refs(dialogue.succ_replaces_input.refs() + ['00145522'])
    _importer(qtbot, dialogue, fenetre, 1)            # sans confirmation : rien d'écarté
    assert dialogue._boite_ecartees is None
    assert db.conn.execute("SELECT COUNT(*) FROM decisions_references WHERE ref_piece = "
                           "'481073071153' AND reference = '00145522'").fetchone()[0] == 0
    assert db.conn.execute("SELECT ref_new FROM piece_supersessions WHERE ref_old = "
                           "'00145522'").fetchone() == ('481073071153',)
    # Rangée comme les autres anciennes références de la pièce (même groupe)
    groupe = dict(db.conn.execute("SELECT ref_piece, group_id FROM piece_equivalence_groups"))
    assert groupe.get('00145522') == groupe.get('488000535957') == groupe['481073071153']


def test_retrait_d_equivalente_revenir_au_dialogue(qapp, qtbot, tmp_path):
    """« Revenir au dialogue » : rien n'est importé ni écarté, la fenêtre reste ouverte."""
    db = _db_extrait(tmp_path)
    fenetre = _fenetre(qapp, db)
    page = (FIXTURES / 'produit_7285.html').read_text(encoding='utf-8')
    saisie = SaisieFicheSite(fenetre, service=_service(db, fenetre))
    saisie.analyser_page(page, URL_7285)
    dialogue = _dialogue_import(qapp)
    dialogue._load_data_deferred()
    dialogue.equiv_input.remove_ref('00145522')
    dialogue._validate_and_accept()
    boite = dialogue._boite_ecartees
    boite.buttons()[1].click()          # « Revenir au dialogue »
    qapp.processEvents()
    assert dialogue.isVisible() and dialogue.result_config is None
    assert fenetre.imports == []
    assert db.conn.execute("SELECT COUNT(*) FROM decisions_references").fetchone()[0] == 0
    dialogue.close()


def test_ecartees_d_un_lot_par_carte():
    """Lot en cartes : seules les cartes cochées comptent ; une référence déplacée
    vers « Remplace » ou « Remplacée par » n'est pas écartée."""
    from types import SimpleNamespace as NS
    from src.core.import_manager import ImportConfiguration
    from src.services.enregistrement_fiche_service import FicheAImporter

    def fiche(ref, equivalentes):
        f = NS(plan=NS(ref_piece=ref), equivalentes=lambda: list(equivalentes))
        f.equivalentes_ecartees = lambda *a, **k: \
            FicheAImporter.equivalentes_ecartees(f, *a, **k)
        return f

    def carte(chemin, f, coche, remplace=(), equivalentes=(), remplacee_par=()):
        champ = lambda refs: NS(refs=lambda: list(refs))
        return {'file': NS(path=chemin, fiche=f), 'importer': NS(isChecked=lambda: coche),
                'remplace': champ(remplace), 'equivalentes': champ(equivalentes),
                'remplacee_par': champ(remplacee_par)}

    dlg = NS(_fiche=None, equiv_input=None, _cartes_fiches=[
        carte('a', fiche('P1', ['E1', 'E2', 'E3']), True, remplace=['E1'], remplacee_par=['E3']),
        carte('b', fiche('P2', ['F1']), False),
        carte('c', fiche('P3', ['G1', 'G2']), True, equivalentes=['G2'])])
    config = ImportConfiguration(files=[], import_type=ImportType.MULTI_FILE)
    config.saisies_fiches = {'a': {'ref': ''}, 'c': {'ref': 'P3'}}
    assert ImportDialog._equivalentes_ecartees(dlg, config) == [('P1', ['E2']), ('P3', ['G1'])]
