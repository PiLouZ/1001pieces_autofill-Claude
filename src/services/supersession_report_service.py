"""
Service de rapport des chaînes de supersession (F8)
Export CSV de toutes les relations ref_old → ref_new de piece_supersessions,
avec résolution de la référence finale de chaque chaîne.

Permet d'auditer globalement "qui remplace quoi" sans chercher ref par ref
(la bannière de recherche ne montre les chaînes qu'au cas par cas).
"""

import csv
import os
from datetime import datetime

from .base_service import BaseService
from ..core.logger import app_logger
from .export_config_service import resolve_output_dir, _assainir_ligne_csv


class SupersessionReportService(BaseService):
    """Export CSV des chaînes de supersession"""

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent_window, parent)

    def export_chains_csv(self) -> str:
        """Exporter toutes les supersessions vers un CSV dans le dossier d'export.

        Colonnes : ref_remplacee ; ref_remplacante ; ref_finale
        ref_finale = bout de la chaîne (suit les ref_new successives,
        garde anti-cycle incluse).

        Returns:
            Chemin du fichier créé, ou '' en cas d'absence de données/échec.
        """
        db_manager = getattr(self.parent_window, 'db_manager', None)
        if not db_manager:
            app_logger.error("[F8] db_manager indisponible")
            return ''

        rows = db_manager.lister_supersessions()
        if not rows:
            app_logger.info("[F8] Aucune supersession à exporter")
            return ''

        # Résolution de la référence finale de chaque chaîne
        successor = {old: new for old, new in rows}

        def _ref_finale(ref: str) -> str:
            vus = {ref}
            current = ref
            while current in successor:
                current = successor[current]
                if current in vus:  # cycle dans les données : on s'arrête proprement
                    app_logger.warning(f"[F8] Cycle de supersession détecté sur {ref}")
                    break
                vus.add(current)
            return current

        filename = f"supersessions_{datetime.now().strftime('%Y%m%d')}.csv"
        output_dir = resolve_output_dir(
            getattr(self.parent_window, 'export_config_service', None)
        )
        full_path = os.path.join(output_dir, filename)

        with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(['ref_remplacee', 'ref_remplacante', 'ref_finale'])
            for ref_old, ref_new in rows:
                writer.writerow(_assainir_ligne_csv([ref_old, ref_new, _ref_finale(ref_old)]))

        app_logger.info(f"[F8] {len(rows)} supersessions exportées vers {filename}")
        return full_path
