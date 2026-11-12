"""
Mixin Fiches du site — tables et écritures de la reprise des fiches produit
(CDC docs/cdc_import_fiches_site.md, § 9, étape 3).

Ne pas instancier directement : ce mixin est conçu pour être hérité par
DatabaseManager uniquement.

Modèle (toutes les colonnes ajoutées sont nullables, sans valeur par défaut
calculée : `ALTER TABLE … ADD COLUMN` ne touche que le schéma, instantané même
sur les 5 millions de liens) :
- `produits_site` : produit du site qui vend une pièce (référence interne
  unique, id_product, EAN, date de lecture). `ref_piece` suit les renommages
  (cf. `_safe_rename_piece_catalog`).
- `piece_associations.provenance` : 'description', 'table', 'les_deux' ;
  vide pour les liens PDF / CSV / saisie.
- `piece_equivalence_groups.origine` et `.ligne_fiche` : étiquette d'origine
  et n° de la ligne « Références équivalentes » de la fiche. La fusion de
  groupes (`add_equivalence`) passe par un UPDATE de group_id : elles suivent.
- `decisions_ecritures` : « même appareil » / « appareils distincts » pour une
  paire d'écritures d'une marque (§ 5.2).
- `decisions_references` : références écartées et étiquettes d'origine
  choisies, avec la forme de la référence pour l'apprentissage (§ 5.3, 5.5).
"""

from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from ...core.logger import app_logger
from . import with_query_lock

PROVENANCES = ('description', 'table', 'les_deux')


def fusion_provenance(actuelle: Optional[str], nouvelle: str) -> str:
    """Provenance d'un lien après une lecture : l'union des deux sources."""
    if not actuelle or actuelle == nouvelle:
        return nouvelle
    if 'les_deux' in (actuelle, nouvelle):
        return 'les_deux'
    return 'les_deux' if {actuelle, nouvelle} == {'description', 'table'} else nouvelle


def _paire(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


class DatabaseFichesSiteMixin:
    """Tables et primitives de la reprise des fiches du site."""

    # ── Schéma ──────────────────────────────────────────────────────────────

    def _setup_fiches_site_tables(self):
        """Créer les tables et colonnes du § 9 (idempotent)."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS produits_site (
                    ref_interne TEXT PRIMARY KEY,
                    id_product  INTEGER,
                    ref_piece   TEXT,
                    ean         TEXT,
                    lu_le       TEXT,
                    FOREIGN KEY (ref_piece) REFERENCES pieces(ref_piece) ON DELETE CASCADE
                )
            """)
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_produits_site_piece ON produits_site(ref_piece)")
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_produits_site_id ON produits_site(id_product)")
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions_ecritures (
                    marque     TEXT NOT NULL,
                    ecriture_a TEXT NOT NULL,
                    ecriture_b TEXT NOT NULL,
                    decision   TEXT NOT NULL CHECK (decision IN ('meme', 'distinct')),
                    decide_le  TEXT,
                    PRIMARY KEY (marque, ecriture_a, ecriture_b)
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions_references (
                    ref_piece TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    nature    TEXT NOT NULL CHECK (nature IN ('ecartee', 'origine')),
                    origine   TEXT,
                    forme     TEXT,
                    decide_le TEXT,
                    PRIMARY KEY (ref_piece, reference),
                    FOREIGN KEY (ref_piece) REFERENCES pieces(ref_piece) ON DELETE CASCADE
                )
            """)
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_decisions_ref_forme ON decisions_references(forme)")
            self._ajouter_colonne_si_absente('piece_associations', 'provenance', 'TEXT')
            self._ajouter_colonne_si_absente('piece_equivalence_groups', 'origine', 'TEXT')
            self._ajouter_colonne_si_absente('piece_equivalence_groups', 'ligne_fiche', 'INTEGER')
        except Exception as e:
            app_logger.error(f"Erreur création des tables des fiches du site : {e}")

    def _ajouter_colonne_si_absente(self, table: str, colonne: str, type_sql: str):
        colonnes = {r[1] for r in self.cursor.execute(f"PRAGMA table_info({table})").fetchall()}
        if colonne not in colonnes:
            self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {type_sql}")
            app_logger.info(f"Migration : colonne {table}.{colonne} ajoutée")

    # ── Lecture ─────────────────────────────────────────────────────────────

    @with_query_lock
    def produits_site_de(self, ref_piece: str) -> List[Dict]:
        rows = self.cursor.execute(
            "SELECT ref_interne, id_product, ref_piece, ean, lu_le FROM produits_site "
            "WHERE ref_piece = ? ORDER BY ref_interne", [ref_piece]).fetchall()
        return [dict(zip(('ref_interne', 'id_product', 'ref_piece', 'ean', 'lu_le'), r))
                for r in rows]

    # ── Écriture (appelées par EnregistrementFicheService, sans commit) ──────
    # Le service ouvre une seule transaction pour toute la fiche : ces
    # primitives n'appellent jamais commit, l'appelant tient _query_lock.

    def _creer_ou_promouvoir_piece(self, ref_piece: str, libelle: Optional[str],
                                   remplacer_libelle: bool) -> Tuple[int, str]:
        """Pièce principale : créée réelle, ou fantôme → réelle (liens inchangés).
        Retourne (piece_id, 'creee' | 'promue' | 'existante')."""
        row = self.cursor.execute(
            "SELECT id, is_phantom, description FROM pieces WHERE ref_piece = ?",
            [ref_piece]).fetchone()
        libelle = (libelle or '').strip() or None
        if row is None:
            cur = self.cursor.execute(
                "INSERT INTO pieces (ref_piece, description) VALUES (?, ?)", [ref_piece, libelle])
            return cur.lastrowid, 'creee'
        piece_id, fantome, description = row
        etat = 'existante'
        if fantome:
            self.cursor.execute("UPDATE pieces SET is_phantom = 0 WHERE id = ?", [piece_id])
            etat = 'promue'
        if libelle and (not description or (remplacer_libelle and description != libelle)):
            self.cursor.execute("UPDATE pieces SET description = ? WHERE id = ?",
                                [libelle, piece_id])
        return piece_id, etat

    def _ajouter_liens_provenance(self, piece_id: int,
                                  liens: Iterable[Tuple[int, str]]) -> Dict[str, int]:
        """Liens pièce → appareil avec leur provenance. Un lien présent n'est pas
        recréé (UNIQUE(piece_id, appareil_id)) : seule sa provenance est complétée."""
        compte = {'crees': 0, 'completes': 0, 'inchanges': 0}
        liens = list(dict(liens).items())
        actuelles = {}
        ids = [a for a, _ in liens]
        for i in range(0, len(ids), 500):
            lot = ids[i:i + 500]
            q = ','.join('?' * len(lot))
            actuelles.update(self.cursor.execute(
                f"SELECT appareil_id, provenance FROM piece_associations "
                f"WHERE piece_id = ? AND appareil_id IN ({q})", [piece_id] + lot).fetchall())
        nouveaux, maj = [], []
        for appareil_id, provenance in liens:
            if appareil_id not in actuelles:
                nouveaux.append((piece_id, appareil_id, provenance))
                continue
            fusion = fusion_provenance(actuelles[appareil_id], provenance)
            if fusion != actuelles[appareil_id]:
                maj.append((fusion, piece_id, appareil_id))
            else:
                compte['inchanges'] += 1
        if nouveaux:
            self.cursor.executemany(
                "INSERT OR IGNORE INTO piece_associations (piece_id, appareil_id, provenance) "
                "VALUES (?, ?, ?)", nouveaux)
        if maj:
            self.cursor.executemany(
                "UPDATE piece_associations SET provenance = ? WHERE piece_id = ? AND appareil_id = ?",
                maj)
        compte['crees'], compte['completes'] = len(nouveaux), len(maj)
        return compte

    def _definir_origines(self, origines: Iterable[Tuple[str, Optional[str], Optional[int]]]) -> int:
        """Étiquette d'origine et n° de ligne des membres de groupe (une valeur
        déjà posée n'est remplacée que par une valeur non vide)."""
        n = 0
        for ref, origine, ligne in origines:
            cur = self.cursor.execute(
                "UPDATE piece_equivalence_groups SET origine = COALESCE(?, origine), "
                "ligne_fiche = COALESCE(?, ligne_fiche) WHERE ref_piece = ?",
                [origine or None, ligne, ref])
            n += cur.rowcount
        return n

    def _enregistrer_produit_site(self, ref_interne: str, id_product: Optional[int],
                                  ref_piece: str, ean: Optional[str], lu_le: str):
        """Produit du site : le site fait foi (id_product, EAN). Un EAN absent de
        la lecture ne vide pas celui déjà connu."""
        self.cursor.execute("""
            INSERT INTO produits_site (ref_interne, id_product, ref_piece, ean, lu_le)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ref_interne) DO UPDATE SET
                id_product = COALESCE(excluded.id_product, produits_site.id_product),
                ref_piece  = excluded.ref_piece,
                ean        = COALESCE(excluded.ean, produits_site.ean),
                lu_le      = excluded.lu_le
        """, [ref_interne, id_product, ref_piece, ean or None, lu_le])

    def _enregistrer_decisions_ecritures(self, decisions: Iterable[Tuple[str, str, str, str]],
                                         le: str) -> int:
        lignes = []
        for marque, a, b, decision in decisions:
            if a == b:
                continue
            x, y = _paire(a, b)
            lignes.append((marque, x, y, decision, le))
        self.cursor.executemany(
            "INSERT OR REPLACE INTO decisions_ecritures VALUES (?, ?, ?, ?, ?)", lignes)
        return len(lignes)

    def _enregistrer_decisions_references(
            self, decisions: Iterable[Tuple[str, str, str, Optional[str], str]], le: str) -> int:
        lignes = [(p, r, n, o, f, le) for p, r, n, o, f in decisions]
        self.cursor.executemany(
            "INSERT OR REPLACE INTO decisions_references VALUES (?, ?, ?, ?, ?, ?)", lignes)
        return len(lignes)


def decisions_ecritures_en_memoire(rows: Iterable[Tuple[str, str, str, str]]
                                   ) -> Dict[Tuple[str, FrozenSet[str]], str]:
    """Lignes (marque, A, B, décision) → forme attendue par rapprocher()."""
    return {(m, frozenset((a, b))): d for m, a, b, d in rows}
