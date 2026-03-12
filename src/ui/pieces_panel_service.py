"""
Service du panneau des pièces - Phase 2.10
Extrait de main_refactored.py pour centraliser la logique de gestion du panneau des pièces

Responsabilités:
- Mise à jour du panneau des pièces en fonction de la sélection
- Gestion des sélections multiples avec pièces communes
- Récupération et affichage des pièces pour les appareils
- Interface standardisée pour la gestion du widget des pièces
"""

from typing import Set, List, Tuple, Optional
from .qt_imports import QListWidgetItem
from .qt_imports import Qt
from .qt_imports import QColor

from src.core.logger import app_logger
from ..utils.error_handler import handle_pieces_panel_errors

class PiecesPanelService:
    """
    Service spécialisé pour la gestion du panneau des pièces
    
    Responsabilités:
    - Mise à jour du panneau selon la sélection d'appareils
    - Gestion des sélections simples et multiples
    - Calcul et affichage des pièces communes
    - Intégration avec le database manager pour récupérer les pièces
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    @handle_pieces_panel_errors()
    def update_pieces_panel(self) -> None:
        """
        Mettre à jour le panneau des pièces selon la sélection actuelle
        - Sélection simple : affiche toutes les pièces de l'appareil
        - Sélection multiple : affiche seulement les pièces communes
        """
        self.main_window.pieces_list.clear()
        
        # Récupérer toutes les lignes sélectionnées
        selected_rows = self._get_selected_rows()
        
        if not selected_rows:
            return
        
        if len(selected_rows) == 1:
            self._handle_single_selection(selected_rows)
        else:
            self._handle_multiple_selection(selected_rows)
    
    def _get_selected_rows(self) -> Set[int]:
        """
        Récupérer l'ensemble des lignes sélectionnées dans le tableau
        
        Returns:
            Set[int]: Ensemble des numéros de lignes sélectionnées
        """
        selected_rows = set()
        selected_ranges = self.main_window.table.selectedRanges()
        
        if selected_ranges:
            # Utiliser les plages sélectionnées
            for range_sel in selected_ranges:
                for row in range(range_sel.topRow(), range_sel.bottomRow() + 1):
                    selected_rows.add(row)
        else:
            # Fallback sur la ligne courante si aucune sélection
            current_row = self.main_window.table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)
        
        return selected_rows
    
    def _handle_single_selection(self, selected_rows: Set[int]) -> None:
        """
        Gérer la sélection d'un seul appareil
        
        Args:
            selected_rows: Ensemble contenant une seule ligne sélectionnée
        """
        row = list(selected_rows)[0]
        db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, row)
        pieces = self.main_window.db_manager.get_pieces_for_appareil(db_id)
        
        refs = [ref_piece for ref_piece, _ in pieces]
        statuses = self.main_window.db_manager.get_pieces_statuses_batch(refs)

        for ref_piece, description in pieces:
            item_text = ref_piece
            if description:
                item_text += f" - {description}"

            status_info = statuses.get(ref_piece, {'status': 'current', 'ref_new': None})
            if status_info['status'] == 'superseded':
                item_text += " →"
                tooltip = f"Remplacée par {status_info['ref_new']}"
            elif status_info['status'] == 'obsolete':
                item_text += " ⚠️"
                tooltip = "Obsolète — aucun remplacement"
            else:
                tooltip = description or ""

            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, ref_piece)
            if tooltip:
                item.setToolTip(tooltip)
            self.main_window.pieces_list.addItem(item)
    
    def _handle_multiple_selection(self, selected_rows: Set[int]) -> None:
        """
        Gérer la sélection de plusieurs appareils
        Affiche seulement les pièces communes à tous les appareils sélectionnés
        
        Args:
            selected_rows: Ensemble des lignes sélectionnées
        """
        all_pieces_sets = self._get_pieces_sets_for_rows(selected_rows)
        
        if all_pieces_sets:
            # Calculer l'intersection de tous les sets (pièces communes)
            common_pieces = set.intersection(*all_pieces_sets)
            
            if common_pieces:
                self._display_common_pieces(common_pieces, selected_rows)
            else:
                self._display_no_common_pieces(len(selected_rows))
    
    def _get_pieces_sets_for_rows(self, selected_rows: Set[int]) -> List[Set[str]]:
        """
        Récupérer les ensembles de pièces pour chaque ligne sélectionnée
        
        Args:
            selected_rows: Ensemble des lignes sélectionnées
            
        Returns:
            List[Set[str]]: Liste des ensembles de références de pièces
        """
        all_pieces_sets = []
        
        for row in selected_rows:
            piece_refs = self._safe_get_pieces_for_row(row)
            if piece_refs is not None:
                all_pieces_sets.append(piece_refs)
        
        return all_pieces_sets
    
    def _display_common_pieces(self, common_pieces: Set[str], selected_rows: Set[int]) -> None:
        """
        Afficher les pièces communes dans le panneau
        
        Args:
            common_pieces: Ensemble des références de pièces communes
            selected_rows: Ensemble des lignes sélectionnées
        """
        statuses = self.main_window.db_manager.get_pieces_statuses_batch(list(common_pieces))

        for common_ref in sorted(common_pieces):
            description = self._get_piece_description(common_ref, selected_rows)

            base_text = f"{common_ref} - {description}" if description else common_ref
            status_info = statuses.get(common_ref, {'status': 'current', 'ref_new': None})
            if status_info['status'] == 'superseded':
                base_text += " →"
                tooltip = f"Remplacée par {status_info['ref_new']}"
            elif status_info['status'] == 'obsolete':
                base_text += " ⚠️"
                tooltip = "Obsolète — aucun remplacement"
            else:
                tooltip = ""

            item_text = f"{base_text} (commune à {len(selected_rows)} appareils)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, common_ref)
            item.setBackground(QColor(240, 248, 255))  # Bleu très clair
            if tooltip:
                item.setToolTip(tooltip)
            self.main_window.pieces_list.addItem(item)
    
    def _get_piece_description(self, ref_piece: str, selected_rows: Set[int]) -> str:
        """
        Récupérer la description d'une pièce depuis le premier appareil qui la contient
        
        Args:
            ref_piece: Référence de la pièce
            selected_rows: Ensemble des lignes sélectionnées
            
        Returns:
            str: Description de la pièce ou chaîne vide si non trouvée
        """
        for row in selected_rows:
            desc = self._safe_get_piece_description_for_row(row, ref_piece)
            if desc:
                return desc
        
        return ""
    
    def _display_no_common_pieces(self, selected_count: int) -> None:
        """
        Afficher un message quand aucune pièce commune n'est trouvée
        
        Args:
            selected_count: Nombre d'appareils sélectionnés
        """
        item = QListWidgetItem(f"Aucune pièce commune aux {selected_count} appareils sélectionnés")
        item.setForeground(QColor(108, 117, 125))  # Gris
        self.main_window.pieces_list.addItem(item)

    @handle_pieces_panel_errors(return_value=None)
    def _safe_get_pieces_for_row(self, row: int) -> Optional[Set[str]]:
        """Récupérer les pièces pour une ligne de manière sécurisée"""
        db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, row)
        pieces = self.main_window.db_manager.get_pieces_for_appareil(db_id)
        return {ref_piece for ref_piece, description in pieces}

    @handle_pieces_panel_errors(return_value="")
    def _safe_get_piece_description_for_row(self, row: int, ref_piece: str) -> str:
        """Récupérer la description d'une pièce pour une ligne de manière sécurisée"""
        db_id = self.main_window.table_fill_service.get_db_id_from_row(self.main_window.table, row)
        pieces = self.main_window.db_manager.get_pieces_for_appareil(db_id)
        for ref, desc in pieces:
            if ref == ref_piece and desc:
                return desc
        return ""