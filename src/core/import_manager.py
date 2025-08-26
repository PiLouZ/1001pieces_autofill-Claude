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
        
        self.setWindowTitle("Configuration d'importation - SPACING 0PX 🎯")
        self.setModal(True)
        self.setMinimumWidth(1000)  # Largeur maintenue à 1000
        self.setMinimumHeight(950)  # Hauteur augmentée 850 → 950 (+100px)
        
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
            file_label.setStyleSheet("font-weight: bold; color: #495057; padding: 4px 2px;")
            file_label.setAlignment(Qt.AlignCenter)
            files_grid.addWidget(file_label, row, col)
        
        files_main_layout.addLayout(files_grid)
        files_group.setLayout(files_main_layout)
        layout.addWidget(files_group)
        
        # Section format reconnu et aperçu des données (repositionnée ici)
        format_group = QGroupBox("Format reconnu et aperçu")
        format_layout = QVBoxLayout()
        
        self.format_info_label = QLabel()
        self.format_info_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        format_layout.addWidget(self.format_info_label)
        
        self.format_desc_label = QLabel()
        self.format_desc_label.setStyleSheet("color: #6c757d; margin-left: 20px;")
        format_layout.addWidget(self.format_desc_label)
        
        # Aperçu des données avec hauteur augmentée
        self.preview_text = QTextEdit()
        self.preview_text.setMinimumHeight(120)  # Augmenté pour au moins 5 lignes
        self.preview_text.setMaximumHeight(180)  # Hauteur max augmentée aussi
        self.preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; font-family: 'Monaco', 'Menlo', 'Courier New', monospace; font-size: 11px;")
        self.preview_text.setReadOnly(True)
        format_layout.addWidget(self.preview_text)
        
        # Espacement visuel augmenté entre l'aperçu et les options
        format_layout.addSpacing(25)  # Augmenté de 15 à 25 pour éviter le chevauchement
        
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
            ref_info = QLabel("💡 La référence commune sera associée à TOUS les appareils importés\n(ex: numéro de lot, commande, projet...)")
            ref_info.setStyleSheet("color: #666; font-style: italic; margin-bottom: 15px; padding: 8px; background-color: #f0f8ff; border-radius: 4px;")
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
            self.common_ref_input.setPlaceholderText("LOT_2024_001, CMD_12345...")
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
        
        # Zone scrollable pour les références individuelles - ASCENSEUR FORCÉ
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)  # FORCER l'ascenseur toujours visible
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Pas d'ascenseur horizontal
        scroll_area.setMinimumHeight(200)  # Hauteur très réduite pour garantir le scroll
        scroll_area.setMaximumHeight(250)  # Hauteur max réduite pour forcer le scroll
        
        scroll_widget = QWidget()
        scroll_widget.setObjectName("scroll_content")
        # Forcer une taille minimum pour garantir que le contenu dépasse la zone visible
        scroll_widget.setMinimumHeight(400)  # Plus grand que la zone scroll (250px) pour forcer le scroll
        
        self.individual_refs_widget = QVBoxLayout(scroll_widget)
        self.individual_refs_widget.setContentsMargins(5, 5, 5, 10)  # Marges réduites
        self.individual_refs_widget.setSpacing(3)  # Espacement minimal mais visible (retour proche original)
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
            
            # UNE SEULE ligne horizontale par fichier (format original simplifié)
            file_layout = QHBoxLayout()
            file_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)  # Aligner à gauche et en haut
            file_layout.setContentsMargins(2, 2, 2, 2)  # Marges minimales
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
            
            # Ajouter directement le layout (retour à la méthode originale)
            self.individual_refs_widget.addLayout(file_layout)
        
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
                        if any(cell.strip() for cell in row):
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
        
        # Effectuer l'import
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
            
            # Effectuer l'import avec marquage drag&drop
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
        """Exécuter l'import avec la configuration donnée"""
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
        
        # Suivi global des doublons entre tous les fichiers
        global_seen_device_refs = set()
        
        # Barre de progression
        progress = QProgressDialog(
            "Importation en cours...", 
            "Annuler", 
            0, 
            len(config.files), 
            self.parent_widget
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        for i, file in enumerate(config.files):
            if progress.wasCanceled():
                break
            
            progress.setValue(i)
            progress.setLabelText(f"Import de {file.filename}...")
            QApplication.processEvents()
            
            try:
                file_results = self._import_single_file(file, config, global_seen_device_refs)
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
                    
            except Exception as e:
                results['errors'].append(f"{file.filename}: {str(e)}")
        
        progress.setValue(len(config.files))
        progress.close()
        
        return results
    
    def _import_single_file(self, file: ImportFile, config: ImportConfiguration, global_seen_device_refs: set) -> Dict[str, Any]:
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
        
        # Effectuer l'import des données
        return self._process_data_import(
            data, 
            references_and_labels,  # Maintenant liste de tuples (ref, label)
            config,
            file,  # Passer le fichier pour les associations par fichier
            global_seen_device_refs  # Suivi global des doublons
        )
    
    
    def _process_data_import(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]], 
                           config: ImportConfiguration, file: ImportFile, seen_device_refs: set) -> Dict[str, Any]:
        """Traiter l'import des données avec les références et libellés séparés"""
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
        
        # Utiliser le set global des références déjà vues pour détecter les doublons entre tous les fichiers
        
        for row in data:
            if not row or not any(cell.strip() for cell in row):
                continue
            
            # Compter chaque ligne non vide comme extraite du fichier
            results['total_lines_extracted'] += 1
            
            # Extraire les références principales pour vérification doublon
            ref_modele = str(row[0]).strip() if len(row) >= 1 else ""
            commercial_ref = str(row[1]).strip() if len(row) >= 2 else ""
            
            # Vérifier si c'est un doublon dans le fichier
            device_key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            if device_key in seen_device_refs and (ref_modele or commercial_ref):
                results['duplicates_in_file'] += 1
                print(f"  🔄 Doublon dans le fichier ignoré: {ref_modele} | {commercial_ref}")
                continue  # Les doublons ne sont PAS comptés dans total_imported
            elif ref_modele or commercial_ref:
                seen_device_refs.add(device_key)
            
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
    
    def _parse_row_data(self, row: List[str], config: ImportConfiguration) -> Optional[Dict[str, Any]]:
        """Parser une ligne de données selon la configuration"""
        if not row:
            return None
        
        # Mode basique : détecter automatiquement selon le nombre de colonnes
        data = {}
        
        if len(row) >= 1:
            data['ref_modele'] = str(row[0]).strip()
        
        if len(row) >= 2:
            data['commercial_ref'] = str(row[1]).strip()
        
        if len(row) >= 3:
            # Traiter la 3ème colonne selon le paramètre third_column_choice
            third_col_value = str(row[2]).strip()
            if config.third_column_choice == "other_ref":
                data['other_ref'] = third_col_value
            elif config.third_column_choice == "notes":
                data['notes'] = third_col_value
            # Si choice == "ignore", ne rien faire avec cette colonne
        
        if len(row) >= 4:
            data['type'] = str(row[0]).strip()
            data['manufacturer'] = str(row[1]).strip()
            data['ref_modele'] = str(row[2]).strip()
            data['commercial_ref'] = str(row[3]).strip()
            
        if len(row) >= 5:
            # Pour les fichiers 5+ colonnes, la 5ème colonne pourrait aussi être concernée
            fifth_col_value = str(row[4]).strip()
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