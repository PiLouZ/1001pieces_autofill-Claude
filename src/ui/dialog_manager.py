"""
🗂️ DialogManager - Gestionnaire unifié des dialogues
Résout le conflit entre les deux DialogService existants
"""

from typing import Optional, Dict, Any, List, Union
from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QTextEdit, QListWidget, QListWidgetItem,
    QInputDialog, Qt, QFont
)
from .message_helper import MessageHelper
from ..core.constants import Messages, UIConfig


class SimpleDialogManager:
    """
    Gestionnaire pour les dialogues simples (remplace l'ancien services/dialog_service.py)
    Responsabilités: Dialogues d'input basiques, catégories, notes
    """
    
    @staticmethod
    def get_text_input(
        parent, 
        title: str, 
        label: str, 
        default_value: str = "",
        placeholder: str = ""
    ) -> Optional[str]:
        """Dialogue d'entrée de texte simple"""
        text, ok = QInputDialog.getText(parent, title, label, text=default_value)
        return text if ok and text.strip() else None
    
    @staticmethod
    def get_multiline_input(
        parent,
        title: str,
        label: str, 
        default_value: str = ""
    ) -> Optional[str]:
        """Dialogue d'entrée de texte multiligne"""
        text, ok = QInputDialog.getMultiLineText(parent, title, label, default_value)
        return text if ok else None
    
    @staticmethod
    def get_categories(parent, current_categories: List[str]) -> Optional[List[str]]:
        """Dialogue de gestion des catégories"""
        text, ok = QInputDialog.getMultiLineText(
            parent,
            "Gestion des Catégories", 
            "Entrez les catégories (une par ligne):",
            '\n'.join(current_categories)
        )
        
        if ok:
            return [line.strip() for line in text.split('\n') if line.strip()]
        return None
    
    @staticmethod
    def get_notes(parent, current_notes: str = "") -> Optional[str]:
        """Dialogue d'édition des notes"""
        text, ok = QInputDialog.getMultiLineText(
            parent,
            "Notes et Commentaires",
            "Entrez vos notes:",
            current_notes
        )
        
        return text if ok else None
    
    @staticmethod
    def get_selection_from_list(
        parent,
        title: str,
        label: str,
        items: List[str],
        current_item: str = ""
    ) -> Optional[str]:
        """Dialogue de sélection dans une liste"""
        item, ok = QInputDialog.getItem(parent, title, label, items, 0, False)
        return item if ok else None


class ComplexDialogManager:
    """
    Gestionnaire pour les dialogues complexes (remplace l'ancien ui/dialog_service.py)
    Responsabilités: Dialogues d'import, autocomplétion, sélections avancées
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
    
    def get_import_options_unified(
        self,
        detected_columns=None,
        default_ref_piece=None,
        import_method="CSV",
        sample_data=None
    ) -> Dict[str, Any]:
        """
        Dialogue unifié pour choisir les options d'import
        Remplace la méthode de l'ancien DialogService complexe
        """
        dialog = ImportOptionsDialog(
            self.main_window,
            detected_columns=detected_columns,
            default_ref_piece=default_ref_piece,
            import_method=import_method,
            sample_data=sample_data
        )
        
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_options()
        return None
    
    def show_autocompletion_popup(
        self,
        parent_widget,
        suggestions: List[str],
        position: tuple = None
    ) -> Optional[str]:
        """Popup d'autocomplétion avancée"""
        popup = AutoCompletionPopup(parent_widget, suggestions, position)
        return popup.show_and_wait()
    
    def get_reference_selection(
        self,
        available_references: List[str],
        title: str = "Sélection de référence"
    ) -> Optional[str]:
        """Dialogue de sélection de référence avec recherche"""
        dialog = ReferenceSelectionDialog(self.main_window, available_references, title)
        
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_selected_reference()
        return None


class ImportOptionsDialog(QDialog):
    """Dialogue complexe pour les options d'import"""
    
    def __init__(self, parent, detected_columns=None, default_ref_piece=None,
                 import_method="CSV", sample_data=None):
        super().__init__(parent)
        self.detected_columns = detected_columns
        self.default_ref_piece = default_ref_piece
        self.import_method = import_method
        self.sample_data = sample_data
        
        self._setup_ui()
        self._init_values()
    
    def _setup_ui(self):
        """Configuration de l'interface"""
        self.setWindowTitle(f"Options d'import {self.import_method}")
        self.setModal(True)
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        
        # Information sur les colonnes détectées
        if self.detected_columns:
            info_text = self._get_info_text()
            info_label = QLabel(info_text)
            info_label.setFont(QFont("", 10, QFont.Bold))
            layout.addWidget(info_label)
        
        # Options d'import
        self._create_import_options(layout)
        
        # Aperçu des données si disponible
        if self.sample_data:
            self._create_data_preview(layout)
        
        # Boutons
        self._create_buttons(layout)
        
        self.setLayout(layout)
    
    def _get_info_text(self) -> str:
        """Obtenir le texte d'information selon le type d'import"""
        if self.import_method == "CSV":
            return f"📊 Fichier CSV détecté : {self.detected_columns} colonnes"
        elif self.import_method == "PDF":
            return f"📄 Données PDF détectées : {self.detected_columns} colonnes"
        else:  # COLLAGE
            return f"📋 Données collées détectées : {self.detected_columns} colonnes"
    
    def _create_import_options(self, layout):
        """Créer les options d'import"""
        # Référence par défaut pour les pièces
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence par défaut:"))
        self.ref_input = QLineEdit(self.default_ref_piece or "")
        self.ref_input.setPlaceholderText("Laisser vide pour détecter automatiquement")
        ref_layout.addWidget(self.ref_input)
        layout.addLayout(ref_layout)
        
        # Options d'import
        self.overwrite_checkbox = QCheckBox("Écraser les données existantes")
        self.validate_checkbox = QCheckBox("Valider les données avant import")
        self.validate_checkbox.setChecked(True)
        
        layout.addWidget(self.overwrite_checkbox)
        layout.addWidget(self.validate_checkbox)
    
    def _create_data_preview(self, layout):
        """Créer l'aperçu des données"""
        preview_label = QLabel("Aperçu des données:")
        preview_label.setFont(QFont("", 9, QFont.Bold))
        layout.addWidget(preview_label)
        
        preview_text = QTextEdit()
        preview_text.setMaximumHeight(100)
        preview_text.setPlainText(str(self.sample_data)[:500] + "..." if len(str(self.sample_data)) > 500 else str(self.sample_data))
        preview_text.setReadOnly(True)
        layout.addWidget(preview_text)
    
    def _create_buttons(self, layout):
        """Créer les boutons de validation"""
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("Importer")
        self.ok_button.setStyleSheet(UIConfig.STYLE_SUCCESS_BUTTON)
        self.ok_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Annuler")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
    
    def _init_values(self):
        """Initialiser les valeurs par défaut"""
        if self.default_ref_piece:
            self.ref_input.setText(self.default_ref_piece)
    
    def get_options(self) -> Dict[str, Any]:
        """Obtenir les options sélectionnées"""
        return {
            'reference_defaut': self.ref_input.text().strip(),
            'ecraser_donnees': self.overwrite_checkbox.isChecked(),
            'valider_donnees': self.validate_checkbox.isChecked(),
            'methode_import': self.import_method,
            'colonnes_detectees': self.detected_columns
        }


class AutoCompletionPopup(QDialog):
    """Popup d'autocomplétion avancée"""
    
    def __init__(self, parent, suggestions: List[str], position: tuple = None):
        super().__init__(parent)
        self.suggestions = suggestions
        self.selected_suggestion = None
        
        self._setup_ui(position)
    
    def _setup_ui(self, position):
        """Configuration du popup"""
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setMaximumHeight(200)
        self.setMinimumWidth(250)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_selected)
        
        for suggestion in self.suggestions:
            self.list_widget.addItem(suggestion)
        
        layout.addWidget(self.list_widget)
        self.setLayout(layout)
        
        # Positionner le popup
        if position:
            self.move(position[0], position[1])
    
    def _on_item_selected(self, item):
        """Gérer la sélection d'un élément"""
        self.selected_suggestion = item.text()
        self.accept()
    
    def show_and_wait(self) -> Optional[str]:
        """Afficher le popup et attendre la sélection"""
        if self.exec_() == QDialog.Accepted:
            return self.selected_suggestion
        return None


class ReferenceSelectionDialog(QDialog):
    """Dialogue de sélection de référence avec recherche"""
    
    def __init__(self, parent, references: List[str], title: str = "Sélection de référence"):
        super().__init__(parent)
        self.all_references = references
        self.filtered_references = references.copy()
        self.selected_reference = None
        
        self.setWindowTitle(title)
        self._setup_ui()
    
    def _setup_ui(self):
        """Configuration de l'interface"""
        self.setModal(True)
        self.setMinimumSize(400, 500)
        
        layout = QVBoxLayout()
        
        # Champ de recherche
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Recherche:"))
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self._filter_references)
        self.search_input.setPlaceholderText("Tapez pour filtrer les références...")
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Liste des références
        self.references_list = QListWidget()
        self.references_list.itemDoubleClicked.connect(self._on_reference_selected)
        self._populate_list()
        layout.addWidget(self.references_list)
        
        # Boutons
        button_layout = QHBoxLayout()
        
        select_button = QPushButton("Sélectionner")
        select_button.setStyleSheet(UIConfig.STYLE_SUCCESS_BUTTON)
        select_button.clicked.connect(self._on_select_clicked)
        
        cancel_button = QPushButton("Annuler")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(select_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def _populate_list(self):
        """Peupler la liste avec les références"""
        self.references_list.clear()
        for ref in self.filtered_references:
            self.references_list.addItem(ref)
    
    def _filter_references(self, search_text: str):
        """Filtrer les références selon le texte de recherche"""
        search_text = search_text.lower()
        self.filtered_references = [
            ref for ref in self.all_references
            if search_text in ref.lower()
        ]
        self._populate_list()
    
    def _on_reference_selected(self, item):
        """Gérer la double-clic sur une référence"""
        self.selected_reference = item.text()
        self.accept()
    
    def _on_select_clicked(self):
        """Gérer le clic sur le bouton Sélectionner"""
        current_item = self.references_list.currentItem()
        if current_item:
            self.selected_reference = current_item.text()
            self.accept()
        else:
            MessageHelper.show_warning(self, Messages.NO_DATA_SELECTED)
    
    def get_selected_reference(self) -> Optional[str]:
        """Obtenir la référence sélectionnée"""
        return self.selected_reference


# Factory pour l'accès unifié aux dialogues
class DialogManager:
    """
    Manager unifié pour tous les dialogues de l'application
    Remplace les deux DialogService en conflit
    """
    
    def __init__(self, main_window=None):
        self.main_window = main_window
        self.simple = SimpleDialogManager()
        self.complex = ComplexDialogManager(main_window) if main_window else None
    
    # Méthodes de délégation pour les dialogues simples
    def get_text_input(self, parent, title: str, label: str, default_value: str = "") -> Optional[str]:
        return self.simple.get_text_input(parent, title, label, default_value)
    
    def get_multiline_input(self, parent, title: str, label: str, default_value: str = "") -> Optional[str]:
        return self.simple.get_multiline_input(parent, title, label, default_value)
    
    def get_categories(self, parent, current_categories: List[str]) -> Optional[List[str]]:
        return self.simple.get_categories(parent, current_categories)
    
    def get_notes(self, parent, current_notes: str = "") -> Optional[str]:
        return self.simple.get_notes(parent, current_notes)
    
    def get_selection_from_list(self, parent, title: str, label: str, items: List[str]) -> Optional[str]:
        return self.simple.get_selection_from_list(parent, title, label, items)
    
    # Méthodes de délégation pour les dialogues complexes
    def get_import_options_unified(self, **kwargs) -> Dict[str, Any]:
        if not self.complex:
            raise RuntimeError("ComplexDialogManager non initialisé - main_window requis")
        return self.complex.get_import_options_unified(**kwargs)
    
    def show_autocompletion_popup(self, parent_widget, suggestions: List[str]) -> Optional[str]:
        if not self.complex:
            raise RuntimeError("ComplexDialogManager non initialisé - main_window requis")
        return self.complex.show_autocompletion_popup(parent_widget, suggestions)
    
    def get_reference_selection(self, available_references: List[str], title: str = "Sélection de référence") -> Optional[str]:
        if not self.complex:
            raise RuntimeError("ComplexDialogManager non initialisé - main_window requis")
        return self.complex.get_reference_selection(available_references, title)