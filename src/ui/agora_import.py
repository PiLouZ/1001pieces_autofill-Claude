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
    QWidget,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.utils.agora.client import (APPAREILS, INFO, ClientAgora, ErreurAgora,
                                    lire_cle)
from src.utils.agora.conversion import (cle_marque, code_emg_propose, libelle_piece,
                                        lignes_appareils, prix_emg)
from src.utils.agora.myspace import (COMMANDABLE, CONSTRUCTEURS, SANS_FICHIER, FamilleAgora,
                                     FamillesMySpace, charger_dossier, myspace_charge)
from src.utils.agora.stockage import BaseAgora, cle_ref
from .style_manager import StyleManager


def _prix(texte: str) -> Optional[float]:
    try:
        return round(float((texte or '').replace('€', '').replace(',', '.').strip()), 2) or None
    except ValueError:
        return None


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
    """Prix de la référence à publier (si pas encore lu), puis appareils
    compatibles d'une référence de la famille (cache d'abord)."""
    termine = pyqtSignal(object)               # dict : info, appareils, erreurs, cache

    def __init__(self, client: ClientAgora, constructeur: int, ref_info: Optional[str],
                 ref_appareils: str, parent=None):
        super().__init__(parent)
        self.client, self.constructeur = client, constructeur
        self.ref_info, self.ref_appareils = ref_info, ref_appareils

    def run(self):
        resultat = {'info': None, 'appareils': None, 'erreurs': {}, 'cache': {},
                    'ref_appareils': self.ref_appareils}
        appels = [(APPAREILS, self.client.appareils, self.ref_appareils)]
        if self.ref_info:
            appels.insert(0, (INFO, self.client.info, self.ref_info))
        for service, appel, ref in appels:
            try:
                r = appel(self.constructeur, ref)
                resultat['info' if service == INFO else 'appareils'] = r
                resultat['cache'][service] = r.depuis_cache
            except ErreurAgora as e:                   # QuotaEpuise compris
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
        self.info_lue = False
        self.message_prix: List[str] = []
        # Appareils lus par référence de la famille (None : Agora n'en connaît aucun).
        # Agora range souvent les appareils sous l'ancienne référence (Beko
        # C00866459 : rien ; 4346040285 qu'elle remplace : 231 appareils).
        self.cas: Dict[str, Optional[list]] = {}
        self._thread = None
        self._marques: Optional[Dict[str, str]] = None
        self._site = None                   # webservice du site (anti-doublon), si configuré
        self._tache_site = None
        self._texte_famille_courant = ''
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

        # Code produit et prix proposés, modifiables avant l'import (Pierre-Louis, 2026-11-26)
        self.ligne_fiche = QWidget()
        ligne = QHBoxLayout(self.ligne_fiche)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.addWidget(QLabel("Code produit :"))
        self.champ_code = QLineEdit()
        self.champ_code.setToolTip("Référence PrestaShop = code Cogilog, d'après les règles des codes produit")
        ligne.addWidget(self.champ_code, 1)
        ligne.addWidget(QLabel("Prix TTC :"))
        self.champ_prix = QLineEdit()
        self.champ_prix.setMaximumWidth(110)
        ligne.addWidget(self.champ_prix)
        ligne.addStretch(1)
        self.ligne_fiche.setVisible(False)
        racine.addWidget(self.ligne_fiche)

        # Quota sur sa propre ligne : à côté des boutons, il était écrasé en colonne
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(self.etat)

        pied = QHBoxLayout()
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
        pied.addStretch(1)
        self.choix_ref = QComboBox()
        self.choix_ref.setToolTip("Référence de la famille dont on demande les appareils compatibles "
                                  "(1 appel, sauf si déjà en cache)")
        self.choix_ref.setVisible(False)
        pied.addWidget(self.choix_ref)
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
        from .agora_fiche import _TACHES
        # Sans parent, gardé dans _TACHES : fermer la fenêtre pendant le chargement ne
        # détruit pas le thread en cours (arrêt de l'application)
        self._thread = ChargementMySpace(self.base, dossier)
        _TACHES.add(self._thread)
        self._thread.finished.connect(lambda t=self._thread: _TACHES.discard(t))
        self._thread.etape.connect(self._etape_myspace)
        self._thread.termine.connect(self._myspace_charge)
        self._thread.start()

    def _etape_myspace(self, message: str):
        self.bandeau_myspace.setText(f"Chargement : {message}")

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
        self.lignes, self.info, self.info_lue, self.message_prix, self.cas = None, {}, False, [], {}
        self.zone_agora.setText("")
        self.ligne_fiche.setVisible(False)
        self.champ_code.clear()
        self.champ_prix.clear()
        self.bouton_import.setEnabled(False)
        if f.trouvee:
            self.constructeur = choisi if choisi is not None else f.courante.constructeur
            self.ref_agora = f.courante.ref_publiee
        else:
            self.constructeur, self.ref_agora = choisi, saisie.replace(' ', '')
        self._texte_famille_courant = self._texte_famille(f, doublons)
        self.zone_famille.setText(self._texte_famille_courant)
        self._verifier_sur_le_site()
        self._remplir_choix_ref()
        self.bouton_agora.setEnabled(self.constructeur is not None and not f.epuisee)
        self._maj_quota()

    def _verifier_sur_le_site(self):
        """Anti-doublon sur le site (webservice), hors du thread principal : références
        de la famille et codes produit qu'elles donneraient."""
        try:
            from src.utils.prestashop.site import SitePrestaShop
            if self._site is None:
                self._site = SitePrestaShop()
        except Exception:
            return                          # site non configuré : contrôle local seulement
        from src.utils.agora.codes import code_produit
        from .agora_fiche import lancer_tache
        refs = self._refs_famille()
        refs += [c for c in (code_produit(r, self.constructeur) for r in list(refs)) if c]
        site, saisie = self._site, self.champ.text().strip()
        self._tache_site = lancer_tache(lambda: site.produits_existants(refs),
                                        lambda produits, err: self._site_verifie(saisie, produits, err), self)

    def _site_verifie(self, saisie: str, produits, erreur: str):
        if saisie != self.champ.text().strip():
            return                          # une autre recherche a été lancée entre-temps
        env = self._site.client.environnement
        if erreur:
            ligne = f"<span style='color:#6c757d'>Site ({env}) non vérifié : {html.escape(erreur)}</span>"
        elif produits:
            liste = ', '.join(f"{html.escape(p.reference)} (n° {p.id}, {'active' if p.actif else 'désactivée'})"
                              for p in produits)
            ligne = f"<b style='color:#c0392b'>Déjà sur le site ({env})</b> : {liste}."
        else:
            ligne = f"<span style='color:#2e7d32'>Aucune fiche sur le site ({env}) pour cette famille.</span>"
        self.zone_famille.setText(self._texte_famille_courant + '<br>' + ligne)

    def _refs_famille(self) -> List[str]:
        f = self.famille
        refs = f.references if f is not None and f.trouvee else []
        return refs or ([self.ref_agora] if self.ref_agora else [])

    def _remplir_choix_ref(self, choisie: Optional[str] = None):
        """Une entrée par référence de la famille : à publier, ancienne, déjà lue."""
        self.choix_ref.clear()
        for ref in self._refs_famille():
            if ref in self.cas:
                etat = "aucun appareil" if self.cas[ref] is None else f"{len(self.cas[ref])} appareils"
            elif self.constructeur is not None and self.client.en_cache(APPAREILS, self.constructeur, ref):
                etat = "en cache"
            elif self.constructeur is not None and self.base.echec(
                    APPAREILS, self.client.cle_cache(self.constructeur, ref)):
                etat = "trop d'appareils pour Agora"
            else:
                etat = "1 appel"
            role = ("à publier" if ref == self.ref_agora
                    else "associée" if self.famille is not None and ref == self.famille.associee else "ancienne")
            self.choix_ref.addItem(f"Appareils de {ref} ({role}, {etat})", ref)
        if choisie is not None:
            i = self.choix_ref.findData(choisie)
            if i >= 0:
                self.choix_ref.setCurrentIndex(i)
        self.choix_ref.setVisible(self.choix_ref.count() > 1)

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
            if cle_ref(c.ref) != cle_ref(f.saisie) and cle_ref(f.saisie) != cle_ref(f.associee or ''):
                lignes.append(f"La référence saisie <b>{e(f.saisie)}</b> est remplacée : "
                              f"{' → '.join(e(p.ref_publiee) for p in f.chaine)}.")
            if f.associee:
                lignes.append(f"Référence associée : <b>{e(f.associee)}</b> (jumelle Whirlpool / Beko ↔ "
                              "Indesit, gardée à part : ses appareils restent sous sa référence)")
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
        ref_appareils = self.choix_ref.currentData() or self.ref_agora
        self.bouton_agora.setEnabled(False)
        self.bouton_chercher.setEnabled(False)
        self.zone_agora.setText(f"Interrogation d'Agora ({ref_appareils})…")
        from .agora_fiche import _TACHES
        self._thread = AppelAgora(self.client, self.constructeur,
                                  None if self.info_lue else self.ref_agora, ref_appareils)
        _TACHES.add(self._thread)
        self._thread.finished.connect(lambda t=self._thread: _TACHES.discard(t))
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
        e = html.escape
        if INFO in r['erreurs']:
            self.message_prix = [f"<span style='color:#b45309'>Prix : {e(r['erreurs'][INFO])}</span>"]
        elif r.get('info') is not None:
            self.info_lue = True
            donnees = r['info'].donnees
            self.info = donnees if isinstance(donnees, dict) else {}
            self.message_prix = self._texte_prix()

        ref = r['ref_appareils']
        lignes = list(self.message_prix)
        appareils = r.get('appareils')
        if APPAREILS in r['erreurs']:
            erreur = r['erreurs'][APPAREILS]
            lignes.append(f"<b style='color:#c0392b'>Appareils de {e(ref)} : {e(erreur)}.</b> "
                          + ("Agora échoue souvent ainsi sur les pièces aux dizaines de milliers "
                             "d'appareils. " if 'code 500' in erreur else "")
                          + "Importez le PDF de la pièce (Fichier → Importer).")
        elif appareils is not None:
            self.cas[ref] = None if appareils.absente else list(appareils.donnees)
        self._calculer_lignes()
        for r_lue, cas in self.cas.items():
            source = "cache" if r_lue == ref and r['cache'].get(APPAREILS) else "Agora"
            lignes.append(f"Appareils de {e(r_lue)} : aucun chez Agora." if cas is None
                          else f"Appareils de {e(r_lue)} : {len(cas)} ({source}).")
        if self.lignes and self.lignes.lignes:
            lignes.append(f"<b>{len(self.lignes.lignes)} appareils compatibles au total</b> — sans marque : "
                          f"{self.lignes.sans_marque}, sans type : {self.lignes.sans_type} "
                          "(l'import les complète ou les propose à valider).")
        # Rien sur cette référence : proposer la suivante de la famille, sans dépenser
        suivante = next((x for x in self._refs_famille() if x not in self.cas), None)
        if ref in self.cas and self.cas[ref] is None:
            if suivante:
                lignes.append(f"Agora range souvent les appareils sous une autre référence de la famille : "
                              f"<b>{e(suivante)}</b> est sélectionnée, cliquez sur <b>Interroger Agora</b> "
                              "pour l'essayer.")
            elif not (self.lignes and self.lignes.lignes):
                lignes.append("<b>Agora ne connaît aucun appareil pour cette famille</b> : importez le PDF.")
        self._remplir_choix_ref(suivante if suivante else ref)
        self.zone_agora.setText('<br>'.join(lignes))
        self.bouton_import.setEnabled(bool(self.lignes and self.lignes.lignes))
        self._maj_quota()

    def _fichiers_import(self, designation: str) -> list:
        """Un fichier d'import par référence dont Agora a donné les appareils : chaque
        liste reste sous sa référence d'origine (Pierre-Louis, 2026-11-26), la famille
        est déclarée par les relations (remplace, remplacée par, réf. associée)."""
        from src.core.import_manager import FileType, ImportFile
        f = self.famille
        courante = self.ref_agora
        associee = f.associee if f else None
        anciennes = list(f.anciennes) if f else []
        libelle = libelle_piece(designation)
        fichiers = []
        for ref, cas in self.cas.items():
            if not cas:
                continue
            lignes = lignes_appareils(cas, lambda a: self.familles.produits(a, self.constructeur),
                                      self._marques_connues())
            if ref == courante:
                relations = {'remplace': anciennes, 'associee': associee or ''}
            elif ref == associee:
                relations = {'associee': courante}
            else:
                relations = {'remplacee_par': [courante]}
            relations['info'] = ("Relations lues dans les fichiers MySpace d'Agora. "
                                 "Retirez une référence erronée, ajoutez-en une au besoin.")
            fichiers.append(ImportFile(path=f"Agora {ref}", type=FileType.CLIPBOARD,
                                       suggested_reference=ref, suggested_label=libelle,
                                       data=lignes.avec_entetes(), relations_source=relations))
        return fichiers

    def _texte_prix(self) -> List[str]:
        e = html.escape
        lignes = []
        if self.info:
            p = prix_emg(self.info, self.constructeur)
            dispo = self.info.get('Availability')
            statut = self.info.get('Status') or ''
            texte = (f"Prix de vente proposé : <b>{_euros(p.vente)}</b> TTC ({e(p.regle)} ; achat "
                     f"{_euros(p.achat_ht)} HT, public {_euros(p.public)})")
            if dispo is not None or statut:
                texte += (f" · disponible : {'oui' if dispo else 'non'}" if dispo is not None else '') + \
                         (f" ({e(str(statut))})" if statut else '')
            lignes.append(texte)
            if p.alerte:
                lignes.append(f"<span style='color:#b45309'>Prix {e(p.alerte)}.</span>")
            if self.info.get('ReplaceBy'):
                lignes.append(f"<span style='color:#b45309'>Agora indique un remplacement : "
                              f"{e(self.info['ReplaceBy'])}.</span>")
        else:
            lignes.append("Prix : Agora ne connaît pas cette référence.")
        # Code et prix proposés dans les champs modifiables (pas d'écrasement d'une saisie)
        if not self.champ_code.text():
            code = code_emg_propose(self.ref_agora, self.constructeur)
            self.champ_code.setText(code or '')
            self.champ_code.setPlaceholderText("aucune règle : à saisir")
        if not self.champ_prix.text() and self.info:
            vente = prix_emg(self.info, self.constructeur).vente
            self.champ_prix.setText(f"{vente:.2f}".replace('.', ',') if vente else '')
        self.ligne_fiche.setVisible(True)
        return lignes

    def _calculer_lignes(self):
        """Appareils de toutes les références lues, réunis (sans doublon)."""
        tous = [c for cas in self.cas.values() if cas for c in cas]
        self.lignes = None
        if not tous:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.lignes = lignes_appareils(
                tous, lambda a: self.familles.produits(a, self.constructeur), self._marques_connues())
        finally:
            QApplication.restoreOverrideCursor()

    # --- Import -------------------------------------------------------------------------
    def ouvrir_import(self):
        if not self.lignes or not self.lignes.lignes:
            return
        from src.core.import_manager import ImportConfiguration, ImportType
        f = self.famille
        designation = self.info.get('Description') or (f.courante.designation if f and f.courante else '')
        # Données commerciales gardées pour la fiche PrestaShop / Cogilog (agora_fiche.py)
        p = prix_emg(self.info, self.constructeur) if self.info else None
        prix_saisi = _prix(self.champ_prix.text())
        regle = (p.regle if p else '') if prix_saisi == (p.vente if p else None) else "prix saisi"
        fichiers = self._fichiers_import(designation)
        if not fichiers:
            return
        # Code et prix retenus pour chaque référence importée (la fiche peut être ouverte
        # sur l'une ou l'autre) : code calculé sur la plus récente, comme convenu avec EMG
        for ref in dict.fromkeys([self.ref_agora] + [x.suggested_reference for x in fichiers]):
            self.base.noter_fiche(ref, self.constructeur, self.champ_code.text().strip(),
                                  designation, p.achat_ht if p else None, prix_saisi, regle)
        config = ImportConfiguration(
            files=fichiers, has_headers=True,
            import_type=ImportType.MULTI_FILE if len(fichiers) > 1 else ImportType.SINGLE_FILE)
        main_window = self.main_window

        def fin(results):
            if hasattr(main_window, '_on_import_complete'):
                main_window._on_import_complete(results)

        main_window.import_manager.importer_avec_dialogue(
            config, callback=fin, titre=f"Importer depuis Agora — {', '.join(f.suggested_reference for f in fichiers)}")
        self.close()
