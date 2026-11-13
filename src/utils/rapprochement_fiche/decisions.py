"""
Plan d'écriture d'une fiche (CDC § 7.1, § 9, § 10.20)

Pur Python, sans Qt ni base : des choix ligne par ligne (`DecisionsFiche`, posés
par les règles de l'import, `regles_import.py`), `planifier()` en tire un
`PlanEnregistrement` que l'import écrit.

- Sans choix, chaque élément suit sa proposition : appareil reconnu relié,
  absent créé, remplacement et équivalente écrits, doute d'identité tranché par
  sa proposition (`CHOIX_IDENTITE`).
- Un choix ligne par ligne l'emporte : appareil choisi, création, ligne ignorée,
  rattachement direct d'une ligne déjà couverte.
- Un élément sans proposition possible (appareil à choisir parmi plusieurs,
  création sans marque ou sans type, référence illisible) est *à compléter* :
  les règles de l'import ne l'importent pas.
- Ajout seul (§ 6.2) : le plan ne contient aucune suppression ; les liens de
  provenance site absents de la fiche sont repris pour information.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from src.utils.lecteur_fiche.lecteur import cle_marque
from src.utils.rapprochement_fiche.acces_base import forme_normalisee
from src.utils.rapprochement_fiche.resultat import (
    CHAMPS_ECARTS, AppareilRapproche, Equivalence, Rapprochement, Remplacement,
)

# Doutes d'appareil qui demandent un choix (catégorie « à valider »)
_DOUTES_CHOIX = {'normalise_ambigu', 'exact_multiple', 'a_valider', 'marque_a_choisir',
                 'type_ambigu'}
# Doutes d'identité : un choix par doute, proposition entre parenthèses
CHOIX_IDENTITE = {
    'ean_different': ('site', 'outil'),
    'libelle_different': ('garder', 'prendre'),
    'ref_interne_autre_piece': ('prendre', 'garder'),
    # Réf. interne sans rapport avec le code produit (codes fournisseur…) : le
    # produit est enregistré avec elle, ou pas du tout (étape 4, traité en bloc)
    'ref_interne_differente': ('enregistrer', 'ignorer'),
}
_FORME_CHIFFRES = re.compile(r'\d')
_FORME_LETTRES = re.compile(r'[A-Za-z]')


def forme_reference(ref: str) -> str:
    """Forme d'une référence pour l'apprentissage des formats (§ 5.5) :
    chiffres → 9, lettres → A, le reste tel quel (`C00319033` → `A99999999`)."""
    return _FORME_LETTRES.sub('A', _FORME_CHIFFRES.sub('9', ref or ''))


# =============================================================================
# Ce que demande une ligne d'appareil
# =============================================================================

def categorie_appareil(a: AppareilRapproche) -> str:
    """Ce que la ligne demande : 'a_valider' (choix d'appareil ou de marque),
    'absents' / 'types_manquants' (création), 'deja_couverts', 'normalises',
    'exacts'. Les règles de l'import tranchent les lignes « à valider »."""
    if set(a.doutes) & _DOUTES_CHOIX:
        return 'a_valider'
    if a.niveau == 'absent':
        return 'types_manquants' if not a.type else 'absents'
    if a.lien == 'deja_couvert':
        return 'deja_couverts'
    if a.niveau == 'normalise':
        return 'normalises'
    if a.appareil_id is None and a.proposition is None:
        return 'a_valider'
    return 'exacts'


# =============================================================================
# Décisions
# =============================================================================

@dataclass
class ChoixAppareil:
    """Choix individuel sur une ligne d'appareil."""
    appareil_id: Optional[int] = None   # appareil choisi parmi les candidats
    creer: bool = False                 # créer l'appareil (marque et type ci-dessous)
    ignorer: bool = False               # laisser la ligne de côté
    rattacher: bool = False             # déjà couvert : rattachement direct demandé
    marque: str = ''
    type: str = ''


@dataclass
class DecisionsFiche:
    """Choix ligne par ligne ; sans choix, chaque élément suit sa proposition."""
    appareils: Dict[int, ChoixAppareil] = field(default_factory=dict)
    remplacements: Dict[str, str] = field(default_factory=dict)     # ancienne → 'garder'/'prendre'/cible/'ignorer'
    origines: Dict[str, str] = field(default_factory=dict)          # réf. → étiquette saisie
    ecartees: Set[str] = field(default_factory=set)                 # réf. écartées
    identite: Dict[str, str] = field(default_factory=dict)          # doute d'identité → choix
    # Règle de l'import (§ 10.12) : un appareil à créer sans type est créé quand
    # même ; l'auto-complétion puis « Suggestions à valider » s'en chargent
    creer_incomplets: bool = False

    def choix(self, index: int) -> ChoixAppareil:
        return self.appareils.setdefault(index, ChoixAppareil())


# =============================================================================
# Plan d'écriture
# =============================================================================

@dataclass
class AppareilACreer:
    index: int                          # ligne du rapprochement
    marque: str
    ref_modele: str
    nom: str
    type: str


@dataclass
class PlanEnregistrement:
    ref_piece: str
    statut_piece: str                   # 'absente', 'fantome', 'reelle'
    libelle: str = ''                   # à poser si la pièce n'en a pas, ou à remplacer
    remplacer_libelle: bool = False
    appareils_a_creer: List[AppareilACreer] = field(default_factory=list)
    # (appareil_id, provenance) ; appareil à créer : ('creer', index)
    liens: List[Tuple[object, str]] = field(default_factory=list)
    remplacements: List[Tuple[str, str]] = field(default_factory=list)
    equivalences: List[str] = field(default_factory=list)           # à relier à la pièce
    origines: List[Tuple[str, Optional[str], Optional[int]]] = field(default_factory=list)
    # (ancienne référence, position dans « Remplace » de la fiche) : complétée à
    # chaque lecture, comme les origines ; ne compte pas dans `vide`
    rangs_remplace: List[Tuple[str, int]] = field(default_factory=list)
    produit: Optional[Dict[str, object]] = None
    # Nom commercial vide d'un appareil connu, complété depuis la fiche :
    # id → {colonne d'appareils: valeur} (sauvegarde événementielle, thread principal)
    maj_appareils: Dict[int, Dict[str, str]] = field(default_factory=dict)
    decisions_ecritures: List[Tuple[str, str, str, str]] = field(default_factory=list)
    decisions_references: List[Tuple[str, str, str, Optional[str], str]] = field(default_factory=list)
    informations: List[str] = field(default_factory=list)
    a_completer: List[str] = field(default_factory=list)
    lignes_a_completer: List[int] = field(default_factory=list)      # index des appareils à compléter
    # Règles de l'import (§ 10.12) : lignes que l'import ne peut pas trancher, non
    # importées et comptées dans l'historique (appareil parmi plusieurs, réf. illisible)
    non_importees: List[str] = field(default_factory=list)
    # Créations retenues pour données bancales : fiche à refaire depuis les PDF (§ 10.14)
    a_refaire: Optional[object] = None          # regles_import.ARefaire

    @property
    def pret(self) -> bool:
        return bool(self.ref_piece) and not self.a_completer

    @property
    def vide(self) -> bool:
        """Rien de nouveau à écrire (relecture d'une fiche déjà reprise)."""
        return not (self.appareils_a_creer or self.remplacements or self.equivalences
                    or self.decisions_ecritures or self.decisions_references
                    or self.maj_appareils
                    or self.statut_piece != 'reelle' or self.libelle)

    def resume(self) -> Dict[str, int]:
        return {
            'appareils_a_creer': len(self.appareils_a_creer),
            'liens': len(self.liens),
            'remplacements': len(self.remplacements),
            'equivalences': len(self.equivalences),
            'decisions': len(self.decisions_ecritures) + len(self.decisions_references),
        }


def planifier(r: Rapprochement, d: DecisionsFiche) -> PlanEnregistrement:
    """Plan d'écriture d'une fiche d'après ses choix ligne par ligne."""
    return _Planificateur(r, d).executer()


class _Planificateur:

    def __init__(self, r: Rapprochement, d: DecisionsFiche):
        self.r, self.d = r, d
        ident = r.identite
        self.plan = PlanEnregistrement(ref_piece=ident.ref_piece or '', statut_piece=ident.statut)
        self.le = datetime.now().isoformat(timespec='seconds')

    def executer(self) -> PlanEnregistrement:
        p = self.plan
        if not p.ref_piece:
            p.a_completer.append("pièce introuvable : ni code produit ni référence interne")
            return p
        self._identite()
        self._differees: List[Tuple[int, AppareilRapproche]] = []
        self._couverts: List[AppareilRapproche] = []
        for i, a in enumerate(self.r.appareils):
            self._appareil(i, a)
        self._resoudre_par_la_fiche()
        self._ecarts()
        for rp in self.r.remplacements:
            self._remplacement(rp)
        for e in self.r.equivalences:
            self._equivalence(e)
        for app in self.r.absents_de_la_fiche:
            p.informations.append(
                f"{app.marque} {app.ref_modele} : lié dans l'outil, absent de la fiche")
        return p

    # --- Identité, libellé, produit du site (§ 5.1, 5.8) ------------------------
    def _choix_identite(self, doute: str) -> str:
        """Choix sur un doute d'identité : posé, sinon la proposition."""
        return self.d.identite.get(doute) or CHOIX_IDENTITE[doute][0]

    def _identite(self):
        i, p = self.r.identite, self.plan
        doutes = self.r.doutes_par_categorie()
        if i.libelle:
            if i.statut_libelle == 'a_remplir' or i.statut == 'absente':
                p.libelle = i.libelle
            elif i.statut_libelle == 'ancienne_regle':
                p.libelle, p.remplacer_libelle = i.libelle, True
            elif 'libelle_different' in doutes and self._choix_identite('libelle_different') == 'prendre':
                p.libelle, p.remplacer_libelle = i.libelle, True
        if not i.ref_interne:
            return
        if 'ref_interne_autre_piece' in doutes and \
                self._choix_identite('ref_interne_autre_piece') != 'prendre':
            return                      # produit laissé à sa pièce actuelle
        if 'ref_interne_differente' in doutes and \
                self._choix_identite('ref_interne_differente') != 'enregistrer':
            return                      # produit non enregistré (réf. interne écartée)
        ean = i.ean if i.statut_ean == 'valide' else None
        if 'ean_different' in doutes and self._choix_identite('ean_different') != 'site':
            ean = None                  # on garde l'EAN de l'outil (COALESCE)
        p.produit = {'ref_interne': i.ref_interne, 'id_product': i.id_product,
                     'ref_piece': i.ref_piece, 'ean': ean, 'lu_le': self.le,
                     'ref_interne_precedente': i.ref_interne_precedente}
        if i.ref_interne_precedente:
            p.informations.append(f"référence interne changée sur le site : "
                                  f"{i.ref_interne_precedente} → {i.ref_interne}")

    # --- Appareils (§ 5.2, 5.6, 5.7) --------------------------------------------
    def _appareil(self, index: int, a: AppareilRapproche):
        choix = self.d.appareils.get(index)
        if choix is not None and choix.ignorer:
            return
        p = self.plan
        cle = cle_marque(a.marque or a.marque_fiche)
        if choix is not None and choix.appareil_id is not None:
            p.liens.append((choix.appareil_id, a.provenance))
            choisi = next((c for c in a.candidats if c.id == choix.appareil_id), None)
            if choisi is not None and choisi.ref_modele != a.ref_modele and cle:
                p.decisions_ecritures.append((cle, a.ref_modele, choisi.ref_modele, 'meme'))
            return
        if (choix is not None and choix.creer) or a.niveau == 'absent':
            self._creer(index, a, choix, cle)
            return
        if a.lien == 'deja_couvert' and not (choix is not None and choix.rattacher):
            self._couverts.append(a)
            return                      # pas de nouveau lien (§ 5.2)
        ident = a.appareil_id if a.appareil_id is not None else a.proposition
        # Candidat unique : relié en bloc seulement s'il a la même réf. (à la
        # ponctuation près) ; trouvé par le seul nom commercial, c'est un autre appareil
        if ident is None and len(a.candidats) == 1 and \
                forme_normalisee(a.candidats[0].ref_modele) == forme_normalisee(a.ref_modele):
            ident = a.candidats[0].id
        if ident is None:
            self._differees.append((index, a))
            return
        p.liens.append((ident, a.provenance))

    def _ecarts(self):
        """Appareil connu au nom commercial vide : complété depuis la fiche (règle de
        l'import : un champ vide est complété, une valeur de l'outil jamais écrasée).
        Seulement pour une ligne qui désigne bien cet appareil (reliée ou couverte)."""
        p = self.plan
        lies = {c for c, _ in p.liens if not isinstance(c, tuple)}
        lies |= {a.appareil_id for a in self._couverts if a.appareil_id is not None}
        vus = set()
        for i, a in enumerate(self.r.appareils):
            choix = self.d.appareils.get(i)
            if choix is not None and (choix.ignorer or choix.creer):
                continue
            for e in a.ecarts:
                if e.tranche or e.appareil_id not in lies or (e.appareil_id, e.champ) in vus:
                    continue
                if choix is not None and choix.appareil_id is not None \
                        and choix.appareil_id != e.appareil_id:
                    continue
                if e.a_completer:
                    vus.add((e.appareil_id, e.champ))
                    colonne = CHAMPS_ECARTS[e.champ][1]
                    p.maj_appareils.setdefault(e.appareil_id, {})[colonne] = e.site

    def _resoudre_par_la_fiche(self):
        """Appareil à choisir parmi plusieurs : si un seul candidat est lié par une
        AUTRE ligne de la fiche (souvent la table du site, sous la bonne marque), c'est
        lui — comme un candidat déjà lié à la pièce (rapprocher, memoires=True). Sans
        cela, seule une relecture le trouverait. Sinon la ligne est à compléter."""
        p = self.plan
        lies = {c for c, _ in p.liens if not isinstance(c, tuple)}
        for index, a in self._differees:
            communs = {c.id for c in a.candidats if forme_normalisee(c.ref_modele)
                       == forme_normalisee(a.ref_modele)} & lies
            if len(communs) == 1:
                p.liens.append((communs.pop(), a.provenance))
                continue
            p.a_completer.append(f"ligne {a.numero or 'table'} {a.marque or '?'} {a.ref_modele} : "
                                 f"appareil à choisir parmi {len(a.candidats)}")
            p.lignes_a_completer.append(index)
        # Ligne « déjà couverte » dont l'appareil est lié quand même par une autre
        # ligne : le lien existera, il porte aussi sa provenance
        lies = {c for c, _ in p.liens if not isinstance(c, tuple)}
        for a in self._couverts:
            if a.appareil_id in lies:
                p.liens.append((a.appareil_id, a.provenance))

    def _creer(self, index, a, choix, cle):
        p = self.plan
        marque = (choix.marque if choix and choix.marque else '') or a.marque
        # Type trouvé (table, ligne, base, catégorie du produit : § 5.6), sinon choisi
        type_ = (choix.type if choix and choix.type else '') or a.type
        if a.suspecte and not (choix is not None and choix.creer):
            p.a_completer.append(f"ligne {a.numero or 'table'} « {a.ref_modele} » : "
                                 f"référence illisible ({a.suspecte}), non créée")
            p.lignes_a_completer.append(index)
            return
        manque = [n for n, v in (('marque', marque), ('type', type_)) if not v]
        if manque and not self.d.creer_incomplets:
            p.a_completer.append(f"ligne {a.numero or 'table'} {a.ref_modele} : "
                                 f"{' et '.join(manque)} à choisir pour la création")
            p.lignes_a_completer.append(index)
            return
        p.appareils_a_creer.append(AppareilACreer(index, marque, a.ref_modele, a.nom, type_))
        p.liens.append((('creer', index), a.provenance))
        # « Créer » malgré des écritures proches : appareils distincts, mémorisé
        cle = cle_marque(marque) or cle
        for c in a.candidats:
            if c.ref_modele != a.ref_modele and cle_marque(c.marque) == cle:
                p.decisions_ecritures.append((cle, a.ref_modele, c.ref_modele, 'distinct'))

    # --- Relations (§ 5.3, 5.4) --------------------------------------------------
    def _remplacement(self, rp: Remplacement):
        if rp.statut in ('deja_present', 'confirme_par_chaine'):
            self._rang(rp)
            return
        if rp.statut in ('identique', 'cycle'):
            return
        choix = self.d.remplacements.get(rp.ancienne)
        if choix == 'ignorer':
            return
        nouvelle = rp.nouvelle
        if rp.statut == 'conflit':
            if (choix or 'garder') == 'garder':
                return
        elif choix not in (None, 'garder', 'prendre'):
            nouvelle = choix            # appariement : autre réf. du code produit
        self.plan.remplacements.append((rp.ancienne, nouvelle))
        self._rang(rp)

    def _rang(self, rp: Remplacement):
        if rp.rang is not None and rp.sens == 'remplace':
            self.plan.rangs_remplace.append((rp.ancienne, rp.rang))

    def _equivalence(self, e: Equivalence):
        # n° de ligne gardé tel quel : 0 = 2ᵉ réf. du code produit, que la Fiche
        # complète réécrit dans le code produit (paire, § 8.1)
        p = self.plan
        origine = self.d.origines.get(e.reference, e.origine)
        if e.reference in self.d.ecartees:
            p.decisions_references.append(
                (p.ref_piece, e.reference, 'ecartee', None, forme_reference(e.reference)))
            return
        if e.statut == 'ecartee':
            return
        if e.statut in ('deja_dans_le_groupe', 'dans_la_succession'):
            if e.statut == 'deja_dans_le_groupe':
                p.origines.append((e.reference, origine or None, e.ligne))
            return
        if e.reference not in self.d.origines and not _FORME_CHIFFRES.search(e.reference):
            return                      # « Brandt », « : » : jamais écrite en bloc
        p.equivalences.append(e.reference)
        p.origines.append((e.reference, origine or None, e.ligne))
        if e.reference in self.d.origines and self.d.origines[e.reference]:
            p.decisions_references.append(
                (p.ref_piece, e.reference, 'origine', self.d.origines[e.reference],
                 forme_reference(e.reference)))
