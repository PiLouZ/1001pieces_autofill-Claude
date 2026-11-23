"""
Règles de nomenclature compilées et résolution d'un appareil (CDC § 6.2).

Résolution, pour un appareil :
1. règles **validées** seulement (les proposées servent à la revue) ;
2. portée **marque** avant **groupe** ; une règle de groupe ne s'applique pas à
   une marque qui a sa propre règle sur le même motif, quel qu'en soit le
   statut (une règle de marque rejetée retire la marque de la règle de groupe) ;
3. la plus spécifique gagne : gabarit > position > préfixe, puis le motif le
   plus long (« GK* » l'emporte sur « G* » : une exception s'écrit par une
   règle plus précise, jamais par une exclusion) ;
4. si les deux clés (`nom`, `code`) donnent un type, ils doivent concorder ;
   sinon : conflit (« à vérifier »), aucun type proposé.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from ..filtre_colonne import (RANG_FORME, forme_motif_regle, longueur_motif_regle,
                              motif_regle_vers_regex, valider_motif_regle)
from ..lecteur_fiche.lecteur import cle_marque
from .cles import CLE_CODE, CLE_NOM

PORTEE_MARQUE = 'marque'
PORTEE_GROUPE = 'groupe'
PORTEES = (PORTEE_MARQUE, PORTEE_GROUPE)

STATUT_PROPOSEE = 'proposee'
STATUT_VALIDEE = 'validee'
STATUT_REJETEE = 'rejetee'
STATUTS = (STATUT_PROPOSEE, STATUT_VALIDEE, STATUT_REJETEE)

ORIGINES = ('decouverte', 'web', 'saisie')


@dataclass(eq=False)
class Regle:
    """Une règle « motif de clé → type », compilée."""
    portee: str
    cible: str
    cle: str
    motif: str
    type_resultat: str
    statut: str = STATUT_PROPOSEE
    origine: str = 'saisie'
    source_url: str = ''
    note: str = ''
    id: Optional[int] = None
    forme: str = field(init=False)
    longueur: int = field(init=False)
    _regex: object = field(init=False, repr=False)

    def __post_init__(self):
        self.motif = valider_motif_regle(self.motif)   # MotifRegleInvalide si hors syntaxe
        self.forme = forme_motif_regle(self.motif)
        self.longueur = longueur_motif_regle(self.motif)
        self._regex = motif_regle_vers_regex(self.motif)

    @classmethod
    def depuis_ligne(cls, ligne: dict) -> 'Regle':
        """Règle depuis une ligne de `regles_nomenclature` (ou du catalogue)."""
        return cls(portee=ligne['portee'], cible=ligne['cible'], cle=ligne['cle'],
                   motif=ligne['motif'], type_resultat=ligne['type_resultat'],
                   statut=ligne.get('statut') or STATUT_PROPOSEE,
                   origine=ligne.get('origine') or 'saisie',
                   source_url=ligne.get('source_url') or '', note=ligne.get('note') or '',
                   id=ligne.get('id'))

    @property
    def specificite(self) -> Tuple[int, int]:
        return RANG_FORME[self.forme], self.longueur

    @property
    def validee(self) -> bool:
        return self.statut == STATUT_VALIDEE

    def s_applique(self, valeur: str) -> bool:
        """La clé (déjà normalisée) répond-elle au motif ?"""
        return bool(valeur) and self._regex.fullmatch(valeur) is not None

    def __repr__(self):
        return f"Regle({self.portee}:{self.cible} {self.cle} {self.motif} → {self.type_resultat}, {self.statut})"


@dataclass(frozen=True)
class Resolution:
    """Résultat de la résolution d'un appareil."""
    type: str = ''                       # '' = aucun type (pas de règle, ou conflit)
    regle_nom: Optional[Regle] = None
    regle_code: Optional[Regle] = None
    conflit: bool = False                # les deux clés se contredisent

    @property
    def regle(self) -> Optional[Regle]:
        """Règle qui porte le type (celle du nom commercial d'abord)."""
        return self.regle_nom or self.regle_code

    @property
    def deux_cles_d_accord(self) -> bool:
        return bool(self.regle_nom and self.regle_code and not self.conflit)


class IndexRegles:
    """Règles rangées par (portée, cible, clé), les plus spécifiques d'abord."""

    def __init__(self, regles: Iterable[Regle], groupe_de: Callable[[str], str]):
        self._groupe_de = groupe_de
        self._toutes: Dict[Tuple[str, str, str], List[Regle]] = {}
        self._motifs_marque: Dict[Tuple[str, str], Set[str]] = {}
        for r in regles:
            cible = cle_marque(r.cible)
            self._toutes.setdefault((r.portee, cible, r.cle), []).append(r)
            if r.portee == PORTEE_MARQUE:
                self._motifs_marque.setdefault((cible, r.cle), set()).add(r.motif)
        for liste in self._toutes.values():
            liste.sort(key=lambda r: (r.specificite, r.motif), reverse=True)
        self._validees = {k: [r for r in v if r.validee] for k, v in self._toutes.items()}

    def candidates(self, marque: str, cle: str, validees: bool = True) -> List[Regle]:
        """Règles qui peuvent viser une marque pour une clé : celles de la marque,
        puis celles de son groupe qui ne doublent pas un motif de la marque."""
        source = self._validees if validees else self._toutes
        m = cle_marque(marque)
        regles = list(source.get((PORTEE_MARQUE, m, cle), ()))
        groupe = self._groupe_de(marque)
        if groupe:
            motifs = self._motifs_marque.get((m, cle), ())
            regles += [r for r in source.get((PORTEE_GROUPE, cle_marque(groupe), cle), ())
                       if r.motif not in motifs]
        return regles

    def meilleure(self, marque: str, cle: str, valeur: str) -> Optional[Regle]:
        """Règle validée retenue pour une clé (marque avant groupe, puis spécificité)."""
        if not valeur:
            return None
        m = cle_marque(marque)
        for r in self._validees.get((PORTEE_MARQUE, m, cle), ()):
            if r.s_applique(valeur):
                return r
        groupe = self._groupe_de(marque)
        if groupe:
            motifs = self._motifs_marque.get((m, cle), ())
            for r in self._validees.get((PORTEE_GROUPE, cle_marque(groupe), cle), ()):
                if r.motif not in motifs and r.s_applique(valeur):
                    return r
        return None

    def resoudre(self, marque: str, valeur_nom: str, valeur_code: str) -> Resolution:
        """Type d'un appareil selon les règles validées (§ 6.2)."""
        par_nom = self.meilleure(marque, CLE_NOM, valeur_nom)
        par_code = self.meilleure(marque, CLE_CODE, valeur_code)
        if par_nom and par_code and par_nom.type_resultat != par_code.type_resultat:
            return Resolution('', par_nom, par_code, conflit=True)
        regle = par_nom or par_code
        return Resolution(regle.type_resultat if regle else '', par_nom, par_code)
