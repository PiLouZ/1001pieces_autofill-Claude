"""
Fenêtre « Importer les fiches du site » : import en masse par lots
(CDC docs/cdc_import_fiches_site.md, § 7.2 à 7.4, § 10.4 à 10.8)

- Exports : les deux CSV PrestaShop (produits avec description ;
  compatibilités). Un export différent de celui de la reprise en cours est
  signalé : « Repartir de zéro » ou « Continuer ».
- Avancement : dernier produit importé, lots enregistrés, fiches à revoir. On
  peut fermer à tout moment et reprendre au lot suivant.
- Lot : « Lire le lot suivant » (thread, progression, « Arrêter »), puis :
  * À décider : ce que l'outil fera sans vous (récapitulatif), les règles à
    poser une fois (mémorisées), les questions du lot ; chaque question a sa
    réponse proposée et ses exemples (src/ui/questions_reprise.py) ;
  * Fiches du lot : ce qu'il reste pour chaque fiche ; « Ouvrir la fiche… »
    = aperçu complet, dont les choix ligne par ligne l'emportent ;
  * Toutes les lignes : table virtuelle filtrable (genre, question, ce que
    l'outil a trouvé, compatibilité, provenance, texte).
- « Accepter les propositions… » montre d'abord ce qu'il va faire ; il ne
  répond jamais à une question sans proposition.
- « Enregistrer le lot » (thread) n'est actif que lorsque toutes les questions
  ont une réponse. Les appareils sans réponse possible (à choisir parmi
  plusieurs, illisibles) ne sont pas écrits : leurs fiches passent dans
  « Fiches à revoir ».

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import copy
import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from PyQt5.QtCore import (
    QAbstractTableModel, QModelIndex, QSettings, QSortFilterProxyModel, Qt, QThread, pyqtSignal,
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QSpinBox, QTableView, QTabWidget, QVBoxLayout, QWidget,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.reprise_site_service import (
    EXPORT_DIFFERENT, EXPORT_IDENTIQUE, RepriseSiteService,
)
from src.utils.boites import choisir_fichier_a_ouvrir, demander_oui_non
from src.utils.rapprochement_fiche import STATUTS_EQUIVALENCE, STATUTS_REMPLACEMENT
from src.utils.reprise_site.questions import A_REVOIR, ILLISIBLE
from .questions_reprise import (
    LIENS_METIER, NIVEAUX_METIER, PROVENANCES_METIER, PanneauQuestions, libelle_reponse, nombre,
)
from .style_manager import StyleManager

_GENRES = {'appareil': "Appareil", 'remplacement': "Ancienne référence", 'equivalence': "Équivalente"}
_DOSSIER_DEFAUT = Path(__file__).resolve().parents[2] / 'data' / 'reprise_site'
_CLE_PRODUITS = 'reprise_site/export_produits'
_CLE_COMPAT = 'reprise_site/export_compatibilites'
_CLE_TAILLE = 'reprise_site/taille_lot'
_SANS_QUESTION = {A_REVOIR: "à revoir : appareil à choisir", ILLISIBLE: "illisible : non créé"}


def _reglages() -> QSettings:
    """Réglages de la fenêtre, avec ceux de l'application (pas le domaine par défaut
    de Qt, partagé avec tout programme lancé par le même Python, tests compris)."""
    fichier = os.environ.get('AUTOFILL_REGLAGES_INI')    # tests : fichier à part
    if fichier:
        return QSettings(fichier, QSettings.IniFormat)
    return QSettings("1001pieces", "autofill")


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

_COLONNES_DETAIL = ("N°", "Pièce", "Genre", "Ce que l'outil a trouvé", "Compatibilité", "Marque",
                    "Référence", "Nom commercial", "Type", "Cité dans", "Question", "Pourquoi")


class ModeleDetailLot(QAbstractTableModel):
    """Tous les éléments du lot (appareils, anciennes références, équivalentes),
    calculés à la demande : rien n'est copié ligne par ligne (≈ 165 000 lignes)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lot = None
        self.lignes: List[tuple] = []        # (index de fiche, genre, index ou objet)

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
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole and section == 0:
            return "Numéro du produit sur 1001pieces.com"
        return None

    def question(self, ligne: int) -> str:
        """Clé de la question d'une ligne d'appareil ('' = aucune)."""
        i, genre, x = self.lignes[ligne]
        q = getattr(self.lot, 'questionnaire', None)
        if q is None or genre != 'appareil':
            return ''
        return q.lignes.get((i, x), '')

    def cles(self, ligne: int):
        """(genre, question, niveau, lien, provenance) d'une ligne, pour le filtre."""
        i, genre, x = self.lignes[ligne]
        if genre == 'appareil':
            a = self.lot.fiches[i].rapprochement.appareils[x]
            return genre, self.question(ligne), a.niveau, a.lien, a.provenance
        return genre, '', x.statut, '', ''

    def libelle_question(self, cle: str) -> str:
        if not cle:
            return ''
        if cle in _SANS_QUESTION:
            return _SANS_QUESTION[cle]
        q = getattr(self.lot, 'questionnaire', None)
        question = q.questions.get(cle) if q is not None else None
        if question is None:
            return cle
        reponse = libelle_reponse(question, question.reponse)
        return f"{cle} · {reponse}" if reponse else f"{cle} · sans réponse"

    def texte(self, ligne: int) -> tuple:
        i, genre, x = self.lignes[ligne]
        f = self.lot.fiches[i]
        if genre == 'appareil':
            a = f.rapprochement.appareils[x]
            return (f.id_produit, f.ref_piece, _GENRES[genre], NIVEAUX_METIER.get(a.niveau, a.niveau),
                    LIENS_METIER.get(a.lien, a.lien), a.marque or a.marque_fiche or "?", a.ref_modele,
                    a.nom, a.type or "—", PROVENANCES_METIER.get(a.provenance, a.provenance),
                    self.libelle_question(self.question(ligne)), a.suspecte or a.raison)
        if genre == 'remplacement':
            return (f.id_produit, f.ref_piece, _GENRES[genre],
                    STATUTS_REMPLACEMENT.get(x.statut, x.statut), '', '',
                    f"{x.ancienne} remplacée par {x.nouvelle}", x.successeur_actuel or '', '', '', '',
                    x.raison)
        return (f.id_produit, f.ref_piece, _GENRES[genre], STATUTS_EQUIVALENCE.get(x.statut, x.statut),
                '', x.origine or '', f"équivalente : {x.reference}", '', '', '', '', x.raison)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return self.texte(index.row())[index.column()]
        return None


class FiltreDetailLot(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.valeurs = ['', '', '', '', '']     # genre, question, niveau, lien, provenance
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


_COLONNES_FICHES = ("N°", "Pièce", "Fiche", "Appareils", "Ce qu'il reste")
_FILTRES_FICHES = [('', "Toutes les fiches"), ('question', "Avec une question"),
                   ('prete', "Prêtes"), ('revoir', "À revoir")]


class ModeleFichesLot(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lot = None
        self.plan = None
        self.questions_fiche: Dict[int, Set[str]] = {}

    def charger(self, lot, plan):
        self.beginResetModel()
        self.lot, self.plan = lot, plan
        self.questions_fiche = {}
        q = getattr(lot, 'questionnaire', None) if lot is not None else None
        if q is not None:
            for question in q.sans_reponse():
                for i, _ in question.occurrences:
                    self.questions_fiche.setdefault(i, set()).add(question.cle)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.lot is None else len(self.lot.fiches)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLONNES_FICHES)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLONNES_FICHES[section]
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole and section == 0:
            return "Numéro du produit sur 1001pieces.com"
        return None

    def etat(self, i: int):
        """(genre, texte) : 'revoir', 'question', 'prete'."""
        f = self.lot.fiches[i]
        if f.erreur:
            return 'revoir', f"À revoir : lecture impossible ({f.erreur})"
        if self.plan is not None and i in self.plan.de_cote:
            return 'revoir', f"À revoir : {f.raison_de_cote or 'mise de côté'}"
        questions = self.questions_fiche.get(i)
        if questions:
            return 'question', f"{len(questions)} question(s) : {', '.join(sorted(questions))}"
        revoir = (self.plan.a_revoir.get(i) if self.plan is not None else None) or []
        if revoir:
            return 'revoir', f"Enregistrée en partie, puis à revoir : {len(revoir)} appareil(s) ({revoir[0]})"
        suffixe = " (choix faits dans la fiche)" if (
            getattr(self.lot, 'questionnaire', None) is not None
            and i in self.lot.questionnaire.individuels) else ''
        return 'prete', "Prête" + suffixe

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.lot is None:
            return None
        f = self.lot.fiches[index.row()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            appareils = len(f.rapprochement.appareils) if f.rapprochement is not None else 0
            return (f.id_produit, f.ref_piece or '?', f.nom, appareils,
                    self.etat(index.row())[1])[index.column()]
        if role == Qt.UserRole:
            return self.etat(index.row())[0]
        return None


class FiltreFichesLot(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.genre = ''

    def filterAcceptsRow(self, ligne, parent):
        if not self.genre:
            return True
        m = self.sourceModel()
        return m.data(m.index(ligne, 0), Qt.UserRole) == self.genre


# =============================================================================
# Fenêtre
# =============================================================================

class RepriseSiteDialog(QDialog):
    """Import des fiches du site, lot par lot, par questions."""

    def __init__(self, db_manager, main_window=None, service: Optional[RepriseSiteService] = None,
                 on_lot_enregistre: Optional[Callable] = None):
        super().__init__(main_window)
        self.setWindowTitle("Importer les fiches du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1240, 880)
        self.db = db_manager
        self.main_window = main_window
        self.on_lot_enregistre = on_lot_enregistre
        self.service = service or RepriseSiteService(db_manager, main_window)
        self.lot = None
        self.plan = None
        self._tache: Optional[_Tache] = None
        self._signature = None
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

        titre = QLabel("Exports du site (CSV de la base PrestaShop)")
        titre.setStyleSheet(StyleManager.TITRE_SECTION)
        racine.addWidget(titre)
        self.champ_produits = self._ligne_fichier(racine, "Produits :", "Export des produits")
        self.champ_compat = self._ligne_fichier(racine, "Compatibilités :", "Export des compatibilités")
        choisir = QHBoxLayout()
        self.bouton_export = QPushButton(qta.icon('fa5s.file-import', color='#555555'),
                                         "Utiliser ces exports")
        self.bouton_export.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_export.clicked.connect(self._examiner_export)
        self.bouton_zero = QPushButton(qta.icon('fa5s.redo', color='#555555'), "Repartir de zéro")
        self.bouton_zero.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_zero.clicked.connect(lambda: self._adopter(True))
        self.bouton_continuer = QPushButton(qta.icon('fa5s.forward', color='#555555'),
                                            "Continuer l'import")
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
        lot.addWidget(QLabel("Fiches par lot :"))
        self.taille = QSpinBox()
        self.taille.setRange(1, 2000)
        self.taille.setValue(int(_reglages().value(_CLE_TAILLE, 100) or 100))
        lot.addWidget(self.taille)
        self.bouton_analyser = QPushButton(qta.icon('fa5s.search', color='white'), "Lire le lot suivant")
        self.bouton_analyser.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_analyser.setToolTip("Lit les fiches suivantes de l'export et les compare à l'outil. "
                                        "Rien n'est enregistré avant « Enregistrer le lot ».")
        self.bouton_analyser.clicked.connect(self._analyser_lot)
        self.bouton_de_cote = QPushButton(qta.icon('fa5s.inbox', color='#555555'), "Fiches à revoir")
        self.bouton_de_cote.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_de_cote.setToolTip("Fiches mises de côté, ou enregistrées en partie parce que des "
                                       "appareils restaient à choisir. Elles reviennent ici quand vous voulez.")
        self.bouton_de_cote.clicked.connect(self._analyser_de_cote)
        self.bouton_annuler = QPushButton(qta.icon('fa5s.stop', color='#555555'), "Arrêter")
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

        self.titre_lot = QLabel("Aucun lot lu : cliquez « Lire le lot suivant ».")
        self.titre_lot.setStyleSheet(StyleManager.TITRE_SECTION)
        racine.addWidget(self.titre_lot)
        self.onglets = QTabWidget()
        self.panneau = PanneauQuestions(self._repondre, self._voir_lignes)
        self.panneau.vider()
        self.onglets.addTab(self.panneau, "À décider")
        self.onglets.addTab(self._construire_fiches(), "Fiches du lot")
        self.onglets.addTab(self._construire_detail(), "Toutes les lignes")
        racine.addWidget(self.onglets, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_propositions = QPushButton(qta.icon('fa5s.check-double', color='#555555'),
                                               "Accepter les propositions…")
        self.bouton_propositions.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_propositions.setToolTip("Répond par sa proposition à chaque question qui en a une. "
                                            "Les questions sans proposition restent à votre décision.")
        self.bouton_propositions.clicked.connect(self._accepter_propositions)
        self.bouton_enregistrer = QPushButton(qta.icon('fa5s.save', color='white'), "Enregistrer le lot")
        self.bouton_enregistrer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_enregistrer.clicked.connect(self._enregistrer)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        pied.addWidget(self.bouton_propositions)
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

    def _construire_fiches(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        haut = QHBoxLayout()
        self.filtre_fiches_genre = QComboBox()
        for valeur, libelle in _FILTRES_FICHES:
            self.filtre_fiches_genre.addItem(libelle, valeur)
        self.filtre_fiches_genre.currentIndexChanged.connect(self._filtrer_fiches)
        haut.addWidget(self.filtre_fiches_genre)
        haut.addStretch(1)
        disposition.addLayout(haut)
        self.modele_fiches = ModeleFichesLot(self)
        self.filtre_fiches = FiltreFichesLot(self)
        self.filtre_fiches.setSourceModel(self.modele_fiches)
        self.table_fiches = QTableView()
        self.table_fiches.setModel(self.filtre_fiches)
        self.table_fiches.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_fiches.verticalHeader().setVisible(False)
        self.table_fiches.verticalHeader().setDefaultSectionSize(22)
        self.table_fiches.horizontalHeader().setStretchLastSection(True)
        self.table_fiches.setAlternatingRowColors(True)
        self.table_fiches.doubleClicked.connect(
            lambda idx: self._ouvrir_fiche(self.filtre_fiches.mapToSource(idx).row()))
        disposition.addWidget(self.table_fiches, 1)
        actions = QHBoxLayout()
        ouvrir = QPushButton(qta.icon('fa5s.search-plus', color='#555555'), "Ouvrir la fiche…")
        ouvrir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        ouvrir.setToolTip("Aperçu complet de la fiche : vos choix ligne par ligne l'emportent sur "
                          "les réponses du lot.")
        ouvrir.clicked.connect(lambda: self._ouvrir_fiche(self._fiche_selectionnee()))
        de_cote = QPushButton("Mettre à revoir")
        de_cote.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        de_cote.setToolTip("Rien n'est enregistré pour cette fiche ; elle passe dans « Fiches à revoir ».")
        de_cote.clicked.connect(self._fiche_de_cote)
        reprendre = QPushButton("Remettre dans le lot")
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
                ("Tous les genres", _GENRES),
                ("Toutes les questions", {}),
                ("Tout ce que l'outil a trouvé", NIVEAUX_METIER),
                ("Toutes les compatibilités", {k: v for k, v in LIENS_METIER.items() if k}),
                ("Partout (description et table)", PROVENANCES_METIER)):
            combo = QComboBox()
            combo.addItem(tous, '')
            for cle, libelle in valeurs.items():
                combo.addItem(libelle, cle)
            combo.currentIndexChanged.connect(self._filtrer)
            filtres.addWidget(combo)
            self.filtres.append(combo)
        self.filtre_texte = QLineEdit()
        self.filtre_texte.setPlaceholderText("Filtrer (n°, pièce, marque, référence)")
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
        reglages = _reglages()
        etat = self.service.etat() or {}
        for champ, cle, colonne, nom in (
                (self.champ_produits, _CLE_PRODUITS, 'chemin_produits', 'produits.csv'),
                (self.champ_compat, _CLE_COMPAT, 'chemin_compatibilites', 'compatibilites.csv')):
            # Le premier chemin qui existe encore : état de l'import, dernier choix,
            # puis l'export rangé dans data/reprise_site/
            candidats = [etat.get(colonne) or '', reglages.value(cle, '') or '',
                         str(_DOSSIER_DEFAUT / nom)]
            chemin = next((c for c in candidats if c and Path(c).exists()), '')
            champ.setText(chemin)

    def _parcourir(self, champ: QLineEdit, titre: str):
        dossier = str(Path(champ.text()).parent) if champ.text() else str(_DOSSIER_DEFAUT)
        choisir_fichier_a_ouvrir(self, titre, dossier, "Fichiers CSV (*.csv);;Tous les fichiers (*)",
                                 lambda chemin: champ.setText(chemin), natif=False)

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
        reglages = _reglages()
        reglages.setValue(_CLE_PRODUITS, produits)
        reglages.setValue(_CLE_COMPAT, compat)
        self._signature = signature
        if statut == EXPORT_DIFFERENT and self.service.dernier_id():
            for b in (self.bouton_zero, self.bouton_continuer):
                b.setVisible(True)
            self._message(f"Cet export (du {signature.date_export.replace('T', ' ')}) n'est pas celui "
                          f"de l'import en cours : repartir de zéro, ou continuer après le produit "
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
        self._message("Exports prêts : lisez le lot suivant.")
        self._rafraichir_etat()

    def _rafraichir_etat(self):
        etat = self.service.etat()
        lots = self.db.lots_reprise_site(limite=1000)
        de_cote = self.db.fiches_de_cote_reprise_site()
        if not etat:
            texte = "Aucun import commencé : choisissez les deux exports."
        else:
            texte = (f"<b>Dernier produit importé : {etat['dernier_id'] or '—'}</b> · exports du "
                     f"{(etat['date_export'] or '?').replace('T', ' à ')} · {len(lots)} lot(s) "
                     f"enregistré(s) · {len(de_cote)} fiche(s) à revoir")
            if lots:
                d = lots[0]
                texte += (f"<br>Dernier lot : produits {d['premier_id']} à {d['dernier_id']}, "
                          f"{d['fiches']} fiche(s), base "
                          f"{((d['taille_apres'] or 0) - (d['taille_avant'] or 0)) / 1e6:+.1f} Mo")
            if self.service.signature is None:
                texte += "<br><i>Cliquez « Utiliser ces exports » pour continuer.</i>"
        self.carte.setText(texte)
        self.bouton_de_cote.setText(f"Fiches à revoir ({len(de_cote)})")
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
        self.texte_progression.setText('')
        fin(resultat, erreur)
        self._rafraichir_etat()

    def _annuler(self):
        if self._tache is not None:
            self._tache.arret.set()
            self.texte_progression.setText("Arrêt demandé…")

    def _analyser_lot(self):
        if self.service.signature is None:
            self._examiner_export()
            if self.service.signature is None:
                return
        taille = self.taille.value()
        _reglages().setValue(_CLE_TAILLE, taille)
        self._effacer_lot()
        self._lancer(lambda prog, annule: self.service.analyser_lot_suivant(taille, prog, annule),
                     self._lot_analyse, "Lecture du lot…")

    def _analyser_de_cote(self):
        self._effacer_lot()
        self._lancer(lambda prog, annule: self.service.analyser_fiches_de_cote(prog, annule),
                     self._lot_analyse, "Lecture des fiches à revoir…")

    def _relire(self):
        lot = self.lot
        self._lancer(lambda prog, annule: self.service.relire_lot(lot, prog, annule),
                     self._lot_analyse, "Relecture du lot (groupes de marques modifiés)…")

    def _lot_analyse(self, lot, erreur: str):
        if erreur:
            arret = 'AnalyseAnnulee' in erreur
            self._message("Lecture arrêtée." if arret else f"Lecture impossible : {erreur}",
                          erreur=not arret)
            return
        if lot is None:
            self._message("Export entièrement importé : plus aucun produit après le dernier traité.")
            return
        self.afficher_lot(lot)

    def afficher_lot(self, lot):
        """Affiche un lot lu (aussi appelé par les tests, sans thread)."""
        self.lot = lot
        if lot.questionnaire is None:
            self.service.questionnaire(lot)
        if not self.panneau.types:
            self.panneau.types = self.service.fiche_service.types_outil()
            self.panneau.marques = self.service.fiche_service.marques_outil()
        e = lot.export
        nature = ("Fiches à revoir" if lot.fiches_de_cote
                  else f"Lot : produits {e.premier_id} à {e.dernier_id}")
        self.titre_lot.setText(f"{nature} · {len(lot.fiches)} fiche(s) · rien n'est encore enregistré")
        self.modele_detail.charger(lot)
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
            self._message(("Enregistrement arrêté" if res.annule else
                           f"Enregistrement interrompu : {res.erreur}")
                          + " — l'import n'a pas avancé ; relisez le lot : rien ne sera doublé.",
                          erreur=not res.annule, avertissement=res.annule)
            return
        self._effacer_lot()
        self._message(f"Lot n° {res.numero} enregistré : {res.resume()}.")
        if self.on_lot_enregistre is not None:
            self.on_lot_enregistre(res)

    # =========================================================================
    # Questions
    # =========================================================================
    def _repondre(self, cle: str, valeur: Optional[str]):
        q = self.lot.questionnaire if self.lot is not None else None
        if q is None:
            return
        q.repondre(cle, valeur)
        if q.relire and self._tache is None:
            self._relire()
            return
        self._mettre_a_jour()

    def _accepter_propositions(self):
        q = self.lot.questionnaire if self.lot is not None else None
        if q is None:
            return
        avec = [x for x in q.sans_reponse() if x.proposition is not None]
        sans = [x for x in q.sans_reponse() if x.proposition is None]
        if not avec:
            self._message("Aucune question avec proposition ne reste sans réponse.")
            return
        texte = "Réponses qui seront données :\n" + "\n".join(
            f"• {x.titre} → {libelle_reponse(x, x.proposition)} ({nombre(x.cas)} cas)" for x in avec)
        if sans:
            texte += "\n\nRestent à votre décision :\n" + "\n".join(f"• {x.titre}" for x in sans)
        demander_oui_non(self, "Accepter les propositions ?", texte, self._propositions_acceptees,
                         defaut=None)

    def _propositions_acceptees(self):
        q = self.lot.questionnaire if self.lot is not None else None
        if q is not None:
            q.accepter_propositions()
            self._mettre_a_jour()

    def _voir_lignes(self, cle: str):
        combo = self.filtres[1]
        i = combo.findData(cle)
        if i < 0:
            return
        combo.setCurrentIndex(i)
        self.onglets.setCurrentIndex(2)

    # =========================================================================
    # Fiches
    # =========================================================================
    def _fiche_selectionnee(self) -> int:
        lignes = self.table_fiches.selectionModel().selectedRows() if self.lot else []
        return self.filtre_fiches.mapToSource(lignes[0]).row() if lignes else -1

    def _fiche_de_cote(self):
        i = self._fiche_selectionnee()
        if i >= 0:
            self.lot.mettre_de_cote(i, "mise à revoir dans le lot")
            self._mettre_a_jour()

    def _fiche_reprise(self):
        i = self._fiche_selectionnee()
        if i >= 0:
            self.lot.reprendre(i)
            self._mettre_a_jour()

    def _ouvrir_depuis_detail(self, index):
        source = self.filtre_detail.mapToSource(index)
        self._ouvrir_fiche(self.modele_detail.lignes[source.row()][0])

    def _ouvrir_fiche(self, i: int):
        if self.lot is None or i < 0 or self.lot.fiches[i].rapprochement is None:
            return
        from .fiche_site_dialog import FicheSiteDialog
        f = self.lot.fiches[i]
        q = self.lot.questionnaire
        dialogue = FicheSiteDialog(self.db, main_window=self, service=self.service.fiche_service,
                                   on_decide=lambda d, i=i: self._fiche_decidee(i, d))
        dialogue.setWindowTitle(f"Fiche du lot n° {f.id_produit}")
        dialogue.afficher_dans_lot(f, q.reponses, copy.deepcopy(q.individuels.get(i)),
                                   acces=self.service._acces_lecture(),
                                   config=self.service.fiche_service.configuration(),
                                   sauver_regles=self.service._sauver_regles)
        dialogue.show()
        self._fiche_ouverte = dialogue

    def _fiche_decidee(self, i: int, individuels):
        if self.lot is not None and self.lot.questionnaire is not None and i < len(self.lot.fiches):
            q = self.lot.questionnaire
            q.memorisees = dict(self.service.fiche_service.configuration().regles)
            if individuels is not None and (individuels.appareils or individuels.remplacements
                                            or individuels.origines or individuels.ecartees
                                            or individuels.identite):
                q.individuels[i] = individuels
            else:
                q.individuels.pop(i, None)
            q.construire()
            self._mettre_a_jour()

    # =========================================================================
    # Filtres et état
    # =========================================================================
    def _remplir_filtre_questions(self):
        combo = self.filtres[1]
        actuelle = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Toutes les questions", '')
        q = self.lot.questionnaire if self.lot is not None else None
        if q is not None:
            for x in q.liste():
                combo.addItem(f"{x.cle} · {x.titre[:70]}", x.cle)
            for cle, libelle in _SANS_QUESTION.items():
                combo.addItem(libelle.capitalize(), cle)
        i = combo.findData(actuelle)
        combo.setCurrentIndex(max(0, i))
        combo.blockSignals(False)

    def _filtrer(self, *_):
        self.filtre_detail.valeurs = [c.currentData() or '' for c in self.filtres]
        self.filtre_detail.texte = self.filtre_texte.text().strip().lower()
        self.filtre_detail.invalidateFilter()
        self.compte_detail.setText(f"{nombre(self.filtre_detail.rowCount())} ligne(s) sur "
                                   f"{nombre(self.modele_detail.rowCount())}")

    def _filtrer_fiches(self, *_):
        self.filtre_fiches.genre = self.filtre_fiches_genre.currentData() or ''
        self.filtre_fiches.invalidateFilter()

    def _effacer_lot(self):
        self.lot = self.plan = None
        self.panneau.vider()
        self.modele_detail.charger(None)
        self.modele_fiches.charger(None, None)
        self.titre_lot.setText("Aucun lot lu : cliquez « Lire le lot suivant ».")
        self.onglets.setTabText(0, "À décider")
        self.onglets.setTabText(1, "Fiches du lot")
        self._activer()

    def _mettre_a_jour(self):
        if self.lot is None:
            return
        q = self.lot.questionnaire
        self.plan = self.lot.planifier()
        self.panneau.afficher(q)
        self._remplir_filtre_questions()
        self.modele_fiches.charger(self.lot, self.plan)
        self._filtrer()
        restantes = q.sans_reponse()
        self.onglets.setTabText(0, f"À décider ({len(restantes)})" if restantes else "À décider")
        self.onglets.setTabText(1, f"Fiches du lot ({len(self.lot.fiches)})")
        p = self.plan
        if p.pret:
            s = p.resume()
            revoir = len(p.a_revoir) + len(p.de_cote)
            self._message(f"Prêt : {s['fiches']} fiche(s) · {nombre(s['appareils_a_creer'])} appareil(s) "
                          f"créé(s) · {nombre(s['liens'])} compatibilité(s) · {s['remplacements']} "
                          f"ancienne(s) référence(s) · {s['equivalences']} équivalente(s)"
                          + (f" · {revoir} fiche(s) passeront dans « Fiches à revoir »" if revoir else ''))
        else:
            texte = f"Il reste {len(restantes)} question(s)" if restantes else "Avant d'enregistrer"
            if p.en_attente:
                texte += " : " + " ; ".join(t.split(' : ')[0] for t in p.en_attente[:3])
                if len(p.en_attente) > 3:
                    texte += " ; …"
            self._message(texte, avertissement=True)
        self._activer()

    def _activer(self):
        occupe = self._tache is not None
        self.bouton_analyser.setEnabled(not occupe)
        self.bouton_export.setEnabled(not occupe)
        self.bouton_annuler.setEnabled(occupe)
        q = self.lot.questionnaire if self.lot is not None else None
        self.bouton_propositions.setEnabled(
            not occupe and q is not None and any(x.proposition is not None for x in q.sans_reponse()))
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
            # (l'écriture s'arrête entre deux fiches ; l'import n'avance pas).
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
