"""
Tests — Métas réglées sur la largeur affichée par Google sur ordinateur

Décision client (2026-09-24) : régler la longueur sur l'affichage ordinateur.
Google coupe à la largeur en pixels (≈ 580 px le title en Arial 20, ≈ 920 px la
description en Arial 14), pas au nombre de caractères. Avec l'ancienne limite
de 150 caractères, 18 % des descriptions réelles débordaient encore.

Quand le gabarit prévu ne laisse la place à aucune marque ou oblige à couper la
phrase (« … compatible avec plus de 200 »), le suivant dans l'ordre propre à la
référence est pris : le résultat reste fixe pour une référence.
"""

import pytest

from src.utils.largeur_texte import largeur_px
from src.utils.seo_generator import SEOGenerator


# ── Mesure ──

def test_largeur_d_un_title_reel():
    """Valeur mesurée par le moteur de rendu (PIL) sur Arial.ttf : 569 px."""
    assert largeur_px("46001221 Joint de hublot pour lave-linge Candy, Hoover, Otsein", 20) == \
        pytest.approx(569.3, abs=0.5)


def test_retient_le_rendu_le_plus_large():
    """À 14 px, les avances arrondies au pixel (rendu hinté) donnent 918 px là où
    les positions fractionnaires donnent 898,5 px : on retient 918."""
    texte = ("Votre verrou de porte 10006917 pour lave-vaisselle Bosch, Siemens et Neff, "
             "anciennes réf. 00630628 et 00623848 — Chronopost J+1 avant 13h")
    assert largeur_px(texte, 14) == 918


def test_w_plus_large_que_i():
    assert largeur_px("W", 20) > 3 * largeur_px("i", 20)


def test_caractere_inconnu_compte_pour_un_n():
    assert largeur_px("中", 20) == largeur_px("n", 20)


# ── Générateur ──

@pytest.fixture
def gen():
    return SEOGenerator()


def test_description_raccourcie_sans_ponctuation_pendante(gen):
    texte = "Votre joint 123 pour lave-linge Candy — " + "commande avant 15h, expédition le jour même " * 5
    court = gen._smart_truncate_description(texte.strip(), 155)
    assert gen._tient_description(court, 155)
    assert court[-1] not in "—–-,:; "


def test_gabarit_suivant_si_le_prevu_ne_laisse_pas_de_marque(gen, monkeypatch):
    """Le gabarit imposé, trop long, ne laisse la place à aucune marque : un autre,
    qui tient avec une marque et sans couper la phrase, est pris."""
    trop_long = ("{description_cap} {reference} pour {type_appareil} {fabricants} — "
                 + "commande avant 15h, expédition le jour même, " * 3 + "retrait en magasin")
    monkeypatch.setattr(gen, "_choose_description_template", lambda *a: trop_long)
    r = gen.generate_meta_description(reference="46001221", description="Joint de hublot",
                                      type_appareil="Lave-linge", fabricants=["Candy", "Hoover"])
    assert r['info']['template_used'] != trop_long
    assert "Candy" in r['description']
    assert not r['info']['truncated']
    assert r['info']['within_limit']


def test_description_reelle_dans_la_largeur(gen):
    for variante in range(40):
        r = gen.generate_meta_description(
            reference="10006917", description="Verrou de porte", type_appareil="Lave-vaisselle",
            fabricants=["Bosch", "Siemens", "Neff"], n_modeles=104366,
            anciennes_refs=["00630628", "00623848"], variante=variante)
        assert largeur_px(r['description'], 14) <= SEOGenerator.DESCRIPTION_MAX_PX
        assert len(r['description']) <= SEOGenerator.DESCRIPTION_MAX_CARACTERES
        assert r['info']['fabricants_used']
        assert "00630628" in r['description']
