"""
Onglet « Appareils » de la configuration des exports

Appellations des types d'appareils dans les textes générés (méta title, méta
description, et les gabarits Titre qui le demandent) : « lave-linge » peut être
cité « machine à laver ».
À gauche les types (tels qu'en base) et leur genre, à droite les autres
appellations du type sélectionné, en dessous la part de chacune et un exemple.
La copie de travail (self._appareils) n'est enregistrée qu'avec « Enregistrer »
(cf. ExportConfigDialog._collect_config). Règles : src/utils/appellations_appareils.py
"""

import copy
import html

from ..utils.qt_imports import (
    Qt, QSize, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QTextBrowser,
)
from .style_manager import StyleManager
from src.utils.appellations_appareils import (
    Appellations, CHAMPS, CONFIG_PAR_DEFAUT, FEMININ, MASCULIN, SOUS_TYPE, SYNONYME,
    Appellation, TITRE, cle_type,
)

import qtawesome as qta


GENRES = [("masculin", MASCULIN), ("féminin", FEMININ)]
NATURES = [("synonyme", SYNONYME), ("sous-type", SOUS_TYPE)]
# Références fictives pour mesurer la part de chaque appellation dans l'aperçu
_NB_REFS_APERCU = 2000


class AppareilsConfigTab(QWidget):
    """Réglages des appellations des appareils."""

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._appareils = []
        self._courant = -1
        self._chargement = False
        self._build_ui()

    # ─── Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        card, grid = self._dialog._build_card(
            "Appellations des appareils",
            "Dans les textes générés, un appareil peut être cité sous une autre "
            "appellation (« machine à laver » pour « lave-linge »). Le choix est fixe "
            "pour une référence : régénérer une fiche ne le change pas. Une appellation "
            "qui obligerait à retirer une marque ou un mot est remplacée par le type en "
            "base. La colonne Type, les filtres et le CSV ne changent pas.",
        )
        add_row = self._dialog._add_grid_row

        self.actif_check = QCheckBox("Citer les appareils sous plusieurs appellations")
        add_row(grid, "Varier :", self.actif_check)

        self.part_spin = QSpinBox()
        self.part_spin.setRange(0, 100)
        self.part_spin.setSuffix(" %")
        self.part_spin.setMinimumWidth(110)
        self.part_spin.setToolTip("Part des fiches qui gardent le type en base ; les autres "
                                  "appellations actives se partagent le reste")
        add_row(grid, "Terme principal :", self._seul(self.part_spin))

        self.champ_checks = {}
        champs = QHBoxLayout()
        for cle, libelle in CHAMPS.items():
            check = QCheckBox(libelle)
            self.champ_checks[cle] = check
            champs.addWidget(check)
        champs.addStretch()
        add_row(grid, "Textes concernés :", champs)
        self.champ_checks['meta_title'].setToolTip(
            "Décochée par défaut : le méta title garde le mot-clé principal")

        # Types | appellations du type sélectionné
        self.types_table = QTableWidget(0, 2)
        self.types_table.setHorizontalHeaderLabels(["Type d'appareil (en base)", "Genre"])
        self._regler_table(self.types_table, colonne_large=0)
        self.types_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.types_table.itemSelectionChanged.connect(self._type_selectionne)
        self.types_table.itemChanged.connect(self._type_modifie)

        self.variantes_table = QTableWidget(0, 4)
        self.variantes_table.setHorizontalHeaderLabels(["Appellation", "Genre", "Nature", "Active"])
        self._regler_table(self.variantes_table, colonne_large=0)
        self.variantes_table.itemChanged.connect(lambda *_: self._variantes_modifiees())

        gauche = self._bloc("Types d'appareils", self.types_table,
                            "Ajouter un type", self._ajouter_type, self._supprimer_type)
        self.titre_variantes = QLabel()
        droite = self._bloc(self.titre_variantes, self.variantes_table,
                            "Ajouter une appellation", self._ajouter_variante,
                            self._supprimer_variante)
        aide = QLabel("Sous-type : juste pour une partie des appareils seulement "
                      "(« radiateur » pour « chauffage »). À n'activer qu'en connaissance de cause.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        droite.layout().addWidget(aide)

        tables = QSplitter(Qt.Horizontal)
        tables.setChildrenCollapsible(False)
        tables.addWidget(gauche)
        tables.addWidget(droite)
        tables.setSizes([320, 560])

        self.apercu = QTextBrowser()
        self.apercu.setStyleSheet(StyleManager.CHAMP_BLANC_BORDE)
        apercu = QWidget()
        apercu_layout = QVBoxLayout(apercu)
        apercu_layout.setContentsMargins(0, 0, 0, 0)
        apercu_layout.addWidget(self._dialog._section_label("Aperçu du type sélectionné"))
        apercu_layout.addWidget(self.apercu)

        bas = QSplitter(Qt.Vertical)
        bas.setChildrenCollapsible(False)
        bas.addWidget(tables)
        bas.addWidget(apercu)
        bas.setSizes([380, 200])

        layout.addWidget(card)
        layout.addWidget(bas, 1)

        self.actif_check.toggled.connect(self._reglages_modifies)
        self.part_spin.valueChanged.connect(self._update_preview)
        for check in self.champ_checks.values():
            check.toggled.connect(self._update_preview)

    @staticmethod
    def _seul(champ):
        row = QHBoxLayout()
        row.addWidget(champ)
        row.addStretch()
        return row

    @staticmethod
    def _regler_table(table, colonne_large):
        entete = table.horizontalHeader()
        for col in range(table.columnCount()):
            entete.setSectionResizeMode(
                col, QHeaderView.Stretch if col == colonne_large else QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)

    def _bloc(self, titre, table, libelle_ajout, ajouter, supprimer) -> QWidget:
        bloc = QWidget()
        layout = QVBoxLayout(bloc)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if isinstance(titre, QLabel):
            titre.setFont(self._dialog._section_label("").font())
            layout.addWidget(titre)
        else:
            layout.addWidget(self._dialog._section_label(titre))
        layout.addWidget(table)
        boutons = QHBoxLayout()
        for texte, icone, couleur, action in ((libelle_ajout, 'fa5s.plus', '#495057', ajouter),
                                              ("Supprimer", 'fa5s.minus', '#dc3545', supprimer)):
            bouton = QPushButton(texte)
            bouton.setIcon(qta.icon(icone, color=couleur))
            bouton.setIconSize(QSize(10, 10))
            bouton.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
            bouton.clicked.connect(action)
            boutons.addWidget(bouton)
        boutons.addStretch()
        layout.addLayout(boutons)
        return bloc

    @staticmethod
    def _combo(options, valeur, rappel) -> QComboBox:
        combo = QComboBox()
        for libelle, code in options:
            combo.addItem(libelle, code)
        index = combo.findData(valeur)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.currentIndexChanged.connect(lambda *_: rappel())
        return combo

    # ─── Chargement / collecte ───────────────────────────────────────────────

    def load(self, config: dict):
        """Copie de travail de la config chargée (déjà nettoyée par le service)."""
        config = config or CONFIG_PAR_DEFAUT
        self._chargement = True
        self.actif_check.setChecked(bool(config.get('actif', True)))
        self.part_spin.setValue(int(config.get('part_principal', 50)))
        for cle, check in self.champ_checks.items():
            check.setChecked(bool(config.get('champs', {}).get(cle, False)))
        self._appareils = copy.deepcopy(config.get('appareils', []))
        self._courant = -1
        self._remplir_types()
        self._chargement = False
        self._reglages_modifies()
        if self._appareils:
            self.types_table.selectRow(0)
        else:
            self._charger_variantes()

    def collect(self) -> dict:
        return {
            'actif': self.actif_check.isChecked(),
            'part_principal': self.part_spin.value(),
            'champs': {cle: check.isChecked() for cle, check in self.champ_checks.items()},
            'appareils': copy.deepcopy(self._appareils),
        }

    # ─── Types d'appareils ───────────────────────────────────────────────────

    def _remplir_types(self):
        chargement, self._chargement = self._chargement, True
        self.types_table.setRowCount(0)
        for i, appareil in enumerate(self._appareils):
            self._ajouter_ligne_type(i, appareil)
        self._chargement = chargement

    def _ajouter_ligne_type(self, ligne, appareil):
        self.types_table.insertRow(ligne)
        self.types_table.setItem(ligne, 0, QTableWidgetItem(appareil.get('type', '')))
        self.types_table.setCellWidget(ligne, 1, self._combo(
            GENRES, appareil.get('genre', MASCULIN), self._genres_types_modifies))

    def _genres_types_modifies(self):
        for i, appareil in enumerate(self._appareils):
            combo = self.types_table.cellWidget(i, 1)
            if combo is not None:
                appareil['genre'] = combo.currentData()
        self._update_preview()

    def _type_modifie(self, item):
        if self._chargement or item.column() != 0:
            return
        ligne = item.row()
        if 0 <= ligne < len(self._appareils):
            self._appareils[ligne]['type'] = cle_type(item.text())
            self._charger_variantes()

    def _type_selectionne(self):
        if self._chargement:
            return
        lignes = self.types_table.selectionModel().selectedRows()
        self._courant = lignes[0].row() if lignes else -1
        self._charger_variantes()

    def _ajouter_type(self):
        self._appareils.append({'type': '', 'genre': MASCULIN, 'variantes': []})
        ligne = len(self._appareils) - 1
        chargement, self._chargement = self._chargement, True
        self._ajouter_ligne_type(ligne, self._appareils[ligne])
        self._chargement = chargement
        self.types_table.selectRow(ligne)
        self.types_table.editItem(self.types_table.item(ligne, 0))

    def _supprimer_type(self):
        if not 0 <= self._courant < len(self._appareils):
            return
        ligne = self._courant
        del self._appareils[ligne]
        self._courant = -1
        self._remplir_types()
        if self._appareils:
            self.types_table.selectRow(min(ligne, len(self._appareils) - 1))
        else:
            self._charger_variantes()

    # ─── Appellations du type sélectionné ────────────────────────────────────

    def _appareil_courant(self):
        return self._appareils[self._courant] if 0 <= self._courant < len(self._appareils) else None

    def _charger_variantes(self):
        appareil = self._appareil_courant()
        chargement, self._chargement = self._chargement, True
        self.variantes_table.setRowCount(0)
        if appareil is None:
            self.titre_variantes.setText("Autres appellations")
        else:
            self.titre_variantes.setText(f"Autres appellations de « {appareil['type'] or '…'} »")
            for variante in appareil['variantes']:
                self._ajouter_ligne_variante(variante)
        self.variantes_table.setEnabled(appareil is not None)
        self._chargement = chargement
        self._update_preview()

    def _ajouter_ligne_variante(self, variante):
        ligne = self.variantes_table.rowCount()
        self.variantes_table.insertRow(ligne)
        self.variantes_table.setItem(ligne, 0, QTableWidgetItem(variante.get('terme', '')))
        self.variantes_table.setCellWidget(ligne, 1, self._combo(
            GENRES, variante.get('genre', MASCULIN), self._variantes_modifiees))
        self.variantes_table.setCellWidget(ligne, 2, self._combo(
            NATURES, variante.get('nature', SYNONYME), self._variantes_modifiees))
        active = QTableWidgetItem()
        active.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        active.setCheckState(Qt.Checked if variante.get('actif', True) else Qt.Unchecked)
        self.variantes_table.setItem(ligne, 3, active)

    def _variantes_modifiees(self):
        """Reporter le tableau des appellations dans la copie de travail."""
        appareil = self._appareil_courant()
        if self._chargement or appareil is None:
            return
        variantes = []
        for ligne in range(self.variantes_table.rowCount()):
            terme = self.variantes_table.item(ligne, 0)
            active = self.variantes_table.item(ligne, 3)
            genre = self.variantes_table.cellWidget(ligne, 1)
            nature = self.variantes_table.cellWidget(ligne, 2)
            variantes.append({
                'terme': terme.text().strip() if terme else '',
                'genre': genre.currentData() if genre else MASCULIN,
                'nature': nature.currentData() if nature else SYNONYME,
                'actif': active is not None and active.checkState() == Qt.Checked,
            })
        appareil['variantes'] = variantes
        self._update_preview()

    def _ajouter_variante(self):
        if self._appareil_courant() is None:
            return
        chargement, self._chargement = self._chargement, True
        self._ajouter_ligne_variante({'terme': '', 'genre': MASCULIN, 'nature': SYNONYME,
                                      'actif': True})
        self._chargement = chargement
        self._variantes_modifiees()
        ligne = self.variantes_table.rowCount() - 1
        self.variantes_table.selectRow(ligne)
        self.variantes_table.editItem(self.variantes_table.item(ligne, 0))

    def _supprimer_variante(self):
        lignes = sorted({i.row() for i in self.variantes_table.selectedIndexes()}, reverse=True)
        if not lignes:
            return
        chargement, self._chargement = self._chargement, True
        for ligne in lignes:
            self.variantes_table.removeRow(ligne)
        self._chargement = chargement
        self._variantes_modifiees()

    # ─── Aperçu ──────────────────────────────────────────────────────────────

    def _reglages_modifies(self):
        actif = self.actif_check.isChecked()
        self.part_spin.setEnabled(actif)
        for check in self.champ_checks.values():
            check.setEnabled(actif)
        self._update_preview()

    def apercu_type(self, type_appareil: str) -> list:
        """[(champ, [(appellation, part en %)])] du type avec les réglages affichés."""
        appellations = Appellations(self.collect())
        type_norm = cle_type(type_appareil)
        resultat = []
        for champ, libelle in [*CHAMPS.items(), (TITRE, "Titres (gabarits cochés)")]:
            comptes = {}
            for i in range(_NB_REFS_APERCU):
                choix = appellations.choisir(type_norm, f"REF{i}", champ)
                comptes[choix] = comptes.get(choix, 0) + 1
            parts = [(choix, round(100 * n / _NB_REFS_APERCU))
                     for choix, n in sorted(comptes.items(), key=lambda x: (-x[1], x[0].terme))]
            resultat.append((libelle, parts))
        return resultat

    def _update_preview(self):
        if self._chargement:
            return
        appareil = self._appareil_courant()
        if appareil is None or not appareil.get('type'):
            self.apercu.setHtml("<p style='color:#6c757d;'>Sélectionnez un type d'appareil.</p>")
            return
        lignes = []
        for libelle, parts in self.apercu_type(appareil['type']):
            detail = " · ".join(
                f"<b>{html.escape(choix.terme)}</b> {part} %" for choix, part in parts)
            lignes.append(f"<p style='margin:4px 0;'>{html.escape(libelle)} : {detail}</p>")
        exemples = [Appellation(appareil['type'], appareil.get('genre', MASCULIN), True)] + [
            Appellation(v['terme'], v['genre'], False)
            for v in appareil['variantes'] if v.get('actif') and v.get('terme')]
        phrases = "<br>".join(
            f"Redonnez vie à {html.escape(a.avec_article_indefini())} Bosch avec la pompe de "
            f"vidange 00145787" for a in exemples)
        lignes.append(f"<p style='margin:10px 0 2px 0; color:#6c757d;'>Accord :</p>"
                      f"<p style='margin:0;'>{phrases}</p>")
        self.apercu.setHtml(
            f"<html><body style='font-size: 13px; padding: 6px;'>{''.join(lignes)}</body></html>")
