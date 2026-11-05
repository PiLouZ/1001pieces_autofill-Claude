"""
Lectures sur les appareils, mixées dans DatabaseManager.

Requêtes autrefois écrites dans la fenêtre principale, le tableau et des
services (proposition Type/Fabricant, normalisation de casse, analyse et
indicateur des doublons), rassemblées dans la couche données (audit
2026-11-05). Le SQL est repris tel quel, et chaque méthode passe par la même
méthode d'exécution que l'appel d'origine (execute_query : erreur avalée → [] ;
execute_custom_query : erreur remontée).
"""

from typing import Dict, Iterable, List, Tuple


class DatabaseAppareilsMixin:
    """Lectures sur la table appareils."""

    # ── Tableau principal ────────────────────────────────────────────────────

    def valeurs_distinctes_colonne(self, db_field: str) -> List[Tuple]:
        """Valeurs distinctes non vides de `db_field` ('type' ou 'manufacturer'),
        sans tenir compte de la casse pour l'ordre (filtres Type / Marque)."""
        return self.execute_query(
            f"SELECT DISTINCT [{db_field}] FROM appareils "
            f"WHERE [{db_field}] IS NOT NULL AND [{db_field}] != '' "
            f"ORDER BY [{db_field}] COLLATE NOCASE"
        )

    # ── Suggestions par similarité ───────────────────────────────────────────

    @staticmethod
    def requete_index_similarite(prefixes):
        """Requête sélectionnant les références partageant l'un des préfixes de
        3 caractères, parmi les appareils déjà renseignés.

        La version d'origine enchaînait une paire de « OR … LIKE ? » par préfixe.
        Deux défauts, tous deux mesurés (v3.71.1) :

        - **coût super-linéaire** — l'évaluation de l'arbre de OR dominait tout le
          reste : 8,9 s pour 300 préfixes, contre 0,5 s ici (×17) ;
        - **échec silencieux** au-delà d'environ 500 préfixes — SQLite refusait la
          requête (« Expression tree is too large », profondeur maximale 1000) et
          `execute_query` avalait l'exception. L'utilisateur lisait « aucune
          proposition » alors que 272 ou 586 l'attendaient.

        Un `IN (…)` est un nœud d'expression unique : la limite de profondeur ne
        s'applique plus. Résultat strictement identique, vérifié sur la base réelle
        (52 136 lignes des deux côtés, 0 écart).

        Effet de bord souhaitable : `LIKE 'k3_%'` traitait « _ » comme un joker,
        ce que cette forme ne fait pas — les références « K3_TYP… » sont désormais
        comparées à la lettre.

        Returns:
            (requête SQL, liste de paramètres)
        """
        prefixes = list(prefixes)
        marqueurs = ",".join("?" * len(prefixes))
        query = (
            "SELECT id, ref_modele, commercial_ref, type, manufacturer FROM appareils "
            "WHERE (type IS NOT NULL AND type != '' OR manufacturer IS NOT NULL AND manufacturer != '') "
            f"AND (LOWER(SUBSTR(ref_modele, 1, 3)) IN ({marqueurs}) "
            f"OR LOWER(SUBSTR(commercial_ref, 1, 3)) IN ({marqueurs}))"
        )
        return query, prefixes + prefixes

    def lire_index_similarite(self, prefixes) -> List[Tuple]:
        """[(id, ref_modele, commercial_ref, type, manufacturer)] des appareils
        renseignés dont une référence commence par l'un des préfixes."""
        query, params = self.requete_index_similarite(prefixes)
        return self.execute_query(query, params)

    # ── Proposition Type / Fabricant ─────────────────────────────────────────

    def combinaisons_type_fabricant(self, references: Dict[str, str]) -> List[Tuple]:
        """[(type, manufacturer, fréquence, exemple)] des appareils sources dont
        une référence vaut l'une des `references` ({colonne: valeur} non vides),
        auto-complétés non vérifiés exclus, la plus fréquente en tête."""
        conditions = [f'{colonne} = ?' for colonne in references]
        params = list(references.values())
        query = f"""
        SELECT type, manufacturer, COUNT(*) as freq,
               MIN(COALESCE(NULLIF(ref_modele, ''), commercial_ref)) AS exemple
        FROM appareils
        WHERE ({' OR '.join(conditions)})
          AND type IS NOT NULL AND type != ''
          AND manufacturer IS NOT NULL AND manufacturer != ''
          AND id NOT IN (SELECT appareil_id FROM appareils_autocompletes)
        GROUP BY type, manufacturer
        ORDER BY freq DESC, type, manufacturer
    """
        return self.execute_query(query, params)

    # ── Normalisation de casse (marques, types) ──────────────────────────────

    def valeurs_frequentes_colonne(self, colonne: str) -> List[Tuple]:
        """[(valeur, nb)] des valeurs non vides de `colonne`, la plus fréquente
        en tête (une orthographe par clé : la plus fréquente l'emporte)."""
        return self.execute_query(
            f"SELECT {colonne}, COUNT(*) FROM appareils "
            f"WHERE {colonne} IS NOT NULL AND TRIM({colonne}) <> '' "
            f"GROUP BY {colonne} ORDER BY COUNT(*) DESC"
        )

    def valeurs_colonne(self, colonne: str) -> List[Tuple]:
        """[(valeur,)] distinctes et non vides de `colonne` (servi par l'index)."""
        return self.execute_query(
            f"SELECT DISTINCT {colonne} FROM appareils "
            f"WHERE {colonne} IS NOT NULL AND TRIM({colonne}) <> ''")

    # ── Doublons ─────────────────────────────────────────────────────────────

    def groupes_doublons_ref_modele(self) -> List[Tuple]:
        """[(ref_modele, nb, ids séparés par des virgules)] des ref_modele portées
        par plusieurs appareils, hors références marquées DISTINCT."""
        return self.execute_query("""
        SELECT ref_modele, COUNT(*) as count, GROUP_CONCAT(id) as ids
        FROM appareils
        WHERE ref_modele IS NOT NULL AND ref_modele != ''
        AND ref_modele NOT IN (
            SELECT ref_modele FROM reference_decisions
            WHERE decision = 'DISTINCT'
        )
        GROUP BY ref_modele
        HAVING count > 1
        ORDER BY count DESC
        """)

    def details_appareils_doublons(self, ids: Iterable[int]) -> List[Tuple]:
        """Détail des appareils `ids` (un lot borné par l'appelant) avec leur
        nombre de pièces : (id, ref_modele, type, manufacturer, commercial_ref,
        other_ref, category, notes, pieces_count)."""
        ids = tuple(ids)
        placeholders = ','.join('?' * len(ids))
        detail_query = f"""
            SELECT a.id, a.ref_modele, a.type, a.manufacturer,
                   a.commercial_ref, a.other_ref, a.category, a.notes,
                   COALESCE(pc.cnt, 0) as pieces_count
            FROM appareils a
            LEFT JOIN (
                SELECT pa.appareil_id, COUNT(*) as cnt
                FROM piece_associations pa
                INNER JOIN pieces p ON pa.piece_id = p.id
                WHERE pa.appareil_id IN ({placeholders})
                GROUP BY pa.appareil_id
            ) pc ON pc.appareil_id = a.id
            WHERE a.id IN ({placeholders})
            """
        return self.execute_query(detail_query, ids + ids)

    def groupes_doublons_pieces(self) -> List[Tuple]:
        """[(ref_piece, nb)] des références de pièce présentes plusieurs fois
        (les 100 plus nombreuses)."""
        return self.execute_query("""
        SELECT ref_piece, COUNT(*) as count
        FROM pieces
        WHERE ref_piece IS NOT NULL AND ref_piece != ''
        GROUP BY ref_piece
        HAVING count > 1
        ORDER BY count DESC
        LIMIT 100
        """)

    def compter_vrais_doublons(self) -> List[Tuple]:
        """[(ref_modele, nb)] des ref_modele en doublon hors décision DISTINCT
        (indicateur de la barre d'outils ; erreur SQL remontée)."""
        return self.execute_custom_query("""
            WITH duplicate_refs AS (
                SELECT ref_modele, COUNT(*) as total_count
                FROM appareils
                WHERE ref_modele IS NOT NULL AND ref_modele != ''
                GROUP BY ref_modele
                HAVING COUNT(*) > 1
            )
            SELECT dr.ref_modele, dr.total_count
            FROM duplicate_refs dr
            LEFT JOIN reference_decisions rd ON dr.ref_modele = rd.ref_modele
            WHERE rd.decision IS NULL OR rd.decision != 'DISTINCT'
            ORDER BY dr.total_count DESC
            """)
