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
    AutocompletionReviewDialog, regrouper_traces, confiance, COL_CHECK, COL_TYPE,
)
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


def test_decisions_remises_au_callback(qapp, db):
    recus = []
    choix = iter(['Cuisinière'])
    fenetre = AutocompletionReviewDialog(
        None, _entrees(db), on_validate=lambda v, c: recus.append((v, c)),
        value_picker=lambda champ, actuel, cands: next(choix))
    item_four = fenetre._items[1]
    fenetre._on_item_double_clicked(item_four, COL_TYPE)   # corrige et coche
    assert item_four.checkState(COL_CHECK) == Qt.Checked
    fenetre._items[0].setCheckState(COL_CHECK, Qt.Checked)  # vérifié sans correction
    fenetre._on_validate_clicked()
    assert recus == [([2, 1], [(1, {'type': 'Cuisinière'})])]


def test_rien_coche_rien_remis(qapp, db):
    recus = []
    fenetre = AutocompletionReviewDialog(None, _entrees(db), on_validate=lambda v, c: recus.append(1))
    fenetre._on_validate_clicked()
    assert recus == []


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
