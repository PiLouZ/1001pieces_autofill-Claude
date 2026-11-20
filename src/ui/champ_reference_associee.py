"""
Champ « Réf. associée » de la fenêtre d'import (CDC docs/cdc_import_fiches_site.md,
§ 10.17) : pour une pièce Whirlpool, Indesit ou Beko, la référence jumelle dans
l'un des deux autres groupes, à droite de la référence de la pièce. Facultative.

Le champ s'affiche d'office si la référence de la pièce a la forme de l'un de ces
groupes (table des formats) ou a déjà été déclarée de l'un d'eux. Il se
préremplit avec la réponse mémorisée, sinon avec l'équivalente de code produit
d'une fiche reprise, ou la 2ᵉ réf. du code produit d'une fiche en cours
d'import. Laissée vide, rien n'est retenu.

Référence de forme inconnue (§ 10.17 bis, Beko `210480241`) : un lien
« Associer… » laisse déclarer son groupe, puis le champ s'affiche. De même, une
réf. associée de forme inconnue fait apparaître le choix de son groupe. Les
groupes choisis sont écrits par l'import (`origines_declarees`).
"""

from typing import Callable, Dict, Optional, Tuple

from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QWidget)
from PyQt5.QtCore import Qt
import qtawesome as qta

from src.utils.rapprochement_fiche.associee import (ORIGINES_ASSOCIEES, autres_origines,
                                                    origine_associable)
from .ref_chips_input import RefChipsInput
from .style_manager import StyleManager

# (réponse connue, référence associée ou None) pour une réf. de pièce
Memoire = Callable[[str], Tuple[bool, Optional[str]]]
# Inversion des rôles : (nouvelle référence de la pièce, nouvelle référence associée)
Inversion = Callable[[str, str], None]

_SANS_GROUPE = "Groupe ?"


class ChampReferenceAssociee(QWidget):
    """Réf. associée d'une pièce, à droite de sa référence : facultative, elle ne
    bloque rien ; laissée vide, rien n'est retenu."""

    def __init__(self, memoire: Optional[Memoire] = None, proposee: str = '',
                 largeur: int = 260, petit: bool = False, parent=None,
                 inversion: Optional[Inversion] = None):
        super().__init__(parent)
        self._memoire = memoire
        self._proposee = proposee or ''
        self._reference = ''
        self._inversion = inversion
        # Groupes choisis ici pour des réf. de forme inconnue (réf. → groupe)
        self._groupes_choisis: Dict[str, str] = {}
        self._choix_ouvert = False          # « Associer… » cliqué
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(6)
        # Réf. de forme inconnue : « Associer… » puis le choix de son groupe
        self.lien_associer = QPushButton("Associer…")
        self.lien_associer.setStyleSheet(StyleManager.REF_ASSOCIEE_LIEN)
        self.lien_associer.setCursor(Qt.PointingHandCursor)
        self.lien_associer.setToolTip(
            "Cette référence n'a la forme ni d'une réf. Whirlpool, ni Indesit, ni Beko. "
            "Indiquez son groupe pour lui donner une réf. associée (jumelle).")
        self.lien_associer.clicked.connect(self._sur_associer)
        self.lien_associer.setVisible(False)
        disposition.addWidget(self.lien_associer)
        self.groupe_piece = self._choix_groupe(
            "Groupe de cette référence (sa forme n'est pas reconnue) : retenu à l'import")
        self.groupe_piece.currentIndexChanged.connect(self._sur_groupe_piece)
        disposition.addWidget(self.groupe_piece)
        # ⇄ : la réf. associée devient la pièce (appareils, libellé), et inversement
        self.bouton_inverser = QPushButton(qta.icon('fa5s.exchange-alt', color='#0066cc'), '')
        self.bouton_inverser.setStyleSheet(StyleManager.ICON_BUTTON)
        self.bouton_inverser.setToolTip("Inverser : la référence associée devient la référence "
                                        "principale (elle reçoit les appareils et le libellé)")
        self.bouton_inverser.setFixedWidth(24)
        self.bouton_inverser.clicked.connect(self.inverser)
        self.bouton_inverser.setVisible(False)
        disposition.addWidget(self.bouton_inverser)
        self.libelle = QLabel("Réf. associée :")
        self.libelle.setStyleSheet(StyleManager.LIBELLE_PETIT_TRANSPARENT if petit
                                   else StyleManager.TEXTE_GRAS_TRANSPARENT)
        disposition.addWidget(self.libelle)
        # Dépôt d'une réf glissée (tuile « Non groupées », pastille d'un autre champ)
        self.champ = RefChipsInput("Réf. jumelle", max_refs=1, accepte_depot=True)
        # Largeur souple : `largeur` au plus, moins si la ligne manque de place
        # (sinon la carte déborde de sa colonne et se fait couper à droite)
        self.champ.setMaximumWidth(largeur)
        self.champ.changed.connect(self._maj_bouton)
        disposition.addWidget(self.champ)
        # Réf. associée de forme inconnue : le choix de son groupe, à sa droite
        self.groupe_associee = self._choix_groupe(
            "Groupe de la réf. associée (sa forme n'est pas reconnue) : retenu à l'import")
        self.groupe_associee.currentIndexChanged.connect(self._sur_groupe_associee)
        disposition.addWidget(self.groupe_associee)
        # Juste après la référence de la pièce : le champ ne prend que sa place
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.setVisible(False)

    @staticmethod
    def _choix_groupe(aide: str) -> QComboBox:
        choix = QComboBox()
        choix.setStyleSheet(StyleManager.CHOIX_GROUPE)
        choix.setToolTip(aide)
        choix.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        choix.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        choix.setVisible(False)
        return choix

    @staticmethod
    def _remplir(choix: QComboBox, groupes, actuel: str = ''):
        """Liste « Groupe ? » + `groupes`, `actuel` sélectionné, sans signal."""
        choix.blockSignals(True)
        choix.clear()
        choix.addItem(_SANS_GROUPE, '')
        for g in groupes:
            choix.addItem(g, g)
        index = choix.findData(actuel) if actuel else 0
        choix.setCurrentIndex(max(index, 0))
        choix.blockSignals(False)
        # Largeur du texte le plus long réservée : sinon la ligne de la carte
        # écrase la liste jusqu'à sa flèche, et le menu déroulant coupe les noms
        metriques = choix.fontMetrics()
        largeur = max(metriques.horizontalAdvance(choix.itemText(i))
                      for i in range(choix.count())) + 34
        choix.setMinimumWidth(largeur)
        choix.view().setMinimumWidth(largeur)

    # --- Origines -------------------------------------------------------------------
    def _origine(self, reference: str) -> str:
        """Groupe d'une référence : déclaré ou lu par sa forme, sinon choisi ici."""
        return origine_associable(reference) or self._groupes_choisis.get(reference, '')

    def _a_declarer(self, reference: str) -> bool:
        """Forme inconnue et aucune déclaration mémorisée : le groupe se choisit ici."""
        return bool(reference) and not origine_associable(reference)

    # --- Référence de la pièce ------------------------------------------------------
    def definir_reference(self, reference: str):
        """La référence de la pièce change (fichier, ou saisie d'un collage) : le
        champ s'affiche si elle est Whirlpool, Indesit ou Beko (forme ou groupe
        déclaré) et se préremplit ; sinon, le lien « Associer… »."""
        reference = (reference or '').strip()
        if reference == self._reference:
            return
        self._reference = reference
        self._afficher()

    def _afficher(self):
        reference = self._reference
        if not reference:
            self.setVisible(False)
            return
        a_declarer = self._a_declarer(reference)
        origine = self._origine(reference)
        # (isVisible() est faux tant que la fenêtre n'est pas montrée : drapeau)
        montrer_choix = a_declarer and (self._choix_ouvert or bool(origine))
        if montrer_choix:
            self._remplir(self.groupe_piece, ORIGINES_ASSOCIEES, origine)
        self.groupe_piece.setVisible(montrer_choix)
        self.lien_associer.setVisible(a_declarer and not montrer_choix)
        for w in (self.libelle, self.champ):
            w.setVisible(bool(origine))
        self.setVisible(True)
        if not origine:
            self.champ.set_refs([])
            self._maj_bouton()
            return
        self.libelle.setToolTip(f"Référence jumelle {autres_origines(origine)} de cette pièce "
                                f"{origine}. Facultative : laissée vide, rien n'est retenu.")
        self.champ.definir_aide(f"Réf. {autres_origines(origine)}")
        _, associee = (self._memoire(reference) if self._memoire is not None else (False, None))
        valeur = associee or self._proposee
        self.champ.set_refs([valeur] if valeur else [])
        self._maj_bouton()

    def _sur_associer(self):
        """« Associer… » : choisir le groupe de la référence de forme inconnue."""
        self._choix_ouvert = True
        self._afficher()
        if self.groupe_piece.isVisible():
            self.groupe_piece.showPopup()

    def _sur_groupe_piece(self, *_):
        groupe = self.groupe_piece.currentData() or ''
        if groupe:
            self._groupes_choisis[self._reference] = groupe
        else:
            self._groupes_choisis.pop(self._reference, None)
        self._afficher()

    def _maj_bouton(self):
        self.bouton_inverser.setVisible(self._inversion is not None and bool(self.champ.refs()))
        self._maj_groupe_associee()

    def _maj_groupe_associee(self):
        """Réf. associée de forme inconnue : choix de son groupe (les deux autres)."""
        refs = self.champ.refs()
        associee = refs[0] if refs else ''
        origine = self._origine(self._reference)
        if not associee or not origine or not self._a_declarer(associee):
            self.groupe_associee.setVisible(False)
            return
        autres = [g for g in ORIGINES_ASSOCIEES if g != origine]
        self._remplir(self.groupe_associee, autres, self._groupes_choisis.get(associee, ''))
        self.groupe_associee.setVisible(True)

    def _sur_groupe_associee(self, *_):
        refs = self.champ.refs()
        if not refs:
            return
        groupe = self.groupe_associee.currentData() or ''
        if groupe:
            self._groupes_choisis[refs[0]] = groupe
        else:
            self._groupes_choisis.pop(refs[0], None)

    def inverser(self):
        """La référence associée devient la principale ; la principale, l'associée."""
        refs = self.champ.refs()
        if not refs or self._inversion is None or refs[0] == self._reference:
            return
        nouvelle, ancienne = refs[0], self._reference
        self._inversion(nouvelle, ancienne)     # la fenêtre change la réf. de la pièce
        self._reference = nouvelle
        # Le groupe choisi suit chaque référence (clé = la référence)
        a_declarer = self._a_declarer(nouvelle)
        self._choix_ouvert = self._choix_ouvert or a_declarer
        self.lien_associer.setVisible(False)
        self.groupe_piece.setVisible(a_declarer)
        if a_declarer:
            self._remplir(self.groupe_piece, ORIGINES_ASSOCIEES,
                          self._groupes_choisis.get(nouvelle, ''))
        self.champ.set_refs([ancienne])
        self._maj_bouton()

    # --- Réponse --------------------------------------------------------------------
    @property
    def reference(self) -> str:
        return self._reference

    def reponse(self) -> Tuple[bool, Optional[str]]:
        """(répondu, référence associée). Pièce hors des trois groupes (ni par sa
        forme, ni déclarée, ni choisie ici), ou champ laissé vide : pas de réponse."""
        if not self._origine(self._reference):
            return False, None
        refs = self.champ.refs()
        return (True, refs[0]) if refs else (False, None)

    def origines_declarees(self) -> Dict[str, str]:
        """Groupes choisis ici, pour la pièce et sa réf. associée de forme inconnue
        (à écrire par l'import ; vide si rien n'est à déclarer)."""
        concernees = [self._reference] + self.champ.refs()[:1]
        return {r: self._groupes_choisis[r] for r in concernees
                if r in self._groupes_choisis and self._a_declarer(r)}
