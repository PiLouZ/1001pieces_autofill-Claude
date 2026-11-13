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

Pur Python, sans Qt ni base : `planifier_import` rend le même `PlanEnregistrement`
que l'aperçu, que l'import écrit ensuite (`EnregistrementFicheService`).
"""

from typing import Optional, Tuple

from src.utils.rapprochement_fiche.acces_base import forme_normalisee
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


def planifier_import(r: Rapprochement,
                     d: Optional[DecisionsFiche] = None) -> PlanEnregistrement:
    """Plan d'écriture d'une fiche par les règles de l'import. `d` : décisions déjà
    posées par les règles (le lot y ajoute ses créations partagées)."""
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
    plan.non_importees = non_importees
    return plan
