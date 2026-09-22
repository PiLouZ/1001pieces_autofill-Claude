"""
Tests — Propagation du libellé entre références liées (lot 1)

Une réf citée dans une relation mais absente de la base est créée en fantôme par
`INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)`, donc **sans
libellé**. Deux chemins d'import s'excluent mutuellement
(`import_manager.py`, if/else) et aucun des deux ne couvrait tous les cas :

- `apply_relations` (socle commun du panneau de relations, v3.72.0) ne propageait
  **rien** ;
- `_apply_succession_from_config` ne propageait que sur sa branche fichier unique,
  jamais sur la branche multi-fichiers ;
- `inherit_phantom_description` n'allait que dans un sens et exigeait
  `is_phantom = 1`, donc ne rattrapait jamais une réf promue par une association
  mais restée anonyme.

Relevé en base le 2026-09-22 : 148 réfs sans libellé, dont 67 fantômes qui avaient
pourtant une voisine nommée.
"""

import pytest

from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType,
    LabelConfiguration, FileType,
)
from src.services.import_relations import (
    Group, CardData, apply_relations, KIND_SUCCESSION, KIND_EQUIVALENCE,
)

LIBELLE = "Carte de puissance"


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


def _desc(db, ref):
    """Libellé de la pièce, ou None si la référence n'existe pas."""
    rows = db.execute_query(
        "SELECT COALESCE(description, '') FROM pieces WHERE ref_piece = ?", [ref]
    )
    return rows[0][0] if rows else None


# ── La primitive ──────────────────────────────────────────────────────────────

class TestPropagateDescription:

    def test_propage_vers_la_ref_anonyme(self, db):
        db.create_piece_standalone("NOMMEE", LIBELLE)
        db.create_piece_standalone("ANONYME", None)

        assert db.propagate_description("NOMMEE", "ANONYME") is True
        assert _desc(db, "ANONYME") == LIBELLE

    def test_propage_dans_l_autre_sens(self, db):
        """Le sens dépend des données, pas de l'ordre des arguments : c'est tout
        l'objet du correctif face à l'ancienne `inherit_phantom_description`."""
        db.create_piece_standalone("ANONYME", None)
        db.create_piece_standalone("NOMMEE", LIBELLE)

        assert db.propagate_description("ANONYME", "NOMMEE") is True
        assert _desc(db, "ANONYME") == LIBELLE
        assert _desc(db, "NOMMEE") == LIBELLE

    def test_n_ecrase_jamais_un_libelle_existant(self, db):
        db.create_piece_standalone("A", LIBELLE)
        db.create_piece_standalone("B", "Son propre libellé")

        assert db.propagate_description("A", "B") is False
        assert _desc(db, "A") == LIBELLE
        assert _desc(db, "B") == "Son propre libellé"

    def test_divergence_journalisee(self, db, caplog):
        """Une nouvelle génération peut changer de nom : on n'écrase pas, mais la
        divergence doit rester repérable après coup."""
        db.create_piece_standalone("A", LIBELLE)
        db.create_piece_standalone("B", "Autre libellé")

        with caplog.at_level("INFO"):
            db.propagate_description("A", "B")

        assert any("divergents" in m for m in caplog.messages), caplog.messages

    def test_deux_refs_anonymes_ne_font_rien(self, db):
        db.create_piece_standalone("A", None)
        db.create_piece_standalone("B", None)

        assert db.propagate_description("A", "B") is False
        assert _desc(db, "A") == ""

    def test_une_piece_promue_sans_libelle_herite_quand_meme(self, db):
        """Le cas que l'ancienne primitive ne pouvait pas traiter : une réf créée
        en fantôme puis promue (is_phantom = 0) par une association, mais toujours
        sans libellé, était exclue par sa clause `is_phantom = 1`."""
        db.create_piece_standalone("PROMUE", None)
        db.execute_custom_query(
            "UPDATE pieces SET is_phantom = 0 WHERE ref_piece = ?", ["PROMUE"]
        )
        db.create_piece_standalone("NOMMEE", LIBELLE)

        assert db.propagate_description("NOMMEE", "PROMUE") is True
        assert _desc(db, "PROMUE") == LIBELLE

    def test_refs_vides_ou_identiques(self, db):
        db.create_piece_standalone("A", LIBELLE)
        assert db.propagate_description("A", "A") is False
        assert db.propagate_description("A", "") is False
        assert db.propagate_description("", "A") is False

    def test_cible_absente_de_la_base(self, db):
        """Si la relation a échoué en amont, la cible n'existe pas : ne pas lever."""
        db.create_piece_standalone("A", LIBELLE)
        assert db.propagate_description("A", "JAMAIS_CREEE") is False


# ── Le socle commun : apply_relations ─────────────────────────────────────────

class TestApplyRelationsPropage:

    def test_lignee_la_courante_hors_lot_herite(self, db):
        """Cas majoritaire en base : la courante citée n'est pas dans le lot, elle
        naît fantôme et restait anonyme alors que le membre porte le nom."""
        db.create_piece_standalone("MEMBRE", LIBELLE)
        groupe = Group(KIND_SUCCESSION, courante="COURANTE", members=["MEMBRE"])

        apply_relations([groupe], [CardData(ref="MEMBRE")], db)

        assert _desc(db, "COURANTE") == LIBELLE

    def test_equivalence_le_membre_anonyme_herite(self, db):
        db.create_piece_standalone("NOMMEE", LIBELLE)
        db.create_piece_standalone("ANONYME", None)
        groupe = Group(KIND_EQUIVALENCE, members=["NOMMEE", "ANONYME"])

        apply_relations([groupe], [CardData(ref="NOMMEE"), CardData(ref="ANONYME")], db)

        assert _desc(db, "ANONYME") == LIBELLE

    def test_carte_remplace_une_ref_base(self, db):
        db.create_piece_standalone("IMPORTEE", LIBELLE)
        cartes = [CardData(ref="IMPORTEE", base_replaces="ANCIENNE")]

        apply_relations([], cartes, db)

        assert _desc(db, "ANCIENNE") == LIBELLE

    def test_relations_toujours_creees(self, db):
        """Le correctif ne doit pas perturber les relations elles-mêmes."""
        db.create_piece_standalone("MEMBRE", LIBELLE)
        groupe = Group(KIND_SUCCESSION, courante="COURANTE", members=["MEMBRE"])

        counts = apply_relations([groupe], [CardData(ref="MEMBRE")], db)

        assert counts == {'successions': 1, 'equivalences': 0,
                          'obsoletes': 1, 'errors': 0}

    def test_db_sans_la_primitive_ne_compte_pas_d_erreur(self):
        """`apply_relations` reçoit son db en duck-typing. Un double qui n'expose
        que les trois primitives de relation ne doit pas voir la propagation
        gonfler `errors` : la relation, elle, a bien été créée."""
        class DbMinimal:
            def __init__(self):
                self.supersessions = []

            def add_supersession(self, old, new):
                self.supersessions.append((old, new))
                return True, ""

            def add_equivalence(self, a, b):
                return True, ""

            def mark_obsolete(self, ref):
                return True

        minimal = DbMinimal()
        counts = apply_relations(
            [Group(KIND_SUCCESSION, courante="C", members=["M"])],
            [CardData(ref="M")], minimal
        )

        assert counts['errors'] == 0
        assert counts['successions'] == 1
        assert minimal.supersessions == [("M", "C")]


# ── L'autre chemin : branche multi-fichiers ───────────────────────────────────

class TestSuccessionMultiFichiers:
    """`_apply_succession_from_config` reste atteignable en multi-fichiers quand
    le panneau de relations est absent — sa branche multi ne propageait rien."""

    @pytest.fixture
    def manager(self, qapp, test_db_manager):
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    def _config(self, refs, **relations):
        fichiers = [ImportFile(path=f"/tmp/f{i}.csv", type=FileType.CSV,
                               suggested_reference=r) for i, r in enumerate(refs)]
        return ImportConfiguration(
            files=fichiers, import_type=ImportType.MULTI_FILE,
            label_config=LabelConfiguration(),
            individual_references={f.path: r for f, r in zip(fichiers, refs)},
            individual_labels={}, **relations
        )

    # Deux fichiers au minimum : `len(config.files) == 1` capte le flux avant la
    # branche multi, même quand l'import_type dit MULTI_FILE.

    def test_succession_multi_propage(self, manager):
        db = manager.db_manager
        db.create_piece_standalone("ANCIENNE", LIBELLE)
        config = self._config(["ANCIENNE", "AUTRE"],
                              succession_current_ref="COURANTE")

        manager._apply_succession_from_config(config, {})

        assert _desc(db, "COURANTE") == LIBELLE

    def test_equivalence_multi_propage(self, manager):
        db = manager.db_manager
        db.create_piece_standalone("EQUIV_A", LIBELLE)
        config = self._config(["EQUIV_A", "AUTRE"],
                              succession_current_ref="PIVOT",
                              equivalence_refs=["EQUIV_A"])

        manager._apply_succession_from_config(config, {})

        assert _desc(db, "PIVOT") == LIBELLE
