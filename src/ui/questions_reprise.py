"""
Panneau « À décider » de l'import des fiches du site (refonte, étape 4)

Commun à « Importer les fiches du site » (un lot) et à « Lire une fiche du
site » (une fiche) : il affiche un `QuestionnaireLot` (src/utils/reprise_site/
questions.py) en langage métier :

1. « Ce que l'outil fera sans vous » : un récapitulatif, aucun clic ;
2. « Règles à poser une fois » puis « Questions » : une carte par question,
   avec le nombre de cas, des exemples, la réponse proposée (bouton vert) et
   les autres réponses ; une question répondue se replie (« Modifier ») ;
3. « Appareils connus, valeur différente sur le site » : une carte par groupe
   d'écarts identiques (`GroupeEcart`), avec les deux lignes Outil / Site de
   chaque cas, la valeur qui diffère en couleur ; un clic sur une valeur la
   garde pour ce cas (clé « E:…@fiche:ligne »), les deux boutons du bas
   répondent pour tout le groupe. Sans clic, l'outil est gardé ;
4. « Règles déjà posées » : rappel des règles mémorisées appliquées, avec
   « Revenir sur cette règle ».

Il ne décide rien lui-même : chaque clic appelle `sur_reponse(cle, valeur)` ;
« Voir les lignes » appelle `sur_voir(cle)`. Le parent reconstruit le panneau
(`afficher`) après chaque réponse.
"""

from typing import Callable, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)
import qtawesome as qta

from src.utils.rapprochement_fiche.resultat import CHAMPS_ECARTS
from src.utils.reprise_site.questions import (
    LOT, REGLE, GroupeEcart, Question, QuestionnaireLot, cle_ecart,
)
from .style_manager import StyleManager

_VERT, _GRIS, _BLEU = '#198754', '#adb5bd', '#0b5ed7'
_RECAP = [
    ('deja_liees', "compatibilité(s) déjà dans l'outil : rien ne change"),
    ('deja_couvertes', "appareil(s) déjà relié(s) à une ancienne référence ou à une équivalente "
                       "de la pièce : rien n'est ajouté"),
    ('nouvelles', "compatibilité(s) nouvelle(s) avec des appareils déjà connus"),
    ('remplacements', "ancienne(s) référence(s) (« Remplace les références »)"),
    ('equivalentes', "équivalente(s) de marque reconnue"),
]
_INFOS = [
    ('illisibles', "ligne(s) illisible(s) ne seront pas créées (ex. « C : », parenthèses) : "
                   "leurs fiches passent dans « Fiches à revoir »"),
    ('profils_ambigus', "fiche(s) lisible(s) de plusieurs façons, même résultat"),
    ('doublons', "ligne(s) qui ne sont que le nom commercial d'un appareil déjà cité par la fiche : "
                 "rien n'est ajouté"),
    ('noms_completes', "nom(s) commercial(aux) vide(s) dans l'outil, complété(s) depuis la fiche"),
    ('ecarts_tranches', "valeur(s) déjà tranchée(s) en faveur de l'outil : rien ne change"),
]
_EXEMPLES_ECART = 4                     # cas montrés par carte avant « Voir les N cas »
_LIBRE = {'type': "Autre type", 'marque': "Autre marque", 'etiquette': "Marque d'origine"}


def nombre(n: int) -> str:
    return f"{n:,}".replace(',', ' ')


def libelle_reponse(q: Question, valeur: Optional[str]) -> str:
    if valeur is None:
        return ''
    for v, libelle in q.choix:
        if v == valeur:
            return libelle
    if ':' in valeur:
        genre, texte = valeur.split(':', 1)
        return {'type': f"type {texte}", 'marque': f"marque {texte}",
                'etiquette': f"marque d'origine {texte}"}.get(genre, texte)
    return valeur


class PanneauQuestions(QScrollArea):
    """Récapitulatif et questions d'un lot (ou d'une fiche)."""

    def __init__(self, sur_reponse: Callable[[str, Optional[str]], None],
                 sur_voir: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self.sur_reponse = sur_reponse
        self.sur_voir = sur_voir
        self.types: List[str] = []
        self.marques: List[str] = []
        self.setWidgetResizable(True)
        self.setStyleSheet(StyleManager.ZONE_DEFILEMENT_NUE)
        self._contenu = QWidget()
        self._contenu.setStyleSheet(StyleManager.FOND_TRANSPARENT)
        self._disposition = QVBoxLayout(self._contenu)
        self._disposition.setContentsMargins(4, 4, 4, 4)
        self._disposition.setSpacing(6)
        self.setWidget(self._contenu)
        self.questionnaire: Optional[QuestionnaireLot] = None
        self.cartes = {}                    # clé → QFrame (tests)
        self.cellules = {}                  # (clé « E:…@i:k », 'outil'/'site') → bouton (tests)
        self._deplies = set()               # groupes d'écarts montrés en entier

    # -------------------------------------------------------------------------
    def vider(self, texte: str = ''):
        self.questionnaire = None
        self._effacer()
        if texte:
            etiquette = QLabel(texte)
            etiquette.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
            self._disposition.addWidget(etiquette)
        self._disposition.addStretch(1)

    def _effacer(self):
        self.cartes, self.cellules = {}, {}
        while self._disposition.count():
            item = self._disposition.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()        # sinon redessinée sous la nouvelle carte
                item.widget().deleteLater()

    def afficher(self, q: QuestionnaireLot, entete: str = ''):
        position = self.verticalScrollBar().value()
        self.questionnaire = q
        self._effacer()
        if entete:
            titre = QLabel(entete)
            titre.setStyleSheet(StyleManager.TITRE_SECTION)
            titre.setWordWrap(True)
            self._disposition.addWidget(titre)
        self._recapitulatif(q)
        questions = q.liste()
        regles = [x for x in questions if x.genre == REGLE and not x.memorisee]
        du_lot = [x for x in questions if x.genre == LOT]
        memorisees = [x for x in questions if x.memorisee]
        if regles:
            self._titre("Règles à poser une fois (votre réponse sera mémorisée pour les lots suivants)")
            for x in regles:
                self._carte(x)
        if du_lot:
            self._titre("Questions")
            for x in du_lot:
                self._carte(x)
        ecarts = q.liste_ecarts()
        if ecarts:
            self._titre("Appareils connus, valeur différente sur le site : cliquez celle à garder "
                        "(sans clic, l'outil est gardé)")
            for g in ecarts:
                self._carte_ecart(g)
        if memorisees:
            self._titre("Règles déjà posées, appliquées ici")
            for x in memorisees:
                self._rappel(x)
        if not questions and not ecarts:
            fin = QLabel("Aucune question : tout est décidé.")
            fin.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
            self._disposition.addWidget(fin)
        self._disposition.addStretch(1)
        self.verticalScrollBar().setValue(position)

    # -------------------------------------------------------------------------
    def _titre(self, texte: str):
        t = QLabel(texte)
        t.setStyleSheet(StyleManager.TITRE_SECTION + " margin-top: 8px;")
        t.setWordWrap(True)
        self._disposition.addWidget(t)

    def _recapitulatif(self, q: QuestionnaireLot):
        self._titre("Ce que l'outil fera sans vous")
        r = q.recapitulatif
        if not any(r.get(c) for c, _ in _RECAP):
            self._ligne_recap('fa5s.info-circle', _GRIS, "Rien d'automatique : tout passe par les "
                                                          "questions ci-dessous.")
        for cle, texte in _RECAP:
            if r.get(cle):
                self._ligne_recap('fa5s.check-circle', _VERT, f"{nombre(r[cle])} {texte}")
        for cle, texte in _INFOS:
            if r.get(cle):
                self._ligne_recap('fa5s.info-circle', _BLEU, f"{nombre(r[cle])} {texte}")
        lignes = q.resume()['lignes_a_revoir']
        if lignes:
            self._ligne_recap('fa5s.info-circle', _BLEU,
                              f"{nombre(lignes)} appareil(s) à choisir parmi plusieurs, sans candidat "
                              f"de même référence : ils ne sont pas reliés, leurs fiches passent "
                              f"dans « Fiches à revoir »")

    def _ligne_recap(self, icone: str, couleur: str, texte: str):
        ligne = QHBoxLayout()
        pastille = QLabel()
        pastille.setPixmap(qta.icon(icone, color=couleur).pixmap(14, 14))
        pastille.setFixedWidth(18)
        etiquette = QLabel(texte)
        etiquette.setWordWrap(True)
        ligne.addWidget(pastille, 0, Qt.AlignTop)
        ligne.addWidget(etiquette, 1)
        boite = QWidget()
        boite.setLayout(ligne)
        ligne.setContentsMargins(6, 0, 0, 0)
        self._disposition.addWidget(boite)

    def _cadre(self, repondue: bool) -> QFrame:
        cadre = QFrame()
        cadre.setObjectName('carteQuestion')
        cadre.setStyleSheet(StyleManager.CARTE_QUESTION_REPONDUE if repondue
                            else StyleManager.CARTE_QUESTION)
        return cadre

    def _carte(self, q: Question):
        cadre = self._cadre(q.repondue)
        self.cartes[q.cle] = cadre
        v = QVBoxLayout(cadre)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        entete = QHBoxLayout()
        pastille = QLabel()
        pastille.setPixmap(qta.icon('fa5s.check-circle' if q.repondue else 'fa5.circle',
                                    color=_VERT if q.repondue else _GRIS).pixmap(16, 16))
        titre = QLabel(f"<b>{q.titre}</b>")
        titre.setWordWrap(True)
        titre.setTextFormat(Qt.RichText)
        compte = QLabel(f"{nombre(q.cas)} cas · {q.fiches} fiche(s)")
        compte.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        entete.addWidget(pastille, 0, Qt.AlignTop)
        entete.addWidget(titre, 1)
        entete.addWidget(compte, 0, Qt.AlignTop)
        v.addLayout(entete)
        if q.repondue:
            ligne = QHBoxLayout()
            reponse = QLabel(f"Réponse : {libelle_reponse(q, q.reponse)}")
            reponse.setStyleSheet(StyleManager.TEXTE_GRIS_MOYEN)
            modifier = QPushButton("Modifier")
            modifier.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
            modifier.clicked.connect(lambda _, c=q.cle: self.sur_reponse(c, None))
            ligne.addSpacing(22)
            ligne.addWidget(reponse, 1)
            self._bouton_voir(ligne, q)
            ligne.addWidget(modifier)
            v.addLayout(ligne)
            self._disposition.addWidget(cadre)
            return
        if q.exemples:
            ex = QLabel("Par exemple : " + " ; ".join(q.exemples))
            ex.setWordWrap(True)
            ex.setStyleSheet(StyleManager.TEXTE_SECONDAIRE + " margin-left: 22px;")
            v.addWidget(ex)
        if q.explication:
            ex = QLabel(q.explication)
            ex.setWordWrap(True)
            ex.setStyleSheet(StyleManager.TEXTE_SECONDAIRE_ITALIQUE + " margin-left: 22px;")
            v.addWidget(ex)
        boutons = QHBoxLayout()
        boutons.addSpacing(22)
        if q.proposition is not None and not any(v_ == q.proposition for v_, _ in q.choix):
            self._choix(boutons, q, q.proposition, libelle_reponse(q, q.proposition), True)
        for valeur, libelle in q.choix:
            self._choix(boutons, q, valeur, libelle, valeur == q.proposition)
        if q.libre:
            self._saisie_libre(boutons, q)
        boutons.addStretch(1)
        self._bouton_voir(boutons, q)
        v.addLayout(boutons)
        self._disposition.addWidget(cadre)

    def _choix(self, disposition, q: Question, valeur: str, libelle: str, propose: bool):
        b = QPushButton(libelle + (" (proposé)" if propose else ''))
        b.setStyleSheet(StyleManager.CHOIX_PROPOSE_BUTTON if propose
                        else StyleManager.SECONDARY_COMPACT_BUTTON)
        b.setProperty('valeur', valeur)
        b.clicked.connect(lambda _, c=q.cle, val=valeur: self.sur_reponse(c, val))
        disposition.addWidget(b)

    def _saisie_libre(self, disposition, q: Question):
        if q.libre == 'etiquette':
            champ = QLineEdit()
            champ.setPlaceholderText("ex. Bauknecht")
            champ.setFixedWidth(140)
            lire = champ.text
        else:
            champ = QComboBox()
            champ.setEditable(True)
            champ.addItem('')
            champ.addItems(self.types if q.libre == 'type' else
                           self._marques_proposees(q) + [m for m in self.marques
                                                         if m not in self._marques_proposees(q)])
            champ.setMinimumWidth(160)
            lire = champ.currentText
        valider = QPushButton(_LIBRE[q.libre] + " : valider")
        valider.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        valider.clicked.connect(
            lambda _, c=q.cle, g=q.libre, f=lire: f().strip() and self.sur_reponse(c, f"{g}:{f().strip()}"))
        disposition.addWidget(champ)
        disposition.addWidget(valider)

    def _marques_proposees(self, q: Question) -> List[str]:
        """Marques annoncées par la fiche d'une question Q3, en tête de liste."""
        lot = self.questionnaire.lot if self.questionnaire else None
        if lot is None or not q.occurrences:
            return []
        return list(dict.fromkeys(lot.fiches[q.occurrences[0][0]].marques_annoncees))

    def _bouton_voir(self, disposition, q: Question):
        if self.sur_voir is None or not q.cle[:1] in ('R', 'Q') or q.cle in ('R5', 'R6', 'R7', 'Q6', 'Q7'):
            return
        voir = QPushButton(qta.icon('fa5s.list', color='#555555'), "Voir les lignes")
        voir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        voir.clicked.connect(lambda _, c=q.cle: self.sur_voir(c))
        disposition.addWidget(voir)

    # --- Écarts outil / site ------------------------------------------------------
    def _carte_ecart(self, g: GroupeEcart):
        decide = g.reponse is not None or all((i, k) in g.choix for i, k, _ in g.cas)
        cadre = self._cadre(decide)
        self.cartes[g.cle] = cadre
        v = QVBoxLayout(cadre)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        entete = QHBoxLayout()
        pastille = QLabel()
        pastille.setPixmap(qta.icon('fa5s.check-circle' if decide else 'fa5s.exchange-alt',
                                    color=_VERT if decide else '#e0a800').pixmap(16, 16))
        titre = QLabel(f"<b>{g.titre}</b>")
        titre.setTextFormat(Qt.RichText)
        titre.setWordWrap(True)
        compte = QLabel(f"{nombre(len(g.cas))} cas · {g.fiches} fiche(s)")
        compte.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        entete.addWidget(pastille, 0, Qt.AlignTop)
        entete.addWidget(titre, 1)
        entete.addWidget(compte, 0, Qt.AlignTop)
        v.addLayout(entete)
        cas = g.cas if g.cle in self._deplies else g.cas[:_EXEMPLES_ECART]
        for i, k, _ in cas[:200]:
            grille = self._comparaison(g, i, k)
            if grille is not None:
                v.addWidget(grille)
        boutons = QHBoxLayout()
        boutons.addSpacing(22)
        n = len(g.cas)
        if n > _EXEMPLES_ECART:
            plus = QPushButton(f"Voir les {nombre(n)} cas" if g.cle not in self._deplies
                               else "Réduire")
            plus.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
            plus.clicked.connect(lambda _, c=g.cle: self._deplier(c))
            boutons.addWidget(plus)
        boutons.addStretch(1)
        if g.reponse is not None:
            reponse = QLabel("Pour tous : " + ("valeur de l'outil" if g.reponse == 'outil'
                                                else "valeur du site"))
            reponse.setStyleSheet(StyleManager.TEXTE_GRIS_MOYEN)
            modifier = QPushButton("Modifier")
            modifier.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
            modifier.clicked.connect(lambda _, c=g.cle: self.sur_reponse(c, None))
            boutons.addWidget(reponse)
            boutons.addWidget(modifier)
        else:
            pluriel = f" ({nombre(n)})" if n > 1 else ''
            garder = QPushButton(f"Garder l'outil{pluriel}")
            garder.setStyleSheet(StyleManager.CHOIX_PROPOSE_BUTTON)
            garder.setProperty('valeur', 'outil')
            garder.clicked.connect(lambda _, c=g.cle: self.sur_reponse(c, 'outil'))
            prendre = QPushButton(f"Prendre le site{pluriel}")
            prendre.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
            prendre.setProperty('valeur', 'site')
            prendre.clicked.connect(lambda _, c=g.cle: self.sur_reponse(c, 'site'))
            boutons.addWidget(garder)
            boutons.addWidget(prendre)
        v.addLayout(boutons)
        self._disposition.addWidget(cadre)

    def _deplier(self, cle: str):
        (self._deplies.discard if cle in self._deplies else self._deplies.add)(cle)
        if self.questionnaire is not None:
            self.afficher(self.questionnaire)

    def _comparaison(self, g: GroupeEcart, i: int, k: int) -> Optional[QWidget]:
        """Deux lignes, Outil puis Site, de l'appareil (i, k) ; chaque valeur qui
        diffère est un bouton qui la garde pour ce cas."""
        q = self.questionnaire
        f = q.lot.fiches[i]
        a = f.rapprochement.appareils[k]
        ecarts = {e.champ: e for e in a.ecarts if not e.tranche and not e.a_completer}
        e0 = next(iter(ecarts.values()), None)
        if e0 is None:
            return None
        c = next((c for c in a.candidats if c.id == e0.appareil_id), None)
        outil = {'marque': c.marque if c else '', 'ref': c.ref_modele if c else '',
                 'type': c.type if c else '', 'nom': ''}
        site = {'marque': a.marque or outil['marque'], 'ref': a.ref_modele,
                'type': a.type_site or outil['type'], 'nom': a.nom}
        for champ, e in ecarts.items():
            outil[champ], site[champ] = e.outil, e.site
        champs = ['marque', 'ref', 'type'] + (['nom'] if a.nom or 'nom' in ecarts else [])
        boite = QWidget()
        grille = QGridLayout(boite)
        grille.setContentsMargins(22, 2, 0, 2)
        grille.setHorizontalSpacing(6)
        grille.setVerticalSpacing(3)
        ligne_fiche = f"ligne {a.numero}" if a.numero else "table du site"
        # Fiche seule (n° de produit inconnu) : la ligne suffit
        origine = QLabel(f"fiche {f.id_produit} · {ligne_fiche}" if f.id_produit else ligne_fiche)
        origine.setStyleSheet(StyleManager.ECART_ENTETE)
        grille.addWidget(origine, 0, 0)
        for col, champ in enumerate(champs, 1):
            t = QLabel(CHAMPS_ECARTS[champ][0])
            t.setStyleSheet(StyleManager.ECART_ENTETE)
            grille.addWidget(t, 0, col)
        for ligne, (cote, nom_ligne, valeurs) in enumerate(
                (('outil', "Outil", outil), ('site', "Site", site)), 1):
            etiquette = QLabel(nom_ligne)
            etiquette.setStyleSheet(StyleManager.ECART_LIGNE)
            grille.addWidget(etiquette, ligne, 0)
            for col, champ in enumerate(champs, 1):
                texte = valeurs[champ] or '—'
                e = ecarts.get(champ)
                if e is None:
                    cellule = QLabel(texte)
                    cellule.setStyleSheet(StyleManager.ECART_EGALE)
                    grille.addWidget(cellule, ligne, col)
                    continue
                cle = f"{cle_ecart(e)}@{i}:{k}"
                groupe = q.ecarts.get(cle_ecart(e))
                decision = groupe.decision(i, k) if groupe is not None else None
                bouton = QPushButton(texte)
                bouton.setCursor(Qt.PointingHandCursor)
                bouton.setToolTip("Garder la valeur de l'outil" if cote == 'outil'
                                  else "Prendre la valeur du site")
                if decision is None:
                    style = StyleManager.ECART_DEFAUT if cote == 'outil' else StyleManager.ECART_DIFFERENT
                elif decision == cote:
                    style = StyleManager.ECART_CHOISI
                else:
                    style = StyleManager.ECART_ECARTE
                bouton.setStyleSheet(style)
                bouton.clicked.connect(lambda _, c=cle, v=cote: self.sur_reponse(c, v))
                self.cellules[(cle, cote)] = bouton
                grille.addWidget(bouton, ligne, col)
        grille.setColumnStretch(len(champs) + 1, 1)
        return boite

    def _rappel(self, q: Question):
        cadre = self._cadre(True)
        self.cartes[q.cle] = cadre
        h = QHBoxLayout(cadre)
        h.setContentsMargins(10, 6, 10, 6)
        pastille = QLabel()
        pastille.setPixmap(qta.icon('fa5s.check-circle', color=_VERT).pixmap(14, 14))
        texte = QLabel(f"{q.titre} <b>{libelle_reponse(q, q.reponse)}</b> · appliquée à "
                       f"{nombre(q.cas)} cas")
        texte.setTextFormat(Qt.RichText)
        texte.setWordWrap(True)
        revenir = QPushButton("Revenir sur cette règle")
        revenir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        revenir.clicked.connect(lambda _, c=q.cle: self.sur_reponse(c, None))
        h.addWidget(pastille, 0, Qt.AlignTop)
        h.addWidget(texte, 1)
        h.addWidget(revenir)
        self._disposition.addWidget(cadre)


# Vocabulaire métier des tables de détail (les deux fenêtres)
NIVEAUX_METIER = {
    'exact': "identique dans l'outil",
    'exact_multiple': "plusieurs appareils de même référence",
    'normalise': "identique à la ponctuation près",
    'normalise_ambigu': "plusieurs écritures dans l'outil",
    'a_valider': "retrouvé ailleurs, à confirmer",
    'absent': "inconnu de l'outil, à créer",
}
LIENS_METIER = {
    'deja_lie': "déjà dans l'outil",
    'deja_couvert': "déjà couverte par une ancienne référence",
    'nouveau': "nouvelle",
    '': "à décider",
}
PROVENANCES_METIER = {'description': "description", 'table': "table du site", 'les_deux': "les deux"}
