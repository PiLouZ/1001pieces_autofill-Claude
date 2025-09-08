"""
Service de gestion des dialogues - Phase 2.6
Extrait de main_refactored.py pour centraliser la logique des dialogues complexes

Responsabilités:
- Dialogues d'import unifiés et options avancées
- Popups d'autocomplétion et sélection
- Dialogues de sélection de références
- Interface standardisée pour tous les dialogues métier
"""

from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QLineEdit, QPushButton, QComboBox, QCheckBox, 
                           QTextEdit, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class DialogService:
    """
    Service spécialisé pour la gestion des dialogues complexes
    
    Responsabilités:
    - Création et configuration des dialogues d'import
    - Gestion des popups d'autocomplétion avancée  
    - Dialogues de sélection de références
    - Standardisation de l'interface utilisateur
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def get_import_options_unified(self, detected_columns=None, default_ref_piece=None, 
                                 import_method="CSV", sample_data=None):
        """Dialogue unifié pour choisir les options d'import"""
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Options d'import {import_method}")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)  # Fenêtre plus large pour l'aperçu
        
        layout = QVBoxLayout()
        
        # Information sur les colonnes détectées
        if detected_columns:
            if import_method == "CSV":
                info_label = QLabel(f"📊 Fichier CSV détecté : {detected_columns} colonnes")
            elif import_method == "PDF":
                info_label = QLabel(f"📄 Données PDF détectées : {detected_columns} colonnes")
            else:  # COLLAGE
                info_label = QLabel(f"📋 Données détectées: {detected_columns} colonnes")
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
            # Convertir sample_data en chaîne formatée si c'est une liste
            if isinstance(sample_data, list):
                # sample_data est une List[List[str]], formatter pour affichage
                formatted_preview = ""
                for i, row in enumerate(sample_data[:5]):  # Max 5 lignes d'aperçu
                    if isinstance(row, list):
                        formatted_preview += " | ".join(str(cell) for cell in row) + "\n"
                    else:
                        formatted_preview += str(row) + "\n"
                preview_text.setPlainText(formatted_preview.strip())
            else:
                # sample_data est déjà une chaîne
                preview_text.setPlainText(str(sample_data))
            preview_text.setMaximumHeight(150)
            preview_text.setReadOnly(True)
            preview_text.setStyleSheet("""
                QTextEdit {
                    background-color: #f8f9fa;
                    border: 1px solid #e9ecef;
                    font-family: 'Monaco', 'Courier New', monospace;
                    font-size: 11px;
                }
            """)
            layout.addWidget(preview_text)
        
        # Boutons
        buttons_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        buttons_layout.addWidget(cancel_btn)
        
        buttons_layout.addStretch()
        
        import_btn = QPushButton(f"Importer {import_method}")
        import_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        import_btn.clicked.connect(dialog.accept)
        import_btn.setDefault(True)
        buttons_layout.addWidget(import_btn)
        
        layout.addLayout(buttons_layout)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            return {
                'reference': ref_input.text().strip(),
                'mode': mode_combo.currentIndex(),
                'auto_complete': auto_complete_cb.isChecked(),
                'validate': validate_cb.isChecked(),
                'clean_duplicates': clean_cb.isChecked()
            }
        
        return None
    
    def show_completion_popup(self, editor_text=None):
        """Afficher popup avec auto-complétion avancée via Cmd+D"""
        # Accès via la table EditableTableWidget
        table = self.main_window.table
        current_item = table.currentItem()
        if not current_item or not table.db_manager:
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
            return  # Pas de suggestions pour les autres colonnes
        
        if not suggestions:
            return
            
        # Créer le dialogue de popup
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Auto-complétion - {column_name}")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout()
        
        # Champ de recherche
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Rechercher:"))
        search_input = QLineEdit(editor_text or current_item.text())
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)
        
        # Liste des suggestions
        suggestions_list = QListWidget()
        
        def update_suggestions():
            """Mettre à jour la liste filtrée"""
            filter_text = search_input.text().lower()
            suggestions_list.clear()
            
            for suggestion in suggestions:
                if filter_text in suggestion.lower():
                    item = QListWidgetItem(suggestion)
                    suggestions_list.addItem(item)
        
        # Initialiser la liste
        update_suggestions()
        
        # Connecter le filtre en temps réel
        search_input.textChanged.connect(update_suggestions)
        layout.addWidget(suggestions_list)
        
        # Informations
        info_label = QLabel(f"💡 {len(suggestions)} {column_name.lower()}s dans la base")
        info_label.setStyleSheet("color: #6c757d; font-style: italic;")
        layout.addWidget(info_label)
        
        # Boutons
        buttons_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        buttons_layout.addWidget(cancel_btn)
        
        buttons_layout.addStretch()
        
        select_btn = QPushButton("Sélectionner")
        select_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e7e34;
            }
        """)
        
        def on_select():
            current_selection = suggestions_list.currentItem()
            if current_selection:
                current_item.setText(current_selection.text())
                # Déclencher la sauvegarde via la table EditableTableWidget
                if hasattr(table, '_on_item_changed'):
                    table._on_item_changed(current_item)
                dialog.accept()
        
        select_btn.clicked.connect(on_select)
        suggestions_list.itemDoubleClicked.connect(on_select)
        select_btn.setDefault(True)
        buttons_layout.addWidget(select_btn)
        
        layout.addLayout(buttons_layout)
        
        dialog.setLayout(layout)
        
        # Focus sur le champ de recherche
        search_input.setFocus()
        search_input.selectAll()
        
        dialog.exec_()
    
    def show_reference_selection_dialog(self, title: str, message: str, default_reference: str) -> Optional[str]:
        """
        Afficher une fenêtre de sélection de référence pour les exports multi-références
        """
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # Message d'explication avec adaptation automatique
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {
                padding: 15px;
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
                color: #495057;
                line-height: 1.4;
            }
        """)
        layout.addWidget(label)
        
        # Calculer la taille optimale selon le contenu du message
        text_metrics = label.fontMetrics()
        text_lines = message.count('\n') + 1
        # Estimation largeur nécessaire (minimum 500px, maximum 800px)
        text_width = min(max(text_metrics.horizontalAdvance(message) // text_lines + 100, 500), 800)
        # Hauteur adaptée au nombre de lignes + padding + contrôles
        dialog_height = min(max(250 + (text_lines - 1) * 25, 250), 400)
        dialog.resize(text_width, dialog_height)
        
        # Champ de saisie pour la référence
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Référence:"))
        
        reference_input = QLineEdit(default_reference)
        reference_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #007bff;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        reference_input.setPlaceholderText("Entrez la référence à exporter...")
        input_layout.addWidget(reference_input)
        
        layout.addLayout(input_layout)
        
        # Note d'aide
        help_label = QLabel("💡 Cette référence sera utilisée pour filtrer les données à exporter")
        help_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-style: italic;
                padding: 5px;
            }
        """)
        layout.addWidget(help_label)
        
        # Boutons
        buttons_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border: 1px solid #6c757d;
                border-radius: 4px;
                background-color: white;
            }
            QPushButton:hover {
                background-color: #f8f9fa;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        buttons_layout.addWidget(cancel_btn)
        
        buttons_layout.addStretch()
        
        export_btn = QPushButton("Exporter")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e7e34;
            }
        """)
        export_btn.clicked.connect(dialog.accept)
        export_btn.setDefault(True)
        buttons_layout.addWidget(export_btn)
        
        layout.addLayout(buttons_layout)
        
        dialog.setLayout(layout)
        
        # Focus sur le champ de saisie et sélectionner le texte
        reference_input.setFocus()
        reference_input.selectAll()
        
        # Validation en temps réel
        def validate_input():
            text = reference_input.text().strip()
            export_btn.setEnabled(bool(text))
        
        reference_input.textChanged.connect(validate_input)
        validate_input()  # Validation initiale
        
        if dialog.exec_() == QDialog.Accepted:
            return reference_input.text().strip()
        
        return None
    
    def _get_all_types(self):
        """Récupérer tous les types distincts de la base de données"""
        try:
            # Utiliser le db_manager de la table EditableTableWidget
            table = self.main_window.table
            if hasattr(table, 'db_manager') and table.db_manager:
                result = table.db_manager.execute_query("""
                    SELECT DISTINCT type FROM appareils 
                    WHERE type != '' 
                    ORDER BY type
                """)
                return [row[0] for row in result]
            else:
                return self.main_window.db_manager.get_all_types()
        except:
            return []
    
    def _get_all_manufacturers(self):
        """Récupérer tous les fabricants distincts de la base de données"""
        try:
            # Utiliser le db_manager de la table EditableTableWidget
            table = self.main_window.table
            if hasattr(table, 'db_manager') and table.db_manager:
                result = table.db_manager.execute_query("""
                    SELECT DISTINCT manufacturer FROM appareils 
                    WHERE manufacturer != '' 
                    ORDER BY manufacturer
                """)
                return [row[0] for row in result]
            else:
                return self.main_window.db_manager.get_all_manufacturers()
        except:
            return []