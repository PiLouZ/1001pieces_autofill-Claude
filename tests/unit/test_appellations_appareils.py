"""
Appellations des appareils dans les textes générés (« lave-linge » / « machine à laver »).

Choix fixe par référence, part du terme principal, sous-types désactivés par
défaut, accord un/une, repli sur le type en base quand l'appellation coûterait
une marque ou un mot, et aucun changement sans appellations (zéro régression).
"""

import copy

import pytest

from src.utils.appellations_appareils import (
    Appellations, CONFIG_PAR_DEFAUT, FEMININ, MIGRATIONS, SOUS_TYPE, nettoyer_config,
)
from src.utils.seo_generator import SEOGenerator
from src.utils.titre_produit_generator import TitreProduitGenerator


def _config(**modifs):
    config = copy.deepcopy(CONFIG_PAR_DEFAUT)
    config.update(modifs)
    return config


TOUS_CHAMPS = {"meta_title": True, "meta_description": True}


def _parts(appellations, type_, champ, n=2000):
    comptes = {}
    for i in range(n):
        terme = appellations.choisir(type_, f"REF{i}", champ).terme
        comptes[terme] = comptes.get(terme, 0) + 1
    return {t: c / n for t, c in comptes.items()}


# ─── Choix ───────────────────────────────────────────────────────────────────

def test_choix_fixe_pour_une_reference():
    a = Appellations(None)
    assert len({a.choisir("lave-linge", "00145787", "titre").terme for _ in range(20)}) == 1


def test_part_du_terme_principal_environ_50_pourcent():
    parts = _parts(Appellations(None), "lave-linge", "meta_description")
    assert set(parts) == {"lave-linge", "machine à laver"}
    assert 0.45 < parts["lave-linge"] < 0.55


@pytest.mark.parametrize("part, attendu", [(100, {"lave-linge"}), (0, {"machine à laver"})])
def test_part_extreme(part, attendu):
    assert set(_parts(Appellations(_config(part_principal=part)), "lave-linge", "meta_description")) == attendu


def test_meta_title_garde_le_terme_principal_par_defaut():
    assert set(_parts(Appellations(None), "lave-linge", "meta_title")) == {"lave-linge"}


def test_titre_varie_quand_le_gabarit_le_demande():
    """Le Titre n'a pas de case ici : c'est son gabarit qui décide (cf. TitreProduitService)."""
    assert set(_parts(Appellations(None), "lave-linge", "titre")) == {"lave-linge",
                                                                       "machine à laver"}
    assert set(_parts(Appellations(_config(actif=False)), "lave-linge", "titre")) == {"lave-linge"}


def test_variation_desactivee():
    assert set(_parts(Appellations(_config(actif=False)), "lave-linge", "meta_description")) == {"lave-linge"}


def test_sous_types_desactives_par_defaut():
    chauffage = next(a for a in CONFIG_PAR_DEFAUT["appareils"] if a["type"] == "chauffage")
    sous_types = [v for v in chauffage["variantes"] if v["nature"] == SOUS_TYPE]
    assert {v["terme"] for v in sous_types} == {"radiateur", "sèche-serviette", "accumulateur"}
    assert not any(v["actif"] for v in sous_types)
    assert set(_parts(Appellations(None), "chauffage", "meta_description")) == {
        "chauffage", "appareil de chauffage"}


def test_type_inconnu_ou_sans_variante():
    a = Appellations(None)
    assert a.choisir("tireuse à bière", "R1", "meta_description").terme == "tireuse à bière"
    assert a.choisir("four", "R1", "meta_description").terme == "four"


def test_type_reconnu_apres_normalisation():
    assert Appellations(None).principal("Lave linge").genre == "m"
    assert Appellations(None).principal("HOTTE").genre == FEMININ


def test_champs_independants():
    """Une même fiche peut citer les deux appellations (tirages distincts par champ)."""
    a = Appellations(_config(champs=TOUS_CHAMPS))
    differents = sum(a.choisir("lave-linge", f"R{i}", "titre")
                     != a.choisir("lave-linge", f"R{i}", "meta_description") for i in range(200))
    assert differents > 50


# ─── Nettoyage de la config ──────────────────────────────────────────────────

def test_config_absente_ou_illisible():
    assert nettoyer_config(None) == CONFIG_PAR_DEFAUT
    assert nettoyer_config("n'importe quoi") == CONFIG_PAR_DEFAUT


def test_config_nettoyee():
    config = nettoyer_config({
        "part_principal": "250",
        "champs": {"meta_title": True},
        "appareils": [
            {"type": " Lave linge ", "genre": "f", "variantes": [
                {"terme": "  machine   à laver ", "genre": "f"},
                {"terme": "Machine à laver"},          # doublon
                {"terme": "lave-linge"},               # égal au type
                {"terme": ""},
                {"terme": "lavante", "nature": "inconnue", "actif": 0},
            ]},
            {"type": "lave-linge"},                    # type en double
            {"type": ""},
        ],
        "migrations": list(MIGRATIONS),                # config déjà migrée
    })
    assert config["part_principal"] == 100
    assert config["champs"] == {"meta_title": True, "meta_description": True}
    assert [a["type"] for a in config["appareils"]] == ["lave-linge"]
    variantes = config["appareils"][0]["variantes"]
    assert [v["terme"] for v in variantes] == ["machine à laver", "lavante"]
    assert variantes[1]["nature"] == "synonyme" and variantes[1]["actif"] is False


def test_liste_utilisateur_fait_foi():
    """Un type retiré par l'utilisateur ne revient pas."""
    config = nettoyer_config({"appareils": [{"type": "four", "variantes": []}],
                              "migrations": list(MIGRATIONS)})
    assert [a["type"] for a in config["appareils"]] == ["four"]


# ─── Méta description ────────────────────────────────────────────────────────

CAS = dict(description="Joint de hublot", fabricants=["Candy"], n_modeles=0)


def _descriptions(type_, appellations, n=300):
    gen = SEOGenerator()
    return [gen.generate_meta_description(reference=f"R{i}", type_appareil=type_,
                                          appellations=appellations, **CAS)
            for i in range(n)]


def test_description_cite_les_deux_appellations():
    textes = [r["description"] for r in _descriptions("Lave-linge", Appellations(None))]
    assert any("machine à laver" in t for t in textes)
    assert any("lave-linge" in t.lower() and "machine à laver" not in t for t in textes)


def test_accord_un_une():
    gen = SEOGenerator()
    gabarit = next(g for g in gen.META_DESCRIPTION_TEMPLATES if "{un_type_appareil}" in g)
    textes = [r for r in _descriptions("Lave-linge", Appellations(_config(part_principal=0)))
              if r["info"]["template_used"] == gabarit]
    assert textes and all("une machine à laver" in r["description"] for r in textes)
    textes = [r for r in _descriptions("Hotte", Appellations(_config(actif=False)))
              if r["info"]["template_used"] == gabarit]
    assert textes and all("à une hotte" in r["description"] for r in textes)


def test_sans_appellations_rien_ne_change():
    """Sans appellations (tests, appels historiques) : le type en base, « un » partout."""
    gen = SEOGenerator()
    gabarit = next(g for g in gen.META_DESCRIPTION_TEMPLATES if "{un_type_appareil}" in g)
    textes = [r for r in _descriptions("Hotte", None) if r["info"]["template_used"] == gabarit]
    assert textes and all("à un hotte" in r["description"] for r in textes)


def test_appellation_longue_ne_coute_ni_marque_ni_troncature():
    gen = SEOGenerator()
    kwargs = dict(description="Carte électronique de puissance programmée",
                  type_appareil="Lave-vaisselle", fabricants=["Bosch", "Siemens", "Neff"],
                  n_modeles=1300, anciennes_refs=["A1", "A2"])
    toujours = Appellations(_config(part_principal=0))
    for i in range(300):
        r0 = gen.generate_meta_description(reference=f"R{i}", **kwargs)
        r1 = gen.generate_meta_description(reference=f"R{i}", appellations=toujours, **kwargs)
        if r1["info"]["appellation"] != "lave-vaisselle":
            assert not r1["info"]["truncated"]
            assert len(r1["info"]["anciennes_refs"]) >= len(r0["info"]["anciennes_refs"])


def test_segment_suit_le_type_en_base():
    """Les gabarits de segment (« Lave-linge Candy : … ») restent choisis par le type en base."""
    gen = SEOGenerator()
    toujours = Appellations(_config(part_principal=0))
    for i in range(100):
        r0 = gen.generate_meta_description(reference=f"R{i}", type_appareil="Lave-linge", **CAS)
        r1 = gen.generate_meta_description(reference=f"R{i}", type_appareil="Lave-linge",
                                           appellations=toujours, **CAS)
        assert r0["info"]["nb_variantes"] == r1["info"]["nb_variantes"]


# ─── Méta title et titre de fiche ────────────────────────────────────────────

def test_meta_title_inchange_par_defaut():
    gen = SEOGenerator()
    for i in range(100):
        args = dict(reference=f"R{i}", description="Pompe", type_appareil="Lave-linge",
                    fabricants=["Bosch"])
        assert (gen.generate_meta_title(**args)["title"]
                == gen.generate_meta_title(appellations=Appellations(None), **args)["title"])


def test_meta_title_varie_si_demande_et_tient_en_entier():
    gen = SEOGenerator()
    a = Appellations(_config(part_principal=0, champs=TOUS_CHAMPS))
    r = gen.generate_meta_title(reference="R1", description="Pompe", type_appareil="Lave-linge",
                                fabricants=["Bosch"], appellations=a)
    assert "machine à laver" in r["title"] and not r["info"]["truncated"]
    long = gen.generate_meta_title(reference="R1", description="Carte électronique de puissance "
                                   "programmée et configurée", type_appareil="Lave-vaisselle",
                                   fabricants=["Bosch", "Siemens", "Neff"], appellations=a)
    assert long["info"]["appellation"] == "lave-vaisselle"


PROFIL = {"template": "{libelle} pour {type} {marques} - {reference}", "max_marques": 4,
          "max_types": 3, "max_caracteres": 120}


class _FenetreFactice:
    """Juste ce que TitreProduitService.calculer_titre lit de la fenêtre principale."""

    def __init__(self, service_config):
        class _Seo:
            @staticmethod
            def poids_types_fiche(donnees):
                return {"Lave-linge": 10}

            @staticmethod
            def appellations():
                return Appellations(_config(part_principal=0))
        self.export_config_service = service_config
        self.seo_service = _Seo()


@pytest.mark.parametrize("varier, attendu", [
    (False, "Pompe de vidange pour lave-linge Bosch - 00145787"),
    (True, "Pompe de vidange pour machine à laver Bosch - 00145787"),
])
def test_case_du_gabarit_titre(tmp_path, monkeypatch, varier, attendu):
    from src.services import export_config_service as ecs
    from src.ui.titre_produit_service import TitreProduitService
    monkeypatch.setattr(ecs.ExportConfigService, "_resolve_config_path",
                        staticmethod(lambda: str(tmp_path / "export_config.json")))
    service = ecs.ExportConfigService()
    assert service.get_titre_profile(None)["varier_appareil"] is False
    config = service.get_config()
    config["titre"]["profiles"][0]["varier_appareil"] = varier
    assert service.save_config(config)
    service = ecs.ExportConfigService()
    donnees = {"description": "pompe de vidange", "fabricants": ["Bosch"], "reference": "00145787"}
    resultat, _ = TitreProduitService(_FenetreFactice(service)).calculer_titre(donnees, None)
    assert resultat["titre"] == attendu


def test_titre_varie_si_demande():
    gen = TitreProduitGenerator()
    a = Appellations(_config(part_principal=0, champs=TOUS_CHAMPS))
    r = gen.generer(PROFIL, "pompe de vidange", ["Lave-linge"], ["Bosch", "Siemens"], "00145787",
                    appellations=a)
    assert r["titre"] == "Pompe de vidange pour machine à laver Bosch et Siemens - 00145787"
    assert r["info"]["types_retenus"] == ["lave-linge"]
    assert r["info"]["appellations"] == ["machine à laver"]


def test_titre_sans_appellations_inchange():
    gen = TitreProduitGenerator()
    r = gen.generer(PROFIL, "pompe de vidange", ["Lave-linge"], ["Bosch"], "00145787")
    assert r["titre"] == "Pompe de vidange pour lave-linge Bosch - 00145787"


def test_titre_appellation_ne_coute_pas_de_marque():
    gen = TitreProduitGenerator()
    profil = dict(PROFIL, max_caracteres=len("Pompe pour lave-linge Bosch et Siemens - 00145787"))
    a = Appellations(_config(part_principal=0, champs=TOUS_CHAMPS))
    r = gen.generer(profil, "pompe", ["Lave-linge"], ["Bosch", "Siemens"], "00145787",
                    appellations=a)
    assert r["titre"] == "Pompe pour lave-linge Bosch et Siemens - 00145787"


# ─── Config des exports ──────────────────────────────────────────────────────

def test_config_des_exports(tmp_path, monkeypatch):
    from src.services import export_config_service as ecs
    monkeypatch.setattr(ecs.ExportConfigService, "_resolve_config_path",
                        staticmethod(lambda: str(tmp_path / "export_config.json")))
    service = ecs.ExportConfigService()
    assert service.get_config()["synonymes_appareils"] == CONFIG_PAR_DEFAUT
    config = service.get_config()
    config["synonymes_appareils"]["actif"] = False
    assert service.save_config(config)
    relu = ecs.ExportConfigService()
    assert relu.get_config()["synonymes_appareils"]["actif"] is False
    assert relu.get_appellations().choisir("lave-linge", "R1", "meta_description").terme == "lave-linge"
