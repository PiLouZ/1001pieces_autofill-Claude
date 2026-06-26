"""
Tests du service de scoring de similarité de référence.

Pur Python, aucune dépendance Qt ni base de données : fixtures en mémoire.
Couvre les deux paliers de confiance (A quasi-exact, B fuzzy), l'exclusion
des préfixes numériques, la déduplication, le tri et la robustesse.
"""

import time

import pytest

from src.services.reference_similarity_service import (
    ReferenceSimilarityService,
    SimilarityCandidate,
    strip_variant_suffix,
    detect_prefix_kind,
    reference_shape_signature,
)


# ── Fonctions utilitaires ───────────────────────────────────────────────────
class TestStripVariantSuffix:
    def test_retire_suffixe_numerique(self):
        assert strip_variant_suffix("SMU6ZCS10S/58") == "SMU6ZCS10S"
        assert strip_variant_suffix("WAQ284A2NL/06") == "WAQ284A2NL"

    def test_retire_suffixe_alphanumerique(self):
        # Codes de build alphanumériques (/C4, /IX, /G) — domaine électroménager
        assert strip_variant_suffix("HE517BBS4/C4") == "HE517BBS4"
        assert strip_variant_suffix("AKZ212/IX") == "AKZ212"
        assert strip_variant_suffix("AFG372/G") == "AFG372"

    def test_inchangee_si_pas_de_suffixe(self):
        assert strip_variant_suffix("WAQ283") == "WAQ283"
        assert strip_variant_suffix("123456") == "123456"

    def test_suffixe_trop_long_non_retire(self):
        # > 3 caractères après le / = pas un suffixe de variante reconnu
        assert strip_variant_suffix("ABC/1234") == "ABC/1234"
        assert strip_variant_suffix("AWO/C6304") == "AWO/C6304"

    def test_retire_clef_parenthesee_bsh(self):
        # Clef parenthésée (XX) du groupe BSH : ref technique = ref commerciale + clef.
        assert strip_variant_suffix("3EMN378B(00)") == "3EMN378B"
        assert strip_variant_suffix("BA036100(00)") == "BA036100"
        assert strip_variant_suffix("5Z11CR10X0(A1)") == "5Z11CR10X0"

    def test_clef_parenthesee_trop_longue_non_retiree(self):
        # > 3 caractères entre parenthèses = pas une clef de variante.
        assert strip_variant_suffix("ABC(1234)") == "ABC(1234)"

    def test_chaine_vide_ou_none(self):
        assert strip_variant_suffix("") == ""
        assert strip_variant_suffix(None) == ""

    def test_idempotent(self):
        once = strip_variant_suffix("SMU6ZCS10S/58")
        assert strip_variant_suffix(once) == once


class TestDetectPrefixKind:
    def test_alpha(self):
        assert detect_prefix_kind("WAQ283") == "alpha"
        assert detect_prefix_kind("SMU6ZCS10S") == "alpha"

    def test_numeric(self):
        assert detect_prefix_kind("123456") == "numeric"
        assert detect_prefix_kind("905112620") == "numeric"

    def test_other(self):
        assert detect_prefix_kind("A1") == "other"     # trop court
        assert detect_prefix_kind("A1B2C3") == "other"  # mixte d'emblée
        assert detect_prefix_kind("") == "other"


class TestReferenceShapeSignature:
    def test_bloc_espace_vs_bloc_contigu(self):
        # Le cœur du correctif : 'HMG 280 X' et 'HMG636BS1' partagent 3 lettres
        # mais sont deux systèmes de nommage distincts → signatures différentes.
        assert reference_shape_signature("HMG 280 X") == "L3SD3SL1"
        assert reference_shape_signature("HMG636BS1") == "L3D3L2D1"
        assert reference_shape_signature("HMG 280 X") != reference_shape_signature("HMG636BS1")

    def test_longueur_de_suite_discrimine_blocs_contigus(self):
        # Sans la longueur des suites, 'HMG200X' et 'HMG730BGB' seraient confondus
        # (tous deux « L D L »). Avec la longueur, ils diffèrent → pas de consensus.
        assert reference_shape_signature("HMG200X") == "L3D3L1"
        assert reference_shape_signature("HMG730BGB") == "L3D3L3"
        assert reference_shape_signature("HMG200X") != reference_shape_signature("HMG730BGB")

    def test_ref_liebherr_distincte(self):
        # 'HMF 250 X' ≠ 'HMFvh 5501-20A 111' (Liebherr) → pas le même système.
        assert reference_shape_signature("HMF 250 X") == "L3SD3SL1"
        assert reference_shape_signature("HMF 250 X") != reference_shape_signature("HMFvh 5501-20A 111")

    def test_clef_variante_ignoree(self):
        # La clef /NN ou (NN) ne fait pas partie de la structure.
        assert reference_shape_signature("HMG636BS1/01") == reference_shape_signature("HMG636BS1")
        assert reference_shape_signature("3EMN378B(00)") == reference_shape_signature("3EMN378B")

    def test_variantes_meme_structure(self):
        # Deux références de la même famille espacée partagent leur signature.
        assert reference_shape_signature("HMG 280 X") == reference_shape_signature("HMG 281 X")


# ── Helpers de construction d'index ──────────────────────────────────────────
def _index(rows):
    return ReferenceSimilarityService.build_reference_index(rows)


# ── Palier A : quasi-exact (suffixe /NN ignoré) ──────────────────────────────
class TestPalierA:
    def test_suffixe_source_vers_base(self):
        # DB contient une variante /58 ; la ligne importée a /82 -> même base.
        rows = [(1, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S/82", "", _index(rows))
        assert len(cands) == 1
        assert cands[0].score == 1.0
        assert cands[0].confidence_tier == "A_suffix_variant"
        assert cands[0].manufacturer == "Bosch"

    def test_sans_suffixe_trouve_variante(self):
        # Sens inverse : la ligne importée n'a pas de suffixe, la DB en a un.
        rows = [(1, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S", "", _index(rows))
        assert len(cands) == 1
        assert cands[0].confidence_tier == "A_suffix_variant"

    def test_suffixe_alphanumerique_match(self):
        # Scénario réel : import 'HE517BBS4/C4' (sans commercial_ref) doit matcher
        # un appareil existant 'HE517BBS4/01' via la base partagée 'HE517BBS4'.
        rows = [(1, "HE517BBS4/01", "", "Four", "Siemens")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("HE517BBS4/C4", "", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Siemens"
        assert cands[0].confidence_tier == "A_suffix_variant"

    def test_deux_variantes_marques_differentes(self):
        # Rebadging : même base, marques différentes -> deux candidats distincts.
        rows = [
            (1, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch"),
            (2, "SMU6ZCS10S/82", "", "Lave-vaisselle", "Siemens"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S/99", "", _index(rows))
        marques = {c.manufacturer for c in cands}
        assert marques == {"Bosch", "Siemens"}
        assert all(c.score == 1.0 for c in cands)


# ── Palier B : fuzzy ─────────────────────────────────────────────────────────
class TestPalierBAlpha:
    def test_fuzzy_alpha_accepte(self):
        rows = [(1, "SMU6ZCS10SAB", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        # 12 caractères, 1 seul différent -> ratio ~0.917 >= 0.90
        cands = svc.find_candidates("SMU6ZCS10SAC", "", _index(rows))
        assert len(cands) == 1
        assert cands[0].confidence_tier == "B_fuzzy_alpha"
        assert cands[0].score >= 0.90

    def test_fuzzy_alpha_sous_seuil_rejete(self):
        rows = [(1, "SMUXXXXXXX", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        # Trop différent -> en dessous du seuil
        cands = svc.find_candidates("SMU1234567", "", _index(rows))
        assert cands == []


class TestPalierBNumeric:
    def _rows(self):
        return [(1, "1234567890", "", "Four", "Brandt")]

    def test_numerique_exclu_par_defaut(self):
        svc = ReferenceSimilarityService()  # allow_numeric_fuzzy=False par défaut
        cands = svc.find_candidates("1234567891", "", _index(self._rows()))
        assert cands == []

    def test_numerique_accepte_si_active(self):
        svc = ReferenceSimilarityService(allow_numeric_fuzzy=True)
        cands = svc.find_candidates("1234567891", "", _index(self._rows()))
        assert len(cands) == 1
        assert cands[0].confidence_tier == "B_fuzzy_numeric"


# ── Concurrence, déduplication, tri ──────────────────────────────────────────
class TestConcurrenceEtDedup:
    def test_plusieurs_candidats_tries_par_score(self):
        rows = [
            (1, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch"),    # Palier A -> 1.0
            (2, "SMU6ZCS10SXY", "", "Lave-vaisselle", "Siemens"),    # Palier B -> <1.0
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S", "", _index(rows))
        assert len(cands) == 2
        # Tri décroissant : le quasi-exact (1.0) d'abord.
        assert cands[0].score >= cands[1].score
        assert cands[0].manufacturer == "Bosch"

    def test_dedup_meme_couple_type_marque(self):
        # Deux références différentes -> même Type/Marque : un seul candidat gardé.
        rows = [
            (1, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch"),
            (2, "SMU6ZCS10S/82", "", "Lave-vaisselle", "Bosch"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S/99", "", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Bosch"

    def test_max_candidates_respecte(self):
        rows = [
            (i, f"SMU6ZCS10S/{i:02d}", "", "Lave-vaisselle", f"Marque{i}")
            for i in range(1, 11)
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S", "", _index(rows), max_candidates=3)
        assert len(cands) == 3


# ── Robustesse ───────────────────────────────────────────────────────────────
class TestRobustesse:
    def test_exclude_db_id_respecte(self):
        rows = [(42, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S/82", "", _index(rows), exclude_db_id=42)
        assert cands == []

    def test_references_vides(self):
        rows = [(1, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        assert svc.find_candidates("", "", _index(rows)) == []
        assert svc.find_candidates(None, None, _index(rows)) == []

    def test_index_vide(self):
        svc = ReferenceSimilarityService()
        assert svc.find_candidates("SMU6ZCS10S", "", _index([])) == []

    def test_entrees_sans_type_ni_marque_ignorees(self):
        rows = [(1, "SMU6ZCS10S/58", "", "", "")]  # ni type ni marque
        svc = ReferenceSimilarityService()
        assert svc.find_candidates("SMU6ZCS10S/82", "", _index(rows)) == []

    def test_match_sur_commercial_ref(self):
        rows = [(1, "", "WGA244BGHK", "Lave-linge", "Bosch")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("", "WGA244BGHK", _index(rows))
        assert len(cands) == 1
        assert cands[0].source == "commercial_ref"

    def test_lignes_mal_formees_ignorees(self):
        rows = [None, (1,), (2, "X"), (3, "SMU6ZCS10S/58", "", "Lave-vaisselle", "Bosch")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("SMU6ZCS10S/82", "", _index(rows))
        assert len(cands) == 1


# ── Performance : pas de balayage O(N) par appel ─────────────────────────────
class TestPerformance:
    def test_index_volumineux_reste_rapide(self):
        # 10 000 entrées synthétiques sur des préfixes variés.
        rows = []
        for i in range(10000):
            prefix = f"{chr(65 + i % 26)}{chr(65 + (i // 26) % 26)}{chr(65 + (i // 676) % 26)}"
            rows.append((i, f"{prefix}{i:06d}", "", "Type", f"Marque{i % 50}"))

        t0 = time.perf_counter()
        index = ReferenceSimilarityService.build_reference_index(rows)
        build_time = time.perf_counter() - t0

        svc = ReferenceSimilarityService()
        t0 = time.perf_counter()
        svc.find_candidates("ABA000001", "", index)
        query_time = time.perf_counter() - t0

        # Grâce au bucketing par préfixe, un appel reste très en dessous de 0.5s.
        assert query_time < 0.5, f"find_candidates trop lent: {query_time:.3f}s"
        assert build_time < 5.0, f"build_reference_index trop lent: {build_time:.3f}s"


def test_to_dict_contrat():
    cand = SimilarityCandidate(
        ref="SMU6ZCS10S/58", type="Lave-vaisselle", manufacturer="Bosch",
        score=0.916666, source="ref_modele", confidence_tier="B_fuzzy_alpha", db_id=1,
    )
    d = cand.to_dict()
    assert d == {
        'ref': "SMU6ZCS10S/58",
        'type': "Lave-vaisselle",
        'manufacturer': "Bosch",
        'score': 0.9167,
        'source': "ref_modele",
        'confidence_tier': "B_fuzzy_alpha",
        'db_id': 1,
    }


class TestWithinOneEdit:
    def test_substitution(self):
        from src.services.reference_similarity_service import within_one_edit
        assert within_one_edit("ch3m61c53", "ch3m61153") is True   # 1 substitution
        assert within_one_edit("abc", "abc") is True               # identique
        assert within_one_edit("ch3m61c53", "ch3m61199") is False  # 2 diff

    def test_insertion_suppression(self):
        from src.services.reference_similarity_service import within_one_edit
        assert within_one_edit("abc123", "abc1234") is True   # 1 insertion
        assert within_one_edit("abc1234", "abc123") is True   # 1 suppression
        assert within_one_edit("abc", "abcde") is False       # 2 de différence

    def test_palier_b_capte_variante_1_caractere(self):
        # CH3M61C53 doit matcher CH3M61153 (Constructa) malgré ratio 0.889 < 0.90
        rows = [(1, "CH3M61153/95", "CH3M61153", "Four", "Constructa")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("CH3M61C53/01", "CH3M61C53", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Constructa"


class TestPalierCConsensus:
    def test_consensus_mono_marque(self):
        # Famille 3HB58* mono-marque (Balay) → suggère Balay même si ref éloignée (3 diff)
        rows = [(i, f"3HB5879N{i}", f"3HB5879N{i}", "Four", "Balay") for i in range(1, 6)]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("3HB5821N3", "3HB5821N3", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Balay"
        assert cands[0].confidence_tier == "C_prefix_consensus"

    def test_pas_de_consensus_si_multi_marques(self):
        # Préfixe partagé mais marques variées (pas de dominante) → rien
        rows = [
            (1, "ABCD111", "ABCD111", "Four", "MarqueA"),
            (2, "ABCD222", "ABCD222", "Four", "MarqueB"),
            (3, "ABCD333", "ABCD333", "Four", "MarqueC"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("ABCD999", "ABCD999", _index(rows))
        assert cands == []

    def test_consensus_ignore_si_groupe_trop_petit(self):
        # Moins de _CONSENSUS_MIN_GROUP appareils → pas de consensus fiable
        rows = [(1, "ZZZZ111", "ZZZZ111", "Four", "Balay")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("ZZZZ999", "ZZZZ999", _index(rows))
        assert cands == []

    def test_consensus_desactivable(self):
        rows = [(i, f"3HB5879N{i}", f"3HB5879N{i}", "Four", "Balay") for i in range(1, 6)]
        svc = ReferenceSimilarityService(enable_prefix_consensus=False)
        cands = svc.find_candidates("3HB5821N3", "3HB5821N3", _index(rows))
        assert cands == []

    def test_consensus_repli_3_car(self):
        # Préfixe 4 car. trop épars (aucun voisin sous 'ADXN'), mais 3 car. 'ADX'
        # dominé Brandt → repli sur 3 car. (Levier 2). Les refs sont assez éloignées
        # pour ne pas déclencher le Palier B fuzzy.
        rows = [
            (1, "ADXA111", "ADXA111", "Hotte", "Brandt"),
            (2, "ADXB222", "ADXB222", "Hotte", "Brandt"),
            (3, "ADXC333", "ADXC333", "Hotte", "Brandt"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("ADXN999", "ADXN999", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Brandt"
        assert cands[0].confidence_tier == "C_prefix_consensus"

    def test_consensus_4_car_prioritaire_sur_3_car(self):
        # Le 4 car. (plus spécifique) gagne quand il a son propre consensus.
        rows = [
            (1, "ADXN111", "ADXN111", "Hotte", "Bosch"),   # 'ADXN' → Bosch
            (2, "ADXN222", "ADXN222", "Hotte", "Bosch"),
            (3, "ADXN333", "ADXN333", "Hotte", "Bosch"),
            (4, "ADXZ444", "ADXZ444", "Hotte", "Brandt"),  # 'ADX' global plus mêlé
            (5, "ADXY555", "ADXY555", "Hotte", "Brandt"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("ADXN999", "ADXN999", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Bosch"   # le 4 car. 'ADXN' prime

    def test_pas_de_consensus_3_car_si_multi_marques(self):
        # 3 car. partagé par plusieurs marques (aucune dominante ≥ 90 %) → rien,
        # même en repli (le garde-fou de dominance protège le préfixe court).
        rows = [
            (1, "ADXA111", "ADXA111", "Hotte", "Brandt"),
            (2, "ADXB222", "ADXB222", "Hotte", "Bosch"),
            (3, "ADXC333", "ADXC333", "Hotte", "Faure"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("ADXN999", "ADXN999", _index(rows))
        assert cands == []


class TestPalierCShapeGate:
    """Garde de structure (signature de forme) sur le consensus de préfixe.

    Cas réels remontés par l'utilisateur : des références commerciales espacées
    ('HMG 280 X', 'HMF 250 X') étaient faussement rattachées à des familles de
    blocs contigus (Bosch 'HMG636BS1', Liebherr 'HMFvh...') sur la seule
    coïncidence des 3 lettres de tête.
    """

    def _bosch_hmg_family(self):
        # Famille Bosch en blocs contigus 'HMG636BS1' (préfixe 'hmg' dominé Bosch).
        return [(i, f"HMG636BS{i}/01", f"HMG636BS{i}", "Four", "Bosch")
                for i in range(1, 6)]

    def test_bloc_espace_n_est_pas_rattache_au_bloc_contigu(self):
        # 'HMG 280 X' (LSDSL) ne doit PAS être suggéré Bosch (HMG636BS1 = LDLD).
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("38900020", "HMG 280 X", _index(self._bosch_hmg_family()))
        assert cands == []

    def test_voisin_espace_legitime_conserve(self):
        # Si un appareil COMPLET de la même structure espacée existe, le consensus
        # doit le proposer (la garde n'élimine que les structures incompatibles).
        rows = [
            (1, "REF001", "HMG 280 X", "Four", "Brandt"),
            (2, "REF002", "HMG 281 X", "Four", "Brandt"),
            (3, "REF003", "HMG 282 X", "Four", "Brandt"),
        ]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("38900099", "HMG 285 X", _index(rows))
        # Toujours proposé (la garde n'élimine que les structures incompatibles) —
        # ici via le fuzzy de même structure (1 chiffre d'écart), tier B ou C.
        assert len(cands) == 1
        assert cands[0].manufacturer == "Brandt"
        assert cands[0].confidence_tier in ("B_fuzzy_alpha", "C_prefix_consensus")

    def test_desactivation_garde_restaure_ancien_comportement(self):
        # Avec la garde désactivée, l'ancien rattachement (faux positif) revient :
        # garantit que le correctif est bien la cause de la différence (et rollback).
        svc = ReferenceSimilarityService(enforce_shape_compatibility=False)
        cands = svc.find_candidates("38900020", "HMG 280 X", _index(self._bosch_hmg_family()))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Bosch"

    def test_garde_n_affecte_pas_familles_homogenes(self):
        # Non-régression : une famille de blocs contigus reste proposée pour une
        # requête de même structure.
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("HMG636XY9", "HMG636XY9", _index(self._bosch_hmg_family()))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Bosch"


class TestPalierANumericKeyBSH:
    def test_clef_parenthesee_match_commercial(self):
        # Scénario BSH réel : un appareil a ref_modele '3EMN378B(00)' et commercial
        # '3EMN378B'. Une ligne importée avec commercial '3EMN378B' doit matcher via
        # la base partagée '3EMN378B' (clef parenthésée retirée).
        rows = [(1, "3EMN378B(00)", "3EMN378B", "Four", "Balay")]
        svc = ReferenceSimilarityService()
        cands = svc.find_candidates("", "3EMN378B", _index(rows))
        assert len(cands) == 1
        assert cands[0].manufacturer == "Balay"
        assert cands[0].confidence_tier == "A_suffix_variant"


class TestPalierCNumericGuard:
    def test_consensus_exclu_sur_prefixe_numerique(self):
        # Préfixe purement numérique dominé par une marque → quand même exclu
        # (le numéro de catalogue n'encode pas la marque).
        rows = [(i, f"3104{i:05d}", f"3104{i:05d}", "Four", "Candy") for i in range(1, 8)]
        svc = ReferenceSimilarityService()  # allow_numeric_fuzzy=False par défaut
        cands = svc.find_candidates("3104999999", "3104999999", _index(rows))
        assert cands == []

    def test_consensus_numerique_si_active(self):
        rows = [(i, f"3104{i:05d}", f"3104{i:05d}", "Four", "Candy") for i in range(1, 8)]
        svc = ReferenceSimilarityService(allow_numeric_fuzzy=True)
        cands = svc.find_candidates("3104999999", "3104999999", _index(rows))
        assert len(cands) == 1
        assert cands[0].confidence_tier == "C_prefix_consensus"
