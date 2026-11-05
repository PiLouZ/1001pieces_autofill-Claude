"""
Colonne « variantes » de la configuration des exports (onglets HTML, Titre, Fiche)

Liste de gauche des gabarits nommés d'un bouton d'export (profils HTML Détails,
gabarits Titre, variantes Fiche complète), commune aux trois onglets :
- gabarit par défaut en tête (étoile), puis les autres par ordre alphanumérique
  naturel ; noms longs sur plusieurs lignes, jamais tronqués ;
- filtre dès SEUIL_FILTRE gabarits (même seuil que les menus de la fenêtre
  principale) ;
- renommer en place (double-clic, F2) ou par le champ « Nom » de la barre
  rendue par barre_nom() ; un nom vide ou déjà pris est refusé, signalé ;
- Nouveau / Dupliquer / Supprimer sous la liste, menu complet au clic droit.

La colonne possède la copie de travail des gabarits jusqu'à « Enregistrer »
(cf. ExportConfigDialog._collect_config). L'onglet fournit trois fonctions :
stocker(profil) reporte ses champs dans le dict, charger(profil) affiche le
dict, nouveau() rend un gabarit aux valeurs par défaut (sans nom).
"""

import copy
from typing import Callable, List, Optional

import qtawesome as qta
from ..utils.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QAbstractItemView, QStyledItemDelegate,
    QStyleOptionViewItem, QEvent, Qt, QSize, QRect, QFont
)
from .style_manager import StyleManager
from .apercu_export_dialog import DelegueNomsReplies
from src.utils.text_utils import cle_tri_naturel, strip_accents


# Mots des messages selon le genre de gabarit : (nom, titre de la liste, féminin)
LIBELLES = {
    'html_details': ("profil", "Profils HTML Détails", False),
    'titre':        ("gabarit", "Gabarits", False),
    'fiche':        ("variante", "Variantes", True),
}

COULEUR_ETOILE = '#f0ad00'

# Marge intérieure des lignes de la liste (feuille de style) : 4 px haut/bas, 6 px côtés
_PADDING_LIGNE = "QListWidget::item { padding: 4px 6px; }"


class DelegueNomsListe(DelegueNomsReplies):
    """Comme DelegueNomsReplies, marges des lignes déduites de la largeur.

    Le calcul de hauteur ne voit pas la marge de la feuille de style, le dessin
    si : un nom qui tient tout juste sur une ligne au calcul était tronqué (« … »)
    au dessin.
    """

    MARGE = 2 * 6 + 4

    def sizeHint(self, option, index):
        vue = self.parent()
        repli = QStyleOptionViewItem(option)
        repli.rect = QRect(0, 0, max(vue.viewport().width() - 2 * vue.spacing() - self.MARGE, 1), 1)
        return QStyledItemDelegate.sizeHint(self, repli, index)


class ColonneVariantes(QWidget):
    """Liste des gabarits d'un onglet, avec leur copie de travail."""

    SEUIL_FILTRE = 6

    def __init__(self, genre: str, stocker: Callable[[dict], None],
                 charger: Callable[[dict], None], nouveau: Callable[[], dict],
                 bouton: str, parent=None):
        """
        Args:
            genre: 'html_details', 'titre' ou 'fiche' (mots des messages).
            bouton: nom du bouton d'export, pour les info-bulles « Par défaut ».
        """
        super().__init__(parent)
        self.genre = genre
        self._stocker, self._charger, self._nouveau = stocker, charger, nouveau
        self._nom, self._titre, self._feminin = LIBELLES[genre]
        self._bouton = bouton
        self._profiles: List[dict] = []
        self._defaut = ""
        self._courant = ""
        # Fonctions appelées après un renommage : f(ancien, nouveau)
        self.renommages: List[Callable[[str, str], None]] = []
        self._etoile = qta.icon('fa5s.star', color=COULEUR_ETOILE)
        self._sans_etoile = qta.icon('fa5s.star', color='transparent')
        self._build_ui()
        self._build_barre_nom()

    # ─── Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.titre_label = QLabel()
        police = QFont()
        police.setBold(True)
        self.titre_label.setFont(police)
        layout.addWidget(self.titre_label)

        self.filtre = QLineEdit()
        self.filtre.setPlaceholderText("Filtrer…")
        self.filtre.setClearButtonEnabled(True)
        self.filtre.textChanged.connect(self._filtrer)
        layout.addWidget(self.filtre)

        self.liste = QListWidget()
        # Noms longs : retour à la ligne, jamais tronqués (comme l'aperçu d'export)
        self.liste.setWordWrap(True)
        self.liste.setTextElideMode(Qt.ElideNone)
        self.liste.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.liste.setResizeMode(QListWidget.Adjust)
        self.liste.setItemDelegate(DelegueNomsListe(self.liste))
        self.liste.setIconSize(QSize(10, 10))
        # Lignes plus serrées que le style global (8 px) : une dizaine de noms visibles
        self.liste.setStyleSheet(_PADDING_LIGNE)
        self.liste.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._menu_contextuel)
        self.liste.currentItemChanged.connect(self._on_item_courant)
        self.liste.itemChanged.connect(self._on_item_renomme)
        self.liste.installEventFilter(self)
        layout.addWidget(self.liste, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.nouveau_btn = QPushButton("Nouvelle" if self._feminin else "Nouveau")
        self.nouveau_btn.setIcon(qta.icon('fa5s.plus', color='#495057'))
        self.nouveau_btn.setToolTip(f"{self._un_nouveau().capitalize()} (valeurs par défaut)")
        self.nouveau_btn.clicked.connect(self.ajouter)
        self.dupliquer_btn = QPushButton()
        self.dupliquer_btn.setIcon(qta.icon('fa5s.copy', color='#495057'))
        self.dupliquer_btn.setToolTip(f"Dupliquer {self._le()} sélectionné{self._e()}")
        self.dupliquer_btn.clicked.connect(self.dupliquer)
        self.supprimer_btn = QPushButton()
        self.supprimer_btn.setIcon(qta.icon('fa5s.trash-alt', color='#c0392b'))
        self.supprimer_btn.setToolTip(f"Supprimer {self._le()} sélectionné{self._e()}")
        self.supprimer_btn.clicked.connect(self.supprimer)
        for btn, style in ((self.nouveau_btn, StyleManager.SECONDARY_COMPACT_BUTTON),
                           (self.dupliquer_btn, StyleManager.SECONDARY_COMPACT_BUTTON),
                           (self.supprimer_btn, StyleManager.DANGER_COMPACT_BUTTON)):
            btn.setIconSize(QSize(11, 11))
            btn.setStyleSheet(style)
            if not btn.text():
                btn.setFixedSize(28, 26)
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)

        aide = QLabel("Double-clic ou F2 : renommer. Clic droit : toutes les actions.")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        layout.addWidget(aide)

    def _build_barre_nom(self):
        """Champ « Nom » + bouton « Par défaut », placés par l'onglet en tête de ses réglages."""
        self._barre_nom = QWidget()
        layout = QVBoxLayout(self._barre_nom)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        libelle = QLabel("Nom :")
        libelle.setFont(self.titre_label.font())
        ligne.addWidget(libelle)
        self.nom_input = QLineEdit()
        self.nom_input.setToolTip(f"Nom {self._du()} sélectionné{self._e()}")
        self.nom_input.textEdited.connect(self._on_nom_saisi)
        self.nom_input.editingFinished.connect(self._fin_saisie_nom)
        ligne.addWidget(self.nom_input, 1)
        self.defaut_btn = QPushButton("Par défaut")
        self.defaut_btn.setCheckable(True)
        self.defaut_btn.setIconSize(QSize(11, 11))
        self.defaut_btn.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON
                                      + "QPushButton:checked { background: #fff4d6; border-color: #f0ad00; }")
        self.defaut_btn.clicked.connect(lambda _coche: self.definir_defaut())
        ligne.addWidget(self.defaut_btn)
        layout.addLayout(ligne)
        self.erreur_nom = QLabel()
        self.erreur_nom.setStyleSheet("color: #c0392b; font-size: 11px;")
        self.erreur_nom.setVisible(False)
        layout.addWidget(self.erreur_nom)

    def barre_nom(self) -> QWidget:
        return self._barre_nom

    # ─── Mots des messages ───────────────────────────────────────────────

    def _e(self):
        return "e" if self._feminin else ""

    def _le(self):
        return ("la " if self._feminin else "le ") + self._nom

    def _du(self):
        return ("de la " if self._feminin else "du ") + self._nom

    def _un_nouveau(self):
        return ("nouvelle " if self._feminin else "nouveau ") + self._nom

    # ─── Données ─────────────────────────────────────────────────────────

    def load(self, profiles: List[dict], defaut: str):
        """Copie de travail des gabarits de la config chargée, défaut sélectionné."""
        self._profiles = copy.deepcopy(profiles)
        self._defaut = defaut if any(p['name'] == defaut for p in self._profiles) \
            else self._profiles[0]['name']
        self._courant = self._defaut
        self.filtre.clear()
        self._remplir(self._courant)
        self._afficher_courant()

    def collect(self):
        """(gabarits, nom par défaut), champs de l'éditeur reportés."""
        self.stocker()
        return copy.deepcopy(self._profiles), self._defaut

    def stocker(self):
        if self._profiles:
            self._stocker(self._find(self._courant))

    def _find(self, nom) -> dict:
        return next((p for p in self._profiles if p['name'] == nom), self._profiles[0])

    def profil_courant(self) -> dict:
        return self._find(self._courant)

    @property
    def nom_courant(self) -> str:
        return self._courant

    @property
    def nom_defaut(self) -> str:
        return self._defaut

    def noms(self) -> List[str]:
        return [p['name'] for p in self._profiles]

    def modifier_tous(self, fonction: Callable[[dict], None]):
        """Appliquer `fonction` à chaque gabarit de la copie de travail (en place)."""
        for profil in self._profiles:
            fonction(profil)

    def profils(self) -> List[dict]:
        """Gabarits (copie), champs de l'éditeur reportés."""
        self.stocker()
        return [dict(p) for p in self._profiles]

    def _unique(self, base):
        noms = set(self.noms())
        if base not in noms:
            return base
        i = 2
        while f"{base} ({i})" in noms:
            i += 1
        return f"{base} ({i})"

    # ─── Liste ───────────────────────────────────────────────────────────

    def noms_ordonnes(self) -> List[str]:
        """Défaut en tête, puis les autres par ordre alphanumérique naturel."""
        autres = sorted((n for n in self.noms() if n != self._defaut), key=cle_tri_naturel)
        return [self._defaut] + autres

    def _remplir(self, choisi: Optional[str] = None):
        self.liste.blockSignals(True)
        self.liste.clear()
        for nom in self.noms_ordonnes():
            item = QListWidgetItem(nom)
            item.setData(Qt.UserRole, nom)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            if nom == self._defaut:
                item.setIcon(self._etoile)
                item.setToolTip(f"Par défaut : utilisé{self._e()} au clic sur le bouton {self._bouton}")
            else:
                # Icône transparente : tous les noms alignés sur celui du défaut
                item.setIcon(self._sans_etoile)
            self.liste.addItem(item)
            if nom == choisi:
                self.liste.setCurrentItem(item)
        self.liste.blockSignals(False)
        nb = len(self._profiles)
        self.titre_label.setText(f"{self._titre} ({nb})")
        avec_filtre = nb >= self.SEUIL_FILTRE
        self.filtre.setVisible(avec_filtre)
        if not avec_filtre:
            self.filtre.clear()
        self.supprimer_btn.setEnabled(nb > 1)
        self._filtrer(self.filtre.text())

    def _item(self, nom) -> Optional[QListWidgetItem]:
        return next((self.liste.item(i) for i in range(self.liste.count())
                     if self.liste.item(i).data(Qt.UserRole) == nom), None)

    def _filtrer(self, texte):
        """Masquer les noms qui ne contiennent pas tous les mots (casse et accents ignorés)."""
        mots = strip_accents(texte).casefold().split()
        for i in range(self.liste.count()):
            item = self.liste.item(i)
            nom = strip_accents(item.data(Qt.UserRole)).casefold()
            item.setHidden(not all(m in nom for m in mots))

    def _on_item_courant(self, item, _precedent):
        if item is None:
            return
        nom = item.data(Qt.UserRole)
        if nom == self._courant:
            return
        self.stocker()
        self._courant = nom
        self._afficher_courant()

    def _afficher_courant(self):
        self._charger(self._find(self._courant))
        self._maj_barre_nom()

    def _maj_barre_nom(self):
        self.nom_input.setText(self._courant)
        self._signaler_nom("")
        est_defaut = self._courant == self._defaut
        self.defaut_btn.setChecked(est_defaut)
        self.defaut_btn.setIcon(qta.icon('fa5s.star', color=COULEUR_ETOILE if est_defaut else '#495057'))
        self.defaut_btn.setToolTip(
            f"{self._le().capitalize()} par défaut, utilisé{self._e()} au clic sur le bouton {self._bouton}"
            if est_defaut else
            f"Utiliser {self._le()} sélectionné{self._e()} au clic sur le bouton {self._bouton}")

    def selectionner(self, nom: str) -> bool:
        """Sélectionner un gabarit par son nom (filtre vidé s'il le masquait)."""
        item = self._item(nom)
        if item is None:
            return False
        if item.isHidden():
            self.filtre.clear()
        self.liste.setCurrentItem(item)
        return True

    # ─── Renommer ────────────────────────────────────────────────────────

    def _refus_nom(self, ancien, nom) -> str:
        """Raison du refus d'un nom ('' si accepté)."""
        if not nom:
            return "Le nom ne peut pas être vide."
        if nom != ancien and nom in self.noms():
            return f"« {nom} » existe déjà : choisissez un autre nom."
        return ""

    def _signaler_nom(self, message):
        self.erreur_nom.setText(message)
        self.erreur_nom.setVisible(bool(message))
        self.nom_input.setStyleSheet("QLineEdit { border: 1px solid #dc3545; }" if message else "")

    def renommer(self, ancien, nouveau, retrier=True) -> bool:
        """Renommer `ancien` en `nouveau` (espaces de bord retirés). Faux si refusé."""
        nouveau = (nouveau or "").strip()
        refus = self._refus_nom(ancien, nouveau)
        if refus:
            self._signaler_nom(refus)
            return False
        self._signaler_nom("")
        if nouveau == ancien:
            return True
        self._find(ancien)['name'] = nouveau
        if self._defaut == ancien:
            self._defaut = nouveau
        if self._courant == ancien:
            self._courant = nouveau
        if retrier:
            self._remplir(self._courant)
        else:
            item = self._item(ancien)
            if item is not None:
                self.liste.blockSignals(True)
                item.setText(nouveau)
                item.setData(Qt.UserRole, nouveau)
                self.liste.blockSignals(False)
        for rappel in self.renommages:
            rappel(ancien, nouveau)
        return True

    def _on_nom_saisi(self, texte):
        # La liste suit la frappe ; elle n'est retriée qu'en fin de saisie
        self.renommer(self._courant, texte, retrier=False)

    def _fin_saisie_nom(self):
        # Nom refusé en fin de saisie : le dernier nom accepté revient
        self.nom_input.setText(self._courant)
        self._signaler_nom("")
        self._remplir(self._courant)

    def _on_item_renomme(self, item):
        ancien = item.data(Qt.UserRole)
        if self.renommer(ancien, item.text()):
            self.nom_input.setText(self._courant)
            return
        # Refusé : l'ancien nom revient dans la liste, la raison sous le champ Nom
        self.liste.blockSignals(True)
        item.setText(ancien)
        self.liste.blockSignals(False)

    def editer_nom(self):
        """Renommer en place le gabarit sélectionné."""
        item = self.liste.currentItem()
        if item is not None:
            self.liste.editItem(item)

    def eventFilter(self, objet, evenement):
        # F2 sur toutes les plateformes (macOS n'en fait pas une touche d'édition)
        if objet is self.liste and evenement.type() == QEvent.KeyPress \
                and evenement.key() == Qt.Key_F2 \
                and self.liste.state() != QAbstractItemView.EditingState:
            self.editer_nom()
            return True
        return super().eventFilter(objet, evenement)

    # ─── Actions ─────────────────────────────────────────────────────────

    def _ajouter_selectionner(self, profil):
        self.stocker()
        self._profiles.append(profil)
        self._courant = profil['name']
        self.filtre.clear()
        self._remplir(self._courant)
        self._afficher_courant()

    def ajouter(self):
        """Nouveau gabarit aux valeurs par défaut, nom proposé à modifier en place."""
        profil = self._nouveau()
        profil['name'] = self._unique(self._un_nouveau().capitalize())
        self._ajouter_selectionner(profil)
        self.editer_nom()

    def dupliquer(self):
        self.stocker()
        source = self._find(self._courant)
        profil = copy.deepcopy(source)
        profil['name'] = self._unique(f"{source['name']} (copie)")
        self._ajouter_selectionner(profil)

    def supprimer(self):
        if len(self._profiles) <= 1:
            QMessageBox.warning(self, "Suppression impossible",
                                f"Au moins {'une' if self._feminin else 'un'} {self._nom} doit exister.")
            return
        nom = self._courant
        if QMessageBox.question(
            self, f"Supprimer {self._le()}", f"Supprimer {self._le()} « {nom} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._profiles = [p for p in self._profiles if p['name'] != nom]
        if self._defaut == nom:
            self._defaut = self._profiles[0]['name']
        self._courant = self._defaut
        self._remplir(self._courant)
        self._afficher_courant()

    def definir_defaut(self):
        self._defaut = self._courant
        self._remplir(self._courant)
        self._maj_barre_nom()

    def _menu_contextuel(self, position):
        item = self.liste.itemAt(position)
        if item is not None and item is not self.liste.currentItem():
            self.liste.setCurrentItem(item)
        menu = QMenu(self)
        if item is not None:
            menu.addAction("Renommer", self.editer_nom)
            menu.addAction("Dupliquer", self.dupliquer)
            defaut = menu.addAction("Définir par défaut", self.definir_defaut)
            defaut.setEnabled(self._courant != self._defaut)
            menu.addSeparator()
        menu.addAction(self._un_nouveau().capitalize(), self.ajouter)
        if item is not None:
            menu.addSeparator()
            supprimer = menu.addAction("Supprimer…", self.supprimer)
            supprimer.setEnabled(len(self._profiles) > 1)
        menu.popup(self.liste.viewport().mapToGlobal(position))
