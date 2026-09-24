"""
Tests — Classement des marques et du type d'appareil pour les métas SEO

Jusqu'à la v3.73, le « tri par fréquence » des marques ne mesurait pas la
fréquence : la requête renvoyait les couples (type, marque) distincts, si bien
qu'une marque pesait son nombre de TYPES d'appareils, pas son nombre de modèles.
Sur la base réelle, la marque n° 1 n'était celle qui a le plus de modèles que
dans 60 % des fiches (Neff avant Bosch pour une ampoule : 4 622 modèles contre
10 252).

Désormais chaque marque et chaque type pèsent leur nombre de modèles distincts,
calculé sur toute la famille de la référence (elle + ses prédécesseurs). Taper
une ancienne référence donne la même méta que taper la référence courante.
"""

import sqlite3

import pytest

from src.data._db_mixins.supersession import DatabaseSupersessionMixin
from src.ui.seo_service import SEOService


class _BaseMemoire(DatabaseSupersessionMixin):
    """Base SQLite en mémoire avec le schéma minimal utilisé par SEOService."""

    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript("""
            CREATE TABLE pieces (id INTEGER PRIMARY KEY, ref_piece TEXT UNIQUE, description TEXT);
            CREATE TABLE appareils (id INTEGER PRIMARY KEY, type TEXT, manufacturer TEXT);
            CREATE TABLE piece_associations (piece_id INTEGER, appareil_id INTEGER);
            CREATE TABLE piece_supersessions (ref_old TEXT PRIMARY KEY, ref_new TEXT);
        """)
        self.panne = False

    def execute_query(self, query, params=None):
        return self.conn.execute(query, params or []).fetchall()

    def execute_custom_query(self, query, params=None):
        if self.panne and 'appareils' in query:
            raise sqlite3.OperationalError("panne simulée")
        return self.conn.execute(query, params or []).fetchall()

    # ── Remplissage ──
    def piece(self, ref, description="Joint"):
        return self.conn.execute("INSERT INTO pieces (ref_piece, description) VALUES (?, ?)",
                                 [ref, description]).lastrowid

    def modeles(self, ref, type_appareil, marque, nombre):
        """Associe `nombre` nouveaux modèles (type, marque) à la référence."""
        piece_id = self.conn.execute("SELECT id FROM pieces WHERE ref_piece = ?", [ref]).fetchone()[0]
        ids = []
        for _ in range(nombre):
            app_id = self.conn.execute("INSERT INTO appareils (type, manufacturer) VALUES (?, ?)",
                                       [type_appareil, marque]).lastrowid
            self.associer(ref, app_id, piece_id)
            ids.append(app_id)
        return ids

    def associer(self, ref, app_id, piece_id=None):
        if piece_id is None:
            piece_id = self.conn.execute("SELECT id FROM pieces WHERE ref_piece = ?", [ref]).fetchone()[0]
        self.conn.execute("INSERT INTO piece_associations VALUES (?, ?)", [piece_id, app_id])

    def remplace(self, ref_old, ref_new):
        self.conn.execute("INSERT INTO piece_supersessions VALUES (?, ?)", [ref_old, ref_new])


class _Texte:
    def __init__(self, texte=''):
        self.texte = texte

    def text(self):
        return self.texte


class _Tableau:
    """Tableau de résultats : lignes (type, marque) visibles."""

    def __init__(self, lignes=()):
        self.lignes = list(lignes) or [("Four", "Bosch")]

    def rowCount(self):
        return len(self.lignes)

    def isRowHidden(self, row):
        return False

    def item(self, row, col):
        return _Texte(self.lignes[row][col])


class _Fenetre:
    def __init__(self, db, lignes_tableau=()):
        self.db_manager = db
        self.search_input = _Texte()
        self.table = _Tableau(lignes_tableau)


@pytest.fixture
def db():
    return _BaseMemoire()


def _meta(db, recherche, lignes_tableau=()):
    """Données SEO telles que les boutons Méta les calculent (supersession comprise)."""
    fenetre = _Fenetre(db, lignes_tableau)
    fenetre.search_input.texte = recherche
    service = SEOService(fenetre)
    donnees = service._get_current_search_data()
    ref_obsolete = service._resolve_supersession(donnees)
    if ref_obsolete:
        donnees = service._enrich_with_supersession_data(donnees, ref_obsolete)
    return donnees


def test_marque_classee_par_modeles_et_non_par_types(db):
    """Une marque présente sur 3 types avec 1 modèle chacun ne passe plus
    devant une marque présente sur 1 type avec 10 modèles."""
    db.piece("R1")
    db.modeles("R1", "Lave-linge", "Candy", 10)
    for type_appareil in ("Lave-linge", "Sèche-linge", "Lave-vaisselle"):
        db.modeles("R1", type_appareil, "Otsein", 1)

    assert _meta(db, "R1")['fabricants'] == ["Candy", "Otsein"]


def test_type_retenu_couvre_le_plus_de_modeles(db):
    """Le type qui compte le plus de marques ne l'emporte plus sur celui qui
    compte le plus de modèles."""
    db.piece("R1")
    db.modeles("R1", "Cuisinière", "Sauter", 8)
    for marque in ("Bosch", "Neff", "Siemens"):
        db.modeles("R1", "Four", marque, 1)

    assert _meta(db, "R1")['type_appareil'] == "Cuisinière"


def test_modele_commun_a_deux_references_compte_une_fois(db):
    """Un modèle associé à la réf courante ET à son prédécesseur ne compte
    qu'une fois : sinon les marques des chaînes de succession seraient gonflées."""
    db.piece("NEW")
    db.piece("OLD")
    db.remplace("OLD", "NEW")
    communs = db.modeles("NEW", "Four", "Bosch", 3)
    for app_id in communs:
        db.associer("OLD", app_id)
    db.modeles("NEW", "Four", "Siemens", 4)

    service = SEOService(_Fenetre(db))
    poids_types, poids_fabricants = service._compter_appareils(["NEW", "OLD"])
    assert poids_fabricants == {"Bosch": 3, "Siemens": 4}
    assert poids_types == {"Four": 7}


def test_egalite_departagee_par_ordre_alphabetique(db):
    """À nombre de modèles égal, l'ordre ne dépend plus de l'ordre de retour SQL."""
    db.piece("R1")
    db.modeles("R1", "Four", "Whirlpool", 2)
    db.modeles("R1", "Four", "bauknecht", 2)
    db.modeles("R1", "Four", "Candy", 2)

    assert _meta(db, "R1")['fabricants'] == ["bauknecht", "Candy", "Whirlpool"]


def test_ancienne_reference_donne_la_meme_meta_que_la_courante(db):
    """Une fiche produit, une méta : taper l'ancienne réf ou la courante donne
    les mêmes marques, le même type et le même libellé. Avant, seules les
    marques de la réf tapée étaient comptées (900 écarts sur 1 643 en base)."""
    db.piece("NEW", "Joint de porte")
    db.piece("OLD_A", "Joint porte ancien")
    db.piece("OLD_B", "Joint")
    db.remplace("OLD_A", "NEW")
    db.remplace("OLD_B", "NEW")
    db.modeles("NEW", "Cuisinière", "Sauter", 2)
    db.modeles("OLD_A", "Cuisinière", "De Dietrich", 5)
    db.modeles("OLD_B", "Four", "Allenzi", 1)

    courante = _meta(db, "NEW")
    for tapee in ("OLD_A", "OLD_B"):
        ancienne = _meta(db, tapee)
        assert ancienne['reference'] == "NEW"
        for cle in ('fabricants', 'type_appareil', 'description'):
            assert ancienne[cle] == courante[cle], (tapee, cle)
    assert courante['fabricants'] == ["De Dietrich", "Sauter", "Allenzi"]


def test_multi_references_libelle_de_la_reference_choisie(db):
    """« A || B » : les deux réfs désignent une même pièce, leurs marques sont
    mises en commun ; le libellé est celui de la réf choisie, plus celui de A."""
    db.piece("A", "Joint de hublot")
    db.piece("B", "Joint hublot (équivalent)")
    db.modeles("A", "Lave-linge", "Candy", 2)
    db.modeles("B", "Lave-linge", "Hoover", 5)

    fenetre = _Fenetre(db)
    fenetre.search_input.texte = "A || B"
    service = SEOService(fenetre)
    donnees = service._get_current_search_data_for_reference("B")

    assert donnees['reference'] == "B"
    assert donnees['description'] == "Joint hublot (équivalent)"
    assert donnees['fabricants'] == ["Hoover", "Candy"]


def test_repli_sur_le_tableau_si_la_base_echoue(db):
    """Si la requête échoue, chaque ligne visible du tableau pèse un modèle."""
    db.piece("R1")
    db.panne = True
    lignes = [("Four", "Siemens"), ("Four", "Bosch"), ("Hotte", "Bosch"), ("Hotte", "Bosch")]

    donnees = _meta(db, "R1", lignes)
    assert donnees['fabricants'] == ["Bosch", "Siemens"]
    assert donnees['type_appareil'] == "Four"  # égalité 2-2 : ordre alphabétique


def test_aucun_appareil(db):
    """Sans modèle associé : valeurs par défaut inchangées."""
    db.piece("R1")
    donnees = _meta(db, "R1")
    assert donnees['fabricants'] == ["multi-marques"]
    assert donnees['type_appareil'] == "appareil électroménager"


# ── Anciennes références citées dans la description ──
# Décision client (2026-09-24) : toujours citer les anciennes références de la
# fiche, 2 au plus, celles qui ont le plus de modèles compatibles.

def test_anciennes_refs_les_plus_compatibles_d_abord(db):
    db.piece("NEW")
    for ref, nombre in (("OLD_A", 2), ("OLD_B", 9), ("OLD_C", 5), ("OLD_D", 5)):
        db.piece(ref)
        db.remplace(ref, "NEW")
        db.modeles(ref, "Four", "Bosch", nombre)
    db.piece("OLD_E")  # sans aucun modèle
    db.remplace("OLD_E", "OLD_A")  # prédécesseur indirect

    service = SEOService(_Fenetre(db))
    preds = db.get_all_predecessors("NEW")
    assert set(preds) == {"OLD_A", "OLD_B", "OLD_C", "OLD_D", "OLD_E"}
    # 9 modèles, puis égalité 5-5 départagée par ordre alphabétique
    assert service._anciennes_refs_principales(preds) == ["OLD_B", "OLD_C"]


def test_ancienne_ref_sans_piece_en_base_comptee_zero(db):
    db.piece("NEW")
    db.remplace("FANTOME", "NEW")
    service = SEOService(_Fenetre(db))
    assert service._anciennes_refs_principales(["FANTOME"]) == ["FANTOME"]
    assert service._anciennes_refs_principales([]) == []


def test_description_cite_toujours_les_anciennes_refs():
    from src.utils.seo_generator import SEOGenerator
    g = SEOGenerator()
    avec_les_deux = 0
    for variante in range(len(SEOGenerator.META_DESCRIPTION_TEMPLATES_SUPERSESSION)):
        r = g.generate_meta_description(reference="71X1028", description="Joint de porte",
                                        type_appareil="Cuisinière", fabricants=["De Dietrich", "Sauter"],
                                        anciennes_refs=["72X7221", "74X5829", "79X0000"], variante=variante)
        # la plus compatible toujours ; la 2ᵉ si la place le permet ; jamais une 3ᵉ
        assert "72X7221" in r['description'], r['description']
        assert "79X0000" not in r['description']
        assert r['info']['is_supersession']
        avec_les_deux += "anciennes réf. 72X7221 et 74X5829" in r['description']
    assert avec_les_deux >= 4


@pytest.mark.parametrize("anciennes,attendu", [
    ([], ""),
    (["A1"], "ancienne réf. A1"),
    (["A1", "B2"], "anciennes réf. A1 et B2"),
])
def test_formulation_des_anciennes_refs(anciennes, attendu):
    from src.utils.seo_generator import SEOGenerator
    assert SEOGenerator._formuler_anciennes_refs(anciennes) == attendu


def test_une_seule_ancienne_ref_si_deux_ne_laissent_aucune_marque():
    from src.utils.seo_generator import SEOGenerator
    g = SEOGenerator()
    gabarit = SEOGenerator.META_DESCRIPTION_TEMPLATES_SUPERSESSION[3]  # le plus long
    g._choose_description_template = lambda *a: gabarit
    r = g.generate_meta_description(reference="140000210041", description="Vis de pied réglage central",
                                    type_appareil="Lave-vaisselle", fabricants=["Bosch"],
                                    anciennes_refs=["140000210017", "140000210099"])
    assert r['info']['anciennes_refs'] == ["140000210017"]
    assert "Bosch" in r['description']
