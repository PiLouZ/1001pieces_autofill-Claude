"""
Traçabilité des auto-complétions (v3.89.0)

- la table `appareils_autocompletes` et ses déclencheurs : une trace disparaît
  quand le champ change ou que l'appareil est supprimé, pas sur un alignement de
  casse ;
- la fenêtre « Auto-complétés à vérifier » : tri du moins sûr au plus sûr,
  décisions remises au callback ;
- le lien et la ligne de l'entrée d'historique d'import.
"""

import os
import tempfile
import types

import pytest
from PyQt5.QtCore import Qt

from src.core.config import Config
from src.core.constants import UIConfig
from src.data.database_manager import DatabaseManager
from src.ui.autocompletion_review_dialog import (
    AutocompletionReviewDialog, regrouper_traces, confiance, categorie, COL_TYPE, COL_MFR,
)
from src.ui.fenetre_revue import VALIDE, REFUSE, ATTENTE, entree
from src.ui.main_refactored import MainWindow

TS = '2026-10-16 08:00:00'


@pytest.fixture
def db():
    chemin = tempfile.mktemp(suffix='.db')
    origine = Config.DB_FILE
    Config.DB_FILE = chemin
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        conn.executemany(
            "INSERT INTO appareils (id, type, manufacturer, ref_modele, commercial_ref, "
            "other_ref, notes, category) VALUES (?, ?, ?, ?, ?, '', '', '')",
            [(1, 'Four', 'Bosch', 'A1', 'C1'), (2, 'Hotte', 'Elica', 'A2', 'C2')])
        conn.commit()
        manager.enregistrer_autocompletions([
            (1, 'type', 'Four', 'S1', 2, 3, TS), (1, 'manufacturer', 'Bosch', 'S1', 3, 3, TS),
            (2, 'type', 'Hotte', 'S2', None, None, TS),
        ])
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _traces(db):
    return db.execute_query(
        "SELECT appareil_id, champ FROM appareils_autocompletes ORDER BY 1, 2")


# ─── Base ────────────────────────────────────────────────────────────────────

def test_lecture_et_comptage(db):
    assert db.compter_autocompletions_a_verifier() == 2
    lignes = db.lire_autocompletions_a_verifier()
    assert lignes[0] == (1, 'A1', 'C1', 'Four', 'Bosch', 'manufacturer', 'Bosch', 'S1', 3, 3, TS)


def test_modifier_le_champ_retire_sa_trace(db):
    db.execute_query("UPDATE appareils SET type = 'Cuisinière' WHERE id = 1")
    assert [tuple(t) for t in _traces(db)] == [(1, 'manufacturer'), (2, 'type')]


def test_alignement_de_casse_garde_la_trace(db):
    db.execute_query("UPDATE appareils SET manufacturer = 'BOSCH' WHERE id = 1")
    assert (1, 'manufacturer') in [tuple(t) for t in _traces(db)]


def test_reecrire_la_meme_valeur_garde_la_trace(db):
    db.execute_query("UPDATE appareils SET type = 'Four' WHERE id = 1")
    assert len(_traces(db)) == 3


def test_supprimer_l_appareil_retire_ses_traces(db):
    db.execute_query("DELETE FROM appareils WHERE id = 1")
    assert [tuple(t) for t in _traces(db)] == [(2, 'type')]


def test_marquer_verifies(db):
    assert db.marquer_autocompletions_verifiees([1, 1]) == 2
    assert db.compter_autocompletions_a_verifier() == 1


def test_schema_idempotent(db):
    """Deuxième ouverture de la même base : ni erreur ni doublon de déclencheur."""
    db._setup_autocompletion_trace_table()
    noms = db.execute_query(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'trg_autocompletes%'")
    assert len(noms) == 3


# ─── Fenêtre ─────────────────────────────────────────────────────────────────

def _entrees(db):
    return regrouper_traces(db.lire_autocompletions_a_verifier())


def test_regroupement_et_tri(db):
    entrees = _entrees(db)
    # Confiance inconnue (cache du batch) d'abord, puis le champ le moins sûr décide
    assert [e['id'] for e in entrees] == [2, 1]
    assert confiance(entrees[1]) == (2, 3)
    assert set(entrees[1]['champs']) == {'type', 'manufacturer'}


def test_tri_une_source_avant_unanimite():
    def entree(i, accord, total):
        return (i, f'R{i}', '', 'Four', 'Bosch', 'type', 'Four', 'S', accord, total, TS)
    ordre = [e['id'] for e in regrouper_traces(
        [entree(1, 12, 12), entree(2, 1, 1), entree(3, 1, 2)])]
    assert ordre == [3, 2, 1]


def _fenetre(entrees, **kw):
    """Fenêtre à plat (sans regroupement) : l'ordre d'ouverture se lit directement."""
    fenetre = AutocompletionReviewDialog(None, entrees, **kw)
    fenetre._combo_groupe.setCurrentIndex(3)
    return fenetre


def _item(fenetre, appareil_id):
    return next(it for it in fenetre._feuilles if entree(it)['id'] == appareil_id)


def test_decisions_remises_au_callback(qapp, db):
    recus = []
    choix = iter(['Cuisinière'])
    fenetre = _fenetre(_entrees(db), on_validate=lambda v, c: recus.append((v, c)),
                       value_picker=lambda champ, actuel, cands: next(choix))
    item_four = _item(fenetre, 1)
    fenetre._on_double_clic(item_four, COL_TYPE)       # corrige et valide
    assert fenetre.etat(item_four) == VALIDE
    assert fenetre.etat(_item(fenetre, 2)) == VALIDE    # validé d'office
    fenetre._on_appliquer()
    assert recus == [([2, 1], [(1, {'type': 'Cuisinière'})])]


def test_tout_valide_par_defaut(qapp, db):
    """Une auto-complétion est présumée juste : tout est validé à l'ouverture."""
    recus = []
    fenetre = _fenetre(_entrees(db), on_validate=lambda v, c: recus.append((v, c)))
    assert all(fenetre.etat(it) == VALIDE for it in fenetre._feuilles)
    assert fenetre._btn_appliquer.text() == "Appliquer (2)"
    fenetre._on_appliquer()
    assert recus == [([2, 1], [])]


def test_rien_decide_rien_remis(qapp, db):
    recus = []
    fenetre = _fenetre(_entrees(db), on_validate=lambda v, c: recus.append(1),
                       on_refuse=lambda r: recus.append(2))
    fenetre.decider(ATTENTE, list(fenetre._feuilles))
    fenetre._on_appliquer()
    assert recus == []


def test_refus_remis_avec_les_valeurs_auto_completees(qapp, db):
    """Refuser = vider les champs que l'import a écrits (ceux qui ont encore sa valeur)."""
    recus = {}
    fenetre = _fenetre(_entrees(db), on_validate=lambda v, c: recus.setdefault('v', (v, c)),
                       on_refuse=lambda r: recus.setdefault('r', r))
    fenetre.decider(REFUSE, [_item(fenetre, 1)])
    fenetre._on_appliquer()
    assert recus['v'] == ([2], [])
    assert recus['r'] == [(1, {'type': 'Four', 'manufacturer': 'Bosch'})]


def test_refus_ignore_un_champ_deja_modifie():
    lignes = [(1, 'R1', '', 'Hotte', 'Bosch', 'type', 'Four', 'S', 1, 1, TS),
              (1, 'R1', '', 'Hotte', 'Bosch', 'manufacturer', 'Bosch', 'S', 1, 1, TS)]
    fenetre = _fenetre(regrouper_traces(lignes), on_validate=None)
    assert fenetre.collecter_refus(fenetre._feuilles) == [(1, {'manufacturer': 'Bosch'})]


def test_regroupement_par_import_et_puces(qapp):
    def ligne(i, accord, total, ts):
        return (i, f'R{i}', '', 'Four', 'Bosch', 'type', 'Four', 'S', accord, total, ts)
    entrees = regrouper_traces([ligne(1, 3, 3, '2026-10-16 08:00:00'),
                                ligne(2, 1, 1, '2026-10-22 11:00:00'),
                                ligne(3, None, None, '2026-10-22 11:00:00')])
    assert [categorie(e) for e in entrees] == ['inconnue', 'unique', 'unanime']
    fenetre = AutocompletionReviewDialog(None, entrees, on_validate=None)
    racine = fenetre._arbre.invisibleRootItem()
    assert [racine.child(i).text(0) for i in range(racine.childCount())] == [
        "Import du 22/10/2026 11:00 — 2", "Import du 16/10/2026 08:00 — 1"]
    assert fenetre._boutons_puces['unique'].text() == "Source unique  1"
    fenetre._choisir_puce('inconnue')
    assert [entree(it)['id'] for it in fenetre._feuilles if not it.isHidden()] == [3]


def test_detail_confronte_la_valeur_aux_pieces(qapp, db):
    fenetre = _fenetre(_entrees(db), on_validate=None, preuves=lambda e: {
        'nb_pieces': 4, 'paires': [('Four', 'Siemens', 9), ('Four', 'Bosch', 1)]})
    fenetre._arbre.setCurrentItem(_item(fenetre, 1))
    texte = fenetre._detail.toPlainText()
    assert "Confirment le type" in texte and "Contredisent la marque" in texte
    assert "d'après S1" in texte


# ─── Historique d'import ─────────────────────────────────────────────────────

def test_lien_et_ligne_dans_l_historique():
    historique = []
    fenetre = types.SimpleNamespace(
        user_interaction_service=types.SimpleNamespace(
            add_to_history=lambda s, duration_ms=None, lien=None: historique.append((s, lien))),
        _lignes_alignements=MainWindow._lignes_alignements)
    MainWindow._safe_show_import_results_new(fenetre, {
        'total_files': 1, 'file_details': [{'filename': 'Collage', 'type': 'CSV', 'lines_processed': 3}],
        'autocompletes_a_verifier': 3,
    })
    texte, lien = historique[0]
    assert "     ==> Auto-complétés à vérifier : 3" in texte.splitlines()
    assert lien == (UIConfig.LIEN_HISTORIQUE_AUTOCOMPLETES, "Vérifier les 3 appareils auto-complétés")


def test_sans_autocompletion_appel_inchange():
    """Rien à vérifier : add_to_history est appelé sans `lien`, comme avant."""
    assert MainWindow._lien_autocompletes({'total_files': 1}) == {}


# ─── Tableau principal : italique, infobulle, oubli à la modification ───────

def _modele():
    from src.data.appareils_table_model import AppareillsTableModel
    modele = AppareillsTableModel()
    modele.load_records([(1, 'Four', 'Bosch', 'A1', 'C1', '', '', '', 0),
                         (2, 'Hotte', 'Elica', 'A2', 'C2', '', '', '', 0)])
    modele.set_autocompletes({1: {'type': ('S1', 2, 3), 'manufacturer': ('S1', 3, 3)}})
    return modele


def test_italique_et_infobulle_des_seules_cellules_auto_completees(qapp):
    modele = _modele()
    assert modele.data(modele.index(0, 0), Qt.FontRole).italic()
    assert modele.data(modele.index(0, 1), Qt.FontRole).italic()
    assert modele.data(modele.index(0, 2), Qt.FontRole) is None     # réf. modèle
    assert modele.data(modele.index(1, 0), Qt.FontRole) is None     # autre appareil
    assert "d'après S1 (2/3)" in modele.data(modele.index(0, 0), Qt.ToolTipRole)
    assert modele.ids_autocompletes([1, 2]) == [1]


def test_modifier_la_cellule_retire_l_italique(qapp):
    modele = _modele()
    modele.setData(modele.index(0, 0), 'Cuisinière')
    assert modele.data(modele.index(0, 0), Qt.FontRole) is None
    assert modele.data(modele.index(0, 1), Qt.FontRole).italic()
    modele.set_field_value(0, 1, 'Siemens')
    assert modele.ids_autocompletes([1]) == []


def test_changer_la_casse_garde_l_italique(qapp):
    modele = _modele()
    modele.setData(modele.index(0, 1), 'BOSCH')
    assert modele.data(modele.index(0, 1), Qt.FontRole).italic()


# ─── Repérage visuel : fond, numéro de ligne, coche cliquable ───────────────

def test_fond_lavande_des_seules_cellules_auto_completees(qapp):
    from src.data.appareils_table_model import _AUTOCOMPLETE_BG
    modele = _modele()
    assert modele.data(modele.index(0, 0), Qt.BackgroundRole).color() == _AUTOCOMPLETE_BG
    assert modele.data(modele.index(0, 2), Qt.BackgroundRole) is None
    assert modele.data(modele.index(1, 0), Qt.BackgroundRole) is None


def test_suggestion_garde_son_fond_jaune(qapp):
    from src.data.appareils_table_model import _SUGGESTION_BG
    modele = _modele()
    modele._pending_suggestions = {1: [{'type': 'Four', 'manufacturer': 'Bosch'}]}
    assert modele.data(modele.index(0, 0), Qt.BackgroundRole).color() == _SUGGESTION_BG


def test_numero_de_ligne_signale_la_ligne_a_verifier(qapp):
    modele = _modele()
    assert modele.ligne_a_verifier(0) and not modele.ligne_a_verifier(1)
    assert not modele.ligne_a_verifier(99)
    assert "à vérifier" in modele.headerData(0, Qt.Vertical, Qt.ToolTipRole)
    assert modele.headerData(1, Qt.Vertical, Qt.ToolTipRole) is None
    assert modele.headerData(0, Qt.Vertical, Qt.DisplayRole) == '1'


def test_numero_rafraichi_quand_la_ligne_n_est_plus_a_verifier(qapp):
    modele = _modele()
    recus = []
    modele.headerDataChanged.connect(lambda o, a, b: recus.append((o, a, b)))
    modele.setData(modele.index(0, 0), 'Cuisinière')
    assert recus == []                               # Fabricant reste à vérifier
    modele.setData(modele.index(0, 1), 'Siemens')
    assert recus == [(Qt.Vertical, 0, 0)] and not modele.ligne_a_verifier(0)
    modele.set_autocompletes({2: {'type': ('S', 1, 1)}})
    assert (Qt.Vertical, 1, 1) in recus


def test_en_tete_de_lignes_garde_le_clic_de_selection(qapp):
    from src.ui.custom_table_view import CustomTableView, _EnteteLignes
    vue = CustomTableView()
    entete = vue.verticalHeader()
    assert isinstance(entete, _EnteteLignes)
    assert entete.sectionsClickable() and entete.highlightSections()


def test_en_tete_de_lignes_dessine_le_repere(qapp):
    from PyQt5.QtGui import QColor
    from src.ui.custom_table_view import CustomTableView, _EnteteLignes
    vue = CustomTableView()
    vue.setModel(_modele())
    vue.resize(400, 200)
    vue.show()
    qapp.processEvents()
    image = vue.verticalHeader().viewport().grab().toImage()
    haut = vue.verticalHeader().sectionSize(0)
    assert QColor(image.pixel(1, haut // 2)) == _EnteteLignes._ORANGE           # ligne 1
    assert QColor(image.pixel(1, haut + haut // 2)) != _EnteteLignes._ORANGE    # ligne 2
    vue.close()


def _clic(position):
    from PyQt5.QtCore import QEvent, QPointF
    from PyQt5.QtGui import QMouseEvent
    return QMouseEvent(QEvent.MouseButtonRelease, QPointF(position), Qt.LeftButton,
                       Qt.LeftButton, Qt.NoModifier)


def test_coche_cliquable_marque_verifie(qapp):
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QStyleOptionViewItem
    from src.data.appareils_table_model import SuggestionCellDelegate
    modele = _modele()
    delegue = SuggestionCellDelegate()
    clics = []
    delegue.verify_handler = lambda index: clics.append((index.row(), index.column()))
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 140, 26)
    sur_icone = delegue._icon_rect(option.rect).center()
    assert delegue.editorEvent(_clic(sur_icone), modele, option, modele.index(0, 1))
    assert clics == [(0, 1)]
    # Ailleurs dans la case, ou sur une cellule non auto-complétée : rien.
    delegue.editorEvent(_clic(option.rect.topLeft()), modele, option, modele.index(0, 1))
    delegue.editorEvent(_clic(sur_icone), modele, option, modele.index(1, 0))
    assert clics == [(0, 1)]
    # Une suggestion en attente garde la priorité (baguette, pas de coche).
    modele._pending_suggestions = {1: [{'type': 'Four', 'manufacturer': 'Bosch'}]}
    acceptees = []
    delegue.accept_handler = lambda index, s: acceptees.append(index.row())
    delegue.editorEvent(_clic(sur_icone), modele, option, modele.index(0, 0))
    assert clics == [(0, 1)] and acceptees == [0]


def test_coche_relayee_vers_marquer_verifie(qapp):
    from src.ui.table_controller import TableController
    appels = []
    faux = types.SimpleNamespace(
        model=_modele(),
        parent_window=types.SimpleNamespace(
            _marquer_lignes_verifiees=lambda ids, origine: appels.append((ids, origine))))
    TableController._on_verify_icon_clicked(faux, faux.model.index(0, 0))
    assert appels == [([1], "clic sur la coche")]


# ─── Tri par colonne des deux fenêtres ──────────────────────────────────────

def _ordre(arbre, col):
    return [arbre.topLevelItem(i).text(col) for i in range(arbre.topLevelItemCount())]


def test_tri_par_colonne_fenetre_autocompletes(qapp):
    def ligne(i, ref, accord, total, ts):
        return (i, ref, '', 'Four', 'Bosch', 'type', 'Four', 'S', accord, total, ts)
    fenetre = AutocompletionReviewDialog(None, regrouper_traces([
        ligne(1, 'B', 12, 12, '2026-10-01 10:00:00'), ligne(2, 'A', 1, 2, '2026-10-16 08:00:00'),
        ligne(3, 'C', 1, 1, '2026-10-10 09:00:00')]), on_validate=None)
    fenetre._combo_groupe.setCurrentIndex(3)             # à plat
    arbre = fenetre._arbre
    assert _ordre(arbre, 1) == ['A', 'C', 'B']           # ordre d'ouverture conservé
    arbre.sortByColumn(1, Qt.DescendingOrder)
    assert _ordre(arbre, 1) == ['C', 'B', 'A']
    arbre.sortByColumn(4, Qt.DescendingOrder)            # confiance : 12/12 > 1/1 > 1/2
    assert _ordre(arbre, 4) == ['12/12', '1/1', '1/2']
    arbre.sortByColumn(6, Qt.AscendingOrder)             # date réelle, pas le texte jj/mm
    assert _ordre(arbre, 1) == ['B', 'C', 'A']


def test_tri_par_colonne_fenetre_suggestions(qapp):
    from src.ui.suggestion_validation_dialog import SuggestionValidationDialog, COL_PREUVE, COL_REF
    def entree_(i, ref, score):
        return {'db_id': i, 'ref_modele': ref, 'commercial_ref': '', 'candidates': [
            {'type': 'Four', 'manufacturer': 'Bosch', 'score': score, 'ref': 'X',
             'confidence_tier': 'B_fuzzy_alpha'}]}
    fenetre = SuggestionValidationDialog(
        None, [entree_(1, 'R1', 0.92), entree_(2, 'R2', 1.0), entree_(3, 'R3', 0.87)], on_validate=None)
    fenetre._combo_groupe.setCurrentIndex(3)             # à plat
    arbre = fenetre._arbre
    arbre.sortByColumn(COL_PREUVE, Qt.AscendingOrder)    # preuve la plus forte d'abord
    assert _ordre(arbre, COL_REF) == ['R2', 'R1', 'R3']
    fenetre._combo_groupe.setCurrentIndex(1)             # regrouper : le tri survit
    fenetre._combo_groupe.setCurrentIndex(3)
    assert arbre.sortColumn() == COL_PREUVE


# ─── « Tout valider » (v3.89.2) ─────────────────────────────────────────────

def test_repartition_par_niveau_de_confiance():
    def ligne(i, accord, total):
        return (i, f'R{i}', '', 'Four', 'Bosch', 'type', 'Four', 'S', accord, total, TS)
    entrees = regrouper_traces([ligne(1, 3, 3), ligne(2, 5, 5), ligne(3, 1, 1),
                                ligne(4, 1, 2), ligne(5, None, None)])
    assert MainWindow._repartition_confiance(entrees) == {
        'unanimes': 2, 'source_unique': 1, 'partagees': 1, 'inconnues': 1}

