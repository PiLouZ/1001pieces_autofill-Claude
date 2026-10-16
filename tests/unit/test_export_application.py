"""
Tests — Export portable de l'application (export_app.py, v3.90.0)

Couvre : liste blanche (rien de lourd ni de personnel ne part), fichiers de test
d'import, réglages d'export vidés de leur chemin local, instantané de la base
(WAL inclus), dépendances épinglées sans outils de développement, Python
embarqué Windows (._pth), lanceurs .bat, décompression des wheels, archive zip
(droits conservés), nettoyage en cas d'échec, et le service d'interface.
"""

import importlib.util
import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def exp():
    spec = importlib.util.spec_from_file_location('export_app_teste', RACINE / 'export_app.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── Liste blanche ───────────────────────────────────────────────────────────

class TestCopieListeBlanche:

    def test_seuls_les_fichiers_utiles_sont_copies(self, exp, tmp_path):
        nb = exp._copy_source(tmp_path)
        assert nb > 50
        racine = {p.name for p in tmp_path.iterdir()}
        assert racine == {'run.py', 'app_icon.png', 'requirements.txt', 'docs', 'src'}
        assert [p.name for p in (tmp_path / 'docs').iterdir()] == ['guide_utilisation.html']

    def test_src_sans_cache_ni_fichier_systeme(self, exp, tmp_path):
        exp._copy_source(tmp_path)
        fichiers = [p for p in (tmp_path / 'src').rglob('*') if p.is_file()]
        assert fichiers and all(p.suffix == '.py' for p in fichiers)
        assert not any('__pycache__' in p.parts for p in fichiers)

    def test_tout_le_code_est_copie(self, exp, tmp_path):
        """Aucun module de src/ oublié (sinon l'application ne démarre pas)."""
        exp._copy_source(tmp_path)
        attendus = {p.relative_to(RACINE) for p in (RACINE / 'src').rglob('*.py')
                    if '__pycache__' not in p.parts}
        copies = {p.relative_to(tmp_path) for p in (tmp_path / 'src').rglob('*.py')}
        assert copies == attendus

    def test_fichiers_de_test_import_copies(self, exp, tmp_path):
        nb = exp._copy_test_import_files(tmp_path)
        dossier = tmp_path / 'fichiers_test_import'
        noms = {p.name for p in dossier.iterdir()}
        assert nb == len(noms) >= 2
        assert any(n.endswith('.pdf') for n in noms)
        assert 'whirlpool_suggestions_test.csv' in noms


class TestConfigExport:

    def test_dossier_de_sortie_vide_profils_conserves(self, exp, tmp_path):
        exp._write_export_config(tmp_path)
        config = json.loads((tmp_path / 'data' / 'export_config.json').read_text(encoding='utf-8'))
        assert config['output_dir'] == ''
        assert 'csv' in config and 'html' in config


# ─── Base de données ─────────────────────────────────────────────────────────

class TestInstantaneBase:

    def test_ecritures_du_wal_incluses(self, exp, tmp_path):
        """Une copie de fichier perdrait la ligne encore dans le -wal."""
        source = tmp_path / 'source.db'
        conn = sqlite3.connect(source)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE t (x)')
        conn.execute('INSERT INTO t VALUES (42)')
        conn.commit()          # connexion gardée ouverte : la ligne reste dans le WAL
        assert Path(str(source) + '-wal').stat().st_size > 0

        dest = tmp_path / 'export'
        cible = exp._snapshot_database(dest, db_path=source)
        conn.close()

        copie = sqlite3.connect(cible)
        assert copie.execute('SELECT x FROM t').fetchall() == [(42,)]
        copie.close()
        assert not Path(str(cible) + '-wal').exists()

    def test_base_absente_leve_une_erreur(self, exp, tmp_path):
        with pytest.raises(FileNotFoundError):
            exp._snapshot_database(tmp_path, db_path=tmp_path / 'absente.db')


# ─── Dépendances ─────────────────────────────────────────────────────────────

class TestDependances:

    def test_fermeture_sans_outils_de_developpement(self, exp):
        pins = exp._dependances_epinglees()
        for necessaire in ('pyqt5', 'qtawesome', 'camelot-py', 'pandas', 'numpy',
                           'opencv-python-headless', 'pdfminer-six', 'chardet'):
            assert necessaire in pins, necessaire
        for outil in ('pytest', 'pytest-qt', 'py-spy', 'vulture', 'tree-sitter',
                      'git-filter-repo'):
            assert outil not in pins, outil
        assert all('==' in v for v in pins.values())

    def test_requirements_frozen_ecrit(self, exp, tmp_path):
        chemin = exp._freeze_requirements(tmp_path)
        lignes = chemin.read_text(encoding='utf-8').split()
        assert any(l.lower().startswith('pyqt5==') for l in lignes)
        assert not any(l.lower().startswith('pytest') for l in lignes)

    def test_exigences_windows(self, exp, tmp_path):
        req, cst = exp._ecrire_exigences_windows(tmp_path)
        directes = req.read_text(encoding='utf-8').split()
        contraintes = cst.read_text(encoding='utf-8').lower()
        assert 'colorama' in directes
        # PyQt5-Qt5 > 5.15.2 n'existe pas pour Windows : jamais épinglé
        assert 'pyqt5-qt5==' not in contraintes
        assert 'numpy==' in contraintes


# ─── Windows ─────────────────────────────────────────────────────────────────

class TestPythonWindows:

    def _faux_python(self, tmp_path):
        archive = tmp_path / 'embed.zip'
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr('python.exe', 'x')
            zf.writestr('python312._pth', 'python312.zip\r\n.\r\n#import site\r\n')
        return archive

    def test_pth_declare_site_packages_et_racine(self, exp, tmp_path):
        dest = tmp_path / 'export'
        dossier = exp._preparer_python_windows(dest, self._faux_python(tmp_path))
        lignes = (dossier / 'python312._pth').read_text(encoding='utf-8').splitlines()
        assert lignes == ['python312.zip', '.', 'Lib\\site-packages', '..', 'import site']
        assert (dossier / 'Lib' / 'site-packages').is_dir()

    def test_telechargement_altere_refuse(self, exp, tmp_path):
        reponse = MagicMock()
        reponse.__enter__.return_value = reponse
        reponse.read.side_effect = [b'faux contenu', b'']
        with patch.object(exp, 'CACHE_DIR', tmp_path), \
                patch.object(exp.urllib.request, 'urlopen', return_value=reponse):
            with pytest.raises(RuntimeError, match='altéré'):
                exp._telecharger_python_windows()
        assert not list(tmp_path.glob('*.zip'))

    def test_cache_utilise_si_empreinte_correcte(self, exp, tmp_path):
        contenu = b'python embarque'
        archive = tmp_path / Path(exp.PYTHON_WIN_URL).name
        archive.write_bytes(contenu)
        import hashlib
        with patch.object(exp, 'CACHE_DIR', tmp_path), \
                patch.object(exp, 'PYTHON_WIN_SHA256', hashlib.sha256(contenu).hexdigest()), \
                patch.object(exp.urllib.request, 'urlopen') as urlopen:
            assert exp._telecharger_python_windows() == archive
        urlopen.assert_not_called()

    def test_wheels_decompresses_sans_repertoire_data(self, exp, tmp_path):
        python_dir = tmp_path / 'python'
        (python_dir / 'Lib' / 'site-packages').mkdir(parents=True)

        def faux_pip(cmd, **kwargs):
            wheels = Path(cmd[cmd.index('-d') + 1])
            wheels.mkdir(parents=True)
            with zipfile.ZipFile(wheels / 'paquet-1.0-py3-none-any.whl', 'w') as zf:
                zf.writestr('paquet/__init__.py', '')
                zf.writestr('paquet-1.0.dist-info/METADATA', 'Name: paquet')
                zf.writestr('paquet-1.0.data/scripts/outil', '')
            assert '--platform' in cmd and 'win_amd64' in cmd
            return MagicMock(returncode=0, stderr='')

        with patch.object(exp.subprocess, 'run', side_effect=faux_pip):
            exp._installer_dependances_windows(python_dir)
        sp = python_dir / 'Lib' / 'site-packages'
        assert (sp / 'paquet' / '__init__.py').exists()
        assert (sp / 'paquet-1.0.dist-info' / 'METADATA').exists()
        assert not (sp / 'paquet-1.0.data').exists()

    def test_echec_pip_remonte(self, exp, tmp_path):
        (tmp_path / 'Lib' / 'site-packages').mkdir(parents=True)
        with patch.object(exp.subprocess, 'run',
                          return_value=MagicMock(returncode=1, stderr='réseau')):
            with pytest.raises(RuntimeError, match='dépendances Windows'):
                exp._installer_dependances_windows(tmp_path)

    def test_lanceurs_bat_ascii_crlf(self, exp, tmp_path):
        exp._ecrire_lanceurs_windows(tmp_path)
        for nom in ('1001pieces_autofill.bat', '1001pieces_autofill_console.bat'):
            brut = (tmp_path / nom).read_bytes()
            brut.decode('ascii')
            assert b'\r\n' in brut and b'\n' not in brut.replace(b'\r\n', b'')
        assert b'pythonw.exe' in (tmp_path / '1001pieces_autofill.bat').read_bytes()

    def test_lisezmoi_windows(self, exp, tmp_path):
        exp._write_readme_windows(tmp_path, '16/10/2026 12:00')
        texte = (tmp_path / 'LISEZMOI.txt').read_bytes().decode('utf-8')
        assert '1001pieces_autofill.bat' in texte and 'fichiers_test_import' in texte


# ─── Archive et orchestration ────────────────────────────────────────────────

class TestArchive:

    def test_zip_conserve_dossier_racine_et_droits(self, exp, tmp_path):
        dossier = tmp_path / '1001pieces_export_macos_test'
        (dossier / 'data').mkdir(parents=True)
        (dossier / 'data' / 'a.txt').write_text('a')
        script = dossier / 'install.command'
        script.write_text('#!/bin/bash')
        script.chmod(0o755)

        archive = exp._zipper(dossier)
        assert not dossier.exists()
        with zipfile.ZipFile(archive) as zf:
            noms = set(zf.namelist())
            assert noms == {'1001pieces_export_macos_test/data/a.txt',
                            '1001pieces_export_macos_test/install.command'}
            mode = zf.getinfo('1001pieces_export_macos_test/install.command').external_attr >> 16
            assert mode & stat.S_IXUSR


class TestCreateExport:

    def test_cible_inconnue(self, exp, tmp_path):
        result = exp.create_export(tmp_path, cible='linux')
        assert not result['success'] and 'linux' in result['error']
        assert list(tmp_path.iterdir()) == []

    def test_echec_ne_laisse_pas_de_dossier(self, exp, tmp_path):
        with patch.object(exp, '_snapshot_database', side_effect=RuntimeError('boum')):
            result = exp.create_export(tmp_path, cible='windows')
        assert not result['success'] and result['error'] == 'boum'
        assert list(tmp_path.iterdir()) == []

    def test_windows_de_bout_en_bout_sans_reseau(self, exp, tmp_path):
        """Orchestration complète, téléchargements et base simulés."""
        def faux_snapshot(dest, progress_callback=None, db_path=None):
            (dest / 'data').mkdir(parents=True, exist_ok=True)
            (dest / 'data' / 'appareils.db').write_bytes(b'db')

        def faux_python(dest, archive):
            (dest / 'python' / 'Lib' / 'site-packages').mkdir(parents=True)
            return dest / 'python'

        with patch.object(exp, '_snapshot_database', side_effect=faux_snapshot), \
                patch.object(exp, '_telecharger_python_windows', return_value=None), \
                patch.object(exp, '_preparer_python_windows', side_effect=faux_python), \
                patch.object(exp, '_installer_dependances_windows'):
            messages = []
            result = exp.create_export(tmp_path, progress_callback=messages.append,
                                       cible='windows')
        assert result['success'], result['error']
        assert result['path'].endswith('.zip') and result['cible'] == 'windows'
        assert [p.suffix for p in tmp_path.iterdir()] == ['.zip']
        with zipfile.ZipFile(result['path']) as zf:
            racines = {n.split('/')[1] for n in zf.namelist()}
        assert {'1001pieces_autofill.bat', 'LISEZMOI.txt', 'data', 'src', 'run.py',
                'fichiers_test_import', 'docs'} <= racines
        assert not racines & {'tests', 'scripts', 'CHANGELOG.md', 'export_app.py', 'wheels'}
        assert messages[-1].startswith('Export terminé')


# ─── Bureau sous Windows (OneDrive) ──────────────────────────────────────────

class TestBureauWindows:

    def test_bureau_systeme_si_desktop_absent(self, qapp, tmp_path):
        """Windows + OneDrive : ~/Desktop n'existe pas, le Bureau est ailleurs."""
        from src.services.export_config_service import ExportConfigService
        from PyQt5.QtCore import QStandardPaths
        bureau_onedrive = tmp_path / 'OneDrive' / 'Bureau'
        bureau_onedrive.mkdir(parents=True)
        with patch('os.path.expanduser', return_value=str(tmp_path)), \
                patch.object(QStandardPaths, 'writableLocation',
                             return_value=str(bureau_onedrive)):
            assert ExportConfigService.get_default_output_dir() == str(bureau_onedrive)

    def test_repli_dossier_personnel(self, qapp, tmp_path):
        from src.services.export_config_service import ExportConfigService
        from PyQt5.QtCore import QStandardPaths
        with patch('os.path.expanduser', return_value=str(tmp_path)), \
                patch.object(QStandardPaths, 'writableLocation',
                             return_value=str(tmp_path / 'inexistant')):
            assert ExportConfigService.get_default_output_dir() == str(tmp_path)


# ─── Service d'interface ─────────────────────────────────────────────────────

class TestAppExportService:

    def test_poste_sans_script_affiche_un_message(self, qapp, tmp_path):
        from src.services import app_export_service as mod
        svc = mod.AppExportService(None)
        with patch.object(mod, '_EXPORT_SCRIPT', tmp_path / 'absent.py'), \
                patch.object(mod.MessageHelper, 'show_info') as info, \
                patch.object(mod, 'QMessageBox') as boite:
            svc.open_dialog()
        info.assert_called_once()
        boite.assert_not_called()

    def test_choix_de_la_cible_transmis(self, qapp, tmp_path):
        from src.services import app_export_service as mod
        svc = mod.AppExportService(None)
        svc.open_dialog()
        boite = svc._boite_cible
        boutons = {b.text(): b for b in boite.buttons()}
        assert set(boutons) == {'Windows', 'macOS', 'Annuler'}
        assert boite.defaultButton() is boutons['Windows']
        with patch.object(svc, '_choisir_dossier_et_exporter') as lancer:
            boutons['macOS'].click()
        lancer.assert_called_once_with('macos')
        boite.close()

    def test_worker_transmet_la_cible(self, qapp, tmp_path):
        from src.services import app_export_service as mod
        faux = MagicMock()
        faux.create_export.return_value = {'success': True}
        with patch.object(mod, '_charger_module_export', return_value=faux):
            worker = mod._ExportWorker(str(tmp_path), 'macos')
            worker.run()
        assert faux.create_export.call_args.kwargs['cible'] == 'macos'
