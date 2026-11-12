"""
Fenêtre « Lire une fiche du site » : aperçu et enregistrement d'une fiche
(CDC docs/cdc_import_fiches_site.md, § 7.1, § 10.3, § 10.8)

- Entrée : le lien de la page publique (téléchargée hors du thread principal)
  ou la description collée (HTML du back-office ou texte).
- Carte de la pièce : référence, nouvelle ou connue, référence produit du site,
  n° du produit, code-barres, nom tiré du titre.
- À décider : le même moteur de questions que l'import par lots, appliqué à
  une fiche (src/utils/reprise_site/questions.py, src/ui/questions_reprise.py) :
  ce que l'outil fera sans vous, les règles (mémorisées), les questions.
- Onglets :
  * Appareils : table virtuelle filtrable ; le panneau sous la table fait un
    choix ligne par ligne (appareil parmi les candidats, créer, rattacher,
    laisser de côté, marque, type), qui l'emporte sur les réponses ;
  * Anciennes références et équivalentes : garder l'existant ou prendre la
    fiche en cas de conflit, marque d'origine, écarter une référence ;
  * À savoir : appareils de l'outil absents de la fiche, passages non compris.
- « Enregistrer » ne s'active que lorsque toutes les questions ont une réponse.

Mode « fiche d'un lot » (import par lots) : `afficher_dans_lot`, sans lien ni
collage ; « Garder ces choix pour le lot » rend au lot les choix faits ligne
par ligne (l'écriture se fait avec tout le lot).

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QThread, pyqtSignal,
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableView, QTabWidget, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.enregistrement_fiche_service import EnregistrementFicheService, telecharger_page
from src.utils.rapprochement_fiche import STATUTS_EQUIVALENCE, STATUTS_REMPLACEMENT
from src.utils.rapprochement_fiche.decisions import (
    CATEGORIES_RESUME, ChoixAppareil, DecisionsFiche, categorie_appareil,
)
from src.utils.reprise_site.questions import A_REVOIR, ILLISIBLE
from .questions_reprise import (
    LIENS_METIER, NIVEAUX_METIER, PROVENANCES_METIER, PanneauQuestions, libelle_reponse,
)
from .style_manager import StyleManager

_STATUTS_PIECE = {'reelle': "déjà dans l'outil",
                  'fantome': "ancienne référence de l'outil, elle deviendra une vraie pièce",
                  'absente': "nouvelle : elle sera créée"}
_COLONNES = ("N°", "Ce que l'outil a trouvé", "Compatibilité", "Marque", "Référence",
             "Nom commercial", "Type", "Cité dans", "Décision", "Pourquoi")
_SANS_QUESTION = {A_REVOIR: "à revoir : appareil à choisir", ILLISIBLE: "illisible : non créé"}


class _Telechargement(QThread):
    """Téléchargement de la page publique, hors du thread principal."""
    termine = pyqtSignal(str, str)      # page, erreur

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.termine.emit(telecharger_page(self.url), '')
        except Exception as e:
            self.termine.emit('', str(e))


class ModeleAppareils(QAbstractTableModel):
    """Lignes d'appareils de la fiche, avec la décision courante de chacune."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.appareils = []
        self.dialogue = None                # FicheSiteDialog : décisions et questions

    def charger(self, appareils, dialogue):
        self.beginResetModel()
        self.appareils, self.dialogue = appareils, dialogue
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.appareils)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLONNES)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLONNES[section]
        return None

    def choix_texte(self, index: int) -> str:
        d = self.dialogue
        if d is None:
            return ''
        a = self.appareils[index]
        c = d.individuels.appareils.get(index)
        if c is not None:
            if c.ignorer:
                return "vous : laisser de côté"
            if c.appareil_id is not None:
                choisi = next((x for x in a.candidats if x.id == c.appareil_id), None)
                return f"vous : relier à {choisi.ref_modele if choisi else c.appareil_id}"
            if c.creer:
                return "vous : créer"
            if c.rattacher:
                return "vous : rattacher"
            return "vous : marque / type choisis"
        cle = d.questionnaire.lignes.get((0, index)) if d.questionnaire else None
        if not cle:
            return "automatique"
        if cle in _SANS_QUESTION:
            return _SANS_QUESTION[cle]
        q = d.questionnaire.questions.get(cle)
        reponse = libelle_reponse(q, q.reponse) if q is not None else ''
        return f"{cle} : {reponse}" if reponse else f"{cle} : à répondre"

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        a = self.appareils[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return (a.numero or "table", NIVEAUX_METIER.get(a.niveau, a.niveau),
                    LIENS_METIER.get(a.lien, a.lien), a.marque or a.marque_fiche or "?",
                    a.ref_modele, a.nom, a.type or "—",
                    PROVENANCES_METIER.get(a.provenance, a.provenance),
                    self.choix_texte(index.row()), a.suspecte or a.raison)[col]
        if role == Qt.UserRole:
            return categorie_appareil(a)
        if role == Qt.UserRole + 1:
            return a.lien
        if role == Qt.UserRole + 2:
            return a.provenance
        return None

    def rafraichir(self):
        if self.appareils:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self.appareils) - 1, len(_COLONNES) - 1))


class FiltreAppareils(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.categorie = self.lien = self.provenance = ''
        self.texte = ''

    def filterAcceptsRow(self, ligne, parent):
        m = self.sourceModel()
        idx = m.index(ligne, 0, parent)
        if self.categorie and m.data(idx, Qt.UserRole) != self.categorie:
            return False
        if self.lien and m.data(idx, Qt.UserRole + 1) != self.lien:
            return False
        if self.provenance and m.data(idx, Qt.UserRole + 2) != self.provenance:
            return False
        if self.texte:
            a = m.appareils[ligne]
            cible = f"{a.marque} {a.marque_fiche} {a.ref_modele} {a.nom} {a.raison}".lower()
            return self.texte in cible
        return True


class FicheSiteDialog(QDialog):
    """Aperçu complet d'une fiche du site, puis enregistrement après réponse aux questions."""

    def __init__(self, db_manager, main_window=None, on_enregistre: Optional[Callable] = None,
                 service: Optional[EnregistrementFicheService] = None,
                 on_decide: Optional[Callable[[DecisionsFiche], None]] = None,
                 chemin_regles=None):
        super().__init__(main_window)
        self.on_decide = on_decide
        self.chemin_regles = chemin_regles      # None = data/reprise_fiches.json du poste
        self.setWindowTitle("Fiche du lot" if on_decide else "Lire une fiche du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1180, 860)
        self.db = db_manager
        self.main_window = main_window
        self.on_enregistre = on_enregistre
        self.service = service or EnregistrementFicheService(db_manager, main_window)
        self.rapprochement = None
        self.lot = None                     # lot d'une seule fiche (moteur de questions)
        self.questionnaire = None
        self.individuels = DecisionsFiche()  # choix ligne par ligne (l'emportent)
        self.plan = None
        self._telechargement = None
        self._types: List[str] = []
        self._marques: List[str] = []
        self._acces = None
        self._config = None
        self._sauver_regles = None
        self._construire()
        if on_decide is not None:
            for w in (self.champ_lien, self.bouton_lien, self.bouton_coller):
                w.setVisible(False)
            self.bouton_enregistrer.setText("Garder ces choix pour le lot")
            self.bouton_enregistrer.setIcon(qta.icon('fa5s.reply', color='white'))

    # =========================================================================
    # Construction
    # =========================================================================
    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)

        entree = QHBoxLayout()
        self.champ_lien = QLineEdit()
        self.champ_lien.setPlaceholderText("Lien de la fiche : https://www.1001pieces.com/20746-….html")
        self.champ_lien.returnPressed.connect(self._lire_lien)
        self.bouton_lien = QPushButton(qta.icon('fa5s.globe', color='#555555'), "Lire")
        self.bouton_lien.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_lien.clicked.connect(self._lire_lien)
        self.bouton_coller = QPushButton(qta.icon('fa5s.paste', color='#555555'), "Coller le texte…")
        self.bouton_coller.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_coller.setCheckable(True)
        self.bouton_coller.toggled.connect(self._basculer_collage)
        entree.addWidget(self.champ_lien, 1)
        entree.addWidget(self.bouton_lien)
        entree.addWidget(self.bouton_coller)
        racine.addLayout(entree)

        self.zone_collage = QWidget()
        collage = QVBoxLayout(self.zone_collage)
        collage.setContentsMargins(0, 0, 0, 0)
        self.champ_description = QPlainTextEdit()
        self.champ_description.setPlaceholderText(
            "Description de la fiche (HTML du back-office ou texte)")
        self.champ_description.setMaximumHeight(140)
        bouton = QPushButton("Lire le texte")
        bouton.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        bouton.clicked.connect(self._lire_description)
        collage.addWidget(self.champ_description)
        collage.addWidget(bouton, 0, Qt.AlignRight)
        self.zone_collage.setVisible(False)
        racine.addWidget(self.zone_collage)

        self.carte = QLabel("Indiquez le lien d'une fiche ou collez son texte.")
        self.carte.setWordWrap(True)
        self.carte.setTextFormat(Qt.RichText)
        self.carte.setStyleSheet(StyleManager.CARTE_GRIS_CLAIR + " padding: 8px;")
        racine.addWidget(self.carte)

        separation = QSplitter(Qt.Vertical)
        self.panneau = PanneauQuestions(self._repondre, self._voir_lignes)
        self.panneau.vider()
        separation.addWidget(self.panneau)
        separation.addWidget(self._construire_onglets())
        separation.setStretchFactor(0, 1)
        separation.setStretchFactor(1, 1)
        separation.setSizes([360, 420])
        racine.addWidget(separation, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_tout = QPushButton(qta.icon('fa5s.check-double', color='#555555'),
                                       "Accepter les propositions")
        self.bouton_tout.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_tout.setToolTip("Répond par sa proposition à chaque question qui en a une.")
        self.bouton_tout.clicked.connect(self._tout_valider)
        self.bouton_enregistrer = QPushButton(qta.icon('fa5s.save', color='white'), "Enregistrer")
        self.bouton_enregistrer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_enregistrer.setEnabled(False)
        self.bouton_enregistrer.clicked.connect(self._enregistrer)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        pied.addWidget(self.bouton_tout)
        pied.addWidget(self.bouton_enregistrer)
        pied.addWidget(fermer)
        racine.addLayout(pied)

    def _construire_onglets(self) -> QWidget:
        self.onglets = QTabWidget()
        self.onglets.addTab(self._construire_appareils(), "Appareils")
        self.relations = QTreeWidget()
        self.relations.setHeaderLabels(["Référence", "Ce que l'outil en sait", "Marque d'origine / cible",
                                        "Décision", "Pourquoi"])
        self.relations.setRootIsDecorated(True)
        self.relations.header().setSectionResizeMode(4, QHeaderView.Stretch)
        self.onglets.addTab(self.relations, "Anciennes références et équivalentes")
        self.informations = QTextBrowser()
        self.onglets.addTab(self.informations, "À savoir")
        return self.onglets

    def _construire_appareils(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        filtres = QHBoxLayout()
        self.filtre_categorie = QComboBox()
        self.filtre_categorie.addItem("Tous les appareils", '')
        for cle, libelle in CATEGORIES_RESUME.items():
            if cle not in ('relations', 'conflits'):
                self.filtre_categorie.addItem(libelle, cle)
        self.filtre_lien = QComboBox()
        self.filtre_lien.addItem("Toutes les compatibilités", '')
        for cle, libelle in LIENS_METIER.items():
            if cle:
                self.filtre_lien.addItem(libelle, cle)
        self.filtre_provenance = QComboBox()
        self.filtre_provenance.addItem("Partout (description et table)", '')
        for cle, libelle in PROVENANCES_METIER.items():
            self.filtre_provenance.addItem(libelle, cle)
        self.filtre_texte = QLineEdit()
        self.filtre_texte.setPlaceholderText("Filtrer (marque, référence, nom)")
        for combo in (self.filtre_categorie, self.filtre_lien, self.filtre_provenance):
            combo.currentIndexChanged.connect(self._filtrer)
        self.filtre_texte.textChanged.connect(self._filtrer)
        for w in (self.filtre_categorie, self.filtre_lien, self.filtre_provenance):
            filtres.addWidget(w)
        filtres.addWidget(self.filtre_texte, 1)
        disposition.addLayout(filtres)

        self.modele = ModeleAppareils(self)
        self.filtre = FiltreAppareils(self)
        self.filtre.setSourceModel(self.modele)
        self.table = QTableView()
        self.table.setModel(self.filtre)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.selectionModel().selectionChanged.connect(self._ligne_selectionnee)
        disposition.addWidget(self.table, 1)

        choix = QHBoxLayout()
        choix.addWidget(QLabel("Lignes sélectionnées :"))
        self.choix_appareil = QComboBox()
        self.choix_appareil.setMinimumWidth(260)
        self.choix_appareil.currentIndexChanged.connect(self._action_choisie)
        self.libelle_marque = QLabel("Marque")
        self.choix_marque = QComboBox()
        self.choix_marque.setEditable(True)
        self.choix_marque.setMinimumWidth(140)
        self.libelle_type = QLabel("Type")
        self.choix_type = QComboBox()
        self.choix_type.setEditable(True)
        self.choix_type.setMinimumWidth(140)
        appliquer = QPushButton("Appliquer")
        appliquer.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        appliquer.clicked.connect(self._appliquer_choix)
        retour = QPushButton("Revenir à la réponse du lot")
        retour.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        retour.setToolTip("Retire le choix fait ligne par ligne : la réponse à la question s'applique.")
        retour.clicked.connect(self._retour_proposition)
        choix.addWidget(self.choix_appareil, 1)
        for w in (self.libelle_marque, self.choix_marque, self.libelle_type, self.choix_type):
            choix.addWidget(w)
        choix.addWidget(appliquer)
        choix.addWidget(retour)
        disposition.addLayout(choix)
        self._action_choisie()
        return boite

    # =========================================================================
    # Lecture
    # =========================================================================
    def _basculer_collage(self, actif: bool):
        self.zone_collage.setVisible(actif)

    def _lire_lien(self):
        url = self.champ_lien.text().strip()
        if not url or self._telechargement is not None:
            return
        self.etat.setText("Téléchargement de la fiche…")
        self.bouton_lien.setEnabled(False)
        self._telechargement = _Telechargement(url, self)
        self._telechargement.termine.connect(lambda page, err: self._page_recue(url, page, err))
        self._telechargement.start()

    def _page_recue(self, url: str, page: str, erreur: str):
        self._telechargement = None
        self.bouton_lien.setEnabled(True)
        if erreur:
            self.etat.setText(f"Lien illisible : {erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        self.analyser_page(page, url)

    def analyser_page(self, page: str, url: str = ''):
        """Lecture d'une page publique (aussi appelée par les tests, sans réseau)."""
        self._analyser(lambda: self.service.analyser_page(page, url)[1])

    def _lire_description(self):
        texte = self.champ_description.toPlainText()
        if texte.strip():
            self._analyser(lambda: self.service.analyser_description(texte)[1])

    def _analyser(self, lire):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = lire()
        except Exception as e:
            app_logger.error(f"[Fiche site] lecture impossible : {e}")
            self.etat.setText(f"Lecture impossible : {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.afficher(r)

    def _outils(self):
        """Accès en lecture, configuration et enregistrement des règles (fiche seule)."""
        if self._acces is None:
            from src.utils.rapprochement_fiche import AccesBaseLecture
            self._acces = AccesBaseLecture(self.db.conn)
        if self._config is None:
            self._config = self.service.configuration()
        if self._sauver_regles is None:
            from src.services.reprise_site_service import RepriseSiteService
            reprise = RepriseSiteService(self.db, self.main_window, fiche_service=self.service,
                                         chemin_configuration=self.chemin_regles)
            self._sauver_regles = reprise._sauver_regles

    def afficher(self, r, decisions: Optional[DecisionsFiche] = None, fiche=None,
                 reponses: Optional[Dict[str, str]] = None):
        """Affiche une fiche rapprochée (fiche seule, ou fiche d'un lot via afficher_dans_lot).
        `decisions` : choix ligne par ligne déjà faits."""
        from src.utils.reprise_site.exports import LotExport
        from src.utils.reprise_site.lot import FicheLot, LotReprise
        from src.utils.reprise_site.questions import QuestionnaireLot
        if not self._types:
            self._types = self.service.types_outil()
            self._marques = self.service.marques_outil()
            self.panneau.types, self.panneau.marques = self._types, self._marques
        self._outils()
        self.rapprochement = r
        ident = r.identite
        if fiche is None:
            fiche = FicheLot(ident.id_product or 0, ident.libelle or '', ident.ref_interne,
                             rapprochement=r)
        else:
            fiche = FicheLot(fiche.id_produit, fiche.nom, fiche.ref_interne, rapprochement=r,
                             profil_ambigu=fiche.profil_ambigu,
                             marques_annoncees=list(fiche.marques_annoncees))
        self.lot = LotReprise(LotExport([], fiche.id_produit, fiche.id_produit), [fiche])
        self.individuels = decisions if decisions is not None else DecisionsFiche()
        with self.db._query_lock:
            self.questionnaire = QuestionnaireLot(self.lot, self._acces, self._config,
                                                  sauver_regles=self._sauver_regles,
                                                  reponses=reponses)
            self.questionnaire.individuels[0] = self.individuels
            self.questionnaire.construire()
        self.lot.questionnaire = self.questionnaire
        self.modele.charger(r.appareils, self)
        self.table.resizeColumnsToContents()
        self._remplir_carte()
        self._remplir_relations()
        self._remplir_informations()
        self._mettre_a_jour()

    def afficher_dans_lot(self, fiche, reponses: Dict[str, str], individuels: Optional[DecisionsFiche],
                          acces=None, config=None, sauver_regles=None):
        """Fiche d'un lot : les réponses du lot sont reprises, les choix ligne par ligne
        reviennent au lot (« Garder ces choix pour le lot »)."""
        self._acces, self._config, self._sauver_regles = acces, config, sauver_regles
        self.afficher(fiche.rapprochement, individuels, fiche=fiche, reponses=dict(reponses))

    # =========================================================================
    # Remplissage
    # =========================================================================
    def _remplir_carte(self):
        r = self.rapprochement
        i = r.identite
        titre = f"<b>{i.libelle}</b><br>" if i.libelle else ''
        lignes = [titre + f"Pièce <b>{i.ref_piece or '?'}</b> · {_STATUTS_PIECE.get(i.statut, i.statut)}"
                  + (" (remplacée)" if i.obsolete else '')]
        if i.ref_interne or i.id_product is not None:
            egale = {'egale': " (= code produit)", 'prefixe': f" (code produit précédé de {i.prefixe})",
                     'lignee': " (une ancienne référence ou une équivalente)"}.get(i.statut_ref_interne, '')
            lignes.append((f"Produit n° {i.id_product} du site · " if i.id_product is not None else '')
                          + (f"référence produit {i.ref_interne}{egale}" if i.ref_interne else ''))
        if i.ean:
            etat = {'a_remplir': "sera ajouté", 'identique': "déjà connu",
                    'different': f"différent de {i.ean_outil}"}.get(i.statut_ean_outil, '')
            lignes.append(f"Code-barres {i.ean} ({'correct' if i.statut_ean == 'valide' else 'clé fausse'}"
                          + (f", {etat}" if etat else '') + ")")
        if i.libelle and i.statut_libelle == 'different':
            lignes.append(f"Nom actuel dans l'outil : « {i.libelle_outil} »")
        elif i.libelle and i.statut_libelle == 'ancienne_regle':
            lignes.append(f"Nom raccourci (sans le type d'appareil) : « {i.libelle_outil} » "
                          f"devient « {i.libelle} »")
        if r.liste_tronquee:
            lignes.append("<i>Liste d'appareils probablement réduite : rien n'en est déduit sur les "
                          "appareils absents.</i>")
        self.carte.setText("<br>".join(lignes))

    def _remplir_relations(self):
        self.relations.clear()
        r = self.rapprochement
        racine_r = QTreeWidgetItem([f"Anciennes références ({len(r.remplacements)})"])
        racine_e = QTreeWidgetItem([f"Équivalentes ({len(r.equivalences)})"])
        self.relations.addTopLevelItems([racine_r, racine_e])
        code_produit = list(dict.fromkeys(
            [r.identite.ref_piece] + [e.reference for e in r.equivalences if e.source == 'code_produit']))
        for rp in r.remplacements:
            fleche = f"{rp.ancienne} remplacée par {rp.nouvelle}"
            item = QTreeWidgetItem(racine_r, [fleche, STATUTS_REMPLACEMENT.get(rp.statut, rp.statut),
                                              rp.successeur_actuel or '', '', rp.raison])
            if rp.statut == 'conflit':
                item.setIcon(0, qta.icon('fa5s.question-circle', color='#b45309'))
                combo = QComboBox()
                combo.addItem("Réponse du lot", None)
                combo.addItem("Garder l'existant", 'garder')
                combo.addItem("Prendre la fiche", 'prendre')
                combo.setCurrentIndex(max(0, combo.findData(self.individuels.remplacements.get(rp.ancienne))))
                combo.currentIndexChanged.connect(
                    lambda _, a=rp.ancienne, w=combo: self._choix_remplacement(a, w.currentData()))
                self.relations.setItemWidget(item, 3, combo)
            elif rp.appariement == 'a_choisir' and len(code_produit) > 1:
                combo = QComboBox()
                for cible in code_produit:
                    combo.addItem(f"remplacée par {cible}", cible)
                combo.setCurrentIndex(max(0, code_produit.index(rp.nouvelle)
                                          if rp.nouvelle in code_produit else 0))
                combo.currentIndexChanged.connect(
                    lambda _, a=rp.ancienne, w=combo: self._choix_remplacement(a, w.currentData()))
                self.relations.setItemWidget(item, 3, combo)
        for e in r.equivalences:
            item = QTreeWidgetItem(racine_e, [f"équivalente : {e.reference}" + (f" (ligne {e.ligne})" if e.ligne else ''),
                                              STATUTS_EQUIVALENCE.get(e.statut, e.statut), '', '', e.raison])
            if e.statut == 'dans_la_succession':
                continue
            if not e.origine and e.statut != 'ecartee':
                item.setIcon(0, qta.icon('fa5s.question-circle', color='#b45309'))
            origine = QLineEdit(self.individuels.origines.get(e.reference, e.origine))
            origine.setPlaceholderText("marque d'origine")
            origine.editingFinished.connect(
                lambda ref=e.reference, w=origine, o=e.origine: self._choix_origine(ref, w.text(), o))
            self.relations.setItemWidget(item, 2, origine)
            if e.statut != 'ecartee':
                ecarter = QPushButton("Écarter")
                ecarter.setCheckable(True)
                ecarter.setChecked(e.reference in self.individuels.ecartees)
                ecarter.setToolTip("Référence erronée : elle n'est pas enregistrée et ne sera plus proposée.")
                ecarter.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
                ecarter.toggled.connect(lambda actif, ref=e.reference: self._ecarter(ref, actif))
                self.relations.setItemWidget(item, 3, ecarter)
        self.relations.expandAll()
        for col in range(4):
            self.relations.resizeColumnToContents(col)
        n = len(r.remplacements) + len(r.equivalences)
        self.onglets.setTabText(1, f"Anciennes références et équivalentes ({n})")

    def _remplir_informations(self):
        r = self.rapprochement
        morceaux = []
        if r.absents_de_la_fiche:
            morceaux.append(f"<h4>Appareils reliés dans l'outil (depuis le site) mais absents de cette "
                            f"fiche ({len(r.absents_de_la_fiche)})</h4>"
                            "<p>Pour information : rien n'est retiré.</p><ul>"
                            + ''.join(f"<li>{a.marque} {a.ref_modele}</li>"
                                      for a in r.absents_de_la_fiche[:300]) + "</ul>")
        lecture = [d for d in r.doutes_par_categorie().get('lecture', [])
                   if 'marque à déduire' not in d.message and 'marque_a_deduire' not in d.message]
        if lecture:
            morceaux.append(f"<h4>Passages de la fiche non compris ({len(lecture)})</h4><ul>"
                            + ''.join(f"<li>{d.message}</li>" for d in lecture) + "</ul>")
        self.informations.setHtml(''.join(morceaux) or "<p>Rien à signaler.</p>")
        self.onglets.setTabText(2, f"À savoir ({len(r.absents_de_la_fiche) + len(lecture)})"
                                if morceaux else "À savoir")

    # =========================================================================
    # Décisions
    # =========================================================================
    def _repondre(self, cle: str, valeur: Optional[str]):
        if self.questionnaire is None:
            return
        with self.db._query_lock:
            self.questionnaire.repondre(cle, valeur)
        if self.questionnaire.relire:
            self.etat.setText("Groupe de marques enregistré : relisez la fiche pour en tenir compte.")
            self.etat.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
        self._mettre_a_jour()

    def _tout_valider(self):
        """Accepte les propositions (les questions sans proposition restent ouvertes)."""
        if self.questionnaire is not None:
            with self.db._query_lock:
                self.questionnaire.accepter_propositions()
            self._mettre_a_jour()

    def _voir_lignes(self, cle: str):
        self.filtre_texte.clear()
        self.onglets.setCurrentIndex(0)
        lignes = [k for (i, k), c in self.questionnaire.lignes.items() if c == cle]
        if lignes:
            source = self.modele.index(lignes[0], 0)
            self.table.scrollTo(self.filtre.mapFromSource(source))
            self.table.selectRow(self.filtre.mapFromSource(source).row())

    def _apres_choix(self):
        with self.db._query_lock:
            self.questionnaire.construire()
        self._mettre_a_jour()

    def _choix_remplacement(self, ancienne: str, choix):
        if choix is None:
            self.individuels.remplacements.pop(ancienne, None)
        else:
            self.individuels.remplacements[ancienne] = choix
        self._apres_choix()

    def _choix_origine(self, ref: str, texte: str, proposee: str):
        texte = texte.strip()
        if texte and texte != proposee:
            self.individuels.origines[ref] = texte
        else:
            self.individuels.origines.pop(ref, None)
        self._apres_choix()

    def _ecarter(self, ref: str, actif: bool):
        (self.individuels.ecartees.add if actif else self.individuels.ecartees.discard)(ref)
        self._apres_choix()

    def _lignes_selectionnees(self) -> List[int]:
        lignes = {self.filtre.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted(lignes)

    def _ligne_selectionnee(self, *_):
        lignes = self._lignes_selectionnees()
        self.choix_appareil.blockSignals(True)
        self.choix_appareil.clear()
        if not lignes or self.rapprochement is None:
            self.choix_appareil.blockSignals(False)
            self._action_choisie()
            return
        a = self.rapprochement.appareils[lignes[0]]
        if a.proposition is not None or a.appareil_id is not None:
            self.choix_appareil.addItem("Réponse du lot (proposition)", ('proposition', None))
        else:
            self.choix_appareil.addItem("Réponse du lot", ('proposition', None))
        if len(lignes) == 1:
            for c in a.candidats:
                self.choix_appareil.addItem(f"Relier à {c.marque} {c.ref_modele} ({c.type or 'sans type'})",
                                            ('lier', c.id))
        self.choix_appareil.addItem("Créer l'appareil", ('creer', None))
        if a.lien == 'deja_couvert':
            self.choix_appareil.addItem("Relier directement à la pièce", ('rattacher', None))
        self.choix_appareil.addItem("Laisser de côté", ('ignorer', None))
        self.choix_appareil.blockSignals(False)
        marques = list(dict.fromkeys([m for m in (a.marque, a.marque_fiche) if m]
                                     + sorted({c.marque for c in a.candidats})))
        self.choix_marque.clear()
        self.choix_marque.addItems(marques + [m for m in self._marques if m not in marques])
        self.choix_marque.setCurrentText(a.marque or a.marque_fiche or '')
        self.choix_type.clear()
        self.choix_type.addItem('')
        self.choix_type.addItems(self._types)
        self.choix_type.setCurrentText(a.type)
        self._action_choisie()

    def _action_choisie(self, *_):
        """Marque et type ne servent qu'à la création : ils ne s'affichent qu'avec elle."""
        action = (self.choix_appareil.currentData() or ('', None))[0]
        for w in (self.libelle_marque, self.choix_marque, self.libelle_type, self.choix_type):
            w.setVisible(action == 'creer')

    def _appliquer_choix(self):
        action, valeur = self.choix_appareil.currentData() or ('proposition', None)
        marque = self.choix_marque.currentText().strip()
        type_ = self.choix_type.currentText().strip()
        for index in self._lignes_selectionnees():
            if action == 'proposition':
                self.individuels.appareils.pop(index, None)
                continue
            self.individuels.appareils[index] = ChoixAppareil(
                appareil_id=valeur if action == 'lier' else None,
                creer=action == 'creer', ignorer=action == 'ignorer',
                rattacher=action == 'rattacher',
                marque=marque if action == 'creer' else '', type=type_ if action == 'creer' else '')
        self._apres_choix()

    def _retour_proposition(self):
        for index in self._lignes_selectionnees():
            self.individuels.appareils.pop(index, None)
        self._apres_choix()

    def _filtrer(self, *_):
        self.filtre.categorie = self.filtre_categorie.currentData() or ''
        self.filtre.lien = self.filtre_lien.currentData() or ''
        self.filtre.provenance = self.filtre_provenance.currentData() or ''
        self.filtre.texte = self.filtre_texte.text().strip().lower()
        self.filtre.invalidateFilter()

    # =========================================================================
    # État et enregistrement
    # =========================================================================
    def _mettre_a_jour(self):
        if self.rapprochement is None or self.questionnaire is None:
            return
        plan_lot = self.lot.planifier()
        self.plan = plan_lot.plans[0][1] if plan_lot.plans else None
        self.panneau.afficher(self.questionnaire)
        self.modele.rafraichir()
        restantes = self.questionnaire.sans_reponse()
        self.bouton_tout.setEnabled(any(x.proposition is not None for x in restantes))
        pret = plan_lot.pret and self.plan is not None and self.plan.pret
        if pret:
            s = self.plan.resume()
            revoir = sum(len(v) for v in plan_lot.a_revoir.values())
            texte = (f"Prêt : {s['appareils_a_creer']} appareil(s) créé(s), {s['liens']} compatibilité(s), "
                     f"{s['remplacements']} ancienne(s) référence(s), {s['equivalences']} équivalente(s)."
                     if not self.plan.vide else
                     "Prêt : rien de nouveau à ajouter ; la fiche confirme ce que l'outil sait déjà.")
            if revoir:
                texte += f" {revoir} appareil(s) restent à choisir : ils ne sont pas enregistrés."
            self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        else:
            if restantes:
                texte = f"Il reste {len(restantes)} question(s) : " + " ; ".join(
                    x.titre[:60] for x in restantes[:2]) + (" ; …" if len(restantes) > 2 else '')
            elif self.plan is None:
                texte = "La pièce de la fiche est introuvable (ni code produit ni référence produit)."
            else:
                texte = "Avant d'enregistrer — " + " ; ".join(plan_lot.en_attente or self.plan.a_completer[:2])
            self.etat.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
        self.etat.setText(texte)
        # Fiche d'un lot : les choix reviennent au lot même si des questions restent
        self.bouton_enregistrer.setEnabled(pret or self.on_decide is not None)

    def _enregistrer(self):
        if self.rapprochement is not None and self.on_decide is not None:
            self.on_decide(self.individuels)
            self.close()
            return
        if self.rapprochement is None or self.plan is None or not self.plan.pret:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = self.service.enregistrer(self.plan)
        finally:
            QApplication.restoreOverrideCursor()
        if not res.ok:
            self.etat.setText(f"Enregistrement interrompu : {res.erreur}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        self.etat.setText(f"Enregistré : {res.resume()}.")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_enregistrer.setEnabled(False)
        if self.on_enregistre is not None:
            self.on_enregistre(self.plan.ref_piece, res)

    def closeEvent(self, event):
        # Téléchargement en cours : le thread survit à la fenêtre jusqu'à sa fin
        t = self._telechargement
        if t is not None:
            t.termine.disconnect()
            t.setParent(None)
            _EN_COURS.add(t)
            t.finished.connect(lambda: _EN_COURS.discard(t))
        super().closeEvent(event)


_EN_COURS = set()
