"""
Tests — Une méta fixe par référence, et Maj+clic pour une autre formulation

Décision client (2026-09-24) : le gabarit n'est plus tiré au hasard à chaque
clic. Il est choisi à partir de la référence (crc32) : deux clics donnent le même
texte, et régénérer une fiche déjà en ligne ne la change pas. Maj+clic propose
la formulation suivante, sans répétition avant d'avoir fait le tour.
"""

import subprocess
import sys
from collections import Counter

import pytest

from src.utils.seo_generator import SEOGenerator

CAS = dict(description="Joint de hublot", type_appareil="Lave-linge",
           fabricants=["Candy", "Hoover", "Otsein"])


@pytest.fixture
def gen():
    return SEOGenerator()


def test_meme_reference_meme_meta(gen):
    for methode in (gen.generate_meta_title, gen.generate_meta_description):
        textes = {str(methode(reference="46001221", **CAS)) for _ in range(20)}
        assert len(textes) == 1


def test_references_differentes_formulations_variees(gen):
    """Le choix dépend de la référence : sur 200 réfs, les gabarits sont variés."""
    gabarits = Counter(gen.generate_meta_description(reference=f"REF{i}", **CAS)['info']['template_used']
                       for i in range(200))
    assert len(gabarits) >= 15


def test_meta_identique_d_un_lancement_a_l_autre(tmp_path):
    """crc32 et non hash() : hash() d'une chaîne change à chaque lancement de Python."""
    code = ("from src.utils.seo_generator import SEOGenerator as G;"
            "print(G().generate_meta_description(reference='46001221', description='Joint',"
            " type_appareil='Four', fabricants=['Bosch'])['description'])")
    sorties = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env={"PYTHONHASHSEED": graine, "AUTOFILL_LOG_DIR": str(tmp_path)}).stdout
               for graine in ("1", "2", "3")}
    assert len(sorties) == 1 and sorties != {""}


def test_variantes_parcourent_tous_les_gabarits_sans_repetition(gen):
    info = gen.generate_meta_description(reference="46001221", **CAS)['info']
    nb = info['nb_variantes']
    vus = [gen.generate_meta_description(reference="46001221", variante=v, **CAS)['info']['template_used']
           for v in range(nb)]
    assert len(set(vus)) == nb
    # puis on reboucle sur la méta fixe
    assert gen.generate_meta_description(reference="46001221", variante=nb, **CAS)['info']['template_used'] == vus[0]


def test_variantes_du_title(gen):
    titres = [gen.generate_meta_title(reference="10006917", variante=v, description="Verrou de porte",
                                      type_appareil="Lave-vaisselle", fabricants=["Bosch"])['title']
              for v in range(2)]
    assert set(titres) == {"10006917 Verrou de porte lave-vaisselle Bosch",
                           "10006917 Verrou de porte pour lave-vaisselle Bosch"}


def test_gabarits_contextuels_toujours_favorises(gen):
    """Le premier gabarit suit la même loi que l'ancien tirage pondéré : les 2
    gabarits de segment (poids 6 contre 25 génériques de poids 1) sortent en
    tête pour environ 12/37 = 32 % des références."""
    segment = set(SEOGenerator.SEGMENT_DESCRIPTION_TEMPLATES["lave-linge"])
    n = 3000
    part = sum(gen._choose_description_template("lave-linge", 0, None, f"R{i}") in segment
               for i in range(n)) / n
    assert 0.28 < part < 0.37


# ── Interface : Maj+clic ──

class _Fenetre:
    pass


def test_maj_clic_passe_a_la_formulation_suivante():
    from src.ui.seo_service import SEOService
    service = SEOService(_Fenetre())
    assert service._variante('description', 'R1', False) == 0
    assert service._variante('description', 'R1', True) == 1
    assert service._variante('description', 'R1', True) == 2
    assert service._variante('title', 'R1', True) == 1        # compteur propre au title
    assert service._variante('description', 'R2', True) == 1  # et à chaque référence
    assert service._variante('description', 'R1', False) == 0  # clic simple : méta fixe


def test_libelle_de_la_formulation():
    from src.ui.seo_service import SEOService
    assert SEOService._libelle_variante({'variante': 0, 'nb_variantes': 27}) == ""
    assert SEOService._libelle_variante({'variante': 2, 'nb_variantes': 27}) == " [formulation 3/27]"
