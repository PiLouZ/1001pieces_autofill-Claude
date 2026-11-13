"""
Export EveryParts des fiches reprises du site (CDC docs/cdc_import_fiches_site.md,
§ 10.18 et § 10.19)

Chaque produit du site repris (`produits_site` : référence produit `.product-reference`,
n° du produit, pièce) donne ses lignes EveryParts : un appareil compatible par ligne,
la 1ʳᵉ colonne (`product` = `{export_ref}`) portant la référence produit du site.
Les appareils sont ceux de la pièce **et de ses anciennes références** (lignée,
décision de l'utilisateur du 2026-11-13) : c'est la liste que montre la fiche du
site (20744 : les 450 appareils de ses 4 prédécesseurs).

Le format est celui de l'export CSV de la configuration (colonnes, séparateur,
encodage, nom de fichier), par le même rendu (`render_csv_row_with`) : rien de
nouveau à paramétrer. Un fichier par produit, ou un seul pour toute la sélection.
Chaque produit exporté garde sa date d'export (`produits_site.exporte_le`).
"""

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from ..core.logger import app_logger
from .base_service import BaseService

Progression = Callable[[int, int, str], None]


@dataclass
class ResultatExport:
    fichiers: List[str] = field(default_factory=list)
    produits: int = 0
    lignes: int = 0
    sans_appareil: List[str] = field(default_factory=list)   # réf. produit sans appareil
    annule: bool = False

    def resume(self) -> str:
        texte = (f"{self.produits} produit(s), {self.lignes} ligne(s) dans "
                 f"{len(self.fichiers)} fichier(s)")
        if self.sans_appareil:
            texte += f" ; {len(self.sans_appareil)} produit(s) sans appareil, non exporté(s)"
        return texte


class ExportFichesReprisesService(BaseService):
    """Export EveryParts des produits du site repris."""

    def __init__(self, db_manager, parent_window=None, parent=None):
        super().__init__(parent_window, parent)
        self.db = db_manager

    def _service_config(self):
        return getattr(self.parent_window, 'export_config_service', None)

    def dossier(self) -> str:
        from .export_config_service import resolve_output_dir
        return resolve_output_dir(self._service_config())

    # --- Produits et lignes ------------------------------------------------------
    def produits(self, non_exportes: bool = False) -> List[Dict]:
        """Produits du site repris, par n° de produit ; `non_exportes` : jamais
        exportés, ou relus depuis leur dernier export."""
        return self.db.produits_site_reprises(non_exportes=non_exportes)

    def references(self, ref_piece: str) -> List[str]:
        """La pièce et ses anciennes références (lignée)."""
        return [ref_piece] + [r for r in self.db.get_all_predecessors(ref_piece) if r != ref_piece]

    def lignes(self, ref_piece: str) -> List[Tuple]:
        """Appareils de la pièce et de sa lignée, une fois chacun :
        (type, marque, réf. modèle, nom commercial, autre réf., réf. de la pièce)."""
        refs = self.references(ref_piece)
        q = ','.join('?' * len(refs))
        with self.db._query_lock:
            rows = self.db.conn.execute(
                f"SELECT a.id, a.type, a.manufacturer, a.ref_modele, a.commercial_ref, "
                f"a.other_ref FROM piece_associations pa "
                f"JOIN pieces p ON p.id = pa.piece_id JOIN appareils a ON a.id = pa.appareil_id "
                f"WHERE p.ref_piece IN ({q}) "
                f"ORDER BY a.manufacturer COLLATE NOCASE, a.ref_modele COLLATE NOCASE, a.id",
                refs).fetchall()
        vus, lignes = set(), []
        for ident, type_, marque, ref, nom, autre in rows:
            if ident in vus:
                continue
            vus.add(ident)
            lignes.append((type_ or '', marque or '', ref or '', nom or '', autre or '', ref_piece))
        return lignes

    # --- Export ------------------------------------------------------------------
    def exporter(self, produits: List[Dict], dossier: str = '', un_seul_fichier: bool = False,
                 progression: Optional[Progression] = None,
                 annule: Optional[Callable[[], bool]] = None) -> ResultatExport:
        """Écrit les fichiers EveryParts des produits donnés (hors du thread principal)."""
        from .export_config_service import (_assainir_ligne_csv, format_csv_filename,
                                            get_csv_settings, render_csv_row_with)
        reglages = get_csv_settings(self._service_config())
        dossier = dossier or self.dossier()
        os.makedirs(dossier, exist_ok=True)
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        res = ResultatExport()
        exportes: List[str] = []
        unique = None
        if un_seul_fichier:
            nom = format_csv_filename(reglages['filename_pattern'], export_ref='fiches_reprises',
                                      timestamp=horodatage)
            unique = self._ouvrir(os.path.join(dossier, nom), reglages)
            res.fichiers.append(unique[2])
        try:
            for k, produit in enumerate(produits):
                if annule is not None and annule():
                    res.annule = True
                    break
                ref_interne = produit['ref_interne']
                if progression is not None:
                    progression(k, len(produits), f"{ref_interne} ({produit['ref_piece']})")
                lignes = self.lignes(produit['ref_piece'])
                if not lignes:
                    res.sans_appareil.append(ref_interne)
                    continue
                if unique is None:
                    nom = format_csv_filename(reglages['filename_pattern'], export_ref=ref_interne,
                                              timestamp=horodatage, produit=produit)
                    fichier = self._ouvrir(os.path.join(dossier, nom), reglages)
                    res.fichiers.append(fichier[2])
                else:
                    fichier = unique
                ecrivain = fichier[1]
                for record in lignes:
                    ecrivain.writerow(_assainir_ligne_csv(
                        render_csv_row_with(reglages['columns'], record, ref_interne, produit)))
                if unique is None:
                    fichier[0].close()
                res.produits += 1
                res.lignes += len(lignes)
                exportes.append(ref_interne)
        finally:
            if unique is not None:
                unique[0].close()
        if exportes:
            self.db.marquer_produits_exportes(exportes, datetime.now().isoformat(timespec='seconds'))
        if progression is not None:
            progression(len(produits), len(produits), "Export terminé")
        app_logger.info(f"[Export EveryParts fiches reprises] {res.resume()} → {dossier}")
        return res

    @staticmethod
    def _ouvrir(chemin: str, reglages: Dict):
        flux = open(chemin, 'w', newline='', encoding=reglages['encoding'])
        ecrivain = csv.writer(flux, delimiter=reglages['separator'])
        ecrivain.writerow(reglages['headers'])
        return flux, ecrivain, chemin
