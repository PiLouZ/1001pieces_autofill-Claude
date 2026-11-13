"""
Fenêtre « Importer les fiches du site » : import en masse, lot par lot
(CDC docs/cdc_import_fiches_site.md, § 7.2 à 7.4, § 10.12 à 10.16)

Un lot de fiches est un import de plusieurs fichiers (une carte par fiche), comme
des PDF. Cette fenêtre ne garde que ce qui est propre au massif :
- les exports : les deux CSV PrestaShop (produits avec description ; compatibilités).
  Un export différent de celui de l'import en cours est signalé : « Repartir de
  zéro » ou « Continuer » ;
- l'avancement : dernier produit importé, lots enregistrés, fiches mises de côté,
  fiches à refaire depuis les PDF. On peut fermer à tout moment et reprendre au
  lot suivant ; relancer un lot ne double rien ;
- « Lire le lot suivant » (thread, progression, « Arrêter ») : les fiches sont
  lues et planifiées par les règles de l'import, sans question, puis la fenêtre
  d'import habituelle s'ouvre avec une carte par fiche (`ouvrir_import_lot`).
  « Importer » écrit le lot comme un import de plusieurs fichiers, puis clôt le
  lot (journal, fiches de côté, avancement).
- « Fiches mises de côté » : les relire et les importer ; « Fiches à refaire » :
  la liste des fiches aux données en vrac (`FichesARefaireDialog`).

Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import os
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.services.reprise_site_service import (
    EXPORT_DIFFERENT, EXPORT_IDENTIQUE, RepriseSiteService,
)
from src.utils.boites import choisir_fichier_a_ouvrir
from .style_manager import StyleManager

_DOSSIER_DEFAUT = Path(__file__).resolve().parents[2] / 'data' / 'reprise_site'
_CLE_PRODUITS = 'reprise_site/export_produits'
_CLE_COMPAT = 'reprise_site/export_compatibilites'
_CLE_TAILLE = 'reprise_site/taille_lot'


def _reglages() -> QSettings:
    """Réglages de la fenêtre, avec ceux de l'application (pas le domaine par défaut
    de Qt, partagé avec tout programme lancé par le même Python, tests compris)."""
    fichier = os.environ.get('AUTOFILL_REGLAGES_INI')    # tests : fichier à part
    if fichier:
        return QSettings(fichier, QSettings.IniFormat)
    return QSettings("1001pieces", "autofill")


class _Tache(QThread):
    """Exécute `fonction(progression, annule)` hors du thread principal."""
    progression = pyqtSignal(int, int, str)
    termine = pyqtSignal(object, str)       # résultat, erreur

    def __init__(self, fonction: Callable, parent=None):
        super().__init__(parent)
        self.fonction = fonction
        self.arret = threading.Event()

    def run(self):
        try:
            resultat = self.fonction(lambda i, n, t: self.progression.emit(i, n, t),
                                     self.arret.is_set)
            self.termine.emit(resultat, '')
        except Exception as e:
            app_logger.error(f"[Reprise site] tâche interrompue : {type(e).__name__} : {e}")
            self.termine.emit(None, f"{type(e).__name__} : {e}")


class RepriseSiteDialog(QDialog):
    """Import des fiches du site, lot par lot, par la fenêtre d'import."""

    def __init__(self, db_manager, main_window=None, service: Optional[RepriseSiteService] = None,
                 on_lot_enregistre: Optional[Callable] = None):
        super().__init__(main_window)
        self.setWindowTitle("Importer les fiches du site")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(900, 360)
        self.db = db_manager
        self.main_window = main_window
        self.on_lot_enregistre = on_lot_enregistre
        self.service = service or RepriseSiteService(db_manager, main_window)
        self.lot = None
        self.plan = None
        self.cartes = []
        self._tache: Optional[_Tache] = None
        self._signature = None
        self._import_en_cours = False
        self._construire()
        self._charger_chemins()
        self._rafraichir_etat()

    # =========================================================================
    # Construction
    # =========================================================================
    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)

        titre = QLabel("Exports du site (CSV de la base PrestaShop)")
        titre.setStyleSheet(StyleManager.TITRE_SECTION)
        racine.addWidget(titre)
        self.champ_produits = self._ligne_fichier(racine, "Produits :", "Export des produits")
        self.champ_compat = self._ligne_fichier(racine, "Compatibilités :", "Export des compatibilités")
        choisir = QHBoxLayout()
        self.bouton_export = QPushButton(qta.icon('fa5s.file-import', color='#555555'),
                                         "Utiliser ces exports")
        self.bouton_export.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_export.clicked.connect(self._examiner_export)
        self.bouton_zero = QPushButton(qta.icon('fa5s.redo', color='#555555'), "Repartir de zéro")
        self.bouton_zero.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_zero.clicked.connect(lambda: self._adopter(True))
        self.bouton_continuer = QPushButton(qta.icon('fa5s.forward', color='#555555'),
                                            "Continuer l'import")
        self.bouton_continuer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_continuer.clicked.connect(lambda: self._adopter(False))
        for b in (self.bouton_zero, self.bouton_continuer):
            b.setVisible(False)
        choisir.addWidget(self.bouton_export)
        choisir.addWidget(self.bouton_zero)
        choisir.addWidget(self.bouton_continuer)
        choisir.addStretch(1)
        racine.addLayout(choisir)

        self.carte = QLabel("")
        self.carte.setWordWrap(True)
        self.carte.setTextFormat(Qt.RichText)
        self.carte.setStyleSheet(StyleManager.CARTE_GRIS_CLAIR + " padding: 8px;")
        racine.addWidget(self.carte)

        lot = QHBoxLayout()
        lot.addWidget(QLabel("Fiches par lot :"))
        self.taille = QSpinBox()
        self.taille.setRange(1, 2000)
        self.taille.setValue(int(_reglages().value(_CLE_TAILLE, 100) or 100))
        lot.addWidget(self.taille)
        self.bouton_analyser = QPushButton(qta.icon('fa5s.search', color='white'), "Lire le lot suivant")
        self.bouton_analyser.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_analyser.setToolTip("Lit les fiches suivantes de l'export, puis ouvre la fenêtre "
                                        "d'import avec une carte par fiche. Rien n'est enregistré "
                                        "avant « Importer ».")
        self.bouton_analyser.clicked.connect(self._analyser_lot)
        self.bouton_de_cote = QPushButton(qta.icon('fa5s.inbox', color='#555555'),
                                          "Fiches mises de côté")
        self.bouton_de_cote.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_de_cote.setToolTip("Fiches décochées à l'import, ou sans code produit : elles "
                                       "reviennent ici quand vous voulez.")
        self.bouton_de_cote.clicked.connect(self._analyser_de_cote)
        self.bouton_a_refaire = QPushButton(qta.icon('fa5s.file-pdf', color='#b45309'),
                                            "Fiches à refaire")
        self.bouton_a_refaire.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_a_refaire.setToolTip("Fiches aux données en vrac : leurs appareils bancals n'ont "
                                         "pas été créés. Cherchez leurs PDF et importez-les.")
        self.bouton_a_refaire.clicked.connect(self._ouvrir_a_refaire)
        self.bouton_everyparts = QPushButton(qta.icon('fa5s.file-csv', color='#555555'),
                                             "Exporter vers EveryParts…")
        self.bouton_everyparts.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_everyparts.setToolTip("Compatibilités des produits repris, au format EveryParts "
                                          "(référence produit du site en 1re colonne).")
        self.bouton_everyparts.clicked.connect(self._ouvrir_everyparts)
        self.bouton_annuler = QPushButton(qta.icon('fa5s.stop', color='#555555'), "Arrêter")
        self.bouton_annuler.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_annuler.clicked.connect(self._annuler)
        self.bouton_annuler.setEnabled(False)
        self.progression = QProgressBar()
        self.progression.setStyleSheet(StyleManager.BARRE_PROGRESSION_DISCRETE)
        self.progression.setTextVisible(False)
        self.progression.setFixedHeight(8)
        for w in (self.bouton_analyser, self.bouton_de_cote, self.bouton_a_refaire,
                  self.bouton_everyparts, self.bouton_annuler):
            lot.addWidget(w)
        lot.addWidget(self.progression, 1)
        racine.addLayout(lot)
        self.texte_progression = QLabel("")
        self.texte_progression.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(self.texte_progression)
        racine.addStretch(1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(self.etat, 1)
        pied.addWidget(fermer)
        racine.addLayout(pied)
        self._activer()

    def _ligne_fichier(self, racine, libelle: str, titre: str) -> QLineEdit:
        ligne = QHBoxLayout()
        etiquette = QLabel(libelle)
        etiquette.setFixedWidth(130)
        champ = QLineEdit()
        parcourir = QPushButton(qta.icon('fa5s.folder-open', color='#555555'), "Parcourir…")
        parcourir.setStyleSheet(StyleManager.SECONDARY_COMPACT_BUTTON)
        parcourir.clicked.connect(lambda: self._parcourir(champ, titre))
        ligne.addWidget(etiquette)
        ligne.addWidget(champ, 1)
        ligne.addWidget(parcourir)
        racine.addLayout(ligne)
        return champ

    # =========================================================================
    # Exports et avancement
    # =========================================================================
    def _charger_chemins(self):
        reglages = _reglages()
        etat = self.service.etat() or {}
        for champ, cle, colonne, nom in (
                (self.champ_produits, _CLE_PRODUITS, 'chemin_produits', 'produits.csv'),
                (self.champ_compat, _CLE_COMPAT, 'chemin_compatibilites', 'compatibilites.csv')):
            # Le premier chemin qui existe encore : état de l'import, dernier choix,
            # puis l'export rangé dans data/reprise_site/
            candidats = [etat.get(colonne) or '', reglages.value(cle, '') or '',
                         str(_DOSSIER_DEFAUT / nom)]
            chemin = next((c for c in candidats if c and Path(c).exists()), '')
            champ.setText(chemin)

    def _parcourir(self, champ: QLineEdit, titre: str):
        dossier = str(Path(champ.text()).parent) if champ.text() else str(_DOSSIER_DEFAUT)
        choisir_fichier_a_ouvrir(self, titre, dossier, "Fichiers CSV (*.csv);;Tous les fichiers (*)",
                                 lambda chemin: champ.setText(chemin), natif=False)

    def _examiner_export(self):
        produits = self.champ_produits.text().strip()
        compat = self.champ_compat.text().strip()
        if not produits or not Path(produits).exists():
            self._message("Choisissez l'export des produits.", erreur=True)
            return
        if compat and not Path(compat).exists():
            self._message("L'export des compatibilités est introuvable.", erreur=True)
            return
        signature, statut = self.service.examiner_export(produits, compat)
        reglages = _reglages()
        reglages.setValue(_CLE_PRODUITS, produits)
        reglages.setValue(_CLE_COMPAT, compat)
        self._signature = signature
        if statut == EXPORT_DIFFERENT and self.service.dernier_id():
            for b in (self.bouton_zero, self.bouton_continuer):
                b.setVisible(True)
            self._message(f"Cet export (du {signature.date_export.replace('T', ' ')}) n'est pas celui "
                          f"de l'import en cours : repartir de zéro, ou continuer après le produit "
                          f"{self.service.dernier_id()} ?", avertissement=True)
            return
        self._adopter(statut != EXPORT_IDENTIQUE and not self.service.dernier_id())

    def _adopter(self, repartir_de_zero: bool):
        if self._signature is None:
            return
        self.service.adopter_export(self._signature, repartir_de_zero)
        for b in (self.bouton_zero, self.bouton_continuer):
            b.setVisible(False)
        self._message("Exports prêts : lisez le lot suivant.")
        self._rafraichir_etat()

    def _rafraichir_etat(self):
        etat = self.service.etat()
        lots = self.db.lots_reprise_site(limite=1000)
        de_cote = self.db.fiches_de_cote_reprise_site()
        a_refaire = self.db.fiches_a_refaire()
        if not etat:
            texte = "Aucun import commencé : choisissez les deux exports."
        else:
            texte = (f"<b>Dernier produit importé : {etat['dernier_id'] or '—'}</b> · exports du "
                     f"{(etat['date_export'] or '?').replace('T', ' à ')} · {len(lots)} lot(s) "
                     f"enregistré(s) · {len(de_cote)} fiche(s) mise(s) de côté · "
                     f"{len(a_refaire)} fiche(s) à refaire depuis les PDF")
            if lots:
                d = lots[0]
                texte += (f"<br>Dernier lot : produits {d['premier_id']} à {d['dernier_id']}, "
                          f"{d['fiches']} fiche(s), base "
                          f"{((d['taille_apres'] or 0) - (d['taille_avant'] or 0)) / 1e6:+.1f} Mo")
            if self.service.signature is None:
                texte += "<br><i>Cliquez « Utiliser ces exports » pour continuer.</i>"
        self.carte.setText(texte)
        self.bouton_de_cote.setText(f"Fiches mises de côté ({len(de_cote)})")
        self.bouton_a_refaire.setText(f"Fiches à refaire ({len(a_refaire)})")
        self._nb_de_cote = len(de_cote)
        self._activer()

    # =========================================================================
    # Lecture d'un lot (thread), puis fenêtre d'import
    # =========================================================================
    def _lancer(self, fonction, fin, texte: str):
        self._tache = _Tache(fonction, self)
        self._tache.progression.connect(self._progresser)
        self._tache.termine.connect(lambda r, e: self._tache_terminee(fin, r, e))
        self.texte_progression.setText(texte)
        self.progression.setRange(0, 0)
        self._activer()
        self._tache.start()

    def _progresser(self, i: int, n: int, texte: str):
        if n:
            self.progression.setRange(0, n)
            self.progression.setValue(i)
        else:
            self.progression.setRange(0, 0)
        self.texte_progression.setText(texte)

    def _tache_terminee(self, fin, resultat, erreur: str):
        self._tache = None
        self.progression.setRange(0, 1)
        self.progression.setValue(1)
        self.texte_progression.setText('')
        fin(resultat, erreur)
        self._rafraichir_etat()

    def _annuler(self):
        if self._tache is not None:
            self._tache.arret.set()
            self.texte_progression.setText("Arrêt demandé…")

    def _analyser_lot(self):
        if self.service.signature is None:
            self._examiner_export()
            if self.service.signature is None:
                return
        taille = self.taille.value()
        _reglages().setValue(_CLE_TAILLE, taille)
        self._lancer(lambda prog, annule: self.service.analyser_lot_suivant(taille, prog, annule),
                     self._lot_analyse, "Lecture du lot…")

    def _analyser_de_cote(self):
        self._lancer(lambda prog, annule: self.service.analyser_fiches_de_cote(prog, annule),
                     self._lot_analyse, "Lecture des fiches mises de côté…")

    def _lot_analyse(self, lot, erreur: str):
        if erreur:
            arret = 'AnalyseAnnulee' in erreur
            self._message("Lecture arrêtée." if arret else f"Lecture impossible : {erreur}",
                          erreur=not arret)
            return
        if lot is None:
            self._message("Export entièrement importé : plus aucun produit après le dernier traité.")
            return
        self.afficher_lot(lot)

    def afficher_lot(self, lot):
        """Planifie un lot lu (règles de l'import) et ouvre la fenêtre d'import, une
        carte par fiche (appelée aussi par les tests, sans thread)."""
        from .fiche_site_import import ouvrir_import_lot
        self.lot = lot
        self.plan = self.service.planifier_lot(lot)
        self._import_en_cours = True
        self.cartes = ouvrir_import_lot(self.main_window, self.service, lot, self.plan,
                                        fin=self._lot_importe, parent=self)
        e = lot.export
        nature = ("Fiches mises de côté" if lot.fiches_de_cote
                  else f"Lot : produits {e.premier_id} à {e.dernier_id}")
        self._message(f"{nature} · {len(self.cartes)} fiche(s) dans la fenêtre d'import · "
                      f"rien n'est encore enregistré.")
        self._activer()

    def _lot_importe(self, res):
        """Fin de l'import du lot (ou fenêtre d'import fermée sans importer : None)."""
        self._import_en_cours = False
        if getattr(self, '_fermee', False):
            self.service.fermer()       # fenêtre fermée pendant l'import : rien à afficher
            return
        self.lot = self.plan = None
        if res is None:
            self._message("Lot non importé : rien n'a été écrit. Relisez-le quand vous voulez.",
                          avertissement=True)
        elif res.annule or not res.ok:
            self._message(("Import arrêté" if res.annule else
                           f"Import interrompu : {res.erreur}")
                          + " — l'import n'a pas avancé ; relisez le lot : rien ne sera doublé.",
                          erreur=not res.annule, avertissement=res.annule)
        else:
            self._message(f"Lot n° {res.numero} enregistré : {res.resume()}.")
            if self.on_lot_enregistre is not None:
                self.on_lot_enregistre(res)
        self._rafraichir_etat()

    def _ouvrir_everyparts(self):
        from .export_fiches_reprises_dialog import ExportFichesReprisesDialog
        ExportFichesReprisesDialog(self.db, main_window=self.main_window).show()

    def _ouvrir_a_refaire(self):
        from .fiches_a_refaire_dialog import FichesARefaireDialog
        dialogue = FichesARefaireDialog(self.db, parent=self, on_change=self._rafraichir_etat)
        dialogue.show()

    # =========================================================================
    def _activer(self):
        occupe = self._tache is not None or self._import_en_cours
        pret = self.service.signature is not None
        self.bouton_analyser.setEnabled(not occupe and pret)
        self.bouton_de_cote.setEnabled(not occupe and pret and bool(getattr(self, '_nb_de_cote', 0)))
        self.bouton_annuler.setEnabled(self._tache is not None)
        self.bouton_export.setEnabled(not occupe)

    def _message(self, texte: str, erreur: bool = False, avertissement: bool = False):
        self.etat.setText(texte)
        self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE if erreur
                                else StyleManager.TEXTE_AVERTISSEMENT if avertissement
                                else StyleManager.TEXTE_SECONDAIRE)

    def closeEvent(self, event):
        self._fermee = True
        t = self._tache
        if t is not None:
            # Lecture en cours : arrêt demandé, le thread survit à la fenêtre jusqu'à sa fin
            t.arret.set()
            t.termine.disconnect()
            t.setParent(None)
            service = self.service
            _EN_COURS.add(t)
            t.finished.connect(lambda: (_EN_COURS.discard(t), service.fermer()))
        elif not self._import_en_cours:
            self.service.fermer()
        super().closeEvent(event)


_EN_COURS = set()
