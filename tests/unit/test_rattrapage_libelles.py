"""
Tests — Calcul du rattrapage des libellés (lot 4)

Les lots 1 à 3 empêchent le problème de se reproduire mais ne réparent rien :
`propagate_description` ne s'exécute qu'à la création d'une relation, et les
références déjà en base ont vu la leur créée il y a des mois.

`calculer_reparations` est pure : elle travaille sur une copie des libellés et
ne touche pas la base. C'est elle qui décide ce que la simulation affiche et ce
que l'écriture applique — les deux lisent la même liste.
"""

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

from rattrapage_libelles import calculer_reparations, charger_voisinage  # noqa: E402


def _reparations(libelles, voisins):
    faites, _ambigues, _sans = calculer_reparations(libelles, voisins)
    return {ref: libelle for ref, libelle, _source, _passe in faites}


class TestCalculerReparations:

    def test_une_voisine_nommee_donne_son_libelle(self):
        libelles = {"ANONYME": "", "NOMMEE": "Pompe de cyclage"}
        voisins = {"ANONYME": {"NOMMEE"}, "NOMMEE": {"ANONYME"}}

        assert _reparations(libelles, voisins) == {"ANONYME": "Pompe de cyclage"}

    def test_un_libelle_existant_n_est_jamais_propose(self):
        libelles = {"DEJA": "Son libellé", "AUTRE": "Un autre"}
        voisins = {"DEJA": {"AUTRE"}, "AUTRE": {"DEJA"}}

        assert _reparations(libelles, voisins) == {}

    def test_voisines_divergentes_sont_une_ambiguite_non_tranchee(self):
        """Deux voisines nommées différemment : le script ne choisit pas à la
        place de l'utilisateur, il signale et passe."""
        libelles = {"ANONYME": "", "A": "Pompe", "B": "Pompe de cyclage"}
        voisins = {"ANONYME": {"A", "B"}, "A": {"ANONYME"}, "B": {"ANONYME"}}

        faites, ambigues, _sans = calculer_reparations(libelles, voisins)

        assert faites == []
        assert ambigues == [("ANONYME", ["Pompe", "Pompe de cyclage"])]

    def test_voisines_d_accord_ne_sont_pas_une_ambiguite(self):
        """Deux voisines qui portent le MÊME libellé : aucune ambiguïté."""
        libelles = {"ANONYME": "", "A": "Sonde CTN", "B": "Sonde CTN"}
        voisins = {"ANONYME": {"A", "B"}, "A": {"ANONYME"}, "B": {"ANONYME"}}

        faites, ambigues, _sans = calculer_reparations(libelles, voisins)

        assert ambigues == []
        assert len(faites) == 1

    def test_propagation_le_long_d_une_chaine(self):
        """Réparer une réf en rend une autre réparable : A → B → C."""
        libelles = {"A": "Support sonde", "B": "", "C": ""}
        voisins = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}

        faites, _ambigues, sans = calculer_reparations(libelles, voisins)

        assert _reparations(libelles, voisins) == {"B": "Support sonde",
                                                   "C": "Support sonde"}
        assert sans == []

    def test_une_seconde_passe_rattrape_un_ordre_defavorable(self):
        """Le maillon éloigné est ici rencontré AVANT celui qui le nourrit : une
        seule passe le laisserait anonyme. Observé en réel — 4 des 78 réparations
        de la base n'arrivent qu'à la seconde passe."""
        libelles = {"C": "", "B": "", "A": "Support sonde"}   # ordre défavorable
        voisins = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}

        faites, _ambigues, sans = calculer_reparations(libelles, voisins)

        passe_par_ref = {ref: passe for ref, _l, _s, passe in faites}
        assert passe_par_ref == {"B": 1, "C": 2}
        assert sans == []

    def test_sans_voisine_nommee_reste_a_saisir(self):
        libelles = {"SEULE": "", "VOISINE_ANONYME": ""}
        voisins = {"SEULE": {"VOISINE_ANONYME"}, "VOISINE_ANONYME": {"SEULE"}}

        faites, ambigues, sans = calculer_reparations(libelles, voisins)

        assert faites == [] and ambigues == []
        assert sans == ["SEULE", "VOISINE_ANONYME"]

    def test_une_ref_isolee_reste_a_saisir(self):
        faites, _ambigues, sans = calculer_reparations({"ISOLEE": ""}, {})

        assert faites == []
        assert sans == ["ISOLEE"]

    def test_la_simulation_ne_modifie_pas_son_entree(self):
        """La simulation doit pouvoir tourner sans effet : elle travaille sur une
        copie, sinon relancer le script afficherait un état déjà réparé."""
        libelles = {"ANONYME": "", "NOMMEE": "Ecrou"}
        voisins = {"ANONYME": {"NOMMEE"}, "NOMMEE": {"ANONYME"}}

        calculer_reparations(libelles, voisins)

        assert libelles["ANONYME"] == ""

    def test_les_espaces_comptent_comme_absence_de_libelle(self):
        libelles = {"ESPACES": "   ", "NOMMEE": "Joint de hublot"}
        voisins = {"ESPACES": {"NOMMEE"}, "NOMMEE": {"ESPACES"}}

        # Le chargement nettoie les libellés ; on simule une entrée déjà nettoyée.
        libelles["ESPACES"] = ""
        assert _reparations(libelles, voisins) == {"ESPACES": "Joint de hublot"}


class TestChargerVoisinage:
    """Le voisinage est symétrique : le libellé peut voyager dans les deux sens
    d'une succession comme d'une équivalence."""

    @pytest.fixture
    def conn(self, tmp_path):
        import sqlite3
        chemin = tmp_path / "voisinage.db"
        c = sqlite3.connect(str(chemin))
        c.row_factory = sqlite3.Row
        c.executescript("""
            CREATE TABLE piece_supersessions (ref_old TEXT PRIMARY KEY, ref_new TEXT);
            CREATE TABLE piece_equivalence_groups (group_id INTEGER, ref_piece TEXT);
        """)
        yield c
        c.close()

    def test_une_supersession_lie_dans_les_deux_sens(self, conn):
        conn.execute("INSERT INTO piece_supersessions VALUES ('ANCIENNE', 'NOUVELLE')")

        voisins = charger_voisinage(conn)

        assert voisins["ANCIENNE"] == {"NOUVELLE"}
        assert voisins["NOUVELLE"] == {"ANCIENNE"}

    def test_un_groupe_d_equivalence_lie_tous_ses_membres(self, conn):
        conn.executemany("INSERT INTO piece_equivalence_groups VALUES (?, ?)",
                         [(1, "A"), (1, "B"), (1, "C")])

        voisins = charger_voisinage(conn)

        assert voisins["A"] == {"B", "C"}
        assert voisins["B"] == {"A", "C"}

    def test_une_supersession_sans_remplacante_ne_lie_rien(self, conn):
        """`ref_new` à NULL signifie « obsolète », pas « remplacée par »."""
        conn.execute("INSERT INTO piece_supersessions VALUES ('OBSOLETE', NULL)")

        assert charger_voisinage(conn) == {}

    def test_groupes_distincts_ne_se_melangent_pas(self, conn):
        conn.executemany("INSERT INTO piece_equivalence_groups VALUES (?, ?)",
                         [(1, "A"), (1, "B"), (2, "X"), (2, "Y")])

        voisins = charger_voisinage(conn)

        assert voisins["A"] == {"B"}
        assert "X" not in voisins["A"]
