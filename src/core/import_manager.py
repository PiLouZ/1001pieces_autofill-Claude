"""
Gestionnaire d'importation unifié pour l'application de gestion d'appareils
Factorisation du code d'importation avec support des libellés hiérarchiques
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Callable
from enum import Enum
import os
from datetime import datetime

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QCheckBox, 
                             QTextEdit, QGroupBox, QProgressDialog, QApplication)
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
    
    # Options d'import technique
    csv_import_mode: int = 2  # 1, 2, 3+ colonnes
    third_column_choice: str = "ignore"
    has_headers: bool = False
    
    def __post_init__(self):
        if self.label_config is None:
            self.label_config = LabelConfiguration()


class ImportDialog(QDialog):
    """Interface utilisateur pour configurer les imports"""
    
    def __init__(self, parent=None, import_config: ImportConfiguration = None):
        super().__init__(parent)
        self.import_config = import_config or ImportConfiguration(files=[], import_type=ImportType.SINGLE_FILE)
        self.result_config = None
        
        self.setWindowTitle("Configuration d'importation")
        self.setModal(True)
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        
        self._setup_ui()
        self._populate_data()
    
    def _setup_ui(self):
        """Créer l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Section fichiers
        files_group = QGroupBox("Fichiers à importer")
        files_layout = QVBoxLayout()
        
        self.files_info = QLabel()
        files_layout.addWidget(self.files_info)
        
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)
        
        # Section référence commune (pour multi-fichiers)
        if self.import_config.import_type == ImportType.MULTI_FILE:
            ref_group = QGroupBox("Référence commune (optionnelle)")
            ref_layout = QVBoxLayout()
            
            self.use_common_ref_cb = QCheckBox("Associer une référence commune à tous les fichiers")
            ref_layout.addWidget(self.use_common_ref_cb)
            
            self.common_ref_input = QLineEdit()
            self.common_ref_input.setPlaceholderText("Référence commune (ex: LOT_2024_001)")
            self.common_ref_input.setEnabled(False)
            ref_layout.addWidget(self.common_ref_input)
            
            self.use_common_ref_cb.toggled.connect(self.common_ref_input.setEnabled)
            
            ref_group.setLayout(ref_layout)
            layout.addWidget(ref_group)
        
        # Section libellés
        labels_group = QGroupBox("Gestion des libellés")
        labels_layout = QVBoxLayout()
        
        self.use_common_label_cb = QCheckBox("Utiliser un libellé commun pour toutes les pièces")
        labels_layout.addWidget(self.use_common_label_cb)
        
        self.common_label_input = QLineEdit()
        self.common_label_input.setPlaceholderText("Libellé commun (ex: Pièces détachées lave-vaisselle)")
        self.common_label_input.setEnabled(False)
        labels_layout.addWidget(self.common_label_input)
        
        self.use_common_label_cb.toggled.connect(self.common_label_input.setEnabled)
        
        # Liste des libellés individuels
        individual_label = QLabel("Libellés individuels par fichier:")
        individual_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        labels_layout.addWidget(individual_label)
        
        self.individual_labels_widget = QVBoxLayout()
        labels_layout.addLayout(self.individual_labels_widget)
        
        labels_group.setLayout(labels_layout)
        layout.addWidget(labels_group)
        
        # Section aperçu des données (si disponible)
        if any(f.data for f in self.import_config.files):
            preview_group = QGroupBox("Aperçu des données")
            preview_layout = QVBoxLayout()
            
            self.preview_text = QTextEdit()
            self.preview_text.setMaximumHeight(150)
            self.preview_text.setReadOnly(True)
            preview_layout.addWidget(self.preview_text)
            
            preview_group.setLayout(preview_layout)
            layout.addWidget(preview_group)
        
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
        # Info fichiers
        if len(self.import_config.files) == 1:
            file = self.import_config.files[0]
            self.files_info.setText(f"📄 Fichier: {file.filename}")
        else:
            files_text = f"📁 {len(self.import_config.files)} fichiers:\n"
            for file in self.import_config.files:
                files_text += f"  • {file.filename}\n"
            self.files_info.setText(files_text)
        
        # Libellés individuels
        for file in self.import_config.files:
            file_layout = QHBoxLayout()
            
            file_label = QLabel(f"📄 {file.filename}:")
            file_layout.addWidget(file_label)
            
            label_input = QLineEdit()
            label_input.setPlaceholderText(file.suggested_label or file.suggested_reference)
            label_input.setText(file.suggested_label or file.suggested_reference)
            label_input.setObjectName(f"label_{file.path}")
            file_layout.addWidget(label_input)
            
            self.individual_labels_widget.addLayout(file_layout)
        
        # Aperçu des données
        if hasattr(self, 'preview_text'):
            preview_lines = []
            for file in self.import_config.files[:2]:  # Max 2 fichiers dans l'aperçu
                if file.data:
                    preview_lines.append(f"=== {file.filename} ===")
                    for i, row in enumerate(file.data[:3]):  # Max 3 lignes par fichier
                        preview_lines.append(" | ".join(str(cell)[:30] for cell in row))
                        if i >= 2:
                            break
                    if len(file.data) > 3:
                        preview_lines.append(f"... et {len(file.data) - 3} autres lignes")
                    preview_lines.append("")
            
            self.preview_text.setPlainText("\n".join(preview_lines))
    
    def _validate_and_accept(self):
        """Valider la configuration et accepter"""
        config = ImportConfiguration(
            files=self.import_config.files,
            import_type=self.import_config.import_type
        )
        
        # Référence commune
        if self.import_config.import_type == ImportType.MULTI_FILE:
            config.use_common_reference = self.use_common_ref_cb.isChecked()
            config.common_reference = self.common_ref_input.text().strip() if config.use_common_reference else None
        
        # Configuration des libellés
        config.label_config = LabelConfiguration()
        config.label_config.use_common_label = self.use_common_label_cb.isChecked()
        config.label_config.common_label = self.common_label_input.text().strip() if config.label_config.use_common_label else ""
        
        # Libellés individuels
        for file in config.files:
            label_input = self.findChild(QLineEdit, f"label_{file.path}")
            if label_input:
                config.label_config.individual_labels[file.path] = label_input.text().strip()
        
        self.result_config = config
        self.accept()
    
    def get_configuration(self) -> Optional[ImportConfiguration]:
        """Récupérer la configuration résultat"""
        return self.result_config


class ImportManager:
    """Gestionnaire unifié pour tous les types d'imports"""
    
    def __init__(self, db_manager, parent_widget=None):
        self.db_manager = db_manager
        self.parent_widget = parent_widget
    
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
                import csv
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    reader = csv.reader(f)
                    return [row for i, row in enumerate(reader) if i < 5]
            elif file_type == FileType.PDF:
                # Utiliser l'extracteur PDF si disponible
                try:
                    from src.data.pdf_extractor_camelot import CamelotPDFExtractor
                    extractor = CamelotPDFExtractor()
                    data = extractor.extract_data(file_path)
                    return data[:5] if data else []
                except ImportError:
                    return []
        except Exception:
            return []
        
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
            'errors': []
        }
        
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
                file_results = self._import_single_file(file, config)
                results['successful_files'] += 1
                
                # Agréger les résultats
                for key in ['total_imported', 'matches_found', 'new_entries', 'associations_created']:
                    results[key] += file_results.get(key, 0)
                    
            except Exception as e:
                results['errors'].append(f"{file.filename}: {str(e)}")
        
        progress.setValue(len(config.files))
        progress.close()
        
        return results
    
    def _import_single_file(self, file: ImportFile, config: ImportConfiguration) -> Dict[str, Any]:
        """Importer un fichier unique"""
        # Charger les données du fichier
        if file.type == FileType.CSV:
            data = self._load_csv_data(file.path)
        elif file.type == FileType.PDF:
            data = self._load_pdf_data(file.path)
        else:
            raise ValueError(f"Type de fichier non supporté: {file.type}")
        
        if not data:
            raise ValueError("Aucune donnée trouvée dans le fichier")
        
        # Déterminer les références à associer
        references_to_associate = []
        
        # Référence commune
        if config.use_common_reference and config.common_reference:
            references_to_associate.append(config.common_reference)
        
        # Référence individuelle du fichier
        individual_ref = config.label_config.individual_labels.get(file.path, file.suggested_reference)
        if individual_ref:
            references_to_associate.append(individual_ref)
        
        # Déterminer le libellé à utiliser
        if config.label_config.use_common_label and config.label_config.common_label:
            piece_label = config.label_config.common_label
        else:
            piece_label = config.label_config.individual_labels.get(file.path, file.suggested_label)
        
        # Effectuer l'import des données
        return self._process_data_import(
            data, 
            references_to_associate, 
            piece_label,
            config
        )
    
    def _load_csv_data(self, file_path: str) -> List[List[str]]:
        """Charger les données d'un fichier CSV"""
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
                    return [row for row in reader if any(cell.strip() for cell in row)]
                    
            except UnicodeDecodeError:
                continue
        
        raise ValueError(f"Impossible de lire le fichier CSV: {file_path}")
    
    def _load_pdf_data(self, file_path: str) -> List[List[str]]:
        """Charger les données d'un fichier PDF"""
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor
            extractor = CamelotPDFExtractor()
            return extractor.extract_data(file_path)
        except ImportError as e:
            raise ValueError(f"Extracteur PDF non disponible: {e}")
    
    def _process_data_import(self, data: List[List[str]], references: List[str], 
                           label: Optional[str], config: ImportConfiguration) -> Dict[str, Any]:
        """Traiter l'import des données avec les références multiples"""
        results = {
            'total_imported': 0,
            'matches_found': 0,
            'new_entries': 0,
            'associations_created': 0
        }
        
        for row in data:
            if not row or not any(cell.strip() for cell in row):
                continue
            
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
                else:
                    results['matches_found'] += 1
                
                # Associer toutes les références
                for reference in references:
                    if reference:
                        try:
                            assoc_id = self.db_manager.add_or_update_piece_with_description(
                                reference, device_id, label
                            )
                            if assoc_id:
                                results['associations_created'] += 1
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
            data['other_ref'] = str(row[2]).strip()
        
        if len(row) >= 4:
            data['type'] = str(row[0]).strip()
            data['manufacturer'] = str(row[1]).strip()
            data['ref_modele'] = str(row[2]).strip()
            data['commercial_ref'] = str(row[3]).strip()
            
        if len(row) >= 5:
            data['other_ref'] = str(row[4]).strip()
        
        # Vérifier qu'on a au moins une donnée utile
        if not any(v for v in data.values() if v):
            return None
        
        return data
    
    def _insert_or_find_device(self, device_data: Dict[str, Any]) -> Optional[int]:
        """Insérer ou trouver un appareil existant"""
        try:
            # Chercher d'abord un appareil existant
            ref_modele = device_data.get('ref_modele', '')
            commercial_ref = device_data.get('commercial_ref', '')
            
            if ref_modele or commercial_ref:
                # Recherche simple basée sur les références
                search_query = """
                    SELECT id FROM appareils 
                    WHERE (ref_modele = ? AND ref_modele != '') 
                       OR (commercial_ref = ? AND commercial_ref != '')
                    LIMIT 1
                """
                results = self.db_manager.execute_query(search_query, [ref_modele, commercial_ref])
                
                if results:
                    return results[0][0]
            
            # Créer un nouvel appareil
            device_id = self.db_manager.insert_appareil(device_data)
            if device_id:
                device_data['is_new'] = True
            return device_id
            
        except Exception as e:
            print(f"Erreur insertion appareil: {e}")
            return None


# Fonctions utilitaires pour l'intégration
def create_import_manager(db_manager, parent_widget=None) -> ImportManager:
    """Créer une instance du gestionnaire d'import"""
    return ImportManager(db_manager, parent_widget)


def import_files_with_dialog(file_paths: List[str], db_manager, parent_widget=None) -> Optional[Dict[str, Any]]:
    """Fonction utilitaire pour importer des fichiers avec interface"""
    manager = create_import_manager(db_manager, parent_widget)
    return manager.import_files(file_paths, show_dialog=True)