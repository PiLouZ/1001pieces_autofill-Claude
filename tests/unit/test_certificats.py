"""Contexte SSL des téléchargements de fiches : jamais sans vérification,
racines trouvées même quand le Python de python.org n'en a pas (sans réseau)."""

import ssl
import sys

import pytest

from src.utils import certificats


def test_contexte_verifie_et_a_des_racines(monkeypatch):
    monkeypatch.setattr(certificats, '_contexte', None)
    ctx = certificats.contexte_ssl()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert certificats.contexte_ssl() is ctx          # en cache


@pytest.mark.skipif(sys.platform != 'darwin', reason="trousseau macOS")
def test_racines_du_trousseau_macos(tmp_path):
    fichier = certificats._racines_trousseau_macos(tmp_path / 'racines.pem')
    assert fichier is not None and 'BEGIN CERTIFICATE' in fichier.read_text()
    ctx = ssl.create_default_context(cafile=str(fichier))
    assert ctx.cert_store_stats()['x509_ca'] > 50


def test_magasin_vide_remplace(monkeypatch, tmp_path):
    """Magasin par défaut vide (python.org) et pas de certifi : repli sur le fichier exporté."""
    vide = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    pem = certificats._racines_trousseau_macos(tmp_path / 'r.pem') if sys.platform == 'darwin' else None
    if pem is None:
        pytest.skip("pas de trousseau macOS")
    monkeypatch.setattr(certificats, '_contexte', None)
    original = ssl.create_default_context
    monkeypatch.setattr(certificats.ssl, 'create_default_context',
                        lambda cafile=None: original(cafile=cafile) if cafile else vide)
    monkeypatch.setitem(sys.modules, 'certifi', None)
    monkeypatch.setattr(certificats, '_racines_trousseau_macos', lambda: pem)
    ctx = certificats.contexte_ssl()
    assert ctx.cert_store_stats()['x509_ca'] > 50
