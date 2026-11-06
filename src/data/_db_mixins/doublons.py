"""
Écritures du nettoyage des doublons, mixées dans DatabaseManager.

Requêtes autrefois écrites dans DuplicatesAnalysisService (_merge_devices,
_delete_duplicate_pieces), rassemblées dans la couche données (restes de
l'audit, 2026-11-06). Le SQL est repris tel quel, avec la même méthode
d'exécution : lot atomique pour la fusion, execute_write (commité) pour la
suppression. Les journaux restent dans le service.
"""

from typing import List


class DatabaseDoublonsMixin:
    """Fusion d'appareils doublons et suppression des pièces dupliquées."""

    def fusionner_appareils(self, master_id: int, duplicate_ids: List[int]) -> bool:
        """Fusionner des appareils doublons vers l'appareil maître, en UNE
        transaction : pour chaque doublon, retirer ses associations déjà
        portées par le maître (contrainte UNIQUE), transférer les autres au
        maître, puis supprimer le doublon. Supprimer l'appareil sans avoir
        transféré ses pièces laisserait des associations orphelines.

        Returns: True si tout a été commité.
        """
        operations = []
        for duplicate_id in duplicate_ids:
            # 1. Associations que le maître a déjà (éviter les violations UNIQUE)
            operations.append(("""
            DELETE FROM piece_associations
            WHERE appareil_id = ?
            AND piece_id IN (
                SELECT piece_id FROM piece_associations
                WHERE appareil_id = ?
            )
            """, (duplicate_id, master_id)))

            # 2. Transférer les pièces restantes du doublon vers le maître
            operations.append((
                "UPDATE piece_associations SET appareil_id = ? WHERE appareil_id = ?",
                (master_id, duplicate_id)
            ))

            # 3. Supprimer l'appareil doublon
            operations.append(("DELETE FROM appareils WHERE id = ?", (duplicate_id,)))

        return self.execute_write_batch(operations)

    def supprimer_pieces_dupliquees(self, ref_piece: str) -> int:
        """Supprimer les pièces dupliquées de `ref_piece` en gardant la plus
        récente (id le plus élevé), commité.

        Returns: nombre de lignes supprimées, ou -1 en cas d'échec.
        """
        return self.execute_write("""
        DELETE FROM pieces
        WHERE ref_piece = ?
        AND id NOT IN (
            SELECT MAX(id) FROM pieces WHERE ref_piece = ?
        )
        """, (ref_piece, ref_piece))
