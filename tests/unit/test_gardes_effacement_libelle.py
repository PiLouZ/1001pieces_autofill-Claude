"""
Tests — Gardes contre l'effacement d'un libellé (lot 3)

Le gestionnaire de pièces effaçait des libellés sans jamais le demander :
la référence était validée non vide, le libellé ne l'était pas. Valider le
dialogue d'édition avec le champ effacé suffisait à perdre le libellé — et à le
perdre pour tout le groupe si « propager aux équivalents » était coché.
L'harmonisation, elle, proposait « (vide) » comme libellé cible du groupe.

`labels_differ` complétait le tableau : un groupe **entièrement** anonyme ne
produisait qu'un seul libellé distinct ({""}) et passait donc pour cohérent.
Le cas le plus grave était le seul à n'être jamais signalé.
"""

import pytest

from src.ui.pieces_manager import libelles_candidats, libelles_incoherents


class TestLibellesIncoherents:
    """`labels_differ` du gestionnaire — la règle qui décide si le bouton
    « harmoniser » apparaît."""

    def test_groupe_entierement_anonyme_est_signale(self):
        """Le cas qui n'était jamais remonté."""
        assert libelles_incoherents(["", "", None]) is True

    def test_groupe_partiellement_nomme_est_signale(self):
        assert libelles_incoherents(["Pompe de cyclage", ""]) is True

    def test_libelles_divergents_restent_signales(self):
        assert libelles_incoherents(["Pompe", "Pompe de cyclage"]) is True

    def test_groupe_coherent_n_est_pas_signale(self):
        assert libelles_incoherents(["Pompe", "Pompe"]) is False

    def test_les_espaces_ne_font_pas_une_divergence(self):
        """« Pompe » et «  Pompe  » sont le même libellé, pas une incohérence."""
        assert libelles_incoherents(["Pompe", "  Pompe  "]) is False


class TestHarmonisationSansVide:
    """`_on_harmonize_labels` ne doit plus proposer le vide comme cible."""

    def test_le_vide_n_est_pas_un_choix(self):
        assert libelles_candidats(["Pompe de cyclage", "", None]) == ["Pompe de cyclage"]

    def test_un_seul_membre_nomme_donne_un_seul_choix(self):
        """Exactement l'effet recherché : propager le seul libellé disponible."""
        assert len(libelles_candidats(["Carte de puissance", "", ""])) == 1

    def test_groupe_entierement_anonyme_ne_donne_aucun_choix(self):
        """Le bouton reste visible (c'est une incohérence) mais il n'y a rien à
        propager : la méthode informe l'utilisateur au lieu de ne rien faire."""
        assert libelles_candidats(["", None, "   "]) == []

    def test_libelles_divergents_restent_tous_proposes(self):
        assert libelles_candidats(["Pompe", "Pompe de cyclage"]) == ["Pompe", "Pompe de cyclage"]


class TestPropagationDepuisLeGestionnaire:
    """Le picker autorise la saisie d'une réf inexistante, créée en fantôme donc
    anonyme. Les handlers de relation du gestionnaire doivent propager le libellé
    comme le font les chemins d'import depuis le lot 1."""

    @pytest.fixture
    def db(self, test_db_manager):
        return test_db_manager

    def _desc(self, db, ref):
        rows = db.execute_query(
            "SELECT COALESCE(description, '') FROM pieces WHERE ref_piece = ?", [ref]
        )
        return rows[0][0] if rows else None

    def test_supersession_propage(self, db):
        db.create_piece_standalone("EXISTANTE", "Joint de hublot")
        ok, _ = db.add_supersession("EXISTANTE", "SAISIE_AU_PICKER")
        assert ok
        db.propagate_description("EXISTANTE", "SAISIE_AU_PICKER")

        assert self._desc(db, "SAISIE_AU_PICKER") == "Joint de hublot"

    def test_equivalence_propage(self, db):
        db.create_piece_standalone("EXISTANTE", "Sonde CTN")
        ok, _ = db.add_equivalence("EXISTANTE", "SAISIE_AU_PICKER")
        assert ok
        db.propagate_description("EXISTANTE", "SAISIE_AU_PICKER")

        assert self._desc(db, "SAISIE_AU_PICKER") == "Sonde CTN"

    def test_add_equivalence_renvoie_bien_un_tuple(self, db):
        """Le résultat n'était pas déballé dans `_on_add_equivalence` : `success`
        valait le tuple, donc toujours vrai, et les échecs passaient pour des
        succès. Ce test fige le contrat sur lequel repose le déballage."""
        resultat = db.add_equivalence("A", "B")
        assert isinstance(resultat, tuple) and len(resultat) == 2
        assert resultat[0] is True

        echec = db.add_equivalence("C", "C")   # une réf ne s'équivaut pas à elle-même
        assert echec[0] is False
        assert echec[1]                        # un message explique pourquoi
