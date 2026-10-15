"""
Tests — Référence commune identique à la référence du fichier : pas de double comptage

`_import_single_file` construit `references_and_labels` en empilant la référence
commune PUIS la référence individuelle du fichier, sans dédoublonner. Quand les
deux valent la même chose, chaque ligne porte deux fois la même association :
la 1ʳᵉ est créée, la 2ⁿᵈᵉ retrouvée en base et comptée « déjà associée ».

Constaté le 2026-10-15 en rejouant un collage de 25 radiateurs (référence
TEST_MARQUES) : synthèse « Nouvelles : 25 » ET « Déjà associées : 25 », alors
qu'aucune association n'existait avant l'import. La base, elle, ne contenait
bien que 25 associations — le défaut est dans le comptage (et dans les 25
allers-retours SQL inutiles), pas dans les écritures.

Depuis l'interface, le cas survient sur un import multi-fichiers dont la
référence commune est aussi celle d'un fichier (ex. « 805101 » + 805101.pdf).
"""

import pytest

from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType,
    LabelConfiguration, FileType,
)

MAPPING = {4: ['type', 'manufacturer', 'ref_modele', 'commercial_ref']}


@pytest.fixture
def manager(qapp, test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _lignes(n):
    return [['Radiateur', 'Delta', f'RAD{i:03d}', f'COM{i:03d}'] for i in range(n)]


def _config(n, ref_commune, ref_fichier, libelle_commun='', libelle_fichier=''):
    fichier = ImportFile(path='Collage', type=FileType.CLIPBOARD,
                         suggested_reference='', suggested_label='', data=_lignes(n))
    return ImportConfiguration(
        files=[fichier], import_type=ImportType.MULTI_FILE,
        common_reference=ref_commune, use_common_reference=bool(ref_commune),
        common_label=libelle_commun,
        label_config=LabelConfiguration(),
        individual_references={'Collage': ref_fichier},
        individual_labels={'Collage': libelle_fichier},
        has_headers=False, column_mapping=MAPPING,
    )


def _nb_associations(db_manager):
    return db_manager.execute_query("SELECT COUNT(*) FROM piece_associations")[0][0]


# 25 lignes → chemin standard ; 60 lignes → chemin batch (seuil 50)
@pytest.mark.parametrize('n', [25, 60], ids=['standard', 'batch'])
def test_reference_commune_egale_a_celle_du_fichier_compte_une_fois(manager, test_db_manager, n):
    resultats = manager._run_import_files(_config(n, 'TEST_MARQUES', 'TEST_MARQUES'))

    assert resultats['new_entries'] == n
    assert resultats['associations_created'] == n
    assert resultats['associations_existing'] == 0
    assert _nb_associations(test_db_manager) == n


def test_apercu_dry_run_compte_une_fois(manager, test_db_manager):
    resultats = manager._run_import_files(_config(25, 'TEST_MARQUES', 'TEST_MARQUES'),
                                          dry_run=True)

    assert resultats['associations_created'] == 25
    assert resultats['associations_existing'] == 0
    assert _nb_associations(test_db_manager) == 0


# Non-régression : deux références DISTINCTES donnent bien deux associations par ligne
@pytest.mark.parametrize('n', [25, 60], ids=['standard', 'batch'])
def test_references_distinctes_donnent_deux_associations(manager, test_db_manager, n):
    resultats = manager._run_import_files(_config(n, 'REF_COMMUNE', 'REF_FICHIER'))

    assert resultats['associations_created'] == 2 * n
    assert resultats['associations_existing'] == 0
    assert _nb_associations(test_db_manager) == 2 * n


# Libellé : même résultat qu'avant le dédoublonnage, où le 2ᵈ passage (fichier)
# remplaçait le libellé du 1ᵉʳ (commun) s'il était renseigné.
@pytest.mark.parametrize('libelle_fichier, attendu', [
    ('Thermostat fichier', 'Thermostat fichier'),
    ('', 'Thermostat commun'),
], ids=['libelle_fichier_prioritaire', 'repli_sur_libelle_commun'])
def test_libelle_conserve_apres_dedoublonnage(manager, test_db_manager, libelle_fichier, attendu):
    manager._run_import_files(_config(5, 'TEST_MARQUES', 'TEST_MARQUES',
                                      libelle_commun='Thermostat commun',
                                      libelle_fichier=libelle_fichier))

    description = test_db_manager.execute_query(
        "SELECT description FROM pieces WHERE ref_piece = 'TEST_MARQUES'")[0][0]
    assert description == attendu
