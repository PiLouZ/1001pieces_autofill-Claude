"""
Onglet « Fiche » de la configuration des exports

Variantes du bouton « Fiche complète », listées dans la colonne de gauche
(ColonneVariantes, copie de travail jusqu'à « Enregistrer », cf.
ExportConfigDialog._collect_config). Les réglages suivent l'ordre de sortie de
la fiche, une carte par bloc : titre (gabarit Titre), marques (réglage commun
de l'onglet HTML), code produit, références remplacées, références
équivalentes, bloc Informations facultatif, liste des appareils (profil HTML
Détails) et limite de caractères de la fiche entière. Aperçu en direct sur des
données fictives.

« Modifier ce gabarit › » ouvre le gabarit dans son onglet, dans la même
fenêtre (même copie de travail : l'aperçu de la fiche suit la modification),
avec un bandeau de retour à la variante.
"""

import html
import re

import qtawesome as qta
from .qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QTextBrowser, QSizePolicy, Qt, QSize
)
from .style_manager import StyleManager
from .champ_modele_html import ChampModeleHtml
from .colonne_variantes import ColonneVariantes, COULEUR_ETOILE
from .titre_config_tab import _APERCU_TITRE
from src.services.html_export_service import HtmlExportService
from src.utils.fiche_produit_generator import FicheProduitGenerator
from src.utils.titre_produit_generator import TitreProduitGenerator


# Données fictives de l'aperçu (le titre reprend la 1ʳᵉ fiche de l'aperçu Titre)
_APERCU_MARQUES = ["Bosch", "Siemens", "Neff"]
_APERCU_REMPLACE = ["00144978"]
_APERCU_EQUIVALENTES = [["11008491"], ["00616190", "00499837"]]

_STYLE_LIEN = (
    "QPushButton { border: none; background: transparent; color: #0b5ed7;"
    " font-size: 11px; padding: 0px; text-align: left; }"
    "QPushButton:hover { text-decoration: underline; }"
)


class SelecteurGabarit(QComboBox):
    """Liste d'un gabarit d'un autre onglet (Titre, HTML Détails).

    « Gabarit par défaut (nom) » en tête, puis les gabarits dans l'ordre de leur
    colonne (défaut marqué d'une étoile, autres par ordre alphanumérique).
    Donnée : '' = gabarit par défaut, sinon le nom. Un nom disparu (supprimé)
    reste affiché, signalé : la fiche utilisera alors le gabarit par défaut.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setMinimumWidth(220)
        self.setMaxVisibleItems(20)
        self._etoile = qta.icon('fa5s.star', color=COULEUR_ETOILE)
        self._sans_etoile = qta.icon('fa5s.star', color='transparent')

    def remplir(self, noms_ordonnes, defaut, choisi):
        self.blockSignals(True)
        self.clear()
        self.addItem(self._sans_etoile, f"Gabarit par défaut ({defaut})", "")
        self.insertSeparator(1)
        for nom in noms_ordonnes:
            self.addItem(self._etoile if nom == defaut else self._sans_etoile, nom, nom)
        if choisi and choisi not in noms_ordonnes:
            self.addItem(qta.icon('fa5s.exclamation-triangle', color='#b45309'),
                         f"{choisi}  (introuvable : gabarit par défaut)", choisi)
        idx = self.findData(choisi or "")
        self.setCurrentIndex(idx if idx >= 0 else 0)
        self.blockSignals(False)


class FicheConfigTab(QWidget):
    """Réglages des variantes du bouton « Fiche complète »."""

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._generateur = FicheProduitGenerator()
        self._build_ui()

    # ─── Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        from .export_config_dialog import VariableChipsBar
        from src.services.export_config_service import DEFAULT_CONFIG
        import copy

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        self.colonne = ColonneVariantes(
            'fiche', self._store_fields, self._load_fields,
            lambda: copy.deepcopy(DEFAULT_CONFIG['fiche']['profiles'][0]), "Fiche complète")

        reglages = QWidget()
        reglages_layout = QVBoxLayout(reglages)
        reglages_layout.setContentsMargins(0, 0, 6, 0)
        reglages_layout.setSpacing(8)
        add_row = self._dialog._add_grid_row

        # En-tête : la variante sélectionnée
        entete, _ = self._dialog._build_card(
            "Fiche produit complète",
            "Bouton Fiche complète : les blocs ci-dessous, dans l'ordre où ils sont "
            "écrits, puis les appareils affichés dans le tableau. Une ligne de "
            "références sans référence n'est pas écrite.",
        )
        entete.layout().insertWidget(entete.layout().count() - 1, self.colonne.barre_nom())
        reglages_layout.addWidget(entete)

        # 1. Titre
        card, grid = self._carte("1 · Titre")
        self.titre_combo = SelecteurGabarit()
        self.titre_combo.setToolTip("Gabarit de l'onglet Titre utilisé pour le titre de la fiche")
        add_row(grid, "Gabarit :", self._seul(self.titre_combo))
        self.titre_apercu_label = QLabel()
        self.titre_apercu_label.setWordWrap(True)
        self.titre_apercu_label.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        add_row(grid, "", self.titre_apercu_label)
        add_row(grid, "", self._seul(self._lien(
            "Modifier ce gabarit ›", lambda: self._modifier_gabarit('titre'))))
        reglages_layout.addWidget(card)

        # 2. Marques : réglage commun à toutes les variantes, dans l'onglet HTML
        card, grid = self._carte("2 · Compatible avec (marques)")
        marques = QLabel("Commun à toutes les variantes : liens des marques réglés dans "
                         "l'onglet HTML (Liste des marques).")
        marques.setWordWrap(True)
        marques.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        add_row(grid, "", marques)
        add_row(grid, "", self._seul(self._lien(
            "Régler dans l'onglet HTML ›", self._regler_marques)))
        reglages_layout.addWidget(card)

        # 3. Code produit
        card, grid = self._carte("3 · Code produit")
        self.code_input = ChampModeleHtml()
        add_row(grid, "Ligne :", self.code_input, VariableChipsBar(
            [("reference", "Référence tapée ; si elle est remplacée, la plus récente")],
            targets=[self.code_input],
        ))
        reglages_layout.addWidget(card)

        # 4. Références remplacées
        card, grid = self._carte("4 · Remplace les références")
        self.remplace_input = ChampModeleHtml()
        self.remplace_input.setToolTip("Écrite seulement si la référence remplace d'anciennes références")
        add_row(grid, "Ligne :", self.remplace_input, VariableChipsBar(
            [("references", "Anciennes références, jointes par le séparateur")],
            targets=[self.remplace_input],
        ))
        reglages_layout.addWidget(card)

        # 5. Références équivalentes (+ séparateur, commun aux lignes 4 et 5)
        card, grid = self._carte("5 · Références équivalentes")
        self.equivalentes_input = ChampModeleHtml()
        self.equivalentes_input.setToolTip(
            "Toutes les références équivalentes, chacune suivie de ses anciennes références,\n"
            "de la plus fournie en appareils à la moins fournie")
        add_row(grid, "Ligne :", self.equivalentes_input, VariableChipsBar(
            [("references", "Références équivalentes, jointes par le séparateur")],
            targets=[self.equivalentes_input],
        ))
        self.separateur_input = QLineEdit()
        self.separateur_input.setMaximumWidth(80)
        self.separateur_input.setToolTip(
            "Texte entre deux références d'une même ligne (blocs 4 et 5 ; une espace par défaut)")
        add_row(grid, "Séparateur (4 et 5) :", self._seul(self.separateur_input))
        reglages_layout.addWidget(card)

        # 6. Bloc Informations
        card, grid = self._carte("6 · Bloc Informations")
        self.informations_check = QCheckBox("Inclure le bloc Informations")
        self.informations_check.setToolTip("Bloc à compléter ensuite sur le site, placé avant la liste des appareils")
        add_row(grid, "", self._seul(self.informations_check))
        self.informations_input = ChampModeleHtml()
        add_row(grid, "Bloc :", self.informations_input)
        reglages_layout.addWidget(card)

        # 7. Liste des appareils + limite de la fiche entière (c'est la liste qu'elle raccourcit)
        card, grid = self._carte("7 · Liste des appareils")
        self.details_combo = SelecteurGabarit()
        self.details_combo.setToolTip("Profil de l'onglet HTML (liste des appareils) utilisé pour la fiche")
        add_row(grid, "Profil :", self._seul(self.details_combo))
        add_row(grid, "", self._seul(self._lien(
            "Modifier ce profil ›", lambda: self._modifier_gabarit('html_details'))))
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
        add_row(grid, "Limite de la fiche :", self._seul(self.max_car_spin))
        reglages_layout.addWidget(card)
        reglages_layout.addStretch()

        # Aperçu
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self._dialog._section_label("Aperçu (données fictives)"))
        self.preview = QTextBrowser()
        self.preview.setStyleSheet("background: white; border: 1px solid #dee2e6;")
        right_layout.addWidget(self.preview)
        layout.addWidget(self._dialog._trois_colonnes(self.colonne, reglages, right))

        for champ in (self.code_input, self.remplace_input, self.equivalentes_input,
                      self.separateur_input, self.informations_input):
            champ.textChanged.connect(self._update_preview)
        self.informations_check.toggled.connect(self._on_informations_toggled)
        for combo in (self.titre_combo, self.details_combo):
            combo.currentIndexChanged.connect(self._update_preview)
        self.max_car_spin.valueChanged.connect(self._update_preview)

    # Colonne des étiquettes de même largeur dans toutes les cartes : champs alignés
    LARGEUR_ETIQUETTES = 135

    def _carte(self, titre):
        card, grid = self._dialog._build_card(titre)
        grid.setColumnMinimumWidth(0, self.LARGEUR_ETIQUETTES)
        return card, grid

    @staticmethod
    def _seul(champ):
        row = QHBoxLayout()
        row.addWidget(champ)
        row.addStretch()
        return row

    @staticmethod
    def _lien(texte, slot):
        lien = QPushButton(texte)
        lien.setCursor(Qt.PointingHandCursor)
        lien.setStyleSheet(_STYLE_LIEN)
        lien.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lien.clicked.connect(slot)
        return lien

    def _on_informations_toggled(self, coche):
        self.informations_input.setEnabled(coche)
        self._update_preview()

    # ─── Gabarits des autres onglets ─────────────────────────────────────────

    def _colonne_titre(self):
        return self._dialog.titre_tab.colonne

    def _colonne_details(self):
        return self._dialog.details_colonne

    def _remplir_selecteurs(self, titre_choisi, details_choisi):
        for combo, colonne, choisi in ((self.titre_combo, self._colonne_titre(), titre_choisi),
                                       (self.details_combo, self._colonne_details(), details_choisi)):
            combo.remplir(colonne.noms_ordonnes(), colonne.nom_defaut, choisi)

    def rafraichir_gabarits(self):
        """Listes Titre / appareils à jour des autres onglets (copies de travail)."""
        if not self.colonne.noms():
            return
        self._remplir_selecteurs(self.titre_combo.currentData() or "",
                                 self.details_combo.currentData() or "")
        self._update_preview()

    def showEvent(self, event):
        super().showEvent(event)
        self.rafraichir_gabarits()

    def renommer_gabarit(self, cle: str, ancien: str, nouveau: str):
        """Un gabarit Titre ('titre_profile') ou HTML Détails ('details_profile')
        renommé : les variantes qui l'utilisent suivent le nouveau nom."""
        if not self.colonne.noms():
            return
        self.colonne.stocker()
        self.colonne.modifier_tous(lambda p: p.update({cle: nouveau}) if p.get(cle) == ancien else None)
        profil = self.colonne.profil_courant()
        self._remplir_selecteurs(profil.get('titre_profile', ''), profil.get('details_profile', ''))

    def _modifier_gabarit(self, genre: str):
        """Ouvrir le gabarit choisi dans son onglet, avec un bandeau de retour."""
        if genre == 'titre':
            combo, colonne, bandeau = self.titre_combo, self._colonne_titre(), self._dialog.titre_tab.retour
        else:
            combo, colonne, bandeau = self.details_combo, self._colonne_details(), self._dialog.html_retour
        nom = combo.currentData() or ""
        if nom not in colonne.noms():
            nom = colonne.nom_defaut
        variante = self.colonne.nom_courant
        self._dialog.ouvrir_sur(genre, nom)
        bandeau.afficher(f"Retour à la fiche « {variante} »",
                         lambda: self._dialog.ouvrir_sur('fiche', variante))

    def _regler_marques(self):
        variante = self.colonne.nom_courant
        self._dialog.afficher_onglet(self._dialog._ONGLETS['html_details'])
        self._dialog.html_retour.afficher(f"Retour à la fiche « {variante} »",
                                          lambda: self._dialog.ouvrir_sur('fiche', variante))

    # ─── Chargement / collecte ───────────────────────────────────────────────

    def load(self, fiche_cfg: dict):
        """Copie de travail des variantes de la config chargée."""
        self.colonne.load(fiche_cfg['profiles'], fiche_cfg['default_profile'])

    def collect(self) -> dict:
        profiles, defaut = self.colonne.collect()
        return {'profiles': profiles, 'default_profile': defaut}

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

    def _store_fields(self, profile):
        profile.update(self._champs())

    def _load_fields(self, profile):
        self._remplir_selecteurs(profile.get('titre_profile', ''), profile.get('details_profile', ''))
        self.code_input.setText(profile.get('code_produit_template', ''))
        self.remplace_input.setText(profile.get('remplace_template', ''))
        self.equivalentes_input.setText(profile.get('equivalentes_template', ''))
        self.informations_input.setText(profile.get('informations_template', ''))
        self.separateur_input.setText(profile.get('separateur_references', ' '))
        self.max_car_spin.setValue(profile.get('max_caracteres', 200000))
        self.informations_check.setChecked(bool(profile.get('inclure_informations')))
        self.informations_input.setEnabled(self.informations_check.isChecked())
        self._update_preview()

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
        if not self.colonne.noms():
            return
        try:
            titre = html.unescape(re.sub(r"<[^>]+>", "", self._titre_apercu())).strip()
            self.titre_apercu_label.setText(f"Aperçu : « {titre} »")
            contenu = self.apercu()
        except Exception as e:
            contenu = f"<p style='color:#c0392b;'>Aperçu impossible : {html.escape(str(e))}</p>"
        self.preview.setHtml(
            f"<html><body style='font-size: 13px; padding: 8px;'>{contenu}</body></html>")
