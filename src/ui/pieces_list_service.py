"""
Service de gestion de la liste des pièces avec boutons d'action au survol - Phase 2.16
Extrait de main_refactored.py pour respecter l'architecture service-orientée

Responsabilités:
- Gestion de la liste des pièces avec boutons d'action au survol
- Widget personnalisé PiecesListWidget avec détection de survol
- Boutons d'action "Edit" et "×" sur chaque élément
- Interface propre entre la liste des pièces et les actions
"""

from typing import Optional
from .qt_imports import (QWidget, QHBoxLayout, QPushButton, QListWidget,
                           QListWidgetItem, QMenu, Qt)
from src.core.logger import app_logger

class PieceActionButtonWidget(QWidget):
    """Widget contenant les boutons d'action pour chaque pièce dans la liste"""
    
    def __init__(self, list_item: QListWidgetItem, parent=None):
        super().__init__(parent)
        self.list_item = list_item
        self.setFixedSize(50, 22)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # Bouton éditer avec icône texte
        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(22, 18)
        edit_btn.setToolTip("Modifier cette pièce")
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 2px;
                font-size: 10px;
                font-weight: bold;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        edit_btn.clicked.connect(self._edit_piece)
        layout.addWidget(edit_btn)
        
        # Bouton supprimer avec icône texte
        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(18, 18)
        delete_btn.setToolTip("Supprimer cette pièce")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 2px;
                font-size: 12px;
                font-weight: bold;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        delete_btn.clicked.connect(self._delete_piece_from_selected)
        layout.addWidget(delete_btn)
        
        layout.addStretch()
        
    def _edit_piece(self):
        """Éditer la pièce - Remonter vers la MainWindow"""
        # Remonter jusqu'à la MainWindow pour trouver les bonnes méthodes
        main_window = self.parent()
        while main_window and not hasattr(main_window, '_edit_piece'):
            main_window = main_window.parent()
        
        if main_window and hasattr(main_window, '_edit_piece'):
            main_window._edit_piece(self.list_item)
    
    def _delete_piece_from_selected(self):
        """Supprimer la pièce des appareils sélectionnés - Remonter vers la MainWindow"""
        # Remonter jusqu'à la MainWindow pour trouver les bonnes méthodes
        main_window = self.parent()
        while main_window and not hasattr(main_window, '_delete_piece_from_selected'):
            main_window = main_window.parent()

        if main_window and hasattr(main_window, '_delete_piece_from_selected'):
            main_window._delete_piece_from_selected(self.list_item)

class PiecesListWidget(QListWidget):
    """Liste des pièces personnalisée avec boutons d'action au survol"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.action_widgets = {}
        self.setMouseTracking(True)
        
    def enterEvent(self, event):
        """Souris entre dans le widget"""
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Souris quitte le widget"""
        super().leaveEvent(event)
        # Masquer tous les boutons d'action
        for widget in self.action_widgets.values():
            widget.hide()
    
    def mouseMoveEvent(self, event):
        """Gérer le survol des éléments de liste"""
        super().mouseMoveEvent(event)
        
        item = self.itemAt(event.pos())
        if item is not None:
            self._show_action_buttons_for_item(item)
        else:
            # Masquer tous les boutons
            for widget in self.action_widgets.values():
                widget.hide()
    
    def _show_action_buttons_for_item(self, item: QListWidgetItem):
        """Afficher les boutons d'action pour un élément"""
        # Masquer tous les boutons d'abord
        for widget in self.action_widgets.values():
            widget.hide()
        
        # Créer ou réutiliser le widget pour cet élément
        item_key = id(item)
        if item_key not in self.action_widgets:
            widget = PieceActionButtonWidget(item, self)
            self.action_widgets[item_key] = widget
            
        # Positionner et afficher le widget
        widget = self.action_widgets[item_key]
        
        # Calculer la position
        rect = self.visualItemRect(item)
        widget.move(rect.right() - widget.width() - 5, rect.top() + 2)
        widget.show()
        widget.raise_()
    
    def clear(self):
        """Override clear pour nettoyer les widgets d'action"""
        # Nettoyer tous les widgets d'action
        for widget in self.action_widgets.values():
            widget.deleteLater()
        self.action_widgets.clear()
        super().clear()

class PiecesListService:
    """
    Service pour la gestion de la liste des pièces avec boutons d'action au survol
    
    Responsabilités:
    - Création et configuration du widget de liste des pièces
    - Gestion des boutons d'action au survol 
    - Interface avec les actions de modification et suppression des pièces
    - Menu contextuel simplifié pour actions spéciales seulement
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def create_pieces_list_widget(self) -> PiecesListWidget:
        """
        Créer et configurer le widget de liste des pièces avec boutons d'action
        
        Returns:
            PiecesListWidget: Widget personnalisé avec boutons au survol
        """
        pieces_list = PiecesListWidget()
        pieces_list.itemDoubleClicked.connect(self.main_window._edit_piece)
        pieces_list.setContextMenuPolicy(Qt.CustomContextMenu)
        pieces_list.customContextMenuRequested.connect(self._show_pieces_context_menu)
        
        app_logger.debug("PiecesListWidget créé avec boutons d'action au survol")
        return pieces_list
    
    def _show_pieces_context_menu(self, position):
        """
        Afficher le menu contextuel simplifié pour les pièces
        Actions de base (modifier/supprimer) maintenant sur boutons survol
        """
        item = self.main_window.pieces_list.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self.main_window)
        
        # Action copier (toujours utile)
        copy_action = menu.addAction("Copier")
        copy_action.triggered.connect(lambda: self.main_window._copy_piece(item))
        
        # Vérifier s'il y a plusieurs appareils sélectionnés
        selected_ranges = self.main_window.table.selectedRanges()
        multiple_selection = len(selected_ranges) > 0 and sum(
            range_sel.bottomRow() - range_sel.topRow() + 1 
            for range_sel in selected_ranges
        ) > 1
        
        # Action spéciale pour suppression de tous les appareils sélectionnés
        if multiple_selection:
            menu.addSeparator()
            delete_from_all_action = menu.addAction("🗑️ Supprimer de tous les appareils sélectionnés")
            delete_from_all_action.triggered.connect(lambda: self.main_window._delete_piece_from_selected(item))
        
        # Afficher le menu
        menu.exec_(self.main_window.pieces_list.mapToGlobal(position))