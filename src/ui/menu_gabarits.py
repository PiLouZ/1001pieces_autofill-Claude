"""
Menu des gabarits d'un bouton à profils (Titre, HTML Détails…), v3.99.4

Liste triée par ordre alphanumérique naturel. À partir de SEUIL_RECHERCHE
gabarits, le menu gagne :
- un champ « Filtrer… » en tête, qui a le focus à l'ouverture : on tape
  directement (casse et accents ignorés, tous les mots doivent figurer) ;
  ↑/↓ parcourent les résultats, Entrée lance le gabarit en surbrillance (le
  premier par défaut), Échap ferme ;
- une section « Récents » : les NB_RECENTS derniers gabarits choisis dans ce
  menu, du plus récent au plus ancien, masquée pendant le filtrage.

Les récents sont mémorisés par poste (QSettings), pas dans
data/export_config.json, suivi par git.
"""

from ..utils.qt_imports import QMenu, QAction, QWidget, QHBoxLayout, QLineEdit, QWidgetAction, QFont, QTimer, QEvent, Qt
from src.utils.text_utils import cle_tri_naturel, strip_accents


# Nombre de noms conservés en réglages : plus que NB_RECENTS, pour qu'un gabarit
# supprimé ou renommé laisse encore assez de récents à afficher
NB_RECENTS_MEMORISES = 10


def lire_recents(settings, cle):
    """Noms mémorisés sous `cle`, du plus récent au plus ancien ([] si aucun)."""
    if settings is None:
        return []
    valeur = settings.value(cle, [])
    # QSettings (plist macOS) rend une chaîne seule pour une liste d'un élément
    if isinstance(valeur, str):
        return [valeur] if valeur else []
    return [str(v) for v in (valeur or []) if v]


def noter_recent(settings, cle, nom):
    """Placer `nom` en tête des récents de `cle`, sans doublon."""
    if settings is None or not nom:
        return
    recents = [nom] + [n for n in lire_recents(settings, cle) if n != nom]
    settings.setValue(cle, recents[:NB_RECENTS_MEMORISES])


def _normaliser(texte):
    return strip_accents(texte).casefold()


class MenuGabarits(QMenu):
    """Menu des gabarits autres que celui par défaut (le clic principal du bouton)."""

    SEUIL_RECHERCHE = 6
    NB_RECENTS = 3

    def __init__(self, parent, noms, nom_defaut, settings_fn, cle_recents):
        """
        Args:
            noms: tous les gabarits configurés (ordre indifférent).
            nom_defaut: gabarit du clic principal, exclu du menu.
            settings_fn: fonction rendant l'objet QSettings (lu à chaque usage :
                les réglages de la fenêtre peuvent être créés après le menu).
            cle_recents: clé QSettings des récents de ce bouton.
        """
        super().__init__(parent)
        self._settings_fn = settings_fn
        self._cle_recents = cle_recents
        self._noms = sorted((n for n in noms if n != nom_defaut), key=cle_tri_naturel)
        self._actions_recents = []
        self.triggered.connect(self._noter_choix)

        self.avec_recherche = len(self._noms) >= self.SEUIL_RECHERCHE
        if not self.avec_recherche:
            for nom in self._noms:
                self._ajouter_gabarit(nom)
            return

        self.champ_filtre = QLineEdit()
        self.champ_filtre.setPlaceholderText("Filtrer…")
        self.champ_filtre.setClearButtonEnabled(True)
        self.champ_filtre.setMinimumWidth(220)
        self.champ_filtre.textChanged.connect(self._filtrer)
        self.champ_filtre.installEventFilter(self)
        conteneur = QWidget()
        disposition = QHBoxLayout(conteneur)
        disposition.setContentsMargins(6, 4, 6, 4)
        disposition.addWidget(self.champ_filtre)
        action_filtre = QWidgetAction(self)
        action_filtre.setDefaultWidget(conteneur)
        self.addAction(action_filtre)

        self._entete_recents = self._ajouter_entete("Récents")
        self._entete_tous = self._ajouter_entete("Tous")
        self._actions_tous = [self._ajouter_gabarit(nom) for nom in self._noms]
        self._aucun = self.addAction("Aucun gabarit ne correspond")
        self._aucun.setEnabled(False)
        self._aucun.setVisible(False)
        self.aboutToShow.connect(self._preparer)

    # ─── Construction ────────────────────────────────────────────────────

    def _ajouter_gabarit(self, nom, avant=None):
        action = self.addAction(nom) if avant is None else self._inserer(nom, avant)
        action.setData(nom)
        return action

    def _inserer(self, nom, avant):
        action = QAction(nom, self)
        self.insertAction(avant, action)
        return action

    def _ajouter_entete(self, texte):
        # Action inactive plutôt que addSection() : les styles Fusion et macOS
        # n'affichent pas le texte des sections
        entete = self.addAction(texte)
        entete.setEnabled(False)
        police = QFont(entete.font())
        police.setBold(True)
        entete.setFont(police)
        return entete

    # ─── Ouverture : récents à jour, filtre vidé ─────────────────────────

    def _preparer(self):
        for action in self._actions_recents:
            self.removeAction(action)
            action.deleteLater()
        recents = [n for n in lire_recents(self._settings_fn(), self._cle_recents)
                   if n in self._noms][:self.NB_RECENTS]
        self._actions_recents = [self._ajouter_gabarit(n, avant=self._entete_tous) for n in recents]
        self.champ_filtre.blockSignals(True)
        self.champ_filtre.clear()
        self.champ_filtre.blockSignals(False)
        self._filtrer("")
        QTimer.singleShot(0, self.champ_filtre.setFocus)

    # ─── Filtrage ────────────────────────────────────────────────────────

    def _filtrer(self, texte):
        mots = _normaliser(texte).split()
        filtrage = bool(mots)
        self._entete_recents.setVisible(not filtrage and bool(self._actions_recents))
        for action in self._actions_recents:
            action.setVisible(not filtrage)
        self._entete_tous.setVisible(not filtrage)
        for action in self._actions_tous:
            nom = _normaliser(action.text())
            action.setVisible(all(m in nom for m in mots))
        visibles = self._actions_choisissables()
        self._aucun.setVisible(filtrage and not visibles)
        self.setActiveAction(visibles[0] if filtrage and visibles else None)

    def _actions_choisissables(self):
        return [a for a in self._actions_recents + self._actions_tous if a.isVisible()]

    # ─── Clavier dans le champ de filtre ─────────────────────────────────

    def eventFilter(self, objet, evenement):
        if objet is getattr(self, 'champ_filtre', None) and evenement.type() == QEvent.KeyPress:
            touche = evenement.key()
            if touche in (Qt.Key_Down, Qt.Key_Up):
                self._deplacer(1 if touche == Qt.Key_Down else -1)
                return True
            if touche in (Qt.Key_Return, Qt.Key_Enter):
                self._lancer_selection()
                return True
            if touche == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(objet, evenement)

    def _deplacer(self, pas):
        visibles = self._actions_choisissables()
        if not visibles:
            return
        courante = self.activeAction()
        if courante in visibles:
            index = (visibles.index(courante) + pas) % len(visibles)
        else:
            index = 0 if pas > 0 else len(visibles) - 1
        self.setActiveAction(visibles[index])
        self.champ_filtre.setFocus()

    def _lancer_selection(self):
        visibles = self._actions_choisissables()
        courante = self.activeAction()
        action = courante if courante in visibles else (visibles[0] if visibles else None)
        if action is None:
            return
        self.close()
        action.trigger()

    # ─── Mémorisation ────────────────────────────────────────────────────

    def _noter_choix(self, action):
        noter_recent(self._settings_fn(), self._cle_recents, action.data())
