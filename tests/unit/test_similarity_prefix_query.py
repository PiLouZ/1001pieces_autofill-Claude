"""
Tests — La requête d'index de similarité ne casse plus sous le nombre de préfixes

`_compute_similarity_suggestions` sélectionne les appareils déjà renseignés dont
une référence partage un préfixe de 3 caractères avec les lignes incomplètes.

La version d'origine enchaînait une paire de « OR … LIKE ? » par préfixe. Au-delà
d'environ 500 préfixes, SQLite refusait la requête — « Expression tree is too
large », profondeur maximale 1000 — et `execute_query` avalait l'exception :
l'utilisateur lisait « aucune proposition » alors que des centaines l'attendaient.
Mesuré : 0 suggestion en 0,00 s à 600 préfixes, contre 272 attendues.

Un `IN (…)` est un nœud d'expression unique. Ces tests verrouillent les deux
propriétés : la requête tient à grande échelle, et elle sélectionne exactement
les mêmes lignes que l'ancienne stratégie.
"""

import sqlite3
import pytest

from src.data.database_manager import DatabaseManager


def _requete(prefixes):
    return DatabaseManager.requete_index_similarite(prefixes)


def _requete_ancienne(prefixes):
    """Stratégie d'origine, reproduite pour comparaison."""
    prefixes = list(prefixes)
    like = " OR ".join(
        ["ref_modele LIKE ? COLLATE NOCASE", "commercial_ref LIKE ? COLLATE NOCASE"] * len(prefixes)
    )
    params = [x for p in prefixes for x in (p + '%', p + '%')]
    query = (
        "SELECT id, ref_modele, commercial_ref, type, manufacturer FROM appareils "
        "WHERE (type IS NOT NULL AND type != '' OR manufacturer IS NOT NULL AND manufacturer != '') "
        f"AND ({like})"
    )
    return query, params


@pytest.fixture
def base(test_db_manager):
    """Quelques appareils renseignés, aux préfixes variés."""
    for type_app, marque, ref, com in [
        ('Aspirateur', 'Samsung', 'SC4520', 'PowerBrush'),
        ('Aspirateur', 'Samsung', 'SC4521', ''),
        ('Four', 'Bosch', 'HBA0001', 'SER0001'),
        ('Frigo', 'LG', 'GBB62PZ', ''),
        ('Lave-linge', 'Bosch', 'K3_TYP103', 'K3_TYP11'),   # « _ », joker LIKE
        ('Sèche-linge', 'Miele', 'KXB99', ''),
    ]:
        test_db_manager.insert_appareil({'type': type_app, 'manufacturer': marque,
                                         'ref_modele': ref, 'commercial_ref': com})
    return test_db_manager


def _ids(db, requete_params):
    query, params = requete_params
    return {r[0] for r in (db.execute_query(query, params) or [])}


class TestEquivalence:
    """Même sélection que l'ancienne stratégie — c'est la contrainte de fond."""

    @pytest.mark.parametrize("prefixes", [
        ['sc4'],
        ['sc4', 'hba'],
        ['sc4', 'hba', 'gbb', 'kxb'],
        ['zzz'],                       # aucun résultat
        [],                            # aucun préfixe
    ])
    def test_memes_lignes_que_l_ancienne_strategie(self, base, prefixes):
        if not prefixes:
            pytest.skip("une requête sans préfixe n'a pas de sens pour l'ancienne forme")
        assert _ids(base, _requete(prefixes)) == _ids(base, _requete_ancienne(prefixes))

    def test_le_prefixe_est_insensible_a_la_casse(self, base):
        assert _ids(base, _requete(['sc4'])) == _ids(base, _requete(['SC4'.lower()]))
        assert _ids(base, _requete(['sc4'])), "SC4520 et SC4521 devraient ressortir"

    def test_les_deux_colonnes_de_reference_sont_couvertes(self, base):
        """« ser » n'existe qu'en référence commerciale."""
        assert _ids(base, _requete(['ser']))


class TestJokerSousJacent:
    """« _ » était un joker pour LIKE ; il ne l'est plus."""

    def test_le_souligne_est_compare_a_la_lettre(self, base):
        """« k3_ » ne doit ramener que les références commençant réellement par K3_."""
        trouves = base.execute_query(*_requete(['k3_']))
        refs = {r[1] for r in trouves}
        assert refs == {'K3_TYP103'}

    def test_un_prefixe_joker_ne_ramene_plus_n_importe_quoi(self, base):
        """Avec LIKE, « s_4 » aurait matché « SC4520 ». Plus maintenant."""
        assert not _ids(base, _requete(['s_4']))
        assert _ids(base, _requete_ancienne(['s_4'])), "l'ancienne forme matchait bien, elle"


class TestPassageAL_Echelle:
    """Le défaut d'origine : au-delà de ~500 préfixes, SQLite refusait la requête."""

    @pytest.mark.parametrize("nombre", [400, 600, 1200, 3000])
    def test_la_requete_tient_a_grande_echelle(self, base, nombre):
        prefixes = [f"{i:03d}" for i in range(nombre)] + ['sc4']
        query, params = _requete(prefixes)
        lignes = base.execute_query(query, params)
        assert lignes is not None
        assert {r[1] for r in lignes} >= {'SC4520', 'SC4521'}

    def test_l_ancienne_strategie_echouait_bien(self, base):
        """Confirme que le défaut corrigé était réel, et non supposé."""
        prefixes = [f"{i:03d}" for i in range(600)]
        query, params = _requete_ancienne(prefixes)
        with pytest.raises(sqlite3.OperationalError, match="Expression tree is too large"):
            base.conn.execute(query, params).fetchone()

    def test_la_nouvelle_ne_leve_rien_sur_le_meme_jeu(self, base):
        prefixes = [f"{i:03d}" for i in range(600)]
        query, params = _requete(prefixes)
        base.conn.execute(query, params).fetchone()   # ne doit pas lever


class TestFormeDeLaRequete:

    def test_un_marqueur_par_prefixe_et_par_colonne(self):
        query, params = _requete(['abc', 'def'])
        assert query.count('?') == len(params) == 4

    def test_les_prefixes_sont_passes_en_parametres(self):
        """Aucune interpolation de valeur dans le SQL — pas d'injection possible."""
        query, params = _requete(["'; DROP TABLE appareils; --"])
        assert 'DROP TABLE' not in query
        assert "'; DROP TABLE appareils; --" in params
