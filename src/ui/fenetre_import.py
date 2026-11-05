"""
Fenêtres de l'import : configuration (ImportDialog et ses groupes de mapping) et
aperçu avant écriture (ImportPreviewDialog).

Déplacées telles quelles depuis src/core/import_manager.py : la couche cœur ne
garde que la logique d'import (ImportManager, modèles de configuration, workers).
"""

from typing import List, Dict, Optional, Tuple
import unicodedata

from PyQt5.QtWidgets import QLayout
from ..utils.qt_imports import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCheckBox,
    QTextEdit,
    QGroupBox,
    QScrollArea,
    QWidget,
    QGridLayout,
    Qt,
    QTimer,
    QCompleter,
    QStringListModel,
    QSizePolicy,
    QSize,
    QSplitter,
    pyqtSignal
)

from .style_manager import StyleManager
from .ref_chips_input import RefChipsInput
from ..core.logger import app_logger
from ..core.import_manager import FileType, ImportConfiguration, ImportType, LabelConfiguration
from ..utils.error_handler import handle_ui_operation_errors


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
                StyleManager.TEXTE_ERREUR_PETIT
            )
            outer.addWidget(self._status_label)

        # Tableau de mapping
        self._mapping_widget = QWidget()
        self._mapping_widget.setStyleSheet(
            StyleManager.CADRE_GRIS_CLAIR
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
                    StyleManager.TEXTE_ERREUR_PETIT
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
        self.format_info_label.setStyleSheet(StyleManager.TEXTE_GRAS)
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
        self.third_col_label.setStyleSheet(StyleManager.TEXTE_GRAS)
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
            ref_lbl.setStyleSheet(StyleManager.TEXTE_GRAS)
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
            desc_lbl2.setStyleSheet(StyleManager.TEXTE_GRAS)
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
            ref_row_lbl.setStyleSheet(StyleManager.TEXTE_GRAS)
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
            desc_row_lbl.setStyleSheet(StyleManager.TEXTE_GRAS)
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
            self._obsolete_checkbox.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
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
            self._remplacee_par_inputs = []

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
                StyleManager.CADRE_GRIS_CLAIR
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
            lbl1.setStyleSheet(StyleManager.TEXTE_GRAS_TRANSPARENT)
            lbl1.setFixedWidth(220)
            row1.addWidget(lbl1)
            self.succ_replaces_input = RefChipsInput("Anciennes réfs remplacées par cette réf, séparées par un espace (ex : REF123 REF124)", max_refs=None)
            self.succ_replaces_input.setMinimumHeight(30)
            row1.addWidget(self.succ_replaces_input)
            succ_layout.addLayout(row1)

            row2 = QHBoxLayout()
            lbl2 = QLabel("Cette réf. est remplacée par :")
            lbl2.setStyleSheet(StyleManager.TEXTE_GRAS_TRANSPARENT)
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
            lbl3.setStyleSheet(StyleManager.TEXTE_GRAS_TRANSPARENT)
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
            self._remplacee_par_inputs = []

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
            scroll_area.setStyleSheet(StyleManager.ZONE_DEFILEMENT_NUE)
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
                ref_input_edit.textChanged.connect(self._pousser_cartes_relations)
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
                StyleManager.LIBELLE_PETIT_TRANSPARENT
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
                obs_check.stateChanged.connect(self._pousser_cartes_relations)
                row2.addWidget(obs_check)

            card_layout.addLayout(row2)
            if self.import_config.import_type == ImportType.MULTI_FILE:
                card_layout.addLayout(self._ligne_remplacee_par(file, obs_check))
            self.individual_refs_widget.addWidget(file_container)

        # Initialiser l'affichage des références selon l'état par défaut de la case à cocher
        self._update_references_display()

        # Autocomplétion pour les champs de succession (fichier unique)
        self._setup_succession_autocomplete()
        self._pousser_cartes_relations()
    
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
                rows = self.import_manager.db_manager.lister_refs_pieces() or []
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
            rows = self.import_manager.db_manager.lister_refs_pieces() or []
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
        btn.setStyleSheet(StyleManager.FLAT_TRANSPARENT_BUTTON)
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
        self._pousser_cartes_relations()
    
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

        # Blocage : remplacements contradictoires (deux remplaçantes pour une réf,
        # boucle). Rien de sensé à « importer quand même » : la base garderait la
        # dernière remplaçante écrite, ou refuserait la boucle en silence.
        conflits = self._conflits_remplacement(config)
        if conflits:
            self._signaler_conflits_remplacement(conflits)
            return

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
            config.individual_references[file.path] = self._ref_du_fichier(file, auto_references_enabled)

            # Libellé = ce que tape l'utilisateur (peut être vide)
            desc_input = self.findChild(QLineEdit, f"desc_{file.path}")
            if desc_input:
                user_label = desc_input.text().strip()
                config.individual_labels[file.path] = user_label if user_label else ""

    def _ref_du_fichier(self, file, auto_references_enabled):
        """Référence de pièce d'un fichier : champ éditable pour le collage, sinon
        déduite du nom de fichier (si l'option automatique est cochée)."""
        if file.type == FileType.CLIPBOARD:
            ref_input_edit = self.findChild(QLineEdit, f"ref_input_{file.path}")
            return ref_input_edit.text().strip() if ref_input_edit else ""
        if auto_references_enabled:
            return file.suggested_reference
        return ""

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
            config.relations_groups = self._relations_groups_zone.groups()
            config.relations_cards = self._cartes_relations(config.individual_references)

        # Obsolète — fichier unique
        if self._obsolete_checkbox is not None and self._obsolete_checkbox.isChecked():
            ref = config.common_reference or (
                config.individual_references.get(config.files[0].path, '') if config.files else ''
            )
            if ref:
                config.obsolete_refs.append(ref)

    def _cartes_relations(self, refs_par_fichier):
        """Données des cartes de fichiers (multi-fichiers) : Obsolète et
        « Remplacée par », une CardData par réf (sans doublon, ordre des fichiers).
        Source unique du récap en direct et de la configuration d'import."""
        from ..services.import_relations import CardData
        obs_by_ref, rempl_by_ref = {}, {}
        for obs_check, file in (getattr(self, '_obsolete_checkboxes', None) or []):
            ref = refs_par_fichier.get(file.path, '') or ''
            if ref:
                obs_by_ref[ref] = obs_check.isChecked()
        for chips, file in (getattr(self, '_remplacee_par_inputs', None) or []):
            ref = refs_par_fichier.get(file.path, '') or ''
            nouvelle = next(iter(chips.refs()), None)
            if ref and nouvelle:
                rempl_by_ref[ref] = nouvelle
        seen, cards = set(), []
        for ref in refs_par_fichier.values():
            if ref and ref not in seen:
                seen.add(ref)
                cards.append(CardData(ref=ref, is_obsolete=obs_by_ref.get(ref, False),
                                      replaced_by=rempl_by_ref.get(ref)))
        return cards

    def _pousser_cartes_relations(self, *_):
        """Transmettre l'état des cartes à la zone de relations (récap + alertes)."""
        zone = getattr(self, '_relations_groups_zone', None)
        if zone is None:
            return
        auto = self.auto_file_references_checkbox.isChecked()
        refs = {f.path: self._ref_du_fichier(f, auto) for f in self.import_config.files}
        zone.set_cards(self._cartes_relations(refs))

    def _sur_remplacee_par_change(self, chips, obs_check):
        """Une réf remplacée devient obsolète : la case est cochée et verrouillée
        tant qu'une remplaçante est saisie, puis rendue dans son état d'avant."""
        if chips.refs():
            if obs_check.isEnabled():
                obs_check.setProperty("etat_avant_remplacement", obs_check.isChecked())
                obs_check.setChecked(True)
                obs_check.setEnabled(False)
                obs_check.setToolTip("Obsolète d'office : cette réf est remplacée.")
        elif not obs_check.isEnabled():
            obs_check.setEnabled(True)
            obs_check.setChecked(bool(obs_check.property("etat_avant_remplacement")))
            obs_check.setToolTip("Marquer cette référence comme obsolète (plus fabriquée)")
        self._pousser_cartes_relations()

    def _remplacante_comme_courante(self, file, ref):
        """Double-clic sur la pastille « Remplacée par » : la réf devient la
        courante de la lignée du fichier (évite de la saisir une 2ᵉ fois)."""
        zone = getattr(self, '_relations_groups_zone', None)
        if zone is None:
            return
        auto = self.auto_file_references_checkbox.isChecked()
        zone.definir_courante(self._ref_du_fichier(file, auto), ref)

    def _ligne_remplacee_par(self, file, obs_check):
        """Ligne « ↳ Remplacée par » d'une carte multi-fichiers (v3.97.0) :
        remplaçante DIRECTE de la réf du fichier (1 réf : lot, base ou nouvelle,
        créée alors en fantôme). Elle peut elle-même être l'ancienne version
        d'une lignée : c'est ce qui permet A → B → C sans perdre B."""
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel("↳ Remplacée par :")
        lbl.setStyleSheet(StyleManager.LIBELLE_PETIT_TRANSPARENT)
        lbl.setFixedWidth(100)
        row.addWidget(lbl)
        chips = RefChipsInput("Remplaçante directe (saisir ou glisser une réf)", max_refs=1,
                               accepte_depot=True)
        chips.setToolTip(
            "Nouvelle réf. qui remplace directement celle de ce fichier.\n"
            "Une seule : une pièce n'est remplacée que par une autre.\n"
            "Glissez ici une tuile (réf du lot, de la base ou fantôme).\n"
            "Double-clic sur la réf saisie : elle devient la courante de la lignée.\n"
            "Glissez ensuite ce fichier dans une lignée : sa remplaçante y sera\n"
            "raccordée à la courante, sans la ressaisir.")
        if getattr(self, '_remplacee_par_model', None) is None:
            lot = [f.suggested_reference for f in self.import_config.files
                   if getattr(f, 'suggested_reference', '')]
            base = (self._relations_base_model.stringList()
                    if getattr(self, '_relations_base_model', None) is not None else [])
            vus = set()
            refs = [r for r in lot + base if r and not (r in vus or vus.add(r))]
            # Référence persistante sur le modèle (piège GC du QCompleter)
            self._remplacee_par_model = QStringListModel(refs, self)
        completer = QCompleter(self._remplacee_par_model, chips)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        chips.setCompleter(completer)
        chips.changed.connect(lambda: self._sur_remplacee_par_change(chips, obs_check))
        chips.pastille_double_cliquee.connect(
            lambda ref, f=file: self._remplacante_comme_courante(f, ref))
        self._remplacee_par_inputs.append((chips, file))
        row.addWidget(chips, 1)
        return row

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

    def _conflits_remplacement(self, config) -> List[str]:
        """Remplacements contradictoires déclarés (multi-fichiers), vide sinon."""
        if config.relations_groups is None and config.relations_cards is None:
            return []
        from ..services.import_relations import conflits_remplacement
        return conflits_remplacement(config.relations_groups or [],
                                     config.relations_cards or [])

    def _signaler_conflits_remplacement(self, conflits: List[str]):
        """Message bloquant (show, jamais exec_) : retour au dialogue pour corriger."""
        from PyQt5.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Remplacements contradictoires")
        box.setText("Ces remplacements ne peuvent pas être enregistrés tels quels :\n\n"
                    + "\n".join(f"• {c}" for c in conflits)
                    + "\n\nCorrigez-les avant d'importer.")
        box.setStandardButtons(QMessageBox.Ok)
        box.setWindowModality(Qt.WindowModal)
        box.finished.connect(lambda *_: box.deleteLater())
        box.show()

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
            StyleManager.CARTE_GRIS_CLAIR
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
            lbl.setStyleSheet(StyleManager.LIBELLE_PETIT_GRIS_TRANSPARENT)
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
            StyleManager.CARTE_GRIS_CLAIR
        )
        couche = QVBoxLayout(encadre)
        couche.setContentsMargins(12, 8, 12, 8)
        couche.setSpacing(2)
        titre = QLabel("<b>Orthographe alignée sur la base</b>")
        titre.setStyleSheet("font-size: 11px; color: #2c3e50; background: transparent; border: none;")
        couche.addWidget(titre)
        for ligne in lignes:
            lbl = QLabel(ligne)
            lbl.setStyleSheet(StyleManager.LIBELLE_PETIT_GRIS_TRANSPARENT)
            couche.addWidget(lbl)
        return encadre

    def _on_confirm(self):
        self.confirmed.emit()
        self.close()

    def _on_cancel(self):
        self.cancelled.emit()
        self.close()
