"""
« Importer depuis Agora » : une pièce, ses appareils compatibles et son prix, sans PDF.

1. Référence saisie → famille lue dans les fichiers MySpace (local, sans quota) :
   référence à publier (la plus récente commandable), anciennes références,
   désignation, état ; contrôle anti-doublon dans l'outil et sur le site
   (produits du site repris).
2. « Interroger Agora » (hors du thread principal) : appareils compatibles et
   prix de la référence à publier. Chaque réponse est gardée en cache, le
   quota du jour (10 appels par service) est affiché et respecté.
3. « Ouvrir l'import » : la fenêtre d'import habituelle, comme pour un collage
   (en-têtes reconnus, mapping, aperçu), référence et libellé préremplis,
   « Remplace » prérempli avec les anciennes références. L'import suit son
   circuit habituel (suggestions, auto-complétés, règles de nomenclature).

Quota épuisé ou pièce inconnue d'Agora : on importe le PDF, comme avant.
Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import html
import os
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.utils.agora.client import (APPAREILS, INFO, ClientAgora, ErreurAgora, QuotaEpuise,
                                    lire_cle)
from src.utils.agora.conversion import (cle_marque, code_emg_propose, libelle_piece,
                                        lignes_appareils, prix_emg)
from src.utils.agora.myspace import (COMMANDABLE, CONSTRUCTEURS, SANS_FICHIER, FamilleAgora,
                                     FamillesMySpace, charger_dossier, myspace_charge)
from src.utils.agora.stockage import BaseAgora, cle_ref
from .style_manager import StyleManager


def _euros(valeur) -> str:
    return f"{valeur:,.2f} €".replace(',', ' ').replace('.', ',') if valeur is not None else '—'


class ChargementMySpace(QThread):
    """Chargement des fichiers MySpace (≈ 5 millions de lignes, une vingtaine de secondes)."""
    etape = pyqtSignal(str)
    termine = pyqtSignal(object, str)          # comptes, erreur

    def __init__(self, base: BaseAgora, dossier: str, parent=None):
        super().__init__(parent)
        self.base, self.dossier = base, dossier

    def run(self):
        try:
            self.termine.emit(charger_dossier(self.base, self.dossier, self.etape.emit), '')
        except Exception as e:
            self.termine.emit(None, str(e))


class AppelAgora(QThread):
    """Prix puis appareils compatibles d'une référence (cache d'abord)."""
    termine = pyqtSignal(object)               # dict : info, appareils, erreurs

    def __init__(self, client: ClientAgora, constructeur: int, ref: str, parent=None):
        super().__init__(parent)
        self.client, self.constructeur, self.ref = client, constructeur, ref

    def run(self):
        resultat = {'info': None, 'appareils': None, 'erreurs': {}, 'cache': {}}
        for service, appel in ((INFO, self.client.info), (APPAREILS, self.client.appareils)):
            try:
                r = appel(self.constructeur, self.ref)
                resultat['info' if service == INFO else 'appareils'] = r
                resultat['cache'][service] = r.depuis_cache
            except QuotaEpuise as e:
                resultat['erreurs'][service] = str(e)
            except ErreurAgora as e:
                resultat['erreurs'][service] = str(e)
            except Exception as e:                     # filet : jamais d'exception hors du thread
                app_logger.error(f"[Agora] {service} : {type(e).__name__}", exc_info=True)
                resultat['erreurs'][service] = f"erreur inattendue ({type(e).__name__})"
        self.termine.emit(resultat)


class SaisieAgora(QDialog):
    """Référence de pièce → famille MySpace → Agora → fenêtre d'import."""

    def __init__(self, main_window, base: Optional[BaseAgora] = None,
                 client: Optional[ClientAgora] = None):
        super().__init__(main_window)
        self.main_window = main_window
        self.base = base or BaseAgora()
        self.client = client or ClientAgora(self.base)
        self.familles = FamillesMySpace(self.base)
        self.setWindowTitle("Importer depuis Agora")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(760, 420)
        self.famille: Optional[FamilleAgora] = None
        self.constructeur: Optional[int] = None
        self.ref_agora: str = ''
        self.lignes = None
        self.info: Dict = {}
        self._thread = None
        self._marques: Optional[Dict[str, str]] = None
        self._construire()
        self._maj_myspace()
        self._maj_quota()

    # --- Interface ------------------------------------------------------------------
    def _construire(self):
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        racine.setSpacing(8)

        self.bandeau_myspace = QLabel()
        self.bandeau_myspace.setWordWrap(True)
        self.bandeau_myspace.setStyleSheet(StyleManager.BANDEAU_AVERTISSEMENT)
        ligne_ms = QHBoxLayout()
        ligne_ms.addWidget(self.bandeau_myspace, 1)
        self.bouton_myspace = QPushButton("Charger les fichiers MySpace…")
        self.bouton_myspace.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_myspace.clicked.connect(self.choisir_dossier_myspace)
        ligne_ms.addWidget(self.bouton_myspace)
        racine.addLayout(ligne_ms)

        saisie = QHBoxLayout()
        saisie.addWidget(QLabel("Référence de pièce :"))
        self.champ = QLineEdit()
        self.champ.setPlaceholderText("ex : 481011015524, C00866459, 140005565027")
        self.champ.returnPressed.connect(self.chercher)
        saisie.addWidget(self.champ, 1)
        self.choix_constructeur = QComboBox()
        self.choix_constructeur.addItem("Constructeur : d'après MySpace", None)
        for n, nom in CONSTRUCTEURS.items():
            self.choix_constructeur.addItem(f"{nom} ({n})", n)
        saisie.addWidget(self.choix_constructeur)
        self.bouton_chercher = QPushButton(qta.icon('fa5s.search', color='white'), "Chercher")
        self.bouton_chercher.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_chercher.clicked.connect(self.chercher)
        saisie.addWidget(self.bouton_chercher)
        racine.addLayout(saisie)

        self.zone_famille = QLabel("")
        self.zone_famille.setWordWrap(True)
        self.zone_famille.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.zone_famille.setAlignment(Qt.AlignTop)
        racine.addWidget(self.zone_famille)

        self.zone_agora = QLabel("")
        self.zone_agora.setWordWrap(True)
        self.zone_agora.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.zone_agora.setAlignment(Qt.AlignTop)
        racine.addWidget(self.zone_agora, 1)

        pied = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        pied.addWidget(self.etat, 1)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        self.bouton_agora = QPushButton(qta.icon('fa5s.cloud-download-alt', color='white'),
                                        "Interroger Agora")
        self.bouton_agora.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_agora.setEnabled(False)
        self.bouton_agora.clicked.connect(self.interroger)
        self.bouton_import = QPushButton(qta.icon('fa5s.file-import', color='white'),
                                         "Ouvrir l'import")
        self.bouton_import.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_import.setEnabled(False)
        self.bouton_import.clicked.connect(self.ouvrir_import)
        pied.addWidget(fermer)
        pied.addWidget(self.bouton_agora)
        pied.addWidget(self.bouton_import)
        racine.addLayout(pied)

    def _maj_myspace(self):
        charge = myspace_charge(self.base)
        if charge:
            date = (self.base.meta('charge_le') or '')[:10]
            self.bandeau_myspace.setText(f"Fichiers MySpace chargés le {date}.")
            self.bandeau_myspace.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
            self.bouton_myspace.setText("Recharger…")
        else:
            self.bandeau_myspace.setText(
                "Fichiers MySpace non chargés : sans eux, ni famille de références ni marque "
                "des appareils. Téléchargez-les sur myspace2.agoraplus.com (un fichier Parts_N "
                "et Products_N par constructeur), puis chargez le dossier.")

    def _maj_quota(self):
        if not lire_cle():
            self.etat.setText("Clé d'API Agora absente : ajoutez data/agora.env (ligne AGORA_KEY=…).")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        self.etat.setText(
            f"Agora aujourd'hui : appareils {self.client.restants(APPAREILS)}/{self.client.quota} "
            f"restants · prix {self.client.restants(INFO)}/{self.client.quota} restants "
            "(remis à zéro à minuit UTC). Une réponse déjà obtenue ne consomme rien.")
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)

    # --- MySpace ---------------------------------------------------------------------
    def choisir_dossier_myspace(self):
        from src.utils.boites import choisir_dossier
        dossier = os.path.dirname(self.base.meta('dossier') or '') or os.path.expanduser('~')
        # Sélecteur dessiné par Qt (natif=False) : le natif macOS, ouvert depuis une
        # fenêtre non modale, peut rester invisible et bloquer tous les clics (cf. boites)
        choisir_dossier(self, "Dossier des fichiers MySpace (Parts_N, Products_N)", dossier,
                        self.charger_myspace, natif=False)

    def charger_myspace(self, dossier: str):
        if not dossier or self._thread is not None:
            return
        self.bouton_myspace.setEnabled(False)
        self._thread = ChargementMySpace(self.base, dossier, self)
        self._thread.etape.connect(lambda m: self.bandeau_myspace.setText(f"Chargement : {m}"))
        self._thread.termine.connect(self._myspace_charge)
        self._thread.start()

    def _myspace_charge(self, comptes, erreur: str):
        self._thread = None
        self.bouton_myspace.setEnabled(True)
        if erreur:
            self.bandeau_myspace.setText(f"Chargement impossible : {erreur}")
            return
        app_logger.info(f"[Agora] MySpace chargé : {sum(comptes.values())} lignes, {len(comptes)} fichiers")
        self._maj_myspace()

    # --- Recherche (local) -------------------------------------------------------------
    def chercher(self):
        saisie = self.champ.text().strip()
        if not saisie:
            return
        choisi = self.choix_constructeur.currentData()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.famille = self.familles.famille(saisie, choisi)
            doublons = self._deja_connues(self.famille.references or [saisie])
        finally:
            QApplication.restoreOverrideCursor()
        f = self.famille
        self.lignes, self.info = None, {}
        self.zone_agora.setText("")
        self.bouton_import.setEnabled(False)
        if f.trouvee:
            self.constructeur = choisi if choisi is not None else f.courante.constructeur
            self.ref_agora = f.courante.ref_publiee
        else:
            self.constructeur, self.ref_agora = choisi, saisie.replace(' ', '')
        self.zone_famille.setText(self._texte_famille(f, doublons))
        self.bouton_agora.setEnabled(self.constructeur is not None and not f.epuisee)
        self._maj_quota()

    def _deja_connues(self, refs: List[str]) -> Dict[str, list]:
        """Références de la famille déjà dans l'outil (et nombre d'appareils), et
        produits du site qui les vendent (anti-doublon)."""
        cles = sorted({cle_ref(r) for r in refs if r})
        if not cles:
            return {'outil': [], 'site': []}
        db = self.main_window.db_manager
        marques = ','.join('?' * len(cles))
        expr = "UPPER(REPLACE(REPLACE(REPLACE(ref_piece, ' ', ''), '-', ''), '.', ''))"
        outil = db.execute_query(
            f"SELECT p.ref_piece, (SELECT COUNT(*) FROM piece_associations a WHERE a.piece_id = p.id) "
            f"FROM pieces p WHERE {expr} IN ({marques})", cles) or []
        site = db.execute_query(
            f"SELECT ref_interne, id_product, ref_piece FROM produits_site WHERE {expr} IN ({marques})",
            cles) or []
        return {'outil': list(outil), 'site': list(site)}

    def _texte_famille(self, f: FamilleAgora, doublons: Dict[str, list]) -> str:
        e = html.escape
        lignes = []
        if f.epuisee:
            lignes.append("<b style='color:#c0392b'>Pièce épuisée</b> : elle renvoie au code générique "
                          "« article épuisé » d'Agora, ce n'est pas un remplacement.")
        if not f.trouvee:
            if self.constructeur is None:
                lignes.append("Référence absente des fichiers MySpace. Choisissez le constructeur "
                              "pour interroger Agora quand même.")
            else:
                note = (" (pas de fichier MySpace pour ce constructeur)"
                        if self.constructeur in SANS_FICHIER else " des fichiers MySpace")
                lignes.append(f"Référence absente{note} : Agora sera interrogé pour "
                              f"<b>{e(self.ref_agora)}</b> chez {e(CONSTRUCTEURS.get(self.constructeur, ''))}.")
        else:
            c = f.courante
            couleur = '#2e7d32' if c.etat == COMMANDABLE else '#b45309'
            lignes.append(f"Référence à publier : <b>{e(c.ref_publiee)}</b> — {e(c.designation)} "
                          f"<span style='color:{couleur}'>({e(c.etat)})</span> · {e(c.nom_constructeur)}")
            if cle_ref(c.ref) != cle_ref(f.saisie):
                lignes.append(f"La référence saisie <b>{e(f.saisie)}</b> est remplacée : "
                              f"{' → '.join(e(p.ref_publiee) for p in f.chaine)}.")
            if f.anciennes:
                lignes.append(f"Remplace : {e(' '.join(f.anciennes))}")
            if f.autres_constructeurs:
                autres = ', '.join(CONSTRUCTEURS.get(n, str(n)) for n in f.autres_constructeurs)
                lignes.append(f"<span style='color:#6c757d'>Même référence aussi chez : {e(autres)}</span>")
        if doublons['site']:
            produits = ', '.join(f"{e(r[0])} (n° {r[1]})" for r in doublons['site'])
            lignes.append(f"<b style='color:#c0392b'>Déjà sur le site</b> : {produits}. "
                          "Vérifiez avant de créer une fiche.")
        if doublons['outil']:
            refs = ', '.join(f"{e(r[0])} ({r[1]} appareils)" for r in doublons['outil'])
            lignes.append(f"Déjà dans l'outil : {refs}.")
        return '<br>'.join(lignes)

    # --- Agora (API) ---------------------------------------------------------------------
    def interroger(self):
        if self._thread is not None or self.constructeur is None or not self.ref_agora:
            return
        self.bouton_agora.setEnabled(False)
        self.bouton_chercher.setEnabled(False)
        self.zone_agora.setText("Interrogation d'Agora…")
        self._thread = AppelAgora(self.client, self.constructeur, self.ref_agora, self)
        self._thread.termine.connect(self._agora_repond)
        self._thread.start()

    def _marques_connues(self) -> Dict[str, str]:
        if self._marques is None:
            rows = self.main_window.db_manager.execute_query(
                "SELECT manufacturer, COUNT(*) AS n FROM appareils WHERE manufacturer != '' "
                "GROUP BY manufacturer ORDER BY n DESC") or []
            self._marques = {}
            for marque, _n in rows:
                self._marques.setdefault(cle_marque(marque), marque)
        return self._marques

    def _agora_repond(self, r: dict):
        self._thread = None
        self.bouton_chercher.setEnabled(True)
        self.bouton_agora.setEnabled(True)
        self._maj_quota()
        e = html.escape
        lignes = []
        info = r.get('info')
        self.info = (info.donnees or {}) if info is not None and isinstance(info.donnees, dict) else {}
        if INFO in r['erreurs']:
            lignes.append(f"<span style='color:#b45309'>Prix : {e(r['erreurs'][INFO])}</span>")
        elif self.info:
            p = prix_emg(self.info, self.constructeur)
            dispo = self.info.get('Availability') or self.info.get('Status') or ''
            texte = (f"Prix de vente : <b>{_euros(p.vente)}</b> TTC ({e(p.regle)} ; achat "
                     f"{_euros(p.achat_ht)} HT, public {_euros(p.public)})")
            if dispo:
                texte += f" · disponibilité : {e(str(dispo))}"
            lignes.append(texte)
            if p.alerte:
                lignes.append(f"<span style='color:#b45309'>Prix {e(p.alerte)}.</span>")
            if self.info.get('ReplaceBy'):
                lignes.append(f"<span style='color:#b45309'>Agora indique un remplacement : "
                              f"{e(self.info['ReplaceBy'])}.</span>")
        code = code_emg_propose(self.ref_agora, self.constructeur)
        lignes.append(f"Code produit proposé (référence PrestaShop / Cogilog) : <b>{e(code)}</b>, à vérifier"
                      if code else "Code produit : préfixe inconnu pour ce constructeur, à saisir.")

        appareils = r.get('appareils')
        self.lignes = None
        if APPAREILS in r['erreurs']:
            lignes.append(f"<b style='color:#c0392b'>Appareils : {e(r['erreurs'][APPAREILS])}.</b> "
                          "Importez le PDF de la pièce (Fichier → Importer).")
        elif appareils is None or appareils.absente:
            lignes.append("<b>Agora ne connaît aucun appareil pour cette pièce</b> : importez le PDF.")
        else:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.lignes = lignes_appareils(
                    appareils.donnees, lambda a: self.familles.produits(a, self.constructeur),
                    self._marques_connues())
            finally:
                QApplication.restoreOverrideCursor()
            n = len(self.lignes.lignes)
            source = "cache" if r['cache'].get(APPAREILS) else "Agora"
            lignes.append(f"<b>{n} appareils compatibles</b> ({source}) — sans marque : "
                          f"{self.lignes.sans_marque}, sans type : {self.lignes.sans_type} "
                          "(l'import les complète ou les propose à valider).")
        self.zone_agora.setText('<br>'.join(lignes))
        self.bouton_import.setEnabled(bool(self.lignes and self.lignes.lignes))

    # --- Import -------------------------------------------------------------------------
    def ouvrir_import(self):
        if not self.lignes or not self.lignes.lignes:
            return
        from src.core.import_manager import (FileType, ImportConfiguration, ImportFile, ImportType)
        f = self.famille
        designation = self.info.get('Description') or (f.courante.designation if f and f.courante else '')
        fichier = ImportFile(
            path=f"Agora {self.ref_agora}", type=FileType.CLIPBOARD,
            suggested_reference=self.ref_agora, suggested_label=libelle_piece(designation),
            data=self.lignes.avec_entetes(),
            relations_source={'remplace': list(f.anciennes) if f else [],
                              'info': "Remplacements lus dans les fichiers MySpace d'Agora. "
                                      "Retirez une référence erronée, ajoutez-en une au besoin."})
        config = ImportConfiguration(files=[fichier], import_type=ImportType.SINGLE_FILE,
                                     has_headers=True)
        main_window = self.main_window

        def fin(results):
            if hasattr(main_window, '_on_import_complete'):
                main_window._on_import_complete(results)

        main_window.import_manager.importer_avec_dialogue(
            config, callback=fin, titre=f"Importer depuis Agora — {self.ref_agora}")
        self.close()
