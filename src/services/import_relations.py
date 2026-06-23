"""Modèle de relations entre références importées : dérivation des états et
orchestration de l'application en base.

Pivot : l'utilisateur déclare des **liens simples** (« Courante », « Ancienne
version de [réf récente] », « groupe d'équivalence », « obsolète », liens base) ;
on **dérive** et on applique. L'utilisateur ne connaît pas l'ordre d'une chaîne :
chaque ancienne pointe DIRECTEMENT vers sa courante (topologie en étoile), donc
aucun cycle ni conflit possible par construction (une réf est courante OU ancienne,
jamais les deux).

Pur Python : `recompute_relations()` n'a aucune dépendance Qt/DB (testable seul).
`apply_relations()` écrit via un db_manager (`add_supersession`, `add_equivalence`,
`mark_obsolete`).

Directions de succession (toutes via add_supersession(ref_old, ref_new)) :
- `newer_ref`        : « cette réf est une ancienne version de C »  → (ref → C)
- `base_replaces`    : « cette réf remplace une ancienne réf X en base » → (X → ref)
- `base_replaced_by` : « cette réf est remplacée par Y en base » → (ref → Y)
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple


@dataclass
class RefRelation:
    """Relations déclarées pour UNE référence importée."""
    ref: str
    is_current: bool = False                 # marquée « Courante » (la plus récente)
    newer_ref: Optional[str] = None          # « ancienne version de » → réf récente (lot, base, ou hors base)
    equiv_group: Optional[int] = None        # id de groupe d'équivalence LOCAL au lot
    is_obsolete: bool = False
    base_replaces: Optional[str] = None      # réf base que cette réf remplace (X → ref)
    base_replaced_by: Optional[str] = None   # réf base qui remplace cette réf (ref → Y)


@dataclass
class DerivedRelations:
    chains: List[List[str]] = field(default_factory=list)          # chaînes ordonnées (anciennes… → tête)
    heads: Set[str] = field(default_factory=set)                   # courantes (marquées is_current)
    chain_id_by_ref: Dict[str, int] = field(default_factory=dict)  # ref → id de composante (couleur)
    equiv_groups: Dict[int, List[str]] = field(default_factory=dict)
    in_chain: Set[str] = field(default_factory=set)                # réfs touchées par ≥1 lien de succession
    warnings: List[Tuple[str, str]] = field(default_factory=list)  # (ref, message)


def recompute_relations(relations: List[RefRelation]) -> DerivedRelations:
    """Dérive l'ensemble des états à partir des liens déclarés. Pur, sans effet."""
    out = DerivedRelations()
    by_ref = {r.ref: r for r in relations}

    # Courantes = réfs explicitement marquées
    out.heads = {r.ref for r in relations if r.is_current}

    # in_chain : toute réf touchée par un lien de succession (lot ou base)
    for r in relations:
        if r.newer_ref or r.base_replaces or r.base_replaced_by:
            out.in_chain.add(r.ref)
        if r.newer_ref in by_ref:
            out.in_chain.add(r.newer_ref)
        if r.is_current and any(o.newer_ref == r.ref for o in relations):
            out.in_chain.add(r.ref)

    # Composantes : chaque ancienne (newer_ref dans le lot) est reliée à sa tête.
    parent: Dict[str, str] = {r.ref: r.ref for r in relations}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for r in relations:
        if r.newer_ref and r.newer_ref in by_ref and r.newer_ref != r.ref:
            union(r.ref, r.newer_ref)

    # Couleurs de composante (seulement réfs in_chain), id par ordre d'apparition
    comp_id: Dict[str, int] = {}
    next_id = 0
    for r in relations:
        if r.ref not in out.in_chain:
            continue
        root = find(r.ref)
        if root not in comp_id:
            comp_id[root] = next_id
            next_id += 1
        out.chain_id_by_ref[r.ref] = comp_id[root]

    # Chaînes : anciennes regroupées par tête (dans le lot) + la tête
    olds_by_head: Dict[str, List[str]] = {}
    for r in relations:
        if r.newer_ref and r.newer_ref in by_ref and r.newer_ref != r.ref:
            olds_by_head.setdefault(r.newer_ref, []).append(r.ref)
    for head, olds in olds_by_head.items():
        out.chains.append(sorted(olds) + [head])

    # Groupes d'équivalence
    for r in relations:
        if r.equiv_group is not None:
            out.equiv_groups.setdefault(r.equiv_group, []).append(r.ref)

    # ── Avertissements ────────────────────────────────────────────────────────
    for r in relations:
        if r.is_current and r.newer_ref:
            out.warnings.append((r.ref, "Marquée Courante ET ancienne version — incohérent."))
        if r.newer_ref == r.ref:
            out.warnings.append((r.ref, "Une réf ne peut pas être sa propre version récente."))
        if r.newer_ref and r.base_replaced_by and r.newer_ref != r.base_replaced_by:
            out.warnings.append((r.ref, "Deux réfs récentes déclarées (lignée + base)."))
        if r.base_replaces and r.base_replaced_by and r.base_replaces == r.base_replaced_by:
            out.warnings.append((r.ref, "« remplace » et « remplacée par » pointent la même réf."))
        if r.is_obsolete and r.base_replaces:
            out.warnings.append((r.ref, "Réf obsolète qui en remplace une autre — à vérifier."))

    # Membre d'équivalence qui n'est pas une courante (avertissement doux)
    for gid, members in out.equiv_groups.items():
        for m in members:
            rel = by_ref.get(m)
            if rel and not rel.is_current and (rel.newer_ref or m in out.in_chain):
                out.warnings.append((m, "Réf équivalente qui n'est pas une courante."))

    return out


def apply_relations(relations: List[RefRelation], db) -> Dict[str, int]:
    """Applique les relations en base via `db`. Topologie en étoile (pas de cycle).
    Retourne un récap de comptes. Ne lève jamais."""
    counts = {'successions': 0, 'equivalences': 0, 'obsoletes': 0, 'errors': 0}

    def _superse(old, new):
        if not old or not new or old == new:
            return
        try:
            res = db.add_supersession(old, new)
            ok = res[0] if isinstance(res, (tuple, list)) else bool(res)
            counts['successions' if ok else 'errors'] += 1
        except Exception:
            counts['errors'] += 1

    # 1) Lignées : chaque ancienne → sa courante ; + liens base
    for r in relations:
        if r.newer_ref:
            _superse(r.ref, r.newer_ref)            # ref est une ancienne version de newer_ref
        if r.base_replaces:
            _superse(r.base_replaces, r.ref)        # ref remplace une ancienne réf base
        if r.base_replaced_by:
            _superse(r.ref, r.base_replaced_by)     # ref remplacée par une réf base

    # 2) Obsolescence
    for r in relations:
        if r.is_obsolete:
            try:
                counts['obsoletes' if db.mark_obsolete(r.ref) else 'errors'] += 1
            except Exception:
                counts['errors'] += 1

    # 3) Groupes d'équivalence : liens par paires (ancre ↔ autres) → fusion
    derived = recompute_relations(relations)
    for gid, members in derived.equiv_groups.items():
        uniq = [m for i, m in enumerate(members) if m not in members[:i]]
        if len(uniq) < 2:
            continue
        anchor = uniq[0]
        for m in uniq[1:]:
            try:
                res = db.add_equivalence(anchor, m)
                ok = res[0] if isinstance(res, (tuple, list)) else bool(res)
                counts['equivalences' if ok else 'errors'] += 1
            except Exception:
                counts['errors'] += 1

    return counts
