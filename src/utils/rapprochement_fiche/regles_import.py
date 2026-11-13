"""
Règles de l'import pour une fiche du site (CDC docs/cdc_import_fiches_site.md, § 10.12)

Une fiche du site est une source d'import comme un PDF ou un CSV : aucune
question. Chaque doute du rapprochement est tranché par la règle que l'import
applique déjà à un fichier :

| Doute | Règle |
|---|---|
| même réf. sous une autre marque du groupe | relié à cet appareil |
| même nom commercial, réf. différente ; marque hors du groupe ; appareil inconnu | créé |
| type d'un appareil à créer inconnu | créé quand même : auto-complétion, puis « Suggestions à valider » |
| marque d'un appareil à créer inconnue | non importé (l'identité d'un appareil est sa marque et sa réf. : créé sans marque, il ne serait jamais retrouvé, et l'auto-complétion lui donnerait la marque d'un autre appareil de même réf.) |
| appareil parmi plusieurs | la proposition (écriture exacte, type) ; sans proposition, ligne non importée |
| réf. illisible | non importée |
| nom commercial d'un appareil déjà cité par la fiche | doublon : rien de créé |
| réf. interne, EAN, réf. interne d'une autre pièce | le site fait foi |
| titre de la fiche ≠ libellé | le libellé de l'outil est gardé (le titre coupé ne sert qu'à une pièce sans libellé) |
| remplacement en conflit | l'existant est gardé |
| équivalente sans marque d'origine | écrite, origine vide (une réf. sans chiffre ne l'est jamais) |
| pas de code produit | pièce à saisir : la fiche n'est pas écrite |
| appareil connu, champ différent sur le site | l'outil est gardé ; un nom commercial vide est complété |
| appareil à créer aux données bancales (nom mêlé de description, n° d'article collé, mot coupé, type de ligne qui n'est pas un appareil, marque inconnue de l'outil) | non créé ; la fiche est notée « à refaire depuis les PDF » (§ 10.14) |
| au moins 20 % des créations bancales : fiche **en vrac** | aucune création ; les liens et les relations sont écrits ; fiche « à refaire depuis les PDF » |

Pur Python, sans Qt ni base : `planifier_import` rend le même `PlanEnregistrement`
que l'aperçu, que l'import écrit ensuite (`EnregistrementFicheService`).
"""

import re
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.utils.rapprochement_fiche.acces_base import forme_normalisee
from src.utils.rapprochement_fiche.coupe_titre import sans_accents, termes_appareils
from src.utils.rapprochement_fiche.decisions import (
    VALIDEE, ChoixAppareil, DecisionsFiche, PlanEnregistrement, categorie_appareil,
    elements_par_categorie, planifier,
)
from src.utils.rapprochement_fiche.resultat import AppareilRapproche, Rapprochement

# Doutes d'identité : le site fait foi pour le commercial, l'outil pour le libellé
REPONSES_IDENTITE = {
    'ean_different': 'site',
    'ref_interne_differente': 'enregistrer',
    'ref_interne_autre_piece': 'prendre',
    'libelle_different': 'garder',
}
SANS_CODE_PRODUIT = "pas de code produit : référence de la pièce à saisir"

# --- Fiches en vrac (§ 10.14) -------------------------------------------------
# Une fiche dont au moins SEUIL_VRAC des créations sont douteuses est « en vrac » :
# aucune création. Sous le seuil, seules les créations douteuses sont retenues.
SEUIL_VRAC = 0.20
MOTIFS_DOUTEUX = {
    'nom_mele_de_description': "nom commercial mêlé d'une description d'appareil",
    'article_colle': "n° d'article collé à la référence",
    'mot_coupe': "mot collé ou coupé",
    'type_ligne_non_appareil': "type écrit sur la ligne qui n'est pas un appareil",
    'marque_inconnue': "marque inconnue de l'outil",
}
# Mots d'une description d'appareil, en plus des types et appellations
_MOTS_DESCRIPTION = ('armoire', 'encastrable', 'encast', 'statique', 'combine', 'combi',
                     'pose libre', 'integrable', '1 porte', '2 portes', '1 groupe', '2 groupes')
_ARTICLE_COLLE = re.compile(r'^\d{3}\.\d{3}\.\d{2}\S')        # n° d'article Ikea collé
_RACINES_COUPEES = ('REFRIG', 'CONGEL', 'LAVE', 'SECHE', 'ASPIR', 'CUISIN', 'ARMOIR', 'COMBI',
                    'MICROWAVE')
_MOT_COUPE = re.compile(r'[0-9+](?:' + '|'.join(_RACINES_COUPEES) + ')')


def _plat(texte: str) -> str:
    return sans_accents(texte or '').lower()


@lru_cache(maxsize=8)
def _mots_description(termes: Tuple[str, ...]) -> re.Pattern:
    mots = sorted({_plat(t) for t in termes} | set(_MOTS_DESCRIPTION), key=len, reverse=True)
    return re.compile(r'(?:^|[\s(/-])(?:' + '|'.join(re.escape(m) for m in mots)
                      + r')(?:s|x)?(?=$|[\s,.;:()/-])')


def motifs_douteux(a: AppareilRapproche, termes: Tuple[str, ...]) -> List[str]:
    """Pourquoi une ligne à créer donnerait un appareil bancal ([] = saine)."""
    m = []
    plats = {_plat(t) for t in termes}
    if a.source_type == 'ligne' and a.type_site and _plat(a.type_site) not in plats:
        m.append('type_ligne_non_appareil')
    if a.nom and _mots_description(termes).search(_plat(a.nom)):
        m.append('nom_mele_de_description')
    if _ARTICLE_COLLE.search(a.nom or '') or _ARTICLE_COLLE.search(a.ref_modele or ''):
        m.append('article_colle')
    if _MOT_COUPE.search(_plat(a.nom).upper()) or _MOT_COUPE.search(_plat(a.ref_modele).upper()):
        m.append('mot_coupe')
    if a.marque_inconnue:
        m.append('marque_inconnue')
    return m


@dataclass
class ARefaire:
    """Fiche à refaire depuis les PDF : créations retenues et pourquoi."""
    en_vrac: bool
    creations: int                      # créations prévues avant la retenue
    retenues: int                       # créations non faites
    motifs: Dict[str, int] = field(default_factory=dict)
    exemples: List[str] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)   # lignes du rapprochement retenues

    @property
    def raison(self) -> str:
        principaux = ', '.join(MOTIFS_DOUTEUX[k] for k, _ in
                               sorted(self.motifs.items(), key=lambda x: -x[1])[:2])
        if self.en_vrac:
            return (f"fiche en vrac : {self.retenues} appareil(s) non créé(s) sur "
                    f"{self.creations} ({principaux})")
        return f"{self.retenues} appareil(s) non créé(s) sur {self.creations} ({principaux})"


def retenir_creations_douteuses(r: Rapprochement, d: DecisionsFiche, plan: PlanEnregistrement,
                                termes: Optional[Tuple[str, ...]] = None) -> Optional[ARefaire]:
    """Créations douteuses du plan : retenues (lignes ignorées dans `d`) ; toutes les
    créations si la fiche est en vrac. Le plan est à refaire ensuite. None : rien de
    douteux."""
    if not plan.appareils_a_creer:
        return None
    termes = termes if termes is not None else termes_appareils(None)
    douteuses, motifs, exemples = [], {}, []
    for a in plan.appareils_a_creer:
        ligne = r.appareils[a.index]
        m = motifs_douteux(ligne, termes)
        if m:
            douteuses.append(a.index)
            for k in m:
                motifs[k] = motifs.get(k, 0) + 1
            if len(exemples) < 3:
                exemples.append(f"{a.marque or '?'} {a.ref_modele}"
                                + (f" « {a.nom} »" if a.nom else '') + (f", {a.type}" if a.type else ''))
    if not douteuses:
        return None
    n = len(plan.appareils_a_creer)
    en_vrac = len(douteuses) / n >= SEUIL_VRAC
    retenues = [a.index for a in plan.appareils_a_creer] if en_vrac else douteuses
    for index in retenues:
        d.appareils[index] = ChoixAppareil(ignorer=True)
    return ARefaire(en_vrac, n, len(retenues), motifs, exemples, list(retenues))


def _meme_ref(a: AppareilRapproche):
    """Le candidat de même réf. (à la ponctuation près), s'il est seul."""
    memes = [c for c in a.candidats
             if forme_normalisee(c.ref_modele) == forme_normalisee(a.ref_modele)]
    if a.proposition is not None:
        memes = [c for c in memes if c.id == a.proposition] or memes
    return memes[0] if len(memes) == 1 else None


def _decrire(a: AppareilRapproche) -> str:
    return f"ligne {a.numero or 'table'} {a.marque or a.marque_fiche or '?'} {a.ref_modele}"


def choix_ligne(a: AppareilRapproche) -> Tuple[Optional[ChoixAppareil], str]:
    """(choix imposé par la règle, raison si la ligne n'est pas importée).
    Choix None : la ligne suit le plan (reliée, ou créée si absente)."""
    if a.motif == 'doublon_nom':
        return ChoixAppareil(ignorer=True), ''          # doublon d'une autre ligne
    if a.suspecte:
        if a.niveau == 'absent' or categorie_appareil(a) == 'a_valider':
            return ChoixAppareil(ignorer=True), f"{_decrire(a)} : référence illisible ({a.suspecte})"
        return None, ''
    if a.niveau == 'absent':
        if not (a.marque or a.marque_fiche):
            return ChoixAppareil(ignorer=True), f"{_decrire(a)} : marque inconnue"
        return None, ''                                  # créé (type vide admis)
    if categorie_appareil(a) != 'a_valider':
        return None, ''
    if a.motif in ('meme_ref_groupe', 'nom_meme_ref'):
        c = _meme_ref(a)
        if c is not None:
            return ChoixAppareil(appareil_id=c.id), ''
    if a.motif == 'nom_ref_differente':
        if not (a.marque or a.marque_fiche):
            return ChoixAppareil(ignorer=True), f"{_decrire(a)} : marque inconnue"
        return ChoixAppareil(creer=True, marque=a.marque or a.marque_fiche, type=a.type), ''
    if a.proposition is not None:
        return ChoixAppareil(appareil_id=a.proposition), ''
    c = _meme_ref(a)
    if c is not None:
        return ChoixAppareil(appareil_id=c.id), ''
    return (ChoixAppareil(ignorer=True),
            f"{_decrire(a)} : appareil à choisir parmi {len(a.candidats)}")


def decisions_import(r: Rapprochement) -> Tuple[DecisionsFiche, list]:
    """Décisions d'une fiche par les règles de l'import, et lignes non importées."""
    d = DecisionsFiche(creer_incomplets=True)
    d.etats = {c: VALIDEE for c in elements_par_categorie(r)}
    doutes = r.doutes_par_categorie()
    d.identite = {k: v for k, v in REPONSES_IDENTITE.items() if k in doutes}
    non_importees = []
    for i, a in enumerate(r.appareils):
        choix, raison = choix_ligne(a)
        if choix is not None:
            d.appareils[i] = choix
        if raison:
            non_importees.append(raison)
    return d, non_importees


def sans_code_produit(r: Rapprochement) -> bool:
    return 'code_produit_absent' in r.doutes_par_categorie() or not r.identite.ref_piece


def planifier_import(r: Rapprochement, d: Optional[DecisionsFiche] = None,
                     appellations: Any = None) -> PlanEnregistrement:
    """Plan d'écriture d'une fiche par les règles de l'import. `d` : décisions déjà
    posées par les règles. `appellations` : types et appellations de l'onglet
    Appareils (config `synonymes_appareils`), pour repérer les créations bancales."""
    non_importees = []
    if d is None:
        d, non_importees = decisions_import(r)
    plan = planifier(r, d)
    if sans_code_produit(r):
        plan.a_completer = [SANS_CODE_PRODUIT]
        return plan
    if plan.lignes_a_completer:
        # Ce que le plan ne sait pas trancher (appareil parmi plusieurs sans
        # candidat lié par la fiche…) n'est pas importé
        for index in plan.lignes_a_completer:
            d.appareils[index] = ChoixAppareil(ignorer=True)
        non_importees += plan.a_completer
        plan = planifier(r, d)
    a_refaire = retenir_creations_douteuses(r, d, plan, termes_appareils(appellations))
    if a_refaire is not None:
        plan = planifier(r, d)
        plan.a_refaire = a_refaire
    plan.non_importees = non_importees
    return plan
