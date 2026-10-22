"""
Gestionnaire d'importation unifié pour l'application de gestion d'appareils
Factorisation du code d'importation avec support des libellés hiérarchiques
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
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
                             QSizePolicy, QSize, QSplitter, pyqtSignal)

from PyQt5.QtWidgets import QLayout
from ..ui.style_manager import StyleManager
from .logger import app_logger
from ..utils.error_handler import handle_ui_operation_errors, handle_database_operation_errors
from ..utils.text_utils import decouper_refs
from ..ui.ref_chips_input import RefChipsInput



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
    # `succession_replaces` et `equivalence_ref` acceptent PLUSIEURS réfs (v3.91.0) :
    # liste, ou chaîne à réfs séparées par des espaces (normalisées par decouper_refs).
    # `succession_replaced_by` reste UNIQUE : piece_supersessions.ref_old est clé
    # primaire, une réf ne peut être remplacée que par une seule autre.
    succession_replaces: Optional[Union[str, List[str]]] = None  # Réfs existantes que cette réf remplace (ref_old=existing, ref_new=imported)
    succession_replaced_by: Optional[str] = None    # Réf existante qui remplace cette réf (ref_old=imported, ref_new=existing)
    equivalence_ref: Optional[Union[str, List[str]]] = None      # Fichier unique : réfs existantes équivalentes à cette réf

    # Références à marquer obsolètes lors de l'import
    obsolete_refs: Optional[List[str]] = None       # Réfs à marquer comme obsolètes après import

    # Modèle « par groupes » (nouveau panneau de relations) — si renseigné, il PRIME
    # sur les champs succession_*/equivalence_ref/obsolete_refs ci-dessus.
    relations_groups: Optional[List] = None         # List[import_relations.Group]
    relations_cards: Optional[List] = None           # List[import_relations.CardData]

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
        ("Notes / Description", "notes"),
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
                "color: #856404; font-size: 11px; background: transparent; border: none;"
            )
            title_col.addWidget(hint_lbl)

            banner_layout.addLayout(title_col, 1)
            outer.addWidget(banner)

            # Label de statut dynamique (rouge/orange selon état du mapping)
            self._status_label = QLabel()
            self._status_label.setStyleSheet(
                "color: #dc3545; font-size: 11px; padding: 1px 0;"
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
                "color: #6c757d; font-family: monospace; font-size: 11px;"
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
                    "color: #198754; font-size: 11px; padding: 1px 0;"
                )
            else:
                self._status_label.setText("Réf. Modèle non assignée — import bloqué")
                self._status_label.setStyleSheet(
                    "color: #dc3545; font-size: 11px; padding: 1px 0;"
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
        # Multi-fichiers : disposition en colonnes (cf _setup_ui) → moins de
        # hauteur nécessaire mais plus de largeur. Fichier unique : inchangé.
        if self.import_config.import_type == ImportType.MULTI_FILE:
            self.setMinimumHeight(720)
            self.resize(1280, 900)
        else:
            # Fichier unique : hauteur ajustée au contenu après chargement
            # (cf _ajuster_hauteur_fichier_unique). L'ancien minimum de 1000 px
            # laissait ~500 px vides sous le formulaire.
            self.setMinimumHeight(480)

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
        self._ajuster_hauteur_fichier_unique()

    def _ajuster_hauteur_fichier_unique(self):
        """Fichier unique : la fenêtre prend la hauteur de son contenu (bornée par
        l'écran). Multi-fichiers : taille fixée à la construction, inchangée."""
        if self.import_config.import_type == ImportType.MULTI_FILE:
            return
        # Recalcul forcé de la mise en page AVANT de mesurer : sinon sizeHint()
        # ignore la nouvelle hauteur de l'aperçu et la fenêtre est réduite sous
        # le minimum de son contenu (blocs comprimés, lien chevauchant l'aperçu).
        if self.layout() is not None:
            self.layout().activate()
        hauteur = max(self.minimumHeight(), self.sizeHint().height(),
                      self.minimumSizeHint().height())
        ecran = self.screen()
        if ecran is not None:   # bornée par l'écran, seulement s'il est connu
            hauteur = min(hauteur, ecran.availableGeometry().height() - 60)
        self.resize(self.width(), hauteur)

    def _setup_ui(self):
        """Créer l'interface utilisateur"""
        layout = QVBoxLayout()
        if self.import_config.import_type != ImportType.MULTI_FILE:
            # Fichier unique : la fenêtre ne descend jamais sous le minimum de son
            # contenu et s'agrandit seule quand il grandit (aperçu, panneau de
            # mapping, section Succession remplis ou ouverts après coup). Sans
            # cela, les blocs se comprimaient : le lien « Adapter le mapping »
            # chevauchait l'aperçu.
            layout.setSizeConstraint(QLayout.SetMinimumSize)
            # Cette contrainte remplace aussi la largeur minimale : un « étai »
            # inscrit les 1000 px dans le contenu lui-même.
            marges = layout.contentsMargins()
            layout.addStrut(self.minimumWidth() - marges.left() - marges.right())
        
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

        # Aperçu à gauche / options techniques à droite (gagne de la hauteur,
        # évite la redondance avec « Adapter le mapping »).
        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)
        preview_row.addWidget(self.preview_text, 1)

        # Options techniques à droite de l'aperçu
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(10, 4, 10, 2)
        
        # Gestion de la 3ème colonne si applicable
        self.third_col_widget = QWidget()
        self.third_col_widget.setStyleSheet("background-color: #fff; border: 1px solid #e9ecef; border-radius: 4px;")
        third_col_layout = QVBoxLayout(self.third_col_widget)
        third_col_layout.setContentsMargins(10, 5, 10, 5)
        third_col_layout.setSpacing(3)

        self.third_col_label = QLabel("Destination de la 3ᵉ colonne :")
        self.third_col_label.setStyleSheet("font-weight: bold;")
        third_col_layout.addWidget(self.third_col_label)
        
        self.third_col_combo = QComboBox()
        self.third_col_combo.addItems(["Ignorer", "Autre référence", "Notes"])
        self.third_col_combo.setCurrentIndex(1)  # "Autre référence" présélectionné (choix le plus fréquent)
        self.third_col_combo.currentIndexChanged.connect(self._sync_quick_third_col_to_mapping)
        third_col_layout.addWidget(self.third_col_combo)
        
        options_layout.addWidget(self.third_col_widget)
        self.third_col_widget.hide()  # Caché par défaut
        
        # Option en-têtes CSV avec style cohérent
        self.headers_checkbox = QCheckBox("1ʳᵉ ligne = en-têtes (ignorée)")
        self.headers_checkbox.setChecked(False)
        self.headers_checkbox.setToolTip("Cochez cette case si la première ligne de votre fichier contient les noms des colonnes")
        self.headers_checkbox.setStyleSheet("font-weight: bold; background-color: #fff; border: 1px solid #e9ecef; border-radius: 4px; padding: 8px 10px; margin-top: 5px;")
        options_layout.addWidget(self.headers_checkbox)
        self.headers_checkbox.hide()  # Caché par défaut, affiché seulement pour CSV
        options_layout.addStretch(1)

        # Panneau d'options à droite — se rétrécit quand ses options sont masquées
        self._format_options_panel = QWidget()
        self._format_options_panel.setLayout(options_layout)
        self._format_options_panel.setMaximumWidth(340)
        preview_row.addWidget(self._format_options_panel, 0, Qt.AlignTop)
        format_layout.addLayout(preview_row)

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
            ref_lbl = QLabel("Référence :")
            ref_lbl.setStyleSheet("font-weight: bold;")
            ref_lbl.setFixedWidth(90)
            row_ref.addWidget(ref_lbl)
            self.common_ref_input = QLineEdit()
            self.common_ref_input.setPlaceholderText("GAUxxxxxx")
            self.common_ref_input.setFixedWidth(170)  # ~20 caractères
            row_ref.addWidget(self.common_ref_input)
            try:
                row_ref.addWidget(self._make_info_button(
                    "La référence commune sera associée à TOUS les appareils importés.\n"
                    "Elle sera créée et enregistrée dans la base de données\n"
                    "comme toute autre référence de pièce."))
            except Exception:
                pass
            row_ref.addStretch(1)

            # Cases « tout appliquer » alignées à droite de la ligne Référence
            self._apply_all_equiv_checkbox = QCheckBox("Toutes équivalentes")
            self._apply_all_equiv_checkbox.setStyleSheet("font-size: 11px; color: #6A1B9A;")
            self._apply_all_equiv_checkbox.setToolTip(
                "Regroupe les références encore non groupées comme équivalentes entre elles\n"
                "(génère le groupe correspondant dans la zone « Relations entre références »)."
            )
            self._apply_all_equiv_checkbox.stateChanged.connect(self._on_apply_all_equiv_changed)
            row_ref.addWidget(self._apply_all_equiv_checkbox)

            self._apply_all_obs_checkbox = QCheckBox("Toutes obsolètes")
            self._apply_all_obs_checkbox.setStyleSheet("font-size: 11px; color: #c0392b;")
            self._apply_all_obs_checkbox.setToolTip(
                "Cocher toutes les références importées comme obsolètes"
            )
            self._apply_all_obs_checkbox.stateChanged.connect(self._on_apply_all_obs_changed)
            row_ref.addWidget(self._apply_all_obs_checkbox)
            ref_layout.addLayout(row_ref)

            # Ligne 2 : Description + case « Appliquer libellé »
            row_desc = QHBoxLayout()
            row_desc.setSpacing(8)
            desc_lbl2 = QLabel("Description :")
            desc_lbl2.setStyleSheet("font-weight: bold;")
            desc_lbl2.setFixedWidth(90)
            row_desc.addWidget(desc_lbl2)
            self.common_ref_description = QLineEdit()
            self.common_ref_description.setPlaceholderText("Ex : Lot pièces lave-vaisselle mars 2024")
            self.common_ref_description.textChanged.connect(self._on_common_description_changed)
            row_desc.addWidget(self.common_ref_description)

            self.apply_to_individual_checkbox = QCheckBox("Appliquer libellé")
            self.apply_to_individual_checkbox.setChecked(True)
            self.apply_to_individual_checkbox.setStyleSheet("font-size: 11px;")
            self.apply_to_individual_checkbox.setToolTip(
                "Duplique automatiquement cette description dans tous les champs libellé individuels"
            )
            self.apply_to_individual_checkbox.stateChanged.connect(self._on_apply_to_individual_changed)
            row_desc.addWidget(self.apply_to_individual_checkbox)
            ref_layout.addLayout(row_desc)

            ref_group.setLayout(ref_layout)
            # Différé : ajouté à la colonne gauche du QSplitter (cf fin _setup_ui)
            self._common_ref_group = ref_group

        self.individual_desc_fields = []

        if len(self.import_config.files) == 1:
            # ── Section "Référence de pièce" compacte (fichier unique) ──────────
            file = self.import_config.files[0]
            ref_group = QGroupBox("Référence de pièce")
            ref_group_layout = QVBoxLayout()
            ref_group_layout.setSpacing(8)

            # Ligne : Réf.
            ref_row = QHBoxLayout()
            ref_row_lbl = QLabel("Réf. :")
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
                ref_display = QLabel(f"→ Réf. : {file.suggested_reference or '—'}")
                ref_display.setStyleSheet(
                    "color: #0066cc; background-color: #f0f8ff; padding: 4px 8px;"
                    " border: 1px solid #ddd; border-radius: 4px; font-weight: bold;"
                )
                ref_display.setObjectName(f"ref_display_{file.path}")
                ref_row.addWidget(ref_display)
            ref_group_layout.addLayout(ref_row)

            # Ligne : Libellé
            desc_row = QHBoxLayout()
            desc_row_lbl = QLabel("Libellé :")
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

            # Mono-fichier : pas de zone de relations « par groupes » (chemin legacy)
            self._relations_groups_zone = None

            # ── Section succession repliable (liens entre réfs uniquement) ──────
            self.succ_replaces_input = None
            self.succ_replaced_by_input = None
            self.equiv_input = None
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
            self.succ_replaces_input = RefChipsInput("Anciennes réfs remplacées par cette réf, séparées par un espace (ex : REF123 REF124)", max_refs=None)
            self.succ_replaces_input.setMinimumHeight(30)
            row1.addWidget(self.succ_replaces_input)
            succ_layout.addLayout(row1)

            row2 = QHBoxLayout()
            lbl2 = QLabel("Cette réf. est remplacée par :")
            lbl2.setStyleSheet("font-weight: bold; background: transparent; border: none;")
            lbl2.setFixedWidth(220)
            row2.addWidget(lbl2)
            self.succ_replaced_by_input = RefChipsInput("Nouvelle réf. qui remplace cette réf. (ex : REF456)", max_refs=1)
            self.succ_replaced_by_input.setMinimumHeight(30)
            self.succ_replaced_by_input.setToolTip(
                "Une seule réf. : une pièce ne peut être remplacée que par une autre.\n"
                "(Plusieurs réfs. de remplacement interchangeables → déclarez-les\n"
                "équivalentes entre elles.)")
            row2.addWidget(self.succ_replaced_by_input)
            succ_layout.addLayout(row2)

            row3 = QHBoxLayout()
            lbl3 = QLabel("Cette réf. est équivalente à :")
            lbl3.setStyleSheet("font-weight: bold; background: transparent; border: none;")
            lbl3.setFixedWidth(220)
            row3.addWidget(lbl3)
            self.equiv_input = RefChipsInput("Réfs équivalentes à cette réf, séparées par un espace (ex : REF789 REF790)", max_refs=None)
            self.equiv_input.setMinimumHeight(30)
            row3.addWidget(self.equiv_input)
            succ_layout.addLayout(row3)

            self._succ_content.setVisible(True)
            succ_container_layout.addWidget(self._succ_content)
            layout.addWidget(succ_container)
            layout.addStretch(1)  # absorbe l'espace restant → format_group reste à hauteur naturelle

        else:
            # ── Mode multi-fichiers — scroll area références individuelles ───────
            self.succ_replaces_input = None
            self.succ_replaced_by_input = None
            self.equiv_input = None
            self._succ_button_group = None
            self._succ_radio_files = []
            self._equiv_checkboxes = []
            self._obsolete_checkbox = None
            self._obsolete_checkboxes = []

            individual_group = QGroupBox("Références individuelles par fichier")
            individual_layout = QVBoxLayout()

            info_and_option_layout = QHBoxLayout()
            info_and_option_layout.setContentsMargins(0, 0, 0, 0)
            info_and_option_layout.setSpacing(6)

            self.auto_file_references_checkbox = QCheckBox("Réf. de pièce = nom de fichier (auto)")
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

            try:
                info_and_option_layout.addWidget(self._make_info_button(
                    "Génération automatique des références de pièces basées sur les noms de fichiers."))
            except Exception:
                pass
            info_and_option_layout.addStretch(1)

            individual_layout.addLayout(info_and_option_layout)

            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            # Fond transparent + sans cadre (pas de rectangle gris bordé)
            scroll_area.setFrameShape(scroll_area.NoFrame)
            scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            scroll_area.viewport().setAutoFillBackground(False)

            scroll_area.setMinimumHeight(80)
            scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            scroll_widget = QWidget()
            scroll_widget.setObjectName("scroll_content")
            scroll_widget.setStyleSheet("#scroll_content { background: transparent; }")

            self.individual_refs_widget = QVBoxLayout(scroll_widget)
            self.individual_refs_widget.setContentsMargins(10, 10, 10, 10)
            self.individual_refs_widget.setSpacing(6)  # espacement entre cartes
            self.individual_refs_widget.setAlignment(Qt.AlignTop)

            scroll_area.setWidget(scroll_widget)

            individual_layout.addWidget(scroll_area)
            individual_group.setLayout(individual_layout)
            individual_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            # ── Zone de relations « par groupes » (lignées de succession +
            # groupes d'équivalence), alimentée par les références du lot ──────
            self._relations_groups_zone = self._build_relations_zone()
            # État de la case « Toutes équivalentes » synchronisé sur le contenu du
            # réservoir (grisée si aucune réf non groupée → coche sans effet).
            if self._relations_groups_zone is not None:
                self._relations_groups_zone.changed.connect(self._update_apply_all_equiv_state)
            self._update_apply_all_equiv_state()
            rel_group = None
            if self._relations_groups_zone is not None:
                rel_group = QGroupBox("Relations entre références (succession / équivalence)")
                rel_layout = QVBoxLayout()
                rel_layout.setContentsMargins(6, 6, 6, 6)
                rel_layout.addWidget(self._relations_groups_zone)
                rel_group.setLayout(rel_layout)
                rel_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            # ── Disposition en colonnes : [Réf. commune + individuelles] | [Relations]
            # Exploite la largeur (1280px) au lieu d'empiler verticalement deux
            # zones à ascenseurs → fin des ascenseurs imbriqués.
            left_col = QWidget()
            # Plafonne la colonne gauche pour laisser la largeur à la zone Relations
            # (sinon le champ Description pousse la poignée et étrique les 2 sous-colonnes).
            left_col.setMaximumWidth(580)
            left_layout = QVBoxLayout(left_col)
            left_layout.setContentsMargins(0, 0, 0, 0)  # l'espace vers la zone Relations est la poignée (8 px)
            left_layout.setSpacing(6)
            if getattr(self, '_common_ref_group', None) is not None:
                left_layout.addWidget(self._common_ref_group)
            left_layout.addWidget(individual_group, 1)

            if rel_group is not None:
                splitter = QSplitter(Qt.Horizontal)
                splitter.addWidget(left_col)
                splitter.addWidget(rel_group)
                splitter.setStretchFactor(0, 2)
                splitter.setStretchFactor(1, 3)
                splitter.setChildrenCollapsible(False)
                # Relations plus large par défaut (deux sous-colonnes succ.|équiv.)
                splitter.setSizes([500, 760])
                layout.addWidget(splitter, 1)
            else:
                layout.addWidget(left_col, 1)

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
        cancel_btn.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("Importer")
        if import_icon:
            self.ok_btn.setIcon(import_icon)
            self.ok_btn.setIconSize(QSize(12, 12))
        self.ok_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
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
                ref_display = QLabel(f"→ Réf. : {file.suggested_reference}")
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

            desc_lbl = QLabel("Libellé :")
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
                # Succession / équivalence : désormais déclarées dans la zone
                # « Relations entre références » (lignées + groupes). Sur la carte
                # on ne garde que « Obsolète ».
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
    
    def _build_relations_zone(self):
        """Construit la zone de relations « par groupes » (lignées de succession +
        groupes d'équivalence) pour le multi-fichiers, alimentée par les références
        du lot. Renvoie None si indisponible (≤ 1 réf ou erreur) — sans bloquer."""
        try:
            from ..ui.import_relations_panel import GroupsZone
            from PyQt5.QtCore import QStringListModel
            refs = [f.suggested_reference for f in self.import_config.files
                    if getattr(f, 'suggested_reference', '')]
            if len(refs) < 2:
                return None
            base_refs = []
            if self.import_manager and hasattr(self.import_manager, 'db_manager'):
                rows = self.import_manager.db_manager.execute_query(
                    "SELECT ref_piece FROM pieces ORDER BY ref_piece LIMIT 5000") or []
                base_refs = [r[0] for r in rows]
            # Référence persistante sur le modèle (piège GC du QCompleter)
            self._relations_base_model = QStringListModel(sorted(base_refs), self)
            return GroupsZone(refs, ref_model=self._relations_base_model)
        except Exception as e:
            app_logger.warning(f"Zone de relations indisponible : {e}")
            return None

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
            for field in [self.succ_replaces_input, self.succ_replaced_by_input, self.equiv_input]:
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
        # Hauteur d'une ligne mesurée sur la police EFFECTIVE (feuille de style
        # appliquée) : l'ancienne estimation fixe de 16 px coupait la dernière
        # ligne de l'aperçu à mi-hauteur.
        self.preview_text.ensurePolished()
        interligne = self.preview_text.fontMetrics().lineSpacing()
        marges = int(self.preview_text.document().documentMargin() * 2) + self.preview_text.frameWidth() * 2
        self.preview_text.setFixedHeight(max(n_lines * interligne + marges + 2, 30))


    def _toggle_succ(self):
        """Ouvre/ferme la section Succession."""
        visible = not self._succ_content.isVisible()
        self._succ_content.setVisible(visible)
        self._ajuster_hauteur_fichier_unique()   # la section ouverte ne doit pas être écrasée
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
        """« Toutes équivalentes » : génère (ou retire) un groupe d'équivalence
        regroupant les références encore *non groupées* (réservoir), sans toucher
        aux lignées/groupes déjà constitués."""
        zone = getattr(self, '_relations_groups_zone', None)
        if zone is None:
            return
        if state == Qt.Checked:
            self._auto_equiv_box = zone.add_all_to_new_equivalence()
            if self._auto_equiv_box is None:
                # Réservoir vide → la coche n'a produit aucun groupe : la décocher
                # plutôt que la laisser cochée sans effet (no-op silencieux).
                self._apply_all_equiv_checkbox.blockSignals(True)
                self._apply_all_equiv_checkbox.setChecked(False)
                self._apply_all_equiv_checkbox.blockSignals(False)
        else:
            box = getattr(self, '_auto_equiv_box', None)
            if box is not None:
                zone.remove_auto_equivalence_group(box)
            self._auto_equiv_box = None
        self._update_apply_all_equiv_state()

    def _update_apply_all_equiv_state(self, *_):
        """Griser « Toutes équivalentes » quand elle serait sans effet (réservoir
        « Non groupées » vide) — jamais quand elle est cochée (décochable en tout temps)."""
        cb = getattr(self, '_apply_all_equiv_checkbox', None)
        if cb is None:
            return
        zone = getattr(self, '_relations_groups_zone', None)
        if zone is None:
            cb.setEnabled(False)
            cb.setToolTip("Zone de relations indisponible : cette case n'a aucun effet.")
            return
        active = cb.isChecked() or zone.reservoir.count() > 0
        cb.setEnabled(active)
        if active:
            cb.setToolTip(
                "Regroupe les références encore non groupées comme équivalentes entre elles\n"
                "(génère le groupe correspondant dans la zone « Relations entre références »).")
        else:
            cb.setToolTip(
                "Aucune référence dans « Non groupées » : cette case n'aurait aucun effet.\n"
                "Sortez d'abord des réfs des lignées/groupes, ou déclarez l'équivalence\n"
                "directement dans la zone « Relations entre références ».")

    def _on_apply_all_obs_changed(self, state):
        """Coche/décoche toutes les cases 'Obsolète' individuelles."""
        for check, _ in getattr(self, '_obsolete_checkboxes', []):
            check.setChecked(state == Qt.Checked)

    # ── Synchro combo rapide « Destination Description » ↔ Colonne 3 du mapping ──
    _QUICK_THIRD_FIELDS = ['ignore', 'other_ref', 'notes']   # index combo rapide → valeur FIELD_CHOICES

    def _third_col_mapping_combo(self):
        """Combo « Colonne 3 » du groupe de mapping à 3 colonnes (ou None)."""
        for w in getattr(self, '_mapping_widgets', []):
            if getattr(w, '_n_cols', None) == 3 and len(getattr(w, '_combos', [])) >= 3:
                return w._combos[2]
        return None

    def _sync_quick_third_col_to_mapping(self, *_):
        """Combo rapide → Colonne 3 du mapping (sans réémettre de signal)."""
        combo = self._third_col_mapping_combo()
        if combo is None or not hasattr(self, 'third_col_combo'):
            return
        val = self._QUICK_THIRD_FIELDS[self.third_col_combo.currentIndex()]
        idx = combo.findData(val)
        if idx >= 0 and combo.currentIndex() != idx:
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    @staticmethod
    def _make_info_button(tooltip: str):
        """Petit bouton plat « ⓘ » (icône fa5s.info-circle) avec une infobulle.
        Factorise le pattern réutilisé sur plusieurs zones du dialogue."""
        import qtawesome as qta
        btn = QPushButton()
        btn.setIcon(qta.icon('fa5s.info-circle', color='#0066cc'))
        btn.setIconSize(QSize(13, 13))
        btn.setFixedSize(20, 20)
        btn.setFlat(True)
        btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
        btn.setToolTip(tooltip)
        return btn

    def _on_mapping_third_col_changed(self, *_):
        """Colonne 3 du mapping → combo rapide (si la valeur est représentable)."""
        combo = self._third_col_mapping_combo()
        if combo is None or not hasattr(self, 'third_col_combo'):
            return
        val = combo.currentData()
        if val in self._QUICK_THIRD_FIELDS:
            idx = self._QUICK_THIRD_FIELDS.index(val)
            if self.third_col_combo.currentIndex() != idx:
                self.third_col_combo.blockSignals(True)
                self.third_col_combo.setCurrentIndex(idx)
                self.third_col_combo.blockSignals(False)

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
                    ref_display.setText(f"→ Réf. : {file.suggested_reference}")
                    ref_display.setStyleSheet("color: #0066cc; background-color: #f0f8ff; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-weight: bold;")
                else:
                    # Affichage grisé indiquant que la référence ne sera pas créée
                    ref_display.setText("→ Réf. : (aucune référence de pièce)")
                    ref_display.setStyleSheet("color: #999; background-color: #f5f5f5; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-style: italic;")
    
    def _validate_and_accept(self):
        """Valider la configuration et accepter"""
        config = ImportConfiguration(
            files=self.import_config.files,
            import_type=self.import_config.import_type
        )
        self._collecter_references_et_libelles(config)
        self._collecter_options_format(config)
        self._collecter_relations(config)
        self._collecter_mapping_colonnes(config)

        # Garde-fou : une option d'équivalence est cochée mais l'état déclaré ne
        # produira AUCUNE équivalence → avertir avant de lancer l'import (sinon
        # l'utilisateur découvre après coup que sa déclaration a été perdue).
        warning = self._equivalence_warning_message(config)
        if warning:
            self._confirm_import_sans_equivalence(config, warning)
            return

        # Garde-fou : collage sans référence de pièce → appareils orphelins.
        warning_ref = self._reference_manquante_warning_message(config)
        if warning_ref:
            self._confirm_import_malgre_avertissement(
                config, "Aucune pièce ne sera associée", warning_ref)
            return

        self.result_config = config
        self.accept()

    def _collecter_references_et_libelles(self, config: ImportConfiguration):
        """Référence commune (multi-fichiers) puis référence et libellé de chaque fichier."""
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

    # Libellé du menu « 3ᵉ colonne » → valeur de ImportConfiguration.third_column_choice
    _CHOIX_TROISIEME_COLONNE = {
        "Ignorer": "ignore",
        "Autre référence": "other_ref",
        "Notes": "notes",
    }

    def _collecter_options_format(self, config: ImportConfiguration):
        """3ᵉ colonne, en-têtes et aperçu."""
        if hasattr(self, 'third_col_combo'):
            choice = self._CHOIX_TROISIEME_COLONNE.get(self.third_col_combo.currentText())
            if choice:
                config.third_column_choice = choice

        if hasattr(self, 'headers_checkbox'):
            config.has_headers = self.headers_checkbox.isChecked()

        config.show_preview = self.preview_checkbox.isChecked()

        # Ancienne configuration (pour compatibilité si nécessaire)
        config.label_config = LabelConfiguration()

    def _collecter_relations(self, config: ImportConfiguration):
        """Succession, équivalence et obsolescence déclarées dans le dialogue."""
        # Succession — fichier unique
        if len(config.files) == 1 and self.succ_replaces_input is not None:
            config.succession_replaces = self.succ_replaces_input.refs() or None
            config.succession_replaced_by = next(iter(self.succ_replaced_by_input.refs()), None)
            config.equivalence_ref = self.equiv_input.refs() or None

        # Succession / équivalence — multi-fichiers : modèle « par groupes » du
        # panneau de relations (lignées + groupes d'équivalence), appliqué par
        # _apply_relations_from_config. Porte aussi l'obsolescence multi-fichiers.
        if (config.import_type == ImportType.MULTI_FILE
                and getattr(self, '_relations_groups_zone', None) is not None):
            from ..services.import_relations import CardData
            config.relations_groups = self._relations_groups_zone.groups()
            obs_by_ref = {}
            for obs_check, file in (self._obsolete_checkboxes or []):
                ref = config.individual_references.get(file.path, '') or ''
                if ref:
                    obs_by_ref[ref] = obs_check.isChecked()
            seen, cards = set(), []
            for ref in config.individual_references.values():
                if ref and ref not in seen:
                    seen.add(ref)
                    cards.append(CardData(ref=ref, is_obsolete=obs_by_ref.get(ref, False)))
            config.relations_cards = cards

        # Obsolète — fichier unique
        if self._obsolete_checkbox is not None and self._obsolete_checkbox.isChecked():
            ref = config.common_reference or (
                config.individual_references.get(config.files[0].path, '') if config.files else ''
            )
            if ref:
                config.obsolete_refs.append(ref)

    def _collecter_mapping_colonnes(self, config: ImportConfiguration):
        """Mapping de colonnes personnalisé (v3.30.0)."""
        if hasattr(self, '_mapping_widgets') and self._mapping_widgets:
            mapping = {}
            for widget in self._mapping_widgets:
                # Stocker si : groupe non reconnu (obligatoire) OU utilisateur a modifié
                if not widget._is_recognized or widget._is_modified:
                    mapping[widget._n_cols] = widget.get_mapping()
            if mapping:
                config.column_mapping = mapping

    def _equivalence_warning_message(self, config) -> Optional[str]:
        """Message d'avertissement si une intention d'équivalence est déclarée mais
        qu'aucune équivalence ne sera créée. None si tout est cohérent."""
        zone = getattr(self, '_relations_groups_zone', None)
        if zone is None or config.relations_groups is None:
            return None
        from ..services.import_relations import count_planned_relations, KIND_EQUIVALENCE
        counts = count_planned_relations(config.relations_groups,
                                         config.relations_cards or [])
        if counts['equivalences'] > 0:
            return None
        cb = getattr(self, '_apply_all_equiv_checkbox', None)
        intent = (
            (cb is not None and cb.isChecked())
            or zone.all_equiv_check.isChecked()
            or any(b.cross_check is not None and b.cross_check.isChecked()
                   for b in zone.all_boxes())
            or any(g.kind == KIND_EQUIVALENCE for g in config.relations_groups)
        )
        if not intent:
            return None
        details = zone.warnings()
        msg = ("Une option d'équivalence est cochée, mais en l'état "
               "AUCUNE liaison d'équivalence ne sera créée par cet import.")
        if details:
            msg += "\n\n" + "\n".join(f"• {d}" for d in details)
        msg += "\n\nImporter quand même (sans équivalence) ?"
        return msg

    def _reference_manquante_warning_message(self, config) -> Optional[str]:
        """Message d'avertissement si un collage va être importé SANS référence de
        pièce : les appareils seront créés mais rattachés à aucune pièce, alors que
        l'association pièce↔appareils est l'objet même de l'import. None si une
        référence est renseignée ou si l'import ne provient pas d'un collage.

        Contrairement à l'import fichier (référence déduite du nom de fichier), le
        collage part d'un champ éditable vide : l'oubli est facile et silencieux."""
        if config.common_reference:
            return None
        collages = [f for f in config.files if f.type == FileType.CLIPBOARD]
        if not collages:
            return None
        if any((config.individual_references.get(f.path) or '').strip() for f in collages):
            return None
        return ("Aucune référence de pièce n'est renseignée : les appareils seront "
                "créés mais ne seront associés à AUCUNE pièce.\n\n"
                "Importer quand même (sans association) ?")

    def _confirm_import_sans_equivalence(self, config, message: str):
        """Avertissement non bloquant : aucune équivalence ne sera créée."""
        self._confirm_import_malgre_avertissement(
            config, "Aucune équivalence ne sera créée", message)

    def _confirm_import_malgre_avertissement(self, config, titre: str, message: str):
        """Avertissement non bloquant (show + callbacks, jamais exec_) : importer
        quand même, ou revenir au dialogue pour corriger la déclaration."""
        from PyQt5.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(titre)
        box.setText(message)
        btn_import = box.addButton("Importer quand même", QMessageBox.AcceptRole)
        box.addButton("Revenir au dialogue", QMessageBox.RejectRole)
        box.setWindowModality(Qt.WindowModal)

        def _on_finished(*_):
            if box.clickedButton() is btn_import:
                self.result_config = config
                self.accept()
            box.deleteLater()

        box.finished.connect(_on_finished)
        box.show()

    def get_configuration(self) -> Optional[ImportConfiguration]:
        """Récupérer la configuration résultat"""
        return self.result_config
    
    @handle_ui_operation_errors(return_value=(2, []), log_prefix="Erreur lors de l'analyse du format")
    def _analyse_format_memo(self, fichier):
        """Analyse de format mémoïsée pour la durée d'une passe d'aperçu.

        `_analyze_formats_and_preview` interroge le même fichier jusqu'à quatre
        fois : une pour l'aperçu, une pour reconnaître le format, une pour les
        options de colonnes. Sur un CSV c'est gratuit — les données sont déjà
        chargées, l'analyse n'est qu'une tranche de liste. Sur un PDF, chaque
        appel relance l'extraction : mesuré à 4 analyses du même fichier pour
        0,76 s, soit 64 % du temps d'ouverture de la fenêtre (v3.71.2).

        Le cache est **local à une passe** : `_analyze_formats_and_preview` le
        vide en entrant. C'est délibéré — le chargement paresseux peut peupler
        `fichier.data` entre deux passes, et un cache persistant servirait alors
        un résultat obsolète. Pendant une passe, rien ne change.
        """
        cle = id(fichier)
        cache = getattr(self, '_cache_analyse_format', None)
        if cache is None:
            cache = self._cache_analyse_format = {}
        if cle not in cache:
            cache[cle] = self._safe_analyze_file_format(fichier)
        return cache[cle]

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
        if not hasattr(self, '_mapping_widgets'):
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
            # Passe par le memo : l'aperçu réanalysera le premier fichier de
            # chaque groupe juste après (cf. _analyse_format_memo). Appelée
            # uniquement depuis _analyze_formats_and_preview, qui vient de vider
            # le cache — aucun risque de résultat obsolète.
            n_cols, _ = self._analyse_format_memo(file)
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
            # « reference » / « ref » seuls désignent la réf. modèle : c'est l'entête
            # le plus courant à la main, et son absence ici laissait le mapping sans
            # ref_modele — donc le bouton Importer grisé sans explication.
            # La correspondance est EXACTE (cell_norm in syns), aucune collision
            # possible avec « ref commerciale » ou « autre ref ».
            'ref_modele':     ['ref_modele', 'ref modele', 'refmodele',
                               'ref technique', 'ref. technique', 'reference technique',
                               'ref. modele', 'reference modele', 'modele',
                               'reference', 'ref'],
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
            # 3ᵉ colonne → « Autre référence » par défaut (= choix du combo rapide
            # « Destination Description », le plus fréquent), pas « Ignorer » :
            # les deux contrôles doivent être cohérents (le mapping prime à l'import).
            return ["ref_modele", "commercial_ref", "other_ref"], False
        elif n_cols >= 4:
            mapping = ["type", "manufacturer", "ref_modele", "commercial_ref"]
            mapping += ["ignore"] * (n_cols - 4)
            return mapping, False
        return ["ignore"] * max(n_cols, 1), False

    # ─────────────────────────────────────────────────────────────────────────

    def _analyze_formats_and_preview(self):
        """Analyser les formats des fichiers et générer l'aperçu des données"""
        # Cache d'analyse valable pour cette passe uniquement (cf. _analyse_format_memo)
        self._cache_analyse_format = {}

        if not self.import_config.files:
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
            _, sample_data_preview = self._analyse_format_memo(first_group_files[0])
        else:
            sample_data_preview = []

        if sample_data_preview:
            n_preview = len(sample_data_preview[0]) if sample_data_preview else 0
            header_line = "".join(f"Col{i+1:<15} " for i in range(n_preview))
            lines = [header_line, f"{'='*60}"]
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
            self._is_format_recognized(n, files, self._analyse_format_memo(files[0])[1])
            for n, files in self._file_groups.items()
            if n == 3
        )
        if has_3col_recognized:
            has_pdf_3col = any(
                f.type == FileType.PDF
                for f in self._file_groups.get(3, [])
            )
            self.third_col_label.setText(
                "Destination de la description :" if has_pdf_3col else "Destination de la 3ᵉ colonne :"
            )
            self.third_col_widget.setVisible(True)
        else:
            self.third_col_widget.setVisible(False)

        # ── Option en-têtes (CSV et collage) ──
        # Le collage est concerné au même titre que le CSV : ses données viennent
        # le plus souvent d'un tableur, entête comprise. La case lui était masquée,
        # rendant l'entête impossible à déclarer — elle était donc importée comme
        # un appareil.
        has_headers_option = any(
            f.type in (FileType.CSV, FileType.CLIPBOARD)
            for files in self._file_groups.values()
            for f in files
        )
        self.headers_checkbox.setVisible(has_headers_option)

        # ── Vider et afficher le conteneur de mapping ──
        while self.mapping_container_layout.count():
            item = self.mapping_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._mapping_widgets = []
        self.mapping_container.setVisible(True)

        # Créer un MappingGroupWidget par groupe (trié par nb colonnes)
        any_headers_detected = False
        for n_cols, files in sorted(self._file_groups.items()):
            _, sample_data = self._analyse_format_memo(files[0])
            is_recognized = self._is_format_recognized(n_cols, files, sample_data)
            default_mapping, headers_detected = self._get_default_mapping(n_cols, files, sample_data)
            any_headers_detected = any_headers_detected or headers_detected
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
            if n_cols == 3:
                widget.mapping_changed.connect(self._on_mapping_third_col_changed)
            self._mapping_widgets.append(widget)
            self.mapping_container_layout.addWidget(widget)

        # Cohérence détection d'entêtes ↔ case « 1ʳᵉ ligne = en-têtes ».
        # Si _detect_csv_header_mapping a reconnu une ligne d'entête (elle a servi à
        # inférer le mapping), la case est pré-cochée : sans cela l'application
        # détectait l'entête PUIS l'importait comme un appareil. L'utilisateur reste
        # libre de décocher.
        # (has_headers_option, pas isVisible() : la visibilité réelle dépend de
        # l'affichage du dialogue, or cette méthode tourne aussi avant.)
        if any_headers_detected and has_headers_option:
            self.headers_checkbox.setChecked(True)

        # Cohérence combo rapide « Destination Description » ↔ Colonne 3 du mapping
        # (le mapping prime à l'import — ils ne doivent jamais se contredire).
        self._on_mapping_third_col_changed()
        self._update_import_button()


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

        # Fichiers refusés par l'analyse à blanc : ils seront sautés à l'import réel.
        # Affiché uniquement s'il y en a — c'est l'information qui permet de renoncer
        # avant écriture plutôt que de la découvrir dans les logs après coup.
        fichiers_illisibles = len(results.get('errors', []))
        if fichiers_illisibles:
            rows_data.append(("Fichiers illisibles (ignorés)", fichiers_illisibles, '#e74c3c'))

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
        note.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(note)

        # ── Casse alignée sur la base (v3.83.0) ───────────────────────────
        # Annoncée avant d'écrire, et non découverte dans l'historique après coup
        encadre = self._encadre_alignements(results)
        if encadre is not None:
            layout.addWidget(encadre)

        # ── Boutons ───────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_bar.addWidget(cancel_btn)

        confirm_btn = QPushButton("Confirmer l'import")
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_bar.addWidget(confirm_btn)

        layout.addLayout(btn_bar)

    # Au-delà, la liste allongerait la fenêtre sans aider à décider : le détail
    # complet reste dans l'historique après l'import
    MAX_ALIGNEMENTS_AFFICHES = 8

    @classmethod
    def _lignes_alignements(cls, results: dict) -> List[str]:
        """['Marques :', 'DELTA → Delta (7),', …, 'Types :', …] ; vide si rien."""
        from ..services.casse_normalisation_service import CasseNormalisationService
        lignes = []
        for cle, titre in (('marques_alignees', 'Marques'), ('types_alignes', 'Types')):
            alignements = results.get(cle) or []
            if not alignements:
                continue
            lignes.append(f"{titre} :")
            visibles = CasseNormalisationService.lignes(alignements[:cls.MAX_ALIGNEMENTS_AFFICHES])
            if len(alignements) > cls.MAX_ALIGNEMENTS_AFFICHES:
                visibles[-1] += ','
                visibles.append(f"… et {len(alignements) - cls.MAX_ALIGNEMENTS_AFFICHES} autres")
            lignes.extend(f"    {v}" for v in visibles)
        return lignes

    def _encadre_alignements(self, results: dict) -> Optional[QWidget]:
        """Encadré « Orthographe alignée sur la base », ou None si rien n'est réécrit."""
        lignes = self._lignes_alignements(results)
        if not lignes:
            return None
        encadre = QWidget()
        encadre.setStyleSheet(
            "background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;"
        )
        couche = QVBoxLayout(encadre)
        couche.setContentsMargins(12, 8, 12, 8)
        couche.setSpacing(2)
        titre = QLabel("<b>Orthographe alignée sur la base</b>")
        titre.setStyleSheet("font-size: 11px; color: #2c3e50; background: transparent; border: none;")
        couche.addWidget(titre)
        for ligne in lignes:
            lbl = QLabel(ligne)
            lbl.setStyleSheet("font-size: 11px; color: #555; background: transparent; border: none;")
            couche.addWidget(lbl)
        return encadre

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

        # Compteurs de log agrégés (v3.66.0) : les messages par-appareil sont
        # comptés puis journalisés en une seule ligne, au lieu d'une ligne chacun.
        # Initialisés ici car _try_auto_complete est aussi appelable hors import.
        self._log_counters = self._nouveaux_compteurs_log()

        # Casse alignée sur la base : marques (v3.82.0, « DELTA » → « Delta ») et
        # types (v3.83.0, « CHAUFFAGE » → « Chauffage »)
        from ..services.casse_normalisation_service import CasseNormalisationService
        self._marques = CasseNormalisationService(db_manager, 'manufacturer')
        self._types = CasseNormalisationService(db_manager, 'type')

    @staticmethod
    def _nouveaux_compteurs_log() -> Dict[str, int]:
        """Compteurs de log remis à zéro (un jeu par import)."""
        return {'autocomplete_type': 0, 'autocomplete_manufacturer': 0}
    
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
                      progress_cb: Optional[Callable] = None, cancel_check: Optional[Callable] = None,
                      pages_vides_out: Optional[List[Dict]] = None) -> List[List[str]]:
        """
        Méthode unifiée pour le chargement PDF avec limite optionnelle

        Args:
            file_path: Chemin vers le fichier PDF
            max_rows: Nombre maximum de lignes à charger (None = toutes)
            preview_mode: Si True, charge seulement la 1ère page (10x plus rapide)
            pages_vides_out: liste à remplir avec les pages vides détectées
                             (fourchettes de références où des appareils manquent).
                             Paramètre de sortie et non attribut : l'aperçu tourne
                             dans un autre thread et ne doit pas écraser l'information
                             d'un import en cours.

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
            if pages_vides_out is not None:
                pages_vides_out.extend((extractor.last_extraction_info or {}).get('pages_vides', []))

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
                dialog.accepted.connect(lambda: self._on_dialog_accepted(dialog, callback, 'import'))
                dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
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
            dialog.accepted.connect(lambda: self._on_dialog_accepted(dialog, callback, 'import'))
            dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
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
                               progress.setLabelText(lbl),
                               QApplication.processEvents())
        )
        progress.canceled.connect(worker.cancel)

        def _on_finished(results):
            worker.wait()
            results['processing_time_ms'] = int((_time.perf_counter() - t0) * 1000)
            if source == 'drag_drop':
                results['import_source'] = 'drag_drop'
            # Le dialogue reste ouvert pendant le rafraîchissement post-import
            # (callback -> table_controller.load_data(), coûteux sur gros volumes,
            # + historique) : le fermer ici laissait un silence total entre la fin
            # de l'import et le tableau à jour, perçu comme un plantage.
            progress.setLabelText("Mise à jour de l'affichage…")
            QApplication.processEvents()
            if hasattr(self, 'main_window') and self.main_window:
                self._trigger_post_import_updates()
            if callback:
                callback(results)
            progress.close()
            if dialog:
                dialog.deleteLater()
            self._import_worker = None

        def _on_error(msg):
            progress.close()
            worker.wait()
            app_logger.error(f"Import worker ({source}) : {msg}")
            # Sans ce message, l'import interrompu (ex. lecture des appareils
            # existants impossible) ne laissait qu'une ligne de log.
            # show() et non exec_() : convention du projet (gel macOS).
            if self.parent_widget:
                from PyQt5.QtWidgets import QMessageBox
                from PyQt5.QtCore import Qt
                box = QMessageBox(QMessageBox.Critical, "Import interrompu",
                                  f"L'import a été interrompu par une erreur :\n\n{msg}\n\n"
                                  f"Relancez l'import ; le détail est dans le journal.",
                                  QMessageBox.Ok, self.parent_widget)
                box.setAttribute(Qt.WA_DeleteOnClose)
                box.show()
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
                               progress.setLabelText(lbl),
                               QApplication.processEvents())
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
            dialog.accepted.connect(lambda: self._on_dialog_accepted(dialog, callback, 'drag_drop'))
            dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
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


    
    def _on_dialog_accepted(self, dialog, callback, source):
        """
        Callback appelé quand un dialogue d'import est accepté (mode non-bloquant).
        Lance d'abord une analyse dry-run (ImportPreviewDialog), puis le vrai import.

        Socle commun des chemins fichier et drag&drop, qui ne différaient que par
        la valeur de `source` transmise en aval.

        Args:
            source: 'import' (fichier ou collage) ou 'drag_drop', propagé tel quel
                    à _launch_preview / _launch_real_import.
        """
        config = dialog.get_configuration()
        if not config:
            if callback:
                callback(None)
            dialog.deleteLater()
            return

        t0 = _time.perf_counter()
        if config.show_preview:
            self._launch_preview(config, callback, t0, dialog=dialog, source=source)
        else:
            self._launch_real_import(config, callback, t0, dialog=dialog, source=source)

    def _on_dialog_rejected(self, dialog, callback):
        """
        Callback appelé quand un dialogue d'import est annulé (mode non-bloquant).

        PHASE 2.2: Gestion propre de l'annulation. Les chemins fichier et
        drag&drop en portaient deux versions strictement identiques.
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
        self._log_counters = self._nouveaux_compteurs_log()

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
            # Collecte (niveau session, accumulée sur tous les fichiers) des lignes
            # restées incomplètes après le mécanisme exact, pour suggestions différées.
            self._pending_similarity_candidates = []
            # Frères COMPLETS du même lot (Type+Marque renseignés) : on les ajoutera à
            # l'index de similarité pour que les incomplètes du lot « voient » leurs
            # frères importés en même temps (pas encore en base au moment du calcul).
            self._imported_complete_for_similarity = []
            # Références de pièce de chaque ligne incomplète (clé : id(device_data)),
            # pour la suggestion « type de la pièce importée ».
            self._refs_pieces_candidats = {}
            # Appareils existants dont Type/Fabricant vides ont été complétés
            # (clé : id), pour le bloc d'historique de l'import.
            self._completions_existants = {}
            # Appareils dont un champ auto-complété a été tracé (fenêtre « à vérifier »)
            self._appareils_autocompletes = set()
            self._horodatage_import = datetime.now().isoformat(sep=' ', timespec='seconds')

            n = len(config.files)
            if progress_cb:
                progress_cb(0, n, "Pré-chargement du cache…")

            shared_devices_cache      = self._preload_existing_devices()
            shared_autocomplete_cache = self._build_autocomplete_cache(shared_devices_cache)
            self._marques.charger()
            self._types.charger()
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
                    errors_out=results['errors'],
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
                    if file_results.get('pages_vides'):
                        alerte = self._alerte_pages_vides(file.filename, file_results['pages_vides'])
                        results.setdefault('alerte_pages_vides', []).append(alerte)
                        app_logger.warning(f"[Import] {' | '.join(alerte)}")

            if progress_cb:
                progress_cb(n, n, "Finalisation…")

            # Appareils existants complétés (Type/Fabricant vides) : tracés dans l'historique
            if self._completions_existants:
                results['appareils_completes'] = list(self._completions_existants.values())
            if self._appareils_autocompletes:
                results['autocompletes_a_verifier'] = len(self._appareils_autocompletes)

            # Marques et types réécrits (« DELTA → Delta ») : tracés dans l'historique
            for service, cle, libelle in ((self._marques, 'marques_alignees', 'Marques alignées'),
                                          (self._types, 'types_alignes', 'Types alignés')):
                alignements = service.alignements()
                if alignements:
                    results[cle] = alignements
                    app_logger.info(f"[Import] {libelle} : {service.resume(alignements)}")

            # Les fichiers en échec sont sautés, pas fatals : le lot se termine et
            # la liste des refusés part dans results['errors'] jusqu'à l'UI.
            echecs = len(results['errors'])
            resume = f"[OK] Import terminé : {results['successful_files']}/{n} fichiers"
            if echecs:
                apercu = " | ".join(results['errors'][:5])
                if echecs > 5:
                    apercu += f" | … ({echecs - 5} de plus)"
                app_logger.warning(f"{resume} — {echecs} fichier(s) ignoré(s) : {apercu}")
            else:
                app_logger.info(resume)

            # Suggestions Type/Marque par similarité (additif, non bloquant) : calcul
            # en un seul lot sur les lignes incomplètes collectées pendant l'import.
            # On transmet progress_cb pour rendre cette phase visible (sinon la barre
            # reste figée sur « Finalisation… » pendant tout le calcul → effet "planté").
            if not dry_run:
                results['similarity_suggestions'] = \
                    self._compute_pending_similarity_suggestions(progress_cb=progress_cb)

            if not dry_run:
                if getattr(config, 'relations_groups', None) is not None or \
                        getattr(config, 'relations_cards', None) is not None:
                    self._apply_relations_from_config(config, results)
                else:
                    self._apply_succession_from_config(config, results)

            if not dry_run and hasattr(self.db_manager, 'cache_invalidation'):
                self.db_manager.cache_invalidation.invalidate_after_import(results)

            # Références pièce importées, dans l'ordre des fichiers (sans doublon ni vide) —
            # utilisé pour charger automatiquement la recherche sur la référence courante.
            seen_refs = set()
            imported_refs = []
            for ref in config.individual_references.values():
                ref = (ref or '').strip()
                if ref and ref not in seen_refs:
                    seen_refs.add(ref)
                    imported_refs.append(ref)
            results['imported_refs'] = imported_refs

            self._log_resume_import(results, seen_device_refs)
            return results

        finally:
            self._import_cancel_check = None
            if cache_service:
                cache_service.resume_invalidation(force_invalidate=True)

    @staticmethod
    def _alerte_pages_vides(nom_fichier: str, trous: List[Dict]) -> List[str]:
        """
        Message d'alerte « pages vides » d'un fichier : un titre puis une fourchette
        par trou. Calculé ici et transporté dans results, comme alerte_mapping,
        pour que le récap n'ait qu'à l'afficher.

        Ex. ['805101.pdf : 4 pages vides — appareils peut-être manquants entre :',
             'p.3 : DFI544BXXL-04 → DFI544D-02', ...]
        """
        nb_pages = sum(len(t['pages']) for t in trous)
        pluriel = 's' if nb_pages > 1 else ''
        lignes = [f"{nom_fichier} : {nb_pages} page{pluriel} vide{pluriel} — "
                  f"appareils peut-être manquants entre :"]
        for trou in trous:
            pages = trou['pages']
            libelle = f"p.{pages[0]}" if len(pages) == 1 else f"p.{pages[0]}-{pages[-1]}"
            lignes.append(f"{libelle} : {trou['avant']} → {trou['apres']}")
            # Réparations des lignes coupées au bord du trou : jamais silencieuses
            for brute, corrigee in trou.get('corrections', []):
                lignes.append(f"{libelle} : tiret rétabli, {brute} → {corrigee}")
            for ligne in trou.get('ignorees', []):
                lignes.append(f"{libelle} : ligne coupée non importée, {ligne}")
        return lignes

    def _log_resume_import(self, results: Dict[str, Any], seen_device_refs: set) -> None:
        """Une ligne de synthèse en fin d'import, en remplacement des messages
        par-appareil (v3.66.0).

        Le rapport « lignes traitées / clés d'appareil distinctes » est volontairement
        mis en avant : c'est l'indicateur qui aurait rendu immédiatement visible le
        bug de déduplication du 2026-09-01 (310 lignes → 1 seule clé distincte), là
        où il fallait auparavant lire 309 lignes de log identiques pour le repérer.
        """
        traitees = results.get('total_imported', 0)
        doublons = results.get('duplicates_in_file', 0)
        distinctes = len(seen_device_refs)
        compteurs = self._log_counters
        app_logger.info(
            f"[Import] Synthèse : {traitees} lignes traitées, {distinctes} clés "
            f"d'appareil distinctes, {doublons} doublons "
            f"— auto-complétion : {compteurs['autocomplete_type']} types, "
            f"{compteurs['autocomplete_manufacturer']} fabricants, "
            f"{len(results.get('appareils_completes', []))} appareils existants complétés"
        )
        # Signal fort : beaucoup de lignes pour une seule identité d'appareil.
        # Le total inclut les doublons — c'est justement là qu'elles atterrissent
        # quand le mapping écrase l'identité (309 des 310 lignes le 2026-09-01).
        lignes = traitees + doublons
        results['cles_distinctes'] = distinctes
        if lignes > 1 and distinctes <= 1:
            # Message calculé ici et transporté dans results : les deux constructeurs
            # de synthèse (import CSV/collage et import PDF) le consomment tel quel,
            # plutôt que de réévaluer la condition chacun de leur côté.
            results['alerte_mapping'] = (
                f"{lignes} lignes n'ont produit que {distinctes} identité(s) "
                f"d'appareil — vérifiez le mapping des colonnes"
            )
            app_logger.warning(f"[Import] {results['alerte_mapping']}.")

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
    
    def _apply_relations_from_config(self, config: ImportConfiguration, results: Dict) -> None:
        """Applique le modèle « par groupes » du nouveau panneau de relations
        (lignées de succession, groupes d'équivalence, courantes externes, obsolètes).
        Non bloquant : un échec ne doit jamais casser un import.
        """
        try:
            from ..services.import_relations import apply_relations
            groups = config.relations_groups or []
            cards = config.relations_cards or []
            counts = apply_relations(groups, cards, self.db_manager)
            results['succession_created'] = results.get('succession_created', 0) + counts.get('successions', 0)
            results['equivalences_created'] = results.get('equivalences_created', 0) + counts.get('equivalences', 0)
            results['obsoletes_marked'] = results.get('obsoletes_marked', 0) + counts.get('obsoletes', 0)
            app_logger.info(
                f"Relations import appliquées : {counts.get('successions', 0)} succession(s), "
                f"{counts.get('equivalences', 0)} équivalence(s), {counts.get('obsoletes', 0)} obsolète(s)"
                + (f", {counts['errors']} erreur(s)" if counts.get('errors') else ""))
        except Exception as e:
            app_logger.error(f"Application des relations d'import échouée (non bloquant) : {e}")

    def _apply_succession_from_config(self, config: ImportConfiguration, results: Dict) -> None:
        """
        Appliquer les relations déclarées dans le dialogue d'import fichier unique
        (l'import multi-fichiers passe par _apply_relations_from_config).

        Fichier unique :
          - succession_replaces    → (ref_old=existing, ref_new=imported_ref), pour chaque réf
          - succession_replaced_by → (ref_old=imported_ref, ref_new=existing)
          - equivalence_ref        → add_equivalence(imported_ref, réf), pour chaque réf
        Tous modes :
          - obsolete_refs          → mark_obsolete
        """
        if not config.files:
            return

        # --- Fichier unique ---
        if len(config.files) == 1:
            file_ref = config.individual_references.get(config.files[0].path, '') or ''
            if not file_ref:
                return

            # Plusieurs anciennes réfs possibles : chacune est remplacée par la réf
            # importée. Un refus (cycle, réf = elle-même) n'empêche pas les suivantes.
            for ancienne in decouper_refs(config.succession_replaces):
                self._appliquer_relation_import(
                    results, 'succession_created', "Succession import",
                    f"{ancienne} → {file_ref}",
                    self.db_manager.add_supersession(ancienne, file_ref),
                    file_ref, ancienne)

            if config.succession_replaced_by:
                nouvelle = config.succession_replaced_by
                self._appliquer_relation_import(
                    results, 'succession_created', "Succession import",
                    f"{file_ref} → {nouvelle}",
                    self.db_manager.add_supersession(file_ref, nouvelle),
                    file_ref, nouvelle)

            for equivalente in decouper_refs(config.equivalence_ref):
                self._appliquer_relation_import(
                    results, 'equivalences_created', "Équivalence import",
                    f"{file_ref} ≡ {equivalente}",
                    self.db_manager.add_equivalence(file_ref, equivalente),
                    file_ref, equivalente)

        # --- Obsolètes (tous modes) ---
        for ref in (config.obsolete_refs or []):
            if ref:
                ok = self.db_manager.mark_obsolete(ref)
                if ok:
                    results['obsolete_marked'] = results.get('obsolete_marked', 0) + 1
                    app_logger.info(f"Obsolète import : {ref}")
                else:
                    app_logger.warning(f"Obsolète import non appliqué : {ref}")

    def _appliquer_relation_import(self, results: Dict, compteur: str, libelle: str,
                                   lien: str, resultat, file_ref: str, partenaire: str) -> None:
        """Comptabiliser et journaliser une relation créée à l'import fichier unique.

        En cas de succès, le libellé est propagé entre la réf importée et la réf
        citée : celle-ci peut être créée en fantôme, ou exister déjà en base avec
        son propre libellé — la propagation va dans le sens utile, quel que soit
        le type de relation déclarée (succession dans un sens ou l'autre, ou
        équivalence)."""
        ok, msg = resultat
        if ok:
            results[compteur] = results.get(compteur, 0) + 1
            app_logger.info(f"{libelle} : {lien}")
            self.db_manager.propagate_description(file_ref, partenaire)
        else:
            app_logger.warning(f"{libelle} non créée ({lien}) : {msg}")

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur import fichier")
    def _safe_import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set,
                                  shared_devices_cache: Optional[Dict] = None,
                                  shared_autocomplete_cache: Optional[Dict] = None,
                                  dry_run: bool = False,
                                  pdf_progress_cb: Optional[Callable] = None,
                                  errors_out: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Wrapper sécurisé pour _import_single_file avec gestion d'erreur intégrée.

        Un fichier illisible ne doit jamais interrompre le lot. Le try/except
        annoncé par le nom de la méthode manquait (v3.72.1) : l'exception remontait
        la boucle, puis _run_import_files, jusqu'à _ImportWorker qui rapportait
        l'import entier comme échoué. Sur un lot de 192 PDF, un seul alias macOS
        renommé en .pdf faisait ainsi perdre tous les fichiers suivants, sans dire
        lequel avait échoué ni où l'import s'était arrêté.

        L'erreur est journalisée, consignée dans `errors_out`, et None est renvoyé :
        la boucle appelante saute le fichier via son garde `if file_results:`, qui
        anticipait déjà ce retour.

        :param errors_out: liste alimentée d'un libellé par fichier en échec.
                           Des chaînes, pas des dicts : l'UI fait `"\\n".join(...)`
                           dessus (main_refactored._safe_show_import_results_new).
        """
        try:
            return self._import_single_file(file, config, file_seen_device_refs,
                                            shared_devices_cache, shared_autocomplete_cache,
                                            dry_run=dry_run, pdf_progress_cb=pdf_progress_cb)
        except Exception as e:
            # Annulation en cours : l'extraction PDF interrompue renvoie [], puis
            # _import_single_file lève « Aucune donnée trouvée dans le fichier ».
            # Ce n'est pas un fichier défectueux — ne pas le signaler comme tel.
            cancel_check = getattr(self, '_import_cancel_check', None)
            if cancel_check and cancel_check():
                app_logger.info(f"[Import] {file.filename} : interrompu par l'annulation")
                return None

            app_logger.error(f"[Import] Fichier ignoré — {file.filename} : {e}", exc_info=True)
            if errors_out is not None:
                errors_out.append(f"{file.filename} : {e}")
            return None

    def _import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set,
                             shared_devices_cache: Optional[Dict] = None,
                             shared_autocomplete_cache: Optional[Dict] = None,
                             dry_run: bool = False,
                             pdf_progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
        """Importer un fichier unique"""
        # Charger les données — clipboard utilise les données pré-chargées, fichiers relus depuis disque
        pages_vides = []
        if file.type == FileType.CLIPBOARD and file.data is not None:
            data = file.data
        elif file.type == FileType.CSV:
            data = self.load_csv_data(file.path)
        elif file.type == FileType.PDF:
            # Import complet : extraction de TOUTES les pages (preview_mode=False par défaut)
            cancel_check = getattr(self, '_import_cancel_check', None)
            data = self.load_pdf_data(file.path, progress_cb=pdf_progress_cb, cancel_check=cancel_check,
                                      pages_vides_out=pages_vides)
        else:
            raise ValueError(f"Type de fichier non supporté: {file.type}")
        
        if not data:
            raise ValueError("Aucune donnée trouvée dans le fichier")

        # Ligne d'en-tête déclarée par l'utilisateur : la retirer avant traitement.
        # Restreint à CSV et collage — l'extracteur PDF supprime déjà l'entête, et
        # config.has_headers est global : sur un import mixte, l'appliquer au PDF
        # supprimerait une vraie ligne de données. La case n'est d'ailleurs proposée
        # que pour ces deux types.
        if config.has_headers and file.type in (FileType.CSV, FileType.CLIPBOARD):
            app_logger.debug(f" En-tête ignorée pour {file.path}: {data[0]}")
            data = data[1:]
            if not data:
                raise ValueError("Le fichier ne contient qu'une ligne d'en-tête")

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
        
        if references_and_labels and individual_ref == references_and_labels[0][0]:
            # Même référence que la commune : une seule association par ligne. Sans
            # ce garde, la 2ᵈᵉ était retrouvée en base et comptée « déjà associée »
            # (collage de 25 lignes : « Nouvelles : 25 » ET « Déjà associées : 25 »).
            # Libellé du fichier prioritaire s'il est renseigné — c'était déjà l'effet
            # des deux passages, le 2ᵈ remplaçant le libellé du 1ᵉʳ.
            if individual_label:
                references_and_labels[0] = (individual_ref, individual_label)
        else:
            # Garder le libellé vide si l'utilisateur n'a rien saisi
            references_and_labels.append((individual_ref, individual_label))

        # Effectuer l'import des données - Mode batch pour gros volumes
        # Seuil pour activer le mode batch optimisé (réduit pour meilleure performance)
        BATCH_THRESHOLD = 50  # lignes - batch dès 50 lignes pour optimisation immédiate

        # En dry_run, toujours utiliser le batch (chemin propre : classification séparée des écritures)
        if dry_run or len(data) >= BATCH_THRESHOLD:
            file_results = self._process_data_import_batch(
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
            app_logger.debug(f" Mode standard pour {len(data)} lignes (< {BATCH_THRESHOLD})")
            file_results = self._process_data_import(
                data,
                references_and_labels,  # Maintenant liste de tuples (ref, label)
                config,
                file,  # Passer le fichier pour les associations par fichier
                file_seen_device_refs  # CORRECTION: Suivi local par fichier
            )

        if pages_vides and isinstance(file_results, dict):
            file_results['pages_vides'] = pages_vides
        return file_results
    
    
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

    def _collecter_candidat_similarite(self, device_data, actif=True, refs_pieces=()):
        """Ranger une ligne importée pour le calcul différé des suggestions Type/Marque.

        Une ligne restée incomplète après le mécanisme exact devient un candidat ;
        une ligne complète devient une référence de comparaison pour ses frères du
        même lot. On stocke la RÉFÉRENCE à device_data : l'id, réinjecté plus tard
        pour les nouveaux appareils, sera visible au moment du calcul.

        Les deux chemins d'import portaient ce bloc à l'identique — le chemin
        standard ne l'avait d'ailleurs reçu qu'en v3.55.0, après qu'on eut constaté
        que les petits imports ne déclenchaient jamais de suggestions.

        Args:
            actif: False en dry-run, où l'on ne collecte rien.
            refs_pieces: références de pièce auxquelles la ligne est rattachée
                (suggestion « type de la pièce importée »).
        """
        from .config import Config

        if not (actif and Config.ENABLE_SIMILARITY_SUGGESTIONS
                and hasattr(self, '_pending_similarity_candidates')):
            return

        complet = ((device_data.get('type') or '').strip()
                   and (device_data.get('manufacturer') or '').strip())
        if complet:
            self._imported_complete_for_similarity.append(device_data)
        else:
            self._pending_similarity_candidates.append(device_data)
            refs = [r for r in refs_pieces if r]
            if refs and hasattr(self, '_refs_pieces_candidats'):
                self._refs_pieces_candidats[id(device_data)] = refs

    # Verdicts rendus par _preparer_ligne
    LIGNE_IGNOREE = 'ignoree'      # vide ou non parsable : rien à faire
    LIGNE_DOUBLON = 'doublon'      # identité déjà vue : rattacher l'association
    LIGNE_A_TRAITER = 'a_traiter'  # identité nouvelle : résoudre l'appareil

    def _preparer_ligne(self, row, config, seen_device_refs, results, prefixe_log=''):
        """Étapes communes aux deux chemins d'import, jusqu'à la décision de traiter.

        `_process_data_import` (standard) et `_process_data_import_batch` portaient
        la même séquence : ignorer les lignes vides, compter la ligne extraite,
        parser selon le mapping, dériver la clé d'identité, décider si c'est un
        doublon. Seule la **résolution** de l'appareil diffère ensuite — SQL
        immédiat d'un côté, cache et écriture différée de l'autre.

        Cette séquence avait déjà divergé trois fois (ordre parse/clé, moment du
        comptage, collecte des suggestions), dont une fois en produisant un bug
        de production. Les tests d'équivalence
        (tests/unit/test_import_paths_equivalence.py) verrouillent le résultat ;
        ce socle commun supprime la possibilité même de la dérive.

        Args:
            prefixe_log: inséré dans les messages de debug pour distinguer les
                deux chemins ('' ou 'BATCH ').

        Returns:
            (verdict, device_data, device_key) — les deux derniers valent None
            pour LIGNE_IGNOREE.
        """
        from .config import Config

        if not row or not any(cell.strip() if cell is not None else False for cell in row):
            return self.LIGNE_IGNOREE, None, None

        # Compter chaque ligne non vide comme extraite du fichier
        results['total_lines_extracted'] += 1

        # Parser AVANT tout : la clé de déduplication doit être dérivée du mapping
        # de colonnes réellement appliqué, pas devinée par position.
        device_data = self._parse_row_data(row, config)
        if not device_data:
            return self.LIGNE_IGNOREE, None, None   # Ligne non parsable, ne pas compter

        # Détection des doublons INTER-fichiers (seen_device_refs est partagé)
        ref_modele, commercial_ref, device_key = self._build_device_key(device_data)

        if device_key in seen_device_refs and (ref_modele or commercial_ref):
            results['duplicates_in_file'] += 1
            app_logger.debug(
                f"   {prefixe_log}Doublon inter-fichiers traité: {ref_modele} | {commercial_ref}")
            return self.LIGNE_DOUBLON, device_data, device_key

        if ref_modele or commercial_ref:
            seen_device_refs.add(device_key)
            if Config.LOG_VERBOSE_PER_DEVICE:
                app_logger.debug(
                    f"[OK] {prefixe_log}LIGNE ACCEPTÉE: Ajout {device_key} aux références vues")

        # Compté seulement maintenant : une ligne ignorée ou doublon n'y entre pas
        results['total_imported'] += 1
        return self.LIGNE_A_TRAITER, device_data, device_key

    def _process_data_import(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]],
                           config: ImportConfiguration, file: ImportFile, seen_device_refs: set) -> Dict[str, Any]:
        """Traiter l'import des données avec les références et libellés séparés"""
        # Import hissé en tête : un « from .config import Config » plus bas dans la
        # fonction rendrait Config local à TOUTE la fonction (UnboundLocalError sur
        # les usages antérieurs).
        from .config import Config

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
            verdict, device_data, device_key = self._preparer_ligne(
                row, config, seen_device_refs, results)

            if verdict == self.LIGNE_IGNOREE:
                continue

            if verdict == self.LIGNE_DOUBLON:
                # Trouver l'appareil existant et créer l'association même pour les doublons
                # Pas de complétion sur un doublon : le chemin batch ne la tente qu'à
                # la 1ʳᵉ occurrence de l'identité (clé = références seules)
                device_id_dup = self._insert_or_find_device(device_data, completer=False)
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

            # Insérer ou trouver l'appareil
            device_id = self._insert_or_find_device(device_data)

            if device_id:
                device_data['id'] = device_id  # pour la collecte des suggestions (ci-dessous)
                if device_data.get('is_new', False):
                    results['new_entries'] += 1
                    # Vérifier si l'appareil CRÉÉ nécessite une complétion manuelle
                    if self._needs_manual_completion(device_data):
                        results['manual_completion'] += 1
                else:
                    results['matches_found'] += 1

                self._collecter_candidat_similarite(
                    device_data, refs_pieces=[r for r, _ in references_and_labels])

                # Associer les références (chaque paire référence-libellé)
                for reference, label in references_and_labels:
                    if reference:
                        assoc_result = self._safe_create_association(reference, device_id, label)
                        if assoc_result:
                            if assoc_result.get('created'):
                                results['associations_created'] += 1
                                app_logger.debug(f"  ✨ Association créée: {reference} → {label} pour appareil {device_id}")
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
        completions = []  # (id, device_data, champs) : Type/Fabricant vides en base
        associations_batch = []
        processed_line_index = 0  # Compteur pour les lignes réellement traitées (hors continue)
        # 1ʳᵉ occurrence de chaque clé DANS CE FICHIER : {device_key: (data_index, existing_id)}.
        # Local au fichier, contrairement à seen_device_refs qui est partagé entre
        # fichiers — associations_batch et processed_line_index le sont aussi.
        first_occurrence_by_key = {}
        
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

            verdict, device_data, device_key = self._preparer_ligne(
                row, config, seen_device_refs, results, prefixe_log='BATCH ')

            if verdict == self.LIGNE_IGNOREE:
                continue

            if verdict == self.LIGNE_DOUBLON:
                # Rattacher l'association à la 1ʳᵉ occurrence. Si elle vient du même
                # fichier, on réutilise son (data_index, existing_id) : la mémoïsation
                # de _batch_create_associations réattribue alors le bon id SANS
                # consommer d'entrée de new_device_ids, y compris quand l'appareil
                # est encore en attente d'insertion. Sinon (doublon inter-fichiers),
                # on ne peut compter que sur un appareil déjà présent en base.
                first_occurrence = first_occurrence_by_key.get(device_key)
                if first_occurrence is not None:
                    dup_index, dup_existing_id = first_occurrence
                else:
                    dup_index = processed_line_index
                    dup_existing_id = self._find_in_cache(device_data, existing_devices_cache)
                if first_occurrence is not None or dup_existing_id:
                    for reference, label in references_and_labels:
                        if reference:
                            associations_batch.append((reference, label, dup_index, dup_existing_id))
                continue

            # Ligne à traiter : la résolution passe par le cache, pas par SQL
            # (le comptage de la ligne traitée est fait par _preparer_ligne)

            # Utiliser cache auto-complétion pour améliorer les données (pas de SQL!)
            self._apply_autocomplete_from_cache(device_data, autocomplete_cache)

            # Vérifier si existe en cache (pas de requête SQL !)
            existing_id = self._find_in_cache(device_data, existing_devices_cache)

            # Mémoriser la résolution de cette ligne pour d'éventuels doublons suivants
            if device_key:
                first_occurrence_by_key.setdefault(device_key, (processed_line_index, existing_id))

            if existing_id:
                # Appareil existant
                results['matches_found'] += 1
                device_data['id'] = existing_id   # pour la collecte des suggestions (ci-dessous)
                if self._needs_update(device_data):
                    existing_updates.append((existing_id, device_data))
                # Type/Fabricant vides en base : le cache filtre en amont, pour ne pas
                # émettre un UPDATE par appareil retrouvé sur un import de 90 000 lignes
                entree = existing_devices_cache.get(device_key) if device_key else None
                champs = self._champs_a_completer(device_data, entree) if entree else {}
                if champs:
                    completions.append((existing_id, device_data, champs))
                    if not dry_run:
                        entree.update(champs)  # cache partagé : fichiers suivants du lot
            else:
                # Nouvel appareil à créer (l'id sera réinjecté après insertion batch)
                results['new_entries'] += 1
                if self._needs_manual_completion(device_data):
                    results['manual_completion'] += 1
                new_devices_batch.append(device_data)

            self._collecter_candidat_similarite(
                device_data, actif=not dry_run,
                refs_pieces=[r for r, _ in references_and_labels])

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

            # Réinjecter l'id généré dans chaque device_data (additif) : nécessaire à la
            # collecte des suggestions par similarité (et sans effet sur le reste du flux).
            # new_device_ids est parallèle à new_devices_batch ; zip tronque si tailles diffèrent.
            for _dev_data, _new_id in zip(new_devices_batch, new_device_ids):
                _dev_data['id'] = _new_id
            self._tracer_autocompletions(
                (d['id'], d, None) for d in new_devices_batch[:len(new_device_ids)])

            app_logger.debug(f" BATCH: Mise à jour de {len(existing_updates)} appareils existants…")
            if existing_updates:
                self._batch_update_devices(existing_updates)
            self._completer_appareils_existants(completions)

            app_logger.debug(f" BATCH: Création de {len(associations_batch)} associations…")

            new_device_associations     = [a for a in associations_batch if not a[3]]
            existing_device_associations = [a for a in associations_batch if a[3]]
            unique_new      = set(a[2] for a in new_device_associations)
            unique_existing = set(a[2] for a in existing_device_associations)
            all_unique      = unique_new | unique_existing
            app_logger.info(f"Associations: {len(associations_batch)} total ({len(new_device_associations)} nouveaux + {len(existing_device_associations)} existants)")
            # Diagnostic, pas une vérification : les deux termes portent sur des
            # populations différentes. `total_imported` ne compte que les lignes
            # NOUVELLES (_preparer_ligne l'incrémente après avoir écarté ignorées et
            # doublons), tandis que `all_unique` recense les indices présents dans
            # associations_batch, doublons compris — rattachés à l'indice de leur 1ʳᵉ
            # occurrence, ou à `processed_line_index` si elle vient d'un autre fichier.
            # Or ce compteur n'avance qu'après les `continue` : sur un fichier 100 %
            # doublons il reste à 0, et la ligne affichait « 0 lignes traitées vs 1 »
            # alors que tout était normal. Sortait 192 fois en INFO sur l'import du
            # 2026-09-10, avec l'allure d'un échec — d'où le passage en debug.
            #
            # Le passage en debug l'a retirée de la console (handler INFO) mais pas de
            # detailed.log, dont le handler accepte DEBUG : le volume y restait inchangé.
            # D'où le garde LOG_VERBOSE_PER_DEVICE, déjà utilisé par _preparer_ligne pour
            # ses logs par-appareil — même intention, même levier : muet par défaut,
            # réactivable pour un diagnostic sans toucher au code.
            if Config.LOG_VERBOSE_PER_DEVICE:
                app_logger.debug(f" BATCH: {results['total_imported']} ligne(s) nouvelle(s), "
                                 f"{len(all_unique)} indice(s) de ligne portant des associations")

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
        """Pré-charger tous les appareils existants pour éviter les requêtes répétées.

        Lève DatabaseError si la lecture échoue : l'import s'arrête plutôt que de
        tourner sur un cache vide (cf. lire_appareils_pour_import).
        """
        rows = self.db_manager.lire_appareils_pour_import()

        # Conserver les lignes brutes pour le calcul des suggestions par similarité
        # (réutilise la même lecture — pas de requête supplémentaire). Les colonnes
        # (id, ref_modele, commercial_ref, type, manufacturer) suffisent : build_reference_index
        # ne lit que row[:5] et ignore other_ref/notes.
        self._existing_devices_rows_for_similarity = rows

        cache = {}
        for row in rows:
            device_id, ref_modele, commercial_ref, device_type, manufacturer, other_ref, notes = row

            # Indexer par ref_modele + commercial_ref pour recherche rapide.
            #
            # v3.65.1 — la garde était `and` alors que la requête SQL ci-dessus
            # sélectionne en `OR` : tout appareil mono-référence (ref_modele SANS
            # commercial_ref, ou l'inverse) était chargé depuis la base puis jeté
            # ici. Il n'entrait donc JAMAIS dans le cache, et un ré-import du même
            # lot le recréait au lieu de le retrouver (bug constaté le 2026-09-01 :
            # 2ᵉ import de 60 lignes → 60 nouveaux appareils au lieu de 60 matches).
            #
            # La clé reste la composite `ref|commercial_ref` : « WW001| » ne peut pas
            # matcher « WW001|CR001 ». Un appareil partiel ne correspond donc qu'à un
            # autre appareil partiel, jamais à un appareil complet — la sévérité de
            # _insert_or_find_device (« évite 2108002 vs 2108002000 ») est préservée.
            if ref_modele or commercial_ref:
                key = f"{(ref_modele or '').lower()}|{(commercial_ref or '').lower()}"
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

    def _compute_pending_similarity_suggestions(self, progress_cb=None) -> Dict[int, list]:
        """Suggestions Type/Marque des lignes restées incomplètes : similarité de
        référence, complétée par le type de la pièce importée. Jamais d'écriture,
        jamais d'échec d'import (chaque étape attrape ses erreurs)."""
        suggestions = self._suggestions_par_similarite(progress_cb=progress_cb)
        return self._ajouter_suggestions_type_piece(suggestions)

    def _ajouter_suggestions_type_piece(self, suggestions: Dict[int, list]) -> Dict[int, list]:
        """Ajoute, pour chaque ligne SANS type, le type que portent déjà au moins
        TYPE_PIECE_PART_MIN des appareils de sa pièce (au moins
        TYPE_PIECE_APPAREILS_MIN appareils typés).

        Fusion avec la similarité : si un candidat propose déjà ce type, rien
        n'est ajouté ; sinon le candidat « pièce » s'ajoute en concurrent (la
        fenêtre de validation ne pré-coche alors plus la ligne).
        """
        from .config import Config
        if not Config.ENABLE_TYPE_PIECE_SUGGESTION:
            return suggestions
        refs_par_ligne = getattr(self, '_refs_pieces_candidats', None) or {}
        if not refs_par_ligne:
            return suggestions
        try:
            from ..services.reference_similarity_service import fusionner_type_piece
            lignes = [d for d in getattr(self, '_pending_similarity_candidates', [])
                      if d.get('id') and not (d.get('type') or '').strip()
                      and id(d) in refs_par_ligne]
            if not lignes:
                return suggestions
            types_par_ref = self.db_manager.compter_types_par_piece(
                r for d in lignes for r in refs_par_ligne[id(d)])

            ajoutees = 0
            for d in lignes:
                fusion = fusionner_type_piece(
                    suggestions.get(d['id'], []), refs_par_ligne[id(d)], types_par_ref,
                    Config.TYPE_PIECE_PART_MIN, Config.TYPE_PIECE_APPAREILS_MIN)
                if fusion is None:
                    continue          # pas de type dominant, ou déjà proposé
                suggestions[d['id']] = fusion
                ajoutees += 1
            app_logger.info(f"Suggestions « type de la pièce » : {ajoutees} appareil(s) "
                            f"sur {len(lignes)} ligne(s) sans type")
            return suggestions
        except Exception as e:
            app_logger.error(f"Suggestions « type de la pièce » échouées (non bloquant) : {e}")
            return suggestions

    def _suggestions_par_similarite(self, progress_cb=None) -> Dict[int, list]:
        """Calcule les suggestions Type/Marque par similarité pour les lignes
        restées incomplètes après le mécanisme exact (collectées pendant la boucle
        d'import dans self._pending_similarity_candidates).

        ADDITIF, aucune écriture : ne fait que proposer. Ne doit JAMAIS faire
        échouer un import (try/except interne, retourne {} en cas de souci).

        :param progress_cb: callable(value, maximum, label) optionnel — rend la phase
            visible dans la ProgressDialog (sinon la barre semble figée → "planté").

        Returns:
            Dict[db_id, List[dict]] — candidats par appareil (SimilarityCandidate.to_dict()).
        """
        from .config import Config
        if not Config.ENABLE_SIMILARITY_SUGGESTIONS:
            return {}
        if not getattr(self, '_pending_similarity_candidates', None):
            return {}
        try:
            from ..services.reference_similarity_service import ReferenceSimilarityService
            # Index = appareils déjà en base + Levier 1 : frères COMPLETS du lot en
            # cours (id réinjecté après insertion), au format attendu
            # (db_id, ref_modele, commercial_ref, type, manufacturer). Les frères du
            # lot suffisent à eux seuls même si la base est vide pour ce préfixe.
            rows = list(getattr(self, '_existing_devices_rows_for_similarity', None) or [])
            for dev in getattr(self, '_imported_complete_for_similarity', []):
                dev_id = dev.get('id')
                if dev_id:
                    rows.append((dev_id, dev.get('ref_modele', ''),
                                 dev.get('commercial_ref', ''),
                                 dev.get('type', ''), dev.get('manufacturer', '')))
            if not rows:
                return {}
            # Coût réel dominant : construire l'index (tous les appareils de la base,
            # potentiellement plusieurs centaines de milliers de lignes) prend souvent
            # plus longtemps que la boucle de recherche elle-même (quelques lignes
            # incomplètes) — sans ce libellé, cette étape était totalement silencieuse.
            if progress_cb:
                progress_cb(0, len(self._pending_similarity_candidates) or 1,
                            "Préparation de l'index de suggestions…")
            reference_index = ReferenceSimilarityService.build_reference_index(rows)
            service = ReferenceSimilarityService(
                allow_numeric_fuzzy=Config.SIMILARITY_ALLOW_NUMERIC_FUZZY,
                fuzzy_threshold=Config.SIMILARITY_FUZZY_THRESHOLD,
                enable_prefix_consensus=Config.SIMILARITY_PREFIX_CONSENSUS,
                enforce_shape_compatibility=Config.SIMILARITY_ENFORCE_SHAPE,
                enforce_code_group=Config.SIMILARITY_GROUPE_CODE,
            )
            suggestions_by_db_id: Dict[int, list] = {}
            total_pending = len(self._pending_similarity_candidates)
            # Throttle des mises à jour de progression : ~1 % ou tous les 50 items
            # (au moins 1), pour ne pas saturer le signal sur de gros volumes.
            step = max(1, total_pending // 100, 50)
            if progress_cb:
                progress_cb(0, total_pending,
                            f"Recherche de suggestions… (0/{total_pending})")
            for idx, device_data in enumerate(self._pending_similarity_candidates):
                db_id = device_data.get('id')
                if not db_id:
                    continue
                candidates = service.find_candidates(
                    ref_modele=device_data.get('ref_modele', ''),
                    commercial_ref=device_data.get('commercial_ref', ''),
                    reference_index=reference_index,
                    exclude_db_id=db_id,
                )
                if candidates:
                    suggestions_by_db_id[db_id] = [c.to_dict() for c in candidates]
                if progress_cb and (idx % step == 0 or idx == total_pending - 1):
                    done = idx + 1
                    progress_cb(done, total_pending,
                                f"Recherche de suggestions… ({done}/{total_pending})")
            app_logger.info(
                f"Suggestions par similarité : {len(suggestions_by_db_id)} appareil(s) "
                f"sur {len(self._pending_similarity_candidates)} ligne(s) incomplète(s)"
            )
            return suggestions_by_db_id
        except Exception as e:
            app_logger.error(f"Calcul des suggestions de similarité échoué (non bloquant): {e}")
            return {}

    def _build_autocomplete_cache(self, existing_devices_cache: Dict[str, Dict]) -> Dict[str, Dict[str, str]]:
        """Construire un cache pour l'auto-complétion (Type + Fabricant par référence)"""
        autocomplete_cache = {}
        # Même règle que _try_auto_complete : pas d'auto-complété non vérifié comme source
        lignes = self.db_manager.execute_query(
            "SELECT DISTINCT appareil_id FROM appareils_autocompletes") or []
        non_verifies = {ligne[0] for ligne in lignes}

        for key, device in existing_devices_cache.items():
            if device.get('id') in non_verifies:
                continue
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
                        'manufacturer': manufacturer,
                        'source': ref_modele or commercial_ref,
                    }
                
                # Indexer par commercial_ref si disponible et différent
                if commercial_ref and commercial_ref.lower() != ref_modele.lower():
                    autocomplete_cache[commercial_ref.lower()] = {
                        'type': device_type,
                        'manufacturer': manufacturer,
                        'source': ref_modele or commercial_ref,
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
            # Le cache ne garde qu'un appareil par référence : confiance inconnue
            for champ in self.CHAMPS_COMPLETABLES:
                if not (device_data.get(champ) or '').strip() and cache_entry.get(champ):
                    device_data[champ] = cache_entry[champ]
                    self._noter_autocompletion(device_data, champ, cache_entry[champ],
                                               cache_entry.get('source'), None, None)
    
    def _find_in_cache(self, device_data: Dict[str, Any], cache: Dict[str, Dict]) -> Optional[int]:
        """Trouver un appareil dans le cache (pas de SQL!)

        v3.65.1 — garde passée de `and` à `or`, symétriquement à
        _preload_existing_devices : une ligne mono-référence ne tentait même pas la
        recherche. La clé composite est identique à celle de _build_device_key, donc
        les trois notions d'identité (clé de dédup, construction du cache, lecture du
        cache) sont désormais alignées sur la même condition.
        """
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()

        if ref_modele or commercial_ref:
            key = f"{ref_modele.lower()}|{commercial_ref.lower()}"
            if key in cache:
                return cache[key]['id']

        return None
    
    def _needs_update(self, device_data: Dict[str, Any]) -> bool:
        """Vérifier si l'appareil a besoin d'une mise à jour (3ème colonne)"""
        return bool(device_data.get('other_ref') or device_data.get('notes'))

    # Champs qu'un import peut compléter sur un appareil existant — jamais écraser
    CHAMPS_COMPLETABLES = ('type', 'manufacturer')

    def _champs_a_completer(self, device_data: Dict[str, Any],
                            valeurs_base: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Type/Fabricant de la ligne (lus dans le fichier ou auto-complétés) à
        reporter sur un appareil existant.

        Jusqu'en v3.88.1, ils n'étaient jamais écrits : `_update_existing_device`
        et `_batch_update_devices` ne portent que la 3ᵉ colonne. L'appareil vide
        restait vide, et comme la ligne paraissait complète en mémoire, il n'était
        pas non plus proposé en suggestion.

        Args:
            valeurs_base: Type/Fabricant connus en base (cache du chemin batch) ; un
                champ déjà renseigné est écarté. None : la garde SQL tranche seule.
        """
        champs = {}
        for champ in self.CHAMPS_COMPLETABLES:
            valeur = (device_data.get(champ) or '').strip()
            if not valeur:
                continue
            if valeurs_base is not None and (valeurs_base.get(champ) or '').strip():
                continue
            champs[champ] = valeur
        return champs

    # Clé privée de device_data : provenance des champs auto-complétés. Sans effet
    # sur les insertions, qui lisent les colonnes une à une (DB_HEADERS, get).
    CLE_AUTOCOMPLETION = '_autocompletion'

    def _noter_autocompletion(self, device_data: Dict[str, Any], champ: str, valeur: str,
                              source: Optional[str], accord: Optional[int],
                              total: Optional[int]) -> None:
        """Retenir d'où vient un champ auto-complété, en attendant l'id de l'appareil.

        accord/total : appareils sources donnant cette valeur / appareils sources
        trouvés (« 1/2 »). None quand la source n'en dit rien (cache du batch).
        """
        device_data.setdefault(self.CLE_AUTOCOMPLETION, {})[champ] = {
            'valeur': valeur, 'source': source or '', 'accord': accord, 'total': total}

    def _tracer_autocompletions(self, appareils) -> None:
        """Inscrire dans appareils_autocompletes les champs auto-complétés ÉCRITS.

        Args:
            appareils: (appareil_id, device_data, champs_ecrits). champs_ecrits None :
                appareil créé, tous ses champs auto-complétés ont été insérés. Sinon,
                seuls ceux réellement écrits (et de même valeur) sont tracés — un
                champ déjà renseigné en base n'a rien reçu.
        Appelée après l'écriture : le déclencheur effacerait sinon la trace.
        """
        enregistrer = getattr(self.db_manager, 'enregistrer_autocompletions', None)
        if enregistrer is None:
            return
        horodatage = (getattr(self, '_horodatage_import', None)
                      or datetime.now().isoformat(sep=' ', timespec='seconds'))
        lignes = []
        for appareil_id, device_data, champs in appareils:
            for champ, prov in (device_data.get(self.CLE_AUTOCOMPLETION) or {}).items():
                ecrit = (device_data.get(champ) if champs is None else champs.get(champ)) or ''
                if not appareil_id or ecrit.strip() != (prov['valeur'] or '').strip():
                    continue
                lignes.append((appareil_id, champ, prov['valeur'], prov['source'],
                               prov['accord'], prov['total'], horodatage))
        if lignes and enregistrer(lignes):
            traces = getattr(self, '_appareils_autocompletes', None)
            if traces is not None:
                traces.update(ligne[0] for ligne in lignes)

    def _completer_appareils_existants(
            self, completions: List[Tuple[int, Dict[str, Any], Dict[str, str]]]) -> int:
        """Écrire les champs vides des appareils existants, commun aux deux chemins.

        La garde WHERE des requêtes refuse d'écraser une valeur : seules les
        écritures effectives (rowcount) sont tracées dans `_completions_existants`,
        restitué en fin d'import dans results['appareils_completes'] pour le bloc
        d'historique. Un même appareil touché par plusieurs fichiers n'y figure
        qu'une fois.

        Returns:
            Nombre d'appareils effectivement complétés.
        """
        if not completions:
            return 0
        from .config import Config
        requetes = {'type': Config.QUERIES['complete_device_type'],
                    'manufacturer': Config.QUERIES['complete_device_manufacturer']}

        faits = []
        conn = self.db_manager.get_connection()
        # _query_lock : accès brut à la connexion partagée depuis _ImportWorker → sérialiser.
        with self.db_manager._query_lock:
            cursor = conn.cursor()
            try:
                for device_id, device_data, champs in completions:
                    ecrits = {}
                    for champ, valeur in champs.items():
                        cursor.execute(requetes[champ], (valeur, device_id))
                        if cursor.rowcount:
                            ecrits[champ] = valeur
                    if ecrits:
                        faits.append((device_id, device_data, ecrits))
                conn.commit()
            except Exception as e:
                conn.rollback()
                app_logger.error(f"Complétion des appareils existants échouée : {e}")
                return 0

        self._tracer_autocompletions(faits)
        if not hasattr(self, '_completions_existants'):
            self._completions_existants = {}
        for device_id, device_data, ecrits in faits:
            trace = self._completions_existants.setdefault(device_id, {
                'id': device_id,
                'ref_modele': (device_data.get('ref_modele') or '').strip(),
                'commercial_ref': (device_data.get('commercial_ref') or '').strip(),
            })
            trace.update(ecrits)
        return len(faits)

    def _batch_insert_devices(self, devices_batch: List[Dict[str, Any]]) -> List[int]:
        """Insertion en lot des nouveaux appareils avec chunking optimisé"""
        if not devices_batch:
            return []
        
        from .config import Config
        query = Config.QUERIES['insert_device_batch']
        chunk_size = Config.BATCH_INSERT_SIZE
        
        
        # Utiliser une transaction globale pour l'efficacité.
        # _query_lock : ce code tourne sur le thread _ImportWorker et accède à la
        # connexion partagée en mode brut (get_connection) — il DOIT être sérialisé
        # avec les accès du thread principal pour éviter la corruption du WAL.
        conn = self.db_manager.get_connection()
        all_new_ids = []

        with self.db_manager._query_lock:
            cursor = conn.cursor()
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
                            app_logger.debug(f"[ERR] Chunk {i//chunk_size + 1}: Impossible de récupérer l'ID pour un appareil")
                            conn.rollback()
                            return []

                    all_new_ids.extend(chunk_ids)
                    app_logger.debug(f"[OK] Chunk {i//chunk_size + 1}: {len(chunk_ids)} appareils insérés")

                conn.commit()
                # Insertion en lot via cursor brut (hors des méthodes normales de
                # DatabaseManager) : invalider explicitement le cache de comptage,
                # sinon count_data() sans filtre (utilisé par load_data() post-import)
                # continue de renvoyer le total d'avant import.
                self.db_manager.invalidate_search_cache(invalidate_total_count=True)
                app_logger.debug(f"[OK] BATCH FINAL: {len(all_new_ids)} appareils insérés au total")
                return all_new_ids

            except Exception as e:
                conn.rollback()
                app_logger.debug(f"[ERR] BATCH: Erreur insertion: {e}")
                app_logger.debug(f"[ERR] BATCH: IDs partiels récupérés avant erreur: {len(all_new_ids)}")
                import traceback
                app_logger.debug(f"[ERR] BATCH: Stack trace: {traceback.format_exc()}")
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

        # _query_lock : accès brut à la connexion partagée depuis _ImportWorker → sérialiser.
        with self.db_manager._query_lock:
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
                app_logger.debug(f"[ERR] BATCH: Erreur mise à jour: {e}")
    
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
                    app_logger.debug(f"[!] BATCH: Pas assez d'IDs pour les nouveaux appareils (index {data_index})")
                    continue
            
            assoc_result = self._safe_create_association(reference, device_id, label)
            if assoc_result:
                if assoc_result.get('created'):
                    results['created'] += 1
                else:
                    results['existing'] += 1
        
        app_logger.debug(f" BATCH: Associations - Créées: {results['created']}, Existantes: {results['existing']}")
        return results
    
    @staticmethod
    def _build_device_key(device_data: Dict[str, Any]) -> Tuple[str, str, str]:
        """Clé d'identité d'un appareil pour la détection de doublons.

        Dérivée des données DÉJÀ parsées par `_parse_row_data`, donc du mapping de
        colonnes réellement appliqué. Avant v3.64.1 la clé était recalculée par
        position (`row[0]`/`row[1]`) en ignorant le mapping : sur un collage
        « Type | Marque | Référence », toutes les lignes recevaient la même clé
        (ex. « lave-linge|samsung ») et 309 lignes sur 310 étaient jetées comme
        doublons (bug constaté le 2026-09-01).

        Returns:
            (ref_modele, commercial_ref, device_key)
        """
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()
        return ref_modele, commercial_ref, f"{ref_modele.lower()}|{commercial_ref.lower()}"

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
            self._normaliser_casse(data)
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

        self._normaliser_casse(data)

        # Appliquer l'autocomplétion si Type ou Fabricant sont manquants
        if data and (not data.get('type') or not data.get('manufacturer')):
            self._try_auto_complete(data)
        
        return data
    
    def _normaliser_casse(self, data: Dict[str, Any]) -> None:
        """Marque et type importés réécrits selon la base (« DELTA » → « Delta »),
        avant l'auto-complétion. Commun aux deux modes de parsing, donc aux deux
        chemins."""
        if data.get('manufacturer'):
            data['manufacturer'] = self._marques.normaliser(data['manufacturer'])
        if data.get('type'):
            data['type'] = self._types.normaliser(data['type'])

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
            app_logger.debug(f" Appareil {device_id} mis à jour avec 3ème colonne: {update_data}")
    
    def _completer_existant(self, device_id: int, device_data: Dict[str, Any]) -> None:
        """Chemin standard : la garde SQL tient lieu du cache du chemin batch."""
        champs = self._champs_a_completer(device_data)
        if champs:
            self._completer_appareils_existants([(device_id, device_data, champs)])

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur insertion appareil")
    def _insert_or_find_device(self, device_data: Dict[str, Any],
                               completer: bool = True) -> Optional[int]:
        """Insérer ou trouver un appareil existant.

        Un appareil retrouvé reçoit la 3ᵉ colonne (other_ref / notes) de la ligne et
        son Type/Fabricant là où il est vide en base — seulement à la 1ʳᵉ occurrence
        de la ligne (`completer`), comme sur le chemin batch : sur un doublon, la
        première valeur l'emporte.

        La résolution reproduit exactement la clé composite du chemin batch
        (_find_in_cache) : une ligne complète ne correspond qu'à un appareil
        complet, une ligne partielle qu'à un appareil partiel de même forme.
        Verrouillé par tests/unit/test_import_paths_equivalence.py.
        """
        # Import hissé en tête : un « from .config import Config » plus bas
        # rendrait Config local à TOUTE la fonction (piège connu du projet).
        from .config import Config

        # Chercher d'abord un appareil existant
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()

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

            existing_id = results[0][0] if results else None

            # Repli « ref_modele seule » — ne s'applique QUE si la ligne entrante est
            # elle-même partielle. Sans cette garde, une ligne COMPLÈTE se rattachait
            # à un appareil partiel existant et sa référence commerciale était perdue :
            # 2 appareils au lieu de 3 sur le chemin standard, 3 sur le chemin batch
            # (divergence B mesurée en v3.69.1). La doctrine v3.66.1 — « un appareil
            # partiel ne correspond qu'à un autre appareil partiel » — est ainsi tenue.
            if existing_id is None and ref_modele and not commercial_ref:
                search_query_ref = """
                    SELECT id FROM appareils
                    WHERE ref_modele = ? AND ref_modele != ''
                       AND (commercial_ref = '' OR commercial_ref IS NULL)
                    LIMIT 1
                """
                results_ref = self.db_manager.execute_query(search_query_ref, [ref_modele])
                if results_ref:
                    existing_id = results_ref[0][0]

            # Cas miroir : seule commercial_ref correspond (v3.65.1).
            #
            # Ce repli n'existait pas : un lot ne renseignant QUE commercial_ref
            # n'était retrouvé par aucune des deux requêtes ci-dessus (la 1ʳᵉ exige
            # les deux références non vides, la 2ᵉ exige ref_modele). Chaque
            # ré-import recréait donc les appareils. Trou symétrique du bug du
            # chemin batch corrigé dans _preload_existing_devices / _find_in_cache.
            #
            # Garde symétrique du repli ci-dessus : les deux sont désormais
            # mutuellement exclusifs (l'un exige commercial_ref vide, l'autre
            # ref_modele vide), il n'y a donc plus de priorité à arbitrer.
            if existing_id is None and commercial_ref and not ref_modele:
                search_query_com = """
                    SELECT id FROM appareils
                    WHERE commercial_ref = ? AND commercial_ref != ''
                       AND (ref_modele = '' OR ref_modele IS NULL)
                    LIMIT 1
                """
                results_com = self.db_manager.execute_query(search_query_com, [commercial_ref])
                if results_com:
                    existing_id = results_com[0][0]

            # Appareil retrouvé, quelle que soit la recherche qui l'a trouvé (v3.88.4).
            # Jusqu'en v3.88.2, seule la recherche stricte écrivait la 3ᵉ colonne : les
            # replis mono-référence la perdaient (le batch l'écrit pour tout appareil
            # existant), et un doublon la réécrivait — dernière valeur gagnante contre
            # première sur le batch, qui ne traite pas les doublons.
            if existing_id is not None:
                if completer:
                    self._update_existing_device(existing_id, device_data)
                    self._completer_existant(existing_id, device_data)
                return existing_id

        # Créer un nouvel appareil.
        # Champs absents complétés à '' — exactement ce que fait _batch_insert_devices
        # avec ses device.get(champ, ''). Sans cela le chemin standard n'insérait que
        # les colonnes présentes et laissait SQLite écrire NULL, si bien que
        # « WHERE type = '' » ne ramenait pas les mêmes lignes selon la taille du
        # fichier importé (divergence A mesurée en v3.69.1).
        # Copie et non mutation : device_data sert ensuite à la collecte des
        # suggestions par similarité, que le chemin batch ne modifie pas non plus.
        donnees_insert = {entete: device_data.get(entete, '') for entete in Config.DB_HEADERS}
        device_id = self.db_manager.insert_appareil(donnees_insert)
        if device_id:
            device_data['is_new'] = True
            self._tracer_autocompletions([(device_id, device_data, None)])
        return device_id
    
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur auto-completion")
    def _try_auto_complete(self, appareil_data: dict) -> bool:
        """Compléter automatiquement Type et Fabricant à partir des références.
        Correspondance exacte uniquement sur les références non vides.
        Sélectionne la combinaison type+fabricant la plus fréquente en base.

        Returns:
            bool: True si au moins un champ a été complété
        """
        from .config import Config

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
        # Toutes les combinaisons, et non plus la seule gagnante (LIMIT 1) : leur
        # répartition donne l'indice de confiance tracé (v3.89.0). Le départage
        # des ex aequo par valeur rend le choix reproductible.
        # Un appareil auto-complété non encore vérifié ne sert pas de source : sa
        # valeur n'est qu'une déduction, et le chemin standard, qui écrit au fil de
        # l'eau, la recompterait aussitôt (confiance gonflée, « 3/3 » pour « 1/1 »).
        query = f"""
            SELECT type, manufacturer, COUNT(*) as freq,
                   MIN(COALESCE(NULLIF(ref_modele, ''), commercial_ref)) AS exemple
            FROM appareils
            WHERE ({where_clause})
              AND type IS NOT NULL AND type != ''
              AND manufacturer IS NOT NULL AND manufacturer != ''
              AND id NOT IN (SELECT appareil_id FROM appareils_autocompletes)
            GROUP BY type, manufacturer
            ORDER BY freq DESC, type, manufacturer
        """

        results = self.db_manager.execute_query(query, params)

        if results:
            found_type, found_manufacturer, _, exemple = results[0][:4]
            total = sum(r[2] for r in results)
            # Agrégé plutôt qu'unitaire (v3.66.0) : ces deux messages représentaient
            # à eux seuls ~550 000 lignes de log, soit le premier poste de volume.
            # Le total est journalisé une fois en fin d'import (_log_resume_import).
            if type_empty:
                appareil_data['type'] = found_type
                self._noter_autocompletion(
                    appareil_data, 'type', found_type, exemple,
                    sum(r[2] for r in results if r[0] == found_type), total)
                self._log_counters['autocomplete_type'] += 1
                if Config.LOG_VERBOSE_PER_DEVICE:
                    app_logger.debug(f"  [OK] Type complété: '' -> '{found_type}'")
            if manufacturer_empty:
                appareil_data['manufacturer'] = found_manufacturer
                self._noter_autocompletion(
                    appareil_data, 'manufacturer', found_manufacturer, exemple,
                    sum(r[2] for r in results if r[1] == found_manufacturer), total)
                self._log_counters['autocomplete_manufacturer'] += 1
                if Config.LOG_VERBOSE_PER_DEVICE:
                    app_logger.debug(f"  [OK] Fabricant complété: '' -> '{found_manufacturer}'")
            return True

        return False

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mises à jour post-import")
    def _trigger_post_import_updates(self):
        """Déclencher les mises à jour post-import (Phase 4 - EventDrivenSaveService)"""
        # Déclencher la sauvegarde événementielle
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
