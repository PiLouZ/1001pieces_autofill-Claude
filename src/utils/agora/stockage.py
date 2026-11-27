"""
Base locale d'Agora : `data/agora.db` (à côté de `appareils.db`, non suivie par git).

- `agora_cache` : réponses de l'API déjà obtenues (une référence n'est jamais
  demandée deux fois) ;
- `agora_appels` : appels du jour par service, pour le quota (jour UTC) ;
- `myspace_pieces`, `myspace_produits`, `myspace_meta` : fichiers MySpace chargés.

Une connexion par opération : la base est lue depuis le thread principal et
depuis les threads d'appel à l'API.
"""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, Tuple

_NON_ALNUM = re.compile(r'[^A-Z0-9]')


def cle_ref(ref: Optional[str]) -> str:
    """Clé de rapprochement d'une référence : majuscules, sans ponctuation ni espace."""
    return _NON_ALNUM.sub('', (ref or '').upper())


def jour_utc(maintenant: Optional[datetime] = None) -> str:
    """Jour du quota Agora (remis à zéro à minuit UTC)."""
    return (maintenant or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y-%m-%d')


def chemin_par_defaut() -> str:
    from src.core.config import Config
    return os.path.join(os.path.dirname(os.path.abspath(Config.DB_FILE)), 'agora.db')


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agora_cache (
    service  TEXT NOT NULL,
    cle      TEXT NOT NULL,
    code     INTEGER NOT NULL,
    reponse  TEXT,
    lu_le    TEXT NOT NULL,
    PRIMARY KEY (service, cle)
);
CREATE TABLE IF NOT EXISTS agora_appels (
    jour     TEXT NOT NULL,
    service  TEXT NOT NULL,
    nombre   INTEGER NOT NULL DEFAULT 0,
    epuise   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (jour, service)
);
CREATE TABLE IF NOT EXISTS fiches_agora (
    ref_piece     TEXT PRIMARY KEY,
    constructeur  INTEGER,
    code          TEXT,
    designation   TEXT,
    prix_achat    REAL,
    prix_ttc      REAL,
    regle_prix    TEXT,
    importee_le   TEXT
);
CREATE TABLE IF NOT EXISTS agora_echecs (
    service  TEXT NOT NULL,
    cle      TEXT NOT NULL,
    code     INTEGER,
    le       TEXT NOT NULL,
    PRIMARY KEY (service, cle)
);
CREATE TABLE IF NOT EXISTS myspace_meta (
    cle      TEXT PRIMARY KEY,
    valeur   TEXT
);
"""


class BaseAgora:
    """Accès à `agora.db`."""

    def __init__(self, chemin: Optional[str] = None):
        self.chemin = chemin or chemin_par_defaut()
        with self.connexion() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def connexion(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.chemin, timeout=30)
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # --- Cache des réponses -------------------------------------------------------
    def lire_cache(self, service: str, cle: str) -> Optional[Tuple[int, Any]]:
        with self.connexion() as c:
            row = c.execute("SELECT code, reponse FROM agora_cache WHERE service = ? AND cle = ?",
                            (service, cle)).fetchone()
        if row is None:
            return None
        return row[0], (json.loads(row[1]) if row[1] else None)

    def ecrire_cache(self, service: str, cle: str, code: int, reponse: Any) -> None:
        with self.connexion() as c:
            c.execute("INSERT OR REPLACE INTO agora_cache VALUES (?, ?, ?, ?, ?)",
                      (service, cle, code, json.dumps(reponse, ensure_ascii=False),
                       datetime.now(timezone.utc).isoformat(timespec='seconds')))

    # --- Pièces qu'Agora ne sait pas traiter (délai dépassé) --------------------------------
    def noter_echec(self, service: str, cle: str, code: int) -> None:
        with self.connexion() as c:
            c.execute("INSERT OR REPLACE INTO agora_echecs VALUES (?, ?, ?, ?)",
                      (service, cle, code, datetime.now(timezone.utc).isoformat(timespec='seconds')))

    def echec(self, service: str, cle: str) -> Optional[str]:
        """Date (ISO, UTC) du dernier échec « délai dépassé » de cette pièce, sinon None."""
        with self.connexion() as c:
            row = c.execute("SELECT le FROM agora_echecs WHERE service = ? AND cle = ?",
                            (service, cle)).fetchone()
        return row[0] if row else None

    # --- Quota ----------------------------------------------------------------------
    def appels_du_jour(self, service: str, jour: Optional[str] = None) -> Tuple[int, bool]:
        """(appels faits aujourd'hui, quota signalé épuisé par Agora)."""
        with self.connexion() as c:
            row = c.execute("SELECT nombre, epuise FROM agora_appels WHERE jour = ? AND service = ?",
                            (jour or jour_utc(), service)).fetchone()
        return (row[0], bool(row[1])) if row else (0, False)

    def compter_appel(self, service: str, jour: Optional[str] = None) -> None:
        with self.connexion() as c:
            c.execute("INSERT INTO agora_appels (jour, service, nombre) VALUES (?, ?, 1) "
                      "ON CONFLICT(jour, service) DO UPDATE SET nombre = nombre + 1",
                      (jour or jour_utc(), service))

    def marquer_epuise(self, service: str, jour: Optional[str] = None) -> None:
        with self.connexion() as c:
            c.execute("INSERT INTO agora_appels (jour, service, nombre, epuise) VALUES (?, ?, 0, 1) "
                      "ON CONFLICT(jour, service) DO UPDATE SET epuise = 1",
                      (jour or jour_utc(), service))

    # --- Fiches importées depuis Agora (données commerciales, pour l'export) -----------
    def noter_fiche(self, ref_piece: str, constructeur: int, code: str, designation: str,
                    prix_achat: Optional[float], prix_ttc: Optional[float], regle: str) -> None:
        with self.connexion() as c:
            c.execute("INSERT OR REPLACE INTO fiches_agora VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (cle_ref(ref_piece), constructeur, code, designation, prix_achat, prix_ttc,
                       regle, datetime.now(timezone.utc).isoformat(timespec='seconds')))

    def fiche(self, ref_piece: str) -> Optional[dict]:
        with self.connexion() as c:
            c.row_factory = sqlite3.Row
            row = c.execute("SELECT * FROM fiches_agora WHERE ref_piece = ?",
                            (cle_ref(ref_piece),)).fetchone()
        return dict(row) if row else None

    def info_en_cache(self, ref_piece: str) -> Optional[Tuple[int, dict]]:
        """(constructeur, réponse getsparepartinfo) déjà obtenue pour cette référence."""
        with self.connexion() as c:
            rows = c.execute("SELECT cle, reponse FROM agora_cache WHERE service = 'info' AND cle LIKE ?",
                             (f"%|{cle_ref(ref_piece)}",)).fetchall()
        for cle, reponse in rows:
            donnees = json.loads(reponse) if reponse else None
            if isinstance(donnees, dict):
                return int(cle.split('|', 1)[0]), donnees
        return None

    # --- Méta ---------------------------------------------------------------------------
    def meta(self, cle: str) -> Optional[str]:
        with self.connexion() as c:
            row = c.execute("SELECT valeur FROM myspace_meta WHERE cle = ?", (cle,)).fetchone()
        return row[0] if row else None

    def ecrire_meta(self, c: sqlite3.Connection, cle: str, valeur: str) -> None:
        c.execute("INSERT OR REPLACE INTO myspace_meta VALUES (?, ?)", (cle, valeur))
