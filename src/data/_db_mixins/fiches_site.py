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
- `piece_supersessions.rang_fiche` : position de l'ancienne référence dans la
  ligne « Remplace les références » de la fiche, pour la réécrire dans le même
  ordre (paires Whirlpool / Indesit, Beko). Vide = ordre de la chaîne.
- `decisions_ecritures` : « même appareil » / « appareils distincts » pour une
  paire d'écritures d'une marque (§ 5.2).
- `decisions_champs` : « garder l'outil » choisi pour un champ d'un appareil
  connu que la fiche donne autrement, avec la valeur du site. Les écrans à
  questions sont retirés (§ 10.20) : la table n'est plus écrite, seulement lue.
- `decisions_references` : références écartées et étiquettes d'origine
  choisies, avec la forme de la référence pour l'apprentissage (§ 5.3, 5.5).
- Reprise en masse (§ 7.3, étape 4) : `reprise_site_etat` (une ligne : dernier
  id_produit traité, export en cours), `reprise_site_lots` (journal des lots
  enregistrés, mesures comprises) et `reprise_site_de_cote` (fiches mises de
  côté, à reprendre plus tard).
"""

from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

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
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions_champs (
                    appareil_id INTEGER NOT NULL,
                    champ       TEXT NOT NULL,
                    valeur_site TEXT,
                    decide_le   TEXT,
                    PRIMARY KEY (appareil_id, champ),
                    FOREIGN KEY (appareil_id) REFERENCES appareils(id) ON DELETE CASCADE
                )
            """)
            # Fiches du site à refaire depuis les PDF (§ 10.14) : une par pièce
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS fiches_a_refaire (
                    ref_piece  TEXT PRIMARY KEY,
                    id_product INTEGER,
                    raison     TEXT,
                    en_vrac    INTEGER,
                    creations  INTEGER,
                    retenues   INTEGER,
                    exemples   TEXT,
                    releve_le  TEXT
                )
            """)
            # Référence associée Whirlpool / Indesit / Beko (§ 10.17) : NULL = « aucune »
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS references_associees (
                    ref_piece TEXT PRIMARY KEY,
                    associee  TEXT,
                    decide_le TEXT
                )
            """)
            self._setup_reprise_site_tables()
            self._ajouter_colonne_si_absente('piece_associations', 'provenance', 'TEXT')
            self._ajouter_colonne_si_absente('piece_equivalence_groups', 'origine', 'TEXT')
            self._ajouter_colonne_si_absente('piece_equivalence_groups', 'ligne_fiche', 'INTEGER')
            self._ajouter_colonne_si_absente('piece_supersessions', 'rang_fiche', 'INTEGER')
            # Export EveryParts des fiches reprises (§ 10.19) : date du dernier export
            self._ajouter_colonne_si_absente('produits_site', 'exporte_le', 'TEXT')
        except Exception as e:
            app_logger.error(f"Erreur création des tables des fiches du site : {e}")
        self._reparer_jumelles_d_equivalentes()

    def _reparer_jumelles_d_equivalentes(self) -> int:
        """Réparation à l'ouverture : la jumelle d'une équivalente de ligne N ≥ 1 a pu
        être marquée « ligne 0 » (lien posé avant que `_ligne_de_la_jumelle` ne suive
        la ligne de la pièce) et monter à tort dans le code produit de la fiche
        (488000537573, jumelle de C00537573, dans celui de C00140702). Elle reprend
        la ligne de sa pièce. Retourne le nombre de jumelles réparées."""
        try:
            with self._query_lock:
                fausses = self.cursor.execute("""
                    SELECT a.ref_piece, p.ligne_fiche
                    FROM references_associees ra
                    JOIN piece_equivalence_groups p ON p.ref_piece = ra.ref_piece
                    JOIN piece_equivalence_groups a ON a.ref_piece = ra.associee
                    WHERE a.ligne_fiche = 0 AND p.ligne_fiche >= 1
                      AND NOT EXISTS (SELECT 1 FROM produits_site s WHERE s.ref_piece = ra.ref_piece)
                      AND NOT EXISTS (SELECT 1 FROM piece_supersessions s WHERE s.ref_old = ra.ref_piece)
                """).fetchall()
                if not fausses:
                    return 0
                self.cursor.executemany(
                    "UPDATE piece_equivalence_groups SET ligne_fiche = ? WHERE ref_piece = ?",
                    [(ligne, ref) for ref, ligne in fausses])
                self.conn.commit()
            app_logger.info(f"Réparation : {len(fausses)} réf. associée(s) d'équivalente remise(s) "
                            f"sur la ligne de leur pièce ({', '.join(r for r, _ in fausses[:10])})")
            return len(fausses)
        except Exception as e:
            app_logger.error(f"Réparation des réf. associées d'équivalentes impossible : {e}")
            return 0

    # --- Export EveryParts des fiches reprises (§ 10.19) ---------------------------
    def produits_site_reprises(self, non_exportes: bool = False) -> List[Dict]:
        """Produits du site repris, par n° de produit. `non_exportes` : jamais
        exportés, ou relus (lu_le) depuis leur dernier export."""
        condition = ("WHERE exporte_le IS NULL OR (lu_le IS NOT NULL AND lu_le > exporte_le)"
                     if non_exportes else "")
        with self._query_lock:
            rows = self.cursor.execute(
                f"SELECT ref_interne, id_product, ref_piece, ean, lu_le, exporte_le "
                f"FROM produits_site {condition} ORDER BY id_product, ref_interne").fetchall()
        cles = ('ref_interne', 'id_product', 'ref_piece', 'ean', 'lu_le', 'exporte_le')
        return [dict(zip(cles, r)) for r in rows]

    def marquer_produits_exportes(self, refs_internes: Iterable[str], le: str) -> int:
        refs = [r for r in dict.fromkeys(refs_internes) if r]
        with self._query_lock:
            for i in range(0, len(refs), 500):
                lot = refs[i:i + 500]
                self.cursor.execute(
                    f"UPDATE produits_site SET exporte_le = ? WHERE ref_interne IN "
                    f"({','.join('?' * len(lot))})", [le] + lot)
            self.conn.commit()
        return len(refs)

    # --- Référence associée Whirlpool / Indesit / Beko (§ 10.17) ---------------------
    def reference_associee(self, ref_piece: str) -> Tuple[bool, Optional[str]]:
        """(réponse connue, référence associée ; None = « aucune »). Sans réponse
        mémorisée : l'équivalente de la ligne 0 (2ᵉ réf. du code produit d'une fiche
        reprise), proposée mais non connue."""
        if not ref_piece:
            return False, None
        with self._query_lock:
            row = self.cursor.execute(
                "SELECT associee FROM references_associees WHERE ref_piece = ?",
                [ref_piece]).fetchone()
            if row is not None:
                return True, row[0]
            row = self.cursor.execute(
                "SELECT e.ref_piece FROM piece_equivalence_groups e "
                "JOIN piece_equivalence_groups p ON p.group_id = e.group_id "
                "WHERE p.ref_piece = ? AND e.ref_piece != ? AND e.ligne_fiche = 0 "
                "ORDER BY e.ref_piece LIMIT 1", [ref_piece, ref_piece]).fetchone()
        return False, (row[0] if row else None)

    def references_associees_de(self, ref_piece: str) -> Set[str]:
        """Références associées retenues pour la pièce, dans les deux sens
        (C00138863 ↔ 482000029398) : elles vont à la suite dans le code produit."""
        if not ref_piece:
            return set()
        with self._query_lock:
            rows = self.cursor.execute(
                "SELECT associee FROM references_associees WHERE ref_piece = ? AND associee IS NOT NULL "
                "UNION SELECT ref_piece FROM references_associees WHERE associee = ?",
                [ref_piece, ref_piece]).fetchall()
        return {r[0] for r in rows if r[0] and r[0] != ref_piece}

    def paires_associees_parmi(self, refs: Iterable[str]) -> List[Tuple[str, str]]:
        """Paires (principale, associée) mémorisées dont les DEUX références sont
        dans `refs` : dans la Fiche complète, chacune va à la suite de sa jumelle,
        sur la même ligne. Ordre stable : décision la plus ancienne d'abord."""
        refs = list(dict.fromkeys(r for r in refs if r))
        if len(refs) < 2:
            return []
        q = ','.join('?' * len(refs))
        with self._query_lock:
            rows = self.cursor.execute(
                f"SELECT ref_piece, associee FROM references_associees "
                f"WHERE associee IS NOT NULL AND ref_piece IN ({q}) AND associee IN ({q}) "
                f"ORDER BY decide_le, ref_piece", refs + refs).fetchall()
        return [(p, a) for p, a in rows if p != a]

    def refs_avec_reponse_associee(self) -> Set[str]:
        """Réfs dont la réf. associée est renseignée : l'une ou l'autre d'une paire,
        ou une réponse « aucune » (filtre « Jumelle à renseigner »)."""
        with self._query_lock:
            rows = self.cursor.execute(
                "SELECT ref_piece FROM references_associees "
                "UNION SELECT associee FROM references_associees WHERE associee IS NOT NULL"
            ).fetchall()
        return {r[0] for r in rows if r[0]}

    def reference_principale_de(self, ref: str) -> Optional[str]:
        """Référence principale d'une référence associée (« ⇄ » ou réponse de
        l'import) : elle vient en premier dans le code produit. None : `ref` n'est
        l'associée d'aucune pièce."""
        if not ref:
            return None
        with self._query_lock:
            row = self.cursor.execute(
                "SELECT ref_piece FROM references_associees WHERE associee = ? "
                "ORDER BY decide_le DESC LIMIT 1", [ref]).fetchone()
        return row[0] if row else None

    def definir_references_associees(self, reponses: Iterable[Tuple[str, Optional[str]]],
                                     le: str, origines: Optional[Dict[str, str]] = None) -> int:
        """Mémorise chaque réponse (référence associée, ou None = « aucune »). Une
        référence associée devient une équivalente de la pièce, avec sa marque
        d'origine, sur la même ligne de la fiche que la pièce (`_ligne_de_la_jumelle`) :
        ligne 0 (code produit, § 8.1) en général, la ligne de la pièce si celle-ci
        est une équivalente d'une autre ligne, aucune si la pièce est une ancienne
        référence (sa jumelle la suit dans « Remplace »). Retourne le nombre de réponses."""
        n = 0
        for ref, associee in reponses:
            ref = (ref or '').strip()
            associee = (associee or '').strip() or None
            if not ref or associee == ref:
                continue
            if associee:
                ok, message = self.add_equivalence(ref, associee)
                if not ok:
                    app_logger.warning(f"Référence associée {ref} ≡ {associee} : {message}")
            with self._query_lock:
                self.cursor.execute(
                    "INSERT OR REPLACE INTO references_associees (ref_piece, associee, decide_le) "
                    "VALUES (?, ?, ?)", [ref, associee, le])
                if associee:
                    ligne = self._ligne_de_la_jumelle(ref)
                    self.cursor.execute(
                        "UPDATE piece_equivalence_groups SET "
                        + ("" if ligne is None else "ligne_fiche = ?, ")
                        + "origine = COALESCE(origine, ?) WHERE ref_piece = ?",
                        ([] if ligne is None else [ligne])
                        + [(origines or {}).get(associee), associee])
                self.conn.commit()
            n += 1
        return n

    def _ligne_de_la_jumelle(self, ref: str) -> Optional[int]:
        """Ligne de la fiche que prend la jumelle de `ref` (sous verrou) : la même
        que `ref`. None = ne pas y toucher (`ref` est une ancienne référence) ;
        0 = code produit (`ref` est la pièce d'un produit du site, ou n'a pas de
        ligne) ; N = `ref` est une équivalente de la ligne N (C00537573, ligne 1 de
        la fiche de C00140702 : sa jumelle 488000537573 reste avec elle, pas dans
        le code produit)."""
        if self.cursor.execute("SELECT 1 FROM piece_supersessions WHERE ref_old = ? LIMIT 1",
                               [ref]).fetchone():
            return None
        if self.cursor.execute("SELECT 1 FROM produits_site WHERE ref_piece = ? LIMIT 1",
                               [ref]).fetchone():
            return 0
        row = self.cursor.execute(
            "SELECT ligne_fiche FROM piece_equivalence_groups WHERE ref_piece = ?",
            [ref]).fetchone()
        return row[0] if row and row[0] else 0

    def lier_paires_fiche(self, paires: Iterable[Tuple[str, str]], le: str) -> int:
        """Paires Whirlpool / Indesit / Beko des lignes « Remplace » et « Équivalentes » (CDC
        § 5.4) : chaque paire devient réf. associée et équivalente, comme la paire
        du code produit, mais SANS la marque « ligne 0 » (ce sont d'anciennes
        références, pas le code produit). Une réponse déjà mémorisée pour l'une
        des deux n'est jamais remplacée. Retourne le nombre de paires liées."""
        n = 0
        for principale, associee in paires:
            principale, associee = (principale or '').strip(), (associee or '').strip()
            if not principale or not associee or principale == associee:
                continue
            with self._query_lock:
                deja = self.cursor.execute(
                    "SELECT 1 FROM references_associees WHERE ref_piece IN (?, ?) "
                    "OR associee IN (?, ?) LIMIT 1",
                    [principale, associee, principale, associee]).fetchone()
            if deja:
                continue
            ok, message = self.add_equivalence(principale, associee)
            if not ok:
                app_logger.warning(f"Paire {principale} ≡ {associee} : {message}")
                continue
            with self._query_lock:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO references_associees (ref_piece, associee, decide_le) "
                    "VALUES (?, ?, ?)", [principale, associee, le])
                self.conn.commit()
            n += 1
        return n

    # --- Réf. associée depuis le gestionnaire de pièces ------------------------------
    def motif_refus_associee(self, principale: str, associee: str) -> str:
        """Motif du refus de lier `associee` comme réf. associée de `principale`
        ('' = possible) : l'une n'existe pas, n'est pas Whirlpool / Indesit / Beko,
        les deux sont du même groupe ou l'une a déjà une autre jumelle. Sans écrire."""
        from src.utils.rapprochement_fiche.associee import autres_origines, origine_associable
        principale, associee = (principale or '').strip(), (associee or '').strip()
        if not principale or not associee or principale == associee:
            return "Choisissez deux références différentes."
        for ref in (principale, associee):
            if not self.lire_piece_exacte(ref):
                return f"{ref} n'existe pas dans les pièces. Créez-la d'abord (Nouvelle pièce)."
        origine_p, origine_a = origine_associable(principale), origine_associable(associee)
        for ref, origine in ((principale, origine_p), (associee, origine_a)):
            if not origine:
                return (f"{ref} n'est ni Whirlpool, ni Indesit, ni Beko : "
                        f"elle ne peut pas avoir de réf. associée.")
        if origine_p == origine_a:
            return (f"Deux réf. {origine_p} ne peuvent pas être jumelles : la réf. "
                    f"associée doit être {autres_origines(origine_p)}.")
        for ref in (principale, associee):
            jumelles = self.references_associees_de(ref) - {principale, associee}
            if jumelles:
                return f"{ref} est déjà liée à {sorted(jumelles)[0]}. Retirez d'abord ce lien."
        return ''

    def lier_reference_associee(self, principale: str, associee: str,
                                le: str) -> Tuple[bool, str]:
        """Lien posé à la main (gestionnaire de pièces) : mêmes effets que la réponse
        de l'import (équivalence, ligne 0 sauf ancienne réf.). Refusé, avec le motif
        (`motif_refus_associee`). Une réponse « aucune » de l'une ou l'autre est
        remplacée : le lien explicite l'emporte."""
        from src.utils.rapprochement_fiche.associee import origine_associable
        motif = self.motif_refus_associee(principale, associee)
        if motif:
            return False, motif
        principale, associee = principale.strip(), associee.strip()
        if principale in self.references_associees_de(associee):
            return True, ""                          # déjà jumelles : rien à faire
        with self._query_lock:
            self.cursor.execute(
                "DELETE FROM references_associees WHERE ref_piece IN (?, ?) AND associee IS NULL",
                [principale, associee])
            self.conn.commit()
        self.definir_references_associees([(principale, associee)], le,
                                          {associee: origine_associable(associee)})
        return True, ""

    def retirer_reference_associee(self, ref: str) -> Optional[str]:
        """Défait la paire dont `ref` fait partie (dans un sens ou dans l'autre).
        L'équivalence est gardée : seul le rôle de jumelle disparaît, et avec lui
        la marque « ligne 0 » de l'associée (sinon elle serait reproposée aussitôt).
        Retourne la jumelle retirée, ou None."""
        if not ref:
            return None
        with self._query_lock:
            row = self.cursor.execute(
                "SELECT ref_piece, associee FROM references_associees "
                "WHERE associee IS NOT NULL AND (ref_piece = ? OR associee = ?) LIMIT 1",
                [ref, ref]).fetchone()
            if row is None:
                return None
            principale, associee = row
            self.cursor.execute(
                "DELETE FROM references_associees WHERE ref_piece = ? AND associee = ?",
                [principale, associee])
            self.cursor.execute(
                "UPDATE piece_equivalence_groups SET ligne_fiche = NULL "
                "WHERE ref_piece = ? AND ligne_fiche = 0", [associee])
            self.conn.commit()
        return associee if principale == ref else principale

    def refuser_reference_proposee(self, proposee: str) -> None:
        """La réf. proposée (équivalente de ligne 0) n'est pas la jumelle : elle reste
        équivalente mais perd la marque « ligne 0 », et n'est plus proposée."""
        if not proposee:
            return
        with self._query_lock:
            self.cursor.execute(
                "UPDATE piece_equivalence_groups SET ligne_fiche = NULL "
                "WHERE ref_piece = ? AND ligne_fiche = 0", [proposee])
            self.conn.commit()

    def inverser_reference_associee(self, ref: str, le: str) -> bool:
        """La principale devient l'associée et inversement ; la marque « ligne 0 »
        suit l'associée (une paire qui ne l'avait pas ne la prend pas)."""
        with self._query_lock:
            row = self.cursor.execute(
                "SELECT ref_piece, associee FROM references_associees "
                "WHERE associee IS NOT NULL AND (ref_piece = ? OR associee = ?) LIMIT 1",
                [ref, ref]).fetchone()
            if row is None:
                return False
            principale, associee = row
            ligne_0 = self.cursor.execute(
                "SELECT 1 FROM piece_equivalence_groups WHERE ref_piece = ? AND ligne_fiche = 0",
                [associee]).fetchone() is not None
            self.cursor.execute(
                "DELETE FROM references_associees WHERE ref_piece IN (?, ?)", [principale, associee])
            self.cursor.execute(
                "INSERT INTO references_associees (ref_piece, associee, decide_le) VALUES (?, ?, ?)",
                [associee, principale, le])
            if ligne_0:
                self.cursor.execute(
                    "UPDATE piece_equivalence_groups SET ligne_fiche = NULL WHERE ref_piece = ?",
                    [associee])
                self.cursor.execute(
                    "UPDATE piece_equivalence_groups SET ligne_fiche = 0 WHERE ref_piece = ?",
                    [principale])
            self.conn.commit()
        return True

    def oublier_reponse_aucune(self, ref: str) -> None:
        """Efface la réponse « aucune » : l'import redemandera la réf. associée."""
        with self._query_lock:
            self.cursor.execute(
                "DELETE FROM references_associees WHERE ref_piece = ? AND associee IS NULL", [ref])
            self.conn.commit()

    def _oublier_paires_de(self, ref_piece: str) -> None:
        """Pièce retirée de son groupe d'équivalence : ses paires de jumelles ne
        tiennent plus (la réponse « aucune » reste). Sans commit."""
        self.cursor.execute(
            "DELETE FROM references_associees WHERE associee IS NOT NULL "
            "AND (ref_piece = ? OR associee = ?)", [ref_piece, ref_piece])

    # --- Fiches à refaire depuis les PDF (§ 10.14) ---------------------------------
    def _noter_fiche_a_refaire(self, ref_piece: str, id_product: Optional[int], a_refaire,
                               le: str):
        """Fiche dont des créations ont été retenues (données bancales). Une relecture
        met la ligne à jour ; un import de la pièce l'en retire."""
        self.cursor.execute(
            "INSERT OR REPLACE INTO fiches_a_refaire (ref_piece, id_product, raison, en_vrac, "
            "creations, retenues, exemples, releve_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [ref_piece, id_product, a_refaire.raison, int(a_refaire.en_vrac), a_refaire.creations,
             a_refaire.retenues, '\n'.join(a_refaire.exemples), le])

    def fiches_a_refaire(self) -> List[Dict]:
        """Fiches à refaire, les plus touchées d'abord."""
        with self._query_lock:
            rows = self.cursor.execute(
                "SELECT ref_piece, id_product, raison, en_vrac, creations, retenues, exemples, "
                "releve_le FROM fiches_a_refaire ORDER BY en_vrac DESC, retenues DESC, ref_piece"
            ).fetchall()
        cles = ('ref_piece', 'id_product', 'raison', 'en_vrac', 'creations', 'retenues',
                'exemples', 'releve_le')
        return [dict(zip(cles, r)) for r in rows]

    def retirer_fiches_a_refaire(self, refs: Iterable[str]) -> List[str]:
        """Retire de la liste les pièces données (fiche refaite par un import, ou
        « Fait ») ; retourne celles qui y étaient."""
        refs = [r for r in dict.fromkeys(refs) if r]
        if not refs:
            return []
        with self._query_lock:
            presentes = []
            for i in range(0, len(refs), 500):
                lot = refs[i:i + 500]
                q = ','.join('?' * len(lot))
                presentes += [r[0] for r in self.cursor.execute(
                    f"SELECT ref_piece FROM fiches_a_refaire WHERE ref_piece IN ({q})", lot)]
                self.cursor.execute(f"DELETE FROM fiches_a_refaire WHERE ref_piece IN ({q})", lot)
            self.conn.commit()
        return presentes

    def _setup_reprise_site_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS reprise_site_etat (
                cle                   TEXT PRIMARY KEY CHECK (cle = 'courant'),
                dernier_id            INTEGER NOT NULL DEFAULT 0,
                date_export           TEXT,
                taille_produits       INTEGER,
                taille_compatibilites INTEGER,
                chemin_produits       TEXT,
                chemin_compatibilites TEXT,
                maj_le                TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS reprise_site_lots (
                numero        INTEGER PRIMARY KEY AUTOINCREMENT,
                premier_id    INTEGER,
                dernier_id    INTEGER,
                date_export   TEXT,
                produits      INTEGER,
                fiches        INTEGER,
                de_cote       INTEGER,
                analyse_s     REAL,
                ecriture_s    REAL,
                taille_avant  INTEGER,
                taille_apres  INTEGER,
                mesures       TEXT,
                enregistre_le TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS reprise_site_de_cote (
                id_produit  INTEGER PRIMARY KEY,
                ref_piece   TEXT,
                nom         TEXT,
                raison      TEXT,
                date_export TEXT,
                le          TEXT
            )
        """)

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

    @with_query_lock
    def pieces_avec_produit_site(self, refs: Iterable[str]) -> Set[str]:
        """Parmi `refs`, celles qui sont vendues sur le site (pièces principales)."""
        refs = [r for r in dict.fromkeys(refs) if r]
        trouvees: Set[str] = set()
        for i in range(0, len(refs), 500):
            lot = refs[i:i + 500]
            trouvees.update(r for (r,) in self.cursor.execute(
                f"SELECT DISTINCT ref_piece FROM produits_site "
                f"WHERE ref_piece IN ({','.join('?' * len(lot))})", lot).fetchall())
        return trouvees

    @with_query_lock
    def memoire_equivalences(self, ref_piece: str) -> Dict[str, Tuple[Optional[str], Optional[int]]]:
        """Membres du groupe d'équivalence de `ref_piece` → (marque d'origine, n° de
        ligne de la fiche) ; 0 = 2ᵉ réf. du code produit, None = rien de mémorisé."""
        rows = self.cursor.execute(
            "SELECT g2.ref_piece, g2.origine, g2.ligne_fiche "
            "FROM piece_equivalence_groups g1 "
            "JOIN piece_equivalence_groups g2 ON g2.group_id = g1.group_id "
            "WHERE g1.ref_piece = ?", [ref_piece]).fetchall()
        return {r: ((o or None), l) for r, o, l in rows}

    @with_query_lock
    def references_ecartees(self, refs_pieces: Iterable[str]) -> Set[str]:
        """Références écartées (§ 5.3) sur l'une des pièces `refs_pieces`."""
        refs = [r for r in dict.fromkeys(refs_pieces) if r]
        ecartees: Set[str] = set()
        for i in range(0, len(refs), 500):
            lot = refs[i:i + 500]
            ecartees.update(r for (r,) in self.cursor.execute(
                f"SELECT reference FROM decisions_references WHERE nature = 'ecartee' "
                f"AND ref_piece IN ({','.join('?' * len(lot))})", lot).fetchall())
        return ecartees

    # ── Reprise en masse (§ 7.3) ─────────────────────────────────────────────

    _COLONNES_ETAT = ('dernier_id', 'date_export', 'taille_produits', 'taille_compatibilites',
                      'chemin_produits', 'chemin_compatibilites', 'maj_le')

    @with_query_lock
    def etat_reprise_site(self) -> Optional[Dict]:
        """État de la reprise (None = jamais commencée)."""
        row = self.cursor.execute(
            f"SELECT {', '.join(self._COLONNES_ETAT)} FROM reprise_site_etat "
            f"WHERE cle = 'courant'").fetchone()
        return dict(zip(self._COLONNES_ETAT, row)) if row else None

    @with_query_lock
    def lots_reprise_site(self, limite: int = 50) -> List[Dict]:
        colonnes = ('numero', 'premier_id', 'dernier_id', 'date_export', 'produits', 'fiches',
                    'de_cote', 'analyse_s', 'ecriture_s', 'taille_avant', 'taille_apres',
                    'mesures', 'enregistre_le')
        rows = self.cursor.execute(
            f"SELECT {', '.join(colonnes)} FROM reprise_site_lots ORDER BY numero DESC LIMIT ?",
            [limite]).fetchall()
        return [dict(zip(colonnes, r)) for r in rows]

    @with_query_lock
    def fiches_de_cote_reprise_site(self) -> List[Dict]:
        colonnes = ('id_produit', 'ref_piece', 'nom', 'raison', 'date_export', 'le')
        rows = self.cursor.execute(
            f"SELECT {', '.join(colonnes)} FROM reprise_site_de_cote ORDER BY id_produit").fetchall()
        return [dict(zip(colonnes, r)) for r in rows]

    @with_query_lock
    def definir_export_reprise_site(self, signature: Dict, repartir_de_zero: bool, le: str):
        """Nouvel export choisi : le garde comme export en cours. `repartir_de_zero`
        remet le dernier id_produit à 0 et oublie les fiches mises de côté."""
        self.cursor.execute("""
            INSERT INTO reprise_site_etat (cle, dernier_id, date_export, taille_produits,
                taille_compatibilites, chemin_produits, chemin_compatibilites, maj_le)
            VALUES ('courant', 0, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cle) DO UPDATE SET
                date_export = excluded.date_export, taille_produits = excluded.taille_produits,
                taille_compatibilites = excluded.taille_compatibilites,
                chemin_produits = excluded.chemin_produits,
                chemin_compatibilites = excluded.chemin_compatibilites, maj_le = excluded.maj_le
        """, [signature['date_export'], signature['taille_produits'],
              signature['taille_compatibilites'], signature['chemin_produits'],
              signature['chemin_compatibilites'], le])
        if repartir_de_zero:
            self.cursor.execute("UPDATE reprise_site_etat SET dernier_id = 0 WHERE cle = 'courant'")
            self.cursor.execute("DELETE FROM reprise_site_de_cote")
        self.conn.commit()

    def _avancer_reprise_site(self, dernier_id: int, le: str):
        """Dernier id_produit traité (sans commit : même transaction que le journal du lot).
        Ne recule jamais : relancer un lot déjà passé ne fait pas revenir la reprise."""
        self.cursor.execute(
            "UPDATE reprise_site_etat SET dernier_id = MAX(dernier_id, ?), maj_le = ? "
            "WHERE cle = 'courant'", [dernier_id, le])

    def _journaliser_lot_reprise_site(self, lot: Dict) -> int:
        colonnes = ('premier_id', 'dernier_id', 'date_export', 'produits', 'fiches', 'de_cote',
                    'analyse_s', 'ecriture_s', 'taille_avant', 'taille_apres', 'mesures',
                    'enregistre_le')
        cur = self.cursor.execute(
            f"INSERT INTO reprise_site_lots ({', '.join(colonnes)}) "
            f"VALUES ({', '.join('?' * len(colonnes))})", [lot.get(c) for c in colonnes])
        return cur.lastrowid

    def _mettre_de_cote_reprise_site(self, fiches: Iterable[Tuple[int, str, str, str]],
                                     date_export: str, le: str):
        """(id_produit, ref_piece, nom, raison) : fiches à reprendre plus tard."""
        self.cursor.executemany(
            "INSERT OR REPLACE INTO reprise_site_de_cote VALUES (?, ?, ?, ?, ?, ?)",
            [(i, r, n, raison, date_export, le) for i, r, n, raison in fiches])

    def _retirer_de_cote_reprise_site(self, ids: Iterable[int]):
        self.cursor.executemany("DELETE FROM reprise_site_de_cote WHERE id_produit = ?",
                                [(i,) for i in ids])

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
        # Deux lignes de la fiche peuvent viser le même appareil (écritures proches,
        # description et table) : leurs provenances se réunissent
        reunis: Dict[int, str] = {}
        for appareil_id, provenance in liens:
            reunis[appareil_id] = fusion_provenance(reunis.get(appareil_id), provenance)
        liens = list(reunis.items())
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

    def _definir_rangs_remplace(self, rangs: Iterable[Tuple[str, int]]) -> int:
        """Position de chaque ancienne référence dans « Remplace les références » de
        la fiche (la fiche fait foi pour l'ordre ; rien n'est créé : seules les
        successions présentes sont complétées)."""
        n = 0
        for ref_old, rang in rangs:
            cur = self.cursor.execute(
                "UPDATE piece_supersessions SET rang_fiche = ? WHERE ref_old = ? "
                "AND rang_fiche IS NOT ?", [rang, ref_old, rang])
            n += cur.rowcount
        return n

    @with_query_lock
    def rangs_remplace(self, refs: Iterable[str]) -> Dict[str, int]:
        """Ancienne référence → position mémorisée dans « Remplace » (absente = aucune)."""
        refs = [r for r in dict.fromkeys(refs) if r]
        resultat: Dict[str, int] = {}
        for i in range(0, len(refs), 500):
            tranche = refs[i:i + 500]
            resultat.update(self.cursor.execute(
                f"SELECT ref_old, rang_fiche FROM piece_supersessions WHERE rang_fiche "
                f"IS NOT NULL AND ref_old IN ({','.join('?' * len(tranche))})",
                tranche).fetchall())
        return resultat

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
