"""
Tests — Trois marques au plus, avec virgules, et raccourcissement du title

Décisions client (2026-09-24) :
- 3 marques au plus, séparées par des virgules, dans le title (« A, B, C ») comme
  dans la description (« A, B et C ») ; jusque-là jusqu'à 10 marques collées
  (« Candy Hoover Otsein Haier Philco Zerowatt… ») ;
- title trop long : garder le type d'appareil, raccourcir plutôt le libellé ;
- plus de gabarit « … {marques} {type} ».

Avant, le title était raccourci par abréviations (« lave-ling. », « congélo »),
puis coupé en plein mot (« … cuisinière Bosc ») : sur les fiches réelles, jusqu'à
21 % d'abréviations, 8 % de titles sans marque et 7 % de fins coupées.
"""

import pytest

from src.utils.seo_generator import SEOGenerator

AVEC_POUR = "{reference} {description} pour {type_appareil} {fabricants}"
SANS_POUR = "{reference} {description} {type_appareil} {fabricants}"


@pytest.fixture
def gen():
    return SEOGenerator()


def _title(gen, monkeypatch, gabarit, description, type_appareil, fabricants, reference="R123"):
    monkeypatch.setattr(gen, "_choose_title_template", lambda *a: gabarit)
    return gen.generate_meta_title(reference=reference, description=description,
                                   type_appareil=type_appareil, fabricants=fabricants)


# ── Title ──

def test_title_trois_marques_avec_virgules(gen, monkeypatch):
    r = _title(gen, monkeypatch, SANS_POUR, "Joint", "Four", ["Bosch", "Siemens", "Neff", "Balay", "Viva"])
    assert r['title'] == "R123 Joint four Bosch, Siemens, Neff"
    assert r['info']['fabricants_count'] == 3


def test_title_marque_en_plusieurs_mots_compte_pour_une(gen, monkeypatch):
    r = _title(gen, monkeypatch, SANS_POUR, "Joint", "Four", ["De Dietrich", "Sauter"])
    assert r['title'] == "R123 Joint four De Dietrich, Sauter"
    assert r['info']['fabricants_count'] == 2


def test_title_retire_pour_avant_une_marque(gen, monkeypatch):
    """« pour » est le premier sacrifié, avant toute marque."""
    marques = ["Candy", "Hoover", "Otsein"]
    complet = "46001221 Joint de hublot pour lave-linge Candy, Hoover, Otsein"  # 62 car.
    assert len(complet) == 62
    r = _title(gen, monkeypatch, AVEC_POUR, "Joint de hublot", "Lave-linge", marques, "46001221")
    assert r['title'] == "46001221 Joint de hublot lave-linge Candy, Hoover, Otsein"


def test_title_retire_les_marques_en_partant_de_la_fin(gen, monkeypatch):
    r = _title(gen, monkeypatch, SANS_POUR, "Verrou de porte", "Lave-vaisselle",
               ["Bosch", "Siemens", "Constructa"], "10006917")
    assert r['title'] == "10006917 Verrou de porte lave-vaisselle Bosch, Siemens"


def test_title_raccourcit_le_libelle_et_garde_le_type(gen, monkeypatch):
    """Décision client : le type d'appareil est gardé, le libellé perd des mots
    entiers — et ne se termine pas sur un mot de liaison (« ou »)."""
    r = _title(gen, monkeypatch, AVEC_POUR, "Façade tiroir congélation intermédiaire ou supérieur",
               "Réfrigérateur", ["Siemens", "Bosch"], "11043719")
    assert r['title'] == "11043719 Façade tiroir congélation réfrigérateur Siemens"


def test_libelle_raccourci_ne_finit_pas_sur_un_mot_de_liaison(gen):
    assert gen._libelles_raccourcis("Façade tiroir congélation intermédiaire ou supérieur") == [
        "Façade tiroir congélation intermédiaire",
        "Façade tiroir congélation",
        "Façade tiroir",
        "Façade",
    ]
    assert gen._libelles_raccourcis("Jeu d'injecteurs gaz") == ["Jeu d'injecteurs", "Jeu"]
    assert gen._libelles_raccourcis("Kit de fixation + vis") == ["Kit de fixation", "Kit"]


def test_title_ne_laisse_pas_de_parenthese_ouverte(gen, monkeypatch):
    r = _title(gen, monkeypatch, SANS_POUR, "Résistance chauffante (E1=700W / E2=1800W) double",
               "Sèche-linge", ["Bosch"], "00640673")
    assert r['title'] == "00640673 Résistance chauffante sèche-linge Bosch"


@pytest.mark.parametrize("gabarit", SEOGenerator.META_TITLE_TEMPLATES)
@pytest.mark.parametrize("description,type_appareil,marques,reference", [
    ("Jeu d'injecteurs gaz butane/propane", "Cuisinière", ["Bosch", "Siemens"], "00605691"),
    ("Carte électronique configurée", "Lave-linge", ["Arthur-Martin-Electrolux"], "973914527609015"),
    ("Panier inférieur complet avec roulettes", "Lave-vaisselle", ["Arthur-Martin-Electrolux", "AEG"], "1525606008"),
    ("Faisceau 3 sondes ambiant évaporateur", "Chauffe-eau", ["Atlantic", "Thermor"], "026350"),
])
def test_title_invariants(gen, monkeypatch, gabarit, description, type_appareil, marques, reference):
    """Référence en tête, ≤ 60 caractères, au moins une marque entière, type présent,
    aucune abréviation."""
    t = _title(gen, monkeypatch, gabarit, description, type_appareil, marques, reference)['title']
    assert t.startswith(reference + " ")
    assert len(t) <= 60
    assert t.endswith(marques[0]) or f"{marques[0]}," in t
    assert gen._normalize_type(type_appareil) in t
    for abreviation in ("lave-vais.", "lave-ling.", "sèche-ling.", "frigo", "congélo", "électromén."):
        assert abreviation not in t


def test_title_sans_marque(gen, monkeypatch):
    r = _title(gen, monkeypatch, SANS_POUR, "Joint", "Four", [])
    assert r['title'] == "R123 Joint four"
    assert r['info']['brand_guaranteed'] is False


def test_gabarit_marques_avant_type_retire():
    for gabarit in SEOGenerator.META_TITLE_TEMPLATES:
        assert gabarit.index("{type_appareil}") < gabarit.index("{fabricants}")


# ── Description ──

@pytest.mark.parametrize("marques,attendu", [
    (["Candy"], "Candy"),
    (["Candy", "Hoover"], "Candy et Hoover"),
    (["Candy", "Hoover", "Otsein"], "Candy, Hoover et Otsein"),
    (["Candy", "Hoover", "Otsein", "Haier", "Philco"], "Candy, Hoover et Otsein"),
])
def test_description_trois_marques_au_plus(gen, marques, attendu):
    gabarit = "Lave-linge {fabricants} : {description} {reference} — Chronopost J+1 avant 13h"
    assert gen._select_fabricants_for_description(
        marques, gabarit, "46001221", "votre joint", "lave-linge", 150) == attendu


def test_description_moins_de_marques_si_la_place_manque(gen):
    gabarit = "{description_cap} {reference} pour {type_appareil} {fabricants}"
    libelle = "votre " + "x" * 100
    # place restante : 150 - len(rendu sans marques) = 21 → « Candy et Hoover » (15) tient, pas 3
    assert gen._select_fabricants_for_description(
        ["Candy", "Hoover", "Otsein"], gabarit, "R12345678", libelle, "lave-linge", 150) == "Candy et Hoover"


def test_description_ne_coupe_jamais_une_marque(gen):
    """Avant : « Arthur-Martin-El » quand la marque ne tenait pas en entier."""
    gabarit = "{description_cap} {reference} pour {type_appareil} {fabricants}"
    libelle = "votre " + "x" * 110
    assert gen._select_fabricants_for_description(
        ["Arthur-Martin-Electrolux"], gabarit, "R12345678", libelle, "lave-linge", 150) == ""


def test_description_sans_marque_sans_double_espace(gen, monkeypatch):
    monkeypatch.setattr(gen, "_choose_description_template",
                        lambda *a: "Lave-linge {fabricants} : {description} {reference} — Chronopost")
    texte = gen.generate_meta_description(reference="R1", description="Joint", type_appareil="Lave-linge",
                                          fabricants=[])['description']
    assert texte == "Lave-linge : votre joint R1 — Chronopost"
