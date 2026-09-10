"""
Tests — Relations déclarées lors d'un import multi-fichiers

`_apply_succession_from_config` crée en base les successions, équivalences et
marqueurs d'obsolescence déclarés dans la fenêtre d'import. Sa branche
**fichier unique** était couverte (cf. test_import_phantom_label.py) ; sa branche
**multi-fichiers** ne l'était par aucun test, alors qu'elle écrit dans
`piece_supersessions`, `piece_equivalence_groups` et `pieces.is_obsolete`.

Trou repéré en mesurant la couverture des champs de configuration :
`succession_current_ref`, `equivalence_refs` et `obsolete_refs` n'apparaissaient
dans aucun fichier de test.

Deux modes existent :
  - une **référence courante** est désignée : toutes les autres pointent vers elle ;
  - **aucune référence courante** (« Option B ») : seuls les équivalents se lient,
    au premier d'entre eux.
"""

import pytest

from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType, FileType,
)


@pytest.fixture
def manager(qapp, test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _config(references, courante=None, equivalents=None, obsoletes=None):
    """Configuration multi-fichiers : une référence par fichier.

    ATTENTION — `_apply_succession_from_config` teste `len(config.files) == 1`
    AVANT la branche multi-fichiers. Un seul fichier part donc dans le chemin
    fichier-unique : tout test visant la branche multi doit fournir **au moins
    deux fichiers**. Deux de ces tests ne le faisaient pas et ne vérifiaient
    rien — défaut révélé par mutation du code source.
    """
    fichiers, individuelles = [], {}
    for i, ref in enumerate(references):
        chemin = f'/tmp/fichier{i}.csv'
        fichiers.append(ImportFile(path=chemin, type=FileType.CSV, suggested_reference=ref))
        individuelles[chemin] = ref
    return ImportConfiguration(
        files=fichiers, import_type=ImportType.MULTI_FILE,
        individual_references=individuelles, individual_labels={},
        succession_current_ref=courante,
        equivalence_refs=equivalents or [],
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


# ─── Succession vers une référence courante ──────────────────────────────────

class TestSuccessionMultiFichiers:

    def test_toutes_les_autres_pointent_vers_la_courante(self, manager):
        resultats = {}
        manager._apply_succession_from_config(
            _config(['ANCIENNE_A', 'ANCIENNE_B', 'COURANTE'], courante='COURANTE'), resultats)

        assert _successions(manager.db_manager) == {
            ('ANCIENNE_A', 'COURANTE'), ('ANCIENNE_B', 'COURANTE')}
        assert resultats['succession_created'] == 2

    def test_la_courante_ne_pointe_pas_vers_elle_meme(self, manager, monkeypatch):
        """Le fichier portant la référence courante doit être ignoré.

        On vérifie que `add_supersession` n'est même pas **appelée** : se contenter
        d'observer la base laisserait passer une régression, la couche base
        refusant déjà l'auto-référence. Le test mesurerait alors ce garde-fou-là,
        pas celui de la boucle.
        """
        appels = []
        monkeypatch.setattr(manager.db_manager, 'add_supersession',
                            lambda old, new: appels.append((old, new)) or (True, ''))

        # Deux fichiers minimum, sinon c'est la branche fichier-unique qui s'exécute
        manager._apply_succession_from_config(
            _config(['COURANTE', 'ANCIENNE'], courante='COURANTE'), {})

        assert ('COURANTE', 'COURANTE') not in appels, \
            f"la référence courante a été traitée : {appels}"
        assert appels == [('ANCIENNE', 'COURANTE')], appels
        assert _successions(manager.db_manager) == set()

    def test_reference_vide_ignoree(self, manager):
        config = _config(['ANCIENNE', 'COURANTE'], courante='COURANTE')
        config.individual_references['/tmp/fichier0.csv'] = ''
        resultats = {}
        manager._apply_succession_from_config(config, resultats)
        assert _successions(manager.db_manager) == set()
        assert 'succession_created' not in resultats

    def test_sans_courante_aucune_succession(self, manager):
        """Option B : sans référence courante, rien à faire hériter."""
        resultats = {}
        manager._apply_succession_from_config(
            _config(['REF_A', 'REF_B'], courante=None), resultats)
        assert _successions(manager.db_manager) == set()
        assert 'succession_created' not in resultats


# ─── Équivalences ────────────────────────────────────────────────────────────

class TestEquivalencesMultiFichiers:

    def test_un_equivalent_est_lie_a_la_courante(self, manager):
        """Une référence listée en équivalence ne devient PAS une succession."""
        resultats = {}
        manager._apply_succession_from_config(
            _config(['EQUIV_A', 'ANCIENNE', 'COURANTE'],
                    courante='COURANTE', equivalents=['EQUIV_A']), resultats)

        assert _successions(manager.db_manager) == {('ANCIENNE', 'COURANTE')}
        assert resultats['equivalences_created'] == 1
        assert resultats['succession_created'] == 1

        groupes = _groupes_equivalence(manager.db_manager)
        assert any({'EQUIV_A', 'COURANTE'} <= refs for refs in groupes.values()), groupes

    def test_option_b_les_equivalents_se_lient_au_premier(self, manager):
        """Sans référence courante, le pivot devient le premier équivalent déclaré."""
        resultats = {}
        manager._apply_succession_from_config(
            _config(['EQUIV_A', 'EQUIV_B', 'EQUIV_C'], courante=None,
                    equivalents=['EQUIV_A', 'EQUIV_B', 'EQUIV_C']), resultats)

        groupes = _groupes_equivalence(manager.db_manager)
        assert any({'EQUIV_A', 'EQUIV_B', 'EQUIV_C'} <= refs for refs in groupes.values()), groupes
        assert _successions(manager.db_manager) == set()

    def test_option_b_le_premier_ne_se_lie_pas_a_lui_meme(self, manager):
        """`equiv_refs[0] != other_ref` : le pivot ne peut pas être sa propre cible."""
        resultats = {}
        # Deux fichiers, mais un seul équivalent déclaré : le pivot serait lui-même
        manager._apply_succession_from_config(
            _config(['EQUIV_SEUL', 'AUTRE'], courante=None, equivalents=['EQUIV_SEUL']),
            resultats)
        assert _groupes_equivalence(manager.db_manager) == {}
        assert 'equivalences_created' not in resultats

    def test_equivalence_et_succession_coexistent(self, manager):
        resultats = {}
        manager._apply_succession_from_config(
            _config(['EQ1', 'EQ2', 'VIEILLE_A', 'VIEILLE_B', 'COURANTE'],
                    courante='COURANTE', equivalents=['EQ1', 'EQ2']), resultats)

        assert _successions(manager.db_manager) == {
            ('VIEILLE_A', 'COURANTE'), ('VIEILLE_B', 'COURANTE')}
        assert resultats['succession_created'] == 2
        assert resultats['equivalences_created'] == 2


# ─── Obsolescence (tous modes) ───────────────────────────────────────────────

class TestObsolescence:

    def test_les_references_declarees_sont_marquees(self, manager):
        for ref in ('OBS_A', 'OBS_B'):
            manager.db_manager.create_piece_standalone(ref, '')
        resultats = {}
        manager._apply_succession_from_config(
            _config(['OBS_A', 'OBS_B', 'COURANTE'], courante='COURANTE',
                    obsoletes=['OBS_A', 'OBS_B']), resultats)

        assert _est_obsolete(manager.db_manager, 'OBS_A') is True
        assert _est_obsolete(manager.db_manager, 'OBS_B') is True
        assert resultats['obsolete_marked'] == 2

    def test_reference_vide_ignoree(self, manager):
        resultats = {}
        manager._apply_succession_from_config(
            _config(['REF'], courante='REF', obsoletes=['', None]), resultats)
        assert 'obsolete_marked' not in resultats

    def test_obsolescence_sans_relation(self, manager):
        """Marquer obsolète ne doit pas dépendre d'une succession déclarée."""
        manager.db_manager.create_piece_standalone('SEULE', '')
        resultats = {}
        manager._apply_succession_from_config(
            _config(['SEULE'], courante=None, obsoletes=['SEULE']), resultats)
        assert _est_obsolete(manager.db_manager, 'SEULE') is True
        assert resultats['obsolete_marked'] == 1


# ─── Robustesse ──────────────────────────────────────────────────────────────

class TestRobustesse:

    def test_sans_fichier_ne_leve_pas(self, manager):
        config = ImportConfiguration(files=[], import_type=ImportType.MULTI_FILE,
                                     individual_references={}, individual_labels={})
        manager._apply_succession_from_config(config, {})

    def test_une_relation_refusee_n_interrompt_pas_les_suivantes(self, manager, monkeypatch):
        """Un cycle refusé sur une paire ne doit pas empêcher les autres."""
        appels = []
        vraie = manager.db_manager.add_supersession

        def add_supersession(old, new):
            appels.append((old, new))
            if old == 'REFUSEE':
                return False, "cycle simulé"
            return vraie(old, new)

        monkeypatch.setattr(manager.db_manager, 'add_supersession', add_supersession)
        resultats = {}
        manager._apply_succession_from_config(
            _config(['REFUSEE', 'ACCEPTEE', 'COURANTE'], courante='COURANTE'), resultats)

        assert len(appels) == 2, "les deux paires doivent être tentées"
        assert _successions(manager.db_manager) == {('ACCEPTEE', 'COURANTE')}
        assert resultats['succession_created'] == 1
