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
            CREATE TABLE piece_equivalence_groups (group_id INTEGER, ref_piece TEXT);
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

    def groupe(self, group_id, *refs):
        """Groupe d'équivalence tel que stocké (anciennes versions comprises)."""
        for ref in refs:
            self.conn.execute("INSERT INTO piece_equivalence_groups VALUES (?, ?)", [group_id, ref])


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



# ── Référence introuvable, casse, libellé vide ──
# Décision client (2026-09-24) : bloquer la génération si le libellé est vide ;
# plus de correspondance partielle (LIKE %réf%) ; la référence est toujours
# écrite comme en base.

def test_reference_retrouvee_sans_tenir_compte_de_la_casse(db):
    db.piece("AS0015516", "Filtres à charbon")
    db.modeles("AS0015516", "Hotte", "De Dietrich", 3)
    service = SEOService(_Fenetre(db))
    assert service._trouver_piece("as0015516") == ("AS0015516", "Filtres à charbon")
    donnees = _meta(db, "as0015516")
    assert donnees['reference'] == "AS0015516"
    assert donnees['fabricants'] == ["De Dietrich"]  # avant : « multi-marques », aucune réf agrégée


def test_fragment_de_reference_ne_suffit_plus(db):
    db.piece("AS0015516", "Filtres à charbon")
    service = SEOService(_Fenetre(db))
    assert service._trouver_piece("0015516") is None
    fenetre = _Fenetre(db)
    fenetre.search_input.texte = "0015516"
    assert SEOService(fenetre)._get_current_search_data() is None


def test_casse_ambigue_refusee(db):
    db.piece("ab12", "Joint")
    db.piece("AB12", "Joint")
    service = SEOService(_Fenetre(db))
    assert service._trouver_piece("Ab12") is None
    assert service._trouver_piece("ab12") == ("ab12", "Joint")


def test_libelle_vide_rendu_vide(db):
    """Plus de repli « pièce détachée » : le libellé vide reste vide."""
    db.piece("00614351", "   ")
    db.modeles("00614351", "Lave-linge", "Balay", 2)
    assert _meta(db, "00614351")['description'] == ""


class _Barre:
    def __init__(self):
        self.messages = []

    def showMessage(self, message, duree=0):
        self.messages.append(message)


class _Historique:
    def __init__(self):
        self.messages = []
        self.liens = []

    def add_to_history(self, message, duration_ms=None, lien=None):
        self.messages.append(message)
        self.liens.append(lien)


def _fenetre_avec_retours(db):
    fenetre = _Fenetre(db)
    fenetre.statusbar = _Barre()
    fenetre.user_interaction_service = _Historique()
    return fenetre


def test_generation_bloquee_si_libelle_vide(db):
    """Le refus s'écrit AUSSI dans l'historique des opérations : seul dans la barre
    d'état, en bas à gauche, loin des boutons, il passait inaperçu (signalé par
    l'utilisateur sur AS6018811 : « les boutons ne font rien »)."""
    db.piece("00614351", None)
    db.modeles("00614351", "Lave-linge", "Balay", 2)
    fenetre = _fenetre_avec_retours(db)
    service = SEOService(fenetre)
    assert service._libelle_manquant({'reference': "00614351", 'description': ""}, "title")
    raison = "Libellé manquant pour 00614351 : complétez-le avant de générer la méta"
    assert fenetre.statusbar.messages == [raison]
    assert fenetre.user_interaction_service.messages == [
        f"SEO: Méta titre non généré pour '00614351'\n==> {raison}"]
    # Lien d'action pour compléter le libellé (historique cliquable, ⌘⇧L)
    assert fenetre.user_interaction_service.liens == [
        ("libelle:00614351", "Compléter le libellé de 00614351  (⌘⇧L)")]
    assert not service._libelle_manquant({'reference': "R1", 'description': "Joint"}, "description")
    assert len(fenetre.user_interaction_service.messages) == 1


def test_seul_le_refus_libelle_porte_un_lien(db):
    """Une référence introuvable n'a rien à compléter : pas de lien."""
    fenetre = _fenetre_avec_retours(db)
    fenetre.search_input.texte = "ZZ999"
    SEOService(fenetre)._signaler_absence_de_donnees("title")
    assert fenetre.user_interaction_service.liens == [None]


def test_ancienne_ref_tapee_bloquee_si_la_courante_n_a_pas_de_libelle(db):
    """Une fiche, une méta : le libellé est celui de la référence courante."""
    db.piece("NEW", "")
    db.piece("OLD", "Joint de porte")
    db.remplace("OLD", "NEW")
    db.modeles("NEW", "Four", "Bosch", 1)
    assert _meta(db, "OLD")['description'] == ""


def test_reference_introuvable_signalee(db):
    fenetre = _fenetre_avec_retours(db)
    fenetre.search_input.texte = "ZZ999"
    SEOService(fenetre)._signaler_absence_de_donnees("description")
    assert fenetre.statusbar.messages == ["Référence introuvable telle quelle : ZZ999"]
    assert fenetre.user_interaction_service.messages == [
        "SEO: Méta description non générée pour 'ZZ999'\n==> Référence introuvable telle quelle : ZZ999"]


def test_aucune_recherche_signalee_sans_reference(db):
    fenetre = _fenetre_avec_retours(db)
    SEOService(fenetre)._signaler_absence_de_donnees("title")
    assert fenetre.statusbar.messages == ["Aucune recherche active pour générer le méta titre"]
    assert fenetre.user_interaction_service.messages == [
        "SEO: Méta titre non généré\n==> Aucune recherche active pour générer le méta titre"]


def test_reference_choisie_absente_ne_produit_plus_de_meta_de_secours(db):
    """Avant : « Pièce détachée ZZ999 », « multi-marques », « appareil électroménager »."""
    fenetre = _Fenetre(db)
    fenetre.search_input.texte = "ZZ999"
    assert SEOService(fenetre)._get_current_search_data_for_reference("ZZ999") is None


def test_multi_references_libelle_vide_remplace_par_celui_de_l_autre(db):
    db.piece("A", "Joint de hublot")
    db.piece("B", "")
    db.modeles("A", "Lave-linge", "Candy", 1)
    fenetre = _Fenetre(db)
    fenetre.search_input.texte = "a || b"
    service = SEOService(fenetre)
    assert service._get_multi_reference_terms() == ["A", "B"]
    donnees = service._get_current_search_data_for_reference("B")
    assert donnees['reference'] == "B"
    assert donnees['description'] == "Joint de hublot"


# ── Réfs équivalentes citées dans la description (3.77.0) ──
# Décisions client (2026-10-08) : « réf. équivalente X » ; 2 au plus, les plus
# compatibles ; 1 ancienne + 1 équivalente quand la fiche a les deux ; le compteur
# de modèles inclut les équivalentes.

@pytest.mark.parametrize("anciennes,equivalentes,attendu", [
    ([], ["E1"], "réf. équivalente E1"),
    ([], ["E1", "E2"], "réf. équivalentes E1 et E2"),
    (["A1"], ["E1"], "ancienne réf. A1, réf. équivalente E1"),
    (["A1", "A2"], [], "anciennes réf. A1 et A2"),
    ([], [], ""),
])
def test_formulation_des_refs_liees(anciennes, equivalentes, attendu):
    from src.utils.seo_generator import SEOGenerator
    assert SEOGenerator._formuler_refs_liees(anciennes, equivalentes) == attendu


def test_une_ancienne_et_une_equivalente_quand_la_fiche_a_les_deux():
    from src.utils.seo_generator import SEOGenerator
    g = SEOGenerator()
    for variante in range(len(SEOGenerator.META_DESCRIPTION_TEMPLATES_SUPERSESSION)):
        r = g.generate_meta_description(reference="C00273284", description="Tuyau de vidange",
                                        type_appareil="Lave-vaisselle", fabricants=["Whirlpool"],
                                        anciennes_refs=["C00256559", "C00256552"],
                                        equivalentes=["758973779", "278449"], variante=variante)
        assert r['info']['anciennes_refs'] == ["C00256559"]
        assert r['info']['equivalentes'] == ["758973779"]
        assert "ancienne réf. C00256559, réf. équivalente 758973779" in r['description']
        assert "C00256552" not in r['description'] and "278449" not in r['description']


def test_equivalentes_seules_toujours_citees_deux_au_plus():
    from src.utils.seo_generator import SEOGenerator
    g = SEOGenerator()
    r = g.generate_meta_description(reference="758973779", description="Tuyau de vidange",
                                    type_appareil="Lave-vaisselle", fabricants=["Smeg"],
                                    equivalentes=["C00273284", "278449", "E3"])
    assert r['info']['is_supersession']
    assert "réf. équivalentes C00273284 et 278449" in r['description']
    assert "E3" not in r['description']


def test_autre_gabarit_plutot_que_sacrifier_l_equivalente():
    """Cas réel (34 fiches sur 329) : le gabarit prévu, trop long avec 1 + 1, ne
    laissait la place à aucune marque ; le repli gardait l'ancienne et lâchait
    l'équivalente. Désormais un gabarit suivant qui garde les deux est préféré."""
    from src.utils.seo_generator import SEOGenerator
    g = SEOGenerator()
    gabarit = SEOGenerator.META_DESCRIPTION_TEMPLATES_SUPERSESSION[3]  # le plus long
    g._choose_description_template = lambda *a: gabarit
    r = g.generate_meta_description(reference="00165314", description="Roulette",
                                    type_appareil="Lave-vaisselle", fabricants=["Bosch", "Siemens", "Neff"],
                                    anciennes_refs=["00183955"], equivalentes=["C00666233"])
    assert r['info']['equivalentes'] == ["C00666233"]
    assert r['info']['anciennes_refs'] == ["00183955"]
    assert r['info']['fabricants_used']
    assert r['info']['within_limit']


def test_sans_equivalente_rien_ne_change():
    """Non-régression : equivalentes=None ou [] → même méta qu'avant la 3.77.0."""
    from src.utils.seo_generator import SEOGenerator
    g = SEOGenerator()
    args = dict(reference="140000210041", description="Vis de pied réglage central",
                type_appareil="Lave-vaisselle", fabricants=["Bosch"],
                anciennes_refs=["140000210017", "140000210099"])
    for variante in range(6):
        sans = g.generate_meta_description(variante=variante, **args)['description']
        assert g.generate_meta_description(variante=variante, equivalentes=[], **args)['description'] == sans


class _FenetreComplete(_Fenetre):
    def __init__(self, db):
        super().__init__(db)
        from unittest.mock import MagicMock
        self.statusbar = MagicMock()
        self.user_interaction_service = MagicMock()


def test_service_choisit_les_equivalentes_hors_chaine_et_compte_leurs_modeles(db, qapp):
    """Bout en bout par le bouton : équivalentes hors chaîne, classées par modèles ;
    le compteur inclut les modèles des équivalentes."""
    from PyQt5.QtWidgets import QApplication
    db.piece("COUR", "Tuyau de vidange"); db.modeles("COUR", "Lave-vaisselle", "Whirlpool", 3)
    db.piece("OLD"); db.remplace("OLD", "COUR"); db.modeles("OLD", "Lave-vaisselle", "Whirlpool", 1)
    db.piece("EQ_PETITE"); db.modeles("EQ_PETITE", "Lave-vaisselle", "Smeg", 2)
    db.piece("EQ_GRANDE"); db.modeles("EQ_GRANDE", "Lave-vaisselle", "Smeg", 40)
    db.piece("EQ_MOYENNE"); db.modeles("EQ_MOYENNE", "Lave-vaisselle", "Smeg", 5)
    db.groupe(1, "COUR", "OLD", "EQ_PETITE", "EQ_GRANDE", "EQ_MOYENNE")

    fenetre = _FenetreComplete(db)
    fenetre.search_input.texte = "COUR"
    service = SEOService(fenetre)
    service._get_multi_reference_terms = lambda: []
    service.generate_meta_description()
    info = service.seo_generator.last_generation_info['description']
    assert info['anciennes_refs'] == ["OLD"]
    assert info['equivalentes'] == ["EQ_GRANDE"]          # 1 + 1, la plus compatible
    assert info['n_modeles'] == 3 + 1 + 2 + 40 + 5         # équivalentes comprises
    assert "réf. équivalente EQ_GRANDE" in QApplication.clipboard().text()


# ── Marques et type complétés par les équivalentes (3.77.0) ──
# Décision client (2026-10-08) : citer les marques des réfs équivalentes, EN
# COMPLÉMENT. Essai écarté : fusionner les modèles évinçait les marques de la
# fiche (réf. Bosch ne citant plus que De Dietrich) et changeait le type.

def _donnees_completees(db, ref):
    service = SEOService(_Fenetre(db))
    donnees = service._get_current_search_data_for_reference(ref)
    service._completer_avec_equivalentes(donnees)
    return donnees


def test_marques_des_equivalentes_en_complement(db):
    db.piece("BOSCH_REF"); db.modeles("BOSCH_REF", "Plaque", "Bosch", 5)
    db.piece("EQ"); db.modeles("EQ", "Plaque", "De Dietrich", 500)   # bien plus de modèles
    db.groupe(1, "BOSCH_REF", "EQ")
    d = _donnees_completees(db, "BOSCH_REF")
    assert d['fabricants'] == ["Bosch", "De Dietrich"]   # la marque propre reste en tête
    assert d['type_appareil'] == "Plaque"


def test_type_propre_jamais_remplace(db):
    db.piece("R"); db.modeles("R", "Four", "Bosch", 3)
    db.piece("EQ"); db.modeles("EQ", "Four vapeur", "Brandt", 300)
    db.groupe(1, "R", "EQ")
    assert _donnees_completees(db, "R")['type_appareil'] == "Four"


def test_fiche_sans_appareil_prend_type_et_marques_des_equivalentes(db):
    """Cas réel : 40 fiches « appareil électroménager multi-marques » (filtres à
    charbon 02859394 → « hotte Cooke & Lewis, Cata et GoodHome »)."""
    db.piece("NUE", "Filtres à charbon")
    db.piece("EQ"); db.modeles("EQ", "Hotte", "Cata", 4); db.modeles("EQ", "Hotte", "GoodHome", 2)
    db.groupe(1, "NUE", "EQ")
    d = _donnees_completees(db, "NUE")
    assert d['fabricants'] == ["Cata", "GoodHome"]
    assert d['type_appareil'] == "Hotte"


def test_sans_groupe_rien_ne_change(db):
    db.piece("SEULE"); db.modeles("SEULE", "Four", "Bosch", 3)
    assert _donnees_completees(db, "SEULE")['fabricants'] == ["Bosch"]


def test_anciennes_versions_d_une_equivalente_comptees(db):
    """Le groupe est pris en entier : une ancienne version de l'équivalente apporte
    aussi ses marques (elle équipe les mêmes appareils)."""
    db.piece("R"); db.modeles("R", "Four", "Bosch", 3)
    db.piece("EQ"); db.piece("EQ_OLD"); db.remplace("EQ_OLD", "EQ")
    db.modeles("EQ_OLD", "Four", "Sauter", 2)
    db.groupe(1, "R", "EQ", "EQ_OLD")
    assert _donnees_completees(db, "R")['fabricants'] == ["Bosch", "Sauter"]
