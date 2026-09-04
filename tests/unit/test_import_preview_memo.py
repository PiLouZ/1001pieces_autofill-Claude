"""
Tests — L'aperçu d'import n'analyse chaque fichier qu'une fois

`_analyze_formats_and_preview` interrogeait le même fichier jusqu'à quatre fois :
une pour le regroupement par nombre de colonnes, une pour l'aperçu, une pour
reconnaître le format, une pour les options de colonnes.

Sur un CSV c'est gratuit — les données sont déjà chargées, l'analyse n'est qu'une
tranche de liste. Sur un PDF, chaque appel relance l'extraction : mesuré à
6 analyses pour 3 fichiers, dont 4 sur le premier.

`_analyse_format_memo` mémoïse pour la durée d'une passe. Le cache est vidé en
entrée de `_analyze_formats_and_preview` : le chargement paresseux peut peupler
`fichier.data` entre deux passes, et un cache persistant servirait alors un
résultat obsolète.
"""

import pytest

from src.core.import_manager import (
    ImportDialog, ImportConfiguration, ImportFile, ImportType, FileType,
)


@pytest.fixture
def compteur(monkeypatch):
    """Compte les analyses réelles, par fichier."""
    appels = []
    originale = ImportDialog._safe_analyze_file_format

    def espion(self, fichier):
        appels.append(fichier.path)
        return originale(self, fichier)

    monkeypatch.setattr(ImportDialog, '_safe_analyze_file_format', espion)
    return appels


def _fichier_csv(nom, colonnes=4, lignes=5):
    return ImportFile(path=f'/tmp/{nom}.csv', type=FileType.CSV,
                      suggested_reference='REF',
                      data=[[f'v{c}' for c in range(colonnes)] for _ in range(lignes)])


def _dialogue(qapp, fichiers):
    config = ImportConfiguration(
        files=fichiers,
        import_type=ImportType.SINGLE_FILE if len(fichiers) == 1 else ImportType.MULTI_FILE,
    )
    return ImportDialog(None, config, import_manager=None)


class TestUneAnalyseParFichier:

    def test_fichier_unique(self, qapp, compteur):
        dlg = _dialogue(qapp, [_fichier_csv('a')])
        compteur.clear()
        dlg._analyze_formats_and_preview()
        assert len(compteur) == 1, f"{len(compteur)} analyses pour 1 fichier : {compteur}"
        dlg.close()

    def test_plusieurs_fichiers_meme_structure(self, qapp, compteur):
        fichiers = [_fichier_csv(n) for n in ('a', 'b', 'c')]
        dlg = _dialogue(qapp, fichiers)
        compteur.clear()
        dlg._analyze_formats_and_preview()
        assert len(compteur) == 3
        assert len(set(compteur)) == 3, "un fichier a été analysé plusieurs fois"
        dlg.close()

    def test_fichiers_de_structures_differentes(self, qapp, compteur):
        """Plusieurs groupes de colonnes : toujours une seule analyse par fichier."""
        fichiers = [_fichier_csv('a', colonnes=2), _fichier_csv('b', colonnes=3),
                    _fichier_csv('c', colonnes=4), _fichier_csv('d', colonnes=3)]
        dlg = _dialogue(qapp, fichiers)
        compteur.clear()
        dlg._analyze_formats_and_preview()
        assert len(compteur) == 4
        assert len(set(compteur)) == 4
        dlg.close()


class TestCacheLocalALaPasse:
    """Le cache ne doit jamais survivre à une passe — sinon il sert du périmé."""

    def test_le_cache_est_vide_en_entree(self, qapp, compteur):
        dlg = _dialogue(qapp, [_fichier_csv('a')])
        dlg._analyze_formats_and_preview()
        premier = dict(dlg._cache_analyse_format)
        assert premier, "le cache devrait contenir l'analyse de la passe"

        compteur.clear()
        dlg._analyze_formats_and_preview()
        assert len(compteur) == 1, "la seconde passe doit réanalyser, pas réutiliser"
        dlg.close()

    def test_une_donnee_rechargee_est_bien_revue(self, qapp, compteur):
        """Si le chargement paresseux remplit le fichier entre deux passes,
        la passe suivante doit voir les nouvelles données."""
        fichier = ImportFile(path='/tmp/tardif.csv', type=FileType.CSV,
                             suggested_reference='REF', data=[['a', 'b']])
        dlg = _dialogue(qapp, [fichier])
        dlg._analyze_formats_and_preview()
        assert 2 in dlg._file_groups

        fichier.data = [['a', 'b', 'c', 'd']]      # rechargement entre deux passes
        dlg._analyze_formats_and_preview()
        assert 4 in dlg._file_groups, "la passe suivante a servi un résultat périmé"
        dlg.close()


class TestResultatIdentique:

    def test_le_memo_rend_ce_que_rend_l_analyse_directe(self, qapp):
        fichier = _fichier_csv('a', colonnes=3)
        dlg = _dialogue(qapp, [fichier])
        dlg._cache_analyse_format = {}
        assert dlg._analyse_format_memo(fichier) == dlg._safe_analyze_file_format(fichier)
        dlg.close()

    def test_l_apercu_reste_affiche(self, qapp):
        dlg = _dialogue(qapp, [_fichier_csv('a')])
        dlg._analyze_formats_and_preview()
        # isVisible() est faux tant que le dialogue parent n'est pas affiché :
        # isHidden() dit si le code a explicitement masqué le widget.
        assert not dlg.preview_text.isHidden()
        assert 'Col1' in dlg.preview_text.toPlainText()
        dlg.close()
