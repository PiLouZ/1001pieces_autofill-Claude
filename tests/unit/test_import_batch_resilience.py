"""
Tests — Résilience du lot d'import face à un fichier illisible

`_safe_import_single_file` annonce dans son nom et sa docstring une « gestion
d'erreur intégrée » qui n'existait pas : le corps se réduisait au `return`.
Aucun `try/except` non plus dans la boucle de `_run_import_files`, ni de clause
`except` dans cette méthode (seulement `try/finally`). Une exception levée par
un seul fichier remontait donc jusqu'à `_ImportWorker`, qui rapportait l'import
**entier** comme échoué.

Conséquence mesurée avant correction, sur un lot de 192 PDF : un alias macOS
renommé en `.pdf` (852 Ko de données `book...mark...`, aucune en-tête `%PDF`)
faisait perdre tous les fichiers suivants. Les précédents restaient écrits en
base — l'écriture est par fichier — sans qu'aucun rapport n'indique lequel avait
échoué ni où l'import s'était arrêté.

Le garde `if file_results:` de la boucle appelante anticipait pourtant déjà un
retour `None` : le wrapper *devait* intercepter et rendre la main. Ces tests
verrouillent ce contrat.

Second contrat verrouillé ici : `results['errors']` était initialisé puis jamais
alimenté ni lu côté moteur, alors que l'UI le consomme depuis toujours
(`main_refactored._safe_show_import_results_new` fait `"\\n".join(...)` dessus).
D'où l'exigence de **chaînes**, pas de dictionnaires.
"""

import pytest

from src.core.import_manager import (
    ImportManager, ImportConfiguration, ImportFile, ImportType, FileType,
)


@pytest.fixture
def manager(qapp, test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _fichier(nom):
    return ImportFile(path=f'/tmp/{nom}', type=FileType.CSV, suggested_reference=nom)


def _config(noms):
    """Lot multi-fichiers : une référence par fichier."""
    fichiers = [_fichier(n) for n in noms]
    return ImportConfiguration(
        files=fichiers, import_type=ImportType.MULTI_FILE,
        individual_references={f.path: f.name_without_ext for f in fichiers},
        individual_labels={},
    )


def _resultat_fichier_ok():
    """Ce que renvoie un fichier correctement importé (clés agrégées par la boucle)."""
    return {
        'total_lines_extracted': 3, 'total_imported': 3, 'matches_found': 1,
        'new_entries': 2, 'associations_created': 3, 'associations_existing': 0,
        'manual_completion': 0, 'duplicates_in_file': 0,
    }


def _simuler_import(echecs):
    """Remplace `_import_single_file` : lève pour les noms listés, réussit sinon.

    `echecs` : {nom_de_fichier: message d'erreur}.
    """
    def _impl(file, config, file_seen_device_refs,
              shared_devices_cache=None, shared_autocomplete_cache=None,
              dry_run=False, pdf_progress_cb=None):
        if file.filename in echecs:
            raise ValueError(echecs[file.filename])
        return _resultat_fichier_ok()
    return _impl


# ── Le wrapper lui-même ───────────────────────────────────────────────────────

def test_fichier_illisible_ne_propage_pas_l_exception(manager, monkeypatch):
    """Le wrapper absorbe l'exception et rend la main au lieu de casser le lot."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'casse.pdf': 'en-tête %PDF absente'}))

    resultat = manager._safe_import_single_file(
        _fichier('casse.pdf'), _config(['casse.pdf']), set())

    assert resultat is None, "un fichier illisible doit renvoyer None, pas lever"


def test_l_erreur_est_consignee_comme_chaine(manager, monkeypatch):
    """Contrat avec l'UI : `"\\n".join(results['errors'])` impose des chaînes."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'casse.pdf': 'en-tête %PDF absente'}))
    erreurs = []

    manager._safe_import_single_file(
        _fichier('casse.pdf'), _config(['casse.pdf']), set(), errors_out=erreurs)

    assert len(erreurs) == 1
    assert isinstance(erreurs[0], str), "des dicts feraient planter le join() de l'UI"
    assert 'casse.pdf' in erreurs[0], "le nom du fichier fautif doit être identifiable"
    assert 'en-tête %PDF absente' in erreurs[0], "la cause doit être conservée"
    # Le contrat UI doit tenir tel quel
    assert "\n".join(erreurs)


def test_sans_errors_out_le_wrapper_reste_silencieux(manager, monkeypatch):
    """`errors_out` est optionnel : les appels historiques ne doivent pas casser."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'casse.pdf': 'boum'}))

    assert manager._safe_import_single_file(
        _fichier('casse.pdf'), _config(['casse.pdf']), set()) is None


def test_annulation_n_est_pas_un_fichier_en_erreur(manager, monkeypatch):
    """Piège : une extraction PDF annulée renvoie [], puis `_import_single_file`
    lève « Aucune donnée trouvée ». Sans garde, annuler produirait un faux
    « fichier illisible » à chaque import interrompu."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'lent.pdf': 'Aucune donnée trouvée dans le fichier'}))
    manager._import_cancel_check = lambda: True
    erreurs = []

    resultat = manager._safe_import_single_file(
        _fichier('lent.pdf'), _config(['lent.pdf']), set(), errors_out=erreurs)

    assert resultat is None
    assert erreurs == [], "une annulation ne doit pas être signalée comme un fichier fautif"


# ── Le lot complet ────────────────────────────────────────────────────────────

def test_le_lot_survit_a_un_fichier_illisible(manager, monkeypatch):
    """LE test central : un fichier fautif au milieu ne doit pas emporter les suivants."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'b.pdf': 'alias macOS, pas un PDF'}))

    resultats = manager._run_import_files(_config(['a.pdf', 'b.pdf', 'c.pdf']), dry_run=True)

    assert resultats['successful_files'] == 2, "a.pdf et c.pdf doivent être importés"
    assert resultats['total_files'] == 3
    assert len(resultats['errors']) == 1
    assert 'b.pdf' in resultats['errors'][0]
    # c.pdf vient APRÈS le fichier fautif : c'est lui qui était perdu avant correction.
    noms_traites = {d['filename'] for d in resultats['file_details']}
    assert noms_traites == {'a.pdf', 'c.pdf'}


def test_les_compteurs_agregent_les_seuls_fichiers_sains(manager, monkeypatch):
    """Les totaux ne doivent compter que les fichiers réellement traités."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'b.pdf': 'illisible'}))

    resultats = manager._run_import_files(_config(['a.pdf', 'b.pdf', 'c.pdf']), dry_run=True)

    # 2 fichiers sains × les valeurs de _resultat_fichier_ok()
    assert resultats['total_imported'] == 6
    assert resultats['new_entries'] == 4
    assert resultats['associations_created'] == 6


def test_plusieurs_fichiers_illisibles_sont_tous_consignes(manager, monkeypatch):
    """Le lot va jusqu'au bout même avec plusieurs fichiers fautifs."""
    monkeypatch.setattr(manager, '_import_single_file', _simuler_import({
        'b.pdf': 'alias macOS',
        'd.pdf': 'PDF tronqué',
    }))

    resultats = manager._run_import_files(
        _config(['a.pdf', 'b.pdf', 'c.pdf', 'd.pdf', 'e.pdf']), dry_run=True)

    assert resultats['successful_files'] == 3
    assert len(resultats['errors']) == 2
    consigne = "\n".join(resultats['errors'])
    assert 'b.pdf' in consigne and 'd.pdf' in consigne


def test_dernier_fichier_illisible_n_empeche_pas_la_finalisation(manager, monkeypatch):
    """Cas limite : l'échec porte sur le dernier fichier du lot."""
    monkeypatch.setattr(manager, '_import_single_file',
                        _simuler_import({'c.pdf': 'illisible'}))

    resultats = manager._run_import_files(_config(['a.pdf', 'b.pdf', 'c.pdf']), dry_run=True)

    assert resultats['successful_files'] == 2
    assert len(resultats['errors']) == 1
    assert 'imported_refs' in resultats, "la phase de finalisation doit être atteinte"


def test_lot_entierement_sain_ne_produit_aucune_erreur(manager, monkeypatch):
    """Garde-fou anti-faux-positif : rien ne doit apparaître sur un lot propre."""
    monkeypatch.setattr(manager, '_import_single_file', _simuler_import({}))

    resultats = manager._run_import_files(_config(['a.pdf', 'b.pdf', 'c.pdf']), dry_run=True)

    assert resultats['successful_files'] == 3
    assert resultats['errors'] == []
