"""
Revue des propositions de type des règles de nomenclature (CDC
docs/cdc_regles_nomenclature.md § 8.2, D8, lot 4).

- accepter : le type proposé est écrit par la sauvegarde événementielle
  (`CorrectionTypesService`, déjà utilisé au lot 1), avec une ligne
  d'historique par appareil au format d'une modification de Type à la main et
  la provenance « règles de nomenclature, règle … » ; un appareil dont le type
  a changé depuis le calcul est ignoré, jamais écrasé. Chaque acceptation est
  rangée en LOT (une règle = un lot), annulable depuis l'écran Règles ;
- refuser : le refus est rangé dans `refus_completions` (champ « type ») — la
  proposition n'est plus jamais refaite, ni par une règle, ni par
  l'auto-complétion de l'import ;
- récapitulatif avant une acceptation groupée : nombre d'appareils et
  comptage par type avant/après (D8) ;
- acceptation groupée permise pour les propositions **fortes**, et pour les
  **simples d'une règle validée sur source web** (décision client du lot 4,
  cas Gaggenau `BS*`) ; les autres simples se décident une par une.

Aucune proposition n'est calculée ici : c'est `RegleNomenclatureService`.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from ..core.logger import app_logger
from ..utils.nomenclature.force import FORCE_FORTE
from .base_service import BaseService
from .correction_types_service import (SENS_ANNULER, SENS_APPLIQUER, BilanCorrection,
                                       CorrectionType, CorrectionTypesService)
from .regle_nomenclature_service import CHAMP_REFUS, libelle_regle

PROVENANCE = "règles de nomenclature"


def _maintenant() -> str:
    return datetime.now().isoformat(sep=' ', timespec='seconds')


def groupable(proposition: dict) -> bool:
    """Une proposition peut-elle être acceptée avec d'autres d'un seul geste ?
    Forte (D8), ou simple d'une règle validée sur une source web (lot 4)."""
    if proposition.get('force') == FORCE_FORTE:
        return True
    return proposition.get('origine') == 'web' and bool((proposition.get('source_url') or '').strip())


def libelle_proposition_regle(proposition: dict) -> str:
    """Libellé de la règle d'une proposition détaillée."""
    if not proposition.get('motif'):
        return "règle supprimée"
    return libelle_regle({'portee': proposition.get('portee'), 'cible': proposition.get('cible'),
                          'motif': proposition.get('motif'),
                          'type_resultat': proposition.get('type_propose')})


@dataclass
class Recapitulatif:
    """Ce qu'une acceptation changerait (D8)."""
    nb: int = 0
    # type → nombre d'appareils, pour les seuls types touchés
    avant: Dict[str, int] = field(default_factory=dict)
    apres: Dict[str, int] = field(default_factory=dict)
    par_regle: Counter = field(default_factory=Counter)

    def lignes(self) -> List[tuple]:
        """[(type, avant, après, écart)] triées par écart décroissant (en valeur absolue)."""
        out = [(t, self.avant.get(t, 0), self.apres.get(t, 0),
                self.apres.get(t, 0) - self.avant.get(t, 0)) for t in set(self.avant) | set(self.apres)]
        return sorted(out, key=lambda l: (-abs(l[3]), l[0]))


@dataclass
class BilanAcceptation:
    acceptees: int = 0
    ignorees: int = 0                 # type changé depuis le calcul : laissé tel quel
    deja_faites: int = 0
    lots: List[int] = field(default_factory=list)
    erreur: str = ''


class RevuePropositionsService(BaseService):
    """Accepter, refuser, annuler les propositions de type."""

    def __init__(self, db_manager, parent_window=None):
        super().__init__(parent_window)
        self.db_manager = db_manager
        self._corrections = CorrectionTypesService(db_manager, parent_window)

    # ── Lecture ─────────────────────────────────────────────────────────────

    def propositions(self) -> List[dict]:
        """Propositions détaillées (appareil + règle) ; [] si la lecture échoue."""
        return self.db_manager.lire_propositions_detaillees() or []

    def propositions_par_appareil(self) -> Dict[int, dict]:
        return {p['appareil_id']: p for p in self.propositions()}

    def recapitulatif(self, propositions: Iterable[dict]) -> Recapitulatif:
        propositions = list(propositions)
        recap = Recapitulatif(nb=len(propositions))
        if not propositions:
            return recap
        comptage = self._corrections.comptage_par_type()
        ecart: Counter = Counter()
        for p in propositions:
            ecart[p.get('type_actuel') or ''] -= 1
            ecart[p['type_propose']] += 1
            recap.par_regle[libelle_proposition_regle(p)] += 1
        for t, n in ecart.items():
            # Type vide : NULL et '' comptent ensemble
            avant = comptage.get(t, 0) if t else comptage.get(None, 0) + comptage.get('', 0)
            recap.avant[t or "(vide)"] = avant
            recap.apres[t or "(vide)"] = avant + n
        return recap

    # ── Décisions ───────────────────────────────────────────────────────────

    def accepter(self, propositions: Iterable[dict]) -> BilanAcceptation:
        """Écrire les types proposés, un lot (annulable) par règle."""
        bilan = BilanAcceptation()
        par_regle: Dict[Optional[int], List[dict]] = {}
        for p in propositions:
            par_regle.setdefault(p.get('regle_id'), []).append(p)
        traitees: List[int] = []
        for regle_id, groupe in par_regle.items():
            libelle = libelle_proposition_regle(groupe[0])
            corrections = [CorrectionType(f"règle {regle_id}", p['appareil_id'],
                                          p.get('manufacturer') or '', p.get('ref_modele') or '',
                                          p.get('commercial_ref') or '', p.get('type_actuel'),
                                          p['type_propose'])
                           for p in groupe]
            resultat = self._corrections.executer(
                corrections, SENS_APPLIQUER, provenance=f"{PROVENANCE}, {libelle}")
            if resultat.a_corriger and not resultat.ecrit:
                bilan.erreur = "écriture des types échouée (voir le journal)"
                break
            bilan.acceptees += len(resultat.a_corriger)
            bilan.deja_faites += len(resultat.deja_faites)
            bilan.ignorees += len(resultat.ignorees)
            if resultat.a_corriger:
                lot = self.db_manager.enregistrer_lot_acceptation(
                    regle_id, libelle, _maintenant(),
                    [(c.appareil_id, c.type_avant, c.type_apres) for c in resultat.a_corriger])
                if lot is not None:
                    bilan.lots.append(lot)
                else:
                    app_logger.error(f"[Nomenclature] lot d'acceptation non rangé ({libelle}) : "
                                     f"annulation depuis l'écran impossible")
            # Acceptées, déjà faites ou périmées : plus rien à proposer
            traitees += [p['appareil_id'] for p in groupe]
        if traitees:
            self.db_manager.supprimer_propositions_type(traitees)
        app_logger.info(f"[Nomenclature] propositions acceptées : {bilan.acceptees} écrite(s), "
                        f"{bilan.ignorees} ignorée(s) (type changé), {len(bilan.lots)} lot(s)")
        return bilan

    def refuser(self, propositions: Iterable[dict]) -> int:
        """Mémoriser les refus (jamais reproposés) et retirer les propositions."""
        propositions = list(propositions)
        if not propositions:
            return 0
        n = self.db_manager.enregistrer_refus(
            (p['appareil_id'], CHAMP_REFUS, p['type_propose']) for p in propositions)
        if n:
            self.db_manager.supprimer_propositions_type(p['appareil_id'] for p in propositions)
        app_logger.info(f"[Nomenclature] {n} proposition(s) refusée(s)")
        return n

    # ── Annulation d'un lot ─────────────────────────────────────────────────

    def lots(self, limite: int = 50) -> List[dict]:
        return self.db_manager.lister_lots_acceptation(limite)

    def annuler_lot(self, lot: dict) -> BilanCorrection:
        """Remettre le type d'avant sur les appareils d'un lot encore au type
        accepté ; un appareil modifié depuis est laissé tel quel."""
        lignes = self.db_manager.lire_acceptations(lot['id'])
        corrections = [CorrectionType(f"lot {lot['id']}", a, '', '', '', avant, apres)
                       for a, avant, apres in lignes]
        bilan = self._corrections.executer(
            corrections, SENS_ANNULER, provenance=f"{PROVENANCE}, {lot['libelle']}")
        if bilan.ecrit or not bilan.a_corriger:
            self.db_manager.marquer_lot_annule(lot['id'], _maintenant())
        return bilan
