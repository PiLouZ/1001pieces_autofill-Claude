"""
Onglet « Titre » de la configuration des exports (v3.99.0)

Gabarits nommés du bouton « Titre » (titre de fiche produit) : gabarit avec
variables, nombre de marques et de types, longueur maximale, séparateurs.
Aperçu en direct sur des données fictives. Les gabarits sont listés dans la
colonne de gauche (ColonneVariantes), qui en garde la copie de travail jusqu'à
« Enregistrer » (cf. ExportConfigDialog._collect_config).
"""

import copy

from ..utils.qt_imports import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
                                QTextBrowser, QCheckBox)
from .champ_modele_html import ChampModeleHtml
from .colonne_variantes import ColonneVariantes
from src.utils.titre_produit_generator import TitreProduitGenerator
from .style_manager import StyleManager


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
        self._build_ui()

    # ─── Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        from .export_config_dialog import VariableChipsBar, BandeauRetour
        from src.services.export_config_service import DEFAULT_CONFIG

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        self.colonne = ColonneVariantes(
            'titre', self._store_fields, self._load_fields,
            lambda: copy.deepcopy(DEFAULT_CONFIG['titre']['profiles'][0]), "Titre")

        card, grid = self._dialog._build_card(
            "Titre de fiche produit",
            "Bouton Titre : copie le titre de la fiche recherchée. Au-delà de la "
            "longueur maximale, les dernières marques puis les derniers types sont "
            "retirés ; le libellé et la référence ne sont jamais coupés.",
        )
        add_row = self._dialog._add_grid_row

        # Gabarit sélectionné dans la colonne de gauche : nom + « Par défaut »
        card.layout().insertWidget(card.layout().count() - 1, self.colonne.barre_nom())

        # Zone colorée : les gabarits H2 contiennent du HTML
        self.template_input = ChampModeleHtml()
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

        self.varier_check = QCheckBox("Varier le nom de l'appareil")
        self.varier_check.setToolTip(
            "Cochée : le type peut être cité sous une autre appellation (« machine à laver »\n"
            "pour « lave-linge »), selon l'onglet Appareils. Décochée : le nom en base.\n"
            "Utile pour un gabarit repris dans une description.")
        add_row(grid, "Appareil :", self._seul(self.varier_check))

        self.max_car_spin = self._spin(0, 500, "Longueur maximale du titre (0 = sans limite)")
        self.max_car_spin.setSuffix(" car.")
        self.max_car_spin.setSpecialValueText("Sans limite")
        add_row(grid, "Longueur maximale :", self._seul(self.max_car_spin))

        # Séparateurs propres aux marques et aux types : « entre » | « avant le dernier »
        self.sep_marques_input, self.dernier_sep_marques_input = self._paire_separateurs(
            add_row, grid, "Séparateurs des marques :", "deux marques", "la dernière marque")
        self.sep_types_input, self.dernier_sep_types_input = self._paire_separateurs(
            add_row, grid, "Séparateurs des types :", "deux types", "le dernier type")

        reglages = QWidget()
        reglages_layout = QVBoxLayout(reglages)
        reglages_layout.setContentsMargins(0, 0, 6, 0)
        self.retour = BandeauRetour()
        reglages_layout.addWidget(self.retour)
        reglages_layout.addWidget(card)
        reglages_layout.addStretch()

        # Aperçu
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self._dialog._section_label("Aperçu (données fictives)"))
        self.preview = QTextBrowser()
        self.preview.setStyleSheet(StyleManager.CHAMP_BLANC_BORDE)
        right_layout.addWidget(self.preview)
        layout.addWidget(self._dialog._trois_colonnes(self.colonne, reglages, right))

        for champ in (self.template_input, self.sep_marques_input, self.dernier_sep_marques_input,
                      self.sep_types_input, self.dernier_sep_types_input):
            champ.textChanged.connect(self._update_preview)
        for spin in (self.max_marques_spin, self.max_types_spin, self.max_car_spin):
            spin.valueChanged.connect(self._update_preview)
        self.varier_check.toggled.connect(self._update_preview)

    @staticmethod
    def _paire_separateurs(add_row, grid, libelle, entre_quoi, avant_quoi):
        """Deux champs sur une ligne : entre deux éléments, avant le dernier."""
        entre, dernier = QLineEdit(), QLineEdit()
        for champ in (entre, dernier):
            champ.setMaximumWidth(80)
        entre.setToolTip(f"Texte entre {entre_quoi} (« , » par défaut)")
        dernier.setToolTip(f"Texte avant {avant_quoi} (« et » par défaut)")
        row = QHBoxLayout()
        row.addWidget(QLabel("entre"))
        row.addWidget(entre)
        row.addSpacing(8)
        row.addWidget(QLabel("avant le dernier"))
        row.addWidget(dernier)
        row.addStretch()
        add_row(grid, libelle, row)
        return entre, dernier

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
        """Copie de travail des gabarits de la config chargée."""
        self.colonne.load(titre_cfg['profiles'], titre_cfg['default_profile'])

    def collect(self) -> dict:
        profiles, defaut = self.colonne.collect()
        return {'profiles': profiles, 'default_profile': defaut}

    def _store_fields(self, profile):
        profile['template'] = self.template_input.text()
        profile['max_marques'] = self.max_marques_spin.value()
        profile['max_types'] = self.max_types_spin.value()
        profile['max_caracteres'] = self.max_car_spin.value()
        profile['varier_appareil'] = self.varier_check.isChecked()
        profile.update(self._separateurs())
        profile.pop('separateur', None)
        profile.pop('dernier_separateur', None)

    def _load_fields(self, profile):
        self.template_input.setText(profile.get('template', ''))
        self.max_marques_spin.setValue(profile.get('max_marques', 4))
        self.max_types_spin.setValue(profile.get('max_types', 3))
        self.max_car_spin.setValue(profile.get('max_caracteres', 120))
        self.varier_check.setChecked(bool(profile.get('varier_appareil', False)))
        self.sep_marques_input.setText(profile.get('separateur_marques', ', '))
        self.dernier_sep_marques_input.setText(profile.get('dernier_separateur_marques', ' et '))
        self.sep_types_input.setText(profile.get('separateur_types', ', '))
        self.dernier_sep_types_input.setText(profile.get('dernier_separateur_types', ' et '))
        self._update_preview()

    def _separateurs(self) -> dict:
        return {
            'separateur_marques': self.sep_marques_input.text(),
            'dernier_separateur_marques': self.dernier_sep_marques_input.text(),
            'separateur_types': self.sep_types_input.text(),
            'dernier_separateur_types': self.dernier_sep_types_input.text(),
        }

    # ─── Aperçu ──────────────────────────────────────────────────────────────

    def apercu(self) -> list:
        """Titres des données fictives avec les réglages affichés : [(titre, résumé)]."""
        profil = {
            'template': self.template_input.text(),
            'max_marques': self.max_marques_spin.value(),
            'max_types': self.max_types_spin.value(),
            'max_caracteres': self.max_car_spin.value(),
            **self._separateurs(),
        }
        appellations = self._appellations() if self.varier_check.isChecked() else None
        lignes = []
        for libelle, poids_types, marques, reference in _APERCU_TITRE:
            types = self._generateur.types_proches(poids_types, profil['max_types'])
            r = self._generateur.generer(profil, libelle, types, marques, reference,
                                         appellations=appellations)
            nb = len(r['info']['marques_retenues'])
            resume = f"{r['longueur']} car. — {nb} marque{'s' if nb > 1 else ''} sur {len(marques)}"
            lignes.append((r['titre'], resume))
        return lignes

    def showEvent(self, event):
        """Aperçu à jour des appellations modifiées entre-temps dans l'onglet Appareils."""
        super().showEvent(event)
        self._update_preview()

    def _appellations(self):
        """Appellations de l'onglet Appareils tel qu'affiché (non enregistré compris)."""
        from src.utils.appellations_appareils import Appellations
        onglet = getattr(self._dialog, 'appareils_tab', None)
        return Appellations(onglet.collect() if onglet is not None else None)

    def _update_preview(self):
        import html
        blocs = "".join(
            f"<p style='margin:6px 0 2px 0;'>{html.escape(titre)}</p>"
            f"<p style='margin:0 0 10px 0; color:#6c757d; font-size:11px;'>{html.escape(resume)}</p>"
            for titre, resume in self.apercu()
        )
        self.preview.setHtml(
            f"<html><body style='font-size: 13px; padding: 8px;'>{blocs}</body></html>")
