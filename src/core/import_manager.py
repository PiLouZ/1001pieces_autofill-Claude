"""
Gestionnaire d'importation unifié pour l'application de gestion d'appareils
Factorisation du code d'importation avec support des libellés hiérarchiques
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Callable
from enum import Enum
import os
import warnings
from datetime import datetime

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QCheckBox, 
                             QTextEdit, QGroupBox, QProgressDialog, QApplication,
                             QScrollArea, QWidget, QGridLayout)
from PyQt5.QtCore import Qt

from .logger import app_logger



class ImportType(Enum):
    """Types d'import supportés"""
    SINGLE_FILE = "single_file"
    MULTI_FILE = "multi_file"
    

class FileType(Enum):
    """Types de fichiers supportés"""
    CSV = "csv"
    PDF = "pdf"


@dataclass
class ImportFile:
    """Représente un fichier à importer"""
    path: str
    type: FileType
    suggested_reference: str
    suggested_label: str = None
    data: List[List[str]] = None
    
    @property
    def filename(self) -> str:
        return os.path.basename(self.path)
    
    @property
    def name_without_ext(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]


@dataclass
class LabelConfiguration:
    """Configuration pour les libellés"""
    use_common_label: bool = False
    common_label: str = ""
    individual_labels: Dict[str, str] = None  # {file_path: label}
    
    def __post_init__(self):
        if self.individual_labels is None:
            self.individual_labels = {}


@dataclass
class ImportConfiguration:
    """Configuration complète d'un import"""
    files: List[ImportFile]
    import_type: ImportType
    common_reference: Optional[str] = None
    use_common_reference: bool = False
    label_config: LabelConfiguration = None
    
    # Nouveau: séparation claire références vs libellés
    individual_references: Dict[str, str] = None  # {file_path: reference} - toujours nom fichier
    individual_labels: Dict[str, str] = None      # {file_path: label} - ce que tape l'utilisateur
    common_label: str = ""                        # Libellé de la référence commune
    
    # Options d'import technique
    csv_import_mode: int = 2  # 1, 2, 3+ colonnes
    third_column_choice: str = "ignore"
    has_headers: bool = False
    
    def __post_init__(self):
        if self.label_config is None:
            self.label_config = LabelConfiguration()
        if self.individual_references is None:
            self.individual_references = {}
        if self.individual_labels is None:
            self.individual_labels = {}


class ImportDialog(QDialog):
    """Interface utilisateur pour configurer les imports"""
    
    def __init__(self, parent=None, import_config: ImportConfiguration = None):
        super().__init__(parent)
        self.import_config = import_config or ImportConfiguration(files=[], import_type=ImportType.SINGLE_FILE)
        self.result_config = None
        
        self.setWindowTitle("Configuration d'importation")
        self.setModal(True)
        self.setMinimumWidth(1000)
        self.setMinimumHeight(1000)
        
        self._setup_ui()
        self._populate_data()
    
    def _setup_ui(self):
        """Créer l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Section fichiers avec layout en grille (max 5 colonnes)
        files_group = QGroupBox("Fichiers à importer")
        files_main_layout = QVBoxLayout()
        
        # Utiliser un layout en grille pour tous les cas avec max 5 colonnes
        files_grid = QGridLayout()
        files_per_row = min(5, max(1, len(self.import_config.files)))
        
        for i, file in enumerate(self.import_config.files):
            row = i // files_per_row
            col = i % files_per_row
            
            file_label = QLabel(f"📄 {file.filename}")
            file_label.setStyleSheet("color: #495057; padding: 2px 0px;")
            file_label.setAlignment(Qt.AlignCenter)
            files_grid.addWidget(file_label, row, col)
        
        files_main_layout.addLayout(files_grid)
        files_group.setLayout(files_main_layout)
        layout.addWidget(files_group)
        
        # Section format reconnu et aperçu des données (repositionnée ici)
        format_group = QGroupBox("Format reconnu et aperçu")
        format_layout = QVBoxLayout()
        
        self.format_info_label = QLabel()
        self.format_info_label.setStyleSheet("font-weight: bold;")
        format_layout.addWidget(self.format_info_label)
        
        self.format_desc_label = QLabel()
        self.format_desc_label.setStyleSheet("color: #6c757d; margin-left: 20px;")
        format_layout.addWidget(self.format_desc_label)
        
        # Aperçu des données avec hauteur augmentée
        self.preview_text = QTextEdit()
        self.preview_text.setMinimumHeight(80)
        self.preview_text.setMaximumHeight(100)
        self.preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; font-family: 'Monaco', 'Menlo', 'Courier New', monospace; font-size: 11px;")
        self.preview_text.setReadOnly(True)
        format_layout.addWidget(self.preview_text)
        
        # Espacement visuel augmenté entre l'aperçu et les options
        format_layout.addSpacing(5)
        
        # Options techniques clairement séparées sous l'aperçu
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(10, 10, 10, 5)  # Marges pour séparer visuellement
        
        # Gestion de la 3ème colonne si applicable
        self.third_col_widget = QWidget()
        self.third_col_widget.setStyleSheet("background-color: #fff; border: 1px solid #e9ecef; border-radius: 4px; padding: 5px;")
        third_col_layout = QHBoxLayout(self.third_col_widget)
        third_col_layout.setContentsMargins(10, 8, 10, 8)
        
        self.third_col_label = QLabel("Destination 3ème colonne:")
        self.third_col_label.setStyleSheet("font-weight: bold;")
        third_col_layout.addWidget(self.third_col_label)
        
        self.third_col_combo = QComboBox()
        self.third_col_combo.addItems(["Ignorer", "Autre référence", "Notes"])
        self.third_col_combo.setCurrentIndex(0)
        third_col_layout.addWidget(self.third_col_combo)
        
        options_layout.addWidget(self.third_col_widget)
        self.third_col_widget.hide()  # Caché par défaut
        
        # Option en-têtes CSV avec style cohérent
        self.headers_checkbox = QCheckBox("Le fichier contient une ligne d'en-têtes (ignorer la première ligne)")
        self.headers_checkbox.setChecked(False)
        self.headers_checkbox.setToolTip("Cochez cette case si la première ligne de votre fichier contient les noms des colonnes")
        self.headers_checkbox.setStyleSheet("font-weight: bold; background-color: #fff; border: 1px solid #e9ecef; border-radius: 4px; padding: 8px 10px; margin-top: 5px;")
        options_layout.addWidget(self.headers_checkbox)
        self.headers_checkbox.hide()  # Caché par défaut, affiché seulement pour CSV
        
        format_layout.addLayout(options_layout)
        
        format_group.setLayout(format_layout)
        layout.addWidget(format_group)
        
        # Section référence commune (pour multi-fichiers)
        if self.import_config.import_type == ImportType.MULTI_FILE:
            ref_group = QGroupBox("Référence commune optionnelle")
            ref_layout = QVBoxLayout()
            
            # Texte d'explication avec hauteur augmentée
            ref_info = QLabel("💡 La référence commune sera associée à TOUS les appareils importés")
            ref_info.setStyleSheet("color: #666; font-style: italic; margin-bottom: 10px; padding: 8px; background-color: #f0f8ff; border-radius: 4px;")
            ref_info.setMinimumHeight(50)
            ref_info.setWordWrap(True)
            ref_layout.addWidget(ref_info)
            
            # Champs référence et libellé sur une seule ligne
            fields_layout = QHBoxLayout()
            
            # Référence commune (1/4 de la largeur)
            ref_label = QLabel("Référence:")
            ref_label.setStyleSheet("font-weight: bold;")
            ref_label.setMinimumWidth(80)
            fields_layout.addWidget(ref_label)
            
            self.common_ref_input = QLineEdit()
            self.common_ref_input.setPlaceholderText("GAUxxxxxx, FARxxxxxxx")
            self.common_ref_input.setMinimumHeight(35)
            fields_layout.addWidget(self.common_ref_input, 1)  # 1 part
            
            # Libellé/Description (3/4 de la largeur)
            desc_label = QLabel("Description:")
            desc_label.setStyleSheet("font-weight: bold; margin-left: 15px;")
            desc_label.setMinimumWidth(80)
            fields_layout.addWidget(desc_label)
            
            self.common_ref_description = QLineEdit()
            self.common_ref_description.setPlaceholderText("Description lisible (ex: Lot pièces lave-vaisselle mars 2024)")
            self.common_ref_description.setMinimumHeight(35)
            fields_layout.addWidget(self.common_ref_description, 3)  # 3 parts
            
            ref_layout.addLayout(fields_layout)
            
            # Layout pour aligner la case à cocher avec le champ Description
            checkbox_layout = QHBoxLayout()
            checkbox_layout.setContentsMargins(0, 5, 0, 0)
            
            # Espace vide pour aligner avec le début du champ Description
            spacer_left = QWidget()
            spacer_left.setFixedWidth(95)  # Largeur du label "Référence:" (80px) + margin (15px)
            checkbox_layout.addWidget(spacer_left)
            
            # Case à cocher alignée avec le champ Description
            self.apply_to_individual_checkbox = QCheckBox("Appliquer aux références individuelles")
            self.apply_to_individual_checkbox.setStyleSheet("font-weight: bold;")
            self.apply_to_individual_checkbox.setToolTip("Applique automatiquement cette description à toutes les références individuelles")
            # Connecter la case à cocher pour dupliquer automatiquement le libellé
            self.apply_to_individual_checkbox.stateChanged.connect(self._on_apply_to_individual_changed)
            # Connecter le champ de description commun pour mise à jour en temps réel
            self.common_ref_description.textChanged.connect(self._on_common_description_changed)
            checkbox_layout.addWidget(self.apply_to_individual_checkbox)
            
            # Espace vide à droite pour équilibrer
            checkbox_layout.addStretch()
            
            ref_layout.addLayout(checkbox_layout)
            
            ref_group.setLayout(ref_layout)
            layout.addWidget(ref_group)
        
        # Section références individuelles par fichier avec ascenseur
        individual_group = QGroupBox("Références individuelles par fichier")
        individual_layout = QVBoxLayout()
        
        # Info et option de génération automatique des références
        info_and_option_layout = QVBoxLayout()
        info_and_option_layout.setContentsMargins(0, 0, 0, 0)
        info_and_option_layout.setSpacing(8)
        
        individual_info = QLabel("💡 Génération automatique des références de pièces basées sur les noms de fichiers")
        individual_info.setStyleSheet("color: #666; font-style: italic; padding: 8px; background-color: #f0f8ff; border-radius: 4px;")
        individual_info.setWordWrap(True)
        info_and_option_layout.addWidget(individual_info)
        
        # Case à cocher pour activer/désactiver les références automatiques
        self.auto_file_references_checkbox = QCheckBox("Associer automatiquement les noms de fichiers comme références de pièces")
        self.auto_file_references_checkbox.setToolTip("Si coché, chaque fichier génère automatiquement une référence de pièce basée sur son nom.\nSi décoché, seuls les données contenues dans les fichiers sont importées.")
        self.auto_file_references_checkbox.setStyleSheet("font-weight: bold; color: #333; margin-left: 10px;")
        
        # Définir la valeur par défaut selon le type de fichiers
        has_pdf = any(f.type == FileType.PDF for f in self.import_config.files)
        has_csv = any(f.type == FileType.CSV for f in self.import_config.files)
        
        if has_pdf and not has_csv:
            # Que des PDF -> coché par défaut
            self.auto_file_references_checkbox.setChecked(True)
        elif has_csv and not has_pdf:
            # Que des CSV -> décoché par défaut  
            self.auto_file_references_checkbox.setChecked(False)
        else:
            # Mélange -> coché par défaut (plus sûr)
            self.auto_file_references_checkbox.setChecked(True)
        
        # Connecter pour mettre à jour l'affichage
        self.auto_file_references_checkbox.stateChanged.connect(self._on_auto_references_changed)
        info_and_option_layout.addWidget(self.auto_file_references_checkbox)
        
        individual_layout.addLayout(info_and_option_layout)
        
        # Zone scrollable pour les références individuelles - ADAPTATIVE
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Ascenseur selon besoin
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Pas d'ascenseur horizontal
        
        # Calculer la hauteur adaptative selon le nombre de fichiers
        num_files = len(self.import_config.files)
        line_height = 45  # Hauteur fixe par ligne (fichier) sans espacement
        base_height = 40   # Hauteur de base réduite pour les marges (20px top + 20px bottom)
        calculated_height = base_height + (num_files * line_height)
        
        # Limiter la hauteur pour éviter une fenêtre trop grande
        min_height = 150
        max_height = 200
        adaptive_height = max(min_height, min(calculated_height, max_height))
        
        scroll_area.setMinimumHeight(adaptive_height)
        if calculated_height > max_height:
            scroll_area.setMaximumHeight(max_height)
        
        scroll_widget = QWidget()
        scroll_widget.setObjectName("scroll_content")
        
        self.individual_refs_widget = QVBoxLayout(scroll_widget)
        self.individual_refs_widget.setContentsMargins(10, 10, 10, 10)  # Marges adaptées
        self.individual_refs_widget.setSpacing(0)  # Pas d'espacement entre les lignes pour optimiser l'espace
        self.individual_refs_widget.setAlignment(Qt.AlignTop)  # Aligner en haut au lieu du centre
        
        # Liste pour garder les références des champs de description individuels
        self.individual_desc_fields = []
        
        scroll_area.setWidget(scroll_widget)
        
        individual_layout.addWidget(scroll_area)
        individual_group.setLayout(individual_layout)
        layout.addWidget(individual_group)
        
        # Section aperçu des données supprimée pour améliorer la lisibilité
        
        # Boutons
        buttons_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Importer")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._validate_and_accept)
        buttons_layout.addWidget(ok_btn)
        
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
    
    def _populate_data(self):
        """Remplir l'interface avec les données"""
        # Les fichiers sont maintenant toujours affichés dans la grille (layout amélioré)
        
        # Analyser les formats et remplir l'aperçu
        self._analyze_formats_and_preview()
        
        # Références individuelles par fichier - FORMAT ORIGINAL : UNE LIGNE PAR PIÈCE
        for i, file in enumerate(self.import_config.files):
            
            # Créer un widget conteneur pour chaque ligne avec hauteur fixe
            file_container = QWidget()
            file_container.setFixedHeight(45)  # Hauteur fixe pour éviter les chevauchements
            file_container.setContentsMargins(0, 0, 0, 0)
            
            # UNE SEULE ligne horizontale par fichier (format original simplifié)
            file_layout = QHBoxLayout(file_container)
            file_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)  # Aligner à gauche et en haut
            file_layout.setContentsMargins(5, 5, 5, 5)  # Marges pour l'espacement
            file_layout.setSpacing(8)  # Espacement réduit entre éléments
            
            # Nom du fichier (style original simplifié)
            file_label = QLabel(f"📄 {file.filename}:")
            file_label.setMinimumWidth(200)
            file_label.setStyleSheet("font-weight: bold;")
            file_layout.addWidget(file_label)
            
            # Référence (basée sur le nom du fichier, affichage conditionnel)
            ref_display = QLabel(f"→ Réf: {file.suggested_reference}")
            ref_display.setStyleSheet("color: #0066cc; background-color: #f0f8ff; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-weight: bold;")
            ref_display.setMinimumWidth(150)
            ref_display.setObjectName(f"ref_display_{file.path}")
            file_layout.addWidget(ref_display)
            
            # Libellé/Description (modifiable)
            desc_label = QLabel("Libellé:")
            desc_label.setMinimumWidth(60)
            desc_label.setStyleSheet("font-weight: bold;")
            file_layout.addWidget(desc_label)
            
            desc_input = QLineEdit()
            desc_input.setPlaceholderText(f"Description pour {file.suggested_reference} (optionnel)")
            desc_input.setText("")  # Vide par défaut
            desc_input.setObjectName(f"desc_{file.path}")
            desc_input.setMinimumHeight(35)
            desc_input.setStyleSheet("padding: 5px; border: 2px solid #ccc; border-radius: 4px;")
            file_layout.addWidget(desc_input)
            
            # Stocker la référence du champ pour la duplication automatique
            self.individual_desc_fields.append(desc_input)
            
            # Ajouter le conteneur avec hauteur fixe au lieu du layout directement
            self.individual_refs_widget.addWidget(file_container)
        
        # Initialiser l'affichage des références selon l'état par défaut de la case à cocher
        self._update_references_display()
        
        # Aperçu des données supprimé pour améliorer la lisibilité
    
    def _on_apply_to_individual_changed(self, state):
        """Gère le changement d'état de la case 'Appliquer aux références individuelles'"""
        if state == Qt.Checked:
            # Dupliquer la description commune vers tous les champs individuels
            common_desc = self.common_ref_description.text()
            for desc_field in self.individual_desc_fields:
                desc_field.setText(common_desc)
        else:
            # Vider tous les champs individuels
            for desc_field in self.individual_desc_fields:
                desc_field.setText("")
    
    def _on_common_description_changed(self, text):
        """Met à jour automatiquement les champs individuels si la case est cochée"""
        if self.apply_to_individual_checkbox.isChecked():
            for desc_field in self.individual_desc_fields:
                desc_field.setText(text)
    
    def _on_auto_references_changed(self, state):
        """Gère le changement d'état de la case 'Références automatiques'"""
        # Mettre à jour l'affichage des références selon l'état de la case
        self._update_references_display()
    
    def _update_references_display(self):
        """Met à jour l'affichage des références selon l'état de la case à cocher"""
        auto_references_enabled = self.auto_file_references_checkbox.isChecked()
        
        for file in self.import_config.files:
            # Trouver le label de référence pour ce fichier
            ref_display = self.findChild(QLabel, f"ref_display_{file.path}")
            if ref_display:
                if auto_references_enabled:
                    # Affichage normal avec référence
                    ref_display.setText(f"→ Réf: {file.suggested_reference}")
                    ref_display.setStyleSheet("color: #0066cc; background-color: #f0f8ff; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-weight: bold;")
                else:
                    # Affichage grisé indiquant que la référence ne sera pas créée
                    ref_display.setText("→ Réf: (aucune référence de pièce)")
                    ref_display.setStyleSheet("color: #999; background-color: #f5f5f5; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-style: italic;")
    
    def _validate_and_accept(self):
        """Valider la configuration et accepter"""
        config = ImportConfiguration(
            files=self.import_config.files,
            import_type=self.import_config.import_type
        )
        
        # Référence commune (pas de case à cocher, juste si le champ n'est pas vide)
        if self.import_config.import_type == ImportType.MULTI_FILE:
            common_ref = self.common_ref_input.text().strip()
            config.use_common_reference = bool(common_ref)
            config.common_reference = common_ref if common_ref else None
            # Libellé de la référence commune
            if hasattr(self, 'common_ref_description'):
                config.common_label = self.common_ref_description.text().strip()
        
        # Nouvelle logique: séparation références/libellés avec prise en compte de la case à cocher
        auto_references_enabled = self.auto_file_references_checkbox.isChecked()
        
        for file in config.files:
            # Référence = seulement si la case à cocher est activée
            if auto_references_enabled:
                config.individual_references[file.path] = file.suggested_reference
            else:
                # Pas de référence automatique, on laisse vide
                config.individual_references[file.path] = ""
            
            # Libellé = ce que tape l'utilisateur (peut être vide)
            desc_input = self.findChild(QLineEdit, f"desc_{file.path}")
            if desc_input:
                user_label = desc_input.text().strip()
                config.individual_labels[file.path] = user_label if user_label else ""
        
        # Options de format et techniques
        if hasattr(self, 'third_col_combo'):
            choice = self.third_col_combo.currentText()
            if choice == "Ignorer":
                config.third_column_choice = "ignore"
            elif choice == "Autre référence":
                config.third_column_choice = "other_ref"
            elif choice == "Notes":
                config.third_column_choice = "notes"
        
        if hasattr(self, 'headers_checkbox'):
            config.has_headers = self.headers_checkbox.isChecked()
        
        # Ancienne configuration (pour compatibilité si nécessaire)
        config.label_config = LabelConfiguration()
        
        self.result_config = config
        self.accept()
    
    def get_configuration(self) -> Optional[ImportConfiguration]:
        """Récupérer la configuration résultat"""
        return self.result_config
    
    def _analyze_formats_and_preview(self):
        """Analyser les formats des fichiers et générer l'aperçu des données"""
        if not self.import_config.files:
            return
        
        # Analyser le premier fichier pour déterminer le format général
        first_file = self.import_config.files[0]
        detected_columns = 0
        sample_data = []
        
        try:
            if first_file.data:
                sample_data = first_file.data[:3]  # 3 premières lignes
                if sample_data:
                    detected_columns = len(sample_data[0])
            else:
                # Charger les données si pas encore fait
                if first_file.type == FileType.CSV:
                    data = self.load_csv_data(first_file.path, max_rows=5)
                else:  # PDF
                    data = self.load_pdf_data(first_file.path, max_rows=5)
                
                if data:
                    sample_data = data[:3]
                    detected_columns = len(data[0]) if data else 0
                    
        except Exception as e:
            print(f"Erreur lors de l'analyse du format: {e}")
            detected_columns = 2  # Valeur par défaut
            sample_data = []
        
        # Mise à jour de la configuration d'import
        self.import_config.csv_import_mode = detected_columns
        
        # Afficher les informations de format
        file_types = set(f.type.value.upper() for f in self.import_config.files)
        if len(self.import_config.files) == 1:
            info_text = f"📊 Fichier {first_file.type.value.upper()} détecté: {detected_columns} colonnes"
        else:
            types_str = ", ".join(file_types)
            info_text = f"📊 Fichiers détectés ({types_str}): {detected_columns} colonnes"
        
        self.format_info_label.setText("Format reconnu:")
        
        # Description du format
        if detected_columns == 1:
            format_desc = "• 1 colonne → Réf. Modèle uniquement"
        elif detected_columns == 2:
            format_desc = "• 2 colonnes → Réf. Modèle + Réf. Commerciale"
        elif detected_columns == 3:
            if FileType.PDF in [f.type for f in self.import_config.files]:
                format_desc = "• 3 colonnes → Réf. technique + Réf. commerciale + Description"
            else:
                format_desc = "• 3 colonnes → Réf. Modèle + Réf. Commerciale + Autre"
        elif detected_columns >= 4:
            format_desc = "• 4+ colonnes → Format complet (Type, Fabricant, Réf. Modèle, Réf. Commerciale, ...)"
        else:
            format_desc = "• Format non reconnu"
        
        self.format_desc_label.setText(format_desc)
        
        # Générer l'aperçu des données
        if sample_data:
            preview_content = ""
            
            # En-têtes de colonnes
            if detected_columns > 0:
                header_line = ""
                for i in range(detected_columns):
                    header_line += f"Col{i+1:<15} "
                preview_content += f"{'='*60}\n{header_line}\n{'='*60}\n"
            
            # Données d'exemple
            for row in sample_data:
                line = ""
                for j in range(min(detected_columns, len(row))):
                    cell_value = str(row[j])[:12] + "..." if len(str(row[j])) > 12 else str(row[j])
                    line += f"{cell_value:<15} "
                preview_content += f"{line}\n"
            
            if len(first_file.data or []) > 3:
                preview_content += f"\n... et {len(first_file.data or []) - 3} autres lignes"
            
            self.preview_text.setPlainText(preview_content)
        
        # Afficher les options spécifiques selon le format
        if detected_columns == 3:
            self.third_col_widget.show()
            if FileType.PDF in [f.type for f in self.import_config.files]:
                self.third_col_label.setText("Destination Description:")
            else:
                self.third_col_label.setText("Destination 3ème colonne:")
        else:
            self.third_col_widget.hide()
        
        # Afficher les options CSV si nécessaire
        has_csv = any(f.type == FileType.CSV for f in self.import_config.files)
        if has_csv:
            self.headers_checkbox.show()
        else:
            self.headers_checkbox.hide()
    


class ImportManager:
    """Gestionnaire unifié pour tous les types d'imports"""
    
    def __init__(self, db_manager, parent_widget=None):
        self.db_manager = db_manager
        self.parent_widget = parent_widget
    
    def load_csv_data(self, file_path: str, max_rows: Optional[int] = None) -> List[List[str]]:
        """
        Méthode unifiée pour le chargement CSV avec limite optionnelle
        
        Args:
            file_path: Chemin vers le fichier CSV
            max_rows: Nombre maximum de lignes à charger (None = toutes)
            
        Returns:
            Liste des lignes (chaque ligne est une liste de cellules)
            
        Raises:
            ValueError: Si le fichier ne peut pas être lu
        """
        import csv
        
        # Détection de l'encodage
        encodings = ['utf-8', 'latin1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    # Détection du séparateur
                    sample = f.read(1024)
                    f.seek(0)
                    
                    sniffer = csv.Sniffer()
                    try:
                        delimiter = sniffer.sniff(sample, delimiters=';,\t').delimiter
                    except csv.Error:
                        delimiter = ';'
                    
                    reader = csv.reader(f, delimiter=delimiter)
                    rows = []
                    
                    for i, row in enumerate(reader):
                        # Appliquer la limite si spécifiée
                        if max_rows is not None and i >= max_rows:
                            break
                        
                        # Ignorer les lignes vides
                        if any(cell.strip() if cell is not None else False for cell in row):
                            rows.append(row)
                    
                    return rows
                    
            except (UnicodeDecodeError, FileNotFoundError, IOError) as e:
                # FileNotFoundError : fichier n'existe pas
                # IOError : problème d'accès au fichier  
                # UnicodeDecodeError : problème d'encodage -> essayer le suivant
                if isinstance(e, FileNotFoundError):
                    # Fichier n'existe pas, arrêter immédiatement
                    break
                elif isinstance(e, UnicodeDecodeError):
                    # Problème d'encodage, essayer le suivant
                    continue
                else:
                    # Autre erreur IO, arrêter
                    break
        
        # Si on arrive ici, aucun encodage n'a fonctionné
        raise ValueError(f"Impossible de lire le fichier CSV: {file_path} (fichier introuvable ou format invalide)")
    
    def load_pdf_data(self, file_path: str, max_rows: Optional[int] = None) -> List[List[str]]:
        """
        Méthode unifiée pour le chargement PDF avec limite optionnelle
        
        Args:
            file_path: Chemin vers le fichier PDF
            max_rows: Nombre maximum de lignes à charger (None = toutes)
            
        Returns:
            Liste des lignes extraites du PDF
            
        Raises:
            ValueError: Si le fichier ne peut pas être traité
        """
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor
            extractor = CamelotPDFExtractor()
            data = extractor.extract_data(file_path)
            
            if not data:
                return []
            
            # Appliquer la limite si spécifiée
            if max_rows is not None:
                return data[:max_rows]
            else:
                return data
                
        except ImportError as e:
            raise ValueError(f"Extracteur PDF non disponible: {e}")
        except Exception as e:
            raise ValueError(f"Erreur lors de l'extraction PDF: {e}")
    
    def import_files(self, file_paths: List[str], show_dialog: bool = True) -> Optional[Dict[str, Any]]:
        """
        Importer un ou plusieurs fichiers
        """
        print(f"🎯 MÉTHODE import_files APPELÉE avec {len(file_paths)} fichiers: {file_paths}")
        """
        
        Args:
            file_paths: Liste des chemins de fichiers
            show_dialog: Afficher l'interface de configuration
            
        Returns:
            Résultats d'import ou None si annulé
        """
        # Préparer la configuration
        import_files = []
        for path in file_paths:
            file_type = self._detect_file_type(path)
            if file_type:
                import_file = ImportFile(
                    path=path,
                    type=file_type,
                    suggested_reference=self._extract_reference_from_filename(path),
                    suggested_label=self._extract_reference_from_filename(path),
                    data=self._get_sample_data(path, file_type)
                )
                import_files.append(import_file)
        
        if not import_files:
            return None
        
        # Déterminer le type d'import
        import_type = ImportType.SINGLE_FILE if len(import_files) == 1 else ImportType.MULTI_FILE
        
        config = ImportConfiguration(
            files=import_files,
            import_type=import_type
        )
        
        if show_dialog:
            dialog = ImportDialog(self.parent_widget, config)
            if dialog.exec_() != QDialog.Accepted:
                return None
            
            config = dialog.get_configuration()
            if not config:
                return None
        
        # PHASE 1: Décision intelligente Async vs Sync avec fallback automatique
        return self._execute_import(config)

    def import_from_drag_drop(self, file_paths: List[str]) -> Optional[Dict[str, Any]]:
        """
        Import spécialisé pour drag&drop avec paramètres par défaut intelligents
        
        Args:
            file_paths: Liste des fichiers à importer
            
        Returns:
            Résultats de l'import ou None si annulé/échoué
            
        Notes:
            - Utilise le nom de fichier comme référence par défaut
            - Affiche toujours le dialogue d'options (UX cohérente)
            - Gère les imports multi-fichiers PDF
            - Format d'historique spécialisé pour drag&drop
        """
        try:
            if not file_paths:
                return None
                
            # Valider et préparer les fichiers
            import_files = []
            for file_path in file_paths:
                if not os.path.exists(file_path):
                    continue
                    
                file_type = self._detect_file_type(file_path)
                if not file_type:
                    continue
                    
                # Référence par défaut depuis nom fichier
                default_reference = self._extract_reference_from_filename(file_path)
                
                # Données d'aperçu pour le dialogue
                sample_data = self._get_sample_data(file_path, file_type)
                
                import_files.append({
                    'path': file_path,
                    'type': file_type,
                    'default_reference': default_reference,
                    'sample_data': sample_data
                })
            
            if not import_files:
                return None
                
            # Déterminer le type d'import
            import_type = ImportType.SINGLE_FILE if len(import_files) == 1 else ImportType.MULTI_FILE
            
            # Configuration avec paramètres par défaut pour drag&drop
            config = ImportConfiguration(
                files=import_files,
                import_type=import_type
            )
            
            # Pour drag&drop, on propose toujours le premier nom de fichier comme référence
            if import_files:
                config.reference_piece = import_files[0]['default_reference']
            
            # Dialogue adapté pour drag&drop
            from src.ui.import_dialog import ImportDialog
            dialog = ImportDialog(self.parent_widget, config)
            
            # Titre spécialisé pour drag&drop
            dialog.setWindowTitle("Import par Glisser-Déposer")
            
            if dialog.exec_() != QDialog.Accepted:
                return None
            
            config = dialog.get_configuration()
            if not config:
                return None
            
            # Effectuer l'import avec la même logique de fallback
            results = self._execute_import(config)
            
            # Marquer les résultats comme provenant du drag&drop
            if results:
                results['import_source'] = 'drag_drop'
                results['source_files'] = [f['path'] for f in import_files]
                
                # Format d'historique spécialisé
                if len(import_files) == 1:
                    file_name = os.path.basename(import_files[0]['path'])
                    file_ext = import_files[0]['type'].value.upper()
                    results['history_label'] = f"{file_ext} (Glisser-Déposer - {file_name})"
                else:
                    results['history_label'] = f"PDF Multi-fichiers ({len(import_files)} fichiers)"
            
            return results
            
        except Exception as e:
            print(f"Erreur import drag&drop: {e}")
            return None
    
    def _detect_file_type(self, file_path: str) -> Optional[FileType]:
        """Détecter le type de fichier"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.csv':
            return FileType.CSV
        elif ext == '.pdf':
            return FileType.PDF
        return None
    
    def _extract_reference_from_filename(self, file_path: str) -> str:
        """Extraire une référence depuis le nom de fichier"""
        return os.path.splitext(os.path.basename(file_path))[0]
    
    def _get_sample_data(self, file_path: str, file_type: FileType) -> Optional[List[List[str]]]:
        """Récupérer un échantillon de données pour l'aperçu"""
        try:
            if file_type == FileType.CSV:
                return self.load_csv_data(file_path, max_rows=5)
            elif file_type == FileType.PDF:
                return self.load_pdf_data(file_path, max_rows=5)
        except Exception as e:
            print(f"Erreur lors du chargement d'échantillon {file_path}: {e}")
        
        return None
    
    
    def _execute_import(self, config: ImportConfiguration) -> Dict[str, Any]:
        """Exécuter l'import synchrone OPTIMISÉ pour responsivité UI"""
        # OPTIMISATION CACHE: Suspendre les invalidations pendant tout l'import
        cache_service = getattr(self.db_manager, 'cache_invalidation', None)
        if cache_service:
            cache_service.suspend_invalidation(f"import de {len(config.files)} fichier(s)")

        try:
            results = {
                'total_files': len(config.files),
                'successful_files': 0,
                'total_imported': 0,
                'matches_found': 0,
                'new_entries': 0,
                'associations_created': 0,
                'associations_existing': 0,
                'manual_completion': 0,
                'duplicates_in_file': 0,
                'errors': [],
                'file_details': []  # Nouveau: détails par fichier
            }

            app_logger.info(f"📝 SYNC OPTIMISÉ: Import de {len(config.files)} fichiers")

            # OPTIMISATION: Barre de progression NON-MODALE pour éviter les freezes
            progress = QProgressDialog(
            "Importation en cours...",
            "Annuler",
            0,
            len(config.files),
            self.parent_widget
            )
            progress.setWindowModality(Qt.NonModal)  # NON-MODAL = plus responsive
            progress.setMinimumDuration(1000)  # Afficher après 1s seulement
            progress.show()

            for i, file in enumerate(config.files):
                # OPTIMISATION: Plus d'appels à processEvents pour fluidité
                QApplication.processEvents()

                if progress.wasCanceled():
                    app_logger.info(f"⚠️ Import annulé par utilisateur à {i}/{len(config.files)}")
                    break

                progress.setValue(i)
                progress.setLabelText(f"Import de {file.filename}... ({i+1}/{len(config.files)})")

                # OPTIMISATION: ProcessEvents après chaque update UI
                QApplication.processEvents()

                try:
                    app_logger.debug(f"📁 Traitement fichier {i+1}/{len(config.files)}: {file.filename}")

                    # Chaque fichier a son propre set pour éviter doublons intra-fichier seulement
                    file_local_seen_refs = set()
                    file_results = self._import_single_file(file, config, file_local_seen_refs)
                    results['successful_files'] += 1

                    # Ajouter les détails du fichier
                    file_detail = {
                        'filename': file.filename,
                        'lines_processed': file_results.get('total_lines_extracted', 0),  # Lignes extraites du fichier
                        'type': 'PDF' if file.type.name == 'PDF' else 'CSV'
                    }
                    results['file_details'].append(file_detail)

                    # Agréger les résultats (y compris les nouvelles métriques)
                    for key in ['total_imported', 'matches_found', 'new_entries', 'associations_created', 'associations_existing', 'manual_completion', 'duplicates_in_file']:
                        results[key] += file_results.get(key, 0)

                    # OPTIMISATION: Mise à jour intermédiaire tous les 5 fichiers
                    if (i + 1) % 5 == 0:
                        app_logger.info(f"⏳ Progression: {i+1}/{len(config.files)} fichiers traités")
                        QApplication.processEvents()  # Permettre à l'UI de se rafraîchir

                except Exception as e:
                    error_msg = f"{file.filename}: {str(e)}"
                    results['errors'].append(error_msg)
                    app_logger.error(f"❌ Erreur import fichier: {error_msg}")

            progress.setValue(len(config.files))
            progress.close()

            app_logger.info(f"✅ SYNC TERMINÉ: {results['successful_files']}/{len(config.files)} fichiers importés")

            # Phase 2.3: Invalider le cache après import complet
            if hasattr(self.db_manager, 'cache_invalidation'):
                self.db_manager.cache_invalidation.invalidate_after_import(results)

            return results

        finally:
            # OPTIMISATION CACHE: Reprendre les invalidations et invalider une seule fois
            if cache_service:
                cache_service.resume_invalidation(force_invalidate=True)
    
    def _import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set) -> Dict[str, Any]:
        """Importer un fichier unique"""
        # Charger les données du fichier avec les méthodes unifiées
        if file.type == FileType.CSV:
            data = self.load_csv_data(file.path)
        elif file.type == FileType.PDF:
            data = self.load_pdf_data(file.path)
        else:
            raise ValueError(f"Type de fichier non supporté: {file.type}")
        
        if not data:
            raise ValueError("Aucune donnée trouvée dans le fichier")
        
        # Nouvelle logique: références et libellés séparés
        references_and_labels = []  # Liste de tuples (référence, libellé)
        
        # Référence commune avec son libellé
        if config.use_common_reference and config.common_reference:
            # Utiliser le libellé saisi par l'utilisateur, ou laisser vide si pas de libellé
            common_label = config.common_label if config.common_label else ""
            references_and_labels.append((config.common_reference, common_label))
        
        # Référence individuelle du fichier avec son libellé
        individual_ref = config.individual_references.get(file.path, file.suggested_reference)
        individual_label = config.individual_labels.get(file.path, "")
        
        # Garder le libellé vide si l'utilisateur n'a rien saisi
        references_and_labels.append((individual_ref, individual_label))
        
        # Effectuer l'import des données - Mode batch pour gros volumes
        # Seuil pour activer le mode batch optimisé (réduit pour meilleure performance)
        BATCH_THRESHOLD = 50  # lignes - batch dès 50 lignes pour optimisation immédiate
        
        if len(data) >= BATCH_THRESHOLD:
            print(f"🚀 Mode BATCH activé pour {len(data)} lignes (seuil: {BATCH_THRESHOLD})")
            return self._process_data_import_batch(
                data, 
                references_and_labels,
                config,
                file,
                file_seen_device_refs
            )
        else:
            print(f"📝 Mode standard pour {len(data)} lignes (< {BATCH_THRESHOLD})")
            return self._process_data_import(
                data, 
                references_and_labels,  # Maintenant liste de tuples (ref, label)
                config,
                file,  # Passer le fichier pour les associations par fichier
                file_seen_device_refs  # CORRECTION: Suivi local par fichier
            )
    
    
    def _process_data_import(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]], 
                           config: ImportConfiguration, file: ImportFile, seen_device_refs: set) -> Dict[str, Any]:
        """Traiter l'import des données avec les références et libellés séparés"""
        print(f"🚀 MÉTHODE _process_data_import APPELÉE avec {len(data)} lignes")
        results = {
            'total_imported': 0,
            'matches_found': 0,
            'new_entries': 0,
            'associations_created': 0,
            'associations_existing': 0,
            'manual_completion': 0,  # Appareils créés/mis à jour sans Type ET Fabricant
            'duplicates_in_file': 0,  # Doublons ref_modele+commercial_ref dans le fichier
            'total_lines_extracted': 0  # Total lignes du fichier (avant traitement doublons)
        }
        
        # CORRECTION: Utiliser le set LOCAL pour détecter les doublons uniquement DANS ce fichier
        # Ne PAS détecter comme doublon des lignes qui sont dans des fichiers différents
        
        for row in data:
            if not row or not any(cell.strip() if cell is not None else False for cell in row):
                continue
            
            # Compter chaque ligne non vide comme extraite du fichier
            results['total_lines_extracted'] += 1
            
            # Extraire les références pour vérification doublon - LOGIQUE INTELLIGENTE
            # Si on a 4+ colonnes et les 2 premières sont très répétitives, utiliser colonnes 2-3
            if len(row) >= 4:
                col0 = str(row[0]).strip() if row[0] is not None else ""
                col1 = str(row[1]).strip() if row[1] is not None else ""  
                col2 = str(row[2]).strip() if row[2] is not None else ""
                col3 = str(row[3]).strip() if row[3] is not None else ""
                
                # Si col2 et col3 semblent plus uniques (contiennent des chiffres/codes), les privilégier
                if (col2 and col3 and (any(c.isdigit() for c in col2) or any(c.isdigit() for c in col3))):
                    ref_modele = col2
                    commercial_ref = col3
                    print(f"🔍 FORMAT 4 COLONNES: Utilisation col2|col3 pour déduplication: {col2}|{col3}")
                else:
                    ref_modele = col0
                    commercial_ref = col1
                    print(f"🔍 FORMAT 4 COLONNES: Utilisation col0|col1 pour déduplication: {col0}|{col1}")
            else:
                # Format standard 2-3 colonnes
                ref_modele = str(row[0]).strip() if len(row) >= 1 and row[0] is not None else ""
                commercial_ref = str(row[1]).strip() if len(row) >= 2 and row[1] is not None else ""
                print(f"🔍 FORMAT STANDARD: Utilisation col0|col1 pour déduplication: {ref_modele}|{commercial_ref}")
            
            # Vérifier si c'est un doublon dans le fichier
            device_key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            print(f"🔍 ANALYSE LIGNE: ref_modele='{ref_modele}', commercial_ref='{commercial_ref}', device_key='{device_key}'")
            print(f"🔍 SEEN_REFS: {list(seen_device_refs)}")
            if device_key in seen_device_refs and (ref_modele or commercial_ref):
                results['duplicates_in_file'] += 1
                print(f"  🔄 Doublon dans le fichier ignoré: {ref_modele} | {commercial_ref}")
                continue  # Les doublons ne sont PAS comptés dans total_imported
            elif ref_modele or commercial_ref:
                seen_device_refs.add(device_key)
                print(f"✅ LIGNE ACCEPTÉE: Ajout {device_key} aux références vues")
            
            results['total_imported'] += 1
            
            # Traiter la ligne selon le mode d'import
            device_data = self._parse_row_data(row, config)
            
            if not device_data:
                continue
            
            # Insérer ou trouver l'appareil
            device_id = self._insert_or_find_device(device_data)
            
            if device_id:
                if device_data.get('is_new', False):
                    results['new_entries'] += 1
                    # Vérifier si l'appareil CRÉÉ nécessite une complétion manuelle
                    if self._needs_manual_completion(device_data):
                        results['manual_completion'] += 1
                else:
                    results['matches_found'] += 1
                
                # Associer les références (chaque paire référence-libellé)
                for reference, label in references_and_labels:
                    if reference:
                        try:
                            # Callback pour gestion intelligente des libellés
                            def smart_label_callback(ref_piece, current_desc, new_desc):
                                # Si nouveau libellé fourni: l'utiliser (remplace l'ancien)
                                if new_desc and new_desc.strip():
                                    return new_desc.strip()
                                # Si pas de nouveau libellé: conserver l'ancien
                                else:
                                    return current_desc
                            
                            # Utiliser le libellé spécifique pour cette référence avec callback
                            result = self.db_manager.add_or_update_piece_with_description(
                                reference, device_id, label, confirm_callback=smart_label_callback
                            )
                            if result:
                                assoc_id, description_updated, association_created = result
                                if association_created:
                                    results['associations_created'] += 1
                                    print(f"  ✨ Association créée: {reference} → {label} pour appareil {device_id}")
                                else:
                                    results['associations_existing'] += 1
                                    print(f"  🔍 Association existante: {reference} → {label} pour appareil {device_id}")
                        except Exception as e:
                            print(f"Erreur association {reference}: {e}")
        
        return results
    
    def _process_data_import_batch(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]], 
                                 config: ImportConfiguration, file: ImportFile, seen_device_refs: set) -> Dict[str, Any]:
        """Version optimisée avec batch processing pour les gros imports"""
        print(f"🚀 MÉTHODE _process_data_import_batch APPELÉE avec {len(data)} lignes")
        print(f"🚀 BATCH MODE: Traitement optimisé de {len(data)} lignes")
        
        results = {
            'total_imported': 0,
            'matches_found': 0,
            'new_entries': 0,
            'associations_created': 0,
            'associations_existing': 0,
            'manual_completion': 0,
            'duplicates_in_file': 0,
            'total_lines_extracted': 0
        }
        
        # Progress indicator spécialisé pour le mode batch
        from PyQt5.QtWidgets import QProgressDialog, QApplication
        from PyQt5.QtCore import Qt
        
        # OPTIMISATION: Progress dialog NON-MODAL pour responsivité
        batch_progress = QProgressDialog(
            f"Mode Batch - Traitement optimisé de {len(data)} lignes...",
            "Annuler",
            0, 4,  # 4 étapes principales
            self.parent_widget
        )
        batch_progress.setWindowModality(Qt.NonModal)  # NON-MODAL = plus responsive
        batch_progress.setMinimumDuration(500)  # Afficher après 0.5s seulement
        batch_progress.show()
        
        # ÉTAPE 1: Pré-charger tous les appareils existants en mémoire (1 seule requête)
        batch_progress.setValue(0)
        batch_progress.setLabelText("📊 Pré-chargement des appareils existants...")
        QApplication.processEvents()
        
        existing_devices_cache = self._preload_existing_devices()
        print(f"📊 BATCH: {len(existing_devices_cache)} appareils en cache")
        
        # Cache pour auto-complétion (Type + Fabricant par référence)
        batch_progress.setLabelText("🧠 Construction cache auto-complétion...")
        QApplication.processEvents()
        
        autocomplete_cache = self._build_autocomplete_cache(existing_devices_cache)
        print(f"🧠 BATCH: {len(autocomplete_cache)} références dans cache auto-complétion")
        
        # ÉTAPE 2: Traitement en mémoire de toutes les lignes
        batch_progress.setValue(1)
        batch_progress.setLabelText("💾 Analyse des données en mémoire...")
        QApplication.processEvents()
        
        new_devices_batch = []
        existing_updates = []
        associations_batch = []
        processed_line_index = 0  # Compteur pour les lignes réellement traitées (hors continue)
        
        # Configuration pour progress optimisé
        from .config import Config
        progress_frequency = Config.IMPORT_PROGRESS_FREQUENCY
        total_rows = len(data)
        
        for idx, row in enumerate(data):
            # OPTIMISATION: ProcessEvents plus fréquent pour très gros volumes
            if idx > 0 and idx % 10 == 0:  # Toutes les 10 lignes au lieu de la frequency config
                QApplication.processEvents()
                # Vérifier si annulation demandée
                if batch_progress.wasCanceled():
                    app_logger.info(f"⚠️ Traitement batch annulé à la ligne {idx}/{len(data)}")
                    break

            if not row or not any(cell.strip() if cell is not None else False for cell in row):
                continue

            results['total_lines_extracted'] += 1

            # CORRECTION BATCH: Détection doublons uniquement DANS ce fichier (pas entre fichiers)
            # LOGIQUE INTELLIGENTE identique à la version standard
            if len(row) >= 4:
                col0 = str(row[0]).strip() if row[0] is not None else ""
                col1 = str(row[1]).strip() if row[1] is not None else ""
                col2 = str(row[2]).strip() if row[2] is not None else ""
                col3 = str(row[3]).strip() if row[3] is not None else ""

                # Si col2 et col3 semblent plus uniques (contiennent des chiffres/codes), les privilégier
                if (col2 and col3 and (any(c.isdigit() for c in col2) or any(c.isdigit() for c in col3))):
                    ref_modele = col2
                    commercial_ref = col3
                    print(f"🔍 BATCH FORMAT 4 COLONNES: Utilisation col2|col3 pour déduplication: {col2}|{col3}")
                else:
                    ref_modele = col0
                    commercial_ref = col1
                    print(f"🔍 BATCH FORMAT 4 COLONNES: Utilisation col0|col1 pour déduplication: {col0}|{col1}")
            else:
                # Format standard 2-3 colonnes
                ref_modele = str(row[0]).strip() if len(row) >= 1 and row[0] is not None else ""
                commercial_ref = str(row[1]).strip() if len(row) >= 2 and row[1] is not None else ""
                print(f"🔍 BATCH FORMAT STANDARD: Utilisation col0|col1 pour déduplication: {ref_modele}|{commercial_ref}")

            device_key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            print(f"🔍 BATCH ANALYSE LIGNE: ref_modele='{ref_modele}', commercial_ref='{commercial_ref}', device_key='{device_key}'")
            print(f"🔍 BATCH SEEN_REFS: {list(seen_device_refs)}")
            if device_key in seen_device_refs and (ref_modele or commercial_ref):
                results['duplicates_in_file'] += 1
                print(f"  🔄 BATCH Doublon dans le fichier ignoré: {ref_modele} | {commercial_ref}")
                continue
            elif ref_modele or commercial_ref:
                seen_device_refs.add(device_key)
                print(f"✅ BATCH LIGNE ACCEPTÉE: Ajout {device_key} aux références vues")

            # Parser les données AVANT de compter total_imported
            device_data = self._parse_row_data(row, config)
            if not device_data:
                continue  # Ligne non parsable, ne pas compter

            # MAINTENANT on compte comme ligne réellement traitée
            results['total_imported'] += 1

            # Utiliser cache auto-complétion pour améliorer les données (pas de SQL!)
            self._apply_autocomplete_from_cache(device_data, autocomplete_cache)

            # Vérifier si existe en cache (pas de requête SQL !)
            existing_id = self._find_in_cache(device_data, existing_devices_cache)

            if existing_id:
                # Appareil existant
                results['matches_found'] += 1
                if self._needs_update(device_data):
                    existing_updates.append((existing_id, device_data))
            else:
                # Nouvel appareil à créer
                results['new_entries'] += 1
                if self._needs_manual_completion(device_data):
                    results['manual_completion'] += 1
                new_devices_batch.append(device_data)

            # Préparer associations (sera traitée après insertion batch)
            # CORRECTION: Utiliser processed_line_index pour avoir des indices consécutifs
            associations_added_for_line = 0
            for reference, label in references_and_labels:
                if reference:
                    # Utiliser processed_line_index pour avoir des indices consécutifs sans trous
                    associations_batch.append((reference, label, processed_line_index, existing_id))
                    associations_added_for_line += 1

            if associations_added_for_line == 0:
                app_logger.warning(f"Ligne {processed_line_index}: Aucune association créée pour cette ligne (pas de référence valide)")

            # Incrémenter le compteur des lignes réellement traitées
            processed_line_index += 1

            # Progress update optimisé (plus fréquent pour meilleure UX)
            if idx > 0 and idx % 25 == 0:  # Mise à jour toutes les 25 lignes
                progress_percent = int((idx / total_rows) * 30)  # 30% pour cette étape
                batch_progress.setLabelText(f"💾 Analyse: {idx}/{total_rows} lignes ({progress_percent}%)")
                QApplication.processEvents()
        
        # ÉTAPE 3: Batch operations sur la base
        batch_progress.setValue(2)
        batch_progress.setLabelText(f"💿 Insertion de {len(new_devices_batch)} nouveaux appareils...")
        QApplication.processEvents()
        
        new_device_ids = self._batch_insert_devices(new_devices_batch) if new_devices_batch else []
        
        # Vérifier la correspondance IDs vs appareils
        if len(new_devices_batch) != len(new_device_ids):
            app_logger.error(f"Erreur critique: {len(new_devices_batch)} nouveaux appareils -> {len(new_device_ids)} IDs obtenus")
        if len(new_devices_batch) != len(new_device_ids):
            print(f"❌ PROBLÈME: Discordance entre appareils créés et IDs récupérés!")
            print(f"   new_devices_batch: {len(new_devices_batch)}")
            print(f"   new_device_ids: {len(new_device_ids)}")
            if new_device_ids:
                print(f"   Premier ID: {new_device_ids[0]}, Dernier ID: {new_device_ids[-1]}")
        
        batch_progress.setLabelText(f"🔄 Mise à jour de {len(existing_updates)} appareils existants...")
        QApplication.processEvents()
        
        if existing_updates:
            self._batch_update_devices(existing_updates)
            
        batch_progress.setValue(3)
        batch_progress.setLabelText(f"🔗 Création de {len(associations_batch)} associations...")
        QApplication.processEvents()
        
        # Analyser les associations qui ont besoin de nouveaux appareils
        new_device_associations = [assoc for assoc in associations_batch if not assoc[3]]  # existing_id est None
        existing_device_associations = [assoc for assoc in associations_batch if assoc[3]]  # existing_id existe
        
        # Calculer le nombre d'appareils uniques concernés par les nouvelles associations
        unique_new_device_indices = set(assoc[2] for assoc in new_device_associations)  # assoc[2] = data_index
        unique_existing_device_indices = set(assoc[2] for assoc in existing_device_associations)
        all_unique_indices = unique_new_device_indices | unique_existing_device_indices
        
        # Log détaillé pour débogage si nécessaire
        app_logger.info(f"Associations: {len(associations_batch)} total ({len(new_device_associations)} nouveaux + {len(existing_device_associations)} existants)")
        app_logger.info(f"Correspondance: {len(new_devices_batch)} nouveaux appareils = {len(unique_new_device_indices)} indices uniques")
        app_logger.info(f"Vérification: {results['total_imported']} lignes traitées vs {len(all_unique_indices)} lignes avec associations")
        
        # ALERTE si discordance entre lignes traitées et associations
        if results['total_imported'] != len(all_unique_indices):
            print(f"❌ PROBLÈME MAJEUR: {results['total_imported']} lignes traitées mais seulement {len(all_unique_indices)} ont des associations!")
            print(f"   Différence: {results['total_imported'] - len(all_unique_indices)} lignes sans association")
            # Créer l'ensemble attendu basé sur processed_line_index (0, 1, 2, ..., total_imported-1)
            expected_indices = set(range(results['total_imported']))
            missing_indices = expected_indices - all_unique_indices
            if missing_indices:
                print(f"   Indices manquants (premières 10): {sorted(list(missing_indices))[:10]}")
            
            # Debug supplémentaire: vérifier si references_and_labels est vide
            if not any(ref for ref, label in references_and_labels if ref):
                print(f"   🚨 CAUSE PROBABLE: references_and_labels ne contient aucune référence valide!")
                print(f"   references_and_labels: {references_and_labels}")
        
        if associations_batch:
            batch_results = self._batch_create_associations(associations_batch, new_device_ids)
            results['associations_created'] += batch_results.get('created', 0)
            results['associations_existing'] += batch_results.get('existing', 0)
        
        batch_progress.setValue(4)
        batch_progress.setLabelText("✅ Import terminé !")
        QApplication.processEvents()
        
        # Fermer le dialogue de progress
        batch_progress.close()
        
        # Phase 2.3: Invalider le cache après import batch
        if hasattr(self.db_manager, 'cache_invalidation'):
            self.db_manager.cache_invalidation.invalidate_after_import(results)
        
        print(f"✅ BATCH: Terminé - {results['total_imported']} lignes traitées")
        return results
    
    def _preload_existing_devices(self) -> Dict[str, Dict]:
        """Pré-charger tous les appareils existants pour éviter les requêtes répétées"""
        from .config import Config
        query = Config.QUERIES['preload_all_devices']
        rows = self.db_manager.execute_query(query)
        
        cache = {}
        for row in rows:
            device_id, ref_modele, commercial_ref, device_type, manufacturer, other_ref, notes = row
            
            # Indexer par ref_modele + commercial_ref pour recherche rapide
            if ref_modele and commercial_ref:
                key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
                cache[key] = {
                    'id': device_id,
                    'ref_modele': ref_modele,
                    'commercial_ref': commercial_ref,
                    'type': device_type,
                    'manufacturer': manufacturer,
                    'other_ref': other_ref,
                    'notes': notes
                }
        
        return cache
    
    def _build_autocomplete_cache(self, existing_devices_cache: Dict[str, Dict]) -> Dict[str, Dict[str, str]]:
        """Construire un cache pour l'auto-complétion (Type + Fabricant par référence)"""
        autocomplete_cache = {}
        
        for key, device in existing_devices_cache.items():
            ref_modele = (device.get('ref_modele') or '').strip()
            commercial_ref = (device.get('commercial_ref') or '').strip()
            device_type = (device.get('type') or '').strip()
            manufacturer = (device.get('manufacturer') or '').strip()
            
            # Créer des entrées pour auto-complétion si Type ET/OU Fabricant disponibles
            if device_type or manufacturer:
                # Indexer par ref_modele si disponible
                if ref_modele:
                    autocomplete_cache[ref_modele.lower()] = {
                        'type': device_type,
                        'manufacturer': manufacturer
                    }
                
                # Indexer par commercial_ref si disponible et différent
                if commercial_ref and commercial_ref.lower() != ref_modele.lower():
                    autocomplete_cache[commercial_ref.lower()] = {
                        'type': device_type,
                        'manufacturer': manufacturer
                    }
        
        return autocomplete_cache
    
    def _apply_autocomplete_from_cache(self, device_data: Dict[str, Any], autocomplete_cache: Dict[str, Dict[str, str]]):
        """Appliquer l'auto-complétion depuis le cache (pas de SQL!)"""
        # Ne compléter que si Type OU Fabricant manquant
        if (device_data.get('type') or '').strip() and (device_data.get('manufacturer') or '').strip():
            return  # Déjà complet
        
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()
        
        # Chercher d'abord par ref_modele
        cache_entry = None
        if ref_modele:
            cache_entry = autocomplete_cache.get(ref_modele.lower())
        
        # Si pas trouvé, chercher par commercial_ref  
        if not cache_entry and commercial_ref:
            cache_entry = autocomplete_cache.get(commercial_ref.lower())
        
        # Appliquer les données trouvées si disponibles
        if cache_entry:
            if not (device_data.get('type') or '').strip() and cache_entry.get('type'):
                device_data['type'] = cache_entry['type']
            if not (device_data.get('manufacturer') or '').strip() and cache_entry.get('manufacturer'):
                device_data['manufacturer'] = cache_entry['manufacturer']
    
    def _find_in_cache(self, device_data: Dict[str, Any], cache: Dict[str, Dict]) -> Optional[int]:
        """Trouver un appareil dans le cache (pas de SQL!)"""
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()
        
        if ref_modele and commercial_ref:
            key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            if key in cache:
                return cache[key]['id']
        
        return None
    
    def _needs_update(self, device_data: Dict[str, Any]) -> bool:
        """Vérifier si l'appareil a besoin d'une mise à jour (3ème colonne)"""
        return bool(device_data.get('other_ref') or device_data.get('notes'))
    
    def _batch_insert_devices(self, devices_batch: List[Dict[str, Any]]) -> List[int]:
        """Insertion en lot des nouveaux appareils avec chunking optimisé"""
        if not devices_batch:
            return []
        
        from .config import Config
        query = Config.QUERIES['insert_device_batch']
        chunk_size = Config.BATCH_INSERT_SIZE
        
        print(f"🚀 BATCH INSERT: {len(devices_batch)} appareils à insérer par chunks de {chunk_size}")
        
        # Utiliser une transaction globale pour l'efficacité
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        all_new_ids = []
        
        try:
            # Traiter par chunks pour optimiser SQLite
            total_chunks = (len(devices_batch) + chunk_size - 1) // chunk_size
            
            for i in range(0, len(devices_batch), chunk_size):
                chunk = devices_batch[i:i + chunk_size]
                
                # Préparer les données pour ce chunk
                insert_data = []
                for device in chunk:
                    insert_data.append((
                        device.get('type', ''),
                        device.get('manufacturer', ''),
                        device.get('ref_modele', ''),
                        device.get('commercial_ref', ''),
                        device.get('other_ref', ''),
                        device.get('notes', ''),
                        device.get('category', '')
                    ))
                
                # CORRECTION: Insérer un par un pour récupérer les IDs correctement
                # executemany() ne garantit pas cursor.lastrowid dans SQLite
                chunk_ids = []
                for device_data in insert_data:
                    cursor.execute(query, device_data)
                    if cursor.lastrowid is not None:
                        chunk_ids.append(cursor.lastrowid)
                    else:
                        print(f"❌ Chunk {i//chunk_size + 1}: Impossible de récupérer l'ID pour un appareil")
                        conn.rollback()
                        return []
                
                all_new_ids.extend(chunk_ids)
                print(f"✅ Chunk {i//chunk_size + 1}: {len(chunk_ids)} appareils insérés")
            
            conn.commit()
            print(f"✅ BATCH FINAL: {len(all_new_ids)} appareils insérés au total")
            return all_new_ids
            
        except Exception as e:
            conn.rollback()
            print(f"❌ BATCH: Erreur insertion: {e}")
            print(f"❌ BATCH: IDs partiels récupérés avant erreur: {len(all_new_ids)}")
            import traceback
            print(f"❌ BATCH: Stack trace: {traceback.format_exc()}")
            return []
    
    def _batch_update_devices(self, updates_batch: List[Tuple[int, Dict[str, Any]]]):
        """Mise à jour en lot des appareils existants"""
        if not updates_batch:
            return
        
        # Groupe par type de mise à jour
        other_ref_updates = []
        notes_updates = []
        
        for device_id, device_data in updates_batch:
            if device_data.get('other_ref'):
                other_ref_updates.append((device_data['other_ref'], device_id))
            if device_data.get('notes'):
                notes_updates.append((device_data['notes'], device_id))
        
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            if other_ref_updates:
                from .config import Config
                cursor.executemany(Config.QUERIES['update_device_other_ref'], other_ref_updates)
            if notes_updates:
                from .config import Config
                cursor.executemany(Config.QUERIES['update_device_notes'], notes_updates)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"❌ BATCH: Erreur mise à jour: {e}")
    
    def _batch_create_associations(self, associations_batch: List[Tuple], new_device_ids: List[int]) -> Dict[str, int]:
        """Création en lot des associations pièces-appareils"""
        if not associations_batch:
            return {'created': 0, 'existing': 0}
        
        results = {'created': 0, 'existing': 0}
        
        # Mapper les indices de data vers les IDs réels (nouveaux + existants) 
        device_id_mapping = {}
        new_device_counter = 0
        
        # Traiter chaque association: (reference, label, data_index, existing_id)
        for reference, label, data_index, existing_id in associations_batch:
            # Utiliser l'index comme clé pour éviter les doublons d'attribution d'ID
            cache_key = f"{data_index}_{existing_id}"
            
            if cache_key in device_id_mapping:
                # Réutiliser l'ID déjà attribué pour cette ligne de donnée
                device_id = device_id_mapping[cache_key]
            elif existing_id:
                # Appareil existant
                device_id = existing_id
                device_id_mapping[cache_key] = device_id
            else:
                # Nouvel appareil - utiliser l'ID de la liste new_device_ids
                if new_device_counter < len(new_device_ids):
                    device_id = new_device_ids[new_device_counter]
                    device_id_mapping[cache_key] = device_id
                    new_device_counter += 1
                else:
                    print(f"⚠️ BATCH: Pas assez d'IDs pour les nouveaux appareils (index {data_index})")
                    continue
            
            try:
                # Utiliser le callback pour gestion intelligente des libellés
                def smart_label_callback(ref_piece, current_desc, new_desc):
                    # Si nouveau libellé fourni: l'utiliser (remplace l'ancien)
                    if new_desc and new_desc.strip():
                        return new_desc.strip()
                    # Si pas de nouveau libellé: conserver l'ancien
                    else:
                        return current_desc
                
                # Utiliser le libellé spécifique pour cette référence avec callback
                result = self.db_manager.add_or_update_piece_with_description(
                    reference, device_id, label, confirm_callback=smart_label_callback
                )
                
                # result = (assoc_id, description_updated, association_created)
                assoc_id, description_updated, association_created = result
                
                if association_created:
                    results['created'] += 1
                else:
                    results['existing'] += 1
                    
            except Exception as e:
                print(f"❌ BATCH: Erreur association {reference}: {e}")
        
        print(f"🔗 BATCH: Associations - Créées: {results['created']}, Existantes: {results['existing']}")
        return results
    
    def _parse_row_data(self, row: List[str], config: ImportConfiguration) -> Optional[Dict[str, Any]]:
        """Parser une ligne de données selon la configuration"""
        if not row:
            return None
        
        # Mode basique : détecter automatiquement selon le nombre de colonnes
        data = {}
        
        if len(row) >= 1:
            data['ref_modele'] = str(row[0]).strip() if row[0] is not None else ""
        
        if len(row) >= 2:
            data['commercial_ref'] = str(row[1]).strip() if row[1] is not None else ""
        
        if len(row) >= 3:
            # Traiter la 3ème colonne selon le paramètre third_column_choice
            third_col_value = str(row[2]).strip() if row[2] is not None else ""
            if config.third_column_choice == "other_ref":
                data['other_ref'] = third_col_value
            elif config.third_column_choice == "notes":
                data['notes'] = third_col_value
            # Si choice == "ignore", ne rien faire avec cette colonne
        
        if len(row) >= 4:
            data['type'] = str(row[0]).strip() if row[0] is not None else ""
            data['manufacturer'] = str(row[1]).strip() if row[1] is not None else ""
            data['ref_modele'] = str(row[2]).strip() if row[2] is not None else ""
            data['commercial_ref'] = str(row[3]).strip() if row[3] is not None else ""
            
        if len(row) >= 5:
            # Pour les fichiers 5+ colonnes, la 5ème colonne pourrait aussi être concernée
            fifth_col_value = str(row[4]).strip() if row[4] is not None else ""
            if config.third_column_choice == "other_ref":
                data['other_ref'] = fifth_col_value
            elif config.third_column_choice == "notes":
                data['notes'] = fifth_col_value
            # Si choice == "ignore", ne rien faire avec cette colonne
        
        # Vérifier qu'on a au moins une donnée utile
        if not any(v for v in data.values() if v):
            return None
        
        # Appliquer l'autocomplétion si Type ou Fabricant sont manquants
        if data and (not data.get('type') or not data.get('manufacturer')):
            self._try_auto_complete(data)
        
        return data
    
    def _needs_manual_completion(self, device_data: Dict[str, Any]) -> bool:
        """Vérifier si un appareil a besoin d'une complétion manuelle (ni type ni fabricant)"""
        type_val = device_data.get('type') or ''
        manufacturer_val = device_data.get('manufacturer') or ''
        type_empty = not str(type_val).strip()
        manufacturer_empty = not str(manufacturer_val).strip()
        return type_empty and manufacturer_empty
    
    def _update_existing_device(self, device_id: int, device_data: Dict[str, Any]) -> None:
        """Mettre à jour un appareil existant avec les nouvelles données de la 3ème colonne"""
        try:
            # Construire les données de mise à jour pour la 3ème colonne uniquement
            update_data = {}
            
            # Si les données contiennent other_ref ou notes (depuis 3ème colonne), les ajouter
            if 'other_ref' in device_data and device_data['other_ref'].strip():
                update_data['other_ref'] = device_data['other_ref'].strip()
            
            if 'notes' in device_data and device_data['notes'].strip():
                update_data['notes'] = device_data['notes'].strip()
            
            if update_data:
                # Construire la requête de mise à jour
                set_clauses = [f"{field} = ?" for field in update_data.keys()]
                update_query = f"UPDATE appareils SET {', '.join(set_clauses)} WHERE id = ?"
                params = list(update_data.values()) + [device_id]
                
                self.db_manager.execute_query(update_query, params)
                print(f"🔄 Appareil {device_id} mis à jour avec 3ème colonne: {update_data}")
        
        except Exception as e:
            print(f"Erreur mise à jour appareil {device_id}: {e}")
    
    def _insert_or_find_device(self, device_data: Dict[str, Any]) -> Optional[int]:
        """Insérer ou trouver un appareil existant"""
        try:
            # Chercher d'abord un appareil existant
            ref_modele = device_data.get('ref_modele', '')
            commercial_ref = device_data.get('commercial_ref', '')
            
            if ref_modele or commercial_ref:
                # Recherche stricte : un appareil est identique si TOUTES les références principales correspondent
                # Cela évite les faux positifs comme 2108002 vs 2108002000 avec même commercial_ref
                search_query = """
                    SELECT id FROM appareils 
                    WHERE ref_modele = ? AND commercial_ref = ?
                       AND ref_modele != '' AND commercial_ref != ''
                    LIMIT 1
                """
                results = self.db_manager.execute_query(search_query, [ref_modele, commercial_ref])
                
                if results:
                    # Appareil trouvé, on le met à jour avec les nouvelles données si nécessaire
                    existing_id = results[0][0]
                    self._update_existing_device(existing_id, device_data)
                    return existing_id
                
                # Si pas de match exact, vérifier si seule ref_modele correspond (cas spécial)
                if ref_modele and ref_modele.strip():
                    search_query_ref = """
                        SELECT id FROM appareils 
                        WHERE ref_modele = ? AND ref_modele != ''
                           AND (commercial_ref = '' OR commercial_ref IS NULL)
                        LIMIT 1
                    """
                    results_ref = self.db_manager.execute_query(search_query_ref, [ref_modele])
                    if results_ref:
                        return results_ref[0][0]
            
            
            # Créer un nouvel appareil
            device_id = self.db_manager.insert_appareil(device_data)
            if device_id:
                device_data['is_new'] = True
            return device_id
            
        except Exception as e:
            print(f"Erreur insertion appareil: {e}")
            return None
    
    def _try_auto_complete(self, appareil_data: dict) -> bool:
        """Essayer de compléter automatiquement Type et Fabricant à partir des références
        
        Returns:
            bool: True si l'auto-complétion a réussi, False sinon
        """
        try:
            # Vérifier d'abord si les champs sont vides
            type_empty = not appareil_data.get('type', '').strip()
            manufacturer_empty = not appareil_data.get('manufacturer', '').strip()
            
            # Si les deux champs sont remplis, pas besoin d'auto-complétion
            if not type_empty and not manufacturer_empty:
                return False
            
            # Récupérer les références principales pour la recherche
            ref_modele = appareil_data.get('ref_modele', '').strip()
            commercial_ref = appareil_data.get('commercial_ref', '').strip()
            
            if not ref_modele and not commercial_ref:
                return False  # Aucune référence principale pour faire la recherche
            
            # Chercher dans la base des appareils existants avec les références principales
            query = """
                SELECT type, manufacturer 
                FROM appareils 
                WHERE (ref_modele = ? OR commercial_ref = ?)
                AND type IS NOT NULL AND type != '' 
                AND manufacturer IS NOT NULL AND manufacturer != ''
                LIMIT 1
            """
            
            results = self.db_manager.execute_query(query, [ref_modele, commercial_ref])
            
            if results:
                found_type, found_manufacturer = results[0]
                
                print(f"🔍 Autocomplétion trouvée: Type='{found_type}', Fabricant='{found_manufacturer}'")
                
                # Compléter seulement les champs vides
                if type_empty:
                    appareil_data['type'] = found_type
                    print(f"  ✅ Type complété: '' -> '{found_type}'")
                
                if manufacturer_empty:
                    appareil_data['manufacturer'] = found_manufacturer
                    print(f"  ✅ Fabricant complété: '' -> '{found_manufacturer}'")
                
                return True
            
            # Aucune correspondance trouvée
            return False
                        
        except Exception as e:
            print(f"Erreur auto-completion: {e}")
            return False


# Fonctions utilitaires pour l'intégration
def create_import_manager(db_manager, parent_widget=None) -> ImportManager:
    """Créer une instance du gestionnaire d'import"""
    return ImportManager(db_manager, parent_widget)


def import_files_with_dialog(file_paths: List[str], db_manager, parent_widget=None) -> Optional[Dict[str, Any]]:
    """Fonction utilitaire pour importer des fichiers avec interface"""
    manager = create_import_manager(db_manager, parent_widget)
    return manager.import_files(file_paths, show_dialog=True)


def import_from_drag_drop(file_paths: List[str], db_manager, parent_widget=None) -> Optional[Dict[str, Any]]:
    """Fonction utilitaire pour import drag&drop"""
    manager = create_import_manager(db_manager, parent_widget)
    return manager.import_from_drag_drop(file_paths)
