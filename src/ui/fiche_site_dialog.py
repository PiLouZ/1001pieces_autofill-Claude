"""
Fenêtre « Lire une fiche du site » : aperçu et enregistrement d'une fiche
(CDC docs/cdc_import_fiches_site.md, § 7.1, étape 3)

- Entrée : le lien de la page publique (téléchargée hors du thread principal)
  ou la description collée (HTML du back-office ou texte).
- Carte de la pièce : référence, statut, référence interne, id_product, EAN,
  libellé tiré du titre.
- Résumé par catégorie : chaque catégorie se valide en bloc, se laisse de côté
  ou reste en attente. « Enregistrer » ne s'active que lorsque plus rien n'est
  en attente ni à compléter.
- Détail des appareils : table virtuelle filtrable (catégorie, lien,
  provenance, texte). Le panneau sous la table applique un choix aux lignes
  sélectionnées : appareil parmi les candidats, création, rattachement direct,
  mise de côté, marque, type.
- Relations : remplacements (garder l'existant / prendre la fiche, autre cible)
  et équivalences (étiquette d'origine, écarter la référence).
- Pièce : choix sur les doutes d'identité (EAN, libellé, référence interne).
- Informations : liens absents de la fiche, ce que le lecteur n'a pas compris.

Mode « fiche d'un lot » (import en masse, étape 4) : `on_decide` fourni, la
fenêtre montre une fiche déjà rapprochée (`afficher(r, decisions)`), sans
lien ni collage ; « Reprendre dans le lot » rend les décisions au lot au lieu
d'écrire (l'écriture se fait avec tout le lot).

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

from typing import Callable, List, Optional

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
from src.utils.rapprochement_fiche import CATEGORIES_DOUTES, LIENS, NIVEAUX
from src.utils.rapprochement_fiche.decisions import (
    ATTENTE, CATEGORIES_RESUME, CHOIX_IDENTITE, DE_COTE, VALIDEE, ChoixAppareil, DecisionsFiche,
    categorie_appareil, categorie_equivalence, categorie_remplacement, elements_par_categorie,
    planifier,
)
from .style_manager import StyleManager

_ETATS = [(ATTENTE, "En attente"), (VALIDEE, "Validée en bloc"), (DE_COTE, "Laissée de côté")]
_PROVENANCES = {'description': "description", 'table': "table du site", 'les_deux': "les deux"}
_STATUTS_PIECE = {'reelle': "pièce réelle", 'fantome': "fantôme → deviendra réelle",
                  'absente': "absente → sera créée"}
_LIBELLES_CHOIX = {'site': "prendre l'EAN du site", 'outil': "garder l'EAN de l'outil",
                   'garder': "garder l'existant", 'prendre': "prendre la fiche",
                   'enregistrer': "enregistrer le produit avec cette réf.",
                   'ignorer': "ne pas enregistrer le produit"}
_COLONNES = ("N°", "Catégorie", "Niveau", "Lien", "Marque", "Réf. modèle", "Nom", "Type",
             "Provenance", "Choix", "Raison")


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
    """Lignes d'appareils du rapprochement, avec le choix courant de chacune."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.appareils = []
        self.decisions: Optional[DecisionsFiche] = None

    def charger(self, appareils, decisions):
        self.beginResetModel()
        self.appareils, self.decisions = appareils, decisions
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
        a = self.appareils[index]
        c = self.decisions.appareils.get(index) if self.decisions else None
        if c is None:
            etat = self.decisions.etat(categorie_appareil(a)) if self.decisions else ATTENTE
            return {VALIDEE: "proposition", DE_COTE: "de côté"}.get(etat, "en attente")
        if c.ignorer:
            return "de côté"
        if c.appareil_id is not None:
            choisi = next((x for x in a.candidats if x.id == c.appareil_id), None)
            return f"lier à {choisi.ref_modele if choisi else c.appareil_id}"
        if c.creer:
            return "créer"
        if c.rattacher:
            return "rattacher"
        return "marque/type choisis"

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        a = self.appareils[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return (a.numero or "table", CATEGORIES_RESUME[categorie_appareil(a)].split(' (')[0],
                    a.niveau, a.lien or "à décider", a.marque or a.marque_fiche or "?",
                    a.ref_modele, a.nom, a.type or "—", _PROVENANCES.get(a.provenance, a.provenance),
                    self.choix_texte(index.row()), a.raison)[col]
        if role == Qt.UserRole:
            return categorie_appareil(a)
        if role == Qt.UserRole + 1:
            return a.lien
        if role == Qt.UserRole + 2:
            return a.provenance
        if role == Qt.ToolTipRole and col == 2:
            return NIVEAUX.get(a.niveau, '')
        if role == Qt.ToolTipRole and col == 3:
            return LIENS.get(a.lien, '')
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
    """Aperçu complet d'une fiche du site, puis enregistrement après validation."""

    def __init__(self, db_manager, main_window=None, on_enregistre: Optional[Callable] = None,
                 service: Optional[EnregistrementFicheService] = None,
                 on_decide: Optional[Callable[[DecisionsFiche], None]] = None):
        super().__init__(main_window)
        self.on_decide = on_decide
        self.setWindowTitle("Fiche du lot" if on_decide else "Lire une fiche du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1180, 820)
        self.main_window = main_window
        self.on_enregistre = on_enregistre
        self.service = service or EnregistrementFicheService(db_manager, main_window)
        self.rapprochement = None
        self.decisions = DecisionsFiche()
        self._telechargement = None
        self._types: List[str] = []
        self._marques: List[str] = []
        self._construire()
        if on_decide is not None:
            for w in (self.champ_lien, self.bouton_lien, self.bouton_coller):
                w.setVisible(False)
            self.bouton_enregistrer.setText("Reprendre dans le lot")
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
        self.bouton_lien = QPushButton(qta.icon('fa5s.globe', color='#555555'), "Lire le lien")
        self.bouton_lien.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_lien.clicked.connect(self._lire_lien)
        self.bouton_coller = QPushButton(qta.icon('fa5s.paste', color='#555555'),
                                         "Coller une description")
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
        bouton = QPushButton("Lire la description")
        bouton.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        bouton.clicked.connect(self._lire_description)
        collage.addWidget(self.champ_description)
        collage.addWidget(bouton, 0, Qt.AlignRight)
        self.zone_collage.setVisible(False)
        racine.addWidget(self.zone_collage)

        self.carte = QLabel("Indiquez le lien d'une fiche ou collez sa description.")
        self.carte.setWordWrap(True)
        self.carte.setTextFormat(Qt.RichText)
        self.carte.setStyleSheet(StyleManager.CARTE_GRIS_CLAIR + " padding: 8px;")
        racine.addWidget(self.carte)

        separation = QSplitter(Qt.Vertical)
        separation.addWidget(self._construire_resume())
        separation.addWidget(self._construire_onglets())
        separation.setStretchFactor(0, 0)
        separation.setStretchFactor(1, 1)
        separation.setSizes([230, 520])
        racine.addWidget(separation, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        self.bouton_enregistrer = QPushButton(qta.icon('fa5s.save', color='white'), "Enregistrer")
        self.bouton_enregistrer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_enregistrer.setEnabled(False)
        self.bouton_enregistrer.clicked.connect(self._enregistrer)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        pied.addWidget(self.bouton_enregistrer)
        pied.addWidget(fermer)
        racine.addLayout(pied)

    def _construire_resume(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        disposition.setContentsMargins(0, 0, 0, 0)
        entete = QHBoxLayout()
        titre = QLabel("Résumé par catégorie")
        titre.setStyleSheet(StyleManager.TITRE_SECTION)
        self.bouton_tout = QPushButton(qta.icon('fa5s.check-double', color='#555555'),
                                       "Tout valider")
        self.bouton_tout.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self.bouton_tout.clicked.connect(self._tout_valider)
        entete.addWidget(titre)
        entete.addStretch(1)
        entete.addWidget(self.bouton_tout)
        disposition.addLayout(entete)
        self.resume = QTreeWidget()
        self.resume.setHeaderLabels(["Catégorie", "Éléments", "Décision", "Type commun"])
        self.resume.setRootIsDecorated(False)
        self.resume.setUniformRowHeights(True)
        self.resume.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.resume.itemDoubleClicked.connect(self._filtrer_sur_categorie)
        disposition.addWidget(self.resume)
        return boite

    def _construire_onglets(self) -> QWidget:
        self.onglets = QTabWidget()
        self.onglets.addTab(self._construire_appareils(), "Appareils")
        self.relations = QTreeWidget()
        self.relations.setHeaderLabels(["Relation", "Statut", "Origine / cible", "Décision", "Raison"])
        self.relations.setRootIsDecorated(True)
        self.relations.header().setSectionResizeMode(4, QHeaderView.Stretch)
        self.onglets.addTab(self.relations, "Relations")
        self.piece = QTreeWidget()
        self.piece.setHeaderLabels(["Doute", "Détail", "Décision"])
        self.piece.setRootIsDecorated(False)
        self.piece.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.onglets.addTab(self.piece, "Pièce")
        self.informations = QTextBrowser()
        self.onglets.addTab(self.informations, "Informations")
        return self.onglets

    def _construire_appareils(self) -> QWidget:
        boite = QWidget()
        disposition = QVBoxLayout(boite)
        filtres = QHBoxLayout()
        self.filtre_categorie = QComboBox()
        self.filtre_categorie.addItem("Toutes les catégories", '')
        for cle, libelle in CATEGORIES_RESUME.items():
            if cle not in ('relations', 'conflits'):
                self.filtre_categorie.addItem(libelle, cle)
        self.filtre_lien = QComboBox()
        self.filtre_lien.addItem("Tous les liens", '')
        for cle, libelle in LIENS.items():
            self.filtre_lien.addItem(libelle, cle)
        self.filtre_provenance = QComboBox()
        self.filtre_provenance.addItem("Toutes provenances", '')
        for cle, libelle in _PROVENANCES.items():
            self.filtre_provenance.addItem(libelle, cle)
        self.filtre_texte = QLineEdit()
        self.filtre_texte.setPlaceholderText("Filtrer (marque, réf., nom)")
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
        self.choix_marque = QComboBox()
        self.choix_marque.setEditable(True)
        self.choix_marque.setMinimumWidth(140)
        self.choix_type = QComboBox()
        self.choix_type.setEditable(True)
        self.choix_type.setMinimumWidth(140)
        appliquer = QPushButton("Appliquer")
        appliquer.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        appliquer.clicked.connect(self._appliquer_choix)
        retour = QPushButton("Revenir à la proposition")
        retour.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        retour.clicked.connect(self._retour_proposition)
        choix.addWidget(self.choix_appareil, 1)
        choix.addWidget(QLabel("Marque"))
        choix.addWidget(self.choix_marque)
        choix.addWidget(QLabel("Type"))
        choix.addWidget(self.choix_type)
        choix.addWidget(appliquer)
        choix.addWidget(retour)
        disposition.addLayout(choix)
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
        if not self._types:
            self._types = self.service.types_outil()
            self._marques = self.service.marques_outil()
        self.afficher(r)

    def afficher(self, r, decisions: Optional[DecisionsFiche] = None):
        if not self._types:
            self._types = self.service.types_outil()
            self._marques = self.service.marques_outil()
        self.rapprochement = r
        self.decisions = decisions if decisions is not None else DecisionsFiche()
        self.modele.charger(r.appareils, self.decisions)
        self.table.resizeColumnsToContents()
        self._remplir_carte()
        self._remplir_relations()
        self._remplir_piece()
        self._remplir_informations()
        self._mettre_a_jour()

    # =========================================================================
    # Remplissage
    # =========================================================================
    def _remplir_carte(self):
        i = self.rapprochement.identite
        lignes = [f"<b>Pièce {i.ref_piece or '?'}</b> — {_STATUTS_PIECE.get(i.statut, i.statut)}"
                  + (" (obsolète)" if i.obsolete else '')]
        if i.ref_interne:
            lignes.append(f"Référence interne : <b>{i.ref_interne}</b> ({i.statut_ref_interne or '—'})"
                          + (f" · id_product {i.id_product}" if i.id_product is not None else ''))
        if i.ean:
            etat = {'a_remplir': "à enregistrer", 'identique': "déjà connu",
                    'different': f"différent de {i.ean_outil}"}.get(i.statut_ean_outil, '')
            lignes.append(f"EAN : {i.ean} ({'valide' if i.statut_ean == 'valide' else 'clé fausse'}"
                          + (f", {etat}" if etat else '') + ")")
        if i.libelle:
            etat = {'a_remplir': "sera le libellé de la pièce", 'identique': "identique au libellé",
                    'different': f"libellé actuel : « {i.libelle_outil} »"}.get(i.statut_libelle, '')
            lignes.append(f"Titre : « {i.libelle} » — {etat}")
        if self.rapprochement.liste_tronquee:
            lignes.append("<i>Liste d'appareils probablement réduite : aucun absent n'en est tiré.</i>")
        self.carte.setText("<br>".join(lignes))

    def _remplir_resume(self):
        self.resume.clear()
        cats = elements_par_categorie(self.rapprochement)
        for cle, elements in cats.items():
            n = sum(len(v) for v in elements.values())
            item = QTreeWidgetItem([CATEGORIES_RESUME[cle], str(n), '', ''])
            item.setData(0, Qt.UserRole, cle)
            self.resume.addTopLevelItem(item)
            combo = QComboBox()
            for etat, libelle in _ETATS:
                combo.addItem(libelle, etat)
            combo.setCurrentIndex([e for e, _ in _ETATS].index(self.decisions.etat(cle)))
            combo.currentIndexChanged.connect(
                lambda _, c=cle, w=combo: self._changer_etat(c, w.currentData()))
            self.resume.setItemWidget(item, 2, combo)
            if cle == 'types_manquants':     # jamais sur les absents, déjà typés
                types = QComboBox()
                types.setEditable(True)
                types.addItem('')
                types.addItems(self._types)
                types.setCurrentText(self.decisions.type_par_categorie.get(cle, ''))
                types.currentTextChanged.connect(lambda t, c=cle: self._type_commun(c, t))
                self.resume.setItemWidget(item, 3, types)
        self.resume.resizeColumnToContents(1)
        self.resume.setColumnWidth(2, 170)

    def _remplir_relations(self):
        self.relations.clear()
        r = self.rapprochement
        racine_r = QTreeWidgetItem([f"Remplacements ({len(r.remplacements)})"])
        racine_e = QTreeWidgetItem([f"Équivalences ({len(r.equivalences)})"])
        self.relations.addTopLevelItems([racine_r, racine_e])
        code_produit = list(dict.fromkeys(
            [r.identite.ref_piece] + [e.reference for e in r.equivalences if e.source == 'code_produit']))
        for rp in r.remplacements:
            fleche = f"{rp.ancienne} → {rp.nouvelle}"
            item = QTreeWidgetItem(racine_r, [fleche, rp.statut, rp.successeur_actuel or '', '', rp.raison])
            if rp.statut == 'conflit':
                combo = QComboBox()
                combo.addItem(_LIBELLES_CHOIX['garder'], 'garder')
                combo.addItem(_LIBELLES_CHOIX['prendre'], 'prendre')
                combo.currentIndexChanged.connect(
                    lambda _, a=rp.ancienne, w=combo: self._choix_remplacement(a, w.currentData()))
                self.relations.setItemWidget(item, 3, combo)
            elif rp.appariement == 'a_choisir' and len(code_produit) > 1:
                combo = QComboBox()
                for cible in code_produit:
                    combo.addItem(f"vers {cible}", cible)
                combo.setCurrentIndex(max(0, code_produit.index(rp.nouvelle)
                                          if rp.nouvelle in code_produit else 0))
                combo.currentIndexChanged.connect(
                    lambda _, a=rp.ancienne, w=combo: self._choix_remplacement(a, w.currentData()))
                self.relations.setItemWidget(item, 3, combo)
        for e in r.equivalences:
            item = QTreeWidgetItem(racine_e, [f"≡ {e.reference}" + (f" (ligne {e.ligne})" if e.ligne else ''),
                                              e.statut, '', '', e.raison])
            if e.statut == 'dans_la_succession':
                continue
            origine = QLineEdit(e.origine)
            origine.setPlaceholderText("étiquette d'origine")
            origine.editingFinished.connect(
                lambda ref=e.reference, w=origine, o=e.origine: self._choix_origine(ref, w.text(), o))
            self.relations.setItemWidget(item, 2, origine)
            if e.statut != 'ecartee':
                ecarter = QPushButton("Écarter")
                ecarter.setCheckable(True)
                ecarter.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
                ecarter.toggled.connect(lambda actif, ref=e.reference: self._ecarter(ref, actif))
                self.relations.setItemWidget(item, 3, ecarter)
        self.relations.expandAll()
        for col in range(4):
            self.relations.resizeColumnToContents(col)

    def _remplir_piece(self):
        self.piece.clear()
        doutes = self.rapprochement.doutes_par_categorie()
        for categorie, liste in doutes.items():
            for d in (d for d in liste if d.element == 'identite'):
                item = QTreeWidgetItem([CATEGORIES_DOUTES.get(categorie, categorie), d.message, ''])
                self.piece.addTopLevelItem(item)
                if categorie in CHOIX_IDENTITE:
                    combo = QComboBox()
                    for choix in CHOIX_IDENTITE[categorie]:
                        combo.addItem(_LIBELLES_CHOIX.get(choix, choix), choix)
                    combo.currentIndexChanged.connect(
                        lambda _, c=categorie, w=combo: self._choix_identite(c, w.currentData()))
                    self.piece.setItemWidget(item, 2, combo)
        self.piece.resizeColumnToContents(0)

    def _remplir_informations(self):
        r = self.rapprochement
        morceaux = []
        if r.absents_de_la_fiche:
            morceaux.append(f"<h4>Liens du site absents de la fiche ({len(r.absents_de_la_fiche)})</h4>"
                            "<p>Pour information : rien n'est retiré.</p><ul>"
                            + ''.join(f"<li>{a.marque} {a.ref_modele}</li>"
                                      for a in r.absents_de_la_fiche[:300]) + "</ul>")
        lecture = r.doutes_par_categorie().get('lecture', [])
        if lecture:
            morceaux.append(f"<h4>Non compris à la lecture ({len(lecture)})</h4><ul>"
                            + ''.join(f"<li>{d.message}</li>" for d in lecture) + "</ul>")
        self.informations.setHtml(''.join(morceaux) or "<p>Rien à signaler.</p>")

    # =========================================================================
    # Décisions
    # =========================================================================
    def _changer_etat(self, categorie: str, etat: str):
        self.decisions.etats[categorie] = etat
        self._mettre_a_jour(resume=False)

    def _type_commun(self, categorie: str, type_: str):
        self.decisions.type_par_categorie[categorie] = type_.strip()
        self._mettre_a_jour(resume=False)

    def _tout_valider(self):
        if self.rapprochement is not None:
            self.decisions.valider_tout(self.rapprochement)
            self._mettre_a_jour()

    def _choix_remplacement(self, ancienne: str, choix: str):
        self.decisions.remplacements[ancienne] = choix
        self._mettre_a_jour(resume=False)

    def _choix_origine(self, ref: str, texte: str, proposee: str):
        texte = texte.strip()
        if texte and texte != proposee:
            self.decisions.origines[ref] = texte
        else:
            self.decisions.origines.pop(ref, None)
        self._mettre_a_jour(resume=False)

    def _ecarter(self, ref: str, actif: bool):
        (self.decisions.ecartees.add if actif else self.decisions.ecartees.discard)(ref)
        self._mettre_a_jour(resume=False)

    def _choix_identite(self, doute: str, choix: str):
        self.decisions.identite[doute] = choix
        self._mettre_a_jour(resume=False)

    def _lignes_selectionnees(self) -> List[int]:
        lignes = {self.filtre.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted(lignes)

    def _ligne_selectionnee(self, *_):
        lignes = self._lignes_selectionnees()
        self.choix_appareil.clear()
        if not lignes or self.rapprochement is None:
            return
        a = self.rapprochement.appareils[lignes[0]]
        self.choix_appareil.addItem("Proposition de l'aperçu", ('proposition', None))
        if len(lignes) == 1:
            for c in a.candidats:
                self.choix_appareil.addItem(f"Lier à {c.marque} {c.ref_modele} ({c.type or 'sans type'})",
                                            ('lier', c.id))
        self.choix_appareil.addItem("Créer l'appareil", ('creer', None))
        if a.lien == 'deja_couvert':
            self.choix_appareil.addItem("Rattacher directement à la pièce", ('rattacher', None))
        self.choix_appareil.addItem("Laisser de côté", ('ignorer', None))
        marques = list(dict.fromkeys([m for m in (a.marque, a.marque_fiche) if m]
                                     + sorted({c.marque for c in a.candidats})))
        self.choix_marque.clear()
        self.choix_marque.addItems(marques + [m for m in self._marques if m not in marques])
        self.choix_marque.setCurrentText(a.marque or a.marque_fiche or '')
        self.choix_type.clear()
        self.choix_type.addItem('')
        self.choix_type.addItems(self._types)
        self.choix_type.setCurrentText(a.type)

    def _appliquer_choix(self):
        action, valeur = self.choix_appareil.currentData() or ('proposition', None)
        marque = self.choix_marque.currentText().strip()
        type_ = self.choix_type.currentText().strip()
        for index in self._lignes_selectionnees():
            a = self.rapprochement.appareils[index]
            if action == 'proposition':
                choix = ChoixAppareil()
                if marque and marque != (a.marque or a.marque_fiche):
                    choix.marque = marque
                if type_ and type_ != a.type:
                    choix.type = type_
                if choix.marque or choix.type:
                    self.decisions.appareils[index] = choix
                else:
                    self.decisions.appareils.pop(index, None)
                continue
            self.decisions.appareils[index] = ChoixAppareil(
                appareil_id=valeur if action == 'lier' else None,
                creer=action == 'creer', ignorer=action == 'ignorer',
                rattacher=action == 'rattacher', marque=marque, type=type_)
        self._mettre_a_jour(resume=False)

    def _retour_proposition(self):
        for index in self._lignes_selectionnees():
            self.decisions.appareils.pop(index, None)
        self._mettre_a_jour(resume=False)

    def _filtrer_sur_categorie(self, item, _colonne=0):
        cle = item.data(0, Qt.UserRole)
        i = self.filtre_categorie.findData(cle)
        if i >= 0:
            self.filtre_categorie.setCurrentIndex(i)
            self.onglets.setCurrentIndex(0)

    def _filtrer(self, *_):
        self.filtre.categorie = self.filtre_categorie.currentData() or ''
        self.filtre.lien = self.filtre_lien.currentData() or ''
        self.filtre.provenance = self.filtre_provenance.currentData() or ''
        self.filtre.texte = self.filtre_texte.text().strip().lower()
        self.filtre.invalidateFilter()

    # =========================================================================
    # État et enregistrement
    # =========================================================================
    def _mettre_a_jour(self, resume: bool = True):
        if self.rapprochement is None:
            return
        if resume:
            self._remplir_resume()
        self.modele.rafraichir()
        self.plan = planifier(self.rapprochement, self.decisions)
        p = self.plan
        if p.pret:
            s = p.resume()
            texte = (f"Prêt : {s['appareils_a_creer']} appareil(s) à créer, {s['liens']} lien(s), "
                     f"{s['remplacements']} remplacement(s), {s['equivalences']} équivalence(s)."
                     if not p.vide else
                     f"Prêt : aucun appareil ni relation à ajouter ; {s['liens']} lien(s) "
                     f"confirmé(s) par la fiche (provenance complétée).")
            self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        else:
            raisons = []
            if p.en_attente:
                raisons.append("en attente : " + ", ".join(c.split(' (')[0] for c in p.en_attente))
            if p.a_completer:
                raisons.append(f"{len(p.a_completer)} ligne(s) à compléter ({p.a_completer[0]}…)")
            texte = "Avant d'enregistrer — " + " ; ".join(raisons)
            self.etat.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
        self.etat.setText(texte)
        # Fiche d'un lot : les décisions reviennent au lot même incomplètes (le lot
        # signale alors la fiche « à compléter »)
        self.bouton_enregistrer.setEnabled(p.pret or self.on_decide is not None)

    def _enregistrer(self):
        if self.rapprochement is not None and self.on_decide is not None:
            self.on_decide(self.decisions)
            self.close()
            return
        if self.rapprochement is None or not self.plan.pret:
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
