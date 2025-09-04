"""
Service Table Widget - Phase 2.17 Refactoring
Extrait de main_refactored.py pour centraliser la logique CustomTableWidget

Responsabilités:
- Gestion personnalisée des événements clavier (Delete, Backspace, Cmd+D)
- Auto-complétion avancée pour colonnes Type et Fabricant
- Interface de filtrage intelligent avec popup
- Intégration avec le DatabaseManager pour les suggestions
"""

from typing import List, Optional
from PyQt5.QtWidgets import (QTableWidget, QApplication, QDialog, QVBoxLayout, 
                           QLineEdit, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeyEvent

from ..core.logger import app_logger
from ..data.database_manager import DatabaseManager


class CustomTableWidget(QTableWidget):
    """Table personnalisée avec gestion des touches Delete/Backspace et auto-complétion"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_manager: Optional[DatabaseManager] = None
        
    def set_db_manager(self, db_manager: DatabaseManager):
        """Définir le gestionnaire de base de données pour l'auto-complétion"""
        self.db_manager = db_manager
    
    def keyPressEvent(self, event: QKeyEvent):
        """Gestion des événements clavier"""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # Effacer le contenu des cellules sélectionnées
            selected_items = self.selectedItems()
            if selected_items:
                for item in selected_items:
                    if item:
                        item.setText("")
                return
        
        # Popup avec liste complète via Cmd+D (ou Ctrl+D sur Windows/Linux)
        if event.key() == Qt.Key_D and (event.modifiers() & Qt.MetaModifier or event.modifiers() & Qt.ControlModifier):
            # Récupérer le texte en cours d'édition si possible
            current_editor_text = None
            if self.state() == QTableWidget.EditingState:
                # La table est en mode édition, récupérer le texte de l'éditeur actuel
                focus_widget = QApplication.focusWidget()
                if focus_widget and hasattr(focus_widget, 'text'):
                    current_editor_text = focus_widget.text()
            
            self._show_completion_popup(current_editor_text)
            return
        
        # Gestion de la touche Entrée pour passer à la cellule suivante vers le bas
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            current_item = self.currentItem()
            if current_item:
                current_row = current_item.row()
                current_col = current_item.column()
                
                # Passer à la cellule suivante vers le bas
                if current_row < self.rowCount() - 1:
                    next_row = current_row + 1
                    next_item = self.item(next_row, current_col)
                    if next_item:
                        self.setCurrentItem(next_item)
                        self.setFocus()  # S'assurer que le tableau garde le focus
            return
        
        # Appeler la méthode parent pour les autres touches
        super().keyPressEvent(event)
    
    def _show_completion_popup(self, editor_text: Optional[str] = None):
        """Afficher popup avec auto-complétion avancée via Cmd+D"""
        current_item = self.currentItem()
        if not current_item or not self.db_manager:
            return
            
        column = current_item.column()
        
        # Popup seulement pour les colonnes 0 (Type) et 1 (Fabricant)
        if column == 0:  # Colonne Type
            suggestions = self._get_all_types()
            column_name = "Type"
        elif column == 1:  # Colonne Fabricant
            suggestions = self._get_all_manufacturers()
            column_name = "Fabricant"
        else:
            return
        
        if not suggestions:
            return
        
        # Créer une boîte de dialogue personnalisée
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Auto-complétion {column_name}")
        dialog.setModal(True)
        dialog.resize(300, 400)
        
        layout = QVBoxLayout()
        
        # Champ de recherche
        search_input = QLineEdit()
        search_input.setPlaceholderText(f"Tapez pour filtrer les {column_name.lower()}s...")
        
        # Utiliser le texte de l'éditeur s'il est fourni, sinon le texte sauvegardé
        if editor_text is not None:
            current_text = editor_text
        else:
            current_text = current_item.text()
        
        search_input.setText(current_text)
        layout.addWidget(search_input)
        
        # Liste des suggestions
        suggestions_list = QListWidget()
        layout.addWidget(suggestions_list)
        
        # Fonction pour filtrer les suggestions
        def filter_suggestions():
            text = search_input.text().lower()
            suggestions_list.clear()
            
            for suggestion in suggestions:
                if text in suggestion.lower():
                    item = QListWidgetItem(suggestion)
                    suggestions_list.addItem(item)
            
            # Sélectionner automatiquement le premier élément
            if suggestions_list.count() > 0:
                suggestions_list.setCurrentRow(0)
                # Ne pas donner le focus à la liste pour garder le focus sur le champ de saisie
        
        # Fonction pour appliquer la sélection
        def apply_selection():
            current_list_item = suggestions_list.currentItem()
            if current_list_item:
                current_item.setText(current_list_item.text())
                dialog.accept()
            elif search_input.text():
                current_item.setText(search_input.text())
                dialog.accept()
        
        # Gestion des touches clavier pour la navigation
        def handle_key_press(event):
            if event.key() == Qt.Key_Down:
                if suggestions_list.currentRow() < suggestions_list.count() - 1:
                    suggestions_list.setCurrentRow(suggestions_list.currentRow() + 1)
                suggestions_list.setFocus()  # Donner le focus seulement quand on navigue
            elif event.key() == Qt.Key_Up:
                if suggestions_list.currentRow() > 0:
                    suggestions_list.setCurrentRow(suggestions_list.currentRow() - 1)
                suggestions_list.setFocus()  # Donner le focus seulement quand on navigue
            elif event.key() in [Qt.Key_Return, Qt.Key_Enter]:
                apply_selection()
            else:
                QLineEdit.keyPressEvent(search_input, event)
        
        search_input.keyPressEvent = handle_key_press
        
        # Gestion des touches pour la liste
        def handle_list_key_press(event):
            if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
                apply_selection()
            elif event.key() == Qt.Key_Escape:
                dialog.reject()
            else:
                QListWidget.keyPressEvent(suggestions_list, event)
        
        suggestions_list.keyPressEvent = handle_list_key_press
        
        # Connecter les événements
        search_input.textChanged.connect(filter_suggestions)
        suggestions_list.itemDoubleClicked.connect(apply_selection)
        
        # Filtrer initialement
        filter_suggestions()
        
        dialog.setLayout(layout)
        search_input.setFocus()
        search_input.selectAll()
        
        dialog.exec_()
    
    
    def _get_type_suggestions(self, partial_text: str) -> List[str]:
        """Obtenir des suggestions pour la colonne Type"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT type FROM appareils 
                WHERE type LIKE ? AND type != '' 
                ORDER BY type
                LIMIT 20
            """, (f"{partial_text}%",))
            
            return [row[0] for row in result]
        except Exception as e:
            app_logger.error(f"Erreur récupération suggestions type: {e}")
            return []
    
    def _get_manufacturer_suggestions(self, partial_text: str) -> List[str]:
        """Obtenir des suggestions pour la colonne Fabricant"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT manufacturer FROM appareils 
                WHERE manufacturer LIKE ? AND manufacturer != '' 
                ORDER BY manufacturer
                LIMIT 20
            """, (f"{partial_text}%",))
            
            return [row[0] for row in result]
        except Exception as e:
            app_logger.error(f"Erreur récupération suggestions fabricant: {e}")
            return []
    
    def _get_all_types(self) -> List[str]:
        """Obtenir toutes les valeurs Type disponibles"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT type FROM appareils 
                WHERE type != '' 
                ORDER BY type
            """)
            
            return [row[0] for row in result]
        except Exception as e:
            app_logger.error(f"Erreur récupération tous les types: {e}")
            return []
    
    def _get_all_manufacturers(self) -> List[str]:
        """Obtenir toutes les valeurs Fabricant disponibles"""
        if not self.db_manager:
            return []
        
        try:
            result = self.db_manager.execute_query("""
                SELECT DISTINCT manufacturer FROM appareils 
                WHERE manufacturer != '' 
                ORDER BY manufacturer
            """)
            
            return [row[0] for row in result]
        except Exception as e:
            app_logger.error(f"Erreur récupération tous les fabricants: {e}")
            return []


class TableWidgetService:
    """
    Service pour la gestion de la CustomTableWidget
    
    Responsabilités:
    - Créer et configurer la table personnalisée
    - Connecter la table au DatabaseManager
    - Gérer l'initialisation des composants table
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def create_custom_table(self, parent=None) -> CustomTableWidget:
        """
        Créer une CustomTableWidget configurée
        
        Returns:
            CustomTableWidget: Table configurée avec auto-complétion
        """
        table = CustomTableWidget(parent)
        table.set_db_manager(self.db_manager)
        return table