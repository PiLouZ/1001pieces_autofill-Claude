"""
Décisions de l'aperçu et plan d'écriture d'une fiche (CDC § 7.1, § 9, étape 3)

Pur Python, sans Qt ni base : l'aperçu remplit un `DecisionsFiche`,
`planifier()` en tire un `PlanEnregistrement` que le service écrit.

- Chaque appareil, remplacement, équivalence et doute d'identité appartient à
  UNE catégorie du résumé (`CATEGORIES_RESUME`). Une catégorie est *validée en
  bloc* (les propositions s'appliquent aux éléments sans choix individuel),
  *laissée de côté* (rien n'est écrit, tout revient à la relecture) ou *en
  attente*. Tant qu'une catégorie est en attente, rien ne s'enregistre.
- Un choix individuel l'emporte toujours sur l'état de sa catégorie.
- Un élément validé sans proposition possible (appareil à choisir parmi
  plusieurs, création sans marque ou sans type) est *à compléter* : il bloque
  l'enregistrement jusqu'à un choix ou sa mise de côté.
- Ajout seul (§ 6.2) : le plan ne contient aucune suppression ; les liens de
  provenance site absents de la fiche sont repris pour information.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from src.utils.lecteur_fiche.lecteur import cle_marque
from src.utils.rapprochement_fiche.resultat import (
    AppareilRapproche, Equivalence, Rapprochement, Remplacement,
)

VALIDEE, DE_COTE, ATTENTE = 'validee', 'de_cote', 'attente'

CATEGORIES_RESUME = {
    'exacts': "Exacts (identiques en base)",
    'normalises': "Normalisés (à la ponctuation près)",
    'deja_couverts': "Déjà couverts par la lignée",
    'a_valider': "À valider (choix d'appareil ou de marque)",
    'absents': "Absents (appareils à créer)",
    'types_manquants': "Types manquants (appareils à créer)",
    'relations': "Remplacements et équivalences",
    'conflits': "Conflits et doutes sur la pièce",
}
# Doutes d'appareil qui demandent un choix (catégorie « à valider »)
_DOUTES_CHOIX = {'normalise_ambigu', 'exact_multiple', 'a_valider', 'marque_a_choisir',
                 'type_ambigu'}
# Doutes d'identité : un choix par doute, proposition entre parenthèses
CHOIX_IDENTITE = {
    'ean_different': ('site', 'outil'),
    'libelle_different': ('garder', 'prendre'),
    'ref_interne_autre_piece': ('prendre', 'garder'),
}
_FORME_CHIFFRES = re.compile(r'\d')
_FORME_LETTRES = re.compile(r'[A-Za-z]')


def forme_reference(ref: str) -> str:
    """Forme d'une référence pour l'apprentissage des formats (§ 5.5) :
    chiffres → 9, lettres → A, le reste tel quel (`C00319033` → `A99999999`)."""
    return _FORME_LETTRES.sub('A', _FORME_CHIFFRES.sub('9', ref or ''))


# =============================================================================
# Catégories
# =============================================================================

def categorie_appareil(a: AppareilRapproche) -> str:
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


def categorie_remplacement(r: Remplacement) -> str:
    if r.statut in ('conflit', 'cycle') or r.appariement == 'a_choisir':
        return 'conflits'
    return 'relations'


def categorie_equivalence(e: Equivalence) -> str:
    return 'relations' if e.origine or e.statut == 'ecartee' else 'conflits'


def elements_par_categorie(r: Rapprochement) -> Dict[str, Dict[str, list]]:
    """catégorie → {'appareils': [index], 'remplacements': [...], 'equivalences': [...],
    'identite': [catégorie de doute]} (catégories non vides seulement)."""
    out: Dict[str, Dict[str, list]] = {}

    def ranger(cat, nature, valeur):
        out.setdefault(cat, {}).setdefault(nature, []).append(valeur)

    for i, a in enumerate(r.appareils):
        ranger(categorie_appareil(a), 'appareils', i)
    for rp in r.remplacements:
        if rp.statut not in ('deja_present', 'confirme_par_chaine', 'identique'):
            ranger(categorie_remplacement(rp), 'remplacements', rp.ancienne)
    for e in r.equivalences:
        if e.statut not in ('deja_dans_le_groupe', 'dans_la_succession', 'ecartee'):
            ranger(categorie_equivalence(e), 'equivalences', e.reference)
    for categorie in r.doutes_par_categorie():
        if categorie in CHOIX_IDENTITE:
            ranger('conflits', 'identite', categorie)
    return {c: out[c] for c in CATEGORIES_RESUME if c in out}


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
    etats: Dict[str, str] = field(default_factory=dict)             # catégorie → état
    appareils: Dict[int, ChoixAppareil] = field(default_factory=dict)
    type_par_categorie: Dict[str, str] = field(default_factory=dict)  # type commun d'une catégorie
    remplacements: Dict[str, str] = field(default_factory=dict)     # ancienne → 'garder'/'prendre'/cible
    origines: Dict[str, str] = field(default_factory=dict)          # réf. → étiquette saisie
    ecartees: Set[str] = field(default_factory=set)                 # réf. écartées
    identite: Dict[str, str] = field(default_factory=dict)          # doute d'identité → choix

    def etat(self, categorie: str) -> str:
        return self.etats.get(categorie, ATTENTE)

    def choix(self, index: int) -> ChoixAppareil:
        return self.appareils.setdefault(index, ChoixAppareil())

    def valider_tout(self, r: Rapprochement):
        for c in elements_par_categorie(r):
            self.etats[c] = VALIDEE


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
    produit: Optional[Dict[str, object]] = None
    decisions_ecritures: List[Tuple[str, str, str, str]] = field(default_factory=list)
    decisions_references: List[Tuple[str, str, str, Optional[str], str]] = field(default_factory=list)
    informations: List[str] = field(default_factory=list)
    a_completer: List[str] = field(default_factory=list)
    en_attente: List[str] = field(default_factory=list)              # catégories en attente

    @property
    def pret(self) -> bool:
        return bool(self.ref_piece) and not self.a_completer and not self.en_attente

    @property
    def vide(self) -> bool:
        """Rien de nouveau à écrire (relecture d'une fiche déjà reprise)."""
        return not (self.appareils_a_creer or self.remplacements or self.equivalences
                    or self.decisions_ecritures or self.decisions_references
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
    """Plan d'écriture d'une fiche d'après les décisions de l'aperçu."""
    return _Planificateur(r, d).executer()


class _Planificateur:

    def __init__(self, r: Rapprochement, d: DecisionsFiche):
        self.r, self.d = r, d
        self.cats = elements_par_categorie(r)
        ident = r.identite
        self.plan = PlanEnregistrement(ref_piece=ident.ref_piece or '', statut_piece=ident.statut)
        self.le = datetime.now().isoformat(timespec='seconds')

    def _etat(self, categorie: str) -> str:
        return self.d.etat(categorie)

    def executer(self) -> PlanEnregistrement:
        p = self.plan
        if not p.ref_piece:
            p.a_completer.append("pièce introuvable : ni code produit ni référence interne")
            return p
        p.en_attente = [CATEGORIES_RESUME[c] for c in self.cats if self._etat(c) == ATTENTE]
        self._identite()
        for i, a in enumerate(self.r.appareils):
            self._appareil(i, a)
        for rp in self.r.remplacements:
            self._remplacement(rp)
        for e in self.r.equivalences:
            self._equivalence(e)
        for app in self.r.absents_de_la_fiche:
            p.informations.append(
                f"{app.marque} {app.ref_modele} : lié dans l'outil, absent de la fiche")
        return p

    # --- Identité, libellé, produit du site (§ 5.1, 5.8) ------------------------
    def _choix_identite(self, doute: str) -> Optional[str]:
        """Choix sur un doute d'identité : individuel, sinon proposition si validé."""
        if doute in self.d.identite:
            return self.d.identite[doute]
        return CHOIX_IDENTITE[doute][0] if self._etat('conflits') == VALIDEE else None

    def _identite(self):
        i, p = self.r.identite, self.plan
        doutes = self.r.doutes_par_categorie()
        if i.libelle:
            if i.statut_libelle == 'a_remplir' or i.statut == 'absente':
                p.libelle = i.libelle
            elif 'libelle_different' in doutes and self._choix_identite('libelle_different') == 'prendre':
                p.libelle, p.remplacer_libelle = i.libelle, True
        if not i.ref_interne:
            return
        if 'ref_interne_autre_piece' in doutes and \
                self._choix_identite('ref_interne_autre_piece') != 'prendre':
            return                      # produit laissé à sa pièce actuelle
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
        categorie = categorie_appareil(a)
        choix = self.d.appareils.get(index)
        etat = self._etat(categorie)
        if choix is not None and choix.ignorer:
            return
        individuel = choix is not None and (choix.appareil_id is not None or choix.creer
                                            or choix.rattacher)
        if not individuel and etat != VALIDEE:
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
            self._creer(index, a, choix, categorie, cle)
            return
        if a.lien == 'deja_couvert' and not (choix is not None and choix.rattacher):
            return                      # pas de nouveau lien (§ 5.2)
        ident = a.appareil_id if a.appareil_id is not None else a.proposition
        if ident is None and len(a.candidats) == 1:
            ident = a.candidats[0].id
        if ident is None:
            p.a_completer.append(f"ligne {a.numero or 'table'} {a.marque or '?'} {a.ref_modele} : "
                                 f"appareil à choisir parmi {len(a.candidats)}")
            return
        p.liens.append((ident, a.provenance))

    def _creer(self, index, a, choix, categorie, cle):
        p = self.plan
        marque = (choix.marque if choix and choix.marque else '') or a.marque
        type_ = ((choix.type if choix and choix.type else '')
                 or self.d.type_par_categorie.get(categorie, '') or a.type)
        manque = [n for n, v in (('marque', marque), ('type', type_)) if not v]
        if manque:
            p.a_completer.append(f"ligne {a.numero or 'table'} {a.ref_modele} : "
                                 f"{' et '.join(manque)} à choisir pour la création")
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
        if rp.statut in ('deja_present', 'confirme_par_chaine', 'identique', 'cycle'):
            return
        choix = self.d.remplacements.get(rp.ancienne)
        etat = self._etat(categorie_remplacement(rp))
        if choix is None and etat != VALIDEE:
            return
        nouvelle = rp.nouvelle
        if rp.statut == 'conflit':
            if (choix or 'garder') == 'garder':
                return
        elif choix not in (None, 'garder', 'prendre'):
            nouvelle = choix            # appariement : autre réf. du code produit
        self.plan.remplacements.append((rp.ancienne, nouvelle))

    def _equivalence(self, e: Equivalence):
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
                p.origines.append((e.reference, origine or None, e.ligne or None))
            return
        if e.reference not in self.d.origines and self._etat(categorie_equivalence(e)) != VALIDEE:
            return
        p.equivalences.append(e.reference)
        p.origines.append((e.reference, origine or None, e.ligne or None))
        if e.reference in self.d.origines and self.d.origines[e.reference]:
            p.decisions_references.append(
                (p.ref_piece, e.reference, 'origine', self.d.origines[e.reference],
                 forme_reference(e.reference)))
