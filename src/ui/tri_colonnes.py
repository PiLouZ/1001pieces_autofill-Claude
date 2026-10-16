"""Tri par clic sur l'en-tête des fenêtres en arbre (v3.89.0).

Partagé par « Valider les suggestions » et « Auto-complétés à vérifier ». Le tri
alphabétique de Qt rangerait « 100 % » avant « 92 % » et « Probable » avant
« Quasi-certain » : chaque cellule peut porter une clé de tri (ROLE_TRI), à
défaut le texte sans casse est comparé.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTreeWidgetItem

ROLE_TRI = Qt.UserRole + 20


class ItemTriable(QTreeWidgetItem):
    """QTreeWidgetItem comparé sur sa clé de tri, colonne par colonne."""

    def __lt__(self, other):
        arbre = self.treeWidget()
        col = arbre.sortColumn() if arbre is not None else 0
        a, b = self.data(col, ROLE_TRI), other.data(col, ROLE_TRI)
        if a is None or b is None or type(a) is not type(b):
            if col == 0 and self.flags() & Qt.ItemIsUserCheckable:
                return int(self.checkState(0)) < int(other.checkState(0))
            return self.text(col).lower() < other.text(col).lower()
        return a < b


def activer_tri(arbre):
    """Tri au clic sur l'en-tête, en gardant l'ordre de remplissage à l'ouverture
    (aucune colonne de tri tant que l'utilisateur n'a pas cliqué)."""
    arbre.header().setSortIndicator(-1, Qt.AscendingOrder)
    arbre.setSortingEnabled(True)
    arbre.header().setSortIndicatorShown(True)


class TriSuspendu:
    """Bloc `with` : tri désactivé pendant un remplissage (un item déjà trié
    bougerait à chaque setText), rétabli ensuite sur la même colonne."""

    def __init__(self, arbre):
        self._arbre = arbre

    def __enter__(self):
        entete = self._arbre.header()
        self._colonne = entete.sortIndicatorSection()
        self._ordre = entete.sortIndicatorOrder()
        self._actif = self._arbre.isSortingEnabled()
        self._arbre.setSortingEnabled(False)
        return self

    def __exit__(self, *exc):
        if self._actif:
            self._arbre.header().setSortIndicator(self._colonne, self._ordre)
            self._arbre.setSortingEnabled(True)
        return False
