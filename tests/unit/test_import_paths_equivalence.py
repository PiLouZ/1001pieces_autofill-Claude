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
    return {'appareils': [tuple(a) for a in appareils], 'associations': associations}


def _executer(chemin: str, lots, config_surcharges=None):
    """Rejouer une séquence de lots dans l'un des deux chemins, sur une base neuve.

    `lots` est une liste de jeux de lignes : plusieurs lots partagent le même
    `seen_device_refs`, ce qui reproduit la déduplication INTER-fichiers.
    Retourne (compteurs cumulés, état de la base, nb de candidats similarité).
    """
    chemin_db = tempfile.mktemp(suffix='.db')
    db_file_origine = Config.DB_FILE
    recherche_origine = Config.SEARCH_PIECES_ONLY
    Config.DB_FILE = chemin_db
    Config.SEARCH_PIECES_ONLY = False
    try:
        db_manager = DatabaseManager()
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
        db_manager.close()
        return cumul, etat, candidats
    finally:
        Config.DB_FILE = db_file_origine
        Config.SEARCH_PIECES_ONLY = recherche_origine
        if os.path.exists(chemin_db):
            os.remove(chemin_db)


def _assert_equivalents(lots, config_surcharges=None):
    """Exiger l'égalité stricte des deux chemins sur les trois sorties observables."""
    c_std, e_std, s_std = _executer('standard', lots, config_surcharges)
    c_bat, e_bat, s_bat = _executer('batch', lots, config_surcharges)

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
