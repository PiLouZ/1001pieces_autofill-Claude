"""
Ménage des marques (2026-11-24) : liste figée, simulation, écriture, retour arrière.

Trois natures de lignes dans la liste versionnée `data/corrections/menage_marques.csv`
(séparateur « ; », relue avant exécution) :

- `reference` : la marque collée dans une référence est retirée
  (« SMEG ST995 » → « ST995 », règle et garde-fous dans `utils/marque_collee.py`) ;
- `marque` : une écriture de marque ramenée à son nom (`AliasMarques`,
  « Glem » → « Glem Gas », « Concord » → « Concorde ») ;
- `fusion` : après nettoyage, l'appareil a exactement les mêmes références (et
  la même marque) qu'un autre : ses pièces passent sur celui-ci (`cible`), puis
  il est retiré (`DatabaseManager.fusionner_appareils`, une transaction).

Comme la correction des types du lot 1 (`CorrectionTypesService`) : une valeur
changée depuis la liste (à la main, par un import) est ignorée, jamais écrasée ;
une ligne d'historique par changement ; le retour arrière relit la liste dans
l'autre sens. **Une fusion ne se défait pas ainsi** : elle se défait en
restaurant la sauvegarde prise avant l'écriture.

Les décisions « appareils distincts » (`reference_decisions`, rangées par
réf. modèle) suivent la réf. modèle renommée (5 en base au 2026-11-24).
"""

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..core.constants import AliasMarques
from ..core.logger import app_logger
from ..utils.marque_collee import cle_marque, retirer_marque_collee
from .base_service import BaseService

ENTETES = ('nature', 'id', 'marque', 'champ', 'avant', 'apres', 'cible')

NATURE_REFERENCE = 'reference'
NATURE_MARQUE = 'marque'
NATURE_FUSION = 'fusion'
NATURES = (NATURE_REFERENCE, NATURE_MARQUE, NATURE_FUSION)

SENS_APPLIQUER = 'appliquer'
SENS_ANNULER = 'annuler'

# Colonnes touchées → libellé du champ dans l'historique (comme une saisie à la main)
CHAMPS = {'ref_modele': 'Référence modèle', 'commercial_ref': 'Référence commerciale',
          'manufacturer': 'Fabricant'}

_TAILLE_PAQUET = 500
_ALIAS = {cle_marque(e): nom for e, nom in AliasMarques.ALIAS.items()}


@dataclass(frozen=True)
class LigneMenage:
    nature: str
    appareil_id: int
    marque: str
    champ: str = ''           # colonne (reference, marque) ; '' pour une fusion
    avant: str = ''           # fusion : références du doublon « modèle | commerciale »
    apres: str = ''
    cible: Optional[int] = None   # fusion : appareil qui garde les pièces

    def inverse(self) -> 'LigneMenage':
        return LigneMenage(self.nature, self.appareil_id, self.marque, self.champ,
                           self.apres, self.avant, self.cible)


@dataclass
class BilanMenage:
    sens: str
    a_faire: List[LigneMenage] = field(default_factory=list)
    deja_faites: List[LigneMenage] = field(default_factory=list)
    # (ligne, raison)
    ignorees: List[Tuple[LigneMenage, str]] = field(default_factory=list)
    # id → (ref_modele, commercial_ref) lus avant écriture, pour l'historique
    references: Dict[int, Tuple[str, str]] = field(default_factory=dict)
    nb_appareils_avant: int = 0
    nb_appareils_apres: Optional[int] = None
    ecrit: bool = False
    fusions_ecrites: int = 0
    historique_ecrit: bool = False

    def par_nature(self) -> Counter:
        return Counter(l.nature for l in self.a_faire)

    @property
    def fusions(self) -> List[LigneMenage]:
        return [l for l in self.a_faire if l.nature == NATURE_FUSION]

    @property
    def comptage_conforme(self) -> bool:
        """Appareils en moins = fusions écrites."""
        return (self.nb_appareils_apres is not None
                and self.nb_appareils_avant - self.nb_appareils_apres == self.fusions_ecrites)


# ── Liste ──────────────────────────────────────────────────────────────────

def lire_liste(chemin) -> List[LigneMenage]:
    """Lire et contrôler la liste figée (ValueError, message en français)."""
    chemin = Path(chemin)
    with chemin.open(encoding='utf-8', newline='') as fichier:
        lecteur = csv.reader(fichier, delimiter=';')
        entete = tuple(next(lecteur, ()))
        if entete != ENTETES:
            raise ValueError(f"{chemin.name} : en-tête inattendu {entete!r}")
        lignes: List[LigneMenage] = []
        vus = set()
        for numero, brute in enumerate(lecteur, start=2):
            if not any(brute):
                continue
            if len(brute) != len(ENTETES):
                raise ValueError(f"{chemin.name}, ligne {numero} : {len(brute)} colonnes au lieu de {len(ENTETES)}")
            v = dict(zip(ENTETES, brute))
            nature = v['nature'].strip()
            if nature not in NATURES:
                raise ValueError(f"{chemin.name}, ligne {numero} : nature « {nature} » inconnue")
            try:
                ident = int(v['id'])
                cible = int(v['cible']) if v['cible'].strip() else None
            except ValueError:
                raise ValueError(f"{chemin.name}, ligne {numero} : identifiant invalide") from None
            champ = v['champ'].strip()
            if nature == NATURE_FUSION:
                if cible is None or cible == ident:
                    raise ValueError(f"{chemin.name}, ligne {numero} : fusion sans cible valide")
            else:
                attendu = ('ref_modele', 'commercial_ref') if nature == NATURE_REFERENCE else ('manufacturer',)
                if champ not in attendu:
                    raise ValueError(f"{chemin.name}, ligne {numero} : champ « {champ} » invalide")
                if v['avant'] == v['apres'] or not v['apres'].strip():
                    raise ValueError(f"{chemin.name}, ligne {numero} : valeur inchangée ou vide")
            cle = (nature, ident, champ)
            if cle in vus:
                raise ValueError(f"{chemin.name}, ligne {numero} : ligne en double")
            vus.add(cle)
            lignes.append(LigneMenage(nature, ident, v['marque'], champ, v['avant'], v['apres'], cible))
    return lignes


def ecrire_liste(chemin, lignes: Iterable[LigneMenage]) -> None:
    with Path(chemin).open('w', encoding='utf-8', newline='') as fichier:
        ecrivain = csv.writer(fichier, delimiter=';', lineterminator='\n')
        ecrivain.writerow(ENTETES)
        for l in lignes:
            ecrivain.writerow((l.nature, l.appareil_id, l.marque, l.champ, l.avant, l.apres,
                               '' if l.cible is None else l.cible))


def calculer_liste(appareils: Iterable[Tuple]) -> List[LigneMenage]:
    """Liste du ménage à partir des appareils (id, type, marque, ref_modele,
    commercial_ref). Lecture seule : c'est la liste à relire puis figer.

    Fusion : appareils de même marque (après alias) aux références identiques
    (sans casse) une fois nettoyées, dont au moins un a changé. L'appareil
    gardé est le plus ancien des non modifiés (sinon le plus ancien) ; pas de
    fusion si deux types renseignés diffèrent."""
    lignes: List[LigneMenage] = []
    groupes = defaultdict(list)
    modifies = set()
    for ident, type_, marque, ref, com in appareils:
        marque = (marque or '').strip()
        finale = _ALIAS.get(cle_marque(marque), marque)
        if finale != marque:
            lignes.append(LigneMenage(NATURE_MARQUE, ident, marque, 'manufacturer', marque, finale))
            modifies.add(ident)
        propres = {}
        for champ, valeur in (('ref_modele', ref), ('commercial_ref', com)):
            valeur = (valeur or '').strip()
            propre = retirer_marque_collee(valeur, finale, type_ or '')
            propres[champ] = propre
            if propre != valeur:
                lignes.append(LigneMenage(NATURE_REFERENCE, ident, finale, champ, valeur, propre))
                modifies.add(ident)
        if finale and (propres['ref_modele'] or propres['commercial_ref']):
            groupes[(cle_marque(finale), propres['ref_modele'].lower(),
                     propres['commercial_ref'].lower())].append(
                (ident, (type_ or '').strip(), finale, propres))
    for membres in groupes.values():
        if len(membres) < 2 or not any(m[0] in modifies for m in membres):
            continue
        if len({m[1] for m in membres if m[1]}) > 1:
            continue                         # types en désaccord : pas de fusion
        intacts = sorted(m[0] for m in membres if m[0] not in modifies)
        garde = intacts[0] if intacts else min(m[0] for m in membres)
        for ident, _t, finale, propres in sorted(membres):
            if ident != garde:
                lignes.append(LigneMenage(NATURE_FUSION, ident, finale, '',
                                          f"{propres['ref_modele']} | {propres['commercial_ref']}",
                                          '', garde))
    ordre = {NATURE_MARQUE: 0, NATURE_REFERENCE: 1, NATURE_FUSION: 2}
    return sorted(lignes, key=lambda l: (ordre[l.nature], l.appareil_id, l.champ))


# ── Service ────────────────────────────────────────────────────────────────

class MenageMarquesService(BaseService):
    """Applique (ou annule) la liste figée du ménage des marques."""

    def __init__(self, db_manager, parent_window=None, parent=None):
        super().__init__(parent_window, parent)
        self.db = db_manager

    def lire_appareils(self) -> List[Tuple]:
        return list(self.db.execute_query(
            "SELECT id, type, manufacturer, ref_modele, commercial_ref FROM appareils") or [])

    def _nb_appareils(self) -> int:
        return self.db.execute_query("SELECT COUNT(*) FROM appareils")[0][0]

    def _lire(self, ids: List[int]) -> Dict[int, Dict[str, str]]:
        trouves: Dict[int, Dict[str, str]] = {}
        ids = sorted(set(ids))
        for debut in range(0, len(ids), _TAILLE_PAQUET):
            paquet = ids[debut:debut + _TAILLE_PAQUET]
            marques = ','.join('?' * len(paquet))
            for ident, marque, ref, com in self.db.execute_query(
                    f"SELECT id, manufacturer, ref_modele, commercial_ref FROM appareils "
                    f"WHERE id IN ({marques})", paquet):
                trouves[ident] = {'manufacturer': (marque or '').strip(),
                                  'ref_modele': (ref or '').strip(),
                                  'commercial_ref': (com or '').strip()}
        return trouves

    def preparer(self, lignes: Iterable[LigneMenage], sens: str = SENS_APPLIQUER) -> BilanMenage:
        if sens not in (SENS_APPLIQUER, SENS_ANNULER):
            raise ValueError(f"sens inconnu : {sens}")
        lignes = list(lignes)
        bilan = BilanMenage(sens=sens, nb_appareils_avant=self._nb_appareils())
        en_base = self._lire([l.appareil_id for l in lignes]
                             + [l.cible for l in lignes if l.cible is not None])
        # Valeurs attendues après les changements de cette liste (pour la garde des fusions)
        apres = {i: dict(v) for i, v in en_base.items()}
        # Doublons dont la fusion est faite : leurs lignes de référence aussi
        fusionnes = {l.appareil_id for l in lignes
                     if l.nature == NATURE_FUSION and l.cible in en_base}
        for l in lignes:
            if l.nature == NATURE_FUSION:
                continue
            l = l if sens == SENS_APPLIQUER else l.inverse()
            v = en_base.get(l.appareil_id)
            if v is None and l.appareil_id in fusionnes:
                bilan.deja_faites.append(l)
            elif v is None:
                bilan.ignorees.append((l, "appareil absent"))
            elif v[l.champ] == l.avant:
                bilan.a_faire.append(l)
                apres[l.appareil_id][l.champ] = l.apres
            elif v[l.champ] == l.apres:
                bilan.deja_faites.append(l)
            else:
                bilan.ignorees.append((l, f"valeur en base « {v[l.champ]} »"))
        for l in (x for x in lignes if x.nature == NATURE_FUSION):
            if sens == SENS_ANNULER:
                bilan.ignorees.append((l, "fusion : se défait en restaurant la sauvegarde"))
                continue
            doublon, cible = apres.get(l.appareil_id), apres.get(l.cible)
            if doublon is None and cible is not None:
                bilan.deja_faites.append(l)
            elif doublon is None or cible is None:
                bilan.ignorees.append((l, "appareil absent"))
            elif _identite(doublon) != _identite(cible):
                bilan.ignorees.append((l, "références ou marque différentes de la cible"))
            else:
                bilan.a_faire.append(l)
        bilan.references = {i: (v['ref_modele'], v['commercial_ref']) for i, v in en_base.items()}
        return bilan

    def executer(self, lignes: Iterable[LigneMenage], sens: str = SENS_APPLIQUER,
                 provenance: str = "ménage des marques") -> BilanMenage:
        bilan = self.preparer(lignes, sens)
        maj: Dict[int, Dict[str, str]] = defaultdict(dict)
        for l in bilan.a_faire:
            if l.nature != NATURE_FUSION:
                maj[l.appareil_id][l.champ] = l.apres
        bilan.ecrit = True
        if maj:
            bilan.ecrit = self._ecrire(dict(maj))
            if not bilan.ecrit:
                app_logger.error(f"[Ménage marques] {len(maj)} appareil(s) non écrits")
                bilan.nb_appareils_apres = self._nb_appareils()
                return bilan
        # Décisions « appareils distincts » rangées par réf. modèle : elles suivent
        paires = sorted({(l.avant, l.apres) for l in bilan.a_faire
                         if l.nature == NATURE_REFERENCE and l.champ == 'ref_modele'})
        if paires and not self.db.renommer_decisions_reference(paires):
            app_logger.warning("[Ménage marques] décisions de référence non renommées")
        par_cible = defaultdict(list)
        for l in bilan.fusions:
            par_cible[l.cible].append(l.appareil_id)
        for cible, doublons in sorted(par_cible.items()):
            if self.db.fusionner_appareils(cible, doublons):
                bilan.fusions_ecrites += len(doublons)
            else:
                app_logger.error(f"[Ménage marques] fusion de {doublons} dans {cible} annulée")
        bilan.historique_ecrit = self._tracer(bilan, provenance)
        bilan.nb_appareils_apres = self._nb_appareils()
        app_logger.info(f"[Ménage marques] {dict(bilan.par_nature())} ({sens}), "
                        f"{bilan.fusions_ecrites} fusion(s) écrite(s), "
                        f"{len(bilan.deja_faites)} déjà faites, {len(bilan.ignorees)} ignorées")
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
            app_logger.error(f"[Ménage marques] échec d'écriture : {e}")
            return False

    def _tracer(self, bilan: BilanMenage, provenance: str) -> bool:
        """Une ligne par champ changé (comme une saisie à la main) et une par
        fusion (« Suppression »), avec la provenance."""
        horodatage = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        suffixe = " — retour arrière" if bilan.sens == SENS_ANNULER else ""
        details = json.dumps([f"(source : {provenance}{suffixe})"], ensure_ascii=False)
        lignes = []
        for l in bilan.a_faire:
            ref, com = bilan.references.get(l.appareil_id, ('', ''))
            appareil = f"{ref} - {com}" if com else ref
            if l.nature == NATURE_FUSION:
                r_cible, c_cible = bilan.references.get(l.cible, ('', ''))
                lignes.append((horodatage, 'delete',
                               f"Doublon « {appareil} » fusionné dans « {r_cible} - {c_cible} » "
                               f"(id {l.cible})", details, appareil, None, None, None))
                continue
            libelle = CHAMPS[l.champ]
            lignes.append((horodatage, 'edit', f"[{libelle}]  '{l.avant}' → '{l.apres}'",
                           details, appareil, libelle, l.avant, l.apres))
        if not lignes:
            return True
        try:
            ok = bool(self.db.ajouter_historique_modifications(lignes))
        except Exception as e:
            app_logger.error(f"[Ménage marques] historique non écrit : {e}")
            ok = False
        return ok


def _identite(v: Dict[str, str]) -> Tuple[str, str, str]:
    return (cle_marque(v['manufacturer']), v['ref_modele'].lower(), v['commercial_ref'].lower())
