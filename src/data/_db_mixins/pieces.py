"""
Lectures sur les pièces, mixées dans DatabaseManager.

Requêtes autrefois écrites dans les fenêtres (gestionnaire de pièces, sélecteur,
import, SEO) et des services (recherche, rapport de supersession), rassemblées
dans la couche données (audit 2026-11-05). Le SQL est repris tel quel.

Chaque méthode passe par execute_query (erreur avalée → []) ou
execute_custom_query (erreur remontée), comme l'appel d'origine : la
mécanique d'erreur et de verrou est inchangée. Elles ne dépendent que de ces
deux méthodes : une base de test simplifiée peut hériter de ce mixin.
"""

from typing import Iterable, List, Tuple

from ...core.config import Config


# Types : NULLIF(TRIM(…), '') — un type VIDE (cellule vidée par Suppr, ligne
# Cmd+N non remplie) n'est pas NULL, donc GROUP_CONCAT l'ajoutait et la
# colonne affichait « Lave-vaisselle, » (virgule finale).
REQUETE_PIECES_COMPLETE = """
        SELECT
            p.ref_piece,
            p.description,
            COUNT(DISTINCT pa.appareil_id) as nb_appareils,
            GROUP_CONCAT(DISTINCT NULLIF(TRIM(a.type), '')) as types_appareils,
            COALESCE(p.is_phantom, 0) as is_phantom
        FROM pieces p
        LEFT JOIN piece_associations pa ON p.id = pa.piece_id
        LEFT JOIN appareils a ON pa.appareil_id = a.id
        GROUP BY p.id, p.ref_piece, p.description, p.is_phantom
        ORDER BY nb_appareils DESC, p.ref_piece ASC
        """


class DatabasePiecesMixin:
    """Lectures sur la table pieces (et ses associations)."""

    # ── Listes de pièces ─────────────────────────────────────────────────────

    def lister_refs_pieces(self) -> List[Tuple]:
        """Références de pièces (5 000 au plus), pour l'autocomplétion de l'import."""
        return self.execute_query("SELECT ref_piece FROM pieces ORDER BY ref_piece LIMIT 5000")

    def lister_pieces_apercu(self) -> List[Tuple]:
        """Premier affichage rapide du gestionnaire de pièces, sans comptages :
        (ref_piece, description, 0, NULL, is_phantom)."""
        return self.execute_query("""
        SELECT p.ref_piece, p.description, 0, NULL, COALESCE(p.is_phantom, 0)
        FROM pieces p
        ORDER BY p.ref_piece ASC
        """)

    def lister_pieces_completes(self) -> List[Tuple]:
        """Gestionnaire de pièces, données complètes : (ref_piece, description,
        nb_appareils, types_appareils, is_phantom)."""
        return self.execute_query(REQUETE_PIECES_COMPLETE)

    def lister_pieces_selecteur(self) -> List[Tuple]:
        """Sélecteur de pièce : (ref_piece, description, is_obsolete, is_phantom)."""
        return self.execute_query("""
                SELECT p.ref_piece, p.description,
                       COALESCE(p.is_obsolete, 0), COALESCE(p.is_phantom, 0)
                FROM pieces p
                ORDER BY p.ref_piece ASC
            """)

    # ── Une pièce, ou quelques-unes ──────────────────────────────────────────

    def lire_libelle_piece(self, ref_piece: str) -> List[Tuple]:
        """[(description,)] de la pièce, ou [] si absente."""
        return self.execute_query(
            "SELECT description FROM pieces WHERE ref_piece = ? LIMIT 1", [ref_piece])

    def lire_libelles_pieces(self, refs: Iterable[str]) -> List[Tuple]:
        """[(ref_piece, description)] des pièces demandées (en une requête)."""
        refs = list(refs)
        placeholders = ",".join(["?"] * len(refs))
        return self.execute_query(
            f"SELECT ref_piece, description FROM pieces WHERE ref_piece IN ({placeholders})",
            refs
        )

    def lire_piece_exacte(self, reference: str) -> List[Tuple]:
        """[(ref_piece, description)] — casse exacte (erreur SQL remontée)."""
        return self.execute_custom_query(
            "SELECT ref_piece, description FROM pieces WHERE ref_piece = ? LIMIT 1", [reference])

    def lire_piece_sans_casse(self, reference: str) -> List[Tuple]:
        """[(ref_piece, description)], deux au plus — casse ignorée : deux lignes
        signalent une référence ambiguë (erreur SQL remontée)."""
        return self.execute_custom_query(
            "SELECT ref_piece, description FROM pieces WHERE ref_piece = ? COLLATE NOCASE LIMIT 2",
            [reference])

    # ── Comptages pour le SEO (erreurs SQL remontées) ────────────────────────

    def compter_modeles_par_ref(self, refs: List[str]) -> List[Tuple]:
        """[(ref_piece, nb de modèles compatibles)] des références données."""
        placeholders = ','.join('?' * len(refs))
        query = f"""SELECT p.ref_piece, COUNT(DISTINCT pa.appareil_id)
                        FROM pieces p
                        JOIN piece_associations pa ON pa.piece_id = p.id
                        WHERE p.ref_piece IN ({placeholders})
                        GROUP BY p.ref_piece"""
        return self.execute_custom_query(query, refs)

    def compter_modeles_compatibles(self, refs: List[str]) -> List[Tuple]:
        """[(nb de modèles distincts compatibles avec l'une des références,)]."""
        placeholders = ','.join('?' * len(refs))
        query = f"""SELECT COUNT(DISTINCT pa.appareil_id)
                        FROM piece_associations pa
                        JOIN pieces p ON pa.piece_id = p.id
                        WHERE p.ref_piece IN ({placeholders})"""
        return self.execute_custom_query(query, refs)

    def compter_appareils_par_type_marque(self, refs: List[str]) -> List[Tuple]:
        """[(type, fabricant, nb de modèles)] pour l'ensemble des références."""
        query = Config.get_query('device_counts_for_pieces',
                                 placeholders=','.join('?' * len(refs)))
        return self.execute_custom_query(query, refs)

    # ── Supersessions ────────────────────────────────────────────────────────

    def lister_supersessions(self) -> List[Tuple]:
        """[(ref_old, ref_new)] de toutes les supersessions, par ancienne réf."""
        return self.execute_query(
            "SELECT ref_old, ref_new FROM piece_supersessions ORDER BY ref_old"
        )
