"""
Règle unique d'auto-complétion Type / Fabricant (proposition_type_fabricant)

Le bouton « Données → Autocomplétion » portait sa propre copie de la requête de
l'import, restée d'avant la v3.89.0 : il prenait des auto-complétés non vérifiés
comme source et ne traçait rien. Les deux chemins passent désormais par
`proposer_type_fabricant` ; ces tests fixent la règle et la parité.
"""

import os
import tempfile
import types

import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.services.proposition_type_fabricant import PropositionChamp, proposer_type_fabricant
from src.ui.data_management_service import DataManagementService

TS = '2026-11-01 08:00:00'


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
            [
                # Sources vérifiées de la réf. R1 : 2 × Four/Bosch, 1 × Four/Siemens
                (1, 'Four', 'Bosch', 'R1', 'C1'),
                (2, 'Four', 'Bosch', 'R1', 'C2'),
                (3, 'Four', 'Siemens', 'R1', 'C3'),
                # Source auto-complétée NON vérifiée de la réf. R2
                (4, 'Hotte', 'Elica', 'R2', 'C4'),
                # Appareils à compléter
                (10, '', '', 'R1', 'X10'),
                (11, 'Four', '', 'R1', 'X11'),
                (12, '', '', 'R2', 'X12'),
                (13, '', '', 'R1', 'X13'),
            ])
        conn.commit()
        manager.enregistrer_autocompletions([(4, 'type', 'Hotte', 'S', 1, 1, TS)])
        yield manager
        manager.close()
    finally:
        Config.DB_FILE = origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _appareil(db, appareil_id):
    ligne = db.execute_query(
        "SELECT type, manufacturer, ref_modele, commercial_ref FROM appareils WHERE id = ?",
        [appareil_id])[0]
    return dict(zip(('type', 'manufacturer', 'ref_modele', 'commercial_ref'), ligne))


def _traces(db, appareil_id):
    return {r[0]: tuple(r[1:]) for r in db.execute_query(
        "SELECT champ, valeur, source, accord, total FROM appareils_autocompletes "
        "WHERE appareil_id = ?", [appareil_id])}


def _service(db):
    return DataManagementService(db, types.SimpleNamespace())


def _lancer_bouton(db, ids):
    lignes = [{'id': i, 'data': _appareil(db, i)} for i in ids]
    return _service(db).auto_complete_empty_fields(lignes)


# ─── Règle ───────────────────────────────────────────────────────────────────

def test_proposition_la_plus_frequente_avec_confiance(db):
    propositions = proposer_type_fabricant(db, _appareil(db, 10))
    assert propositions == {
        'type': PropositionChamp('Four', 'R1', 3, 3),
        'manufacturer': PropositionChamp('Bosch', 'R1', 2, 3),
    }


def test_seuls_les_champs_vides_sont_proposes(db):
    assert set(proposer_type_fabricant(db, _appareil(db, 11))) == {'manufacturer'}


def test_auto_complete_non_verifie_ne_sert_pas_de_source(db):
    assert proposer_type_fabricant(db, _appareil(db, 12)) == {}


def test_rien_sans_reference_ou_si_deja_complet(db):
    assert proposer_type_fabricant(db, {'type': '', 'manufacturer': ''}) == {}
    assert proposer_type_fabricant(db, {'type': 'Four', 'manufacturer': 'Bosch',
                                        'ref_modele': 'R1'}) == {}


def test_valeurs_none_traitees_comme_vides(db):
    assert set(proposer_type_fabricant(
        db, {'type': None, 'manufacturer': None, 'ref_modele': 'R1',
             'commercial_ref': None})) == {'type', 'manufacturer'}


# ─── Bouton « Données → Autocomplétion » ─────────────────────────────────────

def test_bouton_complete_et_trace(db):
    resultat = _lancer_bouton(db, [10])
    assert resultat.completed_count == 1
    assert _appareil(db, 10)['type'] == 'Four'
    assert _appareil(db, 10)['manufacturer'] == 'Bosch'
    assert _traces(db, 10) == {'type': ('Four', 'R1', 3, 3),
                               'manufacturer': ('Bosch', 'R1', 2, 3)}


def test_bouton_ne_prend_pas_un_auto_complete_non_verifie_pour_source(db):
    resultat = _lancer_bouton(db, [12])
    assert resultat.completed_count == 0
    assert _appareil(db, 12)['type'] == ''


def test_bouton_ne_repropose_pas_une_valeur_refusee(db):
    db.enregistrer_refus([(10, 'manufacturer', 'BOSCH')])
    _lancer_bouton(db, [10])
    assert _appareil(db, 10)['type'] == 'Four'
    assert _appareil(db, 10)['manufacturer'] == ''
    assert set(_traces(db, 10)) == {'type'}


def test_ligne_completee_ne_gonfle_pas_la_confiance_des_suivantes(db):
    # 10 est complétée en premier : tracée aussitôt, elle ne compte pas comme
    # source pour 13 (sinon « 4/4 » au lieu de « 3/3 »).
    _lancer_bouton(db, [10, 13])
    assert _traces(db, 13)['type'] == ('Four', 'R1', 3, 3)


# ─── Parité avec l'import ────────────────────────────────────────────────────

def test_import_et_bouton_proposent_la_meme_chose(db):
    from collections import Counter
    from src.core.import_manager import ImportManager

    importeur = ImportManager.__new__(ImportManager)
    importeur.db_manager = db
    importeur._log_counters = Counter()

    for appareil_id in (10, 11, 12):
        donnees = _appareil(db, appareil_id)
        attendu = proposer_type_fabricant(db, donnees)
        complete = importeur._try_auto_complete(donnees)
        assert complete is bool(attendu)
        for champ, proposition in attendu.items():
            assert donnees[champ] == proposition.valeur
            assert donnees[ImportManager.CLE_AUTOCOMPLETION][champ] == {
                'valeur': proposition.valeur, 'source': proposition.source,
                'accord': proposition.accord, 'total': proposition.total}
