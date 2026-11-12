"""
Analyse et décisions d'un lot de fiches (CDC § 7.2, étape 4)

Pur Python, sans Qt : un lot de produits de l'export (`LotExport`) devient un
`LotReprise`, une fiche rapprochée par produit, avec :

- un **résumé par catégorie** (celles de `decisions.CATEGORIES_RESUME`, plus
  « profils ambigus ») compté en fiches et en éléments, chaque catégorie
  validée en bloc, laissée de côté ou en attente pour TOUT le lot ;
- des **doutes regroupés** par genre et par forme : une décision vaut pour toutes
  les fiches du groupe (ex. 41 % de réf. internes « différentes », surtout des
  codes fournisseur `ES…` : un groupe par forme, `AA99999`) ;
- des fiches **personnalisées** (ouvertes dans l'aperçu d'une fiche) : leurs
  décisions propres l'emportent sur celles du lot ;
- un **plan de lot** : un `PlanEnregistrement` par fiche, et les appareils à
  créer **dédoublonnés entre fiches** (même marque, même forme normalisée) :
  chaque fiche est rapprochée seule et ne voit pas les créations prévues par
  les autres ; sans ce partage, deux fiches qui citent le même appareil absent
  le créeraient deux fois.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from src.utils.lecteur_fiche import lire_description
from src.utils.lecteur_fiche.lecteur import cle_marque
from src.utils.rapprochement_fiche.acces_base import AccesBaseLecture, forme_normalisee
from src.utils.rapprochement_fiche.configuration import ConfigurationRapprochement
from src.utils.rapprochement_fiche.decisions import (
    ATTENTE, CATEGORIES_RESUME, CHOIX_IDENTITE, DE_COTE, VALIDEE, AppareilACreer, ChoixAppareil,
    DecisionsFiche, PlanEnregistrement, categorie_equivalence, elements_par_categorie,
    forme_reference, planifier,
)
from src.utils.rapprochement_fiche.rapprochement import rapprocher
from src.utils.rapprochement_fiche.resultat import CATEGORIES_DOUTES, Rapprochement
from src.utils.reprise_site.exports import LotExport, ProduitExport

PROFILS_AMBIGUS = 'profils_ambigus'
CATEGORIES_LOT = dict(CATEGORIES_RESUME)
CATEGORIES_LOT[PROFILS_AMBIGUS] = "Profils ambigus (lecture à confirmer)"

# Genres de doutes traités en bloc, avec leurs choix (le 1er = la proposition)
GENRES_GROUPES = {
    'ref_interne_differente': ("Référence interne sans rapport avec le code produit",
                               CHOIX_IDENTITE['ref_interne_differente']),
    'ref_interne_autre_piece': ("Référence interne déjà rattachée à une autre pièce",
                                CHOIX_IDENTITE['ref_interne_autre_piece']),
    'ean_different': ("EAN du site différent de celui de l'outil", CHOIX_IDENTITE['ean_different']),
    'libelle_different': ("Titre de la fiche différent du libellé", CHOIX_IDENTITE['libelle_different']),
    'remplacement_conflit': ("Remplacement en conflit avec l'existant", ('garder', 'prendre')),
    'origine_inconnue': ("Équivalente sans étiquette d'origine", ('etiquette', 'ecarter')),
}
_CHIFFRES = re.compile(r'\d')


class AnalyseAnnulee(Exception):
    """Analyse du lot interrompue par l'utilisateur."""


def forme_ref_interne(ref: str) -> str:
    """Forme d'une réf. interne pour le regroupement : chiffres → 9, lettres
    gardées (`ES10028` → `ES99999`), pour séparer les familles de codes."""
    return _CHIFFRES.sub('9', (ref or '').upper())


# =============================================================================
# Fiches
# =============================================================================

@dataclass
class FicheLot:
    id_produit: int
    nom: str
    ref_interne: str
    rapprochement: Optional[Rapprochement] = None
    decisions: DecisionsFiche = field(default_factory=DecisionsFiche)
    profil_ambigu: bool = False
    lignes_description: int = 0
    lignes_table: int = 0
    personnalisee: bool = False         # décidée dans l'aperçu de la fiche
    # Lignes posées par le lot, pas par l'utilisateur : mises de côté par « laisser
    # de côté les lignes à compléter », ou rattachées à une création d'une autre fiche
    lignes_auto: Set[int] = field(default_factory=set)
    de_cote: bool = False               # rien n'est écrit, la fiche revient plus tard
    raison_de_cote: str = ''
    erreur: str = ''                    # lecture ou rapprochement impossible
    duree: float = 0.0

    @property
    def ref_piece(self) -> str:
        r = self.rapprochement
        return (r.identite.ref_piece or '') if r is not None else ''


def analyser_produit(produit: ProduitExport, acces: AccesBaseLecture,
                     config: ConfigurationRapprochement, modeles,
                     marques: List[str], types: List[str]) -> FicheLot:
    """Lit et rapproche une fiche de l'export (table complète des compatibilités)."""
    fiche = FicheLot(produit.id_produit, produit.nom, produit.reference,
                     lignes_table=len(produit.compatibilites))
    debut = time.time()
    try:
        lecture = lire_description(produit.description, modeles, marques, types,
                                   marque_produit=produit.marque)
        fiche.profil_ambigu = lecture.profil_ambigu
        fiche.lignes_description = len(lecture.appareils)
        fiche.rapprochement = rapprocher(
            lecture, acces, config, ref_interne=produit.reference, ean=produit.ean,
            categorie=produit.categorie, id_product=produit.id_produit,
            table_site=produit.compatibilites, memoires=True)
    except Exception as e:                  # une fiche illisible ne bloque pas le lot
        fiche.erreur = f"{type(e).__name__} : {e}"
        fiche.de_cote, fiche.raison_de_cote = True, "lecture impossible"
    fiche.duree = time.time() - debut
    if fiche.rapprochement is not None and not fiche.rapprochement.identite.ref_piece:
        fiche.de_cote, fiche.raison_de_cote = True, "pièce introuvable (ni code produit ni réf. interne)"
    return fiche


def analyser_lot(lot: LotExport, acces: AccesBaseLecture, config: ConfigurationRapprochement,
                 modeles, progression: Optional[Callable[[int, int, str], None]] = None,
                 annule: Optional[Callable[[], bool]] = None) -> 'LotReprise':
    """Rapproche chaque produit du lot (lecture seule). L'index des marques de
    `acces` reste en cache d'une fiche à l'autre (et d'un lot à l'autre)."""
    marques = list(acces.marques().values())
    types = list(acces.types().values())
    fiches: List[FicheLot] = []
    debut = time.time()
    n = len(lot.produits)
    for i, produit in enumerate(lot.produits):
        if annule is not None and annule():
            raise AnalyseAnnulee()
        if progression is not None:
            progression(i, n, f"Produit {produit.id_produit} : {produit.nom[:60]}")
        fiches.append(analyser_produit(produit, acces, config, modeles, marques, types))
    if progression is not None:
        progression(n, n, "Analyse terminée")
    return LotReprise(lot, fiches, duree_analyse=time.time() - debut)


# =============================================================================
# Résumé et doutes regroupés
# =============================================================================

@dataclass
class LigneResume:
    cle: str
    libelle: str
    fiches: int
    elements: int


@dataclass
class GroupeDoutes:
    genre: str                          # clé de GENRES_GROUPES
    forme: str                          # sous-groupe ('' = un seul groupe)
    occurrences: List[Tuple[int, str]]  # (index de fiche, élément : réf., ancienne réf.…)
    exemples: List[str] = field(default_factory=list)

    @property
    def cle(self) -> Tuple[str, str]:
        return (self.genre, self.forme)

    @property
    def fiches(self) -> int:
        return len({i for i, _ in self.occurrences})

    @property
    def libelle(self) -> str:
        return GENRES_GROUPES[self.genre][0]

    @property
    def choix(self) -> Tuple[str, ...]:
        return GENRES_GROUPES[self.genre][1]


@dataclass
class PlanLot:
    plans: List[Tuple[int, PlanEnregistrement]]          # (index de fiche, plan) des fiches incluses
    creations: Dict[Tuple[str, str], List[Tuple[int, AppareilACreer]]]  # clé → occurrences
    de_cote: List[int]
    en_attente: List[str]
    fiches_a_completer: List[int]
    lignes_a_completer: int

    @property
    def pret(self) -> bool:
        """Plus rien en attente ni à compléter (un lot dont toutes les fiches sont de
        côté est prêt : il ne fait que les consigner et avancer la reprise)."""
        return not self.en_attente and not self.fiches_a_completer

    def resume(self) -> Dict[str, int]:
        total = {'fiches': len(self.plans), 'de_cote': len(self.de_cote),
                 'appareils_a_creer': len(self.creations),
                 'liens': 0, 'remplacements': 0, 'equivalences': 0}
        for _, p in self.plans:
            s = p.resume()
            for cle in ('liens', 'remplacements', 'equivalences'):
                total[cle] += s[cle]
        return total


def cle_creation(a: AppareilACreer) -> Tuple[str, str]:
    """Identité d'un appareil à créer, pour le partager entre les fiches du lot :
    même clé de marque et même forme normalisée (la règle du § 5.2)."""
    return (cle_marque(a.marque), forme_normalisee(a.ref_modele))


class LotReprise:
    """Un lot analysé et ses décisions (résumé en bloc, groupes de doutes)."""

    def __init__(self, export: LotExport, fiches: List[FicheLot], duree_analyse: float = 0.0):
        self.export = export
        self.fiches = fiches
        self.duree_analyse = duree_analyse
        self.etats: Dict[str, str] = {}
        self.type_par_categorie: Dict[str, str] = {}
        self.choix_groupes: Dict[Tuple[str, str], str] = {}
        self.fiches_de_cote = False         # lot des fiches mises de côté (la reprise n'avance pas)
        self._cats: Dict[int, Dict[str, Dict[str, list]]] = {}

    # --- Catégories ---------------------------------------------------------------
    def categories_fiche(self, index: int) -> Dict[str, Dict[str, list]]:
        if index not in self._cats:
            r = self.fiches[index].rapprochement
            self._cats[index] = elements_par_categorie(r) if r is not None else {}
        return self._cats[index]

    def fiches_actives(self) -> Iterable[Tuple[int, FicheLot]]:
        """Fiches analysées, hors erreurs de lecture."""
        return ((i, f) for i, f in enumerate(self.fiches) if f.rapprochement is not None
                and f.ref_piece)

    def resume(self) -> List[LigneResume]:
        fiches: Dict[str, int] = {}
        elements: Dict[str, int] = {}
        for i, f in self.fiches_actives():
            if f.profil_ambigu:
                fiches[PROFILS_AMBIGUS] = fiches.get(PROFILS_AMBIGUS, 0) + 1
                elements[PROFILS_AMBIGUS] = elements.get(PROFILS_AMBIGUS, 0) + 1
            for cle, contenu in self.categories_fiche(i).items():
                fiches[cle] = fiches.get(cle, 0) + 1
                elements[cle] = elements.get(cle, 0) + sum(len(v) for v in contenu.values())
        return [LigneResume(c, CATEGORIES_LOT[c], fiches[c], elements[c])
                for c in CATEGORIES_LOT if c in fiches]

    def etat(self, categorie: str) -> str:
        return self.etats.get(categorie, ATTENTE)

    def definir_etat(self, categorie: str, etat: str):
        self.etats[categorie] = etat

    def tout_valider(self):
        for ligne in self.resume():
            self.etats[ligne.cle] = VALIDEE

    # --- Doutes regroupés ----------------------------------------------------------
    def groupes_doutes(self) -> List[GroupeDoutes]:
        groupes: Dict[Tuple[str, str], GroupeDoutes] = {}

        def ajouter(genre, forme, index, element, exemple):
            g = groupes.setdefault((genre, forme), GroupeDoutes(genre, forme, []))
            g.occurrences.append((index, element))
            if len(g.exemples) < 5 and exemple not in g.exemples:
                g.exemples.append(exemple)

        for i, f in self.fiches_actives():
            r = f.rapprochement
            doutes = r.doutes_par_categorie()
            ident = r.identite
            for genre in ('ref_interne_differente', 'ref_interne_autre_piece',
                          'ean_different', 'libelle_different'):
                if genre in doutes:
                    forme = forme_ref_interne(ident.ref_interne) if genre == 'ref_interne_differente' else ''
                    exemple = {
                        'ref_interne_differente': f"{ident.ref_interne} ≠ {ident.ref_piece}",
                        'ref_interne_autre_piece': f"{ident.ref_interne} → {ident.piece_du_produit}",
                        'ean_different': f"{ident.ean} ≠ {ident.ean_outil}",
                        'libelle_different': f"« {ident.libelle} »",
                    }[genre]
                    ajouter(genre, forme, i, genre, exemple)
            for rp in r.remplacements:
                if rp.statut == 'conflit':
                    ajouter('remplacement_conflit', '', i, rp.ancienne,
                            f"{rp.ancienne} : {rp.successeur_actuel} / {rp.nouvelle}")
            for e in r.equivalences:
                if categorie_equivalence(e) == 'conflits' and e.statut not in (
                        'deja_dans_le_groupe', 'dans_la_succession', 'ecartee'):
                    ajouter('origine_inconnue', forme_reference(e.reference), i, e.reference,
                            e.reference)
        ordre = list(GENRES_GROUPES)
        return sorted(groupes.values(), key=lambda g: (ordre.index(g.genre), -g.fiches, g.forme))

    def choisir_groupe(self, groupe: GroupeDoutes, choix: str, etiquette: str = ''):
        """Décision en bloc sur un groupe de doutes (les fiches personnalisées gardent
        la leur). Pour `origine_inconnue`, `choix` = 'etiquette' (avec `etiquette`)
        ou 'ecarter'. `choix` vide : retour à la proposition (décisions retirées)."""
        if choix:
            self.choix_groupes[groupe.cle] = choix if choix != 'etiquette' else f"etiquette:{etiquette}"
        else:
            self.choix_groupes.pop(groupe.cle, None)
        for index, element in groupe.occurrences:
            f = self.fiches[index]
            if f.personnalisee:
                continue
            d = f.decisions
            if not choix:
                if groupe.genre in CHOIX_IDENTITE:
                    d.identite.pop(groupe.genre, None)
                elif groupe.genre == 'remplacement_conflit':
                    d.remplacements.pop(element, None)
                else:
                    d.ecartees.discard(element)
                    d.origines.pop(element, None)
                continue
            if groupe.genre in CHOIX_IDENTITE:
                d.identite[groupe.genre] = choix
            elif groupe.genre == 'remplacement_conflit':
                d.remplacements[element] = choix
            elif groupe.genre == 'origine_inconnue':
                if choix == 'ecarter':
                    d.ecartees.add(element)
                    d.origines.pop(element, None)
                else:
                    d.ecartees.discard(element)
                    if etiquette.strip():
                        d.origines[element] = etiquette.strip()
                    else:
                        d.origines.pop(element, None)

    # --- Fiches ------------------------------------------------------------------
    def mettre_de_cote(self, index: int, raison: str = "mise de côté"):
        f = self.fiches[index]
        f.de_cote, f.raison_de_cote = True, raison

    def reprendre(self, index: int):
        f = self.fiches[index]
        if f.rapprochement is not None and f.ref_piece:
            f.de_cote, f.raison_de_cote = False, ''

    def personnaliser(self, index: int, decisions: DecisionsFiche):
        """Décisions prises dans l'aperçu de la fiche : elles l'emportent sur le lot."""
        f = self.fiches[index]
        f.decisions, f.personnalisee = decisions, True

    def decisions_effectives(self, index: int) -> DecisionsFiche:
        """Décisions de la fiche, états et type commun du lot reportés (sauf fiche
        personnalisée, qui garde les siens)."""
        f = self.fiches[index]
        d = f.decisions
        if not f.personnalisee:
            d.etats = {c: self.etat(c) for c in self.categories_fiche(index)}
            d.type_par_categorie = dict(self.type_par_categorie)
        return d

    def lignes_a_completer_de_cote(self) -> int:
        """« Laisser de côté les lignes à compléter » : chaque ligne qui bloque le lot
        (appareil à choisir, marque ou type manquant) est mise de côté."""
        n = 0
        for i, f in self.fiches_actives():
            if f.de_cote:
                continue
            plan = planifier(f.rapprochement, self.decisions_effectives(i))
            for index in plan.lignes_a_completer:
                f.decisions.appareils[index] = ChoixAppareil(ignorer=True)
                f.lignes_auto.add(index)
                n += 1
        return n

    def _rattacher_aux_creations(self, plans: List[Tuple[int, PlanEnregistrement]]
                                 ) -> Set[int]:
        """Ligne à compléter (absente sans type, à valider sans proposition) ou mise
        de côté par le lot, dont l'appareil est créé par une AUTRE ligne du lot : elle reprend la
        marque et le type de cette création, et la partage. Sans cela, la relance du
        lot la trouverait « exacte » et créerait des liens que le 1er passage n'a pas
        posés. Retourne les fiches à replanifier."""
        modeles: Dict[Tuple[str, str], AppareilACreer] = {}
        for _, plan in plans:
            for a in plan.appareils_a_creer:
                modeles.setdefault(cle_creation(a), a)
        a_refaire: Set[int] = set()
        if not modeles:
            return a_refaire
        for i, plan in plans:
            f = self.fiches[i]
            if f.personnalisee:
                continue
            candidates = set(plan.lignes_a_completer) | {
                k for k in f.lignes_auto if (c := f.decisions.appareils.get(k)) and c.ignorer}
            for index in candidates:
                a = f.rapprochement.appareils[index]
                # absente, ou « à valider » sans proposition (nom commercial seul…) :
                # la même marque et la même forme sont créées par le lot
                if a.niveau not in ('absent', 'a_valider'):
                    continue
                cle = (cle_marque(a.marque or a.marque_fiche), forme_normalisee(a.ref_modele))
                modele = modeles.get(cle)
                if not cle[0] or modele is None:
                    continue
                f.decisions.appareils[index] = ChoixAppareil(creer=True, marque=modele.marque,
                                                             type=modele.type)
                f.lignes_auto.add(index)
                a_refaire.add(i)
        return a_refaire

    # --- Plan --------------------------------------------------------------------
    def planifier(self) -> PlanLot:
        plans, de_cote, attente, a_completer = [], [], set(), []
        lignes = 0
        etat_profils = self.etat(PROFILS_AMBIGUS)
        for i, f in enumerate(self.fiches):
            if f.de_cote or f.rapprochement is None or not f.ref_piece:
                de_cote.append(i)
                continue
            if f.profil_ambigu and not f.personnalisee:
                if etat_profils == DE_COTE:
                    de_cote.append(i)
                    continue
                if etat_profils == ATTENTE:
                    attente.add(CATEGORIES_LOT[PROFILS_AMBIGUS])
            plan = planifier(f.rapprochement, self.decisions_effectives(i))
            attente.update(plan.en_attente)
            if plan.a_completer:
                a_completer.append(i)
                lignes += len(plan.a_completer)
            plans.append((i, plan))
        a_refaire = self._rattacher_aux_creations(plans)
        if a_refaire:
            a_completer, lignes = [], 0
            for k, (i, plan) in enumerate(plans):
                if i in a_refaire:
                    plan = planifier(self.fiches[i].rapprochement, self.decisions_effectives(i))
                    plans[k] = (i, plan)
                if plan.a_completer:
                    a_completer.append(i)
                    lignes += len(plan.a_completer)
        creations: Dict[Tuple[str, str], List[Tuple[int, AppareilACreer]]] = {}
        for i, plan in plans:
            for a in plan.appareils_a_creer:
                creations.setdefault(cle_creation(a), []).append((i, a))
        ordre = list(CATEGORIES_LOT.values())
        return PlanLot(plans, creations, de_cote,
                       sorted(attente, key=lambda c: ordre.index(c) if c in ordre else 99),
                       a_completer, lignes)


def libelle_doute(categorie: str) -> str:
    return CATEGORIES_DOUTES.get(categorie, categorie)


def mesures_lot(lot: LotReprise, plan: Optional[PlanLot] = None) -> Dict[str, object]:
    """Chiffres du lot pour le journal et la mesure du § 7.4 : niveaux, liens
    (part déjà en base), provenances, statut des pièces, doutes (en fiches)."""
    from collections import Counter
    niveaux, liens, provenances, pieces, doutes = Counter(), Counter(), Counter(), Counter(), Counter()
    lignes = fiches_sans_doute = 0
    for _, f in lot.fiches_actives():
        r = f.rapprochement
        pieces[r.identite.statut or '?'] += 1
        cats = r.doutes_par_categorie()
        for c in cats:
            doutes[c] += 1
        if not cats:
            fiches_sans_doute += 1
        for a in r.appareils:
            lignes += 1
            niveaux[a.niveau] += 1
            liens[a.lien or 'a_decider'] += 1
            provenances[a.provenance] += 1
    deja = liens.get('deja_lie', 0) + liens.get('deja_couvert', 0)
    out = {
        'fiches': len(lot.fiches), 'fiches_analysees': sum(1 for _ in lot.fiches_actives()),
        'fiches_sans_doute': fiches_sans_doute, 'lignes': lignes,
        'part_deja_en_base': round(deja / lignes, 4) if lignes else 0.0,
        'niveaux': dict(niveaux), 'liens': dict(liens), 'provenances': dict(provenances),
        'pieces': dict(pieces), 'doutes_fiches': dict(doutes.most_common()),
        'profils_ambigus': sum(1 for f in lot.fiches if f.profil_ambigu),
        'erreurs': sum(1 for f in lot.fiches if f.erreur),
        'analyse_s': round(lot.duree_analyse, 2),
    }
    if plan is not None:
        out['plan'] = plan.resume()
        out['creations_lignes'] = sum(len(v) for v in plan.creations.values())
    return out
