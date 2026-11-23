"""
Type « Four combiné micro-ondes » (règles de nomenclature, lot 2, 2026-11-23).

- appellations : « four micro-ondes » ne désigne plus le micro-ondes simple ;
  le nouveau type a son entrée (masculin, « four micro-ondes combiné ») ;
- la config ENREGISTRÉE fait foi sur les défauts : une migration ponctuelle,
  jouée une seule fois, y applique ces deux changements ;
- SEO : segment dédié (sans lui, « Micro-ondes Bosch : … »), normalisation ;
- les autres types ne changent pas.
"""

import copy

from src.core.constants import TypesAppareils
from src.utils.appellations_appareils import (
    CONFIG_PAR_DEFAUT, MIGRATION_FOUR_COMBINE, MIGRATIONS, Appellations, cle_type,
    nettoyer_config,
)
from src.utils.seo_generator import SEOGenerator
from src.utils.titre_produit_generator import TitreProduitGenerator

NOUVEAU = TypesAppareils.FOUR_COMBINE_MICRO_ONDES
CLE = "four combiné micro-ondes"


def _config_enregistree_avant_lot2():
    """Forme de la config de production avant le lot 2 (sans clé « migrations »)."""
    return {
        "actif": True, "part_principal": 50,
        "champs": {"meta_title": True, "meta_description": True},
        "appareils": [
            {"type": "four", "genre": "m", "variantes": []},
            {"type": "micro-ondes", "genre": "m", "variantes": [
                {"terme": "four micro-ondes", "genre": "m", "nature": "synonyme", "actif": True}]},
            {"type": "lavante-séchante", "genre": "f", "variantes": []},
            {"type": "four vapeur", "genre": "m", "variantes": [
                {"terme": "four à vapeur", "genre": "m", "nature": "synonyme", "actif": True}]},
            {"type": "aspirateur", "genre": "m", "variantes": []},
        ],
    }


def _entree(config, type_):
    return next(a for a in config["appareils"] if a["type"] == type_)


# ─── Libellé ────────────────────────────────────────────────────────────────

def test_libelle_exact_decision_d6():
    assert NOUVEAU == "Four combiné micro-ondes"
    assert cle_type(NOUVEAU) == CLE


# ─── Appellations par défaut ────────────────────────────────────────────────

def test_defauts():
    config = nettoyer_config(None)
    micro = _entree(config, "micro-ondes")["variantes"]
    assert [(v["terme"], v["actif"]) for v in micro] == [("four micro-ondes", False)]
    nouveau = _entree(config, CLE)
    assert nouveau["genre"] == "m"
    assert [(v["terme"], v["genre"], v["actif"]) for v in nouveau["variantes"]] == [
        ("four micro-ondes combiné", "m", True)]
    assert config["migrations"] == list(MIGRATIONS)


def test_micro_ondes_ne_devient_plus_four_micro_ondes():
    a = Appellations(dict(CONFIG_PAR_DEFAUT, champs={"meta_title": True, "meta_description": True}))
    termes = {a.choisir("micro-ondes", f"R{i}", "meta_description").terme for i in range(300)}
    assert termes == {"micro-ondes"}


def test_accord_et_variante_du_nouveau_type():
    a = Appellations(None)
    assert a.principal(CLE).avec_article_indefini() == "un four combiné micro-ondes"
    termes = {a.choisir(CLE, f"R{i}", "meta_description").terme for i in range(300)}
    assert termes == {CLE, "four micro-ondes combiné"}


# ─── Migration de la config enregistrée ────────────────────────────────────

def test_migration_config_enregistree():
    config = nettoyer_config(_config_enregistree_avant_lot2())
    assert [(v["terme"], v["actif"]) for v in _entree(config, "micro-ondes")["variantes"]] == [
        ("four micro-ondes", False)]
    types = [a["type"] for a in config["appareils"]]
    # Inséré juste après « four vapeur », le reste dans l'ordre de l'utilisateur
    assert types == ["four", "micro-ondes", "lavante-séchante", "four vapeur", CLE, "aspirateur"]
    assert MIGRATION_FOUR_COMBINE in config["migrations"]
    # Le reste de la config est intact
    assert _entree(config, "four vapeur")["variantes"][0]["actif"] is True
    assert config["champs"] == {"meta_title": True, "meta_description": True}


def test_migration_sans_four_vapeur():
    brute = _config_enregistree_avant_lot2()
    brute["appareils"] = [a for a in brute["appareils"] if a["type"] != "four vapeur"]
    types = [a["type"] for a in nettoyer_config(brute)["appareils"]]
    assert types == ["four", "micro-ondes", CLE, "lavante-séchante", "aspirateur"]


def test_migration_idempotente():
    une_fois = nettoyer_config(_config_enregistree_avant_lot2())
    assert nettoyer_config(copy.deepcopy(une_fois)) == une_fois


def test_migration_ne_rejoue_pas_sur_un_choix_utilisateur():
    """Après migration, l'utilisateur réactive « four micro-ondes » et retire le
    nouveau type : ses choix tiennent au chargement suivant."""
    config = nettoyer_config(_config_enregistree_avant_lot2())
    _entree(config, "micro-ondes")["variantes"][0]["actif"] = True
    config["appareils"] = [a for a in config["appareils"] if a["type"] != CLE]
    relue = nettoyer_config(copy.deepcopy(config))
    assert _entree(relue, "micro-ondes")["variantes"][0]["actif"] is True
    assert CLE not in [a["type"] for a in relue["appareils"]]


def test_migration_garde_une_entree_deja_creee():
    brute = _config_enregistree_avant_lot2()
    brute["appareils"].append({"type": NOUVEAU, "genre": "m", "variantes": [
        {"terme": "combi micro-ondes", "genre": "m"}]})
    config = nettoyer_config(brute)
    entrees = [a for a in config["appareils"] if a["type"] == CLE]
    assert len(entrees) == 1 and entrees[0]["variantes"][0]["terme"] == "combi micro-ondes"


# ─── SEO ────────────────────────────────────────────────────────────────────

def test_normalisation():
    for brut in ("Four combiné micro-ondes", "four combine micro-ondes",
                 "Four combiné micro ondes", " four combine micro ondes "):
        assert SEOGenerator.normaliser_type(brut) == CLE


def test_segment_dedie():
    g = SEOGenerator()
    assert g._segment_templates_for(CLE) == SEOGenerator.SEGMENT_DESCRIPTION_TEMPLATES[CLE]
    # Les autres types gardent leur segment
    assert g._segment_templates_for("micro-ondes") == SEOGenerator.SEGMENT_DESCRIPTION_TEMPLATES["micro-ondes"]
    assert g._segment_templates_for("four") == SEOGenerator.SEGMENT_DESCRIPTION_TEMPLATES["four"]
    assert g._segment_templates_for("four vapeur") == SEOGenerator.SEGMENT_DESCRIPTION_TEMPLATES["four"]


def test_descriptions_jamais_en_micro_ondes():
    g = SEOGenerator()
    for variante in range(60):
        texte = g.generate_meta_description(
            reference="00657225", description="Joint de porte", type_appareil=NOUVEAU,
            fabricants=["Bosch", "Siemens"], n_modeles=40, variante=variante)['description']
        assert not texte.startswith("Micro-ondes"), texte


def test_titre_avec_le_nouveau_type():
    """Libellé plus long : le titre retire une marque avant de couper le type."""
    from src.services.export_config_service import DEFAULT_CONFIG
    profil = {**DEFAULT_CONFIG['titre']['profiles'][0], "max_caracteres": 70}
    r = TitreProduitGenerator().generer(profil, "Joint de porte", [NOUVEAU, "Four"],
                                        ["Bosch", "Siemens", "Neff"], "00657225")
    assert "four combiné micro-ondes" in r["titre"].lower(), r["titre"]
    assert len(r["titre"]) <= 70 and "00657225" in r["titre"], r["titre"]
