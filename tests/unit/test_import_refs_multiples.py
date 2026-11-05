"""
Tests — Plusieurs références dans les champs de relations de l'import (v3.91.0)

Fichier unique : « Cette réf. remplace » et « est équivalente à » acceptent
plusieurs réfs séparées par un espace, affichées en pastilles (RefChipsInput).
« Est remplacée par » reste limitée à UNE réf : piece_supersessions.ref_old est
clé primaire et add_supersession écrit en INSERT OR REPLACE — une 2ᵉ réf
écraserait la 1re en silence.

Multi-fichiers : chaque cadre (lignée / groupe d'équivalence) accepte des réfs
hors lot tapées au clavier — déjà en base, ou nouvelles (créées en fantôme).
"""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from src.utils.text_utils import decouper_refs
from src.ui.ref_chips_input import RefChipsInput
from src.core.import_manager import ImportManager, ImportConfiguration, ImportFile, ImportType, LabelConfiguration, FileType
from src.ui.fenetre_import import ImportDialog
from src.services.import_relations import (
    KIND_SUCCESSION, KIND_EQUIVALENCE, apply_relations, derive,
)
from src.ui.import_relations_panel import GroupsZone, _est_hors_lot

REF_IMPORTEE = "IMPORTEE"
CHEMIN = "/tmp/import_fictif.csv"


# ── Découpage ────────────────────────────────────────────────────────────────

class TestDecouperRefs:

    def test_espaces_multiples_et_doublons(self):
        assert decouper_refs("  00420214   00427589 00420214 ") == ["00420214", "00427589"]

    def test_collage_multi_lignes(self):
        assert decouper_refs("A\nB\tC") == ["A", "B", "C"]

    def test_vide_et_none(self):
        assert decouper_refs("") == [] and decouper_refs(None) == [] and decouper_refs("   ") == []

    def test_liste_aplatie(self):
        assert decouper_refs(["A B", "C", "A"]) == ["A", "B", "C"]


# ── Widget à pastilles ───────────────────────────────────────────────────────

class TestRefChipsInput:

    def test_espace_cree_une_pastille(self, qapp):
        w = RefChipsInput("aide")
        QTest.keyClicks(w.line_edit, "REF1 REF2 ")
        assert w.refs() == ["REF1", "REF2"]
        assert len(w._pastilles) == 2
        assert w.line_edit.text() == ""

    def test_texte_non_valide_compte_quand_meme(self, qapp):
        """Clic sur « Importer » sans appuyer sur Espace : rien ne se perd."""
        w = RefChipsInput()
        QTest.keyClicks(w.line_edit, "REF1 REF2")
        assert w.refs() == ["REF1", "REF2"]

    def test_collage(self, qapp):
        w = RefChipsInput()
        w.line_edit.setText("A B\nC")
        assert w.refs() == ["A", "B", "C"] and w.line_edit.text() == ""

    def test_doublon_ignore(self, qapp):
        w = RefChipsInput()
        w.add_refs(["A", "B", "A"])
        w.add_refs("B")
        assert w.refs() == ["A", "B"]

    def test_retour_arriere_retire_la_derniere(self, qapp):
        w = RefChipsInput()
        w.add_refs("A B")
        QTest.keyClick(w.line_edit, Qt.Key_Backspace)
        assert w.refs() == ["A"]

    def test_croix_retire(self, qapp):
        w = RefChipsInput()
        w.add_refs("A B C")
        w.remove_ref("B")
        assert w.refs() == ["A", "C"]

    def test_entree_valide_sans_fermer(self, qapp):
        w = RefChipsInput()
        QTest.keyClicks(w.line_edit, "A")
        QTest.keyClick(w.line_edit, Qt.Key_Return)
        assert w.refs() == ["A"] and w.line_edit.text() == ""

    def test_max_une_ref(self, qapp):
        w = RefChipsInput(max_refs=1)
        w.show()
        w.add_refs("A B")
        assert w.refs() == ["A"]
        assert not w.line_edit.isVisible()
        w.remove_ref("A")
        assert w.line_edit.isVisible()
        w.close()

    def test_max_une_ref_texte_en_suspens(self, qapp):
        w = RefChipsInput(max_refs=1)
        w.line_edit.blockSignals(True)
        w.line_edit.setText("A B")
        w.line_edit.blockSignals(False)
        assert w.refs() == ["A"]


# ── Application en base (fichier unique) ─────────────────────────────────────

@pytest.fixture
def manager(qapp, test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _config(**relations):
    fichier = ImportFile(path=CHEMIN, type=FileType.CSV, suggested_reference=REF_IMPORTEE)
    return ImportConfiguration(
        files=[fichier], import_type=ImportType.SINGLE_FILE,
        label_config=LabelConfiguration(),
        individual_references={CHEMIN: REF_IMPORTEE},
        individual_labels={}, **relations)


def _successeur(db, ref_old):
    rows = db.execute_query("SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", [ref_old])
    return rows[0][0] if rows else None


def _groupe(db, ref):
    rows = db.execute_query("SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref])
    return rows[0][0] if rows else None


def _fantome(db, ref):
    rows = db.execute_query("SELECT COALESCE(is_phantom, 0) FROM pieces WHERE ref_piece = ?", [ref])
    return bool(rows and rows[0][0])


class TestApplicationFichierUnique:

    def test_plusieurs_anciennes_remplacees(self, manager):
        db = manager.db_manager
        db.create_piece_standalone(REF_IMPORTEE, "Carte")
        res = {}
        manager._apply_succession_from_config(_config(succession_replaces=["OLD1", "OLD2"]), res)
        assert _successeur(db, "OLD1") == REF_IMPORTEE
        assert _successeur(db, "OLD2") == REF_IMPORTEE
        assert res['succession_created'] == 2
        assert _fantome(db, "OLD1") and _fantome(db, "OLD2")

    def test_plusieurs_equivalentes_meme_groupe(self, manager):
        db = manager.db_manager
        db.create_piece_standalone(REF_IMPORTEE, "Carte")
        res = {}
        manager._apply_succession_from_config(_config(equivalence_ref=["EQ1", "EQ2"]), res)
        gid = _groupe(db, REF_IMPORTEE)
        assert gid is not None and _groupe(db, "EQ1") == gid and _groupe(db, "EQ2") == gid
        assert res['equivalences_created'] == 2

    def test_chaine_a_espaces_compatible(self, manager):
        """Ancienne forme (chaîne) toujours acceptée, découpée sur les espaces."""
        db = manager.db_manager
        db.create_piece_standalone(REF_IMPORTEE, "Carte")
        manager._apply_succession_from_config(_config(succession_replaces="OLD1 OLD2"), {})
        assert _successeur(db, "OLD1") == REF_IMPORTEE == _successeur(db, "OLD2")

    def test_une_seule_ref_inchangee(self, manager):
        db = manager.db_manager
        db.create_piece_standalone(REF_IMPORTEE, "Carte")
        res = {}
        manager._apply_succession_from_config(
            _config(succession_replaces="OLD", succession_replaced_by="NEW", equivalence_ref="EQ"), res)
        assert _successeur(db, "OLD") == REF_IMPORTEE
        assert _successeur(db, REF_IMPORTEE) == "NEW"
        assert _groupe(db, "EQ") == _groupe(db, REF_IMPORTEE) is not None
        assert res == {'succession_created': 2, 'equivalences_created': 1}

    def test_refus_n_empeche_pas_les_suivantes(self, manager):
        """La réf importée elle-même dans la liste : refusée, les autres passent."""
        db = manager.db_manager
        db.create_piece_standalone(REF_IMPORTEE, "Carte")
        res = {}
        manager._apply_succession_from_config(
            _config(succession_replaces=[REF_IMPORTEE, "OLD"]), res)
        assert _successeur(db, "OLD") == REF_IMPORTEE
        assert res['succession_created'] == 1


# ── Collecte dans le dialogue (fichier unique) ───────────────────────────────

class TestCollecteDialogue:

    def test_listes_collectees(self, qapp, test_db_manager):
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        f = ImportFile('/a.csv', FileType.CSV, 'REF_A')
        f.data = [['Référence', 'Type', 'Marque'], ['REF_A', 'Four', 'Bosch']]
        cfg = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg = ImportDialog(None, cfg, im)
        assert isinstance(dlg.succ_replaces_input, RefChipsInput)
        dlg.succ_replaces_input.add_refs("OLD1 OLD2")
        dlg.succ_replaced_by_input.add_refs("NEW1 NEW2")   # max 1 → NEW1 seule
        QTest.keyClicks(dlg.equiv_input.line_edit, "EQ1 EQ2")  # non validé : compte quand même
        out = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg._collecter_relations(out)
        assert out.succession_replaces == ["OLD1", "OLD2"]
        assert out.succession_replaced_by == "NEW1"
        assert out.equivalence_ref == ["EQ1", "EQ2"]
        dlg.close()

    def test_champs_vides_none(self, qapp, test_db_manager):
        im = ImportManager(db_manager=test_db_manager, parent_widget=None)
        f = ImportFile('/a.csv', FileType.CSV, 'REF_A')
        f.data = [['Référence', 'Type', 'Marque'], ['REF_A', 'Four', 'Bosch']]
        cfg = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg = ImportDialog(None, cfg, im)
        out = ImportConfiguration(files=[f], import_type=ImportType.SINGLE_FILE)
        dlg._collecter_relations(out)
        assert out.succession_replaces is None
        assert out.succession_replaced_by is None
        assert out.equivalence_ref is None
        dlg.close()


# ── Multi-fichiers : réfs hors lot dans les cadres ───────────────────────────

def _zone(qapp):
    return GroupsZone(["B1", "B2", "B3"])


def _texts(lst):
    return [lst.item(i).text() for i in range(lst.count())]


class TestRefsHorsLot:

    def test_saisie_ajoute_en_italique(self, qapp):
        z = _zone(qapp)
        box = z.add_group(KIND_SUCCESSION)
        QTest.keyClicks(box.saisie_refs, "OLD1 OLD2 ")
        assert _texts(box.members) == ["OLD1", "OLD2"]
        assert all(_est_hors_lot(box.members.item(i)) for i in range(2))
        assert box.members.item(0).font().italic()
        assert z.refs_hors_lot() == ["OLD1", "OLD2"]
        assert "2 réfs hors lot" in z.recap_label.text()

    def test_ref_du_lot_deplacee_pas_dupliquee(self, qapp):
        z = _zone(qapp)
        box = z.add_group(KIND_SUCCESSION)
        z.ajouter_refs(box, ["B1"])
        assert "B1" not in _texts(z.reservoir)
        assert _texts(box.members) == ["B1"]
        assert not _est_hors_lot(box.members.item(0))

    def test_une_ref_un_cadre(self, qapp):
        z = _zone(qapp)
        b1 = z.add_group(KIND_SUCCESSION)
        b2 = z.add_group(KIND_EQUIVALENCE)
        z.ajouter_refs(b1, ["EXT"])
        z.ajouter_refs(b2, ["EXT"])
        assert _texts(b1.members) == [] and _texts(b2.members) == ["EXT"]

    def test_vider_n_envoie_pas_au_reservoir(self, qapp):
        z = _zone(qapp)
        box = z.add_group(KIND_SUCCESSION)
        z.ajouter_refs(box, ["B1", "EXT"])
        z._empty_box(box)
        assert sorted(_texts(z.reservoir)) == ["B1", "B2", "B3"]
        assert z.refs_hors_lot() == []

    def test_supprimer_cadre(self, qapp):
        z = _zone(qapp)
        box = z.add_group(KIND_EQUIVALENCE)
        z.ajouter_refs(box, ["B2", "EXT"])
        z._remove_box(box)
        assert sorted(_texts(z.reservoir)) == ["B1", "B2", "B3"]

    def test_depot_reservoir_purge(self, qapp):
        z = _zone(qapp)
        box = z.add_group(KIND_SUCCESSION)
        z.ajouter_refs(box, ["EXT"])
        # Simule le glisser : l'item (et son marqueur) arrive dans le réservoir
        z.reservoir.addItem(box.members.takeItem(0))
        z.reservoir.dropped.emit()
        assert "EXT" not in _texts(z.reservoir)

    def test_groupes_et_application_en_base(self, qapp, test_db_manager):
        z = _zone(qapp)
        lignee = z.add_group(KIND_SUCCESSION)
        lignee.courante_input.setText("B3")
        z.ajouter_refs(lignee, ["B1", "OLD_EXT"])
        equiv = z.add_group(KIND_EQUIVALENCE)
        z.ajouter_refs(equiv, ["B2", "EQ_EXT"])
        groups = z.groups()
        counts = apply_relations(groups, [], test_db_manager)
        assert counts['errors'] == 0
        assert _successeur(test_db_manager, "OLD_EXT") == "B3"
        assert _successeur(test_db_manager, "B1") == "B3"
        assert _fantome(test_db_manager, "OLD_EXT")
        assert _groupe(test_db_manager, "EQ_EXT") == _groupe(test_db_manager, "B2") is not None

    def test_derive_signale_fantomes(self):
        from src.services.import_relations import Group
        g = Group(kind=KIND_SUCCESSION, courante="B3", members=["B1", "NOUVELLE", "EN_BASE"])
        d = derive([g], [], lot_refs={"B1", "B3"}, base_refs={"EN_BASE"})
        assert d.phantoms == {"NOUVELLE"}
        assert d.obsoletes == {"B1", "NOUVELLE", "EN_BASE"}


class TestHauteurPastilles:
    """v3.91.1 : en réel, dialogue à hauteur contrainte → cadre écrasé, pastilles
    rognées et champ de saisie disparu. La hauteur suit désormais la disposition
    et la politique verticale est fixe (incompressible)."""

    def test_politique_verticale_fixe(self, qapp):
        from PyQt5.QtWidgets import QSizePolicy
        w = RefChipsInput()
        assert w.sizePolicy().verticalPolicy() == QSizePolicy.Fixed

    def test_une_ligne_puis_plusieurs(self, qapp):
        w = RefChipsInput()
        vide = w.heightForWidth(600)
        w.add_refs("C00268319 482000023099")
        une_ligne = w.heightForWidth(600)
        assert une_ligne < vide + 10                  # pastilles + champ sur une ligne
        w.add_refs(" ".join(f"REF{i:03d}" for i in range(40)))
        assert w.heightForWidth(600) > 2 * vide       # plusieurs lignes
        assert w.heightForWidth(300) > w.heightForWidth(600)

    def test_pastilles_jamais_rognees(self, qapp):
        w = RefChipsInput()
        w.resize(600, 10)
        w.add_refs(" ".join(f"REF{i:03d}" for i in range(40)))
        w.show()
        w.resize(600, w.heightForWidth(600))
        for p in w._pastilles:
            assert p.height() == p.sizeHint().height()
            assert p.geometry().bottom() < w.height()
        w.close()
