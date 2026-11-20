"""
Chargement en arrière-plan des comptages du gestionnaire de pièces.

Le nombre d'appareils et les types de chaque pièce (REQUETE_COMPTAGES_PIECES)
parcourent les 5 millions d'associations : 2 à 3 s mesurées le 2026-11-20 sur
la base de production. Exécutée sur le fil de l'interface, la requête figeait
la fenêtre (spinner arrêté, curseur d'attente) à chaque ouverture.

Elle tourne ici dans un QThread, sur SA PROPRE connexion en lecture seule : la
base est en WAL, un lecteur ne bloque personne, et la connexion partagée de
DatabaseManager (et son verrou) reste libre pour le reste de l'appli.
"""

import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..utils.qt_imports import QThread, pyqtSignal
from ..core.constants import DatabaseConfig
from ..data._db_mixins.pieces import REQUETE_COMPTAGES_PIECES


def fichier_base_lisible(db_manager) -> Optional[str]:
    """Chemin du fichier de la base, ou None s'il n'y en a pas (base en
    mémoire, gestionnaire de test simplifié) : le chargement se fait alors
    sur la connexion partagée, comme avant."""
    chemin = getattr(db_manager, 'db_file', None)
    if not isinstance(chemin, str) or not chemin or chemin == ':memory:':
        return None
    return chemin if os.path.isfile(chemin) else None


def comptages_par_id(lignes) -> Dict[int, Tuple[int, Optional[str]]]:
    """{id de pièce: (nb_appareils, types_appareils)} des lignes de
    REQUETE_COMPTAGES_PIECES. Par identifiant : une référence renommée garde
    ses comptages sans attendre le calcul suivant."""
    return {r[0]: (r[1], r[2]) for r in lignes if r}


def fusionner_comptages(lignes_apercu, comptages) -> List[Tuple]:
    """Lignes du tableau (ref_piece, description, nb_appareils,
    types_appareils, is_phantom) : l'aperçu (réf., libellé, fantôme, id — à
    jour, lu sur la connexion principale) complété des comptages connus, trié
    comme avant (nb d'appareils décroissant, puis réf.).

    Une pièce absente des comptages (créée depuis) vaut (0, None) jusqu'au
    calcul suivant."""
    lignes = [
        (r[0], r[1], *comptages.get(r[5], (0, None)), r[4])
        for r in lignes_apercu
    ]
    # ORDER BY nb DESC, ref ASC : collation BINARY de SQLite = ordre des
    # points de code pour de l'UTF-8, donc le même que le tri Python.
    lignes.sort(key=lambda r: (-(r[2] or 0), r[0] or ''))
    return lignes


class ChargementComptages(QThread):
    """Exécute REQUETE_COMPTAGES_PIECES hors du fil de l'interface.

    `termine(lignes, erreur)` : lignes = liste des résultats (None en cas
    d'erreur), erreur = message (None si tout va bien). `interrompre()` coupe
    la requête en cours (sqlite3.Connection.interrupt est sûr entre fils)."""

    termine = pyqtSignal(object, object)

    def __init__(self, chemin_base: str, parent=None):
        super().__init__(parent)
        self._chemin = chemin_base
        self._conn = None
        self.interrompue = False

    def run(self):
        lignes, erreur = None, None
        try:
            uri = Path(self._chemin).resolve().as_uri() + "?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            try:
                # Mêmes réglages de lecture que la connexion principale
                self._conn.execute(f"PRAGMA cache_size={DatabaseConfig.SQLITE_CACHE_SIZE_KIB}")
                self._conn.execute("PRAGMA temp_store=MEMORY")
                self._conn.execute(f"PRAGMA mmap_size={DatabaseConfig.SQLITE_MMAP_SIZE_BYTES}")
                lignes = self._conn.execute(REQUETE_COMPTAGES_PIECES).fetchall()
            finally:
                conn, self._conn = self._conn, None
                conn.close()
        except Exception as exc:     # remonté au fil de l'interface par le signal
            lignes, erreur = None, str(exc) or exc.__class__.__name__
        self.termine.emit(lignes, erreur)

    def interrompre(self):
        self.interrompue = True
        conn = self._conn
        if conn is not None:
            try:
                conn.interrupt()
            except Exception:
                pass
