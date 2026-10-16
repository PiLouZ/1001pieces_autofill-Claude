"""
Tests d'équivalence — les deux chemins d'import doivent produire le même résultat

`_process_data_import` (chemin standard, < 50 lignes) et `_process_data_import_batch`
(chemin batch, >= 50 lignes ou dry-run) implémentent le même contrat métier par deux
stratégies différentes : SQL immédiat d'un côté, cache mémoire + écriture différée de
l'autre. L'aiguillage se fait sur le volume, donc l'utilisateur ne choisit pas son chemin.

Rien n'affirmait jusqu'ici qu'ils devaient rester équivalents. Ils ont pourtant divergé
au moins trois fois — le code en porte les cicatrices en commentaires (« symétrique de la
collecte du chemin batch », « compter APRÈS parse pour cohérence avec le chemin batch »),
et la v3.66.1 a corrigé un bug de production né de cette dérive : un ré-import recréait
des appareils au lieu de les retrouver, le cas « une seule référence renseignée » étant
géré d'un côté et pas de l'autre.

Ces tests sont le garde-fou qui manquait : ils ne vérifient pas *ce que* font les deux
chemins, mais *qu'ils font la même chose*.
"""

import os
import tempfile
import pytest

from src.core.config import Config
from src.data.database_manager import DatabaseManager
from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType,
    LabelConfiguration, FileType,
)


REFERENCES = [("REF_TEST", "libelle")]


# ─── Harnais ─────────────────────────────────────────────────────────────────

def _config_import(**surcharges):
    fichier = ImportFile(path='/tmp/inexistant.csv', type=FileType.CSV,
                         suggested_reference='REF_TEST')
    params = dict(
        files=[fichier], import_type=ImportType.SINGLE_FILE,
        common_reference="REF_TEST", use_common_reference=True,
        label_config=LabelConfiguration(), individual_references={},
        individual_labels={}, csv_import_mode=2, has_headers=False,
    )
    params.update(surcharges)
    return ImportConfiguration(**params), fichier


def _etat_base(db_manager):
    """Photo de l'état observable de la base après import."""
    appareils = db_manager.execute_query(
        "SELECT type, manufacturer, ref_modele, commercial_ref "
        "FROM appareils ORDER BY 1, 2, 3, 4"
    ) or []
    associations = db_manager.execute_query(
        "SELECT COUNT(*) FROM piece_associations"
    )[0][0]
    # Trace des auto-complétions (v3.89.0) : désignée par les références, les id
    # pouvant différer d'un chemin à l'autre
    autocompletes = db_manager.execute_query(
        "SELECT a.ref_modele, a.commercial_ref, t.champ, t.valeur, t.source, t.accord, t.total "
        "FROM appareils_autocompletes t JOIN appareils a ON a.id = t.appareil_id "
        "ORDER BY 1, 2, 3"
    ) or []
    return {'appareils': [tuple(a) for a in appareils], 'associations': associations,
            'autocompletes': [tuple(t) for t in autocompletes]}


def _executer(chemin: str, lots, config_surcharges=None, preexistants=(), details=None):
    """Rejouer une séquence de lots dans l'un des deux chemins, sur une base neuve.

    `lots` est une liste de jeux de lignes : plusieurs lots partagent le même
    `seen_device_refs`, ce qui reproduit la déduplication INTER-fichiers.
    `preexistants` : appareils (type, fabricant, ref_modele, commercial_ref) déjà
    en base avant le 1ᵉʳ lot. `details`, si fourni, reçoit la trace des appareils
    existants complétés.
    Retourne (compteurs cumulés, état de la base, nb de candidats similarité).
    """
    chemin_db = tempfile.mktemp(suffix='.db')
    db_file_origine = Config.DB_FILE
    recherche_origine = Config.SEARCH_PIECES_ONLY
    Config.DB_FILE = chemin_db
    Config.SEARCH_PIECES_ONLY = False
    try:
        db_manager = DatabaseManager()
        if preexistants:
            conn = db_manager.get_connection()
            conn.executemany(
                "INSERT INTO appareils (type, manufacturer, ref_modele, commercial_ref, "
                "other_ref, notes, category) VALUES (?, ?, ?, ?, '', '', '')", preexistants)
            conn.commit()
        manager = ImportManager(db_manager=db_manager, parent_widget=None)
        manager._pending_similarity_candidates = []
        manager._imported_complete_for_similarity = []

        config, fichier = _config_import(**(config_surcharges or {}))
        vus = set()
        cumul = {}

        for lignes in lots:
            if chemin == 'standard':
                resultat = manager._process_data_import(
                    lignes, REFERENCES, config, fichier, vus
                )
            else:
                resultat = manager._process_data_import_batch(
                    lignes, REFERENCES, config, fichier, vus
                )
            for cle, valeur in resultat.items():
                cumul[cle] = cumul.get(cle, 0) + valeur

        etat = _etat_base(db_manager)
        candidats = len(manager._pending_similarity_candidates)
        if details is not None:
            details.extend(sorted(
                (tuple(sorted(t.items())) for t in
                 getattr(manager, '_completions_existants', {}).values())))
        db_manager.close()
        return cumul, etat, candidats
    finally:
        Config.DB_FILE = db_file_origine
        Config.SEARCH_PIECES_ONLY = recherche_origine
        if os.path.exists(chemin_db):
            os.remove(chemin_db)


def _assert_equivalents(lots, config_surcharges=None, preexistants=(), details=None):
    """Exiger l'égalité stricte des deux chemins sur les trois sorties observables
    (quatre avec `details` : la trace des appareils existants complétés)."""
    d_std, d_bat = [], []
    c_std, e_std, s_std = _executer('standard', lots, config_surcharges, preexistants, d_std)
    c_bat, e_bat, s_bat = _executer('batch', lots, config_surcharges, preexistants, d_bat)
    assert d_std == d_bat, (
        f"Complétions divergentes.\n  standard = {d_std}\n  batch    = {d_bat}"
    )
    if details is not None:
        details.extend(d_std)

    assert c_std == c_bat, (
        f"Compteurs divergents.\n  standard = {c_std}\n  batch    = {c_bat}"
    )
    assert e_std['appareils'] == e_bat['appareils'], (
        f"Appareils en base divergents.\n"
        f"  standard = {e_std['appareils']}\n  batch    = {e_bat['appareils']}"
    )
    assert e_std['associations'] == e_bat['associations'], (
        f"Nombre d'associations divergent : "
        f"standard={e_std['associations']} batch={e_bat['associations']}"
    )
    assert s_std == s_bat, (
        f"Candidats à la similarité divergents : standard={s_std} batch={s_bat}"
    )
    assert e_std['autocompletes'] == e_bat['autocompletes'], (
        f"Traces d'auto-complétion divergentes.\n"
        f"  standard = {e_std['autocompletes']}\n  batch    = {e_bat['autocompletes']}"
    )
    return c_std, e_std


# ─── Scénarios de lignes ─────────────────────────────────────────────────────
# Colonnes en mode positionnel 4 champs : type, fabricant, ref_modele, commercial_ref

SCENARIOS = {
    "nominal": [
        ['Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20'],
        ['Lave-vaisselle', 'Bosch', 'SMV4HTX31E', 'ActiveWater'],
        ['Réfrigérateur', 'LG', 'GBB62PZGFN', 'DoorCooling+'],
    ],
    "doublon_intra_fichier": [
        ['Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20'],
        ['Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20'],
        ['Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20'],
    ],
    "ref_modele_seule": [
        ['Aspirateur', 'Samsung', 'SC4520', ''],
        ['Aspirateur', 'Samsung', 'SC4521', ''],
    ],
    "commercial_ref_seule": [
        ['Aspirateur', 'Samsung', '', 'PowerBrush 20'],
        ['Aspirateur', 'Samsung', '', 'PowerBrush 30'],
    ],
    "mono_reference_et_complete_melangees": [
        ['Aspirateur', 'Samsung', 'SC4520', ''],
        ['Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20'],
        ['Aspirateur', 'Samsung', '', 'PowerBrush 20'],
    ],
    "type_marque_manquants": [
        ['', '', 'SC4520', 'PowerBrush 20'],
        ['', 'Samsung', 'SC4521', ''],
        ['Aspirateur', '', 'SC4522', ''],
    ],
    "lignes_vides_intercalees": [
        ['Aspirateur', 'Samsung', 'SC4520', 'PB'],
        ['', '', '', ''],
        ['   ', '  ', ' ', '  '],
        ['Réfrigérateur', 'LG', 'GBB62', 'DC'],
    ],
    "espaces_parasites": [
        ['  Aspirateur ', ' Samsung', ' SC4520 ', ' PowerBrush 20 '],
        ['Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20'],
    ],
    "toutes_references_vides": [
        ['Aspirateur', 'Samsung', '', ''],
        ['Lave-vaisselle', 'Bosch', '', ''],
    ],
    "valeurs_nulles": [
        ['Aspirateur', 'Samsung', 'SC4520', None],
        [None, 'Bosch', 'SMV4', 'ActiveWater'],
    ],
}


# ─── Historique : deux divergences trouvées puis corrigées ───────────────────
# Ces tests ont été écrits en v3.69.1 et ont immédiatement révélé deux écarts,
# marqués alors xfail(strict=True). Corrigés en v3.69.2 dans _insert_or_find_device :
#
#   A. NULL contre chaîne vide — le chemin standard n'insérait que les colonnes
#      présentes et laissait SQLite écrire NULL là où le batch écrit ''.
#      « WHERE type = '' » ne ramenait donc pas les mêmes lignes selon la taille
#      du fichier importé.
#
#   B. Replis de résolution asymétriques — une ligne COMPLÈTE se rattachait à un
#      appareil PARTIEL existant côté standard, et sa référence commerciale était
#      perdue : 2 appareils au lieu de 3. Les replis sont désormais gardés pour
#      ne s'appliquer qu'aux lignes elles-mêmes partielles, reproduisant la clé
#      composite du chemin batch.
#
# Les marqueurs xfail ont été retirés : ces tests doivent passer. S'ils échouent
# à nouveau, c'est qu'un des deux chemins a redérivé.



class TestEquivalenceLotUnique:
    """Un seul lot : le cas d'un fichier isolé."""

    @pytest.mark.parametrize("nom", sorted(SCENARIOS))
    def test_chemins_equivalents(self, qapp, nom):
        _assert_equivalents([SCENARIOS[nom]])


class TestEquivalenceMultiLots:
    """Plusieurs lots partageant `seen_device_refs` : déduplication INTER-fichiers.

    C'est le terrain du bug de la v3.66.1 — le 2ᵉ lot doit retrouver les appareils
    du 1ᵉʳ, pas les recréer.
    """

    def test_reimport_du_meme_lot(self, qapp):
        """Le cas exact de la régression v3.66.1, sur les deux chemins."""
        lot = SCENARIOS["nominal"]
        compteurs, etat = _assert_equivalents([lot, lot])
        # Garde de fond : le ré-import ne doit pas créer de second jeu d'appareils
        assert len(etat['appareils']) == 3, (
            f"Ré-import : 3 appareils attendus, {len(etat['appareils'])} trouvés"
        )
        assert compteurs['duplicates_in_file'] == 3

    def test_reimport_mono_reference(self, qapp):
        """Variante mono-référence — la forme précise qui avait dérivé."""
        lot = SCENARIOS["ref_modele_seule"]
        _, etat = _assert_equivalents([lot, lot])
        assert len(etat['appareils']) == 2

    def test_reimport_commercial_ref_seule(self, qapp):
        """Symétrique : le trou miroir corrigé en v3.66.1."""
        lot = SCENARIOS["commercial_ref_seule"]
        _, etat = _assert_equivalents([lot, lot])
        assert len(etat['appareils']) == 2

    def test_lots_disjoints_puis_recouvrement(self, qapp):
        premier = [['Aspirateur', 'Samsung', 'SC4520', 'PB20']]
        second = [['Réfrigérateur', 'LG', 'GBB62', 'DC']]
        troisieme = [['Aspirateur', 'Samsung', 'SC4520', 'PB20'],
                     ['Four', 'Bosch', 'HBA0001', 'SER0001']]
        _assert_equivalents([premier, second, troisieme])


class TestEquivalenceConfiguration:
    """Les options de configuration ne doivent pas faire diverger les chemins."""

    def test_troisieme_colonne_en_other_ref(self, qapp):
        lignes = [
            ['SC4520', 'PowerBrush 20', 'AUTRE_REF_1'],
            ['SC4521', 'PowerBrush 30', 'AUTRE_REF_2'],
        ]
        _assert_equivalents([lignes], {'third_column_choice': 'other_ref'})

    def test_troisieme_colonne_en_notes(self, qapp):
        lignes = [
            ['SC4520', 'PowerBrush 20', 'une note'],
            ['SC4521', 'PowerBrush 30', 'une autre note'],
        ]
        _assert_equivalents([lignes], {'third_column_choice': 'notes'})

    def test_mapping_de_colonnes_personnalise(self, qapp):
        lignes = [
            ['Samsung', 'SC4520', 'Aspirateur'],
            ['Bosch', 'SMV4HTX31E', 'Lave-vaisselle'],
        ]
        mapping = {3: ['manufacturer', 'ref_modele', 'type']}
        _assert_equivalents([lignes], {'column_mapping': mapping})

    def test_deux_colonnes_seulement(self, qapp):
        lignes = [['SC4520', 'PowerBrush 20'], ['SC4521', 'PowerBrush 30']]
        _assert_equivalents([lignes])


class TestEquivalenceVolume:
    """Au-delà du seuil de bascule : le chemin batch est celui réellement pris."""

    def test_au_dela_du_seuil_de_bascule(self, qapp):
        lignes = [
            ['Aspirateur', 'Samsung', f'SC{i:05d}', f'PowerBrush {i}']
            for i in range(60)
        ]
        compteurs, etat = _assert_equivalents([lignes])
        assert compteurs['total_imported'] == 60
        assert len(etat['appareils']) == 60

    def test_gros_lot_avec_doublons(self, qapp):
        base = [['Aspirateur', 'Samsung', f'SC{i:05d}', f'PB {i}'] for i in range(40)]
        _assert_equivalents([base + base])


class TestCompletionAppareilsExistants:
    """v3.88.2 — un appareil EXISTANT dont Type/Fabricant sont vides reçoit ceux de
    la ligne importée (lus dans le fichier ou auto-complétés), sans jamais écraser
    une valeur déjà saisie.

    Jusqu'en v3.88.1, aucun des deux chemins ne les écrivait, et la ligne, complète
    en mémoire, n'était pas non plus proposée en suggestion : constaté sur une
    copie de la base, 30 appareils vidés puis réimportés → « auto-complétion :
    24 types », 30/30 toujours vides, 6 candidats seulement.
    """

    # Un appareil complet sert de source d'auto-complétion par la réf. commerciale
    SOURCE = ('Four', 'Bosch', 'X2', 'CR1')

    def test_vide_complete_par_auto_completion(self, qapp):
        details = []
        _, etat = _assert_equivalents(
            [[['', '', 'X1', 'CR1']]],
            preexistants=[self.SOURCE, ('', '', 'X1', 'CR1')], details=details)
        assert ('Four', 'Bosch', 'X1', 'CR1') in etat['appareils']
        assert details == [(('commercial_ref', 'CR1'), ('id', 2), ('manufacturer', 'Bosch'),
                            ('ref_modele', 'X1'), ('type', 'Four'))]

    def test_valeur_du_fichier_reportee(self, qapp):
        _, etat = _assert_equivalents(
            [[['Lave-linge', 'Miele', 'X1', 'CR9']]],
            preexistants=[('', '', 'X1', 'CR9')])
        assert etat['appareils'] == [('Lave-linge', 'Miele', 'X1', 'CR9')]

    def test_jamais_ecraser_une_valeur_saisie(self, qapp):
        """Fabricant « Bosch » en base, « Miele » dans le fichier : Bosch reste,
        seul le type vide est complété."""
        details = []
        _, etat = _assert_equivalents(
            [[['Lave-linge', 'Miele', 'X3', 'CR9']]],
            preexistants=[('', 'Bosch', 'X3', 'CR9')], details=details)
        assert etat['appareils'] == [('Lave-linge', 'Bosch', 'X3', 'CR9')]
        assert dict(details[0])['type'] == 'Lave-linge'
        assert 'manufacturer' not in dict(details[0])

    def test_appareil_complet_intouche(self, qapp):
        details = []
        _, etat = _assert_equivalents(
            [[['Lave-linge', 'Miele', 'X4', 'CR9']]],
            preexistants=[('Four', 'Bosch', 'X4', 'CR9')], details=details)
        assert etat['appareils'] == [('Four', 'Bosch', 'X4', 'CR9')]
        assert details == []

    def test_sans_source_reste_candidat_de_suggestion(self, qapp):
        c_std, e_std, s_std = _executer(
            'standard', [[['', '', 'X5', 'CR5']]], preexistants=[('', '', 'X5', 'CR5')])
        c_bat, e_bat, s_bat = _executer(
            'batch', [[['', '', 'X5', 'CR5']]], preexistants=[('', '', 'X5', 'CR5')])
        assert e_std == e_bat and e_std['appareils'] == [('', '', 'X5', 'CR5')]
        assert s_std == s_bat == 1

    def test_mono_references(self, qapp):
        """Les replis « ref_modele seule » / « commercial_ref seule » du chemin
        standard complètent aussi, comme la clé composite du batch."""
        _, etat = _assert_equivalents(
            [[['Four', 'Bosch', 'M1', ''], ['Hotte', 'Elica', '', 'C1']]],
            preexistants=[('', '', 'M1', ''), ('', '', '', 'C1')])
        assert ('Four', 'Bosch', 'M1', '') in etat['appareils']
        assert ('Hotte', 'Elica', '', 'C1') in etat['appareils']

    def test_reimport_trace_une_seule_fois(self, qapp):
        """Deux lots (= deux fichiers) touchant le même appareil : une seule entrée
        dans la trace, et le cache du batch ne retente pas l'écriture."""
        lot = [['Four', 'Bosch', 'X6', 'CR6']]
        details = []
        _assert_equivalents([lot, lot], preexistants=[('', '', 'X6', 'CR6')],
                            details=details)
        assert len(details) == 1

    def test_au_dela_du_seuil_de_bascule(self, qapp):
        lignes = [['Aspirateur', 'Samsung', f'V{i:03d}', f'CV{i}'] for i in range(60)]
        vides = [('', '', f'V{i:03d}', f'CV{i}') for i in range(0, 60, 3)]
        details = []
        _, etat = _assert_equivalents([lignes], preexistants=vides, details=details)
        assert len(details) == 20
        assert all(a[:2] == ('Aspirateur', 'Samsung') for a in etat['appareils'])


class TestTraceAutocompletion:
    """v3.89.0 — tout champ écrit par l'auto-complétion laisse une trace (valeur,
    source, accord des sources), identique sur les deux chemins."""

    SOURCES = [('Four', 'Bosch', 'X2', 'CR1'), ('Four', 'Bosch', 'X3', 'CR1'),
               ('Hotte', 'Bosch', 'X4', 'CR1')]

    def test_appareils_crees(self, qapp):
        _, etat = _assert_equivalents(
            [[['', '', 'N1', 'CR1'], ['Lave-linge', '', 'N2', 'CR1']]],
            preexistants=self.SOURCES)
        # Four : 2 sources sur 3 ; Bosch : 3 sur 3 ; source = plus petite réf. du groupe gagnant
        assert etat['autocompletes'] == [
            ('N1', 'CR1', 'manufacturer', 'Bosch', 'X2', 3, 3),
            ('N1', 'CR1', 'type', 'Four', 'X2', 2, 3),
            ('N2', 'CR1', 'manufacturer', 'Bosch', 'X2', 3, 3),
        ]

    def test_appareil_existant_complete(self, qapp):
        _, etat = _assert_equivalents(
            [[['', '', 'E1', 'CR1']]],
            preexistants=self.SOURCES + [('', 'Bosch', 'E1', 'CR1')])
        # Fabricant déjà saisi : rien écrit, donc rien tracé
        assert etat['autocompletes'] == [('E1', 'CR1', 'type', 'Four', 'X2', 2, 3)]

    def test_valeur_du_fichier_jamais_tracee(self, qapp):
        _, etat = _assert_equivalents(
            [[['Four', 'Bosch', 'N1', 'CR1']]], preexistants=self.SOURCES)
        assert etat['autocompletes'] == []

    def test_auto_complete_non_verifie_ne_sert_pas_de_source(self, qapp):
        """2ᵉ lot : N1, auto-complété au 1ᵉʳ et pas encore vérifié, ne compte pas."""
        _, etat = _assert_equivalents(
            [[['', '', 'N1', 'CR7']], [['', '', 'N2', 'CR7']]],
            preexistants=[('Four', 'Bosch', 'S1', 'CR7')])
        assert [t[0] for t in etat['autocompletes']] == ['N1', 'N1', 'N2', 'N2']
        assert all(t[4:] == ('S1', 1, 1) for t in etat['autocompletes'])

    def test_au_dela_du_seuil_de_bascule(self, qapp):
        lignes = [['', '', f'V{i:03d}', 'CR1'] for i in range(60)]
        _, etat = _assert_equivalents([lignes], preexistants=self.SOURCES)
        assert len(etat['autocompletes']) == 120
