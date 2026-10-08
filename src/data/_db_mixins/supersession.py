"""
Mixin Supersession & Équivalences — extrait de DatabaseManager.

Ne pas instancier directement : ce mixin est conçu pour être hérité par
DatabaseManager uniquement.

Dépendances attendues sur self (fournies par DatabaseManager.__init__) :
    self.cursor       — curseur SQLite actif
    self.conn         — connexion SQLite active
    self._query_lock  — verrou threading pour les écritures
    self.execute_query() — méthode CRUD (définie dans DatabaseManager)
"""

from ...core.logger import app_logger


class DatabaseSupersessionMixin:
    """Méthodes Supersession et Équivalences de pièces pour DatabaseManager."""

    # ── Supersession des références pièces ──────────────────────────────────

    def _setup_supersession_table(self):
        """Créer la table piece_supersessions et migrer le schéma si nécessaire."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS piece_supersessions (
                    ref_old  TEXT NOT NULL,
                    ref_new  TEXT NOT NULL,
                    PRIMARY KEY (ref_old),
                    FOREIGN KEY (ref_old) REFERENCES pieces(ref_piece) ON DELETE CASCADE,
                    FOREIGN KEY (ref_new) REFERENCES pieces(ref_piece) ON DELETE CASCADE
                )
            """)
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_supersessions_old ON piece_supersessions(ref_old)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_supersessions_new ON piece_supersessions(ref_new)"
            )
            # Migration : ajout colonne is_obsolete sur pieces (idempotent)
            try:
                self.cursor.execute(
                    "ALTER TABLE pieces ADD COLUMN is_obsolete INTEGER NOT NULL DEFAULT 0"
                )
                app_logger.info("Migration : colonne is_obsolete ajoutée à pieces")
            except Exception:
                pass  # Colonne déjà présente
            # Migration : ajout colonne is_phantom sur pieces (idempotent)
            try:
                self.cursor.execute(
                    "ALTER TABLE pieces ADD COLUMN is_phantom INTEGER NOT NULL DEFAULT 0"
                )
                app_logger.info("Migration : colonne is_phantom ajoutée à pieces")
            except Exception:
                pass  # Colonne déjà présente
            # Migration : (ref_old, NULL) → is_obsolete=1 puis suppression de la ligne
            null_rows = self.cursor.execute(
                "SELECT ref_old FROM piece_supersessions WHERE ref_new IS NULL"
            ).fetchall()
            if null_rows:
                for (ref_old,) in null_rows:
                    self.cursor.execute(
                        "UPDATE pieces SET is_obsolete = 1 WHERE ref_piece = ?", (ref_old,)
                    )
                self.cursor.execute(
                    "DELETE FROM piece_supersessions WHERE ref_new IS NULL"
                )
                self.conn.commit()
                app_logger.info(f"Migration : {len(null_rows)} entrée(s) (ref_old, NULL) converties en is_obsolete=1")
        except Exception as e:
            app_logger.error(f"Erreur création table piece_supersessions: {e}")

    # ── Équivalence des références pièces ───────────────────────────────────

    def _setup_equivalence_table(self):
        """Créer la table piece_equivalence_groups si nécessaire."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS piece_equivalence_groups (
                    group_id  INTEGER NOT NULL,
                    ref_piece TEXT NOT NULL,
                    PRIMARY KEY (group_id, ref_piece),
                    FOREIGN KEY (ref_piece) REFERENCES pieces(ref_piece) ON DELETE CASCADE
                )
            """)
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_equiv_ref ON piece_equivalence_groups(ref_piece)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_equiv_gid ON piece_equivalence_groups(group_id)"
            )
            self.conn.commit()
        except Exception as e:
            app_logger.error(f"Erreur création table piece_equivalence_groups: {e}")

    def _propagate_predecessors_to_group(self, group_id: int):
        """
        Ajouter dans le groupe tous les prédécesseurs (via chaîne de supersession)
        de ses membres actuels, afin de garantir la transitivité supersession→équivalence.

        Ex : si A ≡ B et C → A, alors C est ajouté au groupe {A, B}.
        Doit être appelé sous _query_lock (utilise self.cursor directement).
        """
        members = {r[0] for r in self.cursor.execute(
            "SELECT ref_piece FROM piece_equivalence_groups WHERE group_id = ?", [group_id]
        ).fetchall()}
        to_add = set()
        for member in members:
            for pred in self.get_all_predecessors(member):
                if pred not in members:
                    to_add.add(pred)
        for pred in to_add:
            self.cursor.execute(
                "INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)", [pred]
            )
            self.cursor.execute(
                "INSERT OR IGNORE INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)",
                [group_id, pred]
            )

    def add_equivalence(self, ref_a: str, ref_b: str) -> tuple:
        """
        Créer un lien d'équivalence symétrique entre ref_a et ref_b.
        Fusionne les groupes si les deux refs appartiennent déjà à des groupes distincts.

        Returns: (success: bool, error_message: str)
        """
        if ref_a == ref_b:
            return False, "Une référence ne peut pas être équivalente à elle-même."
        try:
            with self._query_lock:
                # §7 — créer les refs fantômes si absentes
                for ref in (ref_a, ref_b):
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)", [ref]
                    )
                gid_a = (self.cursor.execute(
                    "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_a]
                ).fetchone() or [None])[0]
                gid_b = (self.cursor.execute(
                    "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_b]
                ).fetchone() or [None])[0]

                if gid_a is None and gid_b is None:
                    new_gid = (self.cursor.execute(
                        "SELECT COALESCE(MAX(group_id), 0) FROM piece_equivalence_groups"
                    ).fetchone()[0]) + 1
                    self.cursor.execute(
                        "INSERT INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)", [new_gid, ref_a]
                    )
                    self.cursor.execute(
                        "INSERT INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)", [new_gid, ref_b]
                    )
                elif gid_a is None:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)", [gid_b, ref_a]
                    )
                elif gid_b is None:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)", [gid_a, ref_b]
                    )
                elif gid_a != gid_b:
                    # Fusion : déplacer tous les membres du groupe B vers le groupe A
                    self.cursor.execute(
                        "UPDATE piece_equivalence_groups SET group_id = ? WHERE group_id = ?", [gid_a, gid_b]
                    )
                # else: déjà dans le même groupe

                # Propager les prédécesseurs (transitivité supersession → équivalence)
                final_gid = self.cursor.execute(
                    "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_a]
                ).fetchone()[0]
                self._propagate_predecessors_to_group(final_gid)
                self.conn.commit()
            return True, ""
        except Exception as e:
            app_logger.error(f"Erreur add_equivalence({ref_a} ≡ {ref_b}): {e}")
            return False, str(e)

    def remove_equivalence(self, ref_piece: str) -> bool:
        """
        Retirer ref_piece de son groupe d'équivalence.
        Si le groupe tombe à ≤ 1 membre, il est dissous.
        """
        try:
            with self._query_lock:
                row = self.cursor.execute(
                    "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_piece]
                ).fetchone()
                if not row:
                    return True
                gid = row[0]
                self.cursor.execute(
                    "DELETE FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_piece]
                )
                count = self.cursor.execute(
                    "SELECT COUNT(*) FROM piece_equivalence_groups WHERE group_id = ?", [gid]
                ).fetchone()[0]
                if count <= 1:
                    self.cursor.execute(
                        "DELETE FROM piece_equivalence_groups WHERE group_id = ?", [gid]
                    )
                self.conn.commit()
            return True
        except Exception as e:
            app_logger.error(f"Erreur remove_equivalence({ref_piece}): {e}")
            return False

    def get_equivalents(self, ref_piece: str) -> list:
        """
        Retourner les références équivalentes à ref_piece (hors ref_piece elle-même).
        """
        try:
            rows = self.execute_query(
                """SELECT peg2.ref_piece
                   FROM piece_equivalence_groups peg
                   JOIN piece_equivalence_groups peg2 ON peg.group_id = peg2.group_id
                   WHERE peg.ref_piece = ? AND peg2.ref_piece != ?
                   ORDER BY peg2.ref_piece""",
                [ref_piece, ref_piece]
            )
            return [r[0] for r in rows] if rows else []
        except Exception as e:
            app_logger.error(f"Erreur get_equivalents({ref_piece}): {e}")
            return []

    def get_equivalents_hors_chaine(self, ref_piece: str) -> list:
        """
        Équivalentes « vraies » de ref_piece : le groupe d'équivalence SANS les
        réfs déjà joignables par une chaîne de succession.

        En base, `_propagate_predecessors_to_group` fait entrer les anciennes
        versions dans le groupe de leur courante. Utile pour l'extension des
        appareils, mais redondant à l'affichage. On retire donc :
        - la famille de ref_piece (sa tête de chaîne et les anciennes versions
          de cette tête), déjà montrée par le bandeau de succession ;
        - les anciennes versions d'une autre équivalente présente dans le groupe
          (elles restent joignables via leur courante).

        Ex : C00256552 → C00273284, et C00273284 ≡ 758973779 ≡ 278449
             get_equivalents_hors_chaine('C00256552') == ['278449', '758973779']

        Une ancienne version dont la courante est HORS du groupe est conservée
        (sinon l'équivalence deviendrait invisible).
        """
        equivalents = self.get_equivalents(ref_piece)
        if not equivalents:
            return []

        def _tete(ref):
            return self.get_supersession_chain(ref)[-1]

        tete_terme = _tete(ref_piece)
        groupe = set(equivalents) | {ref_piece}
        resultat = []
        for ref in equivalents:
            tete = _tete(ref)
            if tete == tete_terme:
                continue                      # même famille que le terme
            if tete != ref and tete in groupe:
                continue                      # ancienne version d'une équivalente listée
            resultat.append(ref)
        return resultat

    def set_description_for_refs(self, refs: list, description: str) -> int:
        """
        Appliquer le même libellé à plusieurs pièces en une seule transaction.

        Returns: nombre de lignes effectivement modifiées.
        """
        if not refs:
            return 0
        try:
            with self._query_lock:
                placeholders = ",".join("?" * len(refs))
                self.cursor.execute(
                    f"UPDATE pieces SET description = ? WHERE ref_piece IN ({placeholders})",
                    [description, *refs]
                )
                updated = self.cursor.rowcount
                self.conn.commit()
            return updated
        except Exception as e:
            app_logger.error(f"Erreur set_description_for_refs({refs} → '{description}'): {e}")
            return 0

    def get_piece_status(self, ref_piece: str) -> dict:
        """
        Retourner le statut de succession d'une référence pièce.

        Returns:
            dict avec les clés :
              - 'status'      : 'current' | 'superseded' | 'obsolete'
              - 'ref_new'     : ref de remplacement (str ou None)
              - 'is_obsolete' : bool — pièce marquée obsolète (plus fabriquée)
            Note : une pièce peut être à la fois superseded ET obsolète.
                   Dans ce cas status='superseded' et is_obsolete=True.
        """
        try:
            succ = self.execute_query(
                "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?", [ref_piece]
            )
            obs = self.execute_query(
                "SELECT is_obsolete FROM pieces WHERE ref_piece = ?", [ref_piece]
            )
            is_obsolete = bool(obs and obs[0][0])
            if succ:
                return {'status': 'superseded', 'ref_new': succ[0][0], 'is_obsolete': is_obsolete}
            if is_obsolete:
                return {'status': 'obsolete', 'ref_new': None, 'is_obsolete': True}
            return {'status': 'current', 'ref_new': None, 'is_obsolete': False}
        except Exception as e:
            app_logger.error(f"Erreur get_piece_status({ref_piece}): {e}")
            return {'status': 'current', 'ref_new': None, 'is_obsolete': False}

    def get_pieces_statuses_batch(self, refs: list) -> dict:
        """
        Retourner les statuts de succession pour une liste de références en une seule requête.

        Returns:
            dict {ref_piece: {
                'status': 'current'|'superseded'|'obsolete'|'replacing',
                'ref_new': str|None,       # ref qui remplace cette pièce
                'refs_old': str|None,      # refs que cette pièce remplace (ex: "A, B")
                'is_obsolete': bool
            }}
        """
        if not refs:
            return {}
        try:
            placeholders = ",".join("?" * len(refs))
            # Requête 1 : statut forward (cette ref est-elle remplacée / obsolète ?)
            rows = self.execute_query(
                f"""SELECT p.ref_piece, ps.ref_new, p.is_obsolete
                    FROM pieces p
                    LEFT JOIN piece_supersessions ps ON ps.ref_old = p.ref_piece
                    WHERE p.ref_piece IN ({placeholders})""",
                refs
            )
            result = {ref: {'status': 'current', 'ref_new': None, 'refs_old': None, 'is_obsolete': False, 'equivalents': None} for ref in refs}
            for ref_piece, ref_new, is_obsolete in (rows or []):
                is_obs = bool(is_obsolete)
                if ref_new is not None:
                    result[ref_piece] = {'status': 'superseded', 'ref_new': ref_new, 'refs_old': None, 'is_obsolete': is_obs}
                elif is_obs:
                    result[ref_piece] = {'status': 'obsolete', 'ref_new': None, 'refs_old': None, 'is_obsolete': True}
                else:
                    result[ref_piece] = {'status': 'current', 'ref_new': None, 'refs_old': None, 'is_obsolete': False}
            # Requête 2 : statut backward (cette ref remplace-t-elle d'autres refs ?)
            replacing_rows = self.execute_query(
                f"""SELECT ps.ref_new, GROUP_CONCAT(ps.ref_old, ', ') as replaced_refs
                    FROM piece_supersessions ps
                    WHERE ps.ref_new IN ({placeholders})
                    GROUP BY ps.ref_new""",
                refs
            )
            for ref_new, replaced_refs in (replacing_rows or []):
                if ref_new in result:
                    result[ref_new]['refs_old'] = replaced_refs
                    if result[ref_new]['status'] == 'current':
                        result[ref_new]['status'] = 'replacing'
            # Requête 3 : équivalences (même groupe d'équivalence)
            equiv_rows = self.execute_query(
                f"""SELECT peg.ref_piece, GROUP_CONCAT(peg2.ref_piece, ', ')
                    FROM piece_equivalence_groups peg
                    JOIN piece_equivalence_groups peg2 ON peg.group_id = peg2.group_id
                        AND peg2.ref_piece != peg.ref_piece
                    WHERE peg.ref_piece IN ({placeholders})
                    GROUP BY peg.ref_piece""",
                refs
            )
            for ref_piece, equiv_str in (equiv_rows or []):
                if ref_piece in result:
                    result[ref_piece]['equivalents'] = equiv_str
            return result
        except Exception as e:
            app_logger.error(f"Erreur get_pieces_statuses_batch: {e}")
            return {ref: {'status': 'current', 'ref_new': None, 'refs_old': None, 'is_obsolete': False, 'equivalents': None} for ref in refs}

    def _definir_obsolescence(self, ref_piece: str, obsolete: bool, operation: str) -> bool:
        """Poser ou retirer le marqueur d'obsolescence d'une pièce.

        Socle commun de mark_obsolete / unmark_obsolete, qui ne différaient que
        par la valeur écrite. Les regrouper garantit que le verrou, le commit et
        la gestion d'erreur restent identiques des deux côtés — une divergence y
        serait silencieuse.

        Args:
            operation: nom de l'appelant, pour que le message d'erreur reste
                       aussi précis qu'avant.
        """
        try:
            with self._query_lock:
                self.cursor.execute(
                    "UPDATE pieces SET is_obsolete = ? WHERE ref_piece = ?",
                    [1 if obsolete else 0, ref_piece]
                )
                self.conn.commit()
            return True
        except Exception as e:
            app_logger.error(f"Erreur {operation}({ref_piece}): {e}")
            return False

    def mark_obsolete(self, ref_piece: str) -> bool:
        """Marquer une pièce comme obsolète (plus fabriquée). Indépendant de la succession."""
        return self._definir_obsolescence(ref_piece, True, 'mark_obsolete')

    def unmark_obsolete(self, ref_piece: str) -> bool:
        """Retirer le marqueur obsolète d'une pièce."""
        return self._definir_obsolescence(ref_piece, False, 'unmark_obsolete')

    def get_appareils_for_piece_ref(self, ref_piece: str) -> list:
        """
        Retourner la liste des appareils associés à une référence pièce.

        Returns:
            list de tuples (type, manufacturer, ref_modele)
        """
        try:
            return self.execute_query(
                """SELECT a.type, a.manufacturer, a.ref_modele
                   FROM appareils a
                   JOIN piece_associations pa ON pa.appareil_id = a.id
                   JOIN pieces p ON pa.piece_id = p.id
                   WHERE p.ref_piece = ?
                   ORDER BY a.manufacturer, a.ref_modele""",
                [ref_piece]
            ) or []
        except Exception as e:
            app_logger.error(f"Erreur get_appareils_for_piece_ref({ref_piece}): {e}")
            return []

    def _resolve_refs_via_supersession(self, term: str, extend_search: bool = False) -> list:
        """
        Retourner les refs courantes des pièces dont une ancienne ref correspond au terme.
        Utilisé pour étendre la recherche aux références supersédées.

        extend_search=False (défaut) : correspondance exacte sur ref_old.
        extend_search=True           : correspondance partielle (LIKE '%term%').

        Returns:
            list de refs courantes (sans doublon), vide si aucune correspondance.
        """
        try:
            op = "LIKE" if extend_search else "="
            param = f"%{term}%" if extend_search else term
            old_matches = self.execute_query(
                f"SELECT DISTINCT ref_old FROM piece_supersessions WHERE ref_old {op} ?",
                [param]
            ) or []
            resolved = []
            for (ref_old,) in old_matches:
                current = self.resolve_current_ref(ref_old)
                if current and current not in resolved:
                    resolved.append(current)
            return resolved
        except Exception as e:
            app_logger.error(f"Erreur _resolve_refs_via_supersession({term}): {e}")
            return []

    def _build_pieces_only_condition(self, term: str, bypass: bool = False,
                                     extra_refs: list = None,
                                     extend_search: bool = False) -> dict:
        """
        Construire la condition SQL pour la recherche par ref_piece (SEARCH_PIECES_ONLY).

        bypass=True     : cherche uniquement la ref telle quelle (sans résolution supersession).
        extra_refs      : refs supplémentaires à inclure en UNION (ex : prédécesseurs pour expansion).
        extend_search   : False (défaut) = correspondance exacte sur ref_piece ;
                          True = correspondance partielle (LIKE '%term%'), y compris
                          pour la résolution de supersession.
        """
        op = "LIKE" if extend_search else "="
        param_term = f"%{term}%" if extend_search else term

        if bypass:
            return {
                'query_type': 'pieces_only',
                'condition': self._piece_association_subquery(op),
                'params': [param_term]
            }

        # Résoudre la chaîne forward (term est peut-être une ancienne ref)
        resolved = self._resolve_refs_via_supersession(term, extend_search=extend_search)

        # Combiner avec les refs supplémentaires explicites (ex : prédécesseurs)
        all_extra = list(resolved)
        if extra_refs:
            for r in extra_refs:
                if r not in all_extra:
                    all_extra.append(r)

        if all_extra:
            placeholders = ",".join("?" * len(all_extra))
            condition = (
                f"a.id IN ("
                f"SELECT pa.appareil_id FROM piece_associations pa "
                f"WHERE pa.piece_id IN ("
                f"SELECT id FROM pieces WHERE ref_piece {op} ? "
                f"UNION SELECT id FROM pieces WHERE ref_piece IN ({placeholders})"
                f"))"
            )
            params = [param_term] + all_extra
        else:
            condition = self._piece_association_subquery(op)
            params = [param_term]
        return {'query_type': 'pieces_only', 'condition': condition, 'params': params}

    def _supersession_chain_cte(self, direction: str = "forward") -> str:
        """CTE récursive commune pour parcourir la chaîne de succession.

        direction="forward"  : suit ref_old -> ref_new (vers la ref courante),
            utilisée par resolve_current_ref() et get_supersession_chain().
        direction="backward" : suit ref_new -> ref_old (vers les
            prédécesseurs), utilisée par get_all_predecessors().

        Params attendus par la requête : [ref_piece, max_depth].
        """
        if direction == "forward":
            join_clause = "JOIN piece_supersessions ps ON ps.ref_old = chain.ref"
            next_ref = "ps.ref_new"
            where_clause = "ps.ref_new IS NOT NULL AND chain.depth < ?"
        else:
            join_clause = "JOIN piece_supersessions ps ON ps.ref_new = chain.ref"
            next_ref = "ps.ref_old"
            where_clause = "chain.depth < ?"

        return f"""
                WITH RECURSIVE chain(ref, depth) AS (
                    SELECT ?, 0
                    UNION ALL
                    SELECT {next_ref}, chain.depth + 1
                    FROM chain
                    {join_clause}
                    WHERE {where_clause}
                )
        """

    def resolve_current_ref(self, ref_piece: str, max_depth: int = 20) -> str:
        """
        Remonter la chaîne de succession jusqu'à la référence courante.
        Protégé contre les cycles via max_depth.

        Returns:
            La ref courante (dernière de la chaîne), ou ref_piece si déjà courante.
        """
        try:
            query = self._supersession_chain_cte("forward") + "SELECT ref FROM chain ORDER BY depth DESC LIMIT 1"
            rows = self.execute_query(query, [ref_piece, max_depth])
            return rows[0][0] if rows else ref_piece
        except Exception as e:
            app_logger.error(f"Erreur resolve_current_ref({ref_piece}): {e}")
            return ref_piece

    def get_all_predecessors(self, ref_piece: str, max_depth: int = 20) -> list:
        """
        Retourner toutes les refs qui ont été remplacées (directement ou indirectement)
        par ref_piece, en remontant la chaîne en sens inverse.

        Ex : si REF_OLD → REF_MID → REF_NEW, alors get_all_predecessors('REF_NEW') = ['REF_MID', 'REF_OLD']

        Returns:
            Liste des refs prédécesseurs, vide si ref_piece n'en a aucun.
        """
        try:
            query = self._supersession_chain_cte("backward") + "SELECT ref FROM chain WHERE depth > 0 ORDER BY depth ASC"
            rows = self.execute_query(query, [ref_piece, max_depth])
            return [r[0] for r in rows] if rows else []
        except Exception as e:
            app_logger.error(f"Erreur get_all_predecessors({ref_piece}): {e}")
            return []

    def get_supersession_chain(self, ref_piece: str, max_depth: int = 20) -> list:
        """
        Retourner la chaîne complète depuis la ref donnée jusqu'à la ref courante.

        Returns:
            Liste ordonnée [ref_piece, ..., ref_courante].
            Contient uniquement ref_piece si elle est déjà courante.
        """
        try:
            query = self._supersession_chain_cte("forward") + "SELECT ref FROM chain ORDER BY depth ASC"
            rows = self.execute_query(query, [ref_piece, max_depth])
            return [r[0] for r in rows] if rows else [ref_piece]
        except Exception as e:
            app_logger.error(f"Erreur get_supersession_chain({ref_piece}): {e}")
            return [ref_piece]

    def _has_supersession_cycle(self, ref_old: str, ref_new: str) -> bool:
        """Vérifier si ajouter ref_old → ref_new créerait un cycle."""
        try:
            current = ref_new
            visited = {ref_old}
            for _ in range(30):
                if current in visited:
                    return True
                visited.add(current)
                rows = self.execute_query(
                    "SELECT ref_new FROM piece_supersessions WHERE ref_old = ?",
                    [current]
                )
                if not rows:
                    return False
                current = rows[0][0]
            return True  # chaîne trop longue, considérée comme cycle
        except Exception as e:
            app_logger.error(f"Erreur détection cycle supersession: {e}")
            return False

    def add_supersession(self, ref_old: str, ref_new) -> tuple:
        """
        Ajouter ou mettre à jour une entrée de supersession.

        Args:
            ref_old : référence remplacée (ou obsolète)
            ref_new : nouvelle référence, ou None pour marquer obsolète

        Returns:
            (success: bool, error_message: str)
        """
        try:
            if ref_new is None:
                return False, "ref_new ne peut pas être None — utiliser mark_obsolete() à la place."
            if ref_old == ref_new:
                return False, "Une référence ne peut pas se remplacer elle-même."
            if self._has_supersession_cycle(ref_old, ref_new):
                return False, f"Cette opération créerait un cycle de succession ({ref_old} → ... → {ref_old})."
            with self._query_lock:
                # §7 — Créer automatiquement les refs fantômes si absentes de pieces
                for ref in (ref_old, ref_new):
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)",
                        [ref]
                    )
                self.cursor.execute(
                    "INSERT OR REPLACE INTO piece_supersessions(ref_old, ref_new) VALUES (?, ?)",
                    [ref_old, ref_new]
                )
                # Propager : si ref_new appartient à un groupe d'équivalence, y ajouter ref_old
                gid_row = self.cursor.execute(
                    "SELECT group_id FROM piece_equivalence_groups WHERE ref_piece = ?", [ref_new]
                ).fetchone()
                if gid_row:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)", [ref_old]
                    )
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO piece_equivalence_groups(group_id, ref_piece) VALUES (?, ?)",
                        [gid_row[0], ref_old]
                    )
                    self._propagate_predecessors_to_group(gid_row[0])
                self.conn.commit()
            return True, ""
        except Exception as e:
            app_logger.error(f"Erreur add_supersession({ref_old} → {ref_new}): {e}")
            return False, str(e)

    def propagate_description(self, ref_a: str, ref_b: str) -> bool:
        """Propager le libellé entre deux références que l'on vient de lier,
        dans le sens où il y a quelque chose à propager.

        Deux réfs reliées par une succession ou une équivalence désignent la même
        pièce du point de vue du catalogue : si l'une porte un libellé et l'autre
        non, la seconde hérite. Le sens n'est pas figé — la réf saisie dans le
        dialogue d'import peut très bien être celle qui est déjà nommée en base,
        et c'est alors la pièce importée qui doit hériter. L'ancienne
        `inherit_phantom_description` ne savait aller que dans un sens, et ne
        s'appliquait qu'aux pièces encore marquées fantômes : une réf promue par
        une association mais restée sans libellé ne pouvait plus jamais hériter.

        Un libellé existant n'est JAMAIS écrasé. Quand les deux réfs sont nommées
        différemment, rien n'est écrit : une nouvelle génération de pièce peut
        légitimement changer de nom. La divergence est seulement journalisée,
        pour rester repérable après coup.

        Returns:
            True si un libellé a effectivement été recopié.
        """
        if not ref_a or not ref_b or ref_a == ref_b:
            return False
        try:
            with self._query_lock:
                rows = self.cursor.execute(
                    "SELECT ref_piece, COALESCE(description, '') FROM pieces "
                    "WHERE ref_piece IN (?, ?)",
                    [ref_a, ref_b]
                ).fetchall()
                libelles = {r[0]: (r[1] or '').strip() for r in rows}
                desc_a = libelles.get(ref_a, '')
                desc_b = libelles.get(ref_b, '')

                if desc_a and desc_b:
                    if desc_a != desc_b:
                        app_logger.info(
                            f"Libellés divergents : '{ref_a}' (« {desc_a} ») et "
                            f"'{ref_b}' (« {desc_b} ») — aucun écrasement."
                        )
                    return False
                if not desc_a and not desc_b:
                    return False

                source, cible, libelle = (
                    (ref_a, ref_b, desc_a) if desc_a else (ref_b, ref_a, desc_b)
                )
                # Le filtre sur la cible vide est redondant avec le test ci-dessus,
                # mais il garde la garantie « jamais d'écrasement » dans le SQL
                # lui-même, où une lecture du code la vérifie sans remonter.
                self.cursor.execute(
                    "UPDATE pieces SET description = ? WHERE ref_piece = ? "
                    "AND (description IS NULL OR TRIM(description) = '')",
                    [libelle, cible]
                )
                recopie = self.cursor.rowcount > 0
                self.conn.commit()
            if recopie:
                app_logger.info(f"Libellé propagé : '{source}' → '{cible}' (« {libelle} »)")
            return recopie
        except Exception as e:
            app_logger.error(f"Erreur propagate_description({ref_a} ↔ {ref_b}): {e}")
            return False

    def remove_supersession(self, ref_old: str) -> bool:
        """Supprimer la relation de supersession pour ref_old."""
        try:
            with self._query_lock:
                self.cursor.execute(
                    "DELETE FROM piece_supersessions WHERE ref_old = ?",
                    [ref_old]
                )
                self.conn.commit()
            return True
        except Exception as e:
            app_logger.error(f"Erreur remove_supersession({ref_old}): {e}")
            return False
