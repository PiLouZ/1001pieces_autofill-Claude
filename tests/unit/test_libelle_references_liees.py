"""
Tests — Propagation du libellé aux références liées (« Modifier la pièce »)

Jusqu'en 3.85.0, la case « Appliquer aussi ce libellé » ne visait que les
pièces équivalentes : pour 626 familles de succession sur 722, elle restait
invisible. Cas réel du 2026-10-15 : `00650715` → `00751249`, libellés
« Amortisseur » et « A » — aucun moyen de propager l'un à l'autre.

La case vise désormais toute la lignée (nouvelles, anciennes, autres versions)
plus les équivalentes, et signale les libellés différents qu'elle écraserait.
"""

import pytest

from src.ui import pieces_manager as pm
from src.ui.pieces_manager import (
    PieceEditDialog, PiecesManagerWindow,
    libelles_remplaces, refs_liees_a_plat, resume_references_liees,
)


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


def _pieces(db, **libelles):
    for ref, lib in libelles.items():
        db.create_piece_standalone(ref, lib)


# ── get_references_liees ──────────────────────────────────────────────────────

class TestReferencesLiees:

    def test_aucune_relation(self, db):
        _pieces(db, SEULE="x")
        assert db.get_references_liees("SEULE") == {
            'nouvelles': [], 'anciennes': [], 'autres': [], 'equivalentes': []}

    def test_chaine_simple_depuis_le_milieu(self, db):
        _pieces(db, A="", B="", C="")
        db.add_supersession("A", "B")
        db.add_supersession("B", "C")
        liees = db.get_references_liees("B")
        assert liees['nouvelles'] == ["C"]
        assert liees['anciennes'] == ["A"]
        assert liees['autres'] == []

    def test_branches_paralleles(self, db):
        """X → T et Y → T : depuis X, Y est une autre version de la lignée."""
        _pieces(db, X="", Y="", T="", Z="")
        db.add_supersession("Z", "X")
        db.add_supersession("X", "T")
        db.add_supersession("Y", "T")
        liees = db.get_references_liees("X")
        assert liees['nouvelles'] == ["T"]
        assert liees['anciennes'] == ["Z"]
        assert liees['autres'] == ["Y"]

    def test_equivalentes_hors_famille(self, db):
        """Les anciennes versions entrent dans le groupe d'équivalence de leur
        courante : elles ne doivent pas être comptées deux fois."""
        _pieces(db, OLD="", CUR="", EQ="")
        db.add_supersession("OLD", "CUR")
        db.add_equivalence("CUR", "EQ")
        liees = db.get_references_liees("CUR")
        assert liees['anciennes'] == ["OLD"]
        assert liees['equivalentes'] == ["EQ"]
        a_plat = refs_liees_a_plat(liees)
        assert sorted(a_plat) == ["EQ", "OLD"]
        assert len(a_plat) == len(set(a_plat))

    def test_cas_reel_00650715(self, db):
        _pieces(db, **{"00650715": "Amortisseur", "00751249": "A"})
        db.add_supersession("00650715", "00751249")
        assert refs_liees_a_plat(db.get_references_liees("00650715")) == ["00751249"]


class TestGetDescriptions:

    def test_libelles_nettoyes_et_absentes_ignorees(self, db):
        _pieces(db, R1="  Joint ", R2="")
        assert db.get_descriptions(["R1", "R2", "ABSENTE"]) == {"R1": "Joint", "R2": ""}

    def test_liste_vide(self, db):
        assert db.get_descriptions([]) == {}


# ── Fonctions pures ───────────────────────────────────────────────────────────

class TestResume:

    def test_une_ligne_par_categorie_non_vide(self):
        liees = {'nouvelles': ["N"], 'anciennes': ["A1", "A2"], 'autres': [], 'equivalentes': ["E"]}
        assert resume_references_liees(liees) == [
            "nouvelle référence : N",
            "anciennes références : A1, A2",
            "équivalente : E",
        ]

    def test_grande_famille_tronquee(self):
        refs = [f"R{i:03d}" for i in range(192)]
        ligne = resume_references_liees({'anciennes': refs})[0]
        assert ligne.endswith("… et 184 autres")


class TestLibellesRemplaces:

    def test_vide_rempli_n_est_pas_remplace(self):
        assert libelles_remplaces({"R": ""}, ["R"], "Joint") == []

    def test_identique_n_est_pas_remplace(self):
        assert libelles_remplaces({"R": "Joint"}, ["R"], " Joint ") == []

    def test_different_est_signale(self):
        assert libelles_remplaces({"00751249": "A"}, ["00751249"], "Amortisseur") == [
            ("00751249", "A")]


# ── Fenêtre « Modifier la pièce » ─────────────────────────────────────────────

class TestDialogue:

    def test_case_cachee_sans_reference_liee(self, qapp):
        dlg = PieceEditDialog(None, "SEULE", "x")
        assert dlg.propagate_checkbox.isHidden()

    def test_case_visible_pour_une_succession_seule(self, qapp):
        dlg = PieceEditDialog(None, "00650715", "Amortisseur",
                              {'nouvelles': ["00751249"]}, {"00751249": "A"})
        assert not dlg.propagate_checkbox.isHidden()
        assert dlg.propagate_checkbox.text() == "Appliquer aussi ce libellé à la référence liée"
        assert dlg.detail_label.text() == "nouvelle référence : 00751249"
        assert not dlg.propagate_checkbox.isChecked()          # décochée par défaut

    def test_libelles_remplaces_suivent_la_frappe(self, qapp):
        dlg = PieceEditDialog(None, "00650715", "Amortisseur",
                              {'nouvelles': ["00751249"]}, {"00751249": "A"})
        assert not dlg.remplaces_label.isHidden()
        assert "00751249 « A »" in dlg.remplaces_label.text()
        dlg.desc_input.setText("A")
        assert dlg.remplaces_label.isHidden()


# ── _do_edit_piece de bout en bout ────────────────────────────────────────────

class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, f):
        self.callbacks.append(f)


class _DialogueDouble:
    """Remplace PieceEditDialog : retient ce qu'il reçoit, renvoie `valeurs`."""
    valeurs = None
    dernier = None

    def __init__(self, parent, current_ref, current_desc, liees=None, libelles=None,
                 focus_field='ref'):
        self.liees, self.libelles = liees, libelles
        self.accepted = _Signal()
        _DialogueDouble.dernier = self

    def show(self):
        pass

    def get_values(self):
        return _DialogueDouble.valeurs


class _Historique:
    def __init__(self):
        self.entrees = []

    def add_to_history(self, msg):
        self.entrees.append(msg)


class _Parent:
    def __init__(self):
        self.user_interaction_service = _Historique()


class _Fenetre:
    def __init__(self, db):
        self.db_manager = db
        self._parent = _Parent()

    def parent(self):
        return self._parent

    def _load_pieces_data(self):
        pass


def _editer(db, monkeypatch, ref, desc, valeurs):
    monkeypatch.setattr(pm, "PieceEditDialog", _DialogueDouble)
    _DialogueDouble.valeurs = valeurs
    fenetre = _Fenetre(db)
    PiecesManagerWindow._do_edit_piece(fenetre, ref, desc)
    for cb in _DialogueDouble.dernier.accepted.callbacks:
        cb()
    return fenetre


class TestEditionBoutEnBout:

    def test_propage_a_la_succession(self, db, monkeypatch):
        _pieces(db, **{"00650715": "A", "00751249": "A"})
        db.add_supersession("00650715", "00751249")
        fenetre = _editer(db, monkeypatch, "00650715", "A", ("00650715", "Amortisseur", True))
        assert db.get_descriptions(["00650715", "00751249"]) == {
            "00650715": "Amortisseur", "00751249": "Amortisseur"}
        historique = "\n".join(fenetre.parent().user_interaction_service.entrees)
        assert "1 référence liée → « Amortisseur »" in historique
        assert "nouvelle référence : 00751249" in historique

    def test_libelle_inchange_mais_case_cochee_propage(self, db, monkeypatch):
        """Le cas réel : 00650715 porte déjà « Amortisseur », il faut pouvoir le
        propager à 00751249 sans le retaper."""
        _pieces(db, **{"00650715": "Amortisseur", "00751249": "A"})
        db.add_supersession("00650715", "00751249")
        _editer(db, monkeypatch, "00650715", "Amortisseur", ("00650715", "Amortisseur", True))
        assert db.get_descriptions(["00751249"]) == {"00751249": "Amortisseur"}

    def test_case_decochee_ne_propage_rien(self, db, monkeypatch):
        _pieces(db, OLD="Ancien", CUR="Courant")
        db.add_supersession("OLD", "CUR")
        _editer(db, monkeypatch, "CUR", "Courant", ("CUR", "Nouveau", False))
        assert db.get_descriptions(["OLD", "CUR"]) == {"OLD": "Ancien", "CUR": "Nouveau"}

    def test_toute_la_famille_et_les_equivalentes(self, db, monkeypatch):
        _pieces(db, X="", Y="", T="", Z="", EQ="")
        for old, new in (("Z", "X"), ("X", "T"), ("Y", "T")):
            db.add_supersession(old, new)
        db.add_equivalence("T", "EQ")
        _editer(db, monkeypatch, "X", "", ("X", "Panier", True))
        assert set(db.get_descriptions(["X", "Y", "T", "Z", "EQ"]).values()) == {"Panier"}

    def test_renommage_seul_ne_propage_pas(self, db, monkeypatch):
        _pieces(db, OLD="Ancien", CUR="Courant")
        db.add_supersession("OLD", "CUR")
        _editer(db, monkeypatch, "CUR", "Courant", ("CUR_V2", "Courant", False))
        assert db.get_descriptions(["OLD", "CUR_V2"]) == {"OLD": "Ancien", "CUR_V2": "Courant"}
