"""
« Fiche PrestaShop et Cogilog » : la fiche de la pièce recherchée, créée sur le
site en un clic (désactivée, cover par défaut) et/ou ajoutée aux fichiers
d'import du jour (Cogilog, PrestaShop).

Tout vient des générateurs existants, sur la recherche en cours, comme les
boutons Titre, Fiche complète, Méta Title et Méta Desc (gabarits au choix) ;
code produit et prix viennent de l'import Agora de la pièce (src/ui/agora_import.py).
Le site (webservice, src/utils/prestashop/) donne les catégories, les fabricants
et les caractéristiques, et dit si une référence de la famille y est déjà.
Tout reste modifiable. Non bloquant : show() + callbacks, threads pour le réseau,
jamais exec_() (conventions du projet).
"""

import html
import os
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)
import qtawesome as qta

from src.core.logger import app_logger
from src.utils.agora.conversion import code_emg_propose, prix_emg
from src.utils.agora.fiche import (FABRICANTS_SITE, CategoriesSite, FicheSite,
                                   ajouter_aux_fichiers_du_jour, fabricant_site)
from src.utils.agora.stockage import BaseAgora
from .style_manager import StyleManager


def _prix(texte: str) -> Optional[float]:
    try:
        return round(float(texte.replace('€', '').replace(',', '.').strip()), 2) or None
    except ValueError:
        return None


def _depuis_le_cache(base: BaseAgora, reference: str) -> dict:
    """Pièce importée avant que l'import ne retienne code et prix : on les
    recalcule d'après la réponse d'Agora gardée en cache (aucun appel)."""
    trouve = base.info_en_cache(reference)
    if not trouve:
        return {}
    constructeur, info = trouve
    p = prix_emg(info, constructeur)
    return {'constructeur': constructeur, 'code': code_emg_propose(reference, constructeur) or '',
            'prix_ttc': p.vente, 'regle_prix': p.regle}


class TacheFond(QThread):
    """Une fonction hors du thread principal (appels au site)."""
    termine = pyqtSignal(object, str)          # résultat, erreur

    def __init__(self, fonction: Callable, parent=None):
        super().__init__(parent)
        self.fonction = fonction

    def run(self):
        try:
            resultat, erreur = self.fonction(), ''
        except Exception as e:
            app_logger.warning(f"[Site] {type(e).__name__} : {e}")
            resultat, erreur = None, str(e) or type(e).__name__
        self.termine.emit(resultat, erreur)


# Tâches en cours, gardées ici et sans parent : fermer la fenêtre pendant un appel ne
# détruit pas le thread (« QThread: Destroyed while thread is still running » arrête
# l'application) ; la suite n'est pas appelée si la fenêtre n'existe plus.
_TACHES = set()


def lancer_tache(fonction: Callable, suite: Callable, fenetre=None) -> TacheFond:
    from PyQt5 import sip
    tache = TacheFond(fonction)

    def _suite(resultat, erreur):
        if fenetre is not None and sip.isdeleted(fenetre):
            return
        try:
            suite(resultat, erreur)
        except Exception:                      # jamais d'exception hors d'un slot (arrêt de l'appli)
            app_logger.error("[Site] suite d'une tâche en échec", exc_info=True)

    tache.termine.connect(_suite)
    tache.finished.connect(lambda: _TACHES.discard(tache))
    _TACHES.add(tache)
    tache.start()
    return tache


def _famille(main_window, reference: str) -> List[str]:
    """La référence, ses anciennes références et ses équivalentes (base de l'outil)."""
    refs = [reference]
    db = getattr(main_window, 'db_manager', None)
    for lire in ('get_all_predecessors', 'get_equivalents'):
        try:
            refs += [r for r in (getattr(db, lire)(reference) or []) if r not in refs]
        except Exception as e:
            app_logger.warning(f"[Site] {lire}({reference}) : {e}")
    return refs


def ouvrir_fiche_site(main_window):
    """Prépare la fiche de la recherche en cours ; les refus (pas de recherche,
    libellé manquant…) sont signalés par les services, comme pour les boutons."""
    relancer = lambda: ouvrir_fiche_site(main_window)
    terme = getattr(getattr(main_window, 'search_input', None), 'text', lambda: '')()
    app_logger.info(f"[Fiche site] ouverture pour « {terme} »")
    ctx_titre = main_window.titre_produit_service.contexte(interactif=True, relancer=relancer)
    if not ctx_titre:
        app_logger.info(f"[Fiche site] titre refusé : {getattr(main_window.seo_service, 'raison_refus', '')}")
        return None
    ctx_fiche = main_window.fiche_produit_service.contexte(interactif=True)
    if not ctx_fiche:
        app_logger.info(f"[Fiche site] fiche refusée : {getattr(main_window.seo_service, 'raison_refus', '')}")
        return None
    donnees = ctx_titre['donnees']
    seo = main_window.seo_service
    reference = donnees['reference']
    base = BaseAgora()
    agora = base.fiche(reference) or _depuis_le_cache(base, reference)
    code = agora.get('code') or code_emg_propose(reference, -1) or ''
    fiche = FicheSite(
        code=code,
        nom=main_window.titre_produit_service.rendre(ctx_titre, None)['html'],
        libelle=donnees.get('description') or '',
        reference=reference,
        prix_ttc=agora.get('prix_ttc'),
        categorie=CategoriesSite().proposer(donnees.get('description') or '',
                                            donnees.get('type_appareil') or ''),
        fabricant=fabricant_site(code, agora.get('constructeur')),
        description=main_window.fiche_produit_service.rendre(ctx_fiche, None)['html'],
        meta_title=seo.calculer_meta_title(donnees)['title'],
        meta_description=seo.calculer_meta_description(donnees)['description'],
    )
    dialogue = FicheSiteDialog(main_window, fiche, agora, ctx_titre, ctx_fiche,
                               type_appareil=donnees.get('type_appareil') or '',
                               famille=_famille(main_window, reference))
    dialogue.show()
    dialogue.raise_()
    dialogue.activateWindow()
    app_logger.info(f"[Fiche site] fenêtre ouverte pour {reference} (code {code or '—'})")
    return dialogue


class FicheSiteDialog(QDialog):
    def __init__(self, main_window, fiche: FicheSite, agora: dict, ctx_titre=None, ctx_fiche=None,
                 type_appareil: str = '', famille: Optional[List[str]] = None, site=None):
        super().__init__(main_window)
        self.main_window, self.fiche, self.agora = main_window, fiche, agora
        self.ctx_titre, self.ctx_fiche = ctx_titre, ctx_fiche
        self.type_appareil = type_appareil
        self.famille = famille or [fiche.reference]
        self.site = site
        self.referentiels = None
        self.doublons = []
        self.cible_maj = None               # fiche déjà en ligne à mettre à jour (doublon)
        self.id_cree: Optional[int] = None
        self.dossier = ''
        self.setWindowTitle(f"Fiche PrestaShop et Cogilog — {fiche.reference}")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1040, 700)
        self.setMinimumSize(900, 620)
        self._construire()
        self._charger_site()

    # --- Interface ------------------------------------------------------------------
    @staticmethod
    def _legende(texte: str) -> QLabel:
        legende = QLabel(texte.upper())
        legende.setStyleSheet(StyleManager.LEGENDE_SECTION)
        return legende

    @staticmethod
    def _champ(libelle: str, widget, aide: Optional[QWidget] = None) -> QWidget:
        """Libellé au-dessus du champ (colonne étroite : pas de QFormLayout)."""
        bloc = QWidget()
        pose = QVBoxLayout(bloc)
        pose.setContentsMargins(0, 0, 0, 0)
        pose.setSpacing(2)
        pose.addWidget(QLabel(libelle))
        pose.addWidget(widget)
        if aide is not None:
            pose.addWidget(aide)
        return bloc

    @staticmethod
    def _duo(gauche: QWidget, droite: QWidget) -> QWidget:
        bloc = QWidget()
        pose = QHBoxLayout(bloc)
        pose.setContentsMargins(0, 0, 0, 0)
        pose.setSpacing(10)
        pose.addWidget(gauche, 1)
        pose.addWidget(droite, 1)
        return bloc

    @staticmethod
    def _note(texte: str = '') -> QLabel:
        note = QLabel(texte)
        note.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        return note

    def _construire(self):
        f = self.fiche
        racine = QVBoxLayout(self)
        racine.setContentsMargins(14, 12, 14, 12)
        racine.setSpacing(8)

        titre = QLabel(f"<span style='font-size:16px;font-weight:600'>Fiche PrestaShop et Cogilog</span>"
                       f"  <span style='color:#6c757d'>pour la pièce {html.escape(f.reference)}</span>")
        racine.addWidget(titre)
        if not self.agora:
            info = QLabel("Pièce non importée depuis Agora : code et prix à saisir.")
            info.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
            racine.addWidget(info)
        racine.addWidget(self._construire_bandeau())

        corps = QHBoxLayout()
        corps.setSpacing(18)
        corps.addLayout(self._construire_formulaire(), 5)
        corps.addLayout(self._construire_apercu(), 5)
        racine.addLayout(corps, 1)

        for champ in (self.champ_nom, self.champ_meta_title, self.champ_meta_description):
            champ.setCursorPosition(0)          # le début du texte visible, pas la fin
        for champ in (self.champ_code, self.champ_nom, self.champ_meta_title, self.champ_meta_description,
                      self.champ_prix):
            champ.textChanged.connect(self._maj_apercu)
        for champ in (self.champ_categorie, self.champ_fabricant, self.champ_type_piece):
            champ.currentTextChanged.connect(lambda *_: self._maj_apercu())
        self._maj_ht()
        self._maj_resume()
        self._maj_apercu()

        self.etat = QLabel("La fiche est créée désactivée, avec la cover par défaut, en attendant les photos.")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        racine.addWidget(self.etat)
        racine.addLayout(self._construire_pied())

    def _construire_bandeau(self) -> QFrame:
        """État du site (connexion, doublon, erreur) : icône + phrase, jamais la couleur seule."""
        self.bandeau = QFrame()
        self.bandeau.setObjectName("bandeauEtat")
        pose = QHBoxLayout(self.bandeau)
        pose.setContentsMargins(10, 6, 10, 6)
        self.icone_etat_site = QLabel()
        pose.addWidget(self.icone_etat_site)
        self.etat_site = QLabel()
        self.etat_site.setWordWrap(True)
        pose.addWidget(self.etat_site, 1)
        self.bouton_reessayer = QPushButton("Réessayer")
        self.bouton_reessayer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_reessayer.setVisible(False)
        self.bouton_reessayer.clicked.connect(self._reessayer)
        pose.addWidget(self.bouton_reessayer)
        self._afficher_etat_site('attente', "Site : connexion…")
        return self.bandeau

    def _afficher_etat_site(self, niveau: str, texte: str, reessayer: bool = False):
        fond, couleur, icone = StyleManager.BANDEAUX_ETAT[niveau]
        self.bandeau.setStyleSheet(StyleManager.bandeau_etat(niveau))
        self.icone_etat_site.setPixmap(qta.icon(icone, color=couleur).pixmap(16, 16))
        self.etat_site.setStyleSheet(f"color: {couleur}; font-size: 12px; background: transparent;")
        self.etat_site.setText(texte)
        self.bouton_reessayer.setVisible(reessayer)

    def _reessayer(self):
        self._afficher_etat_site('attente', "Site : connexion…")
        self._charger_site()

    def _construire_formulaire(self) -> QVBoxLayout:
        f = self.fiche
        colonne = QVBoxLayout()
        colonne.setSpacing(6)
        self.champ_code = QLineEdit(f.code)
        self.champ_code.setToolTip("Référence PrestaShop = code Cogilog (Données → Règles des codes produit)")
        self.champ_nom = QLineEdit(f.nom)
        config = getattr(self.main_window, 'export_config_service', None)
        self.gabarit_titre = self._choix_gabarit(
            config.get_titre_profile_names() if config else [],
            config.get_default_titre_profile_name() if config else '', self._maj_titre)
        self.gabarit_fiche = self._choix_gabarit(
            config.get_fiche_profile_names() if config else [],
            config.get_default_fiche_profile_name() if config else '', self._maj_description)
        self.champ_categorie = self._choix_libre([''] + CategoriesSite().categories, f.categorie)
        self.champ_categorie.currentTextChanged.connect(lambda *_: self._proposer_type_piece())
        self.champ_fabricant = self._choix_libre([''] + sorted(set(FABRICANTS_SITE.values())), f.fabricant)
        self.champ_type_piece = self._choix_libre([''], '')
        self.champ_type_piece.setToolTip("Caractéristique « Type de pièce » du site (proposée d'après la catégorie)")
        self.libelle_type_appareil = QLabel(self.type_appareil or "— (type d'appareil inconnu)")
        self.champ_prix = QLineEdit(f"{f.prix_ttc:.2f}".replace('.', ',') if f.prix_ttc else '')
        self.champ_prix.setMaximumWidth(110)
        self.champ_prix.textChanged.connect(self._maj_ht)
        self.prix_ht = self._note()
        ligne_prix = QWidget()
        pose_prix = QHBoxLayout(ligne_prix)
        pose_prix.setContentsMargins(0, 0, 0, 0)
        pose_prix.addWidget(self.champ_prix)
        pose_prix.addWidget(self.prix_ht, 1)
        self.champ_meta_title = QLineEdit(f.meta_title)
        self.champ_meta_description = QLineEdit(f.meta_description)
        self.compteur_meta_title = self._note()
        self.compteur_meta_description = self._note()

        colonne.addWidget(self._legende("Identité"))
        colonne.addWidget(self._duo(self._champ("Code produit (PrestaShop = Cogilog)", self.champ_code),
                                    self._champ("Gabarit du nom", self.gabarit_titre)))
        colonne.addWidget(self._champ("Nom de la fiche", self.champ_nom))
        colonne.addWidget(self._legende("Classement sur le site"))
        colonne.addWidget(self._duo(self._champ("Catégorie", self.champ_categorie),
                                    self._champ("Fabricant", self.champ_fabricant)))
        colonne.addWidget(self._duo(self._champ("Type d'appareil", self.libelle_type_appareil),
                                    self._champ("Type de pièce", self.champ_type_piece)))
        colonne.addWidget(self._legende("Prix"))
        colonne.addWidget(self._champ("Prix TTC", ligne_prix))
        colonne.addWidget(self._legende("Référencement"))
        colonne.addWidget(self._champ("Méta title", self.champ_meta_title, self.compteur_meta_title))
        colonne.addWidget(self._champ("Méta description", self.champ_meta_description,
                                      self.compteur_meta_description))
        colonne.addStretch(1)
        return colonne

    def _construire_apercu(self) -> QVBoxLayout:
        """Ce que donnera la fiche : carte produit, extrait Google, description rendue."""
        colonne = QVBoxLayout()
        colonne.setSpacing(6)
        colonne.addWidget(self._legende("Aperçu sur le site"))
        carte = QFrame()
        carte.setObjectName("carteApercu")
        carte.setStyleSheet(StyleManager.CARTE_APERCU)
        pose = QHBoxLayout(carte)
        pose.setContentsMargins(12, 12, 12, 12)
        cover = QLabel("Cover par\ndéfaut")
        cover.setAlignment(Qt.AlignCenter)
        cover.setFixedSize(84, 84)
        cover.setStyleSheet(StyleManager.COVER_APERCU)
        pose.addWidget(cover)
        texte = QVBoxLayout()
        texte.setSpacing(2)
        self.apercu_nom = QLabel()
        self.apercu_nom.setWordWrap(True)
        self.apercu_nom.setTextFormat(Qt.RichText)
        self.apercu_classement = self._note()
        self.apercu_prix = QLabel()
        self.apercu_statut = QLabel("Sera créée désactivée, avec la cover par défaut")
        self.apercu_statut.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
        for w in (self.apercu_nom, self.apercu_classement, self.apercu_prix, self.apercu_statut):
            texte.addWidget(w)
        pose.addLayout(texte, 1)
        colonne.addWidget(carte)

        colonne.addWidget(self._legende("Aperçu Google"))
        google = QFrame()
        google.setObjectName("carteApercu")
        google.setStyleSheet(StyleManager.CARTE_APERCU)
        pose_g = QVBoxLayout(google)
        pose_g.setContentsMargins(12, 10, 12, 10)
        pose_g.setSpacing(1)
        self.apercu_url = QLabel("www.1001pieces.com")
        self.apercu_url.setStyleSheet("color: #188038; font-size: 11px;")
        self.apercu_meta_title = QLabel()
        self.apercu_meta_title.setStyleSheet("color: #1a0dab; font-size: 15px;")
        self.apercu_meta_description = QLabel()
        self.apercu_meta_description.setWordWrap(True)
        self.apercu_meta_description.setStyleSheet("color: #4d5156; font-size: 12px;")
        for w in (self.apercu_url, self.apercu_meta_title, self.apercu_meta_description):
            pose_g.addWidget(w)
        colonne.addWidget(google)

        entete = QHBoxLayout()
        entete.addWidget(self._legende("Description"))
        entete.addStretch(1)
        entete.addWidget(QLabel("Gabarit"))
        entete.addWidget(self.gabarit_fiche)
        colonne.addLayout(entete)
        self.apercu_description = QTextBrowser()
        self.apercu_description.setOpenLinks(False)
        self.apercu_description.setStyleSheet(StyleManager.TEXTE_APERCU_HTML)
        self.resume_description = self._note()
        colonne.addWidget(self.apercu_description, 1)
        colonne.addWidget(self.resume_description)
        return colonne

    def _construire_pied(self) -> QHBoxLayout:
        pied = QHBoxLayout()
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        pied.addWidget(fermer)
        pied.addStretch(1)
        self.bouton_dossier = QPushButton("Ouvrir le dossier")
        self.bouton_dossier.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_dossier.setVisible(False)
        self.bouton_dossier.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.dossier)))
        fichiers = QPushButton("Ajouter aux fichiers d'import du jour")
        fichiers.setToolTip("Ajoute la fiche aux fichiers d'import Cogilog et PrestaShop du jour")
        fichiers.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fichiers.clicked.connect(self.ajouter)
        self.bouton_creer = QPushButton("Créer sur PrestaShop")
        self.bouton_creer.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        self.bouton_creer.setEnabled(False)
        self.bouton_creer.clicked.connect(self._action_site)
        for b in (self.bouton_dossier, fichiers, self.bouton_creer):
            pied.addWidget(b)
        return pied

    def _maj_apercu(self):
        """Aperçus recalculés à chaque frappe : carte produit et extrait Google."""
        nom = self.champ_nom.text().strip()
        self.apercu_nom.setText(f"<b>{nom}</b>" if nom else "<i>nom à saisir</i>")
        classement = [t for t in (self.champ_categorie.currentText().strip(),
                                  self.champ_fabricant.currentText().strip(),
                                  self.champ_type_piece.currentText().strip()) if t]
        code = self.champ_code.text().strip()
        self.apercu_classement.setText("  ·  ".join(classement + [f"Code {html.escape(code)}" if code else "code à saisir"]))
        ttc = _prix(self.champ_prix.text())
        self.apercu_prix.setText(
            f"<span style='font-size:18px;font-weight:600'>{ttc:.2f} € TTC</span>".replace('.', ',') +
            f"  <span style='color:#6c757d'>{ttc / 1.2:.2f} € HT</span>".replace('.', ',')
            if ttc else "<span style='color:#b45309'>prix à saisir</span>")
        titre, desc = self.champ_meta_title.text().strip(), self.champ_meta_description.text().strip()
        self.apercu_meta_title.setText(html.escape(titre) or "méta title à saisir")
        self.apercu_meta_description.setText(html.escape(desc) or "méta description à saisir")
        self.compteur_meta_title.setText(f"{len(titre)} caractères")
        self.compteur_meta_description.setText(f"{len(desc)} caractères")

    @staticmethod
    def _choix_libre(valeurs, courant: str) -> QComboBox:
        choix = QComboBox()
        choix.setEditable(True)
        choix.setMinimumContentsLength(14)
        choix.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        choix.addItems(list(valeurs))
        choix.setCurrentText(courant or '')
        return choix

    @staticmethod
    def _choix_gabarit(noms, defaut, rappel) -> QComboBox:
        choix = QComboBox()
        choix.addItems(list(noms))
        if defaut:
            choix.setCurrentText(defaut)
        choix.currentTextChanged.connect(lambda *_: rappel())
        return choix

    def _maj_titre(self):
        if self.ctx_titre is not None:
            self.champ_nom.setText(self.main_window.titre_produit_service.rendre(
                self.ctx_titre, self.gabarit_titre.currentText() or None)['html'])
            self.champ_nom.setCursorPosition(0)

    def _maj_description(self):
        if self.ctx_fiche is not None:
            self.fiche.description = self.main_window.fiche_produit_service.rendre(
                self.ctx_fiche, self.gabarit_fiche.currentText() or None)['html']
        self._maj_resume()

    def _maj_resume(self):
        regle = f" · prix : {html.escape(self.agora['regle_prix'])}" if self.agora.get('regle_prix') else ''
        self.resume_description.setText(f"{len(self.fiche.description)} caractères{regle}")
        self.apercu_description.setHtml(self.fiche.description)

    def _maj_ht(self):
        ttc = _prix(self.champ_prix.text())
        self.prix_ht.setText(f"soit {ttc / 1.2:.2f} € HT".replace('.', ',') if ttc else "prix à saisir")

    def _lancer(self, fonction: Callable, suite: Callable):
        lancer_tache(fonction, suite, self)

    # --- Site : référentiels et anti-doublon -----------------------------------------------
    def _charger_site(self):
        try:
            if self.site is None:
                from src.utils.prestashop.site import SitePrestaShop
                self.site = SitePrestaShop()
        except Exception as e:
            self._afficher_etat_site('nonconf',
                                     f"Site non configuré : {e}. Seuls les fichiers d'import sont possibles.")
            return
        from src.utils.agora.codes import code_produit
        constructeur = self.agora.get('constructeur')
        refs = list(self.famille) + [self.fiche.code] + [
            c for c in (code_produit(r, constructeur) for r in self.famille) if c]
        site = self.site

        def lire():
            return site.referentiels(), site.produits_existants(refs)
        self._lancer(lire, self._site_lu)

    def _site_lu(self, resultat, erreur: str):
        env = self.site.client.environnement if self.site else ''
        if erreur:
            self._afficher_etat_site('erreur', f"Site ({env}) injoignable : {erreur}. "
                                               "Seuls les fichiers d'import sont possibles.", reessayer=True)
            return
        self.referentiels, self.doublons = resultat
        r = self.referentiels
        for champ, valeurs in ((self.champ_categorie, sorted(r.categories)),
                               (self.champ_fabricant, sorted(r.fabricants)),
                               (self.champ_type_piece, sorted(r.types_piece))):
            courant = champ.currentText()
            champ.blockSignals(True)
            champ.clear()
            champ.addItems([''] + valeurs)
            champ.setCurrentText(courant)
            champ.blockSignals(False)
        type_site = next((v for v, i in r.types_appareil.items()
                          if i == r.id_type_appareil(self.type_appareil)), '')
        self.libelle_type_appareil.setText(type_site or f"{self.type_appareil or '—'} (absent du site : non renseigné)")
        self.bouton_creer.setText(f"Créer sur PrestaShop ({env})")
        if self.doublons:
            liste = ', '.join(f"{html.escape(p.reference)} (n° {p.id}, {'active' if p.actif else 'désactivée'})"
                              for p in self.doublons)
            self._afficher_etat_site('doublon', f"<b>Déjà sur le site ({env})</b> : {liste}. "
                                                "Vérifiez avant de créer ou de mettre à jour une fiche.")
            # Une fiche du même code, sinon le seul doublon : on propose de la mettre à jour
            from src.utils.prestashop.site import cle
            self.cible_maj = next((p for p in self.doublons if cle(p.reference) == cle(self.fiche.code)),
                                  self.doublons[0] if len(self.doublons) == 1 else None)
            if self.cible_maj is not None:
                self.bouton_creer.setText(f"Mettre à jour la fiche n° {self.cible_maj.id} ({env})")
                self.apercu_statut.setText("Fiche déjà en ligne : mise à jour bloc par bloc, "
                                           "activation, images et stock inchangés")
        else:
            self._afficher_etat_site('ok', f"Site ({env}) : aucune fiche pour "
                                           f"{html.escape(', '.join(self.famille[:6]))}"
                                           f"{'…' if len(self.famille) > 6 else ''}.")
        self.bouton_creer.setEnabled(True)
        self._maj_apercu()
        self._proposer_type_piece()

    def _proposer_type_piece(self):
        if self.referentiels is None or self.champ_type_piece.currentText():
            return
        from src.utils.prestashop.site import cle
        mot = cle((self.fiche.libelle or '').split(' ')[0])
        selon_libelle = next((v for v in self.referentiels.types_piece if mot and cle(v) == mot), None) or \
            next((v for v in self.referentiels.types_piece if mot and len(mot) >= 4 and cle(v).startswith(mot)), None)
        if selon_libelle:
            self.champ_type_piece.setCurrentText(selon_libelle)
            return
        id_cat = self.referentiels.id_categorie(self.champ_categorie.currentText().strip())
        if id_cat:
            site = self.site
            self._lancer(lambda: site.type_piece_propose(id_cat),
                         lambda valeur, err: (not err and valeur and not self.champ_type_piece.currentText()
                                              and self.champ_type_piece.setCurrentText(valeur)))

    # --- Fiche saisie ---------------------------------------------------------------------
    def _relever(self) -> FicheSite:
        f = self.fiche
        f.code = self.champ_code.text().strip()
        f.nom = self.champ_nom.text().strip()
        f.categorie = self.champ_categorie.currentText().strip()
        f.fabricant = self.champ_fabricant.currentText().strip()
        f.prix_ttc = _prix(self.champ_prix.text())
        f.meta_title = self.champ_meta_title.text().strip()
        f.meta_description = self.champ_meta_description.text().strip()
        return f

    def _signaler(self, texte: str, style=None):
        self.etat.setText(texte)
        self.etat.setStyleSheet(style or StyleManager.TEXTE_SECONDAIRE)

    def _historique(self, texte: str):
        historique = getattr(self.main_window, 'user_interaction_service', None)
        if historique is not None:
            historique.add_to_history(texte)

    # --- Création ou mise à jour sur le site ----------------------------------------------------
    def _action_site(self):
        if self.cible_maj is not None:
            self.mettre_a_jour()
        else:
            self.creer()

    def mettre_a_jour(self):
        """Fiche déjà en ligne : avant / après bloc par bloc (src/ui/prestashop_maj.py)."""
        f, r = self._relever(), self.referentiels
        if r is None or self.cible_maj is None:
            return
        from .prestashop_maj import MiseAJourFicheDialog
        historique = getattr(self.main_window, 'user_interaction_service', None)
        MiseAJourFicheDialog(self, self.site, self.cible_maj.id, f, r.id_categorie(f.categorie),
                             historique.add_to_history if historique is not None else None).show()

    def creer(self):
        f, r = self._relever(), self.referentiels
        if r is None:
            return
        manques = [m for m in ("code produit", "nom", "prix") if m in f.manques()]
        id_cat = r.id_categorie(f.categorie)
        if not id_cat:
            manques.append("catégorie du site")
        if manques:
            self._signaler(f"À compléter avant de créer la fiche : {', '.join(manques)}.",
                           StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        if self.site.client.environnement == 'production':
            from src.utils.boites import demander_oui_non
            demander_oui_non(self, "Créer sur le site en production",
                             f"Créer la fiche {f.code} sur www.1001pieces.com (désactivée) ?",
                             lambda: self._creer(f, id_cat))
        else:
            self._creer(f, id_cat)

    def _creer(self, f: FicheSite, id_cat: int):
        from src.utils.prestashop.site import CARACTERISTIQUE_TYPE_APPAREIL, CARACTERISTIQUE_TYPE_PIECE
        r = self.referentiels
        caracteristiques = []
        if r.id_type_appareil(self.type_appareil):
            caracteristiques.append((CARACTERISTIQUE_TYPE_APPAREIL, r.id_type_appareil(self.type_appareil)))
        type_piece = self.champ_type_piece.currentText().strip()
        if type_piece in r.types_piece:
            caracteristiques.append((CARACTERISTIQUE_TYPE_PIECE, r.types_piece[type_piece]))
        chemin_cover = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                    'data', 'cover_par_defaut.jpg')
        cover = open(chemin_cover, 'rb').read() if os.path.exists(chemin_cover) else None
        site, id_fab = self.site, r.id_fabricant(f.fabricant)
        self.bouton_creer.setEnabled(False)
        self._signaler("Création de la fiche…")
        app_logger.info(f"[Site] création de la fiche {f.code} ({self.site.client.environnement})")
        self._lancer(lambda: site.creer_fiche(f, id_cat, id_fab, caracteristiques, cover),
                     lambda resultat, err: self._cree(f, resultat, err))

    def _cree(self, f: FicheSite, resultat, erreur: str):
        env = self.site.client.environnement
        if erreur:
            self.bouton_creer.setEnabled(True)
            self._signaler(f"Fiche non créée : {erreur}", StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        id_produit, erreur_cover = resultat
        self.id_cree = id_produit
        self.bouton_creer.setText(f"Créée : n° {id_produit}")
        if erreur_cover:
            self._signaler(f"Fiche {f.code} créée sur le site ({env}), produit n° {id_produit}, désactivée, "
                           f"mais sans cover : {erreur_cover}. Ajoutez-la dans le back-office.",
                           StyleManager.TEXTE_AVERTISSEMENT)
        else:
            self._signaler(f"Fiche {f.code} créée sur le site ({env}), produit n° {id_produit}, désactivée "
                           "avec la cover par défaut. Pensez aux compatibilités (Exporter CSV, EveryParts).")
        self._historique(f"Fiche créée sur PrestaShop ({env}) : {f.code} ({f.reference}), "
                         f"produit n° {id_produit}" + (" — sans cover" if erreur_cover else "")
                         + f"\n==> {f.nom}")

    # --- Fichiers d'import ------------------------------------------------------------------
    def ajouter(self):
        f = self._relever()
        if not f.code:
            self._signaler("Le code produit est obligatoire : c'est lui qui relie Cogilog et PrestaShop.",
                           StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        from src.services.export_config_service import resolve_output_dir
        self.dossier = resolve_output_dir(getattr(self.main_window, 'export_config_service', None))
        try:
            r = ajouter_aux_fichiers_du_jour(f, self.dossier)
        except OSError as e:
            app_logger.error(f"[Agora] fiche {f.code} non écrite : {e}")
            self._signaler(f"Écriture impossible : {e}", StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        manques = f.manques()
        self._signaler(f"Fiche {f.code} ajoutée aux fichiers d'import ({r['fiches']} fiche(s) aujourd'hui)"
                       + (f" — à compléter : {', '.join(manques)}" if manques else "") + ".",
                       StyleManager.TEXTE_AVERTISSEMENT if manques else None)
        self.bouton_dossier.setVisible(True)
        self._historique(f"Fiche PrestaShop / Cogilog : {f.code} ({f.reference})\n==> {f.nom}\n"
                         f"==> {r['prestashop']}\n==> {r['cogilog']}")
