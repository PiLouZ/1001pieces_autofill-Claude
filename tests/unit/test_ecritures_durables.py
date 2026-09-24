"""
Tests — Les écritures du nettoyage survivent à la fermeture de l'application

`execute_custom_query` n'appelle jamais `commit()`. La connexion étant ouverte
sans `isolation_level`, le module sqlite3 ouvre une transaction implicite dès le
premier DML : l'écriture est visible depuis la même connexion — donc depuis
l'interface, qui affiche « Nettoyage terminé avec succès » — mais perdue si
l'application se ferme avant qu'autre chose ne commit.

Le symptôme est **intermittent** : n'importe quelle écriture ultérieure valide la
transaction au passage, si bien que l'opération paraît fonctionner la plupart du
temps. C'est ce qui l'a rendu invisible — `device_manager.py:157` porte même un
commentaire qui contourne le piège localement, sans traiter la cause.

Ces tests relisent systématiquement sur une **connexion neuve**, seule façon de
distinguer « écrit » de « commité ».
"""

import sqlite3

import pytest

from src.services.duplicates_analysis_service import DuplicatesAnalysisService


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


def _relire(db, requete, params=()):
    """Relire sur une connexion neuve, comme au lancement suivant de l'application."""
    conn = sqlite3.connect(db.db_file)
    try:
        return conn.execute(requete, params).fetchone()[0]
    finally:
        conn.close()


class TestExecuteWrite:

    def test_une_ecriture_survit_a_une_connexion_neuve(self, db):
        db.create_piece_standalone("REF", "Pompe")

        db.execute_write("UPDATE pieces SET description = ? WHERE ref_piece = ?",
                         ["Pompe de cyclage", "REF"])

        assert _relire(db, "SELECT description FROM pieces WHERE ref_piece = ?",
                       ("REF",)) == "Pompe de cyclage"

    def test_renvoie_le_nombre_reel_de_lignes(self, db):
        """`execute_custom_query` ne renvoyait rien d'exploitable, si bien que les
        appelants simulaient un compte de 1 quoi qu'il arrive."""
        for ref in ("A", "B", "C"):
            db.create_piece_standalone(ref, "")

        assert db.execute_write("UPDATE pieces SET description = 'x'") == 3
        assert db.execute_write("DELETE FROM pieces WHERE ref_piece = 'ABSENTE'") == 0

    def test_une_requete_invalide_renvoie_moins_un(self, db):
        assert db.execute_write("UPDATE table_inexistante SET x = 1") == -1

    def test_une_requete_invalide_ne_laisse_pas_de_transaction_ouverte(self, db):
        """Un rollback manquant bloquerait la base pour toutes les écritures suivantes."""
        db.create_piece_standalone("REF", "Pompe")
        db.execute_write("UPDATE table_inexistante SET x = 1")

        assert db.execute_write("UPDATE pieces SET description = 'Joint' WHERE ref_piece = 'REF'") == 1
        assert _relire(db, "SELECT description FROM pieces WHERE ref_piece = ?", ("REF",)) == "Joint"


class TestExecuteWriteBatch:

    def test_le_lot_entier_est_commite(self, db):
        db.create_piece_standalone("A", "")
        db.create_piece_standalone("B", "")

        ok = db.execute_write_batch([
            ("UPDATE pieces SET description = 'Pompe' WHERE ref_piece = 'A'", None),
            ("UPDATE pieces SET description = 'Joint' WHERE ref_piece = 'B'", None),
        ])

        assert ok is True
        assert _relire(db, "SELECT COUNT(*) FROM pieces WHERE description <> ''") == 2

    def test_un_echec_annule_tout_le_lot(self, db):
        """L'atomicité est le second motif du lot : une fusion qui supprime
        l'appareil sans avoir transféré ses pièces laisserait des associations
        orphelines, les FOREIGN KEY n'étant pas appliquées."""
        db.create_piece_standalone("A", "")

        ok = db.execute_write_batch([
            ("UPDATE pieces SET description = 'Pompe' WHERE ref_piece = 'A'", None),
            ("UPDATE table_inexistante SET x = 1", None),
        ])

        assert ok is False
        assert _relire(db, "SELECT COALESCE(description,'') FROM pieces WHERE ref_piece = 'A'") == ""

    def test_un_lot_vide_est_un_succes(self, db):
        assert db.execute_write_batch([]) is True

    def test_parametres_absents_acceptes(self, db):
        db.create_piece_standalone("A", "Pompe")

        assert db.execute_write_batch([("DELETE FROM pieces", None)]) is True
        assert _relire(db, "SELECT COUNT(*) FROM pieces") == 0


class TestFusionAppareilsDurable:
    """Le chemin réel du bouton « Nettoyer les doublons »."""

    @pytest.fixture
    def service(self, qapp, db):
        return DuplicatesAnalysisService(db_manager=db)

    @pytest.fixture
    def doublons(self, db):
        """Deux appareils identiques, chacun avec une pièce qui lui est propre."""
        db.cursor.execute(
            "INSERT INTO appareils (id, type, manufacturer, ref_modele) VALUES (1,'LV','Bosch','X1')")
        db.cursor.execute(
            "INSERT INTO appareils (id, type, manufacturer, ref_modele) VALUES (2,'LV','Bosch','X1')")
        for ref, appareil in (("P1", 1), ("P2", 2)):
            db.create_piece_standalone(ref, f"Pièce {ref}")
            piece_id = db.execute_query("SELECT id FROM pieces WHERE ref_piece = ?", [ref])[0][0]
            db.cursor.execute(
                "INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)",
                (piece_id, appareil))
        db.conn.commit()

    def test_la_fusion_survit_a_la_fermeture(self, service, db, doublons):
        """Le cœur du défaut : l'interface annonçait la fusion, et au lancement
        suivant les deux appareils étaient de retour."""
        assert service._merge_devices(master_id=1, duplicate_ids=[2]) is True

        assert _relire(db, "SELECT COUNT(*) FROM appareils") == 1

    def test_les_associations_sont_transferees_au_maitre(self, service, db, doublons):
        service._merge_devices(master_id=1, duplicate_ids=[2])

        assert _relire(db, "SELECT COUNT(*) FROM piece_associations WHERE appareil_id = 1") == 2

    def test_aucune_association_orpheline(self, service, db, doublons):
        """Les FOREIGN KEY sont inertes : rien en base ne rattraperait une
        association pointant vers un appareil supprimé."""
        service._merge_devices(master_id=1, duplicate_ids=[2])

        orphelines = _relire(db, """
            SELECT COUNT(*) FROM piece_associations pa
            LEFT JOIN appareils a ON a.id = pa.appareil_id
            WHERE a.id IS NULL
        """)
        assert orphelines == 0

    def test_une_piece_commune_ne_viole_pas_la_contrainte_unique(self, service, db, doublons):
        """Une pièce associée aux DEUX appareils : le transfert doit dédupliquer
        plutôt que violer UNIQUE(piece_id, appareil_id)."""
        db.create_piece_standalone("COMMUNE", "Pièce partagée")
        piece_id = db.execute_query("SELECT id FROM pieces WHERE ref_piece = 'COMMUNE'")[0][0]
        db.cursor.execute("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?,1)", (piece_id,))
        db.cursor.execute("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?,2)", (piece_id,))
        db.conn.commit()

        assert service._merge_devices(master_id=1, duplicate_ids=[2]) is True

        assert _relire(db, "SELECT COUNT(*) FROM piece_associations WHERE piece_id = ?",
                       (piece_id,)) == 1


class TestSuppressionPiecesDupliqueesDurable:

    @pytest.fixture
    def service(self, qapp, db):
        return DuplicatesAnalysisService(db_manager=db)

    def test_le_compte_renvoye_n_est_plus_simule(self, service, db):
        """L'appelant renvoyait 1 quoi qu'il arrive, y compris quand rien n'était
        supprimé."""
        db.create_piece_standalone("UNIQUE_REF", "Pompe")

        assert service._delete_duplicate_pieces("REF_ABSENTE") == 0
        assert _relire(db, "SELECT COUNT(*) FROM pieces WHERE ref_piece = 'UNIQUE_REF'") == 1
