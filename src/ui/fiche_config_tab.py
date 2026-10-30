"""
Onglet « Fiche » de la configuration des exports

Variantes du bouton « Fiche complète » : gabarit Titre et profil HTML Détails
utilisés, lignes Code produit / Remplace / Équivalentes, bloc Informations
facultatif, limite de caractères de la fiche entière. Aperçu en direct sur des
données fictives. Les variantes sont une copie de travail jusqu'à
« Enregistrer » (cf. ExportConfigDialog._collect_config).
"""

import copy
import html

import qtawesome as qta
from .qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QTextBrowser, QMessageBox, QInputDialog, QScrollArea, QFrame, Qt, QSize
)
from .style_manager import StyleManager
from .champ_modele_html import ChampModeleHtml
from .titre_config_tab import _APERCU_TITRE
from src.services.html_export_service import HtmlExportService
from src.utils.fiche_produit_generator import FicheProduitGenerator
from src.utils.titre_produit_generator import TitreProduitGenerator


# Données fictives de l'aperçu (le titre reprend la 1ʳᵉ fiche de l'aperçu Titre)
_APERCU_MARQUES = ["Bosch", "Siemens", "Neff"]
_APERCU_REMPLACE = ["00144978"]
_APERCU_EQUIVALENTES = [["11008491"], ["00616190", "00499837"]]
_PAR_DEFAUT = "(gabarit par défaut)"


class FicheConfigTab(QWidget):
    """Réglages des variantes du bouton « Fiche complète »."""

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._generateur = FicheProduitGenerator()
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
            "Fiche produit complète",
            "Bouton Fiche complète : titre, marques, code produit, références "
            "remplacées et équivalentes, bloc Informations, puis les appareils "
            "affichés dans le tableau. Une ligne de références sans référence "
            "n'est pas écrite.",
        )
        add_row = self._dialog._add_grid_row

        # Variantes : liste déroulante + actions en icônes (comme Titre)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(160)
        self.profile_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        bar.addWidget(self.profile_combo, stretch=1)
        for icone, tooltip, slot, style in (
            ('fa5s.plus',      "Ajouter une variante (valeurs par défaut)", self._add_profile,       StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.copy',      "Dupliquer la variante sélectionnée",        self._duplicate_profile, StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.pen',       "Renommer la variante sélectionnée",         self._rename_profile,    StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.star',      "Par défaut : utiliser cette variante au clic sur le bouton Fiche complète", self._set_default_profile, StyleManager.SECONDARY_COMPACT_BUTTON),
            ('fa5s.trash-alt', "Supprimer la variante sélectionnée",        self._delete_profile,    StyleManager.DANGER_COMPACT_BUTTON),
        ):
            btn = QPushButton()
            btn.setIcon(qta.icon(icone, color='#c0392b' if 'trash' in icone else '#495057'))
            btn.setIconSize(QSize(11, 11))
            btn.setFixedSize(28, 26)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(style)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        add_row(grid, "Variante :", bar)

        self.titre_combo = QComboBox()
        self.titre_combo.setToolTip("Gabarit de l'onglet Titre utilisé pour le titre de la fiche")
        add_row(grid, "Titre :", self._seul(self.titre_combo))

        self.code_input = ChampModeleHtml()
        add_row(grid, "Code produit :", self.code_input, VariableChipsBar(
            [("reference", "Référence tapée ; si elle est remplacée, la plus récente")],
            targets=[self.code_input],
        ))

        self.remplace_input = ChampModeleHtml()
        self.remplace_input.setToolTip("Écrite seulement si la référence remplace d'anciennes références")
        self.equivalentes_input = ChampModeleHtml()
        self.equivalentes_input.setToolTip(
            "Une ligne par référence équivalente, suivie de ses anciennes références,\n"
            "de la plus fournie en appareils à la moins fournie")
        add_row(grid, "Remplace :", self.remplace_input)
        add_row(grid, "Équivalentes :", self.equivalentes_input, VariableChipsBar(
            [("references", "Références de la ligne, jointes par le séparateur")],
            targets=[self.remplace_input, self.equivalentes_input],
        ))

        self.separateur_input = QLineEdit()
        self.separateur_input.setMaximumWidth(80)
        self.separateur_input.setToolTip("Texte entre deux références d'une même ligne (une espace par défaut)")
        add_row(grid, "Séparateur des références :", self._seul(self.separateur_input))

        self.informations_check = QCheckBox("Inclure le bloc Informations")
        self.informations_check.setToolTip("Bloc à compléter ensuite sur le site, placé avant la liste des appareils")
        add_row(grid, "Informations :", self._seul(self.informations_check))
        self.informations_input = ChampModeleHtml()
        add_row(grid, "Bloc Informations :", self.informations_input)

        self.details_combo = QComboBox()
        self.details_combo.setToolTip("Profil de l'onglet HTML (liste des appareils) utilisé pour la fiche")
        add_row(grid, "Liste des appareils :", self._seul(self.details_combo))

        self.max_car_spin = QSpinBox()
        self.max_car_spin.setRange(0, 2000000)
        self.max_car_spin.setSingleStep(5000)
        self.max_car_spin.setSuffix(" car.")
        self.max_car_spin.setSpecialValueText("Celle du profil")
        self.max_car_spin.setMinimumWidth(120)
        self.max_car_spin.setToolTip(
            "Nombre maximum de caractères visibles de la fiche ENTIÈRE.\n"
            "Si dépassé, la liste des appareils est réduite progressivement :\n"
            "  1. Toutes les références (modèle + commerciale)\n"
            "  2. Référence modèle uniquement\n"
            "  3. Référence commerciale uniquement\n"
            "0 = limite du profil de la liste des appareils")
        add_row(grid, "Limite de caractères :", self._seul(self.max_car_spin))

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

        for champ in (self.code_input, self.remplace_input, self.equivalentes_input,
                      self.separateur_input, self.informations_input):
            champ.textChanged.connect(self._update_preview)
        self.informations_check.toggled.connect(self._on_informations_toggled)
        for combo in (self.titre_combo, self.details_combo):
            combo.currentIndexChanged.connect(self._update_preview)
        self.max_car_spin.valueChanged.connect(self._update_preview)

    @staticmethod
    def _seul(champ):
        row = QHBoxLayout()
        row.addWidget(champ)
        row.addStretch()
        return row

    def _on_informations_toggled(self, coche):
        self.informations_input.setEnabled(coche)
        self._update_preview()

    # ─── Gabarits des autres onglets ─────────────────────────────────────────

    def _noms_titre(self):
        return [p['name'] for p in self._dialog.titre_tab.collect()['profiles']]

    def _noms_details(self):
        return [p['name'] for p in self._dialog._collect_profiles()]

    @staticmethod
    def _remplir_combo(combo, noms, choisi):
        """'' = gabarit par défaut ; un nom disparu (renommé, supprimé) reste
        affiché, signalé : la fiche utilisera alors le gabarit par défaut."""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(_PAR_DEFAUT, "")
        for nom in noms:
            combo.addItem(nom, nom)
        if choisi and choisi not in noms:
            combo.addItem(f"{choisi}  (introuvable : gabarit par défaut)", choisi)
        idx = combo.findData(choisi or "")
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def rafraichir_gabarits(self):
        """Listes Titre / appareils à jour des autres onglets (copies de travail)."""
        if not self._profiles:
            return
        profile = self._find(self._current_profile_name)
        self._remplir_combo(self.titre_combo, self._noms_titre(),
                            self.titre_combo.currentData() if self.titre_combo.count()
                            else profile.get('titre_profile', ''))
        self._remplir_combo(self.details_combo, self._noms_details(),
                            self.details_combo.currentData() if self.details_combo.count()
                            else profile.get('details_profile', ''))
        self._update_preview()

    def showEvent(self, event):
        super().showEvent(event)
        self.rafraichir_gabarits()

    # ─── Chargement / collecte ───────────────────────────────────────────────

    def load(self, fiche_cfg: dict):
        """Copie de travail des variantes de la config chargée."""
        self._profiles = copy.deepcopy(fiche_cfg['profiles'])
        self._default_profile = fiche_cfg['default_profile']
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

    def _champs(self) -> dict:
        return {
            'titre_profile': self.titre_combo.currentData() or "",
            'details_profile': self.details_combo.currentData() or "",
            'inclure_informations': self.informations_check.isChecked(),
            'code_produit_template': self.code_input.text(),
            'remplace_template': self.remplace_input.text(),
            'equivalentes_template': self.equivalentes_input.text(),
            'informations_template': self.informations_input.text(),
            'separateur_references': self.separateur_input.text(),
            'max_caracteres': self.max_car_spin.value(),
        }

    def _store_fields(self):
        if self._profiles:
            self._find(self._current_profile_name).update(self._champs())

    def _load_fields(self, profile):
        self._remplir_combo(self.titre_combo, self._noms_titre(), profile.get('titre_profile', ''))
        self._remplir_combo(self.details_combo, self._noms_details(), profile.get('details_profile', ''))
        self.code_input.setText(profile.get('code_produit_template', ''))
        self.remplace_input.setText(profile.get('remplace_template', ''))
        self.equivalentes_input.setText(profile.get('equivalentes_template', ''))
        self.informations_input.setText(profile.get('informations_template', ''))
        self.separateur_input.setText(profile.get('separateur_references', ' '))
        self.max_car_spin.setValue(profile.get('max_caracteres', 200000))
        self.informations_check.setChecked(bool(profile.get('inclure_informations')))
        self.informations_input.setEnabled(self.informations_check.isChecked())
        self._update_preview()

    # ─── Variantes ───────────────────────────────────────────────────────────

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
        name, ok = QInputDialog.getText(self, title, "Nom de la variante :", text=default_text)
        name = name.strip()
        return name if (ok and name) else None

    def _select_new(self, profile):
        self._profiles.append(profile)
        self._current_profile_name = profile['name']
        self._refresh_combo(select_name=profile['name'])
        self._load_fields(profile)

    def _add_profile(self):
        name = self._ask_name("Nouvelle variante", "Nouvelle variante")
        if not name:
            return
        from src.services.export_config_service import DEFAULT_CONFIG
        self._store_fields()
        profile = copy.deepcopy(DEFAULT_CONFIG['fiche']['profiles'][0])
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
        name = self._ask_name("Renommer la variante", old_name)
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
            QMessageBox.warning(self, "Suppression impossible", "Au moins une variante doit exister.")
            return
        name = self._current_profile_name
        if QMessageBox.question(
            self, "Supprimer la variante", f"Supprimer la variante « {name} » ?",
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

    def _titre_apercu(self) -> str:
        titre_cfg = self._dialog.titre_tab.collect()
        nom = self.titre_combo.currentData() or titre_cfg['default_profile']
        profil = next((p for p in titre_cfg['profiles'] if p['name'] == nom),
                      next((p for p in titre_cfg['profiles']
                            if p['name'] == titre_cfg['default_profile']), titre_cfg['profiles'][0]))
        libelle, poids_types, marques, _ = _APERCU_TITRE[0]
        generateur = TitreProduitGenerator()
        types = generateur.types_proches(poids_types, profil.get('max_types', 3))
        return generateur.generer(profil, libelle, types, marques, "00145787")['titre']

    def _marques_apercu(self) -> str:
        d = self._dialog
        liens = d.html_brands_sep.text().join(
            d.html_link_tpl.text().replace('{marque}', m) for m in _APERCU_MARQUES)
        return HtmlExportService.wrap_brand_links(liens, d.html_brands_wrapper.text())

    def _appareils_apercu(self) -> str:
        profils = self._dialog._collect_profiles()
        nom = self.details_combo.currentData() or self._dialog._default_profile
        profil = next((p for p in profils if p['name'] == nom),
                      next((p for p in profils if p['name'] == self._dialog._default_profile), profils[0]))
        return HtmlExportService.wrap_details(
            "<div><i>… appareils affichés dans le tableau …</i></div>",
            profil.get('wrapper_template', '{appareils}'))

    def apercu(self) -> str:
        """HTML de la fiche fictive avec les réglages affichés."""
        return self._generateur.generer(
            self._champs(), self._titre_apercu(), self._marques_apercu(), "00145787",
            _APERCU_REMPLACE, _APERCU_EQUIVALENTES, lambda _reste: self._appareils_apercu(),
        )['html']

    def _update_preview(self):
        if not self._profiles:
            return
        try:
            contenu = self.apercu()
        except Exception as e:
            contenu = f"<p style='color:#c0392b;'>Aperçu impossible : {html.escape(str(e))}</p>"
        self.preview.setHtml(
            f"<html><body style='font-size: 13px; padding: 8px;'>{contenu}</body></html>")
