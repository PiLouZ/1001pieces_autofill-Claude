"""
Tests — Aucune promesse contraire aux conditions de vente dans les métas

Décisions du client (2026-09-24) :
- aucune donnée de stock : jamais « en stock » ni « disponible » ;
- pièces d'origine OU de qualité équivalente : jamais « d'origine » seul, et
  pas le jargon « OEM » ;
- pas de « réparateur agréé », de « retour facile » (le retour est à la charge
  du client), ni de « sans faire appel à un technicien » (pas d'aide au diagnostic) ;
- pas de garantie ;
- expédition le jour même si la COMMANDE est passée avant 15h — et non
  « expédition avant 15h ».

L'audit SEO mesurait 13,6 % de descriptions avec « d'origine »/« OEM » non
nuancé, 12,1 % affirmant un stock, 2,3 % « réparateur agréé »…
"""

import re

import pytest

from src.utils.seo_generator import SEOGenerator

MOTS_INTERDITS = [
    r"\ben stock\b",
    r"\bdisponible",
    r"\bOEM\b",
    r"réparateur agréé",
    r"retour facile",
    r"technicien",
    r"facilement",
    r"gratuit",
    r"garanti",
    r"expédi\w* avant 15h",
]


def _tous_les_gabarits():
    g = SEOGenerator
    gabarits = list(g.META_DESCRIPTION_TEMPLATES)
    gabarits += g.META_DESCRIPTION_TEMPLATES_COMPAT
    gabarits += g.META_DESCRIPTION_TEMPLATES_SUPERSESSION
    for par_segment in g.SEGMENT_DESCRIPTION_TEMPLATES.values():
        gabarits += par_segment
    gabarits += g.META_TITLE_TEMPLATES
    return gabarits


def _violations(texte):
    trouves = [m for m in MOTS_INTERDITS if re.search(m, texte, re.IGNORECASE)]
    if re.search(r"d'origine", texte) and "d'origine ou de qualité équivalente" not in texte:
        trouves.append("« d'origine » sans nuance")
    if "15h" in texte and "commande avant 15h, expédition le jour même" not in texte:
        trouves.append("formule 15h inexacte")
    return trouves


@pytest.mark.parametrize("gabarit", _tous_les_gabarits())
def test_gabarit_conforme(gabarit):
    assert _violations(gabarit) == []


@pytest.mark.parametrize("gabarit", _tous_les_gabarits())
def test_gabarit_se_remplit(gabarit):
    """Chaque gabarit n'utilise que des champs connus du générateur."""
    gabarit.format(description="le joint", description_cap="Le joint", reference="R1",
                   type_appareil="four", fabricants="Bosch", anciennes_refs="ancienne réf. R0")


def test_descriptions_generees_conformes():
    """De bout en bout, y compris les gabarits contextuels (segment, forte
    compatibilité, supersession) et la troncature."""
    g = SEOGenerator()
    cas = [
        ("Joint de hublot", "Lave-linge", ["Candy", "Hoover", "Otsein"], 1200, None),
        ("Verrou de porte", "Lave-vaisselle", ["Bosch", "Siemens"], 5, ["00636708", "00652509"]),
        ("Thermostat", "Four", ["Faure"], 30, None),
        ("Filtre à charbon", "Hotte", ["De Dietrich"], 3, None),
    ]
    for description, type_appareil, fabricants, n_modeles, anciennes in cas:
        # Toutes les formulations possibles pour ce cas (la méta est fixe par
        # référence ; les variantes parcourent tout le pool de gabarits)
        for variante in range(60):
            texte = g.generate_meta_description(
                reference="REF123", description=description, type_appareil=type_appareil,
                fabricants=fabricants, n_modeles=n_modeles, anciennes_refs=anciennes, variante=variante,
            )['description']
            assert _violations(texte) == [], texte


@pytest.mark.parametrize("cle,gabarits", SEOGenerator.SEGMENT_DESCRIPTION_TEMPLATES.items())
def test_segments_sans_accroche_symptome(cle, gabarits):
    """Décision client : plus d'accroche symptôme (« Ne vidange plus ? »). Elle
    dépendait de l'appareil et non de la pièce — « Ne vidange plus ? » sur un
    verrou de porte — et ressemblait à un conseil de diagnostic. Chaque gabarit
    de segment nomme l'appareil en tête, sans question."""
    for gabarit in gabarits:
        assert "?" not in gabarit, gabarit
        tete = gabarit.split(":")[0].lower()
        assert cle in tete or "{type_appareil}" in tete, gabarit
