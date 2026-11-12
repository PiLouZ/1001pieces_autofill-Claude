"""
Contexte SSL pour les téléchargements HTTPS (lecture d'une fiche du site)

Le Python de python.org sur macOS est livré SANS certificats racines (son
`cert.pem` n'existe pas tant qu'on n'a pas lancé « Install Certificates ») :
toute connexion HTTPS échoue alors avec CERTIFICATE_VERIFY_FAILED. La
vérification n'est jamais désactivée ; on cherche des racines, dans l'ordre :

1. le magasin par défaut de Python, s'il contient des certificats (Windows,
   Linux, Python Homebrew…) ;
2. le module `certifi`, s'il est installé ;
3. sur macOS, les racines du trousseau système (`security find-certificate`),
   exportées une fois dans `data/certificats_racines.pem` et rafraîchies tous
   les 30 jours.
"""

import ssl
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from ..core.logger import app_logger

_TROUSSEAU = '/System/Library/Keychains/SystemRootCertificates.keychain'
_FICHIER = Path(__file__).resolve().parents[2] / 'data' / 'certificats_racines.pem'
_VALIDITE_S = 30 * 24 * 3600
_contexte: Optional[ssl.SSLContext] = None


def _a_des_racines(ctx: ssl.SSLContext) -> bool:
    return ctx.cert_store_stats().get('x509_ca', 0) > 0


def _racines_trousseau_macos(fichier: Path = _FICHIER) -> Optional[Path]:
    """Exporte (ou réutilise) les racines du trousseau système macOS en PEM."""
    if sys.platform != 'darwin':
        return None
    try:
        if fichier.exists() and time.time() - fichier.stat().st_mtime < _VALIDITE_S:
            return fichier
        pem = subprocess.run(['security', 'find-certificate', '-a', '-p', _TROUSSEAU],
                             capture_output=True, text=True, timeout=30, check=True).stdout
        if 'BEGIN CERTIFICATE' not in pem:
            return None
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(pem, encoding='ascii')
        return fichier
    except Exception as e:
        app_logger.warning(f"[HTTPS] racines du trousseau macOS illisibles : {e}")
        return fichier if fichier.exists() else None


def contexte_ssl() -> ssl.SSLContext:
    """Contexte SSL vérifiant les certificats, avec des racines trouvées (en cache)."""
    global _contexte
    if _contexte is not None:
        return _contexte
    ctx = ssl.create_default_context()
    if not _a_des_racines(ctx):
        source = ''
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
            source = 'certifi'
        except ImportError:
            fichier = _racines_trousseau_macos()
            if fichier is not None:
                ctx = ssl.create_default_context(cafile=str(fichier))
                source = 'trousseau macOS'
        if source:
            app_logger.info(f"[HTTPS] certificats racines : {source} "
                            f"({ctx.cert_store_stats().get('x509_ca', 0)})")
        else:
            app_logger.warning("[HTTPS] aucun certificat racine trouvé : les liens HTTPS échoueront")
    _contexte = ctx
    return ctx
