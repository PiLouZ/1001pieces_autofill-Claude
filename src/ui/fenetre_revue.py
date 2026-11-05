"""Gabarit commun des fenêtres de revue humaine (v3.94.0).

Partagé par « Valider les suggestions » et « Auto-complétés à vérifier » :

- chaque ligne porte un état à trois valeurs — ✓ validée, ✗ refusée, · en attente —
  au lieu d'une case qui confondait « non » et « pas encore regardé » ;
- les lignes sont regroupées (par preuve, par import…) ; un état appliqué à une
  ligne de groupe vaut pour toutes ses lignes visibles ;
- des puces à compteur filtrent par catégorie, un champ filtre par texte ;
- un panneau de détail montre la preuve de la ligne courante, lue paresseusement
  (callable `preuves`, une lecture par ligne consultée, mise en cache) ;
- « Appliquer » ne ferme pas la fenêtre : les lignes décidées disparaissent et l'on
  poursuit en plusieurs passes. Fermer avec des décisions en cours demande
  confirmation.

Raccourcis (arbre actif) : V valider, R refuser, U remettre en attente, Espace
bascule ✓/·, Entrée corriger, Cmd+Entrée appliquer. Après une décision sur une
seule ligne, la ligne en attente suivante devient courante.

Non bloquant : show() + callbacks (jamais exec_(), cf. conventions projet).
"""

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QColor, QBrush, QKeySequence
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QTreeWidget, QHeaderView, QMenu, QShortcut, QApplication, QAbstractItemView,
    QSplitter, QTextBrowser, QToolButton, QButtonGroup, QMessageBox,
    QTreeWidgetItemIterator,
)
import qtawesome as qta

from src.core.config import pluralize
from .style_manager import StyleManager
from .tri_colonnes import ItemTriable, ROLE_TRI, activer_tri, TriSuspendu

# ── États ────────────────────────────────────────────────────────────────────
VALIDE, REFUSE, ATTENTE = 'valide', 'refuse', 'attente'
_GLYPHE = {VALIDE: ("✓", "#198754", "Validée"),
           REFUSE: ("✗", "#dc3545", "Refusée"),
           ATTENTE: ("·", "#9e9e9e", "En attente")}
_ORDRE_ETAT = {ATTENTE: 0, VALIDE: 1, REFUSE: 2}
# Clic sur la colonne d'état : · → ✓ → ✗ → ·
_SUIVANT = {ATTENTE: VALIDE, VALIDE: REFUSE, REFUSE: ATTENTE}

COL_ETAT = 0

ROLE_FEUILLE = Qt.UserRole + 30
ROLE_ETAT = Qt.UserRole + 31
ROLE_ETAT_INITIAL = Qt.UserRole + 32
ROLE_ENTREE = Qt.UserRole + 33
ROLE_LIBELLE = Qt.UserRole + 34
ROLE_MODIFIEE = Qt.UserRole + 35

_STYLE_PUCE = (
    "QToolButton { background: #f1f3f5; color: #343a40; border: 1px solid #dee2e6;"
    " border-radius: 10px; padding: 2px 10px; font-size: 11px; }"
    "QToolButton:hover { background: #e9ecef; }"
    "QToolButton:checked { background: #0d6efd; color: white; border-color: #0d6efd; }"
)

_AIDE_RACCOURCIS = (
    "<b>Raccourcis</b> (liste active)<br>"
    "V : valider · R : refuser · U : remettre en attente<br>"
    "Espace : basculer ✓ / ·<br>"
    "Entrée ou double-clic : corriger la valeur<br>"
    "⌘ Entrée : appliquer les décisions<br><br>"
    "Sur une ligne de groupe, la décision vaut pour tout le groupe affiché. "
    "Un clic sur la colonne d'état fait tourner · → ✓ → ✗."
)


class _Porteur:
    """Enveloppe d'une entrée : PyQt garde l'objet par référence, là où un dict
    rangé tel quel dans un item serait copié (identité perdue d'un appel à l'autre)."""
    __slots__ = ('entree',)

    def __init__(self, entree):
        self.entree = entree


def entree(item):
    """Entrée (dict) portée par une feuille, None pour une ligne de groupe."""
    porteur = item.data(COL_ETAT, ROLE_ENTREE) if item is not None else None
    return porteur.entree if isinstance(porteur, _Porteur) else None


def html(texte) -> str:
    """Échappement HTML minimal pour le panneau de détail."""
    return (str(texte or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def verdict_pieces(valeur, preuves, champ='type', part_min=0.6, appareils_min=None):
    """Ce que disent les pièces d'un appareil d'une valeur de Type ou de Marque.

    preuves : {'nb_pieces', 'paires': [(type, marque, nb d'appareils)]} — vote des
    appareils qui partagent ses pièces (DatabaseManager.voter_par_pieces).

    appareils_min : effectif sous lequel on ne tranche pas (par défaut le seuil
    du palier « type de la pièce », Config.TYPE_PIECE_APPAREILS_MIN).

    Returns:
        (verdict, valeur majoritaire, part, total) — verdict 'confirme',
        'contredit' ou None (aucun vote, trop peu d'appareils, ou vote trop
        partagé pour trancher).
    """
    if appareils_min is None:
        from src.core.config import Config
        appareils_min = Config.TYPE_PIECE_APPAREILS_MIN
    indice = 0 if champ == 'type' else 1
    compte = {}
    for paire in (preuves or {}).get('paires') or []:
        v = (paire[indice] or '').strip()
        if v:
            compte[v] = compte.get(v, 0) + paire[2]
    total = sum(compte.values())
    if not total:
        return (None, None, 0.0, 0)
    top, n = max(compte.items(), key=lambda kv: kv[1])
    part = n / total
    valeur = (valeur or '').strip().lower()
    if not valeur or part < part_min or total < appareils_min:
        return (None, top, part, total)
    return ('confirme' if top.lower() == valeur else 'contredit', top, part, total)


def phrase_abstention(part, total, appareils_min=None) -> str:
    """Pourquoi le vote des pièces ne tranche pas."""
    if appareils_min is None:
        from src.core.config import Config
        appareils_min = Config.TYPE_PIECE_APPAREILS_MIN
    if total < appareils_min:
        return f"trop peu d'appareils typés pour trancher ({total})"
    return "vote trop partagé pour trancher"


def lignes_vote(preuves, limite=4) -> str:
    """« Four / Bosch (12), … » : les paires votantes, sans les appareils vides."""
    paires = [(t, m, n) for t, m, n in (preuves or {}).get('paires') or [] if t or m]
    return ", ".join(f"{html(t) or '?'} / {html(m) or '?'} ({n})" for t, m, n in paires[:limite])


class FenetreRevue(QDialog):
    """Fenêtre de revue : à spécialiser (cf. les méthodes « À fournir »)."""

    TITRE = ""
    ENTETES = []            # sans la colonne d'état
    LARGEURS = {}           # {colonne: largeur}
    COL_ETIREE = 1
    MODES_GROUPE = []       # [(clé, libellé)] ; le premier est le mode par défaut
    LIBELLE_APPLIQUER = "Appliquer"
    NOM_LIGNE = 'ligne'     # pour pluralize : « 3 lignes »

    def __init__(self, parent, entrees, preuves=None):
        super().__init__(parent)
        self._entrees = list(entrees or [])
        self._preuves = preuves
        self._cache_preuves = {}
        self._feuilles = []
        self._puce = 'toutes'
        self._fermeture_confirmee = False
        self._en_remplissage = False

        self.setWindowTitle(self.TITRE)
        self.resize(1200, 680)
        self.setMinimumSize(820, 440)
        self._construire()
        self._peupler()

    # ── À fournir par la spécialisation ─────────────────────────────────────
    def _etat_initial(self, entree):
        return ATTENTE

    def _remplir_feuille(self, item, entree):
        raise NotImplementedError

    def _cle_groupe(self, entree, mode):
        """(ordre, libellé) du groupe de l'entrée, ou None pour « Aucun »."""
        return None

    def _puces(self):
        """[(clé, libellé, prédicat(entree) -> bool)], hors « Toutes »."""
        return []

    def _texte_recherche(self, item) -> str:
        return " ".join(item.text(c) for c in range(1, item.columnCount()))

    def _html_detail(self, item, preuves) -> str:
        return ""

    def _cle_preuves(self, entree):
        """Clé de cache des preuves paresseuses (None : pas de lecture)."""
        return None

    def _corriger(self, item, colonne=None):
        """Correction de la ligne (Entrée, double-clic). Ouvre un sélecteur non
        bloquant ; la sous-classe appelle _apres_correction(item) une fois la
        valeur posée (jamais de retour synchrone : pas d'exec_)."""

    def _appliquer(self, valides, refuses):
        """Remet les décisions à la fenêtre principale (listes d'items)."""

    def _on_lien(self, cible, item):
        """Lien cliqué dans le panneau de détail (« prendre:2 »…)."""

    # ── Construction ─────────────────────────────────────────────────────────
    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setSpacing(8)

        tete = QHBoxLayout()
        self._titre = QLabel()
        self._titre.setStyleSheet("font-size: 15px; font-weight: bold; color: #212529;")
        tete.addWidget(self._titre)
        tete.addStretch()
        aide = QToolButton()
        aide.setIcon(qta.icon('fa5s.keyboard', color='#6c757d'))
        aide.setAutoRaise(True)
        aide.setToolTip(_AIDE_RACCOURCIS)
        tete.addWidget(aide)
        racine.addLayout(tete)

        filtres = QHBoxLayout()
        filtres.setSpacing(6)
        self._groupe_puces = QButtonGroup(self)
        self._groupe_puces.setExclusive(True)
        self._boutons_puces = {}
        for cle, libelle, _ in [('toutes', "Toutes", None)] + self._puces():
            bouton = QToolButton()
            bouton.setCheckable(True)
            bouton.setStyleSheet(_STYLE_PUCE)
            bouton.setProperty('libelle', libelle)
            bouton.clicked.connect(lambda _=False, c=cle: self._choisir_puce(c))
            self._groupe_puces.addButton(bouton)
            self._boutons_puces[cle] = bouton
            filtres.addWidget(bouton)
        self._boutons_puces['toutes'].setChecked(True)
        filtres.addStretch()
        filtres.addWidget(QLabel("Regrouper par"))
        self._combo_groupe = QComboBox()
        for cle, libelle in self.MODES_GROUPE:
            self._combo_groupe.addItem(libelle, cle)
        self._combo_groupe.currentIndexChanged.connect(lambda _: self._peupler())
        filtres.addWidget(self._combo_groupe)
        self._filtre = QLineEdit()
        self._filtre.setPlaceholderText("Filtrer…")
        self._filtre.setClearButtonEnabled(True)
        self._filtre.addAction(qta.icon('fa5s.search', color='#888'), QLineEdit.LeadingPosition)
        self._filtre.setFixedWidth(220)
        self._filtre.textChanged.connect(lambda _: self._appliquer_filtres())
        filtres.addWidget(self._filtre)
        racine.addLayout(filtres)

        self._separateur = QSplitter(Qt.Horizontal)
        self._arbre = QTreeWidget()
        self._arbre.setColumnCount(len(self.ENTETES) + 1)
        self._arbre.setHeaderLabels([""] + list(self.ENTETES))
        self._arbre.setAlternatingRowColors(True)
        self._arbre.setUniformRowHeights(True)
        self._arbre.setIndentation(14)
        # Flèches et retrait sur la 1ʳᵉ colonne de texte : la colonne d'état reste
        # une colonne nette, alignée d'une ligne à l'autre
        self._arbre.setTreePosition(1)
        self._arbre.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._arbre.itemClicked.connect(self._on_clic)
        self._arbre.itemDoubleClicked.connect(self._on_double_clic)
        self._arbre.currentItemChanged.connect(lambda cur, _prev: self._maj_detail(cur))
        self._arbre.setContextMenuPolicy(Qt.CustomContextMenu)
        self._arbre.customContextMenuRequested.connect(self._on_menu)
        self._arbre.installEventFilter(self)
        copie = QShortcut(QKeySequence.Copy, self._arbre)
        copie.setContext(Qt.WidgetShortcut)
        copie.activated.connect(self._copier_references)
        entete = self._arbre.header()
        entete.setStretchLastSection(False)
        entete.setSectionResizeMode(self.COL_ETIREE, QHeaderView.Stretch)
        self._arbre.setColumnWidth(COL_ETAT, 34)
        for colonne, largeur in self.LARGEURS.items():
            self._arbre.setColumnWidth(colonne, largeur)
        activer_tri(self._arbre)
        self._separateur.addWidget(self._arbre)

        self._detail = QTextBrowser()
        self._detail.setOpenLinks(False)
        self._detail.anchorClicked.connect(
            lambda url: self._on_lien(url.toString(), self._arbre.currentItem()))
        self._detail.setStyleSheet(
            "QTextBrowser { background: #f8f9fa; border: 1px solid #dee2e6;"
            " border-radius: 4px; padding: 6px; font-size: 12px; }")
        self._detail.setMinimumWidth(260)
        self._separateur.addWidget(self._detail)
        self._separateur.setStretchFactor(0, 3)
        self._separateur.setStretchFactor(1, 1)
        self._separateur.setSizes([860, 320])
        racine.addWidget(self._separateur, 1)

        actions = QHBoxLayout()
        self._btn_valider = self._bouton_action("Valider", 'fa5s.check', '#198754',
                                                "Valider la sélection (V)", VALIDE)
        self._btn_refuser = self._bouton_action("Refuser", 'fa5s.times', '#dc3545',
                                                "Refuser la sélection (R)", REFUSE)
        self._btn_attente = self._bouton_action("En attente", 'fa5s.minus', '#6c757d',
                                                "Remettre la sélection en attente (U)", ATTENTE)
        for bouton in (self._btn_valider, self._btn_refuser, self._btn_attente):
            actions.addWidget(bouton)
        self._btn_corriger = QPushButton("Corriger")
        self._btn_corriger.setIcon(qta.icon('fa5s.pen', color='#495057'))
        self._btn_corriger.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        self._btn_corriger.setToolTip("Corriger la valeur de la ligne courante (Entrée)")
        self._btn_corriger.setAutoDefault(False)
        self._btn_corriger.clicked.connect(lambda: self._corriger_courante())
        actions.addWidget(self._btn_corriger)
        actions.addStretch()
        self._resume = QLabel()
        self._resume.setStyleSheet("color: #495057;")
        actions.addWidget(self._resume)
        actions.addSpacing(12)
        fermer = QPushButton("Fermer")
        fermer.setAutoDefault(False)
        fermer.clicked.connect(self.reject)
        actions.addWidget(fermer)
        self._btn_appliquer = QPushButton()
        self._btn_appliquer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self._btn_appliquer.setAutoDefault(False)
        self._btn_appliquer.setToolTip("Appliquer les décisions sans fermer la fenêtre (⌘ Entrée)")
        self._btn_appliquer.clicked.connect(self._on_appliquer)
        actions.addWidget(self._btn_appliquer)
        racine.addLayout(actions)

        appliquer = QShortcut(QKeySequence("Ctrl+Return"), self)
        appliquer.activated.connect(self._on_appliquer)

    def _bouton_action(self, texte, icone, couleur, aide, etat):
        bouton = QPushButton(texte)
        bouton.setIcon(qta.icon(icone, color=couleur))
        bouton.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        bouton.setToolTip(aide)
        bouton.setAutoDefault(False)
        bouton.clicked.connect(lambda: self.decider(etat))
        return bouton

    # ── Remplissage ──────────────────────────────────────────────────────────
    def _mode_groupe(self):
        return self._combo_groupe.currentData() if self.MODES_GROUPE else None

    def _peupler(self):
        """(Re)construit l'arbre en conservant les états et corrections en cours."""
        # Relevé AVANT clear() : les items Qt sont détruits avec l'arbre
        etats = {id(entree(it)): (self.etat(it), bool(it.data(COL_ETAT, ROLE_MODIFIEE)),
                                  self._memoriser_correction(it))
                 for it in self._feuilles}
        courante = self._arbre.currentItem()
        entree_courante = entree(courante)
        self._en_remplissage = True
        with TriSuspendu(self._arbre):
            self._arbre.clear()
            self._feuilles = []
            mode = self._mode_groupe()
            groupes = {}
            for donnees in self._entrees:
                cle = self._cle_groupe(donnees, mode)
                groupes.setdefault(cle, []).append(donnees)
            for cle in sorted(groupes, key=lambda c: (c is not None, c or (0, ''))):
                parent = self._arbre.invisibleRootItem()
                if cle is not None:
                    parent = ItemTriable(self._arbre)
                    parent.setData(COL_ETAT, ROLE_FEUILLE, False)
                    parent.setData(COL_ETAT, ROLE_LIBELLE, cle[1])
                    # Titre sur toute la largeur de la ligne : jamais tronqué par une
                    # colonne étroite (double-clic pour replier)
                    parent.setFirstColumnSpanned(True)
                    for col in (COL_ETAT, 1):
                        parent.setData(col, ROLE_TRI, cle[0])
                    police = parent.font(COL_ETAT)
                    police.setBold(True)
                    parent.setFont(COL_ETAT, police)
                    parent.setBackground(COL_ETAT, QBrush(QColor("#eef1f4")))
                    parent.setExpanded(True)
                for donnees in groupes[cle]:
                    item = ItemTriable(parent)
                    item.setData(COL_ETAT, ROLE_FEUILLE, True)
                    item.setData(COL_ETAT, ROLE_ENTREE, _Porteur(donnees))
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self._remplir_feuille(item, donnees)
                    ancien = etats.get(id(donnees))
                    initial = self._etat_initial(donnees)
                    item.setData(COL_ETAT, ROLE_ETAT_INITIAL, initial)
                    self._poser_etat(item, ancien[0] if ancien else initial)
                    if ancien is not None:
                        item.setData(COL_ETAT, ROLE_MODIFIEE, ancien[1])
                        if ancien[2] is not None:
                            self._reprendre_correction(ancien[2], item)
                    self._feuilles.append(item)
                if cle is not None:
                    parent.setExpanded(True)
        self._en_remplissage = False
        self._appliquer_filtres()
        cible = next((it for it in self._feuilles
                      if entree_courante is not None
                      and entree(it) is entree_courante), None)
        cible = cible or self._prochaine(None)
        if cible is not None:
            self._arbre.setCurrentItem(cible)
        else:
            self._maj_detail(None)

    def _memoriser_correction(self, item):
        """Correction en cours d'une ligne, relevée avant un regroupement
        (spécialisable ; None : rien à reprendre)."""
        return None

    def _reprendre_correction(self, memo, item):
        """Réapplique une correction relevée par _memoriser_correction."""

    # ── États ────────────────────────────────────────────────────────────────
    @staticmethod
    def etat(item):
        return item.data(COL_ETAT, ROLE_ETAT)

    def _poser_etat(self, item, etat):
        glyphe, couleur, libelle = _GLYPHE[etat]
        item.setData(COL_ETAT, ROLE_ETAT, etat)
        item.setText(COL_ETAT, glyphe)
        item.setForeground(COL_ETAT, QBrush(QColor(couleur)))
        item.setTextAlignment(COL_ETAT, Qt.AlignCenter)
        police = item.font(COL_ETAT)
        police.setBold(True)
        police.setPointSize(max(police.pointSize(), 13))
        item.setFont(COL_ETAT, police)
        item.setToolTip(COL_ETAT, libelle)
        item.setData(COL_ETAT, ROLE_TRI, _ORDRE_ETAT[etat])

    def _cibles(self):
        """Feuilles visées : sélection (une ligne de groupe vaut ses lignes visibles),
        à défaut la ligne courante."""
        items = self._arbre.selectedItems() or (
            [self._arbre.currentItem()] if self._arbre.currentItem() else [])
        vues, cibles = set(), []
        for item in items:
            membres = [item] if item.data(COL_ETAT, ROLE_FEUILLE) else [
                item.child(i) for i in range(item.childCount())]
            for membre in membres:
                if not membre.isHidden() and id(membre) not in vues:
                    vues.add(id(membre))
                    cibles.append(membre)
        return cibles

    def decider(self, etat, cibles=None):
        """Pose l'état sur les cibles (sélection par défaut) ; sur une seule ligne,
        passe à la ligne en attente suivante."""
        cibles = self._cibles() if cibles is None else cibles
        if not cibles:
            return
        for item in cibles:
            self._poser_etat(item, etat)
        courante = self._arbre.currentItem()
        if (len(cibles) == 1 and courante is cibles[0] and etat != ATTENTE):
            suivante = self._prochaine(courante)
            if suivante is not None:
                self._arbre.setCurrentItem(suivante)
        self._maj_compteurs()

    def _feuilles_visibles(self):
        it = QTreeWidgetItemIterator(self._arbre)
        while it.value():
            item = it.value()
            if item.data(COL_ETAT, ROLE_FEUILLE) and not item.isHidden() \
                    and not (item.parent() and item.parent().isHidden()):
                yield item
            it += 1

    def _prochaine(self, depuis):
        """Première ligne en attente visible après `depuis` (bouclage), sinon la
        ligne visible suivante, sinon None."""
        visibles = list(self._feuilles_visibles())
        if not visibles:
            return None
        debut = visibles.index(depuis) + 1 if depuis in visibles else 0
        ordre = visibles[debut:] + visibles[:debut]
        attente = next((it for it in ordre if self.etat(it) == ATTENTE), None)
        if attente is not None:
            return attente
        return visibles[debut] if debut < len(visibles) else None

    # ── Événements ───────────────────────────────────────────────────────────
    def eventFilter(self, objet, event):
        if objet is self._arbre and event.type() == QEvent.KeyPress:
            touche, mods = event.key(), event.modifiers() & ~Qt.KeypadModifier
            if touche in (Qt.Key_Return, Qt.Key_Enter):
                if mods & Qt.ControlModifier:
                    self._on_appliquer()
                else:
                    self._corriger_courante()
                return True
            if mods:
                return False
            if touche == Qt.Key_V:
                self.decider(VALIDE)
                return True
            if touche == Qt.Key_R:
                self.decider(REFUSE)
                return True
            if touche == Qt.Key_U:
                self.decider(ATTENTE)
                return True
            if touche == Qt.Key_Space:
                cibles = self._cibles()
                if cibles:
                    tous_valides = all(self.etat(it) == VALIDE for it in cibles)
                    self.decider(ATTENTE if tous_valides else VALIDE, cibles)
                return True
        return super().eventFilter(objet, event)

    def _on_clic(self, item, colonne):
        if colonne == COL_ETAT and item.data(COL_ETAT, ROLE_FEUILLE):
            self._poser_etat(item, _SUIVANT[self.etat(item)])
            self._maj_compteurs()

    def _on_double_clic(self, item, colonne):
        if item.data(COL_ETAT, ROLE_FEUILLE) and colonne != COL_ETAT:
            self._corriger(item, colonne)

    def _corriger_courante(self):
        item = self._arbre.currentItem()
        if item is not None and item.data(COL_ETAT, ROLE_FEUILLE):
            self._corriger(item, None)

    def _apres_correction(self, item):
        """Une ligne corrigée est validée (le geste de correction vaut décision)."""
        item.setData(COL_ETAT, ROLE_MODIFIEE, True)
        self._poser_etat(item, VALIDE)
        self._maj_compteurs()
        self._maj_detail(item)

    def _choisir_puce(self, cle):
        self._puce = cle
        self._appliquer_filtres()

    def _appliquer_filtres(self):
        texte = self._filtre.text().strip().lower()
        predicats = {cle: pred for cle, _, pred in self._puces()}
        predicat = predicats.get(self._puce)
        for item in self._feuilles:
            cache = (bool(texte) and texte not in self._texte_recherche(item).lower()) or \
                    (predicat is not None and not predicat(entree(item)))
            item.setHidden(cache)
        racine = self._arbre.invisibleRootItem()
        for i in range(racine.childCount()):
            groupe = racine.child(i)
            if not groupe.data(COL_ETAT, ROLE_FEUILLE):
                groupe.setHidden(all(groupe.child(j).isHidden()
                                     for j in range(groupe.childCount())))
        self._maj_compteurs()

    def _on_menu(self, position):
        references = self._references_selectionnees()
        if not references:
            return
        menu = QMenu(self)
        menu.addAction(f"Copier {pluralize(len(references), 'référence')}",
                       self._copier_references)
        menu.exec_(self._arbre.viewport().mapToGlobal(position))

    def _reference(self, item) -> str:
        """Référence copiée pour une feuille (spécialisable)."""
        return item.text(1)

    def _references_selectionnees(self):
        return [r for r in (self._reference(it) for it in self._cibles()) if r]

    def _copier_references(self):
        references = self._references_selectionnees()
        if references:
            QApplication.clipboard().setText("\n".join(references))

    # ── Compteurs et détail ──────────────────────────────────────────────────
    def _maj_compteurs(self):
        compte = {VALIDE: 0, REFUSE: 0, ATTENTE: 0}
        for item in self._feuilles:
            compte[self.etat(item)] += 1
        total = len(self._feuilles)
        self._titre.setText(f"{self.TITRE} — {pluralize(total, self.NOM_LIGNE)}")
        self._resume.setText(f"<span style='color:#198754'>✓ {compte[VALIDE]}</span> · "
                             f"<span style='color:#dc3545'>✗ {compte[REFUSE]}</span> · "
                             f"<span style='color:#6c757d'>· {compte[ATTENTE]}</span>")
        self._resume.setToolTip(f"{compte[VALIDE]} validée(s), {compte[REFUSE]} refusée(s), "
                                f"{compte[ATTENTE]} en attente")
        decisions = compte[VALIDE] + compte[REFUSE]
        self._btn_appliquer.setText(f"{self.LIBELLE_APPLIQUER} ({decisions})")
        self._btn_appliquer.setEnabled(decisions > 0)
        for cle, libelle, predicat in [('toutes', "Toutes", None)] + self._puces():
            n = total if predicat is None else sum(
                1 for it in self._feuilles if predicat(entree(it)))
            bouton = self._boutons_puces[cle]
            bouton.setText(f"{libelle}  {n}")
            bouton.setVisible(cle == 'toutes' or n > 0 or self._puce == cle)
        self._maj_groupes()

    def _maj_groupes(self):
        racine = self._arbre.invisibleRootItem()
        for i in range(racine.childCount()):
            groupe = racine.child(i)
            if groupe.data(COL_ETAT, ROLE_FEUILLE):
                continue
            enfants = [groupe.child(j) for j in range(groupe.childCount())]
            n_v = sum(1 for e in enfants if self.etat(e) == VALIDE)
            n_r = sum(1 for e in enfants if self.etat(e) == REFUSE)
            groupe.setText(COL_ETAT, f"{groupe.data(COL_ETAT, ROLE_LIBELLE)} — {len(enfants)}")
            groupe.setToolTip(COL_ETAT, f"{n_v} validée(s), {n_r} refusée(s), "
                                 f"{len(enfants) - n_v - n_r} en attente")

    def _maj_detail(self, item):
        if item is None:
            self._detail.setHtml("<p style='color:#6c757d'>Aucune ligne.</p>")
            return
        if not item.data(COL_ETAT, ROLE_FEUILLE):
            self._detail.setHtml(
                f"<h3>{html(item.data(COL_ETAT, ROLE_LIBELLE))}</h3>"
                f"<p>{pluralize(item.childCount(), self.NOM_LIGNE)}. "
                f"V / R appliquent la décision à tout le groupe affiché.</p>")
            return
        self._detail.setHtml(self._html_detail(item, self.preuves_de(item)))

    def preuves_de(self, item):
        """Preuves paresseuses de la ligne (une lecture, puis cache)."""
        if self._preuves is None:
            return None
        donnees = entree(item)
        cle = self._cle_preuves(donnees)
        if cle is None:
            return None
        if cle not in self._cache_preuves:
            try:
                self._cache_preuves[cle] = self._preuves(donnees)
            except Exception:
                self._cache_preuves[cle] = None
        return self._cache_preuves[cle]

    # ── Application et fermeture ─────────────────────────────────────────────
    def _decisions_en_cours(self):
        return any(self.etat(it) != it.data(COL_ETAT, ROLE_ETAT_INITIAL)
                   or it.data(COL_ETAT, ROLE_MODIFIEE) for it in self._feuilles)

    def _on_appliquer(self):
        valides = [it for it in self._feuilles if self.etat(it) == VALIDE]
        refuses = [it for it in self._feuilles if self.etat(it) == REFUSE]
        if not valides and not refuses:
            return
        self._appliquer(valides, refuses)
        decidees = {id(entree(it)) for it in valides + refuses}
        self._entrees = [e for e in self._entrees if id(e) not in decidees]
        if not self._entrees:
            self._fermeture_confirmee = True
            self.accept()
            return
        self._peupler()

    def reject(self):
        if self._fermeture_confirmee or not self._decisions_en_cours():
            super().reject()
            return
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle("Décisions non appliquées")
        boite.setText("Des décisions n'ont pas été appliquées.")
        boite.setInformativeText("Les appliquer avant de fermer ?")
        appliquer = boite.addButton("Appliquer", QMessageBox.AcceptRole)
        appliquer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        abandonner = boite.addButton("Fermer sans appliquer", QMessageBox.DestructiveRole)
        boite.addButton("Continuer", QMessageBox.RejectRole)
        boite.setDefaultButton(appliquer)

        def _choix(bouton):
            if bouton is appliquer:
                self._on_appliquer()
                self._fermeture_confirmee = True
                super(FenetreRevue, self).reject()
            elif bouton is abandonner:
                self._fermeture_confirmee = True
                super(FenetreRevue, self).reject()

        boite.buttonClicked.connect(_choix)
        boite.setWindowModality(Qt.WindowModal)
        self._confirmation = boite
        boite.show()
