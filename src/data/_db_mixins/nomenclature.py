"""
Mixin Règles de nomenclature — tables et primitives (CDC
docs/cdc_regles_nomenclature.md § 5, lot 3).

Ne pas instancier directement : ce mixin est conçu pour être hérité par
DatabaseManager uniquement.

- `regles_nomenclature` : une règle « motif de référence → type », avec sa
  portée (marque ou groupe), sa clé (`nom` = réf. commerciale, `code` = code
  usine numérique), son statut (proposée / validée / rejetée), sa source et
  ses mesures (couverture, accord) au dernier calcul.
- `propositions_type` : au plus une proposition par appareil, recalculée en
  entier par le moteur. Aucune écriture de type ici : l'application passera
  par la revue (lot 4) et la sauvegarde événementielle.

Lot 4 : `lots_acceptation_type` + `acceptations_type` (acceptations annulables, § 5.3)
et les lectures de la revue et de l'écran Règles.

Les suppressions en cascade sont doublées de déclencheurs : elles valent même
si `Config.FOREIGN_KEYS` est désactivé. La table `appareils` n'est pas touchée.

Dépendances attendues sur self (fournies par DatabaseManager.__init__) :
    self.cursor, self.conn, self._query_lock
"""

from collections import Counter
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ...core.logger import app_logger
from . import with_query_lock

COLONNES_REGLE = ('id', 'portee', 'cible', 'cle', 'forme', 'motif', 'type_resultat', 'statut',
                  'origine', 'source_url', 'note', 'couverture', 'accord', 'calcule_le',
                  'valide_le')
COLONNES_PROPOSITION = ('appareil_id', 'type_actuel', 'type_propose', 'regle_id', 'force',
                        'signaux', 'cree_le')

# Paquets de paramètres (limite de variables SQLite)
_PAQUET = 900


class DatabaseNomenclatureMixin:
    """Tables des règles de nomenclature et de leurs propositions de type."""

    # ── Schéma ──────────────────────────────────────────────────────────────

    def _setup_nomenclature_tables(self):
        """Créer les deux tables, leurs index et déclencheurs (idempotent)."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS regles_nomenclature (
                    id            INTEGER PRIMARY KEY,
                    portee        TEXT NOT NULL CHECK (portee IN ('marque', 'groupe')),
                    cible         TEXT NOT NULL,
                    cle           TEXT NOT NULL CHECK (cle IN ('nom', 'code')),
                    forme         TEXT NOT NULL CHECK (forme IN ('prefixe', 'position', 'gabarit')),
                    motif         TEXT NOT NULL,
                    type_resultat TEXT NOT NULL,
                    statut        TEXT NOT NULL DEFAULT 'proposee'
                                  CHECK (statut IN ('proposee', 'validee', 'rejetee')),
                    origine       TEXT NOT NULL CHECK (origine IN ('decouverte', 'web', 'saisie')),
                    source_url    TEXT,
                    note          TEXT,
                    couverture    INTEGER,
                    accord        INTEGER,
                    calcule_le    TEXT,
                    valide_le     TEXT,
                    UNIQUE (portee, cible, cle, motif)
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS propositions_type (
                    appareil_id  INTEGER PRIMARY KEY
                                 REFERENCES appareils(id) ON DELETE CASCADE,
                    type_actuel  TEXT,
                    type_propose TEXT NOT NULL,
                    regle_id     INTEGER REFERENCES regles_nomenclature(id) ON DELETE CASCADE,
                    force        TEXT NOT NULL CHECK (force IN ('forte', 'simple')),
                    signaux      TEXT,
                    cree_le      TEXT NOT NULL
                )
            """)
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_propositions_type_regle "
                                "ON propositions_type(regle_id)")
            self.cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_propositions_appareil_supprime
                AFTER DELETE ON appareils
                BEGIN
                    DELETE FROM propositions_type WHERE appareil_id = OLD.id;
                END
            """)
            self.cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_propositions_regle_supprimee
                AFTER DELETE ON regles_nomenclature
                BEGIN
                    DELETE FROM propositions_type WHERE regle_id = OLD.id;
                END
            """)
            # Lot 4 : acceptations de propositions, par lot (une décision de
            # l'écran = un lot), pour pouvoir les annuler (CDC § 5.3, D8)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS lots_acceptation_type (
                    id          INTEGER PRIMARY KEY,
                    regle_id    INTEGER,
                    libelle     TEXT NOT NULL,
                    accepte_le  TEXT NOT NULL,
                    nb          INTEGER NOT NULL,
                    annule_le   TEXT
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS acceptations_type (
                    lot_id      INTEGER NOT NULL REFERENCES lots_acceptation_type(id)
                                ON DELETE CASCADE,
                    appareil_id INTEGER NOT NULL,
                    type_avant  TEXT,
                    type_apres  TEXT NOT NULL,
                    PRIMARY KEY (lot_id, appareil_id)
                )
            """)
            self.cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_acceptations_appareil_supprime
                AFTER DELETE ON appareils
                BEGIN
                    DELETE FROM acceptations_type WHERE appareil_id = OLD.id;
                END
            """)
        except Exception as e:
            app_logger.error(f"Erreur création tables des règles de nomenclature : {e}")

    # ── Règles ──────────────────────────────────────────────────────────────

    @with_query_lock
    def lister_regles_nomenclature(self, statut: Optional[str] = None) -> List[dict]:
        """Règles (toutes, ou d'un statut), en dictionnaires."""
        sql = f"SELECT {', '.join(COLONNES_REGLE)} FROM regles_nomenclature"
        params: list = []
        if statut:
            sql += " WHERE statut = ?"
            params.append(statut)
        try:
            self.cursor.execute(sql + " ORDER BY id", params)
            return [dict(zip(COLONNES_REGLE, r)) for r in self.cursor.fetchall()]
        except Exception as e:
            app_logger.error(f"Lecture des règles de nomenclature échouée : {e}")
            return []

    @with_query_lock
    def inserer_regles_nomenclature(self, regles: Iterable[dict]) -> int:
        """Ajouter des règles ; une règle déjà présente (même portée, cible, clé,
        motif) est laissée telle quelle — jamais écrasée. Renvoie le nombre
        ajouté (0 en cas d'échec, journalisé ; rien n'est écrit alors)."""
        colonnes = [c for c in COLONNES_REGLE if c != 'id']
        lignes = [tuple(r.get(c) for c in colonnes) for r in regles]
        if not lignes:
            return 0
        try:
            avant = self.conn.total_changes
            self.cursor.executemany(
                f"INSERT OR IGNORE INTO regles_nomenclature ({', '.join(colonnes)}) "
                f"VALUES ({', '.join('?' * len(colonnes))})", lignes)
            self.conn.commit()
            return self.conn.total_changes - avant
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Ajout des règles de nomenclature échoué : {e}")
            return 0

    @with_query_lock
    def enregistrer_mesures_regles(self, mesures: Dict[int, Tuple[int, int]], horodatage: str) -> bool:
        """Couverture et accord de chaque règle au dernier calcul ({id: (couverture, accord)})."""
        try:
            self.cursor.executemany(
                "UPDATE regles_nomenclature SET couverture = ?, accord = ?, calcule_le = ? "
                "WHERE id = ?",
                [(c, a, horodatage, i) for i, (c, a) in mesures.items()])
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Mesures des règles de nomenclature non enregistrées : {e}")
            return False

    @with_query_lock
    def changer_statut_regle(self, regle_id: int, statut: str, horodatage: Optional[str]) -> bool:
        """Statut d'une règle (écran Règles, lot 4) ; `valide_le` suit le statut
        (posé à la validation, effacé sinon)."""
        try:
            self.cursor.execute(
                "UPDATE regles_nomenclature SET statut = ?, valide_le = ? WHERE id = ?",
                (statut, horodatage if statut == 'validee' else None, regle_id))
            self.conn.commit()
            return self.cursor.rowcount == 1
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Statut de la règle {regle_id} non enregistré : {e}")
            return False

    @with_query_lock
    def enregistrer_note_regle(self, regle_id: int, note: Optional[str]) -> bool:
        try:
            self.cursor.execute("UPDATE regles_nomenclature SET note = ? WHERE id = ?",
                                (note or None, regle_id))
            self.conn.commit()
            return self.cursor.rowcount == 1
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Note de la règle {regle_id} non enregistrée : {e}")
            return False

    # ── Propositions ────────────────────────────────────────────────────────

    @with_query_lock
    def lire_propositions_detaillees(self) -> Optional[List[dict]]:
        """Propositions jointes à l'appareil et à leur règle (revue, lot 4) ;
        None si la lecture a échoué."""
        colonnes = ('appareil_id', 'type_actuel', 'type_propose', 'regle_id', 'force', 'signaux',
                    'type_en_base', 'manufacturer', 'ref_modele', 'commercial_ref', 'other_ref',
                    'portee', 'cible', 'motif', 'origine', 'source_url')
        try:
            self.cursor.execute("""
                SELECT p.appareil_id, p.type_actuel, p.type_propose, p.regle_id, p.force,
                       p.signaux, a.type, a.manufacturer, a.ref_modele, a.commercial_ref,
                       a.other_ref, r.portee, r.cible, r.motif, r.origine, r.source_url
                FROM propositions_type p
                JOIN appareils a ON a.id = p.appareil_id
                LEFT JOIN regles_nomenclature r ON r.id = p.regle_id
                ORDER BY p.regle_id, p.appareil_id
            """)
            return [dict(zip(colonnes, r)) for r in self.cursor.fetchall()]
        except Exception as e:
            app_logger.error(f"Lecture détaillée des propositions de type échouée : {e}")
            return None

    @with_query_lock
    def supprimer_propositions_type(self, appareil_ids: Iterable[int]) -> int:
        """Retirer les propositions des appareils donnés (acceptées ou refusées)."""
        ids = list(dict.fromkeys(appareil_ids))
        retirees = 0
        try:
            for debut in range(0, len(ids), _PAQUET):
                lot = ids[debut:debut + _PAQUET]
                self.cursor.execute("DELETE FROM propositions_type WHERE appareil_id IN "
                                    f"({','.join('?' * len(lot))})", lot)
                retirees += self.cursor.rowcount
            self.conn.commit()
            return retirees
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Retrait des propositions de type échoué : {e}")
            return 0

    @with_query_lock
    def lire_types_appareils(self, appareil_ids: Iterable[int]) -> Dict[int, Optional[str]]:
        """{id: type} des appareils présents parmi ceux donnés."""
        ids = list(dict.fromkeys(appareil_ids))
        types: Dict[int, Optional[str]] = {}
        for debut in range(0, len(ids), _PAQUET):
            lot = ids[debut:debut + _PAQUET]
            self.cursor.execute(f"SELECT id, type FROM appareils WHERE id IN "
                                f"({','.join('?' * len(lot))})", lot)
            types.update(self.cursor.fetchall())
        return types

    @with_query_lock
    def lister_marques_appareils(self) -> List[str]:
        """Marques distinctes (telles qu'écrites en base)."""
        self.cursor.execute("SELECT DISTINCT manufacturer FROM appareils "
                            "WHERE manufacturer IS NOT NULL AND manufacturer <> ''")
        return [r[0] for r in self.cursor.fetchall()]

    @with_query_lock
    def lire_appareils_des_marques(self, marques: Iterable[str]) -> List[tuple]:
        """Comme lire_appareils_nomenclature, limité aux marques données (écrites
        comme en base) : exemples d'une règle sans relire toute la base."""
        marques = list(dict.fromkeys(marques))
        lignes: List[tuple] = []
        for debut in range(0, len(marques), _PAQUET):
            lot = marques[debut:debut + _PAQUET]
            self.cursor.execute(
                "SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref "
                f"FROM appareils WHERE manufacturer IN ({','.join('?' * len(lot))})", lot)
            lignes.extend(self.cursor.fetchall())
        return lignes

    # ── Acceptations (lot 4, annulables) ────────────────────────────────────

    @with_query_lock
    def enregistrer_lot_acceptation(self, regle_id: Optional[int], libelle: str,
                                    horodatage: str, lignes: List[Tuple[int, str, str]]) -> Optional[int]:
        """Un lot d'acceptations : [(appareil_id, type_avant, type_apres)].
        Renvoie l'id du lot, ou None en cas d'échec (journalisé)."""
        try:
            self.cursor.execute(
                "INSERT INTO lots_acceptation_type (regle_id, libelle, accepte_le, nb) "
                "VALUES (?, ?, ?, ?)", (regle_id, libelle, horodatage, len(lignes)))
            lot_id = self.cursor.lastrowid
            self.cursor.executemany(
                "INSERT INTO acceptations_type (lot_id, appareil_id, type_avant, type_apres) "
                "VALUES (?, ?, ?, ?)", [(lot_id, a, av, ap) for a, av, ap in lignes])
            self.conn.commit()
            return lot_id
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Lot d'acceptation non enregistré : {e}")
            return None

    @with_query_lock
    def lister_lots_acceptation(self, limite: int = 50) -> List[dict]:
        colonnes = ('id', 'regle_id', 'libelle', 'accepte_le', 'nb', 'annule_le')
        try:
            self.cursor.execute(f"SELECT {', '.join(colonnes)} FROM lots_acceptation_type "
                                "ORDER BY id DESC LIMIT ?", (limite,))
            return [dict(zip(colonnes, r)) for r in self.cursor.fetchall()]
        except Exception as e:
            app_logger.error(f"Lecture des lots d'acceptation échouée : {e}")
            return []

    @with_query_lock
    def lire_acceptations(self, lot_id: int) -> List[Tuple[int, Optional[str], str]]:
        """[(appareil_id, type_avant, type_apres)] d'un lot."""
        self.cursor.execute("SELECT appareil_id, type_avant, type_apres FROM acceptations_type "
                            "WHERE lot_id = ? ORDER BY appareil_id", (lot_id,))
        return [tuple(r) for r in self.cursor.fetchall()]

    @with_query_lock
    def marquer_lot_annule(self, lot_id: int, horodatage: str) -> bool:
        try:
            self.cursor.execute("UPDATE lots_acceptation_type SET annule_le = ? WHERE id = ?",
                                (horodatage, lot_id))
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Annulation du lot {lot_id} non enregistrée : {e}")
            return False

    @with_query_lock
    def remplacer_propositions_type(self, propositions: Iterable[tuple]) -> int:
        """Remplacer TOUTES les propositions par celles du dernier calcul, en une
        transaction (en cas d'échec, les précédentes restent).

        Args:
            propositions: tuples dans l'ordre de COLONNES_PROPOSITION.
        Returns:
            Nombre écrit, ou -1 en cas d'échec (journalisé).
        """
        lignes = list(propositions)
        try:
            self.cursor.execute("DELETE FROM propositions_type")
            self.cursor.executemany(
                f"INSERT INTO propositions_type ({', '.join(COLONNES_PROPOSITION)}) "
                f"VALUES ({', '.join('?' * len(COLONNES_PROPOSITION))})", lignes)
            self.conn.commit()
            return len(lignes)
        except Exception as e:
            self.conn.rollback()
            app_logger.error(f"Propositions de type non enregistrées : {e}")
            return -1

    @with_query_lock
    def lire_propositions_type(self) -> List[dict]:
        try:
            self.cursor.execute(f"SELECT {', '.join(COLONNES_PROPOSITION)} FROM propositions_type "
                                "ORDER BY appareil_id")
            return [dict(zip(COLONNES_PROPOSITION, r)) for r in self.cursor.fetchall()]
        except Exception as e:
            app_logger.error(f"Lecture des propositions de type échouée : {e}")
            return []

    # ── Lectures pour le moteur ─────────────────────────────────────────────

    @with_query_lock
    def lire_appareils_nomenclature(self) -> List[tuple]:
        """(id, type, marque, ref_modele, commercial_ref, other_ref) de tous les appareils."""
        self.cursor.execute("SELECT id, type, manufacturer, ref_modele, commercial_ref, other_ref "
                            "FROM appareils")
        return self.cursor.fetchall()

    @with_query_lock
    def lire_refus_du_champ(self, champ: str) -> Optional[Set[Tuple[int, str]]]:
        """Tous les refus d'un champ : {(appareil_id, valeur en minuscules)} ;
        None si la lecture a échoué (l'appelant ne propose alors rien)."""
        try:
            self.cursor.execute("SELECT appareil_id, valeur FROM refus_completions WHERE champ = ?",
                                (champ,))
            return {(a, v) for a, v in self.cursor.fetchall()}
        except Exception as e:
            app_logger.error(f"Lecture des refus « {champ} » échouée : {e}")
            return None

    @with_query_lock
    def types_par_piece_partagee(self, appareil_ids: Iterable[int]) -> Dict[int, Counter]:
        """Vote des pièces (§ 7) : pour chaque appareil, le nombre d'AUTRES
        appareils de chaque type qui partagent au moins une de ses pièces
        (compté par pièce partagée ; l'appareil lui-même est exclu)."""
        ids = list(dict.fromkeys(appareil_ids))
        pieces_de: Dict[int, List[int]] = {}
        for debut in range(0, len(ids), _PAQUET):
            lot = ids[debut:debut + _PAQUET]
            self.cursor.execute(
                "SELECT appareil_id, piece_id FROM piece_associations "
                f"WHERE appareil_id IN ({','.join('?' * len(lot))})", lot)
            for a, p in self.cursor.fetchall():
                pieces_de.setdefault(a, []).append(p)
        toutes = list({p for ps in pieces_de.values() for p in ps})
        types_piece: Dict[int, Counter] = {}
        for debut in range(0, len(toutes), _PAQUET):
            lot = toutes[debut:debut + _PAQUET]
            self.cursor.execute(
                "SELECT pa.piece_id, COALESCE(a.type, ''), COUNT(*) FROM piece_associations pa "
                "JOIN appareils a ON a.id = pa.appareil_id "
                f"WHERE pa.piece_id IN ({','.join('?' * len(lot))}) GROUP BY 1, 2", lot)
            for p, t, n in self.cursor.fetchall():
                types_piece.setdefault(p, Counter())[t] += n
        votes: Dict[int, Counter] = {}
        type_de: Dict[int, str] = {}
        appareils = list(pieces_de)
        for debut in range(0, len(appareils), _PAQUET):
            lot = appareils[debut:debut + _PAQUET]
            self.cursor.execute("SELECT id, COALESCE(type, '') FROM appareils "
                                f"WHERE id IN ({','.join('?' * len(lot))})", lot)
            type_de.update(self.cursor.fetchall())
        for a, pieces in pieces_de.items():
            c: Counter = Counter()
            for p in pieces:
                c.update(types_piece.get(p, {}))
                c[type_de.get(a, '')] -= 1   # l'appareil lui-même
            votes[a] = +c
        return votes
