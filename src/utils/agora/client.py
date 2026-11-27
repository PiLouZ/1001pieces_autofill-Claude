"""
Appels à l'API AgoraPlus, en lecture seule, sous quota.

- Clé : variable d'environnement `AGORA_KEY`, sinon fichier `data/agora.env`
  (ligne `AGORA_KEY=…`, non suivi par git). Elle n'est jamais journalisée.
- Quota de la licence : 10 appels par jour et par service, remis à zéro à minuit
  UTC. Le compteur est tenu en local (`agora_appels`) ; un refus d'Agora (403,
  429) marque le service épuisé pour la journée, même si le compteur local ne
  l'est pas (la clé peut servir ailleurs).
- Cache : une réponse obtenue (200, ou 404 = rien chez Agora) n'est jamais
  redemandée. Un refus ou une erreur n'est **jamais** mis en cache (il serait
  lu ensuite comme « aucun appareil »).
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from .stockage import BaseAgora, cle_ref

URL_API = 'https://api.agoraplus.com/'
QUOTA_PAR_JOUR = 10
PAYS = 250                    # France
DELAI = 120                   # secondes : certaines routes répondent lentement

# Services sous quota : nom → gabarit de route
APPAREILS = 'appareils'
INFO = 'info'
ROUTES = {
    APPAREILS: 'api/v2/sparepart/getsparepartusecases/{constructeur}/{ref}/{pays}/English',
    INFO: 'api/sparepart/getsparepartinfo/{constructeur}/{ref}/{pays}',
}
LIBELLES = {APPAREILS: 'appareils compatibles', INFO: 'prix et disponibilité'}


class ErreurAgora(Exception):
    """Réponse inattendue d'Agora (le message ne contient jamais la clé)."""


class QuotaEpuise(ErreurAgora):
    """Plus d'appel possible aujourd'hui pour ce service."""


class CleAbsente(ErreurAgora):
    """Aucune clé d'API configurée."""


def lire_cle(dossier_data: Optional[str] = None) -> Optional[str]:
    cle = os.environ.get('AGORA_KEY', '').strip()
    if cle:
        return cle
    if dossier_data is None:
        from src.core.config import Config
        dossier_data = os.path.dirname(os.path.abspath(Config.DB_FILE))
    chemin = os.path.join(dossier_data, 'agora.env')
    if os.path.exists(chemin):
        with open(chemin, encoding='utf-8') as f:
            for ligne in f:
                if ligne.strip().startswith('AGORA_KEY='):
                    return ligne.split('=', 1)[1].strip().strip('"\'') or None
    return None


class TransportUrllib:
    """Envoi HTTPS (urllib). `preparer()` charge le contexte SSL avant que l'appel
    ne soit compté : un problème local (certificats) ne consomme pas le quota."""

    def __init__(self, contexte=None):
        self.contexte = contexte

    def preparer(self) -> None:
        if self.contexte is None:
            from src.utils.certificats import contexte_ssl
            self.contexte = contexte_ssl()

    def __call__(self, url: str, cle: str) -> Tuple[int, bytes]:
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        self.preparer()
        requete = Request(url, headers={'api_key': cle, 'Accept': 'application/json'})
        try:
            with urlopen(requete, timeout=DELAI, context=self.contexte) as r:
                return r.status, r.read()
        except HTTPError as e:
            return e.code, e.read()


@dataclass
class Reponse:
    donnees: Any
    depuis_cache: bool
    code: int = 200

    @property
    def absente(self) -> bool:
        """Agora ne connaît pas la référence (404 ou réponse vide)."""
        return self.code == 404 or not self.donnees


class ClientAgora:
    """`transport(url, cle) → (code, corps)` est remplaçable (tests, sans réseau)."""

    def __init__(self, base: BaseAgora, cle: Optional[str] = None,
                 transport: Optional[Callable[[str, str], Tuple[int, bytes]]] = None,
                 quota: int = QUOTA_PAR_JOUR):
        self.base = base
        self._cle = cle
        self.transport = transport or TransportUrllib()
        self.quota = quota

    @property
    def cle(self) -> str:
        if self._cle is None:
            self._cle = lire_cle()
        if not self._cle:
            raise CleAbsente("clé d'API Agora absente (data/agora.env, ligne AGORA_KEY=…)")
        return self._cle

    # --- Quota ------------------------------------------------------------------------
    def restants(self, service: str) -> int:
        n, epuise = self.base.appels_du_jour(service)
        return 0 if epuise else max(0, self.quota - n)

    @staticmethod
    def cle_cache(constructeur: int, ref: str) -> str:
        return f"{int(constructeur)}|{cle_ref(ref)}"

    def en_cache(self, service: str, constructeur: int, ref: str) -> bool:
        return self.base.lire_cache(service, self.cle_cache(constructeur, ref)) is not None

    # --- Appels -------------------------------------------------------------------------
    def appareils(self, constructeur: int, ref: str) -> Reponse:
        """Appareils compatibles : [{ManufacturerID, CommercialReference,
        TechnicalReference, Description}, …]."""
        return self._appel(APPAREILS, constructeur, ref)

    def info(self, constructeur: int, ref: str) -> Reponse:
        """Description, PublicPrice, DiscountPrice, BasePrice, Availability,
        Status, ReplaceBy…"""
        return self._appel(INFO, constructeur, ref)

    def _appel(self, service: str, constructeur: int, ref: str) -> Reponse:
        ref = (ref or '').strip()
        cle_cache = self.cle_cache(constructeur, ref)
        deja = self.base.lire_cache(service, cle_cache)
        if deja is not None:
            return Reponse(deja[1], True, deja[0])
        if self.restants(service) <= 0:
            raise QuotaEpuise(f"quota du jour atteint pour « {LIBELLES[service]} » "
                              f"({self.quota} appels, remis à zéro à minuit UTC)")
        from urllib.parse import quote
        url = URL_API + ROUTES[service].format(constructeur=int(constructeur),
                                               ref=quote(ref, safe=''), pays=PAYS)
        cle = self.cle
        preparer = getattr(self.transport, 'preparer', None)
        if preparer is not None:
            try:
                preparer()
            except Exception as e:
                raise ErreurAgora(f"connexion HTTPS impossible : {type(e).__name__}") from None
        self.base.compter_appel(service)          # l'appel compte chez Agora même s'il échoue
        try:
            code, corps = self.transport(url, cle)
        except Exception as e:
            raise ErreurAgora(f"Agora injoignable : {type(e).__name__}") from None
        if code in (401, 403, 429):
            self.base.marquer_epuise(service)
            raise QuotaEpuise(f"Agora refuse l'appel (code {code}) : quota du jour atteint "
                              f"ou clé refusée pour « {LIBELLES[service]} »")
        if code not in (200, 404):
            raise ErreurAgora(f"réponse inattendue d'Agora (code {code})")
        try:
            donnees = json.loads(corps) if corps else None
        except ValueError:
            raise ErreurAgora("réponse d'Agora illisible") from None
        # Enveloppe d'Agora : {ResponseStatus 'S' / 'E', IsValid, ResponseMessage,
        # ResponseErrorMessage, ResponseData}. Une erreur n'est jamais mise en cache.
        if isinstance(donnees, dict) and 'ResponseStatus' in donnees:
            if donnees.get('ResponseStatus') == 'E':
                message = str(donnees.get('ResponseErrorMessage') or donnees.get('ResponseMessage') or '')
                if re.search(r'quota|limit|exceed|too many', message, re.I):
                    self.base.marquer_epuise(service)
                    raise QuotaEpuise(f"Agora refuse l'appel : quota du jour atteint pour "
                                      f"« {LIBELLES[service]} »")
                raise ErreurAgora(f"Agora répond en erreur : {message[:200] or 'sans message'}")
            donnees = donnees.get('ResponseData')
        self.base.ecrire_cache(service, cle_cache, code, donnees)
        return Reponse(donnees, False, code)
