"""Écran « Règles de nomenclature » (CDC docs/cdc_regles_nomenclature.md § 8.1, lot 4).

- Liste filtrable des règles : marque ou groupe, motif (jokers des filtres de
  colonne : `*` `?` `|` `!`), type, statut, source ; cases « changeraient des
  appareils » (désaccords > 0, filtre par défaut quand la découverte a ajouté
  des milliers de règles) et « pureté ≥ 98 % (D7) ».
- Fiche d'une règle : bandeau si elle a été trouvée sous une zone grise,
  mesures, lien source, note, exemples d'appareils (désaccords d'abord),
  Valider / Rejeter / Remettre en proposée, « Revoir ses propositions ».
  Valider ou rejeter plusieurs règles sélectionnées passe par un récapitulatif
  (D4 : jamais de validation automatique, D7 se lit, ne s'applique pas seul).
- Après un changement de statut, les propositions sont recalculées en
  arrière-plan (`CalculNomenclature`) ; « Chercher de nouvelles règles »
  lance la découverte de la même façon (résultat en statut « proposée »).
- Onglet « Acceptations » : les lots acceptés depuis la revue, chacun
  annulable (le type d'avant revient sur les appareils encore au type accepté).

Non bloquant : show() + callbacks (jamais exec_(), cf. conventions projet).
"""

from collections import Counter

import qtawesome as qta
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTableView,
    QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from src.core.config import pluralize
from src.core.logger import app_logger
from src.services.regle_nomenclature_service import (
    RegleNomenclatureService, libelle_regle, pure_d7, purete, zone_grise_de)
from src.utils.filtre_colonne import correspond_au_filtre
from .calcul_nomenclature import MODE_DECOUVRIR, MODE_PROPOSER, CalculNomenclature
from .fenetre_revue import html
from .style_manager import StyleManager

_STATUTS = {'proposee': ("Proposée", '#b06a00', 'fa5s.question-circle'),
            'validee': ("Validée", '#198754', 'fa5s.check-circle'),
            'rejetee': ("Rejetée", '#dc3545', 'fa5s.times-circle')}
_ORIGINES = {'web': "Web", 'decouverte': "Découverte", 'saisie': "Saisie"}

(COL_STATUT, COL_CIBLE, COL_CLE, COL_MOTIF, COL_TYPE, COL_COUVERTURE, COL_ACCORD,
 COL_DESACCORDS, COL_EN_ATTENTE, COL_SOURCE, COL_ZONE) = range(11)
_ENTETES = ["Statut", "Marque / groupe", "Clé", "Motif", "Type", "Couverture", "Accord",
            "Désaccords", "Proposés", "Source", "Zone grise"]
ROLE_TRI = Qt.UserRole + 1
ROLE_REGLE = Qt.UserRole + 2


def desaccords(regle) -> int:
    couverture, accord = regle.get('couverture'), regle.get('accord')
    if couverture is None or accord is None:
        return 0
    return max(0, couverture - accord)


class ModeleRegles(QAbstractTableModel):
    """Règles (dicts de `lister_regles_nomenclature`) + propositions en attente."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._regles = []
        self._en_attente = Counter()
        self._icones = {}

    def charger(self, regles, en_attente):
        self.beginResetModel()
        self._regles = list(regles)
        self._en_attente = Counter(en_attente)
        self.endResetModel()

    def regle(self, ligne):
        return self._regles[ligne] if 0 <= ligne < len(self._regles) else None

    def regles(self):
        return list(self._regles)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._regles)

    def columnCount(self, parent=QModelIndex()):
        return len(_ENTETES)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _ENTETES[section]
        return None

    def _icone(self, nom, couleur):
        cle = (nom, couleur)
        if cle not in self._icones:
            self._icones[cle] = qta.icon(nom, color=couleur)
        return self._icones[cle]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._regles[index.row()]
        col = index.column()
        if role == ROLE_REGLE:
            return r
        p = purete(r)
        if role in (Qt.DisplayRole, ROLE_TRI):
            tri = role == ROLE_TRI
            if col == COL_STATUT:
                return _STATUTS.get(r['statut'], (r['statut'],))[0]
            if col == COL_CIBLE:
                return (f"groupe {r['cible']}" if r['portee'] == 'groupe' else r['cible'])
            if col == COL_CLE:
                return "nom" if r['cle'] == 'nom' else "code"
            if col == COL_MOTIF:
                return r['motif']
            if col == COL_TYPE:
                return r['type_resultat']
            if col == COL_COUVERTURE:
                return (r.get('couverture') or 0) if tri else (
                    "" if r.get('couverture') is None else str(r['couverture']))
            if col == COL_ACCORD:
                return (p if p is not None else -1) if tri else (
                    "" if p is None else f"{p * 100:.1f} %")
            if col == COL_DESACCORDS:
                n = desaccords(r)
                return n if tri else (str(n) if n else "")
            if col == COL_EN_ATTENTE:
                n = self._en_attente.get(r['id'], 0)
                return n if tri else (str(n) if n else "")
            if col == COL_SOURCE:
                return _ORIGINES.get(r['origine'], r['origine'])
            if col == COL_ZONE:
                return zone_grise_de(r)
        if role == Qt.DecorationRole:
            if col == COL_STATUT:
                _, couleur, icone = _STATUTS.get(r['statut'], ("", '#6c757d', 'fa5s.circle'))
                return self._icone(icone, couleur)
            if col == COL_SOURCE and (r.get('source_url') or '').strip():
                return self._icone('fa5s.link', '#0d6efd')
            if col == COL_ZONE and zone_grise_de(r):
                return self._icone('fa5s.exclamation-triangle', '#b06a00')
        if role == Qt.ForegroundRole:
            if col == COL_STATUT:
                return QBrush(QColor(_STATUTS.get(r['statut'], ("", '#6c757d'))[1]))
            if col == COL_DESACCORDS and desaccords(r):
                return QBrush(QColor('#c0392b'))
        if role == Qt.TextAlignmentRole and col in (COL_COUVERTURE, COL_ACCORD, COL_DESACCORDS,
                                                    COL_EN_ATTENTE):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            if col == COL_ZONE and zone_grise_de(r):
                return (f"Trouvée sous la zone grise {zone_grise_de(r)} (préfixe mélangé) : "
                        f"à regarder de près avant de valider")
            if col == COL_SOURCE and (r.get('source_url') or '').strip():
                return r['source_url']
            if col == COL_ACCORD and pure_d7(r):
                return "Pureté ≥ 98 % : validable d'office si un 2e signal concorde (D7)"
        return None


class FiltreRegles(QSortFilterProxyModel):
    """Filtres de l'écran (critères combinés en ET)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cible = ''
        self.motif = ''
        self.type = ''
        self.statut = ''
        self.origine = ''
        self.changeraient = False
        self.d7 = False
        self.setSortRole(ROLE_TRI)

    def filterAcceptsRow(self, ligne, parent):
        r = self.sourceModel().regle(ligne)
        if r is None:
            return False
        if self.cible and self.cible.lower() not in r['cible'].lower():
            return False
        if self.motif and not correspond_au_filtre(r['motif'], self.motif):
            return False
        if self.type and r['type_resultat'] != self.type:
            return False
        if self.statut and r['statut'] != self.statut:
            return False
        if self.origine and r['origine'] != self.origine:
            return False
        if self.changeraient and not desaccords(r):
            return False
        if self.d7 and not pure_d7(r):
            return False
        return True


class ReglesNomenclatureDialog(QDialog):
    """Écran des règles. `on_propositions_changees()` : rappelé après chaque
    recalcul ou annulation (la fenêtre principale relit ses types proposés).
    `ouvrir_revue(regle_id|None)` : ouvre la revue (filtrée sur une règle)."""

    def __init__(self, parent, db_manager, revue_service, on_propositions_changees=None,
                 ouvrir_revue=None):
        super().__init__(parent)
        self.setObjectName("reglesNomenclatureDialog")
        self.db_manager = db_manager
        self.service = RegleNomenclatureService(db_manager, parent)
        self.revue = revue_service
        self._on_propositions_changees = on_propositions_changees or (lambda: None)
        self._ouvrir_revue = ouvrir_revue or (lambda regle_id=None: None)
        self._calcul = None
        self._recalcul_demande = False
        self._message_decouverte = ''
        self._regle_courante = None
        self.setWindowTitle("Règles de nomenclature")
        self.resize(1280, 760)
        self.setMinimumSize(900, 520)
        self._construire()
        self.recharger()

    # ── Construction ─────────────────────────────────────────────────────────
    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setSpacing(8)

        tete = QHBoxLayout()
        self._titre = QLabel()
        self._titre.setStyleSheet("font-size: 15px; font-weight: bold; color: #212529;")
        tete.addWidget(self._titre)
        tete.addStretch()
        self._etat_calcul = QLabel()
        self._etat_calcul.setStyleSheet("color: #6c757d;")
        tete.addWidget(self._etat_calcul)
        racine.addLayout(tete)

        filtres = QHBoxLayout()
        filtres.setSpacing(6)
        self._f_cible = QLineEdit()
        self._f_cible.setPlaceholderText("Marque ou groupe")
        self._f_cible.setClearButtonEnabled(True)
        self._f_cible.setFixedWidth(150)
        self._f_motif = QLineEdit()
        self._f_motif.setPlaceholderText("Motif (AK*, EW?F*…)")
        self._f_motif.setClearButtonEnabled(True)
        self._f_motif.setFixedWidth(150)
        self._f_motif.setToolTip("Jokers des filtres de colonne : * n'importe quoi, ? un "
                                 "caractère, | ou, ! sauf")
        self._f_type = QComboBox()
        self._f_statut = QComboBox()
        for libelle, cle in (("Tous statuts", ''), ("Proposées", 'proposee'),
                             ("Validées", 'validee'), ("Rejetées", 'rejetee')):
            self._f_statut.addItem(libelle, cle)
        self._f_origine = QComboBox()
        for libelle, cle in (("Toutes sources", ''), ("Web", 'web'),
                             ("Découverte", 'decouverte'), ("Saisie", 'saisie')):
            self._f_origine.addItem(libelle, cle)
        self._f_changeraient = QCheckBox("Changeraient des appareils")
        self._f_changeraient.setToolTip("Règles dont au moins un appareil couvert n'a pas "
                                        "encore le type de la règle")
        self._f_d7 = QCheckBox("Pureté ≥ 98 % (D7)")
        for w in (self._f_cible, self._f_motif, self._f_type, self._f_statut, self._f_origine,
                  self._f_changeraient, self._f_d7):
            filtres.addWidget(w)
        filtres.addStretch()
        racine.addLayout(filtres)
        self._f_cible.textChanged.connect(lambda _: self._appliquer_filtres())
        self._f_motif.textChanged.connect(lambda _: self._appliquer_filtres())
        for combo in (self._f_type, self._f_statut, self._f_origine):
            combo.currentIndexChanged.connect(lambda _: self._appliquer_filtres())
        for case in (self._f_changeraient, self._f_d7):
            case.toggled.connect(lambda _: self._appliquer_filtres())

        separateur = QSplitter(Qt.Horizontal)
        self._modele = ModeleRegles(self)
        self._filtre = FiltreRegles(self)
        self._filtre.setSourceModel(self._modele)
        self._table = QTableView()
        self._table.setModel(self._filtre)
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(COL_DESACCORDS, Qt.DescendingOrder)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(22)
        entete = self._table.horizontalHeader()
        entete.setSectionResizeMode(QHeaderView.Interactive)
        entete.setStretchLastSection(False)
        for col, largeur in ((COL_STATUT, 94), (COL_CIBLE, 130), (COL_CLE, 42), (COL_MOTIF, 104),
                             (COL_TYPE, 150), (COL_COUVERTURE, 98), (COL_ACCORD, 70),
                             (COL_DESACCORDS, 104), (COL_EN_ATTENTE, 86), (COL_SOURCE, 92),
                             (COL_ZONE, 82)):
            self._table.setColumnWidth(col, largeur)
        self._table.selectionModel().selectionChanged.connect(lambda *_: self._maj_fiche())
        separateur.addWidget(self._table)

        self._onglets = QTabWidget()
        self._onglets.addTab(self._construire_fiche(), "Règle")
        self._onglets.addTab(self._construire_acceptations(), "Acceptations")
        self._onglets.setMinimumWidth(360)
        separateur.addWidget(self._onglets)
        separateur.setStretchFactor(0, 3)
        separateur.setStretchFactor(1, 2)
        separateur.setSizes([900, 380])
        racine.addWidget(separateur, 1)

        bas = QHBoxLayout()
        self._btn_decouvrir = QPushButton("Chercher de nouvelles règles")
        self._btn_decouvrir.setIcon(qta.icon('fa5s.search-plus', color='#495057'))
        self._btn_decouvrir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self._btn_decouvrir.setToolTip("Découverte dans les données (en arrière-plan) : "
                                       "les nouvelles règles arrivent en statut « proposée »")
        self._btn_decouvrir.setAutoDefault(False)
        self._btn_decouvrir.clicked.connect(self.chercher_nouvelles_regles)
        bas.addWidget(self._btn_decouvrir)
        self._btn_recalculer = QPushButton("Recalculer les propositions")
        self._btn_recalculer.setIcon(qta.icon('fa5s.sync-alt', color='#495057'))
        self._btn_recalculer.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self._btn_recalculer.setAutoDefault(False)
        self._btn_recalculer.clicked.connect(self.recalculer_propositions)
        bas.addWidget(self._btn_recalculer)
        bas.addStretch()
        self._btn_revue = QPushButton()
        self._btn_revue.setIcon(qta.icon('fa5s.tasks', color='white'))
        self._btn_revue.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self._btn_revue.setAutoDefault(False)
        self._btn_revue.clicked.connect(lambda: self._ouvrir_revue(None))
        bas.addWidget(self._btn_revue)
        fermer = QPushButton("Fermer")
        fermer.setAutoDefault(False)
        fermer.clicked.connect(self.close)
        bas.addWidget(fermer)
        racine.addLayout(bas)

    def _construire_fiche(self):
        fiche = QWidget()
        disposition = QVBoxLayout(fiche)
        disposition.setContentsMargins(6, 6, 6, 6)
        self._fiche_titre = QLabel()
        self._fiche_titre.setWordWrap(True)
        self._fiche_titre.setStyleSheet("font-size: 14px; font-weight: bold;")
        disposition.addWidget(self._fiche_titre)
        self._bandeau_zone = QLabel()
        self._bandeau_zone.setWordWrap(True)
        self._bandeau_zone.setStyleSheet(StyleManager.BANDEAU_ZONE_GRISE)
        self._bandeau_zone.setVisible(False)
        disposition.addWidget(self._bandeau_zone)
        self._fiche_infos = QLabel()
        self._fiche_infos.setWordWrap(True)
        self._fiche_infos.setTextFormat(Qt.RichText)
        self._fiche_infos.setOpenExternalLinks(False)
        self._fiche_infos.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        disposition.addWidget(self._fiche_infos)

        actions = QHBoxLayout()
        self._btn_valider = self._bouton("Valider", 'fa5s.check', '#198754',
                                         lambda: self.changer_statut('validee'))
        self._btn_rejeter = self._bouton("Rejeter", 'fa5s.times', '#dc3545',
                                         lambda: self.changer_statut('rejetee'))
        self._btn_proposee = self._bouton("Remettre en proposée", 'fa5s.undo', '#6c757d',
                                          lambda: self.changer_statut('proposee'))
        for b in (self._btn_valider, self._btn_rejeter, self._btn_proposee):
            actions.addWidget(b)
        actions.addStretch()
        disposition.addLayout(actions)
        self._btn_revue_regle = self._bouton("Revoir ses propositions", 'fa5s.tasks', '#138a72',
                                             self._revoir_regle_courante)
        disposition.addWidget(self._btn_revue_regle)

        disposition.addWidget(QLabel("Note"))
        self._note = QTextEdit()
        self._note.setFixedHeight(54)
        disposition.addWidget(self._note)
        self._btn_note = self._bouton("Enregistrer la note", 'fa5s.save', '#495057',
                                      self.enregistrer_note)
        disposition.addWidget(self._btn_note, 0, Qt.AlignLeft)

        disposition.addWidget(QLabel("Exemples (désaccords d'abord)"))
        self._exemples = QTextBrowser()
        self._exemples.setStyleSheet(
            "QTextBrowser { background: #f8f9fa; border: 1px solid #dee2e6;"
            " border-radius: 4px; padding: 4px; font-size: 12px; }")
        disposition.addWidget(self._exemples, 1)
        return fiche

    def _construire_acceptations(self):
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(6, 6, 6, 6)
        aide = QLabel("Acceptations faites depuis la revue des types proposés. Annuler "
                      "remet le type d'avant sur les appareils encore au type accepté ; "
                      "un appareil modifié depuis est laissé tel quel.")
        aide.setWordWrap(True)
        aide.setStyleSheet("color: #6c757d;")
        disposition.addWidget(aide)
        self._lots = QListWidget()
        self._lots.currentItemChanged.connect(lambda *_: self._maj_bouton_annuler())
        disposition.addWidget(self._lots, 1)
        self._btn_annuler_lot = self._bouton("Annuler cette acceptation", 'fa5s.undo-alt',
                                             '#dc3545', self.annuler_lot_courant)
        disposition.addWidget(self._btn_annuler_lot, 0, Qt.AlignLeft)
        return onglet

    @staticmethod
    def _bouton(texte, icone, couleur, action):
        bouton = QPushButton(texte)
        bouton.setIcon(qta.icon(icone, color=couleur))
        bouton.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        bouton.setAutoDefault(False)
        bouton.clicked.connect(lambda: action())
        return bouton

    # ── Données ──────────────────────────────────────────────────────────────
    def recharger(self):
        """Relire les règles, les propositions en attente et les lots."""
        selection = {r['id'] for r in self.regles_selectionnees()}
        regles = self.db_manager.lister_regles_nomenclature()
        en_attente = Counter(p['regle_id'] for p in (self.db_manager.lire_propositions_type() or []))
        self._modele.charger(regles, en_attente)
        types = sorted({r['type_resultat'] for r in regles})
        courant = self._f_type.currentData()
        self._f_type.blockSignals(True)
        self._f_type.clear()
        self._f_type.addItem("Tous types", '')
        for t in types:
            self._f_type.addItem(t, t)
        index = self._f_type.findData(courant) if courant else 0
        self._f_type.setCurrentIndex(max(0, index))
        self._f_type.blockSignals(False)
        self._appliquer_filtres()
        self._reselectionner(selection)
        statuts = Counter(r['statut'] for r in regles)
        n_prop = sum(en_attente.values())
        self._titre.setText(
            f"Règles de nomenclature — {pluralize(len(regles), 'règle')} "
            f"({statuts['validee']} validée{'s' if statuts['validee'] > 1 else ''}, "
            f"{statuts['proposee']} proposée{'s' if statuts['proposee'] > 1 else ''}, "
            f"{statuts['rejetee']} rejetée{'s' if statuts['rejetee'] > 1 else ''})")
        self._btn_revue.setText(f"Revoir les types proposés ({n_prop})")
        self._btn_revue.setEnabled(n_prop > 0)
        self._recharger_lots()
        self._maj_fiche()

    def _reselectionner(self, ids):
        if not ids:
            return
        selection = self._table.selectionModel()
        for ligne in range(self._filtre.rowCount()):
            r = self._filtre.data(self._filtre.index(ligne, 0), ROLE_REGLE)
            if r and r['id'] in ids:
                selection.select(self._filtre.index(ligne, 0),
                                 selection.Select | selection.Rows)

    def _recharger_lots(self):
        self._lots.clear()
        for lot in self.revue.lots():
            texte = f"{lot['accepte_le']} — {lot['libelle']} — {pluralize(lot['nb'], 'appareil')}"
            if lot.get('annule_le'):
                texte += f" (annulée le {lot['annule_le']})"
            item = QListWidgetItem(texte)
            item.setData(Qt.UserRole, lot)
            if lot.get('annule_le'):
                item.setForeground(QBrush(QColor('#9e9e9e')))
            self._lots.addItem(item)
        self._maj_bouton_annuler()

    def _appliquer_filtres(self):
        f = self._filtre
        f.cible = self._f_cible.text().strip()
        f.motif = self._f_motif.text().strip()
        f.type = self._f_type.currentData() or ''
        f.statut = self._f_statut.currentData() or ''
        f.origine = self._f_origine.currentData() or ''
        f.changeraient = self._f_changeraient.isChecked()
        f.d7 = self._f_d7.isChecked()
        f.invalidateFilter()

    def regles_selectionnees(self):
        if not hasattr(self, '_table'):
            return []
        lignes = sorted({i.row() for i in self._table.selectionModel().selectedRows()})
        return [self._filtre.data(self._filtre.index(l, 0), ROLE_REGLE) for l in lignes]

    def selectionner_regle(self, regle_id):
        for ligne in range(self._filtre.rowCount()):
            r = self._filtre.data(self._filtre.index(ligne, 0), ROLE_REGLE)
            if r and r['id'] == regle_id:
                self._table.selectRow(ligne)
                return True
        return False

    # ── Fiche ────────────────────────────────────────────────────────────────
    def _maj_fiche(self):
        regles = self.regles_selectionnees()
        un = len(regles) == 1
        r = regles[0] if un else None
        self._regle_courante = r
        for w in (self._note, self._btn_note, self._btn_revue_regle):
            w.setEnabled(un)
        self._btn_valider.setEnabled(bool(regles))
        self._btn_rejeter.setEnabled(bool(regles))
        self._btn_proposee.setEnabled(bool(regles))
        if not un:
            self._btn_revue_regle.setText("Revoir ses propositions")
        if not regles:
            self._fiche_titre.setText("Aucune règle sélectionnée")
            self._bandeau_zone.setVisible(False)
            self._fiche_infos.setText("")
            self._note.setPlainText("")
            self._exemples.setHtml("")
            return
        if not un:
            couverture = sum(x.get('couverture') or 0 for x in regles)
            self._fiche_titre.setText(f"{pluralize(len(regles), 'règle')} sélectionnées")
            self._bandeau_zone.setVisible(False)
            self._fiche_infos.setText(
                f"{couverture} appareils couverts, "
                f"{sum(desaccords(x) for x in regles)} en désaccord.")
            self._note.setPlainText("")
            self._exemples.setHtml("")
            return
        self._fiche_titre.setText(html(libelle_regle(r)))
        zone = zone_grise_de(r)
        self._bandeau_zone.setText(
            f"Trouvée sous la zone grise {zone} : ce préfixe mélange plusieurs types. "
            f"Une erreur systématique (comme « Four Vapeur » sur les Whirlpool AKP) "
            f"peut s'y cacher : vérifier une source avant de valider." if zone else "")
        self._bandeau_zone.setVisible(bool(zone))
        p = purete(r)
        en_attente = self._modele._en_attente.get(r['id'], 0)
        source = (f"<a href='{html(r['source_url'])}'>{html(r['source_url'])}</a>"
                  if (r.get('source_url') or '').strip() else "—")
        self._fiche_infos.setText(
            f"<table cellspacing='3'>"
            f"<tr><td>Statut</td><td><b>{_STATUTS.get(r['statut'], (r['statut'],))[0]}</b>"
            f"{' le ' + html(r['valide_le']) if r.get('valide_le') else ''}</td></tr>"
            f"<tr><td>Portée</td><td>{'groupe' if r['portee'] == 'groupe' else 'marque'} "
            f"{html(r['cible'])} · clé {'nom commercial' if r['cle'] == 'nom' else 'code usine'}"
            f" · {html(r['forme'])}</td></tr>"
            f"<tr><td>Origine</td><td>{_ORIGINES.get(r['origine'], r['origine'])}</td></tr>"
            f"<tr><td>Mesure</td><td>{r.get('couverture') or 0} couverts, "
            f"{r.get('accord') or 0} d'accord"
            f"{f' ({p * 100:.1f} %)' if p is not None else ''}"
            f"{' — D7 : pureté ≥ 98 %' if pure_d7(r) else ''}</td></tr>"
            f"<tr><td>Proposés</td><td>{en_attente}</td></tr>"
            f"<tr><td>Source</td><td>{source}</td></tr></table>")
        self._note.setPlainText(r.get('note') or '')
        self._btn_valider.setEnabled(r['statut'] != 'validee')
        self._btn_rejeter.setEnabled(r['statut'] != 'rejetee')
        self._btn_proposee.setEnabled(r['statut'] != 'proposee')
        self._btn_revue_regle.setText(f"Revoir ses propositions ({en_attente})")
        self._btn_revue_regle.setEnabled(en_attente > 0)
        self._afficher_exemples(r)

    def _afficher_exemples(self, r):
        ex = self.service.exemples(r)
        if ex.erreur:
            self._exemples.setHtml(f"<p style='color:#c0392b'>{html(ex.erreur)}</p>")
            return
        lignes = [f"<p>{ex.couverture} couverts, {ex.couverture - ex.accord} en désaccord.</p>"]
        if ex.masquees:
            lignes.append(
                f"<p style='color:#b06a00'>{html(', '.join(ex.masquees))} : "
                f"{'a sa' if len(ex.masquees) == 1 else 'ont leur'} propre règle sur ce motif, "
                f"la règle de groupe ne {'la' if len(ex.masquees) == 1 else 'les'} vise pas.</p>")

        def _table(titre, couleur, elements):
            if not elements:
                return
            lignes.append(f"<p style='color:{couleur}'><b>{titre}</b></p><table cellspacing='2'>")
            for _id, marque, ref, com, type_app, libelle in elements:
                reference = " - ".join(x for x in (ref, com) if x)
                lignes.append(f"<tr><td>{html(marque)}</td><td>{html(reference)}</td>"
                              f"<td><b>{html(type_app) or '(vide)'}</b></td>"
                              f"<td style='color:#6c757d'>{html(libelle[:40])}</td></tr>")
            lignes.append("</table>")

        _table(f"Désaccords ({ex.couverture - ex.accord})", '#c0392b', ex.desaccords)
        _table(f"D'accord ({ex.accord})", '#198754', ex.accords)
        self._exemples.setHtml("".join(lignes))

    def _revoir_regle_courante(self):
        if self._regle_courante:
            self._ouvrir_revue(self._regle_courante['id'])

    def enregistrer_note(self):
        r = self._regle_courante
        if r and self.service.enregistrer_note(r['id'], self._note.toPlainText(),
                                               zone_grise=zone_grise_de(r)):
            self.recharger()

    # ── Statut ───────────────────────────────────────────────────────────────
    def changer_statut(self, statut):
        regles = [r for r in self.regles_selectionnees() if r['statut'] != statut]
        if not regles:
            return
        if len(regles) == 1:
            self._ecrire_statut(regles, statut)
            return
        couverture = sum(r.get('couverture') or 0 for r in regles)
        n_desaccords = sum(desaccords(r) for r in regles)
        zones = sum(1 for r in regles if zone_grise_de(r))
        libelle = {'validee': "Valider", 'rejetee': "Rejeter", 'proposee': "Remettre en proposée"}[statut]
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle(f"{libelle} {len(regles)} règles")
        boite.setTextFormat(Qt.RichText)
        boite.setText(f"<b>{libelle} {pluralize(len(regles), 'règle')} ?</b>")
        details = [f"{couverture} appareils couverts, dont {n_desaccords} en désaccord"
                   + (" : ils deviendront des types proposés, à revoir." if statut == 'validee'
                      else ".")]
        if zones:
            details.append(f"<span style='color:#b06a00'>{zones} trouvée"
                           f"{'s' if zones > 1 else ''} sous une zone grise.</span>")
        boite.setInformativeText("<br>".join(details))
        boite.addButton("Annuler", QMessageBox.RejectRole)
        ok = boite.addButton(libelle, QMessageBox.AcceptRole)
        ok.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        boite.setDefaultButton(ok)
        boite.buttonClicked.connect(lambda b: self._ecrire_statut(regles, statut) if b is ok else None)
        boite.setWindowModality(Qt.WindowModal)
        self._confirmation = boite
        boite.show()

    def _ecrire_statut(self, regles, statut):
        changees = sum(1 for r in regles if self.service.changer_statut(r['id'], statut))
        self.recharger()
        if changees:
            self.recalculer_propositions()

    # ── Calculs en arrière-plan ──────────────────────────────────────────────
    def calcul_en_cours(self) -> bool:
        return self._calcul is not None

    def recalculer_propositions(self):
        if self._calcul is not None:
            # Un calcul tourne : on recalculera à sa fin (le statut a pu changer)
            self._recalcul_demande = True
            return
        self._lancer(MODE_PROPOSER, "Recalcul des propositions…")

    def chercher_nouvelles_regles(self):
        if self._calcul is None:
            self._lancer(MODE_DECOUVRIR, "Recherche de nouvelles règles…")

    def _lancer(self, mode, message):
        self._etat_calcul.setText(message)
        self._btn_decouvrir.setEnabled(False)
        self._btn_recalculer.setEnabled(False)
        calcul = CalculNomenclature(self.db_manager, mode,
                                    types_autorises=self.service.types_autorises,
                                    configuration=self.service._configuration, parent=self)
        calcul.termine.connect(lambda bilan, erreur, m=mode: self._fin_calcul(m, bilan, erreur))
        self._calcul = calcul
        calcul.start()

    def _fin_calcul(self, mode, bilan, erreur):
        calcul, self._calcul = self._calcul, None
        if calcul is not None:
            calcul.wait()
            calcul.deleteLater()
        self._btn_decouvrir.setEnabled(True)
        self._btn_recalculer.setEnabled(True)
        if erreur or bilan is None:
            app_logger.error(f"Règles de nomenclature : calcul « {mode} » échoué : {erreur}")
            self._etat_calcul.setText(f"Échec du calcul : {erreur}")
            return
        if mode == MODE_PROPOSER:
            ok = self.service.ecrire_propositions(bilan)
            # Recalcul qui suit une découverte : son message reste en tête
            avant, self._message_decouverte = self._message_decouverte, ''
            self._etat_calcul.setText((f"{avant} · " if avant else "") + (
                f"{pluralize(len(bilan.propositions), 'type proposé', 'types proposés')}"
                f"{', ' + pluralize(len(bilan.conflits), 'conflit') if bilan.conflits else ''}"
                if ok else "Propositions non enregistrées (voir le journal)"))
            self._on_propositions_changees()
        else:
            ajoutees = self.service.enregistrer_decouvertes(bilan)
            zones = sum(1 for c in bilan.nouvelles if c.zone_grise)
            self._message_decouverte = (
                f"{pluralize(ajoutees, 'nouvelle règle proposée', 'nouvelles règles proposées')}"
                + (f", dont {zones} sous une zone grise" if zones else ""))
            self._etat_calcul.setText(self._message_decouverte)
            if ajoutees:
                # Des milliers de règles : on montre d'abord celles qui changeraient
                # des appareils (choix du lot 4)
                self._f_statut.setCurrentIndex(self._f_statut.findData('proposee'))
                self._f_changeraient.setChecked(True)
                # Mesures de la découverte ≠ mesures du moteur : une règle de groupe
                # doublée par une règle de marque ne vise plus cette marque (§ 6.2).
                # Le recalcul les remet d'accord.
                self._recalcul_demande = True
        self.recharger()
        if self._recalcul_demande:
            self._recalcul_demande = False
            self.recalculer_propositions()

    # ── Acceptations ─────────────────────────────────────────────────────────
    def _maj_bouton_annuler(self):
        item = self._lots.currentItem()
        lot = item.data(Qt.UserRole) if item else None
        self._btn_annuler_lot.setEnabled(bool(lot) and not lot.get('annule_le'))

    def annuler_lot_courant(self):
        item = self._lots.currentItem()
        lot = item.data(Qt.UserRole) if item else None
        if not lot or lot.get('annule_le'):
            return
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle("Annuler une acceptation")
        boite.setText(f"Remettre le type d'avant sur les {pluralize(lot['nb'], 'appareil')} "
                      f"de « {lot['libelle']} » ?")
        boite.setInformativeText("Les appareils modifiés depuis sont laissés tels quels. "
                                 "Les propositions seront recalculées.")
        boite.addButton("Non", QMessageBox.RejectRole)
        oui = boite.addButton("Annuler l'acceptation", QMessageBox.AcceptRole)
        oui.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        boite.buttonClicked.connect(lambda b: self._annuler_lot(lot) if b is oui else None)
        boite.setWindowModality(Qt.WindowModal)
        self._confirmation = boite
        boite.show()

    def _annuler_lot(self, lot):
        bilan = self.revue.annuler_lot(lot)
        self._etat_calcul.setText(
            f"Acceptation annulée : {pluralize(len(bilan.a_corriger), 'appareil')} remis, "
            f"{len(bilan.ignorees)} laissé{'s' if len(bilan.ignorees) > 1 else ''} tel"
            f"{'s' if len(bilan.ignorees) > 1 else ''} quel{'s' if len(bilan.ignorees) > 1 else ''}")
        self._on_propositions_changees()
        self.recharger()
        self.recalculer_propositions()
