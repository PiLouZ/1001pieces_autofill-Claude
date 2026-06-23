"""Modèle de relations entre références importées : dérivation des états et
orchestration de l'application en base.

Pivot conceptuel : l'utilisateur déclare des **liens** (« cette réf suit X »,
« appartient au groupe G », « remplace / est remplacée par une réf en base »,
« obsolète ») ; on **dérive** les états (têtes/courantes, composantes de chaîne,
membres de groupe). Aucun état dérivé n'est saisi → pas d'incohérence possible.

Pur Python : `recompute_relations()` n'a aucune dépendance Qt/DB (testable seul).
`apply_relations()` orchestre l'écriture via un db_manager exposant
`add_supersession`, `add_equivalence`, `mark_obsolete`.

Sémantique de `suit_ref` : sur la carte de B2, « Suit : B1 » = B1 est remplacée
par B2 → supersession(ref_old=B1, ref_new=B2). La tête (courante) d'une chaîne est
la réf que personne ne suit (aucun successeur) et qui n'est pas remplacée par une
réf en base. `piece_supersessions.ref_old` étant clé primaire, une réf n'a qu'UN
successeur : déclarer deux fois le même prédécesseur est un conflit.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple


@dataclass
class RefRelation:
    """Relations déclarées pour UNE référence importée."""
    ref: str
    suit_ref: Optional[str] = None          # prédécesseur dans le lot (supersession suit_ref → ref)
    equiv_group: Optional[int] = None        # id de groupe d'équivalence LOCAL au lot
    is_obsolete: bool = False
    base_replaces: Optional[str] = None      # réf base que cette réf remplace (supersession base → ref)
    base_replaced_by: Optional[str] = None   # réf base qui remplace cette réf (supersession ref → base)


@dataclass
class DerivedRelations:
    chains: List[List[str]] = field(default_factory=list)        # chaînes ordonnées (queue → tête)
    heads: Set[str] = field(default_factory=set)                 # têtes = courantes
    chain_id_by_ref: Dict[str, int] = field(default_factory=dict)  # ref → id de composante (couleur)
    equiv_groups: Dict[int, List[str]] = field(default_factory=dict)  # group local → membres
    in_chain: Set[str] = field(default_factory=set)             # réfs impliquées dans ≥1 lien de succession
    warnings: List[Tuple[str, str]] = field(default_factory=list)  # (ref, message)
    invalid_suit: Set[str] = field(default_factory=set)         # réfs dont le lien « suit » est invalide (cycle/doublon)


def recompute_relations(relations: List[RefRelation]) -> DerivedRelations:
    """Dérive l'ensemble des états à partir des liens déclarés. Pur, sans effet."""
    out = DerivedRelations()
    by_ref = {r.ref: r for r in relations}
    refs = list(by_ref.keys())

    # ── Prédécesseur → successeur(s) ; détection des doublons de prédécesseur ──
    successors_of: Dict[str, List[str]] = {}
    for r in relations:
        p = r.suit_ref
        if not p:
            continue
        if p not in by_ref:
            out.warnings.append((r.ref, f"« Suit » pointe vers une réf absente du lot : {p}"))
            out.invalid_suit.add(r.ref)
            continue
        if p == r.ref:
            out.warnings.append((r.ref, "Une réf ne peut pas se suivre elle-même."))
            out.invalid_suit.add(r.ref)
            continue
        successors_of.setdefault(p, []).append(r.ref)

    # Doublon de prédécesseur : une réf ne peut avoir qu'UN successeur (ref_old PK)
    for p, succs in successors_of.items():
        if len(succs) > 1:
            for s in succs:
                out.invalid_suit.add(s)
                out.warnings.append(
                    (s, f"Plusieurs réfs suivent « {p} » ({', '.join(succs)}) — une seule possible."))

    # ── Détection de cycle (en suivant suit_ref) ──────────────────────────────
    for r in relations:
        seen = set()
        cur = r.ref
        while cur is not None:
            if cur in seen:
                out.invalid_suit.add(r.ref)
                out.warnings.append((r.ref, "Boucle de succession détectée."))
                break
            seen.add(cur)
            nxt = by_ref.get(cur)
            cur = nxt.suit_ref if (nxt and nxt.suit_ref in by_ref) else None

    # ── Liens valides (hors invalides) → composantes + chaînes + têtes ────────
    valid_edges = [(r.suit_ref, r.ref) for r in relations
                   if r.suit_ref in by_ref and r.ref not in out.invalid_suit and r.suit_ref != r.ref]

    # in_chain : toute réf touchée par un lien de succession (intra-lot ou base)
    for r in relations:
        if r.suit_ref or r.base_replaces or r.base_replaced_by:
            out.in_chain.add(r.ref)
        if r.suit_ref in by_ref:
            out.in_chain.add(r.suit_ref)

    # Union-Find sur les arêtes valides → composantes (couleurs)
    parent: Dict[str, str] = {ref: ref for ref in refs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for old, new in valid_edges:
        union(old, new)

    # Successeurs valides
    valid_succ: Dict[str, str] = {old: new for old, new in valid_edges}  # old → new (1 seul)
    valid_pred: Dict[str, str] = {new: old for old, new in valid_edges}  # new → old

    # Têtes (courantes) : réf d'une chaîne sans successeur valide et non remplacée par une base
    for r in relations:
        if r.ref not in out.in_chain:
            continue
        has_successor = r.ref in valid_succ
        if not has_successor and not r.base_replaced_by:
            out.heads.add(r.ref)

    # Couleurs de composante : id stable par ordre d'apparition (uniquement réfs in_chain)
    comp_id: Dict[str, int] = {}
    next_id = 0
    for ref in refs:
        if ref not in out.in_chain:
            continue
        root = find(ref)
        if root not in comp_id:
            comp_id[root] = next_id
            next_id += 1
        out.chain_id_by_ref[ref] = comp_id[root]

    # Chaînes ordonnées (queue → tête) par composante
    chains_by_comp: Dict[int, List[str]] = {}
    for ref in refs:
        cid = out.chain_id_by_ref.get(ref)
        if cid is None:
            continue
        chains_by_comp.setdefault(cid, [])
    for cid in chains_by_comp:
        # queue = réf de la composante sans prédécesseur valide
        members = [ref for ref in refs if out.chain_id_by_ref.get(ref) == cid]
        tails = [m for m in members if m not in valid_pred]
        ordered: List[str] = []
        if tails:
            cur = tails[0]
            guard = 0
            while cur is not None and guard <= len(members):
                ordered.append(cur)
                cur = valid_succ.get(cur)
                guard += 1
        else:
            ordered = members  # composante dégénérée (ne devrait pas arriver hors cycle)
        chains_by_comp[cid] = ordered
    out.chains = [chains_by_comp[cid] for cid in sorted(chains_by_comp)]

    # ── Groupes d'équivalence (locaux) ────────────────────────────────────────
    for r in relations:
        if r.equiv_group is not None:
            out.equiv_groups.setdefault(r.equiv_group, []).append(r.ref)

    # Avertissement doux : membre d'équivalence qui n'est pas une tête de chaîne
    for gid, members in out.equiv_groups.items():
        for m in members:
            rel = by_ref.get(m)
            if rel and m in out.in_chain and m not in out.heads:
                out.warnings.append(
                    (m, "Réf équivalente qui n'est pas la plus récente de sa chaîne."))

    # ── Cohérences douces sur les liens base ──────────────────────────────────
    for r in relations:
        if r.base_replaces and r.base_replaced_by and r.base_replaces == r.base_replaced_by:
            out.warnings.append((r.ref, "« remplace » et « remplacée par » pointent la même réf."))
        if r.is_obsolete and r.base_replaces:
            out.warnings.append((r.ref, "Réf obsolète qui en remplace une autre — à vérifier."))
        if r.base_replaced_by and r.ref in valid_succ:
            out.warnings.append((r.ref, "Deux successeurs déclarés (lot + base)."))

    return out


def apply_relations(relations: List[RefRelation], db) -> Dict[str, int]:
    """Applique les relations en base via `db` (add_supersession / add_equivalence /
    mark_obsolete). Ignore les liens « suit » structurellement invalides (cycle/doublon)
    détectés par `recompute_relations`. Retourne un récap de comptes.

    Ne lève jamais : chaque écriture est protégée (les primitives renvoient (ok, msg)).
    """
    derived = recompute_relations(relations)
    counts = {'successions': 0, 'equivalences': 0, 'obsoletes': 0, 'errors': 0}

    def _superse(old, new):
        try:
            res = db.add_supersession(old, new)
            ok = res[0] if isinstance(res, (tuple, list)) else bool(res)
            if ok:
                counts['successions'] += 1
            else:
                counts['errors'] += 1
        except Exception:
            counts['errors'] += 1

    # 1) Chaînes intra-lot (hors liens invalides)
    for r in relations:
        if r.suit_ref and r.ref not in derived.invalid_suit and r.suit_ref != r.ref:
            _superse(r.suit_ref, r.ref)

    # 2) Liens vers la base
    for r in relations:
        if r.base_replaces:
            _superse(r.base_replaces, r.ref)
        if r.base_replaced_by:
            _superse(r.ref, r.base_replaced_by)

    # 3) Obsolescence
    for r in relations:
        if r.is_obsolete:
            try:
                if db.mark_obsolete(r.ref):
                    counts['obsoletes'] += 1
                else:
                    counts['errors'] += 1
            except Exception:
                counts['errors'] += 1

    # 4) Groupes d'équivalence : liens par paires (membre 0 ↔ chaque autre) → fusion
    for gid, members in derived.equiv_groups.items():
        uniq = [m for i, m in enumerate(members) if m not in members[:i]]  # dédup, ordre stable
        if len(uniq) < 2:
            continue
        anchor = uniq[0]
        for m in uniq[1:]:
            try:
                res = db.add_equivalence(anchor, m)
                ok = res[0] if isinstance(res, (tuple, list)) else bool(res)
                if ok:
                    counts['equivalences'] += 1
                else:
                    counts['errors'] += 1
            except Exception:
                counts['errors'] += 1

    return counts
