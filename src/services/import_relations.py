"""Modèle « par groupes » des relations entre références importées + dérivation
des états et orchestration de l'application en base.

L'utilisateur organise les réfs en GROUPES (il ne connaît pas l'ordre des chaînes,
il connaît la courante). Deux types de groupes :
- **lignée de succession** : une `courante` (réf récente, lot / base / à créer en
  fantôme) + des `members` (anciennes versions : réfs du lot, ou saisies hors lot
  — en base ou à créer en fantôme). À l'application : chaque membre →
  add_supersession(membre, courante) + mark_obsolete(membre).
- **groupe d'équivalence** : des `members` (+ `courante` repère optionnelle), tous
  valides et mutuellement équivalents (add_equivalence). Aucune obsolescence.

Une **checkbox `cross_equivalent`** par groupe : les ancres de tous les groupes
cochés sont déclarées équivalentes entre elles (cas « plusieurs courantes selon la
marque », ou « ces réfs interchangeables équivalent à cette lignée »). L'ancre est
la courante d'une lignée, ou la repère / le 1er membre d'un groupe d'équivalence
(cf. `cross_anchor`).

En plus des groupes, chaque réf isolée peut être marquée obsolète, « remplace
une réf en base », et/ou « remplacée par » une réf (carte, v3.97.0 : remplaçante
DIRECTE, qui peut elle-même être l'ancienne version d'une lignée — c'est ainsi
qu'on chaîne A → B → C sans perdre l'étape B). Pur Python ; `apply_relations` écrit via un db_manager
(`add_supersession`, `add_equivalence`, `mark_obsolete`, et `propagate_description`
si le db l'expose — cf. `_propager_libelle`).
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
    replaced_by: Optional[str] = None                # remplaçante directe (ref → replaced_by), v3.97.0


@dataclass
class DerivedModel:
    courantes: Set[str] = field(default_factory=set)         # courantes de lignées présentes dans le lot (badge)
    succ_group_of: Dict[str, int] = field(default_factory=dict)   # ref → index de lignée (liseré)
    equiv_group_of: Dict[str, int] = field(default_factory=dict)  # ref → index de groupe d'équivalence (pastille)
    obsoletes: Set[str] = field(default_factory=set)         # réfs qui seront marquées obsolètes
    cross_courantes: List[str] = field(default_factory=list) # ancres liées par la checkbox (cf. cross_anchor)
    phantoms: Set[str] = field(default_factory=set)          # réfs citées absentes du lot ET de la base
    warnings: List[Tuple[str, str]] = field(default_factory=list)


def cross_anchor(g: Group) -> Optional[str]:
    """Réf qui porte le lien « équivalente entre groupes » pour le groupe `g`.

    - Lignée : la courante (sans courante, la lignée ne peut rien relier).
    - Groupe d'équivalence : la courante repère si saisie, sinon le 1er membre.
      N'importe quel membre convient : tous seront dans le même groupe en base.

    Source unique pour `derive`, `count_planned_relations` et `apply_relations`
    (qui doivent rester des miroirs exacts).
    """
    if g.kind == KIND_SUCCESSION:
        return g.courante or None
    return g.courante or next((m for m in g.members if m), None)


def cross_anchors(groups: List[Group]) -> List[str]:
    """Ancres des groupes cochés « équivalente », sans doublon, dans l'ordre."""
    anchors = [a for a in (cross_anchor(g) for g in groups if g.cross_equivalent) if a]
    return [a for i, a in enumerate(anchors) if a not in anchors[:i]]


def successions_prevues(groups: List[Group], cards: List[CardData]) -> List[Tuple[str, str]]:
    """Liens (ancienne, nouvelle) déclarés, dans l'ordre et sans doublon exact :
    membres de lignée → courante, « remplace » base → carte, carte → « remplacée par »."""
    liens: List[Tuple[str, str]] = []
    for g in groups:
        if g.kind == KIND_SUCCESSION and g.courante:
            liens += [(m, g.courante) for m in g.members if m and m != g.courante]
    for c in cards:
        if c.base_replaces and c.base_replaces != c.ref:
            liens.append((c.base_replaces, c.ref))
        if c.replaced_by and c.replaced_by != c.ref:
            liens.append((c.ref, c.replaced_by))
    return [l for i, l in enumerate(liens) if l not in liens[:i]]


def conflits_remplacement(groups: List[Group], cards: List[CardData]) -> List[str]:
    """Déclarations de remplacement impossibles à enregistrer telles quelles.

    - Une réf ne peut avoir qu'UNE remplaçante (clé primaire `ref_old` de
      `piece_supersessions`) : deux remplaçantes différentes, et la dernière
      écrite effacerait l'autre sans rien dire (INSERT OR REPLACE).
    - Une boucle (A → B → A) serait refusée par la base, lien par lien.
    Ce sont des erreurs de saisie, pas des « sans effet » : la validation bloque.
    """
    succ: Dict[str, List[str]] = {}
    for old, new in successions_prevues(groups, cards):
        succ.setdefault(old, [])
        if new not in succ[old]:
            succ[old].append(new)

    msgs = []
    for old, news in succ.items():
        if len(news) > 1:
            msgs.append(f"{old} est déclarée remplacée par {' et par '.join(news)} : "
                        "une réf n'a qu'une seule remplaçante. Si elles sont "
                        "interchangeables, déclarez-les équivalentes entre elles.")

    # Boucles : suivies uniquement par les liens sans ambiguïté
    unique = {o: n[0] for o, n in succ.items() if len(n) == 1}
    deja = set()
    for depart in unique:
        chemin, ref = [], depart
        while ref in unique and ref not in chemin:
            chemin.append(ref)
            ref = unique[ref]
        if ref in chemin:
            boucle = chemin[chemin.index(ref):]
            cle = frozenset(boucle)
            if cle not in deja:
                deja.add(cle)
                msgs.append("Boucle de remplacement : "
                            + " → ".join(boucle + [ref]) + ".")
    return msgs


def derive(groups: List[Group], cards: List[CardData],
           lot_refs: Set[str], base_refs: Set[str]) -> DerivedModel:
    """Dérive les états visuels et de cohérence. Pur, sans effet."""
    out = DerivedModel()
    cited_external: Set[str] = set()

    for gi, g in enumerate(groups):
        # Membres saisis hors lot (v3.91.0) : absents de la base → fantômes.
        for m in g.members:
            if m and m not in lot_refs and m not in base_refs:
                cited_external.add(m)
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

    # Réfs isolées obsolètes (carte) + liens « remplace » base + « remplacée par »
    for c in cards:
        if c.is_obsolete:
            out.obsoletes.add(c.ref)
        if c.base_replaces and c.base_replaces not in lot_refs and c.base_replaces not in base_refs:
            cited_external.add(c.base_replaces)
        if c.replaced_by and c.replaced_by != c.ref:
            out.obsoletes.add(c.ref)
            if c.replaced_by not in lot_refs and c.replaced_by not in base_refs:
                cited_external.add(c.replaced_by)

    for msg in conflits_remplacement(groups, cards):
        out.warnings.append(("", msg))

    # Checkbox « équivalente entre groupes » : courantes des groupes cochés
    out.cross_courantes = [a for a in (cross_anchor(g) for g in groups if g.cross_equivalent) if a]
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
        if c.replaced_by and c.replaced_by != c.ref:
            counts['successions'] += 1
            obsoletes.add(c.ref)

    cross = cross_anchors(groups)
    counts['equivalences'] += max(0, len(cross) - 1)

    counts['obsoletes'] = len(obsoletes)
    return counts


def apply_relations(groups: List[Group], cards: List[CardData], db,
                    journal: Optional[List[str]] = None) -> Dict[str, int]:
    """Applique le modèle en base via `db`. Retourne un récap de comptes.
    Ne lève jamais (les primitives renvoient (ok, msg) ou bool).
    `journal` (facultatif) reçoit chaque lien créé (« A → B », « A ≡ B ») et
    chaque refus (« A → B refusé : … »), pour le log de l'import."""
    counts = {'successions': 0, 'equivalences': 0, 'obsoletes': 0, 'errors': 0}

    def _ok(res):
        return res[0] if isinstance(res, (tuple, list)) else bool(res)

    def _propager_libelle(a, b):
        """Faire hériter le libellé à celle des deux réfs qui n'en a pas.

        Une réf citée mais absente de la base est créée en fantôme SANS libellé :
        sans cette propagation, elle reste anonyme pour toujours alors que sa
        voisine porte le nom (67 des 72 cas observés en base le 2026-09-22).

        Volontairement hors du comptage et de son try/except : `db` est du
        duck-typing (les tests passent un double qui n'expose que les trois
        primitives de relation). Une absence de méthode ne doit pas se
        transformer en erreur de relation — la relation, elle, a bien été créée.
        """
        propager = getattr(db, 'propagate_description', None)
        if propager is None:
            return
        try:
            propager(a, b)
        except Exception:
            pass

    def _noter(lien, res, ok):
        if journal is None:
            return
        if ok:
            journal.append(lien)
        else:
            motif = res[1] if isinstance(res, (tuple, list)) and len(res) > 1 else ""
            journal.append(f"{lien} refusé" + (f" : {motif}" if motif else ""))

    def _superse(old, new):
        if not old or not new or old == new:
            return
        try:
            res = db.add_supersession(old, new)
            ok = _ok(res)
        except Exception as e:
            counts['errors'] += 1
            _noter(f"{old} → {new}", (False, str(e)), False)
            return
        counts['successions' if ok else 'errors'] += 1
        _noter(f"{old} → {new}", res, ok)
        if ok:
            _propager_libelle(old, new)

    def _equiv(a, b):
        if not a or not b or a == b:
            return
        try:
            res = db.add_equivalence(a, b)
            ok = _ok(res)
        except Exception as e:
            counts['errors'] += 1
            _noter(f"{a} ≡ {b}", (False, str(e)), False)
            return
        counts['equivalences' if ok else 'errors'] += 1
        _noter(f"{a} ≡ {b}", res, ok)
        if ok:
            _propager_libelle(a, b)

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

    # Réfs isolées obsolètes + « remplace » base + « remplacée par » (carte)
    for c in cards:
        if c.is_obsolete:
            obsoletes.add(c.ref)
        if c.base_replaces:
            _superse(c.base_replaces, c.ref)
        if c.replaced_by and c.replaced_by != c.ref:
            _superse(c.ref, c.replaced_by)
            obsoletes.add(c.ref)

    for ref in obsoletes:
        _obsolete(ref)

    # Checkbox « équivalente entre groupes » : relier les ancres cochées
    cross = cross_anchors(groups)
    for c in cross[1:]:
        _equiv(cross[0], c)

    return counts
