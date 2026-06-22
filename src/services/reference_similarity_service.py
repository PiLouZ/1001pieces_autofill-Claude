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

# Palier C — consensus de préfixe : une famille de préfixe dominée à >= ratio par
# une seule (type, marque) sur >= N appareils est considérée mono-marque fiable.
_CONSENSUS_PREFIX_LEN = 4    # longueur du préfixe testé pour le consensus
_CONSENSUS_MIN_GROUP = 3     # nb minimal d'appareils complets partageant le préfixe
_CONSENSUS_MIN_RATIO = 0.90  # part minimale de la marque dominante
_CONSENSUS_MAX_SCORE = 0.85  # score plafond (consensus < quasi-exact/fuzzy fort)

# Suffixe de variante : « /XX » (1 à 3 caractères alphanumériques) en fin de
# référence — couvre les codes de build numériques (/01, /58) ET alphanumériques
# (/C4, /IX, /G) du domaine électroménager. L'ambiguïté éventuelle de regroupement
# retombe toujours sur une validation humaine (jamais d'application auto).
_SUFFIX_VARIANT_RE = re.compile(r'^(?P<base>.+?)/(?P<suffix>[A-Za-z0-9]{1,3})$')
_ALPHA_PREFIX_RE = re.compile(r'^[A-Za-z]{3}')
_NUMERIC_PREFIX_RE = re.compile(r'^\d{3}')

# Longueur du préfixe servant au « bucketing » (pré-filtre de performance).
_PREFIX_LEN = 3


def strip_variant_suffix(ref: str) -> str:
    """Retire un suffixe /XX (1 à 3 caractères alphanumériques) de fin de
    référence. Idempotent.

    Ex: 'SMU6ZCS10S/58' -> 'SMU6ZCS10S' ; 'HE517BBS4/C4' -> 'HE517BBS4' ;
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
                 enable_prefix_consensus: bool = PREFIX_CONSENSUS_BY_DEFAULT):
        self.allow_numeric_fuzzy = allow_numeric_fuzzy
        self.fuzzy_threshold = fuzzy_threshold
        self.enable_prefix_consensus = enable_prefix_consensus

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
        """Palier C : si la famille de préfixe (4 car.) de la référence est dominée
        à >= ratio par une seule (type, marque) sur >= N appareils complets, la
        proposer. Sinon None (préfixe multi-marques = ambigu, ex. numériques rebadgés)."""
        if len(qref_l) < _CONSENSUS_PREFIX_LEN:
            return None
        prefix = qref_l[:_CONSENSUS_PREFIX_LEN]
        bucket3 = qref_l[:_PREFIX_LEN]

        # Collecter une entrée par db_id distinct (évite le double comptage
        # ref_modele/commercial_ref/base d'un même appareil).
        seen = {}   # db_id -> (type, manufacturer, matched_ref, source_field)
        processed_keys = set()
        for cand_key in index.by_prefix.get(bucket3, []):
            if cand_key in processed_keys or not cand_key.startswith(prefix):
                continue
            processed_keys.add(cand_key)
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
