"""
Service pour la gestion du remplissage et de l'affichage des données dans les tables
Extrait des méthodes de remplissage de main_refactored.py
"""

import time
import re
from typing import List, Any, Optional
from PyQt5.QtWidgets import QTableWidgetItem, QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from src.core.config import Config


class TableFillService:
    """Service pour gérer le remplissage des tables et la mise en évidence des recherches"""
    
    def __init__(self, main_window):
        """
        Initialise le service avec référence à la fenêtre principale
        
        Args:
            main_window: Instance de MainWindow
        """
        self.main_window = main_window
    
    def fill_table_chunked(self, table, records: List, progress_dialog, search_term):
        """Remplissage optimisé par chunks pour améliorer la responsivité"""
        chunk_size = Config.CHUNK_SIZE
        total_chunks = (len(records) + chunk_size - 1) // chunk_size
        
        table.blockSignals(True)  # Bloquer les signaux pendant le remplissage
        table.setRowCount(len(records))  # CRUCIAL: Définir le nombre de lignes avant remplissage
        
        try:
            last_update_time = time.time()
            
            for chunk_idx in range(total_chunks):
                start_idx = chunk_idx * chunk_size
                end_idx = min(start_idx + chunk_size, len(records))
                chunk_records = records[start_idx:end_idx]
                
                # Traitement du chunk
                for local_idx, record in enumerate(chunk_records):
                    row_idx = start_idx + local_idx
                    self.fill_single_row(table, row_idx, record, search_term)
                
                # Mise à jour responsive de l'interface
                current_time = time.time()
                if (current_time - last_update_time) * 1000 > Config.RESPONSIVE_UPDATE_INTERVAL:
                    QApplication.processEvents()  # Maintenir la responsivité
                    last_update_time = current_time
                
                # Progression
                if progress_dialog:
                    if progress_dialog.wasCanceled():
                        break
                    progress_value = 60 + ((chunk_idx + 1) / total_chunks) * 35  # 60% -> 95%
                    self._update_progress_with_debounce(
                        progress_dialog, 
                        int(progress_value), 
                        f"Remplissage optimisé... {end_idx}/{len(records)} lignes"
                    )
        
        finally:
            table.blockSignals(False)  # Réactiver les signaux
    
    def fill_table_standard(self, table, records: List, progress_dialog, search_term):
        """Remplissage standard pour les petites tables"""
        table.blockSignals(True)  # CRITIQUE: Bloquer les signaux pour éviter les modifications DB
        table.setRowCount(len(records))  # CRUCIAL: Définir le nombre de lignes avant remplissage
        
        try:
            for row_idx, record in enumerate(records):
                if progress_dialog and progress_dialog.wasCanceled():
                    break
                
                self.fill_single_row(table, row_idx, record, search_term)
                
                # Mise à jour de progression moins fréquente pour petites tables
                if progress_dialog and row_idx % 100 == 0:
                    progress_value = 60 + (row_idx / len(records)) * 35
                    self._update_progress_with_debounce(
                        progress_dialog,
                        int(progress_value),
                        f"Remplissage du tableau... {row_idx}/{len(records)} lignes"
                    )
        
        finally:
            table.blockSignals(False)  # CRITIQUE: Réactiver les signaux
    
    def fill_single_row(self, table, row_idx: int, record, search_term):
        """Remplir une seule ligne de manière optimisée"""
        db_id = record[0]
        
        # En-tête vertical optimisé 
        table.setVerticalHeaderItem(row_idx, QTableWidgetItem(str(row_idx + 1)))
        
        # Traitement optimisé des colonnes par batch
        items_to_set = []  # Liste des (row, col, item) à traiter ensemble
        
        # Traiter toutes les colonnes UI (8 colonnes maintenant, AVEC Nb Pièces)
        for col_idx in range(len(Config.UI_HEADERS)):
            item = self.create_table_item(record, col_idx, db_id, search_term)
            items_to_set.append((row_idx, col_idx, item))
        
        # Appel groupé de setItem pour cette ligne (plus efficace)
        for row, col, item in items_to_set:
            table.setItem(row, col, item)
    
    def create_table_item(self, record, col_idx: int, db_id: int, search_term) -> QTableWidgetItem:
        """Créer un item de table optimisé"""
        if col_idx < len(Config.DB_HEADERS):
            # Colonnes normales de la DB: record[0] = id, record[1..7] = données colonnes
            if col_idx + 1 < len(record):
                actual_data = record[col_idx + 1]  # record[0] = db_id, donc col_idx + 1
                item = QTableWidgetItem(str(actual_data or ""))
            else:
                item = QTableWidgetItem("")
        else:
            # Dernière colonne: Nb Pièces (record[-1] = pieces_count)
            pieces_count = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
            item = QTableWidgetItem(str(pieces_count))
            # Colonne lecture seule pour le nombre de pièces
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            # Style spécial pour la colonne Nb Pièces
            if pieces_count > 0:
                item.setBackground(QColor(220, 248, 198))  # Vert clair
                item.setToolTip(f"{pieces_count} pièce(s) associée(s)")
            else:
                item.setBackground(QColor(248, 248, 248))  # Gris clair
                item.setToolTip("Aucune pièce associée")
        
        # Stocker le db_id dans chaque cellule via UserRole
        item.setData(Qt.ItemDataRole.UserRole, db_id)
        
        # Optimisation: Mise en évidence des résultats de recherche (sauf pour la colonne Nb Pièces)
        if search_term and col_idx < len(Config.DB_HEADERS):
            # PHASE 2.3: Utiliser AdvancedSearchService pour highlighting
            if hasattr(self.main_window, 'advanced_search_service'):
                self.main_window.advanced_search_service.apply_search_highlight(item, search_term)
            else:
                # Fallback vers ancienne méthode
                self.apply_search_highlight(item, search_term)
        
        return item
    
    def apply_search_highlight(self, item: QTableWidgetItem, search_term):
        """Appliquer la mise en évidence de recherche de manière optimisée"""
        item_text = str(item.text()).lower()
        should_highlight = False
        
        if isinstance(search_term, str):
            # Recherche simple (chaîne)
            should_highlight = search_term.lower() in item_text
        elif isinstance(search_term, dict):
            # Recherche parsée (dictionnaire)
            if search_term.get('type') == 'simple':
                # Recherche simple parsée
                terms = search_term.get('terms', [])
                if terms:
                    should_highlight = terms[0].lower() in item_text
            elif search_term.get('type') == 'regex':
                # Recherche par expression régulière
                try:
                    pattern = search_term.get('pattern', '')
                    should_highlight = bool(re.search(pattern, item_text, re.IGNORECASE))
                except:
                    pass
            elif search_term.get('type') == 'or':
                # Recherche avec opérateurs OR
                for group in search_term.get('groups', []):
                    if group.get('type') == 'and':
                        # Tous les termes doivent être présents
                        if all(term.lower() in item_text for term in group.get('terms', [])):
                            should_highlight = True
                            break
        
        if should_highlight:
            item.setBackground(QColor(*Config.SEARCH_HIGHLIGHT_COLOR))

    def get_db_id_from_row(self, table, row: int) -> int:
        """Récupérer le db_id depuis la première cellule de la ligne"""
        # Chercher dans la première cellule non-vide de la ligne
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item and item.data(Qt.ItemDataRole.UserRole) is not None:
                return int(item.data(Qt.ItemDataRole.UserRole))
        raise ValueError(f"Aucun db_id trouvé pour la ligne {row}")
    
    def _update_progress_with_debounce(self, progress_dialog, value, text=None):
        """Déléguer la mise à jour de progression à MainWindow"""
        if hasattr(self.main_window, '_update_progress_with_debounce'):
            self.main_window._update_progress_with_debounce(progress_dialog, value, text)