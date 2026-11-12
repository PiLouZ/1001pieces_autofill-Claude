"""
Fenêtre « Reprise des fiches du site » : import en masse par lots
(CDC docs/cdc_import_fiches_site.md, § 7.2 à 7.4, étape 4)

- Exports : les deux CSV PrestaShop (produits avec description ;
  compatibilités). Un export différent de celui de la reprise en cours est
  signalé : « Repartir de zéro » ou « Continuer ».
- État : dernier id_produit traité, date de l'export, lots enregistrés, fiches
  mises de côté. On peut fermer à tout moment et reprendre au lot suivant.
- Lot : « Analyser le lot suivant » (thread, progression, annulation), puis
  * Résumé : une ligne par catégorie (fiches, éléments), validée en bloc,
    laissée de côté ou en attente pour tout le lot ;
  * Doutes regroupés : un choix par groupe (ex. réf. internes « ES… ») ;
  * Fiches : état de chaque fiche ; double-clic = aperçu complet de la fiche
    (FicheSiteDialog), dont les décisions l'emportent sur celles du lot ;
  * Détail : table virtuelle de tous les éléments du lot, filtrable par
    nature (appareil, remplacement, équivalence), catégorie, niveau, lien,
    provenance et texte.
- « Enregistrer le lot » (thread) n'est actif que lorsque rien n'est en attente
  ni à compléter ; « Laisser de côté les lignes à compléter » débloque en un clic.

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import copy
import threading
from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import (
    QAbstractTableModel, QModelIndex, QSettings, QSortFilterProxyModel, Qt, QThread, pyqtSignal,
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QProgressBar, QPushButton, QSpinBox, QTableView, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.reprise_site_service import (
    EXPORT_DIFFERENT, EXPORT_IDENTIQUE, RepriseSiteService,
)
from src.utils.boites import choisir_fichier_a_ouvrir
from src.utils.rapprochement_fiche import LIENS, NIVEAUX
from src.utils.rapprochement_fiche.decisions import (
    ATTENTE, CATEGORIES_RESUME, DE_COTE, VALIDEE, categorie_appareil, categorie_equivalence,
    categorie_remplacement,
)
from src.utils.reprise_site import CATEGORIES_LOT, PROFILS_AMBIGUS
from .style_manager import StyleManager

_ETATS = [(ATTENTE, "En attente"), (VALIDEE, "Validée en bloc"), (DE_COTE, "Laissée de côté")]
_PROVENANCES = {'description': "description", 'table': "table du site", 'les_deux': "les deux"}
_NATURES = {'appareil': "Appareil", 'remplacement': "Remplacement", 'equivalence': "Équivalence"}
_LIBELLES_CHOIX = {'enregistrer': "enregistrer le produit", 'ignorer': "ne pas enregistrer le produit",
                   'prendre': "prendre la fiche", 'garder': "garder l'existant",
                   'site': "prendre l'EAN du site", 'outil': "garder l'EAN de l'outil",
                   'etiquette': "étiquette ci-contre", 'ecarter': "écarter les références"}
_DOSSIER_DEFAUT = Path(__file__).resolve().parents[2] / 'data' / 'reprise_site'
_CLE_PRODUITS = 'reprise_site/export_produits'
_CLE_COMPAT = 'reprise_site/export_compatibilites'
_CLE_TAILLE = 'reprise_site/taille_lot'


# =============================================================================
# Tâche de fond
# =============================================================================

class _Tache(QThread):
    """Exécute `fonction(progression, annule)` hors du thread principal."""
    progression = pyqtSignal(int, int, str)
    termine = pyqtSignal(object, str)       # résultat, erreur

    def __init__(self, fonction: Callable, parent=None):
        super().__init__(parent)
        self.fonction = fonction
        self.arret = threading.Event()

    def run(self):
        try:
            resultat = self.fonction(lambda i, n, t: self.progression.emit(i, n, t),
                                     self.arret.is_set)
            self.termine.emit(resultat, '')
        except Exception as e:
            app_logger.error(f"[Reprise site] tâche interrompue : {type(e).__name__} : {e}")
            self.termine.emit(None, f"{type(e).__name__} : {e}")


# =============================================================================
# Modèles virtuels
# =============================================================================

_COLONNES_DETAIL = ("Produit", "Pièce", "Nature", "Catégorie", "Niveau / statut", "Lien",
                    "Marque", "Réf.", "Nom / origine", "Type", "Provenance", "Raison")


class ModeleDetailLot(QAbstractTableModel):
    """Tous les éléments du lot (appareils, remplacements, équivalences), calculés
    à la demande : rien n'est copié ligne par ligne (≈ 165 000 lignes par lot)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lot = None
        self.lignes: List[tuple] = []        # (index de fiche, nature, index ou objet)

    def charger(self, lot):
        self.beginResetModel()
        self.lot, self.lignes = lot, []
        if lot is not None:
            for i, f in enumerate(lot.fiches):
                r = f.rapprochement
                if r is None:
                    continue
                self.lignes.extend((i, 'appareil', k) for k in range(len(r.appareils)))
                self.lignes.extend((i, 'remplacement', rp) for rp in r.remplacements)
                self.lignes.extend((i, 'equivalence', e) for e in r.equivalences)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.lignes)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLONNES_DETAIL)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLONNES_DETAIL[section]
        return None

    def cles(self, ligne: int):
        """(nature, catégorie, niveau, lien, provenance) d'une ligne, pour le filtre."""
        i, nature, x = self.lignes[ligne]
        if nature == 'appareil':
            a = self.lot.fiches[i].rapprochement.appareils[x]
            return nature, categorie_appareil(a), a.niveau, a.lien, a.provenance
        if nature == 'remplacement':
            return nature, categorie_remplacement(x), x.statut, '', ''
        return nature, categorie_equivalence(x), x.statut, '', ''

    def texte(self, ligne: int) -> tuple:
        i, nature, x = self.lignes[ligne]
        f = self.lot.fiches[i]
        if nature == 'appareil':
            a = f.rapprochement.appareils[x]
            return (f.id_produit, f.ref_piece, "appareil",
                    CATEGORIES_RESUME[categorie_appareil(a)].split(' (')[0], a.niveau,
                    a.lien or "à décider", a.marque or a.marque_fiche or "?", a.ref_modele, a.nom,
                    a.type or "—", _PROVENANCES.get(a.provenance, a.provenance), a.raison)
        if nature == 'remplacement':
            return (f.id_produit, f.ref_piece, "remplacement",
                    CATEGORIES_RESUME[categorie_remplacement(x)].split(' (')[0], x.statut, '', '',
                    f"{x.ancienne} → {x.nouvelle}", x.successeur_actuel or '', '', '', x.raison)
        return (f.id_produit, f.ref_piece, "équivalence",
                CATEGORIES_RESUME[categorie_equivalence(x)].split(' (')[0], x.statut, '', '',
                f"≡ {x.reference}", x.origine or '', '', '', x.raison)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return self.texte(index.row())[index.column()]
        if role == Qt.ToolTipRole and index.column() == 4:
            return NIVEAUX.get(self.texte(index.row())[4], '')
        if role == Qt.ToolTipRole and index.column() == 5:
            return LIENS.get(self.cles(index.row())[3], '')
        return None


class FiltreDetailLot(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.valeurs = ['', '', '', '', '']     # nature, catégorie, niveau, lien, provenance
        self.texte = ''

    def filterAcceptsRow(self, ligne, parent):
        m = self.sourceModel()
        cles = m.cles(ligne)
        for attendu, valeur in zip(self.valeurs, cles):
            if attendu and attendu != valeur:
                return False
        if self.texte:
            return self.texte in ' '.join(str(v) for v in m.texte(ligne)).lower()
        return True


_COLONNES_FICHES = ("Produit", "Pièce", "Nom", "Lignes desc.", "Lignes table", "État", "Détail")


class ModeleFichesLot(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lot = None
        self.plan = None
        self._plans = {}

    def charger(self, lot, plan):
        self.beginResetModel()
        self.lot, self.plan = lot, plan
        self._plans = dict(plan.plans) if plan is not None else {}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.lot is None else len(self.lot.fiches)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLONNES_FICHES)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLONNES_FICHES[section]
        return None

    def etat(self, i: int):
        f = self.lot.fiches[i]
        if f.erreur:
            return "erreur", f.erreur
        if self.plan is not None and i in self.plan.de_cote:
            return "de côté", f.raison_de_cote or "profil ambigu laissé de côté"
        plan = self._plans.get(i)
        if plan is not None and plan.a_completer:
            return "à compléter", f"{len(plan.a_completer)} ligne(s) : {plan.a_completer[0]}"
        if plan is not None and plan.en_attente:
            return "en attente", ", ".join(c.split(' (')[0] for c in plan.en_attente)
        suffixe = " (décidée dans l'aperçu)" if f.personnalisee else ''
        return "prête" + suffixe, ''

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.lot is None:
            return None
        f = self.lot.fiches[index.row()]
        if role == Qt.DisplayRole:
            etat, detail = self.etat(index.row())
            return (f.id_produit, f.ref_piece or '?', f.nom, f.lignes_description, f.lignes_table,
                    etat, detail)[index.column()]
        return None


# =============================================================================
# Fenêtre
# =============================================================================

class RepriseSiteDialog(QDialog):
    """Import en masse des fiches du site, lot par lot."""

    def __init__(self, db_manager, main_window=None, service: Optional[RepriseSiteService] = None,
                 on_lot_enregistre: Optional[Callable] = None):
        super().__init__(main_window)
        self.setWindowTitle("Reprise des fiches du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1240, 860)
        self.db = db_manager
        self.main_window = main_window
        self.on_lot_enregistre = on_lot_enregistre
        self.service = service or RepriseSiteService(db_manager, main_window)
        self.lot = None
        self.plan = None
        self._tache: Optional[_Tache] = None
        self._signature = None
        self._types: List[str] = []
        self._fiche_ouverte = None
        self._construire()
        self._charger_chemins()
        self._rafraichir_etat()

    # =========================================================================
    # Construction
    # =========================================================================
    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)

        titre = QLabel("Exports du site (CSV PrestaShop, triés par id_produit)")
        titre.setStyleSheet(StyleManager.TITRE_SECTION)
        racine.addWidget(titre)
        self.champ_produits = self._ligne_fichier(racine, "Produits :",
                                                  "Export des produits")
        self.champ_compat = self._ligne_fichier(racine, "Compatibilités :",
                                                "Export des compatibilités")
        choisir = QHBoxLayout()
        self.bouton_export = QPushButton(qta.icon('fa5s.file-import', color='#555555'),
                                         "Utiliser ces exports")
        self.bouton_export.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_export.clicked.connect(self._examiner_export)
        self.bouton_zero = QPushButton(qta.icon('fa5s.redo', color='#555555'), "Repartir de zéro")
        self.bouton_zero.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_zero.clicked.connect(lambda: self._adopter(True))
        self.bouton_continuer = QPushButton(qta.icon('fa5s.forward', color='#555555'),
                                            "Continuer la reprise")
        self.bouton_continuer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_continuer.clicked.connect(lambda: self._adopter(False))
        for b in (self.bouton_zero, self.bouton_continuer):
            b.setVisible(False)
        choisir.addWidget(self.bouton_export)
        choisir.addWidget(self.bouton_zero)
        choisir.addWidget(self.bouton_continuer)
        choisir.addStretch(1)
        racine.addLayout(choisir)

        self.carte = QLabel("")
        self.carte.setWordWrap(True)
        self.carte.setTextFormat(Qt.RichText)
        self.carte.setStyleSheet(StyleManager.CARTE_GRIS_CLAIR + " padding: 8px;")
        racine.addWidget(self.carte)

        lot = QHBoxLayout()
        lot.addWidget(QLabel("Produits par lot :"))
        self.taille = QSpinBox()
        self.taille.setRange(1, 2000)
        self.taille.setValue(int(QSettings().value(_CLE_TAILLE, 100) or 100))
        lot.addWidget(self.taille)
        self.bouton_analyser = QPushButton(qta.icon('fa5s.search', color='white'),
                                           "Analyser le lot suivant")
        self.bouton_analyser.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_analyser.clicked.connect(self._analyser_lot)
        self.bouton_de_cote = QPushButton(qta.icon('fa5s.inbox', color='#555555'),
                                          "Reprendre les fiches de côté")
        self.bouton_de_cote.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_de_cote.clicked.connect(self._analyser_de_cote)
        self.bouton_annuler = QPushButton(qta.icon('fa5s.stop', color='#555555'), "Annuler")
        self.bouton_annuler.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_annuler.clicked.connect(self._annuler)
        self.bouton_annuler.setEnabled(False)
        self.progression = QProgressBar()
        self.progression.setStyleSheet(StyleManager.BARRE_PROGRESSION_DISCRETE)
        self.progression.setTextVisible(False)
        self.progression.setFixedHeight(8)
        self.texte_progression = QLabel("")
        self.texte_progression.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        for w in (self.bouton_analyser, self.bouton_de_cote, self.bouton_annuler):
            lot.addWidget(w)
        lot.addWidget(self.progression, 1)
        racine.addLayout(lot)
        racine.addWidget(self.texte_progression)

        self.onglets = QTabWidget()
        self.onglets.addTab(self._construire_resume(), "Résumé du lot")
        self.onglets.addTab(self._construire_groupes(), "Doutes regroupés")
        self.onglets.addTab(self._construire_fiches(), "Fiches")
        self.onglets.addTab(self._construire_detail(), "Détail")
        racine.addWidget(self.onglets, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_lignes = QPushButton("Laisser de côté les lignes à compléter")
        self.bouton_lignes.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_lignes.clicked.connect(self._lignes_de_cote)
        self.bouton_enregistrer = QPushButton(qta.icon('fa5s.save', color='white'), "Enregistrer le lot")
        self.bouton_enregistrer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_enregistrer.clicked.connect(self._enregistrer)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        pied.addWidget(self.bouton_lignes)
        pied.addWidget(self.bouton_enregistrer)
        pied.addWidget(fermer)
        racine.addLayout(pied)
        self._activer()

    def _ligne_fichier(self, racine, libelle: str, titre: str) -> QLineEdit:
        ligne = QHBoxLayout()
        etiquette = QLabel(libelle)
        etiquette.setFixedWidth(130)
        champ = QLineEdit()
        parcourir = QPushButton(qta.icon('fa5s.folder-open', color='#555555'), "Parcourir…")
        parcourir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        parcourir.clicked.connect(lambda: self._parcourir(champ, titre))
        ligne.addWidget(etiquette)
        ligne.addWidget(champ, 1)
        ligne.addWidget(parcourir)
        racine.addLayout(ligne)
        return champ

    def _construire_resume(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        entete = QHBoxLayout()
        self.titre_lot = QLabel("Aucun lot analysé")
        self.titre_lot.setStyleSheet(StyleManager.TITRE_SECTION)
        tout = QPushButton(qta.icon('fa5s.check-double', color='#555555'), "Tout valider")
        tout.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        tout.clicked.connect(self._tout_valider)
        entete.addWidget(self.titre_lot)
        entete.addStretch(1)
        entete.addWidget(tout)
        disposition.addLayout(entete)
        self.resume = QTreeWidget()
        self.resume.setHeaderLabels(["Catégorie", "Fiches", "Éléments", "Décision", "Type commun"])
        self.resume.setRootIsDecorated(False)
        self.resume.setUniformRowHeights(True)
        self.resume.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.resume.itemDoubleClicked.connect(self._filtrer_sur_categorie)
        disposition.addWidget(self.resume, 1)
        self.mesures = QLabel("")
        self.mesures.setWordWrap(True)
        self.mesures.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        disposition.addWidget(self.mesures)
        return boite

    def _construire_groupes(self) -> QWidget:
        self.groupes = QTreeWidget()
        self.groupes.setHeaderLabels(["Doute", "Forme", "Fiches", "Exemples", "Décision", ""])
        self.groupes.setRootIsDecorated(False)
        self.groupes.header().setSectionResizeMode(3, QHeaderView.Stretch)
        return self.groupes

    def _construire_fiches(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        self.modele_fiches = ModeleFichesLot(self)
        self.table_fiches = QTableView()
        self.table_fiches.setModel(self.modele_fiches)
        self.table_fiches.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_fiches.verticalHeader().setVisible(False)
        self.table_fiches.verticalHeader().setDefaultSectionSize(22)
        self.table_fiches.horizontalHeader().setStretchLastSection(True)
        self.table_fiches.setAlternatingRowColors(True)
        self.table_fiches.doubleClicked.connect(lambda idx: self._ouvrir_fiche(idx.row()))
        disposition.addWidget(self.table_fiches, 1)
        actions = QHBoxLayout()
        ouvrir = QPushButton(qta.icon('fa5s.search-plus', color='#555555'), "Aperçu de la fiche…")
        ouvrir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        ouvrir.clicked.connect(lambda: self._ouvrir_fiche(self._fiche_selectionnee()))
        de_cote = QPushButton("Mettre la fiche de côté")
        de_cote.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        de_cote.clicked.connect(self._fiche_de_cote)
        reprendre = QPushButton("Reprendre la fiche")
        reprendre.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        reprendre.clicked.connect(self._fiche_reprise)
        for b in (ouvrir, de_cote, reprendre):
            actions.addWidget(b)
        actions.addStretch(1)
        disposition.addLayout(actions)
        return boite

    def _construire_detail(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        filtres = QHBoxLayout()
        self.filtres = []
        for tous, valeurs in (
                ("Toutes natures", _NATURES),
                ("Toutes catégories", CATEGORIES_RESUME),
                ("Tous niveaux / statuts", {k: k for k in NIVEAUX}),
                ("Tous les liens", LIENS),
                ("Toutes provenances", _PROVENANCES)):
            combo = QComboBox()
            combo.addItem(tous, '')
            for cle, libelle in valeurs.items():
                combo.addItem(libelle, cle)
            combo.currentIndexChanged.connect(self._filtrer)
            filtres.addWidget(combo)
            self.filtres.append(combo)
        self.filtre_texte = QLineEdit()
        self.filtre_texte.setPlaceholderText("Filtrer (produit, pièce, marque, réf.)")
        self.filtre_texte.textChanged.connect(self._filtrer)
        filtres.addWidget(self.filtre_texte, 1)
        disposition.addLayout(filtres)
        self.modele_detail = ModeleDetailLot(self)
        self.filtre_detail = FiltreDetailLot(self)
        self.filtre_detail.setSourceModel(self.modele_detail)
        self.table_detail = QTableView()
        self.table_detail.setModel(self.filtre_detail)
        self.table_detail.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_detail.verticalHeader().setVisible(False)
        self.table_detail.verticalHeader().setDefaultSectionSize(22)
        self.table_detail.horizontalHeader().setStretchLastSection(True)
        self.table_detail.setAlternatingRowColors(True)
        self.table_detail.doubleClicked.connect(self._ouvrir_depuis_detail)
        disposition.addWidget(self.table_detail, 1)
        self.compte_detail = QLabel("")
        self.compte_detail.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        disposition.addWidget(self.compte_detail)
        return boite

    # =========================================================================
    # Exports et état
    # =========================================================================
    def _charger_chemins(self):
        reglages = QSettings()
        etat = self.service.etat() or {}
        for champ, cle, colonne, nom in (
                (self.champ_produits, _CLE_PRODUITS, 'chemin_produits', 'produits.csv'),
                (self.champ_compat, _CLE_COMPAT, 'chemin_compatibilites', 'compatibilites.csv')):
            chemin = etat.get(colonne) or reglages.value(cle, '') or ''
            if not chemin and (_DOSSIER_DEFAUT / nom).exists():
                chemin = str(_DOSSIER_DEFAUT / nom)
            champ.setText(chemin)

    def _parcourir(self, champ: QLineEdit, titre: str):
        dossier = str(Path(champ.text()).parent) if champ.text() else str(_DOSSIER_DEFAUT)
        choisir_fichier_a_ouvrir(self, titre, dossier, "Fichiers CSV (*.csv);;Tous les fichiers (*)",
                                 lambda chemin: champ.setText(chemin))

    def _examiner_export(self):
        produits = self.champ_produits.text().strip()
        compat = self.champ_compat.text().strip()
        if not produits or not Path(produits).exists():
            self._message("Choisissez l'export des produits.", erreur=True)
            return
        if compat and not Path(compat).exists():
            self._message("L'export des compatibilités est introuvable.", erreur=True)
            return
        signature, statut = self.service.examiner_export(produits, compat)
        reglages = QSettings()
        reglages.setValue(_CLE_PRODUITS, produits)
        reglages.setValue(_CLE_COMPAT, compat)
        self._signature = signature
        if statut == EXPORT_DIFFERENT and self.service.dernier_id():
            for b in (self.bouton_zero, self.bouton_continuer):
                b.setVisible(True)
            self._message(f"Cet export (du {signature.date_export.replace('T', ' ')}) n'est pas celui "
                          f"de la reprise en cours : repartir de zéro, ou continuer après le produit "
                          f"{self.service.dernier_id()} ?", avertissement=True)
            return
        self._adopter(statut != EXPORT_IDENTIQUE and not self.service.dernier_id())

    def _adopter(self, repartir_de_zero: bool):
        if self._signature is None:
            return
        self.service.adopter_export(self._signature, repartir_de_zero)
        for b in (self.bouton_zero, self.bouton_continuer):
            b.setVisible(False)
        self._effacer_lot()
        self._message("Export prêt : analysez le lot suivant.")
        self._rafraichir_etat()

    def _rafraichir_etat(self):
        etat = self.service.etat()
        lots = self.db.lots_reprise_site(limite=1000)
        de_cote = self.db.fiches_de_cote_reprise_site()
        if not etat:
            texte = "Aucune reprise commencée : choisissez les deux exports."
        else:
            texte = (f"<b>Dernier produit traité : {etat['dernier_id'] or '—'}</b> · export du "
                     f"{(etat['date_export'] or '?').replace('T', ' ')} · {len(lots)} lot(s) "
                     f"enregistré(s) · {len(de_cote)} fiche(s) de côté")
            if lots:
                d = lots[0]
                texte += (f"<br>Dernier lot : produits {d['premier_id']} à {d['dernier_id']}, "
                          f"{d['fiches']} fiche(s), analyse {d['analyse_s'] or 0:.0f} s, écriture "
                          f"{d['ecriture_s'] or 0:.0f} s, base "
                          f"{((d['taille_apres'] or 0) - (d['taille_avant'] or 0)) / 1e6:+.1f} Mo")
            if self.service.signature is None:
                texte += "<br><i>Cliquez « Utiliser ces exports » pour reprendre.</i>"
        self.carte.setText(texte)
        self.bouton_de_cote.setEnabled(bool(de_cote) and self._tache is None
                                       and self.service.signature is not None)
        self._activer()

    # =========================================================================
    # Tâches
    # =========================================================================
    def _lancer(self, fonction, fin, texte: str):
        self._tache = _Tache(fonction, self)
        self._tache.progression.connect(self._progresser)
        self._tache.termine.connect(lambda r, e: self._tache_terminee(fin, r, e))
        self.texte_progression.setText(texte)
        self.progression.setRange(0, 0)
        self._activer()
        self._tache.start()

    def _progresser(self, i: int, n: int, texte: str):
        if n:
            self.progression.setRange(0, n)
            self.progression.setValue(i)
        else:
            self.progression.setRange(0, 0)
        self.texte_progression.setText(texte)

    def _tache_terminee(self, fin, resultat, erreur: str):
        self._tache = None
        self.progression.setRange(0, 1)
        self.progression.setValue(1)
        fin(resultat, erreur)
        self._rafraichir_etat()

    def _annuler(self):
        if self._tache is not None:
            self._tache.arret.set()
            self.texte_progression.setText("Annulation demandée…")

    def _analyser_lot(self):
        if self.service.signature is None:
            self._examiner_export()
            if self.service.signature is None:
                return
        taille = self.taille.value()
        QSettings().setValue(_CLE_TAILLE, taille)
        self._effacer_lot()
        self._lancer(lambda prog, annule: self.service.analyser_lot_suivant(taille, prog, annule),
                     self._lot_analyse, "Analyse du lot…")

    def _analyser_de_cote(self):
        self._effacer_lot()
        self._lancer(lambda prog, annule: self.service.analyser_fiches_de_cote(prog, annule),
                     self._lot_analyse, "Analyse des fiches mises de côté…")

    def _lot_analyse(self, lot, erreur: str):
        if erreur:
            annule = 'AnalyseAnnulee' in erreur
            self._message("Analyse annulée." if annule else f"Analyse impossible : {erreur}",
                          erreur=not annule)
            return
        if lot is None:
            self._message("Export entièrement repris : plus aucun produit après le dernier traité.")
            return
        self.afficher_lot(lot)

    def afficher_lot(self, lot):
        """Affiche un lot analysé (aussi appelé par les tests, sans thread)."""
        self.lot = lot
        if not self._types:
            self._types = self.service.fiche_service.types_outil()
        e = lot.export
        nature = "Fiches mises de côté" if lot.fiches_de_cote else f"Produits {e.premier_id} à {e.dernier_id}"
        self.titre_lot.setText(f"{nature} — {len(lot.fiches)} fiche(s)"
                               + (f", {e.sans_contenu} sans contenu" if e.sans_contenu else '')
                               + f" · analyse {lot.duree_analyse:.1f} s")
        self.modele_detail.charger(lot)
        self._remplir_groupes()
        self._mettre_a_jour()
        for table in (self.table_detail, self.table_fiches):
            table.resizeColumnsToContents()
            for col in range(table.model().columnCount() - 1):
                table.setColumnWidth(col, min(table.columnWidth(col), 240))

    def _enregistrer(self):
        if self.lot is None or self.plan is None or not self.plan.pret or self._tache is not None:
            return
        lot, plan = self.lot, self.plan
        self._lancer(lambda prog, annule: self.service.enregistrer_lot(lot, plan, prog, annule),
                     self._lot_enregistre, "Enregistrement du lot…")

    def _lot_enregistre(self, res, erreur: str):
        if res is None:
            self._message(f"Enregistrement interrompu : {erreur}", erreur=True)
            return
        self.service.apres_lot(res)
        if res.annule or not res.ok:
            self._message(("Enregistrement annulé" if res.annule else
                           f"Enregistrement interrompu : {res.erreur}")
                          + " — la reprise n'a pas avancé ; relancez le lot : rien ne sera doublé.",
                          erreur=not res.annule, avertissement=res.annule)
            return
        self._effacer_lot()
        self._message(f"Lot n° {res.numero} enregistré : {res.resume()}.")
        if self.on_lot_enregistre is not None:
            self.on_lot_enregistre(res)

    # =========================================================================
    # Résumé, groupes, fiches
    # =========================================================================
    def _remplir_resume(self):
        self.resume.clear()
        if self.lot is None:
            return
        for ligne in self.lot.resume():
            item = QTreeWidgetItem([ligne.libelle, _nombre(ligne.fiches), _nombre(ligne.elements), '', ''])
            for col in (1, 2):
                item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            item.setData(0, Qt.UserRole, ligne.cle)
            self.resume.addTopLevelItem(item)
            combo = QComboBox()
            for etat, libelle in _ETATS:
                combo.addItem(libelle, etat)
            combo.setCurrentIndex([e for e, _ in _ETATS].index(self.lot.etat(ligne.cle)))
            combo.currentIndexChanged.connect(
                lambda _, c=ligne.cle, w=combo: self._changer_etat(c, w.currentData()))
            self.resume.setItemWidget(item, 3, combo)
            if ligne.cle in ('absents', 'types_manquants'):
                types = QComboBox()
                types.setEditable(True)
                types.addItem('')
                types.addItems(self._types)
                types.setCurrentText(self.lot.type_par_categorie.get(ligne.cle, ''))
                types.currentTextChanged.connect(lambda t, c=ligne.cle: self._type_commun(c, t))
                self.resume.setItemWidget(item, 4, types)
        for col in (1, 2):
            self.resume.resizeColumnToContents(col)
        self.resume.setColumnWidth(3, 170)

    def _remplir_groupes(self):
        self.groupes.clear()
        if self.lot is None:
            return
        for g in self.lot.groupes_doutes():
            item = QTreeWidgetItem([g.libelle, g.forme or '—', str(g.fiches),
                                    ' · '.join(g.exemples), '', ''])
            self.groupes.addTopLevelItem(item)
            combo = QComboBox()
            combo.addItem("Proposition", '')
            combo.setToolTip("Proposition : appliquée quand la catégorie « Conflits et doutes "
                             "sur la pièce » est validée en bloc")
            for choix in g.choix:
                combo.addItem(_LIBELLES_CHOIX.get(choix, choix), choix)
            deja = self.lot.choix_groupes.get(g.cle, '')
            if deja:
                i = combo.findData(deja.split(':', 1)[0])
                combo.setCurrentIndex(max(0, i))
            self.groupes.setItemWidget(item, 4, combo)
            etiquette = None
            if g.genre == 'origine_inconnue':
                etiquette = QLineEdit(deja.split(':', 1)[1] if deja.startswith('etiquette:') else '')
                etiquette.setPlaceholderText("étiquette (ex. BSH)")
                self.groupes.setItemWidget(item, 5, etiquette)
                etiquette.editingFinished.connect(
                    lambda g=g, w=etiquette, c=combo: self._choix_groupe(g, 'etiquette', w.text())
                    if c.currentData() == 'etiquette' else None)
            combo.currentIndexChanged.connect(
                lambda _, g=g, c=combo, e=etiquette: self._choix_groupe(
                    g, c.currentData(), e.text() if e is not None else ''))
        for col in (0, 1, 2):
            self.groupes.resizeColumnToContents(col)
        self.groupes.setColumnWidth(3, 320)
        self.groupes.setColumnWidth(4, 240)
        n = self.groupes.topLevelItemCount()
        self.onglets.setTabText(1, f"Doutes regroupés ({n})" if n else "Doutes regroupés")

    def _choix_groupe(self, groupe, choix: str, etiquette: str = ''):
        self.lot.choisir_groupe(groupe, choix or '', etiquette)
        self._mettre_a_jour(resume=False)

    def _changer_etat(self, categorie: str, etat: str):
        self.lot.definir_etat(categorie, etat)
        self._mettre_a_jour(resume=False)

    def _type_commun(self, categorie: str, type_: str):
        self.lot.type_par_categorie[categorie] = type_.strip()
        self._mettre_a_jour(resume=False)

    def _tout_valider(self):
        if self.lot is not None:
            self.lot.tout_valider()
            self._mettre_a_jour()

    def _lignes_de_cote(self):
        if self.lot is not None:
            n = self.lot.lignes_a_completer_de_cote()
            self._mettre_a_jour(resume=False)
            self._message(f"{n} ligne(s) à compléter laissée(s) de côté (elles reviendront à la "
                          f"relecture de leur fiche).")

    def _fiche_selectionnee(self) -> int:
        lignes = self.table_fiches.selectionModel().selectedRows() if self.lot else []
        return lignes[0].row() if lignes else -1

    def _fiche_de_cote(self):
        i = self._fiche_selectionnee()
        if i >= 0:
            self.lot.mettre_de_cote(i, "mise de côté dans le lot")
            self._mettre_a_jour(resume=False)

    def _fiche_reprise(self):
        i = self._fiche_selectionnee()
        if i >= 0:
            self.lot.reprendre(i)
            self._mettre_a_jour(resume=False)

    def _ouvrir_depuis_detail(self, index):
        source = self.filtre_detail.mapToSource(index)
        self._ouvrir_fiche(self.modele_detail.lignes[source.row()][0])

    def _ouvrir_fiche(self, i: int):
        if self.lot is None or i < 0 or self.lot.fiches[i].rapprochement is None:
            return
        from .fiche_site_dialog import FicheSiteDialog
        f = self.lot.fiches[i]
        decisions = copy.deepcopy(self.lot.decisions_effectives(i))
        dialogue = FicheSiteDialog(self.db, main_window=self, service=self.service.fiche_service,
                                   on_decide=lambda d, i=i: self._fiche_decidee(i, d))
        dialogue.setWindowTitle(f"Fiche du lot — produit {f.id_produit}")
        dialogue.afficher(f.rapprochement, decisions)
        dialogue.show()
        self._fiche_ouverte = dialogue

    def _fiche_decidee(self, i: int, decisions):
        if self.lot is not None and i < len(self.lot.fiches):
            self.lot.personnaliser(i, decisions)
            self._mettre_a_jour(resume=False)

    def _filtrer_sur_categorie(self, item, _colonne=0):
        cle = item.data(0, Qt.UserRole)
        if cle == PROFILS_AMBIGUS:
            return
        i = self.filtres[1].findData(cle)
        if i >= 0:
            self.filtres[1].setCurrentIndex(i)
            self.onglets.setCurrentIndex(3)

    def _filtrer(self, *_):
        self.filtre_detail.valeurs = [c.currentData() or '' for c in self.filtres]
        self.filtre_detail.texte = self.filtre_texte.text().strip().lower()
        self.filtre_detail.invalidateFilter()
        self.compte_detail.setText(f"{self.filtre_detail.rowCount():,} ligne(s) sur "
                                   f"{self.modele_detail.rowCount():,}".replace(',', ' '))

    # =========================================================================
    # État
    # =========================================================================
    def _effacer_lot(self):
        self.lot = self.plan = None
        self.resume.clear()
        self.groupes.clear()
        self.modele_detail.charger(None)
        self.modele_fiches.charger(None, None)
        self.titre_lot.setText("Aucun lot analysé")
        self.mesures.setText('')
        self.onglets.setTabText(1, "Doutes regroupés")
        self._activer()

    def _mettre_a_jour(self, resume: bool = True):
        if self.lot is None:
            return
        if resume:
            self._remplir_resume()
        self.plan = self.lot.planifier()
        self.modele_fiches.charger(self.lot, self.plan)
        self._filtrer()
        p = self.plan
        s = p.resume()
        if p.pret:
            self._message(f"Prêt : {s['fiches']} fiche(s) à enregistrer ({s['de_cote']} de côté), "
                          f"{s['appareils_a_creer']} appareil(s) à créer, {s['liens']} lien(s), "
                          f"{s['remplacements']} remplacement(s), {s['equivalences']} équivalence(s).")
        else:
            raisons = []
            if p.en_attente:
                raisons.append("en attente : " + ", ".join(c.split(' (')[0] for c in p.en_attente))
            if p.fiches_a_completer:
                raisons.append(f"{p.lignes_a_completer} ligne(s) à compléter dans "
                               f"{len(p.fiches_a_completer)} fiche(s)")
            self._message("Avant d'enregistrer — " + " ; ".join(raisons), avertissement=True)
        from src.utils.reprise_site import mesures_lot
        m = mesures_lot(self.lot)
        self.mesures.setText(
            f"{m['lignes']:,} ligne(s) d'appareils · {m['part_deja_en_base']:.0%} déjà en base "
            f"(liées ou couvertes) · {m['fiches_sans_doute']} fiche(s) sans aucun doute"
            .replace(',', ' '))
        self._activer()

    def _activer(self):
        occupe = self._tache is not None
        self.bouton_analyser.setEnabled(not occupe)
        self.bouton_export.setEnabled(not occupe)
        self.bouton_annuler.setEnabled(occupe)
        self.bouton_lignes.setEnabled(not occupe and self.plan is not None
                                      and bool(self.plan.fiches_a_completer))
        self.bouton_enregistrer.setEnabled(not occupe and self.plan is not None and self.plan.pret)

    def _message(self, texte: str, erreur: bool = False, avertissement: bool = False):
        self.etat.setText(texte)
        self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE if erreur else
                                StyleManager.TEXTE_AVERTISSEMENT if avertissement else
                                StyleManager.TEXTE_SECONDAIRE)

    def closeEvent(self, event):
        t = self._tache
        if t is not None:
            # Tâche en cours : arrêt demandé, le thread survit à la fenêtre jusqu'à sa fin
            # (l'écriture s'arrête entre deux fiches ; l'état n'avance pas).
            t.arret.set()
            t.termine.disconnect()
            t.setParent(None)
            service = self.service
            # Lot déjà en partie écrit : caches et sauvegarde quand même
            t.termine.connect(lambda r, _e: service.apres_lot(r)
                              if hasattr(r, 'fiches_ecrites') else None)
            _EN_COURS.add(t)
            t.finished.connect(lambda: (_EN_COURS.discard(t), service.fermer()))
        else:
            self.service.fermer()
        super().closeEvent(event)


_EN_COURS = set()


def _nombre(n: int) -> str:
    return f"{n:,}".replace(',', '\u202f')
