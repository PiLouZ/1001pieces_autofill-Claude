"""Touche Espace = cocher/décocher la case de la ligne courante (v3.89.1).

Qt ne bascule une case à l'Espace que si la cellule courante EST celle de la case :
dès qu'on navigue dans une autre colonne (Référence, Type…), Espace ne fait rien.
La fenêtre des doublons (KeyboardTreeWidget) contournait cela pour elle seule ;
ce module généralise son comportement à toute vue à cases (QTreeWidget,
QTableWidget, ou toute QAbstractItemView).

Seule la ligne courante bascule, comme dans la fenêtre des doublons : la
multi-sélection y sert à autre chose (marquer des groupes distincts) et doit
rester indépendante des cases.
"""

from PyQt5.QtCore import QEvent, QObject, Qt


def basculer_case_courante(vue, colonne=0) -> bool:
    """Bascule la case de la ligne courante. Returns: False si la ligne n'en a pas
    (groupe non cochable, vue sans cases) — la touche suit alors son cours normal."""
    index = vue.currentIndex()
    if not index.isValid():
        return False
    modele = vue.model()
    cible = modele.index(index.row(), colonne, index.parent())
    if not (cible.isValid() and modele.flags(cible) & Qt.ItemIsUserCheckable):
        return False
    etat = modele.data(cible, Qt.CheckStateRole)
    # QTreeWidgetItem se déclare « cochable » par défaut, même sans case affichée
    # (groupes de la fenêtre des doublons) : seule une case réelle porte un état
    if etat is None:
        return False
    # Une case partielle (groupe à moitié coché) devient cochée, comme au clic
    nouvel_etat = Qt.Unchecked if etat == Qt.Checked else Qt.Checked
    return bool(modele.setData(cible, nouvel_etat, Qt.CheckStateRole))


def est_espace_seul(event) -> bool:
    """Espace sans modificateur : Maj/Cmd+Espace gardent leur sens (sélection de
    ligne/colonne dans le tableau principal)."""
    return (event.key() == Qt.Key_Space
            and not (event.modifiers() & ~Qt.KeypadModifier))


class _FiltreEspaceCoche(QObject):
    def __init__(self, vue, colonne):
        super().__init__(vue)
        self._vue = vue
        self._colonne = colonne

    def eventFilter(self, objet, event):
        if (event.type() == QEvent.KeyPress and est_espace_seul(event)
                and basculer_case_courante(self._vue, self._colonne)):
            return True
        return False


def activer_espace_coche(vue, colonne=0):
    """Installe le comportement sur une vue existante (sans la sous-classer)."""
    filtre = _FiltreEspaceCoche(vue, colonne)
    vue.installEventFilter(filtre)
    return filtre
