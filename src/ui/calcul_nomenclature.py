"""
Calculs des règles de nomenclature en arrière-plan (lot 4, CDC § 8.1).

La découverte (§ 6.3) et le calcul des propositions (§ 6.2) relisent les
720 000 appareils : ~3,5 s chacun mesurés le 2026-11-23 sur la base de
production. Sur le fil de l'interface, l'écran Règles serait figé à chaque
validation de règle.

Ils tournent ici dans un QThread, sur SA PROPRE connexion en lecture seule
(comme les comptages du gestionnaire de pièces, PR #166) : la base est en WAL,
un lecteur ne bloque personne. Les lectures sont celles du mixin de la base
(`DatabaseNomenclatureMixin`), montées sur cette connexion : aucun SQL copié.

Le thread ne fait que CALCULER ; l'écriture (propositions, nouvelles règles)
se fait ensuite sur le fil principal, qui écarte ce qui a changé entre-temps
(`RegleNomenclatureService.ecrire_propositions`).
"""

import sqlite3
import threading
from pathlib import Path

from ..core.constants import DatabaseConfig
from ..data._db_mixins.nomenclature import DatabaseNomenclatureMixin
from ..utils.qt_imports import QThread, pyqtSignal
from .chargement_pieces import fichier_base_lisible

MODE_PROPOSER = 'proposer'
MODE_DECOUVRIR = 'decouvrir'


class LecteurNomenclature(DatabaseNomenclatureMixin):
    """Lectures du moteur sur une connexion en lecture seule, propre au fil."""

    def __init__(self, chemin_base: str):
        uri = Path(chemin_base).resolve().as_uri() + "?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.execute(f"PRAGMA cache_size={DatabaseConfig.SQLITE_CACHE_SIZE_KIB}")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.cursor = self.conn.cursor()
        self._query_lock = threading.RLock()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


class CalculNomenclature(QThread):
    """`termine(bilan, erreur)` : bilan = BilanPropositions ou BilanDecouverte
    (None en cas d'erreur), erreur = message (None si tout va bien)."""

    termine = pyqtSignal(object, object)

    def __init__(self, db_manager, mode: str, types_autorises=None, configuration=None,
                 parent=None):
        super().__init__(parent)
        if mode not in (MODE_PROPOSER, MODE_DECOUVRIR):
            raise ValueError(f"mode inconnu : {mode}")
        self._db_manager = db_manager
        self.mode = mode
        self._types_autorises = types_autorises
        self._configuration = configuration

    def run(self):
        from ..services.regle_nomenclature_service import RegleNomenclatureService
        bilan, erreur, lecteur = None, None, None
        try:
            chemin = fichier_base_lisible(self._db_manager)
            # Sans fichier (base en mémoire des tests) : la connexion partagée,
            # protégée par son verrou
            lecteur = LecteurNomenclature(chemin) if chemin else None
            service = RegleNomenclatureService(lecteur or self._db_manager,
                                               types_autorises=self._types_autorises,
                                               configuration=self._configuration)
            bilan = (service.calculer_propositions(ecrire=False) if self.mode == MODE_PROPOSER
                     else service.decouvrir_regles(ecrire=False))
            if getattr(bilan, 'erreur', ''):
                bilan, erreur = None, bilan.erreur
        except Exception as exc:     # remonté au fil de l'interface par le signal
            bilan, erreur = None, str(exc) or exc.__class__.__name__
        finally:
            if lecteur is not None:
                lecteur.close()
        self.termine.emit(bilan, erreur)
