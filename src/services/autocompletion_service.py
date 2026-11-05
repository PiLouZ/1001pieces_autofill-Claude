"""
Service d'autocomplétion - Phase 2.4
Gère les fenêtres d'autocomplétion et la récupération des valeurs
"""

from typing import Callable, List, Optional, Union
from ..utils.qt_imports import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QWidget,
    Qt,
    QTimer
)
from ..data.database_manager import DatabaseManager
from ..core.config import Config
from .base_service import BaseService
from ..utils.ouverture_modale import ouvrir_modal
from ..utils.error_handler import handle_autocompletion_errors
from ..utils.text_utils import strip_accents

class AutoCompletionService(BaseService):
    """Service dédié à l'autocomplétion des cellules"""
    
    def __init__(self, db_manager: DatabaseManager, parent_widget: QWidget = None):
        super().__init__(parent_window=parent_widget)
        self.db_manager = db_manager
        self.parent_widget = parent_widget
    
    def show_column_values_dialog(self, table_widget, current_item, current_col, prefill: str = "",
                                  suggestions: Optional[List[dict]] = None,
                                  sur_resultat: Optional[Callable[[Union[str, dict]], None]] = None) -> None:
        """
        Afficher la fenêtre d'auto-complétion selon la colonne (Cmd+D)

        Args:
            table_widget: Widget du tableau (QTableWidget ou CustomTableView)
            current_item: Item actuel sélectionné (QTableWidgetItem ou compat)
            current_col: Colonne actuelle
            suggestions: candidats Type/Marque par similarité (optionnel). S'ils sont
                fournis, une section « Suggestions » est ajoutée en tête de liste.

            sur_resultat: appelé à la validation (dialogue modal non bloquant,
                jamais exec_) avec :
                - str  : valeur saisie/choisie (à écrire dans la colonne courante)
                - dict : candidat de suggestion choisi (à appliquer en paire Type+Marque)
                Rien n'est appelé si l'utilisateur annule ou si la colonne n'a pas de champ DB.
        """
        db_field = self._get_db_field_name(current_col)
        if not db_field:
            return None

        current_value = prefill if prefill else self._get_current_cell_edit_value(table_widget, current_item, current_col)
        col_label = Config.UI_HEADERS[current_col] if current_col < len(Config.UI_HEADERS) else "Colonne"
        title = f"Valeurs — {col_label}"
        label = f"Sélectionner ou saisir une valeur pour « {col_label} » :"
        # Pré-sélectionner le texte existant (Cmd+D normal), pas lors d'un préfixe de frappe
        select_all = not bool(prefill)
        return self._show_autocompletion_dialog(title, label, db_field, current_value,
                                                select_all=select_all, suggestions=suggestions,
                                                sur_resultat=sur_resultat)

    def show_field_values_dialog(self, db_field: str, current_value: str = "",
                                 suggestions: Optional[List[dict]] = None,
                                 sur_resultat: Optional[Callable[[Union[str, dict]], None]] = None) -> None:
        """Variante de `show_column_values_dialog` SANS dépendance à un tableau : ouvre
        exactement la même fenêtre Cmd+D (valeurs existantes + section Suggestions) pour
        un champ donné. Utilisée par la fenêtre de validation des suggestions pour
        conserver une interaction identique au tableau principal.

        sur_resultat : appelé à la validation avec str (valeur choisie/saisie) ou dict
        (candidat → paire Type+Marque) ; rien à l'annulation.
        """
        labels = {'type': 'Type', 'manufacturer': 'Fabricant'}
        col_label = labels.get(db_field, db_field)
        title = f"Valeurs — {col_label}"
        label = f"Sélectionner ou saisir une valeur pour « {col_label} » :"
        return self._show_autocompletion_dialog(
            title, label, db_field, current_value,
            select_all=bool(current_value), suggestions=suggestions,
            sur_resultat=sur_resultat
        )

    def apply_suggestion_pair(self, candidate: dict, model, db_id: int) -> bool:
        """Applique un candidat de suggestion (Type + Marque) via le pipeline existant.

        Écrit par model.setData() → signal cell_edited → EventDrivenSaveService.
        AUCUN accès direct à la base. Ne touche pas la bannière (responsabilité de
        l'appelant). N'écrit que les champs non vides du candidat.

        Returns:
            bool: True si toutes les écritures tentées ont réussi.
        """
        row = model.find_row_by_db_id(db_id)
        if row is None:
            return False
        # set_field_value (et non setData/index) : écrit même si la ligne est hors page
        # virtuelle (row >= _display_count), où model.index() renverrait un index que la
        # vue refuse. Voir AppareillsTableModel.set_field_value.
        ok = True
        if candidate.get('type'):
            ok = model.set_field_value(row, 0, candidate['type']) and ok
        if candidate.get('manufacturer'):
            ok = model.set_field_value(row, 1, candidate['manufacturer']) and ok
        return ok

    @handle_autocompletion_errors(return_value="")
    def _get_current_cell_edit_value(self, table_widget, current_item, current_col):
        """Récupérer la valeur actuelle d'une cellule, même si elle est en cours d'édition"""
        # Méthode 1: Vérifier si la cellule a un éditeur persistant
        current_index = table_widget.currentIndex()
        if current_index.isValid():
            editor = table_widget.indexWidget(current_index)
            if editor and hasattr(editor, 'text'):
                return editor.text()

        # Méthode 2: Récupérer l'éditeur du delegate si en cours d'édition
        delegate = table_widget.itemDelegate(current_index)
        if hasattr(delegate, 'editor') and delegate.editor and hasattr(delegate.editor, 'text'):
            return delegate.editor.text()

        # Méthode 3: Essayer de récupérer depuis l'état d'édition du tableau
        edit_triggers = table_widget.editTriggers()
        if edit_triggers != table_widget.NoEditTriggers:
            state = table_widget.state()
            if state == table_widget.EditingState:
                # La cellule est en cours d'édition, essayer de récupérer la valeur
                # depuis le focus widget actuel
                focus_widget = table_widget.focusWidget()
                if focus_widget and hasattr(focus_widget, 'text'):
                    return focus_widget.text()

        # Méthode 4: Valeur par défaut depuis l'item
        return current_item.text() if current_item else ""
    
    def _show_autocompletion_dialog(self, title: str, label: str, db_field: str, current_value: str = "",
                                    select_all: bool = True,
                                    suggestions: Optional[List[dict]] = None,
                                    sur_resultat=None) -> None:
        """Afficher une fenêtre d'auto-complétion dédiée avec navigation clavier"""
        dialog = QDialog(self.parent_widget)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(400, 300)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
        # Label d'instruction
        instruction_label = QLabel(label)
        layout.addWidget(instruction_label)
        
        # Champ de saisie avec valeur actuelle
        input_field = QLineEdit(current_value)
        input_field.setPlaceholderText("Tapez pour filtrer la liste...")
        layout.addWidget(input_field)
        
        # Liste des valeurs existantes
        values_list = QListWidget()
        layout.addWidget(values_list)
        
        # Récupérer les valeurs de la base de données et configurer l'interface
        return self._safe_configure_dialog_interface(dialog, layout, input_field, values_list, db_field, current_value, select_all=select_all, suggestions=suggestions, sur_resultat=sur_resultat)

    def _safe_configure_dialog_interface(self, dialog, layout, input_field, values_list, db_field, current_value, select_all: bool = True, suggestions: Optional[List[dict]] = None, sur_resultat=None):
        """Configurer l'interface du dialogue de manière sécurisée"""
        from .reference_similarity_service import decrire_candidat
        # Récupérer les valeurs de la base de données
        all_values = self.db_manager.get_column_values(db_field)
        # Résultat : candidat de suggestion choisi (sinon None → on renvoie le texte saisi).
        chosen = {'candidate': None}

        def update_list():
            """Mettre à jour la liste selon le filtre"""
            filter_text = input_field.text().lower()
            # Comparaison insensible aux accents : « ju » doit retrouver « Jünker »
            # comme « Juno » (et inversement). La valeur insérée garde ses accents.
            filter_norm = strip_accents(filter_text)
            values_list.clear()

            # Section « Suggestions » en tête, uniquement sans filtre actif.
            if suggestions and not filter_text:
                header = QListWidgetItem("— Suggestions —")
                header.setFlags(Qt.NoItemFlags)
                values_list.addItem(header)
                for cand in suggestions:
                    s_item = QListWidgetItem(decrire_candidat(cand))
                    s_item.setData(Qt.UserRole, cand)   # dict complet → application en paire
                    values_list.addItem(s_item)
                separator = QListWidgetItem("— Valeurs existantes —")
                separator.setFlags(Qt.NoItemFlags)
                values_list.addItem(separator)

            # Ajouter les items filtrés
            filtered_values = []
            for value in all_values:
                if not filter_norm or filter_norm in strip_accents(value.lower()):
                    filtered_values.append(value)
                    item = QListWidgetItem(value)
                    values_list.addItem(item)

            # Sélectionner automatiquement le premier item si pas de sélection
            if filtered_values and values_list.count() > 0:
                # Chercher une correspondance exacte d'abord
                exact_match_found = False
                for i in range(values_list.count()):
                    item = values_list.item(i)
                    if item.text() == current_value:
                        values_list.setCurrentItem(item)
                        exact_match_found = True
                        break

                # Si pas de correspondance exacte, sélectionner le premier
                if not exact_match_found:
                    values_list.setCurrentRow(0)

        # Connecter le filtrage
        input_field.textChanged.connect(update_list)

        # Double-clic pour valider
        def on_item_double_clicked(item):
            cand = item.data(Qt.UserRole)
            if isinstance(cand, dict):       # item de suggestion → application en paire
                chosen['candidate'] = cand
                dialog.accept()
                return
            input_field.setText(item.text())
            dialog.accept()

        values_list.itemDoubleClicked.connect(on_item_double_clicked)

        # Clic simple pour remplir le champ (sauf items de suggestion : double-clic requis)
        def on_item_clicked(item):
            if isinstance(item.data(Qt.UserRole), dict):
                return
            input_field.setText(item.text())

        values_list.itemClicked.connect(on_item_clicked)

        # Gestion des événements clavier
        def handle_key_press(event):
            """Gérer les événements clavier pour navigation et validation"""
            key = event.key()

            if key == Qt.Key_Down:
                # Flèche bas : passer à l'item suivant sans modifier le champ de recherche
                current_row = values_list.currentRow()
                if current_row < values_list.count() - 1:
                    values_list.setCurrentRow(current_row + 1)
                elif values_list.count() > 0:
                    values_list.setCurrentRow(0)
            elif key == Qt.Key_Up:
                # Flèche haut : passer à l'item précédent sans modifier le champ de recherche
                current_row = values_list.currentRow()
                if current_row > 0:
                    values_list.setCurrentRow(current_row - 1)
                elif values_list.count() > 0:
                    values_list.setCurrentRow(values_list.count() - 1)
            elif key == Qt.Key_Return or key == Qt.Key_Enter:
                # Entrée : utiliser l'item surligné dans la liste si disponible
                selected_list_item = values_list.currentItem()
                if selected_list_item:
                    cand = selected_list_item.data(Qt.UserRole)
                    if isinstance(cand, dict):
                        chosen['candidate'] = cand
                        dialog.accept()
                        return
                    input_field.setText(selected_list_item.text())
                dialog.accept()
            elif key == Qt.Key_Escape:
                # Échap : annuler
                dialog.reject()
            else:
                # Pour les autres touches, comportement normal du QLineEdit
                QLineEdit.keyPressEvent(input_field, event)

        # Installer le gestionnaire d'événements clavier sur le champ de saisie
        input_field.keyPressEvent = handle_key_press

        # Gestion des événements clavier sur la liste aussi
        def handle_list_key_press(event):
            """Gérer les événements clavier sur la liste"""
            key = event.key()

            if key == Qt.Key_Return or key == Qt.Key_Enter:
                # Entrée : valider la sélection
                current_item = values_list.currentItem()
                if current_item:
                    cand = current_item.data(Qt.UserRole)
                    if isinstance(cand, dict):
                        chosen['candidate'] = cand
                        dialog.accept()
                        return
                    input_field.setText(current_item.text())
                    dialog.accept()
            elif key == Qt.Key_Escape:
                # Échap : annuler
                dialog.reject()
            else:
                # Comportement normal de QListWidget
                QListWidget.keyPressEvent(values_list, event)

        values_list.keyPressEvent = handle_list_key_press

        # Initialiser la liste
        update_list()
        
        # Boutons
        buttons_layout = QHBoxLayout()
        
        ok_button = QPushButton("Valider")
        ok_button.clicked.connect(dialog.accept)
        ok_button.setDefault(True)
        
        cancel_button = QPushButton("Annuler")
        cancel_button.clicked.connect(dialog.reject)
        
        clear_button = QPushButton("Effacer")
        clear_button.clicked.connect(lambda: input_field.clear())
        
        buttons_layout.addWidget(clear_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(cancel_button)
        buttons_layout.addWidget(ok_button)
        
        layout.addLayout(buttons_layout)
        
        # Focus sur le champ de saisie
        input_field.setFocus()
        # Différé : macOS applique son propre selectAll après setFocus().
        # On surcharge ce comportement dans la prochaine itération de l'event loop.
        if select_all:
            QTimer.singleShot(0, input_field.selectAll)
        else:
            QTimer.singleShot(0, lambda: (input_field.deselect(),
                                          input_field.setCursorPosition(len(input_field.text()))))
        
        # Afficher le dialogue : modal sans boucle imbriquée (jamais exec_)
        def _sur_accepte():
            if sur_resultat is None:
                return
            # Un candidat de suggestion choisi prime sur la saisie texte.
            if chosen['candidate'] is not None:
                sur_resultat(chosen['candidate'])
            else:
                sur_resultat(input_field.text().strip())

        ouvrir_modal(dialog, sur_accepte=_sur_accepte)
    
    def _get_db_field_name(self, ui_column: int) -> str:
        """Mapper l'index de colonne UI vers le nom de champ DB"""
        # Mapping avec la nouvelle colonne Nb Pièces
        # UI: Type(0), Fabricant(1), Ref_Modele(2), Commercial_Ref(3), Other_Ref(4), Category(5), Notes(6), Nb_Pieces(7)
        # DB: type, manufacturer, ref_modele, commercial_ref, other_ref, category, notes
        
        column_mapping = {
            0: 'type',           # Type
            1: 'manufacturer',   # Fabricant  
            2: 'ref_modele',     # Réf. Modèle
            3: 'commercial_ref', # Réf. Commerciale
            4: 'other_ref',      # Autre Réf.
            5: 'category',       # Catégorie
            6: 'notes',          # Notes
            # 7 = Nb Pièces (pas de champ DB correspondant)
        }
        
        return column_mapping.get(ui_column, None)