"""
Règles de nomenclature — service du moteur, sans écran (CDC
docs/cdc_regles_nomenclature.md § 3, 5-7, lot 3).

- enregistre des règles après contrôle (type de la liste fermée
  `types_autorises`, jamais un type accessoire, motif valide, portée connue) ;
- charge le catalogue versionné `data/regles_nomenclature.csv` (une règle
  déjà en base n'est jamais écrasée : son statut a pu changer depuis) ;
- calcule les propositions de type (§ 6.2, § 7) et les mesures des règles,
  rangées dans `propositions_type` ; AUCUN type d'appareil n'est écrit ici :
  l'application passera par la revue (lot 4) et la sauvegarde événementielle ;
- découvre des règles candidates (§ 6.3), rangées en statut « proposée ».

Lot 4 (écran Règles, § 8.1) : statut et note d'une règle, exemples
d'appareils (désaccords d'abord), écriture séparée du calcul
(`ecrire_propositions`, `enregistrer_decouvertes`) pour calculer en
arrière-plan et écrire sur le fil principal ; la découverte ne repropose pas
un motif déjà tranché. L'acceptation et le refus des propositions sont dans
`RevuePropositionsService`.

Le cœur est en fonctions pures (`src/utils/nomenclature/`) ; ce service ne
fait que lire la base, assembler et écrire les deux tables du moteur.
"""

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..core.constants import TypesAppareils
from ..core.logger import app_logger
from ..utils.filtre_colonne import MotifRegleInvalide, forme_motif_regle, valider_motif_regle
from ..utils.lecteur_fiche.lecteur import cle_marque
from ..utils.nomenclature.cles import CLE_CODE, CLES, cle_code, cle_nom
from ..utils.nomenclature.decouverte import RegleCandidate, ZoneGrise, decouvrir
from ..utils.nomenclature.force import (force_proposition, libelle_d_accord, part_du_vote)
from ..utils.nomenclature.moteur import (ORIGINES, PORTEE_GROUPE, PORTEES, STATUT_PROPOSEE,
                                         STATUT_VALIDEE, STATUTS, IndexRegles, Regle)
from ..utils.rapprochement_fiche.configuration import charger_configuration
from ..utils.types_autorises import charger_types_autorises, est_type_autorise
from .base_service import BaseService

CHEMIN_CATALOGUE = Path(__file__).resolve().parents[2] / 'data' / 'regles_nomenclature.csv'
ENTETES_CATALOGUE = ('portee', 'cible', 'cle', 'motif', 'type_resultat', 'statut', 'origine',
                     'source_url', 'note')
CHAMP_REFUS = 'type'   # refus_completions : un type refusé n'est jamais reproposé
# Note posée par la découverte sur une règle trouvée sous une zone grise (§ 6.3)
PREFIXE_NOTE_ZONE_GRISE = "sous la zone grise "
# D7 : pureté à partir de laquelle une règle découverte peut être validée d'office
PURETE_D7 = 0.98


def zone_grise_de(regle: dict) -> str:
    """« AK* » si la règle a été trouvée sous une zone grise, sinon ''."""
    note = (regle.get('note') or '').strip()
    if not note.startswith(PREFIXE_NOTE_ZONE_GRISE):
        return ''
    reste = note[len(PREFIXE_NOTE_ZONE_GRISE):].split()
    return reste[0] if reste else ''


def purete(regle: dict) -> Optional[float]:
    """Part des appareils couverts déjà au type de la règle (None : jamais mesurée)."""
    couverture, accord = regle.get('couverture'), regle.get('accord')
    if not couverture or accord is None:
        return None
    return accord / couverture


def pure_d7(regle: dict) -> bool:
    """Pureté ≥ 98 % (D7) — le 2e signal se lit sur la fiche de la règle."""
    p = purete(regle)
    return p is not None and p >= PURETE_D7


def libelle_regle(regle: dict) -> str:
    """« Gaggenau BS* → Four vapeur » (« groupe Whirlpool … » pour un groupe)."""
    portee = "groupe " if regle.get('portee') == PORTEE_GROUPE else ""
    return f"{portee}{regle.get('cible', '')} {regle.get('motif', '')} → {regle.get('type_resultat', '')}"


def _maintenant() -> str:
    return datetime.now().isoformat(sep=' ', timespec='seconds')


def lire_catalogue(chemin=None) -> List[dict]:
    """Lignes du catalogue (CSV « ; », en-tête ENTETES_CATALOGUE).
    Lève ValueError (message en français) si l'en-tête ou une ligne est invalide."""
    chemin = Path(chemin) if chemin else CHEMIN_CATALOGUE
    with chemin.open(encoding='utf-8', newline='') as fichier:
        lecteur = csv.reader(fichier, delimiter=';')
        entete = tuple(next(lecteur, ()))
        if entete != ENTETES_CATALOGUE:
            raise ValueError(f"{chemin.name} : en-tête inattendu {entete!r}")
        lignes = []
        for numero, ligne in enumerate(lecteur, start=2):
            if not any(x.strip() for x in ligne):
                continue
            if len(ligne) != len(ENTETES_CATALOGUE):
                raise ValueError(f"{chemin.name}, ligne {numero} : {len(ligne)} colonnes "
                                 f"au lieu de {len(ENTETES_CATALOGUE)}")
            lignes.append(dict(zip(ENTETES_CATALOGUE, (x.strip() for x in ligne))))
    return lignes


@dataclass
class BilanCatalogue:
    lues: int = 0
    ajoutees: int = 0
    deja_presentes: int = 0
    # (ligne, messages)
    refusees: List[Tuple[dict, List[str]]] = field(default_factory=list)


@dataclass
class BilanPropositions:
    """Ce que le calcul a trouvé (et écrit, si demandé)."""
    appareils: int = 0
    couverts: int = 0                         # au moins une règle validée s'applique
    conflits: List[Tuple[int, Regle, Regle]] = field(default_factory=list)
    refusees: int = 0                         # proposition écartée par un refus mémorisé
    # appareil_id → ligne de propositions_type (dict)
    propositions: Dict[int, dict] = field(default_factory=dict)
    # id de règle → (couverture, accord), toutes règles, tous statuts
    mesures: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    types_hors_liste: Counter = field(default_factory=Counter)
    erreur: str = ''
    ecrit: bool = False
    calcule_le: str = ''
    # Calcul restreint à ces appareils (typage à l'import, lot 5) : None = toute la base.
    # Les mesures des règles n'y sont pas tenues (elles valent pour toute la base).
    appareil_ids: Optional[Tuple[int, ...]] = None

    def par_regle(self) -> Counter:
        return Counter((p['regle_id'], p['type_actuel'], p['type_propose'])
                       for p in self.propositions.values())

    def par_force(self) -> Counter:
        return Counter(p['force'] for p in self.propositions.values())


@dataclass
class ExemplesRegle:
    """Appareils couverts par une règle (fiche de l'écran Règles)."""
    couverture: int = 0
    accord: int = 0
    # (id, marque, ref_modele, commercial_ref, type en base, libellé d'origine)
    desaccords: List[tuple] = field(default_factory=list)
    accords: List[tuple] = field(default_factory=list)
    # Règle de groupe : marques qui ont leur propre règle sur ce motif (§ 6.2)
    masquees: List[str] = field(default_factory=list)
    erreur: str = ''


@dataclass
class BilanDecouverte:
    candidates: List[RegleCandidate] = field(default_factory=list)
    zones_grises: List[ZoneGrise] = field(default_factory=list)
    nouvelles: List[RegleCandidate] = field(default_factory=list)   # pas encore en base
    deja_tranchees: int = 0   # motif réglé par une règle validée/rejetée (marque ou groupe)
    ajoutees: int = 0


class _ReglesIndexees:
    """Règles candidates d'une (marque, clé), prêtes pour les mesures.

    Les préfixes purs (« AKZ* ») sont rangés par leur texte : une clé ne
    consulte que ses propres débuts (≤ 1 recherche par caractère) au lieu de
    tester chaque règle. Après une découverte (≈ 7 400 règles proposées), le
    test règle par règle faisait passer le calcul de 3 s à plus de 100 s ; le
    résultat est identique (mêmes règles, même condition `s_applique`)."""

    __slots__ = ('_prefixes', '_autres', '_longueur_max')

    def __init__(self, regles: Iterable[Regle]):
        from ..utils.filtre_colonne import FORME_PREFIXE
        self._prefixes: Dict[str, List[Regle]] = {}
        self._autres: List[Regle] = []
        for r in regles:
            if r.forme == FORME_PREFIXE:
                self._prefixes.setdefault(r.motif[:-1], []).append(r)
            else:
                self._autres.append(r)
        self._longueur_max = max((len(k) for k in self._prefixes), default=0)

    def qui_s_appliquent(self, valeur: str) -> List[Regle]:
        if not valeur:
            return []
        trouvees = []
        for longueur in range(1, min(len(valeur), self._longueur_max) + 1):
            trouvees.extend(self._prefixes.get(valeur[:longueur], ()))
        trouvees.extend(r for r in self._autres if r.s_applique(valeur))
        return trouvees


class RegleNomenclatureService(BaseService):
    """Moteur des règles de nomenclature (lot 3), et ce que l'écran Règles en lit (lot 4)."""

    def __init__(self, db_manager, parent_window=None, types_autorises=None, configuration=None):
        super().__init__(parent_window)
        self.db_manager = db_manager
        self.types_autorises = (tuple(types_autorises) if types_autorises is not None
                                else charger_types_autorises())
        self._configuration = configuration or charger_configuration()

    # ── Groupes de marques (rapprochement_fiche/configuration.py) ────────────

    def groupe_de(self, marque: str) -> str:
        return self._configuration.groupe_de.get(cle_marque(marque), '')

    def groupes(self) -> List[str]:
        return list((self._configuration.donnees.get('groupes_marques') or {}))

    # ── Contrôle et enregistrement (§ 3) ────────────────────────────────────

    def controler_regle(self, regle: dict) -> List[str]:
        """Messages d'erreur (en français) ; liste vide = règle enregistrable."""
        erreurs = []
        portee, cible = regle.get('portee'), (regle.get('cible') or '').strip()
        if portee not in PORTEES:
            erreurs.append(f"portée « {portee} » inconnue (marque ou groupe)")
        if not cible:
            erreurs.append("cible vide")
        elif portee == PORTEE_GROUPE and cle_marque(cible) not in {cle_marque(g) for g in self.groupes()}:
            erreurs.append(f"groupe « {cible} » inconnu")
        if regle.get('cle') not in CLES:
            erreurs.append(f"clé « {regle.get('cle')} » inconnue (nom ou code)")
        if (regle.get('statut') or STATUT_PROPOSEE) not in STATUTS:
            erreurs.append(f"statut « {regle.get('statut')} » inconnu")
        if (regle.get('origine') or 'saisie') not in ORIGINES:
            erreurs.append(f"origine « {regle.get('origine')} » inconnue")
        type_resultat = regle.get('type_resultat') or ''
        if type_resultat in TypesAppareils.ACCESSOIRES:
            erreurs.append(f"« {type_resultat} » est un type accessoire, exclu des règles (D9)")
        elif not est_type_autorise(type_resultat, self.types_autorises):
            erreurs.append(f"type « {type_resultat} » hors de la liste des types autorisés")
        try:
            motif = valider_motif_regle(regle.get('motif') or '')
            if regle.get('cle') == CLE_CODE and any(c.isalpha() or c == '@' for c in
                                                    motif.replace('[', '').replace(']', '')):
                erreurs.append(f"motif « {motif} » : la clé code n'a que des chiffres")
        except MotifRegleInvalide as e:
            erreurs.append(str(e))
        return erreurs

    def enregistrer_regles(self, regles: Iterable[dict]) -> BilanCatalogue:
        """Contrôler puis ajouter des règles ; une règle déjà en base (même portée,
        cible, clé, motif) reste telle quelle."""
        bilan = BilanCatalogue()
        valides = []
        horodatage = _maintenant()
        for r in regles:
            bilan.lues += 1
            erreurs = self.controler_regle(r)
            if erreurs:
                bilan.refusees.append((r, erreurs))
                continue
            motif = valider_motif_regle(r['motif'])
            statut = r.get('statut') or STATUT_PROPOSEE
            valides.append({
                'portee': r['portee'], 'cible': r['cible'].strip(), 'cle': r['cle'],
                'forme': forme_motif_regle(motif), 'motif': motif,
                'type_resultat': r['type_resultat'], 'statut': statut,
                'origine': r.get('origine') or 'saisie', 'source_url': r.get('source_url') or None,
                'note': r.get('note') or None, 'couverture': r.get('couverture'),
                'accord': r.get('accord'), 'calcule_le': r.get('calcule_le'),
                'valide_le': horodatage if statut == STATUT_VALIDEE else None})
        if valides:
            bilan.ajoutees = self.db_manager.inserer_regles_nomenclature(valides)
        bilan.deja_presentes = len(valides) - bilan.ajoutees
        return bilan

    def charger_catalogue(self, chemin=None, ecrire: bool = True) -> BilanCatalogue:
        """Catalogue versionné → table des règles (ou contrôle seul, sans écrire)."""
        lignes = lire_catalogue(chemin)
        if ecrire:
            return self.enregistrer_regles(lignes)
        bilan = BilanCatalogue(lues=len(lignes))
        connues = {(r['portee'], cle_marque(r['cible']), r['cle'], r['motif'])
                   for r in self.db_manager.lister_regles_nomenclature()}
        for ligne in lignes:
            erreurs = self.controler_regle(ligne)
            if erreurs:
                bilan.refusees.append((ligne, erreurs))
            elif (ligne['portee'], cle_marque(ligne['cible']), ligne['cle'],
                  valider_motif_regle(ligne['motif'])) in connues:
                bilan.deja_presentes += 1
            else:
                bilan.ajoutees += 1
        return bilan

    def regles(self) -> List[Regle]:
        """Règles en base, compilées (une ligne illisible est journalisée et ignorée)."""
        out = []
        for ligne in self.db_manager.lister_regles_nomenclature():
            try:
                out.append(Regle.depuis_ligne(ligne))
            except MotifRegleInvalide as e:
                app_logger.warning(f"Règle de nomenclature {ligne.get('id')} ignorée : {e}")
        return out

    # ── Propositions (§ 6.2, § 7) ───────────────────────────────────────────

    def calculer_propositions(self, ecrire: bool = False,
                              appareil_ids: Optional[Iterable[int]] = None) -> BilanPropositions:
        """Résoudre chaque appareil par les règles validées et préparer les
        propositions ; avec `ecrire`, remplacer `propositions_type` et les
        mesures des règles. Aucun type d'appareil n'est modifié.

        Args:
            appareil_ids: ne calculer que ces appareils (typage à l'import, lot 5) ;
                l'écriture ne remplace alors que leurs propositions, sans toucher
                aux autres ni aux mesures des règles.
        """
        bilan = BilanPropositions()
        if appareil_ids is not None:
            bilan.appareil_ids = tuple(dict.fromkeys(appareil_ids))
            if not bilan.appareil_ids:
                return bilan
        refus = self.db_manager.lire_refus_du_champ(CHAMP_REFUS)
        if refus is None:
            bilan.erreur = "refus illisibles : aucune proposition calculée"
            return bilan
        regles = self.regles()
        index = IndexRegles(regles, self.groupe_de)
        couverture: Counter = Counter()
        accord: Counter = Counter()
        candidates_cache: Dict[Tuple[str, str], '_ReglesIndexees'] = {}
        brutes = []   # (id, type actuel, other_ref, résolution)
        lecture = (self.db_manager.lire_appareils_nomenclature() if bilan.appareil_ids is None
                   else self.db_manager.lire_appareils_nomenclature(bilan.appareil_ids))
        for ident, type_app, marque, ref_modele, ref_com, libelle in lecture:
            bilan.appareils += 1
            type_app = (type_app or '').strip()
            if type_app and not est_type_autorise(type_app, self.types_autorises):
                bilan.types_hors_liste[type_app] += 1
            if type_app in TypesAppareils.ACCESSOIRES or not marque:
                continue
            valeurs = {'nom': cle_nom(ref_modele, ref_com), 'code': cle_code(ref_modele, ref_com)}
            # Mesures : toutes les règles (tous statuts) qui visent l'appareil
            for cle, valeur in valeurs.items():
                if not valeur or bilan.appareil_ids is not None:
                    continue
                cache = (cle_marque(marque), cle)
                if cache not in candidates_cache:
                    candidates_cache[cache] = _ReglesIndexees(
                        index.candidates(marque, cle, validees=False))
                for r in candidates_cache[cache].qui_s_appliquent(valeur):
                    couverture[r.id] += 1
                    accord[r.id] += r.type_resultat == type_app
            resolution = index.resoudre(marque, valeurs['nom'], valeurs['code'])
            if resolution.conflit:
                bilan.conflits.append((ident, resolution.regle_nom, resolution.regle_code))
                continue
            if not resolution.type:
                continue
            bilan.couverts += 1
            if resolution.type == type_app:
                continue
            if (ident, resolution.type.lower()) in refus:
                bilan.refusees += 1
                continue
            brutes.append((ident, type_app, libelle or '', resolution))
        if bilan.appareil_ids is None:
            bilan.mesures = {r.id: (couverture[r.id], accord[r.id]) for r in regles
                             if r.id is not None}

        votes = self.db_manager.types_par_piece_partagee([b[0] for b in brutes]) if brutes else {}
        horodatage = _maintenant()
        for ident, type_app, libelle, resolution in brutes:
            vote = part_du_vote(votes.get(ident), resolution.type)
            libelle_ok = libelle_d_accord(libelle, resolution.type)
            signaux = {
                'regle_nom': resolution.regle_nom.id if resolution.regle_nom else None,
                'regle_code': resolution.regle_code.id if resolution.regle_code else None,
                'deux_cles': resolution.deux_cles_d_accord,
                'vote_pieces': None if vote is None else round(vote, 3),
                'votants': sum((votes.get(ident) or {}).values()),
                'libelle': libelle_ok,
            }
            bilan.propositions[ident] = {
                'appareil_id': ident, 'type_actuel': type_app or None,
                'type_propose': resolution.type, 'regle_id': resolution.regle.id,
                'force': force_proposition(type_app, resolution.type,
                                           resolution.deux_cles_d_accord, vote, libelle_ok),
                'signaux': json.dumps(signaux, ensure_ascii=False), 'cree_le': horodatage}

        bilan.calcule_le = horodatage
        if ecrire:
            self.ecrire_propositions(bilan)
        app_logger.info(f"Règles de nomenclature : {len(bilan.propositions)} proposition(s), "
                        f"{len(bilan.conflits)} conflit(s), {bilan.couverts} appareil(s) couvert(s)")
        return bilan

    def ecrire_propositions(self, bilan: BilanPropositions) -> bool:
        """Ranger un calcul : remplace `propositions_type` et les mesures des règles.

        Le calcul a pu se faire en arrière-plan (lot 4) sur un instantané : une
        proposition dont l'appareil a changé de type depuis, ou qui a été refusée
        entre-temps, est écartée (elle serait périmée)."""
        from ..data._db_mixins.nomenclature import COLONNES_PROPOSITION
        propositions = list(bilan.propositions.values())
        if propositions:
            actuels = self.db_manager.lire_types_appareils(p['appareil_id'] for p in propositions)
            refus = self.db_manager.lire_refus_du_champ(CHAMP_REFUS) or set()
            propositions = [
                p for p in propositions
                if p['appareil_id'] in actuels
                and (actuels[p['appareil_id']] or '').strip() == (p['type_actuel'] or '')
                and (p['appareil_id'], p['type_propose'].lower()) not in refus]
            perimees = len(bilan.propositions) - len(propositions)
            if perimees:
                app_logger.info(f"Règles de nomenclature : {perimees} proposition(s) périmée(s) "
                                f"écartée(s) à l'écriture")
                bilan.propositions = {p['appareil_id']: p for p in propositions}
        lignes = (tuple(p[c] for c in COLONNES_PROPOSITION) for p in propositions)
        if bilan.appareil_ids is not None:
            # Calcul restreint (import) : seules ces propositions, mesures inchangées
            ecrites = self.db_manager.remplacer_propositions_des_appareils(
                bilan.appareil_ids, lignes)
            mesures_ok = True
        else:
            ecrites = self.db_manager.remplacer_propositions_type(lignes)
            mesures_ok = self.db_manager.enregistrer_mesures_regles(
                bilan.mesures, bilan.calcule_le or _maintenant())
        bilan.ecrit = ecrites >= 0 and mesures_ok
        if not bilan.ecrit:
            bilan.erreur = "écriture des propositions ou des mesures échouée (voir le journal)"
        return bilan.ecrit

    # ── Découverte (§ 6.3) ──────────────────────────────────────────────────

    def decouvrir_regles(self, ecrire: bool = False) -> BilanDecouverte:
        """Règles candidates ; avec `ecrire`, les nouvelles sont ajoutées en
        statut « proposée » (origine « découverte »)."""
        appareils = [(ident, marque or '', type_app, cle_nom(rm, rc), cle_code(rm, rc))
                     for ident, type_app, marque, rm, rc, _ in
                     self.db_manager.lire_appareils_nomenclature()]
        candidates, zones = decouvrir(appareils, self.groupe_de)
        bilan = BilanDecouverte(candidates=candidates, zones_grises=zones)
        regles = self.regles()
        connues = {(r.portee, cle_marque(r.cible), r.cle, r.motif) for r in regles}
        # Motifs déjà tranchés (règle validée ou rejetée) pour une marque ou son
        # groupe : la découverte n'y revient pas — elle reproposerait l'erreur
        # majoritaire qu'une règle validée corrige (Whirlpool AKR3* → Four, lot 4)
        tranches = {(r.portee, cle_marque(r.cible), r.cle, r.motif) for r in regles
                    if r.statut != STATUT_PROPOSEE}

        def deja_tranchee(c) -> bool:
            if (c.portee, cle_marque(c.cible), c.cle, c.motif) in tranches:
                return True
            groupe = self.groupe_de(c.cible) if c.portee != PORTEE_GROUPE else ''
            return bool(groupe) and (PORTEE_GROUPE, cle_marque(groupe), c.cle, c.motif) in tranches

        bilan.deja_tranchees = sum(1 for c in candidates if deja_tranchee(c))
        bilan.nouvelles = [c for c in candidates
                           if (c.portee, cle_marque(c.cible), c.cle, c.motif) not in connues
                           and not deja_tranchee(c)
                           and est_type_autorise(c.type_resultat, self.types_autorises)]
        if ecrire:
            self.enregistrer_decouvertes(bilan)
        return bilan

    def enregistrer_decouvertes(self, bilan: BilanDecouverte) -> int:
        """Ajouter les nouvelles candidates en statut « proposée » (origine
        « découverte ») ; une règle entrée en base entre-temps n'est pas écrasée."""
        if not bilan.nouvelles:
            return 0
        horodatage = _maintenant()
        enregistrement = self.enregistrer_regles(
            {'portee': c.portee, 'cible': c.cible, 'cle': c.cle, 'motif': c.motif,
             'type_resultat': c.type_resultat, 'statut': STATUT_PROPOSEE,
             'origine': 'decouverte', 'couverture': c.couverture, 'accord': c.accord,
             'note': f"{PREFIXE_NOTE_ZONE_GRISE}{c.zone_grise}*" if c.zone_grise else None,
             'calcule_le': horodatage} for c in bilan.nouvelles)
        bilan.ajoutees = enregistrement.ajoutees
        return bilan.ajoutees

    # ── Écran Règles (lot 4, § 8.1) ─────────────────────────────────────────

    def changer_statut(self, regle_id: int, statut: str) -> bool:
        """Valider, rejeter ou remettre en « proposée » une règle. Les
        propositions ne changent qu'au prochain calcul (l'écran le relance)."""
        if statut not in STATUTS:
            raise ValueError(f"statut « {statut} » inconnu")
        ok = self.db_manager.changer_statut_regle(regle_id, statut, _maintenant())
        if ok:
            app_logger.info(f"Règle de nomenclature {regle_id} : statut « {statut} »")
        return ok

    def enregistrer_note(self, regle_id: int, note: str, zone_grise: str = '') -> bool:
        """Note libre ; la mention « sous la zone grise X* » posée par la
        découverte est gardée en tête (l'écran s'en sert pour l'alerte)."""
        note = (note or '').strip()
        if zone_grise and not note.startswith(PREFIXE_NOTE_ZONE_GRISE):
            note = f"{PREFIXE_NOTE_ZONE_GRISE}{zone_grise} — {note}" if note \
                else f"{PREFIXE_NOTE_ZONE_GRISE}{zone_grise}"
        return self.db_manager.enregistrer_note_regle(regle_id, note)

    def exemples(self, regle: dict, limite: int = 60) -> 'ExemplesRegle':
        """Appareils couverts par une règle (tous statuts), désaccords en tête.

        Lecture limitée aux marques visées (la marque, ou celles du groupe qui
        n'ont pas leur propre règle sur ce motif) : pas de relecture de la base."""
        exemples = ExemplesRegle()
        try:
            compilee = Regle.depuis_ligne(regle)
        except MotifRegleInvalide as e:
            exemples.erreur = str(e)
            return exemples
        index = IndexRegles(self.regles(), self.groupe_de)
        cible = cle_marque(compilee.cible)
        if compilee.portee == PORTEE_GROUPE:
            marques = [m for m in self.db_manager.lister_marques_appareils()
                       if cle_marque(self.groupe_de(m)) == cible]
        else:
            marques = [m for m in self.db_manager.lister_marques_appareils()
                       if cle_marque(m) == cible]
        accords, desaccords = [], []
        masquees = set()
        for ident, type_app, marque, ref_modele, ref_com, libelle in \
                self.db_manager.lire_appareils_des_marques(marques):
            if (type_app or '') in TypesAppareils.ACCESSOIRES:
                continue
            valeur = (cle_nom(ref_modele, ref_com) if compilee.cle == 'nom'
                      else cle_code(ref_modele, ref_com))
            if not compilee.s_applique(valeur):
                continue
            if compilee.portee == PORTEE_GROUPE and not any(
                    r is compilee or r.id == compilee.id
                    for r in index.candidates(marque, compilee.cle, validees=False)):
                masquees.add(marque or '')
                continue
            ligne = (ident, marque or '', ref_modele or '', ref_com or '', type_app or '',
                     libelle or '')
            (accords if (type_app or '') == compilee.type_resultat else desaccords).append(ligne)
        exemples.couverture = len(accords) + len(desaccords)
        exemples.accord = len(accords)
        exemples.desaccords = desaccords[:limite]
        exemples.accords = accords[:max(0, limite - len(exemples.desaccords))]
        exemples.masquees = sorted(masquees)
        return exemples
