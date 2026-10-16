"""
Service de scoring de similarité de référence — suggestions Type/Marque.

COMPLÈTE (ne remplace JAMAIS) le mécanisme d'auto-complétion EXACTE de
`import_manager.py` (_build_autocomplete_cache / _apply_autocomplete_from_cache).
Il n'intervient que pour les lignes restées incomplètes après la correspondance
exacte, et ne fait QUE proposer des candidats : aucune écriture, aucune
application automatique. La validation utilisateur est toujours obligatoire
(discipline ZERO REGRESSION).

Module pur Python : aucune dépendance Qt ni accès base de données. La
construction de l'index (lecture de la base) est la responsabilité de
l'appelant — ce service ne fait que du calcul sur des données fournies.

Deux paliers de confiance (décidés après analyse des données réelles) :
  - Palier A « quasi-exact » : même référence à un suffixe de variante /NN près
    (ex. SMU6ZCS10S/58 vs SMU6ZCS10S/82 = même appareil) → score 1.0.
  - Palier B « fuzzy » : similarité difflib >= seuil (0.90 par défaut). MODULÉ
    par le format de la référence : un préfixe alphabétique (code technique
    fabricant) est fiable ; un préfixe purement numérique (catalogue générique
    issu du rebadging) est risqué — jusqu'à des dizaines de marques sur un même
    préfixe — donc EXCLU par défaut du fuzzy (configurable).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple

# ── Constantes par défaut (surchargeables via le constructeur) ──────────────
FUZZY_THRESHOLD = 0.90
ALLOW_NUMERIC_FUZZY_BY_DEFAULT = False
PREFIX_CONSENSUS_BY_DEFAULT = True
ENFORCE_SHAPE_BY_DEFAULT = True

# Palier C — consensus de préfixe : une famille de préfixe dominée à >= ratio par
# une seule (type, marque) sur >= N appareils est considérée mono-marque fiable.
# Longueurs de préfixe testées, de la plus spécifique à la plus large : on tente
# d'abord 4 car. ; si rien (famille trop éparse à 4), on retombe sur 3 car. Le
# garde-fou de dominance (≥ ratio) protège contre un préfixe court multi-marques.
_CONSENSUS_PREFIX_LENS = (4, 3)
_CONSENSUS_MIN_GROUP = 3     # nb minimal d'appareils complets partageant le préfixe
_CONSENSUS_MIN_RATIO = 0.90  # part minimale de la marque dominante
_CONSENSUS_MAX_SCORE = 0.85  # score plafond (consensus < quasi-exact/fuzzy fort)

# Suffixe de variante : clef de build de 1 à 3 caractères alphanumériques en fin
# de référence, sous deux formes équivalentes du domaine électroménager :
#   - « /XX » : codes numériques (/01, /58) ET alphanumériques (/C4, /IX, /G) ;
#   - « (XX) » : clef parenthésée des marques du groupe BSH (Bosch, Siemens, Neff,
#     Constructa, Balay, Gaggenau, Junker, Viva, Blaupunkt), p.ex. 3EMN378B(00) où
#     la ref technique = ref commerciale + clef. Retirer cette clef permet au
#     Palier A de reconnaître 3EMN378B(00) ≡ 3EMN378B (même appareil).
# L'ambiguïté éventuelle de regroupement retombe toujours sur une validation
# humaine (jamais d'application auto).
_SUFFIX_VARIANT_RE = re.compile(
    r'^(?P<base>.+?)(?:/(?P<s_slash>[A-Za-z0-9]{1,3})|\((?P<s_paren>[A-Za-z0-9]{1,3})\))$'
)
_ALPHA_PREFIX_RE = re.compile(r'^[A-Za-z]{3}')
_NUMERIC_PREFIX_RE = re.compile(r'^\d{3}')

# Longueur du préfixe servant au « bucketing » (pré-filtre de performance).
_PREFIX_LEN = 3


def strip_variant_suffix(ref: str) -> str:
    """Retire une clef de variante de fin de référence (1 à 3 car. alphanumériques),
    sous forme « /XX » ou « (XX) ». Idempotent.

    Ex: 'SMU6ZCS10S/58' -> 'SMU6ZCS10S' ; 'HE517BBS4/C4' -> 'HE517BBS4' ;
        '3EMN378B(00)' -> '3EMN378B' (clef BSH parenthésée) ;
        'WAQ283' -> 'WAQ283' (inchangé) ; 'AWO/C6304' -> 'AWO/C6304' (suffixe > 3).
    """
    ref = (ref or '').strip()
    m = _SUFFIX_VARIANT_RE.match(ref)
    return m.group('base') if m else ref


def within_one_edit(a: str, b: str) -> bool:
    """True si a et b sont à une distance d'édition <= 1 (1 substitution, 1
    insertion ou 1 suppression). Capte les variantes à un seul caractère que le
    ratio difflib rejette sur les références courtes (ex. 'CH3M61C53' vs
    'CH3M61153' = ratio 0,889 mais 1 seule substitution)."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    # Longueurs différant de 1 : vérifier qu'une seule suppression rend a == b.
    if la > lb:
        a, b = b, a  # a = la plus courte
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def detect_prefix_kind(ref: str) -> str:
    """Retourne 'alpha' si la ref commence par >=3 lettres, 'numeric' si elle
    commence par >=3 chiffres, 'other' sinon (ref trop courte, mixte d'emblée…)."""
    ref = (ref or '').strip()
    if _ALPHA_PREFIX_RE.match(ref):
        return 'alpha'
    if _NUMERIC_PREFIX_RE.match(ref):
        return 'numeric'
    return 'other'


def reference_shape_signature(ref: str) -> str:
    """Signature de structure d'une référence : la séquence des suites de
    caractères, chacune décrite par sa nature (L=lettres, D=chiffres) ET sa
    longueur, après retrait de la clef de variante. Les séparateurs (espace,
    tiret, etc.) sont notés 'S' sans longueur (1 ou plusieurs espaces = même
    séparation).

    La longueur des suites est indispensable : sans elle, 'HMG200X' (HMG+200+X)
    et 'HMG730BGB' (HMG+730+BGB) auraient la même forme grossière « L D L »,
    alors qu'ils appartiennent à deux systèmes de nommage distincts.

    Sert à distinguer deux *systèmes de nommage* qui ne partagent qu'un préfixe
    de lettres mais ont des formats incompatibles :
        'HMG 280 X'          -> 'L3SD3SL1'    (bloc commercial espacé)
        'HMG200X'            -> 'L3D3L1'       (bloc commercial contigu, X final)
        'HMG636BS1'          -> 'L3D3L2D1'     (bloc technique BSH)
        'HMG730BGB'          -> 'L3D3L3'       (micro-ondes Bosch)
        'HMFvh 5501-20A 111' -> 'L5SD4SD2L1SD3' (réf Liebherr)
    Deux références de structures différentes ne peuvent pas appartenir au même
    système de référence : on n'autorise donc pas le consensus de marque (Palier C)
    entre elles. C'est exactement ce qui évite de proposer « Bosch » pour
    'HMG 280 X' ou 'HMG200X' (coïncidences sur 3 lettres de tête).
    """
    base = strip_variant_suffix(ref)
    sig: List[str] = []
    run_cls = ''
    run_len = 0

    def _flush():
        if run_cls == 'S':
            sig.append('S')
        elif run_cls:
            sig.append(f'{run_cls}{run_len}')

    for ch in base:
        if ch.isalpha():
            cls = 'L'
        elif ch.isdigit():
            cls = 'D'
        else:
            cls = 'S'
        if cls == run_cls:
            run_len += 1
        else:
            _flush()
            run_cls = cls
            run_len = 1
    _flush()
    return ''.join(sig)


# Palier « type de la pièce importée » : candidat Type seul (marque vide), calculé
# par l'import à partir des appareils déjà rattachés à la pièce — pas une similarité
# de référence. 'ref' porte la ou les références de pièce, 'score' la part du type.
TIER_TYPE_PIECE = 'P_type_piece'


def est_type_piece(candidat: dict) -> bool:
    return (candidat or {}).get('confidence_tier') == TIER_TYPE_PIECE


def candidat_type_piece(type_piece: str, refs_pieces: List[str], part: float,
                        nb_appareils: int) -> dict:
    """Candidat au même format que SimilarityCandidate.to_dict()."""
    return {
        'ref': ", ".join(refs_pieces),
        'type': type_piece,
        'manufacturer': '',
        'score': part,
        'source': 'piece',
        'confidence_tier': TIER_TYPE_PIECE,
        'db_id': None,
        'nb_appareils': nb_appareils,
    }


def type_majoritaire(compte_par_type: Dict[str, int], part_min: float,
                     appareils_min: int) -> Optional[Tuple[str, float, int]]:
    """(type, part, nb appareils) si un type domine assez, sinon None."""
    total = sum(compte_par_type.values())
    if total < appareils_min or not compte_par_type:
        return None
    type_top, n = max(compte_par_type.items(), key=lambda kv: (kv[1], kv[0]))
    part = n / total
    return (type_top, part, total) if part >= part_min else None


def decrire_candidat(candidat: dict) -> str:
    """Libellé d'un candidat pour les listes (fenêtre Cmd+D)."""
    if est_type_piece(candidat):
        return (f"{candidat.get('type', '')}  (type de la pièce {candidat.get('ref', '')}, "
                f"{candidat.get('score', 0):.0%})")
    return (f"{candidat.get('type', '')} / {candidat.get('manufacturer', '')}  "
            f"(score {candidat.get('score', 0):.0%}, réf. {candidat.get('ref', '')})")


def provenance_candidat(candidat: dict) -> str:
    """Texte de provenance pour l'historique (« source : … »)."""
    if candidat.get('provenance'):
        # Écriture qui n'est pas une suggestion (correction d'un auto-complété)
        return candidat['provenance']
    if est_type_piece(candidat):
        return f"type de la pièce {candidat.get('ref', '')} ({candidat.get('score', 0):.0%})"
    return f"suggestion réf. {candidat.get('ref', '')} (score {candidat.get('score', 0):.0%})"


def infobulle_candidat(candidat: dict) -> str:
    """Info-bulle des cases Type/Marque en attente de validation."""
    if est_type_piece(candidat):
        return (f"Suggestion : {candidat.get('type', '')} — type de "
                f"{candidat.get('score', 0):.0%} des {candidat.get('nb_appareils', 0)} appareils "
                f"de la pièce {candidat.get('ref', '')} — clic pour voir les candidats")
    return (f"Suggestion : {candidat.get('type', '')} / {candidat.get('manufacturer', '')} "
            f"(score {candidat.get('score', 0):.0%}) — clic pour voir les candidats")


@dataclass(frozen=True)
class SimilarityCandidate:
    """Un candidat de suggestion. Immuable, sérialisable via to_dict()."""
    ref: str                  # référence (casse d'origine) de l'appareil candidat trouvé
    type: str
    manufacturer: str
    score: float               # 0.0 – 1.0
    source: str                 # 'ref_modele' | 'commercial_ref' (champ du candidat qui a matché)
    confidence_tier: str        # 'A_suffix_variant' | 'B_fuzzy_alpha' | 'B_fuzzy_numeric'
    db_id: int                  # id de l'appareil candidat en base

    def to_dict(self) -> dict:
        return {
            'ref': self.ref,
            'type': self.type,
            'manufacturer': self.manufacturer,
            'score': round(self.score, 4),
            'source': self.source,
            'confidence_tier': self.confidence_tier,
            'db_id': self.db_id,
        }


@dataclass
class ReferenceIndex:
    """Index préconstruit interrogé par find_candidates.

    NOTE d'implémentation : le plan d'origine typait l'index comme un simple
    Dict[str, List[dict]]. On utilise ici une petite structure dédiée pour
    porter AUSSI l'index secondaire par préfixe — indispensable à la
    performance (cf. build_reference_index). L'appelant n'a pas à connaître ce
    détail : il passe l'objet retourné par build_reference_index tel quel.

    - by_ref : clé = référence en minuscules (formes brute ET sans suffixe),
      valeur = liste d'entrées {db_id, type, manufacturer, matched_ref, source_field}.
    - by_prefix : clé = préfixe de 3 caractères (minuscules), valeur = liste des
      clés `by_ref` BRUTES partageant ce préfixe (sert au pré-filtre du Palier B).
    """
    by_ref: Dict[str, List[dict]] = field(default_factory=dict)
    by_prefix: Dict[str, List[str]] = field(default_factory=dict)


class ReferenceSimilarityService:
    """Service de scoring pur — aucune écriture, aucune dépendance Qt."""

    def __init__(self, allow_numeric_fuzzy: bool = ALLOW_NUMERIC_FUZZY_BY_DEFAULT,
                 fuzzy_threshold: float = FUZZY_THRESHOLD,
                 enable_prefix_consensus: bool = PREFIX_CONSENSUS_BY_DEFAULT,
                 enforce_shape_compatibility: bool = ENFORCE_SHAPE_BY_DEFAULT):
        self.allow_numeric_fuzzy = allow_numeric_fuzzy
        self.fuzzy_threshold = fuzzy_threshold
        self.enable_prefix_consensus = enable_prefix_consensus
        # Garde de compatibilité de structure (cf. reference_shape_signature) :
        # le consensus de préfixe (Palier C) ne regroupe que des références du même
        # système de nommage. Désactivable pour rollback (ZERO REGRESSION).
        self.enforce_shape_compatibility = enforce_shape_compatibility

    # ── Construction de l'index (une seule fois par session) ────────────────
    @staticmethod
    def build_reference_index(rows: Iterable[Tuple]) -> ReferenceIndex:
        """Construit l'index à partir de lignes (db_id, ref_modele,
        commercial_ref, type, manufacturer).

        - Indexe par ref_modele.lower() ET commercial_ref.lower(), plus la
          version sans suffixe /NN de chacune (pour matcher le Palier A dans les
          deux sens : ref source avec ou sans suffixe).
        - Ne garde que les lignes où type OU manufacturer est non vide
          (symétrique au filtre de _build_autocomplete_cache).
        - Remplit l'index secondaire by_prefix (clés brutes uniquement).
        """
        index = ReferenceIndex()

        for row in rows:
            if row is None or len(row) < 5:
                continue
            db_id, ref_modele, commercial_ref, device_type, manufacturer = row[:5]

            device_type = (device_type or '').strip()
            manufacturer = (manufacturer or '').strip()
            # Une entrée n'a d'intérêt que si elle apporte Type et/ou Marque.
            if not device_type and not manufacturer:
                continue

            for raw_ref, source_field in (
                ((ref_modele or '').strip(), 'ref_modele'),
                ((commercial_ref or '').strip(), 'commercial_ref'),
            ):
                if not raw_ref:
                    continue

                raw_key = raw_ref.lower()
                base_key = strip_variant_suffix(raw_ref).lower()

                entry = {
                    'db_id': db_id,
                    'type': device_type,
                    'manufacturer': manufacturer,
                    'matched_ref': raw_ref,        # casse d'origine, pour l'affichage
                    'source_field': source_field,
                }

                # Indexation par clé brute + clé sans suffixe (peut être identique).
                for key in {raw_key, base_key}:
                    index.by_ref.setdefault(key, []).append(entry)

                # Index secondaire de préfixe : clé brute uniquement.
                if len(raw_key) >= _PREFIX_LEN:
                    prefix = raw_key[:_PREFIX_LEN]
                    index.by_prefix.setdefault(prefix, []).append(raw_key)

        return index

    # ── Recherche de candidats ──────────────────────────────────────────────
    def find_candidates(
        self,
        ref_modele: str,
        commercial_ref: str,
        reference_index: ReferenceIndex,
        exclude_db_id: Optional[int] = None,
        max_candidates: int = 5,
    ) -> List[SimilarityCandidate]:
        """Calcule les candidats (Palier A puis B) pour les références fournies.

        Dédupliqué par couple (type, manufacturer) — le meilleur score gagne —,
        trié par score décroissant, tronqué à max_candidates.
        """
        if reference_index is None:
            return []

        results: List[SimilarityCandidate] = []
        for qref in (ref_modele, commercial_ref):
            if qref and qref.strip():
                results.extend(self._match_one_query_ref(qref, reference_index, exclude_db_id))

        # Déduplication par (type, marque) en gardant le meilleur score.
        best_by_pair: Dict[Tuple[str, str], SimilarityCandidate] = {}
        for cand in results:
            pair = (cand.type.lower(), cand.manufacturer.lower())
            current = best_by_pair.get(pair)
            if current is None or cand.score > current.score:
                best_by_pair[pair] = cand

        ordered = sorted(best_by_pair.values(), key=lambda c: c.score, reverse=True)
        return ordered[:max_candidates]

    def _match_one_query_ref(self, qref: str, index: ReferenceIndex,
                             exclude_db_id: Optional[int]) -> List[SimilarityCandidate]:
        """Candidats Palier A puis Palier B pour UNE référence interrogée."""
        out: List[SimilarityCandidate] = []
        qref_l = qref.strip().lower()
        if not qref_l:
            return out
        qbase = strip_variant_suffix(qref).strip().lower()

        # ── Palier A : correspondance sur la base (suffixe /NN ignoré) ───────
        # L'index contient les clés « base » de tous les appareils, donc une
        # seule recherche sur qbase couvre les deux sens (source avec/sans suffixe).
        for entry in index.by_ref.get(qbase, []):
            if exclude_db_id is not None and entry['db_id'] == exclude_db_id:
                continue
            out.append(SimilarityCandidate(
                ref=entry['matched_ref'],
                type=entry['type'],
                manufacturer=entry['manufacturer'],
                score=1.0,
                source=entry['source_field'],
                confidence_tier='A_suffix_variant',
                db_id=entry['db_id'],
            ))

        # ── Palier B : fuzzy sur les références du même bucket de préfixe ────
        prefix_kind = detect_prefix_kind(qref)
        # Préfixe purement numérique exclu du fuzzy (risque inter-marques élevé),
        # MAIS le Palier C (consensus) reste applicable — il s'auto-protège.
        do_fuzzy = (len(qref_l) >= _PREFIX_LEN
                    and not (prefix_kind == 'numeric' and not self.allow_numeric_fuzzy))
        if do_fuzzy:
            b_tier = 'B_fuzzy_numeric' if prefix_kind == 'numeric' else 'B_fuzzy_alpha'
            prefix = qref_l[:_PREFIX_LEN]
            seen_keys = set()
            for cand_key in index.by_prefix.get(prefix, []):
                if cand_key in seen_keys:
                    continue
                seen_keys.add(cand_key)
                # Le Palier A a déjà couvert l'identité exacte / la base.
                if cand_key == qref_l or cand_key == qbase:
                    continue
                ratio = SequenceMatcher(None, qref_l, cand_key).ratio()
                # Accepter si suffisamment proche OU à une seule édition près (variantes
                # à 1 caractère sur réfs courtes, sous le seuil ratio mais évidentes).
                if ratio < self.fuzzy_threshold and not within_one_edit(qref_l, cand_key):
                    continue
                for entry in index.by_ref.get(cand_key, []):
                    if exclude_db_id is not None and entry['db_id'] == exclude_db_id:
                        continue
                    out.append(SimilarityCandidate(
                        ref=entry['matched_ref'],
                        type=entry['type'],
                        manufacturer=entry['manufacturer'],
                        score=ratio,
                        source=entry['source_field'],
                        confidence_tier=b_tier,
                        db_id=entry['db_id'],
                    ))

        # ── Palier C : consensus de préfixe (dernier recours, si rien trouvé) ──
        # Même garde numérique que le Palier B : un numéro de catalogue n'encode
        # pas la marque (la dominance y serait un artefact d'inventaire, pas un
        # signal) — on n'applique le consensus qu'aux préfixes contenant des lettres.
        consensus_allowed = not (prefix_kind == 'numeric' and not self.allow_numeric_fuzzy)
        if not out and self.enable_prefix_consensus and consensus_allowed:
            consensus = self._prefix_consensus(qref_l, index, exclude_db_id)
            if consensus is not None:
                out.append(consensus)

        return out

    def _prefix_consensus(self, qref_l: str, index: ReferenceIndex,
                          exclude_db_id: Optional[int]) -> Optional[SimilarityCandidate]:
        """Palier C : si la famille de préfixe de la référence est dominée à >= ratio
        par une seule (type, marque) sur >= N appareils complets, la proposer.

        On teste du préfixe le plus spécifique au plus large (4 car. puis 3) : la
        première longueur qui produit un consensus dominant gagne. Le garde-fou de
        dominance protège un préfixe court partagé par plusieurs marques (rebadging)."""
        for prefix_len in _CONSENSUS_PREFIX_LENS:
            result = self._consensus_at(qref_l, index, exclude_db_id, prefix_len)
            if result is not None:
                return result
        return None

    def _consensus_at(self, qref_l: str, index: ReferenceIndex,
                      exclude_db_id: Optional[int],
                      prefix_len: int) -> Optional[SimilarityCandidate]:
        """Consensus pour UNE longueur de préfixe donnée (cf. _prefix_consensus)."""
        if len(qref_l) < prefix_len:
            return None
        prefix = qref_l[:prefix_len]
        bucket3 = qref_l[:_PREFIX_LEN]
        # La garde de structure ne vise que la collision de *préfixes de lettres*
        # (deux systèmes de nommage alpha partageant 3 lettres de tête). Sur un
        # préfixe purement numérique, le consensus est déjà gouverné par le seul
        # garde-fou numérique (allow_numeric_fuzzy) et les longueurs y varient
        # légitimement — on n'y applique donc pas la signature de forme.
        apply_shape = (self.enforce_shape_compatibility
                       and detect_prefix_kind(qref_l) != 'numeric')
        query_sig = reference_shape_signature(qref_l) if apply_shape else None

        # Collecter une entrée par db_id distinct (évite le double comptage
        # ref_modele/commercial_ref/base d'un même appareil).
        seen = {}   # db_id -> (type, manufacturer, matched_ref, source_field)
        processed_keys = set()
        for cand_key in index.by_prefix.get(bucket3, []):
            if cand_key in processed_keys or not cand_key.startswith(prefix):
                continue
            processed_keys.add(cand_key)
            # Garde de structure : ne regrouper que des références du même système
            # de nommage (évite « HMG 280 X » -> Bosch via le bloc « HMG636BS1 »).
            if query_sig is not None and reference_shape_signature(cand_key) != query_sig:
                continue
            for entry in index.by_ref.get(cand_key, []):
                if exclude_db_id is not None and entry['db_id'] == exclude_db_id:
                    continue
                seen[entry['db_id']] = (entry['type'], entry['manufacturer'],
                                        entry['matched_ref'], entry['source_field'])

        if len(seen) < _CONSENSUS_MIN_GROUP:
            return None

        counts = Counter((t.lower(), m.lower()) for (t, m, _, _) in seen.values())
        top_pair, top_n = counts.most_common(1)[0]
        if top_n / len(seen) < _CONSENSUS_MIN_RATIO:
            return None   # pas de marque dominante → ambigu, on ne propose rien

        score = round(min(_CONSENSUS_MAX_SCORE, top_n / len(seen)), 4)
        for db_id, (t, m, ref, src) in seen.items():
            if (t.lower(), m.lower()) == top_pair:
                return SimilarityCandidate(
                    ref=ref, type=t, manufacturer=m, score=score,
                    source=src, confidence_tier='C_prefix_consensus', db_id=db_id,
                )
        return None
