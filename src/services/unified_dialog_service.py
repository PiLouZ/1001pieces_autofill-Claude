"""
Service de dialogues unifié - Refactorisation Phase 2
Consolidation de DialogService (simple) et DialogService (complexe)

RESPONSABILITÉS UNIFIÉES :
- Dialogues simples : Catégories, Notes (méthodes statiques)
- Dialogues complexes : Import, Autocomplétion, Références (méthodes d'instance)
- Factory pattern pour création optimisée
- Interface cohérente pour toute l'application

ARCHITECTURE :
- DialogType : Énumération des types de dialogue
- UnifiedDialogService : Service principal avec factory et instances
- Dialogues simples : Méthodes statiques sans dépendances
- Dialogues complexes : Méthodes d'instance avec accès à main_window
"""

from typing import Optional, Dict, Any, List, Union
from enum import Enum
from ..ui.qt_imports import (
    QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit, 
    QListWidget, QListWidgetItem, QMessageBox, QDialogButtonBox
)
from ..ui.qt_imports import Qt
from ..ui.qt_imports import QFont

from ..core.logger import app_logger
from functools import wraps

def _handle_dialog_errors(default_return=None, context="Dialogue"):
    """
    Décorateur pour gérer les erreurs des dialogues Qt
    Pattern: Log l'erreur et retourne une valeur par défaut
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                app_logger.error(f"Erreur {context}: {e}")
                return default_return
        return wrapper
    return decorator

class DialogType(Enum):
    """Types de dialogues disponibles"""
    CATEGORIES = "categories"
    NOTES = "notes" 
    IMPORT_OPTIONS = "import_options"
    REFERENCE_SELECTION = "reference_selection"
    AUTOCOMPLETION = "autocompletion"
    CONFIRMATION = "confirmation"

class SimpleDialogs:
    """
    Dialogues simples - Méthodes statiques sans dépendances UI complexes
    
    Ces dialogues peuvent être utilisés partout sans instanciation
    """
    
    @staticmethod
    @_handle_dialog_errors(default_return=None, context="dialogue catégories")
    def get_categories(parent, current_categories: List[str]) -> Optional[List[str]]:
        """
        Dialogue de gestion des catégories

        Args:
            parent: Widget parent
            current_categories: Liste des catégories actuelles

        Returns:
            Liste des catégories ou None si annulé
        """
        text, ok = QInputDialog.getMultiLineText(
            parent,
            "Gestion des Catégories",
            "Entrez les catégories (une par ligne):",
            '\n'.join(current_categories) if current_categories else ""
        )

        if ok:
            categories = [line.strip() for line in text.split('\n') if line.strip()]
            app_logger.debug(f"Catégories sélectionnées: {categories}")
            return categories
        return None
    
    @staticmethod
    @_handle_dialog_errors(default_return=None, context="dialogue notes")
    def get_notes(parent, current_notes: str = "") -> Optional[str]:
        """
        Dialogue d'édition des notes

        Args:
            parent: Widget parent
            current_notes: Texte des notes actuelles

        Returns:
            Texte des notes ou None si annulé
        """
        text, ok = QInputDialog.getMultiLineText(
            parent,
            "Notes et Commentaires",
            "Entrez vos notes:",
            current_notes
        )

        if ok:
            app_logger.debug("Notes modifiées")
            return text
        return None
    
    @staticmethod
    @_handle_dialog_errors(default_return=False, context="dialogue confirmation")
    def confirm_action(parent, title: str, message: str) -> bool:
        """
        Dialogue de confirmation simple

        Args:
            parent: Widget parent
            title: Titre du dialogue
            message: Message à afficher

        Returns:
            True si confirmé, False sinon
        """
        reply = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes

class ComplexDialogs:
    """
    Dialogues complexes - Méthodes d'instance avec accès à l'application
    
    Ces dialogues nécessitent une instance et accès à main_window
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
    
    @_handle_dialog_errors(default_return=None, context="dialogue options import")
    def get_import_options_unified(self, detected_columns=None, default_ref_piece=None,
                                 import_method="CSV", sample_data=None) -> Optional[Dict[str, Any]]:
        """
        Dialogue unifié pour les options d'import

        Args:
            detected_columns: Nombre de colonnes détectées
            default_ref_piece: Référence par défaut
            import_method: Méthode d'import (CSV, PDF, PASTE)
            sample_data: Échantillon de données pour aperçu

        Returns:
            Dictionnaire avec les options sélectionnées ou None si annulé
        """
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Options d'import {import_method}")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)

        layout = QVBoxLayout()

        # Information sur les colonnes détectées
        if detected_columns:
            info_label = QLabel(f"Données {import_method} détectées : {detected_columns} colonnes")
            info_label.setStyleSheet("color: #28a745; font-weight: bold; margin: 5px;")
            layout.addWidget(info_label)

        # Référence par défaut
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence par défaut :"))
        ref_input = QLineEdit(default_ref_piece or "")
        ref_input.setPlaceholderText("Laisser vide pour auto-détection")
        ref_layout.addWidget(ref_input)
        layout.addLayout(ref_layout)

        # Mode d'import
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode d'import :"))
        mode_combo = QComboBox()
        mode_combo.addItems([
            "Ajouter aux données existantes",
            "Remplacer toutes les données",
            "Mise à jour (selon référence)"
        ])
        mode_layout.addWidget(mode_combo)
        layout.addLayout(mode_layout)

        # Options avancées
        options_label = QLabel("Options:")
        options_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(options_label)

        auto_complete_cb = QCheckBox("Auto-complétion après import")
        auto_complete_cb.setChecked(True)
        layout.addWidget(auto_complete_cb)

        validate_cb = QCheckBox("Valider les données après import")
        validate_cb.setChecked(True)
        layout.addWidget(validate_cb)

        clean_cb = QCheckBox("Nettoyer les doublons automatiquement")
        clean_cb.setChecked(False)
        layout.addWidget(clean_cb)

        # Aperçu des données si disponibles
        if sample_data:
            preview_label = QLabel("Aperçu des données :")
            preview_label.setStyleSheet("font-weight: bold; margin-top: 15px;")
            layout.addWidget(preview_label)

            preview_text = QTextEdit()
            preview_text.setMaximumHeight(150)
            preview_text.setReadOnly(True)

            # Formater l'aperçu selon le type de données
            if isinstance(sample_data, list):
                if sample_data and len(sample_data) > 0:
                    preview_content = "\n".join([
                        f"Ligne {i+1}: {row}" for i, row in enumerate(sample_data[:5])
                    ])
                    if len(sample_data) > 5:
                        preview_content += f"\n... et {len(sample_data) - 5} autres lignes"
                else:
                    preview_content = "Aucune donnée d'aperçu disponible"
            else:
                preview_content = str(sample_data)[:500]

            preview_text.setText(preview_content)
            layout.addWidget(preview_text)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            # Collecter les options sélectionnées
            options = {
                'default_reference': ref_input.text().strip(),
                'import_mode': mode_combo.currentIndex(),
                'import_mode_text': mode_combo.currentText(),
                'auto_complete': auto_complete_cb.isChecked(),
                'validate_data': validate_cb.isChecked(),
                'clean_duplicates': clean_cb.isChecked()
            }

            app_logger.info(f"Options d'import sélectionnées: {options}")
            return options

        return None
    
    @_handle_dialog_errors(default_return=None, context="dialogue sélection référence")
    def show_reference_selection_dialog(self, title: str, message: str,
                                      default_reference: str = "") -> Optional[str]:
        """
        Dialogue de sélection/modification de référence

        Args:
            title: Titre du dialogue
            message: Message explicatif
            default_reference: Référence par défaut

        Returns:
            Référence sélectionnée ou None si annulé
        """
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        # Message explicatif
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("margin: 10px;")
        layout.addWidget(message_label)

        # Champ de référence
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Référence :"))
        ref_input = QLineEdit(default_reference)
        ref_input.setPlaceholderText("Entrez la référence...")
        ref_input.selectAll()  # Sélectionner tout le texte par défaut
        ref_layout.addWidget(ref_input)
        layout.addLayout(ref_layout)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        ref_input.setFocus()

        if dialog.exec_() == QDialog.Accepted:
            reference = ref_input.text().strip()
            if reference:
                app_logger.debug(f"Référence sélectionnée: {reference}")
                return reference

        return None
    
    @_handle_dialog_errors(default_return=None, context="popup autocomplétion")
    def show_autocompletion_popup(self, suggestions: List[str],
                                current_value: str = "") -> Optional[str]:
        """
        Popup d'autocomplétion avec liste de suggestions

        Args:
            suggestions: Liste des suggestions
            current_value: Valeur actuelle

        Returns:
            Valeur sélectionnée ou None si annulé
        """
        if not suggestions:
            return None

        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Autocomplétion")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(300)

        layout = QVBoxLayout()

        # Champ de saisie
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Valeur :"))
        value_input = QLineEdit(current_value)
        input_layout.addWidget(value_input)
        layout.addLayout(input_layout)

        # Liste des suggestions
        suggestions_label = QLabel(f"Suggestions ({len(suggestions)}) :")
        suggestions_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(suggestions_label)

        suggestions_list = QListWidget()
        for suggestion in suggestions:
            item = QListWidgetItem(suggestion)
            suggestions_list.addItem(item)

        # Sélectionner la suggestion qui correspond à la valeur actuelle
        if current_value:
            for i in range(suggestions_list.count()):
                if suggestions_list.item(i).text() == current_value:
                    suggestions_list.setCurrentRow(i)
                    break

        suggestions_list.itemDoubleClicked.connect(dialog.accept)
        layout.addWidget(suggestions_list)

        # Connecter la sélection dans la liste au champ de saisie
        def on_suggestion_selected():
            current_item = suggestions_list.currentItem()
            if current_item:
                value_input.setText(current_item.text())

        suggestions_list.itemSelectionChanged.connect(on_suggestion_selected)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        value_input.setFocus()

        if dialog.exec_() == QDialog.Accepted:
            value = value_input.text().strip()
            app_logger.debug(f"Valeur d'autocomplétion sélectionnée: {value}")
            return value

        return None

class UnifiedDialogService:
    """
    Service de dialogues unifié - Interface principale
    
    Combine dialogues simples (statiques) et complexes (instance)
    Factory pattern pour optimiser l'utilisation
    """
    
    def __init__(self, main_window=None):
        """
        Initialiser le service unifié
        
        Args:
            main_window: Instance optionnelle pour dialogues complexes
        """
        self.main_window = main_window
        self._complex_dialogs = None
    
    @property
    def complex(self) -> ComplexDialogs:
        """Accès lazy aux dialogues complexes"""
        if self._complex_dialogs is None:
            if self.main_window is None:
                raise ValueError("main_window requis pour les dialogues complexes")
            self._complex_dialogs = ComplexDialogs(self.main_window)
        return self._complex_dialogs
    
    # Délégation aux dialogues simples (méthodes statiques)
    @staticmethod
    def get_categories(parent, current_categories: List[str]) -> Optional[List[str]]:
        """Dialogue de gestion des catégories"""
        return SimpleDialogs.get_categories(parent, current_categories)
    
    @staticmethod  
    def get_notes(parent, current_notes: str = "") -> Optional[str]:
        """Dialogue d'édition des notes"""
        return SimpleDialogs.get_notes(parent, current_notes)
    
    @staticmethod
    def confirm_action(parent, title: str, message: str) -> bool:
        """Dialogue de confirmation"""
        return SimpleDialogs.confirm_action(parent, title, message)
    
    # Délégation aux dialogues complexes (méthodes d'instance)
    def get_import_options_unified(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Dialogue d'options d'import"""
        return self.complex.get_import_options_unified(**kwargs)
    
    def show_reference_selection_dialog(self, title: str, message: str, 
                                      default_reference: str = "") -> Optional[str]:
        """Dialogue de sélection de référence"""
        return self.complex.show_reference_selection_dialog(title, message, default_reference)
    
    def show_autocompletion_popup(self, suggestions: List[str], 
                                current_value: str = "") -> Optional[str]:
        """Popup d'autocomplétion"""
        return self.complex.show_autocompletion_popup(suggestions, current_value)
    
    # Factory methods pour compatibilité avec l'ancien code

# Backward compatibility aliases pour migration facile
DialogService = UnifiedDialogService