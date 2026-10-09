"""
Dialogue de configuration des exports CSV et HTML
Accessible via Outils → "Configuration des exports…"

Onglet CSV  : colonnes (en-tête + source/assemblage), séparateur, encodage, pattern nom fichier
Onglet HTML : templates marques et détails avec preview en temps réel
"""

import os

import qtawesome as qta
from .flow_layout import FlowLayout
from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QStackedWidget, QButtonGroup, QWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextBrowser,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QInputDialog, QFrame, Qt, QFont, QSizePolicy, QSize, QSpinBox,
    QEvent, QFileDialog
)
from src.core.logger import app_logger


def _make_icon_toggle(btn, icon_name, icon_color):
    """Factory pour le toggle d'icône bouton nav (évite le piège de closure en boucle)."""
    def _on_toggled(checked):
        btn.setIcon(qta.icon(icon_name, color='white' if checked else icon_color))
    return _on_toggled


class VariableChipsBar(QWidget):
    """Barre de boutons-puces cliquables insérant une variable {nom} dans le
    champ texte actuellement actif parmi une liste de champs cibles.

    Réutilisable pour n'importe quel groupe de variables (CSV, HTML Marques,
    HTML Détails, futurs onglets d'export...) : il suffit de fournir la liste
    de variables (nom + info-bulle) et les QLineEdit concernés.
    """

    def __init__(self, variables: list, targets: list, parent=None):
        """
        Args:
            variables: liste de tuples (nom_variable, description) — le bouton
                affichera "{nom_variable}" et l'info-bulle affichera la description.
            targets: liste de cibles pouvant recevoir l'insertion, chacune étant :
                - un QLineEdit (insertion à la position du curseur), ou
                - un tuple ('table', QTableWidget, colonne) pour insérer dans la
                  cellule en cours d'édition (ou la cellule courante) de cette colonne.
                La cible active est celle ayant le focus le plus récent (par défaut :
                la dernière de la liste).
        """
        super().__init__(parent)
        self._targets = list(targets)
        self._active_target = self._targets[-1] if self._targets else None

        # Disposition qui passe à la ligne : une rangée unique compressait les
        # puces sous leur taille utile et coupait leur texte quand la fenêtre
        # était étroite.
        layout = FlowLayout(self, spacing=4)

        for name, description in variables:
            btn = QPushButton("{" + name + "}")
            btn.setToolTip(description)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton {"
                "  padding: 1px 6px; font-size: 11px; font-family: monospace;"
                "  background: #eef1f4; color: #495057;"
                "  border: 1px solid #dee2e6; border-radius: 8px;"
                "}"
                "QPushButton:hover { background: #dde3e8; }"
            )
            btn.clicked.connect(lambda _checked, n=name: self._insert_variable(n))
            layout.addWidget(btn)

        for target in self._targets:
            self._target_widget(target).installEventFilter(self)

    @staticmethod
    def _target_widget(target):
        """Widget Qt sous-jacent d'une cible (QLineEdit ou tuple table)."""
        return target[1] if isinstance(target, tuple) else target

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            for target in self._targets:
                if self._target_widget(target) is obj:
                    self._active_target = target
                    break
        return super().eventFilter(obj, event)

    def _insert_variable(self, name: str):
        target = self._active_target
        if target is None:
            return
        token = "{" + name + "}"
        if isinstance(target, tuple):
            _, table, col = target
            self._insert_into_table_cell(table, col, token)
        else:
            target.insert(token)
            target.setFocus()

    @staticmethod
    def _insert_into_table_cell(table, col, token):
        """Insérer le token dans la cellule en édition (ou la cellule courante
        de la colonne `col`) d'un QTableWidget."""
        editors = table.viewport().findChildren(QLineEdit)
        if editors:
            editors[0].insert(token)
            return

        item = table.currentItem()
        if item is None or table.currentColumn() != col:
            row = table.currentRow()
            if row < 0:
                return
            item = table.item(row, col)
            if item is None:
                item = QTableWidgetItem("")
                table.setItem(row, col, item)
        item.setText(item.text() + token)
        table.editItem(item)


# Données de prévisualisation HTML
_PREVIEW_DATA = [
    ('Aspirateur', 'Samsung', 'SC4520', 'PowerBrush 20', '', 'AS6015830'),
    ('Aspirateur', 'Samsung', 'SC4521', 'PowerBrush Pro', '', 'AS6015830'),
    ('Lave-vaisselle', 'Bosch', 'SMV4HTX31E', 'ActiveWater', '', 'AS6015830'),
    ('Lave-vaisselle', 'Bosch', 'SMV45EX01E', '', '', 'AS6015830'),
    ('Réfrigérateur', 'LG', 'GBB62PZGFN', 'DoorCooling+', '', 'AS6015830'),
]


class ExportConfigDialog(QDialog):
    """
    Dialogue de configuration des exports CSV et HTML.

    Utilise show() + callback pour rester non-bloquant (convention macOS).
    """

    def __init__(self, export_config_service, parent=None):
        super().__init__(parent)
        self.export_config_service = export_config_service
        self._original_config = export_config_service.get_config()

        self.setWindowTitle("Configuration des exports")
        self.setMinimumSize(720, 520)
        self.setModal(False)

        self._build_ui()
        self._load_config_into_ui()

    # ─── Construction de l'interface ─────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Bandeau commun : dossier de destination (concerne tous les exports
        # fichier, pas seulement le CSV) — donc au-dessus des onglets.
        layout.addLayout(self._build_output_dir_bar())

        # Barre de navigation (remplace QTabWidget)
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(4)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_stack = QStackedWidget()

        _nav_defs = [
            ("CSV",  'fa5s.table', '#2980b9'),
            ("HTML", 'fa5s.code',  '#e67e22'),
        ]
        for i, (label, icon_name, icon_color) in enumerate(_nav_defs):
            btn = QPushButton(label)
            btn.setCheckable(True)
            is_first = (i == 0)
            btn.setIcon(qta.icon(icon_name, color='white' if is_first else icon_color))
            btn.setIconSize(QSize(12, 12))
            btn.setStyleSheet(
                "QPushButton { padding: 4px 12px; font-size: 11px; border-radius: 4px; }"
                "QPushButton:checked { background-color: #495057; color: white; }"
            )
            btn.toggled.connect(
                lambda checked, idx=i: self._nav_stack.setCurrentIndex(idx) if checked else None
            )
            btn.toggled.connect(_make_icon_toggle(btn, icon_name, icon_color))
            self._nav_group.addButton(btn, i)
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")
        layout.addWidget(sep)

        self._nav_stack.addWidget(self._build_csv_tab())
        self._nav_stack.addWidget(self._build_html_tab())
        layout.addWidget(self._nav_stack)

        # Boutons du bas
        layout.addLayout(self._build_footer())

        # Activer le premier onglet
        self._nav_group.button(0).setChecked(True)

    def _build_output_dir_bar(self) -> QHBoxLayout:
        """Bandeau du dossier de destination des exports fichier.

        Commun aux onglets : le réglage ne concerne pas que le CSV (rapport de
        supersession, export de la liste des pièces...). Les exports HTML vont
        dans le presse-papier et ne sont pas concernés.
        """
        self._output_dir = ''

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self._section_label("Dossier d'export :"))

        self.output_dir_input = QLineEdit()
        self.output_dir_input.setReadOnly(True)
        self.output_dir_input.setToolTip(
            "Dossier de destination des exports fichier (CSV, rapports).\n"
            "Les exports HTML sont copiés dans le presse-papier : ils ne sont pas concernés."
        )
        bar.addWidget(self.output_dir_input, 1)

        browse_btn = QPushButton("Parcourir…")
        browse_btn.setIcon(qta.icon('fa5s.folder-open', color='#495057'))
        browse_btn.setIconSize(QSize(11, 11))
        browse_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        )
        browse_btn.clicked.connect(self._browse_output_dir)
        bar.addWidget(browse_btn)

        self.output_dir_reset_btn = QPushButton()
        self.output_dir_reset_btn.setIcon(qta.icon('fa5s.undo', color='#495057'))
        self.output_dir_reset_btn.setIconSize(QSize(11, 11))
        self.output_dir_reset_btn.setFixedSize(28, 26)
        self.output_dir_reset_btn.setToolTip("Revenir au Bureau (valeur par défaut)")
        self.output_dir_reset_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        )
        self.output_dir_reset_btn.clicked.connect(lambda: self._set_output_dir(''))
        bar.addWidget(self.output_dir_reset_btn)

        return bar

    def _set_output_dir(self, value: str):
        """Mettre à jour le dossier d'export : valeur stockée + affichage.

        La valeur stockée reste vide pour « Bureau » (config portable) ; le champ
        affiche toujours le chemin réellement utilisé. Un dossier configuré mais
        devenu inutilisable est signalé en rouge plutôt que masqué.
        """
        self._output_dir = (value or '').strip()

        if self._output_dir:
            self.output_dir_input.setText(self._output_dir)
            utilisable = os.path.isdir(self._output_dir) and os.access(self._output_dir, os.W_OK)
            self.output_dir_input.setStyleSheet(
                '' if utilisable else "QLineEdit { color: #dc3545; }"
            )
        else:
            self.output_dir_input.setText(self.export_config_service.get_default_output_dir())
            self.output_dir_input.setStyleSheet('')

        self.output_dir_reset_btn.setEnabled(bool(self._output_dir))

    def _browse_output_dir(self):
        """Sélection du dossier de destination (dialogue de fichiers natif)."""
        depart = self.output_dir_input.text() or self.export_config_service.get_default_output_dir()
        choisi = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de destination des exports", depart
        )
        if choisi:
            self._set_output_dir(choisi)

    def _build_csv_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # Explication variables disponibles
        vars_label = QLabel(
            "Variables disponibles dans la colonne Source / Assemblage "
            "(cliquer une puce ci-dessous pour insérer dans la cellule sélectionnée) :\n"
            "  {modele_complet} = ref. modèle + commerciale fusionnées (tiret absent si l'une est vide)\n"
            "  {separateur}     = \" - \" si les deux références sont présentes, \"\" sinon"
        )
        vars_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        vars_label.setWordWrap(True)
        layout.addWidget(vars_label)

        # Tableau des colonnes
        self.csv_table = QTableWidget(0, 2)
        self.csv_table.setHorizontalHeaderLabels(["En-tête", "Source / Assemblage"])
        self.csv_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.csv_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.csv_table.setColumnWidth(0, 200)
        self.csv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.csv_table.setAlternatingRowColors(True)
        layout.addWidget(self.csv_table)

        layout.addWidget(VariableChipsBar(
            [
                ("export_ref",     "Référence d'export de l'appareil"),
                ("ref_piece",      "Référence de la pièce"),
                ("type_app",       "Type d'appareil"),
                ("manufacturer",   "Fabricant"),
                ("ref_modele",     "Référence modèle"),
                ("commercial_ref", "Référence commerciale"),
                ("other_ref",      "Autre référence"),
                ("modele_complet", "Référence modèle + commerciale fusionnées (tiret absent si l'une est vide)"),
                ("separateur",     "\" - \" si les deux références sont présentes, \"\" sinon"),
            ],
            targets=[('table', self.csv_table, 1)],
        ))

        # Boutons gestion lignes
        row_btn_layout = QHBoxLayout()
        add_btn = QPushButton("Ajouter une colonne")
        add_btn.setIcon(qta.icon('fa5s.plus', color='#495057'))
        add_btn.setIconSize(QSize(10, 10))
        add_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        add_btn.clicked.connect(self._add_csv_row)
        remove_btn = QPushButton("Supprimer")
        remove_btn.setIcon(qta.icon('fa5s.minus', color='#dc3545'))
        remove_btn.setIconSize(QSize(10, 10))
        remove_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        remove_btn.clicked.connect(self._remove_csv_row)
        up_btn = QPushButton()
        up_btn.setIcon(qta.icon('fa5s.arrow-up', color='#495057'))
        up_btn.setIconSize(QSize(11, 11))
        up_btn.setFixedSize(28, 26)
        up_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        up_btn.setToolTip("Monter la colonne sélectionnée")
        up_btn.clicked.connect(self._move_csv_row_up)
        down_btn = QPushButton()
        down_btn.setIcon(qta.icon('fa5s.arrow-down', color='#495057'))
        down_btn.setIconSize(QSize(11, 11))
        down_btn.setFixedSize(28, 26)
        down_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        down_btn.setToolTip("Descendre la colonne sélectionnée")
        down_btn.clicked.connect(self._move_csv_row_down)
        row_btn_layout.addWidget(add_btn)
        row_btn_layout.addWidget(remove_btn)
        row_btn_layout.addStretch()
        row_btn_layout.addWidget(up_btn)
        row_btn_layout.addWidget(down_btn)
        layout.addLayout(row_btn_layout)

        # Séparateur visuel
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")
        layout.addWidget(sep)

        # Options CSV (séparateur, encodage, pattern)
        opts_layout = QHBoxLayout()

        opts_layout.addWidget(QLabel("Séparateur :"))
        self.csv_sep_input = QLineEdit()
        self.csv_sep_input.setMaximumWidth(50)
        self.csv_sep_input.setToolTip("Caractère séparateur (ex: ; ou ,)")
        opts_layout.addWidget(self.csv_sep_input)

        opts_layout.addSpacing(16)
        opts_layout.addWidget(QLabel("Encodage :"))
        self.csv_enc_combo = QComboBox()
        self.csv_enc_combo.addItems(["utf-8", "utf-8-sig", "latin-1", "cp1252"])
        self.csv_enc_combo.setToolTip("utf-8-sig ajoute un BOM pour compatibilité Excel")
        opts_layout.addWidget(self.csv_enc_combo)

        opts_layout.addSpacing(16)
        opts_layout.addWidget(QLabel("Nom de fichier :"))
        self.csv_pattern_input = QLineEdit()
        self.csv_pattern_input.setToolTip(
            "Pattern du nom de fichier.\n"
            "Variables : {export_ref} (référence export), {timestamp} (date heure)"
        )
        opts_layout.addWidget(self.csv_pattern_input, 1)

        layout.addLayout(opts_layout)

        pattern_chips_layout = QHBoxLayout()
        pattern_chips_layout.addWidget(QLabel("Variables nom de fichier :"))
        pattern_chips_layout.addWidget(VariableChipsBar(
            [
                ("export_ref", "Référence d'export de l'appareil"),
                ("timestamp",  "Date et heure de génération de l'export"),
            ],
            targets=[self.csv_pattern_input],
        ), 1)
        layout.addLayout(pattern_chips_layout)

        return tab

    def _build_html_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(12)

        # ── Panneau gauche : champs de config ────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(6)

        # Section Marques
        left_layout.addWidget(self._section_label("Marques"))

        left_layout.addWidget(QLabel("Template lien :"))
        self.html_link_tpl = QLineEdit()
        left_layout.addWidget(self.html_link_tpl)
        left_layout.addWidget(VariableChipsBar(
            [("marque", "Nom de la marque")],
            targets=[self.html_link_tpl],
        ))

        left_layout.addWidget(QLabel("Séparateur entre marques :"))
        self.html_brands_sep = QLineEdit()
        self.html_brands_sep.setMaximumWidth(80)
        left_layout.addWidget(self.html_brands_sep)

        # Séparateur
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")
        left_layout.addWidget(sep)

        # Section Détails
        left_layout.addWidget(self._section_label("Détails"))

        # Barre de profils : plusieurs formats d'export HTML Détails mémorisables
        profile_bar = QHBoxLayout()
        profile_bar.setSpacing(4)
        profile_bar.addWidget(QLabel("Profil :"))

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(160)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_bar.addWidget(self.profile_combo, stretch=1)

        for label, tooltip, slot in (
            ("Ajouter",   "Créer un nouveau profil (valeurs par défaut)",  self._add_profile),
            ("Dupliquer", "Copier le profil sélectionné",                  self._duplicate_profile),
            ("Renommer",  "Renommer le profil sélectionné",                self._rename_profile),
            ("Supprimer", "Supprimer le profil sélectionné",               self._delete_profile),
            ("Par défaut", "Utiliser ce profil pour le bouton HTML Détails", self._set_default_profile),
        ):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            profile_bar.addWidget(btn)

        left_layout.addLayout(profile_bar)

        left_layout.addWidget(QLabel("En-tête de marque :"))
        self.html_brand_header_tpl = QLineEdit()
        left_layout.addWidget(self.html_brand_header_tpl)

        left_layout.addWidget(QLabel("Ligne modèle :"))
        self.html_model_line_tpl = QLineEdit()
        left_layout.addWidget(self.html_model_line_tpl)

        detail_chips = VariableChipsBar(
            [
                ("marque",          "Nom de la marque"),
                ("modele_complet",  "Référence modèle + commerciale fusionnées (tiret retiré si l'une est vide)"),
                ("ref_modele",      "Référence modèle"),
                ("ref_commerciale", "Référence commerciale"),
                ("other_ref",       "Autre référence"),
                ("separateur",      "\" - \" si les deux références sont présentes, \"\" sinon"),
            ],
            targets=[self.html_brand_header_tpl, self.html_model_line_tpl],
        )
        left_layout.addWidget(detail_chips)

        left_layout.addWidget(QLabel("Séparateur entre groupes :"))
        self.html_group_sep = QLineEdit()
        left_layout.addWidget(self.html_group_sep)

        # Limite de caractères HTML détails
        char_limit_layout = QHBoxLayout()
        char_limit_layout.addWidget(QLabel("Limite de caractères :"))
        self.html_char_limit_spin = QSpinBox()
        self.html_char_limit_spin.setRange(10000, 2000000)
        self.html_char_limit_spin.setSingleStep(5000)
        self.html_char_limit_spin.setSuffix(" car.")
        self.html_char_limit_spin.setToolTip(
            "Nombre maximum de caractères visibles dans l'export HTML Détails.\n"
            "Si dépassé, les données sont réduites progressivement :\n"
            "  1. Toutes les références (modèle + commerciale)\n"
            "  2. Référence modèle uniquement\n"
            "  3. Référence commerciale uniquement"
        )
        char_limit_layout.addWidget(self.html_char_limit_spin)
        char_limit_layout.addStretch()
        left_layout.addLayout(char_limit_layout)

        preview_btn = QPushButton("Prévisualiser")
        preview_btn.setIcon(qta.icon('fa5s.eye', color='#495057'))
        preview_btn.setIconSize(QSize(11, 11))
        preview_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        preview_btn.clicked.connect(self._update_html_preview)
        left_layout.addWidget(preview_btn)

        left_layout.addStretch()
        layout.addWidget(left, 1)

        # ── Panneau droit : preview ───────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(4)

        right_layout.addWidget(self._section_label("Aperçu (données fictives)"))
        self.html_preview = QTextBrowser()
        self.html_preview.setStyleSheet("background: white; border: 1px solid #dee2e6;")
        right_layout.addWidget(self.html_preview)
        layout.addWidget(right, 1)

        return tab

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        reset_btn = QPushButton("Réinitialiser les défauts")
        reset_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        reset_btn.setToolTip("Restaurer les valeurs d'origine (comportement actuel)")
        reset_btn.clicked.connect(self._reset_to_defaults)
        footer.addWidget(reset_btn)
        footer.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 11px; } QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }")
        cancel_btn.clicked.connect(self._on_cancel)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Enregistrer")
        save_btn.setDefault(True)
        save_btn.setIcon(qta.icon('fa5s.save', color='white'))
        save_btn.setIconSize(QSize(12, 12))
        save_btn.setStyleSheet(
            "QPushButton { background-color: #198754; color: white;"
            " padding: 3px 10px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background-color: #157347; }"
        )
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)
        return footer

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        font = QFont()
        font.setBold(True)
        lbl.setFont(font)
        return lbl

    # ─── Chargement de la config dans l'UI ───────────────────────────────────

    def _load_config_into_ui(self):
        config = self.export_config_service.get_config()

        # Dossier de destination (commun aux onglets)
        self._set_output_dir(config.get('output_dir', ''))

        # CSV
        csv_cfg = config.get('csv', {})
        self._populate_csv_table(csv_cfg.get('columns', []))
        self.csv_sep_input.setText(csv_cfg.get('separator', ';'))
        enc = csv_cfg.get('encoding', 'utf-8')
        idx = self.csv_enc_combo.findText(enc)
        self.csv_enc_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.csv_pattern_input.setText(csv_cfg.get('filename_pattern', '{term}_everyParts.csv'))

        # HTML
        brands_cfg = config.get('html', {}).get('brands', {})
        self.html_link_tpl.setText(brands_cfg.get('link_template', ''))
        self.html_brands_sep.setText(brands_cfg.get('separator', ' '))

        # Profils HTML Détails : copie de travail en mémoire jusqu'à Enregistrer
        self._profiles = self.export_config_service.get_details_profiles()
        self._default_profile = self.export_config_service.get_default_details_profile_name()
        self._current_profile_name = self._default_profile
        self._refresh_profile_combo(select_name=self._default_profile)
        self._load_profile_fields(self._find_profile(self._current_profile_name))

    # ─── Gestion des profils HTML Détails ────────────────────────────────────

    def _find_profile(self, name):
        for p in self._profiles:
            if p['name'] == name:
                return p
        return self._profiles[0]

    def _refresh_profile_combo(self, select_name=None):
        """Repeupler la combo (nom réel en itemData, suffixe visuel pour le défaut)"""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in self._profiles:
            display = p['name'] + ("  (défaut)" if p['name'] == self._default_profile else "")
            self.profile_combo.addItem(display, p['name'])
        if select_name:
            idx = next((i for i in range(self.profile_combo.count())
                        if self.profile_combo.itemData(i) == select_name), 0)
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)

    def _store_fields_into_current(self):
        """Reporter les champs de l'éditeur dans le profil courant (en mémoire)"""
        profile = self._find_profile(self._current_profile_name)
        profile['brand_header_template'] = self.html_brand_header_tpl.text()
        profile['model_line_template']   = self.html_model_line_tpl.text()
        profile['group_separator']       = self.html_group_sep.text()
        profile['char_limit']            = self.html_char_limit_spin.value()

    def _load_profile_fields(self, profile):
        self.html_brand_header_tpl.setText(profile.get('brand_header_template', ''))
        self.html_model_line_tpl.setText(profile.get('model_line_template', ''))
        self.html_group_sep.setText(profile.get('group_separator', ''))
        self.html_char_limit_spin.setValue(profile.get('char_limit', 195000))
        self._update_html_preview()

    def _on_profile_changed(self, index):
        if index < 0:
            return
        self._store_fields_into_current()
        self._current_profile_name = self.profile_combo.itemData(index)
        self._load_profile_fields(self._find_profile(self._current_profile_name))

    def _unique_profile_name(self, base):
        names = {p['name'] for p in self._profiles}
        if base not in names:
            return base
        i = 2
        while f"{base} ({i})" in names:
            i += 1
        return f"{base} ({i})"

    def _ask_profile_name(self, title, default_text):
        name, ok = QInputDialog.getText(self, title, "Nom du profil :", text=default_text)
        name = name.strip()
        return name if (ok and name) else None

    def _add_profile(self):
        name = self._ask_profile_name("Nouveau profil", "Nouveau profil")
        if not name:
            return
        from src.services.export_config_service import DEFAULT_CONFIG
        profile = dict(DEFAULT_CONFIG['html']['details'])
        profile['name'] = self._unique_profile_name(name)
        self._store_fields_into_current()
        self._profiles.append(profile)
        self._current_profile_name = profile['name']
        self._refresh_profile_combo(select_name=profile['name'])
        self._load_profile_fields(profile)

    def _duplicate_profile(self):
        self._store_fields_into_current()
        source = self._find_profile(self._current_profile_name)
        profile = dict(source)
        profile['name'] = self._unique_profile_name(f"{source['name']} (copie)")
        self._profiles.append(profile)
        self._current_profile_name = profile['name']
        self._refresh_profile_combo(select_name=profile['name'])
        self._load_profile_fields(profile)

    def _rename_profile(self):
        old_name = self._current_profile_name
        name = self._ask_profile_name("Renommer le profil", old_name)
        if not name or name == old_name:
            return
        name = self._unique_profile_name(name)
        self._find_profile(old_name)['name'] = name
        if self._default_profile == old_name:
            self._default_profile = name
        self._current_profile_name = name
        self._refresh_profile_combo(select_name=name)

    def _delete_profile(self):
        if len(self._profiles) <= 1:
            QMessageBox.warning(self, "Suppression impossible",
                                "Au moins un profil doit exister.")
            return
        name = self._current_profile_name
        if QMessageBox.question(
            self, "Supprimer le profil",
            f"Supprimer le profil « {name} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._profiles = [p for p in self._profiles if p['name'] != name]
        if self._default_profile == name:
            self._default_profile = self._profiles[0]['name']
        self._current_profile_name = self._profiles[0]['name']
        self._refresh_profile_combo(select_name=self._current_profile_name)
        self._load_profile_fields(self._find_profile(self._current_profile_name))

    def _set_default_profile(self):
        self._default_profile = self._current_profile_name
        self._refresh_profile_combo(select_name=self._current_profile_name)

    def _populate_csv_table(self, columns):
        self.csv_table.setRowCount(0)
        for col in columns:
            row = self.csv_table.rowCount()
            self.csv_table.insertRow(row)
            self.csv_table.setItem(row, 0, QTableWidgetItem(col.get('header', '')))
            self.csv_table.setItem(row, 1, QTableWidgetItem(col.get('source', '')))

    # ─── Gestion du tableau CSV ───────────────────────────────────────────────

    def _add_csv_row(self):
        row = self.csv_table.rowCount()
        self.csv_table.insertRow(row)
        self.csv_table.setItem(row, 0, QTableWidgetItem("colonne"))
        self.csv_table.setItem(row, 1, QTableWidgetItem("{ref_piece}"))
        self.csv_table.selectRow(row)

    def _remove_csv_row(self):
        row = self.csv_table.currentRow()
        if row >= 0:
            self.csv_table.removeRow(row)

    def _move_csv_row_up(self):
        row = self.csv_table.currentRow()
        if row <= 0:
            return
        self._swap_csv_rows(row, row - 1)
        self.csv_table.selectRow(row - 1)

    def _move_csv_row_down(self):
        row = self.csv_table.currentRow()
        if row < 0 or row >= self.csv_table.rowCount() - 1:
            return
        self._swap_csv_rows(row, row + 1)
        self.csv_table.selectRow(row + 1)

    def _swap_csv_rows(self, a: int, b: int):
        for col in range(2):
            item_a = self.csv_table.item(a, col)
            item_b = self.csv_table.item(b, col)
            text_a = item_a.text() if item_a else ''
            text_b = item_b.text() if item_b else ''
            self.csv_table.setItem(a, col, QTableWidgetItem(text_b))
            self.csv_table.setItem(b, col, QTableWidgetItem(text_a))

    # ─── Preview HTML ─────────────────────────────────────────────────────────

    def _update_html_preview(self):
        """Générer et afficher un aperçu HTML avec les templates actuels"""
        link_tpl        = self.html_link_tpl.text()
        brands_sep      = self.html_brands_sep.text()
        brand_header    = self.html_brand_header_tpl.text()
        model_line      = self.html_model_line_tpl.text()
        group_sep       = self.html_group_sep.text()

        def render(template: str, context: dict) -> str:
            for key, val in context.items():
                template = template.replace('{' + key + '}', str(val or ''))
            return template

        from collections import defaultdict
        brands_data = defaultdict(list)
        for record in _PREVIEW_DATA:
            _, manufacturer, ref_modele, commercial_ref, _, _ = record
            if manufacturer:
                brands_data[manufacturer].append({
                    'ref_modele': ref_modele, 'commercial_ref': commercial_ref
                })

        # Preview Marques
        brand_links = brands_sep.join(
            render(link_tpl, {'marque': b}) for b in sorted(brands_data)
        )

        # Preview Détails
        detail_parts = []
        for i, brand in enumerate(sorted(brands_data)):
            if i > 0:
                detail_parts.append(group_sep)
            detail_parts.append(render(brand_header, {'marque': brand}))
            for m in brands_data[brand]:
                ref_m = m['ref_modele']
                ref_c = m['commercial_ref']
                modele_complet = f"{ref_m} - {ref_c}".strip(' -') if (ref_m and ref_c) else (ref_m or ref_c or '')
                separateur = ' - ' if (ref_m and ref_c) else ''
                detail_parts.append(render(model_line, {
                    'marque':          brand,
                    'ref_modele':      ref_m,
                    'ref_commerciale': ref_c,
                    'modele_complet':  modele_complet,
                    'separateur':      separateur,
                }))
        detail_html = ''.join(detail_parts)

        preview_html = f"""
        <html><body style="font-family: monospace; font-size: 12px; padding: 8px;">
        <p style="font-weight:bold; color:#6c757d; margin:4px 0;">— Marques —</p>
        <div style="margin-bottom:12px;">{brand_links}</div>
        <p style="font-weight:bold; color:#6c757d; margin:4px 0;">— Détails —</p>
        <div>{detail_html}</div>
        </body></html>
        """
        self.html_preview.setHtml(preview_html)

    # ─── Actions boutons ──────────────────────────────────────────────────────

    def _collect_config(self) -> dict:
        """Lire l'état de l'UI et retourner un dict de config"""
        columns = []
        for row in range(self.csv_table.rowCount()):
            header = self.csv_table.item(row, 0)
            source = self.csv_table.item(row, 1)
            if header and source:
                columns.append({
                    'header': header.text().strip(),
                    'source': source.text().strip()
                })

        return {
            "output_dir": self._output_dir,
            "csv": {
                "separator":        self.csv_sep_input.text() or ';',
                "encoding":         self.csv_enc_combo.currentText(),
                "filename_pattern": self.csv_pattern_input.text() or '{term}_everyParts.csv',
                "columns":          columns
            },
            "html": {
                "brands": {
                    "link_template": self.html_link_tpl.text(),
                    "separator":     self.html_brands_sep.text(),
                    "char_limit":    self.export_config_service.get_html_brands_config().get('char_limit', 195000)
                },
                # 'details' (miroir du profil par défaut) est resynchronisé par
                # ExportConfigService._merge_with_defaults() à la sauvegarde
                "details_profiles":        self._collect_profiles(),
                "details_default_profile": self._default_profile
            }
        }

    def _collect_profiles(self) -> list:
        """Reporter l'éditeur dans le profil courant et retourner tous les profils"""
        self._store_fields_into_current()
        return [dict(p) for p in self._profiles]

    def _on_save(self):
        config = self._collect_config()
        if not config['csv']['columns']:
            QMessageBox.warning(self, "Validation", "Le CSV doit avoir au moins une colonne.")
            return
        if not self._confirmer_dossier_export():
            return
        if self.export_config_service.save_config(config):
            app_logger.info("[OK] Configuration des exports sauvegardée")
            self.close()
        else:
            QMessageBox.critical(self, "Erreur", "Impossible de sauvegarder la configuration.")

    def _confirmer_dossier_export(self) -> bool:
        """Alerter si le dossier configuré est inutilisable, sans bloquer.

        On n'interdit pas l'enregistrement : un dossier sur disque externe
        actuellement débranché reste un réglage légitime. L'export retombera
        sur le Bureau le moment venu (cf. ExportConfigService.get_output_dir).
        """
        if not self._output_dir:
            return True
        if os.path.isdir(self._output_dir) and os.access(self._output_dir, os.W_OK):
            return True

        reponse = QMessageBox.question(
            self,
            "Dossier d'export",
            f"Le dossier suivant est introuvable ou non accessible en écriture :\n"
            f"{self._output_dir}\n\n"
            "Les exports retomberont sur le Bureau tant qu'il reste inutilisable.\n"
            "Enregistrer quand même ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reponse == QMessageBox.Yes

    def _on_cancel(self):
        self.close()

    def _reset_to_defaults(self):
        reply = QMessageBox.question(
            self,
            "Réinitialiser",
            "Remettre la configuration aux valeurs par défaut ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.export_config_service.reset_to_defaults()
            self._load_config_into_ui()
