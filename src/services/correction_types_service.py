"""
Corrections de type d'appareils en lot — règles de nomenclature, lot 1.

CDC `docs/cdc_regles_nomenclature.md` § 9.1 et § 10 : une liste FIGÉE et relue
avec le client (CSV versionné, `data/corrections/`) dit, pour chaque appareil,
le type attendu en base et le type qui le remplace. Ce service :

- prépare (rien n'est écrit) : relit le type en base de chaque appareil et
  classe la ligne — à corriger, déjà corrigée, ou ignorée (type changé entre-
  temps, à la main ou par un import : on n'écrase jamais une décision plus
  récente que la liste) ;
- exécute : écrit les types par la sauvegarde événementielle quand la fenêtre
  est là (sinon, scripts et tests, par la même mise à jour par lots du
  gestionnaire de base, comme `EnregistrementFicheService`), puis laisse une
  ligne par appareil dans `modifications_history`, au format d'une
  modification de Type faite à la main, avec sa provenance ;
- contrôle : comptage par type avant/après, comparé à l'écart attendu.

Le retour arrière est la même liste lue dans l'autre sens (`sens='annuler'`),
avec la même garde : seul un appareil encore au type posé par la correction
revient à son type d'origine.

Effet de bord connu : le déclencheur `trg_autocompletes_type_modifie` retire
la trace « auto-complété » du type d'un appareil corrigé (le type devient une
décision) ; un retour arrière ne la recrée pas.
"""

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..core.logger import app_logger
from .base_service import BaseService

# En-tête attendu du CSV (séparateur « ; »)
ENTETES = ('famille', 'id', 'marque', 'ref_modele', 'ref_commerciale',
           'libelle_origine', 'type_actuel', 'nouveau_type')

SENS_APPLIQUER = 'appliquer'
SENS_ANNULER = 'annuler'

# Même type d'action et même champ qu'une modification de Type à la main :
# l'historique l'affiche et la regroupe (×N) sans rien changer à l'interface.
ACTION_HISTORIQUE = 'edit'
CHAMP_HISTORIQUE = 'Type'

# Lecture des types par paquets (limite de variables SQLite)
_TAILLE_PAQUET = 500


@dataclass(frozen=True)
class CorrectionType:
    """Une ligne de la liste figée : type attendu en base → nouveau type."""
    famille: str
    appareil_id: int
    marque: str
    ref_modele: str
    ref_commerciale: str
    type_avant: str
    type_apres: str

    def inverse(self) -> 'CorrectionType':
        return CorrectionType(self.famille, self.appareil_id, self.marque,
                              self.ref_modele, self.ref_commerciale,
                              self.type_apres, self.type_avant)


@dataclass
class BilanCorrection:
    """Ce que la préparation a trouvé, et ce que l'exécution a fait."""
    sens: str
    a_corriger: List[CorrectionType] = field(default_factory=list)
    deja_faites: List[CorrectionType] = field(default_factory=list)
    # (correction, type trouvé en base ; None = appareil absent)
    ignorees: List[Tuple[CorrectionType, Optional[str]]] = field(default_factory=list)
    comptage_avant: Counter = field(default_factory=Counter)
    comptage_apres: Optional[Counter] = None
    # id → (ref_modele, commercial_ref) lus en base, pour l'historique
    references: Dict[int, Tuple[str, str]] = field(default_factory=dict)
    ecrit: bool = False
    historique_ecrit: bool = False

    def ecart_attendu(self) -> Dict[str, int]:
        """Variation du nombre d'appareils par type si tout `a_corriger` passe."""
        ecart: Counter = Counter()
        for c in self.a_corriger:
            ecart[c.type_avant] -= 1
            ecart[c.type_apres] += 1
        return {t: n for t, n in ecart.items() if n}

    def ecart_constate(self) -> Dict[str, int]:
        if self.comptage_apres is None:
            return {}
        types = set(self.comptage_avant) | set(self.comptage_apres)
        ecart = {t: self.comptage_apres[t] - self.comptage_avant[t] for t in types}
        return {t: n for t, n in ecart.items() if n}

    @property
    def comptage_conforme(self) -> bool:
        return self.comptage_apres is not None and self.ecart_constate() == self.ecart_attendu()


def lire_liste(chemin) -> List[CorrectionType]:
    """Lire et contrôler la liste figée. Lève ValueError (message en français)
    si l'en-tête, un identifiant ou un type est invalide, ou si un appareil y
    figure deux fois."""
    chemin = Path(chemin)
    with chemin.open(encoding='utf-8', newline='') as fichier:
        lecteur = csv.reader(fichier, delimiter=';')
        entete = tuple(next(lecteur, ()))
        if entete != ENTETES:
            raise ValueError(f"{chemin.name} : en-tête inattendu {entete!r}")
        corrections: List[CorrectionType] = []
        vus = set()
        for numero, ligne in enumerate(lecteur, start=2):
            if not any(ligne):
                continue
            if len(ligne) != len(ENTETES):
                raise ValueError(f"{chemin.name}, ligne {numero} : {len(ligne)} colonnes au lieu de {len(ENTETES)}")
            v = dict(zip(ENTETES, (x.strip() for x in ligne)))
            try:
                ident = int(v['id'])
            except ValueError:
                raise ValueError(f"{chemin.name}, ligne {numero} : identifiant « {v['id']} » invalide") from None
            if not v['type_actuel'] or not v['nouveau_type']:
                raise ValueError(f"{chemin.name}, ligne {numero} : type vide")
            if v['type_actuel'] == v['nouveau_type']:
                raise ValueError(f"{chemin.name}, ligne {numero} : type inchangé ({v['type_actuel']})")
            if ident in vus:
                raise ValueError(f"{chemin.name}, ligne {numero} : appareil {ident} en double")
            vus.add(ident)
            corrections.append(CorrectionType(v['famille'], ident, v['marque'], v['ref_modele'],
                                              v['ref_commerciale'], v['type_actuel'], v['nouveau_type']))
    return corrections


class CorrectionTypesService(BaseService):
    """Applique ou annule une liste figée de corrections de type."""

    def __init__(self, db_manager, parent_window=None, parent=None):
        super().__init__(parent_window, parent)
        self.db = db_manager

    # ------------------------------------------------------------------
    # Lecture (rien n'est écrit)
    # ------------------------------------------------------------------
    def comptage_par_type(self) -> Counter:
        return Counter({t: n for t, n in self.db.execute_query(
            "SELECT type, COUNT(*) FROM appareils GROUP BY type")})

    def _lire_appareils(self, ids: List[int]) -> Dict[int, Tuple[Optional[str], str, str]]:
        """id → (type, ref_modele, commercial_ref) des appareils présents."""
        trouves: Dict[int, Tuple[Optional[str], str, str]] = {}
        for debut in range(0, len(ids), _TAILLE_PAQUET):
            paquet = ids[debut:debut + _TAILLE_PAQUET]
            marques = ','.join('?' * len(paquet))
            for ident, type_, ref, commerciale in self.db.execute_query(
                    f"SELECT id, type, ref_modele, commercial_ref FROM appareils "
                    f"WHERE id IN ({marques})", paquet):
                trouves[ident] = (type_, ref or '', commerciale or '')
        return trouves

    def preparer(self, corrections: Iterable[CorrectionType],
                 sens: str = SENS_APPLIQUER) -> BilanCorrection:
        """Classer chaque ligne selon le type trouvé en base."""
        if sens not in (SENS_APPLIQUER, SENS_ANNULER):
            raise ValueError(f"sens inconnu : {sens}")
        liste = [c if sens == SENS_APPLIQUER else c.inverse() for c in corrections]
        bilan = BilanCorrection(sens=sens, comptage_avant=self.comptage_par_type())
        en_base = self._lire_appareils([c.appareil_id for c in liste])
        for c in liste:
            trouve = en_base.get(c.appareil_id)
            if trouve is None:
                bilan.ignorees.append((c, None))
            elif trouve[0] == c.type_avant:
                bilan.a_corriger.append(c)
            elif trouve[0] == c.type_apres:
                bilan.deja_faites.append(c)
            else:
                bilan.ignorees.append((c, trouve[0]))
        bilan.references = {i: (r, cr) for i, (_, r, cr) in en_base.items()}
        return bilan

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------
    def executer(self, corrections: Iterable[CorrectionType], sens: str = SENS_APPLIQUER,
                 provenance: str = "règles de nomenclature") -> BilanCorrection:
        """Préparer puis écrire les lignes à corriger, tracer, recompter."""
        bilan = self.preparer(corrections, sens)
        if not bilan.a_corriger:
            bilan.comptage_apres = Counter(bilan.comptage_avant)
            return bilan

        maj = {c.appareil_id: {'type': c.type_apres} for c in bilan.a_corriger}
        bilan.ecrit = self._ecrire(maj)
        if not bilan.ecrit:
            app_logger.error(f"[Nomenclature] {len(maj)} type(s) non écrits ({sens})")
            bilan.comptage_apres = self.comptage_par_type()
            return bilan

        bilan.historique_ecrit = self._tracer(bilan, provenance)
        bilan.comptage_apres = self.comptage_par_type()
        etat = "conforme" if bilan.comptage_conforme else "ÉCART"
        app_logger.info(f"[Nomenclature] {len(maj)} type(s) écrits ({sens}), "
                        f"{len(bilan.deja_faites)} déjà faits, {len(bilan.ignorees)} ignorés ; "
                        f"comptage {etat}")
        return bilan

    def _ecrire(self, maj: Dict[int, Dict[str, str]]) -> bool:
        """Par la sauvegarde événementielle si la fenêtre est là ; sinon (script,
        tests) par la même mise à jour par lots qu'elle appelle."""
        sauvegarde = getattr(self.parent_window, 'event_driven_save_service', None)
        try:
            if sauvegarde is not None and hasattr(sauvegarde, 'enregistrer_champs_appareils'):
                return bool(sauvegarde.enregistrer_champs_appareils(maj))
            return bool(self.db.update_multiple_cells_batch(maj))
        except Exception as e:
            app_logger.error(f"[Nomenclature] échec d'écriture : {e}")
            return False

    def _tracer(self, bilan: BilanCorrection, provenance: str) -> bool:
        """Une ligne d'historique par appareil, comme une modification de Type
        à la main, avec une ligne de provenance « (source : …) ».

        La provenance est la même pour toutes les lignes : le panneau
        d'historique regroupe les modifications identiques (×N) et, si leurs
        provenances diffèrent, les rebaptise « suggestions par similarité »."""
        horodatage = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        suffixe = " — retour arrière" if bilan.sens == SENS_ANNULER else ""
        details = json.dumps([f"(source : {provenance}{suffixe})"], ensure_ascii=False)
        lignes = []
        for c in bilan.a_corriger:
            ref, commerciale = bilan.references.get(
                c.appareil_id, (c.ref_modele, c.ref_commerciale))
            appareil = f"{ref} - {commerciale}" if commerciale else ref
            lignes.append((horodatage, ACTION_HISTORIQUE,
                           f"[{CHAMP_HISTORIQUE}]  '{c.type_avant or ''}' → '{c.type_apres or ''}'",
                           details, appareil, CHAMP_HISTORIQUE, c.type_avant or '', c.type_apres or ''))
        try:
            ok = bool(self.db.ajouter_historique_modifications(lignes))
        except Exception as e:
            app_logger.error(f"[Nomenclature] historique non écrit : {e}")
            ok = False
        if not ok:
            app_logger.error(f"[Nomenclature] {len(lignes)} ligne(s) d'historique non écrites")
        return ok
