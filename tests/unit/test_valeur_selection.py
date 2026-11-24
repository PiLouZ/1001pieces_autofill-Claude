"""Une valeur Type / Fabricant pour toute une sélection (Cmd+D sur plusieurs lignes).

Mesure du 2026-11-24 (CDC nomenclature § 8.4, D23) : les 40 669 appareils importés
sans type ni marque depuis juillet ont été complétés à la main en ≈ 10 400 gestes,
surtout à la poignée de remplissage ; Cmd+D n'écrivait que la cellule courante.

Testé sur une vraie fenêtre principale (base temporaire, style global), dans un
processus à part : écriture sur les seules lignes sélectionnées, casse alignée
sur la base, une sauvegarde, historique ligne par ligne, un seul Cmd+Z.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

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
                [('', '', f'SEL{i:02d}', '') for i in range(6)]
                + [('Hotte', 'Delta', 'REFDELTA', ''), ('Four', 'Bosch', 'AUTRE', '')])
cnx.commit(); cnx.close()
from PyQt5.QtCore import Qt, QItemSelection, QItemSelectionModel
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
model = fen.table_controller.model
lignes = {model.data(model.index(r, 2)): r for r in range(model.rowCount())}
res = {'nb_lignes_table': model.rowCount()}

appels = []
def factice(table, item, col, prefill="", suggestions=None, sur_resultat=None, nb_lignes=0):
    appels.append({'col': col, 'nb_lignes': nb_lignes})
    sur_resultat(VALEUR[0])
fen.autocompletion_service.show_column_values_dialog = factice

def selectionner(refs, col):
    vue = fen.table
    sel = QItemSelection()
    for ref in refs:
        idx = model.index(lignes[ref], col)
        sel.select(idx, idx)
    vue.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect)
    vue.selectionModel().setCurrentIndex(model.index(lignes[refs[0]], col), QItemSelectionModel.NoUpdate)

def en_base():
    cnx = sqlite3.connect(Config.DB_FILE)
    out = {r: (t or '', m or '') for r, t, m in cnx.execute(
        "SELECT ref_modele, type, manufacturer FROM appareils")}
    cnx.close()
    return out

# 1. Quatre lignes sur six, colonne Fabricant, saisie en capitales
VALEUR = ['DELTA']

selectionner(['SEL00', 'SEL01', 'SEL03', 'SEL04'], 1)
fen._show_column_values_list()
for _ in range(5): app.processEvents()
b = en_base()
res['appel'] = appels[-1]
res['marques'] = {r: b[r][1] for r in ('SEL00', 'SEL01', 'SEL02', 'SEL03', 'SEL04', 'SEL05')}
res['table'] = {r: model.data(model.index(lignes[r], 1)) for r in ('SEL00', 'SEL02')}
attente = fen.grouped_history_service.pending_modifications
res['historique'] = sorted(m for d in attente.values() for m in d['modifications'])
fen.grouped_history_service.flush_all_pending_modifications()

# 2. Un seul Cmd+Z défait les quatre ; Cmd+Maj+Z les rétablit
fen._undo()
for _ in range(3): app.processEvents()
b = en_base()
res['apres_annulation'] = sorted({b[r][1] for r in ('SEL00', 'SEL01', 'SEL03', 'SEL04')})
res['peut_encore_annuler'] = fen.undo_manager.can_undo()
fen._redo()
for _ in range(3): app.processEvents()
b = en_base()
res['apres_retablir'] = sorted({b[r][1] for r in ('SEL00', 'SEL01', 'SEL03', 'SEL04')})

# 3. Colonne Type, toutes les lignes SEL, une déjà à la valeur
VALEUR = ['Lave-linge']
selectionner(['SEL00', 'SEL01', 'SEL02', 'SEL03', 'SEL04', 'SEL05'], 0)
fen._show_column_values_list()
for _ in range(5): app.processEvents()
b = en_base()
res['types'] = sorted({b[f'SEL{i:02d}'][0] for i in range(6)})
res['autres_intacts'] = [b['REFDELTA'], b['AUTRE']]

# 4. Une seule ligne : chemin d'avant (pas de nb_lignes, cellule courante)
VALEUR = ['Plaque']
selectionner(['AUTRE'], 0)
fen._show_column_values_list()
for _ in range(5): app.processEvents()
res['une_ligne'] = appels[-1]
b = en_base()
res['une_ligne_ecrite'] = [b['AUTRE'][0], b['REFDELTA'][0], b['SEL00'][0]]

# 5. Colonne Réf. modèle : jamais de valeur à toute la sélection
res['colonne_ref'] = fen._lignes_selectionnees_dans_colonne(2)
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


def test_valeur_donnee_a_toute_la_selection():
    res = _executer()
    assert res['nb_lignes_table'] == 8
    assert res['appel'] == {'col': 1, 'nb_lignes': 4}
    # Casse alignée sur la marque déjà en base, lignes non sélectionnées intactes
    assert res['marques'] == {'SEL00': 'Delta', 'SEL01': 'Delta', 'SEL02': '',
                              'SEL03': 'Delta', 'SEL04': 'Delta', 'SEL05': ''}
    assert res['table'] == {'SEL00': 'Delta', 'SEL02': ''}
    # Historique : une modification par appareil, comme une saisie à la main
    assert res['historique'] == [['Fabricant', '', 'Delta']] * 4
    assert res['apres_annulation'] == ['']              # un seul Cmd+Z
    assert res['apres_retablir'] == ['Delta']
    assert res['types'] == ['Lave-linge']
    assert res['autres_intacts'] == [['Hotte', 'Delta'], ['Four', 'Bosch']]
    # Une ligne : fenêtre de valeurs habituelle, seule la cellule courante change
    assert res['une_ligne'] == {'col': 0, 'nb_lignes': 0}
    assert res['une_ligne_ecrite'] == ['Plaque', 'Hotte', 'Lave-linge']
    assert res['colonne_ref'] == []
