"""
Retour vers le site et EveryParts (CDC import fiches site, § 8, étape 5)

Fiche complète :
- paire dans le code produit ({reference} = la pièce puis la 2ᵉ réf. du code
  produit mémorisée, ligne 0) ; ses anciennes références rejoignent « Remplace » ;
- une ligne « Références équivalentes » par marque d'origine, puis par ligne
  mémorisée ; sans mémoire, une seule ligne comme avant ;
- références écartées absentes ;
- aller-retour sur les 3 fiches d'exemple : enregistrer, régénérer, relire →
  rien de nouveau.

Export EveryParts :
- référence interne du produit de la pièce proposée (pièce courante de la
  lignée pour une ancienne référence) ; choix si plusieurs produits ; rien sinon ;
- variables {ref_interne} et {id_product} dans les colonnes et le nom du fichier ;
  format par défaut inchangé.

Base construite ou extrait de la vraie base ; aucun réseau ; aucun réglage ni
data/reprise_fiches.json du poste écrit.
"""

import copy
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.data.database_manager import DatabaseManager
from src.services.enregistrement_fiche_service import EnregistrementFicheService
from src.services.export_config_service import (
    DEFAULT_CONFIG, ExportConfigService, format_csv_filename, render_csv_row_with,
)
from src.services.html_export_service import HtmlExportService
from src.ui.fiche_produit_service import FicheProduitService
from src.utils.fiche_produit_generator import FicheProduitGenerator
from src.utils.rapprochement_fiche import ConfigurationRapprochement
from src.utils.rapprochement_fiche.decisions import (
    ChoixAppareil, DecisionsFiche, categorie_appareil, planifier,
)

RACINE = Path(__file__).resolve().parents[2]
FIXTURES = RACINE / 'tests' / 'fixtures' / 'fiches_site'
STANDARD = DEFAULT_CONFIG['fiche']['profiles'][0]


# =============================================================================
# Outils
# =============================================================================

def _db_extrait(tmp_path) -> DatabaseManager:
    chemin = tmp_path / 'extrait.db'
    cnx = sqlite3.connect(chemin)
    cnx.executescript((FIXTURES / 'base_extrait.sql').read_text(encoding='utf-8'))
    cnx.close()
    return DatabaseManager(str(chemin))


def _enregistreur(db):
    return EnregistrementFicheService(db, configuration=ConfigurationRapprochement())


def _decisions(r, ecartees=()):
    d = DecisionsFiche()
    for i, a in enumerate(r.appareils):
        if categorie_appareil(a) == 'a_valider' and a.candidats and \
                a.appareil_id is None and a.proposition is None:
            d.appareils[i] = ChoixAppareil(appareil_id=a.candidats[0].id)
    d.ecartees.update(ecartees)
    return d


def _enregistrer_exemples(db):
    for n in (7285, 20746, 20744):
        page = (FIXTURES / f'produit_{n}.html').read_text(encoding='utf-8')
        _, r = _enregistreur(db).analyser_page(page, f'https://www.1001pieces.com/{n}-fiche.html')
        plan = planifier(r, _decisions(r, ecartees={'481949'} if n == 7285 else ()))
        assert plan.pret, (n, plan.en_attente, plan.a_completer)
        assert _enregistreur(db).enregistrer(plan).ok


def _fiche_service(db):
    """FicheProduitService sur une vraie base, sans fenêtre."""
    fenetre = SimpleNamespace(
        db_manager=db,
        seo_service=SimpleNamespace(
            _count_compatible_models=lambda refs: _nb_appareils(db, refs)))
    return FicheProduitService(fenetre)


def _nb_appareils(db, refs):
    q = ','.join('?' * len(refs))
    return db.conn.execute(
        f"SELECT COUNT(DISTINCT pa.appareil_id) FROM piece_associations pa "
        f"JOIN pieces p ON p.id = pa.piece_id WHERE p.ref_piece IN ({q})", list(refs)).fetchone()[0]


def _appareils_affiches(db, refs):
    """Ce qu'afficherait le tableau pour la pièce et sa lignée (bandeaux actifs)."""
    q = ','.join('?' * len(refs))
    return db.conn.execute(
        f"SELECT DISTINCT a.type, a.manufacturer, a.ref_modele, a.commercial_ref, a.other_ref, ? "
        f"FROM appareils a JOIN piece_associations pa ON pa.appareil_id = a.id "
        f"JOIN pieces p ON p.id = pa.piece_id WHERE p.ref_piece IN ({q}) "
        f"ORDER BY a.manufacturer, a.ref_modele", [refs[0], *refs]).fetchall()


def _instantane(db):
    tables = ('appareils', 'pieces', 'piece_associations', 'piece_supersessions',
              'piece_equivalence_groups', 'produits_site', 'decisions_references')
    return {t: db.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


@pytest.fixture
def config_exports(tmp_path, monkeypatch):
    """Configuration des exports par défaut, dans un fichier de test."""
    chemin = tmp_path / 'export_config.json'
    monkeypatch.setattr(ExportConfigService, '_resolve_config_path',
                        staticmethod(lambda: str(chemin)))
    service = ExportConfigService()
    ancien = HtmlExportService._config_service
    HtmlExportService.set_config_service(service)
    yield service
    HtmlExportService.set_config_service(ancien)


def _regenerer(db, reference, titre):
    """Fiche complète de `reference` avec le profil standard (titre de la fiche)."""
    svc = _fiche_service(db)
    refs = svc.references_fiche(reference)
    appareils = _appareils_affiches(db, [reference, *refs['remplace']])
    return FicheProduitGenerator().generer(
        STANDARD, f'<h2 class="class_perso1">{titre}</h2>',
        HtmlExportService.generate_html_brands(appareils), reference,
        refs['remplace'], refs['equivalentes'],
        lambda reste: HtmlExportService.generate_html_details(appareils, char_limit=reste),
        code_produit=refs['code_produit'], lignes_equivalentes=refs['lignes_equivalentes'],
    )['html']


# =============================================================================
# Générateur
# =============================================================================

def _entete(**kw):
    return FicheProduitGenerator().entete(STANDARD, '', '', '481073071153', [], [], **kw)


def test_paire_dans_le_code_produit():
    assert _entete(code_produit=['481073071153', 'C00319033']) == \
        '<div class="class_perso3">Code produit : 481073071153 C00319033</div>'
    # Sans paire : la seule référence, comme avant
    assert _entete() == '<div class="class_perso3">Code produit : 481073071153</div>'


def test_une_ligne_par_liste_d_equivalentes():
    html = _entete(lignes_equivalentes=[['00145522'], ['49025106', '41018990'], []])
    assert html.count('Références équivalentes') == 2
    assert html.endswith(
        '<div class="class_perso3 class_perso6">Références équivalentes : 00145522</div>'
        '<div class="class_perso3 class_perso6">Références équivalentes : 49025106 41018990</div>')


def test_sans_lignes_toutes_les_lignees_sur_une_ligne():
    html = FicheProduitGenerator().entete(STANDARD, '', '', 'R', [], [['A', 'A0'], ['B']])
    assert html.count('Références équivalentes') == 1
    assert 'Références équivalentes : A A0 B</div>' in html


# =============================================================================
# Regroupement par origine
# =============================================================================

def test_lignes_par_origine_puis_par_ligne_memorisee():
    memoire = {'X1': ('BSH', 1), 'X2': ('bsh', 3), 'Y': ('Candy', 2), 'Z': (None, 4),
               'W': (None, None)}
    lignes = FicheProduitService.lignes_par_origine(
        [['W'], ['Z'], ['X2', 'X0'], ['Y'], ['X1']], memoire)
    # BSH (lignes 1 et 3) ensemble au rang 1, Candy 2, ligne 4 sans origine, puis sans mémoire
    assert lignes == [['X2', 'X0', 'X1'], ['Y'], ['Z'], ['W']]


def test_remplace_dans_l_ordre_de_la_fiche_puis_le_reste():
    ordre = FicheProduitService.ordre_de_la_fiche
    assert ordre(['A', 'B', 'C', 'D'], {}) == ['A', 'B', 'C', 'D']         # sans mémoire
    assert ordre(['A', 'B', 'C', 'D'], {'C': 1, 'A': 2}) == ['C', 'A', 'B', 'D']


def test_sans_memoire_remplace_dans_l_ordre_de_la_chaine(tmp_path):
    """Pièce de l'outil (aucune position mémorisée) : ordre actuel inchangé."""
    db = _db_extrait(tmp_path)
    db.add_supersession('ANC2', 'ANC1')
    db.add_supersession('ANC1', '481073071153')
    svc = _fiche_service(db)
    attendu = list(db.get_all_predecessors('481073071153'))
    assert svc.references_fiche('481073071153')['remplace'] == attendu


def test_sans_memoire_une_seule_ligne_dans_l_ordre():
    lignes = FicheProduitService.lignes_par_origine([['B', 'B0'], ['A']], {})
    assert lignes == [['B', 'B0', 'A']]


# =============================================================================
# Fiches d'exemple : régénération et aller-retour
# =============================================================================

class TestFichesExemple:
    def test_7285_paire_une_ligne_bsh_481949_absente(self, tmp_path):
        db = _db_extrait(tmp_path)
        _enregistrer_exemples(db)
        refs = _fiche_service(db).references_fiche('481073071153')
        assert refs['code_produit'] == ['481073071153', 'C00319033']
        # Ordre de la ligne « Remplace » de la fiche (paires Indesit / Whirlpool)
        assert refs['remplace'] == ['C00535957', '488000535957', 'C00309416', '482000032568']
        assert refs['lignes_equivalentes'] == [['00145522']]
        assert '481949' not in str(refs)

    def test_relecture_complete_la_position_des_remplace(self, tmp_path):
        """Fiche reprise avant la mémoire de position : la relecture la complète,
        sans rien ajouter d'autre."""
        db = _db_extrait(tmp_path)
        _enregistrer_exemples(db)
        db.conn.execute("UPDATE piece_supersessions SET rang_fiche = NULL")
        db.conn.commit()
        page = (FIXTURES / 'produit_7285.html').read_text(encoding='utf-8')
        _, r = _enregistreur(db).analyser_page(page, 'https://www.1001pieces.com/7285-fiche.html')
        plan = planifier(r, _decisions(r))
        assert plan.vide and plan.rangs_remplace
        assert _enregistreur(db).enregistrer(plan).ok
        assert db.rangs_remplace(['C00535957', '488000535957', 'C00309416', '482000032568']) == \
            {'C00535957': 1, '488000535957': 2, 'C00309416': 3, '482000032568': 4}

    def test_ecartee_presente_dans_le_groupe_retiree(self, tmp_path):
        db = _db_extrait(tmp_path)
        _enregistrer_exemples(db)
        db.add_equivalence('481073071153', '481949')   # ajoutée à la main malgré tout
        refs = _fiche_service(db).references_fiche('481073071153')
        assert '481949' not in str(refs)

    def test_ecartee_dans_la_chaine_reste_dans_remplace(self, tmp_path):
        """Cas 00648024 : ancienne réf. citée en équivalente par la fiche, retirée du
        champ « Équivalentes » (donc écartée) : elle reste dans « Remplace »."""
        db = _db_extrait(tmp_path)
        _enregistrer_exemples(db)
        db.add_supersession('ANC_ECARTEE', '481073071153')
        db.conn.execute(
            "INSERT INTO decisions_references (ref_piece, reference, nature, origine, forme, "
            "decide_le) VALUES ('481073071153', 'ANC_ECARTEE', 'ecartee', NULL, 'AAA', '')")
        db.conn.commit()
        refs = _fiche_service(db).references_fiche('481073071153')
        assert 'ANC_ECARTEE' in refs['remplace']
        assert refs['remplace'][:4] == ['C00535957', '488000535957', 'C00309416', '482000032568']
        assert '481949' not in str(refs)                 # l'écartée hors chaîne reste absente

    def test_piece_sans_produit_comme_avant(self, tmp_path):
        """La 2ᵉ réf. du code produit cherchée seule : pas de produit, pas de paire."""
        db = _db_extrait(tmp_path)
        _enregistrer_exemples(db)
        refs = _fiche_service(db).references_fiche('C00319033')
        assert refs['code_produit'] == ['C00319033']
        assert ['481073071153', '488000535957', '482000032568'] in refs['lignes_equivalentes']

    def test_les_3_fiches_regenerees_puis_relues_sans_rien_ajouter(self, tmp_path, config_exports):
        db = _db_extrait(tmp_path)
        _enregistrer_exemples(db)
        fiches = {7285: '481073071153', 20746: '1113161010', 20744: '11051894'}
        avant = _instantane(db)
        for n, reference in fiches.items():
            titre = db.conn.execute("SELECT description FROM pieces WHERE ref_piece = ?",
                                    [reference]).fetchone()[0]
            html = _regenerer(db, reference, titre)
            lecture, r = _enregistreur(db).analyser_description(html)
            assert lecture.code_produit[0] == reference, n
            nb = len(_appareils_affiches(db, [reference, *db.get_all_predecessors(reference)]))
            assert len(lecture.appareils) == nb == {20746: 831, 20744: 450}.get(n, nb), n
            if n == 7285:
                assert lecture.code_produit == ['481073071153', 'C00319033']
                assert [l.references for l in lecture.equivalentes] == [['00145522']]
                assert '481949' not in html
            plan = planifier(r, _decisions(r))
            assert plan.vide, (n, plan.resume())
            assert not r.absents_de_la_fiche, n
            res = _enregistreur(db).enregistrer(plan)
            assert res.ok and res.liens_crees == 0 and res.liens_completes == 0, n
        assert _instantane(db) == avant


# =============================================================================
# Aperçu d'export (rendu hors écran)
# =============================================================================

def test_apercu_d_export_de_la_fiche_7285(qapp, tmp_path, config_exports, monkeypatch):
    """La fenêtre d'aperçu montre la fiche régénérée : paire, une ligne BSH."""
    from PyQt5.QtWidgets import QLineEdit
    import src.ui.apercu_export_dialog as module
    db = _db_extrait(tmp_path)
    _enregistrer_exemples(db)
    titre = 'Pompe de vidange R2.5Y'
    fenetre = SimpleNamespace(
        db_manager=db, export_config_service=config_exports,
        seo_service=SimpleNamespace(raison_refus=None,
                                    _count_compatible_models=lambda r: _nb_appareils(db, r)),
        titre_produit_service=SimpleNamespace(
            calculer_titre=lambda d, p: ({'titre': f'<h2 class="class_perso1">{titre}</h2>'}, None)),
        search_input=QLineEdit('481073071153'))
    svc = FicheProduitService(fenetre)

    class Source:
        genre, libelle = 'fiche', "Fiche complète"

        def noms(self):
            return config_exports.get_fiche_profile_names()

        def defaut(self):
            return config_exports.get_default_fiche_profile_name()

        def contexte(self, interactif, relancer=None):
            refs = svc.references_fiche('481073071153')
            appareils = _appareils_affiches(db, ['481073071153', *refs['remplace']])
            return {'donnees': {'reference': '481073071153'}, 'ref_obsolete': None,
                    'reference': '481073071153', 'appareils': appareils,
                    'marques_html': HtmlExportService.generate_html_brands(appareils), **refs}

        def rendre(self, contexte, nom):
            return svc.rendre(contexte, nom)

        def copier(self, contexte, nom):
            pass

    monkeypatch.setitem(module.SOURCES, 'fiche', lambda mw: Source())
    d = module.ApercuExportDialog(fenetre, 'fiche', parent=None)
    code = d.code.toPlainText()
    assert 'Code produit : 481073071153 C00319033' in code
    assert code.count('Références équivalentes') == 1 and 'Références équivalentes : 00145522' in code
    assert '481949' not in code
    d.resize(1100, 700)
    assert not d.grab().isNull()
    sortie = os.environ.get('AUTOFILL_RENDU_DIR')
    if sortie:                          # vérification visuelle à la demande
        d.grab().save(os.path.join(sortie, 'apercu_fiche_7285.png'))
    d.close()


# =============================================================================
# Export EveryParts : référence interne proposée
# =============================================================================

class _DialogueFactice:
    def __init__(self, reponse=None):
        self.appels, self.reponse = [], reponse

    def show_reference_selection_dialog(self, title, message, default_reference, **kw):
        self.appels.append({'defaut': default_reference, 'message': message, **kw})
        return self.reponse if self.reponse is not None else default_reference


def _export_manager(db, config_service, dialogue):
    from src.services.export_manager import ExportManagerService
    fenetre = SimpleNamespace(
        db_manager=db, export_config_service=config_service, dialog_service=dialogue,
        search_service=SimpleNamespace(extract_first_term=lambda t: t.split()[0]))
    return ExportManagerService(fenetre)


@pytest.fixture
def base_exemples(tmp_path):
    db = _db_extrait(tmp_path)
    _enregistrer_exemples(db)
    return db


class TestEveryParts:
    def test_reference_interne_proposee(self, base_exemples, config_exports):
        from src.core.constants import ExportFormat
        dialogue = _DialogueFactice()
        manager = _export_manager(base_exemples, config_exports, dialogue)
        res = manager._handle_single_reference_dialog('1113161010', ExportFormat.CSV)
        assert dialogue.appels[0]['defaut'] == 'EL1113161010'
        assert 'n° 20746' in dialogue.appels[0]['message']
        assert res.reference == 'EL1113161010' and res.produit['id_product'] == 20746

    def test_ancienne_reference_de_la_lignee(self, base_exemples, config_exports):
        from src.core.constants import ExportFormat
        dialogue = _DialogueFactice()
        manager = _export_manager(base_exemples, config_exports, dialogue)
        res = manager._handle_single_reference_dialog('00703010', ExportFormat.CSV)
        assert dialogue.appels[0]['defaut'] == 'GAU11051894'
        assert res.produit['ref_interne'] == 'GAU11051894'

    def test_sans_produit_comportement_actuel(self, base_exemples, config_exports):
        from src.core.constants import ExportFormat
        dialogue = _DialogueFactice()
        manager = _export_manager(base_exemples, config_exports, dialogue)
        res = manager._handle_single_reference_dialog('C00319033', ExportFormat.CSV)
        assert dialogue.appels[0]['defaut'] == 'C00319033'
        assert 'produits' not in dialogue.appels[0] and res.produit is None
        assert dialogue.appels[0]['message'].startswith("Elle apparaîtra")

    def test_export_html_inchange(self, base_exemples, config_exports):
        from src.core.constants import ExportFormat
        dialogue = _DialogueFactice()
        manager = _export_manager(base_exemples, config_exports, dialogue)
        manager._handle_single_reference_dialog('1113161010', ExportFormat.HTML_DETAILS)
        assert dialogue.appels[0]['defaut'] == '1113161010'

    def test_reference_modifiee_garde_le_produit(self, base_exemples, config_exports):
        from src.core.constants import ExportFormat
        manager = _export_manager(base_exemples, config_exports, _DialogueFactice('AUTRE'))
        res = manager._handle_single_reference_dialog('1113161010', ExportFormat.CSV)
        assert res.reference == 'AUTRE' and res.produit['ref_interne'] == 'EL1113161010'

    def test_plusieurs_produits_choix_dans_le_dialogue(self, qapp, base_exemples, config_exports,
                                                      monkeypatch):
        """Vrai dialogue : la liste « Produit du site » remplit le champ et le nom du fichier."""
        from PyQt5.QtWidgets import QComboBox, QDialog, QLineEdit, QLabel
        from src.core.constants import ExportFormat
        from src.services.unified_dialog_service import UnifiedDialogService
        db = base_exemples
        with db._query_lock:
            db._enregistrer_produit_site('GEN481073071153', 30001, '481073071153', None, 'x')
            db.conn.commit()
        config_exports._config['csv']['filename_pattern'] = '{ref_interne}_{id_product}.csv'
        vus = {}

        def exec_(dialog):
            liste = dialog.findChild(QComboBox, 'produits_site')
            champ = dialog.findChild(QLineEdit)
            vus['avant'] = (liste.count(), champ.text())
            liste.setCurrentIndex(1)
            vus['apres'] = champ.text()
            vus['fichier'] = [l.text() for l in dialog.findChildren(QLabel) if l.text().endswith('.csv')]
            dialog.resize(560, 260)
            sortie = os.environ.get('AUTOFILL_RENDU_DIR')
            if sortie:
                dialog.grab().save(os.path.join(sortie, 'dialogue_export_produits.png'))
            return QDialog.Accepted
        monkeypatch.setattr(QDialog, 'exec_', exec_)
        from PyQt5.QtWidgets import QWidget
        parent = QWidget()
        dialogue = UnifiedDialogService(parent)
        manager = _export_manager(db, config_exports, dialogue)
        res = manager._handle_single_reference_dialog('481073071153', ExportFormat.CSV)
        assert vus['avant'] == (2, '481073071153')
        assert vus['apres'] == 'GEN481073071153'
        assert vus['fichier'] == ['GEN481073071153_30001.csv']
        assert res.reference == 'GEN481073071153' and res.produit['id_product'] == 30001


# =============================================================================
# Variables {ref_interne} et {id_product}
# =============================================================================

PRODUIT = {'ref_interne': 'EL1113161010', 'id_product': 20746}
RECORD = ('Lave-linge', 'Electrolux', '914', 'EWF', '', '1113161010')


def test_variables_dans_les_colonnes():
    colonnes = [{'header': 'product', 'source': '{export_ref}'},
                {'header': 'interne', 'source': '{ref_interne}'},
                {'header': 'id', 'source': '{id_product}'}]
    assert render_csv_row_with(colonnes, RECORD, 'X', PRODUIT) == ['X', 'EL1113161010', '20746']
    assert render_csv_row_with(colonnes, RECORD, 'X') == ['X', '', '']


def test_variables_dans_le_nom_du_fichier():
    assert format_csv_filename('{ref_interne}_{id_product}.csv', 'X', produit=PRODUIT) == \
        'EL1113161010_20746.csv'
    assert format_csv_filename('{export_ref}_everyParts.csv', 'X', produit=PRODUIT) == \
        'X_everyParts.csv'


def test_format_par_defaut_inchange():
    csv_defaut = DEFAULT_CONFIG['csv']
    assert csv_defaut['filename_pattern'] == '{export_ref}_everyParts.csv'
    assert csv_defaut['columns'][0] == {'header': 'product', 'source': '{export_ref}'}
    assert not any('ref_interne' in c['source'] or 'id_product' in c['source']
                   for c in csv_defaut['columns'])


def test_csv_ecrit_avec_le_produit(tmp_path, config_exports):
    import csv
    from src.services.export_manager import ExportManagerService
    config_exports._config['output_dir'] = str(tmp_path)
    config_exports._config['csv']['filename_pattern'] = '{ref_interne}.csv'
    config_exports._config['csv']['columns'] = [{'header': 'product', 'source': '{export_ref}'},
                                                {'header': 'id', 'source': '{id_product}'}]
    manager = ExportManagerService(SimpleNamespace(export_config_service=config_exports))
    manager._add_to_history = lambda *a, **k: None
    assert manager._execute_csv_export([RECORD], 'EL1113161010', produit=PRODUIT)
    with open(tmp_path / 'EL1113161010.csv', encoding=config_exports.get_csv_encoding()) as f:
        lignes = list(csv.reader(f, delimiter=config_exports.get_csv_separator()))
    assert lignes == [['product', 'id'], ['EL1113161010', '20746']]
