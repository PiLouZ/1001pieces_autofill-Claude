"""Bandeau d'équivalence sans doublons avec la chaîne de succession (3.77.0).

En base, les anciennes versions entrent dans le groupe de leur courante
(`_propagate_predecessors_to_group`). Utile pour l'extension des appareils,
mais le bandeau d'équivalence répétait alors la chaîne déjà affichée au-dessus.
Cas réel du 2026-10-08 : C00256552, 482000022012, C00256559 → C00273284,
et C00273284 ≡ 758973779 ≡ 278449.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.ui.table_controller import TableController

ANCIENNES = ["482000022012", "C00256552", "C00256559"]


@pytest.fixture
def db(test_db_manager):
    for old in ANCIENNES:
        assert test_db_manager.add_supersession(old, "C00273284")[0]
    assert test_db_manager.add_equivalence("758973779", "278449")[0]
    assert test_db_manager.add_equivalence("C00273284", "758973779")[0]
    return test_db_manager


class TestGetEquivalentsHorsChaine:
    def test_groupe_complet_en_base(self, db):
        """Pré-condition : le groupe stocké contient bien la chaîne (6 réfs)."""
        assert len(db.get_equivalents("C00273284")) == 5

    def test_courante(self, db):
        assert db.get_equivalents_hors_chaine("C00273284") == ["278449", "758973779"]

    @pytest.mark.parametrize("ancienne", ANCIENNES)
    def test_ancienne_version(self, db, ancienne):
        """Ni la courante ni les sœurs : elles sont dans le bandeau de succession."""
        assert db.get_equivalents_hors_chaine(ancienne) == ["278449", "758973779"]

    def test_cote_equivalente(self, db):
        """Depuis une autre marque : la courante oui, ses anciennes versions non."""
        assert db.get_equivalents_hors_chaine("758973779") == ["278449", "C00273284"]

    def test_ancienne_dont_la_courante_est_hors_groupe_reste_visible(self, test_db_manager):
        """X ≡ A, puis X remplacée par Y qui n'est PAS dans le groupe :
        masquer X rendrait l'équivalence invisible → X reste affichée."""
        assert test_db_manager.add_equivalence("A", "X")[0]
        assert test_db_manager.add_supersession("X", "Y")[0]
        # add_supersession ne propage que vers le groupe de la NOUVELLE réf (Y) :
        # Y reste donc hors du groupe de A.
        assert "Y" not in test_db_manager.get_equivalents("A")
        assert test_db_manager.get_equivalents_hors_chaine("A") == ["X"]

    def test_groupe_d_une_seule_famille(self, test_db_manager):
        """Cas des groupes 22 et 40 en production : rien d'autre que la famille."""
        for old in ("O1", "O2"):
            assert test_db_manager.add_supersession(old, "TETE")[0]
        assert test_db_manager.add_equivalence("O1", "O2")[0]
        assert test_db_manager.get_equivalents("O1")            # groupe non vide…
        assert test_db_manager.get_equivalents_hors_chaine("O1") == []   # …rien à montrer

    def test_sans_groupe(self, test_db_manager):
        assert test_db_manager.get_equivalents_hors_chaine("INCONNUE") == []


def _controleur(db):
    tc = SimpleNamespace(db_manager=db, equivalence_banner=MagicMock(),
                         _equivalence_expand=False, _equivalence_term=None,
                         _equivalence_group=[], _equivalence_display=[],
                         _update_equivalence_banner=MagicMock())
    tc._hide_equivalence_banner = lambda: TableController._hide_equivalence_banner(tc)
    return tc


class TestBandeau:
    def test_affichage_filtre_extension_complete(self, db):
        """Le bandeau montre les 2 vraies équivalentes ; l'extension garde les 5."""
        tc = _controleur(db)
        assert TableController._check_equivalence_banner(tc, "C00273284") is True
        assert tc._equivalence_display == ["278449", "758973779"]
        assert len(tc._equivalence_group) == 5
        assert tc._equivalence_expand is True
        tc.equivalence_banner.setVisible.assert_called_with(True)

    def test_groupe_d_une_seule_famille_cache_le_bandeau(self, test_db_manager):
        for old in ("O1", "O2"):
            test_db_manager.add_supersession(old, "TETE")
        test_db_manager.add_equivalence("O1", "O2")
        tc = _controleur(test_db_manager)
        assert TableController._check_equivalence_banner(tc, "O1") is False
        tc.equivalence_banner.setVisible.assert_called_with(False)
        assert tc._equivalence_display == [] and tc._equivalence_group == []
