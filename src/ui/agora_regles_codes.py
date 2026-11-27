"""
« Règles des codes produit » : comment l'outil propose le code produit EMG
(référence PrestaShop = code Cogilog) d'une fiche nouvelle (src/utils/agora/codes.py).

Une ligne par règle, dans l'ordre d'application : la première qui s'applique
donne le code. Zone de test en bas. « Enregistrer » écrit data/regles_codes.json.
Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from src.core.logger import app_logger
from src.utils.agora.codes import (REGLES_PAR_DEFAUT, RegleCode, charger_regles, code_produit,
                                   enregistrer_regles)
from src.utils.agora.myspace import CONSTRUCTEURS
from .style_manager import StyleManager

_COLONNES = ["Nom", "Constructeurs Agora", "Motif de la référence", "Retirer au début", "Préfixe"]


def _constructeurs(texte: str) -> List[int]:
    return [int(x) for x in texte.replace(';', ',').replace(' ', ',').split(',') if x.strip().isdigit()]


class ReglesCodesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Règles des codes produit")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(900, 460)
        self._construire()
        self._remplir(charger_regles())

    def _construire(self):
        racine = QVBoxLayout(self)
        aide = QLabel(
            "Code produit d'une fiche nouvelle (référence PrestaShop = code Cogilog), calculé sur la "
            "référence la plus récente. La première règle qui s'applique l'emporte. Constructeurs : "
            "numéros Agora séparés par des virgules (vide = tous) — "
            + ", ".join(f"{n} {nom}" for n, nom in CONSTRUCTEURS.items())
            + ". Motif : jokers * et ? (vide = toutes les références).")
        aide.setWordWrap(True)
        aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(aide)

        self.table = QTableWidget(0, len(_COLONNES))
        self.table.setHorizontalHeaderLabels(_COLONNES)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda *_: self._tester())
        racine.addWidget(self.table, 1)

        boutons = QHBoxLayout()
        for libelle, action in (("Ajouter", self._ajouter), ("Supprimer", self._supprimer),
                                ("Monter", lambda: self._deplacer(-1)),
                                ("Descendre", lambda: self._deplacer(1)),
                                ("Règles par défaut", lambda: self._remplir(REGLES_PAR_DEFAUT))):
            b = QPushButton(libelle)
            b.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
            b.clicked.connect(action)
            boutons.addWidget(b)
        boutons.addStretch(1)
        racine.addLayout(boutons)

        test = QHBoxLayout()
        test.addWidget(QLabel("Tester :"))
        self.test_ref = QLineEdit()
        self.test_ref.setPlaceholderText("référence, ex : 00611323")
        self.test_ref.textChanged.connect(self._tester)
        test.addWidget(self.test_ref, 1)
        self.test_constructeur = QComboBox()
        self.test_constructeur.addItem("Constructeur…", None)
        for n, nom in CONSTRUCTEURS.items():
            self.test_constructeur.addItem(f"{nom} ({n})", n)
        self.test_constructeur.currentIndexChanged.connect(self._tester)
        test.addWidget(self.test_constructeur)
        self.resultat = QLabel("")
        self.resultat.setMinimumWidth(220)
        test.addWidget(self.resultat)
        racine.addLayout(test)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        pied.addWidget(self.etat, 1)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        enregistrer = QPushButton("Enregistrer")
        enregistrer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        enregistrer.clicked.connect(self._enregistrer)
        pied.addWidget(fermer)
        pied.addWidget(enregistrer)
        racine.addLayout(pied)

    # --- Table ----------------------------------------------------------------------
    def _remplir(self, regles: List[RegleCode]):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for r in regles:
            self._ajouter_ligne(r)
        self.table.blockSignals(False)
        self._tester()

    def _ajouter_ligne(self, r: RegleCode, position: Optional[int] = None):
        i = self.table.rowCount() if position is None else position
        self.table.insertRow(i)
        valeurs = [r.nom, ", ".join(str(n) for n in r.constructeurs), r.motif, r.retirer, r.prefixe]
        for j, v in enumerate(valeurs):
            self.table.setItem(i, j, QTableWidgetItem(v))

    def regles(self) -> List[RegleCode]:
        texte = lambda i, j: (self.table.item(i, j).text().strip() if self.table.item(i, j) else '')
        return [RegleCode(nom=texte(i, 0) or f"Règle {i + 1}", constructeurs=_constructeurs(texte(i, 1)),
                          motif=texte(i, 2), retirer=texte(i, 3), prefixe=texte(i, 4))
                for i in range(self.table.rowCount())]

    def _ajouter(self):
        self._ajouter_ligne(RegleCode("Nouvelle règle"), max(0, self.table.currentRow() + 1)
                            if self.table.currentRow() >= 0 else None)

    def _supprimer(self):
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())
            self._tester()

    def _deplacer(self, sens: int):
        i = self.table.currentRow()
        j = i + sens
        if i < 0 or not 0 <= j < self.table.rowCount():
            return
        regles = self.regles()
        regles[i], regles[j] = regles[j], regles[i]
        self._remplir(regles)
        self.table.setCurrentCell(j, 0)

    # --- Test et enregistrement -------------------------------------------------------
    def _tester(self, *_):
        ref = self.test_ref.text().strip() if hasattr(self, 'test_ref') else ''
        if not ref:
            self.resultat.setText("")
            return
        code = code_produit(ref, self.test_constructeur.currentData(), self.regles())
        self.resultat.setText(f"→ <b>{code}</b>" if code else "→ aucune règle")

    def _enregistrer(self):
        try:
            enregistrer_regles(self.regles())
        except OSError as e:
            app_logger.error(f"[Agora] règles des codes non enregistrées : {e}")
            self.etat.setText(f"Enregistrement impossible : {e}")
            return
        self.etat.setText("Règles enregistrées.")
