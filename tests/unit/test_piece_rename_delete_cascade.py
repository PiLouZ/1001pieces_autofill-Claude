"""
Tests — Renommer ou supprimer une pièce doit entraîner ses relations

`piece_associations` désigne la pièce par `piece_id` : elle survit naturellement à
un renommage. `piece_supersessions` et `piece_equivalence_groups` la désignent par
sa **référence texte** — elles ne survivent que si le code les met à jour.

Le schéma déclare pourtant ce qu'il faut :

    FOREIGN KEY (ref_old)   REFERENCES pieces(ref_piece) ON DELETE CASCADE
    FOREIGN KEY (ref_new)   REFERENCES pieces(ref_piece) ON DELETE SET NULL
    FOREIGN KEY (ref_piece) REFERENCES pieces(ref_piece) ON DELETE CASCADE

Ces contraintes n'ont jamais rien appliqué : `PRAGMA foreign_keys` n'est activé nulle
part et SQLite le désactive par défaut. Elles ne couvrent d'ailleurs que `ON DELETE`,
jamais `ON UPDATE` — un renommage n'aurait rien propagé même activées.

**Cas réel du 2026-09-10.** Un import déclare la succession `2080942408 → 96001828`,
avec un chiffre oublié dans la référence de remplacement. `add_supersession` crée au
passage une pièce *fantôme* `96001828`. L'utilisateur corrige en renommant ce fantôme
en `960018281` : la pièce est bien renommée, mais la succession continue de pointer
vers `96001828`, désormais introuvable. Trois minutes plus tard, l'export de
`2080942408` suit la chaîne dans le vide et échoue — sur un message générique
« Erreur lors de l'export des données » qui ne dit rien de la chaîne rompue.

`test_resolution_de_chaine_apres_renommage` encode ce symptôme de bout en bout.
"""

import pytest


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


def _successions(db):
    return {(r[0], r[1]) for r in
            (db.execute_query("SELECT ref_old, ref_new FROM piece_supersessions") or [])}


def _groupe_de(db, ref):
    lignes = db.execute_query(
        "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref]) or []
    return lignes[0][0] if lignes else None


def _piece_existe(db, ref):
    return bool(db.execute_query("SELECT 1 FROM pieces WHERE ref_piece = ?", [ref]))


# ── Renommage ────────────────────────────────────────────────────────────────

class TestRenommagePropageLesRelations:

    def test_succession_suit_le_renommage_de_la_remplacante(self, db):
        """Le cas réel : c'est la référence NOUVELLE qui est renommée."""
        db.add_supersession('OLD1', 'NEW1')

        assert db.rename_piece_catalog('NEW1', 'NEW1BIS', 'desc') is True

        assert ('OLD1', 'NEW1BIS') in _successions(db), \
            "la succession doit suivre la remplaçante renommée"
        assert ('OLD1', 'NEW1') not in _successions(db), \
            "elle ne doit plus pointer vers l'ancienne référence, qui n'existe plus"

    def test_succession_suit_le_renommage_de_la_remplacee(self, db):
        """Symétrique : c'est la référence ANCIENNE qui est renommée."""
        db.add_supersession('OLD2', 'NEW2')

        assert db.rename_piece_catalog('OLD2', 'OLD2BIS', 'desc') is True

        assert ('OLD2BIS', 'NEW2') in _successions(db)
        assert ('OLD2', 'NEW2') not in _successions(db)

    def test_equivalence_suit_le_renommage(self, db):
        """Même trou sur les groupes d'équivalence, qui pointent aussi par texte."""
        db.add_equivalence('EQ1', 'EQ2')
        groupe = _groupe_de(db, 'EQ1')
        assert groupe is not None, "pré-requis : le groupe doit exister"

        assert db.rename_piece_catalog('EQ1', 'EQ1BIS', 'desc') is True

        assert _groupe_de(db, 'EQ1BIS') == groupe, \
            "la référence renommée doit rester dans son groupe d'équivalence"
        assert _groupe_de(db, 'EQ1') is None

    def test_resolution_de_chaine_apres_renommage(self, db):
        """LE test qui encode le symptôme utilisateur.

        `resolve_current_ref` est ce que suit l'export. Avant correction il
        renvoyait une référence disparue, l'export ne trouvait aucune donnée et
        affichait une erreur technique sans rapport visible avec la cause.
        """
        db.add_supersession('2080942408', '96001828')
        db.rename_piece_catalog('96001828', '960018281', 'desc')

        courante = db.resolve_current_ref('2080942408')

        assert courante == '960018281', \
            f"la chaîne doit mener à la pièce renommée, pas à '{courante}'"
        assert _piece_existe(db, courante), \
            "la référence résolue doit exister en base — sinon l'export part dans le vide"

    def test_renommage_sans_changement_de_nom_reste_neutre(self, db):
        """Garde-fou : renommer vers le même nom ne doit rien casser."""
        db.add_supersession('OLD3', 'NEW3')

        assert db.rename_piece_catalog('NEW3', 'NEW3', 'nouvelle description') is True

        assert ('OLD3', 'NEW3') in _successions(db)

    def test_pas_de_succession_reflexive(self, db):
        """Une pièce ne peut pas se remplacer elle-même — invariant à préserver."""
        db.add_supersession('OLD4', 'NEW4')
        db.rename_piece_catalog('NEW4', 'NEW4BIS', 'desc')

        assert not [(o, n) for o, n in _successions(db) if o == n], \
            "aucune succession ne doit être réflexive après un renommage"


# ── Suppression ──────────────────────────────────────────────────────────────

class TestSuppressionNettoieLesRelations:
    """Trou jumeau : `ON DELETE CASCADE` est déclaré mais jamais appliqué."""

    def test_succession_supprimee_quand_la_remplacee_disparait(self, db):
        """Sémantique déclarée par le schéma : ON DELETE CASCADE sur ref_old."""
        db.add_supersession('DEL1', 'CIBLE1')

        db.delete_piece_catalog('DEL1')

        assert not [s for s in _successions(db) if s[0] == 'DEL1'], \
            "la succession dont la pièce remplacée est supprimée doit disparaître"

    def test_succession_supprimee_quand_la_remplacante_disparait(self, db):
        """Côté `ref_new` : la ligne part aussi, plutôt que de pointer dans le vide.

        Pourquoi supprimer et non passer `ref_new` à NULL : le code crée
        `ref_new TEXT NOT NULL` (supersession.py) alors que les bases anciennes le
        portent nullable, et `CREATE TABLE IF NOT EXISTS` ne les fera jamais
        converger. Un `SET NULL` lèverait une contrainte sur toute base neuve.
        L'obsolescence de la pièce remplacée n'est pas perdue : elle vit dans
        `pieces.is_obsolete`, hors de cette table.
        """
        db.add_supersession('DEL2', 'CIBLE2')
        db.mark_obsolete('DEL2')

        db.delete_piece_catalog('CIBLE2')

        assert not [s for s in _successions(db) if s[1] == 'CIBLE2'], \
            "plus aucune succession ne doit désigner la remplaçante supprimée"
        assert _piece_existe(db, 'DEL2'), \
            "la pièce remplacée ne doit PAS être emportée par la suppression de sa remplaçante"
        obsolete = db.execute_query(
            "SELECT is_obsolete FROM pieces WHERE ref_piece = ?", ['DEL2'])[0][0]
        assert obsolete == 1, "l'obsolescence doit survivre à la disparition de la remplaçante"

    def test_equivalence_nettoyee_a_la_suppression(self, db):
        db.add_equivalence('EQ3', 'EQ4')
        assert _groupe_de(db, 'EQ3') is not None

        db.delete_piece_catalog('EQ3')

        assert _groupe_de(db, 'EQ3') is None, \
            "l'appartenance au groupe doit disparaître avec la pièce"

    def test_aucune_reference_orpheline_apres_suppression(self, db):
        """Invariant global : après suppression, plus aucune relation ne doit
        désigner une référence absente de `pieces`."""
        db.add_supersession('DEL5', 'CIBLE5')
        db.add_equivalence('DEL5', 'EQ5')

        db.delete_piece_catalog('DEL5')

        orphelines = db.execute_query("""
            SELECT COUNT(*) FROM piece_supersessions s
             WHERE NOT EXISTS (SELECT 1 FROM pieces p WHERE p.ref_piece = s.ref_old)
                OR (s.ref_new IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM pieces p WHERE p.ref_piece = s.ref_new))
        """)[0][0]
        orphelines += db.execute_query("""
            SELECT COUNT(*) FROM piece_equivalence_groups g
             WHERE NOT EXISTS (SELECT 1 FROM pieces p WHERE p.ref_piece = g.ref_piece)
        """)[0][0]

        assert orphelines == 0, f"{orphelines} relation(s) orpheline(s) après suppression"
