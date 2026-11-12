"""
Accès à la base en LECTURE SEULE pour le rapprochement des fiches (CDC § 5)

La connexion est ouverte en `mode=ro` : aucune écriture n'est possible, même
par erreur. Une connexion déjà ouverte peut aussi être fournie (tests, ou le
service de l'étape 3) ; elle n'est alors jamais modifiée par ce module.

- Index des appareils par marque, en cache : forme normalisée → appareils
  (id, écriture exacte, type). Il sert aux deux passes du § 5.2 et révèle les
  écritures multiples d'une même forme (467 cas en base, 2026-11-12). En lot,
  le cache se réutilise d'une fiche à l'autre.
- Lignée d'une pièce (§ 5.2 « déjà couvert ») : famille de succession
  (successeurs, prédécesseurs, autres branches de la même courante) et groupe
  d'équivalence, pour un ensemble de références de départ, calculée une fois
  par fiche.
"""

import re
import sqlite3
import sys
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from src.data._db_mixins.supersession import DatabaseSupersessionMixin
from src.utils.lecteur_fiche.lecteur import cle_marque

_PONCTUATION = re.compile(r"[\s\-/._]+")
_TRANCHE = 500                 # sous la limite historique de 999 variables SQLite
_PROFONDEUR_MAX = 20           # comme get_supersession_chain
_MARQUES_EN_CACHE = 40
# CTE de succession de la base (une seule écriture de la règle) : elle n'utilise pas self
_CTE_AVANT = DatabaseSupersessionMixin._supersession_chain_cte(None, 'forward')
_CTE_ARRIERE = DatabaseSupersessionMixin._supersession_chain_cte(None, 'backward')


def forme_normalisee(ref: str) -> str:
    """Réf. modèle sans espaces, tirets, /, . ni _, en majuscules (§ 5.2)."""
    return _PONCTUATION.sub('', ref or '').upper()


@dataclass(frozen=True)
class AppareilBase:
    id: int
    marque: str
    ref_modele: str
    type: str


@dataclass(frozen=True)
class StatutPiece:
    id: int
    ref_piece: str
    fantome: bool
    obsolete: bool


class IndexMarque:
    """Appareils d'une marque, rangés par forme normalisée de la réf. modèle."""

    def __init__(self, marque: str, appareils: Iterable[AppareilBase]):
        self.marque = marque
        self.par_forme: Dict[str, List[AppareilBase]] = defaultdict(list)
        for a in appareils:
            self.par_forme[forme_normalisee(a.ref_modele)].append(a)

    def candidats(self, ref_modele: str) -> List[AppareilBase]:
        return self.par_forme.get(forme_normalisee(ref_modele), [])

    def par_prefixe(self, prefixe: str) -> List[AppareilBase]:
        """Appareils dont la forme normalisée commence par `prefixe` (famille de
        références : « HD78 » → HD7800, HD7818/50…), pour proposer un type ou une marque."""
        import bisect
        if not hasattr(self, '_formes_triees'):
            self._formes_triees = sorted(self.par_forme)
        formes = self._formes_triees
        out: List[AppareilBase] = []
        i = bisect.bisect_left(formes, prefixe)
        while i < len(formes) and formes[i].startswith(prefixe):
            out.extend(self.par_forme[formes[i]])
            i += 1
        return out

    def __len__(self):
        return sum(len(v) for v in self.par_forme.values())


def _tranches(valeurs: List, taille: int = _TRANCHE):
    for i in range(0, len(valeurs), taille):
        yield valeurs[i:i + taille]


class AccesBaseLecture:
    """Requêtes de lecture du rapprochement (aucune écriture)."""

    def __init__(self, connexion: sqlite3.Connection, fermer: bool = False):
        self.cnx = connexion
        self._fermer = fermer
        self._index: 'OrderedDict[str, IndexMarque]' = OrderedDict()
        self._marques: Optional[Dict[str, str]] = None
        self._types: Optional[Dict[str, str]] = None
        self._tables: Optional[Set[str]] = None

    @classmethod
    def ouvrir(cls, chemin) -> 'AccesBaseLecture':
        """Ouvre la base en lecture seule (URI mode=ro)."""
        uri = f"file:{Path(chemin).resolve()}?mode=ro"
        return cls(sqlite3.connect(uri, uri=True, check_same_thread=False), fermer=True)

    def fermer(self):
        if self._fermer:
            self.cnx.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fermer()

    def oublier(self, marques: Optional[Iterable[str]] = None):
        """Après une écriture (import en masse, étape 4) : oublie l'index des marques
        touchées (toutes si None), et les écritures de marques et de types, qu'une
        création a pu enrichir. Les autres index restent en cache."""
        if marques is None:
            self._index.clear()
        else:
            for m in marques:
                self._index.pop(m, None)
        self._marques = self._types = None
        self._tables = None

    def _lignes(self, requete: str, params: Iterable = ()) -> List[tuple]:
        return self.cnx.execute(requete, list(params)).fetchall()

    # --- Marques et types de l'outil -----------------------------------------
    def marques(self) -> Dict[str, str]:
        """clé de marque → écriture de l'outil (la plus fréquente)."""
        if self._marques is None:
            self._marques = self._ecritures('manufacturer')
        return self._marques

    def types(self) -> Dict[str, str]:
        """clé de type → écriture de l'outil (la plus fréquente)."""
        if self._types is None:
            self._types = self._ecritures('type')
        return self._types

    def _ecritures(self, colonne: str) -> Dict[str, str]:
        meilleures: Dict[str, Tuple[int, str]] = {}
        for valeur, n in self._lignes(
                f"SELECT {colonne}, COUNT(*) FROM appareils "
                f"WHERE {colonne} IS NOT NULL AND {colonne} <> '' GROUP BY {colonne}"):
            cle = cle_marque(valeur)
            if cle not in meilleures or n > meilleures[cle][0]:
                meilleures[cle] = (n, valeur)
        return {k: v for k, (_, v) in meilleures.items()}

    # --- Appareils ----------------------------------------------------------
    def index_marque(self, marque: str) -> IndexMarque:
        """Index de la marque (écriture de l'outil), en cache."""
        if marque in self._index:
            self._index.move_to_end(marque)
            return self._index[marque]
        rows = self._lignes(
            "SELECT id, ref_modele, type FROM appareils WHERE manufacturer = ?", [marque])
        index = IndexMarque(marque, (
            AppareilBase(i, marque, r or '', sys.intern(t or '')) for i, r, t in rows))
        self._index[marque] = index
        while len(self._index) > _MARQUES_EN_CACHE:
            self._index.popitem(last=False)
        return index

    def appareils_par_ref(self, refs: Iterable[str]) -> Dict[str, List[AppareilBase]]:
        """Réf. modèle exacte → appareils, toutes marques confondues."""
        refs = list(dict.fromkeys(r for r in refs if r))
        out: Dict[str, List[AppareilBase]] = defaultdict(list)
        for lot in _tranches(refs):
            q = ','.join('?' * len(lot))
            for i, m, r, t in self._lignes(
                    f"SELECT id, manufacturer, ref_modele, type FROM appareils "
                    f"WHERE ref_modele IN ({q})", lot):
                out[r].append(AppareilBase(i, m or '', r, t or ''))
        return out

    def appareils_par_nom(self, marques: Iterable[str], nom: str) -> List[AppareilBase]:
        """Appareils dont le nom commercial est exactement `nom`, parmi `marques`."""
        marques = list(dict.fromkeys(m for m in marques if m))
        if not nom or not marques:
            return []
        q = ','.join('?' * len(marques))
        return [AppareilBase(i, m or '', r or '', t or '') for i, m, r, t in self._lignes(
            f"SELECT id, manufacturer, ref_modele, type FROM appareils "
            f"WHERE commercial_ref = ? AND manufacturer IN ({q})", [nom] + marques)]

    def decisions_distinct(self, refs: Iterable[str]) -> Set[str]:
        """Réf. modèle déclarées « appareils distincts » (reference_decisions)."""
        refs = list(dict.fromkeys(r for r in refs if r))
        out: Set[str] = set()
        for lot in _tranches(refs):
            q = ','.join('?' * len(lot))
            out.update(r for (r,) in self._lignes(
                f"SELECT ref_modele FROM reference_decisions "
                f"WHERE decision = 'DISTINCT' AND ref_modele IN ({q})", lot))
        return out

    # --- Pièces et relations ---------------------------------------------------
    def pieces(self, refs: Iterable[str]) -> Dict[str, StatutPiece]:
        refs = list(dict.fromkeys(r for r in refs if r))
        out: Dict[str, StatutPiece] = {}
        for lot in _tranches(refs):
            q = ','.join('?' * len(lot))
            for i, ref, fantome, obsolete in self._lignes(
                    f"SELECT id, ref_piece, is_phantom, is_obsolete FROM pieces "
                    f"WHERE ref_piece IN ({q})", lot):
                out[ref] = StatutPiece(i, ref, bool(fantome), bool(obsolete))
        return out

    def successeurs(self, refs: Iterable[str]) -> Dict[str, Optional[str]]:
        """ref_old → ref_new (None = obsolète sans successeur) pour les refs présentes."""
        refs = list(dict.fromkeys(r for r in refs if r))
        out: Dict[str, Optional[str]] = {}
        for lot in _tranches(refs):
            q = ','.join('?' * len(lot))
            out.update(self._lignes(
                f"SELECT ref_old, ref_new FROM piece_supersessions WHERE ref_old IN ({q})", lot))
        return out

    def chaine(self, ref: str) -> List[str]:
        """[ref, …, courante] : même résultat que get_supersession_chain."""
        rows = self._lignes(_CTE_AVANT + "SELECT ref FROM chain ORDER BY depth ASC",
                            [ref, _PROFONDEUR_MAX])
        return [r for (r,) in rows] or [ref]

    def predecesseurs(self, ref: str) -> List[str]:
        """Refs remplacées directement ou non par `ref` : comme get_all_predecessors."""
        rows = self._lignes(
            _CTE_ARRIERE + "SELECT ref FROM chain WHERE depth > 0 ORDER BY depth ASC",
            [ref, _PROFONDEUR_MAX])
        return list(dict.fromkeys(r for (r,) in rows))

    def groupes(self, refs: Iterable[str]) -> Dict[str, int]:
        """ref → group_id d'équivalence (refs présentes dans un groupe)."""
        refs = list(dict.fromkeys(r for r in refs if r))
        out: Dict[str, int] = {}
        for lot in _tranches(refs):
            q = ','.join('?' * len(lot))
            out.update(self._lignes(
                f"SELECT ref_piece, group_id FROM piece_equivalence_groups "
                f"WHERE ref_piece IN ({q})", lot))
        return out

    def membres_groupes(self, group_ids: Iterable[int]) -> List[str]:
        ids = list(dict.fromkeys(g for g in group_ids if g is not None))
        out: List[str] = []
        for lot in _tranches(ids):
            q = ','.join('?' * len(lot))
            out.extend(r for (r,) in self._lignes(
                f"SELECT ref_piece FROM piece_equivalence_groups WHERE group_id IN ({q})", lot))
        return list(dict.fromkeys(out))

    def lignee(self, refs_depart: Iterable[str]) -> Dict[str, str]:
        """
        Lignée des références de départ : ref → relation ('depart', 'succession'
        ou 'equivalence'). Famille de succession de chaque départ (sa courante et
        tout ce que la courante remplace) puis groupe d'équivalence de toute la
        famille ; les anciennes versions d'une équivalente suivent (propagées en
        base par _propagate_predecessors_to_group, refaites ici par sûreté).
        """
        departs = list(dict.fromkeys(r for r in refs_depart if r))
        relation: Dict[str, str] = {r: 'depart' for r in departs}

        def famille(ref):
            tete = self.chaine(ref)[-1]
            return [tete, *self.predecesseurs(tete)]

        for ref in departs:
            for r in famille(ref):
                relation.setdefault(r, 'succession')
        groupes = self.groupes(list(relation))
        for r in self.membres_groupes(groupes.values()):
            if r not in relation:
                relation[r] = 'equivalence'
                for ancienne in self.predecesseurs(r):
                    relation.setdefault(ancienne, 'equivalence')
        return relation

    def liens(self, refs: Iterable[str]) -> Dict[int, Set[str]]:
        """appareil_id → refs de pièces (parmi `refs`) qui le portent déjà."""
        refs = list(dict.fromkeys(r for r in refs if r))
        out: Dict[int, Set[str]] = defaultdict(set)
        for lot in _tranches(refs):
            q = ','.join('?' * len(lot))
            for ref, appareil_id in self._lignes(
                    f"SELECT p.ref_piece, pa.appareil_id FROM piece_associations pa "
                    f"JOIN pieces p ON p.id = pa.piece_id WHERE p.ref_piece IN ({q})", lot):
                out[appareil_id].add(ref)
        return out

    # --- Mémoires de la reprise (§ 9, étape 3) -----------------------------------
    # Une base qui n'a pas encore été migrée (ouverte sans DatabaseManager) n'a
    # ni ces tables ni ces colonnes : les lectures rendent alors du vide.
    def _a_table(self, nom: str) -> bool:
        if self._tables is None:
            self._tables = {r for (r,) in self._lignes(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        return nom in self._tables

    def _a_colonne(self, table: str, colonne: str) -> bool:
        return self._a_table(table) and colonne in {
            r[1] for r in self._lignes(f"PRAGMA table_info({table})")}

    def decisions_paires(self) -> Dict[Tuple[str, FrozenSet[str]], str]:
        """(clé de marque, {écriture A, écriture B}) → 'meme' / 'distinct'."""
        if not self._a_table('decisions_ecritures'):
            return {}
        return {(m, frozenset((a, b))): d for m, a, b, d in self._lignes(
            "SELECT marque, ecriture_a, ecriture_b, decision FROM decisions_ecritures")}

    def decisions_references(self, ref_piece: str) -> Dict[str, Tuple[str, str]]:
        """référence → (nature, origine) consignées pour la pièce."""
        if not ref_piece or not self._a_table('decisions_references'):
            return {}
        return {r: (n, o or '') for r, n, o in self._lignes(
            "SELECT reference, nature, origine FROM decisions_references WHERE ref_piece = ?",
            [ref_piece])}

    def produit_site(self, ref_interne: str = '', id_product: Optional[int] = None
                     ) -> List[Tuple[str, Optional[int], Optional[str], Optional[str]]]:
        """Produits connus par réf. interne ou id_product : (ref_interne, id_product, ref_piece, ean)."""
        if not self._a_table('produits_site') or (not ref_interne and id_product is None):
            return []
        return self._lignes(
            "SELECT ref_interne, id_product, ref_piece, ean FROM produits_site "
            "WHERE ref_interne = ? OR id_product = ?", [ref_interne or None, id_product])

    def libelle(self, ref_piece: str) -> str:
        rows = self._lignes("SELECT description FROM pieces WHERE ref_piece = ?", [ref_piece])
        return (rows[0][0] or '') if rows else ''

    def liens_site(self, ref_piece: str) -> List[Tuple[AppareilBase, str]]:
        """Liens de la pièce venus du site (provenance renseignée)."""
        if not ref_piece or not self._a_colonne('piece_associations', 'provenance'):
            return []
        return [(AppareilBase(i, m or '', r or '', t or ''), prov) for i, m, r, t, prov in self._lignes(
            "SELECT a.id, a.manufacturer, a.ref_modele, a.type, pa.provenance "
            "FROM piece_associations pa JOIN pieces p ON p.id = pa.piece_id "
            "JOIN appareils a ON a.id = pa.appareil_id "
            "WHERE p.ref_piece = ? AND pa.provenance IS NOT NULL", [ref_piece])]
