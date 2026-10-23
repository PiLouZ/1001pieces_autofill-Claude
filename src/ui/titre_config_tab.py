"""
Onglet « Titre » de la configuration des exports (v3.99.0)

Gabarits nommés du bouton « Titre » (titre de fiche produit) : gabarit avec
variables, nombre de marques et de types, longueur maximale, séparateurs.
Aperçu en direct sur des données fictives. Les profils sont une copie de
travail jusqu'à « Enregistrer » (cf. ExportConfigDialog._collect_config).
"""

import copy

import qtawesome as qta
from .qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QTextBrowser, QMessageBox, QInputDialog, QScrollArea, QFrame, Qt, QSize
)
from .style_manager import StyleManager
from src.utils.titre_produit_generator import TitreProduitGenerator


# Données fictives de l'aperçu : (libellé, modèles par type, marques classées, référence)
_APERCU_TITRE = [
    ("pompe de vidange", {"Lave-linge": 412, "Lave-linge séchant": 360, "Lave-vaisselle": 40},
     ["Bosch", "Siemens", "Neff", "Gaggenau", "Constructa", "Balay", "Viva"], "00145787"),
    ("joint de porte", {"Four": 85},
     ["De Dietrich"], "AS0012345"),
]


class TitreConfigTab(QWidget):
    """Réglages des gabarits du bouton « Titre »."""

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._generateur = TitreProduitGenerator()
        self._profiles = []
        self._default_profile = ""
        self._current_profile_name = ""
        self._build_ui()

    # ─── Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        from .export_config_dialog import VariableChipsBar

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        card, grid = self._dialog._build_card(
            "Titre de fiche produit",
            "Bouton Titre : copie le titre de la fiche recherchée. Au-delà de la "
            "longueur maximale, les dernières marques puis les derniers types sont "
            "retirés ; le libellé et la référence ne sont jamais coupés.",
        )
        add_row = self._dialog._add_grid_row

        # Gabarits : liste déroulante + actions en icônes (comme HTML Détails)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(160)
        self.profile_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        bar.addWidget(self.profile_combo, stretch=1)
        for icone, tooltip, slot, style in (
            ('fa5s.plus',      "Ajouter un gabarit (valeurs par défaut)", self._add_profile,         StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.copy',      "Dupliquer le gabarit sélectionné",        self._duplicate_profile,   StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.pen',       "Renommer le gabarit sélectionné",         self._rename_profile,      StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.star',      "Par défaut : utiliser ce gabarit au clic sur le bouton Titre", self._set_default_profile, StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.trash-alt', "Supprimer le gabarit sélectionné",        self._delete_profile,      StyleManager.DANGER_COMPACT_BUTTON),
        ):
            btn = QPushButton()
            btn.setIcon(qta.icon(icone, color='#c0392b' if 'trash' in icone else '#495057'))
            btn.setIconSize(QSize(11, 11))
            btn.setFixedSize(28, 26)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(style)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        add_row(grid, "Gabarit :", bar)

        self.template_input = QLineEdit()
        add_row(grid, "Titre :", self.template_input, VariableChipsBar(
            [
                ("libelle",   "Libellé de la pièce (première lettre en majuscule)"),
                ("type",      "Type(s) d'appareil : le plus courant, et ceux qui en couvrent au moins 80 %"),
                ("marques",   "Marques, de la plus à la moins représentée"),
                ("reference", "Référence la plus récente de la lignée"),
            ],
            targets=[self.template_input],
        ))

        self.max_marques_spin = self._spin(1, 30, "Nombre maximum de marques citées")
        add_row(grid, "Marques au plus :", self._seul(self.max_marques_spin))

        self.max_types_spin = self._spin(1, 5, "Nombre maximum de types d'appareils cités\n"
                                                "(seuls ceux qui pèsent à peu près autant que le premier)")
        add_row(grid, "Types au plus :", self._seul(self.max_types_spin))

        self.max_car_spin = self._spin(0, 500, "Longueur maximale du titre (0 = sans limite)")
        self.max_car_spin.setSuffix(" car.")
        self.max_car_spin.setSpecialValueText("Sans limite")
        add_row(grid, "Longueur maximale :", self._seul(self.max_car_spin))

        self.sep_input = QLineEdit()
        self.sep_input.setMaximumWidth(80)
        self.sep_input.setToolTip("Texte entre deux marques ou deux types (« , » par défaut)")
        add_row(grid, "Séparateur :", self._seul(self.sep_input))

        self.dernier_sep_input = QLineEdit()
        self.dernier_sep_input.setMaximumWidth(80)
        self.dernier_sep_input.setToolTip("Texte avant la dernière marque ou le dernier type (« et » par défaut)")
        add_row(grid, "Avant le dernier :", self._seul(self.dernier_sep_input))

        reglages = QWidget()
        reglages_layout = QVBoxLayout(reglages)
        reglages_layout.setContentsMargins(0, 0, 6, 0)
        reglages_layout.addWidget(card)
        reglages_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(reglages)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(reglages.minimumSizeHint().width()
                               + scroll.verticalScrollBar().sizeHint().width())
        layout.addWidget(scroll, 2)

        # Aperçu
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self._dialog._section_label("Aperçu (données fictives)"))
        self.preview = QTextBrowser()
        self.preview.setStyleSheet("background: white; border: 1px solid #dee2e6;")
        right_layout.addWidget(self.preview)
        layout.addWidget(right, 1)

        for champ in (self.template_input, self.sep_input, self.dernier_sep_input):
            champ.textChanged.connect(self._update_preview)
        for spin in (self.max_marques_spin, self.max_types_spin, self.max_car_spin):
            spin.valueChanged.connect(self._update_preview)

    @staticmethod
    def _spin(minimum, maximum, tooltip):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setMinimumWidth(110)
        spin.setToolTip(tooltip)
        return spin

    @staticmethod
    def _seul(champ):
        row = QHBoxLayout()
        row.addWidget(champ)
        row.addStretch()
        return row

    # ─── Chargement / collecte ───────────────────────────────────────────────

    def load(self, titre_cfg: dict):
        """Copie de travail des profils de la config chargée."""
        self._profiles = copy.deepcopy(titre_cfg['profiles'])
        self._default_profile = titre_cfg['default_profile']
        self._current_profile_name = self._default_profile
        self._refresh_combo(select_name=self._default_profile)
        self._load_fields(self._find(self._current_profile_name))

    def collect(self) -> dict:
        self._store_fields()
        return {'profiles': copy.deepcopy(self._profiles),
                'default_profile': self._default_profile}

    def _find(self, name):
        return next((p for p in self._profiles if p['name'] == name), self._profiles[0])

    def _refresh_combo(self, select_name=None):
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

    def _store_fields(self):
        profile = self._find(self._current_profile_name)
        profile['template'] = self.template_input.text()
        profile['max_marques'] = self.max_marques_spin.value()
        profile['max_types'] = self.max_types_spin.value()
        profile['max_caracteres'] = self.max_car_spin.value()
        profile['separateur'] = self.sep_input.text()
        profile['dernier_separateur'] = self.dernier_sep_input.text()

    def _load_fields(self, profile):
        self.template_input.setText(profile.get('template', ''))
        self.max_marques_spin.setValue(profile.get('max_marques', 4))
        self.max_types_spin.setValue(profile.get('max_types', 3))
        self.max_car_spin.setValue(profile.get('max_caracteres', 120))
        self.sep_input.setText(profile.get('separateur', ', '))
        self.dernier_sep_input.setText(profile.get('dernier_separateur', ' et '))
        self._update_preview()

    # ─── Gabarits ────────────────────────────────────────────────────────────

    def _on_profile_changed(self, index):
        if index < 0:
            return
        self._store_fields()
        self._current_profile_name = self.profile_combo.itemData(index)
        self._load_fields(self._find(self._current_profile_name))

    def _unique_name(self, base):
        names = {p['name'] for p in self._profiles}
        if base not in names:
            return base
        i = 2
        while f"{base} ({i})" in names:
            i += 1
        return f"{base} ({i})"

    def _ask_name(self, title, default_text):
        name, ok = QInputDialog.getText(self, title, "Nom du gabarit :", text=default_text)
        name = name.strip()
        return name if (ok and name) else None

    def _select_new(self, profile):
        self._profiles.append(profile)
        self._current_profile_name = profile['name']
        self._refresh_combo(select_name=profile['name'])
        self._load_fields(profile)

    def _add_profile(self):
        name = self._ask_name("Nouveau gabarit", "Nouveau gabarit")
        if not name:
            return
        from src.services.export_config_service import DEFAULT_CONFIG
        self._store_fields()
        profile = copy.deepcopy(DEFAULT_CONFIG['titre']['profiles'][0])
        profile['name'] = self._unique_name(name)
        self._select_new(profile)

    def _duplicate_profile(self):
        self._store_fields()
        source = self._find(self._current_profile_name)
        profile = copy.deepcopy(source)
        profile['name'] = self._unique_name(f"{source['name']} (copie)")
        self._select_new(profile)

    def _rename_profile(self):
        old_name = self._current_profile_name
        name = self._ask_name("Renommer le gabarit", old_name)
        if not name or name == old_name:
            return
        name = self._unique_name(name)
        self._find(old_name)['name'] = name
        if self._default_profile == old_name:
            self._default_profile = name
        self._current_profile_name = name
        self._refresh_combo(select_name=name)

    def _delete_profile(self):
        if len(self._profiles) <= 1:
            QMessageBox.warning(self, "Suppression impossible", "Au moins un gabarit doit exister.")
            return
        name = self._current_profile_name
        if QMessageBox.question(
            self, "Supprimer le gabarit", f"Supprimer le gabarit « {name} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._profiles = [p for p in self._profiles if p['name'] != name]
        if self._default_profile == name:
            self._default_profile = self._profiles[0]['name']
        self._current_profile_name = self._profiles[0]['name']
        self._refresh_combo(select_name=self._current_profile_name)
        self._load_fields(self._find(self._current_profile_name))

    def _set_default_profile(self):
        self._default_profile = self._current_profile_name
        self._refresh_combo(select_name=self._current_profile_name)

    # ─── Aperçu ──────────────────────────────────────────────────────────────

    def apercu(self) -> list:
        """Titres des données fictives avec les réglages affichés : [(titre, résumé)]."""
        profil = {
            'template': self.template_input.text(),
            'max_marques': self.max_marques_spin.value(),
            'max_types': self.max_types_spin.value(),
            'max_caracteres': self.max_car_spin.value(),
            'separateur': self.sep_input.text(),
            'dernier_separateur': self.dernier_sep_input.text(),
        }
        lignes = []
        for libelle, poids_types, marques, reference in _APERCU_TITRE:
            types = self._generateur.types_proches(poids_types, profil['max_types'])
            r = self._generateur.generer(profil, libelle, types, marques, reference)
            nb = len(r['info']['marques_retenues'])
            resume = f"{r['longueur']} car. — {nb} marque{'s' if nb > 1 else ''} sur {len(marques)}"
            lignes.append((r['titre'], resume))
        return lignes

    def _update_preview(self):
        import html
        blocs = "".join(
            f"<p style='margin:6px 0 2px 0;'>{html.escape(titre)}</p>"
            f"<p style='margin:0 0 10px 0; color:#6c757d; font-size:11px;'>{html.escape(resume)}</p>"
            for titre, resume in self.apercu()
        )
        self.preview.setHtml(
            f"<html><body style='font-size: 13px; padding: 8px;'>{blocs}</body></html>")
