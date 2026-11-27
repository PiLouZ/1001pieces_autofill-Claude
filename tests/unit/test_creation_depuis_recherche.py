"""Créer l'appareil cherché, et le voir malgré la recherche en cours.

Avant : un appareil cherché par sa référence et absent de la base se créait en
vidant les filtres, Cmd+N, puis en retapant la référence ; et toute ligne
ajoutée pendant une recherche restait invisible (ligne vide hors filtres).

Testé sur une vraie fenêtre principale (base temporaire, style global), dans un
processus à part :
- volet A : sous « Aucun résultat », bouton « Créer l'appareil « réf. » » ; Cmd+N
  (ou le bouton) crée l'appareil avec la référence et la marque filtrées, une
  sauvegarde, un seul Cmd+Z ;
- volet B : la ligne créée est épinglée en tête quel que soit le tri, les ajouts
  suivants s'empilent, un changement de filtre les oublie.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from src.utils.filtre_colonne import valeur_litterale

RACINE = Path(__file__).resolve().parents[2]

_SCRIPT = r"""
import json, os, sqlite3, sys, tempfile
sys.path.insert(0, os.getcwd())
from src.core.config import Config
Config.DB_FILE = tempfile.mktemp(suffix='.db')
from src.data.database_manager import DatabaseManager
base = DatabaseManager(Config.DB_FILE)
cnx = sqlite3.connect(Config.DB_FILE)
cnx.executemany("INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) VALUES (?,?,?,?)",
                [('Four', 'Bosch', 'HBA123', ''), ('Four', 'Siemens', 'HBA456', ''),
                 ('Hotte', 'Elica', 'EL9', '')])
cnx.commit(); cnx.close()
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
app = QApplication(sys.argv)
from src.ui.style_manager import StyleManager
app.setStyleSheet(StyleManager.get_modern_style())
from src.ui.main_refactored import MainWindow
fen = MainWindow()
fen.show()
for _ in range(40):
    app.processEvents()
tc = fen.table_controller
model = tc.model
res = {}

def attendre(n=5):
    for _ in range(n):
        app.processEvents()

def filtrer(valeurs):
    for col, widget in tc.filter_widgets.items():
        if widget is None:
            continue
        texte = valeurs.get(col, '')
        widget.blockSignals(True)
        if hasattr(widget, 'setEditText'):
            widget.setEditText(texte)
        else:
            widget.setText(texte)
        widget.blockSignals(False)
    tc.column_filter_timer.stop()
    tc.load_data(tc.current_search_term)
    attendre()

def ids_affiches():
    return [model.get_db_id(r) for r in range(model.rowCount())]

def en_base(i):
    cnx = sqlite3.connect(Config.DB_FILE)
    ligne = cnx.execute("SELECT type, manufacturer, ref_modele FROM appareils WHERE id=?", (i,)).fetchone()
    cnx.close()
    return [v or '' for v in ligne]

# 1. Référence absente + marque filtrée en minuscules : bouton proposé
filtrer({1: 'bosch', 2: 'A694645.00'})
res['vide'] = ids_affiches()
res['bouton'] = fen.table.action_si_vide()

# 2. Clic sur le bouton (= Cmd+N) : appareil prérempli, épinglé, curseur sur Type
fen.table._sur_bouton_vide()
attendre()
nouveau = ids_affiches()[0] if ids_affiches() else None
res['apres_creation'] = len(ids_affiches())
res['en_base'] = en_base(nouveau)
res['table'] = [model.data(model.index(0, c)) for c in (0, 1, 2)]
res['epingle'] = model.est_epingle(nouveau)
idx = fen.table.currentIndex()
res['curseur'] = [idx.row(), idx.column()]
res['bouton_apres'] = fen.table.action_si_vide()

# 3. Un seul Cmd+Z défait le préremplissage (la ligne reste là, épinglée)
fen._undo()
attendre(3)
res['apres_annulation'] = en_base(nouveau)
res['toujours_affiche'] = nouveau in ids_affiches()
fen._redo()
attendre(3)

# 4. Second Cmd+N dans la même recherche : vide (le tableau n'était plus vide),
#    épinglé au-dessus du premier
fen._add_new_row()
attendre()
second = ids_affiches()[0]
res['empiles'] = [ids_affiches() == [second, nouveau], en_base(second)]

# 5. Autre filtre : les épinglés sont oubliés
filtrer({2: 'HBA'})
res['autre_filtre'] = sorted(model.data(model.index(r, 2)) for r in range(model.rowCount()))

# 6. Sans filtre, tri Type décroissant : la ligne ajoutée est en tête quand même
filtrer({})
tc.current_sort_column = 0
tc.current_sort_order = Qt.DescendingOrder
tc.load_data(tc.current_search_term)
attendre()
fen._add_new_row()
attendre()
troisieme = max(ids_affiches())
res['tri'] = [ids_affiches()[0] == troisieme, en_base(troisieme)]
# 7. Recherche par pièce + filtre qui vide le tableau : pas de bouton « Créer »,
#    les filtres actifs sont rappelés sous le message
tc.current_search_term = None
filtrer({2: 'ZZ999'})
res['filtre_seul'] = [len(ids_affiches()), fen.table.action_si_vide(),
                      getattr(fen.table, '_filtres_vide', '')]
for col, widget in tc.filter_widgets.items():
    if widget is not None:
        widget.blockSignals(True)
        (widget.setEditText if hasattr(widget, 'setEditText') else widget.setText)('ZZ999' if col == 2 else '')
        widget.blockSignals(False)
tc.load_data('HBA123', is_search=True)
attendre()
res['piece_filtre'] = [len(ids_affiches()), fen.table.action_si_vide(),
                       getattr(fen.table, '_filtres_vide', '')]
# 8. Pièce + filtre sur une référence qui EXISTE (HBA456, casse différente) :
#    pas de bouton, même si la pièce cherchée vide le tableau
for col, widget in tc.filter_widgets.items():
    if widget is not None:
        widget.blockSignals(True)
        (widget.setEditText if hasattr(widget, 'setEditText') else widget.setText)('hba456' if col == 2 else '')
        widget.blockSignals(False)
tc.load_data('HBA123', is_search=True)
attendre()
res['piece_filtre_existant'] = [len(ids_affiches()), fen.table.action_si_vide()]
print('RESULTAT ' + json.dumps(res), flush=True)
os._exit(0)
"""


def _executer():
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    sortie = subprocess.run([sys.executable, '-c', _SCRIPT], capture_output=True,
                            text=True, timeout=180, env=env, cwd=str(RACINE))
    ligne = [l for l in sortie.stdout.splitlines() if l.startswith('RESULTAT ')]
    assert ligne, sortie.stderr[-3000:]
    return json.loads(ligne[0][len('RESULTAT '):])


def test_creer_l_appareil_cherche_et_le_voir():
    res = _executer()
    assert res['vide'] == []
    assert res['bouton'] == "Créer l'appareil « A694645.00 »"
    # Référence et marque reprises (marque sous l'orthographe de la base)
    assert res['apres_creation'] == 1
    assert res['en_base'] == ['', 'Bosch', 'A694645.00']
    assert res['table'] == ['', 'Bosch', 'A694645.00']
    assert res['epingle'] is True
    assert res['curseur'] == [0, 0]          # Type, première cellule vide
    assert res['bouton_apres'] is None
    assert res['apres_annulation'] == ['', '', '']
    assert res['toujours_affiche'] is True
    assert res['empiles'] == [True, ['', '', '']]
    assert res['autre_filtre'] == ['HBA123', 'HBA456']
    assert res['tri'] == [True, ['', '', '']]
    # Filtre seul : bouton toujours proposé (non-régression), pas de rappel de filtres
    assert res['filtre_seul'] == [0, "Créer l'appareil « ZZ999 »", '']
    # Pièce + filtre sur une référence absente : bouton proposé, filtres rappelés
    assert res['piece_filtre'] == [0, "Créer l'appareil « ZZ999 »", 'Référence modèle = ZZ999']
    # Pièce + filtre sur une référence qui existe : pas de bouton trompeur
    assert res['piece_filtre_existant'] == [0, None]


def test_valeur_litterale():
    assert valeur_litterale('A694645.00') == 'A694645.00'
    assert valeur_litterale('  WAE 100 ') == 'WAE 100'
    for motif in ('', 'HBA*', 'HB?', 'A | B', '!WAE', 'WAE !WAE1', '|'):
        assert valeur_litterale(motif) is None, motif
