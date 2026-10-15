"""
Tests — Nettoyage ponctuel des associations orphelines

Le script supprime les associations pièce↔appareil dont la pièce ou l'appareil
n'existe plus. Ce qui doit être garanti :
  - la simulation n'écrit rien ;
  - une association valide n'est jamais touchée ;
  - un échec de sauvegarde, un écart de comptage ou l'app ouverte empêchent
    toute suppression ;
  - plus d'orphelines que l'audit → arrêt, sans écrire.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

import nettoyage_associations_orphelines as script  # noqa: E402


# Associations : (id, piece_id, appareil_id)
VALIDES = [(1, 10, 100), (2, 11, 100), (3, 10, 101)]
VERS_PIECE_ABSENTE = [(4, 99, 100), (5, 99, 101)]
VERS_APPAREIL_ABSENT = [(6, 11, 999)]          # surcompte la pièce P11 dans le gestionnaire
ORPHELINE_DES_DEUX_COTES = [(7, 98, 998)]      # ne doit être comptée qu'une fois


@pytest.fixture
def base(tmp_path):
    chemin = tmp_path / "appareils.db"
    conn = sqlite3.connect(chemin)
    conn.executescript("""
        CREATE TABLE appareils (id INTEGER PRIMARY KEY, ref_modele TEXT);
        CREATE TABLE pieces (id INTEGER PRIMARY KEY, ref_piece TEXT NOT NULL UNIQUE);
        CREATE TABLE piece_associations (
            id INTEGER PRIMARY KEY,
            piece_id INTEGER NOT NULL,
            appareil_id INTEGER NOT NULL,
            FOREIGN KEY(piece_id) REFERENCES pieces(id) ON DELETE CASCADE,
            FOREIGN KEY(appareil_id) REFERENCES appareils(id) ON DELETE CASCADE,
            UNIQUE(piece_id, appareil_id)
        );
        INSERT INTO appareils VALUES (100, 'M100'), (101, 'M101');
        INSERT INTO pieces VALUES (10, 'P10'), (11, 'P11');
    """)
    conn.executemany("INSERT INTO piece_associations VALUES (?, ?, ?)",
                     VALIDES + VERS_PIECE_ABSENTE + VERS_APPAREIL_ABSENT
                     + ORPHELINE_DES_DEUX_COTES)
    conn.commit()
    conn.close()
    return chemin


@pytest.fixture
def app_fermee(monkeypatch):
    monkeypatch.setattr(script, "autres_processus_ouverts", lambda chemin: [])


def _ids(chemin):
    conn = sqlite3.connect(chemin)
    try:
        return sorted(r[0] for r in conn.execute("SELECT id FROM piece_associations"))
    finally:
        conn.close()


TOUS = sorted(r[0] for r in VALIDES + VERS_PIECE_ABSENTE + VERS_APPAREIL_ABSENT
              + ORPHELINE_DES_DEUX_COTES)
IDS_VALIDES = sorted(r[0] for r in VALIDES)


class TestMesure:

    def test_comptage_sans_double_compte(self, base):
        conn = script._connexion(base)
        etat = script.mesurer(conn)
        conn.close()
        assert etat["vers_piece_absente"] == 3          # 4, 5, 7
        assert etat["pieces_absentes"] == 2             # 99, 98
        assert etat["vers_appareil_absent"] == 2        # 6, 7
        assert etat["orphelines"] == 4                  # 4, 5, 6, 7 — la 7 une seule fois
        assert etat["comptes_faux"] == [("P11", 2, 1)]


class TestSimulation:

    def test_n_ecrit_rien(self, base):
        assert script.main(["--base", str(base)]) == 0
        assert _ids(base) == TOUS
        assert not (base.parent / "backups").exists()

    def test_plus_d_orphelines_que_l_audit_arrete(self, base, monkeypatch, app_fermee):
        monkeypatch.setattr(script, "ATTENDU_AUDIT", 3)
        assert script.main(["--base", str(base), "--ecrire"]) == 3
        assert _ids(base) == TOUS


class TestEcriture:

    def test_supprime_les_orphelines_et_seulement_elles(self, base, app_fermee):
        assert script.main(["--base", str(base), "--ecrire"]) == 0
        assert _ids(base) == IDS_VALIDES
        assert script.controler(base, len(IDS_VALIDES)) == []

    def test_sauvegarde_creee_avant(self, base, app_fermee):
        script.main(["--base", str(base), "--ecrire"])
        copies = list((base.parent / "backups").glob("*nettoyage_orphelins*"))
        assert len(copies) == 1
        conn = sqlite3.connect(copies[0])
        try:
            # La copie contient l'état AVANT suppression
            assert conn.execute("SELECT COUNT(*) FROM piece_associations").fetchone()[0] == len(TOUS)
        finally:
            conn.close()

    def test_echec_de_sauvegarde_bloque_la_suppression(self, base, monkeypatch, app_fermee):
        monkeypatch.setattr(script, "sauvegarder", lambda chemin: None)
        assert script.main(["--base", str(base), "--ecrire"]) == 1
        assert _ids(base) == TOUS

    def test_app_ouverte_bloque(self, base, monkeypatch):
        monkeypatch.setattr(script, "autres_processus_ouverts", lambda chemin: [4242])
        assert script.main(["--base", str(base), "--ecrire"]) == 2
        assert _ids(base) == TOUS

    def test_verification_impossible_bloque(self, base, monkeypatch):
        monkeypatch.setattr(script, "autres_processus_ouverts", lambda chemin: None)
        assert script.main(["--base", str(base), "--ecrire"]) == 2
        assert _ids(base) == TOUS

    def test_ecart_de_comptage_annule_la_transaction(self, base):
        with pytest.raises(RuntimeError, match="écart de comptage"):
            script.supprimer(base, attendu=5)           # 4 orphelines réelles
        assert _ids(base) == TOUS

    def test_rien_a_supprimer(self, base, app_fermee):
        script.main(["--base", str(base), "--ecrire"])
        assert script.main(["--base", str(base), "--ecrire"]) == 0
        assert _ids(base) == IDS_VALIDES


class TestControles:

    def test_detecte_un_volume_inattendu(self, base):
        anomalies = script.controler(base, total_attendu=1)
        assert any("associations au lieu de" in a for a in anomalies)

    def test_detecte_les_orphelines_restantes(self, base):
        anomalies = script.controler(base, total_attendu=len(TOUS))
        assert any("violation" in a for a in anomalies)
        assert any("P11" in a for a in anomalies)
