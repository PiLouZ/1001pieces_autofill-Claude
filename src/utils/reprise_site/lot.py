"""
Analyse et plan d'un lot de fiches (CDC § 7.2, § 10.12 à 10.16, § 10.20)

Pur Python, sans Qt : un lot de produits de l'export (`LotExport`) devient un
`LotReprise`, une fiche rapprochée par produit. Son plan (`planifier_par_regles`)
suit les règles de l'import, sans question :

- un `PlanEnregistrement` par fiche (`regles_import`) ; une fiche sans code
  produit est mise de côté (référence de pièce à saisir dans sa carte) ; ce que
  l'import ne sait pas trancher n'est pas importé, et compté ;
- les appareils à créer **dédoublonnés entre fiches** (même marque, même forme
  normalisée) : chaque fiche est rapprochée seule et ne voit pas les créations
  prévues par les autres ; sans ce partage, deux fiches qui citent le même
  appareil absent le créeraient deux fois ;
- les créations bancales retenues (fiches à refaire depuis les PDF, § 10.14).
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from src.utils.lecteur_fiche import lire_description
from src.utils.lecteur_fiche.lecteur import cle_marque
from src.utils.rapprochement_fiche.acces_base import AccesBaseLecture, forme_normalisee
from src.utils.rapprochement_fiche.configuration import ConfigurationRapprochement
from src.utils.rapprochement_fiche.decisions import (
    AppareilACreer, ChoixAppareil, DecisionsFiche, PlanEnregistrement, planifier,
)
from src.utils.rapprochement_fiche.rapprochement import rapprocher
from src.utils.rapprochement_fiche.resultat import Rapprochement
from src.utils.reprise_site.exports import LotExport, ProduitExport


class AnalyseAnnulee(Exception):
    """Analyse du lot interrompue par l'utilisateur."""


# =============================================================================
# Fiches
# =============================================================================

@dataclass
class FicheLot:
    id_produit: int
    nom: str
    ref_interne: str
    rapprochement: Optional[Rapprochement] = None
    decisions: DecisionsFiche = field(default_factory=DecisionsFiche)   # posées par les règles
    profil_ambigu: bool = False
    lignes_description: int = 0
    lignes_table: int = 0
    marques_annoncees: List[str] = field(default_factory=list)   # « Compatible avec … »
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
        fiche.marques_annoncees = [m for m in lecture.marques_annoncees if m]
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
class PlanLot:
    plans: List[Tuple[int, PlanEnregistrement]]          # (index de fiche, plan) des fiches incluses
    creations: Dict[Tuple[str, str], List[Tuple[int, AppareilACreer]]]  # clé → occurrences
    de_cote: List[int]
    fiches_a_completer: List[int] = field(default_factory=list)
    lignes_a_completer: int = 0
    # Règles de l'import (§ 10.12) : fiche → lignes non importées (historique)
    non_importees: Dict[int, List[str]] = field(default_factory=dict)
    # Fiches à refaire depuis les PDF (§ 10.14) : fiche → regles_import.ARefaire
    a_refaire: Dict[int, object] = field(default_factory=dict)

    @property
    def pret(self) -> bool:
        """Plus rien à compléter (un lot dont toutes les fiches sont de côté est
        prêt : il ne fait que les consigner et avancer la reprise)."""
        return not self.fiches_a_completer

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
    """Un lot analysé et son plan par les règles de l'import."""

    def __init__(self, export: LotExport, fiches: List[FicheLot], duree_analyse: float = 0.0):
        self.export = export
        self.fiches = fiches
        self.duree_analyse = duree_analyse
        self.fiches_de_cote = False         # lot des fiches mises de côté (la reprise n'avance pas)

    def fiches_actives(self) -> Iterable[Tuple[int, FicheLot]]:
        """Fiches analysées, hors erreurs de lecture."""
        return ((i, f) for i, f in enumerate(self.fiches) if f.rapprochement is not None
                and f.ref_piece)

    # --- Fiches ------------------------------------------------------------------
    def mettre_de_cote(self, index: int, raison: str = "mise de côté"):
        f = self.fiches[index]
        f.de_cote, f.raison_de_cote = True, raison

    def reprendre(self, index: int):
        f = self.fiches[index]
        if f.rapprochement is not None and f.ref_piece:
            f.de_cote, f.raison_de_cote = False, ''

    # --- Plan --------------------------------------------------------------------
    def planifier_par_regles(self, appellations=None) -> PlanLot:
        """Plan du lot par les règles de l'import (CDC § 10.12) : aucune question.
        Une fiche sans code produit est mise de côté (référence de pièce à saisir) ;
        ce que l'import ne sait pas trancher n'est pas importé et compté. Les
        créations restent partagées entre les fiches ; les créations bancales sont
        retenues (§ 10.14)."""
        from src.utils.rapprochement_fiche.coupe_titre import termes_appareils
        from src.utils.rapprochement_fiche.regles_import import (
            SANS_CODE_PRODUIT, decisions_import, retenir_creations_douteuses, sans_code_produit)
        regles: Dict[int, List[str]] = {}
        for i, f in self.fiches_actives():
            if f.de_cote:
                continue
            if sans_code_produit(f.rapprochement):
                self.mettre_de_cote(i, SANS_CODE_PRODUIT)
                continue
            f.decisions, regles[i] = decisions_import(f.rapprochement)
        plan = self._planifier()
        if plan.fiches_a_completer:
            for i, p in plan.plans:
                if not p.lignes_a_completer:
                    continue
                for index in p.lignes_a_completer:
                    self.fiches[i].decisions.appareils[index] = ChoixAppareil(ignorer=True)
                regles.setdefault(i, []).extend(p.a_completer)
            plan = self._planifier()
        # Créations bancales retenues (§ 10.14) ; une ligne retenue dont l'appareil est
        # créé proprement par une autre fiche du lot partage cette création (sinon la
        # relance la trouverait « exacte » et ajouterait un lien)
        termes = termes_appareils(appellations)
        a_refaire = {}
        for i, p in plan.plans:
            retenue = retenir_creations_douteuses(self.fiches[i].rapprochement,
                                                  self.fiches[i].decisions, p, termes)
            if retenue is not None:
                a_refaire[i] = retenue
        if a_refaire:
            plan = self._planifier()
            self._partager_creations_saines(plan, a_refaire)
            plan = self._planifier()
        plan.non_importees = {i: v for i, v in regles.items() if v}
        plan.a_refaire = a_refaire
        for i, p in plan.plans:
            p.non_importees = list(plan.non_importees.get(i, []))
            p.a_refaire = a_refaire.get(i)
        return plan

    def _rattacher_aux_creations(self, plans: List[Tuple[int, PlanEnregistrement]]
                                 ) -> Set[int]:
        """Ligne à compléter (absente sans type, à valider sans proposition) dont
        l'appareil est créé par une AUTRE ligne du lot : elle reprend la marque et le
        type de cette création, et la partage. Sans cela, la relance du lot la
        trouverait « exacte » et créerait des liens que le 1er passage n'a pas posés.
        Retourne les fiches à replanifier."""
        modeles: Dict[Tuple[str, str], AppareilACreer] = {}
        for _, plan in plans:
            for a in plan.appareils_a_creer:
                modeles.setdefault(cle_creation(a), a)
        a_refaire: Set[int] = set()
        if not modeles:
            return a_refaire
        for i, plan in plans:
            f = self.fiches[i]
            for index in plan.lignes_a_completer:
                a = f.rapprochement.appareils[index]
                # absente, ou « à valider » sans proposition (nom commercial seul…) :
                # la même marque et la même forme sont créées par le lot
                if a.niveau not in ('absent', 'a_valider') or a.suspecte:
                    continue
                cle = (cle_marque(a.marque or a.marque_fiche), forme_normalisee(a.ref_modele))
                modele = modeles.get(cle)
                if not cle[0] or modele is None:
                    continue
                f.decisions.appareils[index] = ChoixAppareil(creer=True, marque=modele.marque,
                                                             type=modele.type)
                a_refaire.add(i)
        return a_refaire

    def _partager_creations_saines(self, plan: PlanLot, a_refaire: Dict[int, object]):
        """Ligne retenue d'une fiche à refaire, dont la même marque et la même forme
        sont créées par une autre fiche : elle partage cette création."""
        if not plan.creations:
            return
        for i in a_refaire:
            f = self.fiches[i]
            for index, choix in list(f.decisions.appareils.items()):
                if not choix.ignorer:
                    continue
                a = f.rapprochement.appareils[index]
                if a.niveau not in ('absent', 'a_valider') or a.suspecte:
                    continue
                occurrences = plan.creations.get(
                    (cle_marque(a.marque or a.marque_fiche), forme_normalisee(a.ref_modele)))
                if occurrences:
                    modele = occurrences[0][1]
                    f.decisions.appareils[index] = ChoixAppareil(
                        creer=True, marque=modele.marque, type=modele.type)

    def _planifier(self) -> PlanLot:
        plans, de_cote, a_completer = [], [], []
        lignes = 0
        for i, f in enumerate(self.fiches):
            if f.de_cote or f.rapprochement is None or not f.ref_piece:
                de_cote.append(i)
                continue
            plans.append((i, planifier(f.rapprochement, f.decisions)))
        a_refaire = self._rattacher_aux_creations(plans)
        for k, (i, plan) in enumerate(plans):
            if i in a_refaire:
                plan = planifier(self.fiches[i].rapprochement, self.fiches[i].decisions)
                plans[k] = (i, plan)
            if plan.a_completer:
                a_completer.append(i)
                lignes += len(plan.a_completer)
        creations: Dict[Tuple[str, str], List[Tuple[int, AppareilACreer]]] = {}
        for i, plan in plans:
            for a in plan.appareils_a_creer:
                creations.setdefault(cle_creation(a), []).append((i, a))
        return PlanLot(plans, creations, de_cote, a_completer, lignes)


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
