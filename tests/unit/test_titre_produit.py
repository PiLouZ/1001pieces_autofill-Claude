"""
Tests — Titre de fiche produit (bouton « Titre », v3.99.0)

« {libelle} pour {type} {marques} - {reference} » : libellé et référence jamais
coupés, marques puis types retirés en partant de la fin pour tenir dans la
longueur maximale, types cités s'ils pèsent à peu près autant que le premier.
"""

import copy

import pytest

from src.services.export_config_service import DEFAULT_CONFIG, ExportConfigService
from src.ui.seo_service import SEOService
from src.ui.titre_produit_service import TitreProduitService
from src.utils.titre_produit_generator import TitreProduitGenerator

from tests.unit.test_seo_classement_marques import _BaseMemoire, _fenetre_avec_retours

PROFIL = DEFAULT_CONFIG['titre']['profiles'][0]


@pytest.fixture
def gen():
    return TitreProduitGenerator()


def _titre(gen, libelle="pompe de vidange", types=("lave-linge",), marques=("Bosch",),
           reference="00145787", **reglages):
    profil = {**PROFIL, **reglages}
    return gen.generer(profil, libelle, list(types), list(marques), reference)


# ─── Générateur ─────────────────────────────────────────────────────────────

def test_structure_par_defaut(gen):
    r = _titre(gen, marques=["Bosch", "Siemens", "Neff"])
    assert r['titre'] == "Pompe de vidange pour lave-linge Bosch, Siemens et Neff - 00145787"
    assert r['longueur'] == len(r['titre'])
    assert not r['info']['raccourci']


def test_quatre_marques_au_plus(gen):
    r = _titre(gen, marques=["Bosch", "Siemens", "Neff", "Gaggenau", "Balay", "Viva"])
    assert r['info']['marques_retenues'] == ["Bosch", "Siemens", "Neff", "Gaggenau"]
    assert r['info']['nb_marques_disponibles'] == 6
    assert "Balay" not in r['titre'] and "autres" not in r['titre']


def test_longueur_retire_les_marques_puis_les_types(gen):
    marques = ["Bosch", "Siemens", "Neff", "Gaggenau"]
    types = ["lave-linge", "lave-linge séchant"]
    complet = _titre(gen, types=types, marques=marques, max_caracteres=0)['titre']
    r = _titre(gen, types=types, marques=marques, max_caracteres=len(complet) - 1)
    assert r['info']['marques_retenues'] == ["Bosch", "Siemens", "Neff"]
    assert r['info']['types_retenus'] == types
    assert r['info']['raccourci']

    tres_court = _titre(gen, types=types, marques=marques, max_caracteres=10)
    assert tres_court['titre'] == "Pompe de vidange pour lave-linge Bosch - 00145787"
    assert not tres_court['info']['dans_la_limite']


def test_libelle_et_reference_jamais_coupes(gen):
    libelle = "Carte électronique de commande programmée avec logiciel d'origine"
    r = _titre(gen, libelle=libelle, marques=["Bosch", "Siemens"], max_caracteres=40)
    assert r['titre'].startswith(libelle) and r['titre'].endswith("- 00145787")


def test_sans_limite(gen):
    marques = [f"Marque{i}" for i in range(10)]
    r = _titre(gen, marques=marques, max_caracteres=0, max_marques=10)
    assert len(r['info']['marques_retenues']) == 10 and r['info']['dans_la_limite']


def test_separateurs_et_gabarit_libres(gen):
    r = _titre(gen, marques=["Bosch", "Siemens", "Neff"], separateur=" / ",
               dernier_separateur=" / ", template="{reference} | {libelle} {marques} ({type})")
    assert r['titre'] == "00145787 | Pompe de vidange Bosch / Siemens / Neff (lave-linge)"


def test_champs_vides_et_multi_marques(gen):
    r = _titre(gen, marques=["multi-marques"])
    assert r['titre'] == "Pompe de vidange pour lave-linge - 00145787"


def test_normalisations_partagees_avec_les_metas(gen):
    r = _titre(gen, libelle="JOINT DE PORTE", types=["Lave Linge"],
               marques=["Arthur-Martin-Electrolux", "Arthur-Martin-Electrolux"])
    assert r['titre'] == "Joint de porte pour lave-linge Arthur Martin - 00145787"


def test_types_proches():
    tp = TitreProduitGenerator.types_proches
    assert tp({"Lave-linge": 100, "Sèche-linge": 80, "Four": 79}, 3) == ["Lave-linge", "Sèche-linge"]
    assert tp({"Lave-linge": 100, "Sèche-linge": 100, "Lave-vaisselle": 95}, 2) == \
        ["Lave-linge", "Sèche-linge"]
    assert tp({"Four": 3}, 3) == ["Four"]
    assert tp({}, 3) == []


def test_deux_types_joints(gen):
    r = _titre(gen, types=["Lave-linge", "Sèche-linge"], marques=["Candy"])
    assert r['titre'] == "Pompe de vidange pour lave-linge et sèche-linge Candy - 00145787"


# ─── Configuration ──────────────────────────────────────────────────────────

def _service(tmp_path, contenu=None):
    import json
    chemin = tmp_path / "export_config.json"
    if contenu is not None:
        chemin.write_text(json.dumps(contenu), encoding='utf-8')
    svc = ExportConfigService.__new__(ExportConfigService)
    svc._config = {}
    svc._config_path = str(chemin)
    svc._load()
    return svc


def test_config_ancienne_sans_section_titre(tmp_path):
    """Une config d'avant la 3.99 garde ses réglages et reçoit le gabarit par défaut."""
    ancienne = copy.deepcopy(DEFAULT_CONFIG)
    del ancienne['titre']
    ancienne['csv']['separator'] = ","
    svc = _service(tmp_path, ancienne)
    assert svc.get_config()['csv']['separator'] == ","
    assert svc.get_titre_profile_names() == ["Format standard"]
    assert svc.get_titre_profile()['template'] == PROFIL['template']


def test_config_profils_valides_et_completes(tmp_path):
    svc = _service(tmp_path, {'titre': {
        'profiles': [{'name': "Court", 'max_marques': "2"}, {'pas_de_nom': 1},
                     {'name': "Long", 'max_caracteres': "n'importe quoi"}],
        'default_profile': "Long"}})
    assert svc.get_titre_profile_names() == ["Court", "Long"]
    assert svc.get_default_titre_profile_name() == "Long"
    assert svc.get_titre_profile("Court")['max_marques'] == 2
    assert svc.get_titre_profile("Court")['template'] == PROFIL['template']
    assert svc.get_titre_profile("Long")['max_caracteres'] == PROFIL['max_caracteres']
    assert svc.get_titre_profile("Inconnu")['name'] == "Long"


def test_config_defaut_inconnu(tmp_path):
    svc = _service(tmp_path, {'titre': {'profiles': [{'name': "A"}], 'default_profile': "Z"}})
    assert svc.get_default_titre_profile_name() == "A"


# ─── Service (bouton Titre) ─────────────────────────────────────────────────

class _PressePapiers:
    texte = None

    def setText(self, texte):
        _PressePapiers.texte = texte


@pytest.fixture
def presse_papiers(monkeypatch):
    import src.ui.titre_produit_service as module
    monkeypatch.setattr(module.QApplication, "clipboard", staticmethod(lambda: _PressePapiers()))
    _PressePapiers.texte = None
    return _PressePapiers


def _fenetre(db, recherche):
    fenetre = _fenetre_avec_retours(db)
    fenetre.search_input.texte = recherche
    fenetre.seo_service = SEOService(fenetre)
    return fenetre


def test_titre_reference_la_plus_recente_et_lignee(presse_papiers):
    db = _BaseMemoire()
    db.piece("NEW", "pompe de vidange")
    db.piece("OLD", "Ancien libellé")
    db.remplace("OLD", "NEW")
    db.modeles("NEW", "Lave-linge", "Bosch", 10)
    db.modeles("OLD", "Lave-linge séchant", "Siemens", 9)
    db.modeles("OLD", "Four", "Neff", 2)
    fenetre = _fenetre(db, "OLD")
    TitreProduitService(fenetre).generer_titre()
    assert presse_papiers.texte == \
        "Pompe de vidange pour lave-linge et lave-linge séchant Bosch, Siemens et Neff - NEW"
    assert "Supersédée → NEW" in fenetre.statusbar.messages[-1]
    assert fenetre.user_interaction_service.messages[-1].startswith(
        "Titre: fiche 'NEW' (remplace OLD)")


def test_titre_refuse_sans_libelle(presse_papiers):
    db = _BaseMemoire()
    db.piece("R1", "")
    db.modeles("R1", "Four", "Bosch", 1)
    fenetre = _fenetre(db, "R1")
    TitreProduitService(fenetre).generer_titre()
    assert presse_papiers.texte is None
    assert fenetre.statusbar.messages == [
        "Libellé manquant pour R1 : complétez-le avant de générer le titre"]
    assert fenetre.user_interaction_service.messages[0].startswith(
        "Titre: Titre de fiche non généré pour 'R1'")


def test_titre_profil_choisi(presse_papiers, tmp_path):
    db = _BaseMemoire()
    db.piece("R1", "joint")
    db.modeles("R1", "Four", "Bosch", 1)
    fenetre = _fenetre(db, "R1")
    fenetre.export_config_service = _service(tmp_path, {'titre': {'profiles': [
        {'name': "Standard"}, {'name': "Réf d'abord", 'template': "{reference} {libelle}"}]}})
    service = TitreProduitService(fenetre)
    service.generer_titre("Réf d'abord")
    assert presse_papiers.texte == "R1 Joint"
    service.generer_titre()
    assert presse_papiers.texte == "Joint pour four Bosch - R1"
