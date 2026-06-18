"""
Gestionnaire d'importation unifié pour l'application de gestion d'appareils
Factorisation du code d'importation avec support des libellés hiérarchiques
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Callable
from enum import Enum
import os
import time as _time
import unicodedata
import warnings
from datetime import datetime

from ..ui.qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QComboBox, QCheckBox,
                             QTextEdit, QGroupBox, QApplication,
                             QScrollArea, QWidget, QGridLayout, Qt, QTimer, QThread,
                             QCompleter, QStringListModel, QRadioButton, QButtonGroup,
                             QSizePolicy, QSize, pyqtSignal)

from .logger import app_logger
from ..utils.error_handler import handle_ui_operation_errors, handle_database_operation_errors



class ImportType(Enum):
    """Types d'import supportés"""
    SINGLE_FILE = "single_file"
    MULTI_FILE = "multi_file"
    

class FileType(Enum):
    """Types de fichiers supportés"""
    CSV = "csv"
    PDF = "pdf"
    CLIPBOARD = "clipboard"  # Données issues du presse-papiers (v3.31.0)


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

    # Aperçu (dry-run) avant import définitif — désactivé par défaut (trop lent)
    show_preview: bool = False

    # Succession déclarée lors de l'import (optionnel)
    succession_replaces: Optional[str] = None       # Réf existante que cette réf remplace (ref_old=existing, ref_new=imported)
    succession_replaced_by: Optional[str] = None    # Réf existante qui remplace cette réf (ref_old=imported, ref_new=existing)
    succession_current_ref: Optional[str] = None    # Multi-fichiers : réf désignée comme courante (les autres lui sont successées)

    # Équivalences déclarées lors de l'import (multi-fichiers)
    equivalence_refs: Optional[List[str]] = None    # Réfs cochées comme équivalentes à la courante (ou entre elles si pas de courante)

    # Références à marquer obsolètes lors de l'import
    obsolete_refs: Optional[List[str]] = None       # Réfs à marquer comme obsolètes après import

    # Mapping personnalisé des colonnes (v3.30.0)
    # None = comportement positionnel actuel (défaut, zéro régression)
    # Clé   : nombre de colonnes du groupe de fichiers
    # Valeur : liste de N destinations (une par colonne détectée)
    # Exemple : {3: ["commercial_ref", "ref_modele", "ignore"]}
    column_mapping: Optional[Dict[int, List[str]]] = None

    def __post_init__(self):
        if self.label_config is None:
            self.label_config = LabelConfiguration()
        if self.individual_references is None:
            self.individual_references = {}
        if self.individual_labels is None:
            self.individual_labels = {}
        if self.equivalence_refs is None:
            self.equivalence_refs = []
        if self.obsolete_refs is None:
            self.obsolete_refs = []


# ── MappingGroupWidget (v3.30.0) ─────────────────────────────────────────────

class MappingGroupWidget(QWidget):
    """
    Widget de mapping pour un groupe de fichiers de même structure.
    - Format reconnu  : toggle discret replié, combos pré-remplies selon format détecté
    - Format non reconnu : toujours déplié, obligatoire avant import
    """

    mapping_changed = pyqtSignal()

    FIELD_CHOICES = [
        ("— Ignorer —",      "ignore"),
        ("Réf. Modèle",      "ref_modele"),
        ("Réf. Commerciale", "commercial_ref"),
        ("Type d'appareil",  "type"),
        ("Fabricant",        "manufacturer"),
        ("Autre Référence",  "other_ref"),
        ("Notes",            "notes"),
    ]

    def __init__(self, n_cols: int, files: list, sample_data: list,
                 is_recognized: bool, default_mapping: list,
                 headers_detected: bool = False, parent=None):
        super().__init__(parent)
        self._n_cols = n_cols
        self._is_recognized = is_recognized
        self._headers_detected = headers_detected
        self._is_modified = False   # True dès que l'utilisateur modifie une combo
        self._combos = []
        self._toggle_btn = None
        self._status_label = None
        self._expanded = not is_recognized  # non-reconnu = toujours déplié
        self._build_ui(n_cols, files, sample_data, is_recognized, default_mapping)

    # ── Construction UI ──────────────────────────────────────────────────────

    def _build_ui(self, n_cols, files, sample_data, is_recognized, default_mapping):
        import os
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 1, 0, 1)
        outer.setSpacing(2)

        file_names = self._format_file_names(files)
        col_label = f"{n_cols} colonne{'s' if n_cols > 1 else ''}"

        if is_recognized:
            self._toggle_btn = QPushButton(
                f"▶  Adapter le mapping  —  {file_names}  ({col_label})"
            )
            self._toggle_btn.setFlat(True)
            self._toggle_btn.setCursor(Qt.PointingHandCursor)
            self._toggle_btn.setStyleSheet(
                "QPushButton { color: #0066cc; font-size: 11px; text-align: left;"
                " padding: 2px 4px; border: none; background: transparent; }"
                "QPushButton:hover { color: #004499; text-decoration: underline; }"
            )
            self._toggle_btn.clicked.connect(self._toggle)
            outer.addWidget(self._toggle_btn)
        else:
            # ── Bandeau d'avertissement proéminent ───────────────────────────
            banner = QWidget()
            banner.setStyleSheet(
                "QWidget { background: #fff3cd; border: 1px solid #ffc107;"
                " border-radius: 4px; }"
            )
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(8, 6, 8, 6)
            banner_layout.setSpacing(6)

            title_col = QVBoxLayout()
            title_col.setSpacing(1)

            warn_lbl = QLabel(f"Vérifiez le mapping des colonnes — {file_names}  ({col_label})")
            warn_lbl.setStyleSheet(
                "color: #856404; font-weight: bold; font-size: 11px;"
                " background: transparent; border: none;"
            )
            title_col.addWidget(warn_lbl)

            if self._headers_detected:
                hint_lbl = QLabel("Entêtes détectées automatiquement — confirmez la correspondance avant d'importer")
            else:
                hint_lbl = QLabel("Format non standard — assignez au moins la colonne Réf. Modèle")
            hint_lbl.setStyleSheet(
                "color: #856404; font-size: 10px; background: transparent; border: none;"
            )
            title_col.addWidget(hint_lbl)

            banner_layout.addLayout(title_col, 1)
            outer.addWidget(banner)

            # Label de statut dynamique (rouge/orange selon état du mapping)
            self._status_label = QLabel()
            self._status_label.setStyleSheet(
                "color: #dc3545; font-size: 10px; padding: 1px 0;"
            )
            outer.addWidget(self._status_label)

        # Tableau de mapping
        self._mapping_widget = QWidget()
        self._mapping_widget.setStyleSheet(
            "QWidget { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }"
        )
        grid = QGridLayout(self._mapping_widget)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)

        for i in range(n_cols):
            lbl = QLabel(f"Colonne {i + 1}")
            lbl.setStyleSheet(
                "font-weight: bold; font-size: 11px; background: transparent; border: none;"
            )
            grid.addWidget(lbl, i, 0)

            examples = []
            for row in sample_data[:2]:
                if i < len(row):
                    val = str(row[i])[:18].strip()
                    if val:
                        examples.append(f'"{val}"')
            ex_lbl = QLabel("  /  ".join(examples) if examples else "—")
            ex_lbl.setStyleSheet(
                "color: #6c757d; font-family: monospace; font-size: 10px;"
                " background: transparent; border: none;"
            )
            ex_lbl.setMinimumWidth(0)
            ex_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            grid.addWidget(ex_lbl, i, 1)

            combo = QComboBox()
            combo.setMinimumHeight(28)
            for label, value in self.FIELD_CHOICES:
                combo.addItem(label, value)
            target = default_mapping[i] if i < len(default_mapping) else "ignore"
            for idx, (_, val) in enumerate(self.FIELD_CHOICES):
                if val == target:
                    combo.setCurrentIndex(idx)
                    break
            combo.currentIndexChanged.connect(self._on_combo_changed)
            self._combos.append(combo)
            grid.addWidget(combo, i, 2)

        outer.addWidget(self._mapping_widget)
        self._mapping_widget.setVisible(self._expanded)

        # Mettre à jour le statut APRÈS que les combos soient construits
        self._update_status()

    # ── Comportement ─────────────────────────────────────────────────────────

    def _toggle(self):
        self._expanded = not self._expanded
        self._mapping_widget.setVisible(self._expanded)
        arrow = "▼" if self._expanded else "▶"
        text = self._toggle_btn.text()
        self._toggle_btn.setText(arrow + text[1:])

    def _on_combo_changed(self):
        self._is_modified = True
        self._update_status()
        self.mapping_changed.emit()

    def _update_status(self):
        """Met à jour le label de statut dynamique pour les groupes non reconnus."""
        if not self._is_recognized and self._status_label:
            if self.has_ref_modele():
                self._status_label.setText("Réf. Modèle assignée — mapping prêt")
                self._status_label.setStyleSheet(
                    "color: #28a745; font-size: 10px; padding: 1px 0;"
                )
            else:
                self._status_label.setText("Réf. Modèle non assignée — import bloqué")
                self._status_label.setStyleSheet(
                    "color: #dc3545; font-size: 10px; padding: 1px 0;"
                )

    # ── API publique ─────────────────────────────────────────────────────────

    def get_mapping(self) -> list:
        """Retourne la liste des destinations (une par colonne détectée)."""
        return [combo.currentData() for combo in self._combos]

    def has_ref_modele(self) -> bool:
        return "ref_modele" in self.get_mapping()

    def is_mandatory_and_incomplete(self) -> bool:
        """True si le groupe est non reconnu ET sans ref_modele → bloque l'import."""
        return not self._is_recognized and not self.has_ref_modele()

    @staticmethod
    def _format_file_names(files: list) -> str:
        import os
        names = [os.path.basename(f.path) for f in files[:3]]
        result = ", ".join(names)
        if len(files) > 3:
            result += f" +{len(files) - 3}"
        return result


# ─────────────────────────────────────────────────────────────────────────────

class ImportDialog(QDialog):
    """Interface utilisateur pour configurer les imports"""
    
    def __init__(self, parent=None, import_config: ImportConfiguration = None, import_manager=None):
        super().__init__(parent)
        self.import_config = import_config or ImportConfiguration(files=[], import_type=ImportType.SINGLE_FILE)
        self.result_config = None
        self.import_manager = import_manager  # PHASE 2.1: Référence à ImportManager pour chargement lazy

        is_clipboard = any(f.type == FileType.CLIPBOARD for f in self.import_config.files)
        self.setWindowTitle("Importer depuis le presse-papiers" if is_clipboard else "Configuration d'importation")
        self.setModal(True)
        self.setMinimumWidth(1000)
        self.setMinimumHeight(1000)

        # PHASE 2.1: Flag pour indiquer si les données sont chargées
        self._data_loaded = False

        self._setup_ui()

        # PHASE 2.1 OPTIMISATION: Lazy loading - charger les données APRÈS l'affichage
        # Afficher un message temporaire pendant le chargement
        self._show_loading_message()

        # Lancer le chargement différé (50ms après l'affichage du dialogue)
        QTimer.singleShot(50, self._load_data_deferred)

    def _show_loading_message(self):
        """Afficher un message temporaire pendant le chargement des données"""
        # Cette méthode sera appelée AVANT que les données ne soient chargées
        # Elle initialise l'interface avec des placeholders
        pass  # L'interface affichera les placeholders par défaut

    def _load_data_deferred(self):
        """
        Charger les données en différé (appelé via QTimer après affichage)

        PHASE 2.1 OPTIMISATION: Cette méthode s'exécute APRÈS que le dialogue
        soit affiché, éliminant le freeze initial.
        """
        if not self.import_manager:
            app_logger.warning("ImportManager non disponible pour chargement lazy")
            self._populate_data()
            return

        # Charger les données pour chaque fichier si nécessaire
        for file in self.import_config.files:
            if file.data is None:
                # Charger les données avec cache et preview mode (Phase 1.1 + 1.2)
                file_type = file.type
                if file_type == FileType.CSV:
                    file.data = self.import_manager.load_csv_data(file.path, max_rows=5)
                elif file_type == FileType.PDF:
                    # Utiliser le mode preview de Phase 1.1
                    file.data = self.import_manager.load_pdf_data(file.path, max_rows=5, preview_mode=True)

        # Marquer les données comme chargées
        self._data_loaded = True

        # Maintenant, peupler l'interface avec les vraies données
        self._populate_data()

    def _setup_ui(self):
        """Créer l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Section format reconnu et aperçu des données
        format_group = QGroupBox("Format reconnu et aperçu")
        format_layout = QVBoxLayout()
        format_layout.setSpacing(4)
        
        self.format_info_label = QLabel()
        self.format_info_label.setStyleSheet("font-weight: bold;")
        format_layout.addWidget(self.format_info_label)
        
        self.format_desc_label = QLabel()
        self.format_desc_label.setStyleSheet("color: #6c757d; margin-left: 20px;")
        format_layout.addWidget(self.format_desc_label)

        # Bandeau d'alerte format non reconnu (masqué par défaut)
        self.format_warning_widget = QWidget()
        self.format_warning_widget.setStyleSheet(
            "QWidget { background-color: #dc3545; border-radius: 6px; padding: 4px; }"
        )
        warning_layout = QVBoxLayout(self.format_warning_widget)
        warning_layout.setContentsMargins(14, 10, 14, 10)
        warning_layout.setSpacing(4)

        warning_title = QLabel("Format non reconnu")
        warning_title.setStyleSheet(
            "color: white; font-weight: bold; font-size: 14px;"
            "background: transparent;"
        )
        warning_layout.addWidget(warning_title)

        warning_sub = QLabel("Ce fichier ne peut pas être importé.\nVérifiez qu'il s'agit d'un CSV ou PDF compatible.")
        warning_sub.setStyleSheet(
            "color: #ffe0e0; font-size: 11px; background: transparent;"
        )
        warning_layout.addWidget(warning_sub)

        self.format_warning_widget.setVisible(False)
        format_layout.addWidget(self.format_warning_widget)

        # Aperçu des données (hauteur auto-ajustée selon contenu — voir _set_preview_text)
        self.preview_text = QTextEdit()
        self.preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; font-family: 'Monaco', 'Menlo', 'Courier New', monospace; font-size: 11px;")
        self.preview_text.setReadOnly(True)
        self.preview_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        format_layout.addWidget(self.preview_text)

        # Options techniques sous l'aperçu
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(10, 4, 10, 2)
        
        # Gestion de la 3ème colonne si applicable
        self.third_col_widget = QWidget()
        self.third_col_widget.setStyleSheet("background-color: #fff; border: 1px solid #e9ecef; border-radius: 4px;")
        third_col_layout = QHBoxLayout(self.third_col_widget)
        third_col_layout.setContentsMargins(10, 3, 10, 3)
        
        self.third_col_label = QLabel("Destination 3ème colonne:")
        self.third_col_label.setStyleSheet("font-weight: bold;")
        third_col_layout.addWidget(self.third_col_label)
        
        self.third_col_combo = QComboBox()
        self.third_col_combo.addItems(["Ignorer", "Autre référence", "Notes"])
        self.third_col_combo.setCurrentIndex(1)  # "Autre référence" présélectionné (choix le plus fréquent)
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

        # Conteneur de mapping de colonnes (v3.30.0 — sous l'aperçu et les options)
        self.mapping_container = QWidget()
        self.mapping_container_layout = QVBoxLayout(self.mapping_container)
        self.mapping_container_layout.setContentsMargins(0, 2, 0, 0)
        self.mapping_container_layout.setSpacing(4)
        self.mapping_container.setVisible(False)
        format_layout.addWidget(self.mapping_container)

        format_group.setLayout(format_layout)
        format_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(format_group)
        
        # Section référence commune (pour multi-fichiers)
        if self.import_config.import_type == ImportType.MULTI_FILE:
            ref_group = QGroupBox("Référence commune optionnelle")
            ref_layout = QVBoxLayout()
            ref_layout.setSpacing(6)

            # Ligne 1 : Référence (largeur fixe) + icône info
            row_ref = QHBoxLayout()
            row_ref.setSpacing(6)
            ref_lbl = QLabel("Référence:")
            ref_lbl.setStyleSheet("font-weight: bold;")
            ref_lbl.setFixedWidth(90)
            row_ref.addWidget(ref_lbl)
            self.common_ref_input = QLineEdit()
            self.common_ref_input.setPlaceholderText("GAUxxxxxx")
            self.common_ref_input.setFixedWidth(170)  # ~20 caractères
            row_ref.addWidget(self.common_ref_input)
            try:
                import qtawesome as qta
                info_btn = QPushButton()
                info_btn.setIcon(qta.icon('fa5s.info-circle', color='#0066cc'))
                info_btn.setIconSize(QSize(13, 13))
                info_btn.setFixedSize(20, 20)
                info_btn.setFlat(True)
                info_btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
                info_btn.setToolTip(
                    "La référence commune sera associée à TOUS les appareils importés.\n"
                    "Elle sera créée et enregistrée dans la base de données\n"
                    "comme toute autre référence de pièce."
                )
                row_ref.addWidget(info_btn)
            except Exception:
                pass
            row_ref.addStretch()
            ref_layout.addLayout(row_ref)

            # Ligne 2 : Description + checkbox
            row_desc = QHBoxLayout()
            row_desc.setSpacing(8)
            desc_lbl2 = QLabel("Description:")
            desc_lbl2.setStyleSheet("font-weight: bold;")
            desc_lbl2.setFixedWidth(90)
            row_desc.addWidget(desc_lbl2)
            self.common_ref_description = QLineEdit()
            self.common_ref_description.setPlaceholderText("Ex : Lot pièces lave-vaisselle mars 2024")
            self.common_ref_description.textChanged.connect(self._on_common_description_changed)
            row_desc.addWidget(self.common_ref_description)
            ref_layout.addLayout(row_desc)

            # Ligne 3 : cases "tout appliquer" sur une seule ligne
            row_apply_all = QHBoxLayout()
            row_apply_all.setSpacing(16)
            row_apply_all.addSpacing(90)  # aligne avec l'input description
            self.apply_to_individual_checkbox = QCheckBox("Appliquer libellé")
            self.apply_to_individual_checkbox.setChecked(True)
            self.apply_to_individual_checkbox.setStyleSheet("font-size: 11px;")
            self.apply_to_individual_checkbox.setToolTip(
                "Duplique automatiquement cette description dans tous les champs libellé individuels"
            )
            self.apply_to_individual_checkbox.stateChanged.connect(self._on_apply_to_individual_changed)
            row_apply_all.addWidget(self.apply_to_individual_checkbox)

            self._apply_all_equiv_checkbox = QCheckBox("Toutes équivalentes")
            self._apply_all_equiv_checkbox.setStyleSheet("font-size: 11px; color: #6c757d;")
            self._apply_all_equiv_checkbox.setToolTip(
                "Cocher toutes les références importées comme équivalentes entre elles"
            )
            self._apply_all_equiv_checkbox.stateChanged.connect(self._on_apply_all_equiv_changed)
            row_apply_all.addWidget(self._apply_all_equiv_checkbox)

            self._apply_all_obs_checkbox = QCheckBox("Toutes obsolètes")
            self._apply_all_obs_checkbox.setStyleSheet("font-size: 11px; color: #c0392b;")
            self._apply_all_obs_checkbox.setToolTip(
                "Cocher toutes les références importées comme obsolètes"
            )
            self._apply_all_obs_checkbox.stateChanged.connect(self._on_apply_all_obs_changed)
            row_apply_all.addWidget(self._apply_all_obs_checkbox)
            row_apply_all.addStretch()
            ref_layout.addLayout(row_apply_all)

            ref_group.setLayout(ref_layout)
            layout.addWidget(ref_group)
        
        self.individual_desc_fields = []

        if len(self.import_config.files) == 1:
            # ── Section "Référence de pièce" compacte (fichier unique) ──────────
            file = self.import_config.files[0]
            ref_group = QGroupBox("Référence de pièce")
            ref_group_layout = QVBoxLayout()
            ref_group_layout.setSpacing(8)

            # Ligne : Réf.
            ref_row = QHBoxLayout()
            ref_row_lbl = QLabel("Réf.:")
            ref_row_lbl.setStyleSheet("font-weight: bold;")
            ref_row_lbl.setFixedWidth(70)
            ref_row.addWidget(ref_row_lbl)
            if file.type == FileType.CLIPBOARD:
                ref_input_edit = QLineEdit()
                ref_input_edit.setPlaceholderText("Référence pièce (ex: AS6015830)")
                ref_input_edit.setObjectName(f"ref_input_{file.path}")
                ref_input_edit.setStyleSheet("padding: 5px; border: 2px solid #0066cc; border-radius: 4px;")
                ref_row.addWidget(ref_input_edit)
            else:
                ref_display = QLabel(f"→ Réf: {file.suggested_reference or '—'}")
                ref_display.setStyleSheet(
                    "color: #0066cc; background-color: #f0f8ff; padding: 4px 8px;"
                    " border: 1px solid #ddd; border-radius: 4px; font-weight: bold;"
                )
                ref_display.setObjectName(f"ref_display_{file.path}")
                ref_row.addWidget(ref_display)
            ref_group_layout.addLayout(ref_row)

            # Ligne : Libellé
            desc_row = QHBoxLayout()
            desc_row_lbl = QLabel("Libellé:")
            desc_row_lbl.setStyleSheet("font-weight: bold;")
            desc_row_lbl.setFixedWidth(70)
            desc_row.addWidget(desc_row_lbl)
            desc_input = QLineEdit()
            desc_input.setPlaceholderText("Description optionnelle")
            desc_input.setObjectName(f"desc_{file.path}")
            desc_row.addWidget(desc_input)
            ref_group_layout.addLayout(desc_row)
            self.individual_desc_fields.append(desc_input)

            # Checkbox obsolète — toujours visible dans la section principale
            self._obsolete_checkbox = QCheckBox("Marquer comme obsolète (pièce plus fabriquée)")
            self._obsolete_checkbox.setToolTip(
                "Cochez si cette pièce est obsolète (plus fabriquée).\n"
                "Elle restera visible mais sera marquée Obsolète."
            )
            self._obsolete_checkbox.setStyleSheet("color: #c0392b; font-size: 11px;")
            ref_group_layout.addWidget(self._obsolete_checkbox)

            ref_group.setLayout(ref_group_layout)
            layout.addWidget(ref_group)

            # Checkbox masquée toujours cochée — pour compatibilité _validate_and_accept
            self.auto_file_references_checkbox = QCheckBox()
            self.auto_file_references_checkbox.setChecked(True)
            self.auto_file_references_checkbox.setVisible(False)
            layout.addWidget(self.auto_file_references_checkbox)

            # ── Section succession repliable (liens entre réfs uniquement) ──────
            self.succ_replaces_input = None
            self.succ_replaced_by_input = None
            self._succ_button_group = None
            self._succ_radio_files = []
            self._equiv_checkboxes = []
            self._obsolete_checkboxes = []

            succ_container = QWidget()
            succ_container_layout = QVBoxLayout(succ_container)
            succ_container_layout.setContentsMargins(0, 0, 0, 0)
            succ_container_layout.setSpacing(4)

            self._succ_toggle_btn = QPushButton("▼  Succession (optionnel)")
            self._succ_toggle_btn.setFlat(True)
            self._succ_toggle_btn.setCursor(Qt.PointingHandCursor)
            self._succ_toggle_btn.setStyleSheet(
                "QPushButton { color: #0066cc; font-size: 11px; text-align: left;"
                " padding: 4px 6px; border: none; background: transparent; }"
                "QPushButton:hover { color: #004499; text-decoration: underline; }"
            )
            self._succ_toggle_btn.clicked.connect(self._toggle_succ)
            succ_container_layout.addWidget(self._succ_toggle_btn)

            self._succ_content = QWidget()
            self._succ_content.setStyleSheet(
                "QWidget { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }"
            )
            succ_layout = QVBoxLayout(self._succ_content)
            succ_layout.setContentsMargins(12, 8, 12, 8)
            succ_layout.setSpacing(6)

            succ_info = QLabel("Déclarez ici si cette référence est liée à une succession de pièces déjà en base.")
            succ_info.setStyleSheet(
                "color: #666; font-style: italic; padding: 4px; background: transparent; border: none;"
            )
            succ_info.setWordWrap(True)
            succ_layout.addWidget(succ_info)

            row1 = QHBoxLayout()
            lbl1 = QLabel("Cette réf. remplace :")
            lbl1.setStyleSheet("font-weight: bold; background: transparent; border: none;")
            lbl1.setFixedWidth(220)
            row1.addWidget(lbl1)
            self.succ_replaces_input = QLineEdit()
            self.succ_replaces_input.setPlaceholderText("Ancienne réf. remplacée par cette réf. (ex : REF123)")
            self.succ_replaces_input.setMinimumHeight(30)
            self.succ_replaces_input.setStyleSheet("background: white; border: 1px solid #ced4da; border-radius: 4px; padding: 4px 6px;")
            row1.addWidget(self.succ_replaces_input)
            succ_layout.addLayout(row1)

            row2 = QHBoxLayout()
            lbl2 = QLabel("Cette réf. est remplacée par :")
            lbl2.setStyleSheet("font-weight: bold; background: transparent; border: none;")
            lbl2.setFixedWidth(220)
            row2.addWidget(lbl2)
            self.succ_replaced_by_input = QLineEdit()
            self.succ_replaced_by_input.setPlaceholderText("Nouvelle réf. qui remplace cette réf. (ex : REF456)")
            self.succ_replaced_by_input.setMinimumHeight(30)
            self.succ_replaced_by_input.setStyleSheet("background: white; border: 1px solid #ced4da; border-radius: 4px; padding: 4px 6px;")
            row2.addWidget(self.succ_replaced_by_input)
            succ_layout.addLayout(row2)

            self._succ_content.setVisible(True)
            succ_container_layout.addWidget(self._succ_content)
            layout.addWidget(succ_container)
            layout.addStretch(1)  # absorbe l'espace restant → format_group reste à hauteur naturelle

        else:
            # ── Mode multi-fichiers — scroll area références individuelles ───────
            self.succ_replaces_input = None
            self.succ_replaced_by_input = None
            self._succ_button_group = None
            self._succ_radio_files = []
            self._equiv_checkboxes = []
            self._obsolete_checkbox = None
            self._obsolete_checkboxes = []

            individual_group = QGroupBox("Références individuelles par fichier")
            individual_layout = QVBoxLayout()

            info_and_option_layout = QVBoxLayout()
            info_and_option_layout.setContentsMargins(0, 0, 0, 0)
            info_and_option_layout.setSpacing(8)

            individual_info = QLabel("Génération automatique des références de pièces basées sur les noms de fichiers")
            individual_info.setStyleSheet("color: #666; font-style: italic; padding: 8px; background-color: #f0f8ff; border-radius: 4px;")
            individual_info.setWordWrap(True)
            info_and_option_layout.addWidget(individual_info)

            self.auto_file_references_checkbox = QCheckBox("Associer automatiquement les noms de fichiers comme références de pièces")
            self.auto_file_references_checkbox.setToolTip(
                "Si coché, chaque fichier génère automatiquement une référence de pièce basée sur son nom.\n"
                "Si décoché, seuls les données contenues dans les fichiers sont importées."
            )
            self.auto_file_references_checkbox.setStyleSheet("font-weight: bold; color: #333; margin-left: 10px;")

            has_pdf = any(f.type == FileType.PDF for f in self.import_config.files)
            has_csv = any(f.type == FileType.CSV for f in self.import_config.files)

            if has_pdf and not has_csv:
                self.auto_file_references_checkbox.setChecked(True)
            elif has_csv and not has_pdf:
                self.auto_file_references_checkbox.setChecked(False)
            else:
                self.auto_file_references_checkbox.setChecked(True)

            self.auto_file_references_checkbox.stateChanged.connect(self._on_auto_references_changed)
            info_and_option_layout.addWidget(self.auto_file_references_checkbox)

            individual_layout.addLayout(info_and_option_layout)

            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            scroll_area.setMinimumHeight(80)
            scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            scroll_widget = QWidget()
            scroll_widget.setObjectName("scroll_content")

            self.individual_refs_widget = QVBoxLayout(scroll_widget)
            self.individual_refs_widget.setContentsMargins(10, 10, 10, 10)
            self.individual_refs_widget.setSpacing(6)  # espacement entre cartes
            self.individual_refs_widget.setAlignment(Qt.AlignTop)

            scroll_area.setWidget(scroll_widget)

            individual_layout.addWidget(scroll_area)
            individual_group.setLayout(individual_layout)
            individual_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(individual_group, 1)

        # Boutons
        buttons_layout = QHBoxLayout()

        self.preview_checkbox = QCheckBox("Aperçu avant import (vérification détaillée, plus lent)")
        self.preview_checkbox.setChecked(False)
        self.preview_checkbox.setToolTip("Affiche un récapitulatif détaillé (créations/mises à jour) avant l'écriture définitive en base")
        buttons_layout.addWidget(self.preview_checkbox)

        buttons_layout.addStretch()

        try:
            import qtawesome as qta
            cancel_icon = qta.icon('fa5s.times', color='#495057')
            import_icon = qta.icon('fa5s.file-import', color='white')
        except Exception:
            cancel_icon = None
            import_icon = None

        cancel_btn = QPushButton("Annuler")
        if cancel_icon:
            cancel_btn.setIcon(cancel_icon)
            cancel_btn.setIconSize(QSize(11, 11))
        cancel_btn.setStyleSheet(
            "QPushButton { padding: 3px 10px; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); }"
        )
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("Importer")
        if import_icon:
            self.ok_btn.setIcon(import_icon)
            self.ok_btn.setIconSize(QSize(11, 11))
        self.ok_btn.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background-color: #218838; }"
            "QPushButton:disabled { background-color: #94d3a2; color: #e9f7ec; }"
        )
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._validate_and_accept)
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)
    
    def _populate_data(self):
        """Remplir l'interface avec les données"""
        # Les fichiers sont maintenant toujours affichés dans la grille (layout amélioré)
        
        # Analyser les formats et remplir l'aperçu
        self._analyze_formats_and_preview()
        
        # Références individuelles par fichier — multi-fichiers uniquement
        # (fichier unique : champs créés dans _setup_ui, section "Référence de pièce")
        for i, file in (enumerate(self.import_config.files) if len(self.import_config.files) > 1 else []):
            
            # ── Carte 2 lignes par fichier ───────────────────────────────────
            file_container = QWidget()
            file_container.setStyleSheet(
                "QWidget { background: white; border: 1px solid #e9ecef; border-radius: 4px; }"
            )
            card_layout = QVBoxLayout(file_container)
            card_layout.setContentsMargins(10, 6, 10, 6)
            card_layout.setSpacing(4)

            # Ligne 1 : référence (gauche) + nom de fichier (droite, flex)
            row1 = QHBoxLayout()
            row1.setSpacing(8)

            if file.type == FileType.CLIPBOARD:
                ref_input_edit = QLineEdit()
                ref_input_edit.setPlaceholderText("Référence pièce (ex: AS6015830)")
                ref_input_edit.setObjectName(f"ref_input_{file.path}")
                ref_input_edit.setFixedWidth(200)
                ref_input_edit.setStyleSheet(
                    "padding: 3px 6px; border: 2px solid #0066cc; border-radius: 4px; background: white;"
                )
                row1.addWidget(ref_input_edit)
            else:
                ref_display = QLabel(f"→ Réf: {file.suggested_reference}")
                ref_display.setStyleSheet(
                    "color: #0066cc; background-color: #f0f8ff; padding: 3px 8px;"
                    " border: 1px solid #ddd; border-radius: 4px; font-weight: bold; font-size: 11px;"
                )
                ref_display.setObjectName(f"ref_display_{file.path}")
                row1.addWidget(ref_display)

            file_label = QLabel(file.filename)
            file_label.setStyleSheet(
                "font-weight: bold; font-size: 12px; background: transparent; border: none;"
            )
            file_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row1.addWidget(file_label, 1)

            card_layout.addLayout(row1)

            # Ligne 2 : libellé + flags (Courante / Équivalente / Obsolète)
            row2 = QHBoxLayout()
            row2.setSpacing(8)

            desc_lbl = QLabel("Libellé:")
            desc_lbl.setStyleSheet(
                "font-size: 11px; color: #495057; background: transparent; border: none;"
            )
            desc_lbl.setFixedWidth(50)
            row2.addWidget(desc_lbl)

            desc_input = QLineEdit()
            desc_input.setPlaceholderText(
                "Description de la pièce (optionnel)" if file.type == FileType.CLIPBOARD
                else f"Description pour {file.suggested_reference} (optionnel)"
            )
            desc_input.setText("")
            desc_input.setObjectName(f"desc_{file.path}")
            desc_input.setStyleSheet(
                "padding: 3px 6px; border: 1px solid #ced4da; border-radius: 4px;"
                " font-size: 11px; background: white;"
            )
            row2.addWidget(desc_input, 1)
            self.individual_desc_fields.append(desc_input)

            if self.import_config.import_type == ImportType.MULTI_FILE:
                if self._succ_button_group is None:
                    self._succ_button_group = QButtonGroup(self)
                    self._succ_button_group.setExclusive(True)

                radio = QRadioButton("Courante")
                radio.setToolTip("Désigner cette réf. comme courante — les autres lui seront successées à l'import")
                radio.setStyleSheet("font-size: 11px; color: #495057; background: transparent; border: none;")
                self._succ_button_group.addButton(radio, i)
                self._succ_radio_files.append(file)
                row2.addWidget(radio)

                equiv_check = QCheckBox("Équivalente")
                equiv_check.setToolTip(
                    "Marquer cette réf. comme équivalente à la pièce courante\n"
                    "(même fonction, fabricant différent — les deux restent valides)"
                )
                equiv_check.setStyleSheet("font-size: 11px; color: #6c757d; background: transparent; border: none;")
                self._equiv_checkboxes.append((equiv_check, file))
                row2.addWidget(equiv_check)

                obs_check = QCheckBox("Obsolète")
                obs_check.setToolTip("Marquer cette référence comme obsolète (plus fabriquée)")
                obs_check.setStyleSheet("font-size: 11px; color: #c0392b; background: transparent; border: none;")
                self._obsolete_checkboxes.append((obs_check, file))
                row2.addWidget(obs_check)

            card_layout.addLayout(row2)
            self.individual_refs_widget.addWidget(file_container)

        # Initialiser l'affichage des références selon l'état par défaut de la case à cocher
        self._update_references_display()

        # Autocomplétion pour les champs de succession (fichier unique)
        self._setup_succession_autocomplete()
    
    def _setup_succession_autocomplete(self):
        """Configurer l'autocomplétion sur les champs de succession (fichier unique)."""
        if self.succ_replaces_input is None:
            return
        if not self.import_manager or not hasattr(self.import_manager, 'db_manager'):
            return
        try:
            rows = self.import_manager.db_manager.execute_query(
                "SELECT ref_piece FROM pieces ORDER BY ref_piece LIMIT 5000"
            ) or []
            ref_list = [r[0] for r in rows]
            for field in [self.succ_replaces_input, self.succ_replaced_by_input]:
                model = QStringListModel(ref_list, field)
                completer = QCompleter(model, field)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                field.setCompleter(completer)
        except Exception as e:
            app_logger.warning(f"Autocomplétion succession non disponible : {e}")

    def _set_preview_text(self, text: str):
        """Définit le texte de l'aperçu et ajuste la hauteur pour éviter l'ascenseur."""
        self.preview_text.setPlainText(text)
        n_lines = text.count('\n') + 1 if text else 0
        self.preview_text.setFixedHeight(max(n_lines * 16 + 6, 30))

    def _toggle_succ(self):
        """Ouvre/ferme la section Succession."""
        visible = not self._succ_content.isVisible()
        self._succ_content.setVisible(visible)
        arrow = "▼" if visible else "▶"
        text = self._succ_toggle_btn.text()
        self._succ_toggle_btn.setText(arrow + text[1:])

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
    
    def _on_apply_all_equiv_changed(self, state):
        """Coche/décoche toutes les cases 'Équivalente' individuelles."""
        for check, _ in getattr(self, '_equiv_checkboxes', []):
            check.setChecked(state == Qt.Checked)

    def _on_apply_all_obs_changed(self, state):
        """Coche/décoche toutes les cases 'Obsolète' individuelles."""
        for check, _ in getattr(self, '_obsolete_checkboxes', []):
            check.setChecked(state == Qt.Checked)

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
            # Référence — champ éditable pour le clipboard, sinon basé sur le fichier
            if file.type == FileType.CLIPBOARD:
                ref_input_edit = self.findChild(QLineEdit, f"ref_input_{file.path}")
                config.individual_references[file.path] = ref_input_edit.text().strip() if ref_input_edit else ""
            elif auto_references_enabled:
                config.individual_references[file.path] = file.suggested_reference
            else:
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

        config.show_preview = self.preview_checkbox.isChecked()
        
        # Ancienne configuration (pour compatibilité si nécessaire)
        config.label_config = LabelConfiguration()

        # Succession — fichier unique
        if len(config.files) == 1 and self.succ_replaces_input is not None:
            config.succession_replaces = self.succ_replaces_input.text().strip() or None
            config.succession_replaced_by = self.succ_replaced_by_input.text().strip() or None

        # Succession — multi-fichiers (ref courante désignée)
        if (config.import_type == ImportType.MULTI_FILE
                and self._succ_button_group is not None
                and self._succ_button_group.checkedId() >= 0
                and self._succ_radio_files):
            checked_id = self._succ_button_group.checkedId()
            if checked_id < len(self._succ_radio_files):
                current_file = self._succ_radio_files[checked_id]
                config.succession_current_ref = config.individual_references.get(current_file.path) or None

        # Équivalences — multi-fichiers (cases cochées "Équivalente")
        if config.import_type == ImportType.MULTI_FILE and self._equiv_checkboxes:
            for equiv_check, file in self._equiv_checkboxes:
                if equiv_check.isChecked():
                    ref = config.individual_references.get(file.path, '') or ''
                    if ref:
                        config.equivalence_refs.append(ref)

        # Obsolète — fichier unique
        if self._obsolete_checkbox is not None and self._obsolete_checkbox.isChecked():
            ref = config.common_reference or (
                config.individual_references.get(config.files[0].path, '') if config.files else ''
            )
            if ref:
                config.obsolete_refs.append(ref)

        # Obsolète — multi-fichiers (cases cochées "Obsolète")
        if config.import_type == ImportType.MULTI_FILE and self._obsolete_checkboxes:
            for obs_check, file in self._obsolete_checkboxes:
                if obs_check.isChecked():
                    ref = config.individual_references.get(file.path, '') or ''
                    if ref:
                        config.obsolete_refs.append(ref)

        # Mapping de colonnes personnalisé (v3.30.0)
        from .config import Config
        if Config.ENABLE_COLUMN_MAPPING and hasattr(self, '_mapping_widgets') and self._mapping_widgets:
            mapping = {}
            for widget in self._mapping_widgets:
                # Stocker si : groupe non reconnu (obligatoire) OU utilisateur a modifié
                if not widget._is_recognized or widget._is_modified:
                    mapping[widget._n_cols] = widget.get_mapping()
            if mapping:
                config.column_mapping = mapping

        self.result_config = config
        self.accept()
    
    def get_configuration(self) -> Optional[ImportConfiguration]:
        """Récupérer la configuration résultat"""
        return self.result_config
    
    @handle_ui_operation_errors(return_value=(2, []), log_prefix="Erreur lors de l'analyse du format")
    def _safe_analyze_file_format(self, first_file):
        """Helper pour analyser le format d'un fichier (avec gestion d'erreur)"""
        detected_columns = 0
        sample_data = []

        if first_file.data:
            sample_data = first_file.data[:3]  # 3 premières lignes
            if sample_data:
                detected_columns = len(sample_data[0])
        else:
            # Charger les données si pas encore fait (normalement fait par lazy loading)
            if self.import_manager:
                if first_file.type == FileType.CSV:
                    data = self.import_manager.load_csv_data(first_file.path, max_rows=5)
                else:  # PDF
                    # PHASE 1 OPTIMISATION: Mode preview pour aperçu rapide
                    data = self.import_manager.load_pdf_data(first_file.path, max_rows=5, preview_mode=True)

                if data:
                    sample_data = data[:3]
                    detected_columns = len(data[0]) if data else 0
            else:
                app_logger.warning("ImportManager non disponible pour analyser le format")

        return detected_columns, sample_data

    def _update_import_button(self):
        """Active/désactive le bouton Importer selon l'état des groupes non reconnus."""
        from .config import Config
        if not Config.ENABLE_COLUMN_MAPPING or not hasattr(self, '_mapping_widgets'):
            return
        all_ok = not any(w.is_mandatory_and_incomplete() for w in self._mapping_widgets)
        if hasattr(self, 'ok_btn'):
            self.ok_btn.setEnabled(all_ok)

    # ── Helpers groupement et mapping (v3.30.0) ──────────────────────────────

    def _group_files_by_columns(self) -> Dict[int, list]:
        """
        Analyser tous les fichiers et les grouper par nombre de colonnes détecté.
        Clé 0 = format non reconnu (fichier vide ou illisible).
        """
        groups: Dict[int, list] = {}
        for file in self.import_config.files:
            n_cols, _ = self._safe_analyze_file_format(file)
            groups.setdefault(n_cols, []).append(file)
        return groups

    @staticmethod
    def _normalize_header(s: str) -> str:
        """Normalise un header : minuscules, sans accents, sans ponctuation de fin."""
        s = str(s).lower().strip().strip('.')
        s = unicodedata.normalize('NFD', s)
        return ''.join(c for c in s if unicodedata.category(c) != 'Mn').strip()

    @staticmethod
    def _detect_csv_header_mapping(sample_data: list, n_cols: int) -> Optional[List[str]]:
        """
        Analyse la 1ère ligne pour détecter des entêtes CSV/collage connues.
        Retourne la liste de fields détectés, ou None si rien n'est reconnu.
        """
        if not sample_data or not sample_data[0]:
            return None
        first_row = sample_data[0]
        norm = ImportDialog._normalize_header

        synonyms: Dict[str, List[str]] = {
            'ref_modele':     ['ref_modele', 'ref modele', 'refmodele',
                               'ref technique', 'ref. technique', 'reference technique',
                               'ref. modele', 'reference modele', 'modele'],
            'commercial_ref': ['commercial_ref', 'ref commerciale', 'ref. commerciale',
                               'reference commerciale', 'ref comm', 'commercial'],
            'manufacturer':   ['fabricant', 'manufacturer', 'marque', 'brand'],
            'type':           ['type', "type d'appareil", 'type appareil'],
            'other_ref':      ['autre ref', 'autre reference', 'other_ref', 'autre', 'ref2'],
            'notes':          ['notes', 'note', 'commentaire', 'description', 'libelle'],
        }
        norm_synonyms = {
            field: [norm(s) for s in syns]
            for field, syns in synonyms.items()
        }

        mapping = []
        detected_any = False
        for cell in first_row[:n_cols]:
            cell_norm = norm(str(cell))
            field = 'ignore'
            for field_name, syns in norm_synonyms.items():
                if cell_norm in syns:
                    field = field_name
                    detected_any = True
                    break
            mapping.append(field)

        return mapping if detected_any else None

    @staticmethod
    def _is_format_recognized(n_cols: int, files: list, sample_data: list) -> bool:
        """
        Format reconnu = PDF 3 colonnes (Réf. technique / Réf. commerciale / Description).
        Note : l'extracteur PDF supprime la ligne d'entête avant de retourner les données,
        donc on ne peut pas vérifier les headers dans sample_data. On se base sur
        FileType.PDF + n_cols == 3, ce qui identifie de façon fiable le format 1001pièces.
        Tout autre format nécessite validation explicite du mapping par l'utilisateur.
        """
        return n_cols == 3 and any(f.type == FileType.PDF for f in files)

    def _get_default_mapping(self, n_cols: int, files: list,
                             sample_data: list = None) -> Tuple[List[str], bool]:
        """
        Retourne (mapping, headers_detected) pour un groupe.
        - Pour CSV/Collage : tente la détection d'entêtes ; si réussie → mapping inféré
          et headers_detected=True pour avertir l'utilisateur de vérifier.
        - Sinon : mapping positionnel par défaut, headers_detected=False.
        """
        # Pour CSV et collage : tenter la détection d'entêtes
        if sample_data and any(f.type in (FileType.CSV, FileType.CLIPBOARD) for f in files):
            detected = self._detect_csv_header_mapping(sample_data, n_cols)
            if detected:
                return detected, True

        # Mapping positionnel par défaut
        if n_cols == 1:
            return ["ref_modele"], False
        elif n_cols == 2:
            return ["ref_modele", "commercial_ref"], False
        elif n_cols == 3:
            return ["ref_modele", "commercial_ref", "ignore"], False
        elif n_cols >= 4:
            mapping = ["type", "manufacturer", "ref_modele", "commercial_ref"]
            mapping += ["ignore"] * (n_cols - 4)
            return mapping, False
        return ["ignore"] * max(n_cols, 1), False

    # ─────────────────────────────────────────────────────────────────────────

    def _analyze_formats_and_preview(self):
        """Analyser les formats des fichiers et générer l'aperçu des données"""
        if not self.import_config.files:
            return

        from .config import Config
        if not Config.ENABLE_COLUMN_MAPPING:
            # Comportement actuel inchangé
            self._analyze_formats_and_preview_legacy()
            return

        # Grouper les fichiers par structure
        self._file_groups = self._group_files_by_columns()

        # Masquer les labels legacy de format (le mapping les remplace)
        self.format_info_label.setVisible(False)
        self.format_desc_label.setVisible(False)
        self.format_warning_widget.setVisible(False)

        # ── Aperçu : utiliser le premier fichier du premier groupe (trié par nb colonnes) ──
        sorted_groups = sorted(self._file_groups.items())
        first_group_files = sorted_groups[0][1] if sorted_groups else []
        if first_group_files:
            _, sample_data_preview = self._safe_analyze_file_format(first_group_files[0])
        else:
            sample_data_preview = []

        if sample_data_preview:
            n_preview = len(sample_data_preview[0]) if sample_data_preview else 0
            header_line = "".join(f"Col{i+1:<15} " for i in range(n_preview))
            lines = [f"{'='*60}", header_line, f"{'='*60}"]
            for row in sample_data_preview:
                line = ""
                for j in range(min(n_preview, len(row))):
                    val = str(row[j])
                    cell = (val[:12] + "...") if len(val) > 12 else val
                    line += f"{cell:<15} "
                lines.append(line)
            self._set_preview_text("\n".join(lines))
            self.preview_text.setVisible(True)
        else:
            self.preview_text.setVisible(False)

        # ── Options : third_col_widget si groupe reconnu à 3 colonnes ──
        has_3col_recognized = any(
            self._is_format_recognized(n, files, self._safe_analyze_file_format(files[0])[1])
            for n, files in self._file_groups.items()
            if n == 3
        )
        if has_3col_recognized:
            has_pdf_3col = any(
                f.type == FileType.PDF
                for f in self._file_groups.get(3, [])
            )
            self.third_col_label.setText(
                "Destination Description:" if has_pdf_3col else "Destination 3ème colonne:"
            )
            self.third_col_widget.setVisible(True)
        else:
            self.third_col_widget.setVisible(False)

        # ── Option en-têtes CSV ──
        has_csv = any(
            f.type == FileType.CSV
            for files in self._file_groups.values()
            for f in files
        )
        self.headers_checkbox.setVisible(has_csv)

        # ── Vider et afficher le conteneur de mapping ──
        while self.mapping_container_layout.count():
            item = self.mapping_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._mapping_widgets = []
        self.mapping_container.setVisible(True)

        # Créer un MappingGroupWidget par groupe (trié par nb colonnes)
        for n_cols, files in sorted(self._file_groups.items()):
            _, sample_data = self._safe_analyze_file_format(files[0])
            is_recognized = self._is_format_recognized(n_cols, files, sample_data)
            default_mapping, headers_detected = self._get_default_mapping(n_cols, files, sample_data)
            widget = MappingGroupWidget(
                n_cols=n_cols,
                files=files,
                sample_data=sample_data,
                is_recognized=is_recognized,
                default_mapping=default_mapping,
                headers_detected=headers_detected,
                parent=self
            )
            widget.mapping_changed.connect(self._update_import_button)
            self._mapping_widgets.append(widget)
            self.mapping_container_layout.addWidget(widget)

        self._update_import_button()

    def _analyze_formats_and_preview_legacy(self):
        """Comportement historique : analyse le premier fichier pour le format général"""
        # Analyser le premier fichier pour déterminer le format général
        first_file = self.import_config.files[0]
        detected_columns, sample_data = self._safe_analyze_file_format(first_file)
        
        # Mise à jour de la configuration d'import
        self.import_config.csv_import_mode = detected_columns
        
        # Afficher les informations de format
        file_types = set(f.type.value.upper() for f in self.import_config.files)
        if len(self.import_config.files) == 1:
            info_text = f" Fichier {first_file.type.value.upper()} détecté: {detected_columns} colonnes"
        else:
            types_str = ", ".join(file_types)
            info_text = f" Fichiers détectés ({types_str}): {detected_columns} colonnes"
        
        # Description du format
        format_non_reconnu = False
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
            format_desc = ""
            format_non_reconnu = True

        if format_non_reconnu:
            self.format_info_label.setText("")
            self.format_desc_label.setText("")
            self.format_warning_widget.setVisible(True)
            if hasattr(self, 'ok_btn'):
                self.ok_btn.setEnabled(False)
        else:
            self.format_info_label.setText("Format reconnu:")
            self.format_desc_label.setText(format_desc)
            self.format_warning_widget.setVisible(False)
            if hasattr(self, 'ok_btn'):
                self.ok_btn.setEnabled(True)
        
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
            
            self._set_preview_text(preview_content)

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
    


class _ImportWorker(QThread):
    """Thread d'import — exécute _run_import_files() hors du main thread.
    Émet progress_updated pour mettre à jour la ProgressDialog sur le main thread,
    et finished quand le traitement est terminé."""

    progress_updated = pyqtSignal(int, int, str)   # value, maximum, label
    finished         = pyqtSignal(dict)
    error_occurred   = pyqtSignal(str)

    def __init__(self, manager, config, dry_run=False):
        super().__init__()
        self._manager  = manager
        self._config   = config
        self._canceled = False
        self._dry_run  = dry_run

    def cancel(self):
        self._canceled = True

    def run(self):
        try:
            results = self._manager._run_import_files(
                self._config,
                progress_cb=lambda v, m, lbl: self.progress_updated.emit(v, m, lbl),
                cancel_check=lambda: self._canceled,
                dry_run=self._dry_run,
            )
            self.finished.emit(results or {'total_files': 0, 'successful_files': 0,
                                           'total_imported': 0, 'errors': []})
        except Exception as e:
            app_logger.error(f"_ImportWorker: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class _ImportPreviewWorker(QThread):
    """Thread d'analyse dry-run — même pipeline que _ImportWorker mais sans écriture DB.
    Émet preview_ready avec les comptages simulés pour ImportPreviewDialog."""

    progress_updated = pyqtSignal(int, int, str)
    preview_ready    = pyqtSignal(dict)
    error_occurred   = pyqtSignal(str)

    def __init__(self, manager, config):
        super().__init__()
        self._manager  = manager
        self._config   = config
        self._canceled = False

    def cancel(self):
        self._canceled = True

    def run(self):
        try:
            results = self._manager._run_import_files(
                self._config,
                progress_cb=lambda v, m, lbl: self.progress_updated.emit(v, m, lbl),
                cancel_check=lambda: self._canceled,
                dry_run=True,
            )
            self.preview_ready.emit(results or {})
        except Exception as e:
            app_logger.error(f"_ImportPreviewWorker: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class ImportPreviewDialog(QDialog):
    """
    Dialogue de prévisualisation avant import (dry-run).
    Affiche les comptages simulés et laisse l'utilisateur confirmer ou annuler.
    Utilise show() + signaux (pas exec_()) pour éviter le freeze macOS.
    """

    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, results: dict, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prévisualisation de l'import")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Titre fichier(s) ──────────────────────────────────────────────
        file_details = results.get('file_details', [])
        if len(file_details) == 1:
            title_text = f"<b>{file_details[0]['filename']}</b>"
        elif len(file_details) > 1:
            title_text = f"<b>{len(file_details)} fichiers</b>"
        else:
            title_text = "<b>Import</b>"

        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        layout.addWidget(title_lbl)

        # ── Tableau de comptages ──────────────────────────────────────────
        grid_widget = QWidget()
        grid_widget.setStyleSheet(
            "background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;"
        )
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        rows_data = [
            ("Appareils à créer",          results.get('new_entries', 0),        '#2ecc71'),
            ("Déjà en base",               results.get('matches_found', 0),      '#3498db'),
            ("À compléter manuellement",   results.get('manual_completion', 0),  '#e67e22'),
            ("Doublons traités",           results.get('duplicates_in_file', 0), '#95a5a6'),
            ("Associations pièces",        results.get('associations_created', 0),'#9b59b6'),
        ]

        for i, (label, count, color) in enumerate(rows_data):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; color: #555; background: transparent; border: none;")
            count_lbl = QLabel(f"<b>{count:,}</b>".replace(',', ' '))
            count_lbl.setStyleSheet(
                f"font-size: 12px; color: {color}; background: transparent; border: none;"
            )
            count_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl,       i, 0)
            grid.addWidget(count_lbl, i, 1)

        layout.addWidget(grid_widget)

        # Comptage exact depuis v3.40.1 (réplique en lecture seule du chemin réel)
        note = QLabel("* Associations qui seront créées (les doublons déjà en base sont exclus)")
        note.setStyleSheet("font-size: 10px; color: #999;")
        layout.addWidget(note)

        # ── Boutons ───────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_bar.addWidget(cancel_btn)

        confirm_btn = QPushButton("Confirmer l'import")
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet(
            "QPushButton { background: #2ecc71; color: white; font-weight: bold;"
            " border-radius: 4px; padding: 4px 14px; }"
            "QPushButton:hover { background: #27ae60; }"
        )
        confirm_btn.clicked.connect(self._on_confirm)
        btn_bar.addWidget(confirm_btn)

        layout.addLayout(btn_bar)

    def _on_confirm(self):
        self.confirmed.emit()
        self.close()

    def _on_cancel(self):
        self.cancelled.emit()
        self.close()


class ImportManager:
    """Gestionnaire unifié pour tous les types d'imports"""
    
    def __init__(self, db_manager, parent_widget=None):
        self.db_manager = db_manager
        self.parent_widget = parent_widget
        self.main_window = parent_widget  # Pour accès aux services

        # PHASE 1.2 OPTIMISATION: Cache des métadonnées fichiers
        # Clé: (file_path, mtime), Valeur: sample_data
        # Évite de recharger les mêmes fichiers
        self._file_metadata_cache = {}
    
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
    
    def load_pdf_data(self, file_path: str, max_rows: Optional[int] = None, preview_mode: bool = False,
                      progress_cb: Optional[Callable] = None, cancel_check: Optional[Callable] = None) -> List[List[str]]:
        """
        Méthode unifiée pour le chargement PDF avec limite optionnelle

        Args:
            file_path: Chemin vers le fichier PDF
            max_rows: Nombre maximum de lignes à charger (None = toutes)
            preview_mode: Si True, charge seulement la 1ère page (10x plus rapide)

        Returns:
            Liste des lignes extraites du PDF

        Raises:
            ValueError: Si le fichier ne peut pas être traité

        Notes:
            PHASE 1 OPTIMISATION: preview_mode=True réduit drastiquement le temps
            de chargement pour les aperçus de dialogue
        """
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor
            extractor = CamelotPDFExtractor()
            data = extractor.extract_data(file_path, preview_mode=preview_mode,
                                            progress_cb=progress_cb, cancel_check=cancel_check)

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
    
    def import_files(self, file_paths: List[str], show_dialog: bool = True, callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """
        Importer un ou plusieurs fichiers

        Args:
            file_paths: Liste des chemins de fichiers
            show_dialog: Afficher l'interface de configuration
            callback: Fonction appelée avec les résultats (pour mode non-bloquant)

        Returns:
            Résultats d'import ou None si annulé
            PHASE 2.2: Retourne None immédiatement si callback fourni (mode non-bloquant)

        Notes:
            PHASE 2.2 OPTIMISATION: Si callback fourni, le dialogue est non-bloquant
            et les résultats sont passés au callback au lieu d'être retournés.
        """
        # PHASE 2.1 OPTIMISATION: Lazy loading - NE PAS charger les données ici
        # Les données seront chargées en différé dans le dialogue
        # Ceci élimine complètement le freeze AVANT l'ouverture du dialogue

        # Préparer la configuration RAPIDEMENT (sans chargement de données)
        import_files = []
        for path in file_paths:
            file_type = self._detect_file_type(path)
            if file_type:
                import_file = ImportFile(
                    path=path,
                    type=file_type,
                    suggested_reference=self._extract_reference_from_filename(path),
                    suggested_label=self._extract_reference_from_filename(path),
                    data=None  # PHASE 2.1: Pas de données - chargement lazy dans le dialogue
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
            # PHASE 2.1: Passer import_manager pour lazy loading
            dialog = ImportDialog(self.parent_widget, config, import_manager=self)

            # PHASE 2.2 OPTIMISATION: Dialogue non-bloquant si callback fourni
            if callback:
                # Mode non-bloquant: show() au lieu de exec_()
                dialog.accepted.connect(lambda: self._on_import_dialog_accepted(dialog, callback))
                dialog.rejected.connect(lambda: self._on_import_dialog_rejected(dialog, callback))
                dialog.show()
                return None  # Retour immédiat, résultat via callback
            else:
                # Mode bloquant classique (compatibilité)
                if dialog.exec_() != QDialog.Accepted:
                    return None

                config = dialog.get_configuration()
                if not config:
                    return None

        # PHASE 1: Décision intelligente Async vs Sync avec fallback automatique
        return self._execute_import(config)

    def import_from_clipboard(self, rows: List[List[str]], callback: Optional[Callable] = None) -> None:
        """
        Ouvrir ImportDialog alimenté par les données du presse-papiers (v3.31.0).
        Même expérience que l'import de fichier : aperçu, mapping, référence de pièce.

        Args:
            rows: Données déjà parsées du presse-papiers
            callback: Fonction appelée avec les résultats (mode non-bloquant)
        """
        import_file = ImportFile(
            path="Collage",
            type=FileType.CLIPBOARD,
            suggested_reference="",
            suggested_label="",
            data=rows  # Données pré-chargées — le lazy loading les utilisera directement
        )
        config = ImportConfiguration(
            files=[import_file],
            import_type=ImportType.SINGLE_FILE
        )
        dialog = ImportDialog(self.parent_widget, config, import_manager=self)
        if callback:
            dialog.accepted.connect(lambda: self._on_import_dialog_accepted(dialog, callback))
            dialog.rejected.connect(lambda: self._on_import_dialog_rejected(dialog, callback))
            dialog.show()
        else:
            if dialog.exec_() == QDialog.Accepted:
                config = dialog.get_configuration()
                if config:
                    return self._execute_import(config)

    def _launch_real_import(self, config, callback, t0, dialog=None, source='import'):
        """Lance le vrai _ImportWorker après confirmation (ou directement si pas de preview)."""
        from ..ui.progress_dialog import ProgressDialog
        from .constants import DatabaseConfig

        # Filet de sécurité quotidien : copie de la base avant écritures massives
        # (au plus une copie / 24h pour ne pas ralentir les imports répétés)
        backup_service = getattr(getattr(self, 'main_window', None), 'backup_service', None)
        if backup_service:
            backup_service.create_backup(
                reason="import",
                max_age_hours=DatabaseConfig.BACKUP_MIN_INTERVAL_IMPORT_H
            )

        n        = len(config.files)
        progress = ProgressDialog("Importation en cours", "Annuler", 0, n, self.parent_widget)
        progress.show()

        worker = _ImportWorker(self, config)
        self._import_worker = worker

        worker.progress_updated.connect(
            lambda v, m, lbl: (progress.setRange(0, m),
                               progress.setValue(v),
                               progress.setLabelText(lbl))
        )
        progress.canceled.connect(worker.cancel)

        def _on_finished(results):
            progress.close()
            worker.wait()
            results['processing_time_ms'] = int((_time.perf_counter() - t0) * 1000)
            if source == 'drag_drop':
                results['import_source'] = 'drag_drop'
            if hasattr(self, 'main_window') and self.main_window:
                self._trigger_post_import_updates()
            if callback:
                callback(results)
            if dialog:
                dialog.deleteLater()
            self._import_worker = None

        def _on_error(msg):
            progress.close()
            worker.wait()
            app_logger.error(f"Import worker ({source}) : {msg}")
            if callback:
                callback(None)
            if dialog:
                dialog.deleteLater()
            self._import_worker = None

        worker.finished.connect(_on_finished)
        worker.error_occurred.connect(_on_error)
        worker.start()

    def _launch_preview(self, config, callback, t0, dialog=None, source='import'):
        """Étape dry-run : analyse sans écriture, puis ImportPreviewDialog, puis import réel."""
        from ..ui.progress_dialog import ProgressDialog
        n        = len(config.files)
        progress = ProgressDialog("Analyse en cours…", "Annuler", 0, n, self.parent_widget)
        progress.show()

        preview_worker = _ImportPreviewWorker(self, config)
        self._preview_worker = preview_worker

        preview_worker.progress_updated.connect(
            lambda v, m, lbl: (progress.setRange(0, m),
                               progress.setValue(v),
                               progress.setLabelText(lbl))
        )
        progress.canceled.connect(preview_worker.cancel)

        def _on_preview_ready(results):
            progress.close()
            preview_worker.wait()
            self._preview_worker = None

            preview_dlg = ImportPreviewDialog(results, config, self.parent_widget)

            def _on_confirmed():
                self._launch_real_import(config, callback, t0, dialog=dialog, source=source)

            def _on_cancelled():
                if callback:
                    callback(None)
                if dialog:
                    dialog.deleteLater()

            preview_dlg.confirmed.connect(_on_confirmed)
            preview_dlg.cancelled.connect(_on_cancelled)
            preview_dlg.show()

        def _on_preview_error(msg):
            progress.close()
            preview_worker.wait()
            self._preview_worker = None
            # Fallback : lancer l'import directement sans preview
            app_logger.warning(f"Preview worker erreur ({msg}) — import direct")
            self._launch_real_import(config, callback, t0, dialog=dialog, source=source)

        preview_worker.preview_ready.connect(_on_preview_ready)
        preview_worker.error_occurred.connect(_on_preview_error)
        preview_worker.start()

    def _on_import_dialog_accepted(self, dialog, callback):
        """
        Callback appelé quand le dialogue d'import est accepté (mode non-bloquant).
        Lance d'abord une analyse dry-run (ImportPreviewDialog), puis le vrai import.
        """
        config = dialog.get_configuration()
        if not config:
            if callback:
                callback(None)
            dialog.deleteLater()
            return

        t0 = _time.perf_counter()
        if config.show_preview:
            self._launch_preview(config, callback, t0, dialog=dialog, source='import')
        else:
            self._launch_real_import(config, callback, t0, dialog=dialog, source='import')

    def _on_import_dialog_rejected(self, dialog, callback):
        """
        Callback appelé quand le dialogue d'import est annulé (mode non-bloquant)

        PHASE 2.2: Permet de gérer l'annulation proprement
        """
        try:
            # Import annulé, appeler le callback avec None
            if callback:
                callback(None)
        finally:
            # Nettoyer le dialogue
            dialog.deleteLater()

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur import drag&drop")
    def import_from_drag_drop(self, file_paths: List[str], callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
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
        if not file_paths:
            return None

        # PHASE 2.1: Valider et préparer les fichiers (sans charger les données)
        import_files = []
        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue

            file_type = self._detect_file_type(file_path)
            if not file_type:
                continue

            # Référence par défaut depuis nom fichier
            default_reference = self._extract_reference_from_filename(file_path)

            # PHASE 2.1: Lazy loading - NE PAS charger les données ici
            # Créer un objet ImportFile cohérent avec import_files()
            import_file = ImportFile(
                path=file_path,
                type=file_type,
                suggested_reference=default_reference,
                suggested_label=default_reference,
                data=None  # Chargement lazy dans le dialogue
            )
            import_files.append(import_file)

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
            config.reference_piece = import_files[0].suggested_reference

        # Dialogue adapté pour drag&drop
        # PHASE 2.1: Utiliser ImportDialog avec import_manager pour lazy loading
        dialog = ImportDialog(self.parent_widget, config, import_manager=self)

        # Titre spécialisé pour drag&drop
        dialog.setWindowTitle("Import par Glisser-Déposer")

        # PHASE 2.2 OPTIMISATION: Dialogue non-bloquant si callback fourni
        if callback:
            # Mode non-bloquant pour drag&drop
            dialog.accepted.connect(lambda: self._on_drag_drop_dialog_accepted(dialog, callback))
            dialog.rejected.connect(lambda: self._on_drag_drop_dialog_rejected(dialog, callback))
            dialog.show()
            return None  # Retour immédiat, résultat via callback
        else:
            # Mode bloquant classique (compatibilité)
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
                results['source_files'] = [f.path for f in import_files]

                # Format d'historique spécialisé
                if len(import_files) == 1:
                    file_name = os.path.basename(import_files[0].path)
                    file_ext = import_files[0].type.value.upper()
                    results['history_label'] = f"{file_ext} (Glisser-Déposer - {file_name})"
                else:
                    results['history_label'] = f"PDF Multi-fichiers ({len(import_files)} fichiers)"

            return results

    def _on_drag_drop_dialog_accepted(self, dialog, callback):
        """
        Callback appelé quand le dialogue drag&drop est accepté (mode non-bloquant).
        Lance d'abord une analyse dry-run (ImportPreviewDialog), puis le vrai import.
        """
        config = dialog.get_configuration()
        if not config:
            if callback:
                callback(None)
            dialog.deleteLater()
            return

        t0 = _time.perf_counter()
        if config.show_preview:
            self._launch_preview(config, callback, t0, dialog=dialog, source='drag_drop')
        else:
            self._launch_real_import(config, callback, t0, dialog=dialog, source='drag_drop')

    def _on_drag_drop_dialog_rejected(self, dialog, callback):
        """
        Callback appelé quand le dialogue drag&drop est annulé (mode non-bloquant)

        PHASE 2.2: Gestion propre de l'annulation
        """
        try:
            # Import annulé, appeler le callback avec None
            if callback:
                callback(None)
        finally:
            # Nettoyer le dialogue
            dialog.deleteLater()
    
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

    def _run_import_files(self, config: ImportConfiguration,
                          progress_cb=None, cancel_check=None,
                          dry_run: bool = False) -> Dict[str, Any]:
        """Moteur d'import pur — aucune opération UI.
        Peut s'exécuter dans un QThread.

        :param progress_cb: callable(value, maximum, label) pour les mises à jour UI
        :param cancel_check: callable() → bool pour l'annulation
        :param dry_run: si True, analyse sans aucune écriture en base
        """
        # Stocker le cancel_check pour les sous-méthodes (_process_data_import_batch, etc.)
        self._import_cancel_check = cancel_check

        cache_service = getattr(self.db_manager, 'cache_invalidation', None)
        if cache_service and not dry_run:
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
                'file_details': []
            }

            app_logger.info(f" Import de {len(config.files)} fichier(s)")
            seen_device_refs = set()

            n = len(config.files)
            if progress_cb:
                progress_cb(0, n, "Pré-chargement du cache…")

            shared_devices_cache      = self._preload_existing_devices()
            shared_autocomplete_cache = self._build_autocomplete_cache(shared_devices_cache)
            app_logger.info(f" Cache prêt : {len(shared_devices_cache)} appareils")

            for i, file in enumerate(config.files):
                if cancel_check and cancel_check():
                    app_logger.info(f"[!] Import annulé à {i}/{n}")
                    break

                if progress_cb:
                    progress_cb(i, n, f"Import de {file.filename}… ({i+1}/{n})")

                pdf_progress_cb = None
                if progress_cb and file.type == FileType.PDF:
                    # Sous-résolution pour faire avancer la barre PENDANT l'extraction
                    # d'un même fichier (sinon elle reste bloquée sur i/n)
                    PDF_SUBSCALE = 1000

                    def pdf_progress_cb(page, total_pages, _i=i, _n=n, _file=file):
                        sub_value = _i * PDF_SUBSCALE + int((page / total_pages) * PDF_SUBSCALE)
                        progress_cb(sub_value, _n * PDF_SUBSCALE,
                                    f"Extraction de {_file.filename} : page {page}/{total_pages} ({_i+1}/{_n})")

                file_results = self._safe_import_single_file(
                    file, config, seen_device_refs,
                    shared_devices_cache, shared_autocomplete_cache,
                    dry_run=dry_run, pdf_progress_cb=pdf_progress_cb,
                )

                if file_results:
                    results['successful_files'] += 1
                    results['file_details'].append({
                        'filename': file.filename,
                        'lines_processed': file_results.get('total_lines_extracted', 0),
                        'type': 'PDF' if file.type.name == 'PDF' else 'CSV'
                    })
                    for key in ['total_imported', 'matches_found', 'new_entries',
                                'associations_created', 'associations_existing',
                                'manual_completion', 'duplicates_in_file']:
                        results[key] += file_results.get(key, 0)

            if progress_cb:
                progress_cb(n, n, "Finalisation…")

            app_logger.info(f"[OK] Import terminé : {results['successful_files']}/{n} fichiers")

            if not dry_run:
                self._apply_succession_from_config(config, results)

            if not dry_run and hasattr(self.db_manager, 'cache_invalidation'):
                self.db_manager.cache_invalidation.invalidate_after_import(results)

            return results

        finally:
            self._import_cancel_check = None
            if cache_service:
                cache_service.resume_invalidation(force_invalidate=True)

    def _execute_import(self, config: ImportConfiguration) -> Dict[str, Any]:
        """Exécuter l'import de façon synchrone (chemins drag-drop et fallback).
        Affiche une ProgressDialog sur le main thread avec processEvents()."""
        from ..ui.progress_dialog import ProgressDialog

        n        = len(config.files)
        progress = ProgressDialog("Importation en cours", "Annuler", 0, n, self.parent_widget)
        progress.show()

        def _progress_cb(v, m, lbl):
            progress.setRange(0, m)
            progress.setValue(v)
            progress.setLabelText(lbl)
            QApplication.processEvents()

        results = self._run_import_files(
            config,
            progress_cb=_progress_cb,
            cancel_check=lambda: progress.wasCanceled(),
        )

        progress.close()

        if hasattr(self, 'main_window') and self.main_window:
            self._trigger_post_import_updates()

        return results
    
    def _apply_succession_from_config(self, config: ImportConfiguration, results: Dict) -> None:
        """
        Appliquer les relations de succession déclarées dans le dialogue d'import.

        Fichier unique :
          - succession_replaces    → (ref_old=existing, ref_new=imported_ref)
          - succession_replaced_by → (ref_old=imported_ref, ref_new=existing)
        Multi-fichiers :
          - succession_current_ref → toutes les autres refs pointent vers la ref courante
        """
        if not config.files:
            return

        # --- Fichier unique ---
        if len(config.files) == 1:
            file_ref = config.individual_references.get(config.files[0].path, '') or ''
            if not file_ref:
                return

            if config.succession_replaces:
                ok, msg = self.db_manager.add_supersession(config.succession_replaces, file_ref)
                if ok:
                    results['succession_created'] = results.get('succession_created', 0) + 1
                    app_logger.info(f"Succession import : {config.succession_replaces} → {file_ref}")
                    # La réf saisie est créée en fantôme → hériter du libellé importé
                    self.db_manager.inherit_phantom_description(file_ref, config.succession_replaces)
                else:
                    app_logger.warning(f"Succession import non créée ({config.succession_replaces} → {file_ref}) : {msg}")

            if config.succession_replaced_by:
                ok, msg = self.db_manager.add_supersession(file_ref, config.succession_replaced_by)
                if ok:
                    results['succession_created'] = results.get('succession_created', 0) + 1
                    app_logger.info(f"Succession import : {file_ref} → {config.succession_replaced_by}")
                    # La réf saisie est créée en fantôme → hériter du libellé importé
                    self.db_manager.inherit_phantom_description(file_ref, config.succession_replaced_by)
                else:
                    app_logger.warning(f"Succession import non créée ({file_ref} → {config.succession_replaced_by}) : {msg}")

        # --- Multi-fichiers ---
        elif config.import_type == ImportType.MULTI_FILE:
            current = config.succession_current_ref   # Peut être None (Option B)
            equiv_refs = config.equivalence_refs or []

            for file in config.files:
                other_ref = config.individual_references.get(file.path, '') or ''
                if not other_ref or other_ref == current:
                    continue

                if other_ref in equiv_refs:
                    # Équivalence — lier à la courante, ou au premier équivalent si pas de courante
                    pivot = current or (equiv_refs[0] if equiv_refs[0] != other_ref else None)
                    if pivot:
                        ok, msg = self.db_manager.add_equivalence(pivot, other_ref)
                        if ok:
                            results['equivalences_created'] = results.get('equivalences_created', 0) + 1
                            app_logger.info(f"Équivalence import : {other_ref} ≡ {pivot}")
                        else:
                            app_logger.warning(f"Équivalence import non créée ({other_ref} ≡ {pivot}) : {msg}")
                elif current:
                    # Succession normale
                    ok, msg = self.db_manager.add_supersession(other_ref, current)
                    if ok:
                        results['succession_created'] = results.get('succession_created', 0) + 1
                        app_logger.info(f"Succession import (multi) : {other_ref} → {current}")
                    else:
                        app_logger.warning(f"Succession import (multi) non créée ({other_ref} → {current}) : {msg}")

        # --- Obsolètes (tous modes) ---
        for ref in (config.obsolete_refs or []):
            if ref:
                ok = self.db_manager.mark_obsolete(ref)
                if ok:
                    results['obsolete_marked'] = results.get('obsolete_marked', 0) + 1
                    app_logger.info(f"Obsolète import : {ref}")
                else:
                    app_logger.warning(f"Obsolète import non appliqué : {ref}")

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur import fichier")
    def _safe_import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set,
                                  shared_devices_cache: Optional[Dict] = None,
                                  shared_autocomplete_cache: Optional[Dict] = None,
                                  dry_run: bool = False,
                                  pdf_progress_cb: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """Wrapper sécurisé pour _import_single_file avec gestion d'erreur intégrée"""
        return self._import_single_file(file, config, file_seen_device_refs,
                                        shared_devices_cache, shared_autocomplete_cache,
                                        dry_run=dry_run, pdf_progress_cb=pdf_progress_cb)

    def _import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set,
                             shared_devices_cache: Optional[Dict] = None,
                             shared_autocomplete_cache: Optional[Dict] = None,
                             dry_run: bool = False,
                             pdf_progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
        """Importer un fichier unique"""
        # Charger les données — clipboard utilise les données pré-chargées, fichiers relus depuis disque
        if file.type == FileType.CLIPBOARD and file.data is not None:
            data = file.data
        elif file.type == FileType.CSV:
            data = self.load_csv_data(file.path)
        elif file.type == FileType.PDF:
            # Import complet : extraction de TOUTES les pages (preview_mode=False par défaut)
            cancel_check = getattr(self, '_import_cancel_check', None)
            data = self.load_pdf_data(file.path, progress_cb=pdf_progress_cb, cancel_check=cancel_check)
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

        # En dry_run, toujours utiliser le batch (chemin propre : classification séparée des écritures)
        if dry_run or len(data) >= BATCH_THRESHOLD:
            return self._process_data_import_batch(
                data,
                references_and_labels,
                config,
                file,
                file_seen_device_refs,
                shared_devices_cache,
                shared_autocomplete_cache,
                dry_run=dry_run,
            )
        else:
            app_logger.debug(" Mode standard pour {len(data)} lignes (< {BATCH_THRESHOLD})")
            return self._process_data_import(
                data, 
                references_and_labels,  # Maintenant liste de tuples (ref, label)
                config,
                file,  # Passer le fichier pour les associations par fichier
                file_seen_device_refs  # CORRECTION: Suivi local par fichier
            )
    
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur association")
    def _safe_create_association(self, reference: str, device_id: int, label: str):
        """Helper pour créer une association avec gestion d'erreur"""
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
            return {'created': association_created, 'assoc_id': assoc_id}
        return None

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
            'duplicates_in_file': 0,  # Doublons ref_modele+commercial_ref inter-fichiers
            'total_lines_extracted': 0  # Total lignes du fichier (avant traitement doublons)
        }
        
        # MODIFICATION: Utiliser le set GLOBAL pour détecter les doublons INTER-fichiers
        # Détecter comme doublon des lignes identiques même dans des fichiers différents
        
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
                else:
                    ref_modele = col0
                    commercial_ref = col1
            else:
                # Format standard 2-3 colonnes
                ref_modele = str(row[0]).strip() if len(row) >= 1 and row[0] is not None else ""
                commercial_ref = str(row[1]).strip() if len(row) >= 2 and row[1] is not None else ""
            
            # Vérifier si c'est un doublon dans le fichier
            device_key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            if device_key in seen_device_refs and (ref_modele or commercial_ref):
                results['duplicates_in_file'] += 1
                app_logger.debug(f"   Doublon inter-fichiers traité: {ref_modele} | {commercial_ref}")
                # Trouver l'appareil existant et créer l'association même pour les doublons
                device_data_dup = self._parse_row_data(row, config)
                if device_data_dup:
                    device_id_dup = self._insert_or_find_device(device_data_dup)
                    if device_id_dup:
                        for reference, label in references_and_labels:
                            if reference:
                                assoc_result = self._safe_create_association(reference, device_id_dup, label)
                                if assoc_result:
                                    if assoc_result.get('created'):
                                        results['associations_created'] += 1
                                    else:
                                        results['associations_existing'] += 1
                continue  # L'appareil n'est pas recompté dans total_imported
            elif ref_modele or commercial_ref:
                seen_device_refs.add(device_key)
                app_logger.debug("[OK] LIGNE ACCEPTÉE: Ajout {device_key} aux références vues")
            
            # Traiter la ligne selon le mode d'import
            device_data = self._parse_row_data(row, config)

            if not device_data:
                continue

            # Compter APRÈS parse pour cohérence avec le chemin batch
            results['total_imported'] += 1

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
                        assoc_result = self._safe_create_association(reference, device_id, label)
                        if assoc_result:
                            if assoc_result.get('created'):
                                results['associations_created'] += 1
                                app_logger.debug("  ✨ Association créée: {reference} → {label} pour appareil {device_id}")
                            else:
                                results['associations_existing'] += 1
        
        return results
    
    def _process_data_import_batch(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]],
                                 config: ImportConfiguration, file: ImportFile, seen_device_refs: set,
                                 shared_devices_cache: Optional[Dict] = None,
                                 shared_autocomplete_cache: Optional[Dict] = None,
                                 dry_run: bool = False) -> Dict[str, Any]:
        """Version optimisée avec batch processing pour les gros imports.
        Si dry_run=True : classification uniquement, aucune écriture en base."""
        
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
        
        # ÉTAPE 1: Utiliser le cache partagé si fourni, sinon pré-charger (import fichier unique)
        cancel_check = getattr(self, '_import_cancel_check', None)
        if shared_devices_cache is not None:
            existing_devices_cache = shared_devices_cache
            autocomplete_cache = shared_autocomplete_cache or self._build_autocomplete_cache(existing_devices_cache)
            app_logger.debug(f" BATCH: Cache partagé utilisé ({len(existing_devices_cache)} appareils)")
        else:
            existing_devices_cache = self._preload_existing_devices()
            autocomplete_cache = self._build_autocomplete_cache(existing_devices_cache)

        # ÉTAPE 2: Traitement en mémoire de toutes les lignes
        app_logger.debug(f" BATCH: Analyse de {len(data)} lignes…")
        
        new_devices_batch = []
        existing_updates = []
        associations_batch = []
        processed_line_index = 0  # Compteur pour les lignes réellement traitées (hors continue)
        
        # Configuration pour progress optimisé
        from .config import Config
        progress_frequency = Config.IMPORT_PROGRESS_FREQUENCY
        total_rows = len(data)
        
        for idx, row in enumerate(data):
            # Vérifier si annulation demandée tous les 10 éléments
            if idx > 0 and idx % 10 == 0:
                if cancel_check and cancel_check():
                    app_logger.info(f"[!] Traitement batch annulé à la ligne {idx}/{len(data)}")
                    break

            if not row or not any(cell.strip() if cell is not None else False for cell in row):
                continue

            results['total_lines_extracted'] += 1

            # MODIFICATION BATCH: Détection doublons INTER-fichiers (entre tous les fichiers)
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
                else:
                    ref_modele = col0
                    commercial_ref = col1
            else:
                # Format standard 2-3 colonnes
                ref_modele = str(row[0]).strip() if len(row) >= 1 and row[0] is not None else ""
                commercial_ref = str(row[1]).strip() if len(row) >= 2 and row[1] is not None else ""

            device_key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            if device_key in seen_device_refs and (ref_modele or commercial_ref):
                results['duplicates_in_file'] += 1
                app_logger.debug(f"   BATCH Doublon inter-fichiers traité: {ref_modele} | {commercial_ref}")
                # Trouver l'appareil dans le cache et préparer l'association
                device_data_dup = self._parse_row_data(row, config)
                if device_data_dup:
                    dup_existing_id = self._find_in_cache(device_data_dup, existing_devices_cache)
                    if dup_existing_id:
                        for reference, label in references_and_labels:
                            if reference:
                                associations_batch.append((reference, label, processed_line_index, dup_existing_id))
                continue
            elif ref_modele or commercial_ref:
                seen_device_refs.add(device_key)
                app_logger.debug(f"[OK] BATCH LIGNE ACCEPTÉE: Ajout {device_key} aux références vues")

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

            if idx > 0 and idx % 100 == 0:
                app_logger.debug(f" BATCH: {idx}/{total_rows} lignes analysées")

        # ÉTAPE 3: Batch operations sur la base (ignorées en dry_run)
        if not dry_run:
            app_logger.debug(f" BATCH: Insertion de {len(new_devices_batch)} nouveaux appareils…")

            new_device_ids = self._batch_insert_devices(new_devices_batch) if new_devices_batch else []

            if len(new_devices_batch) != len(new_device_ids):
                app_logger.error(f"Erreur critique: {len(new_devices_batch)} nouveaux appareils -> {len(new_device_ids)} IDs obtenus")

            app_logger.debug(f" BATCH: Mise à jour de {len(existing_updates)} appareils existants…")
            if existing_updates:
                self._batch_update_devices(existing_updates)

            app_logger.debug(f" BATCH: Création de {len(associations_batch)} associations…")

            new_device_associations     = [a for a in associations_batch if not a[3]]
            existing_device_associations = [a for a in associations_batch if a[3]]
            unique_new      = set(a[2] for a in new_device_associations)
            unique_existing = set(a[2] for a in existing_device_associations)
            all_unique      = unique_new | unique_existing
            app_logger.info(f"Associations: {len(associations_batch)} total ({len(new_device_associations)} nouveaux + {len(existing_device_associations)} existants)")
            app_logger.info(f"Vérification: {results['total_imported']} lignes traitées vs {len(all_unique)} lignes avec associations")

            if associations_batch:
                batch_results = self._batch_create_associations(associations_batch, new_device_ids)
                results['associations_created'] += batch_results.get('created', 0)
                results['associations_existing'] += batch_results.get('existing', 0)

            if hasattr(self.db_manager, 'cache_invalidation'):
                self.db_manager.cache_invalidation.invalidate_after_import(results)
        else:
            # Dry-run (F7) : compter exactement depuis associations_batch (construit en
            # ÉTAPE 2 dans les deux modes), en répliquant la logique de
            # _batch_create_associations en lecture seule. L'ancienne approximation
            # (nouveaux appareils × refs valides) donnait des comptages faux.
            existing_pairs_in_db = set()
            existing_device_ids = list({a[3] for a in associations_batch if a[3]})
            CHUNK = 500
            for i in range(0, len(existing_device_ids), CHUNK):
                chunk = existing_device_ids[i:i + CHUNK]
                placeholders = ','.join('?' * len(chunk))
                rows = self.db_manager.execute_query(
                    f"SELECT p.ref_piece, pa.appareil_id "
                    f"FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id "
                    f"WHERE pa.appareil_id IN ({placeholders})",
                    chunk
                )
                existing_pairs_in_db.update((r[0], r[1]) for r in rows or [])

            created = existing = 0
            seen_pairs = set(existing_pairs_in_db)
            for reference, _label, data_index, existing_id in associations_batch:
                # Même clé que le chemin réel : appareil existant = id DB,
                # nouvel appareil = index de ligne (l'id n'existe pas encore)
                pair = (reference, existing_id) if existing_id else (reference, f"new_{data_index}")
                if pair in seen_pairs:
                    existing += 1
                else:
                    created += 1
                    seen_pairs.add(pair)

            results['associations_created'] = created
            results['associations_existing'] = existing

        app_logger.debug(f"[OK] BATCH: Terminé — {results['total_imported']} lignes traitées")
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
                        app_logger.debug("[ERR] Chunk {i//chunk_size + 1}: Impossible de récupérer l'ID pour un appareil")
                        conn.rollback()
                        return []
                
                all_new_ids.extend(chunk_ids)
                app_logger.debug("[OK] Chunk {i//chunk_size + 1}: {len(chunk_ids)} appareils insérés")
            
            conn.commit()
            app_logger.debug("[OK] BATCH FINAL: {len(all_new_ids)} appareils insérés au total")
            return all_new_ids
            
        except Exception as e:
            conn.rollback()
            app_logger.debug("[ERR] BATCH: Erreur insertion: {e}")
            app_logger.debug("[ERR] BATCH: IDs partiels récupérés avant erreur: {len(all_new_ids)}")
            import traceback
            app_logger.debug("[ERR] BATCH: Stack trace: {traceback.format_exc()}")
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
            app_logger.debug("[ERR] BATCH: Erreur mise à jour: {e}")
    
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
                    app_logger.debug("[!] BATCH: Pas assez d'IDs pour les nouveaux appareils (index {data_index})")
                    continue
            
            assoc_result = self._safe_create_association(reference, device_id, label)
            if assoc_result:
                if assoc_result.get('created'):
                    results['created'] += 1
                else:
                    results['existing'] += 1
        
        app_logger.debug(" BATCH: Associations - Créées: {results['created']}, Existantes: {results['existing']}")
        return results
    
    def _parse_row_data(self, row: List[str], config: ImportConfiguration) -> Optional[Dict[str, Any]]:
        """Parser une ligne de données selon la configuration"""
        if not row:
            return None

        # Mode mapping personnalisé (v3.30.0) — uniquement si explicitement renseigné
        n = len(row)
        if config.column_mapping and n in config.column_mapping:
            data = {}
            for i, field in enumerate(config.column_mapping[n]):
                if i < n and field != "ignore" and row[i] is not None:
                    data[field] = str(row[i]).strip()
            if not any(v for v in data.values() if v):
                return None
            if not data.get('type') or not data.get('manufacturer'):
                self._try_auto_complete(data)
            return data

        # Mode positionnel — comportement actuel inchangé (fallback)
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
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur mise à jour appareil")
    def _update_existing_device(self, device_id: int, device_data: Dict[str, Any]) -> None:
        """Mettre à jour un appareil existant avec les nouvelles données de la 3ème colonne"""
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
            app_logger.debug(" Appareil {device_id} mis à jour avec 3ème colonne: {update_data}")
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur insertion appareil")
    def _insert_or_find_device(self, device_data: Dict[str, Any]) -> Optional[int]:
        """Insérer ou trouver un appareil existant"""
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
    
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur auto-completion")
    def _try_auto_complete(self, appareil_data: dict) -> bool:
        """Compléter automatiquement Type et Fabricant à partir des références.
        Correspondance exacte uniquement sur les références non vides.
        Sélectionne la combinaison type+fabricant la plus fréquente en base.

        Returns:
            bool: True si au moins un champ a été complété
        """
        type_empty = not appareil_data.get('type', '').strip()
        manufacturer_empty = not appareil_data.get('manufacturer', '').strip()

        if not type_empty and not manufacturer_empty:
            return False

        # Construire la condition uniquement sur les références non vides
        ref_modele = appareil_data.get('ref_modele', '').strip()
        commercial_ref = appareil_data.get('commercial_ref', '').strip()

        if not ref_modele and not commercial_ref:
            return False

        conditions = []
        params = []
        if ref_modele:
            conditions.append('ref_modele = ?')
            params.append(ref_modele)
        if commercial_ref:
            conditions.append('commercial_ref = ?')
            params.append(commercial_ref)

        where_clause = ' OR '.join(conditions)
        query = f"""
            SELECT type, manufacturer, COUNT(*) as freq
            FROM appareils
            WHERE ({where_clause})
              AND type IS NOT NULL AND type != ''
              AND manufacturer IS NOT NULL AND manufacturer != ''
            GROUP BY type, manufacturer
            ORDER BY freq DESC
            LIMIT 1
        """

        results = self.db_manager.execute_query(query, params)

        if results:
            found_type, found_manufacturer = results[0][0], results[0][1]
            if type_empty:
                appareil_data['type'] = found_type
                app_logger.debug(f"  [OK] Type complété: '' -> '{found_type}'")
            if manufacturer_empty:
                appareil_data['manufacturer'] = found_manufacturer
                app_logger.debug(f"  [OK] Fabricant complété: '' -> '{found_manufacturer}'")
            return True

        return False

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mises à jour post-import")
    def _trigger_post_import_updates(self):
        """Déclencher les mises à jour post-import (Phase 4 - EventDrivenSaveService)"""
        from ..core.config import Config

        # Déclencher la sauvegarde événementielle si activée
        if Config.ENABLE_EVENT_DRIVEN_SAVE:
            if hasattr(self.main_window, 'event_driven_save_service') and self.main_window.event_driven_save_service:
                self.main_window.event_driven_save_service.handle_import_completed()
                app_logger.debug("EventDrivenSaveService: Sauvegarde événementielle déclenchée après import")

        # Toujours déclencher la mise à jour du bouton "lignes à compléter"
        if hasattr(self.main_window, '_update_incomplete_button_visibility'):
            from ..ui.qt_imports import QTimer
            QTimer.singleShot(200, self.main_window._update_incomplete_button_visibility)
            app_logger.debug("Mise à jour bouton 'lignes à compléter' programmée")

        # Invalider le cache des doublons après import
        if hasattr(self.main_window, 'duplicate_indicator_service') and self.main_window.duplicate_indicator_service:
            self.main_window.duplicate_indicator_service.invalidate_cache("import")
            app_logger.debug("Cache doublons invalidé après import")


# Fonctions utilitaires pour l'intégration
def create_import_manager(db_manager, parent_widget=None) -> ImportManager:
    """Créer une instance du gestionnaire d'import"""
    return ImportManager(db_manager, parent_widget)




def import_from_drag_drop(file_paths: List[str], db_manager, parent_widget=None) -> Optional[Dict[str, Any]]:
    """Fonction utilitaire pour import drag&drop"""
    manager = create_import_manager(db_manager, parent_widget)
    return manager.import_from_drag_drop(file_paths)
