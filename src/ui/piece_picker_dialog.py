"""
PiecePickerDialog : dialog de sélection de pièce avec recherche en temps réel.
RefTagList        : widget de liste de références supprimables (chips).
"""

import qtawesome as qta
from typing import Callable, Optional, List
from PyQt5.QtCore import QEvent, QSortFilterProxyModel, QTimer
from PyQt5.QtGui import QKeySequence, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QShortcut, QTableView
from ..utils.qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                          QLabel, QPushButton, QLineEdit, QTableWidget,
                          QTableWidgetItem, QHeaderView, Qt, QFrame, QScrollArea,
                          QSize, pyqtSignal, QColor, QFont)
from src.core.logger import app_logger
from .style_manager import StyleManager


# ── RefTagList ───────────────────────────────────────────────────────────────

class RefTagList(QWidget):
    """
    Widget affichant des références comme des lignes (chips) individuellement supprimables.

    Chaque ligne : [ref monospace] [description grisée]  [✕]

    Auto-scrollable : hauteur limitée à MAX_HEIGHT, ascenseur vertical si dépassement.
    Signal ref_removed(str) émis quand l'utilisateur clique ✕.
    """

    ref_removed       = pyqtSignal(str)
    ref_clicked       = pyqtSignal(str)   # émis au clic gauche sur le texte de la référence
    ref_right_clicked = pyqtSignal(str)   # émis au clic droit sur le texte de la référence
    MAX_HEIGHT = 124  # ~4 chips visibles avant scroll

    def __init__(self, parent=None):
        super().__init__(parent)
        self._compact = False

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # ── Chemin normal : QScrollArea (gestionnaire, panneau pièces) ────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(3)

        self._scroll.setWidget(self._content)
        self._outer.addWidget(self._scroll)

        # ── Chemin compact : QWidget plat sans QScrollArea ────────────────
        self._flat = QWidget()
        self._flat.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._flat_layout = QVBoxLayout(self._flat)
        self._flat_layout.setContentsMargins(16, 0, 0, 0)
        self._flat_layout.setSpacing(0)
        self._flat.setVisible(False)
        self._outer.addWidget(self._flat)

        self._refs = []
        self._full_height_mode = False
        # Message affiché quand la liste est vide (mode pleine hauteur seulement)
        self._empty_text = ""
        self.setVisible(False)

    # ── API publique ─────────────────────────────────────────────────────────

    def set_refs(self, refs: list, color: str = '#2c3e50',
                 descriptions: Optional[dict] = None):
        """
        Mettre à jour la liste des chips.

        :param refs: liste de références à afficher
        :param color: couleur du texte de la référence
        :param descriptions: dict {ref: description} optionnel pour affichage inline
        """
        self._refs = list(refs)
        n = len(refs)

        if self._compact:
            # ── Chemin plat : pas de QScrollArea ─────────────────────────────
            while self._flat_layout.count():
                item = self._flat_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for ref in refs:
                desc = (descriptions or {}).get(ref, '')
                row_widget = self._make_row(ref, desc, color)
                self._flat_layout.addWidget(row_widget)

            if not self._full_height_mode:
                self._flat.setVisible(n > 0)
                self.setVisible(n > 0)
        else:
            # ── Chemin normal : QScrollArea ───────────────────────────────────
            while self._layout.count():
                item = self._layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for ref in refs:
                desc = (descriptions or {}).get(ref, '')
                row_widget = self._make_row(ref, desc, color)
                self._layout.addWidget(row_widget)

            if n == 0 and self._full_height_mode and self._empty_text:
                empty = QLabel(self._empty_text)
                empty.setAlignment(Qt.AlignCenter)
                empty.setWordWrap(True)
                empty.setStyleSheet("color: #adb5bd; font-size: 11px; padding-top: 12px;")
                self._layout.addWidget(empty)

            self._layout.addStretch()

            if not self._full_height_mode:
                if n == 0:
                    self.setVisible(False)
                else:
                    self._scroll.setFixedHeight(min(n * 31 + 4, self.MAX_HEIGHT))
                    self.setVisible(True)
        # else full_height_mode : toujours visible, hauteur gérée par le layout parent

    def is_empty(self) -> bool:
        return len(self._refs) == 0

    def enable_full_height_mode(self):
        """Mode hauteur libre : le widget remplit l'espace disponible (panneau latéral)."""
        from ..utils.qt_imports import QSizePolicy
        self._full_height_mode = True
        self.setVisible(True)
        self._scroll.setMaximumHeight(16777215)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Fond du cadre parent plutôt que le gris par défaut de la zone défilante
        # (grands blocs gris vides dans le panneau du gestionnaire de pièces)
        self._scroll.setStyleSheet(StyleManager.ZONE_DEFILEMENT_TRANSPARENTE)
        self._scroll.viewport().setAutoFillBackground(False)

    def set_empty_text(self, text: str):
        """Message centré et estompé affiché quand la liste est vide (mode pleine
        hauteur). Pris en compte au prochain set_refs()."""
        self._empty_text = text

    # ── Interne ──────────────────────────────────────────────────────────────

    def _make_row(self, ref: str, desc: str, color: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            "QWidget { background: transparent; border: none;"
            "border-bottom: 1px solid #eeeeee; } "
            "QWidget:hover { background: #f5f5f5; }"
        )
        row.setFixedHeight(28)

        h = QHBoxLayout(row)
        h.setContentsMargins(8, 3, 6, 3)
        h.setSpacing(6)

        # Référence en monospace bold coloré — cliquable (copie + recherche)
        ref_lbl = QLabel(ref)
        ref_lbl.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
        )
        ref_lbl.setCursor(Qt.PointingHandCursor)
        ref_lbl.setToolTip(f"Cliquer pour rechercher '{ref}'")
        ref_lbl.enterEvent  = lambda event, lbl=ref_lbl, c=color: lbl.setStyleSheet(
            f"color: {c}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
            "text-decoration: underline;"
        )
        ref_lbl.leaveEvent  = lambda event, lbl=ref_lbl, c=color: lbl.setStyleSheet(
            f"color: {c}; font-weight: bold; font-size: 11px;"
            "font-family: monospace; background: transparent; border: none;"
        )
        def _ref_mouse_press(event, r=ref):
            if event.button() == Qt.LeftButton:
                self.ref_clicked.emit(r)
            elif event.button() == Qt.RightButton:
                self.ref_right_clicked.emit(r)
        ref_lbl.mousePressEvent = _ref_mouse_press
        h.addWidget(ref_lbl)

        # Description en gris (si disponible)
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                "color: #6c757d; font-size: 11px; background: transparent; border: none;"
            )
            desc_lbl.setMaximumWidth(200)
            h.addWidget(desc_lbl, 1)
        else:
            h.addStretch(1)

        # ✕ cliquable (QLabel pour éviter la hauteur minimale imposée par macOS)
        remove_lbl = QLabel("<b>✕</b>")
        remove_lbl.setStyleSheet(
            "color: #dc3545; font-size: 13px; background: transparent; border: none;"
            "padding: 0 2px;"
        )
        remove_lbl.setToolTip(f"Retirer {ref}")
        remove_lbl.setCursor(Qt.PointingHandCursor)
        remove_lbl.mousePressEvent = (lambda event, r=ref: self.ref_removed.emit(r))
        h.addWidget(remove_lbl)

        return row


# ── PiecePickerDialog ────────────────────────────────────────────────────────

class _FiltreRefLibelle(QSortFilterProxyModel):
    """Filtre sur la référence ou le libellé (pas sur le statut)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._texte = ''

    def definir_texte(self, texte: str):
        self._texte = (texte or '').strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, ligne, parent):
        if not self._texte:
            return True
        modele = self.sourceModel()
        return any(self._texte in (modele.index(ligne, c, parent).data() or '').lower()
                   for c in (0, 1))


class PiecePickerDialog(QDialog):
    """
    Fenêtre de sélection de pièces avec un panier.

    - En haut, le panier (`RefChipsInput`, comme à l'import) : les réfs retenues,
      retirables (✕, Retour arrière) ; on peut y taper ou coller des réfs. Une
      réf. inconnue est signalée : elle sera créée en fantôme.
    - Dessous, la recherche (réf. ou libellé) filtre le tableau sans jamais vider
      le panier ; double-clic ou Entrée sur une ligne l'ajoute au panier (ou la
      remplace, panier à une réf.).
    - « Ajouter N références » (⌘Entrée) valide. `valider(refs)` peut refuser
      avec un motif : il s'affiche sous le panier, la fenêtre reste ouverte.

    Usage :
        dlg = PiecePickerDialog(db_manager, parent=self, exclude_ref='AS001')
        ouvrir_modal(dlg, sur_accepte=lambda: traiter(dlg.selected_refs()))
        # (ouverture_modale.ouvrir_modal : show() + callbacks, jamais exec_)
    """

    def __init__(self, db_manager, parent=None, exclude_ref: Optional[str] = None,
                 title: str = "Sélectionner une pièce",
                 multi_select: bool = False, max_refs: Optional[int] = -1,
                 filtre: Optional[Callable[[str], bool]] = None,
                 valider: Optional[Callable[[List[str]], str]] = None,
                 recherche_initiale: str = ''):
        super().__init__(parent)
        self.db_manager = db_manager
        self.exclude_ref = exclude_ref
        # max_refs : None = illimité ; par défaut, déduit de multi_select
        self._max = (None if multi_select else 1) if max_refs == -1 else max_refs
        self._filtre = filtre
        self._valider = valider
        self._connues: set = set()
        self._items_statut: dict = {}     # réf → (item Statut, texte, icône d'origine)
        self._marquees: set = set()

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(600, 480)
        self._init_ui()
        self._load_pieces()
        if recherche_initiale:
            self._recherche.setText(recherche_initiale)
            self._filtrer()
        self._maj_panier()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _init_ui(self):
        from .ref_chips_input import RefChipsInput
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        unique = self._max == 1
        titre_panier = QLabel("Référence choisie :" if unique else "Références choisies :")
        titre_panier.setStyleSheet(StyleManager.TEXTE_GRAS_TRANSPARENT)
        layout.addWidget(titre_panier)
        self._panier = RefChipsInput(
            "Tapez ou collez une réf., ou double-cliquez une ligne" if unique
            else "Tapez ou collez des réf., ou double-cliquez des lignes", max_refs=self._max)
        self._panier.changed.connect(self._maj_panier)
        self._panier.line_edit.textChanged.connect(lambda *_: self._maj_panier())
        self._panier.line_edit.returnPressed.connect(self._entree_panier_vide)
        layout.addWidget(self._panier)

        self._etat = QLabel("")
        self._etat.setStyleSheet(StyleManager.TEXTE_GRIS_PETIT)
        self._etat.setWordWrap(True)
        layout.addWidget(self._etat)
        self._erreur = QLabel("")
        self._erreur.setStyleSheet(StyleManager.TEXTE_ERREUR_PETIT)
        self._erreur.setWordWrap(True)
        self._erreur.setVisible(False)
        layout.addWidget(self._erreur)

        # Recherche : filtre le tableau, ne touche jamais au panier
        ligne_recherche = QHBoxLayout()
        ligne_recherche.addWidget(QLabel("Rechercher :"))
        self._recherche = QLineEdit()
        self._recherche.setPlaceholderText("Réf. ou libellé…")
        self._recherche.setClearButtonEnabled(True)
        self._delai = QTimer(self)
        self._delai.setSingleShot(True)
        self._delai.setInterval(150)
        self._delai.timeout.connect(self._filtrer)
        self._recherche.textChanged.connect(lambda *_: self._delai.start())
        self._recherche.returnPressed.connect(self._entree_recherche)
        self._recherche.installEventFilter(self)
        ligne_recherche.addWidget(self._recherche)
        layout.addLayout(ligne_recherche)

        self._modele = QStandardItemModel(0, 3, self)
        self._modele.setHorizontalHeaderLabels(["Référence", "Libellé", "Statut"])
        self._proxy = _FiltreRefLibelle(self)
        self._proxy.setSourceModel(self._modele)
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._ajouter_ligne)
        self._table.installEventFilter(self)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        # Tri croissant par défaut (sinon Qt part de l'indicateur décroissant)
        hdr.setSortIndicator(0, Qt.AscendingOrder)
        self._table.setColumnWidth(0, 140)
        self._table.setColumnWidth(1, 300)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(self._table)

        aide = QLabel("Double-clic ou Entrée sur une ligne : l'ajouter au choix  ·  "
                      "⌘Entrée : valider")
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE_ITALIQUE)
        layout.addWidget(aide)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        self._ok_btn = QPushButton("")
        self._ok_btn.setIcon(qta.icon('fa5s.check', color='white'))
        self._ok_btn.setIconSize(QSize(11, 11))
        self._ok_btn.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self._ok_btn.setAutoDefault(False)     # Entrée dans la recherche n'accepte pas
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._ok_btn)
        layout.addLayout(btn_row)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.accept)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.accept)

    # ── Chargement ───────────────────────────────────────────────────────────

    def _load_pieces(self):
        """Charger les pièces une fois ; la recherche filtre sans recharger."""
        try:
            rows = self.db_manager.lister_pieces_selecteur() or []
        except Exception as e:
            app_logger.error(f"PiecePickerDialog: erreur chargement pièces: {e}")
            rows = []
        self._connues = {r[0] for r in rows if r[0]}
        italique = QFont()
        italique.setItalic(True)
        gris = QColor(150, 150, 150)
        for ref, desc, is_obsolete, is_phantom in rows:
            if not ref or ref == self.exclude_ref:
                continue
            if self._filtre is not None and not self._filtre(ref):
                continue
            ref_item, desc_item = QStandardItem(ref), QStandardItem(desc or "")
            # Mêmes icônes et libellés que la colonne Statut du gestionnaire
            if is_phantom:
                texte, icone, couleur = "Fantôme", 'fa5s.ghost', '#999999'
            elif is_obsolete:
                texte, icone, couleur = "Obsolète", 'fa5s.ban', '#c62828'
            else:
                texte, icone, couleur = "OK", 'fa5s.check-circle', '#2e7d32'
            st_item = QStandardItem(qta.icon(icone, color=couleur), texte)
            if is_phantom:
                for item in (ref_item, desc_item, st_item):
                    item.setForeground(gris)
                ref_item.setFont(italique)
                desc_item.setFont(italique)
            self._items_statut[ref] = (st_item, texte, st_item.icon())
            self._modele.appendRow([ref_item, desc_item, st_item])
        self._proxy.sort(0, Qt.AscendingOrder)

    # ── Recherche et ajout au panier ─────────────────────────────────────────

    def _filtrer(self):
        self._proxy.definir_texte(self._recherche.text())

    def _ref_ligne(self, index) -> Optional[str]:
        if not index.isValid():
            return None
        return self._proxy.index(index.row(), 0).data()

    def _ajouter_ligne(self, index=None):
        ref = self._ref_ligne(index if index is not None else self._table.currentIndex())
        if not ref:
            return
        if self._max == 1:
            self._panier.set_refs([ref])
            self._maj_panier()
        else:
            self._panier.add_refs([ref])

    def _entree_recherche(self):
        """Entrée dans la recherche : une seule ligne visible → l'ajouter ;
        sinon la ligne sélectionnée."""
        if self._delai.isActive():
            self._delai.stop()
            self._filtrer()
        if self._proxy.rowCount() == 1:
            self._ajouter_ligne(self._proxy.index(0, 0))
        elif self._table.currentIndex().isValid():
            self._ajouter_ligne()

    def _entree_panier_vide(self):
        if not self._panier.line_edit.text().strip():
            self.accept()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if obj is self._table and event.key() in (Qt.Key_Return, Qt.Key_Enter) \
                    and not event.modifiers() & Qt.ControlModifier:
                self._ajouter_ligne()
                return True
            if obj is self._recherche and event.key() == Qt.Key_Down:
                self._table.setFocus()
                if not self._table.currentIndex().isValid() and self._proxy.rowCount():
                    self._table.setCurrentIndex(self._proxy.index(0, 0))
                return True
        return super().eventFilter(obj, event)

    # ── Panier ───────────────────────────────────────────────────────────────

    def _maj_panier(self):
        refs = self._panier.refs()
        self._erreur.setVisible(False)
        # « ✓ Ajoutée » sur les lignes du panier (elles restent visibles)
        for ref in self._marquees - set(refs):
            if ref in self._items_statut:
                item, texte, icone = self._items_statut[ref]
                item.setText(texte)
                item.setIcon(icone)
        for ref in set(refs) - self._marquees:
            if ref in self._items_statut:
                item = self._items_statut[ref][0]
                item.setText("Ajoutée")
                item.setIcon(qta.icon('fa5s.check', color='#2e7d32'))
        self._marquees = set(refs)
        inconnues = [r for r in refs if r not in self._connues]
        if not refs:
            self._etat.setText("Rien de choisi pour l'instant.")
        else:
            texte = (f"{len(refs)} choisie{'s' if len(refs) > 1 else ''}")
            if inconnues:
                texte += (f" · {len(inconnues)} inconnue{'s' if len(inconnues) > 1 else ''}"
                          f" (sera{'ont' if len(inconnues) > 1 else ''} créée"
                          f"{'s' if len(inconnues) > 1 else ''} en fantôme) : "
                          + ", ".join(inconnues))
            self._etat.setText(texte)
        n = len(refs)
        if self._max == 1:
            self._ok_btn.setText("Choisir")
        else:
            self._ok_btn.setText(f"Ajouter {n} référence{'s' if n > 1 else ''}" if n
                                 else "Ajouter")
        self._ok_btn.setEnabled(bool(refs))

    def accept(self):
        refs = self.selected_refs()
        if not refs:
            return
        if self._valider is not None:
            motif = self._valider(refs)
            if motif:
                self._erreur.setText(motif)
                self._erreur.setVisible(True)
                return
        super().accept()

    # ── API publique ─────────────────────────────────────────────────────────

    def selected_ref(self) -> Optional[str]:
        """La première réf. choisie (ou None)."""
        refs = self._panier.refs()
        return refs[0] if refs else None

    def selected_refs(self) -> List[str]:
        """Toutes les réfs choisies, y compris le texte tapé non validé."""
        return self._panier.refs()
