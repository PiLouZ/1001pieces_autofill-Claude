"""
Reprise en masse des fiches du site, par lots (CDC docs/cdc_import_fiches_site.md,
§ 7.2 à 7.4, étape 4)

Le service tient une **session** de reprise :
- l'export en cours (deux CSV, `SignatureExport`) et l'état mémorisé en base
  (`reprise_site_etat` : dernier id_produit traité, date de l'export) ; un export
  différent de celui de l'état est signalé, l'utilisateur choisit de repartir de
  zéro ou de continuer ;
- une connexion **en lecture seule** à la base (`AccesBaseLecture.ouvrir`), gardée
  toute la session : l'index des marques reste en cache d'une fiche à l'autre et
  d'un lot à l'autre ; après l'écriture d'un lot, seules les marques où des
  appareils ont été créés sont oubliées ;
- le lecteur des exports, gardé lui aussi : seul le 1er lot d'une session repasse
  les produits déjà traités.

`analyser_lot_suivant` et `enregistrer_lot` tournent hors du thread principal
(l'interface passe par un QThread) ; `apres_lot` (caches, sauvegarde
événementielle) se fait sur le thread principal.

Écriture d'un lot, par les briques de l'étape 3 (`EnregistrementFicheService`) :
1. tous les appareils à créer du lot en UNE insertion du tronc d'import
   (`_batch_insert_devices`), dédoublonnés entre fiches (même marque, même forme
   normalisée) ;
2. chaque fiche : pièce, liens avec provenance, remplacements et équivalences,
   origines, produit du site, décisions ;
3. dans la même transaction : journal du lot, fiches mises de côté, et
   avancement du dernier id_produit.

Relancer un lot ne crée aucun doublon : l'état n'avance qu'une fois le lot
écrit en entier, et chaque écriture est rejouable (un appareil créé ressort
« exact », un lien présent ne fait que compléter sa provenance, une relation
présente est ignorée).
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from ..core.logger import app_logger
from .base_service import BaseService
from .enregistrement_fiche_service import EnregistrementFicheService, ResultatEnregistrement

Progression = Callable[[int, int, str], None]

# Statut d'un export choisi par rapport à l'état mémorisé
EXPORT_NOUVEAU = 'nouveau'              # aucune reprise commencée
EXPORT_IDENTIQUE = 'identique'          # l'export de l'état : on continue
EXPORT_DIFFERENT = 'different'          # autre export (plus récent ?) : repartir ou continuer


@dataclass
class ResultatLot:
    ok: bool = True
    annule: bool = False
    erreur: str = ''
    numero: Optional[int] = None
    fiches_ecrites: int = 0
    de_cote: int = 0
    appareils_crees: int = 0
    liens_crees: int = 0
    liens_completes: int = 0
    remplacements: int = 0
    equivalences: int = 0
    ecriture_s: float = 0.0
    taille_avant: int = 0
    taille_apres: int = 0
    marques_touchees: List[str] = field(default_factory=list)

    def resume(self) -> str:
        croissance = (self.taille_apres - self.taille_avant) / 1e6
        return (f"{self.fiches_ecrites} fiche(s) enregistrée(s), {self.de_cote} mise(s) de côté ; "
                f"{self.appareils_crees} appareil(s) créé(s), {self.liens_crees} lien(s) créé(s), "
                f"{self.liens_completes} complété(s) ; {self.remplacements} remplacement(s), "
                f"{self.equivalences} équivalence(s) ; {self.ecriture_s:.1f} s, "
                f"base {croissance:+.1f} Mo")


def taille_base(chemin: str) -> int:
    """Taille de la base, journal WAL compris."""
    total = 0
    for suffixe in ('', '-wal'):
        try:
            total += os.path.getsize(chemin + suffixe)
        except OSError:
            pass
    return total


class RepriseSiteService(BaseService):
    """Session de reprise des fiches du site par lots."""

    def __init__(self, db_manager, parent_window=None, parent=None, configuration=None,
                 fiche_service: Optional[EnregistrementFicheService] = None):
        super().__init__(parent_window, parent)
        self.db = db_manager
        self.fiche_service = fiche_service or EnregistrementFicheService(
            db_manager, parent_window, configuration=configuration)
        self.signature = None
        self._acces = None
        self._modeles = None
        self._lecteur = None                # générateur de lire_exports
        self._position: Optional[int] = None  # dernier id_produit consommé par le lecteur

    # -------------------------------------------------------------------------
    # Export et état
    # -------------------------------------------------------------------------
    def etat(self) -> Optional[Dict]:
        return self.db.etat_reprise_site()

    def examiner_export(self, chemin_produits: str, chemin_compatibilites: str = ''):
        """(signature, statut) d'un export par rapport à l'état mémorisé."""
        from ..utils.reprise_site import SignatureExport
        signature = SignatureExport.de(chemin_produits, chemin_compatibilites or None)
        etat = self.etat()
        if not etat or not etat.get('date_export'):
            return signature, EXPORT_NOUVEAU
        connue = SignatureExport(etat.get('chemin_produits') or '', etat.get('chemin_compatibilites') or '',
                                 etat.get('taille_produits') or 0, etat.get('taille_compatibilites') or 0,
                                 etat.get('date_export') or '')
        return signature, (EXPORT_IDENTIQUE if signature.meme_export(connue) else EXPORT_DIFFERENT)

    def adopter_export(self, signature, repartir_de_zero: bool = False):
        """L'export devient celui de la reprise ; `repartir_de_zero` remet l'état à 0."""
        self.db.definir_export_reprise_site(
            {'date_export': signature.date_export, 'taille_produits': signature.taille_produits,
             'taille_compatibilites': signature.taille_compatibilites,
             'chemin_produits': signature.chemin_produits,
             'chemin_compatibilites': signature.chemin_compatibilites},
            repartir_de_zero, datetime.now().isoformat(timespec='seconds'))
        self.signature = signature
        self._lecteur, self._position = None, None
        app_logger.info(f"[Reprise site] export {signature.chemin_produits} du "
                        f"{signature.date_export} " + ("(depuis le début)" if repartir_de_zero
                                                       else "(reprise continuée)"))

    def dernier_id(self) -> int:
        etat = self.etat()
        return int(etat['dernier_id']) if etat else 0

    # -------------------------------------------------------------------------
    # Analyse (hors du thread principal)
    # -------------------------------------------------------------------------
    def _acces_lecture(self):
        from ..utils.rapprochement_fiche import AccesBaseLecture
        if self._acces is None:
            self._acces = AccesBaseLecture.ouvrir(self.db.db_file)
        return self._acces

    def _modeles_lecture(self):
        if self._modeles is None:
            self._modeles = self.fiche_service._modeles()
        return self._modeles

    def analyser_lot_suivant(self, taille: int = 100, progression: Optional[Progression] = None,
                             annule: Optional[Callable[[], bool]] = None):
        """Lot suivant de l'export (après le dernier id_produit traité), analysé.
        None quand l'export est épuisé. Le même lot revient tant qu'il n'est pas
        enregistré (relance)."""
        from ..utils.reprise_site import analyser_lot, lire_exports, prochain_lot
        if self.signature is None:
            raise RuntimeError("aucun export choisi")
        depart = self.dernier_id()
        if self._lecteur is None or self._position != depart:
            if progression is not None and depart:
                progression(0, 0, f"Passage des produits déjà traités (jusqu'à {depart})…")
            self._lecteur = lire_exports(self.signature.chemin_produits,
                                         self.signature.chemin_compatibilites or None,
                                         apres_id=depart)
        if progression is not None:
            progression(0, 0, "Lecture des exports…")
        export = prochain_lot(self._lecteur, taille)
        if export is None:
            self._position = depart
            return None
        self._position = export.dernier_id
        return analyser_lot(export, self._acces_lecture(), self.fiche_service.configuration(),
                            self._modeles_lecture(), progression, annule)

    def analyser_fiches_de_cote(self, progression: Optional[Progression] = None,
                                annule: Optional[Callable[[], bool]] = None):
        """Lot formé des fiches mises de côté (toutes), relues dans l'export."""
        from ..utils.reprise_site import analyser_lot, lire_exports, prochain_lot
        ids = {f['id_produit'] for f in self.db.fiches_de_cote_reprise_site()}
        if not ids or self.signature is None:
            return None
        lecteur = lire_exports(self.signature.chemin_produits,
                               self.signature.chemin_compatibilites or None, seulement=ids)
        export = prochain_lot(lecteur, len(ids))
        if export is None:
            return None
        lot = analyser_lot(export, self._acces_lecture(), self.fiche_service.configuration(),
                           self._modeles_lecture(), progression, annule)
        lot.fiches_de_cote = True
        return lot

    # -------------------------------------------------------------------------
    # Écriture (hors du thread principal)
    # -------------------------------------------------------------------------
    def enregistrer_lot(self, lot, plan, progression: Optional[Progression] = None,
                        annule: Optional[Callable[[], bool]] = None) -> ResultatLot:
        """Écrit un lot planifié (`plan.pret`). L'état n'avance qu'à la fin."""
        from ..utils.reprise_site import mesures_lot
        res = ResultatLot(taille_avant=taille_base(self.db.db_file))
        if plan.en_attente or plan.fiches_a_completer:
            res.ok, res.erreur = False, "lot non validé : " + "; ".join(
                plan.en_attente + [f"{len(plan.fiches_a_completer)} fiche(s) à compléter"])
            return res
        debut = time.time()
        try:
            self._ecrire_lot(lot, plan, res, progression, annule)
        except Exception as e:
            app_logger.error(f"[Reprise site] lot {lot.export.premier_id}-{lot.export.dernier_id} "
                             f"interrompu : {e}")
            res.ok, res.erreur = False, str(e)
        res.ecriture_s = time.time() - debut
        res.taille_apres = taille_base(self.db.db_file)
        if res.ok and not res.annule:
            self._clore_lot(lot, plan, res, mesures_lot(lot, plan))
        if self._acces is not None:
            self._acces.oublier(res.marques_touchees)
        app_logger.info(f"[Reprise site] lot {lot.export.premier_id}-{lot.export.dernier_id} : "
                        + (res.resume() if res.ok and not res.annule else res.erreur or "annulé"))
        return res

    def _ecrire_lot(self, lot, plan, res: ResultatLot, progression, annule):
        from ..utils.rapprochement_fiche.decisions import AppareilACreer
        # 1. Appareils à créer, une fois pour tout le lot (1ʳᵉ occurrence : écriture, nom, type)
        cles = list(plan.creations)
        uniques = [AppareilACreer(n, *self._attributs(plan.creations[c][0][1]))
                   for n, c in enumerate(cles)]
        if progression is not None:
            progression(0, len(plan.plans), f"Création de {len(uniques)} appareil(s)…")
        ids = self.fiche_service.creer_appareils(uniques)
        res.appareils_crees = len(ids)
        res.marques_touchees = sorted({a.marque for a in uniques})
        par_fiche: Dict[int, Dict[int, int]] = {}
        for n, c in enumerate(cles):
            for i_fiche, a in plan.creations[c]:
                par_fiche.setdefault(i_fiche, {})[a.index] = ids[n]
        # 2. Fiche par fiche
        for k, (i_fiche, p) in enumerate(plan.plans):
            if annule is not None and annule():
                res.annule = True
                return
            if progression is not None:
                progression(k, len(plan.plans), f"Fiche {lot.fiches[i_fiche].id_produit} "
                                                f"({p.ref_piece})")
            r = ResultatEnregistrement()
            self.fiche_service._ecrire(p, r, nouveaux=par_fiche.get(i_fiche, {}))
            res.fiches_ecrites += 1
            res.liens_crees += r.liens_crees
            res.liens_completes += r.liens_completes
            res.remplacements += r.relations.get('successions', 0)
            res.equivalences += r.relations.get('equivalences', 0)
        if progression is not None:
            progression(len(plan.plans), len(plan.plans), "Fiches enregistrées")

    @staticmethod
    def _attributs(a) -> Tuple[str, str, str, str]:
        return a.marque, a.ref_modele, a.nom, a.type

    def _clore_lot(self, lot, plan, res: ResultatLot, mesures: Dict):
        """Journal du lot, fiches mises de côté, dernier id_produit : une transaction."""
        le = datetime.now().isoformat(timespec='seconds')
        date_export = self.signature.date_export if self.signature else ''
        de_cote = [(lot.fiches[i].id_produit, lot.fiches[i].ref_piece, lot.fiches[i].nom,
                    lot.fiches[i].raison_de_cote or "profil ambigu laissé de côté")
                   for i in plan.de_cote]
        res.de_cote = len(de_cote)
        mesures = dict(mesures, resultat={
            'appareils_crees': res.appareils_crees, 'liens_crees': res.liens_crees,
            'liens_completes': res.liens_completes, 'remplacements': res.remplacements,
            'equivalences': res.equivalences})
        db = self.db
        with db._query_lock:
            ecrites = [lot.fiches[i].id_produit for i, _ in plan.plans]
            db._retirer_de_cote_reprise_site(ecrites)
            db._mettre_de_cote_reprise_site(de_cote, date_export, le)
            res.numero = db._journaliser_lot_reprise_site({
                'premier_id': lot.export.premier_id, 'dernier_id': lot.export.dernier_id,
                'date_export': date_export, 'produits': len(lot.export.produits)
                + lot.export.sans_contenu, 'fiches': res.fiches_ecrites, 'de_cote': res.de_cote,
                'analyse_s': round(lot.duree_analyse, 2), 'ecriture_s': round(res.ecriture_s, 2),
                'taille_avant': res.taille_avant, 'taille_apres': res.taille_apres,
                'mesures': json.dumps(mesures, ensure_ascii=False), 'enregistre_le': le})
            if not getattr(lot, 'fiches_de_cote', False):
                db._avancer_reprise_site(lot.export.dernier_id, le)
            db.conn.commit()

    # -------------------------------------------------------------------------
    # Thread principal
    # -------------------------------------------------------------------------
    def apres_lot(self, res: ResultatLot):
        """Caches invalidés et sauvegarde événementielle, une fois par lot."""
        if not res.fiches_ecrites and not res.appareils_crees:
            return
        bilan = ResultatEnregistrement(appareils_crees=res.appareils_crees,
                                       liens_crees=res.liens_crees,
                                       liens_completes=res.liens_completes)
        self.fiche_service._apres_ecriture(bilan, source="reprise_site")

    def fermer(self):
        if self._acces is not None:
            self._acces.fermer()
            self._acces = None
        self._lecteur = None
