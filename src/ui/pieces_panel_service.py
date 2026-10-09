"""
Service du panneau des pièces
Responsabilités:
- Mise à jour du panneau selon la sélection
- Gestion des sélections simples et multiples
- Mise à jour de l'en-tête (nom appareil + compteur) et du titre de l'onglet
- Placeholder quand aucun appareil n'est sélectionné
"""

from typing import Set, List, Optional
from .qt_imports import QListWidgetItem, Qt, QColor
from src.core.logger import app_logger
from ..utils.error_handler import handle_pieces_panel_errors


class PiecesPanelService:
    """
    Service spécialisé pour la gestion du panneau des pièces.
    """

    def __init__(self, main_window):
        self.main_window = main_window

    # ── Point d'entrée principal ───────────────────────────────────────────

    @handle_pieces_panel_errors()
    def update_pieces_panel(self) -> None:
        """
        Mettre à jour le panneau selon la sélection courante.
        - Aucune sélection : placeholder
        - Sélection simple : toutes les pièces de l'appareil
        - Sélection multiple : pièces communes
        """
        self.main_window.pieces_list.clear()
        selected_rows = self._get_selected_rows()

        # Carte « nouvelle pièce » ouverte : sa cible suit la sélection
        card = getattr(self.main_window, 'piece_add_card', None)
        if card is not None and card.isVisible():
            card.set_target_count(len(selected_rows))

        if not selected_rows:
            self._show_placeholder()
            self._update_header(label="", count=0)
            return

        if len(selected_rows) == 1:
            # Message visible seulement si l'appareil n'a aucune pièce (liste vide) ;
            # auparavant le panneau restait blanc, sans explication.
            self._set_placeholder("Aucune pièce associée à cet appareil")
            self._handle_single_selection(selected_rows)
        else:
            self._set_placeholder(
                f"Aucune pièce commune aux {len(selected_rows)} appareils sélectionnés")
            self._handle_multiple_selection(selected_rows)

    # ── Sélection simple ───────────────────────────────────────────────────

    def _handle_single_selection(self, selected_rows: Set[int]) -> None:
        row = list(selected_rows)[0]
        db_id = self.main_window.table_fill_service.get_db_id_from_row(
            self.main_window.table, row
        )
        pieces = self.main_window.db_manager.get_pieces_for_appareil(db_id)
        refs = [ref_piece for ref_piece, _ in pieces]
        statuses = self.main_window.db_manager.get_pieces_statuses_batch(refs)

        for ref_piece, description in pieces:
            status_info = statuses.get(ref_piece, {'status': 'current', 'ref_new': None, 'refs_old': None})
            self.main_window.pieces_list.add_piece_item(ref_piece, description or "", status_info)

        # En-tête : nom de l'appareil
        device_label = self._get_device_label(db_id)
        self._update_header(label=device_label, count=len(pieces))

    # ── Sélection multiple ─────────────────────────────────────────────────

    def _handle_multiple_selection(self, selected_rows: Set[int]) -> None:
        all_pieces_sets = self._get_pieces_sets_for_rows(selected_rows)

        if not all_pieces_sets:
            self._update_header(label=f"{len(selected_rows)} appareils sélectionnés", count=0)
            return

        common_pieces = set.intersection(*all_pieces_sets)

        if common_pieces:
            self._display_common_pieces(common_pieces, selected_rows)
            self._update_header(
                label=f"{len(selected_rows)} appareils sélectionnés",
                count=len(common_pieces)
            )
        else:
            self._display_no_common_pieces(len(selected_rows))
            self._update_header(
                label=f"{len(selected_rows)} appareils sélectionnés",
                count=0
            )

    def _get_pieces_sets_for_rows(self, selected_rows: Set[int]) -> List[Set[str]]:
        result = []
        for row in selected_rows:
            piece_refs = self._safe_get_pieces_for_row(row)
            if piece_refs is not None:
                result.append(piece_refs)
        return result

    def _display_common_pieces(self, common_pieces: Set[str], selected_rows: Set[int]) -> None:
        statuses = self.main_window.db_manager.get_pieces_statuses_batch(list(common_pieces))
        for ref in sorted(common_pieces):
            description = self._get_piece_description(ref, selected_rows)
            status_info = statuses.get(ref, {'status': 'current', 'ref_new': None, 'refs_old': None})
            item = self.main_window.pieces_list.add_piece_item(ref, description or "", status_info)
            item.setBackground(QColor(240, 248, 255))

    def _display_no_common_pieces(self, selected_count: int) -> None:
        item = QListWidgetItem(f"Aucune pièce commune aux {selected_count} appareils sélectionnés")
        item.setForeground(QColor(108, 117, 125))
        self.main_window.pieces_list.addItem(item)

    # ── Placeholder ────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        """Afficher un message quand aucun appareil n'est sélectionné."""
        self._set_placeholder("Sélectionnez un appareil pour voir ses pièces")

    def _set_placeholder(self, text: str) -> None:
        """Message centré de la liste vide (peint par PiecesListWidget, pas un item)."""
        pieces_list = self.main_window.pieces_list
        if hasattr(pieces_list, 'set_placeholder_text'):
            pieces_list.set_placeholder_text(text)

    # ── En-tête et titre d'onglet ──────────────────────────────────────────

    def _update_header(self, label: str, count: int) -> None:
        """Mettre à jour le label d'en-tête et le compteur."""
        if hasattr(self.main_window, 'pieces_header_label'):
            self.main_window.pieces_header_label.setText(label)

        if hasattr(self.main_window, 'pieces_count_label'):
            self.main_window.pieces_count_label.setText(
                f"{count} pièce{'s' if count > 1 else ''}" if count else ""
            )

    def _get_device_label(self, db_id: int) -> str:
        """Retourner 'Type · Fabricant  [ref_modele – ref_commercial]' pour l'appareil donné."""
        try:
            info = self.main_window.db_manager.get_device_info(db_id)
            if info:
                main_parts = [info.get('type', ''), info.get('manufacturer', '')]
                label = "  ·  ".join(p for p in main_parts if p)
                ref_parts = [info.get('ref_modele', ''), info.get('commercial_ref', '')]
                refs = "  –  ".join(p for p in ref_parts if p)
                if refs:
                    label = f"{label}  [{refs}]" if label else f"[{refs}]"
                return label
        except Exception:
            pass
        return ""

    # ── Helpers internes ───────────────────────────────────────────────────

    def _get_selected_rows(self) -> Set[int]:
        selected_rows = set()
        selected_ranges = self.main_window.table.selectedRanges()
        if selected_ranges:
            for r in selected_ranges:
                for row in range(r.topRow(), r.bottomRow() + 1):
                    selected_rows.add(row)
        else:
            current_row = self.main_window.table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)
        return selected_rows

    def _get_piece_description(self, ref_piece: str, selected_rows: Set[int]) -> str:
        for row in selected_rows:
            desc = self._safe_get_piece_description_for_row(row, ref_piece)
            if desc:
                return desc
        return ""

    @handle_pieces_panel_errors(return_value=None)
    def _safe_get_pieces_for_row(self, row: int) -> Optional[Set[str]]:
        db_id = self.main_window.table_fill_service.get_db_id_from_row(
            self.main_window.table, row
        )
        pieces = self.main_window.db_manager.get_pieces_for_appareil(db_id)
        return {ref_piece for ref_piece, _ in pieces}

    @handle_pieces_panel_errors(return_value="")
    def _safe_get_piece_description_for_row(self, row: int, ref_piece: str) -> str:
        db_id = self.main_window.table_fill_service.get_db_id_from_row(
            self.main_window.table, row
        )
        pieces = self.main_window.db_manager.get_pieces_for_appareil(db_id)
        for ref, desc in pieces:
            if ref == ref_piece and desc:
                return desc
        return ""
