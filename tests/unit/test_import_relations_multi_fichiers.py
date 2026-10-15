"""
Tests — Relations déclarées lors d'un import multi-fichiers, chemin sans panneau

En multi-fichiers, les relations passent par le panneau « par groupes » et
`_apply_relations_from_config`. Quand ce panneau est absent (moins de deux
références, ou erreur à sa construction), la configuration retombe sur
`_apply_succession_from_config`, qui n'applique plus alors que les marqueurs
d'obsolescence (`obsolete_refs`).

Historique : cette méthode portait une branche multi-fichiers pilotée par
`succession_current_ref` / `equivalence_refs`. Aucun code de l'application ne
renseignait ces deux champs depuis l'arrivée du panneau par groupes : la branche
ne créait jamais rien en production. Elle a été retirée en 3.84.2 ; le test
`test_multi_sans_panneau_ne_cree_aucune_relation` fige ce comportement.
"""

import pytest

from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType, FileType,
)


@pytest.fixture
def manager(qapp, test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _config(references, obsoletes=None):
    """Configuration multi-fichiers : une référence par fichier.

    ATTENTION — `_apply_succession_from_config` traite `len(config.files) == 1`
    comme un import fichier unique : un test visant le multi-fichiers doit
    fournir **au moins deux fichiers**.
    """
    fichiers, individuelles = [], {}
    for i, ref in enumerate(references):
        chemin = f'/tmp/fichier{i}.csv'
        fichiers.append(ImportFile(path=chemin, type=FileType.CSV, suggested_reference=ref))
        individuelles[chemin] = ref
    return ImportConfiguration(
        files=fichiers, import_type=ImportType.MULTI_FILE,
        individual_references=individuelles, individual_labels={},
        obsolete_refs=obsoletes or [],
    )


def _successions(db):
    return {(r[0], r[1]) for r in
            (db.execute_query("SELECT ref_old, ref_new FROM piece_supersessions") or [])}


def _groupes_equivalence(db):
    """{group_id: {refs}} — les refs partageant un groupe sont équivalentes."""
    groupes = {}
    for gid, ref in (db.execute_query(
            "SELECT group_id, ref_piece FROM piece_equivalence_groups") or []):
        groupes.setdefault(gid, set()).add(ref)
    return groupes


def _est_obsolete(db, ref):
    lignes = db.execute_query(
        "SELECT COALESCE(is_obsolete, 0) FROM pieces WHERE ref_piece = ?", [ref])
    return bool(lignes[0][0]) if lignes else None


# ─── Multi-fichiers sans panneau de relations ────────────────────────────────

class TestMultiSansPanneau:

    def test_multi_sans_panneau_ne_cree_aucune_relation(self, manager, monkeypatch):
        """Seule l'obsolescence s'applique : aucune succession ni équivalence
        n'est même tentée."""
        appels = []
        monkeypatch.setattr(manager.db_manager, 'add_supersession',
                            lambda *a: appels.append(('succession', a)) or (True, ''))
        monkeypatch.setattr(manager.db_manager, 'add_equivalence',
                            lambda *a: appels.append(('equivalence', a)) or (True, ''))
        resultats = {}
        manager._apply_succession_from_config(
            _config(['REF_A', 'REF_B', 'REF_C']), resultats)

        assert appels == []
        assert resultats == {}


# ─── Obsolescence (tous modes) ───────────────────────────────────────────────

class TestObsolescence:

    def test_les_references_declarees_sont_marquees(self, manager):
        for ref in ('OBS_A', 'OBS_B'):
            manager.db_manager.create_piece_standalone(ref, '')
        resultats = {}
        manager._apply_succession_from_config(
            _config(['OBS_A', 'OBS_B', 'COURANTE'], obsoletes=['OBS_A', 'OBS_B']), resultats)

        assert _est_obsolete(manager.db_manager, 'OBS_A') is True
        assert _est_obsolete(manager.db_manager, 'OBS_B') is True
        assert resultats['obsolete_marked'] == 2

    def test_reference_vide_ignoree(self, manager):
        resultats = {}
        manager._apply_succession_from_config(
            _config(['REF', 'AUTRE'], obsoletes=['', None]), resultats)
        assert 'obsolete_marked' not in resultats

    def test_obsolescence_sans_relation(self, manager):
        """Marquer obsolète ne doit pas dépendre d'une succession déclarée."""
        manager.db_manager.create_piece_standalone('SEULE', '')
        resultats = {}
        manager._apply_succession_from_config(
            _config(['SEULE', 'AUTRE'], obsoletes=['SEULE']), resultats)
        assert _est_obsolete(manager.db_manager, 'SEULE') is True
        assert resultats['obsolete_marked'] == 1


# ─── Robustesse ──────────────────────────────────────────────────────────────

class TestRobustesse:

    def test_sans_fichier_ne_leve_pas(self, manager):
        config = ImportConfiguration(files=[], import_type=ImportType.MULTI_FILE,
                                     individual_references={}, individual_labels={})
        manager._apply_succession_from_config(config, {})

    def test_une_relation_refusee_n_interrompt_pas_les_suivantes(self, manager, monkeypatch):
        """Fichier unique : un cycle refusé sur « remplace » ne doit pas empêcher
        « remplacée par » ni l'équivalence."""
        appels = []
        vraie = manager.db_manager.add_supersession

        def add_supersession(old, new):
            appels.append((old, new))
            if old == 'REFUSEE':
                return False, "cycle simulé"
            return vraie(old, new)

        monkeypatch.setattr(manager.db_manager, 'add_supersession', add_supersession)
        config = _config(['IMPORTEE'])
        config.import_type = ImportType.SINGLE_FILE
        config.succession_replaces = 'REFUSEE'
        config.succession_replaced_by = 'NOUVELLE'
        config.equivalence_ref = 'EQUIV'
        resultats = {}
        manager._apply_succession_from_config(config, resultats)

        assert appels == [('REFUSEE', 'IMPORTEE'), ('IMPORTEE', 'NOUVELLE')]
        assert _successions(manager.db_manager) == {('IMPORTEE', 'NOUVELLE')}
        assert resultats['succession_created'] == 1
        assert resultats['equivalences_created'] == 1
