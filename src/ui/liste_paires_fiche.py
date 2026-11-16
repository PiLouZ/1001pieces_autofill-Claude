"""
Liste des paires de réf. associées d'une fiche du site, dans la fenêtre d'import
(CDC docs/cdc_import_fiches_site.md, § 5.4)

Une ligne par paire trouvée sur les lignes « Remplace » et « Équivalentes » :
case cochée = la paire sera liée ; décochée = elle ne l'est pas. Une paire
déjà liée, ou en conflit avec une réponse déjà donnée, est montrée sans case
modifiable, avec sa raison. Les suites de références qui n'ont pas pu être
liées (nombre impair, même groupe côte à côte) sont listées en dessous.

`compact=True` (carte d'un lot) : un bouton « Paires (n) » déplie la liste.
Le choix est porté par la fiche (`FicheAImporter.paires_decochees`).
"""

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from .style_manager import StyleManager

_STATUTS = {'nouveau': "à lier", 'deja_present': "déjà liées", 'conflit': "non liée"}


class ListePairesFiche(QWidget):
    """Paires de réf. associées d'une fiche, à cocher."""

    def __init__(self, parent=None, compact: bool = False,
                 au_changement: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.compact = compact
        self.au_changement = au_changement
        self.fiche = None
        self.cases = {}                 # clé de la paire → QCheckBox
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.titre = QToolButton() if compact else QLabel()
        if compact:
            self.titre.setCheckable(True)
            self.titre.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.titre.setArrowType(Qt.RightArrow)
            self.titre.setAutoRaise(True)
            self.titre.toggled.connect(self._deplier)
        self.titre.setStyleSheet(StyleManager.LIBELLE_PETIT_TRANSPARENT)
        layout.addWidget(self.titre)
        self.contenu = QWidget()
        self.lignes = QVBoxLayout(self.contenu)
        self.lignes.setContentsMargins(12 if compact else 0, 0, 0, 0)
        self.lignes.setSpacing(1)
        layout.addWidget(self.contenu)
        self.contenu.setVisible(not compact)
        self.setVisible(False)

    # ------------------------------------------------------------------
    def definir(self, fiche) -> None:
        """Remplit la liste avec les paires de `fiche` (FicheAImporter)."""
        self.fiche = fiche
        while self.lignes.count():
            item = self.lignes.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.cases = {}
        a = fiche.apercu_paires() if fiche is not None else {'paires': [], 'non_liees': []}
        for p in a['paires']:
            self.lignes.addWidget(self._ligne_paire(p))
        for n in a['non_liees']:
            texte = QLabel(f"{n['ligne']} · {' '.join(n['references'])} — non liées : "
                           f"{n['raison']}")
            texte.setWordWrap(True)
            texte.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
            self.lignes.addWidget(texte)
        self.setVisible(bool(a['paires'] or a['non_liees']))
        self._titre()

    def _ligne_paire(self, p) -> QWidget:
        ligne = QWidget()
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        case = QCheckBox(f"{p['ligne']} · {p['principale']} ⇄ {p['associee']}")
        case.setChecked(p['cochee'] or p['statut'] == 'deja_present')
        case.setEnabled(p['modifiable'])
        case.setStyleSheet(StyleManager.LIBELLE_PETIT_TRANSPARENT)
        if p['modifiable']:
            case.setToolTip("Décochée : les deux références ne sont pas liées.")
            case.toggled.connect(lambda coche, cle=p['cle']: self._basculer(cle, coche))
            self.cases[p['cle']] = case
        h.addWidget(case)
        statut = _STATUTS.get(p['statut'], p['statut'])
        etat = QLabel(f"{statut} : {p['raison']}" if p['raison'] else statut)
        etat.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT if p['statut'] == 'conflit'
                           else StyleManager.TEXTE_SECONDAIRE)
        h.addWidget(etat, 1)
        return ligne

    def _basculer(self, cle, coche: bool) -> None:
        if self.fiche is None:
            return
        if coche:
            self.fiche.paires_decochees.discard(cle)
        else:
            self.fiche.paires_decochees.add(cle)
        self._titre()
        if self.au_changement is not None:
            self.au_changement()

    def _titre(self) -> None:
        n = self.fiche.apercu_paires()['a_lier'] if self.fiche is not None else 0
        self.titre.setText(f"Paires de réf. associées ({n} à lier)")

    def _deplier(self, ouvert: bool) -> None:
        self.contenu.setVisible(ouvert)
        self.titre.setArrowType(Qt.DownArrow if ouvert else Qt.RightArrow)
