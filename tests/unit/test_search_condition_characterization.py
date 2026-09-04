"""
Tests de caractérisation — `_build_search_condition_optimized`

Cette fonction construit le SQL de **toute** la recherche de l'application, sur
une base de ~690 000 appareils. Complexité cognitive 97 sur 186 lignes : c'est la
fonction la plus risquée du dépôt, et elle n'avait **aucun test direct**.

Ces tests ne jugent pas ce que la fonction *devrait* faire : ils figent ce qu'elle
fait **aujourd'hui**, exactement, pour que toute modification ultérieure du SQL
produit soit visible. C'est le filet indispensable avant de la décomposer.

Deux constats ont motivé leur écriture :

1. **Le chemin de production n'était pas testé.** `Config.SEARCH_PIECES_ONLY` vaut
   `True` en production et aucun code de `src/` ne le modifie — or `tests/conftest.py`
   le force à `False` pour la fixture de base. La suite exerçait donc le mode LIKE,
   pas le mode réellement utilisé.
2. **La branche FTS5 est inatteignable** tant que `SEARCH_PIECES_ONLY` vaut `True` :
   elle est gardée par `not SEARCH_PIECES_ONLY`. Un test le vérifie explicitement.

L'instantané de référence vit dans `tests/fixtures/search_conditions_golden.json`.
Le régénérer sciemment (voir `_ecrire_instantane`) est un acte délibéré : le diff
montre alors précisément quel SQL change.
"""

import json
import os
import tempfile
import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager

INSTANTANE = os.path.join(os.path.dirname(__file__), '..', 'fixtures',
                          'search_conditions_golden.json')

# ─── Matrice d'entrées ───────────────────────────────────────────────────────

ENTREES = [
    ("chaine_vide",            ""),
    ("chaine_espaces",         "   "),
    ("none",                   None),
    ("chaine_simple",          "AS6015830"),
    # Fige une incohérence réelle : en mode LIKE les paramètres utilisent la chaîne
    # NON trimmée ('%  X  %'), là où le mode pieces_only utilise la version trimmée.
    # Défaut latent hors chemin de production — figé ici, pas corrigé.
    ("chaine_avec_espaces",    "  AS6015830  "),
    ("simple_sans_terme",      {'type': 'simple', 'terms': []}),
    ("simple",                 {'type': 'simple', 'terms': ['AS6015830']}),
    ("simple_bypass",          {'type': 'simple', 'terms': ['A1'], 'bypass_supersession': True}),
    ("simple_extend",          {'type': 'simple', 'terms': ['A1'], 'extend_search': True}),
    ("simple_predecesseurs",   {'type': 'simple', 'terms': ['A1'], 'expand_predecessors': ['P1', 'P2']}),
    ("simple_equivalents",     {'type': 'simple', 'terms': ['A1'], 'expand_equivalents': ['E1']}),
    ("simple_pred_et_equiv",   {'type': 'simple', 'terms': ['A1'],
                                'expand_predecessors': ['P1'], 'expand_equivalents': ['P1', 'E1']}),
    ("and_sans_terme",         {'type': 'and', 'terms': []}),
    ("and_deux_termes",        {'type': 'and', 'terms': ['A1', 'B2']}),
    ("and_extend",             {'type': 'and', 'terms': ['A1', 'B2'], 'extend_search': True}),
    ("or_sans_groupe",         {'type': 'or', 'groups': []}),
    ("or_groupe_simple",       {'type': 'or', 'groups': [{'type': 'simple', 'terms': ['A1']}]}),
    ("or_groupe_and",          {'type': 'or', 'groups': [{'type': 'and', 'terms': ['A1', 'B2']}]}),
    ("or_mixte",               {'type': 'or', 'groups': [{'type': 'simple', 'terms': ['A1']},
                                                         {'type': 'and', 'terms': ['B2', 'C3']}]}),
    ("or_groupe_vide",         {'type': 'or', 'groups': [{'type': 'simple', 'terms': []}]}),
    ("or_extend",              {'type': 'or', 'groups': [{'type': 'simple', 'terms': ['A1']}],
                               'extend_search': True}),
    ("type_inconnu",           {'type': 'inconnu', 'terms': ['A1']}),
]

MODES = [
    ("pieces_only=True,fts5=True",   True,  True),
    ("pieces_only=True,fts5=False",  True,  False),
    ("pieces_only=False,fts5=False", False, False),
    ("pieces_only=False,fts5=True",  False, True),
]


# ─── Harnais ─────────────────────────────────────────────────────────────────

def _base_temporaire(avec_supersession=False):
    """DatabaseManager sur une base neuve, éventuellement avec une chaîne de
    supersession — le seul état de base dont dépend la construction du SQL."""
    chemin = tempfile.mktemp(suffix='.db')
    Config.DB_FILE = chemin
    db = DatabaseManager()
    if avec_supersession:
        db.execute_custom_query(
            "INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES ('A1', 1)")
        db.execute_custom_query(
            "INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES ('A2', 1)")
        db.execute_custom_query(
            "INSERT OR REPLACE INTO piece_supersessions(ref_old, ref_new) VALUES ('A1', 'A2')")
    return db, chemin


def _relever(avec_supersession=False):
    """Sortie de la fonction pour toute la matrice entrées × drapeaux."""
    pieces_only_origine = Config.SEARCH_PIECES_ONLY
    fts5_origine = Config.USE_FTS5
    db_file_origine = Config.DB_FILE
    db, chemin = _base_temporaire(avec_supersession)
    try:
        releve = {}
        for libelle_mode, pieces_only, fts5 in MODES:
            Config.SEARCH_PIECES_ONLY = pieces_only
            Config.USE_FTS5 = fts5
            releve[libelle_mode] = {
                nom: db._build_search_condition_optimized(entree)
                for nom, entree in ENTREES
            }
        return releve
    finally:
        Config.SEARCH_PIECES_ONLY = pieces_only_origine
        Config.USE_FTS5 = fts5_origine
        db.close()
        Config.DB_FILE = db_file_origine
        if os.path.exists(chemin):
            os.remove(chemin)


def _ecrire_instantane():
    """Régénérer le fichier de référence — acte délibéré, jamais automatique.

    À lancer à la main après avoir vérifié que le changement de SQL est voulu :
        python -c "import tests.unit.test_search_condition_characterization as t; \
                   t._ecrire_instantane()"
    """
    contenu = {
        'base_vide': _relever(False),
        'base_avec_supersession': _relever(True),
    }
    with open(INSTANTANE, 'w', encoding='utf-8') as f:
        json.dump(contenu, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write('\n')
    return contenu


@pytest.fixture(scope="module")
def instantane():
    with open(INSTANTANE, encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def releve_actuel(qapp):
    return {
        'base_vide': _relever(False),
        'base_avec_supersession': _relever(True),
    }


# ─── Le filet : égalité au caractère près ────────────────────────────────────

class TestInstantane:
    """Le SQL produit doit être identique à la référence, caractère par caractère."""

    @pytest.mark.parametrize("etat_base", ['base_vide', 'base_avec_supersession'])
    @pytest.mark.parametrize("mode", [m[0] for m in MODES])
    def test_sql_inchange(self, releve_actuel, instantane, etat_base, mode):
        attendu = instantane[etat_base][mode]
        obtenu = releve_actuel[etat_base][mode]

        assert set(obtenu) == set(attendu), "la matrice d'entrées a changé"
        for nom in sorted(attendu):
            assert obtenu[nom] == attendu[nom], (
                f"\nSQL modifié pour « {nom} » en mode {mode} ({etat_base}).\n"
                f"  attendu : {attendu[nom]}\n"
                f"  obtenu  : {obtenu[nom]}\n"
                f"Si le changement est voulu, régénérer via _ecrire_instantane()."
            )


# ─── Invariants structurels ──────────────────────────────────────────────────

class TestInvariants:

    def test_autant_de_placeholders_que_de_parametres(self, releve_actuel):
        """Un décalage ici produirait une erreur SQLite à l'exécution."""
        for etat_base, par_mode in releve_actuel.items():
            for mode, cas in par_mode.items():
                for nom, resultat in cas.items():
                    if not isinstance(resultat, dict):
                        continue
                    attendus = resultat['condition'].count('?')
                    fournis = len(resultat['params'])
                    assert attendus == fournis, (
                        f"{nom} / {mode} / {etat_base} : "
                        f"{attendus} placeholders pour {fournis} paramètres"
                    )

    @pytest.mark.parametrize("nom_vide", [
        'chaine_vide', 'chaine_espaces', 'none', 'simple_sans_terme',
        'and_sans_terme', 'or_sans_groupe', 'or_groupe_vide', 'type_inconnu',
    ])
    def test_entrees_sans_recherche_rendent_none(self, releve_actuel, nom_vide):
        """Aucune condition ne doit être produite pour une recherche vide."""
        for par_mode in releve_actuel.values():
            for mode, cas in par_mode.items():
                assert cas[nom_vide] is None, f"{nom_vide} en mode {mode}"


class TestModeDeProduction:
    """Ce que fait réellement l'application : SEARCH_PIECES_ONLY = True."""

    def test_toutes_les_conditions_sont_pieces_only(self, releve_actuel):
        for mode in ("pieces_only=True,fts5=True", "pieces_only=True,fts5=False"):
            for nom, resultat in releve_actuel['base_vide'][mode].items():
                if isinstance(resultat, dict):
                    assert resultat.get('query_type') == 'pieces_only', nom

    def test_fts5_est_inatteignable_en_mode_pieces_only(self, releve_actuel):
        """La branche FTS5 est gardée par `not SEARCH_PIECES_ONLY` : activer ou
        désactiver l'index ne change donc rien au SQL produit en production."""
        avec = releve_actuel['base_vide']["pieces_only=True,fts5=True"]
        sans = releve_actuel['base_vide']["pieces_only=True,fts5=False"]
        assert avec == sans

    def test_la_supersession_etend_la_recherche(self, releve_actuel):
        """A1 → A2 en base : la condition doit couvrir les deux références."""
        vide = releve_actuel['base_vide']["pieces_only=True,fts5=True"]['simple_extend']
        avec = releve_actuel['base_avec_supersession']["pieces_only=True,fts5=True"]['simple_extend']
        assert vide != avec, "la chaîne de supersession n'influence pas la condition"
        assert 'A2' in avec['params']
