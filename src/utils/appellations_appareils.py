"""
Appellations des types d'appareils dans les textes générés

« Lave-linge » se dit aussi « machine à laver » : pour qu'une fiche réponde aux
deux recherches sans répéter le même mot sur des milliers de pages, les textes
générés (méta title, méta description, titre de fiche) peuvent citer l'appareil
sous une autre appellation.

Règles (décision client 2026-11-09) :
- choix FIXE pour une référence : crc32(référence | type | champ), comme le
  gabarit des métas. Régénérer une fiche ne la change pas ; chaque champ a son
  propre tirage, donc une même fiche peut citer les deux appellations ;
- le terme principal (le type en base) garde une part réglable (50 % par
  défaut), les autres appellations actives se partagent le reste ;
- les sous-types (« radiateur » pour « chauffage ») ne sont justes que pour une
  partie des appareils : livrés désactivés, activables un par un ;
- chaque appellation porte son genre, pour accorder « un » / « une ».

Seuls les textes générés changent : la colonne Type, les filtres, la recherche
et le CSV gardent le type en base. Sans Qt : testable seul.
"""

import copy
import random
import zlib
from typing import Any, Dict, List, NamedTuple, Optional


MASCULIN, FEMININ = "m", "f"
SYNONYME, SOUS_TYPE = "synonyme", "sous_type"

# Textes générés où l'appellation peut varier (clé de config → libellé affiché)
CHAMPS = {
    "meta_title": "Méta title",
    "meta_description": "Méta description",
}

# Titres : réglés gabarit par gabarit (case « Varier le nom de l'appareil » de
# l'onglet Titre), pas ici. Le service ne passe les appellations au générateur
# que pour un gabarit coché ; ce champ varie donc dès qu'on le demande.
TITRE = "titre"


def _v(terme: str, genre: str, nature: str = SYNONYME, actif: Optional[bool] = None) -> Dict:
    return {"terme": terme, "genre": genre, "nature": nature,
            "actif": (nature == SYNONYME) if actif is None else actif}


def _a(type_: str, genre: str, *variantes: Dict) -> Dict:
    return {"type": type_, "genre": genre, "variantes": list(variantes)}


# Types présents en base au 2026-11-09, du plus au moins fréquent. Un type sans
# variante sert quand même : son genre accorde « un » / « une ».
APPAREILS_PAR_DEFAUT: List[Dict] = [
    _a("lave-vaisselle", MASCULIN, _v("machine à laver la vaisselle", FEMININ)),
    _a("lave-linge", MASCULIN, _v("machine à laver", FEMININ)),
    _a("réfrigérateur", MASCULIN, _v("frigo", MASCULIN)),
    _a("four", MASCULIN),
    _a("sèche-linge", MASCULIN, _v("séchoir à linge", MASCULIN)),
    _a("plaque", FEMININ, _v("plaque de cuisson", FEMININ), _v("table de cuisson", FEMININ)),
    _a("cuisinière", FEMININ, _v("gazinière", FEMININ, SOUS_TYPE)),
    _a("congélateur", MASCULIN, _v("congélo", MASCULIN)),
    _a("hotte", FEMININ, _v("hotte aspirante", FEMININ), _v("hotte de cuisine", FEMININ)),
    # « four micro-ondes » désigne d'abord le four combiné micro-ondes (lot 2 des
    # règles de nomenclature, 2026-11-23) : désactivé pour le micro-ondes simple
    _a("micro-ondes", MASCULIN, _v("four micro-ondes", MASCULIN, actif=False)),
    _a("lavante-séchante", FEMININ, _v("lave-linge séchant", MASCULIN),
       _v("machine à laver séchante", FEMININ)),
    _a("aspirateur", MASCULIN),
    _a("four vapeur", MASCULIN, _v("four à vapeur", MASCULIN)),
    _a("four combiné micro-ondes", MASCULIN, _v("four micro-ondes combiné", MASCULIN)),
    _a("chauffage", MASCULIN, _v("appareil de chauffage", MASCULIN),
       _v("radiateur", MASCULIN, SOUS_TYPE), _v("sèche-serviette", MASCULIN, SOUS_TYPE),
       _v("accumulateur", MASCULIN, SOUS_TYPE)),
    _a("chauffe-eau", MASCULIN, _v("ballon d'eau chaude", MASCULIN), _v("cumulus", MASCULIN)),
    _a("machine à café", FEMININ, _v("cafetière", FEMININ), _v("machine expresso", FEMININ)),
    _a("cave à vin", FEMININ, _v("armoire à vin", FEMININ)),
    _a("autocuiseur", MASCULIN, _v("cocotte-minute", FEMININ, actif=False),
       _v("cuiseur sous pression", MASCULIN)),
    _a("robot", MASCULIN, _v("robot de cuisine", MASCULIN), _v("robot ménager", MASCULIN)),
    _a("tiroir chauffant", MASCULIN, _v("tiroir chauffe-plats", MASCULIN)),
    _a("centrale repassage", FEMININ, _v("centrale vapeur", FEMININ),
       _v("générateur vapeur", MASCULIN)),
    _a("friteuse", FEMININ),
    _a("gril électrique", MASCULIN, _v("grill électrique", MASCULIN)),
    _a("appareil à raclette", MASCULIN, _v("raclette électrique", FEMININ)),
    _a("fer à repasser", MASCULIN),
    _a("climatiseur", MASCULIN, _v("climatisation", FEMININ), _v("clim", FEMININ)),
    _a("plancha", FEMININ),
    _a("mixer", MASCULIN, _v("mixeur", MASCULIN), _v("blender", MASCULIN)),
    _a("bouilloire", FEMININ),
]

# Migrations ponctuelles d'une config ENREGISTRÉE (sa liste d'appareils fait foi :
# changer les défauts ci-dessus ne l'atteint pas). Chacune ne joue qu'une fois : son
# nom est noté dans la config, un réglage refait ensuite par l'utilisateur tient.
MIGRATION_FOUR_COMBINE = "2026-11-23 four combiné micro-ondes"
MIGRATIONS = (MIGRATION_FOUR_COMBINE,)

CONFIG_PAR_DEFAUT: Dict[str, Any] = {
    "actif": True,
    # Part du terme principal (type en base) dans les tirages, en %
    "part_principal": 50,
    # Méta title : toujours le terme principal (le mot-clé qui pèse le plus)
    "champs": {"meta_title": False, "meta_description": True},
    "appareils": APPAREILS_PAR_DEFAUT,
    # Les défauts intègrent déjà toutes les migrations
    "migrations": list(MIGRATIONS),
}


class Appellation(NamedTuple):
    terme: str
    genre: str
    principal: bool

    @property
    def feminin(self) -> bool:
        return self.genre == FEMININ

    def avec_article_indefini(self) -> str:
        """« un lave-linge », « une machine à laver »."""
        return f"{'une' if self.feminin else 'un'} {self.terme}"


def cle_type(type_appareil: str) -> str:
    """Clé de correspondance : la forme normalisée des métas (« Lave linge » → « lave-linge »)."""
    from .seo_generator import SEOGenerator
    return SEOGenerator.normaliser_type(type_appareil or "")


def nettoyer_config(brute: Any) -> Dict[str, Any]:
    """Config valide, complétée par les défauts. Absente ou illisible → défauts.

    La liste d'appareils enregistrée fait foi : un type ou une appellation
    retirés par l'utilisateur ne reviennent pas. Une appellation sans terme ou
    égale au type est écartée, un doublon aussi.
    """
    config = copy.deepcopy(CONFIG_PAR_DEFAUT)
    if not isinstance(brute, dict):
        return config
    if isinstance(brute.get("actif"), bool):
        config["actif"] = brute["actif"]
    try:
        config["part_principal"] = min(100, max(0, int(brute.get("part_principal",
                                                                 config["part_principal"]))))
    except (TypeError, ValueError):
        pass
    if isinstance(brute.get("champs"), dict):
        for champ in CHAMPS:
            if isinstance(brute["champs"].get(champ), bool):
                config["champs"][champ] = brute["champs"][champ]
    if isinstance(brute.get("appareils"), list):
        appareils, vus = [], set()
        for a in brute["appareils"]:
            if not isinstance(a, dict):
                continue
            type_ = cle_type(str(a.get("type", "")))
            if not type_ or type_ in vus:
                continue
            vus.add(type_)
            variantes, termes = [], {type_.casefold()}
            for v in a.get("variantes") or []:
                if not isinstance(v, dict):
                    continue
                terme = " ".join(str(v.get("terme", "")).split())
                if not terme or terme.casefold() in termes:
                    continue
                termes.add(terme.casefold())
                nature = v.get("nature") if v.get("nature") in (SYNONYME, SOUS_TYPE) else SYNONYME
                variantes.append({
                    "terme": terme,
                    "genre": FEMININ if v.get("genre") == FEMININ else MASCULIN,
                    "nature": nature,
                    "actif": bool(v.get("actif", nature == SYNONYME)),
                })
            appareils.append({"type": type_,
                              "genre": FEMININ if a.get("genre") == FEMININ else MASCULIN,
                              "variantes": variantes})
        config["appareils"] = appareils
        faites = brute.get("migrations")
        faites = [str(m) for m in faites] if isinstance(faites, list) else []
        if MIGRATION_FOUR_COMBINE not in faites:
            _migrer_four_combine(appareils)
        config["migrations"] = sorted(set(faites) | set(MIGRATIONS))
    return config


def _migrer_four_combine(appareils: List[Dict]) -> None:
    """Type « Four combiné micro-ondes » (lot 2 des règles de nomenclature) :
    « four micro-ondes » désactivé pour le micro-ondes, entrée du nouveau type
    ajoutée après « four vapeur » (à défaut après « micro-ondes », sinon en fin)."""
    for a in appareils:
        if a["type"] == "micro-ondes":
            for v in a["variantes"]:
                if v["terme"].casefold() == "four micro-ondes":
                    v["actif"] = False
    nouveau = next(a for a in APPAREILS_PAR_DEFAUT if a["type"] == "four combiné micro-ondes")
    if any(a["type"] == nouveau["type"] for a in appareils):
        return
    types = [a["type"] for a in appareils]
    rang = next((types.index(t) + 1 for t in ("four vapeur", "micro-ondes") if t in types),
                len(appareils))
    appareils.insert(rang, copy.deepcopy(nouveau))


class Appellations:
    """Choix de l'appellation d'un type d'appareil, selon la config (déjà nettoyée ou non)."""

    def __init__(self, config: Any = None):
        self.config = nettoyer_config(config)
        self._par_type = {a["type"]: a for a in self.config["appareils"]}

    def principal(self, type_norm: str) -> Appellation:
        """Le type en base lui-même, avec son genre (masculin s'il n'est pas listé)."""
        entree = self._par_type.get(cle_type(type_norm))
        return Appellation(type_norm, entree["genre"] if entree else MASCULIN, True)

    def candidates(self, type_norm: str, champ: str) -> List[Appellation]:
        """Principal puis appellations actives ; principal seul si le champ ne varie pas.

        Un champ hors CHAMPS (le Titre) varie toujours : son gabarit en décide.
        """
        principal = self.principal(type_norm)
        entree = self._par_type.get(cle_type(type_norm))
        champ_coupe = champ in CHAMPS and not self.config["champs"].get(champ)
        if not (entree and self.config["actif"]) or champ_coupe:
            return [principal]
        return [principal] + [Appellation(v["terme"], v["genre"], False)
                              for v in entree["variantes"] if v["actif"]]

    def poids(self, nb_candidates: int) -> List[float]:
        """Principal : part_principal % ; le reste partagé à égalité."""
        if nb_candidates <= 1:
            return [1.0]
        part = self.config["part_principal"] / 100.0
        return [part] + [(1.0 - part) / (nb_candidates - 1)] * (nb_candidates - 1)

    def choisir(self, type_norm: str, reference: str, champ: str) -> Appellation:
        """Appellation fixe pour (référence, type, champ).

        crc32 et non hash() : hash() d'une chaîne change à chaque lancement de Python.
        """
        candidates = self.candidates(type_norm, champ)
        if len(candidates) == 1:
            return candidates[0]
        graine = zlib.crc32(f"{reference}|{cle_type(type_norm)}|{champ}".encode("utf-8"))
        tirage = random.Random(graine).random()
        cumul = 0.0
        for candidate, poids in zip(candidates, self.poids(len(candidates))):
            cumul += poids
            if tirage < cumul:
                return candidate
        return candidates[-1]
