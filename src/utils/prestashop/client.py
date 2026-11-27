"""
Accès au webservice PrestaShop (JSON en lecture, XML en écriture).

- Authentification HTTP Basic, la clé en identifiant ; jamais journalisée.
- User-Agent propre à l'outil : Cloudflare refuse celui de Python par défaut.
- `transport(méthode, url, en-têtes, corps) → (code, corps)` est remplaçable
  (tests, sans réseau).
"""

import base64
import json
import os
import re
import uuid
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

USER_AGENT = '1001pieces-autofill (Ukoo)'
DELAI = 90


class ErreurPrestaShop(Exception):
    """Réponse en erreur du webservice (le message ne contient jamais la clé)."""


class ConfigAbsente(ErreurPrestaShop):
    """data/prestashop.env absent ou incomplet."""


def lire_config(dossier_data: Optional[str] = None) -> Tuple[str, str]:
    """(adresse du site, clé), d'après PS_URL / PS_KEY (environnement, sinon fichier)."""
    url, cle = os.environ.get('PS_URL', ''), os.environ.get('PS_KEY', '')
    if not (url and cle):
        if dossier_data is None:
            from src.core.config import Config
            dossier_data = os.path.dirname(os.path.abspath(Config.DB_FILE))
        chemin = os.path.join(dossier_data, 'prestashop.env')
        if os.path.exists(chemin):
            with open(chemin, encoding='utf-8') as f:
                valeurs = dict(l.strip().split('=', 1) for l in f if '=' in l and not l.startswith('#'))
            url = url or valeurs.get('PS_URL', '')
            cle = cle or valeurs.get('PS_KEY', '')
    url, cle = url.strip().strip('"\'').rstrip('/'), cle.strip().strip('"\'')
    if not (url and cle):
        raise ConfigAbsente("webservice PrestaShop non configuré (data/prestashop.env : PS_URL=…, PS_KEY=…)")
    return url, cle


def _transport_urllib(methode: str, url: str, entetes: Dict[str, str],
                      corps: Optional[bytes]) -> Tuple[int, bytes]:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    contexte = None
    try:
        from src.utils.certificats import contexte_ssl
        contexte = contexte_ssl()
    except Exception:
        contexte = None
    requete = Request(url, data=corps, headers=entetes, method=methode)
    try:
        with urlopen(requete, timeout=DELAI, context=contexte) as r:
            return r.status, r.read()
    except HTTPError as e:
        return e.code, e.read()


def _message_erreur(code: int, corps: bytes) -> str:
    texte = corps.decode('utf-8', errors='replace') if corps else ''
    try:
        erreurs = json.loads(texte).get('errors') or []
        if erreurs:
            return '; '.join(str(e.get('message', '')) for e in erreurs)
    except (ValueError, AttributeError):
        pass
    messages = re.findall(r'<message><!\[CDATA\[(.*?)\]\]></message>', texte, re.S)
    return '; '.join(messages) or f"code {code}"


class ClientPrestaShop:
    def __init__(self, url: Optional[str] = None, cle: Optional[str] = None,
                 transport: Optional[Callable] = None):
        if url is None or cle is None:
            url, cle = lire_config()
        self.url = url.rstrip('/')
        self._auth = 'Basic ' + base64.b64encode(f"{cle}:".encode()).decode()
        self.transport = transport or _transport_urllib

    @property
    def environnement(self) -> str:
        """« dev » ou « production », pour l'afficher avant une écriture."""
        return 'production' if re.match(r'https?://(www\.)?1001pieces\.com', self.url) else 'dev'

    def _appel(self, methode: str, chemin: str, params: Optional[Dict[str, str]] = None,
               corps: Optional[bytes] = None, type_corps: str = 'application/xml') -> Tuple[int, bytes]:
        url = f"{self.url}/api/{chemin.lstrip('/')}"
        if params:
            url += '?' + urlencode(params, safe='[]%,|')
        entetes = {'Authorization': self._auth, 'User-Agent': USER_AGENT}
        if corps is not None:
            entetes['Content-Type'] = type_corps
        try:
            code, reponse = self.transport(methode, url, entetes, corps)
        except Exception as e:
            raise ErreurPrestaShop(f"site injoignable : {type(e).__name__}") from None
        if code >= 400:
            raise ErreurPrestaShop(f"{methode} {chemin.split('?')[0]} : {_message_erreur(code, reponse)}")
        return code, reponse

    def lister(self, ressource: str, champs: str = 'full', filtres: Optional[Dict[str, str]] = None,
               limite: Optional[str] = None, tri: Optional[str] = None) -> list:
        """Liste d'une ressource ([] si rien). filtres : {'reference': '[EL123]'}."""
        params = {'output_format': 'JSON', 'display': champs}
        for champ, valeur in (filtres or {}).items():
            params[f'filter[{champ}]'] = valeur
        if limite:
            params['limit'] = limite
        if tri:
            params['sort'] = tri
        _code, corps = self._appel('GET', ressource, params)
        donnees = json.loads(corps or b'null')
        return (donnees or {}).get(ressource, []) if isinstance(donnees, dict) else []

    def lire(self, ressource: str, ident: int) -> Dict[str, Any]:
        _code, corps = self._appel('GET', f"{ressource}/{int(ident)}", {'output_format': 'JSON'})
        donnees = json.loads(corps)
        return next(iter(donnees.values())) if isinstance(donnees, dict) and donnees else {}

    def creer(self, ressource: str, xml: str) -> int:
        """POST d'une ressource ; retourne son id."""
        _code, corps = self._appel('POST', ressource, {'output_format': 'JSON'}, xml.encode('utf-8'))
        try:
            donnees = json.loads(corps)
            return int(next(iter(donnees.values()))['id'])
        except (ValueError, KeyError, StopIteration, TypeError):
            m = re.search(rb'<id><!\[CDATA\[(\d+)\]\]></id>', corps or b'')
            if m:
                return int(m.group(1))
            raise ErreurPrestaShop("création : identifiant absent de la réponse") from None

    def envoyer_image(self, id_produit: int, contenu: bytes, nom: str = 'cover.jpg') -> None:
        """Image d'un produit (la première devient la cover)."""
        limite = f"----autofill{uuid.uuid4().hex}"
        corps = (f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{nom}\"\r\n"
                 f"Content-Type: image/jpeg\r\n\r\n").encode() + contenu + f"\r\n--{limite}--\r\n".encode()
        self._appel('POST', f"images/products/{int(id_produit)}", None, corps,
                    f"multipart/form-data; boundary={limite}")
