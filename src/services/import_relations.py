"""Modèle « par groupes » des relations entre références importées + dérivation
des états et orchestration de l'application en base.

L'utilisateur organise les réfs en GROUPES (il ne connaît pas l'ordre des chaînes,
il connaît la courante). Deux types de groupes :
- **lignée de succession** : une `courante` (réf récente, lot / base / à créer en
  fantôme) + des `members` (anciennes versions). À l'application : chaque membre →
  add_supersession(membre, courante) + mark_obsolete(membre).
- **groupe d'équivalence** : des `members` (+ `courante` repère optionnelle), tous
  valides et mutuellement équivalents (add_equivalence). Aucune obsolescence.

Une **checkbox `cross_equivalent`** par groupe : les courantes de tous les groupes
cochés sont déclarées équivalentes entre elles (cas « plusieurs courantes selon la
marque »).

En plus des groupes, chaque réf isolée peut être marquée obsolète et/ou « remplace
une réf en base » (carte). Pur Python ; `apply_relations` écrit via un db_manager
(`add_supersession`, `add_equivalence`, `mark_obsolete`).
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple

KIND_SUCCESSION = 'succession'
KIND_EQUIVALENCE = 'equivalence'


@dataclass
class Group:
    kind: str = KIND_SUCCESSION                      # 'succession' | 'equivalence'
    courante: Optional[str] = None                   # réf récente / repère (lot, base, ou à créer)
    members: List[str] = field(default_factory=list) # réfs du lot dans le groupe
    cross_equivalent: bool = False                   # « équivalente aux autres groupes cochés »


@dataclass
class CardData:
    """Données portées par la carte d'une réf (hors groupes)."""
    ref: str
    is_obsolete: bool = False
    base_replaces: Optional[str] = None              # réf base que cette réf remplace (base → ref)


@dataclass
class DerivedModel:
    courantes: Set[str] = field(default_factory=set)         # courantes de lignées présentes dans le lot (badge)
    succ_group_of: Dict[str, int] = field(default_factory=dict)   # ref → index de lignée (liseré)
    equiv_group_of: Dict[str, int] = field(default_factory=dict)  # ref → index de groupe d'équivalence (pastille)
    obsoletes: Set[str] = field(default_factory=set)         # réfs qui seront marquées obsolètes
    cross_courantes: List[str] = field(default_factory=list) # courantes liées par la checkbox
    phantoms: Set[str] = field(default_factory=set)          # réfs citées absentes du lot ET de la base
    warnings: List[Tuple[str, str]] = field(default_factory=list)


def derive(groups: List[Group], cards: List[CardData],
           lot_refs: Set[str], base_refs: Set[str]) -> DerivedModel:
    """Dérive les états visuels et de cohérence. Pur, sans effet."""
    out = DerivedModel()
    cited_external: Set[str] = set()

    for gi, g in enumerate(groups):
        if g.kind == KIND_SUCCESSION:
            if g.courante:
                if g.courante in lot_refs:
                    out.courantes.add(g.courante)
                elif g.courante not in base_refs:
                    cited_external.add(g.courante)
            for m in g.members:
                out.succ_group_of[m] = gi
                # Une courante peut figurer parmi les membres (elle y reste visible) :
                # elle n'est alors ni obsolète ni auto-remplacée (cas géré, pas une erreur).
                if g.courante and m != g.courante:
                    out.obsoletes.add(m)
                if not g.courante:
                    out.warnings.append((m, "Lignée sans courante définie."))
        else:  # équivalence
            for m in g.members:
                out.equiv_group_of[m] = gi
            if g.courante and g.courante not in lot_refs and g.courante not in base_refs:
                cited_external.add(g.courante)

    # Réfs isolées obsolètes (carte) + liens « remplace » base
    for c in cards:
        if c.is_obsolete:
            out.obsoletes.add(c.ref)
        if c.base_replaces and c.base_replaces not in lot_refs and c.base_replaces not in base_refs:
            cited_external.add(c.base_replaces)

    # Checkbox « équivalente entre groupes » : courantes des groupes cochés
    out.cross_courantes = [g.courante for g in groups if g.cross_equivalent and g.courante]
    if len(out.cross_courantes) == 1:
        out.warnings.append((out.cross_courantes[0],
                             "Groupe coché « équivalent » seul — au moins deux requis."))

    out.phantoms = cited_external
    return out


def count_planned_relations(groups: List[Group], cards: List[CardData]) -> Dict[str, int]:
    """Compter les relations qui SERAIENT créées par apply_relations, sans écrire.
    Miroir exact de sa logique (déduplication et cas old == new compris) —
    utilisé par le récap en direct du panneau et le garde-fou à la validation."""
    counts = {'successions': 0, 'equivalences': 0, 'obsoletes': 0}
    obsoletes: Set[str] = set()

    for g in groups:
        if g.kind == KIND_SUCCESSION and g.courante:
            for m in g.members:
                if m and m != g.courante:
                    counts['successions'] += 1
                    obsoletes.add(m)
        elif g.kind == KIND_EQUIVALENCE:
            members = [m for i, m in enumerate(g.members) if m and m not in g.members[:i]]
            if g.courante and g.courante not in members:
                members = [g.courante] + members
            counts['equivalences'] += max(0, len(members) - 1)

    for c in cards:
        if c.is_obsolete:
            obsoletes.add(c.ref)
        if c.base_replaces and c.base_replaces != c.ref:
            counts['successions'] += 1

    cross = [g.courante for g in groups if g.cross_equivalent and g.courante]
    cross = [c for i, c in enumerate(cross) if c not in cross[:i]]
    counts['equivalences'] += max(0, len(cross) - 1)

    counts['obsoletes'] = len(obsoletes)
    return counts


def apply_relations(groups: List[Group], cards: List[CardData], db) -> Dict[str, int]:
    """Applique le modèle en base via `db`. Retourne un récap de comptes.
    Ne lève jamais (les primitives renvoient (ok, msg) ou bool)."""
    counts = {'successions': 0, 'equivalences': 0, 'obsoletes': 0, 'errors': 0}

    def _ok(res):
        return res[0] if isinstance(res, (tuple, list)) else bool(res)

    def _superse(old, new):
        if not old or not new or old == new:
            return
        try:
            counts['successions' if _ok(db.add_supersession(old, new)) else 'errors'] += 1
        except Exception:
            counts['errors'] += 1

    def _equiv(a, b):
        if not a or not b or a == b:
            return
        try:
            counts['equivalences' if _ok(db.add_equivalence(a, b)) else 'errors'] += 1
        except Exception:
            counts['errors'] += 1

    def _obsolete(ref):
        try:
            counts['obsoletes' if db.mark_obsolete(ref) else 'errors'] += 1
        except Exception:
            counts['errors'] += 1

    obsoletes: Set[str] = set()

    for g in groups:
        if g.kind == KIND_SUCCESSION and g.courante:
            for m in g.members:
                if m != g.courante:
                    _superse(m, g.courante)
                    obsoletes.add(m)
        elif g.kind == KIND_EQUIVALENCE:
            members = [m for i, m in enumerate(g.members) if m not in g.members[:i]]
            if g.courante and g.courante not in members:
                members = [g.courante] + members
            for m in members[1:]:
                _equiv(members[0], m)

    # Réfs isolées obsolètes + « remplace » base (carte)
    for c in cards:
        if c.is_obsolete:
            obsoletes.add(c.ref)
        if c.base_replaces:
            _superse(c.base_replaces, c.ref)

    for ref in obsoletes:
        _obsolete(ref)

    # Checkbox « équivalente entre groupes » : relier les courantes cochées
    cross = [g.courante for g in groups if g.cross_equivalent and g.courante]
    cross = [c for i, c in enumerate(cross) if c not in cross[:i]]
    for c in cross[1:]:
        _equiv(cross[0], c)

    return counts
