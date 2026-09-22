"""
Tests — Le libellé importé atteint les pièces fantômes créées à la volée

Quand l'import déclare une relation (succession ou équivalence), la référence
partenaire saisie dans le dialogue n'est pas importée : elle est créée en
« fantôme » par `INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)`,
donc sans description.

`propagate_description` recopie alors le libellé de la pièce importée.
Il n'était branché que sur les deux branches de succession — la branche
équivalence, écrite juste en dessous, l'avait oublié. Le libellé atteignait
donc le fantôme selon le **type de relation déclarée**, jamais selon les données
(défaut remonté par l'utilisateur, corrigé en v3.69.4).

Depuis le lot 1 (2026-09-22), l'héritage passe par `propagate_description`,
bidirectionnelle : voir `test_propagation_libelle_relations.py` pour les
chemins qui ne propageaient rien du tout (socle commun, branche multi-fichiers).
"""

import pytest

from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType,
    LabelConfiguration, FileType,
)

LIBELLE = "Carte de puissance"
REF_IMPORTEE = "IMPORTEE"
CHEMIN = "/tmp/import_fictif.csv"


@pytest.fixture
def manager(qapp, test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _config(**relations):
    fichier = ImportFile(path=CHEMIN, type=FileType.CSV,
                         suggested_reference=REF_IMPORTEE)
    return ImportConfiguration(
        files=[fichier], import_type=ImportType.SINGLE_FILE,
        label_config=LabelConfiguration(),
        individual_references={CHEMIN: REF_IMPORTEE},
        individual_labels={}, **relations
    )


def _appliquer(manager, **relations):
    """Créer la pièce importée avec son libellé, puis appliquer les relations."""
    manager.db_manager.create_piece_standalone(REF_IMPORTEE, LIBELLE)
    manager._apply_succession_from_config(_config(**relations), {})


def _piece(manager, ref):
    """(description, is_phantom) de la pièce, ou None si absente."""
    rows = manager.db_manager.execute_query(
        "SELECT COALESCE(description, ''), COALESCE(is_phantom, 0) "
        "FROM pieces WHERE ref_piece = ?", [ref]
    )
    return (rows[0][0], rows[0][1]) if rows else None


class TestHeritageDuLibelle:
    """Les trois branches de relation doivent se comporter identiquement."""

    def test_equivalence(self, manager):
        """Le cas corrigé : la branche équivalence n'héritait pas."""
        _appliquer(manager, equivalence_ref="EQUIVALENTE")

        piece = _piece(manager, "EQUIVALENTE")
        assert piece is not None, "la pièce fantôme n'a pas été créée"
        description, fantome = piece
        assert fantome == 1, "la référence partenaire doit être un fantôme"
        assert description == LIBELLE

    def test_succession_remplace(self, manager):
        """Garde de non-régression : cette branche fonctionnait déjà."""
        _appliquer(manager, succession_replaces="ANCIENNE")
        assert _piece(manager, "ANCIENNE") == (LIBELLE, 1)

    def test_succession_remplacee_par(self, manager):
        """Garde de non-régression : cette branche fonctionnait déjà."""
        _appliquer(manager, succession_replaced_by="NOUVELLE")
        assert _piece(manager, "NOUVELLE") == (LIBELLE, 1)


class TestGardes:
    """Les garanties portées par le SQL de propagate_description."""

    def test_un_libelle_existant_n_est_jamais_ecrase(self, manager):
        manager.db_manager.create_piece_standalone("EQUIVALENTE", "Son propre libellé")
        _appliquer(manager, equivalence_ref="EQUIVALENTE")

        description, _ = _piece(manager, "EQUIVALENTE")
        assert description == "Son propre libellé"

    def test_rien_a_heriter_si_la_source_n_a_pas_de_libelle(self, manager):
        manager.db_manager.create_piece_standalone(REF_IMPORTEE, "")
        manager._apply_succession_from_config(
            _config(equivalence_ref="EQUIVALENTE"), {}
        )
        description, fantome = _piece(manager, "EQUIVALENTE")
        assert fantome == 1
        assert description == ""

    def test_l_equivalence_est_bien_creee(self, manager):
        """Le correctif ne doit pas perturber la relation elle-même."""
        resultats = {}
        manager.db_manager.create_piece_standalone(REF_IMPORTEE, LIBELLE)
        manager._apply_succession_from_config(
            _config(equivalence_ref="EQUIVALENTE"), resultats
        )
        assert resultats.get('equivalences_created') == 1
