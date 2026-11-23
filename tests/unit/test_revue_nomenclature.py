"""
Règles de nomenclature, lot 4 — écran Règles et revue des propositions
(CDC docs/cdc_regles_nomenclature.md § 8.1-8.2, D8).

- service : statut, note (mention de zone grise gardée), exemples (désaccords
  d'abord), recalcul après validation/rejet ;
- revue : accepter une ligne (historique au format Type, provenance), accepter
  un groupe avec récapitulatif, annuler un lot (appareil modifié depuis laissé
  tel quel), refuser (jamais reproposé après recalcul) ;
- groupable : fortes, et simples d'une règle validée sur source web ;
- écriture différée d'un calcul fait en arrière-plan : propositions périmées
  écartées ;
- fenêtres (style global) : écran Règles, revue, critère « type proposé » du
  tableau.
"""

import json
import sqlite3

import pytest

from src.data.database_manager import DatabaseManager
from src.services.regle_nomenclature_service import (
    RegleNomenclatureService, pure_d7, zone_grise_de)
from src.services.revue_propositions_service import (
    RevuePropositionsService, groupable)


@pytest.fixture
def base(tmp_path):
    chemin = tmp_path / 'test.db'
    db = DatabaseManager(str(chemin))
    cnx = sqlite3.connect(str(chemin))
    appareils = [
        (1, 'Four', 'Gaggenau', 'BS270100/01', 'BS270100', 'COMBIVAP'),         # → Four vapeur (simple, web)
        (2, 'Four vapeur', 'Gaggenau', 'BS450110/01', 'BS450110', ''),           # déjà juste
        (3, 'Four', 'Whirlpool', '857331012000', 'AKR331IX', 'Plaque Email Gaz'),  # → Plaque (forte)
        (6, 'Cuisinière', 'Siemens', 'HM10220EU/01', 'HM10220EU', ''),           # aucune règle
        (7, 'Four', 'Gaggenau', 'BSP220100/01', 'BSP220100', ''),                # → Four vapeur
        (8, 'Four', 'Gaggenau', 'BS270100/02', 'BS270100', ''),                  # → Four vapeur
        (9, 'Réfrigérateur', 'Liebherr', 'GN 3056', 'GN3056', ''),               # → Congélateur (simple, sans source)
    ]
    cnx.executemany("INSERT INTO appareils(id, type, manufacturer, ref_modele, commercial_ref, "
                    "other_ref) VALUES (?, ?, ?, ?, ?, ?)", appareils)
    cnx.commit()
    cnx.close()
    service = RegleNomenclatureService(db)
    service.charger_catalogue()
    service.calculer_propositions(ecrire=True)
    yield db
    db.close()


def _types(db):
    return dict(db.execute_query("SELECT id, type FROM appareils"))


def _props(db):
    return {p['appareil_id']: p for p in db.lire_propositions_detaillees()}


def test_propositions_detaillees_et_groupables(base):
    props = _props(base)
    assert set(props) == {1, 3, 7, 8, 9}
    assert props[1]['motif'] == 'BS*' and props[1]['origine'] == 'web'
    assert groupable(props[3])                      # forte
    assert groupable(props[1])                      # simple, règle web avec source
    assert not groupable(props[9])                  # simple, règle sans source


def test_accepter_une_ligne_historique_et_lot(base):
    revue = RevuePropositionsService(base)
    bilan = revue.accepter([_props(base)[3]])
    assert bilan.acceptees == 1 and len(bilan.lots) == 1 and not bilan.erreur
    assert _types(base)[3] == 'Plaque'
    assert 3 not in _props(base)
    hist = base.execute_query(
        "SELECT action_type, title, details, field_name, old_value, new_value "
        "FROM modifications_history")
    assert len(hist) == 1
    action, titre, details, champ, avant, apres = hist[0]
    assert (action, champ, avant, apres) == ('edit', 'Type', 'Four', 'Plaque')
    assert titre == "[Type]  'Four' → 'Plaque'"
    assert "règles de nomenclature, groupe Whirlpool AKR3* → Plaque" in json.loads(details)[0]


def test_acceptation_groupee_recapitulatif_et_annulation(base):
    revue = RevuePropositionsService(base)
    gaggenau = [p for p in _props(base).values() if p['cible'] == 'Gaggenau']
    recap = revue.recapitulatif(gaggenau)
    assert recap.nb == 3
    lignes = {t: (av, ap) for t, av, ap, _ in recap.lignes()}
    assert lignes['Four'][1] == lignes['Four'][0] - 3
    assert lignes['Four vapeur'][1] == lignes['Four vapeur'][0] + 3
    bilan = revue.accepter(gaggenau)
    assert bilan.acceptees == 3 and len(bilan.lots) == 1
    assert {_types(base)[i] for i in (1, 7, 8)} == {'Four vapeur'}
    # Un appareil retouché à la main depuis : l'annulation le laisse tel quel
    base.execute_query("UPDATE appareils SET type = 'Cuisinière' WHERE id = 8")
    base.conn.commit()
    lot = revue.lots()[0]
    assert lot['nb'] == 3 and not lot['annule_le']
    annulation = revue.annuler_lot(lot)
    assert annulation.ecrit and len(annulation.a_corriger) == 2 and len(annulation.ignorees) == 1
    assert _types(base)[1] == 'Four' and _types(base)[7] == 'Four' and _types(base)[8] == 'Cuisinière'
    assert revue.lots()[0]['annule_le']


def test_refus_jamais_repropose(base):
    revue = RevuePropositionsService(base)
    assert revue.refuser([_props(base)[9]]) == 1
    assert 9 not in _props(base)
    RegleNomenclatureService(base).calculer_propositions(ecrire=True)
    assert 9 not in _props(base) and 1 in _props(base)
    assert _types(base)[9] == 'Réfrigérateur'


def test_rejet_d_une_regle_puis_recalcul(base):
    service = RegleNomenclatureService(base)
    regle = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'BS*')
    assert service.changer_statut(regle['id'], 'rejetee')
    relue = next(r for r in base.lister_regles_nomenclature() if r['id'] == regle['id'])
    assert relue['statut'] == 'rejetee' and relue['valide_le'] is None
    service.calculer_propositions(ecrire=True)
    assert not {1, 7, 8} & set(_props(base))
    assert service.changer_statut(regle['id'], 'validee')
    service.calculer_propositions(ecrire=True)
    assert {1, 7, 8} <= set(_props(base))
    with pytest.raises(ValueError):
        service.changer_statut(regle['id'], 'peut-etre')


def test_note_garde_la_zone_grise(base):
    service = RegleNomenclatureService(base)
    regle = base.lister_regles_nomenclature()[0]
    assert service.enregistrer_note(regle['id'], "vu en ligne", zone_grise='AK*')
    relue = next(r for r in base.lister_regles_nomenclature() if r['id'] == regle['id'])
    assert zone_grise_de(relue) == 'AK*' and 'vu en ligne' in relue['note']
    assert zone_grise_de({'note': 'autre'}) == ''
    assert pure_d7({'couverture': 100, 'accord': 98}) and not pure_d7({'couverture': 100, 'accord': 97})
    assert not pure_d7({'couverture': None, 'accord': None})


def test_exemples_desaccords_d_abord(base):
    service = RegleNomenclatureService(base)
    regle = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'BS*')
    ex = service.exemples(regle)
    assert (ex.couverture, ex.accord) == (4, 1)
    assert {d[0] for d in ex.desaccords} == {1, 7, 8}
    assert [a[0] for a in ex.accords] == [2]
    groupe = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'AKR3*')
    assert [d[0] for d in service.exemples(groupe).desaccords] == [3]


def test_ecriture_differee_ecarte_les_perimees(base):
    service = RegleNomenclatureService(base)
    bilan = service.calculer_propositions(ecrire=False)
    # Entre le calcul (arrière-plan) et l'écriture : un type changé, un refus
    base.execute_query("UPDATE appareils SET type = 'Four vapeur' WHERE id = 1")
    base.conn.commit()
    base.enregistrer_refus([(7, 'type', 'Four vapeur')])
    assert service.ecrire_propositions(bilan)
    assert set(_props(base)) == {3, 8, 9}


# ── Fenêtres (avec le style global de l'application) ─────────────────────────

import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _vider_boucle(qapp):
    from PyQt5.QtWidgets import QApplication
    for _ in range(3):
        qapp.processEvents()
    QApplication.sendPostedEvents(None, 0)
    qapp.processEvents()


@pytest.fixture
def style_global(qapp):
    from src.ui.style_manager import StyleManager
    ancien = qapp.styleSheet()
    qapp.setStyleSheet(StyleManager.get_modern_style())
    yield qapp
    qapp.setStyleSheet(ancien)


def _attendre_calcul(qapp, dialogue, delai=30):
    fin = time.time() + delai
    while dialogue.calcul_en_cours() and time.time() < fin:
        qapp.processEvents()
        time.sleep(0.02)
    _vider_boucle(qapp)
    assert not dialogue.calcul_en_cours()


def _ecran(base):
    from src.ui.regles_nomenclature_dialog import ReglesNomenclatureDialog
    rappels = []
    dlg = ReglesNomenclatureDialog(None, base, RevuePropositionsService(base),
                                   on_propositions_changees=lambda: rappels.append(1))
    return dlg, rappels


def test_ecran_regles_filtres_fiche_et_rejet(style_global, base):
    qapp = style_global
    dlg, rappels = _ecran(base)
    dlg.show()
    _vider_boucle(qapp)
    n = len(base.lister_regles_nomenclature())
    assert dlg._filtre.rowCount() == n and "Règles de nomenclature" in dlg._titre.text()
    dlg._f_motif.setText("BS*")
    assert dlg._filtre.rowCount() == 1
    dlg._f_motif.setText("")
    dlg._f_changeraient.setChecked(True)
    assert 0 < dlg._filtre.rowCount() < n
    dlg._f_changeraient.setChecked(False)
    regle = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'BS*')
    assert dlg.selectionner_regle(regle['id'])
    _vider_boucle(qapp)
    assert "Gaggenau BS*" in dlg._fiche_titre.text()
    assert "Désaccords (3)" in dlg._exemples.toPlainText()
    assert dlg._btn_revue_regle.isEnabled() and not dlg._bandeau_zone.isVisible()
    # Rejeter : recalcul en arrière-plan, les propositions de la règle disparaissent
    dlg.changer_statut('rejetee')
    _attendre_calcul(qapp, dlg)
    assert not {1, 7, 8} & set(_props(base)) and rappels
    assert next(r for r in base.lister_regles_nomenclature()
                if r['id'] == regle['id'])['statut'] == 'rejetee'
    dlg.close()
    _vider_boucle(qapp)


def test_ecran_regles_zone_grise_et_decouverte(style_global, base):
    qapp = style_global
    cnx = sqlite3.connect(base.db_file)
    cnx.executemany("INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) "
                    "VALUES ('Lave-linge', 'Bosch', ?, ?)",
                    [(f'WAT{n:04d}/01', f'WAT{n:04d}') for n in range(40)])
    cnx.execute("INSERT INTO regles_nomenclature(portee, cible, cle, forme, motif, type_resultat, "
                "statut, origine, note) VALUES ('marque', 'Whirlpool', 'nom', 'prefixe', 'AKX*', "
                "'Four', 'proposee', 'decouverte', 'sous la zone grise AK*')")
    cnx.commit()
    cnx.close()
    dlg, _ = _ecran(base)
    dlg.show()
    _vider_boucle(qapp)
    zone = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'AKX*')
    assert dlg.selectionner_regle(zone['id'])
    _vider_boucle(qapp)
    assert dlg._bandeau_zone.isVisible() and "AK*" in dlg._bandeau_zone.text()
    avant = len(base.lister_regles_nomenclature())
    dlg.chercher_nouvelles_regles()
    assert dlg.calcul_en_cours()
    _attendre_calcul(qapp, dlg)
    regles = base.lister_regles_nomenclature()
    nouvelles = [r for r in regles[avant:]]
    assert nouvelles and {r['statut'] for r in nouvelles} == {'proposee'}
    assert "nouvelle" in dlg._etat_calcul.text()
    assert dlg._f_changeraient.isChecked()     # filtre par défaut après une découverte
    dlg.close()
    _vider_boucle(qapp)


def test_ecran_regles_annuler_un_lot(style_global, base, monkeypatch):
    qapp = style_global
    revue = RevuePropositionsService(base)
    revue.accepter([_props(base)[3]])
    dlg, rappels = _ecran(base)
    dlg.show()
    _vider_boucle(qapp)
    assert dlg._lots.count() == 1
    dlg._lots.setCurrentRow(0)
    assert dlg._btn_annuler_lot.isEnabled()
    dlg._annuler_lot(dlg._lots.currentItem().data(0x0100))
    _attendre_calcul(qapp, dlg)
    assert _types(base)[3] == 'Four' and 3 in _props(base)      # reproposé après recalcul
    assert "annulée" in dlg._lots.item(0).text()
    dlg.close()
    _vider_boucle(qapp)


def test_revue_groupee_bornee_et_recapitulatif(style_global, base):
    from PyQt5.QtWidgets import QMessageBox
    from src.ui.fenetre_revue import ATTENTE, VALIDE, entree
    from src.ui.propositions_type_dialog import PropositionsTypeDialog
    qapp = style_global
    revue = RevuePropositionsService(base)
    decisions = []
    dlg = PropositionsTypeDialog(None, revue.propositions(),
                                 lambda a, r: (decisions.append((a, r)), revue.accepter(a),
                                               revue.refuser(r)),
                                 recapitulatif=revue.recapitulatif)
    dlg.show()
    _vider_boucle(qapp)
    feuilles = {entree(it)['appareil_id']: it for it in dlg._feuilles}
    assert set(feuilles) == {1, 3, 7, 8, 9}
    # Tout sélectionné : la simple Liebherr (sans source web) reste en attente
    dlg.decider(VALIDE, list(feuilles.values()))
    assert dlg.etat(feuilles[9]) == ATTENTE and dlg._bandeau.isVisible()
    assert all(dlg.etat(feuilles[i]) == VALIDE for i in (1, 3, 7, 8))
    # Une à une : permise
    dlg.decider(VALIDE, [feuilles[9]])
    assert dlg.etat(feuilles[9]) == VALIDE
    dlg._on_appliquer()
    boite = dlg._recap_boite
    assert boite.isVisible() and "5 appareils" in boite.text()
    assert "Four" in boite.informativeText()
    accepter = next(b for b in boite.buttons() if b.text() == "Accepter")
    accepter.click()
    _vider_boucle(qapp)
    assert len(decisions) == 1 and len(decisions[0][0]) == 5
    assert _types(base)[3] == 'Plaque' and _types(base)[9] == 'Congélateur'
    assert not _props(base)
    dlg.close()
    _vider_boucle(qapp)


def test_critere_type_propose_du_tableau(base):
    from src.data.appareils_table_model import AppareillsTableModel
    from src.ui.table_controller import TableController
    critere = TableController._CRITERES_NAV['type_propose']
    assert hasattr(TableController, critere['reevaluer'])
    assert hasattr(AppareillsTableModel, critere['ligne_page'])
    assert hasattr(base, critere['position_sql'])
    # Position SQL dans l'ordre de l'écran (tri par id) : 1, 3, 7, 8, 9
    trouve = base.find_type_propose_position(None, {}, None, 'ASC', False, -1, 'down')
    assert trouve is not None
    model = AppareillsTableModel()
    model.load_records([(i, 'Four', 'X', f'R{i}', '', '', '', 0) for i in (2, 3, 4)])
    model.set_propositions_type({3: {'type': 'Plaque', 'regle': 'AKR3*', 'force': 'forte'}})
    assert model.find_type_propose_row(-1, 'down') == (1, 0)
    assert model.find_type_propose_row(1, 'down') is None
    assert "Type proposé : Plaque" in model.data(model.index(1, 0), 3)   # ToolTipRole
    assert model.ids_types_proposes([2, 3, 4]) == [3]


_SCRIPT_FENETRE = r"""
import json, os, sys, tempfile
sys.path.insert(0, os.getcwd())
from src.core.config import Config
Config.DB_FILE = tempfile.mktemp(suffix='.db')
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QMenu
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
app = QApplication(sys.argv)
from src.ui.main_refactored import MainWindow
fen = MainWindow()
from src.ui.style_manager import StyleManager
app.setStyleSheet(StyleManager.get_modern_style())
fen.show()
for _ in range(5): app.processEvents()
res = {'revue': hasattr(fen, 'revue_nomenclature'),
       'groupe_masque': not fen.revue_nomenclature.groupe.isVisible()}
fen._open_regles_nomenclature()
for _ in range(5): app.processEvents()
dlg = fen.revue_nomenclature._regles_dialog
res['ecran'] = bool(dlg and dlg.isVisible() and not dlg.isModal())
res['menu'] = any(a.text() == "Règles de nomenclature…" for m in app.allWidgets() if isinstance(m, QMenu)
                  for a in m.actions())
dlg.close()
for _ in range(3): app.processEvents()
print('RESULTAT ' + json.dumps(res), flush=True)
os._exit(0)
"""


def test_fenetre_principale_menu_et_ecran():
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    sortie = subprocess.run([sys.executable, '-c', _SCRIPT_FENETRE], capture_output=True,
                            text=True, timeout=180, env=env, cwd=str(RACINE))
    ligne = [l for l in sortie.stdout.splitlines() if l.startswith('RESULTAT ')]
    assert ligne, sortie.stderr[-3000:]
    assert json.loads(ligne[0][len('RESULTAT '):]) == {
        'revue': True, 'groupe_masque': True, 'ecran': True, 'menu': True}


def test_regle_proposee_ne_masque_pas_la_regle_de_groupe():
    """Constat du lot 4 sur la base réelle : la découverte proposait « Whirlpool
    AKR3* → Four » (l'erreur majoritaire) et sa seule présence retirait Whirlpool
    de la règle validée « groupe Whirlpool AKR3* → Plaque » (115 propositions
    fortes perdues). Une règle proposée ne décide rien (D4)."""
    from src.utils.nomenclature.moteur import IndexRegles, Regle
    from src.utils.nomenclature.cles import cle_code, cle_nom
    from src.utils.rapprochement_fiche.configuration import ConfigurationRapprochement
    from src.utils.lecteur_fiche.lecteur import cle_marque
    config = ConfigurationRapprochement()
    groupe_de = lambda m: config.groupe_de.get(cle_marque(m), '')
    validee = Regle('groupe', 'Whirlpool', 'nom', 'AKR3*', 'Plaque', 'validee')
    proposee = Regle('marque', 'Whirlpool', 'nom', 'AKR3*', 'Four', 'proposee')
    index = IndexRegles([validee, proposee], groupe_de)
    assert index.resoudre('Whirlpool', cle_nom('', 'AKR331IX'), '').type == 'Plaque'
    rejetee = Regle('marque', 'Whirlpool', 'nom', 'AKR3*', 'Four', 'rejetee')
    assert IndexRegles([validee, rejetee], groupe_de).resoudre(
        'Whirlpool', cle_nom('', 'AKR331IX'), '').type == ''


def test_decouverte_ne_repropose_pas_un_motif_tranche(base):
    """Les appareils Whirlpool AKR3 en « Four » formeraient une règle pure ;
    la règle validée du groupe a déjà tranché ce motif."""
    cnx = sqlite3.connect(base.db_file)
    cnx.executemany("INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) "
                    "VALUES ('Four', 'Whirlpool', ?, ?)",
                    [(f'8573310{n:05d}', f'AKR3{n:03d}IX') for n in range(40)])
    # AKR mélangé (comme en production) : la descente va jusqu'à AKR3
    cnx.executemany("INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) "
                    "VALUES ('Hotte', 'Whirlpool', ?, ?)",
                    [(f'8573360{n:05d}', f'AKR6{n:03d}IX') for n in range(40)])
    cnx.commit()
    cnx.close()
    service = RegleNomenclatureService(base)
    bilan = service.decouvrir_regles(ecrire=False)
    assert bilan.deja_tranchees >= 1
    assert not [c for c in bilan.nouvelles if c.motif.startswith('AKR3')
                and c.cible in ('Whirlpool',)]
    service.decouvrir_regles(ecrire=True)
    bilan = service.calculer_propositions(ecrire=True)
    assert sum(1 for p in bilan.propositions.values() if p['type_propose'] == 'Plaque') == 41


@pytest.mark.parametrize('valeur,filtre,attendu', [
    ('AKZ*', 'AK*', True), ('AKZ*', 'akz', True), ('EW?F*', 'EW?F*', True),
    ('BS*', 'AK* | BS*', True), ('AKZ#S*', 'AK* !AKZ#*', False), ('HB86*', '', True),
    ('G*', 'GK*', False), ('50%', '50%', True),
])
def test_filtre_de_motif_comme_le_sql(valeur, filtre, attendu):
    """Même sens que condition_filtre_colonne (LIKE), appliqué en Python."""
    from src.utils.filtre_colonne import condition_filtre_colonne, correspond_au_filtre
    assert correspond_au_filtre(valeur, filtre) is attendu
    condition = condition_filtre_colonne('v', filtre)
    if condition:
        cnx = sqlite3.connect(':memory:')
        sql, params = condition
        assert bool(cnx.execute(f"SELECT 1 FROM (SELECT ? AS v) WHERE {sql}",
                                [valeur, *params]).fetchone()) is attendu


def test_index_des_prefixes_equivalent_au_test_regle_par_regle():
    import random
    from src.services.regle_nomenclature_service import _ReglesIndexees
    from src.utils.nomenclature.moteur import Regle
    alea = random.Random(4)
    lettres = 'ABKRZ0123456789'
    motifs = {''.join(alea.choice(lettres) for _ in range(alea.randint(1, 4))) + '*'
              for _ in range(300)} | {'AK?S*', 'A[1-3]*', 'AKZ9###'}
    regles = [Regle('marque', 'X', 'nom', m, 'Four') for m in motifs]
    index = _ReglesIndexees(regles)
    for _ in range(2000):
        valeur = ''.join(alea.choice(lettres) for _ in range(alea.randint(0, 9)))
        attendu = {id(r) for r in regles if r.s_applique(valeur)}
        assert {id(r) for r in index.qui_s_appliquent(valeur)} == attendu
